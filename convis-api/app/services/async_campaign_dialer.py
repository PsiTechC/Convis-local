"""
Async Campaign Dialer Service
Replaces threading with asyncio for better performance and resource management
"""
import logging
import os
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

import pytz
import redis.asyncio as aioredis
from bson import ObjectId
from twilio.rest import Client

from app.config.async_database import AsyncDatabase
from app.config.settings import settings
from app.utils.twilio_helpers import decrypt_twilio_credentials

logger = logging.getLogger(__name__)


class AsyncCampaignDialer:
    """
    Async service for managing campaign calls.

    Key improvements over sync version:
    1. Uses asyncio.create_task() instead of threading.Thread
    2. Uses asyncio.sleep() instead of time.sleep()
    3. Uses Motor async MongoDB driver
    4. Uses redis.asyncio for non-blocking Redis operations
    """

    def __init__(self):
        # Redis client for distributed locking (async) - lazy init
        self._redis_client = None
        self._redis_url = settings.redis_url or os.getenv("REDIS_URL", "redis://localhost:6379")

        # Default Twilio client - LAZY INITIALIZATION to avoid blocking startup
        self._default_twilio_client = None
        self._twilio_initialized = False
        self._user_twilio_clients: Dict[str, Client] = {}

        # Base URL for TwiML
        configured_base_url = settings.base_url or settings.api_base_url
        self.base_url = configured_base_url or os.getenv("BASE_URL", "https://your-domain.com")

        self.twiml_url = f"{self.base_url}/api/twilio-webhooks/outbound-call"
        self.status_callback = f"{self.base_url}/api/twilio-webhooks/call-status"
        self.recording_callback = f"{self.base_url}/api/twilio-webhooks/recording"

        self.last_error: Optional[str] = None

        # Track active monitoring tasks
        self._active_tasks: Dict[str, asyncio.Task] = {}

    @property
    def redis_client(self):
        """Lazy initialization of Redis client."""
        if self._redis_client is None:
            self._redis_client = aioredis.from_url(self._redis_url, decode_responses=True)
        return self._redis_client

    @property
    def default_twilio_client(self):
        """Lazy initialization of default Twilio client."""
        if not self._twilio_initialized:
            account_sid = settings.twilio_account_sid or os.getenv("TWILIO_ACCOUNT_SID")
            auth_token = settings.twilio_auth_token or os.getenv("TWILIO_AUTH_TOKEN")
            if account_sid and auth_token:
                self._default_twilio_client = Client(account_sid, auth_token)
            self._twilio_initialized = True
        return self._default_twilio_client

    async def acquire_lock(self, campaign_id: str, ttl: int = 180) -> bool:
        """Acquire a distributed lock for a campaign (async)."""
        lock_key = f"lock:campaign:{campaign_id}"
        return await self.redis_client.set(lock_key, "1", nx=True, ex=ttl)

    async def release_lock(self, campaign_id: str):
        """Release the lock for a campaign (async)."""
        lock_key = f"lock:campaign:{campaign_id}"
        await self.redis_client.delete(lock_key)

    def is_within_working_window(self, lead: Dict[str, Any], working_window: Dict[str, Any]) -> bool:
        """Check if current time is within the working window for a lead."""
        try:
            lead_tz = lead.get("timezone", working_window.get("timezone", "America/New_York"))
            tz = pytz.timezone(lead_tz)
            now = datetime.now(tz)

            if now.weekday() not in working_window.get("days", []):
                return False

            start_time = working_window.get("start", "09:00")
            end_time = working_window.get("end", "17:00")

            start_hour, start_min = map(int, start_time.split(":"))
            end_hour, end_min = map(int, end_time.split(":"))

            start_dt = now.replace(hour=start_hour, minute=start_min, second=0, microsecond=0)
            end_dt = now.replace(hour=end_hour, minute=end_min, second=0, microsecond=0)

            return start_dt <= now <= end_dt

        except Exception as e:
            logger.error(f"Error checking working window: {e}")
            return False

    async def get_next_lead(
        self,
        campaign_id: str,
        ignore_window: bool = False,
        ignore_attempt_limit: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """Get the next lead to call for a campaign (async)."""
        try:
            db = await AsyncDatabase.get_db()
            campaigns_collection = db["campaigns"]
            leads_collection = db["leads"]

            campaign = await campaigns_collection.find_one({"_id": ObjectId(campaign_id)})
            if not campaign:
                logger.error(f"Campaign {campaign_id} not found")
                return None

            query = {
                "campaign_id": ObjectId(campaign_id),
                "status": "queued"
            }

            sort = [("order_index", 1), ("_id", 1)]
            working_window = campaign.get("working_window", {})

            # Find leads matching the query
            cursor = leads_collection.find(query).sort(sort).limit(10)
            leads = await cursor.to_list(length=10)

            for lead in leads:
                if ignore_window:
                    logger.info(f"Lead {lead['_id']} selected for test call (ignoring working window)")
                    return lead

                if self.is_within_working_window(lead, working_window):
                    return lead

            logger.info(f"No available leads for campaign {campaign_id}")
            return None

        except Exception as e:
            logger.error(f"Error getting next lead: {e}")
            return None

    async def place_call(self, campaign_id: str, lead_id: str) -> Optional[str]:
        """Place an outbound call to a lead (async)."""
        try:
            db = await AsyncDatabase.get_db()
            campaigns_collection = db["campaigns"]
            leads_collection = db["leads"]
            call_attempts_collection = db["call_attempts"]
            provider_connections_collection = db["provider_connections"]

            # Get campaign and lead in parallel
            campaign_task = campaigns_collection.find_one({"_id": ObjectId(campaign_id)})
            lead_task = leads_collection.find_one({"_id": ObjectId(lead_id)})

            campaign, lead = await asyncio.gather(campaign_task, lead_task)

            if not campaign or not lead:
                logger.error("Campaign or lead not found")
                self.last_error = "Campaign or lead record is missing in the database."
                return None

            caller_id = campaign.get("caller_id")
            to_number = lead.get("e164")

            if not caller_id:
                self.last_error = "Campaign is missing a caller ID."
                return None

            if not to_number:
                self.last_error = "Lead does not have a valid phone number in E.164 format."
                return None

            twilio_client = await self._get_twilio_client_for_campaign(campaign, provider_connections_collection)
            if not twilio_client:
                self.last_error = "No active Twilio credentials found."
                return None

            # Update lead status to calling
            await leads_collection.update_one(
                {"_id": ObjectId(lead_id)},
                {
                    "$set": {"status": "calling", "updated_at": datetime.utcnow()},
                    "$inc": {"attempts": 1}
                }
            )

            assistant_id = campaign.get("assistant_id", "")

            twiml_url_complete = f"{self.twiml_url}?leadId={lead_id}&campaignId={campaign_id}&assistantId={assistant_id}"
            status_cb_complete = f"{self.status_callback}?leadId={lead_id}&campaignId={campaign_id}"
            recording_cb_complete = f"{self.recording_callback}?leadId={lead_id}&campaignId={campaign_id}"

            logger.info(f"[ASYNC_PLACE_CALL] Initiating call for campaign {campaign_id}, lead {lead_id}")

            # Run Twilio SDK call in executor (it's blocking)
            loop = asyncio.get_event_loop()
            call = await loop.run_in_executor(
                None,
                lambda: twilio_client.calls.create(
                    to=to_number,
                    from_=caller_id,
                    url=twiml_url_complete,
                    status_callback=status_cb_complete,
                    status_callback_event=["initiated", "ringing", "answered", "completed", "busy", "no-answer", "failed", "canceled"],
                    status_callback_method="POST",
                    record="true",
                    recording_status_callback=recording_cb_complete,
                    recording_status_callback_method="POST",
                    timeout=30
                )
            )

            logger.info(f"[ASYNC_PLACE_CALL] SUCCESS - Call SID: {call.sid}")

            # Create call attempt record
            attempt_num = lead.get("attempts", 1)
            await call_attempts_collection.insert_one({
                "campaign_id": ObjectId(campaign_id),
                "lead_id": ObjectId(lead_id),
                "attempt": attempt_num,
                "call_sid": call.sid,
                "status": "initiated",
                "started_at": datetime.utcnow(),
                "ended_at": None,
                "recording_url": None,
                "transcript": None,
                "analysis": None,
                "duration": None
            })

            # Update lead with call SID
            await leads_collection.update_one(
                {"_id": ObjectId(lead_id)},
                {"$set": {"last_call_sid": call.sid}}
            )

            # Start background monitor using asyncio task (instead of threading)
            task = asyncio.create_task(
                self._monitor_and_trigger_next(
                    call.sid, campaign_id, lead_id,
                    campaigns_collection, leads_collection, call_attempts_collection
                )
            )
            self._active_tasks[call.sid] = task
            logger.info(f"[ASYNC_MONITOR] Started async monitor task for call {call.sid}")

            self.last_error = None
            return call.sid

        except Exception as e:
            logger.error(f"Error placing call: {e}")
            try:
                db = await AsyncDatabase.get_db()
                await db["leads"].update_one(
                    {"_id": ObjectId(lead_id)},
                    {"$set": {"status": "queued"}}
                )
            except Exception:
                pass

            try:
                from twilio.base.exceptions import TwilioRestException
                if isinstance(e, TwilioRestException):
                    self.last_error = f"Twilio error {e.code}: {e.msg or e.msg}"
                else:
                    self.last_error = str(e)
            except Exception:
                self.last_error = str(e)
            return None

    async def _monitor_and_trigger_next(
        self,
        call_sid: str,
        campaign_id: str,
        lead_id: str,
        campaigns_collection,
        leads_collection,
        call_attempts_collection
    ):
        """
        Monitor call completion and trigger next call (async version).

        Uses asyncio.sleep() instead of time.sleep() - doesn't block event loop.
        """
        try:
            await asyncio.sleep(10)  # Wait for call to start (non-blocking)

            for _ in range(90):  # Monitor for up to 3 minutes
                await asyncio.sleep(2)  # Check every 2 seconds (non-blocking)

                # Check if call has ended
                attempt = await call_attempts_collection.find_one({"call_sid": call_sid})
                if attempt and attempt.get("status") in ["completed", "busy", "no-answer", "failed", "canceled"]:
                    logger.info(f"[ASYNC_MONITOR] Call {call_sid} ended with status: {attempt.get('status')}")

                    # Update lead status
                    await leads_collection.update_one(
                        {"_id": ObjectId(lead_id)},
                        {
                            "$set": {
                                "status": attempt.get("status", "completed"),
                                "last_outcome": attempt.get("status", "completed"),
                                "updated_at": datetime.utcnow()
                            }
                        }
                    )
                    logger.info(f"[ASYNC_MONITOR] Lead {lead_id} marked as {attempt.get('status')}")

                    # Check if campaign is still running
                    campaign_check = await campaigns_collection.find_one({"_id": ObjectId(campaign_id)})
                    if campaign_check and campaign_check.get("status") == "running":
                        logger.info(f"[ASYNC_MONITOR] Campaign still running - triggering next call")

                        next_lead = await self.get_next_lead(campaign_id, ignore_window=False)
                        if next_lead:
                            logger.info(f"[ASYNC_MONITOR] Found next lead: {next_lead.get('name')} ({next_lead.get('e164')})")

                            next_call_sid = await self.place_call(campaign_id, str(next_lead["_id"]))
                            if next_call_sid:
                                logger.info(f"[ASYNC_MONITOR] SUCCESS! Next call placed: {next_call_sid}")
                            else:
                                logger.warning(f"[ASYNC_MONITOR] Failed to place next call: {self.last_error}")
                        else:
                            logger.info(f"[ASYNC_MONITOR] No more leads available - campaign complete")
                    else:
                        logger.info(f"[ASYNC_MONITOR] Campaign not running - skipping next call")

                    break  # Exit monitoring loop

        except asyncio.CancelledError:
            logger.info(f"[ASYNC_MONITOR] Monitor task cancelled for call {call_sid}")
        except Exception as e:
            logger.error(f"[ASYNC_MONITOR] Error in monitor task: {e}")
        finally:
            # Clean up task reference
            self._active_tasks.pop(call_sid, None)

    async def _get_twilio_client_for_campaign(
        self,
        campaign: Dict[str, Any],
        provider_connections_collection
    ) -> Optional[Client]:
        """Get Twilio client for campaign (async)."""
        user_id = campaign.get("user_id")
        if user_id:
            user_key = str(user_id)
            cached = self._user_twilio_clients.get(user_key)
            if cached:
                return cached

            try:
                user_obj_id = ObjectId(user_id) if not isinstance(user_id, ObjectId) else user_id
            except Exception:
                user_obj_id = None

            if user_obj_id:
                connection = await provider_connections_collection.find_one({
                    "user_id": user_obj_id,
                    "provider": "twilio"
                })
                if connection:
                    account_sid, auth_token = decrypt_twilio_credentials(connection)
                    if account_sid and auth_token:
                        try:
                            client = Client(account_sid, auth_token)
                            self._user_twilio_clients[user_key] = client
                            return client
                        except Exception as cred_error:
                            logger.error(f"Failed to initialize Twilio client: {cred_error}")

        return self.default_twilio_client

    async def dial_next(self, campaign_id: str) -> bool:
        """Dial the next lead in a campaign (with locking) - async version."""
        try:
            if not await self.acquire_lock(campaign_id):
                logger.info(f"Campaign {campaign_id} is locked, skipping")
                return False

            try:
                lead = await self.get_next_lead(campaign_id)
                if not lead:
                    logger.info(f"No leads available for campaign {campaign_id}")
                    return False

                call_sid = await self.place_call(campaign_id, str(lead["_id"]))
                return call_sid is not None

            finally:
                pass  # Lock will auto-expire

        except Exception as e:
            logger.error(f"Error in dial_next: {e}")
            await self.release_lock(campaign_id)
            return False

    async def handle_call_completed(self, campaign_id: str, lead_id: str, call_status: str):
        """Handle call completion and trigger next call (async version)."""
        try:
            db = await AsyncDatabase.get_db()
            leads_collection = db["leads"]
            campaigns_collection = db["campaigns"]

            lead_task = leads_collection.find_one({"_id": ObjectId(lead_id)})
            campaign_task = campaigns_collection.find_one({"_id": ObjectId(campaign_id)})

            lead, campaign = await asyncio.gather(lead_task, campaign_task)

            if not lead or not campaign:
                logger.warning(f"Lead or campaign not found: lead={lead_id}, campaign={campaign_id}")
                return

            now = datetime.utcnow()
            mapped_status = self._map_call_status(call_status)
            should_continue = campaign.get("status") == "running"

            update_doc = {
                "last_outcome": call_status,
                "updated_at": now,
            }

            if mapped_status == "completed":
                update_doc.update({
                    "status": "completed",
                    "next_retry_at": None,
                    "fallback_round": lead.get("fallback_round", 0)
                })
            else:
                fallback_round = lead.get("fallback_round", 0)
                terminal_status = mapped_status if mapped_status in {"busy", "no-answer"} else "failed"
                update_doc.update({
                    "status": terminal_status,
                    "next_retry_at": None,
                    "fallback_round": fallback_round
                })

            await leads_collection.update_one(
                {"_id": ObjectId(lead_id)},
                {"$set": update_doc}
            )

            await campaigns_collection.update_one(
                {"_id": ObjectId(campaign_id)},
                {"$set": {"last_call_ended_at": now}}
            )

            logger.info(f"Call completed for lead {lead_id}: status={call_status}")

            # Trigger next call using asyncio task (instead of threading)
            if should_continue:
                asyncio.create_task(self._trigger_next_call(campaign_id))
                logger.info(f"[ASYNC_INSTANT_DIAL] Async task started for next call")

        except Exception as e:
            logger.error(f"Error handling call completion: {e}")
            import traceback
            logger.error(traceback.format_exc())

            try:
                db = await AsyncDatabase.get_db()
                await db["leads"].update_one(
                    {"_id": ObjectId(lead_id)},
                    {"$set": {"status": "queued", "updated_at": datetime.utcnow()}}
                )
            except Exception:
                pass
        finally:
            try:
                await self.release_lock(campaign_id)
            except Exception:
                pass

    async def _trigger_next_call(self, campaign_id: str):
        """Trigger the next call in the campaign (async helper)."""
        try:
            logger.info(f"[ASYNC_INSTANT_DIAL] Triggering next call for campaign {campaign_id}")
            next_lead = await self.get_next_lead(campaign_id, ignore_window=False)

            if next_lead:
                logger.info(f"[ASYNC_INSTANT_DIAL] Found next lead: {next_lead.get('name')} ({next_lead.get('e164')})")
                next_call_sid = await self.place_call(campaign_id, str(next_lead["_id"]))

                if next_call_sid:
                    logger.info(f"[ASYNC_INSTANT_DIAL] Next call placed successfully: {next_call_sid}")
                else:
                    logger.warning(f"[ASYNC_INSTANT_DIAL] Failed to place next call: {self.last_error}")
            else:
                logger.info(f"[ASYNC_INSTANT_DIAL] No more leads available for campaign {campaign_id}")

        except Exception as e:
            logger.error(f"[ASYNC_INSTANT_DIAL] Error triggering next call: {e}")
            import traceback
            logger.error(traceback.format_exc())

    def _map_call_status(self, call_status: str) -> str:
        """Map Twilio call status to internal status."""
        status_map = {
            "completed": "completed",
            "answered": "completed",
            "busy": "busy",
            "no-answer": "no-answer",
            "failed": "failed",
            "canceled": "failed",
            "machine": "machine",
        }
        return status_map.get(call_status, "failed")

    async def cancel_all_monitors(self):
        """Cancel all active monitoring tasks."""
        for call_sid, task in list(self._active_tasks.items()):
            if not task.done():
                task.cancel()
                logger.info(f"Cancelled monitor task for call {call_sid}")
        self._active_tasks.clear()

    async def close(self):
        """Clean up resources."""
        await self.cancel_all_monitors()
        await self.redis_client.close()


# Singleton instance
async_campaign_dialer = AsyncCampaignDialer()

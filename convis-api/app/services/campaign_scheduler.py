"""
Asynchronous campaign dispatcher that enforces concurrency, business hours,
and fallback retry logic on top of the existing CampaignDialer.

OPTIMIZED: Now uses AsyncCampaignDialer and async MongoDB operations for better latency.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

import pytz
from bson import ObjectId
from pymongo import ReturnDocument

from app.config.database import Database
from app.config.async_database import AsyncDatabase
from app.config.settings import settings
from app.services.async_campaign_dialer import AsyncCampaignDialer

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.utcnow()


class CampaignScheduler:
    """Background dispatcher that continuously feeds leads into the dialer.

    OPTIMIZED: Now uses AsyncCampaignDialer for non-blocking call operations.
    """

    def __init__(self, interval_seconds: Optional[int] = None):
        self.interval_seconds = interval_seconds or settings.campaign_dispatch_interval_seconds
        self._task: Optional[asyncio.Task] = None
        self._stop_event = None  # Created lazily in start() to avoid event loop issues
        self._async_dialer = None  # Lazy initialization

    @property
    def async_dialer(self):
        """Lazy initialization of AsyncCampaignDialer."""
        if self._async_dialer is None:
            self._async_dialer = AsyncCampaignDialer()
        return self._async_dialer

    async def start(self):
        if self._task and not self._task.done():
            logger.info("Campaign dispatcher already running")
            return
        logger.info("Starting campaign dispatcher (interval=%ss)", self.interval_seconds)
        # Create stop event in the correct event loop
        if self._stop_event is None:
            self._stop_event = asyncio.Event()
        else:
            self._stop_event.clear()
        loop = asyncio.get_running_loop()
        self._task = loop.create_task(self._run(), name="campaign-dispatcher")

    async def shutdown(self):
        if not self._task:
            return
        logger.info("Stopping campaign dispatcher")
        try:
            # Set stop event and cancel task in the same event loop
            if self._stop_event:
                self._stop_event.set()
            if self._task and not self._task.done():
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
        except Exception as e:
            logger.warning(f"Error during campaign scheduler shutdown: {e}")
        finally:
            self._task = None

    async def _run(self):
        while not self._stop_event.is_set():
            try:
                # OPTIMIZED: Now uses async dispatch for non-blocking operations
                await self.dispatch_once_async()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception("Campaign dispatcher tick failed: %s", exc)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.interval_seconds)
            except asyncio.TimeoutError:
                continue

    # ====== Core tick ======
    def dispatch_once(self):
        """One synchronous tick that scans running campaigns and dials leads."""
        db = Database.get_db()
        campaigns_collection = db["campaigns"]
        leads_collection = db["leads"]
        running_campaigns = list(campaigns_collection.find({"status": "running"}))
        now = utc_now()
        total_dispatched = 0

        # CRITICAL FIX: Reset stale "calling" leads (stuck > 30 seconds)
        # This handles cases where Twilio webhook never arrives or call is declined/rejected
        stale_threshold = now - timedelta(seconds=30)
        stale_reset = leads_collection.update_many(
            {
                "status": "calling",
                "updated_at": {"$lt": stale_threshold}
            },
            {
                "$set": {
                    "status": "no-answer",
                    "last_outcome": "timeout-no-webhook",
                    "updated_at": now
                }
            }
        )
        if stale_reset.modified_count > 0:
            logger.warning(f"[SCHEDULER] Reset {stale_reset.modified_count} stale 'calling' leads (no webhook received after 30s)")

        if running_campaigns:
            logger.debug(f"[SCHEDULER] Found {len(running_campaigns)} running campaign(s)")

        for campaign in running_campaigns:
            try:
                campaign_id = str(campaign.get("_id"))
                campaign_name = campaign.get("name", "Unknown")

                if not self._campaign_is_active(campaign, now):
                    logger.debug(f"[SCHEDULER] Campaign {campaign_name} ({campaign_id}) is not active (checking delays/business hours)")
                    continue

                slots = self._available_slots_for_campaign(db, campaign)
                if slots <= 0:
                    logger.debug(f"[SCHEDULER] Campaign {campaign_name} ({campaign_id}) has no available slots (current calls in progress)")
                    continue

                logger.info(f"[SCHEDULER] Campaign {campaign_name} ({campaign_id}) has {slots} available slot(s)")

                for _ in range(slots):
                    lead = self._reserve_lead(db, campaign, now)
                    if not lead:
                        logger.debug(f"[SCHEDULER] No ready leads found for campaign {campaign_name} ({campaign_id})")
                        break
                    lead_name = lead.get("name", "Unknown")
                    logger.info(f"[SCHEDULER] Reserved lead {lead_name} for campaign {campaign_name}")
                    dispatched = self._start_call(campaign, lead)
                    if dispatched:
                        total_dispatched += 1
                        logger.info(f"[SCHEDULER] Successfully dispatched call for lead {lead_name}")
                    else:
                        logger.warning(f"[SCHEDULER] Failed to dispatch call for lead {lead_name}")
            except Exception as campaign_error:
                logger.exception(
                    "[SCHEDULER] Failed to process campaign %s: %s",
                    campaign.get("_id"),
                    campaign_error
                )

        if total_dispatched:
            logger.info(f"[SCHEDULER] Dispatched {total_dispatched} lead(s) this tick")
        elif running_campaigns:
            logger.debug(f"[SCHEDULER] Tick completed - no leads dispatched (campaigns may be waiting for delays)")

    # ====== Async Core tick (OPTIMIZED) ======
    async def dispatch_once_async(self):
        """One async tick that scans running campaigns and dials leads.

        OPTIMIZED: Uses async MongoDB operations for non-blocking execution.
        """
        db = await AsyncDatabase.get_db()
        campaigns_collection = db["campaigns"]
        leads_collection = db["leads"]
        running_campaigns = await campaigns_collection.find({"status": "running"}).to_list(length=100)
        now = utc_now()
        total_dispatched = 0

        # CRITICAL FIX: Reset stale "calling" leads (stuck > 30 seconds)
        stale_threshold = now - timedelta(seconds=30)
        stale_reset = await leads_collection.update_many(
            {
                "status": "calling",
                "updated_at": {"$lt": stale_threshold}
            },
            {
                "$set": {
                    "status": "no-answer",
                    "last_outcome": "timeout-no-webhook",
                    "updated_at": now
                }
            }
        )
        if stale_reset.modified_count > 0:
            logger.warning(f"[SCHEDULER_ASYNC] Reset {stale_reset.modified_count} stale 'calling' leads (no webhook received after 30s)")

        if running_campaigns:
            logger.debug(f"[SCHEDULER_ASYNC] Found {len(running_campaigns)} running campaign(s)")

        for campaign in running_campaigns:
            try:
                campaign_id = str(campaign.get("_id"))
                campaign_name = campaign.get("name", "Unknown")

                if not self._campaign_is_active(campaign, now):
                    logger.debug(f"[SCHEDULER_ASYNC] Campaign {campaign_name} ({campaign_id}) is not active")
                    continue

                slots = await self._available_slots_for_campaign_async(db, campaign)
                if slots <= 0:
                    logger.debug(f"[SCHEDULER_ASYNC] Campaign {campaign_name} ({campaign_id}) has no available slots")
                    continue

                logger.info(f"[SCHEDULER_ASYNC] Campaign {campaign_name} ({campaign_id}) has {slots} available slot(s)")

                for _ in range(slots):
                    lead = await self._reserve_lead_async(db, campaign, now)
                    if not lead:
                        logger.debug(f"[SCHEDULER_ASYNC] No ready leads found for campaign {campaign_name}")
                        break
                    lead_name = lead.get("name", "Unknown")
                    logger.info(f"[SCHEDULER_ASYNC] Reserved lead {lead_name} for campaign {campaign_name}")
                    dispatched = await self._start_call_async(campaign, lead)
                    if dispatched:
                        total_dispatched += 1
                        logger.info(f"[SCHEDULER_ASYNC] Successfully dispatched call for lead {lead_name}")
                    else:
                        logger.warning(f"[SCHEDULER_ASYNC] Failed to dispatch call for lead {lead_name}")
            except Exception as campaign_error:
                logger.exception(
                    "[SCHEDULER_ASYNC] Failed to process campaign %s: %s",
                    campaign.get("_id"),
                    campaign_error
                )

        if total_dispatched:
            logger.info(f"[SCHEDULER_ASYNC] Dispatched {total_dispatched} lead(s) this tick")
        elif running_campaigns:
            logger.debug(f"[SCHEDULER_ASYNC] Tick completed - no leads dispatched")

    async def _available_slots_for_campaign_async(self, db, campaign: Dict[str, Any]) -> int:
        """Async version of available slots calculation."""
        leads_collection = db["leads"]
        campaign_id = campaign["_id"]
        in_progress = await leads_collection.count_documents({
            "campaign_id": campaign_id,
            "status": "calling"
        })
        pacing = campaign.get("pacing", {})
        pacing_limit = pacing.get("max_concurrent", 1)
        lines = campaign.get("lines", 1)
        max_slots = max(1, min(pacing_limit, lines))
        available = max_slots - in_progress
        return max(0, available)

    async def _reserve_lead_async(self, db, campaign: Dict[str, Any], now: datetime) -> Optional[Dict[str, Any]]:
        """Async version of lead reservation."""
        leads_collection = db["leads"]
        campaign_id = campaign["_id"]

        query = {
            "campaign_id": campaign_id,
            "status": "queued"
        }

        sort = [("order_index", 1), ("_id", 1)]

        lead = await leads_collection.find_one_and_update(
            query,
            {
                "$set": {
                    "status": "calling",
                    "updated_at": now,
                    "next_retry_at": None,
                    "last_outcome": "dialing",
                },
                "$inc": {"attempts": 1},
            },
            sort=sort,
            return_document=ReturnDocument.AFTER
        )

        if lead:
            lead.setdefault("fallback_round", 0)
            logger.info(
                "Reserved lead %s (attempt %s) for campaign %s",
                lead.get("_id"),
                lead.get("attempts"),
                campaign_id
            )
        return lead

    async def _start_call_async(self, campaign: Dict[str, Any], lead: Dict[str, Any]) -> bool:
        """Async version of call initiation using AsyncCampaignDialer."""
        campaign_id = str(campaign["_id"])
        lead_id = str(lead["_id"])
        try:
            call_sid = await self.async_dialer.place_call(campaign_id, lead_id)
            if not call_sid:
                raise RuntimeError(self.async_dialer.last_error or "Unknown dialer error")
            return True
        except Exception as error:
            logger.error(
                "Failed to start call for campaign %s lead %s: %s",
                campaign_id,
                lead_id,
                error
            )
            # Revert lead state to queued so it can be retried later
            db = await AsyncDatabase.get_db()
            await db["leads"].update_one(
                {"_id": ObjectId(lead_id)},
                {
                    "$set": {
                        "status": "queued",
                        "last_outcome": "dispatch-error",
                        "updated_at": utc_now()
                    }
                }
            )
            return False

    def _campaign_is_active(self, campaign: Dict[str, Any], now: datetime) -> bool:
        start_at = campaign.get("start_at")
        if start_at and start_at > now:
            return False

        stop_at = campaign.get("stop_at")
        if stop_at and stop_at <= now:
            return False

        # NO DELAY MODE - Call immediately for maximum speed
        # Removed inter-call delay entirely for instant sequential dialing

        return self._within_business_hours(campaign, now)

    def _within_business_hours(self, campaign: Dict[str, Any], now: datetime) -> bool:
        window = campaign.get("working_window") or {}
        tz_name = window.get("timezone") or settings.default_timezone
        start_str = window.get("start", "09:00")
        end_str = window.get("end", "17:00")
        days = window.get("days") or [0, 1, 2, 3, 4]

        tz = pytz.timezone(tz_name)
        aware_now = pytz.utc.localize(now)
        local_now = aware_now.astimezone(tz)

        if days and local_now.weekday() not in days:
            return False

        start_hour, start_minute = map(int, start_str.split(":"))
        end_hour, end_minute = map(int, end_str.split(":"))

        start_dt = local_now.replace(
            hour=start_hour, minute=start_minute, second=0, microsecond=0
        )
        end_dt = local_now.replace(
            hour=end_hour, minute=end_minute, second=0, microsecond=0
        )

        return start_dt <= local_now <= end_dt

    def _available_slots_for_campaign(self, db, campaign: Dict[str, Any]) -> int:
        leads_collection = db["leads"]
        campaign_id = campaign["_id"]
        in_progress = leads_collection.count_documents({
            "campaign_id": campaign_id,
            "status": "calling"
        })
        pacing = campaign.get("pacing", {})
        pacing_limit = pacing.get("max_concurrent", 1)
        lines = campaign.get("lines", 1)
        max_slots = max(1, min(pacing_limit, lines))
        available = max_slots - in_progress
        return max(0, available)

    def _reserve_lead(self, db, campaign: Dict[str, Any], now: datetime) -> Optional[Dict[str, Any]]:
        leads_collection = db["leads"]
        campaign_id = campaign["_id"]

        # Simple query: just get queued leads in CSV order
        # No attempt limits - each lead is called exactly once
        query = {
            "campaign_id": campaign_id,
            "status": "queued"
        }

        # Sort by order_index first (call in CSV order)
        sort = [("order_index", 1), ("_id", 1)]

        lead = leads_collection.find_one_and_update(
            query,
            {
                "$set": {
                    "status": "calling",
                    "updated_at": now,
                    "next_retry_at": None,
                    "last_outcome": "dialing",
                },
                "$inc": {"attempts": 1},
            },
            sort=sort,
            return_document=ReturnDocument.AFTER
        )

        if lead:
            lead.setdefault("fallback_round", 0)
            logger.info(
                "Reserved lead %s (attempt %s) for campaign %s",
                lead.get("_id"),
                lead.get("attempts"),
                campaign_id
            )
        return lead

    def _start_call(self, campaign: Dict[str, Any], lead: Dict[str, Any]) -> bool:
        campaign_id = str(campaign["_id"])
        lead_id = str(lead["_id"])
        try:
            call_sid = self._dialer.place_call(campaign_id, lead_id)
            if not call_sid:
                raise RuntimeError(self._dialer.last_error or "Unknown dialer error")
            return True
        except Exception as error:
            logger.error(
                "Failed to start call for campaign %s lead %s: %s",
                campaign_id,
                lead_id,
                error
            )
            # Revert lead state to queued so it can be retried later
            db = Database.get_db()
            db["leads"].update_one(
                {"_id": ObjectId(lead_id)},
                {
                    "$set": {
                        "status": "queued",
                        "last_outcome": "dispatch-error",
                        "updated_at": utc_now()
                    }
                }
            )
            return False


campaign_scheduler = CampaignScheduler()

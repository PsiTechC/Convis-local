from datetime import datetime, timedelta
from typing import List
import csv
import io

from bson import ObjectId
from fastapi import APIRouter, HTTPException, status, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pymongo import ReturnDocument

from app.config.database import Database
from app.models.campaign import (
    CampaignCreate,
    CampaignListResponse,
    CampaignResponse,
    LeadUploadResponse,
    CampaignStatusUpdate,
    CampaignStats,
    LeadResponse,
    CampaignUpdate,
    AttemptBackoff,
    ManualRetryRequest,
)
from app.services.phone_service import PhoneService
from app.services.async_campaign_dialer import AsyncCampaignDialer
from app.utils.threadpool import run_in_thread

import logging

logger = logging.getLogger(__name__)

router = APIRouter()

# Initialize services
phone_service = PhoneService()
# Use async campaign dialer for better performance
async_dialer = AsyncCampaignDialer()


def serialize_campaign(doc: dict) -> CampaignResponse:
    doc = doc.copy()
    doc["_id"] = str(doc.pop("_id"))
    doc["user_id"] = str(doc["user_id"]) if isinstance(doc.get("user_id"), ObjectId) else doc.get("user_id")
    if doc.get("assistant_id") and isinstance(doc["assistant_id"], ObjectId):
        doc["assistant_id"] = str(doc["assistant_id"])
    if doc.get("calendar_account_id") and isinstance(doc["calendar_account_id"], ObjectId):
        doc["calendar_account_id"] = str(doc["calendar_account_id"])
    doc["created_at"] = doc["created_at"].isoformat() if isinstance(doc.get("created_at"), datetime) else doc.get("created_at")
    doc["updated_at"] = doc["updated_at"].isoformat() if isinstance(doc.get("updated_at"), datetime) else doc.get("updated_at")
    doc["calendar_enabled"] = bool(doc.get("calendar_enabled", False))
    system_prompt = doc.get("system_prompt_override")
    if system_prompt:
        doc["system_prompt_override"] = system_prompt.strip()
        if not doc["system_prompt_override"]:
            doc["system_prompt_override"] = None
    else:
        doc["system_prompt_override"] = None
    if doc.get("database_config") and isinstance(doc["database_config"], dict):
        doc["database_config"] = {**doc["database_config"]}
    else:
        doc["database_config"] = None
    doc["lines"] = int(doc.get("lines") or doc.get("pacing", {}).get("max_concurrent", 1))
    doc["attempts_per_number"] = int(doc.get("attempts_per_number") or doc.get("retry_policy", {}).get("max_attempts", 3))
    doc["priority"] = doc.get("priority", "standard")
    attempt_backoff = doc.get("attempt_backoff") or AttemptBackoff.default().model_dump()
    if isinstance(attempt_backoff, AttemptBackoff):
        attempt_backoff = attempt_backoff.model_dump()
    doc["attempt_backoff"] = attempt_backoff
    return CampaignResponse(**doc)


def serialize_lead(doc: dict) -> LeadResponse:
    doc = doc.copy()
    doc["_id"] = str(doc.pop("_id"))
    doc["campaign_id"] = str(doc["campaign_id"]) if isinstance(doc.get("campaign_id"), ObjectId) else doc.get("campaign_id")
    if isinstance(doc.get("created_at"), datetime):
        doc["created_at"] = doc["created_at"].isoformat()
    if isinstance(doc.get("updated_at"), datetime):
        doc["updated_at"] = doc["updated_at"].isoformat()
    if "order_index" in doc and doc["order_index"] is not None:
        doc["order_index"] = int(doc["order_index"])
    return LeadResponse(**doc)


@router.post("/", response_model=CampaignResponse, status_code=status.HTTP_201_CREATED)
async def create_campaign(payload: CampaignCreate):
    """Create a new outbound campaign."""
    try:
        logger.info(f"Creating campaign with payload: {payload.model_dump()}")

        db = Database.get_db()
        campaigns_collection = db["campaigns"]

        # Validate and convert user_id to ObjectId
        try:
            user_obj_id = ObjectId(payload.user_id)
        except Exception as e:
            logger.error(f"Invalid user_id format: {payload.user_id}, error: {e}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid user_id format: {str(e)}")

        # Validate and convert assistant_id to ObjectId if provided
        assistant_obj_id = None
        if payload.assistant_id:
            try:
                assistant_obj_id = ObjectId(payload.assistant_id)
            except Exception as e:
                logger.error(f"Invalid assistant_id format: {payload.assistant_id}, error: {e}")
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid assistant_id format: {str(e)}")

        # Validate calendar account if calendar is enabled
        calendar_account_obj_id = None
        if payload.calendar_enabled and payload.calendar_account_id:
            try:
                calendar_account_obj_id = ObjectId(payload.calendar_account_id)
                # Verify the calendar account exists and belongs to this user
                calendar_accounts_collection = db["calendar_accounts"]
                calendar_account = await run_in_thread(
                    calendar_accounts_collection.find_one,
                    {
                        "_id": calendar_account_obj_id,
                        "user_id": user_obj_id
                    }
                )
                if not calendar_account:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Calendar account not found or does not belong to this user"
                    )
                logger.info(f"Calendar account {calendar_account_obj_id} validated for user {user_obj_id}")
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Invalid calendar_account_id format: {payload.calendar_account_id}, error: {e}")
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid calendar_account_id format: {str(e)}")

        now = datetime.utcnow()
        calendar_enabled = payload.calendar_enabled
        system_prompt_override = (payload.system_prompt_override or "").strip() or None
        database_config = payload.database_config.model_dump() if payload.database_config else None

        doc = {
            "user_id": user_obj_id,
            "name": payload.name,
            "country": payload.country,
            "working_window": payload.working_window.model_dump(),
            "caller_id": payload.caller_id,
            "assistant_id": assistant_obj_id,
            "retry_policy": payload.retry_policy.model_dump(),
            "pacing": payload.pacing.model_dump(),
            "start_at": payload.start_at,
            "stop_at": payload.stop_at,
            "calendar_enabled": calendar_enabled,
            "calendar_account_id": calendar_account_obj_id,
            "system_prompt_override": system_prompt_override,
            "database_config": database_config,
            "status": "draft",
            "created_at": now,
            "updated_at": now,
            "next_index": 0,
            "lines": payload.lines,
            "attempts_per_number": payload.attempts_per_number,
            "attempt_backoff": payload.attempt_backoff.model_dump(),
            "priority": payload.priority,
        }

        logger.info(f"Inserting campaign document: {doc}")
        result = await run_in_thread(campaigns_collection.insert_one, doc)
        logger.info(f"Created campaign {result.inserted_id} for user {payload.user_id}")

        created = await run_in_thread(campaigns_collection.find_one, {"_id": result.inserted_id})
        if not created:
            raise Exception("Campaign was created but not found in database")

        return serialize_campaign(created)

    except HTTPException:
        raise
    except Exception as error:
        import traceback
        error_detail = traceback.format_exc()
        logger.error(f"Error creating campaign: {error}")
        logger.error(f"Full traceback: {error_detail}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create campaign: {str(error)}"
        )


@router.get("/user/{user_id}", response_model=CampaignListResponse, status_code=status.HTTP_200_OK)
async def list_campaigns(user_id: str):
    """Return all campaigns for a user."""
    try:
        db = Database.get_db()
        campaigns_collection = db["campaigns"]

        try:
            user_obj_id = ObjectId(user_id)
        except Exception:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid user_id format")

        docs: List[dict] = await run_in_thread(
            lambda: list(
                campaigns_collection.find({"user_id": user_obj_id}).sort("created_at", -1)
            )
        )
        campaigns = [serialize_campaign(doc) for doc in docs]
        return CampaignListResponse(campaigns=campaigns, total=len(campaigns))

    except HTTPException:
        raise
    except Exception as error:
        logger.error(f"Error listing campaigns: {error}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch campaigns")


@router.put("/{campaign_id}", response_model=CampaignResponse, status_code=status.HTTP_200_OK)
async def update_campaign(campaign_id: str, payload: CampaignUpdate):
    """Update an existing campaign's configuration."""
    try:
        db = Database.get_db()
        campaigns_collection = db["campaigns"]

        try:
            campaign_obj_id = ObjectId(campaign_id)
        except Exception:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid campaign_id format")

        update_doc = payload.model_dump(exclude_unset=True)

        if "assistant_id" in update_doc:
            assistant_value = update_doc.get("assistant_id")
            if assistant_value:
                try:
                    update_doc["assistant_id"] = ObjectId(assistant_value)
                except Exception as exc:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid assistant_id format: {exc}")
            else:
                update_doc.pop("assistant_id", None)

        # Validate calendar_account_id if provided
        if "calendar_account_id" in update_doc:
            calendar_account_value = update_doc.get("calendar_account_id")
            if calendar_account_value:
                try:
                    calendar_account_obj_id = ObjectId(calendar_account_value)
                    # Get the campaign to find the user_id
                    campaign = campaigns_collection.find_one({"_id": campaign_obj_id})
                    if not campaign:
                        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

                    # Verify the calendar account exists and belongs to the campaign owner
                    calendar_accounts_collection = db["calendar_accounts"]
                    calendar_account = calendar_accounts_collection.find_one({
                        "_id": calendar_account_obj_id,
                        "user_id": campaign.get("user_id")
                    })
                    if not calendar_account:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Calendar account not found or does not belong to campaign owner"
                        )
                    update_doc["calendar_account_id"] = calendar_account_obj_id
                except HTTPException:
                    raise
                except Exception as exc:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid calendar_account_id format: {exc}")
            else:
                update_doc.pop("calendar_account_id", None)

        if "system_prompt_override" in update_doc:
            prompt_value = update_doc.get("system_prompt_override")
            if prompt_value is not None:
                trimmed_prompt = prompt_value.strip()
                update_doc["system_prompt_override"] = trimmed_prompt or None

        if "database_config" in update_doc:
            db_config_value = update_doc.get("database_config")
            if db_config_value is None:
                update_doc["database_config"] = None
            else:
                update_doc["database_config"] = {**db_config_value}

        if "attempt_backoff" in update_doc and update_doc["attempt_backoff"]:
            attempt_value = update_doc["attempt_backoff"]
            if isinstance(attempt_value, AttemptBackoff):
                update_doc["attempt_backoff"] = attempt_value.model_dump()
            else:
                update_doc["attempt_backoff"] = AttemptBackoff(**attempt_value).model_dump()

        if "working_window" in update_doc and update_doc["working_window"]:
            window = update_doc["working_window"]
            if "days" in window and window["days"]:
                window["days"] = sorted(window["days"])
            update_doc["working_window"] = window

        if "retry_policy" in update_doc and update_doc["retry_policy"]:
            policy = update_doc["retry_policy"]
            if "retry_after_minutes" in policy and policy["retry_after_minutes"]:
                policy["retry_after_minutes"] = [int(value) for value in policy["retry_after_minutes"] if value is not None]
            update_doc["retry_policy"] = policy

        if "pacing" in update_doc and update_doc["pacing"]:
            pacing = update_doc["pacing"]
            update_doc["pacing"] = pacing

        update_doc["updated_at"] = datetime.utcnow()

        updated_doc = campaigns_collection.find_one_and_update(
            {"_id": campaign_obj_id},
            {"$set": update_doc},
            return_document=ReturnDocument.AFTER,
        )

        if not updated_doc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

        return serialize_campaign(updated_doc)

    except HTTPException:
        raise
    except Exception as error:
        logger.error(f"Error updating campaign {campaign_id}: {error}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update campaign")


@router.get("/{campaign_id}", response_model=CampaignResponse, status_code=status.HTTP_200_OK)
async def get_campaign(campaign_id: str):
    try:
        db = Database.get_db()
        campaigns_collection = db["campaigns"]

        try:
            campaign_obj_id = ObjectId(campaign_id)
        except Exception:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid campaign_id format")

        doc = campaigns_collection.find_one({"_id": campaign_obj_id})
        if not doc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

        return serialize_campaign(doc)

    except HTTPException:
        raise
    except Exception as error:
        logger.error(f"Error fetching campaign: {error}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to load campaign")


@router.post("/{campaign_id}/test-call", status_code=status.HTTP_200_OK)
async def trigger_test_call(campaign_id: str):
    """
    Trigger an immediate call attempt for the next available lead in the campaign.
    Useful for on-demand testing from the dashboard.
    """
    try:
        db = Database.get_db()
        campaigns_collection = db["campaigns"]
        leads_collection = db["leads"]
        call_attempts_collection = db["call_attempts"]

        try:
            campaign_obj_id = ObjectId(campaign_id)
        except Exception:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid campaign_id format")

        campaign = campaigns_collection.find_one({"_id": campaign_obj_id})
        if not campaign:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

        stale_threshold = datetime.utcnow() - timedelta(minutes=5)
        active_call = leads_collection.find_one({
            "campaign_id": campaign_obj_id,
            "status": "calling",
            "updated_at": {"$gte": stale_threshold}
        })

        if active_call:
            latest_attempt = call_attempts_collection.find_one(
                {"lead_id": active_call["_id"]},
                sort=[("started_at", -1)]
            )
            terminal_statuses = {"completed", "busy", "no-answer", "failed", "canceled"}
            if latest_attempt and latest_attempt.get("status") in terminal_statuses:
                leads_collection.update_one(
                    {"_id": active_call["_id"]},
                    {
                        "$set": {
                            "status": "queued",
                            "last_outcome": latest_attempt.get("status", "manual-reset"),
                            "next_retry_at": None,
                            "updated_at": datetime.utcnow()
                        }
                    }
                )
                active_call = None

        if active_call:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A call is already in progress for this campaign. Please wait for it to finish before testing."
            )
        # Requeue any stale calls that never completed
        leads_collection.update_many(
            {
                "campaign_id": campaign_obj_id,
                "status": "calling",
                "updated_at": {"$lt": stale_threshold}
            },
            {
                "$set": {
                    "status": "queued",
                    "last_outcome": "stale-call-reset",
                    "next_retry_at": None,
                    "updated_at": datetime.utcnow()
                }
            }
        )

        next_lead = await async_dialer.get_next_lead(
            campaign_id,
            ignore_window=True,
            ignore_attempt_limit=True,
        )
        if not next_lead:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No queued leads available for test call. Make sure you have uploaded leads with status 'queued' for this campaign."
            )

        call_sid = await async_dialer.place_call(campaign_id, str(next_lead["_id"]))
        if not call_sid:
            detail_message = async_dialer.last_error or "Unable to place test call. Verify Twilio credentials, caller ID, and lead phone number."
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=detail_message
            )

        return {
            "message": "Test call initiated successfully",
            "lead_id": str(next_lead["_id"]),
            "call_sid": call_sid
        }

    except HTTPException:
        raise
    except Exception as error:
        logger.error(f"Error triggering test call for campaign {campaign_id}: {error}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error while attempting test call"
        )


@router.post("/{campaign_id}/leads/upload", response_model=LeadUploadResponse, status_code=status.HTTP_200_OK)
async def upload_leads(
    campaign_id: str,
    file: UploadFile = File(...),
    batch_name: str | None = Form(default=None),
):
    """
    Upload leads from CSV file.
    Expected columns: phone, name (optional), email (optional)
    """
    next_index_counter = 0
    try:
        db = Database.get_db()
        campaigns_collection = db["campaigns"]
        leads_collection = db["leads"]

        # Verify campaign exists
        try:
            campaign_obj_id = ObjectId(campaign_id)
        except Exception:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid campaign_id format")

        campaign = await run_in_thread(campaigns_collection.find_one, {"_id": campaign_obj_id})
        if not campaign:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
        next_index_counter = int(campaign.get("next_index", 0) or 0)

        # Get campaign country and timezone
        campaign_country = campaign.get("country", "US")
        campaign_tz = campaign.get("working_window", {}).get("timezone", "America/New_York")

        # Read CSV
        contents = await file.read()
        csv_text = contents.decode("utf-8")
        csv_reader = csv.DictReader(io.StringIO(csv_text))

        # Process leads
        total = 0
        valid = 0
        invalid = 0
        mismatches = 0
        now = datetime.utcnow()

        leads_to_insert = []
        batch_name_clean = batch_name.strip() if batch_name else None

        for row in csv_reader:
            total += 1
            normalized_keys = {(key or "").strip(): (row[key] or "").strip() for key in row.keys()}
            lowercase_lookup = {key.lower(): value for key, value in normalized_keys.items() if key}

            def pick_value(possible_keys):
                for possible_key in possible_keys:
                    value = lowercase_lookup.get(possible_key.lower(), "")
                    if value:
                        return value
                return ""

            phone_keys = {"phone", "phone_number", "number", "mobile", "mobile_number", "contact_number", "contact"}
            name_keys = {"name", "full_name", "contact_name"}
            email_keys = {"email", "email_address"}
            first_name_keys = {"firstname", "first_name", "first"}
            last_name_keys = {"lastname", "last_name", "surname", "family_name"}
            timezone_keys = {"timezone", "tz"}

            raw_number = pick_value(phone_keys)
            first_name = pick_value(first_name_keys) or None
            last_name = pick_value(last_name_keys) or None
            name = pick_value(name_keys) or None
            email = pick_value(email_keys) or None

            if not raw_number:
                invalid += 1
                continue

            if not first_name and not name:
                invalid += 1
                continue

            # Validate and normalize phone number
            is_valid, e164, region, timezones = phone_service.normalize_and_validate(raw_number, campaign_country)

            if not is_valid:
                invalid += 1
                continue

            # Check for region mismatch
            is_mismatch = phone_service.check_region_mismatch(e164, campaign_country)
            if is_mismatch:
                mismatches += 1

            # Detect timezone
            timezone_override = pick_value(timezone_keys)
            lead_tz = timezone_override or (timezones[0] if timezones else campaign_tz)

            if not name and (first_name or last_name):
                name_parts = [part for part in [first_name, last_name] if part]
                name = " ".join(name_parts) if name_parts else None

            # Create lead document
            lead_doc = {
                "campaign_id": campaign_obj_id,
                "raw_number": raw_number,
                "e164": e164,
                "timezone": lead_tz,
                "first_name": first_name,
                "last_name": last_name,
                "batch_name": batch_name_clean,
                "name": name,
                "email": email,
                "status": "queued",
                "attempts": 0,
                "order_index": next_index_counter,
                "next_retry_at": None,
                "fallback_round": 0,
                "last_outcome": None,
                "last_call_sid": None,
                "retry_on": None,
                "sentiment": None,
                "summary": None,
                "calendar_booked": False,
                "created_at": now,
                "updated_at": now,
                "custom_fields": {
                    key: value
                    for key, value in normalized_keys.items()
                    if key.lower() not in phone_keys | name_keys | email_keys | first_name_keys | last_name_keys | timezone_keys
                    and value
                }
            }

            leads_to_insert.append(lead_doc)
            next_index_counter += 1
            valid += 1

        # Bulk insert leads
        if leads_to_insert:
            await run_in_thread(leads_collection.insert_many, leads_to_insert)
            await run_in_thread(
                campaigns_collection.update_one,
                {"_id": campaign_obj_id},
                {"$set": {"next_index": next_index_counter}}
            )
            logger.info(f"Inserted {len(leads_to_insert)} leads for campaign {campaign_id}")

        message = f"Uploaded {valid} valid leads"
        if invalid > 0:
            message += f", {invalid} invalid"
        if mismatches > 0:
            message += f", {mismatches} region mismatches"

        return LeadUploadResponse(
            total=total,
            valid=valid,
            invalid=invalid,
            mismatches=mismatches,
            message=message
        )

    except HTTPException:
        raise
    except Exception as error:
        logger.error(f"Error uploading leads: {error}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to upload leads: {str(error)}")


@router.get("/{campaign_id}/leads", response_model=List[LeadResponse], status_code=status.HTTP_200_OK)
async def get_campaign_leads(campaign_id: str, skip: int = 0, limit: int = 100):
    """
    Get leads for a campaign
    Cached for 2 seconds for blazing fast polling (polled every 1 second in frontend)
    Limit enforced to max 500 for performance
    """
    try:
        # Enforce maximum limit for performance
        limit = min(limit, 500)
        
        # Check cache first (2s cache for blazing fast polling)
        from app.utils.cache import get_from_cache, set_to_cache, generate_cache_key
        cache_key = generate_cache_key("campaign:leads", campaign_id, skip, limit)
        cached_result = await get_from_cache(cache_key)
        if cached_result:
            logger.debug(f"Cache hit for campaign leads: {campaign_id}")
            return cached_result
        db = Database.get_db()
        leads_collection = db["leads"]

        try:
            campaign_obj_id = ObjectId(campaign_id)
        except Exception:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid campaign_id format")

        docs = list(
            leads_collection.find({"campaign_id": campaign_obj_id})
            .sort([("order_index", 1), ("_id", 1)])
            .skip(skip)
            .limit(limit)
        )

        result = [serialize_lead(doc) for doc in docs]
        
        # Cache the result for 2 seconds (blazing fast polling)
        from app.utils.cache import set_to_cache, generate_cache_key
        cache_key = generate_cache_key("campaign:leads", campaign_id, skip, limit)
        await set_to_cache(cache_key, result, expire=2)
        
        return result

    except HTTPException:
        raise
    except Exception as error:
        logger.error(f"Error fetching leads: {error}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch leads")


@router.get("/{campaign_id}/leads/retry", response_model=List[LeadResponse], status_code=status.HTTP_200_OK)
async def get_retry_leads(campaign_id: str):
    """
    Return leads scheduled for retry (e.g., no-answer/busy) for the next dial window.
    """
    try:
        db = Database.get_db()
        leads_collection = db["leads"]

        try:
            campaign_obj_id = ObjectId(campaign_id)
        except Exception:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid campaign_id format")

        docs = list(
            leads_collection.find({
                "campaign_id": campaign_obj_id,
                "retry_on": {"$ne": None}
            }).sort("_id", 1)
        )

        return [serialize_lead(doc) for doc in docs]

    except HTTPException:
        raise
    except Exception as error:
        logger.error(f"Error fetching retry leads: {error}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch retry leads")


@router.get("/{campaign_id}/active-call", status_code=status.HTTP_200_OK)
async def get_active_calls(campaign_id: str):
    """
    Return the lead(s) currently in progress for this campaign.
    Cached for 1 second for blazing fast polling
    """
    try:
        # Check cache first (1s cache for blazing fast polling)
        from app.utils.cache import get_from_cache, set_to_cache, generate_cache_key
        cache_key = generate_cache_key("campaign:active_calls", campaign_id)
        cached_result = await get_from_cache(cache_key)
        if cached_result:
            logger.debug(f"Cache hit for active calls: {campaign_id}")
            return cached_result
        db = Database.get_db()
        leads_collection = db["leads"]

        try:
            campaign_obj_id = ObjectId(campaign_id)
        except Exception:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid campaign_id format")

        docs = list(
            leads_collection.find({
                "campaign_id": campaign_obj_id,
                "status": "calling"
            }).sort("updated_at", -1)
        )

        result = {
            "count": len(docs),
            "active_calls": [serialize_lead(doc) for doc in docs]
        }
        
        # Cache the result for 1 second (blazing fast polling)
        from app.utils.cache import set_to_cache, generate_cache_key
        cache_key = generate_cache_key("campaign:active_calls", campaign_id)
        await set_to_cache(cache_key, result, expire=1)
        
        return result

    except HTTPException:
        raise
    except Exception as error:
        logger.error(f"Error fetching active calls for campaign {campaign_id}: {error}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch active calls")


@router.post("/{campaign_id}/manual-retry", status_code=status.HTTP_200_OK)
async def manual_retry_leads(campaign_id: str, payload: ManualRetryRequest):
    """
    Manually queue a list of leads for immediate retry (fallback list override).
    """
    try:
        if not payload.lead_ids:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="lead_ids may not be empty")

        db = Database.get_db()
        campaigns_collection = db["campaigns"]
        leads_collection = db["leads"]

        try:
            campaign_obj_id = ObjectId(campaign_id)
        except Exception:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid campaign_id format")

        campaign = campaigns_collection.find_one({"_id": campaign_obj_id})
        if not campaign:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

        lead_object_ids = []
        for lead_id in payload.lead_ids:
            try:
                lead_object_ids.append(ObjectId(lead_id))
            except Exception:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid lead_id format: {lead_id}")

        now = datetime.utcnow()
        result = leads_collection.update_many(
            {
                "_id": {"$in": lead_object_ids},
                "campaign_id": campaign_obj_id
            },
            {
                "$set": {
                    "status": "queued",
                    "next_retry_at": now,
                    "updated_at": now,
                    "last_outcome": payload.reason or "manual-retry",
                },
                "$inc": {"fallback_round": 1}
            }
        )

        return {
            "message": f"Queued {result.modified_count} lead(s) for retry",
            "modified": result.modified_count
        }

    except HTTPException:
        raise
    except Exception as error:
        logger.error(f"Error performing manual retry for campaign {campaign_id}: {error}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to queue manual retry")


@router.patch("/{campaign_id}/status", response_model=CampaignResponse, status_code=status.HTTP_200_OK)
async def update_campaign_status(campaign_id: str, payload: CampaignStatusUpdate):
    """Update campaign status (start, pause, stop)"""
    try:
        db = Database.get_db()
        campaigns_collection = db["campaigns"]
        leads_collection = db["leads"]

        try:
            campaign_obj_id = ObjectId(campaign_id)
        except Exception:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid campaign_id format")

        # Validate status
        if payload.status not in ["running", "paused", "stopped", "completed"]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid status")

        # If starting campaign, reset all leads to queued for a fresh session
        if payload.status == "running":
            # Get current campaign to check if it was previously in a different state
            current_campaign = campaigns_collection.find_one({"_id": campaign_obj_id})
            if not current_campaign:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

            # Only reset leads if campaign was not already running (fresh start)
            if current_campaign.get("status") != "running":
                logger.info(f"Starting fresh campaign session for {campaign_id} - resetting all leads to queued")

                # Reset all leads to queued status, clear attempts and outcomes
                leads_collection.update_many(
                    {"campaign_id": campaign_obj_id},
                    {
                        "$set": {
                            "status": "queued",
                            "attempts": 0,
                            "next_retry_at": None,
                            "last_outcome": None,
                            "updated_at": datetime.utcnow()
                        }
                    }
                )

                # Clear campaign's last call timestamp to start immediately
                campaigns_collection.update_one(
                    {"_id": campaign_obj_id},
                    {
                        "$set": {
                            "status": payload.status,
                            "last_call_ended_at": None,
                            "updated_at": datetime.utcnow()
                        }
                    }
                )
                logger.info(f"Reset {leads_collection.count_documents({'campaign_id': campaign_obj_id})} leads to queued status")

                # CRITICAL FIX: Immediately trigger first call instead of waiting for scheduler
                # This eliminates the 2-second delay for first call
                # When user manually starts campaign, bypass working window (they explicitly want it to run)
                try:
                    import asyncio

                    async def trigger_first_call():
                        try:
                            logger.info(f"[START_CAMPAIGN] Triggering immediate first call for campaign {campaign_id}")
                            # Use ignore_window=True because user explicitly clicked Start Campaign
                            lead = await async_dialer.get_next_lead(campaign_id, ignore_window=True, ignore_attempt_limit=False)
                            if lead:
                                logger.info(f"[START_CAMPAIGN] Found lead: {lead.get('name')} ({lead.get('e164')})")
                                call_sid = await async_dialer.place_call(campaign_id, str(lead["_id"]))
                                if call_sid:
                                    logger.info(f"[START_CAMPAIGN] First call placed successfully: {call_sid}")
                                else:
                                    logger.warning(f"[START_CAMPAIGN] Failed to place first call: {async_dialer.last_error}")
                            else:
                                logger.warning(f"[START_CAMPAIGN] No leads available for immediate call")
                        except Exception as e:
                            logger.error(f"[START_CAMPAIGN] Error triggering first call: {e}")
                            import traceback
                            logger.error(traceback.format_exc())

                    # Run as async task to not block the API response
                    asyncio.create_task(trigger_first_call())
                except Exception as e:
                    logger.error(f"Error starting first call task: {e}")
            else:
                # Campaign is already running, just update status (resume scenario)
                campaigns_collection.update_one(
                    {"_id": campaign_obj_id},
                    {
                        "$set": {
                            "status": payload.status,
                            "updated_at": datetime.utcnow()
                        }
                    }
                )
        else:
            # Update campaign status (pause/stop/complete)
            result = campaigns_collection.update_one(
                {"_id": campaign_obj_id},
                {
                    "$set": {
                        "status": payload.status,
                        "updated_at": datetime.utcnow()
                    }
                }
            )

            if result.matched_count == 0:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

            # CRITICAL FIX: When stopping campaign, reset any stuck "calling" leads
            # This ensures leads don't remain stuck if webhook fails
            if payload.status in ["stopped", "paused"]:
                stuck_leads = leads_collection.update_many(
                    {
                        "campaign_id": campaign_obj_id,
                        "status": "calling"
                    },
                    {
                        "$set": {
                            "status": "no-answer",
                            "last_outcome": "campaign-stopped",
                            "updated_at": datetime.utcnow()
                        }
                    }
                )
                if stuck_leads.modified_count > 0:
                    logger.warning(f"Reset {stuck_leads.modified_count} stuck 'calling' leads when stopping campaign {campaign_id}")

        # Get updated campaign
        doc = campaigns_collection.find_one({"_id": campaign_obj_id})
        return serialize_campaign(doc)

    except HTTPException:
        raise
    except Exception as error:
        logger.error(f"Error updating campaign status: {error}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update status")


@router.post("/{campaign_id}/reset-stuck-leads", status_code=status.HTTP_200_OK)
async def reset_stuck_leads(campaign_id: str):
    """Emergency endpoint to reset leads stuck in 'calling' status"""
    try:
        db = Database.get_db()
        leads_collection = db["leads"]

        try:
            campaign_obj_id = ObjectId(campaign_id)
        except Exception:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid campaign_id format")

        # Reset all stuck leads
        result = leads_collection.update_many(
            {
                "campaign_id": campaign_obj_id,
                "status": "calling"
            },
            {
                "$set": {
                    "status": "no-answer",
                    "last_outcome": "manual-reset",
                    "updated_at": datetime.utcnow()
                }
            }
        )

        logger.info(f"Manually reset {result.modified_count} stuck leads for campaign {campaign_id}")

        return {
            "message": f"Reset {result.modified_count} stuck lead(s)",
            "count": result.modified_count
        }

    except HTTPException:
        raise
    except Exception as error:
        logger.error(f"Error resetting stuck leads: {error}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to reset leads")


@router.get("/{campaign_id}/stats", response_model=CampaignStats, status_code=status.HTTP_200_OK)
async def get_campaign_stats(campaign_id: str):
    """
    Get campaign statistics
    Cached for 2 seconds for blazing fast polling (polled every 1 second in frontend)
    """
    try:
        # Check cache first (2s cache for blazing fast polling)
        from app.utils.cache import get_from_cache, set_to_cache, generate_cache_key
        cache_key = generate_cache_key("campaign:stats", campaign_id)
        cached_result = await get_from_cache(cache_key)
        if cached_result:
            logger.debug(f"Cache hit for campaign stats: {campaign_id}")
            return cached_result
        db = Database.get_db()
        leads_collection = db["leads"]
        call_attempts_collection = db["call_attempts"]

        try:
            campaign_obj_id = ObjectId(campaign_id)
        except Exception:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid campaign_id format")

        # Aggregate lead stats
        lead_stats = list(leads_collection.aggregate([
            {"$match": {"campaign_id": campaign_obj_id}},
            {
                "$group": {
                    "_id": "$status",
                    "count": {"$sum": 1}
                }
            }
        ]))

        # Convert to dict
        stats_dict = {item["_id"]: item["count"] for item in lead_stats}
        total_leads = sum(stats_dict.values())

        # Get sentiment average
        sentiment_pipeline = [
            {"$match": {"campaign_id": campaign_obj_id, "sentiment": {"$ne": None}}},
            {
                "$group": {
                    "_id": None,
                    "avg_score": {"$avg": "$sentiment.score"}
                }
            }
        ]
        sentiment_result = list(leads_collection.aggregate(sentiment_pipeline))
        avg_sentiment = sentiment_result[0]["avg_score"] if sentiment_result else None

        # Get calendar bookings
        calendar_bookings = leads_collection.count_documents({
            "campaign_id": campaign_obj_id,
            "calendar_booked": True
        })

        # Get call stats
        call_stats = list(call_attempts_collection.aggregate([
            {"$match": {"campaign_id": campaign_obj_id}},
            {
                "$group": {
                    "_id": None,
                    "total_calls": {"$sum": 1},
                    "avg_duration": {"$avg": "$duration"}
                }
            }
        ]))

        total_calls = call_stats[0]["total_calls"] if call_stats else 0
        avg_duration = call_stats[0]["avg_duration"] if call_stats else None

        result = CampaignStats(
            total_leads=total_leads,
            queued=stats_dict.get("queued", 0),
            completed=stats_dict.get("completed", 0),
            failed=stats_dict.get("failed", 0),
            no_answer=stats_dict.get("no-answer", 0),
            busy=stats_dict.get("busy", 0),
            calling=stats_dict.get("calling", 0),
            avg_sentiment_score=avg_sentiment,
            calendar_bookings=calendar_bookings,
            total_calls=total_calls,
            avg_call_duration=avg_duration
        )
        
        # Cache the result for 2 seconds (blazing fast polling)
        from app.utils.cache import set_to_cache, generate_cache_key
        cache_key = generate_cache_key("campaign:stats", campaign_id)
        await set_to_cache(cache_key, result.dict(), expire=2)
        
        return result

    except HTTPException:
        raise
    except Exception as error:
        logger.error(f"Error fetching campaign stats: {error}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch stats")


@router.get("/{campaign_id}/status", status_code=status.HTTP_200_OK)
async def get_campaign_status_overview(campaign_id: str):
    """
    Lightweight status summary used by dispatcher dashboards.
    """
    try:
        db = Database.get_db()
        campaigns_collection = db["campaigns"]

        try:
            campaign_obj_id = ObjectId(campaign_id)
        except Exception:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid campaign_id format")

        campaign = campaigns_collection.find_one({"_id": campaign_obj_id})
        if not campaign:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

        leads_collection = db["leads"]
        pipeline = [
            {"$match": {"campaign_id": campaign_obj_id}},
            {"$group": {"_id": "$status", "count": {"$sum": 1}}}
        ]
        summary = {doc["_id"]: doc["count"] for doc in leads_collection.aggregate(pipeline)}
        now = datetime.utcnow()
        next_retry = leads_collection.count_documents({
            "campaign_id": campaign_obj_id,
            "status": {"$in": ["queued", "pending"]},
            "next_retry_at": {"$lte": now}
        })
        in_progress = summary.get("calling", 0)
        max_lines = min(
            campaign.get("pacing", {}).get("max_concurrent", 1),
            campaign.get("lines", 1)
        )

        return {
            "campaign_id": campaign_id,
            "status": campaign.get("status"),
            "counts": summary,
            "next_retry_ready": next_retry,
            "concurrency": {
                "active": in_progress,
                "max_lines": max_lines,
                "available": max(0, max_lines - in_progress)
            }
        }

    except HTTPException:
        raise
    except Exception as error:
        logger.error(f"Error fetching campaign status overview: {error}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch status")


@router.get("/{campaign_id}/export", status_code=status.HTTP_200_OK)
async def export_campaign_report(campaign_id: str):
    """Export campaign report as CSV"""
    try:
        db = Database.get_db()
        leads_collection = db["leads"]
        call_attempts_collection = db["call_attempts"]

        try:
            campaign_obj_id = ObjectId(campaign_id)
        except Exception:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid campaign_id format")

        # Get all leads with call attempts
        leads = list(leads_collection.find({"campaign_id": campaign_obj_id}))

        # Create CSV in memory
        output = io.StringIO()
        writer = csv.writer(output)

        # Write header
        writer.writerow([
            "Lead ID",
            "Number",
            "Name",
            "Status",
            "Attempts",
            "Sentiment",
            "Sentiment Score",
            "Calendar Booked",
            "Recording URL",
            "Summary"
        ])

        # Write data rows
        for lead in leads:
            lead_id = str(lead["_id"])

            # Get last call attempt with recording
            call_attempt = call_attempts_collection.find_one(
                {"lead_id": lead["_id"], "recording_url": {"$ne": None}},
                sort=[("started_at", -1)]
            )

            recording_url = call_attempt.get("recording_url") if call_attempt else ""
            sentiment = lead.get("sentiment", {})

            writer.writerow([
                lead_id,
                lead.get("e164", ""),
                lead.get("name", ""),
                lead.get("status", ""),
                lead.get("attempts", 0),
                sentiment.get("label", "") if sentiment else "",
                sentiment.get("score", "") if sentiment else "",
                "Yes" if lead.get("calendar_booked") else "No",
                recording_url,
                lead.get("summary", "")
            ])

        # Return as streaming response
        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=campaign_{campaign_id}_report.csv"}
        )

    except HTTPException:
        raise
    except Exception as error:
        logger.error(f"Error exporting campaign: {error}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to export report")


# ===== DELETE CAMPAIGN =====

@router.delete("/{campaign_id}", status_code=status.HTTP_200_OK)
async def delete_campaign(campaign_id: str):
    """
    Delete a campaign and all its associated data (leads, call attempts).

    Args:
        campaign_id: Campaign ID

    Returns:
        Success message

    Raises:
        HTTPException: If campaign not found or error occurs
    """
    try:
        db = Database.get_db()
        campaigns_collection = db['campaigns']
        leads_collection = db['leads']
        call_attempts_collection = db['call_attempts']

        logger.info(f"Deleting campaign: {campaign_id}")

        # Validate and convert campaign_id to ObjectId
        try:
            campaign_obj_id = ObjectId(campaign_id)
        except Exception as e:
            logger.error(f"Invalid campaign_id format: {campaign_id}, error: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid campaign_id format: {str(e)}"
            )

        # Check if campaign exists
        campaign = campaigns_collection.find_one({"_id": campaign_obj_id})
        if not campaign:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Campaign not found"
            )

        # Delete all call attempts for this campaign's leads
        leads_cursor = leads_collection.find({"campaign_id": campaign_obj_id})
        lead_ids = [lead["_id"] for lead in leads_cursor]

        if lead_ids:
            call_attempts_result = call_attempts_collection.delete_many(
                {"lead_id": {"$in": lead_ids}}
            )
            logger.info(f"Deleted {call_attempts_result.deleted_count} call attempts")

        # Delete all leads for this campaign
        leads_result = leads_collection.delete_many({"campaign_id": campaign_obj_id})
        logger.info(f"Deleted {leads_result.deleted_count} leads")

        # Delete the campaign
        campaigns_collection.delete_one({"_id": campaign_obj_id})
        logger.info(f"Campaign {campaign_id} deleted successfully")

        return {
            "message": "Campaign deleted successfully",
            "deleted_leads": leads_result.deleted_count,
            "deleted_call_attempts": call_attempts_result.deleted_count if lead_ids else 0
        }

    except HTTPException:
        raise
    except Exception as error:
        import traceback
        error_detail = traceback.format_exc()
        logger.error(f"Error deleting campaign: {error}")
        logger.error(f"Full traceback: {error_detail}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete campaign: {str(error)}"
        )


# ===== SCHEDULER ENDPOINTS (for cron jobs) =====

@router.post("/scheduler/check", status_code=status.HTTP_200_OK)
async def scheduler_check_campaigns():
    """
    Scheduler endpoint: Check all running campaigns and dial next leads.
    Call this periodically (every 5-10 minutes) via cron or scheduler.
    """
    try:
        from app.services.campaign_scheduler import CampaignScheduler
        scheduler = CampaignScheduler()
        scheduler.check_and_dial_campaigns()
        return {"message": "Campaign check completed"}
    except Exception as error:
        logger.error(f"Error in scheduler check: {error}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Scheduler check failed")


@router.post("/scheduler/retry", status_code=status.HTTP_200_OK)
async def scheduler_process_retries():
    """
    Scheduler endpoint: Process retry leads for all campaigns.
    Call this once daily (e.g., 8 AM) via cron.
    """
    try:
        from app.services.campaign_scheduler import CampaignScheduler
        scheduler = CampaignScheduler()
        scheduler.process_all_campaign_retries()
        return {"message": "Retry processing completed"}
    except Exception as error:
        logger.error(f"Error in scheduler retry: {error}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Scheduler retry failed")

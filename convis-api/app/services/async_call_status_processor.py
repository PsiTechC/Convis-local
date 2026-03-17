"""
Async Call Status Processor
Non-blocking version using Motor async MongoDB driver
"""
from datetime import datetime
from typing import Optional

import logging

from app.config.async_database import AsyncDatabase
from app.services.async_campaign_dialer import async_campaign_dialer

logger = logging.getLogger(__name__)


async def process_call_status_async(
    call_sid: Optional[str],
    call_status: Optional[str],
    call_duration: Optional[str],
    lead_id: Optional[str],
    campaign_id: Optional[str],
):
    """
    Update call attempt records and notify the dialer about completion (async version).

    This is the non-blocking version that:
    1. Uses Motor async MongoDB driver
    2. Uses async campaign dialer
    3. Doesn't block the FastAPI event loop
    """
    if not call_sid or not call_status:
        raise ValueError("call_sid and call_status are required")

    logger.info(f"[ASYNC_PROCESSOR] Processing call status - SID: {call_sid}, Status: {call_status}, Lead: {lead_id}, Campaign: {campaign_id}")

    db = await AsyncDatabase.get_db()
    call_attempts_collection = db["call_attempts"]

    update_data = {
        "status": call_status,
        "updated_at": datetime.utcnow()
    }

    if call_duration:
        try:
            update_data["duration"] = int(call_duration)
        except ValueError:
            logger.warning("Invalid CallDuration '%s' for CallSid %s", call_duration, call_sid)

    if call_status in ["completed", "busy", "no-answer", "failed", "canceled"]:
        update_data["ended_at"] = datetime.utcnow()
        logger.info(f"[ASYNC_PROCESSOR] Call ended - Status: {call_status}, SID: {call_sid}")

    await call_attempts_collection.update_one(
        {"call_sid": call_sid},
        {"$set": update_data},
        upsert=True
    )
    logger.info(f"[ASYNC_PROCESSOR] Updated call attempt record for SID: {call_sid}")

    # Handle call completion
    if call_status in ["completed", "busy", "no-answer", "failed", "canceled"]:
        # Lookup campaign_id from lead if missing
        if not campaign_id and lead_id:
            logger.warning(f"[ASYNC_PROCESSOR] campaignId missing, looking up from lead {lead_id}")
            try:
                from bson import ObjectId
                leads_collection = db["leads"]
                lead = await leads_collection.find_one({"_id": ObjectId(lead_id)})
                if lead and lead.get("campaign_id"):
                    campaign_id = str(lead["campaign_id"])
                    logger.info(f"[ASYNC_PROCESSOR] Found campaign_id: {campaign_id} from lead")
            except Exception as e:
                logger.error(f"[ASYNC_PROCESSOR] Failed to lookup campaign from lead: {e}")

        if lead_id and campaign_id:
            logger.info(f"[ASYNC_PROCESSOR] Triggering async handle_call_completed for Lead: {lead_id}, Campaign: {campaign_id}")
            await async_campaign_dialer.handle_call_completed(campaign_id, lead_id, call_status)
        else:
            logger.warning(f"[ASYNC_PROCESSOR] Skipping handle_call_completed - Status: {call_status}, Lead: {lead_id}, Campaign: {campaign_id}")

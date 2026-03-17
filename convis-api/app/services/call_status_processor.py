"""Shared helpers for processing Twilio call status callbacks."""

from datetime import datetime
from typing import Optional

import logging

from app.config.database import Database
from app.services.campaign_dialer import CampaignDialer

logger = logging.getLogger(__name__)

_dialer = CampaignDialer()


def process_call_status(
    call_sid: Optional[str],
    call_status: Optional[str],
    call_duration: Optional[str],
    lead_id: Optional[str],
    campaign_id: Optional[str],
):
    """Update call attempt records and notify the dialer about completion."""
    if not call_sid or not call_status:
        raise ValueError("call_sid and call_status are required")

    logger.info(f"[PROCESSOR] Processing call status - SID: {call_sid}, Status: {call_status}, Lead: {lead_id}, Campaign: {campaign_id}")

    db = Database.get_db()
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
        logger.info(f"[PROCESSOR] Call ended - Status: {call_status}, SID: {call_sid}")

    call_attempts_collection.update_one(
        {"call_sid": call_sid},
        {"$set": update_data},
        upsert=True
    )
    logger.info(f"[PROCESSOR] Updated call attempt record for SID: {call_sid}")

    # CRITICAL FIX: If campaignId is missing, look it up from the lead
    if call_status in ["completed", "busy", "no-answer", "failed", "canceled"]:
        if not campaign_id and lead_id:
            logger.warning(f"[PROCESSOR] campaignId missing from webhook, looking up from lead {lead_id}")
            try:
                from bson import ObjectId
                leads_collection = db["leads"]
                lead = leads_collection.find_one({"_id": ObjectId(lead_id)})
                if lead and lead.get("campaign_id"):
                    campaign_id = str(lead["campaign_id"])
                    logger.info(f"[PROCESSOR] Found campaign_id: {campaign_id} from lead")
            except Exception as e:
                logger.error(f"[PROCESSOR] Failed to lookup campaign from lead: {e}")

        if lead_id and campaign_id:
            logger.info(f"[PROCESSOR] Triggering handle_call_completed for Lead: {lead_id}, Campaign: {campaign_id}")
            _dialer.handle_call_completed(campaign_id, lead_id, call_status)
        else:
            logger.warning(f"[PROCESSOR] Skipping handle_call_completed - Status: {call_status}, Lead: {lead_id}, Campaign: {campaign_id}")

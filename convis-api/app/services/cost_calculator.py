"""
Cost Calculator Service
Automatically calculates and stores call costs when calls complete
"""
import logging
from typing import Optional, Dict
from datetime import datetime
from bson import ObjectId

from app.config.database import Database
from app.utils.pricing import PricingCalculator, TWILIO_PRICING, USD_TO_INR

logger = logging.getLogger(__name__)


async def calculate_and_store_call_cost(
    call_sid: str,
    duration_seconds: int,
    currency: str = "USD"
) -> Optional[Dict]:
    """
    Calculate cost for a completed call and store it in the database

    Args:
        call_sid: Twilio Call SID
        duration_seconds: Call duration in seconds
        currency: Currency for cost calculation (USD or INR)

    Returns:
        Dict with cost breakdown if successful, None otherwise
    """
    try:
        db = Database.get_db()
        call_logs_collection = db['call_logs']
        assistants_collection = db['assistants']

        # Get call log
        call_log = call_logs_collection.find_one({"call_sid": call_sid})
        if not call_log:
            logger.warning(f"[COST] Call log not found for SID: {call_sid}")
            return None

        # Skip if cost already calculated
        if call_log.get("cost_calculated"):
            logger.info(f"[COST] Cost already calculated for call: {call_sid}")
            return call_log.get("cost_breakdown")

        # Get duration in minutes
        duration_minutes = duration_seconds / 60.0
        if duration_minutes <= 0:
            logger.warning(f"[COST] Invalid duration for call {call_sid}: {duration_seconds}s")
            return None

        # Get assistant configuration to determine voice mode and providers
        assistant_id = call_log.get("assigned_assistant_id") or call_log.get("assistant_id")
        if not assistant_id:
            logger.warning(f"[COST] No assistant ID found for call: {call_sid}")
            return None

        assistant = assistants_collection.find_one({"_id": ObjectId(str(assistant_id))})
        if not assistant:
            logger.warning(f"[COST] Assistant not found: {assistant_id}")
            return None

        # Determine if using Realtime API or Custom Providers
        asr_provider = call_log.get("asr_provider") or assistant.get("asr_provider", "openai")
        tts_provider = call_log.get("tts_provider") or assistant.get("tts_provider", "openai")
        llm_provider = call_log.get("llm_provider") or assistant.get("llm_provider", "openai")

        # Check if it's OpenAI Realtime API mode
        is_realtime = (
            asr_provider == "openai" and
            tts_provider == "openai" and
            llm_provider in ["openai", "openai-realtime"]
        )

        calculator = PricingCalculator(currency=currency)

        if is_realtime:
            # OpenAI Realtime API cost
            model = call_log.get("model") or assistant.get("model", "gpt-4o-realtime-preview")

            logger.info(f"[COST] Calculating Realtime API cost for {call_sid}: model={model}, duration={duration_minutes:.2f}min")

            cost_breakdown = calculator.calculate_realtime_api_cost(
                model=model,
                duration_minutes=duration_minutes
            )
        else:
            # Custom Provider Pipeline cost
            asr_model = call_log.get("asr_model") or assistant.get("asr_model", "nova-2")
            llm_model = call_log.get("llm_model") or assistant.get("llm_model", "gpt-4o-mini")
            tts_model = call_log.get("tts_model") or assistant.get("tts_model", "tts-1")

            logger.info(f"[COST] Calculating Custom Provider cost for {call_sid}: ASR={asr_provider}/{asr_model}, LLM={llm_provider}/{llm_model}, TTS={tts_provider}/{tts_model}, duration={duration_minutes:.2f}min")

            cost_breakdown = calculator.calculate_custom_pipeline_cost(
                asr_provider=asr_provider,
                asr_model=asr_model,
                llm_provider=llm_provider,
                llm_model=llm_model,
                tts_provider=tts_provider,
                tts_model=tts_model,
                duration_minutes=duration_minutes
            )

        # Derive API cost (always track in USD for consistency)
        api_cost_usd = cost_breakdown.get("api_cost_usd")
        if api_cost_usd is None:
            # Fallback if only total is present (total likely already in USD)
            api_cost_usd = cost_breakdown.get("total_usd", cost_breakdown.get("total", 0.0))

        # Twilio streaming cost returned from calculator (call minutes)
        twilio_call_cost_usd = cost_breakdown.get("twilio_cost_usd", 0.0)
        twilio_call_cost_inr = twilio_call_cost_usd * USD_TO_INR

        # Always include recording charge separately
        twilio_recording_cost_usd = TWILIO_PRICING["recording_per_minute_usd"] * duration_minutes
        twilio_recording_cost_inr = twilio_recording_cost_usd * USD_TO_INR

        # Totals per currency
        api_cost_currency = api_cost_usd * USD_TO_INR if currency == "INR" else api_cost_usd
        twilio_total_usd = twilio_call_cost_usd + twilio_recording_cost_usd
        twilio_total_currency = (
            (twilio_call_cost_inr + twilio_recording_cost_inr)
            if currency == "INR"
            else twilio_total_usd
        )

        total_cost = api_cost_currency + twilio_total_currency

        # Store cost in database
        cost_data = {
            "cost_calculated": True,
            "cost_currency": currency,
            "cost_breakdown": cost_breakdown,
            "cost_twilio": round(twilio_total_currency, 4),
            "cost_twilio_call": round(twilio_call_cost_inr if currency == "INR" else twilio_call_cost_usd, 4),
            "cost_twilio_recording": round(twilio_recording_cost_inr if currency == "INR" else twilio_recording_cost_usd, 4),
            "cost_api": round(api_cost_currency, 4),
            "cost_total": round(total_cost, 4),
            "cost_calculated_at": datetime.utcnow(),
            "duration_minutes": round(duration_minutes, 2),
            "is_realtime_api": is_realtime
        }

        # Update call log with cost information
        call_logs_collection.update_one(
            {"call_sid": call_sid},
            {"$set": cost_data}
        )

        logger.info(f"[COST] ✓ Cost calculated for {call_sid}: Total={currency} {total_cost:.4f} (API: {api_cost:.4f}, Twilio: {twilio_total:.4f})")

        return {
            "total": total_cost,
            "api_cost": api_cost,
            "twilio_cost": twilio_total,
            "currency": currency,
            "duration_minutes": duration_minutes,
            "breakdown": cost_breakdown
        }

    except Exception as e:
        logger.error(f"[COST] Error calculating cost for call {call_sid}: {e}", exc_info=True)
        return None


async def recalculate_all_call_costs(user_id: Optional[str] = None, limit: int = 100):
    """
    Recalculate costs for existing calls that don't have cost data

    Args:
        user_id: Optional user ID to limit recalculation to specific user
        limit: Maximum number of calls to process
    """
    try:
        db = Database.get_db()
        call_logs_collection = db['call_logs']

        # Find calls without cost data
        query = {"cost_calculated": {"$ne": True}, "duration": {"$gt": 0}}
        if user_id:
            query["user_id"] = ObjectId(user_id)

        calls_to_process = list(
            call_logs_collection.find(query)
            .sort("created_at", -1)
            .limit(limit)
        )

        logger.info(f"[COST] Found {len(calls_to_process)} calls to recalculate costs")

        success_count = 0
        for call_log in calls_to_process:
            call_sid = call_log.get("call_sid")
            duration = call_log.get("duration", 0)

            if call_sid and duration > 0:
                result = await calculate_and_store_call_cost(call_sid, duration)
                if result:
                    success_count += 1

        logger.info(f"[COST] Recalculated costs for {success_count}/{len(calls_to_process)} calls")

        return {
            "total_processed": len(calls_to_process),
            "successful": success_count,
            "failed": len(calls_to_process) - success_count
        }

    except Exception as e:
        logger.error(f"[COST] Error in batch cost recalculation: {e}", exc_info=True)
        return {"error": str(e)}

"""
Transcription Management Routes
Handles retroactive transcription and transcription status

OPTIMIZED: Now uses AsyncPostCallProcessor for non-blocking operations.
"""
from fastapi import APIRouter, HTTPException, status
from typing import Dict, Any, List
from datetime import datetime, timedelta
import logging
import asyncio

from app.config.database import Database
from app.config.async_database import AsyncDatabase
from app.services.async_post_call_processor import AsyncPostCallProcessor

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/transcribe-batch")
async def transcribe_batch_calls(batch_size: int = 5, delay_seconds: int = 3):
    """
    Transcribe calls in small batches with delays to avoid rate limits.

    Args:
        batch_size: Number of calls to process in each batch (default: 5)
        delay_seconds: Delay between batches in seconds (default: 3)

    Returns:
        Progress report with transcribed/failed counts
    """
    try:
        logger.info(f"Starting batch transcription (batch_size={batch_size}, delay={delay_seconds}s)...")

        db = Database.get_db()
        call_logs_collection = db['call_logs']

        # Find calls with recordings but no transcripts (or failed transcriptions)
        query = {
            'recording_url': {'$ne': None, '$exists': True},
            '$or': [
                {'transcript': {'$exists': False}},
                {'transcript': None},
                {'transcript': ''},
                {'transcript': '[Transcription unavailable]'}
            ]
        }

        calls_to_transcribe = list(call_logs_collection.find(query).limit(batch_size))
        total = len(calls_to_transcribe)

        logger.info(f"Found {total} calls to transcribe in this batch")

        if total == 0:
            return {
                "message": "All calls already have transcripts!",
                "total_calls": 0,
                "transcribed": 0,
                "failed": 0,
                "remaining": 0
            }

        # Process calls with rate limiting (OPTIMIZED: using async processor)
        processor = AsyncPostCallProcessor()
        transcribed = 0
        failed = 0

        for i, call in enumerate(calls_to_transcribe, 1):
            call_sid = call.get('call_sid')
            recording_url = call.get('recording_url')

            try:
                logger.info(f"[{i}/{total}] Transcribing {call_sid}...")
                await processor.transcribe_and_update_call(call_sid, recording_url)
                transcribed += 1
                logger.info(f"[{i}/{total}] Transcribed {call_sid}")

                # Delay between each call to avoid rate limits
                if i < total:
                    await asyncio.sleep(delay_seconds)

            except Exception as e:
                failed += 1
                logger.error(f"✗ [{i}/{total}] Failed to transcribe {call_sid}: {e}")

        # Check remaining calls
        remaining = call_logs_collection.count_documents(query)

        return {
            "message": f"Batch complete! {transcribed}/{total} calls transcribed successfully.",
            "total_calls": total,
            "transcribed": transcribed,
            "failed": failed,
            "remaining": remaining,
            "next_action": "Call this endpoint again to process next batch" if remaining > 0 else "All done!"
        }

    except Exception as e:
        logger.error(f"Error in transcribe_batch: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/transcribe-all")
async def transcribe_all_calls():
    """
    Transcribe all past calls that have recordings but no transcripts.
    This can be triggered from the UI.

    WARNING: May hit rate limits if there are many calls.
    Use /transcribe-batch for safer processing.
    """
    try:
        logger.info("Starting retroactive transcription...")

        db = Database.get_db()
        call_logs_collection = db['call_logs']

        # Find calls with recordings but no transcripts (or failed transcriptions)
        query = {
            'recording_url': {'$ne': None, '$exists': True},
            '$or': [
                {'transcript': {'$exists': False}},
                {'transcript': None},
                {'transcript': ''},
                {'transcript': '[Transcription unavailable]'}
            ]
        }

        calls_to_transcribe = list(call_logs_collection.find(query))
        total = len(calls_to_transcribe)

        logger.info(f"Found {total} calls to transcribe")

        if total == 0:
            return {
                "message": "All calls already have transcripts!",
                "total_calls": 0,
                "transcribed": 0,
                "failed": 0
            }

        # Process calls with delays to reduce rate limit issues (OPTIMIZED: using async processor)
        processor = AsyncPostCallProcessor()
        transcribed = 0
        failed = 0

        for i, call in enumerate(calls_to_transcribe, 1):
            call_sid = call.get('call_sid')
            recording_url = call.get('recording_url')

            try:
                logger.info(f"[{i}/{total}] Transcribing {call_sid}...")
                await processor.transcribe_and_update_call(call_sid, recording_url)
                transcribed += 1
                logger.info(f"[{i}/{total}] Transcribed {call_sid}")

                # 2 second delay between calls to avoid rate limits
                if i < total:
                    await asyncio.sleep(2)

            except Exception as e:
                failed += 1
                logger.error(f"✗ [{i}/{total}] Failed to transcribe {call_sid}: {e}")

        return {
            "message": f"Transcription complete! {transcribed}/{total} calls transcribed successfully.",
            "total_calls": total,
            "transcribed": transcribed,
            "failed": failed
        }

    except Exception as e:
        logger.error(f"Error in transcribe_all: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/reanalyze/{call_sid}")
async def reanalyze_single_call(call_sid: str):
    """
    Re-analyze a single call to extract customer data (email, name) and conversation log.
    Useful for testing or fixing individual calls.
    """
    try:
        logger.info(f"Re-analyzing call {call_sid}...")

        db = Database.get_db()
        call_logs_collection = db['call_logs']

        # Find the call
        call = call_logs_collection.find_one({'call_sid': call_sid})
        if not call:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Call {call_sid} not found"
            )

        transcript = call.get('transcript')
        if not transcript or transcript in ['', '[Transcription unavailable]']:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Call has no transcript to analyze"
            )

        recording_url = call.get('recording_url')
        processor = AsyncPostCallProcessor()

        # Force re-analysis to extract customer data with updated GPT prompt
        await processor.transcribe_and_update_call(call_sid, recording_url, force_reanalyze=True)

        # Fetch updated call
        updated_call = call_logs_collection.find_one({'call_sid': call_sid})

        return {
            "message": f"Re-analysis complete for call {call_sid}",
            "call_sid": call_sid,
            "customer_data": updated_call.get('customer_data'),
            "conversation_log_count": len(updated_call.get('conversation_log', []) or []),
            "summary": updated_call.get('summary'),
            "sentiment": updated_call.get('sentiment')
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error re-analyzing call {call_sid}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/reanalyze-all")
async def reanalyze_all_transcripts():
    """
    Re-analyze all calls that have transcripts but no conversation_log.
    This will use GPT to parse the transcript into User/Assistant conversation format.
    """
    try:
        logger.info("Starting re-analysis for conversation parsing...")

        db = Database.get_db()
        call_logs_collection = db['call_logs']

        # Find calls with transcripts but no conversation_log
        query = {
            'transcript': {'$ne': None, '$exists': True, '$nin': ['', '[Transcription unavailable]']},
            '$or': [
                {'conversation_log': {'$exists': False}},
                {'conversation_log': None},
                {'conversation_log': []}
            ]
        }

        calls_to_reanalyze = list(call_logs_collection.find(query).limit(20))  # Process 20 at a time
        total = len(calls_to_reanalyze)

        logger.info(f"Found {total} calls to re-analyze for conversation parsing")

        if total == 0:
            return {
                "message": "All calls already have conversation logs!",
                "total_calls": 0,
                "reanalyzed": 0,
                "failed": 0
            }

        processor = AsyncPostCallProcessor()
        reanalyzed = 0
        failed = 0

        for i, call in enumerate(calls_to_reanalyze, 1):
            call_sid = call.get('call_sid')
            recording_url = call.get('recording_url')

            try:
                logger.info(f"[{i}/{total}] Re-analyzing {call_sid}...")
                await processor.transcribe_and_update_call(call_sid, recording_url)
                reanalyzed += 1
                logger.info(f"[{i}/{total}] Re-analyzed {call_sid}")

                # 2 second delay between calls to avoid rate limits
                if i < total:
                    await asyncio.sleep(2)

            except Exception as e:
                failed += 1
                logger.error(f"✗ [{i}/{total}] Failed to re-analyze {call_sid}: {e}")

        # Count remaining
        remaining = call_logs_collection.count_documents(query)

        return {
            "message": f"Re-analysis complete! {reanalyzed}/{total} calls processed.",
            "total_calls": total,
            "reanalyzed": reanalyzed,
            "failed": failed,
            "remaining": remaining,
            "next_action": "Call this endpoint again to process more" if remaining > 0 else "All done!"
        }

    except Exception as e:
        logger.error(f"Error in reanalyze_all: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/status")
async def transcription_status():
    """
    Get transcription coverage statistics
    """
    try:
        db = Database.get_db()
        call_logs = db['call_logs']

        total_calls = call_logs.count_documents({})
        with_recordings = call_logs.count_documents({'recording_url': {'$ne': None}})
        with_transcripts = call_logs.count_documents({'transcript': {'$ne': None, '$exists': True}})

        coverage = (with_transcripts / with_recordings * 100) if with_recordings > 0 else 0

        return {
            "total_calls": total_calls,
            "calls_with_recordings": with_recordings,
            "calls_with_transcripts": with_transcripts,
            "coverage_percentage": round(coverage, 1),
            "needs_transcription": with_recordings - with_transcripts
        }

    except Exception as e:
        logger.error(f"Error getting transcription status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/fetch-from-twilio")
async def fetch_recordings_from_twilio():
    """
    Fetch recordings from Twilio for calls that don't have recording URLs
    """
    try:
        import os
        from twilio.rest import Client

        account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        auth_token = os.getenv("TWILIO_AUTH_TOKEN")

        if not account_sid or not auth_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Twilio credentials not configured"
            )

        client = Client(account_sid, auth_token)
        db = Database.get_db()
        call_logs = db['call_logs']

        # Fetch recordings from last 30 days
        cutoff = datetime.utcnow() - timedelta(days=30)
        recordings = client.recordings.list(date_created_after=cutoff, limit=500)

        logger.info(f"Found {len(recordings)} recordings in Twilio")

        updated = 0
        transcribed = 0
        processor = AsyncPostCallProcessor()

        for rec in recordings:
            call_sid = rec.call_sid
            recording_url = f"https://api.twilio.com{rec.uri.replace('.json', '.mp3')}"

            # Check if call exists
            call_log = call_logs.find_one({'call_sid': call_sid})

            if not call_log:
                # Create new entry
                call_logs.insert_one({
                    'call_sid': call_sid,
                    'recording_url': recording_url,
                    'recording_sid': rec.sid,
                    'created_at': rec.date_created,
                    'updated_at': datetime.utcnow()
                })
                updated += 1

            # Update recording URL if missing
            elif not call_log.get('recording_url'):
                call_logs.update_one(
                    {'call_sid': call_sid},
                    {'$set': {'recording_url': recording_url, 'recording_sid': rec.sid}}
                )
                updated += 1

            # Transcribe if needed
            if not call_log or not call_log.get('transcript'):
                try:
                    await processor.transcribe_and_update_call(call_sid, recording_url)
                    transcribed += 1
                    await asyncio.sleep(0.5)
                except Exception as e:
                    logger.error(f"Error transcribing {call_sid}: {e}")

        return {
            "message": f"Fetched {len(recordings)} recordings from Twilio",
            "total_recordings": len(recordings),
            "recordings_added": updated,
            "transcribed": transcribed
        }

    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Twilio library not installed"
        )
    except Exception as e:
        logger.error(f"Error fetching from Twilio: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

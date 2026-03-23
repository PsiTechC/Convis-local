"""
Async Inbound Post-Call Processor
Optimized with parallel operations using asyncio.gather
"""
import logging
import httpx
import asyncio
from typing import Optional, Dict, Any
from datetime import datetime
from bson import ObjectId

from app.config.async_database import AsyncDatabase
from app.config.settings import settings

logger = logging.getLogger(__name__)


class AsyncInboundPostCallProcessor:
    """
    Async processor for inbound calls with parallel operations.

    Optimizations:
    1. Motor async driver for non-blocking DB operations
    2. Parallel transcription update + analysis
    3. Parallel calendar booking + WhatsApp notification
    """

    def __init__(self):
        self.openai_api_key = settings.openai_api_key

    async def download_recording(self, recording_url: str) -> Optional[bytes]:
        """Download call recording from Twilio (non-blocking)."""
        try:
            if not recording_url.endswith('.mp3'):
                recording_url = recording_url + '.mp3'

            auth = None
            if settings.twilio_account_sid and settings.twilio_auth_token:
                auth = (settings.twilio_account_sid, settings.twilio_auth_token)

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    recording_url,
                    auth=auth,
                    timeout=60.0,
                    follow_redirects=True
                )
                response.raise_for_status()
                logger.info(f"Downloaded recording: {len(response.content)} bytes")
                return response.content

        except Exception as e:
            logger.error(f"Error downloading recording from {recording_url}: {e}")
            return None

    async def transcribe_audio(self, audio_bytes: bytes) -> Optional[str]:
        """Transcribe audio using OpenAI Whisper API (non-blocking)."""
        try:
            if not self.openai_api_key:
                logger.error("OpenAI API key not configured")
                return None

            async with httpx.AsyncClient() as client:
                files = {
                    'file': ('recording.mp3', audio_bytes, 'audio/mpeg'),
                }
                data = {
                    'model': 'whisper-1',
                    'language': 'en',
                }

                response = await client.post(
                    'https://api.openai.com/v1/audio/transcriptions',
                    headers={'Authorization': f'Bearer {self.openai_api_key}'},
                    files=files,
                    data=data,
                    timeout=120.0
                )
                response.raise_for_status()
                result = response.json()
                transcript = result.get('text', '').strip()
                logger.info(f"Transcription completed: {len(transcript)} characters")
                return transcript

        except Exception as e:
            logger.error(f"Error transcribing audio: {e}")
            return None

    async def analyze_transcript(self, transcript: str) -> Optional[Dict[str, Any]]:
        """Analyze transcript using GPT (non-blocking)."""
        try:
            if not self.openai_api_key or not transcript or len(transcript.strip()) < 10:
                return {
                    "sentiment": "neutral",
                    "sentiment_score": 0.0,
                    "summary": "Call too short or empty transcript.",
                    "appointment": None
                }

            prompt = f"""Analyze the following phone call transcript and provide a structured JSON response.

The transcript is from an inbound call to our AI assistant.

Provide a JSON response with these exact fields:
- sentiment: one of "positive", "neutral", or "negative"
- sentiment_score: a float between -1.0 (very negative) and 1.0 (very positive)
- summary: a concise summary in 3-8 sentences describing what was discussed
- appointment: if a meeting/appointment was scheduled, provide an object with {{title, start_iso, end_iso, timezone}}, otherwise null

TRANSCRIPT:
{transcript}

Respond ONLY with the JSON object, no additional text."""

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    'https://api.openai.com/v1/chat/completions',
                    headers={
                        'Authorization': f'Bearer {self.openai_api_key}',
                        'Content-Type': 'application/json'
                    },
                    json={
                        'model': 'gpt-4o-mini',
                        'messages': [
                            {'role': 'system', 'content': 'You are an expert at analyzing phone call transcripts. Always respond with valid JSON only.'},
                            {'role': 'user', 'content': prompt}
                        ],
                        'temperature': 0.3,
                        'response_format': {'type': 'json_object'}
                    },
                    timeout=60.0
                )
                response.raise_for_status()
                result = response.json()

                content = result['choices'][0]['message']['content']
                import json
                analysis = json.loads(content)

                logger.info(f"Analysis completed - Sentiment: {analysis.get('sentiment')}")
                return analysis

        except Exception as e:
            logger.error(f"Error analyzing transcript: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                "sentiment": "neutral",
                "sentiment_score": 0.0,
                "summary": "Unable to analyze call.",
                "appointment": None
            }

    async def process_inbound_call(self, call_sid: str, assistant_id: str, recording_url: str):
        """
        Process a completed inbound call with OPTIMIZED parallel operations.

        Flow:
        1. Get assistant info + Download recording (PARALLEL)
        2. Transcribe audio (sequential - needed for analysis)
        3. PARALLEL: Analyze transcript + Update call log with transcript
        4. PARALLEL: Calendar booking + WhatsApp notification + Final DB update
        """
        try:
            logger.info(f"[ASYNC] Starting post-call processing for inbound call {call_sid}")

            db = await AsyncDatabase.get_db()
            assistants_collection = db['assistants']
            call_logs_collection = db['call_logs']

            # Step 1: PARALLEL - Get assistant info + Download recording
            async def get_assistant():
                return await assistants_collection.find_one({"_id": ObjectId(assistant_id)})

            assistant_task = get_assistant()
            download_task = self.download_recording(recording_url)

            assistant, audio_bytes = await asyncio.gather(assistant_task, download_task)

            if not assistant:
                logger.error(f"Assistant {assistant_id} not found")
                return

            user_id = assistant.get('user_id')
            if not user_id:
                logger.error(f"No user_id found for assistant {assistant_id}")
                return

            if not audio_bytes:
                logger.error(f"Failed to download recording for call {call_sid}")
                return

            # Step 2: Transcribe audio (sequential - needed for analysis)
            transcript = await self.transcribe_audio(audio_bytes)
            if not transcript:
                logger.error(f"Failed to transcribe call {call_sid}")
                return

            logger.info(f"Transcript for call {call_sid}: {transcript[:200]}...")

            # Step 3: PARALLEL - Analyze transcript + Update call log with transcript
            async def update_transcript_in_db():
                await call_logs_collection.update_one(
                    {"call_sid": call_sid},
                    {"$set": {"transcript": transcript, "updated_at": datetime.utcnow()}}
                )

            analysis_task = self.analyze_transcript(transcript)
            db_task = update_transcript_in_db()

            analysis, _ = await asyncio.gather(analysis_task, db_task)

            if not analysis:
                logger.error(f"Failed to analyze transcript for call {call_sid}")
                return

            # Step 4: PARALLEL - Update analysis in DB + Handle appointment + WhatsApp
            async def update_analysis_in_db():
                await call_logs_collection.update_one(
                    {"call_sid": call_sid},
                    {
                        "$set": {
                            "sentiment": analysis.get("sentiment"),
                            "sentiment_score": analysis.get("sentiment_score"),
                            "summary": analysis.get("summary"),
                            "analyzed_at": datetime.utcnow(),
                            "updated_at": datetime.utcnow()
                        }
                    }
                )

            async def handle_appointment_and_whatsapp():
                """Handle calendar booking and WhatsApp notification in one task."""
                appointment = analysis.get("appointment")
                if not appointment or not appointment.get("start_iso"):
                    return

                logger.info(f"Appointment detected for inbound call {call_sid}: {appointment.get('title')}")

                try:
                    from app.services.calendar_service import CalendarService

                    calendar_service = CalendarService()
                    await calendar_service.book_inbound_appointment(
                        call_sid=call_sid,
                        user_id=str(user_id),
                        assistant_id=assistant_id,
                        appointment=appointment
                    )
                    logger.info(f"Calendar appointment booked for inbound call {call_sid}")

                    # Send WhatsApp confirmation
                    await self._send_whatsapp_confirmation(
                        db, call_sid, user_id, appointment
                    )

                except ImportError:
                    logger.warning("CalendarService not available")
                except Exception as e:
                    logger.error(f"Error booking appointment: {e}")
                    import traceback
                    logger.error(traceback.format_exc())

            async def update_calendar_event_with_summary():
                """Update calendar event with call summary after processing."""
                try:
                    from app.services.calendar_service import CalendarService

                    # Get call log to check for call duration
                    call_log = await call_logs_collection.find_one({"call_sid": call_sid})
                    call_duration = call_log.get("duration") if call_log else None

                    calendar_service = CalendarService()
                    await calendar_service.update_event_with_call_summary(
                        call_sid=call_sid,
                        call_summary=analysis.get("summary", "No summary available"),
                        transcript=transcript,
                        recording_url=recording_url,
                        call_duration=call_duration
                    )
                    logger.info(f"[CALENDAR_SUMMARY] Calendar event updated for call {call_sid}")
                except ImportError:
                    logger.warning("CalendarService not available for summary update")
                except Exception as e:
                    logger.warning(f"Error updating calendar with summary: {e}")

            # Run all final operations in parallel
            await asyncio.gather(
                update_analysis_in_db(),
                handle_appointment_and_whatsapp(),
                update_calendar_event_with_summary(),
                return_exceptions=True
            )

            logger.info(f"[ASYNC] Post-call processing completed for inbound call {call_sid}")

        except Exception as e:
            logger.error(f"Error in async inbound post-call processing: {e}")
            import traceback
            logger.error(traceback.format_exc())

    async def _send_whatsapp_confirmation(
        self,
        db,
        call_sid: str,
        user_id,
        appointment: Dict[str, Any]
    ):
        """Send WhatsApp confirmation asynchronously."""
        try:
            from app.services.appointment_whatsapp_service import AppointmentWhatsAppService

            call_logs_collection = db["call_logs"]
            call_log = await call_logs_collection.find_one({"call_sid": call_sid})

            if call_log and call_log.get("from_number"):
                caller_phone = call_log["from_number"]
                customer_name = call_log.get("caller_name", "Customer")

                booking_data = {
                    "_id": call_sid,
                    "customer_name": customer_name,
                    "start_time": appointment.get("start_iso"),
                    "location": appointment.get("location", "Phone Call"),
                    "duration": appointment.get("duration", 30)
                }

                whatsapp_result = await AppointmentWhatsAppService.send_appointment_confirmation(
                    user_id=str(user_id),
                    booking_data=booking_data,
                    phone_number=caller_phone
                )

                if whatsapp_result.get("success"):
                    logger.info(f"WhatsApp confirmation sent to {caller_phone} for call {call_sid}")
                else:
                    logger.warning(f"Failed to send WhatsApp confirmation: {whatsapp_result.get('error')}")
            else:
                logger.warning(f"No phone number found for call {call_sid}, skipping WhatsApp")

        except Exception as whatsapp_error:
            logger.error(f"Error sending WhatsApp confirmation: {whatsapp_error}")
            import traceback
            logger.error(traceback.format_exc())


# Singleton instance for easy import
async_inbound_processor = AsyncInboundPostCallProcessor()

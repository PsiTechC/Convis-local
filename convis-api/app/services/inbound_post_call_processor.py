"""
Inbound Post-Call Processor
Handles transcription, analysis, and appointment booking for inbound calls
"""
import logging
import httpx
from typing import Optional, Dict, Any
from datetime import datetime
from bson import ObjectId

from app.config.database import Database
from app.config.settings import settings

logger = logging.getLogger(__name__)


class InboundPostCallProcessor:
    """Process inbound calls after completion: transcribe, analyze, and book appointments"""

    def __init__(self):
        self.db = Database.get_db()
        self.call_logs_collection = self.db['call_logs']
        self.assistants_collection = self.db['assistants']
        # MongoDB databases don't have .get() method, use direct access
        self.inbound_call_logs_collection = self.db['call_logs']
        self.openai_api_key = settings.openai_api_key

    async def download_recording(self, recording_url: str) -> Optional[bytes]:
        """
        Download call recording from Twilio.

        Args:
            recording_url: URL to the recording

        Returns:
            Audio bytes or None
        """
        try:
            # Twilio recordings need .mp3 extension for download
            if not recording_url.endswith('.mp3'):
                recording_url = recording_url + '.mp3'

            # Use Twilio credentials for authentication
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
        """
        Transcribe audio using OpenAI Whisper API.

        Args:
            audio_bytes: Audio file bytes

        Returns:
            Transcript text or None
        """
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
        """
        Analyze transcript using GPT to extract sentiment, summary, and appointment info.

        Args:
            transcript: Call transcript

        Returns:
            Analysis dict with sentiment, summary, and appointment or None
        """
        try:
            if not self.openai_api_key or not transcript or len(transcript.strip()) < 10:
                return {
                    "sentiment": "neutral",
                    "sentiment_score": 0.0,
                    "summary": "Call too short or empty transcript.",
                    "appointment": None
                }

            # Construct prompt for GPT
            prompt = f"""Analyze the following phone call transcript and provide a structured JSON response.

The transcript is from an inbound call to our AI assistant.

Provide a JSON response with these exact fields:
- sentiment: one of "positive", "neutral", or "negative"
- sentiment_score: a float between -1.0 (very negative) and 1.0 (very positive)
- summary: a concise summary in 3-8 sentences describing what was discussed
- appointment: if a meeting/appointment was scheduled, provide an object with {{title, start_iso, end_iso, timezone}}, otherwise null

Example format:
{{
  "sentiment": "positive",
  "sentiment_score": 0.7,
  "summary": "The caller inquired about product pricing...",
  "appointment": {{
    "title": "Follow-up Meeting",
    "start_iso": "2025-01-13T13:00:00",
    "end_iso": "2025-01-13T14:00:00",
    "timezone": "America/New_York"
  }}
}}

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

                logger.info(f"Analysis completed - Sentiment: {analysis.get('sentiment')}, Appointment: {bool(analysis.get('appointment'))}")
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
        Process a completed inbound call: transcribe, analyze, and book appointments.

        Args:
            call_sid: Twilio call SID
            assistant_id: AI assistant ID used for the call
            recording_url: URL to the call recording
        """
        try:
            logger.info(f"Starting post-call processing for inbound call {call_sid}")

            # Step 1: Get assistant to find user_id
            assistant = self.assistants_collection.find_one({"_id": ObjectId(assistant_id)})
            if not assistant:
                logger.error(f"Assistant {assistant_id} not found")
                return

            user_id = assistant.get('user_id')
            if not user_id:
                logger.error(f"No user_id found for assistant {assistant_id}")
                return

            # Step 2: Download recording
            audio_bytes = await self.download_recording(recording_url)
            if not audio_bytes:
                logger.error(f"Failed to download recording for call {call_sid}")
                return

            # Step 3: Transcribe audio
            transcript = await self.transcribe_audio(audio_bytes)
            if not transcript:
                logger.error(f"Failed to transcribe call {call_sid}")
                return

            logger.info(f"Transcript for call {call_sid}: {transcript[:200]}...")

            # Step 4: Analyze transcript
            analysis = await self.analyze_transcript(transcript)
            if not analysis:
                logger.error(f"Failed to analyze transcript for call {call_sid}")
                return

            # Step 5: Update call log with analysis
            self.call_logs_collection.update_one(
                {"call_sid": call_sid},
                {
                    "$set": {
                        "transcript": transcript,
                        "sentiment": analysis.get("sentiment"),
                        "sentiment_score": analysis.get("sentiment_score"),
                        "summary": analysis.get("summary"),
                        "analyzed_at": datetime.utcnow(),
                        "updated_at": datetime.utcnow()
                    }
                }
            )

            # Step 6: Handle appointment booking if present
            appointment = analysis.get("appointment")
            if appointment and appointment.get("start_iso"):
                logger.info(f"Appointment detected for inbound call {call_sid}: {appointment.get('title')}")

                try:
                    from app.services.calendar_service import CalendarService

                    calendar_service = CalendarService()

                    # For inbound calls, we don't have a lead_id or campaign_id
                    # We'll create a generic inbound call record
                    await calendar_service.book_inbound_appointment(
                        call_sid=call_sid,
                        user_id=str(user_id),
                        assistant_id=assistant_id,
                        appointment=appointment
                    )

                    logger.info(f"Calendar appointment booked for inbound call {call_sid}")

                    # Step 6a: Send WhatsApp confirmation if phone number available
                    try:
                        from app.services.appointment_whatsapp_service import AppointmentWhatsAppService

                        # Get caller's phone number from call logs
                        call_log = db["call_logs"].find_one({"call_sid": call_sid})
                        if call_log and call_log.get("from_number"):
                            caller_phone = call_log["from_number"]

                            # Get customer name from call log or use generic name
                            customer_name = call_log.get("caller_name", "Customer")

                            # Prepare booking data for WhatsApp
                            booking_data = {
                                "_id": call_sid,  # Use call_sid as booking identifier
                                "customer_name": customer_name,
                                "start_time": appointment.get("start_iso"),
                                "location": appointment.get("location", "Phone Call"),
                                "duration": appointment.get("duration", 30)
                            }

                            # Send WhatsApp confirmation
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
                            logger.warning(f"No phone number found for call {call_sid}, skipping WhatsApp confirmation")

                    except Exception as whatsapp_error:
                        logger.error(f"Error sending WhatsApp confirmation: {whatsapp_error}")
                        # Don't fail the entire process if WhatsApp fails
                        import traceback
                        logger.error(traceback.format_exc())

                except ImportError:
                    logger.warning("CalendarService not available")
                except Exception as e:
                    logger.error(f"Error booking appointment: {e}")
                    import traceback
                    logger.error(traceback.format_exc())

            logger.info(f"Post-call processing completed for inbound call {call_sid}")

        except Exception as e:
            logger.error(f"Error in inbound post-call processing: {e}")
            import traceback
            logger.error(traceback.format_exc())

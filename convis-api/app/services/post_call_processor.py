"""
Post-call AI processing service
Handles transcription, sentiment analysis, and summary generation using OpenAI
"""
import logging
import os
import json
import httpx
from datetime import datetime
from typing import Optional, Dict, Any
from bson import ObjectId

from app.config.database import Database
from app.utils.assistant_keys import (
    resolve_assistant_api_key,
    resolve_user_provider_key,
)

logger = logging.getLogger(__name__)


class PostCallProcessor:
    """Service for post-call AI processing"""

    def __init__(self):
        self.env_openai_api_key = os.getenv("OPENAI_API_KEY")
        if not self.env_openai_api_key:
            logger.warning("OPENAI_API_KEY not set - post-call processing will be limited")

    async def download_recording(self, recording_url: str, account_sid: str = None, auth_token: str = None) -> Optional[bytes]:
        """
        Download recording file from Twilio.

        Args:
            recording_url: URL to the recording (with .mp3 extension)
            account_sid: Twilio Account SID (optional, will use env if not provided)
            auth_token: Twilio Auth Token (optional, will use env if not provided)

        Returns:
            Recording bytes or None
        """
        try:
            # Use provided credentials or fall back to environment variables
            if not account_sid:
                account_sid = os.getenv("TWILIO_ACCOUNT_SID")
            if not auth_token:
                auth_token = os.getenv("TWILIO_AUTH_TOKEN")

            if not account_sid or not auth_token:
                logger.error("Twilio credentials not configured")
                return None

            # CRITICAL FIX: Add strict timeout to prevent hanging
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    recording_url,
                    auth=(account_sid, auth_token),
                    timeout=30.0  # 30 second timeout instead of 60
                )
                response.raise_for_status()

                # Limit file size to prevent memory issues (max 50MB)
                content = response.content
                if len(content) > 50 * 1024 * 1024:
                    logger.error(f"Recording too large: {len(content)} bytes")
                    return None

                return content

        except httpx.TimeoutException:
            logger.error(f"Timeout downloading recording from {recording_url}")
            return None
        except Exception as e:
            logger.error(f"Error downloading recording: {e}")
            return None

    async def transcribe_audio(self, audio_bytes: bytes, openai_api_key: Optional[str]) -> Optional[str]:
        """
        Transcribe audio using Deepgram (fast) with OpenAI Whisper fallback.
        Deepgram is 5-10x faster than Whisper for most audio files.

        Args:
            audio_bytes: Audio file bytes
            openai_api_key: OpenAI API key for Whisper fallback

        Returns:
            Transcript text or None
        """
        # Try Deepgram first (much faster)
        deepgram_key = os.getenv("DEEPGRAM_API_KEY")
        if deepgram_key:
            try:
                transcript = await self._transcribe_with_deepgram(audio_bytes, deepgram_key)
                if transcript:
                    return transcript
                logger.warning("Deepgram transcription returned empty, falling back to Whisper")
            except Exception as e:
                logger.warning(f"Deepgram transcription failed, falling back to Whisper: {e}")

        # Fallback to OpenAI Whisper
        return await self._transcribe_with_whisper(audio_bytes, openai_api_key)

    async def _transcribe_with_deepgram(self, audio_bytes: bytes, api_key: str) -> Optional[str]:
        """Transcribe audio using Deepgram Pre-recorded API (fast)."""
        try:
            import time
            start_time = time.time()

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.deepgram.com/v1/listen",
                    headers={
                        "Authorization": f"Token {api_key}",
                        "Content-Type": "audio/wav"
                    },
                    params={
                        "model": "nova-2",
                        "punctuate": "true",
                        "language": "en"
                    },
                    content=audio_bytes,
                    timeout=60.0
                )

            if response.status_code >= 400:
                logger.error(f"Deepgram transcription failed ({response.status_code}): {response.text}")
                return None

            result = response.json()
            transcript = ""

            channels = result.get("results", {}).get("channels", [])
            if channels:
                alternatives = channels[0].get("alternatives", [])
                if alternatives:
                    transcript = alternatives[0].get("transcript", "")

            elapsed = time.time() - start_time
            logger.info(f"⚡ Deepgram transcription completed in {elapsed:.1f}s: {len(transcript)} characters")
            return transcript

        except Exception as e:
            logger.error(f"Error in Deepgram transcription: {e}")
            return None

    async def _transcribe_with_whisper(self, audio_bytes: bytes, openai_api_key: Optional[str]) -> Optional[str]:
        """Transcribe audio using OpenAI Whisper (slower fallback)."""
        try:
            if not openai_api_key:
                logger.warning("No OpenAI API key available for transcription")
                return None

            import time
            start_time = time.time()

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.openai.com/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {openai_api_key}"},
                    data={"model": "whisper-1"},
                    files={"file": ("recording.wav", audio_bytes, "audio/wav")},
                    timeout=120.0
                )

            if response.status_code >= 400:
                logger.error(
                    "OpenAI transcription failed (%s): %s",
                    response.status_code,
                    response.text
                )
                response.raise_for_status()

            result = response.json()
            transcript = result.get("text", "")

            elapsed = time.time() - start_time
            logger.info(f"Whisper transcription completed in {elapsed:.1f}s: {len(transcript)} characters")
            return transcript

        except Exception as e:
            logger.error(f"Error transcribing audio: {e}")
            return None

    async def analyze_transcript(self, transcript: str, openai_api_key: Optional[str]) -> Optional[Dict[str, Any]]:
        """
        Analyze transcript using GPT to extract sentiment, summary, and appointment info.

        Args:
            transcript: Call transcript

        Returns:
            Analysis dict with sentiment, summary, and appointment or None
        """
        try:
            if not openai_api_key:
                logger.warning("No OpenAI API key available for transcript analysis")
                return {
                    "sentiment": "neutral",
                    "sentiment_score": 0.0,
                    "summary": "OpenAI key unavailable for analysis.",
                    "appointment": None
                }

            if not transcript or len(transcript.strip()) < 10:
                # Empty or very short transcript
                return {
                    "sentiment": "neutral",
                    "sentiment_score": 0.0,
                    "summary": "Call too short or empty transcript.",
                    "appointment": None
                }

            # Construct prompt for GPT
            prompt = f"""Analyze the following phone call transcript and provide a structured JSON response.

Transcript:
{transcript}

Provide a JSON response with these exact fields:
- sentiment: one of "positive", "neutral", or "negative"
- sentiment_score: a float between -1.0 (very negative) and 1.0 (very positive)
- summary: a concise summary in 3-8 sentences describing what was discussed
- appointment: if a meeting/appointment was scheduled, provide an object with {{title, start_iso, end_iso, timezone}}, otherwise null
- customer_email: Extract the customer's email address if mentioned. IMPORTANT:
  * Emails are often SPELLED OUT letter by letter (e.g., "F.B.G.A.D" means "fbgad")
  * "at the rate" or "at" means "@"
  * "dot" means "."
  * Reconstruct the full email address in standard format (e.g., "fbgadhave611@gmail.com")
  * If the email was corrected during the call, use the FINAL corrected version
  * Return null if no email was mentioned
- customer_name: Extract the customer's name if they mentioned it, otherwise null
- email_mentioned: boolean - true if an email address was mentioned/discussed during the call
- conversation: an array of conversation turns. Each turn should be an object with:
  - role: "user" for the customer/caller or "assistant" for the AI agent/support representative
  - text: the exact text spoken by that person
  Parse the transcript carefully to separate what the customer said vs what the agent/assistant said. Look for conversational cues like questions, responses, greetings, etc.

Return ONLY the JSON, no other text."""

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {openai_api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": "gpt-4o-mini",
                        "messages": [
                            {"role": "system", "content": "You are an expert call analyst. Always return valid JSON."},
                            {"role": "user", "content": prompt}
                        ],
                        "temperature": 0.3,
                        "max_tokens": 1000
                    },
                    timeout=60.0
                )
                response.raise_for_status()

                result = response.json()
                content = result["choices"][0]["message"]["content"].strip()

                # Parse JSON response
                # Remove markdown code blocks if present
                if content.startswith("```"):
                    content = content.split("```")[1]
                    if content.startswith("json"):
                        content = content[4:]
                    content = content.strip()

                analysis = json.loads(content)
                logger.info(f"Analysis completed: sentiment={analysis.get('sentiment')}")

                return analysis

        except Exception as e:
            logger.error(f"Error analyzing transcript: {e}")
            # Return default values on error
            return {
                "sentiment": "neutral",
                "sentiment_score": 0.0,
                "summary": "Unable to analyze call.",
                "appointment": None
            }

    async def process_call(self, call_sid: str, lead_id: str, campaign_id: str):
        """
        Process a completed call: transcribe, analyze, and update database.

        Args:
            call_sid: Twilio Call SID
            lead_id: Lead ID
            campaign_id: Campaign ID
        """
        try:
            logger.info(f"Processing call {call_sid} for lead {lead_id}")

            db = Database.get_db()
            call_attempts_collection = db["call_attempts"]
            leads_collection = db["leads"]

            # Get call attempt
            call_attempt = call_attempts_collection.find_one({"call_sid": call_sid})
            if not call_attempt:
                logger.error(f"Call attempt not found for CallSid: {call_sid}")
                return

            recording_url = call_attempt.get("recording_url")
            if not recording_url:
                logger.warning(f"No recording URL for call {call_sid}")
                return

            # Resolve OpenAI API key (per assistant/user)
            openai_api_key = self._resolve_openai_api_key(call_attempt)
            if not openai_api_key:
                logger.error(f"No OpenAI API key available for call {call_sid}")
                return

            # Step 1: Download recording
            logger.info(f"Downloading recording from {recording_url}")
            audio_bytes = await self.download_recording(recording_url)
            if not audio_bytes:
                logger.error("Failed to download recording")
                return

            # Step 2: Transcribe
            logger.info("Transcribing audio...")
            transcript = await self.transcribe_audio(audio_bytes, openai_api_key)
            if not transcript:
                logger.error("Failed to transcribe audio")
                transcript = ""

            # Update call attempt with transcript
            call_attempts_collection.update_one(
                {"_id": call_attempt["_id"]},
                {"$set": {"transcript": transcript, "updated_at": datetime.utcnow()}}
            )

            # Step 3: Analyze
            logger.info("Analyzing transcript...")
            analysis = await self.analyze_transcript(transcript, openai_api_key)
            if not analysis:
                logger.error("Failed to analyze transcript")
                return

            # Update call attempt with analysis
            call_attempts_collection.update_one(
                {"_id": call_attempt["_id"]},
                {
                    "$set": {
                        "analysis": analysis,
                        "updated_at": datetime.utcnow()
                    }
                }
            )

            # Step 4: Update lead with sentiment and summary
            sentiment_data = {
                "label": analysis.get("sentiment", "neutral"),
                "score": analysis.get("sentiment_score", 0.0)
            }

            leads_collection.update_one(
                {"_id": ObjectId(lead_id)},
                {
                    "$set": {
                        "sentiment": sentiment_data,
                        "summary": analysis.get("summary", ""),
                        "updated_at": datetime.utcnow()
                    }
                }
            )

            # Step 5: Handle appointment booking if present
            appointment = analysis.get("appointment")
            if appointment and appointment.get("start_iso"):
                logger.info(f"Appointment detected for lead {lead_id}: {appointment.get('title')}")
                try:
                    from app.services.calendar_service import CalendarService
                    from app.services.appointment_whatsapp_service import AppointmentWhatsAppService

                    calendar_service = CalendarService()
                    event_id = await calendar_service.book_appointment(lead_id, campaign_id, appointment)

                    # Step 5a: Send WhatsApp confirmation if phone number available and calendar event created
                    if event_id:
                        try:
                            # Get lead details for phone number
                            lead = leads_collection.find_one({"_id": ObjectId(lead_id)})
                            if lead and lead.get("phone"):
                                phone_number = lead["phone"]
                                customer_name = lead.get("full_name") or lead.get("first_name", "Customer")

                                # Get user_id from campaign
                                campaigns_collection = db["campaigns"]
                                campaign = campaigns_collection.find_one({"_id": ObjectId(campaign_id)})
                                if campaign:
                                    user_id = str(campaign["user_id"])

                                    # Prepare booking data for WhatsApp
                                    booking_data = {
                                        "_id": call_sid,
                                        "customer_name": customer_name,
                                        "start_time": appointment.get("start_iso"),
                                        "location": appointment.get("location", "Phone Call"),
                                        "duration": appointment.get("duration", 30)
                                    }

                                    # Send WhatsApp confirmation
                                    whatsapp_result = await AppointmentWhatsAppService.send_appointment_confirmation(
                                        user_id=user_id,
                                        booking_data=booking_data,
                                        phone_number=phone_number
                                    )

                                    if whatsapp_result.get("success"):
                                        logger.info(f"WhatsApp confirmation sent to {phone_number} for outbound call {call_sid}")
                                    else:
                                        logger.warning(f"Failed to send WhatsApp confirmation: {whatsapp_result.get('error')}")
                        except Exception as whatsapp_error:
                            logger.error(f"Error sending WhatsApp confirmation for outbound call: {whatsapp_error}")
                            # Don't fail the entire process if WhatsApp fails

                except ImportError:
                    logger.warning("CalendarService not yet implemented")

            logger.info(f"Post-call processing completed for call {call_sid}")

        except Exception as e:
            logger.error(f"Error in post-call processing: {e}")
            import traceback
            logger.error(traceback.format_exc())

    def _resolve_openai_api_key(self, call_attempt: Dict[str, Any]) -> Optional[str]:
        """
        Determine the correct OpenAI API key for a call.
        Prefers environment-injected keys (deployment-managed) and falls back to persisted keys.
        """
        db = Database.get_db()
        call_sid = call_attempt.get("call_sid")
        assistant_id = None
        user_id = None

        # Deployment-first: use env var if present to keep runtime deterministic
        if self.env_openai_api_key:
            return self.env_openai_api_key

        # Try call_logs (covers inbound/outbound direct calls)
        call_logs_collection = db["call_logs"]
        call_log = call_logs_collection.find_one({"call_sid": call_sid})
        if call_log:
            assistant_id = call_log.get("assistant_id")
            user_id = call_log.get("user_id")

        # Campaign attempts: fetch campaign for assistant/user references
        if not user_id or not assistant_id:
            campaign_id = call_attempt.get("campaign_id")
            if campaign_id:
                try:
                    campaign_obj_id = campaign_id if isinstance(campaign_id, ObjectId) else ObjectId(str(campaign_id))
                    campaign = db["campaigns"].find_one({"_id": campaign_obj_id})
                except Exception as exc:
                    logger.warning(f"Invalid campaign_id on call {call_sid}: {exc}")
                    campaign = None
                if campaign:
                    user_id = user_id or campaign.get("user_id")
                    assistant_id = assistant_id or campaign.get("assistant_id")

        # Assistant-scoped key takes precedence
        if assistant_id:
            try:
                assistant_obj_id = assistant_id if isinstance(assistant_id, ObjectId) else ObjectId(str(assistant_id))
                assistant = db["assistants"].find_one({"_id": assistant_obj_id})
            except Exception as exc:
                logger.warning(f"Invalid assistant_id on call {call_sid}: {exc}")
                assistant = None

            if assistant:
                try:
                    key, _ = resolve_assistant_api_key(db, assistant, required_provider="openai")
                    return key
                except Exception as exc:
                    detail = getattr(exc, "detail", str(exc))
                    logger.warning(f"Assistant API key resolution failed for call {call_sid}: {detail}")

        # Fallback to any OpenAI key saved under the user account
        if user_id:
            key = resolve_user_provider_key(db, user_id, "openai")
            if key:
                return key

        # Last resort: environment variable
        if self.env_openai_api_key:
            logger.info(f"Using OPENAI_API_KEY env fallback for call {call_sid}")
        else:
            logger.error(f"OPENAI_API_KEY env variable not set. Unable to process call {call_sid}")

        return self.env_openai_api_key

    async def transcribe_and_update_call(self, call_sid: str, recording_url: str):
        """
        Transcribe a call recording and update call_logs with the transcript.
        This is used for regular (non-campaign) calls.

        Args:
            call_sid: Twilio Call SID
            recording_url: URL to the recording (with .mp3 extension)
        """
        try:
            logger.info(f"Transcribing call {call_sid}")

            db = Database.get_db()
            call_logs_collection = db["call_logs"]

            # Get the call to find the user_id
            call = call_logs_collection.find_one({"call_sid": call_sid})
            if not call:
                logger.error(f"Call {call_sid} not found in database")
                return

            # Check if a real-time transcript already exists (from OpenAI Realtime API or custom provider)
            existing_transcript = call.get("transcript")
            if existing_transcript and existing_transcript not in ["", "[Transcription unavailable]", "Unable to analyze call."]:
                logger.info(f"Call {call_sid} already has a real-time transcript ({len(existing_transcript)} chars). Skipping post-call transcription.")
                # Still run analysis on existing transcript if not done
                if not call.get("summary") or call.get("summary") == "Unable to analyze call." or not call.get("conversation_log"):
                    logger.info("Running analysis on existing transcript...")
                    # Resolve OpenAI API key for analysis
                    call_attempt = {"call_sid": call_sid}
                    openai_key = self._resolve_openai_api_key(call_attempt)
                    analysis = await self.analyze_transcript(existing_transcript, openai_key)
                    if analysis:
                        update_data = {
                            "analysis": analysis,
                            "sentiment": analysis.get("sentiment", "neutral"),
                            "sentiment_score": analysis.get("sentiment_score", 0.0),
                            "summary": analysis.get("summary", ""),
                            "updated_at": datetime.utcnow()
                        }

                        # Add parsed conversation log if available
                        conversation = analysis.get("conversation")
                        if conversation and isinstance(conversation, list):
                            update_data["conversation_log"] = conversation
                            logger.info(f"Saving parsed conversation with {len(conversation)} turns for {call_sid}")

                        # Extract and save customer data (email, name) if available
                        customer_email = analysis.get("customer_email")
                        customer_name = analysis.get("customer_name")
                        if customer_email or customer_name:
                            customer_data = call.get("customer_data") or {}
                            if customer_email:
                                customer_data["email"] = customer_email
                                logger.info(f"Extracted customer email: {customer_email} for call {call_sid}")
                            if customer_name:
                                customer_data["name"] = customer_name
                                logger.info(f"Extracted customer name: {customer_name} for call {call_sid}")
                            update_data["customer_data"] = customer_data

                        call_logs_collection.update_one(
                            {"call_sid": call_sid},
                            {"$set": update_data}
                        )
                        logger.info(f"Analysis completed for existing transcript of {call_sid}")
                return

            user_id = call.get("user_id")
            if not user_id:
                logger.error(f"No user_id for call {call_sid}")
                return

            # Get user's Twilio credentials from provider_connections
            from bson import ObjectId
            from app.utils.twilio_helpers import decrypt_twilio_credentials

            provider_connections = db["provider_connections"]
            twilio_connection = provider_connections.find_one({
                "user_id": user_id if isinstance(user_id, ObjectId) else ObjectId(user_id),
                "provider": "twilio"
            })

            if not twilio_connection:
                logger.error(f"No Twilio connection found for user {user_id}")
                return

            account_sid, auth_token = decrypt_twilio_credentials(twilio_connection)
            if not account_sid or not auth_token:
                logger.error(f"Invalid Twilio credentials for user {user_id}")
                return

            # Step 1: Download recording
            logger.info(f"Downloading recording from {recording_url}")
            audio_bytes = await self.download_recording(recording_url, account_sid, auth_token)
            if not audio_bytes:
                logger.error(f"Failed to download recording for {call_sid}")
                return

            # Step 2: Resolve OpenAI API key
            call_attempt = {"call_sid": call_sid}
            openai_key = self._resolve_openai_api_key(call_attempt)

            # Step 3: Transcribe
            logger.info("Transcribing audio using OpenAI Whisper...")
            transcript = await self.transcribe_audio(audio_bytes, openai_key)
            if not transcript:
                logger.warning(f"Transcription failed or empty for {call_sid}")
                transcript = "[Transcription unavailable]"

            # Step 4: Analyze
            logger.info("Analyzing transcript...")
            analysis = await self.analyze_transcript(transcript, openai_key)
            if not analysis:
                analysis = {
                    "sentiment": "neutral",
                    "sentiment_score": 0.0,
                    "summary": "Unable to analyze call.",
                    "appointment": None
                }

            # Step 4: Build update data with transcript and analysis
            update_data = {
                "transcript": transcript,
                "transcription_status": "completed",
                "analysis": analysis,
                "sentiment": analysis.get("sentiment", "neutral"),
                "sentiment_score": analysis.get("sentiment_score", 0.0),
                "summary": analysis.get("summary", ""),
                "updated_at": datetime.utcnow()
            }

            # Add parsed conversation log if available from GPT analysis
            conversation = analysis.get("conversation")
            if conversation and isinstance(conversation, list):
                update_data["conversation_log"] = conversation
                logger.info(f"Saving parsed conversation with {len(conversation)} turns for {call_sid}")

            # Extract and save customer data (email, name, etc.)
            customer_email = analysis.get("customer_email")
            customer_name = analysis.get("customer_name")
            if customer_email or customer_name:
                customer_data = call.get("customer_data") or {}
                if customer_email:
                    customer_data["email"] = customer_email
                    logger.info(f"Extracted customer email: {customer_email} for call {call_sid}")
                if customer_name:
                    customer_data["name"] = customer_name
                    logger.info(f"Extracted customer name: {customer_name} for call {call_sid}")
                update_data["customer_data"] = customer_data

            # Update call log
            call_logs_collection.update_one(
                {"call_sid": call_sid},
                {"$set": update_data}
            )

            logger.info(f"Transcription completed for call {call_sid}: {len(transcript)} characters")

            # Step 5: Update calendar event with call summary if appointment was booked
            try:
                call_log = call_logs_collection.find_one({"call_sid": call_sid})
                if call_log and call_log.get("appointment_booked"):
                    from app.services.calendar_service import CalendarService
                    calendar_service = CalendarService()

                    summary = analysis.get("summary", "Call completed")
                    recording_url = call_log.get("recording_url")

                    await calendar_service.update_calendar_event_with_call_summary(
                        call_sid=call_sid,
                        call_summary=summary,
                        recording_url=recording_url
                    )
                    logger.info(f"Calendar event updated with call summary for {call_sid}")

                    # Step 6: Send email with call summary
                    try:
                        from app.services.email_service import EmailService
                        email_service = EmailService()

                        # Get appointment details
                        appointments_collection = db["appointments"]
                        appointment = appointments_collection.find_one({"call_sid": call_sid})

                        if appointment:
                            # Get user email
                            users_collection = db["users"]
                            user = users_collection.find_one({"_id": appointment.get("user_id")})

                            if user and user.get("email"):
                                email_sent = email_service.send_meeting_summary_email(
                                    to_email=user.get("email"),
                                    meeting_title=appointment.get("title", "Meeting"),
                                    call_summary=summary,
                                    meeting_date=appointment.get("start"),
                                    recording_url=recording_url,
                                    call_sid=call_sid,
                                    attendee_name=user.get("name") or user.get("email").split("@")[0]
                                )

                                if email_sent:
                                    logger.info(f"Call summary email sent to {user.get('email')}")
                                else:
                                    logger.warning("Failed to send call summary email")
                            else:
                                logger.warning(f"No email found for user {appointment.get('user_id')}")
                        else:
                            logger.warning(f"No appointment found for call {call_sid}")

                    except Exception as e:
                        logger.error(f"Failed to send call summary email: {e}")
                        # Don't fail if email fails
                        pass

            except Exception as e:
                logger.error(f"Failed to update calendar event: {e}")
                # Don't fail the whole process if calendar update fails
                pass

        except Exception as e:
            logger.error(f"Error transcribing call {call_sid}: {e}")
            import traceback
            logger.error(traceback.format_exc())

            # Update with error status
            try:
                db = Database.get_db()
                call_logs_collection = db["call_logs"]
                call_logs_collection.update_one(
                    {"call_sid": call_sid},
                    {
                        "$set": {
                            "transcription_status": "failed",
                            "transcription_error": str(e),
                            "updated_at": datetime.utcnow()
                        }
                    }
                )
            except Exception:
                pass

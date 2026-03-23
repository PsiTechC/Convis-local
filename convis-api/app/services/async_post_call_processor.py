"""
Async Post-call AI processing service with parallel operations
Optimized for low latency using asyncio.gather for concurrent execution
"""
import logging
import os
import json
import httpx
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any, Tuple
from bson import ObjectId

from app.config.async_database import AsyncDatabase, get_async_collection
from app.utils.assistant_keys import (
    resolve_assistant_api_key,
    resolve_user_provider_key,
)

logger = logging.getLogger(__name__)


class AsyncPostCallProcessor:
    """
    Optimized async service for post-call AI processing.

    Key optimizations:
    1. Uses Motor (async MongoDB driver) for non-blocking DB operations
    2. Parallelizes independent operations with asyncio.gather
    3. Streams operations where possible
    """

    def __init__(self):
        self.env_openai_api_key = os.getenv("OPENAI_API_KEY")
        if not self.env_openai_api_key:
            logger.warning("OPENAI_API_KEY not set - post-call processing will be limited")

    async def download_recording(
        self,
        recording_url: str,
        account_sid: str = None,
        auth_token: str = None
    ) -> Optional[bytes]:
        """Download recording file from Twilio (non-blocking)."""
        try:
            if not account_sid:
                account_sid = os.getenv("TWILIO_ACCOUNT_SID")
            if not auth_token:
                auth_token = os.getenv("TWILIO_AUTH_TOKEN")

            if not account_sid or not auth_token:
                logger.error("Twilio credentials not configured")
                return None

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    recording_url,
                    auth=(account_sid, auth_token),
                    timeout=30.0
                )
                response.raise_for_status()

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
                    timeout=60.0  # Deepgram is fast, 60s is plenty
                )

            if response.status_code >= 400:
                logger.error(f"Deepgram transcription failed ({response.status_code}): {response.text}")
                return None

            result = response.json()
            transcript = ""

            # Extract transcript from Deepgram response
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
                logger.error(f"OpenAI transcription failed ({response.status_code}): {response.text}")
                response.raise_for_status()

            result = response.json()
            transcript = result.get("text", "")

            elapsed = time.time() - start_time
            logger.info(f"Whisper transcription completed in {elapsed:.1f}s: {len(transcript)} characters")
            return transcript

        except Exception as e:
            logger.error(f"Error transcribing audio with Whisper: {e}")
            return None

    async def analyze_transcript(self, transcript: str, openai_api_key: Optional[str]) -> Optional[Dict[str, Any]]:
        """Analyze transcript using GPT (non-blocking) with robust JSON parsing."""
        try:
            if not openai_api_key:
                logger.warning("No OpenAI API key available for transcript analysis")
                return {
                    "sentiment": "neutral",
                    "sentiment_score": 0.0,
                    "summary": "OpenAI key unavailable for analysis.",
                    "appointment": None,
                    "customer_email": None,
                    "customer_name": None,
                    "email_mentioned": False,
                    "issue_description": None,
                    "issue_category": None,
                    "issue_priority": None,
                    "action_required": None,
                    "extracted_data": {},
                    "conversation": []
                }

            if not transcript or len(transcript.strip()) < 10:
                return {
                    "sentiment": "neutral",
                    "sentiment_score": 0.0,
                    "summary": "Call too short or empty transcript.",
                    "appointment": None,
                    "customer_email": None,
                    "customer_name": None,
                    "email_mentioned": False,
                    "issue_description": None,
                    "issue_category": None,
                    "issue_priority": None,
                    "action_required": None,
                    "extracted_data": {},
                    "conversation": []
                }

            # Truncate very long transcripts to avoid token limits
            max_transcript_length = 8000
            truncated_transcript = transcript[:max_transcript_length] if len(transcript) > max_transcript_length else transcript
            if len(transcript) > max_transcript_length:
                logger.info(f"Transcript truncated from {len(transcript)} to {max_transcript_length} chars for analysis")

            prompt = f"""Analyze the following phone call transcript and provide a structured JSON response.

Transcript:
{truncated_transcript}

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
- issue_description: If the caller described a problem, issue, or request, provide a detailed description of what they're experiencing. Include all technical details, error messages, symptoms, or specifics they mentioned. Return null if no issue was discussed.
- issue_category: Categorize the issue if applicable. Options: "technical", "billing", "account", "feature_request", "bug_report", "general_inquiry", "complaint", "support", null
- issue_priority: Based on the caller's urgency and issue severity, suggest priority: "low", "medium", "high", "critical", or null
- action_required: What follow-up action is needed? e.g., "create_ticket", "callback", "escalate", "send_info", "resolved", null
- extracted_data: An object containing any other structured data mentioned in the call such as:
  * phone_number: customer's phone number if mentioned
  * order_number: any order/ticket/reference number mentioned
  * product_name: specific product or service discussed
  * account_id: any account or customer ID mentioned
  * location: any location/address mentioned
  * custom fields as key-value pairs
- conversation: an array of conversation turns (limit to 20 most important turns). Each turn should be an object with:
  - role: "user" for the customer/caller or "assistant" for the AI agent/support representative
  - text: the exact text spoken by that person (keep each text under 200 characters)
  Parse the transcript carefully to separate what the customer said vs what the agent/assistant said.

CRITICAL: Return ONLY valid JSON. No markdown, no code blocks, no explanations. Escape special characters in strings properly."""

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
                            {"role": "system", "content": "You are an expert call analyst. You MUST return ONLY valid JSON with no markdown formatting. Always escape special characters in strings. Never truncate the JSON response."},
                            {"role": "user", "content": prompt}
                        ],
                        "temperature": 0.2,
                        "max_tokens": 2000,  # Increased to prevent truncation
                        "response_format": {"type": "json_object"}  # Force JSON response
                    },
                    timeout=90.0
                )
                response.raise_for_status()

                result = response.json()
                content = result["choices"][0]["message"]["content"].strip()

                # Parse JSON with robust error handling
                analysis = self._parse_json_safely(content)

                if analysis:
                    logger.info(f"Analysis completed: sentiment={analysis.get('sentiment')}, email={analysis.get('customer_email')}, issue={analysis.get('issue_category')}")

                    # Ensure all required fields exist
                    analysis.setdefault("sentiment", "neutral")
                    analysis.setdefault("sentiment_score", 0.0)
                    analysis.setdefault("summary", "")
                    analysis.setdefault("appointment", None)
                    analysis.setdefault("customer_email", None)
                    analysis.setdefault("customer_name", None)
                    analysis.setdefault("email_mentioned", False)
                    analysis.setdefault("issue_description", None)
                    analysis.setdefault("issue_category", None)
                    analysis.setdefault("issue_priority", None)
                    analysis.setdefault("action_required", None)
                    analysis.setdefault("extracted_data", {})
                    analysis.setdefault("conversation", [])

                    return analysis
                else:
                    logger.error("Failed to parse analysis JSON after all attempts")
                    return self._get_default_analysis("JSON parsing failed")

        except httpx.TimeoutException:
            logger.error("Timeout during transcript analysis")
            return self._get_default_analysis("Analysis timed out")
        except Exception as e:
            logger.error(f"Error analyzing transcript: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return self._get_default_analysis(f"Analysis error: {str(e)[:100]}")

    def _parse_json_safely(self, content: str) -> Optional[Dict[str, Any]]:
        """Parse JSON with multiple fallback strategies for malformed responses."""
        import re

        # Strategy 1: Direct parse
        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            logger.warning(f"Direct JSON parse failed: {e}")

        # Strategy 2: Remove markdown code blocks
        try:
            cleaned = content
            if "```" in cleaned:
                # Extract content between code blocks
                match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', cleaned)
                if match:
                    cleaned = match.group(1)
                else:
                    # Just remove the backticks
                    cleaned = re.sub(r'```(?:json)?', '', cleaned)
            return json.loads(cleaned.strip())
        except json.JSONDecodeError as e:
            logger.warning(f"Markdown-cleaned JSON parse failed: {e}")

        # Strategy 3: Fix common JSON issues
        try:
            fixed = content
            # Remove trailing commas before } or ]
            fixed = re.sub(r',\s*([}\]])', r'\1', fixed)
            # Fix unescaped newlines in strings
            fixed = re.sub(r'(?<!\\)\n(?=[^"]*"[^"]*$)', r'\\n', fixed)
            # Fix unescaped quotes
            fixed = re.sub(r'(?<!\\)"(?=[^:,\[\]{}]*[^"\\]")', r'\\"', fixed)
            return json.loads(fixed)
        except json.JSONDecodeError as e:
            logger.warning(f"Fixed JSON parse failed: {e}")

        # Strategy 4: Extract JSON object using regex
        try:
            # Find the outermost { } pair
            match = re.search(r'\{[\s\S]*\}', content)
            if match:
                json_str = match.group(0)
                return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.warning(f"Regex-extracted JSON parse failed: {e}")

        # Strategy 5: Try to repair truncated JSON
        try:
            repaired = self._repair_truncated_json(content)
            if repaired:
                return json.loads(repaired)
        except json.JSONDecodeError as e:
            logger.warning(f"Repaired JSON parse failed: {e}")

        return None

    def _repair_truncated_json(self, content: str) -> Optional[str]:
        """Attempt to repair truncated JSON by closing open brackets/braces."""
        import re

        # Remove any partial content after last complete value
        # Count open brackets/braces
        open_braces = content.count('{') - content.count('}')
        open_brackets = content.count('[') - content.count(']')

        if open_braces <= 0 and open_brackets <= 0:
            return None  # Not truncated in a way we can fix

        # Find last complete key-value pair
        # Remove trailing incomplete content
        repaired = content.rstrip()

        # Remove trailing comma if present
        repaired = re.sub(r',\s*$', '', repaired)

        # Remove incomplete string at end
        if repaired.count('"') % 2 != 0:
            # Find last complete string
            last_quote = repaired.rfind('"')
            if last_quote > 0:
                # Check if this closes a string
                prev_content = repaired[:last_quote]
                if prev_content.count('"') % 2 != 0:
                    # This quote opens a string, remove it
                    repaired = repaired[:last_quote]
                    repaired = re.sub(r'[,:]\s*$', '', repaired)

        # Close open structures
        repaired += ']' * open_brackets
        repaired += '}' * open_braces

        return repaired

    def _get_default_analysis(self, reason: str) -> Dict[str, Any]:
        """Return default analysis structure when parsing fails."""
        return {
            "sentiment": "neutral",
            "sentiment_score": 0.0,
            "summary": reason,
            "appointment": None,
            "customer_email": None,
            "customer_name": None,
            "email_mentioned": False,
            "issue_description": None,
            "issue_category": None,
            "issue_priority": None,
            "action_required": None,
            "extracted_data": {},
            "conversation": []
        }

    async def _resolve_openai_api_key_async(self, call_attempt: Dict[str, Any]) -> Optional[str]:
        """Resolve OpenAI API key asynchronously."""
        # Use env var first (fastest path)
        if self.env_openai_api_key:
            return self.env_openai_api_key

        db = await AsyncDatabase.get_db()
        call_sid = call_attempt.get("call_sid")
        assistant_id = None
        user_id = None

        # Try call_logs
        call_logs_collection = db["call_logs"]
        call_log = await call_logs_collection.find_one({"call_sid": call_sid})
        if call_log:
            assistant_id = call_log.get("assistant_id")
            user_id = call_log.get("user_id")

        # Campaign attempts
        if not user_id or not assistant_id:
            campaign_id = call_attempt.get("campaign_id")
            if campaign_id:
                try:
                    campaign_obj_id = campaign_id if isinstance(campaign_id, ObjectId) else ObjectId(str(campaign_id))
                    campaign = await db["campaigns"].find_one({"_id": campaign_obj_id})
                except Exception as exc:
                    logger.warning(f"Invalid campaign_id on call {call_sid}: {exc}")
                    campaign = None
                if campaign:
                    user_id = user_id or campaign.get("user_id")
                    assistant_id = assistant_id or campaign.get("assistant_id")

        # Assistant-scoped key
        if assistant_id:
            try:
                assistant_obj_id = assistant_id if isinstance(assistant_id, ObjectId) else ObjectId(str(assistant_id))
                assistant = await db["assistants"].find_one({"_id": assistant_obj_id})
            except Exception as exc:
                logger.warning(f"Invalid assistant_id on call {call_sid}: {exc}")
                assistant = None

            if assistant:
                try:
                    # Note: This helper may need async conversion too
                    from app.config.database import Database
                    sync_db = Database.get_db()
                    key, _ = resolve_assistant_api_key(sync_db, assistant, required_provider="openai")
                    return key
                except Exception as exc:
                    detail = getattr(exc, "detail", str(exc))
                    logger.warning(f"Assistant API key resolution failed for call {call_sid}: {detail}")

        # Fallback to user key
        if user_id:
            from app.config.database import Database
            sync_db = Database.get_db()
            key = resolve_user_provider_key(sync_db, user_id, "openai")
            if key:
                return key

        return self.env_openai_api_key

    async def _execute_user_workflow(
        self,
        workflow_id: str,
        template_id: str,
        config: Dict[str, Any],
        call_data: Dict[str, Any],
        user_id: str
    ) -> Dict[str, Any]:
        """
        Execute a user workflow based on its template type.

        Supports:
        - send-email-after-call: Send email via SMTP or SendGrid
        - slack-notification: Send Slack webhook notification
        - custom-webhook: Call external webhook with call data
        - update-crm: Sync to CRM (HubSpot, Salesforce, etc.)
        - create-calendar-event: Create calendar booking

        Args:
            workflow_id: The workflow document ID
            template_id: Template type identifier
            config: Workflow configuration from user
            call_data: Call data to include in the workflow
            user_id: User who owns the workflow

        Returns:
            Dict with success status and error message if failed
        """
        try:
            logger.info(f"[USER_WORKFLOW] Executing template '{template_id}' with config: {list(config.keys())}")

            if template_id == "custom-webhook":
                return await self._execute_webhook_workflow(config, call_data)

            elif template_id == "slack-notification":
                return await self._execute_slack_workflow(config, call_data)

            elif template_id == "send-email-after-call":
                return await self._execute_email_workflow(config, call_data, user_id)

            elif template_id == "update-crm":
                return await self._execute_crm_workflow(config, call_data, user_id)

            elif template_id == "create-calendar-event":
                return await self._execute_calendar_workflow(config, call_data, user_id)

            else:
                logger.warning(f"[USER_WORKFLOW] Unknown template: {template_id}")
                return {"success": False, "error": f"Unknown template: {template_id}"}

        except Exception as e:
            logger.error(f"[USER_WORKFLOW] Error executing workflow: {e}")
            return {"success": False, "error": str(e)}

    async def _execute_webhook_workflow(
        self,
        config: Dict[str, Any],
        call_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute custom webhook workflow."""
        try:
            webhook_url = config.get("webhook_url")
            if not webhook_url:
                return {"success": False, "error": "No webhook URL configured"}

            method = config.get("method", "POST").upper()
            custom_headers = config.get("custom_headers", {})

            # Parse headers if it's a string
            if isinstance(custom_headers, str):
                try:
                    custom_headers = json.loads(custom_headers) if custom_headers else {}
                except:
                    custom_headers = {}

            headers = {
                "Content-Type": "application/json",
                **custom_headers
            }

            # Prepare payload with all call data
            payload = {
                "event": "call_completed",
                "timestamp": datetime.utcnow().isoformat() + "Z",
                **call_data
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                if method == "POST":
                    response = await client.post(webhook_url, json=payload, headers=headers)
                elif method == "PUT":
                    response = await client.put(webhook_url, json=payload, headers=headers)
                else:
                    return {"success": False, "error": f"Unsupported method: {method}"}

                if response.status_code >= 200 and response.status_code < 300:
                    logger.info(f"[USER_WORKFLOW] Webhook triggered successfully: {webhook_url}")
                    return {"success": True, "status_code": response.status_code}
                else:
                    return {"success": False, "error": f"Webhook returned {response.status_code}: {response.text[:200]}"}

        except httpx.TimeoutException:
            return {"success": False, "error": "Webhook timeout"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _execute_slack_workflow(
        self,
        config: Dict[str, Any],
        call_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute Slack notification workflow."""
        try:
            webhook_url = config.get("webhook_url")
            if not webhook_url:
                return {"success": False, "error": "No Slack webhook URL configured"}

            # Check sentiment filter
            only_negative = config.get("only_negative", False)
            sentiment = call_data.get("sentiment", "neutral")
            if only_negative and sentiment not in ["negative", "very_negative"]:
                logger.info("[USER_WORKFLOW] Skipping Slack notification (sentiment not negative)")
                return {"success": True, "skipped": True, "reason": "Sentiment filter"}

            # Build Slack message
            channel = config.get("channel", "")
            include_sentiment = config.get("include_sentiment", True)

            summary = call_data.get("summary", "No summary available")
            customer_name = call_data.get("customer_name", "Unknown")
            customer_phone = call_data.get("customer_phone", call_data.get("to_number", "Unknown"))
            duration = call_data.get("duration", 0)

            # Format duration
            minutes = int(duration // 60)
            seconds = int(duration % 60)
            duration_str = f"{minutes}m {seconds}s" if minutes > 0 else f"{seconds}s"

            # Build message blocks
            blocks = [
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": "📞 Call Completed"}
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*Customer:* {customer_name}"},
                        {"type": "mrkdwn", "text": f"*Phone:* {customer_phone}"},
                        {"type": "mrkdwn", "text": f"*Duration:* {duration_str}"},
                    ]
                },
            ]

            if include_sentiment:
                sentiment_emoji = {"positive": "😊", "negative": "😟", "neutral": "😐"}.get(sentiment, "😐")
                blocks[1]["fields"].append({"type": "mrkdwn", "text": f"*Sentiment:* {sentiment_emoji} {sentiment}"})

            # Add summary
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Summary:*\n{summary[:500]}"}
            })

            # Add customer email and issue if present
            customer_email = call_data.get("customer_email")
            issue_description = call_data.get("issue_description")

            if customer_email:
                blocks.append({
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"*Customer Email:* {customer_email}"}
                })

            if issue_description:
                blocks.append({
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"*Issue:* {issue_description[:300]}"}
                })

            payload = {"blocks": blocks}
            if channel:
                payload["channel"] = channel

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(webhook_url, json=payload)
                if response.status_code == 200:
                    return {"success": True}
                else:
                    return {"success": False, "error": f"Slack returned {response.status_code}"}

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _execute_email_workflow(
        self,
        config: Dict[str, Any],
        call_data: Dict[str, Any],
        user_id: str
    ) -> Dict[str, Any]:
        """Execute email workflow using SendGrid or SMTP."""
        try:
            # Get recipient email - prefer config, fallback to customer email
            to_email = config.get("to_email") or call_data.get("customer_email")
            if not to_email:
                return {"success": False, "error": "No recipient email (configure to_email or extract from call)"}

            subject = config.get("subject", "Thank you for speaking with us")
            include_summary = config.get("include_summary", True)
            include_transcript = config.get("include_transcript", False)

            # Build email body
            customer_name = call_data.get("customer_name", "Customer")
            summary = call_data.get("summary", "")
            transcript = call_data.get("transcript", "")

            body = f"Dear {customer_name},\n\nThank you for your call today.\n\n"

            if include_summary and summary:
                body += f"Call Summary:\n{summary}\n\n"

            if include_transcript and transcript:
                body += f"Transcript:\n{transcript[:2000]}\n\n"

            body += "If you have any questions, please don't hesitate to reach out.\n\nBest regards"

            # Try SendGrid first
            sendgrid_key = os.getenv("SENDGRID_API_KEY")
            from_email = os.getenv("SENDGRID_FROM_EMAIL", "noreply@convis.ai")

            if sendgrid_key:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.post(
                        "https://api.sendgrid.com/v3/mail/send",
                        headers={
                            "Authorization": f"Bearer {sendgrid_key}",
                            "Content-Type": "application/json"
                        },
                        json={
                            "personalizations": [{"to": [{"email": to_email}]}],
                            "from": {"email": from_email},
                            "subject": subject,
                            "content": [{"type": "text/plain", "value": body}]
                        }
                    )
                    if response.status_code in [200, 202]:
                        logger.info(f"[USER_WORKFLOW] Email sent to {to_email}")
                        return {"success": True}
                    else:
                        return {"success": False, "error": f"SendGrid error: {response.status_code}"}
            else:
                return {"success": False, "error": "No email service configured (set SENDGRID_API_KEY)"}

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _execute_crm_workflow(
        self,
        config: Dict[str, Any],
        call_data: Dict[str, Any],
        user_id: str
    ) -> Dict[str, Any]:
        """Execute CRM update workflow (HubSpot, Salesforce, etc.)."""
        try:
            crm_provider = config.get("crm_provider", "hubspot")
            api_key = config.get("api_key")

            if not api_key:
                return {"success": False, "error": f"No {crm_provider} API key configured"}

            customer_email = call_data.get("customer_email")
            customer_name = call_data.get("customer_name", "Unknown")
            customer_phone = call_data.get("customer_phone", call_data.get("to_number"))
            summary = call_data.get("summary", "")

            if crm_provider == "hubspot":
                return await self._update_hubspot(api_key, customer_email, customer_name, customer_phone, summary, config)
            else:
                return {"success": False, "error": f"CRM provider {crm_provider} not implemented"}

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _update_hubspot(
        self,
        api_key: str,
        email: str,
        name: str,
        phone: str,
        summary: str,
        config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update HubSpot with call data."""
        try:
            if not email and not phone:
                return {"success": False, "error": "Need email or phone for HubSpot"}

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }

            async with httpx.AsyncClient(timeout=15.0) as client:
                # Search for existing contact
                search_body = {
                    "filterGroups": [{
                        "filters": [{"propertyName": "email", "operator": "EQ", "value": email}] if email else [{"propertyName": "phone", "operator": "EQ", "value": phone}]
                    }]
                }

                search_response = await client.post(
                    "https://api.hubapi.com/crm/v3/objects/contacts/search",
                    headers=headers,
                    json=search_body
                )

                contact_id = None
                if search_response.status_code == 200:
                    results = search_response.json().get("results", [])
                    if results:
                        contact_id = results[0]["id"]

                # Create or update contact
                if not contact_id and config.get("create_contact", True):
                    # Create new contact
                    first_name, last_name = (name.split(" ", 1) + [""])[:2] if name else ("", "")
                    create_response = await client.post(
                        "https://api.hubapi.com/crm/v3/objects/contacts",
                        headers=headers,
                        json={
                            "properties": {
                                "email": email,
                                "firstname": first_name,
                                "lastname": last_name,
                                "phone": phone
                            }
                        }
                    )
                    if create_response.status_code == 201:
                        contact_id = create_response.json()["id"]
                        logger.info(f"[USER_WORKFLOW] Created HubSpot contact {contact_id}")

                # Log activity
                if contact_id and config.get("log_activity", True):
                    note_response = await client.post(
                        "https://api.hubapi.com/crm/v3/objects/notes",
                        headers=headers,
                        json={
                            "properties": {
                                "hs_note_body": f"Call Summary:\n{summary[:5000]}",
                                "hs_timestamp": datetime.utcnow().isoformat()
                            },
                            "associations": [{
                                "to": {"id": contact_id},
                                "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 202}]
                            }]
                        }
                    )
                    if note_response.status_code == 201:
                        logger.info(f"[USER_WORKFLOW] Added note to HubSpot contact {contact_id}")

                return {"success": True, "contact_id": contact_id}

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _execute_calendar_workflow(
        self,
        config: Dict[str, Any],
        call_data: Dict[str, Any],
        user_id: str
    ) -> Dict[str, Any]:
        """Execute calendar event creation workflow."""
        try:
            # Only create if appointment was booked during call
            if not call_data.get("appointment_booked"):
                return {"success": True, "skipped": True, "reason": "No appointment booked"}

            appointment_date = call_data.get("appointment_date")
            if not appointment_date:
                return {"success": True, "skipped": True, "reason": "No appointment date"}

            # Calendar integration would go here
            # For now, log the intent
            logger.info(f"[USER_WORKFLOW] Calendar event would be created for {appointment_date}")
            return {"success": True, "note": "Calendar integration pending"}

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def process_call(self, call_sid: str, lead_id: str, campaign_id: str):
        """
        Process a completed call with OPTIMIZED parallel operations.

        Flow:
        1. Check for existing real-time transcript (from Deepgram ASR during call)
        2. If no transcript, download recording and transcribe
        3. PARALLEL: Analysis + DB update for transcript
        4. PARALLEL: Calendar booking + WhatsApp notification + Lead update
        """
        try:
            logger.info(f"[ASYNC] Processing call {call_sid} for lead {lead_id}")

            db = await AsyncDatabase.get_db()
            call_attempts_collection = db["call_attempts"]
            call_logs_collection = db["call_logs"]
            leads_collection = db["leads"]

            # Get call attempt (async)
            call_attempt = await call_attempts_collection.find_one({"call_sid": call_sid})
            if not call_attempt:
                logger.error(f"Call attempt not found for CallSid: {call_sid}")
                return

            # ⚡ OPTIMIZATION: Check for existing real-time transcript first
            # Real-time transcripts are captured during the call from Deepgram ASR + LLM responses
            transcript = None
            transcript_source = "none"

            # Check call_attempt for transcript
            existing_transcript = call_attempt.get("transcript")
            if existing_transcript and existing_transcript.strip() and existing_transcript not in ["", "[Transcription unavailable]"]:
                transcript = existing_transcript
                transcript_source = call_attempt.get("transcript_source", "call_attempt")
                logger.info(f"[ASYNC] ⚡ Using existing transcript from call_attempt ({len(transcript)} chars, source: {transcript_source})")

            # Also check call_logs for real-time transcript
            if not transcript:
                call_log = await call_logs_collection.find_one({
                    "$or": [
                        {"call_sid": call_sid},
                        {"frejun_call_id": call_sid}
                    ]
                })
                if call_log:
                    existing_transcript = call_log.get("transcript")
                    if existing_transcript and existing_transcript.strip() and existing_transcript not in ["", "[Transcription unavailable]"]:
                        transcript = existing_transcript
                        transcript_source = call_log.get("transcript_source", "call_log")
                        logger.info(f"[ASYNC] ⚡ Using existing transcript from call_log ({len(transcript)} chars, source: {transcript_source})")

            # Only transcribe if no real-time transcript exists
            if not transcript:
                recording_url = call_attempt.get("recording_url")
                if not recording_url:
                    logger.warning(f"No recording URL and no existing transcript for call {call_sid}")
                    return

                # Resolve OpenAI API key
                openai_api_key = await self._resolve_openai_api_key_async(call_attempt)
                if not openai_api_key:
                    logger.error(f"No OpenAI API key available for call {call_sid}")
                    return

                # Download and transcribe recording (fallback path)
                logger.info(f"[ASYNC] No real-time transcript found, downloading recording from {recording_url}")
                audio_bytes = await self.download_recording(recording_url)
                if not audio_bytes:
                    logger.error("Failed to download recording")
                    return

                logger.info("[ASYNC] Transcribing audio (fallback - no real-time transcript available)...")
                transcript = await self.transcribe_audio(audio_bytes, openai_api_key)
                transcript_source = "post_call_transcription"
                if not transcript:
                    logger.error("Failed to transcribe audio")
                    transcript = ""
            else:
                # We have real-time transcript - still need openai key for analysis
                openai_api_key = await self._resolve_openai_api_key_async(call_attempt)

            # Step 3: PARALLEL - Update transcript in DB + Analyze transcript
            # These can run concurrently since analysis doesn't depend on DB update
            logger.info("Running analysis and transcript DB update in parallel...")

            async def update_transcript_in_db():
                await call_attempts_collection.update_one(
                    {"_id": call_attempt["_id"]},
                    {"$set": {"transcript": transcript, "updated_at": datetime.utcnow()}}
                )

            analysis_task = self.analyze_transcript(transcript, openai_api_key)
            db_update_task = update_transcript_in_db()

            analysis, _ = await asyncio.gather(analysis_task, db_update_task)

            if not analysis:
                logger.error("Failed to analyze transcript")
                return

            # Step 4: PARALLEL - Update analysis + Update lead + Book calendar + Send WhatsApp
            # All these operations are independent of each other
            logger.info("Running post-analysis updates in parallel...")

            async def update_analysis_in_db():
                await call_attempts_collection.update_one(
                    {"_id": call_attempt["_id"]},
                    {"$set": {"analysis": analysis, "updated_at": datetime.utcnow()}}
                )

            async def update_lead():
                sentiment_data = {
                    "label": analysis.get("sentiment", "neutral"),
                    "score": analysis.get("sentiment_score", 0.0)
                }
                await leads_collection.update_one(
                    {"_id": ObjectId(lead_id)},
                    {
                        "$set": {
                            "sentiment": sentiment_data,
                            "summary": analysis.get("summary", ""),
                            "updated_at": datetime.utcnow()
                        }
                    }
                )

            async def handle_appointment_and_notification():
                """Handle calendar booking and WhatsApp notification."""
                appointment = analysis.get("appointment")
                if not appointment or not appointment.get("start_iso"):
                    return

                logger.info(f"Appointment detected for lead {lead_id}: {appointment.get('title')}")
                try:
                    from app.services.calendar_service import CalendarService
                    from app.services.appointment_whatsapp_service import AppointmentWhatsAppService

                    calendar_service = CalendarService()
                    event_id = await calendar_service.book_appointment(lead_id, campaign_id, appointment)

                    if event_id:
                        # Get lead and campaign details for WhatsApp
                        lead = await leads_collection.find_one({"_id": ObjectId(lead_id)})
                        if lead and lead.get("phone"):
                            phone_number = lead["phone"]
                            customer_name = lead.get("full_name") or lead.get("first_name", "Customer")

                            campaigns_collection = db["campaigns"]
                            campaign = await campaigns_collection.find_one({"_id": ObjectId(campaign_id)})
                            if campaign:
                                user_id = str(campaign["user_id"])

                                booking_data = {
                                    "_id": call_sid,
                                    "customer_name": customer_name,
                                    "start_time": appointment.get("start_iso"),
                                    "location": appointment.get("location", "Phone Call"),
                                    "duration": appointment.get("duration", 30)
                                }

                                whatsapp_result = await AppointmentWhatsAppService.send_appointment_confirmation(
                                    user_id=user_id,
                                    booking_data=booking_data,
                                    phone_number=phone_number
                                )

                                if whatsapp_result.get("success"):
                                    logger.info(f"WhatsApp confirmation sent to {phone_number}")
                                else:
                                    logger.warning(f"Failed to send WhatsApp: {whatsapp_result.get('error')}")

                                # Send email confirmation if customer email is available
                                customer_email = appointment.get("attendee_email") or lead.get("email")
                                if customer_email and campaign.get("assistant_id"):
                                    try:
                                        from app.services.appointment_email_service import appointment_email_service
                                        appointment_doc = {
                                            "_id": call_sid,
                                            "customer_name": customer_name,
                                            "customer_email": customer_email,
                                            "customer_phone": phone_number,
                                            "start_time": appointment.get("start_iso"),
                                            "end_time": appointment.get("end_iso"),
                                            "title": appointment.get("title", "Appointment"),
                                            "timezone": appointment.get("timezone", "UTC"),
                                            "duration_minutes": appointment.get("duration", 30),
                                            "location": appointment.get("location"),
                                            "meeting_link": appointment.get("hangout_link"),
                                        }
                                        email_result = await appointment_email_service.send_appointment_confirmation(
                                            assistant_id=str(campaign["assistant_id"]),
                                            appointment_data=appointment_doc,
                                            call_sid=call_sid
                                        )
                                        if email_result.get("success"):
                                            logger.info(f"Email confirmation sent to {customer_email}")
                                        else:
                                            logger.warning(f"Email not sent: {email_result.get('error')}")
                                    except Exception as email_error:
                                        logger.error(f"Error sending email confirmation: {email_error}")
                except ImportError:
                    logger.warning("CalendarService not yet implemented")
                except Exception as e:
                    logger.error(f"Error in appointment handling: {e}")

            async def update_calendar_event_with_summary():
                """Update calendar event with call summary after processing."""
                try:
                    from app.services.calendar_service import CalendarService

                    calendar_service = CalendarService()
                    await calendar_service.update_event_with_call_summary(
                        call_sid=call_sid,
                        call_summary=analysis.get("summary", "No summary available"),
                        transcript=transcript,
                        recording_url=recording_url,
                        call_duration=call_attempt.get("duration")
                    )
                    logger.info(f"[CALENDAR_SUMMARY] Calendar event updated for call {call_sid}")
                except ImportError:
                    logger.warning("CalendarService not available for summary update")
                except Exception as e:
                    logger.warning(f"Error updating calendar with summary: {e}")

            # Run all post-analysis operations in parallel
            await asyncio.gather(
                update_analysis_in_db(),
                update_lead(),
                handle_appointment_and_notification(),
                update_calendar_event_with_summary(),
                return_exceptions=True  # Don't fail all if one fails
            )

            # Trigger workflows after call processing
            try:
                from app.services.integrations.workflow_engine import WorkflowEngine
                from app.models.workflow import TriggerEvent

                # Get lead details for customer info
                lead = await leads_collection.find_one({"_id": ObjectId(lead_id)})

                # Determine customer email (prefer extracted from call, fallback to lead data)
                customer_email = analysis.get("customer_email") or (lead.get("email", "") if lead else "")

                # Update lead with extracted email if found and not already set
                if analysis.get("customer_email") and lead and not lead.get("email"):
                    await leads_collection.update_one(
                        {"_id": ObjectId(lead_id)},
                        {"$set": {"email": analysis.get("customer_email"), "updated_at": datetime.utcnow()}}
                    )
                    logger.info(f"[EMAIL_EXTRACTION] Updated lead {lead_id} with email: {analysis.get('customer_email')}")

                # Get assistant info for workflow filtering
                assistant_id = call_attempt.get("assistant_id")
                assistant_name = None
                assigned_workflow_ids = []

                if assistant_id:
                    assistants_collection = db["assistants"]
                    try:
                        assistant_obj_id = assistant_id if isinstance(assistant_id, ObjectId) else ObjectId(str(assistant_id))
                        assistant = await assistants_collection.find_one({"_id": assistant_obj_id})
                        if assistant:
                            assistant_name = assistant.get("name")
                            assigned_workflow_ids = assistant.get("assigned_workflows", [])
                            logger.info(f"[WORKFLOWS] Assistant {assistant_name} has {len(assigned_workflow_ids)} assigned workflows: {assigned_workflow_ids}")
                    except Exception as e:
                        logger.warning(f"[WORKFLOWS] Error getting assistant info: {e}")

                # Prepare call data for workflow trigger with all necessary fields
                call_data = {
                    "_id": str(call_attempt["_id"]),
                    "call_sid": call_sid,
                    "status": call_attempt.get("status", "completed"),
                    "duration": call_attempt.get("duration", 0),
                    "direction": call_attempt.get("direction", "outbound"),
                    "from_number": call_attempt.get("from_number"),
                    "to_number": call_attempt.get("to_number"),
                    "transcription": transcript,
                    "transcript": transcript,  # Some workflows may use this name
                    "summary": analysis.get("summary", ""),
                    "sentiment": analysis.get("sentiment", "neutral"),
                    "sentiment_score": analysis.get("sentiment_score", 0.0),
                    "created_at": call_attempt.get("created_at"),
                    "ended_at": datetime.utcnow(),
                    "recording_url": call_attempt.get("recording_url"),
                    "campaign_id": campaign_id,
                    "lead_id": lead_id,
                    "customer_name": analysis.get("customer_name") or (lead.get("name", "") if lead else ""),
                    "customer_email": customer_email,
                    "customer_phone": call_attempt.get("to_number"),
                    "analysis": analysis,
                    "appointment_booked": analysis.get("appointment_booked", False),
                    "appointment_date": analysis.get("appointment_date"),
                    "email_mentioned": analysis.get("email_mentioned", False),
                    # Issue tracking fields (for support/technical calls)
                    "issue_description": analysis.get("issue_description"),
                    "issue_category": analysis.get("issue_category"),
                    "issue_priority": analysis.get("issue_priority"),
                    "action_required": analysis.get("action_required"),
                    "extracted_data": analysis.get("extracted_data", {}),
                    # Conversation log for detailed analysis
                    "conversation": analysis.get("conversation", []),
                    # Assistant info
                    "assistant_id": str(assistant_id) if assistant_id else None,
                    "assistant_name": assistant_name,
                }

                # Get user_id from call_attempt or campaign
                user_id = call_attempt.get("user_id")
                if not user_id and campaign_id:
                    campaigns_collection = db["campaigns"]
                    campaign = await campaigns_collection.find_one({"_id": ObjectId(campaign_id)})
                    if campaign:
                        user_id = campaign.get("user_id")

                if user_id:
                    logger.info(f"[WORKFLOWS] Starting workflow execution for call {call_sid}, user={user_id}, assistant={assistant_id}")

                    # Use the unified workflow engine
                    engine = WorkflowEngine()

                    # Trigger workflows - filter by assistant's assigned workflows if available
                    workflow_results = await engine.trigger_workflows(
                        trigger_event=TriggerEvent.CALL_COMPLETED,
                        trigger_data=call_data,
                        user_id=str(user_id),
                        assistant_id=str(assistant_id) if assistant_id else None,
                        assigned_workflow_ids=assigned_workflow_ids if assigned_workflow_ids else None
                    )

                    # Count and log results
                    executed = sum(1 for r in workflow_results if r.get("success"))
                    total = len(workflow_results)
                    logger.info(f"[WORKFLOWS] Executed {executed}/{total} workflows for call {call_sid}")

                    # Log individual workflow results
                    for result in workflow_results:
                        workflow_name = result.get('workflow_name', result.get('workflow_id', 'Unknown'))
                        if result.get("success"):
                            logger.info(f"[WORKFLOWS] Workflow '{workflow_name}' succeeded")
                        else:
                            logger.warning(f"[WORKFLOWS] Workflow '{workflow_name}' failed: {result.get('error')}")
                else:
                    logger.warning(f"[WORKFLOWS] No user_id found for call {call_sid}, skipping workflows")

            except Exception as e:
                logger.error(f"[WORKFLOWS] Error executing workflows: {e}")
                import traceback
                logger.error(traceback.format_exc())
                # Don't fail the entire post-call processing if workflows fail

            # Trigger n8n webhooks (legacy - direct n8n trigger for users with global n8n integration)
            try:
                from app.services.integrations.n8n_service import n8n_service

                if n8n_service.is_enabled() and user_id:
                    logger.info(f"[N8N] Triggering legacy n8n webhook for call {call_sid}")

                    # Trigger n8n webhook
                    n8n_result = await n8n_service.trigger_call_completed(
                        call_data=call_data,
                        user_id=str(user_id)
                    )

                    if n8n_result.get("success"):
                        logger.info(f"[N8N] Triggered n8n webhook successfully for call {call_sid}")
                    else:
                        logger.warning(f"[N8N] Failed to trigger n8n webhook: {n8n_result.get('error')}")

            except Exception as e:
                logger.error(f"[N8N] Error triggering n8n webhook: {e}")
                # Don't fail the entire post-call processing if n8n fails

            # Execute user_workflows (template-based workflows from /api/n8n/user-workflows)
            try:
                if user_id:
                    user_workflows_collection = db["user_workflows"]

                    # Find active user workflows for this user with call_completed trigger
                    user_workflows = await user_workflows_collection.find({
                        "user_id": str(user_id),
                        "active": True,
                        "trigger_type": "call_completed"
                    }).to_list(length=100)

                    if user_workflows:
                        logger.info(f"[USER_WORKFLOWS] Found {len(user_workflows)} active user workflows for user {user_id}")

                        for workflow in user_workflows:
                            try:
                                workflow_id = str(workflow["_id"])
                                workflow_name = workflow.get("name", "Unknown")
                                template_id = workflow.get("template_id", "")
                                config = workflow.get("config", {})

                                logger.info(f"[USER_WORKFLOWS] Executing '{workflow_name}' (template: {template_id})")

                                # Execute based on template type
                                execution_result = await self._execute_user_workflow(
                                    workflow_id=workflow_id,
                                    template_id=template_id,
                                    config=config,
                                    call_data=call_data,
                                    user_id=str(user_id)
                                )

                                # Update execution stats
                                await user_workflows_collection.update_one(
                                    {"_id": workflow["_id"]},
                                    {
                                        "$inc": {"execution_count": 1},
                                        "$set": {
                                            "last_execution": {
                                                "status": "success" if execution_result.get("success") else "failed",
                                                "finished_at": datetime.utcnow().isoformat(),
                                                "error": execution_result.get("error")
                                            },
                                            "updated_at": datetime.utcnow()
                                        }
                                    }
                                )

                                if execution_result.get("success"):
                                    logger.info(f"[USER_WORKFLOWS] '{workflow_name}' executed successfully")
                                else:
                                    logger.warning(f"[USER_WORKFLOWS] '{workflow_name}' failed: {execution_result.get('error')}")

                            except Exception as wf_error:
                                logger.error(f"[USER_WORKFLOWS] Error executing workflow {workflow.get('name', 'Unknown')}: {wf_error}")
                    else:
                        logger.debug(f"[USER_WORKFLOWS] No active user workflows found for user {user_id}")

            except Exception as e:
                logger.error(f"[USER_WORKFLOWS] Error executing user workflows: {e}")
                import traceback
                logger.error(traceback.format_exc())
                # Don't fail the entire post-call processing if user workflows fail

            logger.info(f"[ASYNC] Post-call processing completed for call {call_sid}")

        except Exception as e:
            logger.error(f"Error in async post-call processing: {e}")
            import traceback
            logger.error(traceback.format_exc())

    async def transcribe_and_update_call(self, call_sid: str, recording_url: str, force_reanalyze: bool = False):
        """
        Transcribe a call recording and update call_logs with the transcript.
        Optimized version with parallel operations.

        Args:
            call_sid: The call SID to process
            recording_url: URL to the recording
            force_reanalyze: If True, re-run GPT analysis even if call already has summary/conversation_log
        """
        try:
            logger.info(f"[ASYNC] Transcribing call {call_sid}")

            db = await AsyncDatabase.get_db()
            call_logs_collection = db["call_logs"]

            # Get the call
            call = await call_logs_collection.find_one({"call_sid": call_sid})
            if not call:
                logger.error(f"Call {call_sid} not found in database")
                return

            # Check for existing transcript
            existing_transcript = call.get("transcript")
            if existing_transcript and existing_transcript not in ["", "[Transcription unavailable]", "Unable to analyze call."]:
                logger.info(f"Call {call_sid} already has a transcript. Running analysis only...")

                # Run analysis on existing transcript if needed or forced
                needs_analysis = not call.get("summary") or call.get("summary") == "Unable to analyze call." or not call.get("conversation_log")
                if needs_analysis or force_reanalyze:
                    call_attempt = {"call_sid": call_sid}
                    openai_key = await self._resolve_openai_api_key_async(call_attempt)
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

                        await call_logs_collection.update_one(
                            {"call_sid": call_sid},
                            {"$set": update_data}
                        )
                return

            user_id = call.get("user_id")
            if not user_id:
                logger.error(f"No user_id for call {call_sid}")
                return

            # Get Twilio credentials
            from app.utils.twilio_helpers import decrypt_twilio_credentials

            provider_connections = db["provider_connections"]
            twilio_connection = await provider_connections.find_one({
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
            audio_bytes = await self.download_recording(recording_url, account_sid, auth_token)
            if not audio_bytes:
                logger.error(f"Failed to download recording for {call_sid}")
                return

            # Step 2: Resolve OpenAI API key
            call_attempt = {"call_sid": call_sid}
            openai_key = await self._resolve_openai_api_key_async(call_attempt)

            # Step 3: Transcribe
            transcript = await self.transcribe_audio(audio_bytes, openai_key)
            if not transcript:
                transcript = "[Transcription unavailable]"

            # Step 4: Analyze (can start immediately after transcription)
            analysis = await self.analyze_transcript(transcript, openai_key)
            if not analysis:
                analysis = {
                    "sentiment": "neutral",
                    "sentiment_score": 0.0,
                    "summary": "Unable to analyze call.",
                    "appointment": None
                }

            # Step 5: PARALLEL - Update call log + Calendar update + Email
            async def update_call_log():
                # Build update data
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
                    # Build customer_data object
                    customer_data = call.get("customer_data") or {}
                    if customer_email:
                        customer_data["email"] = customer_email
                        logger.info(f"Extracted customer email: {customer_email} for call {call_sid}")
                    if customer_name:
                        customer_data["name"] = customer_name
                        logger.info(f"Extracted customer name: {customer_name} for call {call_sid}")
                    update_data["customer_data"] = customer_data

                await call_logs_collection.update_one(
                    {"call_sid": call_sid},
                    {"$set": update_data}
                )

            async def update_calendar_and_send_email():
                try:
                    # Refresh call_log data
                    call_log = await call_logs_collection.find_one({"call_sid": call_sid})
                    if call_log and call_log.get("appointment_booked"):
                        from app.services.calendar_service import CalendarService
                        calendar_service = CalendarService()

                        summary = analysis.get("summary", "Call completed")
                        rec_url = call_log.get("recording_url")

                        await calendar_service.update_calendar_event_with_call_summary(
                            call_sid=call_sid,
                            call_summary=summary,
                            recording_url=rec_url
                        )
                        logger.info(f"Calendar event updated for {call_sid}")

                        # Send email in parallel with calendar update
                        await self._send_summary_email(db, call_sid, analysis, rec_url)

                except Exception as e:
                    logger.error(f"Failed to update calendar/send email: {e}")

            # Run final updates in parallel
            await asyncio.gather(
                update_call_log(),
                update_calendar_and_send_email(),
                return_exceptions=True
            )

            logger.info(f"[ASYNC] Transcription completed for call {call_sid}")

        except Exception as e:
            logger.error(f"Error transcribing call {call_sid}: {e}")
            import traceback
            logger.error(traceback.format_exc())

            # Update with error status
            try:
                db = await AsyncDatabase.get_db()
                await db["call_logs"].update_one(
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

    async def _send_summary_email(self, db, call_sid: str, analysis: Dict, recording_url: str):
        """Send email with call summary (async-safe wrapper)."""
        try:
            from app.services.async_email_service import AsyncEmailService

            appointments_collection = db["appointments"]
            appointment = await appointments_collection.find_one({"call_sid": call_sid})

            if appointment:
                users_collection = db["users"]
                user = await users_collection.find_one({"_id": appointment.get("user_id")})

                if user and user.get("email"):
                    email_service = AsyncEmailService()
                    await email_service.send_meeting_summary_email(
                        to_email=user.get("email"),
                        meeting_title=appointment.get("title", "Meeting"),
                        call_summary=analysis.get("summary", ""),
                        meeting_date=appointment.get("start"),
                        recording_url=recording_url,
                        call_sid=call_sid,
                        attendee_name=user.get("name") or user.get("email").split("@")[0]
                    )
                    logger.info(f"Summary email sent to {user.get('email')}")
        except ImportError:
            # Fall back to sync email if async not available
            logger.warning("AsyncEmailService not available, skipping email")
        except Exception as e:
            logger.error(f"Failed to send summary email: {e}")


# Singleton instance for easy import
async_post_call_processor = AsyncPostCallProcessor()

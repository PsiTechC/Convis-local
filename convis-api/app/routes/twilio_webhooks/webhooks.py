"""
Dynamic Twilio Webhook Router
Routes voice calls and SMS based on the To number (or AccountSid for subaccounts)
No manual webhook configuration needed - one endpoint handles all numbers.
"""

from fastapi import APIRouter, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse
from typing import Optional
from bson import ObjectId
import logging

from app.config.database import Database
from app.config.async_database import AsyncDatabase
from app.config.settings import settings
from app.services.async_call_status_processor import process_call_status_async
from twilio.twiml.voice_response import VoiceResponse, Connect
from twilio.twiml.messaging_response import MessagingResponse

logger = logging.getLogger(__name__)

router = APIRouter()


# ==================== Helper Functions ====================

async def _trigger_transcription_after_delay(call_sid: str, delay_seconds: int = 5):
    """
    Wait for recording to be ready, then trigger transcription.
    OPTIMIZED: Uses async MongoDB operations.

    Args:
        call_sid: Twilio Call SID
        delay_seconds: Seconds to wait before checking
    """
    import asyncio
    await asyncio.sleep(delay_seconds)

    try:
        db = await AsyncDatabase.get_db()
        call_logs_collection = db['call_logs']

        # Check if recording URL exists (async)
        call_log = await call_logs_collection.find_one({"call_sid": call_sid})
        if not call_log:
            logger.warning(f"Call log not found for transcription: {call_sid}")
            return

        recording_url = call_log.get("recording_url")
        if not recording_url:
            logger.info(f"No recording URL yet for {call_sid}, will transcribe when recording callback arrives")
            return

        # Trigger transcription using async processor
        from app.services.async_post_call_processor import AsyncPostCallProcessor
        processor = AsyncPostCallProcessor()

        logger.info(f"Starting transcription for call: {call_sid}")
        await processor.transcribe_and_update_call(call_sid, recording_url)

    except Exception as e:
        logger.error(f"Error triggering transcription for {call_sid}: {e}")


# ==================== Voice Webhook ====================

@router.api_route("/voice", methods=["GET", "POST"])
async def voice_webhook(
    request: Request,
    To: Optional[str] = Form(None),
    From: Optional[str] = Form(None),
    CallSid: Optional[str] = Form(None),
    AccountSid: Optional[str] = Form(None)
):
    """
    Dynamic voice webhook router.

    This single endpoint handles ALL incoming voice calls across all numbers.
    Routes calls based on:
    1. The To number (which Twilio number was called)
    2. (Optional) AccountSid for subaccount-based routing

    Twilio sends these parameters on every webhook:
    - To: The phone number that was called (your Twilio number)
    - From: The caller's phone number
    - CallSid: Unique call identifier
    - AccountSid: Account or subaccount SID

    Args:
        request: FastAPI request
        To: Twilio number that received the call
        From: Caller's number
        CallSid: Call SID
        AccountSid: Account/subaccount SID

    Returns:
        HTMLResponse: TwiML response
    """
    try:
        logger.info(f"Voice webhook - To: {To}, From: {From}, CallSid: {CallSid}")

        if not To:
            # Fallback: try to get from query params (GET request)
            To = request.query_params.get('To')
            From = request.query_params.get('From')
            CallSid = request.query_params.get('CallSid')
            AccountSid = request.query_params.get('AccountSid')

        if not To:
            logger.error("No 'To' parameter in webhook request")
            response = VoiceResponse()
            response.say("Sorry, we could not process your call. Please try again later.")
            return HTMLResponse(content=str(response), media_type="application/xml")

        db = Database.get_db()
        phone_numbers_collection = db['phone_numbers']
        assistants_collection = db['assistants']

        # Look up the phone number in our database
        phone_doc = phone_numbers_collection.find_one({"phone_number": To})

        if not phone_doc:
            logger.warning(f"Phone number {To} not found in database")
            response = VoiceResponse()
            response.say("Sorry, this number is not configured. Please contact support.")
            return HTMLResponse(content=str(response), media_type="application/xml")

        # Check if an assistant is assigned
        if not phone_doc.get("assigned_assistant_id"):
            logger.warning(f"No assistant assigned to {To}")
            response = VoiceResponse()
            response.say("Sorry, this number is not yet configured with an AI assistant. Please contact support.")
            return HTMLResponse(content=str(response), media_type="application/xml")

        assistant_id = str(phone_doc["assigned_assistant_id"])

        # Verify assistant exists
        assistant = assistants_collection.find_one({"_id": ObjectId(assistant_id)})
        if not assistant:
            logger.error(f"Assistant {assistant_id} not found for number {To}")
            response = VoiceResponse()
            response.say("Sorry, configuration error. Please contact support.")
            return HTMLResponse(content=str(response), media_type="application/xml")

        # Create TwiML response - connect directly to AI without artificial greetings
        response = VoiceResponse()

        # Connect to the media stream WebSocket for this specific assistant
        # Use API_BASE_URL from settings for production, otherwise detect from request
        if settings.api_base_url:
            # Convert https:// to wss:// for WebSocket
            base_url = settings.api_base_url.replace('https://', '').replace('http://', '')
            websocket_url = f'wss://{base_url}/api/inbound-calls/media-stream/{assistant_id}'
        else:
            # Fallback to request hostname detection
            host = request.url.hostname
            if request.url.port and request.url.port not in [80, 443]:
                host = f"{host}:{request.url.port}"
            websocket_url = f'wss://{host}/api/inbound-calls/media-stream/{assistant_id}'

        logger.info(f"Routing call to assistant {assistant_id} via {websocket_url}")

        # Enable call recording with callback URL
        if settings.api_base_url:
            recording_callback_url = f"{settings.api_base_url}/api/twilio-webhooks/recording?CallSid={{CallSid}}"
        else:
            protocol = 'https' if request.url.scheme == 'https' else 'http'
            host = request.url.hostname
            if request.url.port and request.url.port not in [80, 443]:
                host = f"{host}:{request.url.port}"
            recording_callback_url = f"{protocol}://{host}/api/twilio-webhooks/recording?CallSid={{CallSid}}"

        # Record the call for transcription
        response.record(
            recording_status_callback=recording_callback_url,
            recording_status_callback_event='completed',
            recording_status_callback_method='POST',
            max_length=3600,  # 1 hour max
            timeout=5,  # 5 seconds of silence ends recording
            transcribe=False  # We use OpenAI Whisper instead
        )

        connect = Connect()
        connect.stream(url=websocket_url)
        response.append(connect)

        return HTMLResponse(content=str(response), media_type="application/xml")

    except Exception as error:
        import traceback
        logger.error(f"Error in voice webhook: {str(error)}")
        logger.error(traceback.format_exc())

        # Return error TwiML
        response = VoiceResponse()
        response.say("Sorry, an error occurred. Please try again later.")
        return HTMLResponse(content=str(response), media_type="application/xml")


@router.api_route("/voice-status", methods=["GET", "POST"])
async def voice_status_callback(
    request: Request,
    CallSid: Optional[str] = Form(None),
    CallStatus: Optional[str] = Form(None),
    To: Optional[str] = Form(None),
    From: Optional[str] = Form(None),
    CallDuration: Optional[str] = Form(None)
):
    """
    Voice status callback - receives call status updates.

    Twilio sends status updates as calls progress:
    - initiated, ringing, in-progress, completed, busy, failed, no-answer

    You can use this to log call analytics, update dashboards, etc.

    Args:
        CallSid: Call SID
        CallStatus: Current status
        To: Twilio number
        From: Caller number
        CallDuration: Duration in seconds

    Returns:
        dict: Success message
    """
    try:
        logger.info(f"Voice status - CallSid: {CallSid}, Status: {CallStatus}, Duration: {CallDuration}s")

        # You can add custom logic here:
        # - Log to analytics database
        # - Update real-time dashboard
        # - Send notifications
        # - Calculate costs

        # For now, just log it
        db = Database.get_db()
        call_logs_collection = db['call_logs']

        if CallSid:
            call_logs_collection.update_one(
                {"call_sid": CallSid},
                {
                    "$set": {
                        "status": CallStatus,
                        "duration": int(CallDuration) if CallDuration else None,
                        "updated_at": datetime.utcnow()
                    },
                    "$setOnInsert": {
                        "call_sid": CallSid,
                        "to": To,
                        "from": From,
                        "created_at": datetime.utcnow()
                    }
                },
                upsert=True
            )

            # Trigger transcription and cost calculation when call completes
            if CallStatus == "completed":
                logger.info(f"Call completed, checking for recording to transcribe: {CallSid}")

                # Wait a few seconds for recording to be ready
                import asyncio
                asyncio.create_task(_trigger_transcription_after_delay(CallSid, 5))

                # Calculate and store call cost
                try:
                    from app.services.cost_calculator import calculate_and_store_call_cost
                    duration_seconds = int(CallDuration) if CallDuration else 0
                    if duration_seconds > 0:
                        asyncio.create_task(calculate_and_store_call_cost(CallSid, duration_seconds))
                        logger.info(f"[COST] Triggered cost calculation for call: {CallSid}")
                except Exception as cost_error:
                    logger.error(f"[COST] Failed to trigger cost calculation: {cost_error}")

        return {"message": "Status received"}

    except Exception as error:
        logger.error(f"Error in voice status callback: {str(error)}")
        import traceback
        logger.error(traceback.format_exc())
        return {"error": str(error)}


# ==================== SMS Webhook ====================

@router.api_route("/sms", methods=["GET", "POST"])
async def sms_webhook(
    request: Request,
    To: Optional[str] = Form(None),
    From: Optional[str] = Form(None),
    Body: Optional[str] = Form(None),
    MessageSid: Optional[str] = Form(None),
    AccountSid: Optional[str] = Form(None),
    NumMedia: Optional[str] = Form(None)
):
    """
    Dynamic SMS webhook router.

    This single endpoint handles ALL incoming SMS across all numbers.
    Routes messages based on the To number.

    Twilio sends these parameters:
    - To: Your Twilio number that received the SMS
    - From: Sender's phone number
    - Body: Message content
    - MessageSid: Unique message identifier
    - NumMedia: Number of media attachments (MMS)

    Args:
        request: FastAPI request
        To: Twilio number
        From: Sender number
        Body: Message text
        MessageSid: Message SID
        AccountSid: Account SID
        NumMedia: Number of media files

    Returns:
        HTMLResponse: TwiML response
    """
    try:
        logger.info(f"SMS webhook - To: {To}, From: {From}, Body: {Body[:50] if Body else 'None'}")

        if not To:
            # Fallback for GET
            To = request.query_params.get('To')
            From = request.query_params.get('From')
            Body = request.query_params.get('Body')
            MessageSid = request.query_params.get('MessageSid')

        if not To:
            logger.error("No 'To' parameter in SMS webhook")
            response = MessagingResponse()
            response.message("Error: Unable to process message.")
            return HTMLResponse(content=str(response), media_type="application/xml")

        db = Database.get_db()
        phone_numbers_collection = db['phone_numbers']
        assistants_collection = db['assistants']
        sms_logs_collection = db['sms_logs']

        # Look up the phone number
        phone_doc = phone_numbers_collection.find_one({"phone_number": To})

        if not phone_doc:
            logger.warning(f"SMS to unknown number: {To}")
            response = MessagingResponse()
            response.message("This number is not configured.")
            return HTMLResponse(content=str(response), media_type="application/xml")

        # Log the incoming SMS
        sms_log = {
            "message_sid": MessageSid,
            "to": To,
            "from": From,
            "body": Body,
            "num_media": int(NumMedia) if NumMedia else 0,
            "direction": "inbound",
            "phone_number_id": phone_doc["_id"],
            "created_at": datetime.utcnow()
        }

        # Check if assistant is assigned
        if phone_doc.get("assigned_assistant_id"):
            sms_log["assistant_id"] = phone_doc["assigned_assistant_id"]
            assistant_id = str(phone_doc["assigned_assistant_id"])

            # Fetch assistant
            assistant = assistants_collection.find_one({"_id": ObjectId(assistant_id)})
            if assistant:
                sms_log["assistant_name"] = assistant.get("name")

        sms_logs_collection.insert_one(sms_log)

        # For now, return a simple acknowledgment
        # TODO: In the future, you can integrate with OpenAI to generate intelligent responses
        response = MessagingResponse()

        if phone_doc.get("assigned_assistant_id"):
            response.message(f"Message received! This is handled by {assistant.get('name', 'our AI assistant')}. SMS responses coming soon!")
        else:
            response.message("Message received. This number is not yet configured with an AI assistant.")

        logger.info(f"SMS logged successfully - MessageSid: {MessageSid}")

        return HTMLResponse(content=str(response), media_type="application/xml")

    except Exception as error:
        import traceback
        logger.error(f"Error in SMS webhook: {str(error)}")
        logger.error(traceback.format_exc())

        response = MessagingResponse()
        response.message("Error processing your message. Please try again.")
        return HTMLResponse(content=str(response), media_type="application/xml")


@router.api_route("/sms-status", methods=["GET", "POST"])
async def sms_status_callback(
    request: Request,
    MessageSid: Optional[str] = Form(None),
    MessageStatus: Optional[str] = Form(None),
    To: Optional[str] = Form(None),
    From: Optional[str] = Form(None)
):
    """
    SMS status callback - receives SMS delivery status updates.

    Status values: queued, sending, sent, delivered, undelivered, failed

    Args:
        MessageSid: Message SID
        MessageStatus: Current status
        To: Recipient
        From: Sender

    Returns:
        dict: Success message
    """
    try:
        logger.info(f"SMS status - MessageSid: {MessageSid}, Status: {MessageStatus}")

        db = Database.get_db()
        sms_logs_collection = db['sms_logs']

        if MessageSid:
            sms_logs_collection.update_one(
                {"message_sid": MessageSid},
                {
                    "$set": {
                        "status": MessageStatus,
                        "updated_at": datetime.utcnow()
                    }
                }
            )

        return {"message": "Status received"}

    except Exception as error:
        logger.error(f"Error in SMS status callback: {str(error)}")
        import traceback
        logger.error(traceback.format_exc())
        return {"error": str(error)}


# Import datetime at the top
from datetime import datetime


# ==================== Campaign Webhooks ====================

@router.api_route("/outbound-call", methods=["GET", "POST"])
async def outbound_call_webhook(
    request: Request,
    leadId: Optional[str] = Form(None),
    campaignId: Optional[str] = Form(None),
    assistantId: Optional[str] = Form(None)
):
    """
    TwiML endpoint for outbound campaign calls.
    Connects the call to the assigned AI assistant.
    """
    try:
        # Try query params if form is empty
        if not leadId:
            leadId = request.query_params.get('leadId')
            campaignId = request.query_params.get('campaignId')
            assistantId = request.query_params.get('assistantId')

        logger.info(f"Outbound call - Lead: {leadId}, Campaign: {campaignId}, Assistant: {assistantId}")

        response = VoiceResponse()

        if not assistantId:
            response.say("Sorry, no assistant configured for this campaign.")
            return HTMLResponse(content=str(response), media_type="application/xml")

        # Connect to AI assistant via WebSocket
        # Use API_BASE_URL from settings for production, otherwise detect from request
        if settings.api_base_url:
            # Convert https:// to wss:// for WebSocket
            base_url = settings.api_base_url.replace('https://', '').replace('http://', '')
            stream_url = f'wss://{base_url}/api/outbound-calls/media-stream/{assistantId}'
        else:
            # Fallback to request hostname detection
            host = request.url.hostname
            if request.url.port and request.url.port not in [80, 443]:
                host = f"{host}:{request.url.port}"
            stream_url = f'wss://{host}/api/outbound-calls/media-stream/{assistantId}'

        logger.info(f"Connecting campaign call to assistant {assistantId} via {stream_url}")

        connect = Connect()
        query_params = []
        if campaignId:
            query_params.append(f"campaignId={campaignId}")
        if leadId:
            query_params.append(f"leadId={leadId}")
        if query_params:
            stream_url = f"{stream_url}?{'&'.join(query_params)}"
        connect.stream(url=stream_url)
        response.append(connect)

        return HTMLResponse(content=str(response), media_type="application/xml")

    except Exception as error:
        logger.error(f"Error in outbound call webhook: {error}")
        response = VoiceResponse()
        response.say("Sorry, an error occurred.")
        return HTMLResponse(content=str(response), media_type="application/xml")


@router.api_route("/call-status", methods=["GET", "POST"])
async def campaign_call_status(
    request: Request,
    CallSid: Optional[str] = Form(None),
    CallStatus: Optional[str] = Form(None),
    CallDuration: Optional[str] = Form(None),
    leadId: Optional[str] = Form(None),
    campaignId: Optional[str] = Form(None)
):
    """
    Campaign call status callback.
    Updates lead status and triggers next call on completion.
    """
    try:
        # Try query params
        if not CallSid:
            CallSid = request.query_params.get('CallSid')
            CallStatus = request.query_params.get('CallStatus')
            CallDuration = request.query_params.get('CallDuration')
            leadId = request.query_params.get('leadId')
            campaignId = request.query_params.get('campaignId')

        logger.info(f"[WEBHOOK] Campaign call status received - CallSid: {CallSid}, Status: {CallStatus}, Duration: {CallDuration}s, Lead: {leadId}, Campaign: {campaignId}")

        if not CallSid or not CallStatus:
            logger.error(f"[WEBHOOK] Missing required parameters - CallSid: {CallSid}, CallStatus: {CallStatus}")
            return {"error": "Missing required parameters"}

        # Process the status update (async for better performance)
        await process_call_status_async(CallSid, CallStatus, CallDuration, leadId, campaignId)
        logger.info(f"[WEBHOOK] Successfully processed call status for CallSid: {CallSid}")

        # Calculate cost for completed calls
        if CallStatus == "completed" and CallDuration:
            try:
                from app.services.cost_calculator import calculate_and_store_call_cost
                import asyncio
                duration_seconds = int(CallDuration)
                if duration_seconds > 0:
                    asyncio.create_task(calculate_and_store_call_cost(CallSid, duration_seconds))
                    logger.info(f"[COST] Triggered cost calculation for campaign call: {CallSid}")
            except Exception as cost_error:
                logger.error(f"[COST] Failed to trigger cost calculation: {cost_error}")

        return {"message": "Status updated"}

    except Exception as error:
        logger.error(f"[WEBHOOK] Error in campaign call status: {error}")
        import traceback
        logger.error(traceback.format_exc())
        return {"error": str(error)}


@router.api_route("/recording", methods=["GET", "POST"])
async def campaign_recording_callback(
    request: Request,
    RecordingSid: Optional[str] = Form(None),
    RecordingUrl: Optional[str] = Form(None),
    CallSid: Optional[str] = Form(None),
    RecordingStatus: Optional[str] = Form(None),
    RecordingDuration: Optional[str] = Form(None),
    leadId: Optional[str] = Form(None),
    campaignId: Optional[str] = Form(None)
):
    """
    Campaign recording callback.
    Stores recording URL and triggers post-call AI processing.
    """
    try:
        # Try query params
        if not RecordingSid:
            RecordingSid = request.query_params.get('RecordingSid')
            RecordingUrl = request.query_params.get('RecordingUrl')
            CallSid = request.query_params.get('CallSid')
            RecordingStatus = request.query_params.get('RecordingStatus')
            RecordingDuration = request.query_params.get('RecordingDuration')
            leadId = request.query_params.get('leadId')
            campaignId = request.query_params.get('campaignId')

        logger.info(f"Recording callback - RecordingSid: {RecordingSid}, CallSid: {CallSid}, Status: {RecordingStatus}")

        if not RecordingSid or not CallSid:
            return {"error": "Missing required parameters"}

        # Add .mp3 extension to recording URL for direct download
        recording_mp3_url = f"{RecordingUrl}.mp3" if RecordingUrl else None

        db = Database.get_db()
        call_attempts_collection = db["call_attempts"]
        call_logs_collection = db["call_logs"]

        # Update call attempt with recording info
        update_result = call_attempts_collection.update_one(
            {"call_sid": CallSid},
            {
                "$set": {
                    "recording_url": recording_mp3_url,
                    "recording_sid": RecordingSid,
                    "recording_status": RecordingStatus,
                    "recording_duration": int(RecordingDuration) if RecordingDuration else None,
                    "updated_at": datetime.utcnow()
                }
            }
        )

        # Also update call_logs with recording URL
        call_logs_collection.update_one(
            {"call_sid": CallSid},
            {
                "$set": {
                    "recording_url": recording_mp3_url,
                    "recording_sid": RecordingSid,
                    "recording_status": RecordingStatus,
                    "recording_duration": int(RecordingDuration) if RecordingDuration else None,
                    "updated_at": datetime.utcnow()
                }
            }
        )

        if update_result.matched_count > 0:
            logger.info(f"Recording URL saved for CallSid: {CallSid}")

        # Trigger post-call processing for completed recordings (async optimized)
        if RecordingStatus == "completed" and recording_mp3_url:
            try:
                from app.services.async_post_call_processor import AsyncPostCallProcessor
                processor = AsyncPostCallProcessor()
                import asyncio

                # Always trigger transcription for all calls (both realtime and custom provider modes)
                # Twilio native transcription doesn't work with <Stream> verb used by WebSocket calls
                logger.info(f"Triggering automatic transcription for call: {CallSid}")
                asyncio.create_task(processor.transcribe_and_update_call(CallSid, recording_mp3_url))

                # If this is a campaign call, also trigger post-call AI processing (sentiment/summary)
                if leadId and campaignId:
                    logger.info(f"Triggering post-call processing for campaign call: {CallSid}")
                    asyncio.create_task(processor.process_call(CallSid, leadId, campaignId))

            except Exception as e:
                logger.error(f"Error triggering post-call processing: {e}")

        return {"message": "Recording saved"}

    except Exception as error:
        logger.error(f"Error in recording callback: {error}")
        return {"error": str(error)}

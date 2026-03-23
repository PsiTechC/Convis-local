"""
WhatsApp Webhooks Routes
Handles incoming webhook events from Meta WhatsApp Business API
"""

from fastapi import APIRouter, HTTPException, Request, Query, status
from typing import Dict, Any
from datetime import datetime, timedelta
from bson import ObjectId
import logging

from app.config.database import Database
from app.config.settings import settings

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/webhook")
async def verify_webhook(
    request: Request,
    mode: str = Query(None, alias="hub.mode"),
    token: str = Query(None, alias="hub.verify_token"),
    challenge: str = Query(None, alias="hub.challenge")
):
    """
    Webhook verification endpoint for Meta WhatsApp
    Meta will call this endpoint to verify the webhook URL
    """
    logger.info(f"Webhook verification request: mode={mode}, token={token}")

    # Verify token matches what you configured in Meta App Dashboard
    verify_token = getattr(settings, 'whatsapp_webhook_verify_token', 'your_verify_token_here')

    if mode == "subscribe" and token == verify_token:
        logger.info("Webhook verified successfully")
        return int(challenge)
    else:
        logger.warning(f"Webhook verification failed: mode={mode}, token={token}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Verification failed"
        )


@router.post("/webhook")
async def handle_webhook(request: Request):
    """
    Handle incoming webhook events from WhatsApp

    Events include:
    - Message status updates (sent, delivered, read)
    - Incoming messages
    - Template status updates
    """
    try:
        body = await request.json()
        logger.info(f"Webhook received: {body}")

        # Process webhook data
        if body.get("object") == "whatsapp_business_account":
            entries = body.get("entry", [])

            for entry in entries:
                changes = entry.get("changes", [])

                for change in changes:
                    value = change.get("value", {})

                    # Handle message status updates
                    if "statuses" in value:
                        await handle_status_updates(value["statuses"])

                    # Handle incoming messages
                    if "messages" in value:
                        await handle_incoming_messages(value["messages"], value.get("metadata", {}))

                    # Handle message errors
                    if "errors" in value:
                        await handle_message_errors(value["errors"])

        return {"status": "success"}

    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}")
        # Return 200 to prevent Meta from retrying
        return {"status": "error", "message": str(e)}


async def handle_status_updates(statuses: list):
    """
    Handle message status updates (sent, delivered, read, failed)
    """
    db = Database.get_db()
    messages_collection = db["whatsapp_messages"]

    for status_update in statuses:
        message_id = status_update.get("id")
        status_value = status_update.get("status")
        timestamp = status_update.get("timestamp")

        if not message_id:
            continue

        logger.info(f"Status update for message {message_id}: {status_value}")

        update_data = {"status": status_value}

        # Update timestamp based on status
        if timestamp:
            ts_datetime = datetime.fromtimestamp(int(timestamp))

            if status_value == "delivered":
                update_data["delivered_at"] = ts_datetime
            elif status_value == "read":
                update_data["read_at"] = ts_datetime

        # Handle errors
        if "errors" in status_update:
            errors = status_update["errors"]
            if errors:
                update_data["error"] = errors[0].get("message", "Unknown error")
                update_data["status"] = "failed"

        # Update message in database
        result = messages_collection.update_one(
            {"message_id": message_id},
            {"$set": update_data}
        )

        if result.modified_count > 0:
            logger.info(f"Updated message {message_id} with status {status_value}")
        else:
            logger.warning(f"Message {message_id} not found in database")


async def handle_incoming_messages(messages: list, metadata: dict):
    """
    Handle incoming messages from customers
    """
    db = Database.get_db()
    incoming_messages_collection = db["whatsapp_incoming_messages"]

    phone_number_id = metadata.get("phone_number_id")

    for message in messages:
        message_id = message.get("id")
        from_number = message.get("from")
        timestamp = message.get("timestamp")
        message_type = message.get("type")

        logger.info(f"Incoming message {message_id} from {from_number}, type: {message_type}")

        # Extract message content based on type
        content = {}
        if message_type == "text":
            content = {"text": message.get("text", {}).get("body")}
        elif message_type == "image":
            content = message.get("image", {})
        elif message_type == "video":
            content = message.get("video", {})
        elif message_type == "document":
            content = message.get("document", {})
        elif message_type == "audio":
            content = message.get("audio", {})
        elif message_type == "location":
            content = message.get("location", {})
        elif message_type == "contacts":
            content = message.get("contacts", {})

        # Find the credential/user associated with this phone number
        credentials_collection = db["whatsapp_credentials"]

        # This is a simplified approach - you might need to decrypt and compare
        # For now, we'll store the message with phone_number_id reference
        credential = credentials_collection.find_one({"phone_number_id": phone_number_id})

        doc = {
            "message_id": message_id,
            "phone_number_id": phone_number_id,
            "from": from_number,
            "message_type": message_type,
            "content": content,
            "timestamp": datetime.fromtimestamp(int(timestamp)) if timestamp else datetime.utcnow(),
            "received_at": datetime.utcnow(),
            "processed": False
        }

        if credential:
            doc["user_id"] = credential["user_id"]
            doc["credential_id"] = credential["_id"]

        # Insert incoming message
        incoming_messages_collection.insert_one(doc)
        logger.info(f"Stored incoming message {message_id}")

        # Process appointment-related responses
        if message_type == "text" and content.get("text"):
            await process_appointment_response(from_number, content["text"], credential)


async def process_appointment_response(from_number: str, message_text: str, credential: dict):
    """
    Process customer responses to appointment confirmations
    Handles CONFIRM, RESCHEDULE, and CANCEL actions
    """
    if not credential:
        logger.warning(f"No credential found for message from {from_number}")
        return

    user_id = str(credential["user_id"])
    message_lower = message_text.lower().strip()

    logger.info(f"Processing appointment response from {from_number}: {message_text}")

    # Import services here to avoid circular imports
    from app.services.appointment_whatsapp_service import AppointmentWhatsAppService
    from app.services.calendar_service import CalendarService
    from app.services.whatsapp_service import WhatsAppService
    from app.utils.encryption import encryption_service

    db = Database.get_db()
    call_logs_collection = db["call_logs"]

    # Find the most recent call log for this phone number
    call_log = call_logs_collection.find_one(
        {"from_number": from_number, "user_id": credential["user_id"]},
        sort=[("created_at", -1)]
    )

    if not call_log:
        logger.warning(f"No call log found for phone number {from_number}")
        return

    # Check if there's an appointment linked to this call
    appointment_data = call_log.get("appointment")
    if not appointment_data:
        logger.warning(f"No appointment found in call log for {from_number}")
        return

    # Initialize WhatsApp service to send response
    api_key = encryption_service.decrypt(credential["api_key"])
    bearer_token = encryption_service.decrypt(credential["bearer_token"])
    api_url = credential.get("api_url", "https://whatsapp-api-backend-production.up.railway.app")

    whatsapp_service = WhatsAppService(
        api_key=api_key,
        bearer_token=bearer_token,
        base_url=api_url
    )

    # Determine action based on message
    if "confirm" in message_lower or "✅" in message_text or message_lower in ["yes", "ok", "okay"]:
        # CONFIRM appointment
        logger.info(f"Customer {from_number} confirmed appointment")

        # Update call log to mark appointment as confirmed
        call_logs_collection.update_one(
            {"_id": call_log["_id"]},
            {"$set": {"appointment.confirmed": True, "appointment.confirmed_at": datetime.utcnow()}}
        )

        # Send confirmation message
        response_text = "✅ Thank you for confirming your appointment! We look forward to seeing you."
        await whatsapp_service.send_text_message(to=from_number, message=response_text)
        logger.info(f"Sent confirmation acknowledgment to {from_number}")

    elif "cancel" in message_lower or "❌" in message_text:
        # CANCEL appointment
        logger.info(f"Customer {from_number} requested to cancel appointment")

        try:
            # Get calendar service and delete the event
            calendar_service = CalendarService()
            event_id = appointment_data.get("event_id")
            provider = appointment_data.get("provider")

            if event_id and provider:
                # Delete from calendar
                await calendar_service.delete_event(user_id, provider, event_id)
                logger.info(f"Deleted calendar event {event_id} for {from_number}")

                # Update call log
                call_logs_collection.update_one(
                    {"_id": call_log["_id"]},
                    {"$set": {"appointment.cancelled": True, "appointment.cancelled_at": datetime.utcnow()}}
                )

                # Send cancellation confirmation
                response_text = "❌ Your appointment has been cancelled. We hope to see you again soon!"
                await whatsapp_service.send_text_message(to=from_number, message=response_text)
                logger.info(f"Sent cancellation confirmation to {from_number}")
            else:
                logger.warning(f"Missing event_id or provider for cancellation: {appointment_data}")
                response_text = "We couldn't find your appointment details. Please contact us directly."
                await whatsapp_service.send_text_message(to=from_number, message=response_text)

        except Exception as e:
            logger.error(f"Error cancelling appointment: {str(e)}")
            response_text = "There was an error cancelling your appointment. Please contact us directly."
            await whatsapp_service.send_text_message(to=from_number, message=response_text)

    elif "reschedule" in message_lower or "📅" in message_text or "change" in message_lower:
        # RESCHEDULE appointment - Initial request
        logger.info(f"Customer {from_number} requested to reschedule appointment")

        # Mark as reschedule requested
        call_logs_collection.update_one(
            {"_id": call_log["_id"]},
            {"$set": {"appointment.reschedule_requested": True, "appointment.reschedule_requested_at": datetime.utcnow()}}
        )

        # Send reschedule instructions
        response_text = "📅 To reschedule your appointment, please reply with your preferred date and time.\n\nExample: March 20, 3:00 PM"
        await whatsapp_service.send_text_message(to=from_number, message=response_text)
        logger.info(f"Sent reschedule instructions to {from_number}")

    elif appointment_data.get("reschedule_requested"):
        # Customer is in reschedule mode and has sent a new time
        logger.info(f"Processing reschedule time from {from_number}: {message_text}")

        # Try to parse the new time
        new_time = AppointmentWhatsAppService.parse_reschedule_time(message_text)

        if new_time:
            try:
                # Get the original appointment duration (default 30 minutes)
                original_start = appointment_data.get("start_time")
                original_end = appointment_data.get("end_time")

                if isinstance(original_start, str):
                    original_start_dt = datetime.fromisoformat(original_start.replace('Z', '+00:00'))
                else:
                    original_start_dt = original_start

                if isinstance(original_end, str):
                    original_end_dt = datetime.fromisoformat(original_end.replace('Z', '+00:00'))
                else:
                    original_end_dt = original_end

                duration_minutes = int((original_end_dt - original_start_dt).total_seconds() / 60)

                # Calculate new end time
                new_end_time = new_time + timedelta(minutes=duration_minutes)

                # Update calendar event
                calendar_service = CalendarService()
                event_id = appointment_data.get("event_id")
                provider = appointment_data.get("provider")

                if event_id and provider:
                    success = await calendar_service.update_event(
                        user_id=user_id,
                        provider=provider,
                        event_id=event_id,
                        event_data={
                            "start_iso": new_time.isoformat(),
                            "end_iso": new_end_time.isoformat(),
                            "timezone": appointment_data.get("timezone", "America/New_York")
                        }
                    )

                    if success:
                        # Update call log
                        call_logs_collection.update_one(
                            {"_id": call_log["_id"]},
                            {
                                "$set": {
                                    "appointment.start_time": new_time.isoformat(),
                                    "appointment.end_time": new_end_time.isoformat(),
                                    "appointment.rescheduled": True,
                                    "appointment.rescheduled_at": datetime.utcnow(),
                                    "appointment.reschedule_requested": False
                                }
                            }
                        )

                        # Format the new time for confirmation
                        formatted_date = new_time.strftime("%B %d, %Y")
                        formatted_time = new_time.strftime("%I:%M %p")

                        response_text = f"✅ Your appointment has been rescheduled to {formatted_date} at {formatted_time}. See you then!"
                        await whatsapp_service.send_text_message(to=from_number, message=response_text)
                        logger.info(f"Appointment rescheduled successfully for {from_number}")
                    else:
                        response_text = "There was an error rescheduling your appointment. Please contact us directly."
                        await whatsapp_service.send_text_message(to=from_number, message=response_text)
                else:
                    logger.warning(f"Missing event_id or provider for reschedule: {appointment_data}")
                    response_text = "We couldn't find your appointment details. Please contact us directly."
                    await whatsapp_service.send_text_message(to=from_number, message=response_text)

            except Exception as e:
                logger.error(f"Error rescheduling appointment: {str(e)}")
                response_text = "There was an error rescheduling your appointment. Please contact us directly."
                await whatsapp_service.send_text_message(to=from_number, message=response_text)
        else:
            # Could not parse the time
            response_text = "I couldn't understand that date/time. Please try again with a format like:\n• March 20, 3:00 PM\n• Tomorrow at 2pm\n• Next Monday at 10am"
            await whatsapp_service.send_text_message(to=from_number, message=response_text)
            logger.warning(f"Could not parse reschedule time from {from_number}: {message_text}")

    else:
        # Unknown response - provide guidance
        logger.info(f"Unknown appointment response from {from_number}: {message_text}")
        response_text = "Please reply with:\n• CONFIRM to confirm your appointment\n• RESCHEDULE to change the time\n• CANCEL to cancel"
        await whatsapp_service.send_text_message(to=from_number, message=response_text)


async def handle_message_errors(errors: list):
    """
    Handle message errors from WhatsApp
    """
    logger.error(f"WhatsApp errors received: {errors}")

    db = Database.get_db()
    messages_collection = db["whatsapp_messages"]

    for error in errors:
        error_code = error.get("code")
        error_message = error.get("message")
        error_data = error.get("error_data", {})

        logger.error(f"WhatsApp error {error_code}: {error_message}")

        # Update message status if we have message reference
        # This depends on the error structure from Meta


@router.get("/incoming-messages")
async def get_incoming_messages(
    limit: int = 50,
    offset: int = 0,
    unprocessed_only: bool = False
):
    """
    Get incoming messages (requires authentication in production)
    """
    db = Database.get_db()
    incoming_messages_collection = db["whatsapp_incoming_messages"]

    query = {}
    if unprocessed_only:
        query["processed"] = False

    messages = incoming_messages_collection.find(query).sort("received_at", -1).skip(offset).limit(limit)

    result = []
    for msg in messages:
        result.append({
            "id": str(msg["_id"]),
            "message_id": msg.get("message_id"),
            "from": msg.get("from"),
            "message_type": msg.get("message_type"),
            "content": msg.get("content"),
            "timestamp": msg.get("timestamp").isoformat() if msg.get("timestamp") else None,
            "processed": msg.get("processed", False)
        })

    return result


@router.post("/incoming-messages/{message_id}/mark-processed")
async def mark_message_processed(message_id: str):
    """
    Mark an incoming message as processed
    """
    db = Database.get_db()
    incoming_messages_collection = db["whatsapp_incoming_messages"]

    try:
        result = incoming_messages_collection.update_one(
            {"_id": ObjectId(message_id)},
            {"$set": {"processed": True, "processed_at": datetime.utcnow()}}
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid message ID format"
        )

    if result.modified_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found"
        )

    return {"status": "success"}

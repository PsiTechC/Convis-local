"""
Appointment WhatsApp Confirmation Service
Handles sending appointment confirmations via WhatsApp
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime
from bson import ObjectId

from app.config.database import Database
from app.services.whatsapp_service import WhatsAppService
from app.utils.encryption import encryption_service

logger = logging.getLogger(__name__)


class AppointmentWhatsAppService:
    """Service for sending appointment confirmations via WhatsApp"""

    @staticmethod
    async def get_whatsapp_service_for_user(user_id: str) -> Optional[WhatsAppService]:
        """Get the first active WhatsApp credential for a user"""
        db = Database.get_db()
        credentials_collection = db["whatsapp_credentials"]

        # Find the first active WhatsApp credential for this user
        credential = credentials_collection.find_one({
            "user_id": ObjectId(user_id),
            "status": "active"
        })

        if not credential:
            logger.warning(f"No active WhatsApp credential found for user {user_id}")
            return None

        # Decrypt credentials
        api_key = encryption_service.decrypt(credential["api_key"])
        bearer_token = encryption_service.decrypt(credential["bearer_token"])
        api_url = credential.get("api_url", "https://whatsapp-api-backend-production.up.railway.app")

        return WhatsAppService(
            api_key=api_key,
            bearer_token=bearer_token,
            base_url=api_url
        )

    @staticmethod
    async def send_appointment_confirmation(
        user_id: str,
        booking_data: Dict[str, Any],
        phone_number: str
    ) -> Dict[str, Any]:
        """
        Send appointment confirmation via WhatsApp

        Args:
            user_id: User ID who owns the WhatsApp credential
            booking_data: Booking information from calendar
            phone_number: Customer's phone number (with country code)

        Returns:
            Result of the WhatsApp message send
        """
        whatsapp_service = await AppointmentWhatsAppService.get_whatsapp_service_for_user(user_id)

        if not whatsapp_service:
            return {
                "success": False,
                "error": "No active WhatsApp credential found. Please add a WhatsApp credential first."
            }

        # Extract booking details
        customer_name = booking_data.get("customer_name", "Customer")
        start_time = booking_data.get("start_time")
        location = booking_data.get("location", "Online Meeting")
        duration = booking_data.get("duration", 30)

        # Format date and time
        if isinstance(start_time, str):
            start_datetime = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
        else:
            start_datetime = start_time

        formatted_date = start_datetime.strftime("%B %d, %Y")  # March 15, 2025
        formatted_time = start_datetime.strftime("%I:%M %p")   # 2:00 PM

        # Template parameters
        # Template: appointment_confirmation
        # Body: Hello {{1}}, Your appointment has been confirmed for {{2}} at {{3}}. Location: {{4}} Duration: {{5}} minutes
        template_params = [
            customer_name,
            formatted_date,
            formatted_time,
            location,
            str(duration)
        ]

        try:
            # Send template message
            result = await whatsapp_service.send_template_message(
                to=phone_number,
                template_name="convis_confirmation",
                parameters=template_params
            )

            if result.get("success"):
                # Save message record
                db = Database.get_db()
                messages_collection = db["whatsapp_messages"]

                # Get credential ID
                credentials_collection = db["whatsapp_credentials"]
                credential = credentials_collection.find_one({
                    "user_id": ObjectId(user_id),
                    "status": "active"
                })

                if credential:
                    message_doc = {
                        "user_id": ObjectId(user_id),
                        "credential_id": credential["_id"],
                        "to": phone_number,
                        "message_type": "template",
                        "template_name": "convis_confirmation",
                        "status": "sent",
                        "message_id": result.get("message_id"),
                        "content": {
                            "booking_id": str(booking_data.get("_id")),
                            "customer_name": customer_name,
                            "appointment_date": formatted_date,
                            "appointment_time": formatted_time
                        },
                        "sent_at": datetime.utcnow(),
                        "delivered_at": None,
                        "read_at": None
                    }
                    messages_collection.insert_one(message_doc)

                logger.info(f"Appointment confirmation sent to {phone_number} for booking {booking_data.get('_id')}")
                return result
            else:
                logger.error(f"Failed to send appointment confirmation: {result.get('error')}")
                return result

        except Exception as e:
            logger.error(f"Error sending appointment confirmation: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    @staticmethod
    def parse_reschedule_time(message_text: str) -> Optional[datetime]:
        """
        Parse date and time from customer's reschedule message

        Args:
            message_text: Message text like "March 20, 3:00 PM" or "tomorrow at 2pm"

        Returns:
            Parsed datetime or None
        """
        try:
            from dateutil import parser
            import re

            # Clean up common patterns
            text = message_text.strip()

            # Try to parse with dateutil parser
            parsed_dt = parser.parse(text, fuzzy=True)

            # If the parsed date is in the past, assume they meant next occurrence
            if parsed_dt < datetime.now():
                # If only time was specified, assume tomorrow
                if not any(word in text.lower() for word in ['today', 'tomorrow', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday', 'jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec']):
                    parsed_dt = parsed_dt.replace(day=datetime.now().day + 1)

            return parsed_dt

        except Exception as e:
            logger.error(f"Error parsing reschedule time '{message_text}': {e}")
            return None

    @staticmethod
    async def handle_appointment_response(
        phone_number: str,
        message_text: str,
        user_id: str
    ) -> Dict[str, Any]:
        """
        Handle customer responses to appointment confirmations

        Args:
            phone_number: Customer's phone number
            message_text: Message text received
            user_id: User ID who owns the appointment

        Returns:
            Action to take based on the response
        """
        message_lower = message_text.lower().strip()

        # Find the most recent appointment for this phone number
        db = Database.get_db()

        # This would need to be implemented based on your calendar integration
        # For now, returning the action type
        if "confirm" in message_lower or "✅" in message_text:
            return {
                "action": "confirm",
                "message": "Thank you for confirming your appointment!"
            }
        elif "reschedule" in message_lower or "📅" in message_text:
            return {
                "action": "reschedule",
                "message": "Please reply with your preferred date and time (e.g., 'March 20, 3:00 PM')"
            }
        elif "cancel" in message_lower or "❌" in message_text:
            return {
                "action": "cancel",
                "message": "Your appointment has been cancelled. We hope to see you again soon!"
            }
        else:
            return {
                "action": "unknown",
                "message": "Please reply with CONFIRM, RESCHEDULE, or CANCEL"
            }

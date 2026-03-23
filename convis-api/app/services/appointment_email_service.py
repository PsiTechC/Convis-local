"""
Appointment Email Service
Handles sending appointment confirmation emails with custom templates and attachments
Uses user-configured SMTP settings per AI assistant
"""
import os
import re
import ssl
import logging
import smtplib
import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime
from typing import Optional, Dict, Any, List
from bson import ObjectId
from cryptography.fernet import Fernet

from app.config.database import Database
from app.config.settings import settings

logger = logging.getLogger(__name__)

# Encryption key for SMTP passwords (should be in settings for production)
# Use encryption_key from settings, fallback to jwt_secret if not set
_default_key = settings.encryption_key or settings.jwt_secret or "default_encryption_key_32chars!"
ENCRYPTION_KEY = os.getenv("SMTP_ENCRYPTION_KEY", _default_key[:32].ljust(32, '0'))


def get_fernet():
    """Get Fernet instance for encryption/decryption"""
    import base64
    key = base64.urlsafe_b64encode(ENCRYPTION_KEY.encode()[:32].ljust(32, b'0'))
    return Fernet(key)


def encrypt_password(password: str) -> str:
    """Encrypt SMTP password for storage"""
    if not password:
        return ""
    try:
        fernet = get_fernet()
        return fernet.encrypt(password.encode()).decode()
    except Exception as e:
        logger.error(f"Error encrypting password: {e}")
        return password  # Return plain if encryption fails


def decrypt_password(encrypted_password: str) -> str:
    """Decrypt SMTP password from storage"""
    if not encrypted_password:
        return ""
    try:
        fernet = get_fernet()
        return fernet.decrypt(encrypted_password.encode()).decode()
    except Exception as e:
        logger.error(f"Error decrypting password: {e}")
        return encrypted_password  # Return as-is if decryption fails


# Available template variables with descriptions
TEMPLATE_VARIABLES = {
    "customer_name": "Customer's full name",
    "customer_email": "Customer's email address",
    "customer_phone": "Customer's phone number",
    "appointment_date": "Formatted appointment date (e.g., December 15, 2024)",
    "appointment_time": "Formatted appointment time (e.g., 2:30 PM)",
    "appointment_datetime": "Full date and time (e.g., December 15, 2024 at 2:30 PM)",
    "appointment_duration": "Duration in minutes",
    "appointment_title": "Title/subject of the appointment",
    "meeting_link": "Video meeting link (if available)",
    "location": "Physical location (if available)",
    "company_name": "Your company name",
    "agent_name": "AI agent name",
    "sender_name": "Email sender name",
    "sender_email": "Email sender address",
    "timezone": "Appointment timezone",
}


def format_date(iso_date: str, timezone: str = "UTC") -> str:
    """Format ISO date to readable format"""
    try:
        dt = datetime.fromisoformat(iso_date.replace('Z', '+00:00'))
        return dt.strftime("%B %d, %Y")
    except Exception:
        return iso_date


def format_time(iso_date: str, timezone: str = "UTC") -> str:
    """Format ISO date to readable time"""
    try:
        dt = datetime.fromisoformat(iso_date.replace('Z', '+00:00'))
        return dt.strftime("%I:%M %p")
    except Exception:
        return iso_date


def format_datetime(iso_date: str, timezone: str = "UTC") -> str:
    """Format ISO date to readable date and time"""
    try:
        dt = datetime.fromisoformat(iso_date.replace('Z', '+00:00'))
        return dt.strftime("%B %d, %Y at %I:%M %p")
    except Exception:
        return iso_date


def substitute_variables(template: str, variables: Dict[str, Any]) -> str:
    """
    Substitute template variables in the format {{variable_name}}

    Args:
        template: Template string with {{variable_name}} placeholders
        variables: Dictionary of variable names to values

    Returns:
        Template with variables substituted
    """
    if not template:
        return ""

    result = template

    # Replace all {{variable_name}} patterns
    pattern = r'\{\{(\w+)\}\}'

    def replace_var(match):
        var_name = match.group(1)
        value = variables.get(var_name, "")
        # Handle None values
        if value is None:
            return ""
        return str(value)

    result = re.sub(pattern, replace_var, result)
    return result


def build_template_variables(
    appointment_data: Dict[str, Any],
    assistant: Dict[str, Any],
    user: Dict[str, Any],
    smtp_config: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Build the complete dictionary of template variables

    Args:
        appointment_data: Appointment details from database
        assistant: AI assistant document
        user: User document
        smtp_config: SMTP configuration

    Returns:
        Dictionary of all available template variables
    """
    # Get start time for formatting
    start_time = appointment_data.get('start_time') or appointment_data.get('start_iso', '')
    if isinstance(start_time, datetime):
        start_time = start_time.isoformat()

    timezone = appointment_data.get('timezone', 'UTC')

    return {
        # Customer info
        "customer_name": appointment_data.get('customer_name') or appointment_data.get('attendee_name', 'Valued Customer'),
        "customer_email": appointment_data.get('customer_email') or appointment_data.get('attendee_email', ''),
        "customer_phone": appointment_data.get('customer_phone') or appointment_data.get('attendee_phone', ''),

        # Appointment info
        "appointment_date": format_date(start_time, timezone) if start_time else '',
        "appointment_time": format_time(start_time, timezone) if start_time else '',
        "appointment_datetime": format_datetime(start_time, timezone) if start_time else '',
        "appointment_duration": str(appointment_data.get('duration_minutes', appointment_data.get('duration', 30))),
        "appointment_title": appointment_data.get('title', 'Appointment'),
        "meeting_link": appointment_data.get('meeting_link', appointment_data.get('hangout_link', '')),
        "location": appointment_data.get('location', ''),
        "timezone": timezone,

        # Company/Agent info
        "company_name": user.get('companyName', user.get('company_name', 'Our Company')),
        "agent_name": assistant.get('name', 'AI Assistant'),
        "sender_name": smtp_config.get('sender_name', user.get('companyName', 'Our Company')),
        "sender_email": smtp_config.get('sender_email', ''),
    }


def get_default_html_template() -> str:
    """Get the default HTML email template"""
    return """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Appointment Confirmation</title>
</head>
<body style="margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f5f5f5;">
    <table role="presentation" style="width: 100%; border-collapse: collapse;">
        <tr>
            <td align="center" style="padding: 40px 0;">
                <table role="presentation" style="width: 600px; max-width: 100%; border-collapse: collapse; background-color: #ffffff; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
                    <!-- Header -->
                    <tr>
                        <td style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 30px 40px; border-radius: 8px 8px 0 0;">
                            <h1 style="margin: 0; color: #ffffff; font-size: 24px; font-weight: 600;">
                                Appointment Confirmed
                            </h1>
                            <p style="margin: 10px 0 0; color: rgba(255,255,255,0.9); font-size: 14px;">
                                {{company_name}}
                            </p>
                        </td>
                    </tr>

                    <!-- Body -->
                    <tr>
                        <td style="padding: 40px;">
                            <p style="margin: 0 0 20px; color: #333333; font-size: 16px; line-height: 1.6;">
                                Dear {{customer_name}},
                            </p>

                            <p style="margin: 0 0 30px; color: #555555; font-size: 15px; line-height: 1.6;">
                                Thank you for scheduling an appointment with us. Here are your appointment details:
                            </p>

                            <!-- Appointment Details Card -->
                            <table role="presentation" style="width: 100%; border-collapse: collapse; background-color: #f8f9fa; border-radius: 8px; margin-bottom: 30px;">
                                <tr>
                                    <td style="padding: 25px;">
                                        <table role="presentation" style="width: 100%; border-collapse: collapse;">
                                            <tr>
                                                <td style="padding: 8px 0; color: #666666; font-size: 14px; width: 120px;">Date:</td>
                                                <td style="padding: 8px 0; color: #333333; font-size: 14px; font-weight: 600;">{{appointment_date}}</td>
                                            </tr>
                                            <tr>
                                                <td style="padding: 8px 0; color: #666666; font-size: 14px;">Time:</td>
                                                <td style="padding: 8px 0; color: #333333; font-size: 14px; font-weight: 600;">{{appointment_time}}</td>
                                            </tr>
                                            <tr>
                                                <td style="padding: 8px 0; color: #666666; font-size: 14px;">Duration:</td>
                                                <td style="padding: 8px 0; color: #333333; font-size: 14px; font-weight: 600;">{{appointment_duration}} minutes</td>
                                            </tr>
                                            <tr>
                                                <td style="padding: 8px 0; color: #666666; font-size: 14px;">Timezone:</td>
                                                <td style="padding: 8px 0; color: #333333; font-size: 14px; font-weight: 600;">{{timezone}}</td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                            </table>

                            <p style="margin: 0 0 20px; color: #555555; font-size: 15px; line-height: 1.6;">
                                If you need to reschedule or cancel, please contact us as soon as possible.
                            </p>

                            <p style="margin: 30px 0 0; color: #333333; font-size: 15px;">
                                Best regards,<br>
                                <strong>{{sender_name}}</strong>
                            </p>
                        </td>
                    </tr>

                    <!-- Footer -->
                    <tr>
                        <td style="background-color: #f8f9fa; padding: 20px 40px; border-radius: 0 0 8px 8px; border-top: 1px solid #e9ecef;">
                            <p style="margin: 0; color: #888888; font-size: 12px; text-align: center;">
                                This email was sent by {{company_name}}
                            </p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
"""


def get_default_text_template() -> str:
    """Get the default plain text email template"""
    return """
Appointment Confirmed - {{company_name}}

Dear {{customer_name}},

Thank you for scheduling an appointment with us. Here are your appointment details:

Date: {{appointment_date}}
Time: {{appointment_time}}
Duration: {{appointment_duration}} minutes
Timezone: {{timezone}}

If you need to reschedule or cancel, please contact us as soon as possible.

Best regards,
{{sender_name}}

---
This email was sent by {{company_name}}
"""


class AppointmentEmailService:
    """Service for sending appointment confirmation emails"""

    def __init__(self):
        # LAZY initialization - don't connect to DB at import time
        # This is critical for Cloud Run fast startup
        self._db = None

    @property
    def db(self):
        """Lazy database connection - only connect when first needed."""
        if self._db is None:
            self._db = Database.get_db()
        return self._db

    async def send_appointment_confirmation(
        self,
        assistant_id: str,
        appointment_data: Dict[str, Any],
        call_sid: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send appointment confirmation email using assistant's email settings

        Args:
            assistant_id: AI assistant ID
            appointment_data: Appointment details including customer email
            call_sid: Optional call SID for logging

        Returns:
            Dict with success status and message
        """
        try:
            # Get assistant configuration
            assistants_collection = self.db['assistants']
            assistant = assistants_collection.find_one({"_id": ObjectId(assistant_id)})

            if not assistant:
                return {"success": False, "error": "Assistant not found"}

            # Check if email is enabled
            if not assistant.get('email_enabled', False):
                logger.info(f"Email not enabled for assistant {assistant_id}")
                return {"success": False, "error": "Email not enabled for this assistant"}

            # Get SMTP config
            smtp_config = assistant.get('smtp_config', {})
            if not smtp_config or not smtp_config.get('enabled', False):
                return {"success": False, "error": "SMTP not configured for this assistant"}

            # Validate required SMTP fields
            required_fields = ['smtp_host', 'smtp_port', 'smtp_username', 'smtp_password', 'sender_email']
            for field in required_fields:
                if not smtp_config.get(field):
                    return {"success": False, "error": f"Missing SMTP configuration: {field}"}

            # Get recipient email
            recipient_email = appointment_data.get('customer_email') or appointment_data.get('attendee_email')
            if not recipient_email:
                return {"success": False, "error": "No recipient email provided"}

            # Get user for company info
            users_collection = self.db['users']
            user = users_collection.find_one({"_id": ObjectId(assistant.get('user_id'))})
            if not user:
                user = {}

            # Build template variables
            variables = build_template_variables(appointment_data, assistant, user, smtp_config)

            # Get email template
            email_template = assistant.get('email_template', {})

            # Get subject and body
            subject_template = email_template.get('subject_template') or "Your Appointment Confirmation - {{appointment_date}}"
            body_html = email_template.get('body_html') or get_default_html_template()
            body_text = email_template.get('body_text') or get_default_text_template()

            # Substitute variables
            subject = substitute_variables(subject_template, variables)
            html_content = substitute_variables(body_html, variables)
            text_content = substitute_variables(body_text, variables)

            # Get attachments
            attachments = assistant.get('email_attachments', [])

            # Send email
            result = await self._send_email(
                smtp_config=smtp_config,
                to_email=recipient_email,
                to_name=variables.get('customer_name', ''),
                subject=subject,
                html_content=html_content,
                text_content=text_content,
                attachments=attachments
            )

            # Log email
            await self._log_email(
                assistant_id=assistant_id,
                user_id=str(assistant.get('user_id')),
                recipient_email=recipient_email,
                recipient_name=variables.get('customer_name'),
                subject=subject,
                status="sent" if result['success'] else "failed",
                appointment_id=str(appointment_data.get('_id', '')),
                call_sid=call_sid,
                error_message=result.get('error')
            )

            return result

        except Exception as e:
            logger.error(f"Error sending appointment confirmation: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {"success": False, "error": str(e)}

    async def _send_email(
        self,
        smtp_config: Dict[str, Any],
        to_email: str,
        to_name: str,
        subject: str,
        html_content: str,
        text_content: str,
        attachments: List[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Send email using SMTP

        Args:
            smtp_config: SMTP configuration
            to_email: Recipient email
            to_name: Recipient name
            subject: Email subject
            html_content: HTML body
            text_content: Plain text body
            attachments: List of attachment file info

        Returns:
            Dict with success status
        """
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = f"{smtp_config.get('sender_name', '')} <{smtp_config['sender_email']}>"
            msg['To'] = f"{to_name} <{to_email}>" if to_name else to_email

            # Add text and HTML parts
            text_part = MIMEText(text_content, 'plain', 'utf-8')
            html_part = MIMEText(html_content, 'html', 'utf-8')

            msg.attach(text_part)
            msg.attach(html_part)

            # Add attachments
            if attachments:
                # Convert to mixed type for attachments
                msg_with_attachments = MIMEMultipart('mixed')
                msg_with_attachments['Subject'] = msg['Subject']
                msg_with_attachments['From'] = msg['From']
                msg_with_attachments['To'] = msg['To']

                # Add the alternative part
                alt_part = MIMEMultipart('alternative')
                alt_part.attach(text_part)
                alt_part.attach(html_part)
                msg_with_attachments.attach(alt_part)

                # Add each attachment
                for att in attachments:
                    file_path = att.get('file_path')
                    if file_path and os.path.exists(file_path):
                        try:
                            with open(file_path, 'rb') as f:
                                attachment_data = f.read()

                            mime_type = att.get('mime_type', 'application/octet-stream')
                            maintype, subtype = mime_type.split('/', 1) if '/' in mime_type else ('application', 'octet-stream')

                            attachment_part = MIMEBase(maintype, subtype)
                            attachment_part.set_payload(attachment_data)
                            encoders.encode_base64(attachment_part)

                            original_filename = att.get('original_filename', att.get('filename', 'attachment'))
                            attachment_part.add_header(
                                'Content-Disposition',
                                'attachment',
                                filename=original_filename
                            )

                            msg_with_attachments.attach(attachment_part)
                            logger.info(f"Added attachment: {original_filename}")
                        except Exception as e:
                            logger.error(f"Error adding attachment {file_path}: {e}")

                msg = msg_with_attachments

            # Decrypt password
            password = decrypt_password(smtp_config['smtp_password'])

            # Send email using async SMTP
            use_tls = smtp_config.get('use_tls', True)
            use_ssl = smtp_config.get('use_ssl', False)

            if use_ssl:
                # SSL connection (usually port 465)
                await aiosmtplib.send(
                    msg,
                    hostname=smtp_config['smtp_host'],
                    port=smtp_config['smtp_port'],
                    username=smtp_config['smtp_username'],
                    password=password,
                    use_tls=True,
                    validate_certs=True
                )
            else:
                # STARTTLS connection (usually port 587)
                await aiosmtplib.send(
                    msg,
                    hostname=smtp_config['smtp_host'],
                    port=smtp_config['smtp_port'],
                    username=smtp_config['smtp_username'],
                    password=password,
                    start_tls=use_tls
                )

            logger.info(f"Email sent successfully to {to_email}")
            return {"success": True, "message": "Email sent successfully"}

        except aiosmtplib.SMTPAuthenticationError as e:
            logger.error(f"SMTP authentication failed: {e}")
            return {"success": False, "error": "SMTP authentication failed. Check username and password."}
        except aiosmtplib.SMTPConnectError as e:
            logger.error(f"SMTP connection failed: {e}")
            return {"success": False, "error": f"Failed to connect to SMTP server: {smtp_config['smtp_host']}:{smtp_config['smtp_port']}"}
        except Exception as e:
            logger.error(f"Error sending email: {e}")
            return {"success": False, "error": str(e)}

    async def _log_email(
        self,
        assistant_id: str,
        user_id: str,
        recipient_email: str,
        recipient_name: Optional[str],
        subject: str,
        status: str,
        appointment_id: Optional[str] = None,
        call_sid: Optional[str] = None,
        error_message: Optional[str] = None
    ):
        """Log email sending for tracking"""
        try:
            email_logs_collection = self.db['email_logs']

            log_entry = {
                "assistant_id": assistant_id,
                "user_id": user_id,
                "recipient_email": recipient_email,
                "recipient_name": recipient_name,
                "subject": subject,
                "status": status,
                "appointment_id": appointment_id,
                "call_sid": call_sid,
                "error_message": error_message,
                "sent_at": datetime.utcnow(),
                "opened_at": None,
                "clicked_at": None
            }

            email_logs_collection.insert_one(log_entry)
            logger.info(f"Email log created for {recipient_email}")

        except Exception as e:
            logger.error(f"Error logging email: {e}")

    async def test_smtp_connection(
        self,
        smtp_config: Dict[str, Any],
        test_recipient: str
    ) -> Dict[str, Any]:
        """
        Test SMTP connection by sending a test email

        Args:
            smtp_config: SMTP configuration to test
            test_recipient: Email address to send test to

        Returns:
            Dict with success status and message
        """
        try:
            test_html = """
            <html>
            <body style="font-family: Arial, sans-serif; padding: 20px;">
                <h2 style="color: #667eea;">SMTP Connection Test Successful!</h2>
                <p>This is a test email to verify your SMTP configuration.</p>
                <p>Your email settings are working correctly.</p>
                <hr style="border: 1px solid #eee; margin: 20px 0;">
                <p style="color: #888; font-size: 12px;">Sent from Convis AI Platform</p>
            </body>
            </html>
            """

            test_text = """
            SMTP Connection Test Successful!

            This is a test email to verify your SMTP configuration.
            Your email settings are working correctly.

            ---
            Sent from Convis AI Platform
            """

            result = await self._send_email(
                smtp_config=smtp_config,
                to_email=test_recipient,
                to_name="",
                subject="SMTP Test - Convis AI Platform",
                html_content=test_html,
                text_content=test_text,
                attachments=None
            )

            return result

        except Exception as e:
            logger.error(f"SMTP test failed: {e}")
            return {"success": False, "error": str(e)}


# Singleton instance
appointment_email_service = AppointmentEmailService()

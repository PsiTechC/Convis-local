"""
Async Email Service for Convis
Non-blocking email operations using aiosmtplib
"""
import aiosmtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Optional
from app.config.settings import settings

logger = logging.getLogger(__name__)


class AsyncEmailService:
    """
    Async service for sending emails using aiosmtplib.

    Benefits over sync smtplib:
    - Non-blocking I/O - doesn't block the event loop
    - Better connection pooling
    - Native async/await support
    """

    def __init__(self):
        self.smtp_host = settings.smtp_host
        self.smtp_port = settings.smtp_port
        self.smtp_use_ssl = settings.smtp_use_ssl
        self.email_user = settings.email_user
        self.email_pass = settings.email_pass
        self.frontend_url = settings.frontend_url

    async def _send_email(self, message: MIMEMultipart) -> bool:
        """Send email asynchronously using aiosmtplib."""
        try:
            if self.smtp_use_ssl and self.smtp_port == 465:
                # Use SSL connection for port 465
                await aiosmtplib.send(
                    message,
                    hostname=self.smtp_host,
                    port=self.smtp_port,
                    username=self.email_user,
                    password=self.email_pass,
                    use_tls=True,
                    timeout=30
                )
            else:
                # Use STARTTLS for other ports (e.g., 587)
                await aiosmtplib.send(
                    message,
                    hostname=self.smtp_host,
                    port=self.smtp_port,
                    username=self.email_user,
                    password=self.email_pass,
                    start_tls=True,
                    timeout=30
                )
            return True
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False

    async def send_meeting_scheduled_email(
        self,
        to_email: str,
        meeting_title: str,
        meeting_date: datetime,
        meeting_time: str,
        timezone: str,
        notes: Optional[str] = None,
        call_sid: Optional[str] = None,
        attendee_name: Optional[str] = None
    ) -> bool:
        """Send email notification when a meeting is scheduled during a call."""
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"Meeting Scheduled: {meeting_title}"
            msg['From'] = f"Convis AI <{self.email_user}>"
            msg['To'] = to_email

            formatted_date = meeting_date.strftime("%A, %B %d, %Y")

            call_details_section = ""
            if call_sid:
                call_log_url = f"{self.frontend_url}/call-logs?call_sid={call_sid}"
                call_details_section = f"""
                <div style="margin-top: 20px; padding: 15px; background-color: #f8f9fa; border-left: 4px solid #4CAF50; border-radius: 4px;">
                    <p style="margin: 0; font-size: 14px; color: #666;">
                        <strong>Call Details Available</strong><br>
                        This meeting was scheduled during a phone call.
                    </p>
                    <p style="margin-top: 10px;">
                        <a href="{call_log_url}" style="display: inline-block; padding: 10px 20px; background-color: #4CAF50; color: white; text-decoration: none; border-radius: 4px; font-weight: 500;">
                            View Call Details & Recording
                        </a>
                    </p>
                </div>
                """

            html_body = f"""
            <!DOCTYPE html>
            <html>
            <head><meta charset="UTF-8"></head>
            <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
                <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 30px; text-align: center; border-radius: 8px 8px 0 0;">
                    <h1 style="color: white; margin: 0; font-size: 28px;">Meeting Scheduled</h1>
                </div>
                <div style="background-color: #ffffff; padding: 30px; border: 1px solid #e0e0e0; border-top: none; border-radius: 0 0 8px 8px;">
                    <p style="font-size: 16px; margin-bottom: 20px;">
                        Hello{f", {attendee_name}" if attendee_name else ""},
                    </p>
                    <p style="font-size: 16px; margin-bottom: 25px;">
                        Your meeting has been successfully scheduled and added to your calendar.
                    </p>
                    <div style="background-color: #f8f9fa; padding: 20px; border-radius: 8px; margin-bottom: 20px;">
                        <h2 style="margin-top: 0; margin-bottom: 15px; font-size: 20px; color: #333;">
                            {meeting_title}
                        </h2>
                        <table style="width: 100%; border-collapse: collapse;">
                            <tr>
                                <td style="padding: 8px 0; color: #666; font-weight: 500; width: 100px;">Date:</td>
                                <td style="padding: 8px 0; color: #333; font-weight: 600;">{formatted_date}</td>
                            </tr>
                            <tr>
                                <td style="padding: 8px 0; color: #666; font-weight: 500;">Time:</td>
                                <td style="padding: 8px 0; color: #333; font-weight: 600;">{meeting_time}</td>
                            </tr>
                            <tr>
                                <td style="padding: 8px 0; color: #666; font-weight: 500;">Timezone:</td>
                                <td style="padding: 8px 0; color: #333;">{timezone}</td>
                            </tr>
                        </table>
                        {f'<div style="margin-top: 15px; padding-top: 15px; border-top: 1px solid #e0e0e0;"><p style="margin: 0; color: #666; font-size: 14px;"><strong>Notes:</strong></p><p style="margin: 5px 0 0 0; color: #333;">{notes}</p></div>' if notes else ''}
                    </div>
                    {call_details_section}
                    <div style="margin-top: 25px; padding: 15px; background-color: #e3f2fd; border-radius: 6px;">
                        <p style="margin: 0; font-size: 14px; color: #1976d2;">
                            This event has been automatically added to your connected calendar.
                        </p>
                    </div>
                </div>
                <div style="text-align: center; margin-top: 30px; padding-top: 20px; border-top: 1px solid #e0e0e0;">
                    <p style="font-size: 12px; color: #999; margin: 0;">
                        This is an automated message from Convis AI<br>
                        {datetime.now().year} Convis. All rights reserved.
                    </p>
                </div>
            </body>
            </html>
            """

            text_body = f"""
Meeting Scheduled: {meeting_title}

Hello{f", {attendee_name}" if attendee_name else ""},

Your meeting has been successfully scheduled.

MEETING DETAILS:
Title: {meeting_title}
Date: {formatted_date}
Time: {meeting_time}
Timezone: {timezone}
{"Notes: " + notes if notes else ""}

This event has been automatically added to your connected calendar.

---
This is an automated message from Convis AI
            """

            part1 = MIMEText(text_body, 'plain')
            part2 = MIMEText(html_body, 'html')
            msg.attach(part1)
            msg.attach(part2)

            success = await self._send_email(msg)
            if success:
                logger.info(f"Meeting scheduled email sent to {to_email}")
            return success

        except Exception as e:
            logger.error(f"Failed to send meeting scheduled email: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    async def send_meeting_summary_email(
        self,
        to_email: str,
        meeting_title: str,
        call_summary: str,
        meeting_date: datetime,
        recording_url: Optional[str] = None,
        call_sid: Optional[str] = None,
        attendee_name: Optional[str] = None
    ) -> bool:
        """Send email with call summary after the meeting call is completed."""
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"Call Summary: {meeting_title}"
            msg['From'] = f"Convis AI <{self.email_user}>"
            msg['To'] = to_email

            formatted_date = meeting_date.strftime("%A, %B %d, %Y") if meeting_date else "N/A"

            links_section = ""
            if call_sid or recording_url:
                call_log_url = f"{self.frontend_url}/call-logs?call_sid={call_sid}" if call_sid else ""
                links_section = f"""
                <div style="margin-top: 25px;">
                    {f'<a href="{call_log_url}" style="display: inline-block; margin-right: 10px; margin-bottom: 10px; padding: 12px 24px; background-color: #4CAF50; color: white; text-decoration: none; border-radius: 6px; font-weight: 500;">View Full Call Details</a>' if call_sid else ''}
                    {f'<a href="{recording_url}" style="display: inline-block; margin-bottom: 10px; padding: 12px 24px; background-color: #2196F3; color: white; text-decoration: none; border-radius: 6px; font-weight: 500;">Listen to Recording</a>' if recording_url else ''}
                </div>
                """

            html_body = f"""
            <!DOCTYPE html>
            <html>
            <head><meta charset="UTF-8"></head>
            <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
                <div style="background: linear-gradient(135deg, #4CAF50 0%, #45a049 100%); padding: 30px; text-align: center; border-radius: 8px 8px 0 0;">
                    <h1 style="color: white; margin: 0; font-size: 28px;">Call Summary Available</h1>
                </div>
                <div style="background-color: #ffffff; padding: 30px; border: 1px solid #e0e0e0; border-top: none; border-radius: 0 0 8px 8px;">
                    <p style="font-size: 16px; margin-bottom: 20px;">
                        Hello{f", {attendee_name}" if attendee_name else ""},
                    </p>
                    <p style="font-size: 16px; margin-bottom: 25px;">
                        Your call has been processed and the summary is now available.
                    </p>
                    <div style="background-color: #f8f9fa; padding: 15px; border-radius: 6px; margin-bottom: 20px;">
                        <p style="margin: 0; font-size: 14px; color: #666;">
                            <strong>Meeting:</strong> {meeting_title}<br>
                            <strong>Date:</strong> {formatted_date}
                        </p>
                    </div>
                    <div style="margin-bottom: 25px;">
                        <h2 style="margin-top: 0; margin-bottom: 15px; font-size: 20px; color: #333; border-bottom: 2px solid #4CAF50; padding-bottom: 10px;">
                            Call Summary
                        </h2>
                        <div style="background-color: #f8f9fa; padding: 20px; border-radius: 6px; border-left: 4px solid #4CAF50;">
                            <p style="margin: 0; color: #333; white-space: pre-line;">{call_summary}</p>
                        </div>
                    </div>
                    {links_section}
                    <div style="margin-top: 25px; padding: 15px; background-color: #e3f2fd; border-radius: 6px;">
                        <p style="margin: 0; font-size: 14px; color: #1976d2;">
                            This summary has been automatically added to your calendar event.
                        </p>
                    </div>
                </div>
                <div style="text-align: center; margin-top: 30px; padding-top: 20px; border-top: 1px solid #e0e0e0;">
                    <p style="font-size: 12px; color: #999; margin: 0;">
                        This is an automated message from Convis AI<br>
                        {datetime.now().year} Convis. All rights reserved.
                    </p>
                </div>
            </body>
            </html>
            """

            text_body = f"""
Call Summary: {meeting_title}

Hello{f", {attendee_name}" if attendee_name else ""},

Your call has been processed and the summary is now available.

MEETING DETAILS:
Meeting: {meeting_title}
Date: {formatted_date}

CALL SUMMARY:
{call_summary}

{"RECORDING: " + recording_url if recording_url else ""}
{"FULL DETAILS: " + self.frontend_url + "/call-logs?call_sid=" + call_sid if call_sid else ""}

---
This is an automated message from Convis AI
            """

            part1 = MIMEText(text_body, 'plain')
            part2 = MIMEText(html_body, 'html')
            msg.attach(part1)
            msg.attach(part2)

            success = await self._send_email(msg)
            if success:
                logger.info(f"Meeting summary email sent to {to_email}")
            return success

        except Exception as e:
            logger.error(f"Failed to send meeting summary email: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    async def send_otp_email(self, email: str, otp: str) -> bool:
        """Send OTP email asynchronously."""
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = 'Welcome to Convis Labs! Verify Your Email'
            msg['From'] = self.email_user
            msg['To'] = email

            html_body = f"""
            <div style="font-family: Arial, sans-serif; color: #333;">
                <p>Dear User,</p>
                <p>Thank you for registering with Convis Labs. We are excited to have you on board and look forward to providing you with the best AI-driven solutions to enhance your experience.</p>
                <p>To complete your registration, please verify your email by entering the OTP provided below</p>
                <h3>Your OTP: <strong>{otp}</strong></h3>
                <p>If you didn't register, please ignore this email.</p>
                <p>Best regards,<br>Convis Labs Team</p>
            </div>
            """

            html_part = MIMEText(html_body, 'html')
            msg.attach(html_part)

            success = await self._send_email(msg)
            if success:
                logger.info(f"OTP email sent successfully to {email}")
            return success

        except Exception as e:
            logger.error(f"Failed to send OTP email to {email}: {e}")
            return False

    async def send_otp_email_with_retry(
        self,
        email: str,
        otp: str,
        retries: int = 3,
        delay_ms: int = 3000
    ) -> None:
        """
        Send OTP email with retry logic (non-blocking).

        Args:
            email: Recipient email address
            otp: The OTP code to send
            retries: Number of retry attempts
            delay_ms: Delay between retries in milliseconds
        """
        import asyncio
        delay_seconds = delay_ms / 1000

        for attempt in range(1, retries + 1):
            try:
                success = await self.send_otp_email(email, otp)
                if success:
                    return
                raise Exception("Email send returned False")

            except Exception as error:
                logger.error(f"Attempt {attempt} failed to send email to {email}: {str(error)}")

                if attempt == retries:
                    raise Exception('Failed to send OTP after multiple attempts.')

                # Non-blocking sleep
                await asyncio.sleep(delay_seconds)


# Singleton instance
async_email_service = AsyncEmailService()

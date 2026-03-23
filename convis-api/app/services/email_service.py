"""
Email Service for Convis
Sends professional emails for meeting notifications and call summaries
"""
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Optional
from app.config.settings import settings

logger = logging.getLogger(__name__)


class EmailService:
    """Service for sending emails"""

    def __init__(self):
        self.smtp_host = settings.smtp_host
        self.smtp_port = settings.smtp_port
        self.smtp_use_ssl = settings.smtp_use_ssl
        self.email_user = settings.email_user
        self.email_pass = settings.email_pass
        self.frontend_url = settings.frontend_url

    def _create_smtp_connection(self):
        """Create SMTP connection"""
        try:
            if self.smtp_use_ssl:
                server = smtplib.SMTP_SSL(self.smtp_host, self.smtp_port)
            else:
                server = smtplib.SMTP(self.smtp_host, self.smtp_port)
                server.starttls()

            server.login(self.email_user, self.email_pass)
            return server
        except Exception as e:
            logger.error(f"Failed to create SMTP connection: {e}")
            raise

    def send_meeting_scheduled_email(
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
        """
        Send email notification when a meeting is scheduled during a call.

        Args:
            to_email: Recipient email address
            meeting_title: Title of the meeting
            meeting_date: Date of the meeting
            meeting_time: Time of the meeting (e.g., "2:00 PM - 3:00 PM")
            timezone: Timezone (e.g., "America/New_York")
            notes: Additional notes from the call
            call_sid: Call SID for linking to call details
            attendee_name: Name of the person who scheduled the meeting

        Returns:
            True if sent successfully, False otherwise
        """
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"Meeting Scheduled: {meeting_title}"
            msg['From'] = f"Convis AI <{self.email_user}>"
            msg['To'] = to_email

            # Format date
            formatted_date = meeting_date.strftime("%A, %B %d, %Y")

            # Create call details link if available
            call_details_section = ""
            if call_sid:
                call_log_url = f"{self.frontend_url}/call-logs?call_sid={call_sid}"
                call_details_section = f"""
                <div style="margin-top: 20px; padding: 15px; background-color: #f8f9fa; border-left: 4px solid #4CAF50; border-radius: 4px;">
                    <p style="margin: 0; font-size: 14px; color: #666;">
                        📊 <strong>Call Details Available</strong><br>
                        This meeting was scheduled during a phone call. The full call summary and recording will be added to your calendar automatically.
                    </p>
                    <p style="margin-top: 10px;">
                        <a href="{call_log_url}" style="display: inline-block; padding: 10px 20px; background-color: #4CAF50; color: white; text-decoration: none; border-radius: 4px; font-weight: 500;">
                            View Call Details & Recording
                        </a>
                    </p>
                </div>
                """

            # Create HTML body
            html_body = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
            </head>
            <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">

                <!-- Header -->
                <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 30px; text-align: center; border-radius: 8px 8px 0 0;">
                    <h1 style="color: white; margin: 0; font-size: 28px; font-weight: 600;">Meeting Scheduled ✓</h1>
                </div>

                <!-- Main Content -->
                <div style="background-color: #ffffff; padding: 30px; border: 1px solid #e0e0e0; border-top: none; border-radius: 0 0 8px 8px;">

                    <p style="font-size: 16px; margin-bottom: 20px;">
                        Hello{f", {attendee_name}" if attendee_name else ""},
                    </p>

                    <p style="font-size: 16px; margin-bottom: 25px;">
                        Your meeting has been successfully scheduled and added to your calendar.
                    </p>

                    <!-- Meeting Details Card -->
                    <div style="background-color: #f8f9fa; padding: 20px; border-radius: 8px; margin-bottom: 20px;">
                        <h2 style="margin-top: 0; margin-bottom: 15px; font-size: 20px; color: #333;">
                            📅 {meeting_title}
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

                    <!-- Calendar Integration -->
                    <div style="margin-top: 25px; padding: 15px; background-color: #e3f2fd; border-radius: 6px;">
                        <p style="margin: 0; font-size: 14px; color: #1976d2;">
                            ℹ️ This event has been automatically added to your connected calendar (Google Calendar or Microsoft Calendar).
                        </p>
                    </div>

                    <!-- Footer Message -->
                    <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #e0e0e0;">
                        <p style="font-size: 14px; color: #666; margin: 0;">
                            Need to reschedule or have questions? Simply reply to this email or contact us.
                        </p>
                    </div>
                </div>

                <!-- Email Footer -->
                <div style="text-align: center; margin-top: 30px; padding-top: 20px; border-top: 1px solid #e0e0e0;">
                    <p style="font-size: 12px; color: #999; margin: 0;">
                        This is an automated message from Convis AI<br>
                        © {datetime.now().year} Convis. All rights reserved.
                    </p>
                </div>

            </body>
            </html>
            """

            # Create plain text alternative
            text_body = f"""
Meeting Scheduled: {meeting_title}

Hello{f", {attendee_name}" if attendee_name else ""},

Your meeting has been successfully scheduled and added to your calendar.

MEETING DETAILS:
Title: {meeting_title}
Date: {formatted_date}
Time: {meeting_time}
Timezone: {timezone}
{"Notes: " + notes if notes else ""}

{"CALL DETAILS:" if call_sid else ""}
{f"This meeting was scheduled during a phone call. View the full call details and recording at: {self.frontend_url}/call-logs?call_sid={call_sid}" if call_sid else ""}

This event has been automatically added to your connected calendar.

Need to reschedule? Simply reply to this email.

---
This is an automated message from Convis AI
© {datetime.now().year} Convis. All rights reserved.
            """

            # Attach both versions
            part1 = MIMEText(text_body, 'plain')
            part2 = MIMEText(html_body, 'html')

            msg.attach(part1)
            msg.attach(part2)

            # Send email
            server = self._create_smtp_connection()
            server.send_message(msg)
            server.quit()

            logger.info(f"Meeting scheduled email sent to {to_email}")
            return True

        except Exception as e:
            logger.error(f"Failed to send meeting scheduled email: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    def send_meeting_summary_email(
        self,
        to_email: str,
        meeting_title: str,
        call_summary: str,
        meeting_date: datetime,
        recording_url: Optional[str] = None,
        call_sid: Optional[str] = None,
        attendee_name: Optional[str] = None
    ) -> bool:
        """
        Send email with call summary after the meeting call is completed.

        Args:
            to_email: Recipient email address
            meeting_title: Title of the meeting
            call_summary: AI-generated summary of the call
            meeting_date: Date of the meeting
            recording_url: URL to the call recording
            call_sid: Call SID for linking to full call details
            attendee_name: Name of the attendee

        Returns:
            True if sent successfully, False otherwise
        """
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"Call Summary: {meeting_title}"
            msg['From'] = f"Convis AI <{self.email_user}>"
            msg['To'] = to_email

            # Format date
            formatted_date = meeting_date.strftime("%A, %B %d, %Y")

            # Create links section
            links_section = ""
            if call_sid or recording_url:
                call_log_url = f"{self.frontend_url}/call-logs?call_sid={call_sid}" if call_sid else ""

                links_section = f"""
                <div style="margin-top: 25px;">
                    {f'<a href="{call_log_url}" style="display: inline-block; margin-right: 10px; margin-bottom: 10px; padding: 12px 24px; background-color: #4CAF50; color: white; text-decoration: none; border-radius: 6px; font-weight: 500;">📊 View Full Call Details</a>' if call_sid else ''}
                    {f'<a href="{recording_url}" style="display: inline-block; margin-bottom: 10px; padding: 12px 24px; background-color: #2196F3; color: white; text-decoration: none; border-radius: 6px; font-weight: 500;">🎙️ Listen to Recording</a>' if recording_url else ''}
                </div>
                """

            # Create HTML body
            html_body = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
            </head>
            <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">

                <!-- Header -->
                <div style="background: linear-gradient(135deg, #4CAF50 0%, #45a049 100%); padding: 30px; text-align: center; border-radius: 8px 8px 0 0;">
                    <h1 style="color: white; margin: 0; font-size: 28px; font-weight: 600;">Call Summary Available</h1>
                </div>

                <!-- Main Content -->
                <div style="background-color: #ffffff; padding: 30px; border: 1px solid #e0e0e0; border-top: none; border-radius: 0 0 8px 8px;">

                    <p style="font-size: 16px; margin-bottom: 20px;">
                        Hello{f", {attendee_name}" if attendee_name else ""},
                    </p>

                    <p style="font-size: 16px; margin-bottom: 25px;">
                        Your call has been processed and the summary is now available. This summary has also been automatically added to your calendar event.
                    </p>

                    <!-- Meeting Info -->
                    <div style="background-color: #f8f9fa; padding: 15px; border-radius: 6px; margin-bottom: 20px;">
                        <p style="margin: 0; font-size: 14px; color: #666;">
                            <strong>Meeting:</strong> {meeting_title}<br>
                            <strong>Date:</strong> {formatted_date}
                        </p>
                    </div>

                    <!-- Call Summary -->
                    <div style="margin-bottom: 25px;">
                        <h2 style="margin-top: 0; margin-bottom: 15px; font-size: 20px; color: #333; border-bottom: 2px solid #4CAF50; padding-bottom: 10px;">
                            📞 Call Summary
                        </h2>
                        <div style="background-color: #f8f9fa; padding: 20px; border-radius: 6px; border-left: 4px solid #4CAF50;">
                            <p style="margin: 0; color: #333; white-space: pre-line;">{call_summary}</p>
                        </div>
                    </div>

                    {links_section}

                    <!-- Calendar Note -->
                    <div style="margin-top: 25px; padding: 15px; background-color: #e3f2fd; border-radius: 6px;">
                        <p style="margin: 0; font-size: 14px; color: #1976d2;">
                            ℹ️ This summary has been automatically added to your calendar event for easy reference.
                        </p>
                    </div>

                </div>

                <!-- Email Footer -->
                <div style="text-align: center; margin-top: 30px; padding-top: 20px; border-top: 1px solid #e0e0e0;">
                    <p style="font-size: 12px; color: #999; margin: 0;">
                        This is an automated message from Convis AI<br>
                        © {datetime.now().year} Convis. All rights reserved.
                    </p>
                </div>

            </body>
            </html>
            """

            # Create plain text alternative
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

This summary has been automatically added to your calendar event.

---
This is an automated message from Convis AI
© {datetime.now().year} Convis. All rights reserved.
            """

            # Attach both versions
            part1 = MIMEText(text_body, 'plain')
            part2 = MIMEText(html_body, 'html')

            msg.attach(part1)
            msg.attach(part2)

            # Send email
            server = self._create_smtp_connection()
            server.send_message(msg)
            server.quit()

            logger.info(f"Meeting summary email sent to {to_email}")
            return True

        except Exception as e:
            logger.error(f"Failed to send meeting summary email: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

"""
Email Integration Service
Handles email sending with SMTP and templates
"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from typing import Dict, Any, Optional, List
from datetime import datetime
import logging
from app.models.integration import EmailCredentials
from app.services.integrations.template_renderer import TemplateRenderer

logger = logging.getLogger(__name__)


class EmailService:
    """Email SMTP integration service"""

    def __init__(self, credentials: EmailCredentials):
        """Initialize Email service with SMTP credentials"""
        self.smtp_host = credentials.smtp_host
        self.smtp_port = credentials.smtp_port
        self.smtp_username = credentials.smtp_username
        self.smtp_password = credentials.smtp_password
        self.from_email = credentials.from_email
        self.from_name = credentials.from_name or credentials.from_email
        self.use_tls = credentials.use_tls

    def _get_smtp_connection(self):
        """Create SMTP connection"""
        try:
            if self.use_tls:
                server = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=30)
                server.starttls()
            else:
                server = smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, timeout=30)

            server.login(self.smtp_username, self.smtp_password)
            return server

        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"SMTP authentication failed: {e}")
            raise Exception(f"Email authentication failed: Invalid credentials")
        except smtplib.SMTPException as e:
            logger.error(f"SMTP error: {e}")
            raise Exception(f"Email server error: {str(e)}")
        except Exception as e:
            logger.error(f"Email connection error: {e}")
            raise Exception(f"Failed to connect to email server: {str(e)}")

    def test_connection(self) -> Dict[str, Any]:
        """Test email connection and credentials"""
        try:
            server = self._get_smtp_connection()
            server.quit()
            return {
                "success": True,
                "message": "Successfully connected to email server"
            }
        except Exception as e:
            return {
                "success": False,
                "message": str(e)
            }

    def send_email(
        self,
        config: Dict[str, Any],
        context_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Send an email

        Args:
            config: Email configuration with to, subject, body, etc.
            context_data: Data for template rendering

        Returns:
            Send result
        """
        try:
            # Render recipient(s)
            to_email = TemplateRenderer.render(
                config.get("to", ""),
                context_data
            )

            if not to_email:
                return {
                    "success": False,
                    "error": "Recipient email is required",
                    "message": "Recipient email address is required"
                }

            # Support multiple recipients
            if isinstance(to_email, str):
                to_emails = [e.strip() for e in to_email.split(",")]
            else:
                to_emails = to_email

            # Render subject
            subject = TemplateRenderer.render(
                config.get("subject", "Notification"),
                context_data
            )

            # Render body
            body = TemplateRenderer.render(
                config.get("body", ""),
                context_data
            )

            # Get email format (html or plain)
            email_format = config.get("format", "html")

            # Create message
            msg = MIMEMultipart("alternative")
            msg["From"] = f"{self.from_name} <{self.from_email}>"
            msg["To"] = ", ".join(to_emails)
            msg["Subject"] = subject

            # Add CC if specified
            cc_emails = []
            if "cc" in config:
                cc = TemplateRenderer.render(config["cc"], context_data)
                if isinstance(cc, str):
                    cc_emails = [e.strip() for e in cc.split(",")]
                else:
                    cc_emails = cc
                msg["Cc"] = ", ".join(cc_emails)

            # Add BCC if specified
            bcc_emails = []
            if "bcc" in config:
                bcc = TemplateRenderer.render(config["bcc"], context_data)
                if isinstance(bcc, str):
                    bcc_emails = [e.strip() for e in bcc.split(",")]
                else:
                    bcc_emails = bcc

            # Attach body
            if email_format == "html":
                # For HTML emails, also include plain text version
                plain_body = self._html_to_plain(body)
                msg.attach(MIMEText(plain_body, "plain"))
                msg.attach(MIMEText(body, "html"))
            else:
                msg.attach(MIMEText(body, "plain"))

            # Add attachments if specified
            if "attachments" in config:
                # This would handle file attachments
                # For now, we'll skip actual file handling
                pass

            # Send email
            logger.info(f"Sending email to {to_emails}")
            server = self._get_smtp_connection()

            # Combine all recipients
            all_recipients = to_emails + cc_emails + bcc_emails

            server.sendmail(
                self.from_email,
                all_recipients,
                msg.as_string()
            )
            server.quit()

            return {
                "success": True,
                "to": to_emails,
                "subject": subject,
                "message": f"Email sent to {', '.join(to_emails)}"
            }

        except Exception as e:
            logger.error(f"Error sending email: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": f"Failed to send email: {str(e)}"
            }

    def _html_to_plain(self, html: str) -> str:
        """
        Convert HTML to plain text (simple version)
        For production, consider using library like html2text
        """
        import re

        # Remove HTML tags
        text = re.sub(r'<[^>]+>', '', html)

        # Replace HTML entities
        text = text.replace('&nbsp;', ' ')
        text = text.replace('&amp;', '&')
        text = text.replace('&lt;', '<')
        text = text.replace('&gt;', '>')
        text = text.replace('&quot;', '"')
        text = text.replace('&#39;', "'")

        # Replace <br> with newlines
        text = text.replace('<br>', '\n').replace('<br/>', '\n').replace('<br />', '\n')

        # Clean up whitespace
        text = '\n'.join(line.strip() for line in text.split('\n'))

        return text

    def send_template_email(
        self,
        template_name: str,
        config: Dict[str, Any],
        context_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Send email using a predefined template

        Args:
            template_name: Name of the email template
            config: Email configuration
            context_data: Data for template rendering
        """
        # Get template from database or file system
        # For now, we'll use inline templates
        templates = {
            "call_completed": {
                "subject": "Call Completed: {{customer.name}}",
                "body": """
                <html>
                <body>
                    <h2>Call Completed</h2>
                    <p><strong>Customer:</strong> {{customer.name}}</p>
                    <p><strong>Phone:</strong> {{customer.phone}}</p>
                    <p><strong>Duration:</strong> {{call.duration|round:0}} seconds</p>
                    <p><strong>Status:</strong> {{call.status|upper}}</p>

                    <h3>Call Summary</h3>
                    <p>{{call.summary|default:No summary available}}</p>

                    <h3>Transcript</h3>
                    <pre>{{call.transcription|truncate:500}}</pre>

                    <p>---<br>
                    Sent from Convis AI Call System</p>
                </body>
                </html>
                """
            },
            "jira_ticket_created": {
                "subject": "Jira Ticket Created: {{jira.ticket_key}}",
                "body": """
                <html>
                <body>
                    <h2>Jira Ticket Created</h2>
                    <p>A new Jira ticket has been created for your recent call.</p>

                    <p><strong>Ticket:</strong> <a href="{{jira.url}}">{{jira.ticket_key}}</a></p>
                    <p><strong>Summary:</strong> {{jira.summary}}</p>

                    <h3>Call Details</h3>
                    <p><strong>Customer:</strong> {{customer.name}}</p>
                    <p><strong>Duration:</strong> {{call.duration|round:0}} seconds</p>
                    <p><strong>Date:</strong> {{call.created_at|datetime}}</p>

                    <p>---<br>
                    Sent from Convis AI Call System</p>
                </body>
                </html>
                """
            },
            "workflow_error": {
                "subject": "Workflow Error: {{workflow.name}}",
                "body": """
                <html>
                <body>
                    <h2>Workflow Execution Error</h2>
                    <p>An error occurred while executing workflow: <strong>{{workflow.name}}</strong></p>

                    <p><strong>Error:</strong> {{error.message}}</p>
                    <p><strong>Action:</strong> {{error.action}}</p>
                    <p><strong>Time:</strong> {{error.timestamp|datetime}}</p>

                    <p>Please check your workflow configuration and integration settings.</p>

                    <p>---<br>
                    Sent from Convis AI Call System</p>
                </body>
                </html>
                """
            }
        }

        template = templates.get(template_name)
        if not template:
            return {
                "success": False,
                "error": f"Template '{template_name}' not found",
                "message": f"Email template '{template_name}' not found"
            }

        # Merge template with config
        email_config = {
            **config,
            "subject": config.get("subject", template["subject"]),
            "body": config.get("body", template["body"])
        }

        return self.send_email(email_config, context_data)

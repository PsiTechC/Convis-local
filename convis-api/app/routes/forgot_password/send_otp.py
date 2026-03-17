from fastapi import APIRouter, HTTPException, status
from app.models.forgot_password import SendOTP, SendOTPResponse
from app.config.database import Database
from app.utils.otp import generate_otp
from app.config.settings import settings
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/send-otp", response_model=SendOTPResponse, status_code=status.HTTP_200_OK)
async def send_otp(otp_data: SendOTP):
    """
    Send OTP to user's email for password reset

    Args:
        otp_data: Email address to send OTP to

    Returns:
        SendOTPResponse: Success message

    Raises:
        HTTPException: If user not found, email fails, or internal error occurs
    """
    try:
        # Get database connection
        db = Database.get_db()
        users_collection = db['users']

        logger.info(f"OTP request for email: {otp_data.email}")

        # Find user by email
        user = users_collection.find_one({"email": otp_data.email})

        if not user:
            logger.warning(f"User not found for email: {otp_data.email}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        # Generate OTP
        otp = generate_otp()
        logger.info(f"Generated OTP for {otp_data.email}: {otp}")

        # Update user with OTP
        users_collection.update_one(
            {"email": otp_data.email},
            {"$set": {"otp": otp}}
        )
        logger.info(f"OTP saved in DB for {otp_data.email}")

        # Send OTP email
        try:
            # Create message
            message = MIMEMultipart('alternative')
            message['Subject'] = 'Convis Labs Password Reset OTP'
            message['From'] = settings.email_user
            message['To'] = otp_data.email

            # HTML body
            html_body = f"""
            <p>Hello,</p>
            <p>Your OTP for password reset is: <strong>{otp}</strong></p>
            <p>This OTP is valid for a short time only. If you didn't request this, please ignore this email.</p>
            """

            html_part = MIMEText(html_body, 'html')
            message.attach(html_part)

            # Connect to SMTP server
            logger.info("Connecting to SMTP server...")
            if settings.smtp_use_ssl and settings.smtp_port == 465:
                # Use SMTP_SSL for port 465
                with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port) as server:
                    server.login(settings.email_user, settings.email_pass)
                    server.send_message(message)
            else:
                # Use SMTP with STARTTLS for port 587
                with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
                    server.starttls()
                    server.login(settings.email_user, settings.email_pass)
                    server.send_message(message)

            logger.info(f"OTP email sent successfully to {otp_data.email}")

        except Exception as email_error:
            logger.error(f"Failed to send OTP email: {str(email_error)}")
            # Don't fail the request if email fails - OTP is already saved
            logger.warning("OTP saved in DB but email failed to send")

        return SendOTPResponse(message="OTP sent to email.")

    except HTTPException:
        raise
    except Exception as error:
        import traceback
        logger.error(f"Error sending OTP: {str(error)}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send OTP: {str(error)}"
        )

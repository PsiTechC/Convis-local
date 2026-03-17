"""
Email Settings endpoints for AI Assistants
Handles SMTP configuration, testing, and email template management
"""
from fastapi import APIRouter, HTTPException, status, Depends, UploadFile, File
from app.models.ai_assistant import SmtpTestRequest, SmtpTestResponse, SendTestEmailRequest
from app.config.database import Database
from app.utils.auth import get_current_user
from app.services.appointment_email_service import (
    appointment_email_service,
    encrypt_password,
    decrypt_password,
    TEMPLATE_VARIABLES,
    get_default_html_template,
    get_default_text_template
)
from bson import ObjectId
from datetime import datetime
import os
import base64
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

# Upload directory for email logos
LOGO_UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "../../../uploads/email_logos")
os.makedirs(LOGO_UPLOAD_DIR, exist_ok=True)

ALLOWED_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}
MAX_LOGO_SIZE = 2 * 1024 * 1024  # 2MB


@router.get("/{assistant_id}/email-settings")
async def get_email_settings(
    assistant_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get email settings for an AI assistant
    Returns SMTP config (password masked), email template, and attachments
    """
    try:
        db = Database.get_db()
        assistants_collection = db['assistants']

        # Validate and fetch assistant
        try:
            assistant_obj_id = ObjectId(assistant_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid assistant_id format")

        assistant = assistants_collection.find_one({"_id": assistant_obj_id})
        if not assistant:
            raise HTTPException(status_code=404, detail="AI assistant not found")

        # Verify ownership
        if str(assistant.get('user_id')) != str(current_user.get('_id')):
            raise HTTPException(status_code=403, detail="Not authorized")

        # Get SMTP config with masked password
        smtp_config = assistant.get('smtp_config', {})
        if smtp_config.get('smtp_password'):
            smtp_config = {**smtp_config, 'smtp_password': '********'}

        # Get email template
        email_template = assistant.get('email_template', {})

        # Get attachments
        attachments = assistant.get('email_attachments', [])
        formatted_attachments = []
        for att in attachments:
            uploaded_at = att.get('uploaded_at')
            if isinstance(uploaded_at, datetime):
                uploaded_at = uploaded_at.isoformat() + "Z"
            formatted_attachments.append({
                "filename": att.get('filename'),
                "original_filename": att.get('original_filename', att.get('filename')),
                "file_type": att.get('file_type'),
                "file_size": att.get('file_size'),
                "uploaded_at": uploaded_at
            })

        return {
            "email_enabled": assistant.get('email_enabled', False),
            "smtp_config": smtp_config,
            "email_template": email_template,
            "attachments": formatted_attachments,
            "available_variables": TEMPLATE_VARIABLES,
            "default_html_template": get_default_html_template(),
            "default_text_template": get_default_text_template()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting email settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{assistant_id}/email-settings")
async def update_email_settings(
    assistant_id: str,
    settings: dict,
    current_user: dict = Depends(get_current_user)
):
    """
    Update email settings for an AI assistant
    Handles SMTP config and email template
    """
    try:
        db = Database.get_db()
        assistants_collection = db['assistants']

        # Validate and fetch assistant
        try:
            assistant_obj_id = ObjectId(assistant_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid assistant_id format")

        assistant = assistants_collection.find_one({"_id": assistant_obj_id})
        if not assistant:
            raise HTTPException(status_code=404, detail="AI assistant not found")

        # Verify ownership
        if str(assistant.get('user_id')) != str(current_user.get('_id')):
            raise HTTPException(status_code=403, detail="Not authorized")

        update_fields = {"updated_at": datetime.utcnow()}

        # Handle email_enabled
        if 'email_enabled' in settings:
            update_fields['email_enabled'] = bool(settings['email_enabled'])

        # Handle SMTP config
        if 'smtp_config' in settings:
            smtp_config = settings['smtp_config']

            # Encrypt password if it's a new password (not the masked one)
            if smtp_config.get('smtp_password') and smtp_config['smtp_password'] != '********':
                smtp_config['smtp_password'] = encrypt_password(smtp_config['smtp_password'])
            elif smtp_config.get('smtp_password') == '********':
                # Keep existing password
                existing_smtp = assistant.get('smtp_config', {})
                smtp_config['smtp_password'] = existing_smtp.get('smtp_password', '')

            update_fields['smtp_config'] = smtp_config

        # Handle email template
        if 'email_template' in settings:
            update_fields['email_template'] = settings['email_template']

        # Update database
        assistants_collection.update_one(
            {"_id": assistant_obj_id},
            {"$set": update_fields}
        )

        logger.info(f"Email settings updated for assistant {assistant_id}")
        return {"message": "Email settings updated successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating email settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{assistant_id}/email-settings/test-smtp")
async def test_smtp_connection(
    assistant_id: str,
    test_request: SmtpTestRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Test SMTP connection by sending a test email
    """
    try:
        db = Database.get_db()
        assistants_collection = db['assistants']

        # Validate and fetch assistant
        try:
            assistant_obj_id = ObjectId(assistant_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid assistant_id format")

        assistant = assistants_collection.find_one({"_id": assistant_obj_id})
        if not assistant:
            raise HTTPException(status_code=404, detail="AI assistant not found")

        # Verify ownership
        if str(assistant.get('user_id')) != str(current_user.get('_id')):
            raise HTTPException(status_code=403, detail="Not authorized")

        # Build SMTP config for testing
        smtp_config = {
            "enabled": True,
            "sender_email": test_request.sender_email,
            "sender_name": test_request.sender_name,
            "smtp_host": test_request.smtp_host,
            "smtp_port": test_request.smtp_port,
            "smtp_username": test_request.smtp_username,
            "smtp_password": encrypt_password(test_request.smtp_password),  # Encrypt for the test
            "use_tls": test_request.use_tls,
            "use_ssl": test_request.use_ssl
        }

        # Send test email
        result = await appointment_email_service.test_smtp_connection(
            smtp_config=smtp_config,
            test_recipient=test_request.test_recipient
        )

        if result['success']:
            return SmtpTestResponse(
                success=True,
                message=f"Test email sent successfully to {test_request.test_recipient}"
            )
        else:
            return SmtpTestResponse(
                success=False,
                message=result.get('error', 'Failed to send test email')
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error testing SMTP: {e}")
        return SmtpTestResponse(success=False, message=str(e))


@router.post("/{assistant_id}/email-settings/send-test")
async def send_test_email_with_template(
    assistant_id: str,
    test_request: SendTestEmailRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Send a test email using the saved template and SMTP settings
    Uses sample data for template variables
    """
    try:
        db = Database.get_db()
        assistants_collection = db['assistants']
        users_collection = db['users']

        # Validate and fetch assistant
        try:
            assistant_obj_id = ObjectId(assistant_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid assistant_id format")

        assistant = assistants_collection.find_one({"_id": assistant_obj_id})
        if not assistant:
            raise HTTPException(status_code=404, detail="AI assistant not found")

        # Verify ownership
        if str(assistant.get('user_id')) != str(current_user.get('_id')):
            raise HTTPException(status_code=403, detail="Not authorized")

        # Check if SMTP is configured
        smtp_config = assistant.get('smtp_config', {})
        if not smtp_config.get('enabled'):
            raise HTTPException(status_code=400, detail="SMTP is not enabled for this assistant")

        # Get user for company name
        user = users_collection.find_one({"_id": ObjectId(assistant.get('user_id'))})

        # Create sample appointment data
        sample_appointment = {
            "customer_name": "John Doe (Sample)",
            "customer_email": test_request.test_recipient,
            "customer_phone": "+1 555-123-4567",
            "start_time": datetime.utcnow().replace(hour=14, minute=30).isoformat(),
            "end_time": datetime.utcnow().replace(hour=15, minute=0).isoformat(),
            "title": "Sample Consultation Meeting",
            "timezone": "America/New_York",
            "duration_minutes": 30,
            "location": "Conference Room A",
            "meeting_link": "https://meet.example.com/sample-meeting"
        }

        # Send test email
        result = await appointment_email_service.send_appointment_confirmation(
            assistant_id=assistant_id,
            appointment_data=sample_appointment,
            call_sid="TEST-" + datetime.utcnow().strftime("%Y%m%d%H%M%S")
        )

        if result['success']:
            return {
                "success": True,
                "message": f"Test email sent successfully to {test_request.test_recipient}"
            }
        else:
            return {
                "success": False,
                "message": result.get('error', 'Failed to send test email')
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending test email: {e}")
        return {"success": False, "message": str(e)}


@router.post("/{assistant_id}/email-settings/upload-logo")
async def upload_email_logo(
    assistant_id: str,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Upload a logo image for email header
    """
    try:
        db = Database.get_db()
        assistants_collection = db['assistants']

        # Validate and fetch assistant
        try:
            assistant_obj_id = ObjectId(assistant_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid assistant_id format")

        assistant = assistants_collection.find_one({"_id": assistant_obj_id})
        if not assistant:
            raise HTTPException(status_code=404, detail="AI assistant not found")

        # Verify ownership
        if str(assistant.get('user_id')) != str(current_user.get('_id')):
            raise HTTPException(status_code=403, detail="Not authorized")

        # Validate file
        file_ext = os.path.splitext(file.filename)[1].lower()
        if file_ext not in ALLOWED_IMAGE_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"File type not supported. Allowed: {', '.join(ALLOWED_IMAGE_EXTENSIONS)}"
            )

        content = await file.read()
        if len(content) > MAX_LOGO_SIZE:
            raise HTTPException(status_code=400, detail="Logo file too large. Maximum 2MB.")

        # Save file
        assistant_dir = os.path.join(LOGO_UPLOAD_DIR, str(assistant_id))
        os.makedirs(assistant_dir, exist_ok=True)

        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_logo{file_ext}"
        file_path = os.path.join(assistant_dir, filename)

        with open(file_path, 'wb') as f:
            f.write(content)

        # Convert to base64 for embedding in emails
        content_type = f"image/{file_ext.replace('.', '')}"
        if file_ext == '.jpg':
            content_type = "image/jpeg"

        base64_data = base64.b64encode(content).decode('utf-8')
        logo_data_url = f"data:{content_type};base64,{base64_data}"

        # Update assistant's email template with logo
        email_template = assistant.get('email_template', {})
        email_template['logo_url'] = logo_data_url
        email_template['logo_file_path'] = file_path

        assistants_collection.update_one(
            {"_id": assistant_obj_id},
            {
                "$set": {
                    "email_template": email_template,
                    "updated_at": datetime.utcnow()
                }
            }
        )

        return {
            "message": "Logo uploaded successfully",
            "logo_url": logo_data_url
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading logo: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{assistant_id}/email-logs")
async def get_email_logs(
    assistant_id: str,
    limit: int = 50,
    skip: int = 0,
    current_user: dict = Depends(get_current_user)
):
    """
    Get email sending logs for an AI assistant
    """
    try:
        db = Database.get_db()
        assistants_collection = db['assistants']
        email_logs_collection = db['email_logs']

        # Validate and fetch assistant
        try:
            assistant_obj_id = ObjectId(assistant_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid assistant_id format")

        assistant = assistants_collection.find_one({"_id": assistant_obj_id})
        if not assistant:
            raise HTTPException(status_code=404, detail="AI assistant not found")

        # Verify ownership
        if str(assistant.get('user_id')) != str(current_user.get('_id')):
            raise HTTPException(status_code=403, detail="Not authorized")

        # Get logs
        cursor = email_logs_collection.find(
            {"assistant_id": assistant_id}
        ).sort("sent_at", -1).skip(skip).limit(limit)

        logs = []
        for log in cursor:
            sent_at = log.get('sent_at')
            if isinstance(sent_at, datetime):
                sent_at = sent_at.isoformat() + "Z"

            logs.append({
                "id": str(log.get('_id')),
                "recipient_email": log.get('recipient_email'),
                "recipient_name": log.get('recipient_name'),
                "subject": log.get('subject'),
                "status": log.get('status'),
                "error_message": log.get('error_message'),
                "sent_at": sent_at,
                "call_sid": log.get('call_sid'),
                "appointment_id": log.get('appointment_id')
            })

        # Get total count
        total = email_logs_collection.count_documents({"assistant_id": assistant_id})

        return {
            "logs": logs,
            "total": total,
            "limit": limit,
            "skip": skip
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting email logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))

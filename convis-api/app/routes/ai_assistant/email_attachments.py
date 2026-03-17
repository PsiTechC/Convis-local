"""
Email Attachments endpoints for AI Assistants
Handles uploading, listing, and deleting email attachments that will be sent with appointment confirmations
"""
from fastapi import APIRouter, HTTPException, status, UploadFile, File, Depends
from app.models.ai_assistant import EmailAttachment, EmailAttachmentUploadResponse, DeleteResponse
from app.config.database import Database
from app.utils.auth import get_current_user
from bson import ObjectId
from datetime import datetime
import os
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

# Base directory for email attachments
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "../../../uploads/email_attachments")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Allowed file types for email attachments
ALLOWED_EXTENSIONS = {'.pdf', '.docx', '.doc', '.xlsx', '.xls', '.pptx', '.ppt', '.txt', '.png', '.jpg', '.jpeg', '.gif'}
MAX_FILE_SIZE = 25 * 1024 * 1024  # 25MB - email attachment size limit
MAX_ATTACHMENTS_PER_ASSISTANT = 10  # Limit attachments per assistant


def get_file_extension(filename: str) -> str:
    """Get file extension from filename"""
    return os.path.splitext(filename)[1].lower()


def get_mime_type(extension: str) -> str:
    """Get MIME type from file extension"""
    mime_types = {
        '.pdf': 'application/pdf',
        '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        '.doc': 'application/msword',
        '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        '.xls': 'application/vnd.ms-excel',
        '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
        '.ppt': 'application/vnd.ms-powerpoint',
        '.txt': 'text/plain',
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.gif': 'image/gif',
    }
    return mime_types.get(extension, 'application/octet-stream')


@router.post("/{assistant_id}/email-attachments/upload", response_model=EmailAttachmentUploadResponse, status_code=status.HTTP_200_OK)
async def upload_email_attachment(
    assistant_id: str,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Upload an email attachment for an AI assistant
    These attachments will be included in appointment confirmation emails

    Args:
        assistant_id: AI Assistant ID
        file: Uploaded file (PDF, DOCX, images, etc.)

    Returns:
        EmailAttachmentUploadResponse: Upload status and file info
    """
    try:
        db = Database.get_db()
        assistants_collection = db['assistants']

        logger.info(f"Uploading email attachment {file.filename} for assistant {assistant_id}")

        # Validate assistant_id
        try:
            assistant_obj_id = ObjectId(assistant_id)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid assistant_id format"
            )

        # Fetch assistant and verify ownership
        assistant = assistants_collection.find_one({"_id": assistant_obj_id})
        if not assistant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="AI assistant not found"
            )

        # Verify user owns this assistant
        if str(assistant.get('user_id')) != str(current_user.get('_id')):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to modify this assistant"
            )

        # Check attachment count limit
        existing_attachments = assistant.get('email_attachments', [])
        if len(existing_attachments) >= MAX_ATTACHMENTS_PER_ASSISTANT:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Maximum {MAX_ATTACHMENTS_PER_ASSISTANT} attachments allowed per assistant"
            )

        # Validate file extension
        file_ext = get_file_extension(file.filename)
        if file_ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File type not supported. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
            )

        # Read file content
        content = await file.read()
        file_size = len(content)

        # Check file size
        if file_size > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File too large. Maximum size: {MAX_FILE_SIZE // (1024*1024)}MB"
            )

        # Check total attachments size (max 50MB total)
        total_existing_size = sum(att.get('file_size', 0) for att in existing_attachments)
        if total_existing_size + file_size > 50 * 1024 * 1024:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Total attachments size exceeds 50MB limit"
            )

        # Create assistant-specific directory
        assistant_dir = os.path.join(UPLOAD_DIR, str(assistant_id))
        os.makedirs(assistant_dir, exist_ok=True)

        # Generate unique filename
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        # Sanitize original filename
        safe_original = "".join(c for c in file.filename if c.isalnum() or c in '.-_')
        safe_filename = f"{timestamp}_{safe_original}"
        file_path = os.path.join(assistant_dir, safe_filename)

        # Save file
        with open(file_path, 'wb') as f:
            f.write(content)

        logger.info(f"Email attachment saved to {file_path}")

        # Store file metadata
        file_metadata = {
            "filename": safe_filename,
            "original_filename": file.filename,
            "file_type": file_ext.replace('.', ''),
            "file_size": file_size,
            "uploaded_at": datetime.utcnow(),
            "file_path": file_path,
            "mime_type": get_mime_type(file_ext)
        }

        # Update assistant document
        assistants_collection.update_one(
            {"_id": assistant_obj_id},
            {
                "$push": {"email_attachments": file_metadata},
                "$set": {"updated_at": datetime.utcnow()}
            }
        )

        logger.info(f"Successfully uploaded email attachment {file.filename}")

        # Get total attachments count
        updated_assistant = assistants_collection.find_one({"_id": assistant_obj_id})
        total_attachments = len(updated_assistant.get('email_attachments', []))

        return EmailAttachmentUploadResponse(
            message=f"Attachment '{file.filename}' uploaded successfully",
            attachment=EmailAttachment(
                filename=safe_filename,
                original_filename=file.filename,
                file_type=file_ext.replace('.', ''),
                file_size=file_size,
                uploaded_at=file_metadata['uploaded_at'].isoformat() + "Z",
                file_path=file_path
            ),
            total_attachments=total_attachments
        )

    except HTTPException:
        raise
    except Exception as error:
        import traceback
        logger.error(f"Error uploading email attachment: {str(error)}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload attachment: {str(error)}"
        )


@router.get("/{assistant_id}/email-attachments", status_code=status.HTTP_200_OK)
async def list_email_attachments(
    assistant_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    List all email attachments for an AI assistant

    Args:
        assistant_id: AI Assistant ID

    Returns:
        List of email attachments
    """
    try:
        db = Database.get_db()
        assistants_collection = db['assistants']

        # Validate assistant_id
        try:
            assistant_obj_id = ObjectId(assistant_id)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid assistant_id format"
            )

        # Fetch assistant
        assistant = assistants_collection.find_one({"_id": assistant_obj_id})
        if not assistant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="AI assistant not found"
            )

        # Verify user owns this assistant
        if str(assistant.get('user_id')) != str(current_user.get('_id')):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to view this assistant"
            )

        attachments = assistant.get('email_attachments', [])

        # Format response
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
                "uploaded_at": uploaded_at,
                "mime_type": att.get('mime_type', 'application/octet-stream')
            })

        return {
            "attachments": formatted_attachments,
            "total": len(formatted_attachments)
        }

    except HTTPException:
        raise
    except Exception as error:
        import traceback
        logger.error(f"Error listing email attachments: {str(error)}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list attachments: {str(error)}"
        )


@router.delete("/{assistant_id}/email-attachments/{filename}", response_model=DeleteResponse, status_code=status.HTTP_200_OK)
async def delete_email_attachment(
    assistant_id: str,
    filename: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Delete an email attachment from an AI assistant

    Args:
        assistant_id: AI Assistant ID
        filename: Name of the file to delete

    Returns:
        DeleteResponse: Deletion status
    """
    try:
        db = Database.get_db()
        assistants_collection = db['assistants']

        logger.info(f"Deleting email attachment {filename} from assistant {assistant_id}")

        # Validate assistant_id
        try:
            assistant_obj_id = ObjectId(assistant_id)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid assistant_id format"
            )

        # Fetch assistant
        assistant = assistants_collection.find_one({"_id": assistant_obj_id})
        if not assistant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="AI assistant not found"
            )

        # Verify user owns this assistant
        if str(assistant.get('user_id')) != str(current_user.get('_id')):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to modify this assistant"
            )

        # Find file in attachments
        attachments = assistant.get('email_attachments', [])
        file_to_delete = None
        for att in attachments:
            if att['filename'] == filename:
                file_to_delete = att
                break

        if not file_to_delete:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Attachment not found"
            )

        # Delete physical file
        file_path = file_to_delete.get('file_path')
        if file_path and os.path.exists(file_path):
            os.remove(file_path)

        # Remove file metadata from database
        assistants_collection.update_one(
            {"_id": assistant_obj_id},
            {
                "$pull": {"email_attachments": {"filename": filename}},
                "$set": {"updated_at": datetime.utcnow()}
            }
        )

        logger.info(f"Successfully deleted email attachment {filename}")

        original_filename = file_to_delete.get('original_filename', filename)
        return DeleteResponse(message=f"Attachment '{original_filename}' deleted successfully")

    except HTTPException:
        raise
    except Exception as error:
        import traceback
        logger.error(f"Error deleting email attachment: {str(error)}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete attachment: {str(error)}"
        )

"""
WhatsApp Credentials Routes
Handles CRUD operations for WhatsApp Business credentials
"""

from fastapi import APIRouter, HTTPException, Depends, status
from typing import List
from datetime import datetime
from bson import ObjectId

from app.models.whatsapp import (
    WhatsAppCredentialCreate,
    WhatsAppCredentialUpdate,
    WhatsAppCredentialResponse,
    WhatsAppConnectionTest,
    WhatsAppConnectionTestResponse
)
from app.config.database import Database
from app.utils.auth import get_current_user
from app.utils.encryption import encryption_service
from app.services.whatsapp_service import WhatsAppService

router = APIRouter()


def format_credential_response(doc: dict) -> WhatsAppCredentialResponse:
    """Format MongoDB document to response model"""
    return WhatsAppCredentialResponse(
        id=str(doc["_id"]),
        user_id=str(doc["user_id"]),
        label=doc["label"],
        last_four=doc["last_four"],
        api_url_masked=doc.get("api_url_masked", "railway.app"),
        status=doc.get("status", "active"),
        created_at=doc["created_at"].isoformat() if isinstance(doc["created_at"], datetime) else doc["created_at"],
        updated_at=doc.get("updated_at").isoformat() if doc.get("updated_at") and isinstance(doc.get("updated_at"), datetime) else None
    )


@router.post("/test-connection", response_model=WhatsAppConnectionTestResponse)
async def test_whatsapp_connection(
    payload: WhatsAppConnectionTest,
    current_user: dict = Depends(get_current_user)
):
    """
    Test Railway WhatsApp API connection before saving credentials
    """
    try:
        whatsapp_service = WhatsAppService(
            api_key=payload.api_key,
            bearer_token=payload.bearer_token,
            base_url=payload.api_url or "https://whatsapp-api-backend-production.up.railway.app"
        )

        result = await whatsapp_service.test_connection()

        if result.get("success"):
            return WhatsAppConnectionTestResponse(
                success=True,
                message="Connection successful! Railway WhatsApp API is accessible.",
                templates_count=result.get("templates_count"),
                api_accessible=True
            )
        else:
            return WhatsAppConnectionTestResponse(
                success=False,
                message=f"Connection failed: {result.get('error', 'Unknown error')}",
                api_accessible=False
            )

    except Exception as e:
        return WhatsAppConnectionTestResponse(
            success=False,
            message=f"Connection test failed: {str(e)}",
            api_accessible=False
        )


@router.post("/credentials", response_model=WhatsAppCredentialResponse, status_code=status.HTTP_201_CREATED)
async def create_whatsapp_credential(
    payload: WhatsAppCredentialCreate,
    current_user: dict = Depends(get_current_user)
):
    """
    Save Railway WhatsApp API credentials for a user
    """
    db = Database.get_db()
    credentials_collection = db["whatsapp_credentials"]

    user_id = current_user.get("user_id") or str(current_user.get("_id"))

    # Test connection first
    try:
        whatsapp_service = WhatsAppService(
            api_key=payload.api_key,
            bearer_token=payload.bearer_token,
            base_url=payload.api_url or "https://whatsapp-api-backend-production.up.railway.app"
        )
        connection_test = await whatsapp_service.test_connection()

        if not connection_test.get("success"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid credentials: {connection_test.get('error', 'Connection failed')}"
            )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to verify credentials: {str(e)}"
        )

    # Encrypt sensitive data
    encrypted_api_key = encryption_service.encrypt(payload.api_key)
    encrypted_bearer_token = encryption_service.encrypt(payload.bearer_token)

    # Get last 4 characters for display
    last_four = payload.api_key[-4:] if len(payload.api_key) >= 4 else "****"

    # Mask API URL
    api_url = payload.api_url or "https://whatsapp-api-backend-production.up.railway.app"
    api_url_masked = "railway.app" if "railway" in api_url.lower() else "custom"

    doc = {
        "user_id": ObjectId(user_id),
        "label": payload.label,
        "api_key": encrypted_api_key,
        "bearer_token": encrypted_bearer_token,
        "api_url": api_url,
        "last_four": last_four,
        "api_url_masked": api_url_masked,
        "status": "active",
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }

    result = credentials_collection.insert_one(doc)
    doc["_id"] = result.inserted_id

    return format_credential_response(doc)


@router.get("/credentials", response_model=List[WhatsAppCredentialResponse])
async def get_whatsapp_credentials(
    current_user: dict = Depends(get_current_user)
):
    """
    Get all WhatsApp credentials for the authenticated user
    """
    db = Database.get_db()
    credentials_collection = db["whatsapp_credentials"]

    user_id = current_user.get("user_id") or str(current_user.get("_id"))

    credentials = credentials_collection.find(
        {"user_id": ObjectId(user_id)}
    ).sort("created_at", -1)

    return [format_credential_response(doc) for doc in credentials]


@router.get("/credentials/{credential_id}", response_model=WhatsAppCredentialResponse)
async def get_whatsapp_credential(
    credential_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get a specific WhatsApp credential by ID
    """
    db = Database.get_db()
    credentials_collection = db["whatsapp_credentials"]

    user_id = current_user.get("user_id") or str(current_user.get("_id"))

    try:
        credential = credentials_collection.find_one({
            "_id": ObjectId(credential_id),
            "user_id": ObjectId(user_id)
        })
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid credential ID format"
        )

    if not credential:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Credential not found"
        )

    return format_credential_response(credential)


@router.put("/credentials/{credential_id}", response_model=WhatsAppCredentialResponse)
async def update_whatsapp_credential(
    credential_id: str,
    payload: WhatsAppCredentialUpdate,
    current_user: dict = Depends(get_current_user)
):
    """
    Update WhatsApp credential
    """
    db = Database.get_db()
    credentials_collection = db["whatsapp_credentials"]

    user_id = current_user.get("user_id") or str(current_user.get("_id"))

    try:
        credential = credentials_collection.find_one({
            "_id": ObjectId(credential_id),
            "user_id": ObjectId(user_id)
        })
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid credential ID format"
        )

    if not credential:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Credential not found"
        )

    update_data = {}

    if payload.label:
        update_data["label"] = payload.label

    if payload.bearer_token:
        update_data["bearer_token"] = encryption_service.encrypt(payload.bearer_token)

    if payload.api_key:
        update_data["api_key"] = encryption_service.encrypt(payload.api_key)
        update_data["last_four"] = payload.api_key[-4:] if len(payload.api_key) >= 4 else "****"

    if payload.api_url:
        update_data["api_url"] = payload.api_url
        update_data["api_url_masked"] = "railway.app" if "railway" in payload.api_url.lower() else "custom"

    update_data["updated_at"] = datetime.utcnow()

    credentials_collection.update_one(
        {"_id": ObjectId(credential_id)},
        {"$set": update_data}
    )

    updated_credential = credentials_collection.find_one({"_id": ObjectId(credential_id)})
    return format_credential_response(updated_credential)


@router.delete("/credentials/{credential_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_whatsapp_credential(
    credential_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Delete WhatsApp credential
    """
    db = Database.get_db()
    credentials_collection = db["whatsapp_credentials"]

    user_id = current_user.get("user_id") or str(current_user.get("_id"))

    try:
        result = credentials_collection.delete_one({
            "_id": ObjectId(credential_id),
            "user_id": ObjectId(user_id)
        })
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid credential ID format"
        )

    if result.deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Credential not found"
        )

    return None


@router.post("/credentials/{credential_id}/verify", response_model=WhatsAppConnectionTestResponse)
async def verify_whatsapp_credential(
    credential_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Verify that a saved WhatsApp credential is still valid
    """
    db = Database.get_db()
    credentials_collection = db["whatsapp_credentials"]

    user_id = current_user.get("user_id") or str(current_user.get("_id"))

    try:
        credential = credentials_collection.find_one({
            "_id": ObjectId(credential_id),
            "user_id": ObjectId(user_id)
        })
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid credential ID format"
        )

    if not credential:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Credential not found"
        )

    # Decrypt credentials
    api_key = encryption_service.decrypt(credential["api_key"])
    bearer_token = encryption_service.decrypt(credential["bearer_token"])
    api_url = credential.get("api_url", "https://whatsapp-api-backend-production.up.railway.app")

    # Test connection
    try:
        whatsapp_service = WhatsAppService(
            api_key=api_key,
            bearer_token=bearer_token,
            base_url=api_url
        )

        result = await whatsapp_service.test_connection()

        if result.get("success"):
            # Update status to active
            credentials_collection.update_one(
                {"_id": ObjectId(credential_id)},
                {"$set": {"status": "active", "updated_at": datetime.utcnow()}}
            )

            return WhatsAppConnectionTestResponse(
                success=True,
                message="Credential is valid and active",
                templates_count=result.get("templates_count"),
                api_accessible=True
            )
        else:
            # Update status to error
            credentials_collection.update_one(
                {"_id": ObjectId(credential_id)},
                {"$set": {"status": "error", "updated_at": datetime.utcnow()}}
            )

            return WhatsAppConnectionTestResponse(
                success=False,
                message=f"Credential verification failed: {result.get('error')}",
                api_accessible=False
            )

    except Exception as e:
        credentials_collection.update_one(
            {"_id": ObjectId(credential_id)},
            {"$set": {"status": "error", "updated_at": datetime.utcnow()}}
        )

        return WhatsAppConnectionTestResponse(
            success=False,
            message=f"Verification failed: {str(e)}",
            api_accessible=False
        )

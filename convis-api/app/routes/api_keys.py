from fastapi import APIRouter, HTTPException, status
from bson import ObjectId
from datetime import datetime
from typing import Optional, Dict, Any
from app.config.database import Database
from app.models.api_key import APIKeyCreate, APIKeyUpdate, APIKeyResponse, APIKeyListResponse, AllowedProvider
from app.utils.encryption import encryption_service
import logging

logger = logging.getLogger(__name__)


router = APIRouter()

ALLOWED_PROVIDERS: Dict[AllowedProvider, str] = {
    'openai': 'OpenAI',
    'anthropic': 'Anthropic',
    'azure_openai': 'Azure OpenAI',
    'google': 'Google Vertex',
    'custom': 'Custom'
}


def format_api_key_response(doc: Dict[str, Any]) -> APIKeyResponse:
    return APIKeyResponse(
        id=str(doc['_id']),
        user_id=str(doc['user_id']),
        provider=doc['provider'],
        label=doc['label'],
        description=doc.get('description'),
        last_four=doc.get('last_four', '****'),
        created_at=doc['created_at'].isoformat() + "Z",
        updated_at=doc['updated_at'].isoformat() + "Z",
    )


def validate_user_id(user_id: str) -> ObjectId:
    try:
        return ObjectId(user_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid user_id format"
        )


@router.post("/", response_model=APIKeyResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(payload: APIKeyCreate):
    """Create a new AI provider API key for a user."""
    try:
        db = Database.get_db()
        users_collection = db['users']
        keys_collection = db['api_keys']

        user_obj_id = validate_user_id(payload.user_id)

        # Ensure user exists
        if not users_collection.find_one({"_id": user_obj_id}):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        now = datetime.utcnow()
        encrypted_key = encryption_service.encrypt(payload.api_key)
        last_four = payload.api_key[-4:] if len(payload.api_key) >= 4 else payload.api_key

        doc = {
            "user_id": user_obj_id,
            "provider": payload.provider,
            "label": payload.label.strip(),
            "description": payload.description.strip() if payload.description else None,
            "key": encrypted_key,
            "last_four": last_four,
            "created_at": now,
            "updated_at": now,
        }

        result = keys_collection.insert_one(doc)
        logger.info(f"Created API key {result.inserted_id} for user {payload.user_id}")

        doc['_id'] = result.inserted_id
        return format_api_key_response(doc)

    except HTTPException:
        raise
    except Exception as error:
        import traceback
        logger.error(f"Error creating API key: {error}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create API key")


@router.get("/user/{user_id}", response_model=APIKeyListResponse, status_code=status.HTTP_200_OK)
async def list_user_api_keys(user_id: str):
    """Return all API keys saved by a user."""
    try:
        db = Database.get_db()
        keys_collection = db['api_keys']

        user_obj_id = validate_user_id(user_id)

        docs = list(keys_collection.find({"user_id": user_obj_id}).sort("created_at", -1))
        return APIKeyListResponse(
            keys=[format_api_key_response(doc) for doc in docs],
            total=len(docs)
        )
    except HTTPException:
        raise
    except Exception as error:
        import traceback
        logger.error(f"Error fetching API keys for user {user_id}: {error}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch API keys")


def get_api_key_doc(keys_collection, key_id: str) -> Dict[str, Any]:
    try:
        key_obj_id = ObjectId(key_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid key_id format")

    doc = keys_collection.find_one({"_id": key_obj_id})
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    return doc


@router.put("/{key_id}", response_model=APIKeyResponse, status_code=status.HTTP_200_OK)
async def update_api_key(key_id: str, payload: APIKeyUpdate):
    """Update label/provider/api-key contents."""
    try:
        db = Database.get_db()
        keys_collection = db['api_keys']

        existing = get_api_key_doc(keys_collection, key_id)
        update_doc: Dict[str, Any] = {}

        if payload.label is not None:
            update_doc['label'] = payload.label.strip()
        if payload.provider is not None:
            update_doc['provider'] = payload.provider
        if payload.description is not None:
            update_doc['description'] = payload.description.strip() if payload.description else None
        if payload.api_key is not None:
            encrypted_key = encryption_service.encrypt(payload.api_key)
            update_doc['key'] = encrypted_key
            update_doc['last_four'] = payload.api_key[-4:] if len(payload.api_key) >= 4 else payload.api_key

        if not update_doc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields provided to update")

        update_doc['updated_at'] = datetime.utcnow()
        keys_collection.update_one({"_id": existing['_id']}, {"$set": update_doc})

        refreshed = keys_collection.find_one({"_id": existing['_id']})
        return format_api_key_response(refreshed)
    except HTTPException:
        raise
    except Exception as error:
        import traceback
        logger.error(f"Error updating API key {key_id}: {error}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update API key")


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_api_key(key_id: str):
    """Delete a stored API key if it's not assigned to any assistants."""
    try:
        db = Database.get_db()
        keys_collection = db['api_keys']
        assistants_collection = db['assistants']

        doc = get_api_key_doc(keys_collection, key_id)

        # Prevent deletion if key is in use
        in_use = assistants_collection.count_documents({"api_key_id": doc['_id']})
        if in_use:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete key while it is assigned to AI assistants"
            )

        keys_collection.delete_one({"_id": doc['_id']})
        logger.info(f"Deleted API key {key_id}")
        return None
    except HTTPException:
        raise
    except Exception as error:
        import traceback
        logger.error(f"Error deleting API key {key_id}: {error}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to delete API key")

import logging
import os
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urlencode

import httpx
import jwt
from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query, status, Depends
from fastapi.responses import RedirectResponse

from app.config.database import Database
from app.config.settings import settings
from app.services.calendar_service import CalendarService
from app.utils.auth import get_current_user, verify_user_ownership
from app.utils.encryption import encryption_service

logger = logging.getLogger(__name__)

router = APIRouter()

SUPPORTED_PROVIDERS = {"google", "microsoft"}
STATE_TTL_SECONDS = 600


def _get_api_origin() -> str:
    explicit = settings.api_base_url or settings.base_url or os.getenv("API_BASE_URL")
    if explicit:
        return explicit.rstrip("/")
    # Fallback to production URL
    return "https://api.convis.ai"


def _encode_state(user_id: str, provider: str) -> str:
    payload = {
        "user_id": user_id,
        "provider": provider,
        "exp": datetime.utcnow() + timedelta(seconds=STATE_TTL_SECONDS),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def _decode_state(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired OAuth state") from exc


def _validate_provider(provider: str) -> str:
    normalized = provider.lower()
    if normalized not in SUPPORTED_PROVIDERS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported provider")
    return normalized


def _serialize_account(doc: dict) -> dict:
    def _iso(value: Optional[datetime]) -> Optional[str]:
        return value.isoformat() if isinstance(value, datetime) else None

    return {
        "id": str(doc.get("_id")),
        "provider": doc.get("provider"),
        "email": doc.get("email"),
        "created_at": _iso(doc.get("created_at")),
        "updated_at": _iso(doc.get("updated_at")),
    }


async def _exchange_google_token(code: str, redirect_uri: str) -> dict:
    client_id = settings.google_client_id
    client_secret = settings.google_client_secret
    if not client_id or not client_secret:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Google credentials not configured")

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json()


async def _exchange_microsoft_token(code: str, redirect_uri: str) -> dict:
    client_id = settings.microsoft_client_id
    client_secret = settings.microsoft_client_secret
    if not client_id or not client_secret:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Microsoft credentials not configured")

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://login.microsoftonline.com/common/oauth2/v2.0/token",
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
                "scope": "offline_access Calendars.Read Calendars.ReadWrite User.Read",
            },
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json()


async def _fetch_google_profile(access_token: str) -> dict:
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json()


async def _fetch_microsoft_profile(access_token: str) -> dict:
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://graph.microsoft.com/v1.0/me",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json()


@router.get("/accounts/{user_id}")
async def list_calendar_accounts(user_id: str, current_user: dict = Depends(get_current_user)):
    # Verify user owns this resource
    await verify_user_ownership(current_user, user_id)

    try:
        user_obj_id = ObjectId(user_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid user_id format")

    db = Database.get_db()
    accounts_collection = db["calendar_accounts"]
    docs = list(accounts_collection.find({"user_id": user_obj_id}).sort("provider", 1))
    return {"accounts": [_serialize_account(doc) for doc in docs], "total": len(docs)}


@router.delete("/accounts/{account_id}")
async def delete_calendar_account(account_id: str, current_user: dict = Depends(get_current_user)):
    try:
        account_obj_id = ObjectId(account_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid account_id format")

    db = Database.get_db()
    accounts_collection = db["calendar_accounts"]

    # First, verify the account exists and belongs to the current user
    account = accounts_collection.find_one({"_id": account_obj_id})
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Calendar account not found")

    # Verify ownership
    account_user_id = str(account.get("user_id"))
    await verify_user_ownership(current_user, account_user_id)

    # Delete the account
    result = accounts_collection.delete_one({"_id": account_obj_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Calendar account not found")

    logger.info(f"User {current_user['user_id']} disconnected calendar account {account_id}")
    return {"message": "Calendar disconnected"}


@router.get("/{provider}/auth-url")
async def get_auth_url(provider: str, user_id: str, current_user: dict = Depends(get_current_user)):
    normalized_provider = _validate_provider(provider)

    # Verify user owns this resource
    await verify_user_ownership(current_user, user_id)

    try:
        user_obj_id = ObjectId(user_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid user_id format")

    db = Database.get_db()
    users_collection = db["users"]
    if not users_collection.find_one({"_id": user_obj_id}):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    base_origin = _get_api_origin()
    redirect_uri = f"{base_origin}/api/calendar/{normalized_provider}/callback"
    state_token = _encode_state(user_id, normalized_provider)

    if normalized_provider == "google":
        client_id = settings.google_client_id
        if not client_id:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Google client ID missing")
        params = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": "https://www.googleapis.com/auth/calendar.readonly https://www.googleapis.com/auth/calendar.events https://www.googleapis.com/auth/userinfo.email https://www.googleapis.com/auth/userinfo.profile",
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
            "state": state_token,
        }
        auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
    else:
        client_id = settings.microsoft_client_id
        if not client_id:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Microsoft client ID missing")
        params = {
            "client_id": client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "response_mode": "query",
            "scope": "offline_access Calendars.Read Calendars.ReadWrite User.Read",
            "state": state_token,
        }
        auth_url = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize?" + urlencode(params)

    return {"auth_url": auth_url}


@router.get("/{provider}/callback")
async def oauth_callback(provider: str, code: str = Query(...), state: str = Query(...)):
    normalized_provider = _validate_provider(provider)
    payload = _decode_state(state)
    if payload.get("provider") != normalized_provider:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Mismatched OAuth state")

    user_id = payload.get("user_id")
    try:
        user_obj_id = ObjectId(user_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid user in OAuth state")

    redirect_target = f"{settings.frontend_url.rstrip('/')}/connect-calendar"

    base_origin = _get_api_origin()
    redirect_uri = f"{base_origin}/api/calendar/{normalized_provider}/callback"

    try:
        if normalized_provider == "google":
            token_data = await _exchange_google_token(code, redirect_uri)
            profile = await _fetch_google_profile(token_data.get("access_token"))
            email = profile.get("email") or profile.get("name")
        else:
            token_data = await _exchange_microsoft_token(code, redirect_uri)
            profile = await _fetch_microsoft_profile(token_data.get("access_token"))
            email = profile.get("mail") or profile.get("userPrincipalName") or profile.get("displayName")

        refresh_token = token_data.get("refresh_token")
        access_token = token_data.get("access_token")
        expires_in = token_data.get("expires_in", 3600)

        db = Database.get_db()
        accounts_collection = db["calendar_accounts"]
        now = datetime.utcnow()
        existing = accounts_collection.find_one({"user_id": user_obj_id, "provider": normalized_provider})
        if existing and not refresh_token:
            refresh_token = (existing.get("oauth") or {}).get("refreshToken")

        # Encrypt tokens before storing
        encrypted_access_token = encryption_service.encrypt(access_token) if access_token else None
        encrypted_refresh_token = encryption_service.encrypt(refresh_token) if refresh_token else None

        accounts_collection.update_one(
            {"user_id": user_obj_id, "provider": normalized_provider},
            {
                "$set": {
                    "email": email,
                    "oauth": {
                        "accessToken": encrypted_access_token,
                        "refreshToken": encrypted_refresh_token,
                        "expiry": datetime.utcnow().timestamp() + expires_in,
                    },
                    "updated_at": now,
                },
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )

        params = urlencode({"status": "success", "provider": normalized_provider})
        return RedirectResponse(url=f"{redirect_target}?{params}", status_code=302)

    except httpx.HTTPError as http_error:
        logger.error("OAuth exchange failed: %s", http_error)
        params = urlencode({"status": "error", "provider": normalized_provider, "message": "OAuth exchange failed"})
        return RedirectResponse(url=f"{redirect_target}?{params}", status_code=302)
    except Exception as exc:
        logger.error("Calendar OAuth callback error: %s", exc)
        params = urlencode({"status": "error", "provider": normalized_provider, "message": "Unable to connect calendar"})
        return RedirectResponse(url=f"{redirect_target}?{params}", status_code=302)


@router.get("/events/{user_id}")
async def list_calendar_events(
    user_id: str,
    provider: Optional[str] = None,
    limit: int = 10,
    time_min: Optional[str] = Query(None, description="Start of time range (ISO 8601)"),
    time_max: Optional[str] = Query(None, description="End of time range (ISO 8601)"),
    current_user: dict = Depends(get_current_user)
):
    # Verify user owns this resource
    await verify_user_ownership(current_user, user_id)

    try:
        ObjectId(user_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid user_id format")

    normalized_provider = provider.lower() if provider else None
    if normalized_provider and normalized_provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported provider filter")

    limit = max(1, min(limit, 100))  # Increased to 100 for monthly view
    service = CalendarService()
    events = await service.fetch_upcoming_events(user_id, normalized_provider, limit, time_min, time_max)
    return {"events": events}


@router.get("/appointment-details/{event_id}")
async def get_appointment_details(
    event_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get appointment details including call summary, transcript, and recording URL.
    This endpoint retrieves Convis-booked appointments with their associated call data.
    """
    db = Database.get_db()
    appointments_collection = db["appointments"]
    call_logs_collection = db["call_logs"]

    # Try to find appointment by provider_event_id first (for calendar events)
    appointment = appointments_collection.find_one({"provider_event_id": event_id})

    # If not found, try by appointment _id
    if not appointment:
        try:
            appointment = appointments_collection.find_one({"_id": ObjectId(event_id)})
        except Exception:
            pass

    if not appointment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")

    # Verify ownership - appointment should belong to the current user
    appointment_user_id = appointment.get("user_id")
    if appointment_user_id:
        await verify_user_ownership(current_user, str(appointment_user_id))

    # Get call log if we have a call_sid
    call_sid = appointment.get("call_sid")
    call_log = None
    if call_sid:
        call_log = call_logs_collection.find_one({"call_sid": call_sid})

    # Build response with appointment and call details
    response = {
        "id": str(appointment.get("_id")),
        "provider_event_id": appointment.get("provider_event_id"),
        "title": appointment.get("title"),
        "start_time": appointment.get("start_time").isoformat() if isinstance(appointment.get("start_time"), datetime) else appointment.get("start_time"),
        "end_time": appointment.get("end_time").isoformat() if isinstance(appointment.get("end_time"), datetime) else appointment.get("end_time"),
        "timezone": appointment.get("timezone"),
        "location": appointment.get("location"),
        "meeting_link": appointment.get("meeting_link"),
        "customer_name": appointment.get("customer_name"),
        "customer_phone": appointment.get("customer_phone"),
        "customer_email": appointment.get("customer_email"),
        "status": appointment.get("status"),
        "provider": appointment.get("provider"),
        "call_sid": call_sid,
        # Call summary fields from appointment record (updated by post-call processor)
        "call_summary": appointment.get("call_summary"),
        "transcript": appointment.get("transcript"),
        "recording_url": appointment.get("recording_url"),
        "call_duration": appointment.get("call_duration"),
    }

    # If call log exists, supplement with more details
    if call_log:
        if not response.get("call_summary"):
            response["call_summary"] = call_log.get("summary")
        if not response.get("transcript"):
            response["transcript"] = call_log.get("transcript")
        if not response.get("recording_url"):
            response["recording_url"] = call_log.get("recording_url")
        if not response.get("call_duration"):
            response["call_duration"] = call_log.get("duration")
        # Additional call details
        response["sentiment"] = call_log.get("sentiment")
        response["sentiment_score"] = call_log.get("sentiment_score")
        response["call_status"] = call_log.get("status")
        response["from_number"] = call_log.get("from_number")
        response["to_number"] = call_log.get("to_number")

    return response

"""
Calendar integration service for Google Calendar and Microsoft Calendar
"""
import logging
import os
from datetime import datetime
from typing import Optional, Dict, Any, List
import httpx
from bson import ObjectId

from app.config.database import Database
from app.utils.encryption import encryption_service

logger = logging.getLogger(__name__)


class CalendarService:
    """Service for calendar operations"""

    def __init__(self):
        self.db = Database.get_db()
        self.calendar_accounts_collection = self.db["calendar_accounts"]
        self.appointments_collection = self.db["appointments"]
        self.leads_collection = self.db["leads"]

    def _decrypt_token(self, encrypted_token: str) -> str:
        """Decrypt OAuth token."""
        try:
            return encryption_service.decrypt(encrypted_token)
        except Exception as e:
            logger.error(f"Error decrypting token: {e}")
            # If decryption fails, might be plain text (backwards compatibility)
            return encrypted_token

    async def _handle_token_error(self, account: Dict[str, Any], error: Exception) -> None:
        """Handle token-related errors, including revoked tokens."""
        error_str = str(error).lower()

        # Check for token revocation errors
        if any(keyword in error_str for keyword in ["invalid_grant", "token_revoked", "invalid_token", "unauthorized"]):
            logger.warning(f"OAuth token revoked or invalid for account {account.get('_id')}. Marking account as invalid.")

            # Mark account as requiring re-authorization
            self.calendar_accounts_collection.update_one(
                {"_id": account["_id"]},
                {
                    "$set": {
                        "oauth.is_valid": False,
                        "oauth.error": "Token revoked or invalid. Please reconnect your calendar.",
                        "updated_at": datetime.utcnow()
                    }
                }
            )
        else:
            logger.error(f"Token error for account {account.get('_id')}: {error}")

    async def get_calendar_account(self, user_id: str, provider: str = "google") -> Optional[Dict[str, Any]]:
        """
        Get calendar account for a user.

        Args:
            user_id: User ID
            provider: "google" or "microsoft"

        Returns:
            Calendar account document or None
        """
        try:
            account = self.calendar_accounts_collection.find_one({
                "user_id": ObjectId(user_id),
                "provider": provider
            })
            return account
        except Exception as e:
            logger.error(f"Error getting calendar account: {e}")
            return None

    async def get_calendar_account_by_id(self, calendar_account_id: str) -> Optional[Dict[str, Any]]:
        """
        Get calendar account by ID.

        Args:
            calendar_account_id: Calendar account ID (ObjectId string)

        Returns:
            Calendar account document or None
        """
        try:
            account = self.calendar_accounts_collection.find_one({
                "_id": ObjectId(calendar_account_id)
            })
            return account
        except Exception as e:
            logger.error(f"Error getting calendar account by ID: {e}")
            return None

    async def refresh_access_token(self, account: Dict[str, Any]) -> Optional[str]:
        """
        Refresh OAuth access token.

        Args:
            account: Calendar account document

        Returns:
            New access token or None
        """
        try:
            oauth_data = account.get("oauth", {})
            encrypted_refresh_token = oauth_data.get("refreshToken")
            provider = account.get("provider")

            if not encrypted_refresh_token:
                logger.error("No refresh token available")
                return None

            # Decrypt refresh token
            refresh_token = self._decrypt_token(encrypted_refresh_token)

            if provider == "google":
                # Google OAuth token refresh
                client_id = oauth_data.get("clientId") or os.getenv("GOOGLE_CLIENT_ID")
                client_secret = oauth_data.get("clientSecret") or os.getenv("GOOGLE_CLIENT_SECRET")

                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        "https://oauth2.googleapis.com/token",
                        data={
                            "client_id": client_id,
                            "client_secret": client_secret,
                            "refresh_token": refresh_token,
                            "grant_type": "refresh_token"
                        }
                    )
                    response.raise_for_status()
                    data = response.json()
                    new_access_token = data.get("access_token")

                    # Encrypt new access token before storing
                    encrypted_access_token = encryption_service.encrypt(new_access_token)

                    # Update stored token
                    self.calendar_accounts_collection.update_one(
                        {"_id": account["_id"]},
                        {
                            "$set": {
                                "oauth.accessToken": encrypted_access_token,
                                "oauth.expiry": datetime.utcnow().timestamp() + data.get("expires_in", 3600),
                                "updated_at": datetime.utcnow()
                            }
                        }
                    )

                    return new_access_token

            elif provider == "microsoft":
                # Microsoft OAuth token refresh
                client_id = oauth_data.get("clientId") or os.getenv("MICROSOFT_CLIENT_ID")
                client_secret = oauth_data.get("clientSecret") or os.getenv("MICROSOFT_CLIENT_SECRET")

                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        "https://login.microsoftonline.com/common/oauth2/v2.0/token",
                        data={
                            "client_id": client_id,
                            "client_secret": client_secret,
                            "refresh_token": refresh_token,
                            "grant_type": "refresh_token",
                            "scope": "Calendars.ReadWrite"
                        }
                    )
                    response.raise_for_status()
                    data = response.json()
                    new_access_token = data.get("access_token")

                    # Encrypt new access token before storing
                    encrypted_access_token = encryption_service.encrypt(new_access_token)

                    # Update stored token
                    self.calendar_accounts_collection.update_one(
                        {"_id": account["_id"]},
                        {
                            "$set": {
                                "oauth.accessToken": encrypted_access_token,
                                "oauth.expiry": datetime.utcnow().timestamp() + data.get("expires_in", 3600),
                                "updated_at": datetime.utcnow()
                            }
                        }
                    )

                    return new_access_token

        except httpx.HTTPStatusError as e:
            # Handle HTTP errors (including revoked tokens)
            await self._handle_token_error(account, e)
            return None
        except Exception as e:
            logger.error(f"Error refreshing access token: {e}")
            return None

    async def ensure_access_token(self, account: Dict[str, Any]) -> Optional[str]:
        """Return a valid access token, refreshing it if needed."""
        try:
            oauth_data = account.get("oauth", {})
            encrypted_access_token = oauth_data.get("accessToken")
            expiry = oauth_data.get("expiry", 0)

            if not encrypted_access_token:
                return None

            # Decrypt access token
            access_token = self._decrypt_token(encrypted_access_token)

            # Refresh token if it expires within the next minute
            if datetime.utcnow().timestamp() >= expiry - 60:
                logger.info("Access token expiring soon; refreshing for account %s", account.get("_id"))
                refreshed = await self.refresh_access_token(account)
                if refreshed:
                    access_token = refreshed
            return access_token
        except Exception as exc:
            logger.error(f"Failed to ensure access token: {exc}")
            return None

    async def create_google_event(self, access_token: str, event_data: Dict[str, Any]) -> Optional[str]:
        """
        Create Google Calendar event.

        Args:
            access_token: Google access token
            event_data: Event data with title, start, end, timezone

        Returns:
            Event ID or None
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://www.googleapis.com/calendar/v3/calendars/primary/events",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "summary": event_data.get("title", "Meeting"),
                        "start": {
                            "dateTime": event_data.get("start_iso"),
                            "timeZone": event_data.get("timezone", "America/New_York")
                        },
                        "end": {
                            "dateTime": event_data.get("end_iso"),
                            "timeZone": event_data.get("timezone", "America/New_York")
                        },
                        "description": event_data.get("notes", "")
                    },
                    timeout=30.0
                )
                if response.status_code != 200:
                    error_detail = response.text
                    logger.error(f"Google Calendar API error: {response.status_code} - {error_detail}")
                    logger.error(f"Event data sent: {event_data}")
                    return None

                result = response.json()
                event_id = result.get("id")
                logger.info(f"Google event created successfully: {event_id}")
                logger.info(f"Event details - Title: {event_data.get('title')}, Start: {event_data.get('start_iso')}, End: {event_data.get('end_iso')}")
                return event_id

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error creating Google event: {e.response.status_code} - {e.response.text}")
            logger.error(f"Event data that failed: {event_data}")
            return None
        except Exception as e:
            logger.error(f"Error creating Google event: {e}")
            logger.error(f"Event data: {event_data}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    async def create_microsoft_event(self, access_token: str, event_data: Dict[str, Any]) -> Optional[str]:
        """
        Create Microsoft Calendar event.

        Args:
            access_token: Microsoft access token
            event_data: Event data with title, start, end, timezone

        Returns:
            Event ID or None
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://graph.microsoft.com/v1.0/me/events",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "subject": event_data.get("title", "Meeting"),
                        "start": {
                            "dateTime": event_data.get("start_iso"),
                            "timeZone": event_data.get("timezone", "America/New_York")
                        },
                        "end": {
                            "dateTime": event_data.get("end_iso"),
                            "timeZone": event_data.get("timezone", "America/New_York")
                        },
                        "body": {
                            "contentType": "Text",
                            "content": event_data.get("notes", "")
                        }
                    },
                    timeout=30.0
                )
                response.raise_for_status()
                result = response.json()
                event_id = result.get("id")
                logger.info(f"Microsoft event created: {event_id}")
                return event_id

        except Exception as e:
            logger.error(f"Error creating Microsoft event: {e}")
            return None

    async def fetch_google_events(self, access_token: str, max_events: int = 10, account: Optional[Dict[str, Any]] = None, time_min: Optional[str] = None, time_max: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch Google Calendar events. If time_min/time_max not provided, fetches upcoming events."""
        try:
            # Default to upcoming events if no time range specified
            if not time_min:
                time_min = datetime.utcnow().isoformat() + "Z"

            params = {
                "timeMin": time_min,
                "maxResults": max_events,
                "singleEvents": True,
                "orderBy": "startTime",
            }

            # Add time_max if provided
            if time_max:
                params["timeMax"] = time_max

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://www.googleapis.com/calendar/v3/calendars/primary/events",
                    headers={"Authorization": f"Bearer {access_token}"},
                    params=params,
                    timeout=30.0,
                )
                response.raise_for_status()
                payload = response.json()
                events: List[Dict[str, Any]] = []
                for item in payload.get("items", []):
                    start = item.get("start", {})
                    end = item.get("end", {})
                    start_iso = start.get("dateTime") or (start.get("date") + "T00:00:00Z" if start.get("date") else None)
                    end_iso = end.get("dateTime") or (end.get("date") + "T00:00:00Z" if end.get("date") else None)
                    events.append({
                        "id": item.get("id"),
                        "title": item.get("summary", "(No title)"),
                        "start": start_iso,
                        "end": end_iso,
                        "location": item.get("location"),
                        "meeting_link": item.get("hangoutLink") or item.get("htmlLink"),
                        "organizer": item.get("organizer", {}).get("email"),
                    })
                return events
        except httpx.HTTPStatusError as exc:
            if account:
                await self._handle_token_error(account, exc)
            logger.error(f"Error fetching Google events: {exc}")
            return []
        except Exception as exc:
            logger.error(f"Error fetching Google events: {exc}")
            return []

    async def fetch_microsoft_events(self, access_token: str, max_events: int = 10, account: Optional[Dict[str, Any]] = None, time_min: Optional[str] = None, time_max: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch Microsoft (Outlook/Teams) calendar events. If time_min/time_max not provided, fetches upcoming events."""
        try:
            params = {
                "$top": max_events,
                "$orderby": "start/dateTime",
                "$select": "id,subject,start,end,location,onlineMeetingUrl,organizer,webLink",
            }

            # Add time filtering if provided
            filters = []
            if time_min:
                filters.append(f"start/dateTime ge '{time_min}'")
            if time_max:
                filters.append(f"start/dateTime lt '{time_max}'")

            if filters:
                params["$filter"] = " and ".join(filters)

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://graph.microsoft.com/v1.0/me/events",
                    headers={"Authorization": f"Bearer {access_token}"},
                    params=params,
                    timeout=30.0,
                )
                response.raise_for_status()
                payload = response.json()
                events: List[Dict[str, Any]] = []
                for item in payload.get("value", []):
                    start = item.get("start", {})
                    end = item.get("end", {})
                    events.append({
                        "id": item.get("id"),
                        "title": item.get("subject", "(No title)"),
                        "start": start.get("dateTime"),
                        "end": end.get("dateTime"),
                        "timezone": start.get("timeZone"),
                        "location": (item.get("location") or {}).get("displayName"),
                        "meeting_link": item.get("onlineMeetingUrl") or item.get("webLink"),
                        "organizer": ((item.get("organizer") or {}).get("emailAddress") or {}).get("address"),
                    })
                return events
        except httpx.HTTPStatusError as exc:
            if account:
                await self._handle_token_error(account, exc)
            logger.error(f"Error fetching Microsoft events: {exc}")
            return []
        except Exception as exc:
            logger.error(f"Error fetching Microsoft events: {exc}")
            return []

    async def fetch_upcoming_events(self, user_id: str, provider: Optional[str] = None, max_events: int = 10, time_min: Optional[str] = None, time_max: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return aggregated events for the given user. Supports date range filtering."""
        try:
            query: Dict[str, Any] = {"user_id": ObjectId(user_id)}
            if provider:
                query["provider"] = provider

            accounts = list(self.calendar_accounts_collection.find(query))
            events: List[Dict[str, Any]] = []

            for account in accounts:
                # Skip accounts marked as invalid
                if account.get("oauth", {}).get("is_valid") is False:
                    logger.warning("Skipping invalid account %s", account.get("_id"))
                    continue

                token = await self.ensure_access_token(account)
                if not token:
                    logger.warning("No valid access token for account %s", account.get("_id"))
                    continue

                provider_name = account.get("provider")
                provider_events: List[Dict[str, Any]] = []

                if provider_name == "google":
                    provider_events = await self.fetch_google_events(token, max_events, account, time_min, time_max)
                elif provider_name == "microsoft":
                    provider_events = await self.fetch_microsoft_events(token, max_events, account, time_min, time_max)

                for event in provider_events:
                    event["provider"] = provider_name
                    event["account_email"] = account.get("email")
                events.extend(provider_events)

            # Sort by start datetime when available
            events.sort(key=lambda evt: evt.get("start") or "")
            return events[:max_events]
        except Exception as exc:
            logger.error(f"Error fetching upcoming events: {exc}")
            return []

    async def book_appointment(self, lead_id: str, campaign_id: str, appointment_data: Dict[str, Any], provider: str = "google", calendar_account_id_override: Optional[str] = None) -> Optional[str]:
        """
        Book an appointment for a lead using the campaign's assigned calendar account.

        Args:
            lead_id: Lead ID
            campaign_id: Campaign ID
            appointment_data: Appointment details from AI analysis
            provider: "google" or "microsoft" (deprecated - uses campaign's assigned calendar)
            calendar_account_id_override: Override calendar account ID (optional, takes priority)

        Returns:
            Provider event ID if created, otherwise None.
        """
        try:
            # Get campaign to find user_id and calendar_account_id
            campaigns_collection = self.db["campaigns"]
            campaign = campaigns_collection.find_one({"_id": ObjectId(campaign_id)})
            if not campaign:
                logger.error(f"Campaign {campaign_id} not found")
                return

            user_id = str(campaign["user_id"])

            # Priority: override > campaign calendar > fallback to user's first calendar
            calendar_account_id = calendar_account_id_override or campaign.get("calendar_account_id")

            # Get the calendar account
            if calendar_account_id:
                account = self.calendar_accounts_collection.find_one({"_id": ObjectId(calendar_account_id) if isinstance(calendar_account_id, str) else calendar_account_id})
                if not account:
                    logger.error(f"Calendar account {calendar_account_id} not found")
                    return
                provider = account.get("provider", "google")
                source = "override" if calendar_account_id_override else "campaign"
                logger.info(f"Using {source} calendar account {calendar_account_id} ({provider}) for campaign {campaign_id}")
            else:
                # Fallback to first available calendar account for the user
                logger.warning(f"No calendar account assigned to campaign {campaign_id}, using first available for user {user_id}")
                account = await self.get_calendar_account(user_id, provider)
                if not account:
                    logger.warning(f"No calendar account available for user {user_id}")
                    return

            # Get access token (refresh if needed) - use ensure_access_token for decryption and refresh
            access_token = await self.ensure_access_token(account)
            if not access_token:
                logger.error("Failed to get valid access token")
                return None

            # Create calendar event
            event_id = None
            if provider == "google":
                event_id = await self.create_google_event(access_token, appointment_data)
            elif provider == "microsoft":
                event_id = await self.create_microsoft_event(access_token, appointment_data)

            if not event_id:
                logger.error("Failed to create calendar event")
                return None

            # Save appointment record
            appointment_doc = {
                "user_id": ObjectId(user_id),
                "lead_id": ObjectId(lead_id),
                "campaign_id": ObjectId(campaign_id),
                "provider": provider,
                "provider_event_id": event_id,
                "title": appointment_data.get("title", "Meeting"),
                "start_time": datetime.fromisoformat(appointment_data.get("start_iso")),
                "end_time": datetime.fromisoformat(appointment_data.get("end_iso")),
                "timezone": appointment_data.get("timezone", "America/New_York"),
                "duration_minutes": appointment_data.get("duration_minutes", 30),
                # Customer contact info for email confirmations
                "customer_name": appointment_data.get("attendee_name") or appointment_data.get("customer_name"),
                "customer_email": appointment_data.get("attendee_email") or appointment_data.get("customer_email"),
                "customer_phone": appointment_data.get("attendee_phone") or appointment_data.get("customer_phone"),
                "notes": appointment_data.get("notes"),
                "meeting_link": appointment_data.get("hangout_link") or appointment_data.get("meeting_link"),
                "location": appointment_data.get("location"),
                "status": "confirmed",
                "created_at": datetime.utcnow()
            }

            self.appointments_collection.insert_one(appointment_doc)

            # Update lead
            self.leads_collection.update_one(
                {"_id": ObjectId(lead_id)},
                {"$set": {"calendar_booked": True, "updated_at": datetime.utcnow()}}
            )

            logger.info(f"Appointment booked for lead {lead_id}: {event_id}")
            return event_id

        except Exception as e:
            logger.error(f"Error booking appointment: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    async def check_availability_across_calendars(
        self,
        calendar_account_ids: List[str],
        start_time: datetime,
        end_time: datetime
    ) -> Dict[str, Any]:
        """
        Check availability across multiple calendars.

        Args:
            calendar_account_ids: List of calendar account IDs to check
            start_time: Start time of the requested slot
            end_time: End time of the requested slot

        Returns:
            Dict with:
                - is_available: bool - True if ALL calendars are free
                - conflicts: List of calendars with conflicts
        """
        try:
            conflicts = []

            # Convert times to ISO format for API calls
            time_min = start_time.isoformat() + "Z"
            time_max = end_time.isoformat() + "Z"

            for cal_id in calendar_account_ids:
                account = await self.get_calendar_account_by_id(cal_id)
                if not account:
                    logger.warning(f"Calendar account {cal_id} not found, skipping")
                    continue

                # Skip invalid accounts
                if account.get("oauth", {}).get("is_valid") is False:
                    logger.warning(f"Calendar account {cal_id} is invalid, skipping")
                    continue

                token = await self.ensure_access_token(account)
                if not token:
                    logger.warning(f"No valid token for calendar {cal_id}, skipping")
                    continue

                # Fetch events in the requested time range
                provider = account.get("provider")
                events = []

                if provider == "google":
                    events = await self.fetch_google_events(token, max_events=50, account=account, time_min=time_min, time_max=time_max)
                elif provider == "microsoft":
                    events = await self.fetch_microsoft_events(token, max_events=50, account=account, time_min=time_min, time_max=time_max)

                # Check if any events overlap with requested time
                conflicting_events = []
                for event in events:
                    event_start = datetime.fromisoformat(event.get("start", "").replace("Z", "+00:00"))
                    event_end = datetime.fromisoformat(event.get("end", "").replace("Z", "+00:00"))

                    # Check for overlap
                    if not (event_end <= start_time or event_start >= end_time):
                        conflicting_events.append({
                            "title": event.get("title"),
                            "start": event.get("start"),
                            "end": event.get("end")
                        })

                if conflicting_events:
                    conflicts.append({
                        "calendar_id": cal_id,
                        "calendar_email": account.get("email"),
                        "provider": provider,
                        "conflicting_events": conflicting_events
                    })

            return {
                "is_available": len(conflicts) == 0,
                "conflicts": conflicts
            }

        except Exception as e:
            logger.error(f"Error checking availability across calendars: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                "is_available": False,
                "conflicts": [],
                "error": str(e)
            }

    async def get_next_available_calendar_round_robin(
        self,
        assistant: Dict[str, Any],
        start_time: datetime,
        end_time: datetime
    ) -> Optional[str]:
        """
        Get next available calendar using round-robin scheduling.

        Args:
            assistant: Assistant document with calendar_account_ids and last_calendar_used_index
            start_time: Appointment start time
            end_time: Appointment end time

        Returns:
            calendar_account_id of available calendar or None if all busy
        """
        try:
            calendar_ids = assistant.get("calendar_account_ids", [])
            if not calendar_ids:
                logger.warning("No calendar accounts configured for assistant")
                return None

            last_used_index = assistant.get("last_calendar_used_index", -1)
            num_calendars = len(calendar_ids)

            # Try each calendar starting from the next one in round-robin order
            for i in range(num_calendars):
                # Calculate round-robin index
                current_index = (last_used_index + 1 + i) % num_calendars
                calendar_id = calendar_ids[current_index]

                # Check if this calendar is available
                availability = await self.check_availability_across_calendars(
                    [calendar_id],
                    start_time,
                    end_time
                )

                if availability.get("is_available"):
                    # Update the assistant's last_used_index
                    assistants_collection = self.db["assistants"]
                    assistants_collection.update_one(
                        {"_id": assistant["_id"]},
                        {"$set": {"last_calendar_used_index": current_index}}
                    )
                    logger.info(f"Selected calendar {calendar_id} (index {current_index}) via round-robin")
                    return calendar_id

            logger.warning("All calendars are busy for the requested time slot")
            return None

        except Exception as e:
            logger.error(f"Error in round-robin calendar selection: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    async def update_event(self, user_id: str, provider: str, event_id: str, event_data: Dict[str, Any]) -> bool:
        """
        Update a calendar event (for rescheduling).

        Args:
            user_id: User ID
            provider: "google" or "microsoft"
            event_id: Event ID to update
            event_data: New event data with start_iso, end_iso, timezone

        Returns:
            True if updated successfully, False otherwise
        """
        try:
            # Get calendar account
            account = await self.get_calendar_account(user_id, provider)
            if not account:
                logger.error(f"No {provider} calendar account for user {user_id}")
                return False

            # Get access token
            access_token = await self.ensure_access_token(account)
            if not access_token:
                logger.error("Failed to get valid access token")
                return False

            # Update event based on provider
            if provider == "google":
                async with httpx.AsyncClient() as client:
                    response = await client.patch(
                        f"https://www.googleapis.com/calendar/v3/calendars/primary/events/{event_id}",
                        headers={
                            "Authorization": f"Bearer {access_token}",
                            "Content-Type": "application/json"
                        },
                        json={
                            "start": {
                                "dateTime": event_data.get("start_iso"),
                                "timeZone": event_data.get("timezone", "America/New_York")
                            },
                            "end": {
                                "dateTime": event_data.get("end_iso"),
                                "timeZone": event_data.get("timezone", "America/New_York")
                            }
                        },
                        timeout=30.0
                    )
                    if response.status_code == 200:
                        logger.info(f"Google event {event_id} updated successfully")
                        return True
                    else:
                        logger.error(f"Failed to update Google event: {response.status_code} - {response.text}")
                        return False

            elif provider == "microsoft":
                async with httpx.AsyncClient() as client:
                    response = await client.patch(
                        f"https://graph.microsoft.com/v1.0/me/events/{event_id}",
                        headers={
                            "Authorization": f"Bearer {access_token}",
                            "Content-Type": "application/json"
                        },
                        json={
                            "start": {
                                "dateTime": event_data.get("start_iso"),
                                "timeZone": event_data.get("timezone", "America/New_York")
                            },
                            "end": {
                                "dateTime": event_data.get("end_iso"),
                                "timeZone": event_data.get("timezone", "America/New_York")
                            }
                        },
                        timeout=30.0
                    )
                    if response.status_code == 200:
                        logger.info(f"Microsoft event {event_id} updated successfully")
                        return True
                    else:
                        logger.error(f"Failed to update Microsoft event: {response.status_code} - {response.text}")
                        return False

        except Exception as e:
            logger.error(f"Error updating calendar event: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    async def update_event_with_call_summary(
        self,
        call_sid: str,
        call_summary: str,
        transcript: str = None,
        recording_url: str = None,
        call_duration: int = None
    ) -> bool:
        """
        Update a calendar event with call summary after the call ends.
        This is called by the post-call processor.

        Args:
            call_sid: Twilio call SID to find the associated appointment
            call_summary: AI-generated summary of the call
            transcript: Full conversation transcript (optional)
            recording_url: URL to call recording (optional)
            call_duration: Duration of call in seconds (optional)

        Returns:
            True if updated successfully, False otherwise
        """
        try:
            logger.info(f"[CALENDAR_SUMMARY] Updating calendar event for call {call_sid}")

            # Find the appointment record by call_sid
            appointment = self.appointments_collection.find_one({"call_sid": call_sid})
            if not appointment:
                logger.info(f"[CALENDAR_SUMMARY] No appointment found for call {call_sid}")
                return False

            provider = appointment.get("provider", "google")
            event_id = appointment.get("provider_event_id")
            user_id = str(appointment.get("user_id"))

            if not event_id:
                logger.error("[CALENDAR_SUMMARY] No provider_event_id in appointment record")
                return False

            # Get calendar account
            account = await self.get_calendar_account(user_id, provider)
            if not account:
                logger.error(f"[CALENDAR_SUMMARY] No {provider} calendar account for user {user_id}")
                return False

            # Get access token
            access_token = await self.ensure_access_token(account)
            if not access_token:
                logger.error("[CALENDAR_SUMMARY] Failed to get valid access token")
                return False

            # Format the call summary for calendar event description
            frontend_url = os.getenv("FRONTEND_URL", "https://convis.ai")
            call_log_url = f"{frontend_url}/call-logs?call_sid={call_sid}"

            # Build enhanced description with call summary
            duration_str = ""
            if call_duration:
                mins = call_duration // 60
                secs = call_duration % 60
                duration_str = f"\n⏱️ Duration: {mins}m {secs}s"

            description = f"""📞 Call Summary:
{call_summary}
{duration_str}

📋 Key Discussion Points:
{self._extract_key_points(call_summary)}

🔗 View Full Call Details: {call_log_url}
"""

            if recording_url:
                description += f"\n🎙️ Recording: {recording_url}"

            if transcript:
                # Truncate transcript if too long (calendar events have limits)
                truncated_transcript = transcript[:2000] + "..." if len(transcript) > 2000 else transcript
                description += f"\n\n📝 Transcript Preview:\n{truncated_transcript}"

            # Update the calendar event
            if provider == "google":
                async with httpx.AsyncClient() as client:
                    response = await client.patch(
                        f"https://www.googleapis.com/calendar/v3/calendars/primary/events/{event_id}",
                        headers={
                            "Authorization": f"Bearer {access_token}",
                            "Content-Type": "application/json"
                        },
                        json={"description": description},
                        timeout=30.0
                    )
                    if response.status_code == 200:
                        logger.info(f"[CALENDAR_SUMMARY] ✅ Google event {event_id} updated with call summary")
                    else:
                        logger.error(f"[CALENDAR_SUMMARY] Failed to update Google event: {response.status_code}")
                        return False

            elif provider == "microsoft":
                async with httpx.AsyncClient() as client:
                    response = await client.patch(
                        f"https://graph.microsoft.com/v1.0/me/events/{event_id}",
                        headers={
                            "Authorization": f"Bearer {access_token}",
                            "Content-Type": "application/json"
                        },
                        json={"body": {"contentType": "text", "content": description}},
                        timeout=30.0
                    )
                    if response.status_code == 200:
                        logger.info(f"[CALENDAR_SUMMARY] ✅ Microsoft event {event_id} updated with call summary")
                    else:
                        logger.error(f"[CALENDAR_SUMMARY] Failed to update Microsoft event: {response.status_code}")
                        return False

            # Update the appointment record with call summary
            self.appointments_collection.update_one(
                {"call_sid": call_sid},
                {
                    "$set": {
                        "call_summary": call_summary,
                        "transcript": transcript,
                        "recording_url": recording_url,
                        "call_duration": call_duration,
                        "summary_updated_at": datetime.utcnow()
                    }
                }
            )

            logger.info(f"[CALENDAR_SUMMARY] ✅ Appointment record updated with call summary")

            # Send email with call summary
            try:
                from app.services.async_email_service import async_email_service

                # Get user email
                users_collection = self.db["users"]
                user = users_collection.find_one({"_id": ObjectId(user_id)})

                if user and user.get("email"):
                    # Get meeting details from appointment
                    meeting_title = appointment.get("title", "Meeting")
                    meeting_date = appointment.get("start")

                    email_sent = await async_email_service.send_meeting_summary_email(
                        to_email=user.get("email"),
                        meeting_title=meeting_title,
                        call_summary=call_summary,
                        meeting_date=meeting_date,
                        recording_url=recording_url,
                        call_sid=call_sid,
                        attendee_name=user.get("name") or user.get("email").split("@")[0]
                    )

                    if email_sent:
                        logger.info(f"[CALENDAR_SUMMARY] ✅ Call summary email sent to {user.get('email')}")
                    else:
                        logger.warning(f"[CALENDAR_SUMMARY] ⚠️ Failed to send call summary email")
                else:
                    logger.warning(f"[CALENDAR_SUMMARY] ⚠️ No email found for user {user_id}")

            except Exception as e:
                logger.error(f"[CALENDAR_SUMMARY] Error sending summary email: {e}")
                import traceback
                logger.error(traceback.format_exc())
                # Don't fail the whole process if email fails

            return True

        except Exception as e:
            logger.error(f"[CALENDAR_SUMMARY] Error updating calendar event with summary: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    def _extract_key_points(self, summary: str) -> str:
        """Extract or format key points from the call summary."""
        if not summary:
            return "• No summary available"

        # If summary is already bullet points, return as is
        if "•" in summary or "-" in summary:
            return summary

        # Split into sentences and format as bullet points
        sentences = summary.replace(". ", ".\n").split("\n")
        key_points = []
        for s in sentences[:5]:  # Limit to 5 key points
            s = s.strip()
            if s and len(s) > 10:
                key_points.append(f"• {s}")

        return "\n".join(key_points) if key_points else f"• {summary[:200]}"

    async def delete_event(self, user_id: str, provider: str, event_id: str) -> bool:
        """
        Delete a calendar event.

        Args:
            user_id: User ID
            provider: "google" or "microsoft"
            event_id: Event ID to delete

        Returns:
            True if deleted successfully, False otherwise
        """
        try:
            # Get calendar account
            account = await self.get_calendar_account(user_id, provider)
            if not account:
                logger.error(f"No {provider} calendar account for user {user_id}")
                return False

            # Get access token
            access_token = await self.ensure_access_token(account)
            if not access_token:
                logger.error("Failed to get valid access token")
                return False

            # Delete event based on provider
            if provider == "google":
                async with httpx.AsyncClient() as client:
                    response = await client.delete(
                        f"https://www.googleapis.com/calendar/v3/calendars/primary/events/{event_id}",
                        headers={"Authorization": f"Bearer {access_token}"},
                        timeout=30.0
                    )
                    if response.status_code == 204:
                        logger.info(f"Google event {event_id} deleted successfully")
                        return True
                    else:
                        logger.error(f"Failed to delete Google event: {response.status_code} - {response.text}")
                        return False

            elif provider == "microsoft":
                async with httpx.AsyncClient() as client:
                    response = await client.delete(
                        f"https://graph.microsoft.com/v1.0/me/events/{event_id}",
                        headers={"Authorization": f"Bearer {access_token}"},
                        timeout=30.0
                    )
                    if response.status_code == 204:
                        logger.info(f"Microsoft event {event_id} deleted successfully")
                        return True
                    else:
                        logger.error(f"Failed to delete Microsoft event: {response.status_code} - {response.text}")
                        return False

        except Exception as e:
            logger.error(f"Error deleting calendar event: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    async def update_calendar_event_with_call_summary(self, call_sid: str, call_summary: str, recording_url: Optional[str] = None) -> bool:
        """
        Update calendar event with call summary and recording link after call ends.

        Args:
            call_sid: Twilio call SID
            call_summary: Summary of the call
            recording_url: URL to call recording (optional)

        Returns:
            True if updated successfully, False otherwise
        """
        try:
            # Find appointment by call_sid
            appointment = self.appointments_collection.find_one({"call_sid": call_sid})
            if not appointment:
                logger.warning(f"No appointment found for call {call_sid}")
                return False

            provider = appointment.get("provider")
            provider_event_id = appointment.get("provider_event_id")
            user_id = appointment.get("user_id")

            if not provider_event_id:
                logger.error(f"No provider event ID for appointment {appointment.get('_id')}")
                return False

            # Get calendar account
            account = await self.get_calendar_account(str(user_id), provider)
            if not account:
                logger.error(f"No calendar account found for user {user_id}")
                return False

            # Get access token
            access_token = await self.ensure_access_token(account)
            if not access_token:
                logger.error("Failed to get access token")
                return False

            # Build description with call summary and recording link
            frontend_url = os.getenv("FRONTEND_URL", "https://convis.ai")
            call_log_url = f"{frontend_url}/call-logs?call_sid={call_sid}"

            description = f"""📞 Call Summary:
{call_summary}

{'🎙️ Recording: ' + recording_url if recording_url else ''}

📊 View Full Call Details:
{call_log_url}

Click the link above to listen to the recording, view the full transcript, and see all call analytics.
"""

            # Update event based on provider
            if provider == "google":
                return await self._update_google_event(access_token, provider_event_id, description)
            elif provider == "microsoft":
                return await self._update_microsoft_event(access_token, provider_event_id, description)

            return False

        except Exception as e:
            logger.error(f"Error updating calendar event with call summary: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    async def _update_google_event(self, access_token: str, event_id: str, description: str) -> bool:
        """Update Google Calendar event description."""
        try:
            async with httpx.AsyncClient() as client:
                # First, get the existing event
                get_response = await client.get(
                    f"https://www.googleapis.com/calendar/v3/calendars/primary/events/{event_id}",
                    headers={"Authorization": f"Bearer {access_token}"},
                    timeout=30.0
                )
                get_response.raise_for_status()
                existing_event = get_response.json()

                # Update with new description
                existing_event["description"] = description

                # Patch the event
                response = await client.patch(
                    f"https://www.googleapis.com/calendar/v3/calendars/primary/events/{event_id}",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json"
                    },
                    json=existing_event,
                    timeout=30.0
                )
                response.raise_for_status()
                logger.info(f"Google event {event_id} updated with call summary")
                return True

        except Exception as e:
            logger.error(f"Error updating Google event: {e}")
            return False

    async def _update_microsoft_event(self, access_token: str, event_id: str, description: str) -> bool:
        """Update Microsoft Calendar event description."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.patch(
                    f"https://graph.microsoft.com/v1.0/me/events/{event_id}",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "body": {
                            "contentType": "Text",
                            "content": description
                        }
                    },
                    timeout=30.0
                )
                response.raise_for_status()
                logger.info(f"Microsoft event {event_id} updated with call summary")
                return True

        except Exception as e:
            logger.error(f"Error updating Microsoft event: {e}")
            return False

    async def book_inbound_appointment(self, call_sid: str, user_id: str, assistant_id: str, appointment: Dict[str, Any], provider: str = "google", calendar_account_id: Optional[str] = None) -> Optional[str]:
        """
        Book an appointment for an inbound call.

        Args:
            call_sid: Twilio call SID
            user_id: User ID (owner of the calendar)
            assistant_id: AI assistant ID
            appointment: Appointment details from AI analysis
            provider: "google" or "microsoft"
            calendar_account_id: Specific calendar account ID to use (optional)

        Returns:
            Provider event ID if created, otherwise None.
        """
        try:
            logger.info(f"[BOOK_INBOUND] Starting appointment booking for call {call_sid}")
            logger.info(f"[BOOK_INBOUND] Appointment data: {appointment}")
            logger.info(f"[BOOK_INBOUND] Calendar account ID: {calendar_account_id}, Provider: {provider}")

            # Get calendar account - prioritize specific calendar_account_id if provided
            if calendar_account_id:
                account = await self.get_calendar_account_by_id(calendar_account_id)
                if not account:
                    logger.error(f"[BOOK_INBOUND] No calendar account found with ID {calendar_account_id}")
                    return
                # Update provider from the actual account
                provider = account.get("provider", provider)
                logger.info(f"[BOOK_INBOUND] Using specific calendar account: {account.get('email')} ({provider})")
            else:
                account = await self.get_calendar_account(user_id, provider)
                if not account:
                    logger.error(f"[BOOK_INBOUND] No {provider} calendar account for user {user_id}")
                    return
                logger.info(f"[BOOK_INBOUND] Using user's calendar account: {account.get('email')} ({provider})")

            # Get access token (refresh if needed) - use ensure_access_token for decryption and refresh
            access_token = await self.ensure_access_token(account)
            if not access_token:
                logger.error("[BOOK_INBOUND] Failed to get valid access token")
                return

            # Add initial description with placeholder for call summary
            frontend_url = os.getenv("FRONTEND_URL", "https://convis.ai")
            call_log_url = f"{frontend_url}/call-logs?call_sid={call_sid}"

            initial_description = f"""{appointment.get('notes', '')}

📊 Call Details:
This appointment was scheduled during a call. The call summary and recording will be added here automatically after the call ends.

View Call Log: {call_log_url}
"""

            # Add description to appointment data
            appointment_with_description = {**appointment, "notes": initial_description}

            # Create calendar event
            logger.info(f"[BOOK_INBOUND] Creating {provider} calendar event...")
            event_id = None
            if provider == "google":
                event_id = await self.create_google_event(access_token, appointment_with_description)
            elif provider == "microsoft":
                event_id = await self.create_microsoft_event(access_token, appointment_with_description)

            if not event_id:
                logger.error("[BOOK_INBOUND] Failed to create calendar event - no event ID returned")
                return

            # Save appointment record (for inbound calls, we don't have lead_id or campaign_id)
            appointment_doc = {
                "user_id": ObjectId(user_id),
                "assistant_id": ObjectId(assistant_id),
                "call_sid": call_sid,
                "call_type": "inbound",
                "provider": provider,
                "provider_event_id": event_id,
                "title": appointment.get("title", "Inbound Call Appointment"),
                "start": datetime.fromisoformat(appointment.get("start_iso")),
                "end": datetime.fromisoformat(appointment.get("end_iso")),
                "timezone": appointment.get("timezone", "America/New_York"),
                "created_at": datetime.utcnow()
            }

            result = self.appointments_collection.insert_one(appointment_doc)
            logger.info(f"[BOOK_INBOUND] Appointment record saved to database with ID: {result.inserted_id}")

            # Update call log to mark appointment booked
            call_logs = self.db["call_logs"]
            call_logs.update_one(
                {"call_sid": call_sid},
                {"$set": {"appointment_booked": True, "updated_at": datetime.utcnow()}}
            )

            # Send email notification about scheduled meeting
            try:
                from app.services.async_email_service import async_email_service

                # Get user email
                users_collection = self.db["users"]
                user = users_collection.find_one({"_id": ObjectId(user_id)})

                if user and user.get("email"):
                    # Format meeting time
                    start_dt = datetime.fromisoformat(appointment.get("start_iso"))
                    end_dt = datetime.fromisoformat(appointment.get("end_iso"))
                    meeting_time = f"{start_dt.strftime('%I:%M %p')} - {end_dt.strftime('%I:%M %p')}"

                    # Get caller information from call log
                    call_log = call_logs.find_one({"call_sid": call_sid})
                    caller_name = None
                    if call_log:
                        # Try to extract name from call metadata or use phone number
                        caller_name = call_log.get("caller_name") or call_log.get("from_number")

                    email_sent = await async_email_service.send_meeting_scheduled_email(
                        to_email=user.get("email"),
                        meeting_title=appointment.get("title", "Inbound Call Appointment"),
                        meeting_date=start_dt,
                        meeting_time=meeting_time,
                        timezone=appointment.get("timezone", "America/New_York"),
                        notes=appointment.get("notes", ""),
                        call_sid=call_sid,
                        attendee_name=user.get("name") or user.get("email").split("@")[0]
                    )

                    if email_sent:
                        logger.info(f"[BOOK_INBOUND] Meeting notification email sent to {user.get('email')}")
                    else:
                        logger.warning(f"[BOOK_INBOUND] Failed to send meeting notification email")
                else:
                    logger.warning(f"[BOOK_INBOUND] No email found for user {user_id}")

            except Exception as e:
                logger.error(f"[BOOK_INBOUND] Error sending meeting email: {e}")
                import traceback
                logger.error(traceback.format_exc())
                # Don't fail the whole process if email fails
                pass

            logger.info(f"[BOOK_INBOUND] ✓ Appointment booked successfully for call {call_sid}: event_id={event_id}")
            return event_id

        except Exception as e:
            logger.error(f"Error booking inbound appointment: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

"""
Twilio Service - Scalable setup for managing thousands of phone numbers
Eliminates manual Console configuration by automating webhooks, TwiML Apps,
and subaccount management via the Twilio REST API.
"""

import logging
from typing import Optional, List, Dict, Any
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
from app.config.settings import settings

logger = logging.getLogger(__name__)


class TwilioService:
    """Service class for Twilio operations that scale to thousands of users"""

    def __init__(self, account_sid: str, auth_token: str, subaccount_sid: Optional[str] = None):
        """
        Initialize Twilio client

        Args:
            account_sid: Main account SID or subaccount SID
            auth_token: Auth token for the account
            subaccount_sid: Optional subaccount SID for multi-tenant isolation
        """
        self.account_sid = account_sid
        self.auth_token = auth_token
        self.subaccount_sid = subaccount_sid

        # If subaccount is provided, use it; otherwise use main account
        if subaccount_sid:
            # Parent account client can manage subaccounts
            parent_client = Client(account_sid, auth_token)
            self.client = parent_client.api.accounts(subaccount_sid)
        else:
            self.client = Client(account_sid, auth_token)

    # ==================== TwiML App Management ====================

    async def ensure_twiml_app(
        self,
        friendly_name: str = "Convis Voice Router",
        voice_url: Optional[str] = None,
        sms_url: Optional[str] = None,
        status_callback: Optional[str] = None
    ) -> str:
        """
        Ensure a TwiML App exists (create or get existing).
        TwiML Apps let you change URLs once for all attached numbers.

        Args:
            friendly_name: Name of the TwiML app
            voice_url: Voice webhook URL
            sms_url: SMS webhook URL
            status_callback: Status callback URL

        Returns:
            app_sid: The TwiML App SID
        """
        try:
            # Search for existing app
            apps = self.client.applications.list(friendly_name=friendly_name, limit=1)

            if apps:
                app_sid = apps[0].sid
                logger.info(f"Found existing TwiML App: {app_sid}")

                # Update URLs if provided
                if voice_url or sms_url or status_callback:
                    update_params = {}
                    if voice_url:
                        update_params['voice_url'] = voice_url
                        update_params['voice_method'] = 'POST'
                    if sms_url:
                        update_params['sms_url'] = sms_url
                        update_params['sms_method'] = 'POST'
                    if status_callback:
                        update_params['status_callback'] = status_callback
                        update_params['status_callback_method'] = 'POST'

                    self.client.applications(app_sid).update(**update_params)
                    logger.info(f"Updated TwiML App {app_sid} with new URLs")

                return app_sid

            # Create new app
            create_params = {'friendly_name': friendly_name}
            if voice_url:
                create_params['voice_url'] = voice_url
                create_params['voice_method'] = 'POST'
            if sms_url:
                create_params['sms_url'] = sms_url
                create_params['sms_method'] = 'POST'
            if status_callback:
                create_params['status_callback'] = status_callback
                create_params['status_callback_method'] = 'POST'

            app = self.client.applications.create(**create_params)
            logger.info(f"Created new TwiML App: {app.sid}")
            return app.sid

        except TwilioRestException as e:
            logger.error(f"Twilio error ensuring TwiML App: {e}")
            raise
        except Exception as e:
            logger.error(f"Error ensuring TwiML App: {e}")
            raise

    # ==================== Phone Number Management ====================

    async def buy_number(
        self,
        phone_number: str,
        voice_url: Optional[str] = None,
        sms_url: Optional[str] = None,
        voice_application_sid: Optional[str] = None,
        friendly_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Purchase a phone number and configure webhooks automatically.

        Args:
            phone_number: E.164 format phone number (e.g., +12025551234)
            voice_url: Direct voice webhook URL (if not using TwiML App)
            sms_url: Direct SMS webhook URL (if not using TwiML App)
            voice_application_sid: TwiML App SID (recommended over direct URLs)
            friendly_name: Friendly name for the number

        Returns:
            dict: Phone number details including SID, phone_number, capabilities
        """
        try:
            purchase_params = {'phone_number': phone_number}

            # Option 1: Attach to TwiML App (recommended)
            if voice_application_sid:
                purchase_params['voice_application_sid'] = voice_application_sid
                logger.info(f"Attaching number to TwiML App: {voice_application_sid}")

            # Option 2: Direct webhook URLs
            if voice_url:
                purchase_params['voice_url'] = voice_url
                purchase_params['voice_method'] = 'POST'

            if sms_url:
                purchase_params['sms_url'] = sms_url
                purchase_params['sms_method'] = 'POST'

            if friendly_name:
                purchase_params['friendly_name'] = friendly_name

            # Purchase the number
            incoming_phone_number = self.client.incoming_phone_numbers.create(**purchase_params)

            logger.info(f"Successfully purchased number: {incoming_phone_number.phone_number}")

            return {
                'sid': incoming_phone_number.sid,
                'phone_number': incoming_phone_number.phone_number,
                'friendly_name': incoming_phone_number.friendly_name,
                'capabilities': {
                    'voice': incoming_phone_number.capabilities.get('voice', False),
                    'sms': incoming_phone_number.capabilities.get('sms', False),
                    'mms': incoming_phone_number.capabilities.get('mms', False)
                }
            }

        except TwilioRestException as e:
            logger.error(f"Twilio error buying number {phone_number}: {e}")
            raise
        except Exception as e:
            logger.error(f"Error buying number {phone_number}: {e}")
            raise

    async def update_number_webhook(
        self,
        phone_number_sid: str,
        voice_url: Optional[str] = None,
        sms_url: Optional[str] = None,
        voice_application_sid: Optional[str] = None,
        friendly_name: Optional[str] = None
    ) -> bool:
        """
        Update webhook configuration for an existing phone number.

        Args:
            phone_number_sid: Twilio phone number SID
            voice_url: Voice webhook URL
            sms_url: SMS webhook URL
            voice_application_sid: TwiML App SID
            friendly_name: Update friendly name (e.g., to show assigned agent)

        Returns:
            bool: True if successful
        """
        try:
            update_params = {}

            if voice_application_sid:
                update_params['voice_application_sid'] = voice_application_sid

            if voice_url:
                update_params['voice_url'] = voice_url
                update_params['voice_method'] = 'POST'

            if sms_url:
                update_params['sms_url'] = sms_url
                update_params['sms_method'] = 'POST'

            if friendly_name:
                update_params['friendly_name'] = friendly_name

            self.client.incoming_phone_numbers(phone_number_sid).update(**update_params)
            logger.info(f"Updated webhook for number SID: {phone_number_sid}")
            return True

        except TwilioRestException as e:
            logger.error(f"Twilio error updating number {phone_number_sid}: {e}")
            raise
        except Exception as e:
            logger.error(f"Error updating number {phone_number_sid}: {e}")
            raise

    async def attach_all_numbers_to_app(self, app_sid: str) -> int:
        """
        Batch operation: Attach all existing numbers to a TwiML App.
        Use this for one-time migration from manual configuration.

        Args:
            app_sid: TwiML App SID

        Returns:
            int: Number of phone numbers updated
        """
        try:
            numbers = self.client.incoming_phone_numbers.list(limit=1000)
            count = 0

            for number in numbers:
                try:
                    self.client.incoming_phone_numbers(number.sid).update(
                        voice_application_sid=app_sid
                    )
                    count += 1
                    logger.info(f"Attached {number.phone_number} to app {app_sid}")
                except Exception as e:
                    logger.error(f"Failed to attach {number.phone_number}: {e}")
                    continue

            logger.info(f"Successfully attached {count} numbers to TwiML App {app_sid}")
            return count

        except TwilioRestException as e:
            logger.error(f"Twilio error in batch attach: {e}")
            raise
        except Exception as e:
            logger.error(f"Error in batch attach: {e}")
            raise

    # ==================== Messaging Service Management ====================

    async def create_messaging_service(
        self,
        friendly_name: str,
        inbound_request_url: Optional[str] = None,
        status_callback: Optional[str] = None
    ) -> str:
        """
        Create a Messaging Service for SMS at scale.
        One webhook handles all numbers in the service.

        Args:
            friendly_name: Name of the messaging service
            inbound_request_url: Inbound SMS webhook URL
            status_callback: Status callback URL

        Returns:
            str: Messaging Service SID
        """
        try:
            create_params = {'friendly_name': friendly_name}

            if inbound_request_url:
                create_params['inbound_request_url'] = inbound_request_url
            if status_callback:
                create_params['status_callback'] = status_callback

            service = self.client.messaging.services.create(**create_params)
            logger.info(f"Created Messaging Service: {service.sid}")
            return service.sid

        except TwilioRestException as e:
            logger.error(f"Twilio error creating messaging service: {e}")
            raise
        except Exception as e:
            logger.error(f"Error creating messaging service: {e}")
            raise

    async def add_number_to_messaging_service(
        self,
        service_sid: str,
        phone_number_sid: str
    ) -> bool:
        """
        Add a phone number to a Messaging Service.

        Args:
            service_sid: Messaging Service SID
            phone_number_sid: Phone number SID to add

        Returns:
            bool: True if successful
        """
        try:
            self.client.messaging.services(service_sid).phone_numbers.create(
                phone_number_sid=phone_number_sid
            )
            logger.info(f"Added number {phone_number_sid} to service {service_sid}")
            return True

        except TwilioRestException as e:
            logger.error(f"Twilio error adding number to service: {e}")
            raise
        except Exception as e:
            logger.error(f"Error adding number to service: {e}")
            raise

    # ==================== Subaccount Management (Multi-tenant) ====================

    async def create_subaccount(
        self,
        friendly_name: str
    ) -> Dict[str, str]:
        """
        Create a Twilio subaccount for multi-tenant isolation.
        Each customer gets their own subaccount with separate usage/logs/limits.

        Args:
            friendly_name: Name for the subaccount (e.g., "Customer ABC")

        Returns:
            dict: {'sid': subaccount_sid, 'auth_token': subaccount_auth_token}
        """
        try:
            # Only works with parent account client
            if self.subaccount_sid:
                raise ValueError("Cannot create subaccounts from within a subaccount")

            subaccount = self.client.api.accounts.create(friendly_name=friendly_name)
            logger.info(f"Created subaccount: {subaccount.sid}")

            return {
                'sid': subaccount.sid,
                'auth_token': subaccount.auth_token,
                'friendly_name': friendly_name
            }

        except TwilioRestException as e:
            logger.error(f"Twilio error creating subaccount: {e}")
            raise
        except Exception as e:
            logger.error(f"Error creating subaccount: {e}")
            raise

    async def list_available_numbers(
        self,
        country_code: str = "US",
        area_code: Optional[str] = None,
        contains: Optional[str] = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Search for available phone numbers to purchase.

        Args:
            country_code: Country code (US, CA, GB, etc.)
            area_code: Filter by area code
            contains: Filter by digits contained in number
            limit: Max results

        Returns:
            list: Available phone numbers with details
        """
        try:
            search_params = {'limit': limit}
            if area_code:
                search_params['area_code'] = area_code
            if contains:
                search_params['contains'] = contains

            available = self.client.available_phone_numbers(country_code).local.list(**search_params)

            results = []
            for number in available:
                results.append({
                    'phone_number': number.phone_number,
                    'friendly_name': number.friendly_name,
                    'locality': number.locality,
                    'region': number.region,
                    'capabilities': {
                        'voice': number.capabilities.get('voice', False),
                        'sms': number.capabilities.get('SMS', False),
                        'mms': number.capabilities.get('MMS', False)
                    }
                })

            return results

        except TwilioRestException as e:
            logger.error(f"Twilio error searching numbers: {e}")
            raise
        except Exception as e:
            logger.error(f"Error searching numbers: {e}")
            raise

    async def get_number_details(self, phone_number_sid: str) -> Dict[str, Any]:
        """
        Get details for a specific phone number.

        Args:
            phone_number_sid: Phone number SID

        Returns:
            dict: Phone number details
        """
        try:
            number = self.client.incoming_phone_numbers(phone_number_sid).fetch()

            return {
                'sid': number.sid,
                'phone_number': number.phone_number,
                'friendly_name': number.friendly_name,
                'voice_url': number.voice_url,
                'sms_url': number.sms_url,
                'voice_application_sid': number.voice_application_sid,
                'capabilities': {
                    'voice': number.capabilities.get('voice', False),
                    'sms': number.capabilities.get('sms', False),
                    'mms': number.capabilities.get('mms', False)
                }
            }

        except TwilioRestException as e:
            logger.error(f"Twilio error fetching number details: {e}")
            raise
        except Exception as e:
            logger.error(f"Error fetching number details: {e}")
            raise


# Helper function to get Twilio service instance
def get_twilio_service(
    account_sid: Optional[str] = None,
    auth_token: Optional[str] = None,
    subaccount_sid: Optional[str] = None
) -> TwilioService:
    """
    Get a TwilioService instance using provided or default credentials.

    Args:
        account_sid: Override default account SID
        auth_token: Override default auth token
        subaccount_sid: Optional subaccount SID

    Returns:
        TwilioService: Configured service instance
    """
    sid = account_sid or settings.twilio_account_sid
    token = auth_token or settings.twilio_auth_token

    if not sid or not token:
        raise ValueError("Twilio credentials not provided and not found in settings")

    return TwilioService(sid, token, subaccount_sid)

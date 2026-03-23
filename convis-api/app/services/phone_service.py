"""
Phone number validation and timezone detection service
"""
import phonenumbers
from phonenumbers import NumberParseException, timezone as pn_timezone
from typing import Optional, Tuple, List
import logging

logger = logging.getLogger(__name__)


class PhoneService:
    """Service for phone number operations"""

    @staticmethod
    def normalize_and_validate(raw_number: str, default_region: str = "US") -> Tuple[bool, Optional[str], Optional[str], List[str]]:
        """
        Normalize and validate a phone number.

        Args:
            raw_number: Raw phone number string
            default_region: Default country code (ISO 2-letter)

        Returns:
            Tuple of (is_valid, e164_format, detected_region, timezones)
        """
        try:
            # Clean the number first
            cleaned = raw_number.strip()

            # If number doesn't start with +, try adding it
            # This handles cases like "918850501889" (India) or "14155551234" (US)
            if not cleaned.startswith('+'):
                cleaned_with_plus = '+' + cleaned

                # Try parsing with + prefix first (for international format without +)
                try:
                    parsed = phonenumbers.parse(cleaned_with_plus, None)
                    if phonenumbers.is_valid_number(parsed):
                        # Get E.164 format
                        e164 = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
                        # Get region code
                        region = phonenumbers.region_code_for_number(parsed)
                        # Get possible timezones
                        timezones = pn_timezone.time_zones_for_number(parsed)
                        return True, e164, region, list(timezones) if timezones else []
                except NumberParseException:
                    # If that didn't work, continue to try other methods
                    pass

            # Try parsing with region hint
            try:
                parsed = phonenumbers.parse(raw_number, default_region)
            except NumberParseException:
                # Try parsing without region (for numbers with + already)
                parsed = phonenumbers.parse(raw_number, None)

            # Validate the number
            if not phonenumbers.is_valid_number(parsed):
                logger.warning(f"Invalid phone number: {raw_number}")
                return False, None, None, []

            # Get E.164 format
            e164 = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)

            # Get region code
            region = phonenumbers.region_code_for_number(parsed)

            # Get possible timezones
            timezones = pn_timezone.time_zones_for_number(parsed)

            return True, e164, region, list(timezones) if timezones else []

        except Exception as e:
            logger.error(f"Error parsing phone number {raw_number}: {e}")
            return False, None, None, []

    @staticmethod
    def detect_timezone(e164_number: str, fallback_tz: str = "America/New_York") -> str:
        """
        Detect timezone for a phone number.

        Args:
            e164_number: Phone number in E.164 format
            fallback_tz: Fallback timezone if detection fails

        Returns:
            IANA timezone string
        """
        try:
            parsed = phonenumbers.parse(e164_number, None)
            timezones = pn_timezone.time_zones_for_number(parsed)

            if timezones and len(timezones) > 0:
                # Return first timezone (most common)
                return timezones[0]

            return fallback_tz

        except Exception as e:
            logger.error(f"Error detecting timezone for {e164_number}: {e}")
            return fallback_tz

    @staticmethod
    def check_region_mismatch(e164_number: str, expected_country: str) -> bool:
        """
        Check if a phone number's region matches the expected country.

        Args:
            e164_number: Phone number in E.164 format
            expected_country: Expected ISO country code

        Returns:
            True if there's a mismatch, False otherwise
        """
        try:
            parsed = phonenumbers.parse(e164_number, None)
            region = phonenumbers.region_code_for_number(parsed)
            return region != expected_country.upper()
        except Exception:
            return False

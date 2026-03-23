"""
Credentials Encryption Service
Handles secure encryption/decryption of integration credentials using Fernet (AES-128)
"""
import os
import base64
import hashlib
import logging
from typing import Dict, Any, Optional
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)


class CredentialsEncryption:
    """
    Secure credentials encryption service using Fernet symmetric encryption.

    Uses a master encryption key derived from:
    1. ENCRYPTION_KEY environment variable (required in production)
    2. Falls back to a derived key from SECRET_KEY for development

    Each user's credentials are additionally salted with their user_id
    for extra security isolation between accounts.
    """

    _instance = None
    _fernet: Optional[Fernet] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        """Initialize the encryption key"""
        # Try to get encryption key from environment
        encryption_key = os.getenv("ENCRYPTION_KEY")

        if not encryption_key:
            # Fall back to deriving from SECRET_KEY
            secret_key = os.getenv("SECRET_KEY", "convis-default-secret-key-change-in-production")
            logger.warning(
                "ENCRYPTION_KEY not set, deriving from SECRET_KEY. "
                "Set ENCRYPTION_KEY in production for better security."
            )

            # Derive a Fernet-compatible key from SECRET_KEY
            salt = b"convis-credential-salt-v1"
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000,
            )
            key = base64.urlsafe_b64encode(kdf.derive(secret_key.encode()))
            self._fernet = Fernet(key)
        else:
            # Use provided encryption key
            # Ensure it's properly formatted for Fernet
            if len(encryption_key) == 32:
                # 32 bytes = raw key, encode it
                key = base64.urlsafe_b64encode(encryption_key.encode())
            elif len(encryption_key) == 44:
                # Already base64 encoded
                key = encryption_key.encode()
            else:
                # Hash it to get consistent length
                hashed = hashlib.sha256(encryption_key.encode()).digest()
                key = base64.urlsafe_b64encode(hashed)

            self._fernet = Fernet(key)

        logger.info("Credentials encryption service initialized")

    def encrypt(self, data: str, user_id: Optional[str] = None) -> str:
        """
        Encrypt a string value

        Args:
            data: The string to encrypt
            user_id: Optional user ID for additional salting

        Returns:
            Base64-encoded encrypted string
        """
        try:
            # Add user-specific salt if provided
            if user_id:
                salted_data = f"{user_id}:{data}"
            else:
                salted_data = data

            encrypted = self._fernet.encrypt(salted_data.encode())
            return base64.urlsafe_b64encode(encrypted).decode()

        except Exception as e:
            logger.error(f"Encryption error: {e}")
            raise ValueError("Failed to encrypt data")

    def decrypt(self, encrypted_data: str, user_id: Optional[str] = None) -> str:
        """
        Decrypt an encrypted string

        Args:
            encrypted_data: Base64-encoded encrypted string
            user_id: Optional user ID that was used for salting

        Returns:
            Decrypted string
        """
        try:
            # Decode from our base64 wrapper
            encrypted_bytes = base64.urlsafe_b64decode(encrypted_data.encode())

            # Decrypt
            decrypted = self._fernet.decrypt(encrypted_bytes).decode()

            # Remove user salt if present
            if user_id and decrypted.startswith(f"{user_id}:"):
                return decrypted[len(user_id) + 1:]

            return decrypted

        except Exception as e:
            logger.error(f"Decryption error: {e}")
            raise ValueError("Failed to decrypt data - key may have changed")

    def encrypt_credentials(
        self,
        credentials: Dict[str, Any],
        user_id: Optional[str] = None,
        sensitive_fields: Optional[list] = None
    ) -> Dict[str, Any]:
        """
        Encrypt sensitive fields in a credentials dictionary

        Args:
            credentials: Dictionary of credentials
            user_id: User ID for salting
            sensitive_fields: List of field names to encrypt.
                            If None, encrypts common sensitive fields.

        Returns:
            Dictionary with sensitive fields encrypted
        """
        if sensitive_fields is None:
            # Default sensitive field patterns
            sensitive_fields = [
                "api_token", "api_key", "access_token", "refresh_token",
                "password", "secret", "private_key", "smtp_password",
                "client_secret", "webhook_secret", "signing_secret"
            ]

        encrypted = {}

        for key, value in credentials.items():
            if value is None:
                encrypted[key] = None
            elif any(sf in key.lower() for sf in sensitive_fields):
                # This is a sensitive field, encrypt it
                if isinstance(value, str) and value:
                    encrypted[key] = {
                        "_encrypted": True,
                        "value": self.encrypt(value, user_id)
                    }
                else:
                    encrypted[key] = value
            elif isinstance(value, dict):
                # Recursively encrypt nested dicts
                encrypted[key] = self.encrypt_credentials(value, user_id, sensitive_fields)
            else:
                # Non-sensitive field, keep as-is
                encrypted[key] = value

        return encrypted

    def decrypt_credentials(
        self,
        credentials: Dict[str, Any],
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Decrypt sensitive fields in a credentials dictionary

        Args:
            credentials: Dictionary with encrypted fields
            user_id: User ID that was used for salting

        Returns:
            Dictionary with sensitive fields decrypted
        """
        decrypted = {}

        for key, value in credentials.items():
            if value is None:
                decrypted[key] = None
            elif isinstance(value, dict):
                if value.get("_encrypted"):
                    # This is an encrypted field
                    decrypted[key] = self.decrypt(value["value"], user_id)
                else:
                    # Recursively decrypt nested dicts
                    decrypted[key] = self.decrypt_credentials(value, user_id)
            else:
                decrypted[key] = value

        return decrypted

    def mask_credentials(
        self,
        credentials: Dict[str, Any],
        show_last_chars: int = 4
    ) -> Dict[str, Any]:
        """
        Mask sensitive fields for display (e.g., in UI)

        Args:
            credentials: Credentials dictionary
            show_last_chars: Number of characters to show at end

        Returns:
            Dictionary with sensitive fields masked
        """
        sensitive_patterns = [
            "api_token", "api_key", "access_token", "refresh_token",
            "password", "secret", "private_key", "smtp_password",
            "client_secret", "webhook_secret"
        ]

        masked = {}

        for key, value in credentials.items():
            if value is None:
                masked[key] = None
            elif isinstance(value, dict):
                if value.get("_encrypted"):
                    # Show as masked
                    masked[key] = "••••••••"
                else:
                    masked[key] = self.mask_credentials(value, show_last_chars)
            elif any(sf in key.lower() for sf in sensitive_patterns):
                if isinstance(value, str) and len(value) > show_last_chars:
                    masked[key] = "••••••••" + value[-show_last_chars:]
                else:
                    masked[key] = "••••••••"
            else:
                masked[key] = value

        return masked


# Singleton instance
credentials_encryption = CredentialsEncryption()

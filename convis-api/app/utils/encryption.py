"""
Encryption utilities for securing sensitive data like API credentials
"""
from cryptography.fernet import Fernet
from app.config.settings import settings
import logging
import base64

logger = logging.getLogger(__name__)


class EncryptionService:
    """Service for encrypting and decrypting sensitive data"""

    def __init__(self):
        if settings.encryption_key:
            try:
                # Ensure the key is properly formatted
                key = settings.encryption_key.encode() if isinstance(settings.encryption_key, str) else settings.encryption_key
                # Pad or truncate to 32 bytes for Fernet
                key = base64.urlsafe_b64encode(key[:32].ljust(32, b'='))
                self.cipher = Fernet(key)
                self.enabled = True
                logger.info("Encryption service initialized")
            except Exception as e:
                logger.error(f"Failed to initialize encryption: {e}")
                self.cipher = None
                self.enabled = False
        else:
            logger.warning("No encryption key configured - credentials will be stored unencrypted")
            self.cipher = None
            self.enabled = False

    def encrypt(self, data: str) -> str:
        """
        Encrypt a string

        Args:
            data: Plain text string to encrypt

        Returns:
            Encrypted string (base64 encoded)
        """
        if not self.enabled or not self.cipher:
            logger.warning("Encryption not enabled - returning plain text")
            return data

        try:
            encrypted = self.cipher.encrypt(data.encode())
            return encrypted.decode()
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            raise

    def decrypt(self, encrypted_data: str) -> str:
        """
        Decrypt a string

        Args:
            encrypted_data: Encrypted string (base64 encoded)

        Returns:
            Decrypted plain text string
        """
        if not self.enabled or not self.cipher:
            logger.warning("Encryption not enabled - returning data as-is")
            return encrypted_data

        try:
            decrypted = self.cipher.decrypt(encrypted_data.encode())
            return decrypted.decode()
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            # Check if data looks like it might be plain text (not encrypted)
            # Fernet tokens start with 'gAAAAA' typically
            if encrypted_data and not encrypted_data.startswith('gAAAAA'):
                logger.warning("Decryption failed but data doesn't look encrypted - might be plain text")
                return encrypted_data
            # If it looks encrypted but failed to decrypt, the ENCRYPTION_KEY likely changed
            logger.error("CRITICAL: Data appears encrypted but decryption failed - ENCRYPTION_KEY may have changed!")
            logger.error("Stored credentials are unreadable. User needs to reconnect their provider.")
            raise ValueError("Decryption failed - encryption key mismatch. Please reconnect your provider credentials.")

    @staticmethod
    def generate_key() -> str:
        """
        Generate a new encryption key

        Returns:
            Base64 encoded encryption key
        """
        key = Fernet.generate_key()
        return key.decode()


# Global encryption service instance
encryption_service = EncryptionService()

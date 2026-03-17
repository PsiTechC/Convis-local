"""
Migration script to encrypt existing calendar OAuth tokens in the database.
This should be run once after deploying the encryption changes.
"""
import logging
from app.config.database import Database
from app.utils.encryption import encryption_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def migrate_calendar_tokens():
    """Encrypt all existing unencrypted calendar tokens."""
    try:
        db = Database.connect()
        calendar_accounts = db["calendar_accounts"]

        # Find all accounts
        accounts = list(calendar_accounts.find({}))
        logger.info(f"Found {len(accounts)} calendar accounts to check")

        migrated_count = 0

        for account in accounts:
            oauth_data = account.get("oauth", {})
            access_token = oauth_data.get("accessToken")
            refresh_token = oauth_data.get("refreshToken")

            # Check if tokens need encryption (try to decrypt - if it fails, they're plain text)
            needs_migration = False
            encrypted_access_token = access_token
            encrypted_refresh_token = refresh_token

            if access_token:
                try:
                    # Try to decrypt - if it succeeds, already encrypted
                    encryption_service.decrypt(access_token)
                    logger.info(f"Account {account['_id']} access token already encrypted")
                except:
                    # If decrypt fails, it's plain text - encrypt it
                    encrypted_access_token = encryption_service.encrypt(access_token)
                    needs_migration = True
                    logger.info(f"Encrypting access token for account {account['_id']}")

            if refresh_token:
                try:
                    # Try to decrypt - if it succeeds, already encrypted
                    encryption_service.decrypt(refresh_token)
                    logger.info(f"Account {account['_id']} refresh token already encrypted")
                except:
                    # If decrypt fails, it's plain text - encrypt it
                    encrypted_refresh_token = encryption_service.encrypt(refresh_token)
                    needs_migration = True
                    logger.info(f"Encrypting refresh token for account {account['_id']}")

            if needs_migration:
                # Update the account with encrypted tokens and mark as valid
                calendar_accounts.update_one(
                    {"_id": account["_id"]},
                    {
                        "$set": {
                            "oauth.accessToken": encrypted_access_token,
                            "oauth.refreshToken": encrypted_refresh_token,
                            "oauth.is_valid": True
                        }
                    }
                )
                migrated_count += 1
                logger.info(f"Migrated account {account['_id']}")
            else:
                # Just mark as valid if already encrypted
                calendar_accounts.update_one(
                    {"_id": account["_id"]},
                    {
                        "$set": {
                            "oauth.is_valid": True
                        }
                    }
                )

        logger.info(f"Migration complete! Migrated {migrated_count} accounts")
        Database.close()

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        import traceback
        logger.error(traceback.format_exc())


if __name__ == "__main__":
    logger.info("Starting calendar token encryption migration...")
    migrate_calendar_tokens()

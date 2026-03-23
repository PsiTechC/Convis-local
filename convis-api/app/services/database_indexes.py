"""
Database Indexes Setup for Convis
Creates indexes for optimal query performance at scale
"""
from app.config.database import Database
from app.voice_pipeline.helpers.logger_config import configure_logger

logger = configure_logger(__name__)


def create_all_indexes():
    """
    Create all necessary database indexes for production performance
    Safe to run multiple times - MongoDB will skip existing indexes
    """
    try:
        db = Database.get_db()
        logger.info("[DATABASE_INDEXES] Starting index creation...")

        # Call Logs Collection Indexes
        call_logs = db["call_logs"]

        # 1. Unique index on call_sid (primary lookup)
        call_logs.create_index("call_sid", unique=True, name="idx_call_sid_unique")
        logger.info("[DATABASE_INDEXES] ✅ Created unique index on call_logs.call_sid")

        # 2. Compound index for user queries (user_id + created_at descending)
        call_logs.create_index([("user_id", 1), ("created_at", -1)], name="idx_user_calls")
        logger.info("[DATABASE_INDEXES] ✅ Created index on call_logs.user_id + created_at")

        # 3. Index on status for filtering active/completed calls
        call_logs.create_index("status", name="idx_status")
        logger.info("[DATABASE_INDEXES] ✅ Created index on call_logs.status")

        # 4. Index on created_at for time-based queries
        call_logs.create_index([("created_at", -1)], name="idx_created_at")
        logger.info("[DATABASE_INDEXES] ✅ Created index on call_logs.created_at")

        # AI Assistants Collection Indexes
        assistants = db["ai_assistants"]

        # 1. Index on user_id for fetching user's assistants
        assistants.create_index("user_id", name="idx_assistant_user")
        logger.info("[DATABASE_INDEXES] ✅ Created index on ai_assistants.user_id")

        # 2. Compound index for user's assistants sorted by creation
        assistants.create_index([("user_id", 1), ("created_at", -1)], name="idx_assistant_user_created")
        logger.info("[DATABASE_INDEXES] ✅ Created index on ai_assistants.user_id + created_at")

        # Phone Numbers Collection Indexes
        phone_numbers = db["phone_numbers"]

        # 1. Unique index on phone_number
        phone_numbers.create_index("phone_number", unique=True, name="idx_phone_unique")
        logger.info("[DATABASE_INDEXES] ✅ Created unique index on phone_numbers.phone_number")

        # 2. Index on user_id for user's phone numbers
        phone_numbers.create_index("user_id", name="idx_phone_user")
        logger.info("[DATABASE_INDEXES] ✅ Created index on phone_numbers.user_id")

        # Provider Connections Collection Indexes
        provider_connections = db["provider_connections"]

        # 1. Compound index for user + provider lookup
        provider_connections.create_index([("user_id", 1), ("provider", 1)], name="idx_provider_user")
        logger.info("[DATABASE_INDEXES] ✅ Created index on provider_connections.user_id + provider")

        # Users Collection Indexes
        users = db["users"]

        # 1. Unique index on email
        users.create_index("email", unique=True, name="idx_user_email_unique")
        logger.info("[DATABASE_INDEXES] ✅ Created unique index on users.email")

        # Campaigns Collection Indexes (if using campaigns)
        campaigns = db["campaigns"]

        # 1. Index on user_id for user's campaigns
        campaigns.create_index("user_id", name="idx_campaign_user")
        logger.info("[DATABASE_INDEXES] ✅ Created index on campaigns.user_id")

        # 2. Compound index for active campaigns
        campaigns.create_index([("user_id", 1), ("status", 1), ("scheduled_time", 1)], name="idx_campaign_active")
        logger.info("[DATABASE_INDEXES] ✅ Created index on campaigns.user_id + status + scheduled_time")

        # Leads Collection Indexes
        leads = db["leads"]

        # 1. Compound index for campaign status lookups
        leads.create_index([("campaign_id", 1), ("status", 1), ("_id", 1)], name="idx_leads_campaign_status_id")
        logger.info("[DATABASE_INDEXES] ✅ Created index on leads.campaign_id + status + _id")

        # 2. Retry scheduling index
        leads.create_index([("campaign_id", 1), ("retry_on", 1)], name="idx_leads_campaign_retry_on")
        logger.info("[DATABASE_INDEXES] ✅ Created index on leads.campaign_id + retry_on")

        # 3. Ordering index
        leads.create_index([("campaign_id", 1), ("order_index", 1)], name="idx_leads_campaign_order")
        logger.info("[DATABASE_INDEXES] ✅ Created index on leads.campaign_id + order_index")

        logger.info("[DATABASE_INDEXES] 🎉 All indexes created successfully!")
        return True

    except Exception as e:
        logger.error(f"[DATABASE_INDEXES] Failed to create indexes: {e}", exc_info=True)
        return False


def list_all_indexes():
    """List all indexes for verification"""
    try:
        db = Database.get_db()

        collections = ["call_logs", "ai_assistants", "phone_numbers", "provider_connections", "users", "campaigns", "leads"]

        logger.info("[DATABASE_INDEXES] Current indexes:")
        for collection_name in collections:
            collection = db[collection_name]
            indexes = collection.list_indexes()
            logger.info(f"\n{collection_name}:")
            for idx in indexes:
                logger.info(f"  - {idx['name']}: {idx.get('key', {})}")

        return True
    except Exception as e:
        logger.error(f"[DATABASE_INDEXES] Failed to list indexes: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    # Run this script to create indexes
    create_all_indexes()
    list_all_indexes()

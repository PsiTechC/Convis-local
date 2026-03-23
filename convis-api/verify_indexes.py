#!/usr/bin/env python3
"""
Database Index Verification Script
Checks and creates missing indexes for optimal query performance
"""

import sys
import logging
from app.config.database import Database

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def verify_and_create_indexes():
    """Verify that all required indexes exist and create missing ones"""

    try:
        db = Database.get_db()

        # Define required indexes for each collection
        required_indexes = {
            'call_logs': [
                {'keys': [('user_id', 1)], 'name': 'user_id_1'},
                {'keys': [('call_sid', 1)], 'name': 'call_sid_1'},
                {'keys': [('frejun_call_id', 1)], 'name': 'frejun_call_id_1'},
                {'keys': [('created_at', -1)], 'name': 'created_at_-1'},
                {'keys': [('user_id', 1), ('created_at', -1)], 'name': 'user_id_1_created_at_-1'},
                {'keys': [('assigned_assistant_id', 1)], 'name': 'assigned_assistant_id_1'},
            ],
            'users': [
                {'keys': [('email', 1)], 'name': 'email_1', 'unique': True},
                {'keys': [('clerk_user_id', 1)], 'name': 'clerk_user_id_1'},
            ],
            'phone_numbers': [
                {'keys': [('user_id', 1)], 'name': 'user_id_1'},
                {'keys': [('phone_number', 1)], 'name': 'phone_number_1'},
                {'keys': [('assigned_assistant_id', 1)], 'name': 'assigned_assistant_id_1'},
            ],
            'assistants': [
                {'keys': [('user_id', 1)], 'name': 'user_id_1'},
            ],
            'provider_connections': [
                {'keys': [('user_id', 1), ('provider', 1)], 'name': 'user_id_1_provider_1'},
            ],
        }

        results = {
            'existing': [],
            'created': [],
            'errors': []
        }

        for collection_name, indexes in required_indexes.items():
            collection = db[collection_name]

            # Get existing indexes
            existing_indexes = list(collection.list_indexes())
            existing_index_names = {idx['name'] for idx in existing_indexes}

            logger.info(f"\n{'='*60}")
            logger.info(f"Collection: {collection_name}")
            logger.info(f"{'='*60}")

            for index_spec in indexes:
                index_name = index_spec['name']

                if index_name in existing_index_names:
                    logger.info(f"✅ Index '{index_name}' already exists")
                    results['existing'].append(f"{collection_name}.{index_name}")
                else:
                    try:
                        # Create the index
                        unique = index_spec.get('unique', False)
                        collection.create_index(
                            index_spec['keys'],
                            name=index_name,
                            unique=unique,
                            background=True  # Don't block other operations
                        )
                        logger.info(f"✨ Created index '{index_name}' (unique={unique})")
                        results['created'].append(f"{collection_name}.{index_name}")
                    except Exception as e:
                        logger.error(f"❌ Failed to create index '{index_name}': {e}")
                        results['errors'].append(f"{collection_name}.{index_name}: {str(e)}")

        # Print summary
        logger.info(f"\n{'='*60}")
        logger.info("SUMMARY")
        logger.info(f"{'='*60}")
        logger.info(f"✅ Existing indexes: {len(results['existing'])}")
        logger.info(f"✨ Created indexes: {len(results['created'])}")
        logger.info(f"❌ Errors: {len(results['errors'])}")

        if results['created']:
            logger.info("\nNewly created indexes:")
            for idx in results['created']:
                logger.info(f"  - {idx}")

        if results['errors']:
            logger.warning("\nErrors encountered:")
            for err in results['errors']:
                logger.warning(f"  - {err}")

        # Verify dashboard query performance
        logger.info(f"\n{'='*60}")
        logger.info("PERFORMANCE VERIFICATION")
        logger.info(f"{'='*60}")

        # Check index usage for common query
        explain_result = db.call_logs.find({'user_id': {'$exists': True}}).sort('created_at', -1).limit(10).explain()

        if 'executionStats' in explain_result:
            execution_stats = explain_result['executionStats']
            logger.info(f"Sample query execution stats:")
            logger.info(f"  - Docs examined: {execution_stats.get('totalDocsExamined', 'N/A')}")
            logger.info(f"  - Docs returned: {execution_stats.get('nReturned', 'N/A')}")
            logger.info(f"  - Execution time: {execution_stats.get('executionTimeMillis', 'N/A')}ms")

            if execution_stats.get('totalDocsExamined', 0) > execution_stats.get('nReturned', 0) * 10:
                logger.warning("⚠️  Warning: Query is scanning many more docs than returned (missing index?)")

        logger.info(f"\n{'='*60}")
        logger.info("✅ Index verification complete!")
        logger.info(f"{'='*60}\n")

        return len(results['errors']) == 0

    except Exception as e:
        logger.error(f"❌ Fatal error during index verification: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

if __name__ == '__main__':
    success = verify_and_create_indexes()
    sys.exit(0 if success else 1)

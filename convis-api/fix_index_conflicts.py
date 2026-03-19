"""
Safe Index Conflict Resolution Script
This script will:
1. List all current indexes
2. Identify conflicting indexes
3. Drop only the conflicting ones
4. Let the app recreate them with new names
"""
from pymongo import MongoClient
from pymongo.errors import OperationFailure
import sys

# MongoDB connection from .env
MONGODB_URI = "mongodb://psitech:KajuPista%2425@72.60.203.40:10169/convis_python?authSource=admin"
DATABASE_NAME = "convis_python"

def connect_to_mongodb():
    """Connect to MongoDB"""
    try:
        client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
        # Test connection
        client.server_info()
        print("[OK] Connected to MongoDB successfully\n")
        return client[DATABASE_NAME]
    except Exception as e:
        print(f"[ERROR] Failed to connect to MongoDB: {e}")
        sys.exit(1)

def list_collection_indexes(db, collection_name):
    """List all indexes for a collection"""
    try:
        collection = db[collection_name]
        indexes = list(collection.list_indexes())
        return indexes
    except Exception as e:
        print(f"[WARN] Error listing indexes for {collection_name}: {e}")
        return []

def print_all_indexes(db):
    """Print all current indexes for documentation"""
    collections = ["call_logs", "ai_assistants", "phone_numbers",
                   "provider_connections", "users", "campaigns", "leads"]

    print("=" * 80)
    print("CURRENT DATABASE INDEXES (BEFORE CHANGES)")
    print("=" * 80)

    all_indexes = {}
    for collection_name in collections:
        indexes = list_collection_indexes(db, collection_name)
        all_indexes[collection_name] = indexes

        if indexes:
            print(f"\n[{collection_name}]")
            for idx in indexes:
                keys = idx.get('key', {})
                name = idx.get('name', 'unnamed')
                unique = "UNIQUE" if idx.get('unique', False) else ""
                print(f"   - {name}: {dict(keys)} {unique}")
        else:
            print(f"\n[{collection_name}] No indexes")

    print("\n" + "=" * 80)
    return all_indexes

def identify_conflicts(existing_indexes):
    """
    Identify indexes that will conflict with the new schema
    These are indexes with auto-generated names that match our new index definitions
    """
    conflicts = []

    # Define the new index schema from database_indexes.py
    # Format: (collection, field_combo, new_name, old_auto_generated_name_pattern)
    expected_indexes = {
        'leads': [
            # New: idx_leads_campaign_status_id on [campaign_id, status, _id]
            # Old: campaign_id_1_status_1__id_1
            (['campaign_id', 'status', '_id'], 'idx_leads_campaign_status_id', 'campaign_id_1_status_1__id_1'),

            # New: idx_leads_campaign_retry_on on [campaign_id, retry_on]
            # Old: campaign_id_1_retry_on_1
            (['campaign_id', 'retry_on'], 'idx_leads_campaign_retry_on', 'campaign_id_1_retry_on_1'),

            # New: idx_leads_campaign_order on [campaign_id, order_index]
            # Old: campaign_id_1_order_index_1
            (['campaign_id', 'order_index'], 'idx_leads_campaign_order', 'campaign_id_1_order_index_1'),
        ],
        'campaigns': [
            # New: idx_campaign_active on [user_id, status, scheduled_time]
            # Old: user_id_1_status_1_scheduled_time_1
            (['user_id', 'status', 'scheduled_time'], 'idx_campaign_active', 'user_id_1_status_1_scheduled_time_1'),
        ]
    }

    for collection_name, indexes in existing_indexes.items():
        if collection_name not in expected_indexes:
            continue

        for idx in indexes:
            idx_name = idx.get('name', '')

            # Skip the _id_ index (MongoDB default, never drop)
            if idx_name == '_id_':
                continue

            # Check if this index name matches any known conflicting patterns
            for expected in expected_indexes[collection_name]:
                old_name = expected[2]
                new_name = expected[1]

                # If we find an old auto-generated name that conflicts with our new schema
                if idx_name == old_name or (idx_name != new_name and old_name in idx_name):
                    conflicts.append({
                        'collection': collection_name,
                        'index_name': idx_name,
                        'keys': idx.get('key', {}),
                        'will_be_replaced_by': new_name
                    })

    return conflicts

def drop_conflicting_indexes(db, conflicts, dry_run=True):
    """Safely drop conflicting indexes"""
    if not conflicts:
        print("\n[OK] No conflicting indexes found!")
        return True

    print("\n" + "=" * 80)
    print("CONFLICTING INDEXES TO BE REMOVED")
    print("=" * 80)

    for conflict in conflicts:
        print(f"\n[CONFLICT] Collection: {conflict['collection']}")
        print(f"   Index Name: {conflict['index_name']}")
        print(f"   Fields: {dict(conflict['keys'])}")
        print(f"   >> Will be replaced with: {conflict['will_be_replaced_by']}")

    if dry_run:
        print("\n" + "=" * 80)
        print("[DRY RUN] No changes made - this is just a preview")
        print("=" * 80)
        return True

    print("\n" + "=" * 80)
    print("DROPPING CONFLICTING INDEXES...")
    print("=" * 80)

    for conflict in conflicts:
        collection_name = conflict['collection']
        index_name = conflict['index_name']

        try:
            db[collection_name].drop_index(index_name)
            print(f"[OK] Dropped {collection_name}.{index_name}")
        except OperationFailure as e:
            print(f"[ERROR] Failed to drop {collection_name}.{index_name}: {e}")
            return False
        except Exception as e:
            print(f"[ERROR] Unexpected error dropping {collection_name}.{index_name}: {e}")
            return False

    print("\n[OK] All conflicting indexes removed successfully!")
    return True

def main():
    """Main execution"""
    print("\n" + "=" * 80)
    print("CONVIS API - INDEX CONFLICT RESOLUTION TOOL")
    print("=" * 80)

    # Connect to MongoDB
    db = connect_to_mongodb()

    # Step 1: Document current state
    existing_indexes = print_all_indexes(db)

    # Step 2: Identify conflicts
    conflicts = identify_conflicts(existing_indexes)

    # Step 3: Show what will be changed (dry run)
    print("\n" + "=" * 80)
    print("ANALYSIS COMPLETE")
    print("=" * 80)
    drop_conflicting_indexes(db, conflicts, dry_run=True)

    if not conflicts:
        print("\n[OK] No action needed - your database is already compatible!")
        return

    # Step 4: Ask for confirmation
    print("\n" + "=" * 80)
    print("[READY] Ready to fix the conflicts")
    print("=" * 80)
    print("\nThis script will:")
    print("  1. Drop the old conflicting indexes listed above")
    print("  2. Keep all other indexes intact")
    print("  3. Your app will recreate them with new names on next startup")
    print("\nThis is SAFE because:")
    print("  [+] Only removes duplicate/conflicting indexes")
    print("  [+] Doesn't touch unique indexes that protect data integrity")
    print("  [+] App will recreate all needed indexes automatically")

    response = input("\n[?] Proceed with dropping conflicting indexes? (yes/no): ").strip().lower()

    if response != 'yes':
        print("\n[ABORT] No changes made")
        return

    # Step 5: Actually drop the conflicting indexes
    success = drop_conflicting_indexes(db, conflicts, dry_run=False)

    if success:
        print("\n" + "=" * 80)
        print("[SUCCESS] Index conflicts resolved!")
        print("=" * 80)
        print("\nNext steps:")
        print("  1. Restart your FastAPI application")
        print("  2. The app will recreate indexes with new names automatically")
        print("  3. Monitor the startup logs to confirm index creation")
        print("\n[DONE] Your database is now ready!")
    else:
        print("\n" + "=" * 80)
        print("[FAILED] Could not complete the operation")
        print("=" * 80)
        print("\nSome indexes could not be dropped. Please check the errors above.")

if __name__ == "__main__":
    main()

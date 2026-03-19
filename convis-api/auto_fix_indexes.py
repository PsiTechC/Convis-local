"""
Automated Index Conflict Resolution
Automatically fixes the index conflicts without prompting
"""
from pymongo import MongoClient
from pymongo.errors import OperationFailure
import sys

# MongoDB connection
MONGODB_URI = "mongodb://psitech:KajuPista%2425@72.60.203.40:10169/convis_python?authSource=admin"
DATABASE_NAME = "convis_python"

def main():
    print("=" * 80)
    print("AUTOMATED INDEX CONFLICT FIX")
    print("=" * 80)

    # Connect to MongoDB
    try:
        client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
        client.server_info()
        print("[OK] Connected to MongoDB")
        db = client[DATABASE_NAME]
    except Exception as e:
        print(f"[ERROR] Failed to connect: {e}")
        sys.exit(1)

    # Define conflicting indexes to drop
    conflicts = [
        ("leads", "campaign_id_1_retry_on_1"),
        ("leads", "campaign_id_1_order_index_1"),
        ("leads", "campaign_id_1_status_1__id_1"),
    ]

    print("\n[INFO] The following conflicting indexes will be dropped:")
    for collection, index_name in conflicts:
        print(f"  - {collection}.{index_name}")

    print("\n[INFO] Starting index removal...")

    success_count = 0
    error_count = 0

    for collection_name, index_name in conflicts:
        try:
            # Check if index exists before trying to drop
            collection = db[collection_name]
            index_info = collection.index_information()

            if index_name in index_info:
                collection.drop_index(index_name)
                print(f"[OK] Dropped {collection_name}.{index_name}")
                success_count += 1
            else:
                print(f"[SKIP] Index {collection_name}.{index_name} doesn't exist")
        except OperationFailure as e:
            print(f"[ERROR] Failed to drop {collection_name}.{index_name}: {e}")
            error_count += 1
        except Exception as e:
            print(f"[ERROR] Unexpected error with {collection_name}.{index_name}: {e}")
            error_count += 1

    print("\n" + "=" * 80)
    if error_count == 0:
        print("[SUCCESS] All conflicting indexes removed successfully!")
        print("=" * 80)
        print(f"\nRemoved {success_count} conflicting indexes")
        print("\nNext steps:")
        print("  1. Restart your FastAPI application")
        print("  2. App will recreate indexes with new names automatically")
        print("  3. Monitor startup logs to confirm index creation")
        print("\n[DONE] Your application should now start without errors!")
    else:
        print(f"[PARTIAL] {success_count} indexes removed, {error_count} errors")
        print("=" * 80)
        print("\nPlease review the errors above")
        sys.exit(1)

if __name__ == "__main__":
    main()

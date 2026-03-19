"""
Check assistant knowledge base files in MongoDB
"""
from app.config.database import Database
from bson import ObjectId

def check_assistant_kb(assistant_id):
    """Check if assistant has knowledge base files"""
    db = Database.get_db()
    assistants_collection = db['assistants']

    try:
        assistant = assistants_collection.find_one({"_id": ObjectId(assistant_id)})

        if not assistant:
            print(f"[ERROR] Assistant {assistant_id} not found")
            return

        print(f"[INFO] Assistant: {assistant.get('name', 'Unknown')}")
        print(f"[INFO] ID: {assistant_id}")

        kb_files = assistant.get('knowledge_base_files', [])

        if not kb_files:
            print(f"\n[WARNING] No knowledge base files found in database")
            print("This means documents were never successfully uploaded.")
        else:
            print(f"\n[INFO] Found {len(kb_files)} knowledge base file(s):")
            for i, file in enumerate(kb_files, 1):
                print(f"\n  File {i}:")
                print(f"    Filename: {file.get('filename')}")
                print(f"    Type: {file.get('file_type')}")
                print(f"    Size: {file.get('file_size', 0) / 1024:.2f} KB")
                print(f"    Chunks: {file.get('chunks_count', 0)}")
                print(f"    Uploaded: {file.get('uploaded_at')}")
                print(f"    Path: {file.get('file_path')}")

                # Check if physical file exists
                import os
                if os.path.exists(file.get('file_path', '')):
                    print(f"    Status: [OK] Physical file exists")
                else:
                    print(f"    Status: [ERROR] Physical file NOT found")

    except Exception as e:
        print(f"[ERROR] Failed to check assistant: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    assistant_id = "6990519963f0a96ad24eb012"
    check_assistant_kb(assistant_id)

"""
Fix assistant LLM model in database from llama3.2 to llama3.2:3b
"""
from app.config.database import Database

def fix_llm_models():
    """Update all assistants using llama3.2 to llama3.2:3b"""
    db = Database.get_db()
    assistants_collection = db['assistants']

    # Find assistants with llama3.2 (without :3b)
    result = assistants_collection.update_many(
        {"llm_model": "llama3.2"},
        {"$set": {"llm_model": "llama3.2:3b"}}
    )

    print(f"Updated {result.modified_count} assistant(s) from 'llama3.2' to 'llama3.2:3b'")

    # Also update llama3.1 to llama3.1:8b for consistency
    result2 = assistants_collection.update_many(
        {"llm_model": "llama3.1"},
        {"$set": {"llm_model": "llama3.1:8b"}}
    )

    print(f"Updated {result2.modified_count} assistant(s) from 'llama3.1' to 'llama3.1:8b'")

if __name__ == "__main__":
    fix_llm_models()
    print("[SUCCESS] Database updated!")

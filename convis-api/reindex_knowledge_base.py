"""
Re-index all knowledge base files into ChromaDB
This script re-processes all uploaded documents and creates embeddings
"""
from app.config.database import Database
from app.utils import conversational_rag
from app.config.settings import settings
from bson import ObjectId
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def reindex_assistant_kb(assistant_id):
    """Re-index all knowledge base files for an assistant"""
    db = Database.get_db()
    assistants_collection = db['assistants']

    try:
        assistant = assistants_collection.find_one({"_id": ObjectId(assistant_id)})

        if not assistant:
            logger.error(f"Assistant {assistant_id} not found")
            return False

        logger.info(f"Assistant: {assistant.get('name', 'Unknown')}")
        logger.info(f"ID: {assistant_id}")

        kb_files = assistant.get('knowledge_base_files', [])

        if not kb_files:
            logger.warning("No knowledge base files found")
            return False

        logger.info(f"Found {len(kb_files)} knowledge base file(s) to re-index")

        # Check if using local embeddings
        use_local = settings.embedding_model.lower() == "local"
        logger.info(f"Using {'LOCAL' if use_local else 'OPENAI'} embeddings")

        # Create ChromaDB directory if it doesn't exist
        chroma_db_path = os.path.join(
            os.path.dirname(__file__),
            "app", "chroma_db"
        )
        os.makedirs(chroma_db_path, exist_ok=True)
        logger.info(f"ChromaDB path: {chroma_db_path}")

        success_count = 0
        fail_count = 0

        # Re-process each file
        for i, file_info in enumerate(kb_files, 1):
            filename = file_info.get('filename')
            file_path = file_info.get('file_path')
            file_type = file_info.get('file_type')

            logger.info(f"\n[{i}/{len(kb_files)}] Processing: {filename}")

            # Check if file exists
            if not os.path.exists(file_path):
                logger.error(f"  [ERROR] Physical file not found: {file_path}")
                fail_count += 1
                continue

            try:
                # Process document and create embeddings
                result = conversational_rag.process_document_for_conversation(
                    assistant_id=assistant_id,
                    file_path=file_path,
                    filename=filename,
                    file_type=file_type,
                    api_key=None,  # Not needed for local embeddings
                    use_local_embeddings=use_local
                )

                if result['success']:
                    logger.info(f"  [OK] Created {result['chunks_count']} chunks")
                    success_count += 1
                else:
                    logger.error(f"  [ERROR] Failed: {result.get('error', 'Unknown error')}")
                    fail_count += 1

            except Exception as e:
                logger.error(f"  [ERROR] Exception: {e}")
                import traceback
                logger.error(traceback.format_exc())
                fail_count += 1

        # Get final stats
        logger.info(f"\n{'='*60}")
        logger.info(f"Re-indexing complete!")
        logger.info(f"  Success: {success_count}/{len(kb_files)}")
        logger.info(f"  Failed:  {fail_count}/{len(kb_files)}")

        # Check ChromaDB stats
        try:
            kb_stats = conversational_rag.get_kb_stats(assistant_id)
            if kb_stats['exists']:
                logger.info(f"\nChromaDB Collection Stats:")
                logger.info(f"  Total chunks: {kb_stats['total_chunks']}")
                logger.info(f"  Files: {kb_stats['files_count']}")
                logger.info(f"  File list: {kb_stats['files']}")
            else:
                logger.warning(f"\nChromaDB collection does not exist!")
        except Exception as e:
            logger.error(f"Failed to get KB stats: {e}")

        logger.info(f"{'='*60}")

        return success_count > 0

    except Exception as e:
        logger.error(f"Failed to re-index assistant: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


if __name__ == "__main__":
    assistant_id = "6990519963f0a96ad24eb012"

    print("="*60)
    print("Knowledge Base Re-indexing Script")
    print("="*60)
    print(f"Assistant ID: {assistant_id}")
    print(f"This will re-process all documents and create embeddings")
    print("="*60)
    print()

    success = reindex_assistant_kb(assistant_id)

    print()
    if success:
        print("[SUCCESS] Knowledge base re-indexed successfully!")
        print("Your assistant can now access the knowledge base.")
    else:
        print("[FAILED] Re-indexing failed. Check the errors above.")

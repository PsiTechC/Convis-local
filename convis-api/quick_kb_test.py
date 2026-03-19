"""Quick test of knowledge base retrieval"""
import asyncio
import sys

async def test_kb():
    from app.utils.conversational_rag import search_conversation_context, get_kb_stats
    from app.config.settings import settings

    assistant_id = "6990519963f0a96ad24eb012"

    # Check stats
    stats = get_kb_stats(assistant_id)
    print(f"KB Stats: {stats}")

    if not stats['exists']:
        print("ERROR: Knowledge base doesn't exist!")
        return False

    # Test query
    query = "contraband smuggling incident"
    print(f"\nTesting query: '{query}'")

    use_local = settings.embedding_model.lower() == "local"
    context = await search_conversation_context(
        assistant_id=assistant_id,
        query=query,
        api_key=None,
        top_k=3,
        relevance_threshold=0.5,
        use_local_embeddings=use_local
    )

    if context:
        print(f"SUCCESS: Retrieved {len(context)} chars")
        print(f"Preview: {context[:200]}...")
        return True
    else:
        print("FAILED: No context retrieved")
        return False

if __name__ == "__main__":
    result = asyncio.run(test_kb())
    sys.exit(0 if result else 1)

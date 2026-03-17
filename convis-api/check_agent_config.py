#!/usr/bin/env python3
"""
Diagnostic script to check AI assistant configuration and verify streaming pipeline compatibility.
Run this to see why interruption might not be working.
"""
import asyncio
from app.config.database import Database
from bson import ObjectId

async def check_agent_config(agent_id: str = None):
    """Check agent configuration for streaming pipeline compatibility"""
    try:
        db = Database.get_db()
        assistants_collection = db['assistants']

        if agent_id:
            # Check specific agent
            try:
                agent = assistants_collection.find_one({"_id": ObjectId(agent_id)})
            except:
                agent = assistants_collection.find_one({"name": agent_id})
        else:
            # Get most recent agent
            agent = assistants_collection.find_one(sort=[("created_at", -1)])

        if not agent:
            print("❌ No agent found!")
            return

        print("\n" + "="*80)
        print(f"🤖 Agent: {agent.get('name', 'Unknown')}")
        print(f"📋 ID: {agent['_id']}")
        print("="*80)

        # Check ASR provider
        asr_provider = agent.get('asr_provider', 'openai')
        print(f"\n🎤 ASR Provider: {asr_provider}")

        if asr_provider == 'deepgram':
            print("   ✅ DEEPGRAM - Streaming pipeline will be enabled!")
            print("   ✅ Interruption handling: AVAILABLE")
            print("   ✅ Fast response (600-900ms): AVAILABLE")
        else:
            print(f"   ⚠️  {asr_provider.upper()} - Batch mode only")
            print("   ❌ Interruption handling: NOT AVAILABLE")
            print("   ❌ Fast response: NOT AVAILABLE (1200-1800ms)")
            print(f"\n   💡 TIP: Change ASR provider to 'deepgram' to enable interruption!")

        # Check other providers
        print(f"\n🔊 TTS Provider: {agent.get('tts_provider', 'openai')}")
        print(f"🧠 LLM Provider: {agent.get('llm_provider', 'openai')}")
        print(f"🌍 ASR Language: {agent.get('asr_language', 'en')}")
        print(f"🗣️  Bot Language: {agent.get('bot_language', 'en')}")

        # Check streaming flag
        voice_mode = agent.get('voice_mode', 'custom')
        print(f"\n🎙️  Voice Mode: {voice_mode}")

        # Check if streaming would be enabled
        print("\n" + "="*80)
        print("🔍 STREAMING PIPELINE STATUS")
        print("="*80)

        if asr_provider == 'deepgram':
            print("✅ Streaming pipeline will be initialized")
            print("✅ Interruption handling active")
            print("✅ Fast response time enabled")
        else:
            print("❌ Streaming pipeline will NOT be initialized")
            print(f"   Reason: ASR provider is '{asr_provider}' (must be 'deepgram')")
            print("\n📝 To enable streaming:")
            print("   1. Edit this agent in the UI")
            print("   2. Change 'ASR Provider' to 'Deepgram'")
            print("   3. Make a test call")
            print("   4. Try interrupting the AI while it's speaking")

        print("\n" + "="*80)

    except Exception as e:
        print(f"❌ Error checking agent: {e}")
        import traceback
        traceback.print_exc()

async def list_all_agents():
    """List all agents with their ASR providers"""
    try:
        db = Database.get_db()
        assistants_collection = db['assistants']

        agents = list(assistants_collection.find().sort("created_at", -1).limit(20))

        if not agents:
            print("❌ No agents found!")
            return

        print("\n" + "="*80)
        print(f"📋 ALL AGENTS (showing last 20)")
        print("="*80)

        for agent in agents:
            asr_provider = agent.get('asr_provider', 'openai')
            streaming_status = "✅ STREAMING" if asr_provider == 'deepgram' else "❌ BATCH"

            print(f"\n{streaming_status} | {agent.get('name', 'Unknown')}")
            print(f"    ID: {agent['_id']}")
            print(f"    ASR: {asr_provider} | TTS: {agent.get('tts_provider', 'openai')} | LLM: {agent.get('llm_provider', 'openai')}")

        print("\n" + "="*80)

    except Exception as e:
        print(f"❌ Error listing agents: {e}")

if __name__ == "__main__":
    import sys

    print("\n🔍 AI ASSISTANT CONFIGURATION CHECKER")
    print("Checking streaming pipeline and interruption support...\n")

    if len(sys.argv) > 1:
        if sys.argv[1] == "--list":
            asyncio.run(list_all_agents())
        else:
            asyncio.run(check_agent_config(sys.argv[1]))
    else:
        print("Checking most recent agent...\n")
        asyncio.run(check_agent_config())

        print("\n💡 Usage:")
        print(f"   python {sys.argv[0]} <agent_id>     # Check specific agent")
        print(f"   python {sys.argv[0]} --list         # List all agents")

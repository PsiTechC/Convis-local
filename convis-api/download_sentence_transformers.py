"""
Download sentence-transformers model for offline use
"""
import os

# CRITICAL: Set HF_HUB_OFFLINE=0 BEFORE importing sentence_transformers
print("Setting HF_HUB_OFFLINE=0 to allow downloads...")
os.environ['HF_HUB_OFFLINE'] = '0'

print("Importing sentence_transformers...")
from sentence_transformers import SentenceTransformer

def download_model():
    """Download the sentence-transformers model to local cache"""
    model_name = 'all-MiniLM-L6-v2'

    print(f"\n{'='*60}")
    print(f"Downloading sentence-transformers model: {model_name}")
    print(f"{'='*60}\n")

    try:
        print(f"Loading model '{model_name}'...")
        model = SentenceTransformer(model_name)

        print(f"\n✅ SUCCESS! Model downloaded and cached.")
        print(f"Cache location: {os.path.expanduser('~/.cache/huggingface/hub/')}")

        # Test the model
        print("\nTesting model with sample text...")
        test_text = "This is a test sentence"
        embedding = model.encode(test_text)
        print(f"✅ Embedding generated successfully (dimension: {len(embedding)})")

        print(f"\n{'='*60}")
        print("Model is ready for offline use!")
        print(f"{'='*60}\n")

        return True

    except Exception as e:
        print(f"\n❌ ERROR: Failed to download model")
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = download_model()
    exit(0 if success else 1)

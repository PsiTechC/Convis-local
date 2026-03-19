"""
Download sentence-transformers model files using huggingface_hub
This avoids loading the full PyTorch dependencies
"""
import os

# CRITICAL: Set environment variables BEFORE importing
print("Setting HF_HUB_OFFLINE=0 to allow downloads...")
os.environ['HF_HUB_OFFLINE'] = '0'
# Disable symlinks for Windows (avoids permission errors)
os.environ['HF_HUB_DISABLE_SYMLINKS_WARNING'] = '1'

from huggingface_hub import snapshot_download

def download_model():
    """Download the sentence-transformers model files to local cache"""
    model_name = 'sentence-transformers/all-MiniLM-L6-v2'

    print(f"\n{'='*60}")
    print(f"Downloading model: {model_name}")
    print(f"{'='*60}\n")

    try:
        print(f"Downloading model files...")
        cache_dir = snapshot_download(
            repo_id=model_name,
            cache_dir=os.path.expanduser('~/.cache/huggingface/hub/'),
            local_dir_use_symlinks=False  # Disable symlinks for Windows
        )

        print(f"\n[SUCCESS] Model downloaded and cached.")
        print(f"Cache location: {cache_dir}")

        print(f"\n{'='*60}")
        print("Model is ready for offline use!")
        print(f"{'='*60}\n")

        return True

    except Exception as e:
        print(f"\n[ERROR] Failed to download model")
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = download_model()
    exit(0 if success else 1)

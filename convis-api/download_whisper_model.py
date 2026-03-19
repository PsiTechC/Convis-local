"""
Download Whisper models for offline use
"""
import os
import sys

# MUST set this BEFORE importing faster_whisper
os.environ["HF_HUB_OFFLINE"] = "0"

from faster_whisper import WhisperModel

def download_model(model_size="base", device="cpu", compute_type="int8"):
    """Download and cache a Whisper model"""
    print(f"Downloading Whisper '{model_size}' model...")
    print(f"Device: {device}, Compute type: {compute_type}")
    print("This may take a few minutes depending on your internet connection.\n")

    try:
        # This will download the model if not cached
        model = WhisperModel(model_size, device=device, compute_type=compute_type)
        print(f"\n[SUCCESS] Whisper '{model_size}' model downloaded and cached successfully!")
        print(f"Model is ready for offline use.")
        return True
    except Exception as e:
        print(f"\n[ERROR] Failed to download model: {e}")
        return False

if __name__ == "__main__":
    # Download the models that are used in the codebase
    models_to_download = ["base", "small"]

    print("=" * 60)
    print("Whisper Model Downloader")
    print("=" * 60)
    print(f"HF_HUB_OFFLINE is set to: {os.environ.get('HF_HUB_OFFLINE', 'not set')}")
    print()

    all_success = True
    for model_size in models_to_download:
        print(f"\n{'=' * 60}")
        if not download_model(model_size):
            all_success = False

    print(f"\n{'=' * 60}")
    if all_success:
        print("[SUCCESS] All models downloaded successfully!")
        print("Your system is now ready for offline ASR.")
    else:
        print("[PARTIAL] Some models failed to download.")
        print("Check the errors above and try again.")
    print("=" * 60)

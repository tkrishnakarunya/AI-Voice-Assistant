import os
import sys
import urllib.request
import ssl

# Ensure SSL context bypass for environments with certificate verification issues
try:
    ssl._create_default_https_context = ssl._create_unverified_context
except AttributeError:
    pass

# Add src to python path to read settings.py
sys.path.append(os.path.join(os.path.dirname(__file__), "src"))
try:
    from settings import MODEL_DIR, MODEL_PATH, VOICES_PATH
except ImportError:
    # Fallback paths if import fails
    MODEL_DIR = r"C:\AI_Models\Kokoro"
    MODEL_PATH = os.path.join(MODEL_DIR, "kokoro-v1.0.onnx")
    VOICES_PATH = os.path.join(MODEL_DIR, "voices-v1.0.bin")

MODEL_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx"
VOICES_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin"

def download_with_progress(url, dest_path):
    print(f"Downloading {url} to {dest_path}...")
    
    def reporthook(blocknum, blocksize, totalsize):
        readsofar = blocknum * blocksize
        if totalsize > 0:
            percent = readsofar * 1e2 / totalsize
            s = f"\rProgress: {percent:5.1f}% [{readsofar / 1024 / 1024:0.1f} MB / {totalsize / 1024 / 1024:0.1f} MB]"
            sys.stdout.write(s)
            sys.stdout.flush()
        else:
            sys.stdout.write(f"\rDownloaded {readsofar / 1024 / 1024:0.1f} MB")
            sys.stdout.flush()
            
    try:
        urllib.request.urlretrieve(url, dest_path, reporthook)
        print("\nDownload complete!")
    except Exception as e:
        print(f"\nDownload failed: {e}")
        raise e

def main():
    print("=== Kokoro TTS Model Setup ===")
    print(f"Target Directory: {MODEL_DIR}")
    
    # 1. Create directory if not exists
    if not os.path.exists(MODEL_DIR):
        print(f"Creating directory: {MODEL_DIR}")
        os.makedirs(MODEL_DIR, exist_ok=True)
        
    # 2. Check model file
    if os.path.exists(MODEL_PATH):
        print(f"Model file already exists: {MODEL_PATH}")
    else:
        print(f"Model file missing: {MODEL_PATH}")
        try:
            download_with_progress(MODEL_URL, MODEL_PATH)
        except Exception as e:
            print(f"Error downloading model: {e}")
            if os.path.exists(MODEL_PATH):
                try:
                    os.remove(MODEL_PATH)
                except Exception:
                    pass
            sys.exit(1)
            
    # 3. Check voices file
    if os.path.exists(VOICES_PATH):
        print(f"Voices file already exists: {VOICES_PATH}")
    else:
        print(f"Voices file missing: {VOICES_PATH}")
        try:
            download_with_progress(VOICES_URL, VOICES_PATH)
        except Exception as e:
            print(f"Error downloading voices: {e}")
            if os.path.exists(VOICES_PATH):
                try:
                    os.remove(VOICES_PATH)
                except Exception:
                    pass
            sys.exit(1)
            
    print("\nKokoro TTS setup completed successfully!")
    print(f"Model path: {MODEL_PATH}")
    print(f"Voices path: {VOICES_PATH}")

if __name__ == "__main__":
    main()

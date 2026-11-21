"""Download offline models into backend/models/ (git-ignored) so the app runs without internet.

    cd backend
    python scripts/download_models.py              # Whisper model from STT_MODEL (default: small)
    python scripts/download_models.py small medium # several sizes

Faster-whisper (CTranslate2) weights come from the Systran repos on Hugging Face. After the download the app
loads them from disk; nothing is fetched at runtime.
"""
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from core.stt import MODELS_DIR, REPOS   # noqa: E402


def download(size: str) -> Path:
    from huggingface_hub import snapshot_download
    repo = REPOS.get(size, size)
    target = MODELS_DIR / f"faster-whisper-{size.replace('/', '_')}"
    print(f"→ {repo}  →  {target}")
    snapshot_download(repo_id=repo, local_dir=str(target),
                      allow_patterns=["config.json", "model.bin", "tokenizer.json", "vocabulary.*", "preprocessor_config.json"])
    size_mb = sum(f.stat().st_size for f in target.rglob("*") if f.is_file()) / 1e6
    print(f"  done, {size_mb:.0f} MB")
    return target


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(BACKEND / ".env", override=False)
    sizes = sys.argv[1:] or [os.environ.get("STT_MODEL", "small")]
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    for s in sizes:
        download(s)

"""Speech-to-text (W2). Local faster-whisper by default (offline, audio never leaves the machine), OpenAI opt-in.

Public API
----------
transcribe(raw, mime)  -> {"text", "segments": [{"start","end","text"}], "provider", "model", "duration_s"}   (timer stage `stt`)
LiveSession            -> real-time dictation: feed 16 kHz mono PCM16 chunks, get partial + stable text while speaking,
                          then .final() for the best full-quality transcript (same dict as transcribe) + a WAV for evidence.
status(), preload()    -> model state for the UI / warm-up at startup.

Providers (merged with APEX 2 adapters/stt.py): local (faster-whisper, default, audio stays on the machine) | openai |
groq (whisper-large-v3 behind the OpenAI-compatible API) | elevenlabs (scribe_v1). Cloud providers receive unmasked
audio: opt-in only. Cost per minute (STT_PRICE_EUR_PER_MIN) is written to the `stt` metric.

Env: STT_PROVIDER=local|openai|groq|elevenlabs (whisper_local = local), STT_API_KEY, STT_PRICE_EUR_PER_MIN, STT_MODEL=small, STT_LANGUAGE=de, STT_VOCAB, STT_COMPUTE=int8, STT_THREADS, STT_MODEL_DIR.
Models are downloaded once with `python scripts/download_models.py` into backend/models/.
"""
from __future__ import annotations

import io
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import wave
from pathlib import Path

import numpy as np

from . import llm_bridge

SR = 16_000
BACKEND = Path(__file__).resolve().parent.parent
MODELS_DIR = Path(os.environ.get("STT_MODEL_DIR", BACKEND / "models")).resolve()
REPOS = {s: f"Systran/faster-whisper-{s}" for s in ("tiny", "base", "small", "medium", "large-v3")}
REPOS["large-v3-turbo"] = "mobiuslabsgmbh/faster-whisper-large-v3-turbo"

DEFAULT_VOCAB = ("Bohrpfahl, Bewehrung, Nachunternehmer, Polier, Widerlager, Pfahlkopfbalken, Meißel, Hydraulikschaden, "
                 "Behinderungsanzeige, Mehrkostenanzeige, Nachtragsmeldung, Bautagesbericht, Baugrundgutachten, Schalung, Achse")
# Whisper's well-known German hallucinations on silence / noise
HALLUCINATIONS = re.compile(r"untertitel|vielen dank (fürs|für's|für das) zuschauen|bis zum nächsten mal|copyright|amara\.org|swr 20\d\d|zdf", re.I)


EXT = {"audio/webm": ".webm", "audio/ogg": ".ogg", "audio/mp4": ".m4a", "audio/x-m4a": ".m4a", "audio/aac": ".aac", "audio/mpeg": ".mp3",
       "audio/wav": ".wav", "audio/x-wav": ".wav", "audio/wave": ".wav", "video/mp4": ".mp4", "video/webm": ".webm", "video/quicktime": ".mov"}


def _ext(mime: str) -> str:
    return EXT.get((mime or "").split(";")[0].strip().lower(), ".bin")


def _cfg():
    e = os.environ.get
    prov = e("STT_PROVIDER", "local").lower().replace("whisper_local", "local")
    return {"provider": prov, "model": e("STT_MODEL", "small"), "api_key": e("STT_API_KEY", ""),
            "price_min": float(e("STT_PRICE_EUR_PER_MIN", "0") or 0), "language": e("STT_LANGUAGE", "de") or None,
            "vocab": e("STT_VOCAB", DEFAULT_VOCAB), "compute": e("STT_COMPUTE", "int8"),
            "threads": int(e("STT_THREADS", "0") or 0) or max(2, (os.cpu_count() or 4) - 2), "device": e("STT_DEVICE", "auto").lower()}


# ------------------------------------------------------------------ model (loaded once, lazily, thread-safe)
_lock = threading.Lock()
_state = {"model": None, "path": None, "device": None, "loading": False, "error": None, "load_s": None}


def _model_path(size: str) -> str:
    local = MODELS_DIR / f"faster-whisper-{size.replace('/', '_')}"
    if (local / "model.bin").exists():
        return str(local)
    return size if size in REPOS or "/" not in size else size   # faster-whisper downloads to the HF cache on first use


def _model(size: str | None = None):
    if _state["model"] is not None:
        return _state["model"]
    with _lock:
        if _state["model"] is None:
            from faster_whisper import WhisperModel
            c = _cfg()
            _state.update(loading=True, error=None)
            t0 = time.perf_counter()
            try:
                path = _model_path(size or _local_size())
                # auto: Apple-GPU (Metal/MPS, ~1.5x faster on M1) when available, else CPU int8
                devices = ["mps", "cpu"] if c["device"] == "auto" else [c["device"]]
                for i, dev in enumerate(devices):
                    try:
                        _state["model"] = WhisperModel(path, device=dev, compute_type=c["compute"], cpu_threads=c["threads"], num_workers=2)
                        _state["device"] = dev
                        break
                    except Exception:
                        if i == len(devices) - 1:
                            raise
                _state.update(path=path, load_s=round(time.perf_counter() - t0, 2))
            except Exception as e:
                _state["error"] = str(e)
                raise
            finally:
                _state["loading"] = False
    return _state["model"]


def preload(background: bool = True):
    """Warm the local model so the first dictation is fast."""
    if _cfg()["provider"] != "local" or _state["model"] is not None:
        return

    def run():
        try:
            m = _model()
            m.transcribe(np.zeros(SR, dtype=np.float32), language=_cfg()["language"], beam_size=1)   # JIT / allocator warm-up
        except Exception:
            pass
    threading.Thread(target=run, daemon=True).start() if background else run()


def status() -> dict:
    c = _cfg()
    local = MODELS_DIR / f"faster-whisper-{c['model']}"
    return {"provider": c["provider"], "model": c["model"], "language": c["language"], "compute": c["compute"], "device": _state["device"] or c["device"],
            "offline_model_on_disk": (local / "model.bin").exists(), "loaded": _state["model"] is not None,
            "loading": _state["loading"], "load_s": _state["load_s"], "error": _state["error"],
            "ready": c["provider"] in REMOTE or _state["model"] is not None,
            "fallback_local": c["provider"] in REMOTE and os.environ.get("STT_FALLBACK_LOCAL", "1") != "0",
            "last_fallback": _state.get("fallback_error")}


# ------------------------------------------------------------------ audio decoding
def decode(raw: bytes, mime: str = "") -> np.ndarray:
    """Any browser/phone audio (webm/opus, mp4/aac, wav, m4a, ogg, mp3) -> float32 mono 16 kHz."""
    ff = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
    if Path(ff).exists():
        # temp file, not a pipe: MP4/M4A from iPhones keeps its index at the end and needs a seekable input
        with tempfile.NamedTemporaryFile(suffix=_ext(mime)) as f:
            f.write(raw); f.flush()
            p = subprocess.run([ff, "-nostdin", "-hide_banner", "-loglevel", "error", "-i", f.name, "-f", "s16le", "-ac", "1", "-ar", str(SR), "pipe:1"],
                               capture_output=True, timeout=120)
        if p.returncode == 0 and p.stdout:
            return np.frombuffer(p.stdout, np.int16).astype(np.float32) / 32768.0
    from faster_whisper import decode_audio   # PyAV fallback (no ffmpeg binary needed)
    return decode_audio(io.BytesIO(raw), sampling_rate=SR)


def pcm16_to_float(pcm: bytes) -> np.ndarray:
    return np.frombuffer(pcm[: len(pcm) - len(pcm) % 2], np.int16).astype(np.float32) / 32768.0


def wav_bytes(samples: np.ndarray) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((np.clip(samples, -1, 1) * 32767).astype(np.int16).tobytes())
    return buf.getvalue()


# ------------------------------------------------------------------ transcription
def _clean(segs):
    out = []
    for s in segs:
        t = s.text.strip()
        if not t or HALLUCINATIONS.search(t) or getattr(s, "no_speech_prob", 0) > 0.75:
            continue
        out.append({"start": round(s.start, 2), "end": round(s.end, 2), "text": t})
    return out


def _lang(language):
    """'de-DE' / 'en-US' / 'de' -> 'de' / 'en'; None -> configured default."""
    return (language or _cfg()["language"] or "").split("-")[0].lower() or None


def _local(samples: np.ndarray, *, beam: int = 5, prompt: str | None = None, vad: bool = True, language: str | None = None,
           size: str | None = None) -> list[dict]:
    c = _cfg()
    segs, _info = _model(size).transcribe(samples, language=_lang(language), beam_size=beam, initial_prompt=prompt or c["vocab"],
                                      vad_filter=vad, vad_parameters={"min_silence_duration_ms": 500},
                                      condition_on_previous_text=False, temperature=0.0)
    return _clean(list(segs))


def _openai(raw: bytes, mime: str, language: str | None = None, base_url: str | None = None, default_model: str = "whisper-1") -> list[dict]:
    from openai import OpenAI
    c = _cfg()
    ext = _ext(mime).lstrip(".").replace("bin", "webm")
    if base_url:                                   # groq: whisper-large-v3 / -turbo, distil-whisper
        model = c["model"] if c["model"].startswith(("whisper", "distil")) else default_model
    else:                                          # openai: only whisper-1 and gpt-4o(-mini)-transcribe exist
        model = c["model"] if c["model"] == "whisper-1" or c["model"].startswith("gpt-") else default_model
    fmt = "verbose_json" if model.startswith(("whisper", "distil")) else "json"   # gpt-4o-*-transcribe: text only
    kw = {"base_url": base_url} if base_url else {}
    r = OpenAI(api_key=c["api_key"] or None, **kw).audio.transcriptions.create(
        model=model, file=(f"audio.{ext}", raw, mime or "audio/webm"), prompt=c["vocab"],
        language=_lang(language), response_format=fmt)
    segs = getattr(r, "segments", None) or [{"start": 0, "end": getattr(r, "duration", 0) or 0, "text": r.text}]
    return [{"start": round(float(_g(s, "start")), 2), "end": round(float(_g(s, "end")), 2), "text": str(_g(s, "text")).strip()} for s in segs if str(_g(s, "text")).strip()]


def _groq(raw: bytes, mime: str, language: str | None = None) -> list[dict]:
    return _openai(raw, mime, language, base_url="https://api.groq.com/openai/v1", default_model="whisper-large-v3")


def _elevenlabs(raw: bytes, mime: str, language: str | None = None) -> list[dict]:
    """ElevenLabs Scribe: word timestamps grouped into sentence segments (split on pauses > 0.8 s or punctuation)."""
    import requests
    c = _cfg()
    lang = {"de": "deu", "en": "eng"}.get(_lang(language) or "de", "deu")
    r = requests.post("https://api.elevenlabs.io/v1/speech-to-text", headers={"xi-api-key": c["api_key"]},
                      data={"model_id": c["model"] if c["model"].startswith("scribe") else "scribe_v1", "language_code": lang},
                      files={"file": (f"audio{_ext(mime)}", raw, mime or "audio/webm")}, timeout=120)
    r.raise_for_status()
    data = r.json()
    segs, cur = [], None
    for w in (w for w in data.get("words", []) if w.get("type", "word") == "word"):
        if cur and (w["start"] - cur["end"] > 0.8 or cur["text"].rstrip().endswith((".", "?", "!"))):
            segs.append(cur)
            cur = None
        if cur is None:
            cur = {"start": round(float(w["start"]), 2), "end": round(float(w["end"]), 2), "text": w["text"]}
        else:
            cur["end"], cur["text"] = round(float(w["end"]), 2), cur["text"] + " " + w["text"]
    if cur:
        segs.append(cur)
    text = (data.get("text") or "").strip()
    return [dict(s, text=s["text"].strip()) for s in segs] or ([{"start": 0.0, "end": 0.0, "text": text}] if text else [])


REMOTE = {"openai": _openai, "groq": _groq, "elevenlabs": _elevenlabs}


def _g(o, k):
    return o[k] if isinstance(o, dict) else getattr(o, k)


# Domain fixes for words Whisper merges on construction sites ("hit rock at 4 m" -> "hit rocket 4 m").
# Only unambiguous patterns; each one keeps the segment timing (the evidence ref still points at the same seconds).
DOMAIN_FIXES = [(re.compile(r"\brocket (?=\d)", re.I), "rock at "), (re.compile(r"\bpile(s)? (?:seven|7)\b", re.I), r"pile\1 7"),
                (re.compile(r"\baches (?=\d)", re.I), "Achse ")]       # English Whisper hears the German "Achse 2" as "aches 2"


def _fix(text: str) -> str:
    for rx, rep in DOMAIN_FIXES:
        text = rx.sub(rep, text)
    return text


def _result(segments, provider, model, duration_s):
    segments = [dict(s, text=_fix(s["text"])) for s in segments]
    return {"text": " ".join(s["text"] for s in segments).strip(), "segments": segments, "provider": provider, "model": model,
            "duration_s": round(duration_s, 2)}


def transcribe(raw: bytes, mime: str, language: str | None = None) -> dict:
    """Return {"text", "segments": [{"start","end","text"}], "provider", "model", "duration_s"}. Timer stage: `stt`."""
    c = _cfg()
    if c["provider"] in REMOTE:
        try:
            with llm_bridge.timed("stt", "stt", model=f"{c['provider']}:{c['model']}", provider=c["provider"], audio_bytes=len(raw)) as t:
                segs = REMOTE[c["provider"]](raw, mime, language)
                dur = segs[-1]["end"] if segs else 0
                t.meta.update(audio_s=round(dur, 2))
                t.add_cost(dur / 60 * c["price_min"])      # lands in the row's cost_eur
            return _result(segs, c["provider"], c["model"], dur)
        except Exception as e:
            # cloud STT down / out of credits: fall back to the offline model if it is on disk (STT_FALLBACK_LOCAL=0 disables)
            local = MODELS_DIR / f"faster-whisper-{_local_size()}"
            if os.environ.get("STT_FALLBACK_LOCAL", "1") == "0" or not (local / "model.bin").exists():
                raise
            _state["fallback_error"] = f"{c['provider']}: {str(e)[:200]}"
            res = transcribe_samples(decode(raw, mime), language, size=_local_size())
            res["fallback_from"] = c["provider"]
            return res
    samples = decode(raw, mime)
    return transcribe_samples(samples, language)


def _local_size() -> str:
    """Local faster-whisper size: STT_MODEL when it is a local size, else STT_LOCAL_MODEL (default small)."""
    m = _cfg()["model"]
    return m if m in REPOS else os.environ.get("STT_LOCAL_MODEL", "small")


def transcribe_samples(samples: np.ndarray, language: str | None = None, size: str | None = None) -> dict:
    size = size or _cfg()["model"]
    dur = len(samples) / SR
    _model(size)   # load outside the timer so `stt` measures inference, not the one-off model load
    with llm_bridge.Timer("stt", "stt", model=f"local:{size}", provider="local", audio_s=round(dur, 2)):
        segs = _local(samples, beam=5, language=language, size=size)
    return _result(segs, "local", f"faster-whisper-{size}", dur)


# ------------------------------------------------------------------ real-time dictation
class LiveSession:
    """Streaming dictation on top of a non-streaming model.

    Audio arrives as 16 kHz mono PCM16. `partial()` re-transcribes only the not-yet-stable tail (fast greedy decoding);
    segments that ended well before the end of the buffer are committed and never change again, so the window stays short
    and latency stays low however long the user talks. `final()` transcribes the full recording once with beam search,
    which is what becomes evidence.
    """
    STABLE_MARGIN_S = 1.6     # a segment ending this long before the buffer end is considered final
    MAX_TAIL_S = 24.0         # force-commit if the tail grows (e.g. no pauses)

    def __init__(self, language: str | None = None):
        self.language = language
        self.pcm = bytearray()
        self.offset_s = 0.0
        self.committed: list[dict] = []
        self.last_partial = ""
        self._busy = threading.Lock()

    @property
    def duration_s(self) -> float:
        return len(self.pcm) / 2 / SR

    def add(self, chunk: bytes):
        self.pcm.extend(chunk)

    def partial(self) -> dict | None:
        if not self._busy.acquire(blocking=False):
            return None                                  # previous partial still running: skip, never queue up
        try:
            audio = pcm16_to_float(bytes(self.pcm))
            tail = audio[int(self.offset_s * SR):]
            if len(tail) < SR * 0.6:
                return None
            if float(np.sqrt(np.mean(tail[-SR:] ** 2))) < 0.003 and not self.last_partial:
                return {"stable": self._stable(), "partial": "", "duration_s": round(self.duration_s, 1)}
            context = (self._stable()[-200:] or _cfg()["vocab"])
            segs = _local(tail, beam=1, prompt=context, vad=True, language=self.language)
            end = len(tail) / SR
            n = 0                                         # how many leading segments are now stable
            for i, s in enumerate(segs[:-1]):             # the last segment may still grow: never commit it
                if s["end"] < end - self.STABLE_MARGIN_S or end > self.MAX_TAIL_S:
                    n = i + 1
                else:
                    break
            base = self.offset_s
            for s in segs[:n]:
                self.committed.append({"start": round(base + s["start"], 2), "end": round(base + s["end"], 2), "text": s["text"]})
            if n:
                self.offset_s = base + segs[n - 1]["end"]
            self.last_partial = " ".join(s["text"] for s in segs[n:]).strip()
            return {"stable": self._stable(), "partial": self.last_partial, "duration_s": round(self.duration_s, 1)}
        finally:
            self._busy.release()

    def _stable(self) -> str:
        return " ".join(s["text"] for s in self.committed).strip()

    def final(self) -> tuple[dict, bytes]:
        with self._busy:
            audio = pcm16_to_float(bytes(self.pcm))
        return transcribe_samples(audio, self.language), wav_bytes(audio)


def segment_for_quote(segments: list[dict], quote: str) -> dict | None:
    """The transcript segment that best contains a quoted clause (for 'Diktat 00:04–00:11' locators)."""
    words = set(re.findall(r"\w{3,}", (quote or "").lower()))
    if not words or not segments:
        return None
    best = max(segments, key=lambda s: len(words & set(re.findall(r"\w{3,}", s["text"].lower()))))
    return best if words & set(re.findall(r"\w{3,}", best["text"].lower())) else None


def fmt_ts(sec: float) -> str:
    sec = max(0, int(round(sec)))
    return f"{sec // 60:02d}:{sec % 60:02d}"

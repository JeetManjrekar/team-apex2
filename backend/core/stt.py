"""Speech-to-text (W2). Local faster-whisper by default, OpenAI opt-in (STT_PROVIDER)."""


def transcribe(raw: bytes, mime: str) -> dict:
    """Return {"text", "segments": [{"start","end","text"}], "provider", "model", "duration_s"}. Timer stage: `stt`."""
    raise NotImplementedError("W2: implement core/stt.transcribe")

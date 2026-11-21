"""Voice (W2): Whisper speech-to-text -> assistant -> draft with audio evidence.

POST /api/voice             multipart `audio` (any format: webm/opus, m4a/aac, wav, mp3, mp4 video) — one-shot upload.
                            Form `submit=false` returns the transcript only (preview). Used by the browser fallback and
                            the planned mobile app.
WS   /api/voice/stream      real-time dictation. Client sends {"type":"start"}, then binary frames of 16 kHz mono PCM16
                            (little-endian), then {"type":"stop"} (or {"type":"cancel"}). Server sends
                            {"type":"ready"}, {"type":"partial","stable","partial","duration_s"} about every second,
                            and finally {"type":"final","transcript","result","audio_file"}.
GET  /api/voice/status      model / provider state for the UI.
"""
import asyncio
import json
import os

from fastapi import APIRouter, File, Form, UploadFile, WebSocket, WebSocketDisconnect

from core import assistant, llm_bridge, stt
from core.errors import ApiError
from core.store import UPLOADS, new_id

router = APIRouter(prefix="/api", tags=["voice"])

MAX_UPLOAD = 50 * 1024 * 1024
MAX_LIVE_S = float(os.environ.get("STT_MAX_LIVE_S", "300"))
PARTIAL_EVERY_S = float(os.environ.get("STT_PARTIAL_EVERY_S", "0.9"))

if os.environ.get("STT_PRELOAD", "1") != "0":
    stt.preload(background=True)          # warm the offline model while the server starts


def _meta(audio_file, tr):
    return {"audio_file": audio_file, "segments": tr["segments"], "duration_s": tr["duration_s"], "stt_model": tr["model"], "stt_provider": tr["provider"]}


def _submit(text, meta):
    """Transcript -> assistant (same path as typed chat, but as voice with audio evidence)."""
    if not text.strip():
        raise ApiError(422, "No speech recognised. Please try again closer to the microphone.")
    return assistant.handle(text, voice=True, evidence_meta=meta)


@router.get("/voice/status")
def voice_status():
    return stt.status()


@router.post("/voice")
def voice(audio: UploadFile = File(...), submit: bool = Form(True), language: str | None = Form(None)):
    """W2: audio -> core.stt.transcribe -> assistant.handle(voice=True, evidence_meta=...)."""
    raw = audio.file.read()
    if not raw:
        raise ApiError(400, "empty audio")
    if len(raw) > MAX_UPLOAD:
        raise ApiError(413, "audio too large (max 50 MB)")
    aid = new_id()
    with llm_bridge.Timer("voice_to_draft_end_to_end", f"voice-{aid}", source="upload"):
        name = f"{aid}{stt._ext(audio.content_type)}"
        (UPLOADS / name).write_bytes(raw)
        try:
            tr = stt.transcribe(raw, audio.content_type or "", language)
        except Exception as e:
            raise ApiError(502, f"speech recognition failed: {e}")
        if not submit:
            return {"transcript": tr, "audio_file": f"uploads/{name}"}
        return {"transcript": tr, "audio_file": f"uploads/{name}", "result": _submit(tr["text"], _meta(f"uploads/{name}", tr))}


@router.websocket("/voice/stream")
async def voice_stream(ws: WebSocket):
    await ws.accept()
    sess, submit, alive = stt.LiveSession(), True, True
    await ws.send_json({"type": "ready", "status": stt.status()})

    async def ticker():
        last = 0.0
        while alive:
            await asyncio.sleep(PARTIAL_EVERY_S)
            if sess.duration_s - last < 0.4:
                continue
            last = sess.duration_s
            try:
                r = await asyncio.to_thread(sess.partial)
            except Exception as e:                      # model still loading etc.: report, keep recording
                await ws.send_json({"type": "warning", "detail": str(e)})
                continue
            if r is not None and alive:
                await ws.send_json({"type": "partial", **r})

    task = None
    try:
        while True:
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                return
            if msg.get("bytes"):
                sess.add(msg["bytes"])
                if task is None:
                    task = asyncio.create_task(ticker())
                if sess.duration_s > MAX_LIVE_S:
                    await ws.send_json({"type": "warning", "detail": f"maximum length {int(MAX_LIVE_S)} s reached, stopping"})
                    msg = {"text": json.dumps({"type": "stop"})}
                else:
                    continue
            data = json.loads(msg.get("text") or "{}")
            kind = data.get("type")
            if kind == "start":
                submit = data.get("submit", True)
                sess.language = data.get("language") or None
            elif kind == "cancel":
                await ws.send_json({"type": "cancelled"})
                return
            elif kind == "stop":
                alive = False
                if task:
                    task.cancel()
                aid = new_id()
                with llm_bridge.Timer("voice_to_draft_end_to_end", f"voice-{aid}", source="live", audio_s=round(sess.duration_s, 1)):
                    tr, wav = await asyncio.to_thread(sess.final)
                    name = f"{aid}.wav"
                    (UPLOADS / name).write_bytes(wav)
                    out = {"type": "final", "transcript": tr, "audio_file": f"uploads/{name}"}
                    if submit and tr["text"].strip():
                        out["result"] = await asyncio.to_thread(_submit, tr["text"], _meta(f"uploads/{name}", tr))
                    elif submit:
                        out["error"] = "No speech recognised. Please try again closer to the microphone."
                await ws.send_json(out)
                return
    except WebSocketDisconnect:
        return
    except Exception as e:
        try:
            await ws.send_json({"type": "error", "detail": str(e)})
        except Exception:
            pass
    finally:
        alive = False
        if task:
            task.cancel()
        try:
            await ws.close()
        except Exception:
            pass

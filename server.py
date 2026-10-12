import json
import os
import random
import re
import tempfile
import uuid

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from openai import RateLimitError
from pydantic import BaseModel

from agent.pipeline import Pipeline
from agent.voice_scripts import VOICE_SCRIPTS

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.yaml")
DIST_DIR = os.path.join(BASE_DIR, "web", "dist")

pipeline = Pipeline(CONFIG_PATH)
OUTPUT_DIR = pipeline._data_path(pipeline.cfg.get("output_dir", "output"))
os.makedirs(OUTPUT_DIR, exist_ok=True)

app = FastAPI(title="Vik Agent", version="1.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    text: str
    history: list[dict] = []


class ChatResponse(BaseModel):
    id: str
    reply: str
    audio_url: str
    heard: str | None = None


class RateRequest(BaseModel):
    id: str
    rating: str | None = None


class NotesRequest(BaseModel):
    text: str = ""


def _parse_history(raw):
    if not raw:
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return []
    return [
        m for m in raw
        if m.get("role") in ("user", "assistant") and m.get("content")
    ]


def _run(text=None, audio=None, history=None, source="text"):
    if history:
        history = _parse_history(history)
    out_path = os.path.join(OUTPUT_DIR, f"reply_{uuid.uuid4().hex}.mp3")
    try:
        heard, reply, _ = pipeline.run(
            text=text, audio=audio, out=out_path, history=history
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except RateLimitError:
        raise HTTPException(
            status_code=429,
            detail="LLM free-tier limit reached (OpenRouter daily cap). Thoda ruk ke phir try karo.",
        )
    question = heard or text or ""
    item_id = pipeline.memory.log(question, reply, source=source, heard=heard)
    return ChatResponse(
        id=item_id,
        reply=reply,
        audio_url=f"/api/audio/{os.path.basename(out_path)}",
        heard=heard,
    )


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "voice_enrolled": pipeline._voice_id(pipeline.cfg.get("tts", {})) is not None,
    }


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")
    return _run(text=text, history=req.history, source="text")


@app.post("/api/voice", response_model=ChatResponse)
async def voice(audio: UploadFile = File(...), history: str = "[]"):
    suffix = os.path.splitext(audio.filename or "")[1] or ".webm"
    fd, tmp_path = tempfile.mkstemp(suffix=suffix, dir=OUTPUT_DIR)
    os.close(fd)
    try:
        with open(tmp_path, "wb") as f:
            f.write(await audio.read())
        return _run(audio=tmp_path, history=history, source="voice")
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


@app.get("/api/audio/{name}")
def get_audio(name: str):
    if not re.fullmatch(r"reply_[0-9a-f]{32}\.mp3", name):
        raise HTTPException(status_code=404, detail="not found")
    path = os.path.join(OUTPUT_DIR, name)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(path, media_type="audio/mpeg")


# ---------------------------------------------------------------- voice training


@app.get("/api/voice/status")
def voice_status():
    samples = pipeline.list_voice_samples()
    cfg = pipeline.cfg.get("tts", {})
    voice_id = pipeline._voice_id(cfg)
    state = None
    if voice_id:
        try:
            model = pipeline.tts.get_model(voice_id)
            state = (model or {}).get("state")
        except Exception:
            state = None
    return {
        "voice_id": voice_id,
        "voice_enrolled": voice_id is not None,
        "state": state,
        "base_sample": os.path.exists(
            pipeline._data_path(cfg.get("reference_audio", "voice/ref.wav"))
        ),
        "sample_count": len(samples),
        "samples": samples,
    }


@app.get("/api/voice/scripts")
def voice_scripts(count: int = 5):
    count = max(1, min(count, len(VOICE_SCRIPTS)))
    return {"scripts": random.sample(VOICE_SCRIPTS, count)}


@app.post("/api/voice/train")
async def voice_train(
    audio: UploadFile = File(...),
    text: str = Form(""),
    retrain: bool = Form(True),
):
    suffix = os.path.splitext(audio.filename or "")[1] or ".webm"
    fd, tmp_path = tempfile.mkstemp(suffix=suffix, dir=OUTPUT_DIR)
    os.close(fd)
    try:
        with open(tmp_path, "wb") as f:
            f.write(await audio.read())
        sid = pipeline.save_voice_sample(tmp_path, text, ext=suffix)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    result = {"sample_id": sid, "sample_count": len(pipeline.list_voice_samples())}
    if retrain:
        try:
            voice_id, used = pipeline.train_voice()
            result.update({"voice_id": voice_id, "trained_on": used, "trained": True})
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"sample saved, but retrain failed: {e}")
    return result


@app.delete("/api/voice/samples/{sid}")
def voice_sample_delete(sid: str):
    if not pipeline.delete_voice_sample(sid):
        raise HTTPException(status_code=404, detail="sample not found")
    return {"ok": True, "sample_count": len(pipeline.list_voice_samples())}


# ------------------------------------------------------------- self-learning


@app.get("/api/memory")
def memory_state():
    return {
        "stats": pipeline.memory.stats(),
        "notes": pipeline.memory.notes(),
        "history": pipeline.memory.recent(25),
    }


@app.post("/api/memory/rate")
def memory_rate(req: RateRequest):
    if req.rating not in ("up", "down", None):
        raise HTTPException(status_code=400, detail="rating must be up, down or null")
    if not pipeline.memory.rate(req.id, req.rating):
        raise HTTPException(status_code=404, detail="entry not found")
    return {"ok": True, "stats": pipeline.memory.stats()}


@app.post("/api/memory/notes")
def memory_notes(req: NotesRequest):
    pipeline.memory.set_notes(req.text)
    return {"ok": True, "notes": pipeline.memory.notes()}


@app.post("/api/memory/reflect")
def memory_reflect():
    stats = pipeline.memory.stats()
    history = pipeline.memory.recent(25)
    if not history:
        raise HTTPException(status_code=400, detail="no history to learn from yet")
    lines = []
    for it in history:
        mark = {"up": "LIKED", "down": "DISLIKED"}.get(it.get("rating"), "unrated")
        q = (it.get("question") or "").strip().replace("\n", " ")
        a = (it.get("reply") or "").strip().replace("\n", " ")
        lines.append(f"[{mark}] User: {q}\nVikash: {a}")
    current = pipeline.memory.notes() or "(none yet)"
    prompt = (
        "A chat agent replies as a persona named Vikash, who speaks clear, natural "
        "Hindi (Roman script) with good English mixed in (no Bhojpuri, no dialect, no "
        "added accent, no extra filler words), warm, lightly humorous, 2-6 sentences, "
        "plain spoken words (no markdown/lists/emojis), first person, and must never "
        "reveal being an AI.\n\n"
        "Below are recent exchanges with the user's thumbs up/down feedback, and the "
        "current self-notes. Rewrite the self-notes as at most 8 short, concrete, "
        "actionable bullets that will make future replies better: what to do more of "
        "(from LIKED), what to avoid (from DISLIKED), recurring topics and user "
        "preferences. Output only the bullet list.\n\n"
        f"CURRENT NOTES:\n{current}\n\nRECENT EXCHANGES:\n" + "\n\n".join(lines)
    )
    try:
        notes = pipeline.llm.reflect(prompt)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except RateLimitError:
        raise HTTPException(
            status_code=429,
            detail="LLM free-tier limit reached — reflection try again later.",
        )
    if not notes.strip():
        notes = current
    pipeline.memory.set_notes(notes)
    return {"ok": True, "notes": pipeline.memory.notes(), "stats": pipeline.memory.stats()}


@app.get("/api/memory/report")
def memory_report():
    return PlainTextResponse(pipeline.memory.build_report(), media_type="text/markdown")


# ---------------------------------------------------------------- profile size


def _file_info(path):
    if path and os.path.exists(path):
        return {
            "name": os.path.basename(path),
            "chars": os.path.getsize(path),
            "mtime": os.path.getmtime(path),
        }
    return None


@app.get("/api/profile")
def profile_state():
    persona = pipeline.cfg.get("persona", {})
    src = pipeline._path(persona.get("profile_file", "profile.md"))
    dst = pipeline._path(persona.get("profile_summary_file", "profile_summary.md"))
    return {
        "mode": persona.get("profile_mode", "auto"),
        "profile": _file_info(src),
        "summary": _file_info(dst),
    }


@app.post("/api/profile/condense")
def profile_condense():
    try:
        dst = pipeline.ensure_profile_summary(force=True)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except RateLimitError:
        raise HTTPException(
            status_code=429,
            detail="LLM free-tier limit reached — thoda ruk ke phir try karo.",
        )
    if not dst:
        raise HTTPException(status_code=400, detail="nothing to condense or LLM returned empty")
    with open(dst, encoding="utf-8") as f:
        return {"ok": True, "summary": f.read(), **_file_info(dst)}


if os.path.isdir(DIST_DIR):
    app.mount("/", StaticFiles(directory=DIST_DIR, html=True), name="web")


if __name__ == "__main__":
    import uvicorn

    try:
        pipeline.ensure_profile_summary()
    except Exception as e:
        print(f"[startup] profile condense skipped: {e}")

    uvicorn.run(app, host="127.0.0.1", port=8000)

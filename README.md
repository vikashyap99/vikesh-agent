# Vik_Agent

A fully **cloud, 100% free** agent that answers **as Vikash, in Vikash's cloned voice**.
Nothing heavy runs on your laptop — no local models, no GPU, no big downloads.

Pipeline: `text or voice input → (STT) → LLM persona + context.md → voice clone TTS → audio file`

## Free cloud stack

| Stage | Service | Free tier |
| --- | --- | --- |
| Persona LLM | OpenRouter (`nvidia/nemotron-3-super-120b-a12b:free`) | ~50 req/day free, 20 req/min |
| Speech-to-text | Groq Whisper (`whisper-large-v3-turbo`) | Free API tier |
| Voice clone TTS | Fish Audio `s2.1-pro-free` | Free tier, 8k credits/mo, ~7 min, commercial use |

Any OpenAI-compatible provider works for the LLM/STT — just edit `config.yaml`.
For the LLM you can point at any free model on
[OpenRouter](https://openrouter.ai/models?max_price=0) by changing `llm.model`
(the `:free` suffix is required). Free models share an upstream pool and can
throttle intermittently, so `llm.fallback_models` lists models OpenRouter can
auto-route to when the primary is rate-limited. Qwen3-TTS (Alibaba DashScope,
free quota) is a valid TTS alternative.

## Setup

```sh
cd /Users/vikashkumar/Desktop/Interview/Vik_Agent
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # then paste your API keys into .env
```

### Get the free API keys

Add each key to `.env`:

| Key | Where to get it |
| --- | --- |
| `OPENROUTER_API_KEY` | https://openrouter.ai/keys (used by the persona LLM) |
| `GROQ_API_KEY` | https://console.groq.com/keys (used for speech-to-text) |
| `FISH_API_KEY` | https://fish.audio/ (sign up → API key in account settings) |
| `GEMINI_API_KEY` | https://aistudio.google.com/app/apikey (optional — only if you switch `config.yaml` back to Gemini) |

## Enroll your voice (one time)

1. Record 10–30s of clean speech (quiet room, natural Hinglish + English).
2. Convert to WAV and put it at `voice/ref.wav`:

```sh
afconvert -f WAVE -d LEI16@16000 -c 1 input.m4a voice/ref.wav
```

3. Write exactly what you said into `voice/ref.txt`.
4. Create the cloud voice clone:

```sh
python cli.py --enroll
```

This stores the returned `reference_id` in `voice/voice_id.txt`; later runs reuse it.

## Keep the prompt (and quota) small

`profile.md` is detailed, so sending it whole on every request wastes tokens and
burns free-tier quota. Instead, `persona.profile_mode: auto` (default) injects a
**condensed summary** (`profile_summary.md`) and keeps the full file on disk:

```sh
python cli.py --condense-profile     # regenerate profile_summary.md from profile.md
```

The summary is generated automatically the first time the server starts (or on
first use) and is regenerated whenever `profile.md` changes. Set
`persona.profile_mode: full` in `config.yaml` to send the whole profile instead.

## Run

```sh
# text in -> your voice out
python cli.py "Bhai, AI tools pe kya scene hai?"

# voice in -> your voice out
python cli.py --audio question.m4a

# don't auto-play
python cli.py "hello" --no-play
```

Output goes to `output/reply.mp3`.

## Web UI (React)

Prefer a GUI? There's a React chat UI in `web/` backed by a small FastAPI server.

**1. Start the backend** (from the project root):

```sh
.venv/bin/python server.py        # http://127.0.0.1:8000
```

**2. Start the React app** (in a second terminal):

```sh
cd web
npm install        # first time only
npm run dev        # http://localhost:5173
```

Open http://localhost:5173 — type or click 🎤 to speak, and get replies in Vikash's
cloned voice with inline playback. Chat history is kept for context.

**Production build** (serve the UI from the backend on a single port):

```sh
cd web && npm run build
cd .. && .venv/bin/python server.py   # now http://127.0.0.1:8000 serves the UI too
```

### 🎙 Train your voice (in the UI)

Header → **Train voice**. The panel shows a Hinglish line to read aloud; hit
**Record**, read it naturally, **Stop**, then **Save & improve voice**. Each clip is
saved to `voice/samples/` and the voice model is **retrained from all samples**
(base `voice/ref.wav` + every recorded clip). More clean clips (and matching
transcripts) = better clone. You can preview and remove samples.

> Fish Audio only *creates* models (it can't update one in place), so each retrain
> builds a fresh model and updates `voice/voice_id.txt`. Free tier allows up to 20
> samples per model. Only clone your own voice.

### 🧠 Self-learning memory (in the UI)

Header → **Memory**. How it works:

- **Every exchange is saved** to `memory/history.jsonl` (question + reply + source).
- Rate replies with the 👍 / 👎 under each answer.
- **Reflect & improve** asks the LLM to read recent exchanges + your feedback and
  rewrite concise *learned notes* into `memory/notes.md`.
- Those notes **and the last few turns are injected into the system prompt**, so the
  agent actually adapts across sessions (voice and text).
- `memory/report.md` is a human-readable record that *validates* improvement: totals,
  positive-feedback %, and a trend (recent 👍 rate vs earlier 👍 rate) — an honest
  signal based on your ratings, not an objective score.

Files (gitignored, stay on your machine): `memory/history.jsonl`, `memory/notes.md`,
`memory/report.md`.

### API endpoints

| Method | Path | Body | Returns |
| --- | --- | --- | --- |
| `POST` | `/api/chat` | `{ "text": "...", "history": [...] }` | `{ id, reply, audio_url, heard }` |
| `POST` | `/api/voice` | multipart `audio` + `history` | `{ id, reply, audio_url, heard }` |
| `GET` | `/api/audio/{name}` | — | the generated `reply_*.mp3` |
| `GET` | `/api/health` | — | `{ status, voice_enrolled }` |
| `GET` | `/api/voice/status` | — | samples, voice id, model state |
| `GET` | `/api/voice/scripts` | `?count=` | random reading prompts |
| `POST` | `/api/voice/train` | multipart `audio` + `text` + `retrain` | `{ sample_id, sample_count, voice_id?, trained_on? }` |
| `DELETE` | `/api/voice/samples/{id}` | — | `{ ok, sample_count }` |
| `GET` | `/api/memory` | — | `{ stats, notes, history }` |
| `POST` | `/api/memory/rate` | `{ id, rating }` | `{ ok, stats }` |
| `POST` | `/api/memory/notes` | `{ text }` | `{ ok, notes }` |
| `POST` | `/api/memory/reflect` | — | `{ ok, notes, stats }` |
| `GET` | `/api/memory/report` | — | `report.md` (markdown) |
| `GET` | `/api/profile` | — | `{ mode, profile, summary }` (file sizes) |
| `POST` | `/api/profile/condense` | — | `{ ok, summary, name, chars, mtime }` |

## Deploy

The app is one container: FastAPI serves the built React UI and talks to the cloud
APIs. `Dockerfile`, `.dockerignore` and `render.yaml` are included.

**Render (recommended)**

1. Push this repo to GitHub.
2. Render → **New → Blueprint** → pick the repo (it reads `render.yaml`).
3. Enter the secrets when prompted: `OPENROUTER_API_KEY`, `GROQ_API_KEY`, `FISH_API_KEY`.
4. Deploy. `render.yaml` sets `VIK_DATA_DIR=/var/data` and mounts a 1 GB disk there,
   so the voice clone, `memory/` and generated audio survive restarts/redeploys.

Run command used in the image: `uvicorn server:app --host 0.0.0.0 --port $PORT`
(single worker, health check `/api/health`).

> ⚠️ **Persistent disks on Render require a paid instance** (Starter+). On the free
> plan the container has no disk, so it works but resets voice/learning on each
> restart or redeploy.

> ℹ️ `voice/` and `memory/` are gitignored (they're personal), so a fresh deploy
> starts empty — open the app and use **Train voice** once to create the clone; it
> is then stored on the disk and reused.

**Local Docker check**

```sh
docker build -t vik-agent .
docker run --rm -p 8000:8000 --env-file .env \
  -v "$PWD/data:/var/data" -e VIK_DATA_DIR=/var/data vik-agent
```

**Other hosts** (Railway, Fly.io, a VPS): the container is portable — mount a
persistent volume and set the same env vars + `VIK_DATA_DIR`. VM/VPS alternative:
run `uvicorn server:app` under systemd behind nginx. Never expose the free API keys
to untrusted public traffic (quotas are per key).

## Files you edit

- `context.md` — persona guide (already written).
- `profile.md` — identity/background details.
- `profile_summary.md` — auto-generated condensed profile injected into the prompt.
- `config.yaml` — providers, models, paths.
- `voice/ref.wav` + `voice/ref.txt` — reference voice + transcript.
- `voice/samples/` — extra clips recorded from the UI (LLM/voice training).
- `memory/` — self-learning log + notes + report (auto-managed).
- `.env` — your API keys (never commit this).

## Notes

- Free tiers have rate/credit limits; short replies keep usage low.
- Fish Audio free tier provides a few public voice slots and commercial use.
- Only clone your own voice, or a voice you have clear permission to use.

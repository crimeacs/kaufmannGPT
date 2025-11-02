## Agents Overview

This project is an AI stand‑up comedy system composed of cooperating agents (microservices) that generate jokes and analyze audience reactions in real time using OpenAI's Realtime API. It also includes a lightweight frontend for observability and manual control.

Refer to the detailed guides in `README.md`, `REALTIME_API_GUIDE.md`, and `DOCKER_README.md` for deeper dives. This document focuses on how the agents work together.

### High‑Level Architecture

```
┌─────────────────────────────────────────────┐
│  Frontend (Port 3000 → host 3002)           │
│  - Real‑time logs (SSE)                     │
│  - Service health + controls                │
│  - API testing + auto‑performance           │
└───────────────┬─────────────────────────────┘
                │ HTTP (REST) + SSE
    ┌───────────┴────────────┐
    │                        │
    ▼                        ▼
┌─────────────┐         ┌──────────────┐
│  Audience   │         │    Joke      │
│  Service    │         │  Service     │
│  (8000→8002)│         │  (8001→8003) │
└──────┬──────┘         └──────┬───────┘
       │ WebSocket (OpenAI Realtime API)
       └───────────► wss://api.openai.com/v1/realtime
```

Notes on ports:
- In Docker: containers listen on 8000 (audience) and 8001 (joke), mapped to 8002 and 8003 on the host. The frontend runs on container 3000 mapped to host 3002. See `docker-compose.yml`.
- When running locally without Docker, hit services on `http://localhost:8000` and `http://localhost:8001`.

## Components

### Audience Analysis Agent (FastAPI)
- File: `src/api/audience_service.py`
- Purpose: Ingests audio (base64 PCM16) and determines audience state (`is_laughing`, `reaction_type`, `confidence`, `description`).
- Realtime mode: `WebSocket /ws/analyze` streams audio chunks to OpenAI Realtime API and streams back JSON analyses.
- Stores: Latest reaction + a deque history (last 100).
- Exposes real‑time logs via SSE at `GET /stream/logs` for the frontend.

Key endpoints:
- `POST /analyze` — Analyze a base64 PCM16 chunk.
- `POST /analyze-file` — Analyze an uploaded audio file.
- `GET /latest` — Return the most recent reaction (consumed by the joke service).
- `GET /history` — Return recent reactions.
- `WebSocket /ws/analyze` — Continuous analysis stream.
- `GET /health` — Health check.

Internals:
- Uses `src/audience_analyzer/realtime_analyzer.py` to connect to OpenAI Realtime API via WebSocket (`gpt-realtime` by default).
- Session can be configured with stored prompts (`audience_prompt_id`) for consistent JSON output; fallback to inline instructions if unset.

### Joke Generation Agent (FastAPI)
- File: `src/api/joke_service.py`
- Purpose: Generates jokes tailored to the current audience reaction and returns both text and synthesized speech (PCM16).
- Coordinates with the audience agent by fetching `GET /latest` (configurable via `AUDIENCE_SERVICE_URL`).
- Exposes real‑time logs via SSE at `GET /stream/logs`.

Key endpoints:
- `POST /generate` — Generate a joke; returns text and optionally base64 audio.
- `POST /generate/audio` — Generate and return PCM16 audio file directly.
- `POST /generate/auto` — Auto‑fetch latest reaction from the audience service, then generate.
- `GET /stats` — Performance stats (e.g., engagement rate based on stored history).
- `POST /reset` — Reset in‑memory generator state/history.
- `WebSocket /ws/perform` — Stream of audience reactions in, jokes out.
- `GET /health` — Health check.

Internals:
- Uses `src/joke_generator/realtime_generator.py` to connect to OpenAI Realtime API via WebSocket.
- Session supports stored prompts (`joke_prompt_id`) with variables injected each run: `audience_reaction`, `comedy_style`, `theme`.
- Streams text (`response.text.delta`) and audio (`response.audio.delta`) and assembles a final response with timestamp and audio bytes.

### Frontend Debug Console
- Directory: `frontend/`
- Purpose: Single‑page observability and control panel.
- Features:
  - Service health indicators
  - Live logs from both services (SSE)
  - Forms to call each API endpoint
  - Auto‑performance mode (continuous loop of analyze→generate)

Build/serve:
- In Docker, Nginx serves the built assets on container port 3000 (host 3002).
- Locally, Vite dev server on 3000 (see `frontend/package.json`, `vite.config.js`).

## Runtime Flow

There are two main operating modes.

### 1) Realtime Streaming (Recommended)
1. Frontend (or client) captures/streams audience audio over `WebSocket /ws/analyze` to the audience service.
2. Audience service forwards audio to OpenAI Realtime API and receives incremental text responses that parse to JSON with reaction fields.
3. Audience service updates its `latest` state and SSE logs.
4. Joke service (via `POST /generate/auto`) fetches `GET /latest`, configures its Realtime session (voice, prompt, variables), and requests a model response.
5. Joke service receives streaming text + audio; returns the aggregated text and base64 audio (or a direct PCM file from `/generate/audio`).
6. Frontend displays text and can play audio; logs flow to the UI via SSE.

### 2) Legacy/Batch (Non‑Realtime)
- The audience service can analyze discrete audio chunks via `POST /analyze`.
- The joke service can generate based on a specified reaction via `POST /generate`.

## APIs and Events (OpenAI Realtime)

- Upstream WebSocket: `wss://api.openai.com/v1/realtime?model=gpt-realtime`
- Required headers: `Authorization: Bearer <OPENAI_API_KEY>`, `OpenAI-Beta: realtime=v1`
- Common events used by agents:
  - `session.update` — Configure modalities, voice, prompt, variables
  - `conversation.item.create` — Add user text to the conversation
  - `input_audio_buffer.append` / `commit` — Stream audience audio
  - `response.create` — Request a new model response
  - `response.text.delta` / `.done` — Streaming/complete text
  - `response.audio.delta` / `.done` — Streaming/complete audio

See `REALTIME_API_GUIDE.md` for detailed payload shapes and best practices.

## Configuration

All core settings live in `config.yaml`:

- `openai_api_key`: API key (or use env `OPENAI_API_KEY`)
- `joke_model`, `audience_model`: Typically `gpt-realtime`
- `joke_prompt_id`, `audience_prompt_id`: Stored prompt IDs (optional)
- `voice`: Realtime voice (e.g., alloy, ash, ballad, echo, shimmer, verse, marin, cedar)
- `initial_theme`, `comedy_style`: Defaults for joke generation
- `analysis_interval`, `joke_interval`, `max_jokes`: Performance pacing
- Logging and audio options

Environment variables:
- `OPENAI_API_KEY`: Required at runtime unless set in `config.yaml`
- `AUDIENCE_SERVICE_URL`: Joke service uses this to reach audience service (Docker default: `http://audience-service:8000`)

## Running the System

### Docker (recommended)

```bash
export OPENAI_API_KEY="your-key"
./start.sh
# Frontend: http://localhost:3002
# Audience API: http://localhost:8002
# Joke API:     http://localhost:8003
```

### Local (without Docker)

```bash
export OPENAI_API_KEY="your-key"

# Audience service (port 8000)
python -m uvicorn src.api.audience_service:app --reload --host 0.0.0.0 --port 8000

# Joke service (port 8001)
python -m uvicorn src.api.joke_service:app --reload --host 0.0.0.0 --port 8001

# Frontend (dev server, port 3000)
cd frontend && npm install && npm run dev
```

### Demos
- `python realtime_demo.py` — Demonstrates end‑to‑end Realtime usage
- `example_usage.py` — Legacy/REST examples

## Observability

- Logs: `GET /stream/logs` on both services (SSE). The frontend subscribes and renders color‑coded streams.
- Health: `GET /health` on both services.
- Stats: `GET /stats` on the joke service.

## Extending the Agents

- Prompts: Create stored prompts at the OpenAI platform and set their IDs in `config.yaml` for versioned, centrally managed behavior with variable substitution.
- Voices: Change `voice` in `config.yaml` to alter delivery style.
- Themes/Style: Update `initial_theme` and `comedy_style` to set defaults; pass `theme` per request.
- Frontend: Extend `frontend/app.js` and `frontend/index.html` to add controls, presets, or visualization.

## Security & Reliability Notes

- API key should be provided via environment variables in production.
- Services implement structured error responses and timeouts for upstream calls.
- Docker Compose config sets health checks and restart policies.

---

For deeper technical details and payload examples, see:
- `README.md` — Full project overview and usage
- `REALTIME_API_GUIDE.md` — Realtime protocol events and examples
- `IMPLEMENTATION_SUMMARY.md` — What was built and why
- `DOCKER_README.md` — Containerization details and troubleshooting



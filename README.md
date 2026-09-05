# Glancy — Voice RAG Chatbot

Browser voice assistant powered by **Pipecat**, with answers grounded in the
[Glancy Fawcett](https://www.glancyfawcett.com/) website knowledge base stored in **Chroma**.

## Stack

| Layer | Choice |
|--------|--------|
| Voice pipeline | Pipecat |
| Transport | SmallWebRTC (local browser) |
| STT / TTS | Deepgram Nova / Aura |
| LLM | Groq |
| Embeddings | Ollama `nomic-embed-text` (local) |
| Vector DB | Chroma (local retriever) |
| API | FastAPI |
| Frontend | React + Vite (`frontend/`) |

## Directory layout

```
bot/           # Voice bot, prompts, Q&A, RAG tool
kb/            # Website crawl, chunk, embed, Chroma retrieve
api/           # FastAPI: /health, /ingest, /search, /ask
frontend/      # React voice UI (Connect / transcript)
data/chroma/   # Local Chroma persistence
```

## Prerequisites

1. Python 3.11+
2. Node.js 18+
3. [Ollama](https://ollama.com/) running locally with embeddings:

```bash
ollama pull nomic-embed-text
```

4. API keys in `.env`:
   - `GROQ_API_KEY` — text Q&A and voice LLM
   - `DEEPGRAM_API_KEY` — voice STT + TTS

## Setup

```bash
cd /var/www/html/ai_agents/glancy
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env: set GROQ_API_KEY and DEEPGRAM_API_KEY

cd frontend
npm install
cp .env.example .env
```

> If `pip` fails due to a local proxy, install with:  
> `HTTP_PROXY= HTTPS_PROXY= pip install -r requirements.txt`

## Ingest the website

```bash
source .venv/bin/activate
python -m kb.ingest
```

## Text API

```bash
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

- `GET /health`
- `POST /ingest`
- `GET /search?q=showrooms&k=5`
- `POST /ask` — Chroma retrieve + Groq

```bash
curl -X POST http://127.0.0.1:8000/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"Where is the Manchester showroom?","k":5}'
```

## Voice bot + browser UI

Requires ingested Chroma data, Ollama for query embeddings, plus Groq + Deepgram keys.

**Terminal 1 — bot**

```bash
source .venv/bin/activate
python -m bot.main
# or: python -m bot.main -t webrtc
```

**Terminal 2 — frontend**

```bash
cd frontend
npm run dev
```

Open **http://localhost:5173**, click **Connect**, allow the microphone, and talk.

The Vite app proxies `/api` to the bot at `http://localhost:7860` (signaling at `/api/offer`). You can still use the built-in Pipecat client at `http://localhost:7860/client` if needed.

## Knowledge-base / voice flow

1. Crawl + chunk website → Chroma (Ollama embeddings)
2. Text: `POST /ask` retrieves then generates with Groq
3. Voice: browser → SmallWebRTC → Deepgram STT → Groq (+ `search_site_kb`) → Deepgram TTS → speaker

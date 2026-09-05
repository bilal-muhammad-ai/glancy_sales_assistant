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
| Frontend | Pipecat runner client (custom React later) |

## Directory layout

```
bot/           # Voice bot, prompts, Q&A, RAG tool
kb/            # Website crawl, chunk, embed, Chroma retrieve
api/           # FastAPI: /health, /ingest, /search, /ask
frontend/      # Custom browser UI (later)
data/chroma/   # Local Chroma persistence
```

## Prerequisites

1. Python 3.11+
2. [Ollama](https://ollama.com/) running locally with embeddings:

```bash
ollama pull nomic-embed-text
```

3. API keys in `.env`:
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

## Voice bot (Pipecat)

Requires ingested Chroma data, Ollama for query embeddings, plus Groq + Deepgram keys.

```bash
source .venv/bin/activate
python -m bot.main
```

Then open the Pipecat client (typically **http://localhost:7860/client**), allow the microphone, and talk.

The bot greets you, uses Deepgram for speech in/out, Groq for replies, and calls `search_site_kb` (Chroma) for factual Glancy Fawcett questions.

If the runner expects an explicit transport flag:

```bash
python -m bot.main -t webrtc
```

## Knowledge-base / voice flow

1. Crawl + chunk website → Chroma (Ollama embeddings)
2. Text: `POST /ask` retrieves then generates with Groq
3. Voice: mic → Deepgram STT → Groq (+ optional `search_site_kb`) → Deepgram TTS → speaker

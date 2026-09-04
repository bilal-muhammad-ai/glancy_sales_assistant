# Glancy — Voice RAG Chatbot

Browser voice assistant powered by **Pipecat**, with answers grounded in the
[Glancy Fawcett](https://www.glancyfawcett.com/) website knowledge base stored in **Chroma**.

## Stack

| Layer | Choice |
|--------|--------|
| Voice pipeline | Pipecat (later) |
| Transport | Daily / WebRTC (later) |
| STT / TTS | Deepgram / Cartesia (later) |
| LLM | Groq |
| Embeddings | **Ollama** `nomic-embed-text` (local) |
| Vector DB | Chroma (local retriever) |
| API | FastAPI |
| Frontend | React (later) |

## Directory layout

```
bot/           # Prompts, Q&A, Pipecat tools
kb/            # Website crawl, chunk, embed, Chroma retrieve
api/           # FastAPI: /health, /ingest, /search, /ask
frontend/      # Browser mic / speaker UI
data/chroma/   # Local Chroma persistence
```

## Prerequisites

1. Python 3.11+
2. [Ollama](https://ollama.com/) running locally
3. Embedding model pulled:

```bash
ollama pull nomic-embed-text
```

4. A **Groq API key** for text Q&A (`GROQ_API_KEY` in `.env`)

## Setup

```bash
cd /var/www/html/ai_agents/glancy
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env and set GROQ_API_KEY
```

## Ingest the website (~253 pages from sitemap)

```bash
source .venv/bin/activate
python -m kb.ingest
```

This crawls `SITE_BASE_URL`, chunks pages, embeds with Ollama, and rebuilds the Chroma collection.

## API

```bash
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

- `GET /health` — config check
- `POST /ingest` — full re-crawl and reindex
- `GET /search?q=showrooms&k=5` — Chroma similarity search
- `POST /ask` — text Q&A (Chroma retrieve + Groq)

### Search

```bash
curl "http://127.0.0.1:8000/search?q=Manchester%20showroom"
```

### Ask (RAG)

```bash
curl -X POST http://127.0.0.1:8000/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"Where is the Manchester showroom?","k":5}'
```

Returns `answer` plus `sources` (URLs from the knowledge base).

## Knowledge-base / Q&A flow

1. Load URLs from `sitemap.xml` (+ BFS for any extras)
2. Fetch HTML, extract main text
3. Chunk (~500 words, 100 overlap)
4. Embed with Ollama `nomic-embed-text`
5. Store / retrieve via Chroma (`retrieve` / `GET /search`)
6. `POST /ask` retrieves chunks, then Groq answers from that context only

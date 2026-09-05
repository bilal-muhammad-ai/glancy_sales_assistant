"""FastAPI app: health, ingest, search, and text Q&A."""

from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from bot.qa import GroqNotConfiguredError, ask
from kb.chroma_store import retrieve
from kb.ingest import ingest
from kb.settings import get_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Glancy KB API", version="0.1.0")


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1)
    k: int = Field(2, ge=1, le=10)


@app.get("/health")
def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "site_base_url": settings.site_base_url,
        "chroma_collection": settings.chroma_collection,
        "ollama_embed_model": settings.ollama_embed_model,
        "groq_model": settings.groq_model,
        "groq_configured": bool(settings.groq_api_key.strip()),
        "deepgram_configured": bool(settings.deepgram_api_key.strip()),
    }


@app.post("/ingest")
async def run_ingest() -> dict:
    try:
        stats = await ingest()
    except Exception as exc:
        logger.exception("Ingest failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"ok": True, **stats}


@app.get("/search")
def search(
    q: str = Query(..., min_length=1, description="Search query"),
    k: int = Query(5, ge=1, le=20),
) -> dict:
    hits = retrieve(q, k=k)
    return {"query": q, "count": len(hits), "results": hits}


@app.post("/ask")
def run_ask(body: AskRequest) -> dict:
    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=422, detail="question must not be empty")
    try:
        return ask(question, k=body.k)
    except GroqNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Ask failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

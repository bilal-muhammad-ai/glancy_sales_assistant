"""FastAPI app: health, ingest, and Chroma search."""

from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Query

from kb.chroma_store import retrieve
from kb.ingest import ingest
from kb.settings import get_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Glancy KB API", version="0.1.0")


@app.get("/health")
def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "site_base_url": settings.site_base_url,
        "chroma_collection": settings.chroma_collection,
        "ollama_embed_model": settings.ollama_embed_model,
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

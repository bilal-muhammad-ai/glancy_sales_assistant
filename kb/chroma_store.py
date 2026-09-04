"""Chroma persistence with Ollama embeddings and similarity retrieve."""

from __future__ import annotations

import logging
from typing import Any

import chromadb
from chromadb.api.models.Collection import Collection
from chromadb.utils.embedding_functions import OllamaEmbeddingFunction

from kb.settings import Settings, get_settings

logger = logging.getLogger(__name__)


def _embedding_function(settings: Settings) -> OllamaEmbeddingFunction:
    return OllamaEmbeddingFunction(
        url=settings.ollama_base_url.rstrip("/"),
        model_name=settings.ollama_embed_model,
    )


def get_client(settings: Settings | None = None) -> chromadb.PersistentClient:
    settings = settings or get_settings()
    return chromadb.PersistentClient(path=settings.chroma_path)


def get_collection(settings: Settings | None = None) -> Collection:
    settings = settings or get_settings()
    client = get_client(settings)
    return client.get_or_create_collection(
        name=settings.chroma_collection,
        embedding_function=_embedding_function(settings),
        metadata={"hnsw:space": "cosine"},
    )


def reset_collection(settings: Settings | None = None) -> Collection:
    """Delete the collection if it exists, then create a fresh one."""
    settings = settings or get_settings()
    client = get_client(settings)
    try:
        client.delete_collection(settings.chroma_collection)
        logger.info("Deleted collection %s", settings.chroma_collection)
    except Exception:
        pass
    return get_collection(settings)


def add_documents(
    ids: list[str],
    documents: list[str],
    metadatas: list[dict[str, Any]],
    settings: Settings | None = None,
    batch_size: int = 32,
) -> None:
    """Embed and upsert documents into Chroma in small batches."""
    if not ids:
        return
    collection = get_collection(settings)
    for start in range(0, len(ids), batch_size):
        end = start + batch_size
        collection.upsert(
            ids=ids[start:end],
            documents=documents[start:end],
            metadatas=metadatas[start:end],
        )
        logger.info("Upserted chunks %s–%s", start + 1, min(end, len(ids)))


def retrieve(query: str, k: int = 5, settings: Settings | None = None) -> list[dict[str, Any]]:
    """Similarity search via Chroma; returns text, url, title, distance."""
    collection = get_collection(settings)
    if collection.count() == 0:
        return []

    result = collection.query(
        query_texts=[query],
        n_results=min(k, collection.count()),
        include=["documents", "metadatas", "distances"],
    )

    hits: list[dict[str, Any]] = []
    docs = (result.get("documents") or [[]])[0]
    metas = (result.get("metadatas") or [[]])[0]
    distances = (result.get("distances") or [[]])[0]

    for text, meta, distance in zip(docs, metas, distances):
        meta = meta or {}
        hits.append(
            {
                "text": text or "",
                "url": meta.get("url", ""),
                "title": meta.get("title", ""),
                "chunk_index": meta.get("chunk_index"),
                "distance": distance,
            }
        )
    return hits

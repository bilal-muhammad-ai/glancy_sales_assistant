"""Retrieve-then-generate Q&A using Chroma + Groq."""

from __future__ import annotations

import logging
from typing import Any

from groq import Groq

from bot.prompts import SYSTEM_PROMPT
from kb.chroma_store import retrieve
from kb.settings import get_settings

logger = logging.getLogger(__name__)


class GroqNotConfiguredError(RuntimeError):
    """Raised when GROQ_API_KEY is missing."""


def build_context(hits: list[dict[str, Any]]) -> str:
    """Format retrieved chunks into a single context block."""
    if not hits:
        return "No relevant documents found."

    parts: list[str] = []
    for hit in hits:
        title = hit.get("title") or "Untitled"
        url = hit.get("url") or ""
        text = hit.get("text") or ""
        parts.append(f"Source: {title}\nURL: {url}\n{text}")
    return "\n\n---\n\n".join(parts)


def build_sources(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplicate hits by URL, keeping the best (lowest) distance."""
    best: dict[str, dict[str, Any]] = {}
    for hit in hits:
        url = hit.get("url") or ""
        if not url:
            continue
        distance = hit.get("distance")
        existing = best.get(url)
        if existing is None or (
            distance is not None
            and (existing.get("distance") is None or distance < existing["distance"])
        ):
            best[url] = {
                "url": url,
                "title": hit.get("title") or "",
                "distance": distance,
            }
    return list(best.values())


def ask(question: str, k: int = 5) -> dict[str, Any]:
    """Retrieve site chunks, ask Groq, return answer + sources."""
    settings = get_settings()
    if not settings.groq_api_key.strip():
        raise GroqNotConfiguredError("GROQ_API_KEY is not set")

    hits = retrieve(question, k=k, settings=settings)
    context = build_context(hits)
    sources = build_sources(hits)

    user_content = (
        f"Website context:\n{context}\n\n"
        f"Question: {question.strip()}\n\n"
        "Answer the question using only the website context above."
    )

    client = Groq(api_key=settings.groq_api_key)
    completion = client.chat.completions.create(
        model=settings.groq_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0.2,
        max_tokens=2048,
    )

    answer = (completion.choices[0].message.content or "").strip()
    logger.info("Answered question with %s sources", len(sources))
    return {
        "question": question.strip(),
        "answer": answer,
        "sources": sources,
    }

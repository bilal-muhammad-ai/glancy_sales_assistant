"""search_site_kb tool — query Chroma and return chunks."""

from __future__ import annotations

from kb.chroma_store import retrieve


def format_hits(hits: list[dict], limit: int | None = None) -> str:
    """Turn retrieve() hits into a readable context string."""
    if not hits:
        return "No relevant documents found."
    selected = hits if limit is None else hits[:limit]
    parts = []
    for hit in selected:
        title = hit.get("title") or "Untitled"
        url = hit.get("url") or ""
        text = hit.get("text") or ""
        parts.append(f"Source: {title}\nURL: {url}\n{text}")
    return "\n\n---\n\n".join(parts)


def query_site_kb(query: str, k: int = 5) -> str:
    """Search the website knowledge base and return relevant passages."""
    hits = retrieve(query, k=k)
    return format_hits(hits)


# Backwards-compatible alias for earlier imports.
search_site_kb_sync = query_site_kb


async def search_site_kb(params, query: str, k: int = 5) -> None:
    """Search the Glancy Fawcett website knowledge base.

    Use this for factual questions about the company, showrooms, products,
    brands, services, FAQs, history, or team.

    Args:
        query: Natural-language search query derived from the user's question.
        k: Maximum number of passages to return (1–10). Prefer 5.
    """
    from pipecat.services.llm_service import FunctionCallParams

    assert isinstance(params, FunctionCallParams)
    k = max(1, min(int(k), 10))
    result = query_site_kb(query, k=k)
    await params.result_callback({"result": result})

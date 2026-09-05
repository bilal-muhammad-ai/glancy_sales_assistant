"""search_site_kb tool — query Chroma and return chunks."""

from __future__ import annotations

import asyncio
from typing import Any

from kb.chroma_store import retrieve

# Keep tool payloads under Groq on-demand TPM (~8k for gpt-oss-120b).
DEFAULT_K = 2
MAX_K = 3
MAX_CHARS_PER_HIT = 800  # ~200 tokens; 2 hits ≈ under ~500 tokens of KB text
MAX_SEARCHES_PER_TURN = 1
RETRIEVE_TIMEOUT_SECS = 8.0

_ALREADY_SEARCHED_MSG = (
    "Knowledge base already searched this turn. "
    "Answer now from the earlier tool result, or say you do not know. "
    "Do not call search_site_kb again."
)


def format_hits(
    hits: list[dict],
    limit: int | None = None,
    *,
    max_chars: int = MAX_CHARS_PER_HIT,
) -> str:
    """Turn retrieve() hits into a readable context string."""
    if not hits:
        return "No relevant documents found."
    selected = hits if limit is None else hits[:limit]
    parts = []
    for hit in selected:
        title = hit.get("title") or "Untitled"
        url = hit.get("url") or ""
        text = hit.get("text") or ""
        if max_chars > 0 and len(text) > max_chars:
            text = text[:max_chars].rstrip() + "…"
        parts.append(f"Source: {title}\nURL: {url}\n{text}")
    return "\n\n---\n\n".join(parts)


def query_site_kb(query: str, k: int = DEFAULT_K) -> str:
    """Search the website knowledge base and return relevant passages."""
    hits = retrieve(query, k=k)
    return format_hits(hits)


# Backwards-compatible alias for earlier imports.
search_site_kb_sync = query_site_kb


def _role(msg: Any) -> str | None:
    if isinstance(msg, dict):
        role = msg.get("role")
        return role if isinstance(role, str) else None
    return None


def _searches_this_turn(context: Any) -> int:
    """Count tool results after the latest user message (current turn)."""
    get_messages = getattr(context, "get_messages", None)
    if not callable(get_messages):
        return 0
    messages = get_messages() or []
    last_user = -1
    for i, msg in enumerate(messages):
        if _role(msg) == "user":
            last_user = i
    if last_user < 0:
        return 0
    return sum(1 for msg in messages[last_user + 1 :] if _role(msg) == "tool")


async def search_site_kb(params, query: str, k: int = DEFAULT_K) -> None:
    """Search the Glancy Fawcett website knowledge base.

    Use this for factual questions about the company, showrooms, products,
    brands, services, FAQs, history, or team. Call at most once per user turn.

    Args:
        query: Natural-language search query derived from the user's question.
        k: Maximum number of passages to return (1–3). Prefer 2.
    """
    from pipecat.services.llm_service import FunctionCallParams

    from bot.debug_log import dbg

    assert isinstance(params, FunctionCallParams)
    k = max(1, min(int(k), MAX_K))

    prior = _searches_this_turn(params.context)
    # #region agent log
    dbg(
        "B",
        "search_kb.py:entry",
        "tool_start",
        {"query": query[:120], "k": k, "prior_searches": prior},
    )
    # #endregion
    if prior >= MAX_SEARCHES_PER_TURN:
        # #region agent log
        dbg("B", "search_kb.py:capped", "tool_capped", {"prior_searches": prior})
        # #endregion
        await params.result_callback({"result": _ALREADY_SEARCHED_MSG})
        return

    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(query_site_kb, query, k),
            timeout=RETRIEVE_TIMEOUT_SECS,
        )
        # #region agent log
        dbg(
            "B",
            "search_kb.py:before_callback",
            "tool_ok",
            {"result_chars": len(result), "result_preview": result[:160]},
        )
        # #endregion
        await params.result_callback({"result": result})
        # #region agent log
        dbg("B", "search_kb.py:after_callback", "result_callback_done", {})
        # #endregion
    except TimeoutError:
        # #region agent log
        dbg("B", "search_kb.py:timeout", "tool_timeout", {"timeout_s": RETRIEVE_TIMEOUT_SECS})
        # #endregion
        await params.result_callback(
            {
                "result": (
                    "Knowledge-base search timed out. "
                    "Say briefly that you could not look that up right now."
                )
            }
        )
    except Exception as exc:
        # #region agent log
        dbg(
            "B",
            "search_kb.py:error",
            "tool_exception",
            {"error": str(exc), "type": type(exc).__name__},
        )
        # #endregion
        raise

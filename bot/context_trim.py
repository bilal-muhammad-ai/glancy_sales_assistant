"""Keep voice LLM context under Groq TPM limits."""

from __future__ import annotations

from typing import Any

from pipecat.frames.frames import Frame, LLMContextFrame
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from bot.debug_log import dbg

# Keep the current user turn intact; only drop older turns.
MAX_USER_TURNS = 2
TOOL_STUB = "[Earlier knowledge-base result omitted to save context.]"


def _role(message: Any) -> str | None:
    if isinstance(message, dict):
        role = message.get("role")
        return role if isinstance(role, str) else None
    return None


def _shrink_tools_before_index(messages: list[Any], cutoff: int) -> list[Any]:
    """Stub tool payloads that belong to older turns only."""
    out: list[Any] = []
    for i, msg in enumerate(messages):
        if i >= cutoff or not isinstance(msg, dict) or _role(msg) != "tool":
            out.append(msg)
            continue
        shrunk = dict(msg)
        shrunk["content"] = TOOL_STUB
        out.append(shrunk)
    return out


def trim_messages(
    messages: list[Any],
    *,
    max_user_turns: int = MAX_USER_TURNS,
) -> list[Any]:
    """Preserve system/developer + the last N user turns completely.

    Never stubs tool results from the current turn (after the latest user
    message). Stubbing those caused the model to re-call search_site_kb in a
    loop and eventually drop the user question from context.
    """
    if not messages:
        return messages

    head: list[Any] = []
    rest: list[Any] = []
    for msg in messages:
        if not rest and _role(msg) in ("system", "developer"):
            head.append(msg)
        else:
            rest.append(msg)

    user_idxs = [i for i, m in enumerate(rest) if _role(m) == "user"]
    if not user_idxs:
        # No user turn yet (e.g. greeting) — leave as-is.
        return head + rest

    # user_idxs[-2] raises IndexError when there is only one user message.
    turns = max(1, min(max_user_turns, len(user_idxs)))
    keep_from = user_idxs[-turns]
    last_user = user_idxs[-1]
    older = rest[:keep_from]
    kept = rest[keep_from:]

    # Stub tools only in turns before the most recent user message.
    # Relative to `kept`, that cutoff is (last_user - keep_from).
    cutoff_in_kept = last_user - keep_from
    kept = _shrink_tools_before_index(kept, cutoff_in_kept)

    # Drop orphan leading tool messages if any remain.
    while kept and _role(kept[0]) == "tool":
        kept.pop(0)

    # Older history outside the kept window is discarded entirely (safer than
    # keeping stubbed tool loops that confuse the model).
    _ = older
    return head + kept


class ContextTrimProcessor(FrameProcessor):
    """Trim shared LLMContext in-place before each LLM run."""

    def __init__(self, context: LLMContext, **kwargs):
        super().__init__(**kwargs)
        self._context = context

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, LLMContextFrame):
            # #region agent log
            before = self._context.get_messages()
            before_roles = [
                (m.get("role") if isinstance(m, dict) else type(m).__name__) for m in before
            ]
            # #endregion
            self._context.transform_messages(trim_messages)
            # #region agent log
            after = self._context.get_messages()
            after_roles = [
                (m.get("role") if isinstance(m, dict) else type(m).__name__) for m in after
            ]
            tool_lens = []
            stubbed = 0
            for m in after:
                if isinstance(m, dict) and m.get("role") == "tool":
                    content = m.get("content") or ""
                    if isinstance(content, str):
                        tool_lens.append(len(content))
                        if content.startswith("[Earlier knowledge-base"):
                            stubbed += 1
            has_user = any(r == "user" for r in after_roles)
            dbg(
                "D",
                "context_trim.py:trim",
                "context_trimmed",
                {
                    "direction": str(direction),
                    "before_n": len(before),
                    "after_n": len(after),
                    "before_roles": before_roles,
                    "after_roles": after_roles,
                    "tool_content_lens": tool_lens,
                    "stubbed_tools": stubbed,
                    "has_user": has_user,
                    "runId": "post-fix",
                },
            )
            # #endregion
        await self.push_frame(frame, direction)

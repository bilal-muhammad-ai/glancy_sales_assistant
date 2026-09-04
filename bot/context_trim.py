"""Keep voice LLM context under Groq TPM limits."""

from __future__ import annotations

from typing import Any

from pipecat.frames.frames import Frame, LLMContextFrame
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

# Keep recent turns; older tool payloads are the usual token blow-up.
MAX_CONTEXT_MESSAGES = 16
KEEP_FULL_TOOL_RESULTS = 1
TOOL_STUB = "[Earlier knowledge-base result omitted to save context.]"


def _role(message: Any) -> str | None:
    if isinstance(message, dict):
        role = message.get("role")
        return role if isinstance(role, str) else None
    return None


def _shrink_old_tool_results(messages: list[Any], keep_last: int) -> list[Any]:
    tool_idxs = [i for i, m in enumerate(messages) if _role(m) == "tool"]
    drop = set(tool_idxs[:-keep_last] if keep_last > 0 else tool_idxs)
    if not drop:
        return messages

    out: list[Any] = []
    for i, msg in enumerate(messages):
        if i not in drop or not isinstance(msg, dict):
            out.append(msg)
            continue
        shrunk = dict(msg)
        shrunk["content"] = TOOL_STUB
        out.append(shrunk)
    return out


def trim_messages(
    messages: list[Any],
    *,
    max_messages: int = MAX_CONTEXT_MESSAGES,
    keep_full_tool_results: int = KEEP_FULL_TOOL_RESULTS,
) -> list[Any]:
    """Preserve system/developer prefix, then keep the newest messages.

    Drops orphan leading tool messages after a cut, and stubs older tool
    results so prior KB dumps do not accumulate past Groq TPM limits.
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

    budget = max(0, max_messages - len(head))
    kept = rest[-budget:] if budget else []

    while kept and _role(kept[0]) == "tool":
        kept.pop(0)

    return head + _shrink_old_tool_results(kept, keep_full_tool_results)


class ContextTrimProcessor(FrameProcessor):
    """Trim shared LLMContext in-place before each LLM run."""

    def __init__(self, context: LLMContext, **kwargs):
        super().__init__(**kwargs)
        self._context = context

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, LLMContextFrame):
            self._context.transform_messages(trim_messages)
        await self.push_frame(frame, direction)

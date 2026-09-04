"""Split page text into overlapping chunks (word-based, simple)."""

from __future__ import annotations

from kb.settings import get_settings


def chunk_text(
    text: str,
    chunk_size: int | None = None,
    overlap: int | None = None,
) -> list[str]:
    """Split text into overlapping chunks by word count (~token-sized for English)."""
    settings = get_settings()
    size = chunk_size or settings.chunk_size_tokens
    overlap_words = overlap if overlap is not None else settings.chunk_overlap_tokens
    if overlap_words >= size:
        raise ValueError("chunk overlap must be smaller than chunk size")

    words = text.split()
    if not words:
        return []
    if len(words) <= size:
        return [" ".join(words)]

    chunks: list[str] = []
    start = 0
    step = size - overlap_words
    while start < len(words):
        end = min(start + size, len(words))
        piece = " ".join(words[start:end]).strip()
        if piece:
            chunks.append(piece)
        if end >= len(words):
            break
        start += step
    return chunks

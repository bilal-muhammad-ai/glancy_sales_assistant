"""Crawl the site, chunk pages, and reindex Chroma."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import sys

from kb.chroma_store import add_documents, reset_collection
from kb.chunk import chunk_text
from kb.crawl import discover_and_crawl
from kb.settings import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _chunk_id(url: str, index: int) -> str:
    digest = hashlib.sha1(f"{url}::{index}".encode()).hexdigest()[:16]
    return f"{digest}_{index}"


async def ingest() -> dict[str, int]:
    """Wipe Chroma, crawl the site, chunk, and upsert. Returns counts."""
    settings = get_settings()
    pages = await discover_and_crawl(settings)

    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict] = []

    for url, (title, text) in sorted(pages.items()):
        chunks = chunk_text(text)
        for index, chunk in enumerate(chunks):
            ids.append(_chunk_id(url, index))
            documents.append(chunk)
            metadatas.append(
                {
                    "url": url,
                    "title": title or "",
                    "chunk_index": index,
                }
            )

    reset_collection(settings)
    add_documents(ids, documents, metadatas, settings=settings)

    stats = {
        "pages": len(pages),
        "chunks": len(documents),
        "errors": 0,
    }
    logger.info(
        "Ingest complete: %s pages → %s chunks into %s",
        stats["pages"],
        stats["chunks"],
        settings.chroma_collection,
    )
    return stats


def main() -> None:
    try:
        stats = asyncio.run(ingest())
    except KeyboardInterrupt:
        logger.error("Ingest cancelled")
        sys.exit(130)
    except Exception:
        logger.exception("Ingest failed")
        sys.exit(1)
    print(f"pages={stats['pages']} chunks={stats['chunks']}")


if __name__ == "__main__":
    main()

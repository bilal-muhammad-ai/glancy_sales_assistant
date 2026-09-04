"""search_site_kb tool — query Chroma and return chunks."""

from kb.chroma_store import retrieve


def search_site_kb(query: str, k: int = 5) -> str:
    """Search the website knowledge base and return relevant passages."""
    hits = retrieve(query, k=k)
    if not hits:
        return "No relevant documents found."
    parts = []
    for hit in hits:
        title = hit.get("title") or "Untitled"
        url = hit.get("url") or ""
        text = hit.get("text") or ""
        parts.append(f"Source: {title}\nURL: {url}\n{text}")
    return "\n\n---\n\n".join(parts)

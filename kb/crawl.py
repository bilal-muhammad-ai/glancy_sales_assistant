"""Website crawl helpers: discover URLs, fetch pages, extract text."""

from __future__ import annotations

import asyncio
import logging
import re
import xml.etree.ElementTree as ET
from collections import deque
from typing import Iterable
from urllib.parse import urldefrag, urljoin, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup

from kb.settings import Settings, get_settings

logger = logging.getLogger(__name__)

USER_AGENT = "GlancyKBBot/0.1 (+local-kb-ingest)"
SKIP_PREFIXES = ("/_next/", "/uploads/")
SKIP_PATHS = {"/html-embedding-example"}
SKIP_EXTENSIONS = (
    ".js",
    ".css",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
    ".svg",
    ".ico",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".pdf",
    ".mp4",
    ".zip",
)
SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def normalize_url(url: str, base_url: str | None = None) -> str:
    """Resolve relative URLs, force https, drop fragment and query."""
    if base_url:
        url = urljoin(base_url, url)
    url, _ = urldefrag(url)
    parsed = urlparse(url)
    scheme = "https" if parsed.scheme in ("http", "https") else parsed.scheme
    netloc = parsed.netloc.lower()
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    return urlunparse((scheme, netloc, path, "", "", ""))


def allowed_hosts(base_url: str) -> set[str]:
    host = urlparse(base_url).netloc.lower()
    hosts = {host}
    if host.startswith("www."):
        hosts.add(host[4:])
    else:
        hosts.add(f"www.{host}")
    return hosts


def is_allowed_url(url: str, base_url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    if parsed.netloc.lower() not in allowed_hosts(base_url):
        return False
    path = parsed.path or "/"
    if path in SKIP_PATHS or any(path.startswith(p) for p in SKIP_PREFIXES):
        return False
    lower = path.lower()
    if any(lower.endswith(ext) for ext in SKIP_EXTENSIONS):
        return False
    return True


def _http_headers() -> dict[str, str]:
    return {"User-Agent": USER_AGENT, "Accept": "text/html,application/xml;q=0.9,*/*;q=0.8"}


async def fetch_text(client: httpx.AsyncClient, url: str, timeout: float) -> str | None:
    """GET a URL; retry once on timeout/5xx. Return body text or None."""
    for attempt in range(2):
        try:
            response = await client.get(url, timeout=timeout, follow_redirects=True)
            if response.status_code >= 500 and attempt == 0:
                await asyncio.sleep(0.5)
                continue
            if response.status_code >= 400:
                logger.warning("HTTP %s for %s", response.status_code, url)
                return None
            return response.text
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            logger.warning("Fetch error %s (%s)", url, exc)
            if attempt == 0:
                await asyncio.sleep(0.5)
                continue
            return None
    return None


def parse_sitemap_urls(xml_text: str) -> list[str]:
    root = ET.fromstring(xml_text)
    tag = root.tag.split("}")[-1]
    locs: list[str] = []

    if tag == "sitemapindex":
        for loc in root.findall(".//sm:loc", SITEMAP_NS):
            if loc.text:
                locs.append(loc.text.strip())
        return locs

    for loc in root.findall(".//sm:loc", SITEMAP_NS):
        if loc.text:
            locs.append(loc.text.strip())
    # Fallback without namespace
    if not locs:
        for loc in root.iter():
            if loc.tag.split("}")[-1] == "loc" and loc.text:
                locs.append(loc.text.strip())
    return locs


async def load_sitemap_urls(client: httpx.AsyncClient, base_url: str, timeout: float) -> list[str]:
    sitemap_url = urljoin(base_url.rstrip("/") + "/", "sitemap.xml")
    xml_text = await fetch_text(client, sitemap_url, timeout)
    if not xml_text:
        logger.warning("Could not load sitemap at %s", sitemap_url)
        return []

    entries = parse_sitemap_urls(xml_text)
    # Nested sitemap index: fetch child sitemaps
    child_urls: list[str] = []
    page_urls: list[str] = []
    for entry in entries:
        if entry.rstrip("/").endswith(".xml"):
            child_urls.append(entry)
        else:
            page_urls.append(entry)

    for child in child_urls:
        child_xml = await fetch_text(client, child, timeout)
        if child_xml:
            page_urls.extend(parse_sitemap_urls(child_xml))

    normalized = []
    seen: set[str] = set()
    for raw in page_urls:
        url = normalize_url(raw)
        if url not in seen and is_allowed_url(url, base_url):
            seen.add(url)
            normalized.append(url)
    return normalized


def extract_links(html: str, page_url: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    links: list[str] = []
    seen: set[str] = set()
    for tag in soup.find_all("a", href=True):
        href = tag["href"].strip()
        if href.startswith(("mailto:", "tel:", "javascript:")):
            continue
        url = normalize_url(href, page_url)
        if url in seen or not is_allowed_url(url, base_url):
            continue
        seen.add(url)
        links.append(url)
    return links


def extract_title(soup: BeautifulSoup) -> str:
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    h1 = soup.find("h1")
    if h1:
        return h1.get_text(" ", strip=True)
    return ""


def extract_text(html: str) -> tuple[str, str]:
    """Return (title, cleaned body text)."""
    soup = BeautifulSoup(html, "lxml")
    title = extract_title(soup)

    for tag in soup(["script", "style", "noscript", "nav", "footer", "header", "form", "svg"]):
        tag.decompose()

    root = soup.find("main") or soup.find("article") or soup.body or soup
    text = root.get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text).strip()
    return title, text


async def crawl_bfs_urls(
    client: httpx.AsyncClient,
    seed_urls: Iterable[str],
    base_url: str,
    timeout: float,
    delay_ms: int,
    concurrency: int,
) -> dict[str, tuple[str, str]]:
    """
    Crawl allowed pages starting from seed_urls.
    Returns {url: (title, text)}.
    """
    queue: deque[str] = deque()
    seen: set[str] = set()
    for seed in seed_urls:
        url = normalize_url(seed)
        if is_allowed_url(url, base_url) and url not in seen:
            seen.add(url)
            queue.append(url)

    results: dict[str, tuple[str, str]] = {}
    sem = asyncio.Semaphore(concurrency)
    lock = asyncio.Lock()
    delay = delay_ms / 1000.0
    settings = get_settings()

    async def process(url: str) -> None:
        async with sem:
            await asyncio.sleep(delay)
            html = await fetch_text(client, url, timeout)
            if not html:
                return
            title, text = extract_text(html)
            if len(text) < settings.min_text_chars:
                logger.info("Skip short page %s (%s chars)", url, len(text))
            else:
                results[url] = (title, text)

            new_links = extract_links(html, url, base_url)
            async with lock:
                for link in new_links:
                    if link not in seen:
                        seen.add(link)
                        queue.append(link)

    while queue:
        batch_size = min(len(queue), concurrency)
        batch = [queue.popleft() for _ in range(batch_size)]
        await asyncio.gather(*(process(url) for url in batch))

    return results


async def discover_and_crawl(settings: Settings | None = None) -> dict[str, tuple[str, str]]:
    """Load sitemap URLs, BFS-crawl the site, return {url: (title, text)}."""
    settings = settings or get_settings()
    base_url = normalize_url(settings.site_base_url)

    limits = httpx.Limits(max_connections=settings.crawl_concurrency)
    async with httpx.AsyncClient(headers=_http_headers(), limits=limits) as client:
        sitemap_urls = await load_sitemap_urls(client, base_url, settings.crawl_timeout_s)
        seeds = sitemap_urls or [base_url]
        if base_url not in seeds:
            seeds = [base_url, *seeds]
        logger.info("Discovered %s seed URLs (sitemap + home)", len(seeds))
        pages = await crawl_bfs_urls(
            client=client,
            seed_urls=seeds,
            base_url=base_url,
            timeout=settings.crawl_timeout_s,
            delay_ms=settings.crawl_delay_ms,
            concurrency=settings.crawl_concurrency,
        )
    logger.info("Crawled %s pages with usable text", len(pages))
    return pages

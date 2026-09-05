"""Shared settings for the knowledge-base pipeline."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    site_base_url: str = "https://www.glancyfawcett.com"
    chroma_path: str = str(ROOT_DIR / "data" / "chroma")
    chroma_collection: str = "site_kb"

    ollama_base_url: str = "http://localhost:11434"
    ollama_embed_model: str = "nomic-embed-text"

    crawl_concurrency: int = 4
    crawl_delay_ms: int = 200
    crawl_timeout_s: float = 30.0
    min_text_chars: int = 100

    chunk_size_tokens: int = 500
    chunk_overlap_tokens: int = 100

    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"

    deepgram_api_key: str = ""
    deepgram_tts_voice: str = "aura-2-thalia-en"


@lru_cache
def get_settings() -> Settings:
    return Settings()

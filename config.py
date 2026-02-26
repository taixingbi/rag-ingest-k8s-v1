"""
Configuration loaded from environment (.env).
Values are read when Settings() is created so CLI args (--env, --target localhost|atlas) take effect.
"""

from dataclasses import dataclass, field
import os

from dotenv import load_dotenv

load_dotenv()


def _env(key: str, default: str) -> str:
    return os.environ.get(key, default)


def _env_int(key: str, default: str) -> int:
    return int(os.environ.get(key, default))


def _embed_model_default() -> str:
    """Default embed model from EMBED_MODEL or provider; reads EMBED_PROVIDER once."""
    model = _env("EMBED_MODEL", "")
    if model:
        return model
    provider = _env("EMBED_PROVIDER", "ollama")
    if provider == "ollama":
        return "nomic-embed-text"
    if provider == "vllm":
        return ""
    return "text-embedding-3-small"


@dataclass
class Settings:
    mongodb_uri: str = field(default_factory=lambda: _env("MONGODB_URI", ""))
    mongodb_db: str = field(default_factory=lambda: _env("MONGODB_DB", "rag"))
    mongodb_collection: str = field(default_factory=lambda: _env("MONGODB_COLLECTION", "rag_chunks"))

    openai_api_key: str = field(default_factory=lambda: _env("OPENAI_API_KEY", ""))
    # Embed: "openai", "ollama", or "vllm"
    embed_provider: str = field(default_factory=lambda: _env("EMBED_PROVIDER", "ollama"))
    embed_model: str = field(default_factory=_embed_model_default)
    # For ollama/vllm: base URL (defaults applied in main: 11434 for ollama, 8000 for vllm)
    embed_base_url: str = field(default_factory=lambda: _env("EMBED_BASE_URL", ""))
    # Optional hint for Vector Search index dims (ollama/vllm); 0 = use 1536 in hint
    embed_dims: int = field(default_factory=lambda: _env_int("EMBED_DIMS", "0"))

    # Chunking (token-based preferred, char-based fallback)
    chunk_tokens: int = field(default_factory=lambda: _env_int("CHUNK_TOKENS", "1000"))
    overlap_tokens: int = field(default_factory=lambda: _env_int("OVERLAP_TOKENS", "150"))
    chunk_chars: int = field(default_factory=lambda: _env_int("CHUNK_CHARS", "5000"))
    overlap_chars: int = field(default_factory=lambda: _env_int("OVERLAP_CHARS", "800"))

    # Ingest (batch size for embeddings API; max throughput defaults)
    batch_size: int = field(default_factory=lambda: _env_int("BATCH_SIZE", "128"))
    max_concurrent_files: int = field(default_factory=lambda: _env_int("MAX_CONCURRENT_FILES", "6"))
    block_queue_size: int = field(default_factory=lambda: _env_int("BLOCK_QUEUE_SIZE", "4"))
    embed_max_concurrent: int = field(default_factory=lambda: _env_int("EMBED_MAX_CONCURRENT", "8"))

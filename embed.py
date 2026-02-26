import asyncio
import os
import time
from typing import List
from openai import OpenAI, AsyncOpenAI, RateLimitError, APIError, APIConnectionError

# ----------------------------
# Token bucket (TPM rate limiting) — OpenAI only
# ----------------------------
# Skipped when EMBED_PROVIDER=ollama or vllm (no TPM limit). EMBED_TPM_SAFETY is only
# read when using OpenAI. RATE = refill (tokens/sec); CAPACITY = max tokens in bucket.

_bucket_initialized = False
RATE = 0.0
CAPACITY = 0.0
token_budget = 0.0
last_refill = 0.0
_lock: asyncio.Lock | None = None


def _init_bucket() -> None:
    """Initialize token bucket from env; only when using OpenAI (first acquire_tokens call)."""
    global RATE, CAPACITY, token_budget, last_refill, _lock, _bucket_initialized
    if _bucket_initialized:
        return
    _bucket_initialized = True
    tpm_limit = int(os.environ.get("OPENAI_TPM_LIMIT", "1000000"))
    tpm_safety = float(os.environ.get("EMBED_TPM_SAFETY", "0.9"))
    RATE = (tpm_limit * tpm_safety) / 60
    CAPACITY = RATE * 25
    token_budget = CAPACITY
    last_refill = time.monotonic()
    _lock = asyncio.Lock()


def estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 chars per token)."""
    return max(1, int(len(text) / 4))


async def acquire_tokens(cost: int) -> None:
    """Wait until the token bucket has at least `cost` tokens, then spend them.
    No-op when EMBED_PROVIDER=ollama or vllm (no TPM limit); EMBED_TPM_SAFETY is not used.
    """
    provider = os.environ.get("EMBED_PROVIDER", "ollama").lower()
    if provider in ("ollama", "vllm"):
        return
    global token_budget, last_refill
    _init_bucket()
    if cost <= 0:
        return
    if cost > CAPACITY:
        raise ValueError(
            f"acquire_tokens(cost={cost}) exceeds bucket CAPACITY={CAPACITY}; "
            "increase CAPACITY or use smaller batches."
        )

    assert _lock is not None
    while True:
        async with _lock:
            now = time.monotonic()
            elapsed = now - last_refill
            token_budget = min(CAPACITY, token_budget + elapsed * RATE)
            last_refill = now

            if token_budget >= cost:
                token_budget -= cost
                return
            need = cost - token_budget
            sleep_sec = min(2.0, max(0.05, need / RATE))

        await asyncio.sleep(sleep_sec)


# ----------------------------
# Embeddings
# ----------------------------

def _raise_connection_hint(provider: str, base_url: str, cause: BaseException | None = None) -> None:
    """Raise a clear error when embed server (ollama/vllm) is unreachable."""
    provider = (provider or "").lower()
    if provider == "ollama":
        hint = (
            "Is Ollama running? Start with: ollama serve  # pull embed model: ollama pull nomic-embed-text (do not use 'run'). "
            "From Docker, set EMBED_BASE_URL=http://host.docker.internal:11434/v1 to reach Ollama on the host."
        )
    elif provider == "vllm":
        hint = "Is the vLLM server running with an embeddings model?"
    else:
        hint = "Check that the server is running and EMBED_BASE_URL is correct."
    err = ConnectionError(
        f"Cannot connect to {provider or 'embed'} at {base_url}. {hint}"
    )
    if cause is not None:
        raise err from cause
    raise err


def embed_texts_openai(
    client: OpenAI,
    model: str,
    texts: List[str],
    max_retries: int = 3,
    base_delay: float = 1.0,
) -> List[List[float]]:
    """
    Batch embed with exponential backoff retry logic.
    Keep texts reasonably sized (32-128 chunks per request).
    """
    if not texts:
        return []
    for attempt in range(max_retries):
        try:
            resp = client.embeddings.create(model=model, input=texts)
            return [d.embedding for d in resp.data]
        except APIConnectionError as e:
            # Catch before APIError (APIConnectionError is a subclass of APIError)
            provider = os.environ.get("EMBED_PROVIDER", "ollama").lower()
            if provider in ("ollama", "vllm"):
                base_url = os.environ.get("EMBED_BASE_URL") or (
                    "http://localhost:11434/v1" if provider == "ollama" else "http://localhost:8000/v1"
                )
                _raise_connection_hint(provider, base_url, cause=e)
            raise
        except (RateLimitError, APIError) as e:
            if attempt == max_retries - 1:
                raise
            delay = base_delay * (2 ** attempt)
            print(f"Embedding API error (attempt {attempt + 1}/{max_retries}): {e}. Retrying in {delay}s...")
            time.sleep(delay)
        except Exception as e:
            # For other errors, don't retry
            raise
    
    raise RuntimeError("Failed to embed texts after retries")


async def embed_texts_openai_async(
    client: AsyncOpenAI,
    model: str,
    texts: List[str],
    max_retries: int = 3,
    base_delay: float = 1.0,
) -> List[List[float]]:
    """Async batch embed with exponential backoff retry."""
    if not texts:
        return []
    for attempt in range(max_retries):
        try:
            resp = await client.embeddings.create(model=model, input=texts)
            return [d.embedding for d in resp.data]
        except APIConnectionError as e:
            # Catch before APIError (APIConnectionError is a subclass of APIError)
            provider = os.environ.get("EMBED_PROVIDER", "ollama").lower()
            if provider in ("ollama", "vllm"):
                base_url = os.environ.get("EMBED_BASE_URL") or (
                    "http://localhost:11434/v1" if provider == "ollama" else "http://localhost:8000/v1"
                )
                _raise_connection_hint(provider, base_url, cause=e)
            raise
        except (RateLimitError, APIError) as e:
            if attempt == max_retries - 1:
                raise
            delay = base_delay * (2 ** attempt)
            print(f"Embedding API error (attempt {attempt + 1}/{max_retries}): {e}. Retrying in {delay}s...")
            await asyncio.sleep(delay)
        except Exception as e:
            raise
    raise RuntimeError("Failed to embed texts after retries")
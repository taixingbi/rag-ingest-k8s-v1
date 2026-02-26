"""
Ingest files (JSON/MD/PDF) -> chunk -> embed -> upsert into MongoDB Atlas Vector Search.

Architecture:
- Mac mini (local): Reads files, chunks, computes embeddings, upserts to Atlas
- MongoDB Atlas: Stores text + metadata + embedding vector with Vector Search index

Install:
  pip install pymongo[srv] openai python-dotenv tiktoken
  # Optional for PDF:
  pip install pdfplumber

Env (.env):
  MONGODB_URI="mongodb+srv://<user>:<pass>@<cluster>/<db>?retryWrites=true&w=majority"
  MONGODB_DB="rag"
  MONGODB_COLLECTION="rag_chunks"
  OPENAI_API_KEY="..."
  EMBED_MODEL="text-embedding-3-small"  # or set per provider (default: nomic-embed-text for ollama)
  CHUNK_TOKENS=1000
  OVERLAP_TOKENS=150
  BATCH_SIZE=128
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import queue
import sys
import threading
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

# In K8s/Docker there is no TTY; force line buffering so logs appear in kubectl logs / docker logs.
if not sys.stdout.isatty():
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass

from pymongo import MongoClient
from openai import OpenAI, AsyncOpenAI

from chunk import chunk_text_tokens
from config import Settings
from db import (
    delete_chunks_by_source,
    ensure_unique_index,
    upsert_chunks,
    async_delete_chunks_by_source,
    async_ensure_unique_index,
    async_upsert_chunks,
)
from embed import (
    acquire_tokens,
    embed_texts_openai,
    embed_texts_openai_async,
    estimate_tokens,
)
from normalize import _extract_metadata, detect_file_type, normalize_document
from state import load_state, save_state, should_skip_file, update_file_state
from utils import (
    compute_stable_id,
    get_file_mtime,
    get_files_for_ingest,
    now_iso,
    read_lines_in_blocks,
    sha256_text,
    stable_json_text,
)

try:
    from motor.motor_asyncio import AsyncIOMotorClient
except ImportError:
    AsyncIOMotorClient = None


def _is_openai_compatible(settings: Settings) -> bool:
    """True when embed provider uses OpenAI-compatible API (openai, ollama, vllm)."""
    return settings.embed_provider in ("openai", "ollama", "vllm")


def _require_openai_compatible(settings: Settings) -> None:
    """Raise ValueError if embed provider is not openai, ollama, or vllm."""
    if not _is_openai_compatible(settings):
        raise ValueError(
            f"Unsupported EMBED_PROVIDER={settings.embed_provider!r}; use openai, ollama, or vllm."
        )


def _openai_embed_client_kwargs(settings: Settings) -> dict:
    """Kwargs for OpenAI(...) or AsyncOpenAI(...). Use only when _is_openai_compatible(settings)."""
    if settings.embed_provider == "openai":
        return {"api_key": settings.openai_api_key}
    if settings.embed_provider == "ollama":
        return {"base_url": settings.embed_base_url or "http://localhost:11434/v1", "api_key": "ollama"}
    if settings.embed_provider == "vllm":
        return {"base_url": settings.embed_base_url or "http://localhost:8000/v1", "api_key": "vllm"}
    raise ValueError(f"Not an OpenAI-compatible provider: {settings.embed_provider}")


# ----------------------------
# Helpers for doc building
# ----------------------------

def _tags_from_filename(filename: str) -> List[str]:
    """Infer tags from filename for metadata."""
    lower = filename.lower()
    if "profile" in lower:
        return ["profile", "resume", "candidate"]
    if "resume" in lower:
        return ["resume", "candidate"]
    if "qa" in lower:
        return ["qa", "questions"]
    return ["document"]


def _title_for_doc(file_metadata: Optional[Dict[str, Any]], filename: str) -> str:
    """Title from metadata or filename stem."""
    if file_metadata and file_metadata.get("title"):
        return file_metadata["title"]
    return os.path.splitext(filename)[0]


# ----------------------------
# Main ingestion
# ----------------------------

def build_docs_for_file(
    filepath: str,
    embed_client: Any,
    settings: Settings,
) -> List[Dict[str, Any]]:
    """
    Process a single file: normalize -> chunk -> embed -> build MongoDB documents.
    
    Returns list of document dicts matching the target schema.
    """
    filename = os.path.basename(filepath)
    source_id = filename
    file_type = detect_file_type(filepath)
    mtime = get_file_mtime(filepath)
    
    # Normalize document to text
    text, file_metadata = normalize_document(filepath)
    
    # Chunk
    chunks = chunk_text_tokens(
        text=text,
        chunk_tokens=settings.chunk_tokens,
        overlap_tokens=settings.overlap_tokens,
        model=settings.embed_model,
        chunk_chars=settings.chunk_chars,
        overlap_chars=settings.overlap_chars,
    )
    
    if not chunks:
        return []
    
    # Embed in batches (OpenAI-compatible: async with limited concurrency to avoid 429)
    embeddings: List[List[float]] = []
    if _is_openai_compatible(settings):
        sem = asyncio.Semaphore(settings.embed_max_concurrent)

        async def _embed_one(client: Any, model: str, batch: List[str]) -> List[List[float]]:
            cost = sum(estimate_tokens(t) for t in batch)
            await acquire_tokens(cost)
            async with sem:
                return await embed_texts_openai_async(client, model, batch)

        async def _embed_batches() -> List[List[float]]:
            client = AsyncOpenAI(**_openai_embed_client_kwargs(settings))
            try:
                batches = [chunks[i : i + settings.batch_size] for i in range(0, len(chunks), settings.batch_size)]
                tasks = [_embed_one(client, settings.embed_model, b) for b in batches]
                results = await asyncio.gather(*tasks)
                return [e for r in results for e in r]
            finally:
                await client.close()
        embeddings = asyncio.run(_embed_batches())
    else:
        _require_openai_compatible(settings)
    
    # Build MongoDB documents matching target schema
    docs = _docs_from_chunks_embeddings(
        source_id, filepath, file_type, mtime, filename, file_metadata,
        chunks, embeddings, 0, settings,
    )
    return docs


async def build_docs_for_file_async(
    filepath: str,
    embed_client: Any,
    settings: Settings,
    progress_callback: Optional[Callable[[int, int, Dict[str, float]], None]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, float]]:
    """Async: normalize -> chunk -> embed -> build MongoDB documents. Returns (docs, timings).
    When progress_callback is set, embedding runs in batches of PROGRESS_CHUNK_INTERVAL and
    callback(n_done, n_total, timings) is invoked after each batch so progress streams."""
    timings: Dict[str, float] = {"load_parse": 0.0, "chunk": 0.0, "embed": 0.0, "mongo_bulk_write": 0.0, "finalize": 0.0}
    filename = os.path.basename(filepath)
    source_id = filename
    file_type = detect_file_type(filepath)
    mtime = get_file_mtime(filepath)
    t0 = time.perf_counter()
    text, file_metadata = normalize_document(filepath)
    timings["load_parse"] = time.perf_counter() - t0
    t0 = time.perf_counter()
    chunks = chunk_text_tokens(
        text=text,
        chunk_tokens=settings.chunk_tokens,
        overlap_tokens=settings.overlap_tokens,
        model=settings.embed_model,
        chunk_chars=settings.chunk_chars,
        overlap_chars=settings.overlap_chars,
    )
    timings["chunk"] = time.perf_counter() - t0
    if not chunks:
        return [], timings
    n_total = len(chunks)
    embeddings: List[List[float]] = []
    t_embed_start = time.perf_counter()
    if progress_callback is not None:
        # Stream progress: embed in batches of PROGRESS_CHUNK_INTERVAL and report after each
        next_milestone = PROGRESS_CHUNK_INTERVAL
        for start in range(0, n_total, PROGRESS_CHUNK_INTERVAL):
            batch_chunks = chunks[start : start + PROGRESS_CHUNK_INTERVAL]
            if _is_openai_compatible(settings):
                sem = asyncio.Semaphore(settings.embed_max_concurrent)

                async def _embed_one(batch: List[str]) -> List[List[float]]:
                    cost = sum(estimate_tokens(t) for t in batch)
                    await acquire_tokens(cost)
                    async with sem:
                        return await embed_texts_openai_async(
                            embed_client, settings.embed_model, batch
                        )

                api_batches = [batch_chunks[i : i + settings.batch_size] for i in range(0, len(batch_chunks), settings.batch_size)]
                results = await asyncio.gather(*[_embed_one(b) for b in api_batches])
                batch_embs = [e for r in results for e in r]
            else:
                _require_openai_compatible(settings)
            embeddings.extend(batch_embs)
            timings["embed"] = time.perf_counter() - t_embed_start
            n_done = start + len(batch_chunks)
            while next_milestone <= n_done:
                progress_callback(next_milestone, n_total, timings)
                next_milestone += PROGRESS_CHUNK_INTERVAL
    else:
        if _is_openai_compatible(settings):
            sem = asyncio.Semaphore(settings.embed_max_concurrent)

            async def _embed_one(batch: List[str]) -> List[List[float]]:
                cost = sum(estimate_tokens(t) for t in batch)
                await acquire_tokens(cost)
                async with sem:
                    return await embed_texts_openai_async(
                        embed_client, settings.embed_model, batch
                    )

            batches = [chunks[i : i + settings.batch_size] for i in range(0, len(chunks), settings.batch_size)]
            results = await asyncio.gather(*[_embed_one(b) for b in batches])
            embeddings = [e for r in results for e in r]
        else:
            _require_openai_compatible(settings)
        timings["embed"] = time.perf_counter() - t_embed_start
    docs = _docs_from_chunks_embeddings(
        source_id, filepath, file_type, mtime, filename, file_metadata,
        chunks, embeddings, 0, settings,
    )
    return docs, timings


def _docs_from_chunks_embeddings(
    source_id: str,
    filepath: str,
    file_type: str,
    mtime: str,
    filename: str,
    file_metadata: Optional[Dict[str, Any]],
    chunks: List[str],
    embeddings: List[List[float]],
    chunk_offset: int,
    settings: Settings,
) -> List[Dict[str, Any]]:
    """Build MongoDB doc dicts from chunks and embeddings. Single source of truth for doc schema."""
    if not embeddings:
        return []
    dims = len(embeddings[0]) if embeddings else 1536
    title = _title_for_doc(file_metadata, filename)
    tags = _tags_from_filename(filename)
    ts = now_iso()
    docs: List[Dict[str, Any]] = []
    for i, (chunk_text, emb) in enumerate(zip(chunks, embeddings)):
        global_i = chunk_offset + i
        chunk_id = f"{source_id}::chunk_{global_i:04d}"
        chunk_hash = sha256_text(chunk_text)
        doc_id = compute_stable_id(source_id, chunk_id, chunk_hash)
        doc = {
            "_id": doc_id,
            "chunk_id": chunk_id,
            "source": {"source_id": source_id, "path": filepath, "type": file_type, "mtime": mtime},
            "text": chunk_text,
            "metadata": {"title": title, "section": f"chunk_{global_i}", "tags": tags, "lang": "en"},
            "embedding": emb,
            "embedding_model": settings.embed_model,
            "dims": dims,
            "created_at": ts,
            "updated_at": ts,
        }
        docs.append(doc)
    return docs


def process_ndjson_blocks(
    filepath: str,
    col: Any,
    embed_client: Any,
    settings: Settings,
    block_size: int = 10,
    file_index: Optional[int] = None,
    file_total: Optional[int] = None,
) -> Tuple[int, bool]:
    """
    Process NDJSON in blocks via queue: producer reads blocks, consumer does chunk->embed->mongo.
    First block is built and processed in the main thread so we don't freeze waiting for the producer.
    """
    with open(filepath, "r", encoding="utf-8") as f:
        first_line = f.readline().strip()
    if not first_line:
        return 0, False
    try:
        first_obj = json.loads(first_line)
    except json.JSONDecodeError:
        return 0, False

    filename = os.path.basename(filepath)
    source_id = filename
    file_type = detect_file_type(filepath)
    mtime = get_file_mtime(filepath)
    file_metadata = _extract_metadata(first_obj) if isinstance(first_obj, dict) else None

    t_ingest_start = time.perf_counter()
    t0 = time.perf_counter()
    delete_chunks_by_source(col, source_id)
    t_db_delete = time.perf_counter() - t0

    chunk_offset = 0
    total_docs = 0
    total_timings: Dict[str, float] = {"load_parse": 0.0, "chunk": 0.0, "embed": 0.0, "mongo_bulk_write": 0.0, "finalize": 0.0}

    async def _embed_block_batches(chunks_block: List[str], block_num: Optional[int] = None) -> List[List[float]]:
        sem = asyncio.Semaphore(settings.embed_max_concurrent)
        async def _embed_one(client: Any, model: str, batch: List[str]) -> List[List[float]]:
            cost = sum(estimate_tokens(t) for t in batch)
            await acquire_tokens(cost)
            async with sem:
                return await embed_texts_openai_async(client, model, batch)
        client = AsyncOpenAI(**_openai_embed_client_kwargs(settings))
        try:
            batches = [chunks_block[i : i + settings.batch_size] for i in range(0, len(chunks_block), settings.batch_size)]
            n_batches = len(batches)
            done_count = 0
            done_lock = asyncio.Lock()

            async def _with_progress(batch: List[str]) -> List[List[float]]:
                nonlocal done_count
                r = await _embed_one(client, settings.embed_model, batch)
                async with done_lock:
                    done_count += 1
                    # if n_batches > 1 and block_num is not None:
                    #     print(f"  Block {block_num}: embedding batch {done_count}/{n_batches}...", flush=True)
                return r

            tasks = [_with_progress(b) for b in batches]
            results = await asyncio.gather(*tasks)
            return [e for r in results for e in r]
        finally:
            await client.close()

    def process_one_block(block_num: int, objs: List[Any]) -> None:
        nonlocal chunk_offset, total_docs, total_timings
        n_objs = len(objs) if objs else 0
        # print(f"  Block {block_num}: parsing {n_objs} objects...", flush=True)
        timings: Dict[str, float] = {}
        t0 = time.perf_counter()
        text = stable_json_text(objs)
        timings["load_parse"] = time.perf_counter() - t0
        t0 = time.perf_counter()
        chunks = chunk_text_tokens(
            text=text,
            chunk_tokens=settings.chunk_tokens,
            overlap_tokens=settings.overlap_tokens,
            model=settings.embed_model,
            chunk_chars=settings.chunk_chars,
            overlap_chars=settings.overlap_chars,
        )
        timings["chunk"] = time.perf_counter() - t0
        if not chunks:
            for k in total_timings:
                total_timings[k] += timings.get(k, 0.0)
            return
        # print(f"  Block {block_num}: {len(chunks)} chunks, embedding...", flush=True)
        t0 = time.perf_counter()
        if _is_openai_compatible(settings):
            embeddings = asyncio.run(_embed_block_batches(chunks, block_num=block_num))
        else:
            _require_openai_compatible(settings)
        timings["embed"] = time.perf_counter() - t0
        t0 = time.perf_counter()
        docs = _docs_from_chunks_embeddings(
            source_id, filepath, file_type, mtime, filename, file_metadata,
            chunks, embeddings, chunk_offset, settings,
        )
        t0_upsert = time.perf_counter()
        upsert_chunks(col, docs)
        timings["mongo_bulk_write"] = time.perf_counter() - t0_upsert
        timings["finalize"] = 0.0
        chunk_offset += len(chunks)
        total_docs += len(docs)
        for k in total_timings:
            total_timings[k] += timings.get(k, 0.0)
        n_chunks = len(chunks)
        lp, ch, em, mb = timings["load_parse"], timings["chunk"], timings["embed"], timings["mongo_bulk_write"]
        # print(f"  block {block_num}: summary: load_parse={lp:.3f}s chunk={ch:.3f}s embed={em:.3f}s mongo_bulk_write={mb:.3f}s chunks={n_chunks}")

    # Build first block in main thread (no wait on producer) to avoid freeze
    first_block_lines: List[str] = []
    with open(filepath, "r", encoding="utf-8") as f:
        f.readline()  # skip first line (already have first_obj)
        for _ in range(block_size - 1):
            line = f.readline()
            if not line:
                break
            line = line.strip()
            if line:
                first_block_lines.append(line)
    first_objs: List[Any] = [first_obj]
    for line in first_block_lines:
        try:
            first_objs.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    process_one_block(1, first_objs)

    # Remaining blocks via producer/consumer
    maxsize = settings.block_queue_size if settings.block_queue_size > 0 else 0
    block_queue: "queue.Queue[Tuple[Optional[int], Optional[List[Any]]]]" = queue.Queue(maxsize=maxsize)

    def producer() -> None:
        with open(filepath, "r", encoding="utf-8") as f:
            for _ in range(block_size):  # skip first block (already processed)
                if not f.readline():
                    break
            block_num = 1
            for block in read_lines_in_blocks(f, block_size=block_size):
                block_num += 1
                objs: List[Any] = []
                for line in block:
                    try:
                        objs.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass  # skip malformed line
                block_queue.put((block_num, objs))
        block_queue.put((None, None))

    producer_thread = threading.Thread(target=producer, daemon=True)
    producer_thread.start()

    while True:
        block_num, objs = block_queue.get()
        if block_num is None:
            break
        process_one_block(block_num, objs)
    lp, ch, em, mb = total_timings["load_parse"], total_timings["chunk"], total_timings["embed"], total_timings["mongo_bulk_write"]
    total_s = time.perf_counter() - t_ingest_start
    thr = total_docs / total_s if total_s > 0 else 0
    lat_ms = (total_s / total_docs * 1000) if total_docs else 0
    embed_pct = (100 * em / total_s) if total_s > 0 else 0
    write_pct = (100 * mb / total_s) if total_s > 0 else 0
    prefix = f"file {file_index}/{file_total}: " if (file_index is not None and file_total is not None) else ""
    print(f"{prefix}INGEST shard={filename} chunks={total_docs} total={total_s:.3f}s thr={thr:.1f}c/s lat={lat_ms:.1f}ms | embed={em:.3f}s({embed_pct:.1f}%) write={mb:.3f}s({write_pct:.1f}%) chunk={ch:.3f}s db_del={t_db_delete:.3f}s parse={lp:.3f}s")
    return total_docs, True


def ingest_folder(
    folder_glob: str = "data/**/*",
    skip_unchanged: bool = True,
    job_index: Optional[int] = None,
    job_total: Optional[int] = None,
    mode: str = "sync",
) -> None:
    """
    Ingest all matching files from folder.
    
    Args:
        folder_glob: Glob pattern for files to ingest (e.g., "data/**/*.json")
        skip_unchanged: If True, skip files that haven't changed since last ingest
        job_index: When set with job_total, only process files where index % job_total == job_index (Indexed Job).
        job_total: Total number of parallel pods (with job_index).
        mode: Ingest mode for logging ("sync" or "async").
    """
    settings = Settings()
    _log_ingest_config(settings, folder_glob, mode)

    assert settings.mongodb_uri, "Missing MONGODB_URI"
    if settings.embed_provider == "openai":
        assert settings.openai_api_key, "Missing OPENAI_API_KEY"
    if settings.embed_provider == "vllm":
        assert settings.embed_model, "Missing EMBED_MODEL for vllm"
    
    # MongoDB connection
    mongo = MongoClient(settings.mongodb_uri)
    db = mongo[settings.mongodb_db]
    col = db[settings.mongodb_collection]
    ensure_unique_index(col)
    
    # Embed client (OpenAI, ollama, or vllm)
    if _is_openai_compatible(settings):
        embed_client = OpenAI(**_openai_embed_client_kwargs(settings))
    else:
        _require_openai_compatible(settings)
    
    # Load state for incremental ingestion
    state = load_state()
    start = time.perf_counter()
    files = get_files_for_ingest(folder_glob)
    if job_index is not None and job_total is not None:
        files = [f for i, f in enumerate(files) if i % job_total == job_index]
    print(f"Found {len(files)} files matching pattern")
    
    total_docs = 0
    skipped = 0
    last_printed_round = 0

    for file_index_one, filepath in enumerate(files, start=1):
        # Check if file should be skipped (incremental ingestion)
        if skip_unchanged:
            try:
                text, _ = normalize_document(filepath)
                content_hash = sha256_text(text)
                mtime = get_file_mtime(filepath)
                
                if should_skip_file(filepath, content_hash, mtime, state):
                    print(f"Skipping unchanged: {filepath}")
                    skipped += 1
                    continue
            except Exception as e:
                print(f"Warning: Could not check state for {filepath}: {e}")
        
        # Process file
        try:
            doc_start = time.perf_counter()
            if filepath.endswith(".json"):
                n, ok = process_ndjson_blocks(filepath, col, embed_client, settings, block_size=10, file_index=file_index_one, file_total=len(files))
                if ok:
                    total_docs += n
                    if skip_unchanged:
                        text, _ = normalize_document(filepath)
                        content_hash = sha256_text(text)
                        mtime = get_file_mtime(filepath)
                        update_file_state(filepath, content_hash, mtime, state)
                    continue
            print(f"Processing: {filepath}")
            docs = build_docs_for_file(filepath, embed_client, settings)

            if docs:
                source_id = docs[0]["source"]["source_id"]
                deleted = delete_chunks_by_source(col, source_id)
                if deleted:
                    print(f"  Deleted {deleted} old chunks for {source_id}")
                upsert_chunks(col, docs)
                print(f"  Written to MongoDB: {len(docs)} chunks ({source_id})", flush=True)
                total_docs += len(docs)
                while last_printed_round + 640 <= total_docs:
                    last_printed_round += 640
                    print(f"  ... Processed {last_printed_round} chunks total")
                
                # Update state
                if skip_unchanged:
                    text, _ = normalize_document(filepath)
                    content_hash = sha256_text(text)
                    mtime = get_file_mtime(filepath)
                    update_file_state(filepath, content_hash, mtime, state)
                
                elapsed = time.perf_counter() - doc_start
                print(f"  ✓ Ingested {len(docs)} chunks ({elapsed:.2f}s)")
            else:
                elapsed = time.perf_counter() - doc_start
                print(f"  ⚠ No chunks generated ({elapsed:.2f}s)")
        except Exception as e:
            print(f"  ✗ Error processing {filepath}: {e}")
            import traceback
            traceback.print_exc()
    
    # Save state
    if skip_unchanged:
        save_state(state)

    durable_s = time.perf_counter() - start
    print(f"\nDone.")
    print(f"  Durable time: {durable_s:.2f}s")
    print(f"  Total chunks upserted: {total_docs}")
    print(f"  Files skipped (unchanged): {skipped}")
    print(f"  MongoDB: {settings.mongodb_db}.{settings.mongodb_collection}")


PROGRESS_CHUNK_INTERVAL = 640  # Print progress every N chunks (async path: upsert in batches and print after each)


async def _process_one_file_async(
    filepath: str,
    col: Any,
    embed_client: Any,
    settings: Settings,
    state: Dict[str, Dict[str, str]],
    block_num: Optional[int] = None,
    total_files: Optional[int] = None,
) -> tuple[int, Exception | None, Optional[Dict[str, float]]]:
    """Process one file: build_docs_async -> delete_by_source -> upsert -> update state. Returns (num_docs, error, timings)."""
    docs, timings = await build_docs_for_file_async(filepath, embed_client, settings, progress_callback=None)
    if not docs:
        return 0, None, timings
    source_id = docs[0]["source"]["source_id"]
    t_del_start = time.perf_counter()
    await async_delete_chunks_by_source(col, source_id)
    timings["db_delete"] = time.perf_counter() - t_del_start
    t_mongo = 0.0
    if block_num is not None:
        for start in range(0, len(docs), PROGRESS_CHUNK_INTERVAL):
            batch = docs[start : start + PROGRESS_CHUNK_INTERVAL]
            t_batch = time.perf_counter()
            await async_upsert_chunks(col, batch)
            t_mongo += time.perf_counter() - t_batch
        timings["mongo_bulk_write"] = t_mongo
    else:
        t_upsert_start = time.perf_counter()
        await async_upsert_chunks(col, docs)
        timings["mongo_bulk_write"] = time.perf_counter() - t_upsert_start
    text, _ = normalize_document(filepath)
    content_hash = sha256_text(text)
    mtime = get_file_mtime(filepath)
    update_file_state(filepath, content_hash, mtime, state)
    return len(docs), None, timings


def _run_meta_dir(folder_glob: str) -> str:
    """Base directory for pipeline run meta (shared across pods)."""
    return folder_glob.split("**")[0].rstrip("/") if "**" in folder_glob else folder_glob


def _write_run_start(meta_dir: str, ts: str) -> None:
    try:
        path = os.path.join(meta_dir, ".run_start.json")
        with open(path, "w") as f:
            json.dump({"ts": ts}, f)
    except Exception:
        pass


def _read_run_start(meta_dir: str) -> Optional[str]:
    try:
        path = os.path.join(meta_dir, ".run_start.json")
        if os.path.isfile(path):
            with open(path) as f:
                return json.load(f).get("ts")
    except Exception:
        pass
    return None


def _write_run_done(meta_dir: str, job_index: int, chunks: int, errors: int, ts: str) -> None:
    try:
        path = os.path.join(meta_dir, f".run_done_{job_index}.json")
        with open(path, "w") as f:
            json.dump({"chunks": chunks, "errors": errors, "ts": ts}, f)
    except Exception:
        pass


def _list_run_done_count(meta_dir: str) -> int:
    try:
        import glob
        pattern = os.path.join(meta_dir, ".run_done_*.json")
        return len(glob.glob(pattern))
    except Exception:
        return 0


def _read_all_run_done(meta_dir: str) -> List[Dict[str, Any]]:
    try:
        import glob
        pattern = os.path.join(meta_dir, ".run_done_*.json")
        out = []
        for path in glob.glob(pattern):
            with open(path) as f:
                out.append(json.load(f))
        return out
    except Exception:
        return []


def _remove_run_meta(meta_dir: str) -> None:
    try:
        import glob
        for pattern in (os.path.join(meta_dir, ".run_start.json"), os.path.join(meta_dir, ".run_done_*.json")):
            for path in glob.glob(pattern):
                try:
                    os.remove(path)
                except Exception:
                    pass
    except Exception:
        pass


def ingest_folder_async(
    folder_glob: str = "data/**/*",
    skip_unchanged: bool = True,
    job_index: Optional[int] = None,
    job_total: Optional[int] = None,
    mode: str = "async",
) -> None:
    """Ingest using async workers in-process (no queue). Saves state at end. When job_index/job_total set, only process this pod's share of files."""
    settings = Settings()
    _log_ingest_config(settings, folder_glob, mode)
    assert settings.mongodb_uri, "Missing MONGODB_URI"
    if settings.embed_provider == "openai":
        assert settings.openai_api_key, "Missing OPENAI_API_KEY"
    if settings.embed_provider == "vllm":
        assert settings.embed_model, "Missing EMBED_MODEL for vllm"
    assert AsyncIOMotorClient is not None, "Install motor: pip install motor"

    async def _run() -> None:
        start = time.perf_counter()
        pod_name = os.environ.get("HOSTNAME", "local")
        mongo = AsyncIOMotorClient(settings.mongodb_uri)
        db = mongo[settings.mongodb_db]
        col = db[settings.mongodb_collection]
        await async_ensure_unique_index(col)
        if _is_openai_compatible(settings):
            embed_client = AsyncOpenAI(**_openai_embed_client_kwargs(settings))
        else:
            _require_openai_compatible(settings)
        state = load_state()
        all_files = get_files_for_ingest(folder_glob)
        if job_index is not None and job_total is not None:
            files = [f for i, f in enumerate(all_files) if i % job_total == job_index]
        else:
            files = all_files
        total_pipeline_shards = len(all_files)
        to_process: List[str] = []
        skipped = 0
        for filepath in files:
            if skip_unchanged:
                try:
                    text, _ = normalize_document(filepath)
                    content_hash = sha256_text(text)
                    mtime = get_file_mtime(filepath)
                    if should_skip_file(filepath, content_hash, mtime, state):
                        print(f"Skipping unchanged: {filepath}")
                        skipped += 1
                        continue
                except Exception as e:
                    print(f"Warning: Could not check state for {filepath}: {e}")
            to_process.append(filepath)
        if not to_process:
            if skip_unchanged:
                save_state(state)
            print(f"Nothing to do. Durable time: {time.perf_counter() - start:.2f}s")
            return

        input_dir = _run_meta_dir(folder_glob)
        ts_start = datetime.now().astimezone().replace(microsecond=0).isoformat()
        # RUN_START once per pipeline: only pod 0 (or single process) prints and writes start meta
        if job_total is None or job_total == 1 or job_index == 0:
            _write_run_start(input_dir, ts_start)
            print(f"{ts_start} RUN_START mode={pod_name} embedder={settings.embed_provider} model={settings.embed_model} shards={total_pipeline_shards} input_dir={input_dir}", flush=True)

        max_concurrent = settings.max_concurrent_files
        sem = asyncio.Semaphore(max_concurrent)
        progress_lock = asyncio.Lock()
        total_docs = 0
        processed = 0
        errors = 0
        last_printed_round = 0
        total_timings: Dict[str, float] = {"load_parse": 0.0, "chunk": 0.0, "embed": 0.0, "mongo_bulk_write": 0.0, "finalize": 0.0}

        total_files = len(to_process)

        async def process_with_semaphore(filepath: str, block_num: int) -> None:
            nonlocal total_docs, processed, errors, last_printed_round
            async with sem:
                try:
                    doc_start = time.perf_counter()
                    n, _, timings = await _process_one_file_async(
                        filepath, col, embed_client, settings, state,
                        block_num=block_num, total_files=total_files,
                    )
                    total_s = time.perf_counter() - doc_start
                    async with progress_lock:
                        total_docs += n
                        if timings:
                            for k in total_timings:
                                total_timings[k] += timings.get(k, 0.0)
                        while last_printed_round + 640 <= total_docs:
                            last_printed_round += 640
                        processed += 1
                    if timings and n:
                        lp = timings.get("load_parse", 0)
                        ch = timings.get("chunk", 0)
                        em = timings.get("embed", 0)
                        mb = timings.get("mongo_bulk_write", 0)
                        db_del = timings.get("db_delete", 0)
                        filename = os.path.basename(filepath)
                        thr = n / total_s if total_s > 0 else 0
                        lat_ms = (total_s / n * 1000) if n else 0
                        embed_pct = int(100 * em / total_s) if total_s > 0 else 0
                        mongo_ns = f"{settings.mongodb_db}.{settings.mongodb_collection}"
                        ts = datetime.now().astimezone().replace(microsecond=0).isoformat()
                        print(f"{ts} {pod_name} INGEST shard={filename} chunks={n} total_s={total_s:.2f} thr={thr:.1f}cps lat_ms={lat_ms:.1f} embed_s={em:.2f}({embed_pct}%) write_s={mb:.2f} chunk_s={ch:.2f} db_del_s={db_del:.2f} parse_s={lp:.2f} durable_s={total_s:.2f} errors=0 mongo={mongo_ns}", flush=True)
                    else:
                        filename = os.path.basename(filepath)
                        mongo_ns = f"{settings.mongodb_db}.{settings.mongodb_collection}"
                        ts = datetime.now().astimezone().replace(microsecond=0).isoformat()
                        print(f"{ts} {pod_name} INGEST shard={filename} chunks={n} durable_s={total_s:.2f} errors=0 mongo={mongo_ns}", flush=True)
                except Exception as e:
                    errors += 1
                    print(f"  ✗ {filepath}: {e}", flush=True)
                    import traceback
                    traceback.print_exc()
                    mongo_ns = f"{settings.mongodb_db}.{settings.mongodb_collection}"
                    ts = datetime.now().astimezone().replace(microsecond=0).isoformat()
                    print(f"{ts} {pod_name} INGEST shard={os.path.basename(filepath)} durable_s=0 chunks=0 errors=1 mongo={mongo_ns}", flush=True)

        await asyncio.gather(*[process_with_semaphore(fp, i + 1) for i, fp in enumerate(to_process)])

        wall_s = time.perf_counter() - start
        mongo_ns = f"{settings.mongodb_db}.{settings.mongodb_collection}"
        ts_end = datetime.now().astimezone().replace(microsecond=0).isoformat()

        # RUN_SUMMARY once per pipeline: last pod to finish aggregates and prints
        if job_total is None or job_total == 1:
            avg_thr = total_docs / wall_s if wall_s > 0 else 0
            print(flush=True)
            print(f"{ts_end} RUN_SUMMARY mode={pod_name} shards={processed} total_chunks={total_docs} wall_s={wall_s:.2f} avg_thr={avg_thr:.1f}cps errors={errors} mongo={mongo_ns}", flush=True)
        else:
            idx = job_index if job_index is not None else 0
            _write_run_done(input_dir, idx, total_docs, errors, ts_end)
            done_count = _list_run_done_count(input_dir)
            if done_count >= job_total:
                start_ts = _read_run_start(input_dir)
                dones = _read_all_run_done(input_dir)
                agg_chunks = sum(d.get("chunks", 0) for d in dones)
                agg_errors = sum(d.get("errors", 0) for d in dones)
                try:
                    t0 = datetime.fromisoformat(start_ts) if start_ts else None
                    t1 = max(datetime.fromisoformat(d.get("ts", "")) for d in dones) if dones else None
                    wall_s = (t1 - t0).total_seconds() if t0 and t1 else wall_s
                except Exception:
                    pass
                avg_thr = agg_chunks / wall_s if wall_s > 0 else 0
                print(flush=True)
                print(f"{ts_end} RUN_SUMMARY mode={pod_name} shards={total_pipeline_shards} total_chunks={agg_chunks} wall_s={wall_s:.2f} avg_thr={avg_thr:.1f}cps errors={agg_errors} mongo={mongo_ns}", flush=True)
                _remove_run_meta(input_dir)

        if skip_unchanged:
            save_state(state)

    asyncio.run(_run())


def add_ingest_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--env", default="dev")
    parser.add_argument("--target", default="localhost", choices=["localhost", "atlas"], help="MongoDB: localhost or atlas")
    parser.add_argument("--mode", choices=["sync", "async"], default="async")
    parser.add_argument("--max-inflight", type=int, default=128)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--embedder", default="ollama")
    parser.add_argument("--input-dir", default="./data", help="Directory to glob for files (default: ./data)")
    parser.add_argument("--pattern", default="**/*", help="Glob pattern under input-dir, e.g. *.json (default: **/*)")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dry-run", action="store_true")


def _ingest_glob(args: argparse.Namespace) -> str:
    """Build effective file glob from --input-dir and --pattern (recursive if pattern has no **)."""
    base = args.input_dir.rstrip(os.sep)
    pat = args.pattern.lstrip(os.sep).replace("\\", "/")
    if "**" in pat:
        combined = f"{base}{os.sep}{pat}"
    else:
        combined = f"{base}{os.sep}**{os.sep}{pat}"
    return combined.replace("\\", "/")


def _ingest_input_dir_and_pattern(folder_glob: str) -> Tuple[str, str]:
    """Derive input_dir and pattern from folder_glob for config logging."""
    if "**" in folder_glob:
        before, rest = folder_glob.split("**", 1)
        input_dir = before.rstrip("/").rstrip(os.sep) or "."
        pattern = "**" + rest
    else:
        input_dir = os.path.dirname(folder_glob) or "."
        pattern = os.path.basename(folder_glob)
    return input_dir, pattern


def _log_ingest_config(settings: Settings, folder_glob: str, mode: str) -> None:
    """Print startup config (target, batch_size, mode, embedder, input_dir, pattern) and k8s env when set."""
    target = "atlas" if (settings.mongodb_uri and "mongodb+srv" in settings.mongodb_uri) else "localhost"
    input_dir, pattern = _ingest_input_dir_and_pattern(folder_glob)
    print(
        f"Config: target={target} batch_size={settings.batch_size} mode={mode} embedder={settings.embed_provider} "
        f"embed_model={settings.embed_model} input_dir={input_dir} pattern={pattern}",
        flush=True,
    )
    k8s_parts = []
    for key in ("JOB_PARALLELISM", "JOB_COMPLETION_INDEX", "JOB_COMPLETIONS", "STATE_FILE"):
        val = os.environ.get(key, "").strip()
        if val:
            k8s_parts.append(f"{key}={val}")
    if k8s_parts:
        print("K8s: " + " ".join(k8s_parts), flush=True)


if __name__ == "__main__":
    # Drop empty/whitespace-only args (e.g. from multiline paste or docker-compose) so we don't get "unrecognized arguments"
    sys.argv = [a for a in sys.argv if a and a.strip()]

    # Line-buffer stdout so progress logs appear as they're printed (not in one shot at the end, e.g. in Docker)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)

    COLLECTIONS = {"dev": "collection_taixingbi_dev", "qa": "collection_taixingbi_qa", "prod": "collection_taixingbi_prod"}

    parser = argparse.ArgumentParser(description="RAG ingest: chunk, embed, upsert to MongoDB")
    subparsers = parser.add_subparsers(dest="command", required=True)
    ingest_parser = subparsers.add_parser("ingest", help="Run ingest pipeline")
    add_ingest_args(ingest_parser)
    args = parser.parse_args()

    assert args.command == "ingest"
    folder_glob = _ingest_glob(args)

    # Env: set collection
    if args.env in COLLECTIONS:
        os.environ["MONGODB_COLLECTION"] = COLLECTIONS[args.env]
    # Target: which MongoDB
    if args.target == "localhost":
        os.environ["MONGODB_URI"] = os.environ.get("MONGODB_URI_LOCAL", "mongodb://localhost:27017")

    # Embedder -> EMBED_PROVIDER (openai | ollama | vllm)
    if args.embedder == "openai":
        os.environ["EMBED_PROVIDER"] = "openai"
    elif args.embedder == "ollama":
        os.environ["EMBED_PROVIDER"] = "ollama"
    elif args.embedder == "vllm":
        os.environ["EMBED_PROVIDER"] = "vllm"
    else:
        raise ValueError(f"Unsupported --embedder={args.embedder!r}; use openai, ollama, or vllm.")
    os.environ["BATCH_SIZE"] = str(args.batch_size)

    skip_unchanged = not args.force
    use_async = args.mode == "async"

    # Indexed Job: per-pod state and partition files by job index
    job_index_val: Optional[int] = None
    job_total_val: Optional[int] = None
    job_completion_index = os.environ.get("JOB_COMPLETION_INDEX", "").strip()
    job_parallelism = os.environ.get("JOB_PARALLELISM", "").strip()
    if job_completion_index != "" and job_parallelism != "":
        try:
            job_index_val = int(job_completion_index)
            job_total_val = int(job_parallelism)
            os.environ["STATE_FILE"] = f"/data/state-{job_completion_index}.json"
        except ValueError:
            pass

    if use_async:
        ingest_folder_async(folder_glob, skip_unchanged=skip_unchanged, job_index=job_index_val, job_total=job_total_val, mode=args.mode)
    else:
        ingest_folder(folder_glob, skip_unchanged=skip_unchanged, job_index=job_index_val, job_total=job_total_val, mode=args.mode)

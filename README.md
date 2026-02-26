# RAG Ingest - MongoDB Atlas Vector Search

Local ingestion pipeline that reads files (JSON/MD/PDF), chunks them, computes embeddings, and upserts into MongoDB Atlas Vector Search.

## Architecture

- **Mac mini (local)**: Reads files → chunks → computes embeddings (OpenAI, ollama, or vLLM) → upserts to Atlas
- **MongoDB Atlas**: Stores text + metadata + embedding vector with Vector Search index


## Setup

```bash
python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip 
pip install -r requirements.txt

# Optional: For PDF support
pip install pdfplumber
```

## Configuration (.env)

```bash
MONGODB_URI="mongodb+srv://<user>:<pass>@<cluster>/<db>?retryWrites=true&w=majority"
MONGODB_DB="rag"
MONGODB_COLLECTION="rag_chunks"

# Embed: openai | ollama | vllm (default: ollama)
EMBED_PROVIDER=ollama
OPENAI_API_KEY="sk-..."
OPENAI_EMBED_MODEL="text-embedding-3-small"  # or text-embedding-3-large (openai only)

# Self-hosted (no TPM limit):
#   ollama: EMBED_PROVIDER=ollama, EMBED_MODEL=nomic-embed-text (default), EMBED_BASE_URL=http://localhost:11434/v1. Install: ollama serve then ollama pull nomic-embed-text (use pull, not run)
#   vllm: EMBED_PROVIDER=vllm, EMBED_MODEL=<your-model>, EMBED_BASE_URL=http://localhost:8000/v1
# EMBED_BASE_URL=   # override for ollama/vllm (defaults: 11434/v1 for ollama, 8000/v1 for vllm). From Docker with Ollama on host: http://host.docker.internal:11434/v1
# EMBED_DIMS=      # optional; embedding dimension hint for Atlas Vector Search index (ollama/vllm; used in "Next steps" print)

CHUNK_TOKENS=1000
OVERLAP_TOKENS=150
BATCH_SIZE=128
EMBED_MAX_CONCURRENT=8
MAX_CONCURRENT_FILES=6
# Token bucket (OpenAI only; ignored for ollama, vllm)
EMBED_TPM_SAFETY=0.9
# OPENAI_TPM_LIMIT=1000000   # set higher if your account has more TPM
```

## Docker (docker-compose)

Requires a `.env` in the project root (see Configuration). Put input files under `./data` on the host; they are mounted at `/data` in the container.

**MongoDB from Docker:** The default command uses `--target atlas`, so `MONGODB_URI` in `.env` must be your **Atlas** connection string (`mongodb+srv://...`). If it is `mongodb://localhost:27017`, the container will try to reach MongoDB inside the container and get "Connection refused". To use MongoDB running on your host Mac from inside the container, use `--target localhost` and set in `.env`: `MONGODB_URI_LOCAL=mongodb://host.docker.internal:27017`.

**Ollama from Docker:** If ingest runs in Docker and Ollama runs on the host Mac, the container cannot use `localhost:11434`. In `.env` set `EMBED_BASE_URL=http://host.docker.internal:11434/v1` so the container reaches Ollama on the host.

**One-off ingest (recommended)** — uses default command with `/data`, `--force`, in-process async:

```bash
docker-compose run --rm rag-ingest
```

Run this **exact** one-liner (nothing after `rag-ingest`). Pasting a multi-line command without `\` at the end of each line will make zsh run the next line as a new command (`command not found: --target`). Adding flags like `--force` after `rag-ingest` replaces the whole command and can cause "unrecognized arguments".

**Custom command** — if you override, use `--input-dir /data` (path inside the container):

```bash
# Async (default, in-process)
docker-compose run --rm rag-ingest python main.py ingest \
  --input-dir /data --pattern "**/*" \
  --env dev --target atlas --mode async --force

# Sync
docker-compose run --rm rag-ingest python main.py ingest \
  --input-dir /data --env dev --target atlas --force
```

## Usage
Options:
`--env` (dev|qa|prod), default: dev.
`--target` (localhost|atlas), which MongoDB to write to.
`--input-dir` (default: ./data), directory to glob for files.
`--pattern` (default: **/*), glob under input-dir, e.g. *.json.
`--mode` (sync|async), default: async (in-process).
`--max-inflight` (default: 128), max in-flight tasks.
`--batch-size` (default: 64), embedding batch size.
`--embedder` (default: ollama): openai, ollama, or vllm.
`--force`, re-ingest all files (ignore state).
`--resume`, resume from state (if supported).
`--dry-run`, don't write to DB (if supported).

python main.py ingest \
  --env dev \
  --target atlas \
  --mode async \
  --batch-size 64 \
  --embedder ollama \
  --input-dir ./data \
  --pattern "*.json" \
  --force

docker build -t rag-ingest:latest .

docker-compose run --rm rag-ingest python main.py ingest \
  --env dev \
  --target atlas \
  --mode sync \
  --batch-size 64 \
  --embedder ollama \
  --input-dir /data \
  --pattern "*.json" \
  --force

For **Kubernetes** deployment (Job on cluster), see [k8s.md](k8s.md).

## Data Model

Collection: `rag.rag_chunks`

Each chunk document:
```json
{
  "_id": "sha256(source_id + chunk_id + content_hash)",
  "chunk_id": "profile.json::chunk_0003",
  "source": {
    "source_id": "profile.json",
    "path": "data/profile.json",
    "type": "json",
    "mtime": "2026-02-19T12:00:00Z"
  },
  "text": "chunk text...",
  "metadata": {
    "title": "Profile",
    "section": "chunk_0",
    "tags": ["profile", "resume", "candidate"],
    "lang": "en"
  },
  "embedding": [0.0123, ...],
  "embedding_model": "text-embedding-3-small",
  "dims": 1536,
  "created_at": "2026-02-19T12:01:00Z",
  "updated_at": "2026-02-19T12:01:00Z"
}
```

## MongoDB Atlas Vector Search Index

After ingestion, create a Vector Search index in Atlas UI:

1. Go to Atlas → Search → Create Search Index
2. Select "JSON Editor"
3. Configure:
```json
{
  "fields": [
    {
      "type": "knnVector",
      "path": "embedding",
      "numDimensions": 1536,
      "similarity": "cosine"
    },
    {
      "type": "string",
      "path": "source.source_id"
    },
    {
      "type": "string",
      "path": "metadata.tags"
    },
    {
      "type": "string",
      "path": "text"
    }
  ]
}
```

## Incremental Ingestion

The pipeline uses `state.json` to track file hashes and modification times. Files that haven't changed are automatically skipped. Delete `state.json` to reset or use `--force` flag to re-ingest everything.

## Supported File Types

- **JSON**: Automatically normalized (sorted keys, stable format)
- **Markdown (.md)**: Text extracted as-is
- **Text (.txt)**: Plain text files
- **PDF**: Requires `pdfplumber` package

## MongoDB Collections

Update collection name in `.env`:
```
MONGODB_COLLECTION=collection_taixingbi_dev
MONGODB_COLLECTION=collection_taixingbi_qa
MONGODB_COLLECTION=collection_taixingbi_prod
```

## Links

- [MongoDB Atlas Dashboard](https://cloud.mongodb.com/v2/5f8d901d427b1f41a5daf2c0#/explorer/6994e45919851ad449223e8a/db_hunt/collection_taixingbi_dev/find)

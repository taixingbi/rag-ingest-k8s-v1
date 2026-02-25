# RAG Ingest - MongoDB Atlas Vector Search

## Configuration (.env)

```bash
MONGODB_URI="mongodb+srv://<user>:<pass>@<cluster>/<db>?retryWrites=true&w=majority"
MONGODB_DB="rag"
MONGODB_COLLECTION="rag_chunks"

# Embed: openai (TPM-limited) or sentence_transformers (local, no TPM limit)
EMBED_PROVIDER=openai
OPENAI_API_KEY="sk-..."
OPENAI_EMBED_MODEL="text-embedding-3-small"  # or text-embedding-3-large

# For local embeddings (no TPM limit, lower latency): EMBED_PROVIDER=sentence_transformers, EMBED_MODEL=BAAI/bge-small-en-v1.5
# EMBED_BATCH_SIZE_LOCAL=256   # larger = faster encode (sentence_transformers only)
# EMBED_DEVICE=cuda            # or mps, cpu (sentence_transformers only; default auto)

CHUNK_TOKENS=1000
OVERLAP_TOKENS=150
BATCH_SIZE=128
EMBED_MAX_CONCURRENT=8
MAX_CONCURRENT_FILES=6
# Token bucket (OpenAI only; ignored when EMBED_PROVIDER=sentence_transformers)
EMBED_TPM_SAFETY=0.9
# OPENAI_TPM_LIMIT=1000000   # set higher if your account has more TPM
```

## Docker (docker-compose)

Requires a `.env` in the project root (see Configuration). Put input files under `./data` on the host; they are mounted at `/data` in the container.

**MongoDB from Docker:** The default command uses `--target atlas`, so `MONGODB_URI` in `.env` must be your **Atlas** connection string (`mongodb+srv://...`). If it is `mongodb://localhost:27017`, the container will try to reach MongoDB inside the container and get "Connection refused". To use MongoDB running on your host Mac from inside the container, use `--target localhost` and set in `.env`: `MONGODB_URI_LOCAL=mongodb://host.docker.internal:27017`.

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
`--embedder` (default: sentence-transformers), openai or sentence-transformers.
`--force`, re-ingest all files (ignore state).
`--resume`, resume from state (if supported).
`--dry-run`, don't write to DB (if supported).

python main.py ingest \
  --env dev \
  --target atlas \
  --mode async \
  --batch-size 32 \
  --embedder sentence-transformers \
  --input-dir ./data \
  --pattern "*.json" \
  --force

docker-compose run --rm rag-ingest python main.py ingest \
  --env dev \
  --target atlas \
  --mode async \
  --batch-size 32 \
  --embedder sentence-transformers \
  --input-dir /data \
  --pattern "*.json" \
  --force

## Kubernetes (step-by-step)

Run one-off ingest as a **Job** on any Kubernetes cluster (Docker Desktop, minikube, or remote). No queue services—single Job, then exit. Defaults are tuned for Mac mini 4 / low-resource; increase `resources` in `job.yaml` and ConfigMap batch/concurrency for stronger nodes.

---

### Step 1: Ensure you have a cluster and kubectl

- **Docker Desktop:** Settings → Kubernetes → Enable Kubernetes → Apply & Restart. When the Kubernetes icon is green:
  ```bash
  kubectl config use-context docker-desktop
  ```
- **minikube:** `minikube start` then `kubectl config use-context minikube`
- **Remote:** Configure `KUBECONFIG` and set your context.

Check:
```bash
kubectl config current-context
kubectl cluster-info
```

---

### Step 2: Create the Secret (credentials)

Create the secret with your **real** MongoDB Atlas URI and OpenAI API key (do not commit these):

```bash
kubectl create secret generic rag-ingest-secret \
  --from-literal=MONGODB_URI='mongodb+srv://USER:PASSWORD@cluster.xxxxx.mongodb.net/?retryWrites=true&w=majority' \
  --from-literal=OPENAI_API_KEY='sk-proj-...'
```

Verify:
```bash
kubectl get secret rag-ingest-secret
```

---

### Step 3: Build the container image

From the project root:

```bash
docker build -t rag-ingest:latest .
```

- **Local cluster (Docker Desktop / minikube):** The Job uses `rag-ingest:latest` and `imagePullPolicy: Never`, so the cluster will use this local image. No registry needed.
- **Remote cluster:** Push to your registry and update `k8s/job.yaml`: set `image` to e.g. `your-registry/rag-ingest:latest` and `imagePullPolicy: Always` (or remove the line).

---

### Step 4: Apply Kubernetes manifests

Apply ConfigMap, PVC, and Job (do **not** apply `k8s/secret.yaml` if you created the secret in Step 2):

```bash
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/pvc.yaml
kubectl apply -f k8s/job.yaml
```

Expected output:
```
configmap/rag-ingest-config created
persistentvolumeclaim/rag-ingest-data created
job.batch/rag-ingest created
```

---

### Step 5: (Optional) Put input files in the volume

The Job reads from `/data` (mounted from PVC `rag-ingest-data`). If the PVC is empty, the ingest will find no files.

**Option A — Copy from your machine using a temporary pod:**

```bash
kubectl apply -f k8s/data-loader-pod.yaml
kubectl wait --for=condition=Ready pod/data-loader --timeout=60s
kubectl exec data-loader -- sh -c 'rm -rf /data/*'
kubectl cp ./data data-loader:/data/
kubectl delete pod data-loader
```

**Option B —** Use an init container or a different volume (e.g. hostPath) in `k8s/job.yaml` if your data already lives somewhere the cluster can mount.

---

### Step 6: Watch the Job run

```bash
# Job and pod status
kubectl get job rag-ingest
kubectl get pods -l app=rag-ingest

# Stream logs (replace POD_NAME if needed)
kubectl logs -f job/rag-ingest
```

---

### Step 7: Re-run or clean up

- **Run the Job again** (e.g. after adding more files to the PVC):
  ```bash
  kubectl delete job rag-ingest
  kubectl apply -f k8s/job.yaml
  ```
- **Remove everything:**
  ```bash
  kubectl delete job rag-ingest
  kubectl delete pvc rag-ingest-data
  kubectl delete configmap rag-ingest-config
  kubectl delete secret rag-ingest-secret
  ```

---

### Files in `k8s/`

| File | Purpose |
|------|--------|
| `configmap.yaml` | Non-sensitive env (MONGODB_DB, MONGODB_COLLECTION, chunk/batch, EMBED_PROVIDER). Edit to match your env. |
| `secret.yaml` | Optional; only if you want to manage secrets from a file. Prefer `kubectl create secret` (Step 2). |
| `pvc.yaml` | PersistentVolumeClaim for `/data` and state; 5Gi. |
| `job.yaml` | One-off ingest Job; uses ConfigMap + Secret + PVC. |
| `data-loader-pod.yaml` | Optional; temporary pod to copy host `./data` into the PVC (see Step 5). |

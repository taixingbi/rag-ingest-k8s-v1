## Docker (docker-compose)

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

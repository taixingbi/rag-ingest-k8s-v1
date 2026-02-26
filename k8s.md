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

**Indexed Job (2 pods):** The Job uses `completionMode: Indexed` with `completions: 2` and `parallelism: 2`, so two pods run at once. Each pod gets a unique `JOB_COMPLETION_INDEX` (0 or 1) from Kubernetes and processes a disjoint subset of files: pod 0 handles files at index 0, 2, 4, ... and pod 1 handles 1, 3, 5, ... (partition by `file_index % job_total == job_index`). Each pod uses its own state file (`/data/state-0.json`, `/data/state-1.json`) to avoid conflicts on the shared PVC. To change the number of pods, update `completions`, `parallelism`, and the `JOB_PARALLELISM` env var in `k8s/job.yaml` so they all match, then delete and re-apply the Job.

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

If `kubectl wait` times out or you see "cannot exec into a container in a completed pod; current phase is Failed", the pod failed before becoming Ready. Check why: `kubectl describe pod data-loader` and `kubectl logs data-loader`. Common causes: PVC `rag-ingest-data` not bound (create it first with `kubectl apply -f k8s/pvc.yaml`), or the cluster cannot pull the `busybox` image. Fix the issue, then delete the pod and re-run the apply/wait/cp/delete steps.

**Option B —** Use an init container or a different volume (e.g. hostPath) in `k8s/job.yaml` if your data already lives somewhere the cluster can mount.

---

### Step 6: Watch the Job run

```bash
# Job and pod status
kubectl get job rag-ingest
kubectl get pods -l app=rag-ingest

kubectl logs -l job-name=rag-ingest --all-containers=true
```

---

### Step 7: Re-run or clean up

- **Run the Job again** (e.g. after adding more files to the PVC, or after changing `job.yaml`):
  ```bash
  kubectl delete job rag-ingest
  kubectl apply -f k8s/job.yaml
  ```
  Job `spec.template` and `spec.completionMode` are immutable; if `kubectl apply` reports "field is immutable", delete the job first, then apply.
- **Remove everything:**
  ```bash
  kubectl delete job rag-ingest
  kubectl delete pvc rag-ingest-data
  kubectl delete configmap rag-ingest-config
  kubectl delete secret rag-ingest-secret
  ```

---

### command 
 ```bash
kubectl get job rag-ingest -o yaml
  ```
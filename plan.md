Remove queue/Redis/RabbitMQ and use simple K8s

Current state





Queue/Redis/RabbitMQ: Implemented for RabbitMQ only: queue_rabbit.py (aio_pika), config.py (amqp_url, rabbitmq_queue), main.py (--queue with none|memory|redis|rabbitmq, RabbitMQ branch), docker-compose.yml (rabbitmq service + AMQP env), requirements.txt (aio-pika). There is no queue_redis.py; "redis" only appears in CLI choices and docs.



K8s: No Kubernetes manifests exist in the repo. The app runs via Docker Compose today.

Note: The standard-library queue.Queue in main.py (used for block_queue in NDJSON processing) is in-process flow control only—not an external queue—so it stays.



Part 1: Remove queue / Redis / RabbitMQ







Area



Change





Code



Delete queue_rabbit.py.





config.py



Remove amqp_url and rabbitmq_queue (and any comment tying config to RabbitMQ).





main.py



Remove --queue argument (or reduce to a single effective mode). Remove the use_rabbitmq branch that imports and calls ingest_via_rabbitmq; always use ingest_folder_async when --mode async and ingest_folder when sync.





requirements.txt



Remove the RabbitMQ comment and the aio-pika>=9.0.0 line.





docker-compose.yml



Remove the rabbitmq service, depends_on, and all AMQP_* / RABBITMQ_* env. Make rag-ingest the only service; default command should use --mode async without any --queue (in-process async only). Remove rabbitmq_data volume.





Docs



Update README.md (and any other docs like tmp.md, PLAN_QUEUE_ASYNC_DOCKER.md) to drop references to --queue, Redis, and RabbitMQ; describe only sync vs async and the new default command.

Result: one way to run ingest—sync or in-process async—with no external queue or broker.



Part 2: Simple Kubernetes setup

Add a minimal k8s/ (or kubernetes/) directory with only what’s needed to run the ingest app in-cluster, no queue infrastructure.





Deployment (or Job): Single workload that runs the existing image (built from Dockerfile). Command: same as the simplified compose default, e.g. python main.py ingest --input-dir /data --pattern "**/*" --env dev --target atlas --mode async --force. Use a Job if ingest is one-off (run once, exit); use a Deployment if you want a long-running or repeatable process. For “simple,” a Job is often enough.



ConfigMap: Non-sensitive env (e.g. MONGODB_DB, MONGODB_COLLECTION, CHUNK_*, BATCH_SIZE, EMBED_PROVIDER, EMBED_MODEL). Reference from the Job/Deployment.



Secret: Sensitive env (e.g. MONGODB_URI, OPENAI_API_KEY). Mount or inject as env from a Secret.



Volume for data/state: Use a PVC (or emptyDir for ephemeral runs) and mount at /data and optionally where state.json lives (e.g. /app/state.json) so resume works if you use a Job with a shared volume.

No Redis, RabbitMQ, or queue-related Services/Deployments in K8s.

flowchart LR
  subgraph k8s [K8s cluster]
    Job[Job or Deployment]
    ConfigMap[ConfigMap]
    Secret[Secret]
    PVC[PVC optional]
    Job --> ConfigMap
    Job --> Secret
    Job --> PVC
  end
  Job -->|ingest| Mongo[(MongoDB Atlas)]

Optional: a Service is only needed if something must call the app over the network; for a batch ingest Job, it can be omitted.



File summary







Action



File





Delete



queue_rabbit.py





Edit



config.py, main.py, requirements.txt, docker-compose.yml, README.md (and optionally tmp.md, PLAN_QUEUE_ASYNC_DOCKER.md)





Add



k8s/job.yaml (or deployment.yaml), k8s/configmap.yaml, k8s/secret.yaml (or a kustomize/env approach), optional k8s/pvc.yaml

Image: assume the app image is built and pushed to a registry (e.g. your-registry/rag-ingest:latest); the manifests will reference that image. No change to the Dockerfile beyond what’s already there.



Clarification





Prefer a Job (run once to completion) or a Deployment (keeps one pod running / restartable) for the ingest app in K8s? Default recommendation: Job for “run ingest and exit” simplicity.


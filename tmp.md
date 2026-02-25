
python main.py ingest \
  --env dev \
  --target atlas \
  --mode sync \
  --batch-size 32 \
  --embedder sentence-transformers \
  --input-dir ./data \
  --pattern "*.json" \
  --force

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
  --mode sync \
  --batch-size 32 \
  --embedder sentence-transformers \
  --input-dir /data \
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
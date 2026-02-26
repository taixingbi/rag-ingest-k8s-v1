python main.py ingest \
  --env dev \
  --target atlas \
  --mode async \
  --batch-size 32 \
  --embedder sentence-transformers \
  --input-dir ./data \
  --pattern "*.json" \
  --force
Embed: sentence_transformers (BAAI/bge-small-en-v1.5)
Found 4 files; 4 to process, 0 skipped (unchanged)
file 1/4: INGEST shard=wiki_shard_001.json chunks=90 total=2.707s thr=33.2c/s lat=30.1ms | embed=2.292s(84.7%) write=0.260s(9.6%) chunk=0.069s db_del=0.074s parse=0.002s
file 2/4: INGEST shard=wiki_shard_002.json chunks=90 total=3.647s thr=24.7c/s lat=40.5ms | embed=2.270s(62.2%) write=0.262s(7.2%) chunk=0.041s db_del=1.061s parse=0.006s
file 3/4: INGEST shard=wiki_shard_003.json chunks=107 total=3.888s thr=27.5c/s lat=36.3ms | embed=2.756s(70.9%) write=1.070s(27.5%) chunk=0.032s db_del=0.017s parse=0.004s
file 4/4: INGEST shard=wiki_shard_004.json chunks=113 total=4.181s thr=27.0c/s lat=37.0ms | embed=3.007s(71.9%) write=1.104s(26.4%) chunk=0.036s db_del=0.020s parse=0.005s
  total summary: load_parse=0.018s chunk=0.178s embed=10.325s mongo_bulk_write=2.696s chunks=400

Done (async).
  Durable time: 18.62s
  Total chunks upserted: 400
  Files processed: 4, errors: 0
  MongoDB: db_hunt.collection_taixingbi_dev



(venv) h@hs-mac-mini rag-ingest-k8s-v1 % kubectl logs -l job-name=rag-ingest --all-containers=true
Found 2 files; 2 to process, 0 skipped (unchanged)
file 1/2: INGEST shard=wiki_shard_001.json chunks=90 total=7.869s thr=11.4c/s lat=87.4ms | embed=6.891s(87.6%) write=0.246s(3.1%) chunk=0.696s db_del=0.025s parse=0.003s
file 2/2: INGEST shard=wiki_shard_003.json chunks=107 total=9.138s thr=11.7c/s lat=85.4ms | embed=8.000s(87.5%) write=1.067s(11.7%) chunk=0.028s db_del=0.030s parse=0.006s
  total summary: load_parse=0.009s chunk=0.724s embed=14.892s mongo_bulk_write=1.314s chunks=197

Done (async).
  Durable time: 26.47s
  Total chunks upserted: 197
  Files processed: 2, errors: 0
  MongoDB: db_hunt.collection_taixingbi_dev

  
Found 2 files; 2 to process, 0 skipped (unchanged)
file 1/2: INGEST shard=wiki_shard_002.json chunks=90 total=8.201s thr=11.0c/s lat=91.1ms | embed=7.032s(85.7%) write=0.260s(3.2%) chunk=0.866s db_del=0.031s parse=0.004s
file 2/2: INGEST shard=wiki_shard_004.json chunks=113 total=9.826s thr=11.5c/s lat=87.0ms | embed=8.672s(88.3%) write=1.089s(11.1%) chunk=0.027s db_del=0.027s parse=0.007s
  total summary: load_parse=0.011s chunk=0.893s embed=15.704s mongo_bulk_write=1.349s chunks=203

Done (async).
  Durable time: 26.45s
  Total chunks upserted: 203
  Files processed: 2, errors: 0



(venv) h@hs-mac-mini rag-ingest-k8s-cpu-v1 % docker-compose run --rm rag-ingest python main.py ingest \
  --env dev \
  --target atlas \
  --mode async \
  --batch-size 32 \
  --embedder ollama \
  --input-dir /data \
  --pattern "*.json" \
  --force
Container rag-ingest-k8s-cpu-v1-rag-ingest-run-11c2371911cd Creating 
Container rag-ingest-k8s-cpu-v1-rag-ingest-run-11c2371911cd Created 
Warning: could not load state from state.json: [Errno 21] Is a directory: 'state.json'
2026-02-26T04:05:23+00:00 RUN_START mode=aa9f4f72ca62 embedder=ollama model=nomic-embed-text shards=6 input_dir=/data
2026-02-26T04:06:15+00:00 aa9f4f72ca62 INGEST shard=wiki_shard_006.json chunks=89 total_s=51.34 thr=1.7cps lat_ms=576.8 embed_s=50.93(99%) write_s=0.35 chunk_s=0.01 db_del_s=0.03 parse_s=0.00 durable_s=51.34 errors=0 mongo=db_hunt.collection_taixingbi_dev
2026-02-26T04:08:21+00:00 aa9f4f72ca62 INGEST shard=wiki_shard_003.json chunks=823 total_s=176.90 thr=4.7cps lat_ms=214.9 embed_s=172.42(97%) write_s=4.23 chunk_s=0.12 db_del_s=0.03 parse_s=0.02 durable_s=176.90 errors=0 mongo=db_hunt.collection_taixingbi_dev
2026-02-26T04:08:23+00:00 aa9f4f72ca62 INGEST shard=wiki_shard_002.json chunks=830 total_s=179.94 thr=4.6cps lat_ms=216.8 embed_s=174.49(96%) write_s=3.16 chunk_s=0.11 db_del_s=2.14 parse_s=0.02 durable_s=179.94 errors=0 mongo=db_hunt.collection_taixingbi_dev
2026-02-26T04:08:27+00:00 aa9f4f72ca62 INGEST shard=wiki_shard_004.json chunks=831 total_s=183.71 thr=4.5cps lat_ms=221.1 embed_s=178.09(96%) write_s=4.21 chunk_s=0.12 db_del_s=1.25 parse_s=0.02 durable_s=183.71 errors=0 mongo=db_hunt.collection_taixingbi_dev
2026-02-26T04:08:36+00:00 aa9f4f72ca62 INGEST shard=wiki_shard_005.json chunks=848 total_s=191.63 thr=4.4cps lat_ms=226.0 embed_s=186.18(97%) write_s=5.24 chunk_s=0.12 db_del_s=0.02 parse_s=0.02 durable_s=191.63 errors=0 mongo=db_hunt.collection_taixingbi_dev
2026-02-26T04:08:37+00:00 aa9f4f72ca62 INGEST shard=wiki_shard_001.json chunks=872 total_s=193.84 thr=4.5cps lat_ms=222.3 embed_s=187.44(96%) write_s=5.17 chunk_s=0.76 db_del_s=0.39 parse_s=0.03 durable_s=193.84 errors=0 mongo=db_hunt.collection_taixingbi_dev

2026-02-26T04:08:37+00:00 RUN_SUMMARY mode=aa9f4f72ca62 shards=6 total_chunks=4293 wall_s=194.35 avg_thr=22.1cps errors=0 mongo=db_hunt.collection_taixingbi_dev


(venv) h@hs-mac-mini rag-ingest-k8s-cpu-v1 % docker-compose run --rm rag-ingest python main.py ingest \
  --env dev \
  --target atlas \
  --mode sync \
  --batch-size 32 \
  --embedder ollama \
  --input-dir /data \
  --pattern "*.json" \
  --force
Container rag-ingest-k8s-cpu-v1-rag-ingest-run-72b48181bf99 Creating 
Container rag-ingest-k8s-cpu-v1-rag-ingest-run-72b48181bf99 Created 
Embed: ollama (nomic-embed-text)
Warning: could not load state from state.json: [Errno 21] Is a directory: 'state.json'
Found 6 files matching pattern
file 1/6: INGEST shard=wiki_shard_001.json chunks=872 total=47.380s thr=18.4c/s lat=54.3ms | embed=40.452s(85.4%) write=5.974s(12.6%) chunk=0.798s db_del=0.100s parse=0.029s
file 2/6: INGEST shard=wiki_shard_002.json chunks=831 total=30.794s thr=27.0c/s lat=37.1ms | embed=25.798s(83.8%) write=4.749s(15.4%) chunk=0.127s db_del=0.071s parse=0.026s
file 3/6: INGEST shard=wiki_shard_003.json chunks=823 total=47.088s thr=17.5c/s lat=57.2ms | embed=41.037s(87.2%) write=5.733s(12.2%) chunk=0.171s db_del=0.091s parse=0.028s
file 4/6: INGEST shard=wiki_shard_004.json chunks=831 total=39.726s thr=20.9c/s lat=47.8ms | embed=34.753s(87.5%) write=4.716s(11.9%) chunk=0.135s db_del=0.076s parse=0.027s
file 5/6: INGEST shard=wiki_shard_005.json chunks=848 total=43.351s thr=19.6c/s lat=51.1ms | embed=37.257s(85.9%) write=5.782s(13.3%) chunk=0.152s db_del=0.088s parse=0.038s
file 6/6: INGEST shard=wiki_shard_006.json chunks=89 total=9.484s thr=9.4c/s lat=106.6ms | embed=9.055s(95.5%) write=0.364s(3.8%) chunk=0.026s db_del=0.029s parse=0.005s










(venv) h@hs-mac-mini rag-ingest-k8s-cpu-v1 % kubectl logs -l job-name=rag-ingest --all-containers=true

2026-02-26T04:12:55+00:00 rag-ingest-2 INGEST shard=wiki_shard_003.json chunks=823 total_s=46.45 thr=17.7cps lat_ms=56.4 embed_s=40.84(87%) write_s=4.17 chunk_s=1.28 db_del_s=0.07 parse_s=0.03 durable_s=46.45 errors=0 mongo=db_hunt.collection_taixingbi_dev
2026-02-26T04:14:23+00:00 rag-ingest-3 INGEST shard=wiki_shard_004.json chunks=831 total_s=39.80 thr=20.9cps lat_ms=47.9 embed_s=34.73(87%) write_s=4.16 chunk_s=0.76 db_del_s=0.07 parse_s=0.03 durable_s=39.80 errors=0 mongo=db_hunt.collection_taixingbi_dev

2026-02-26T04:14:23+00:00 RUN_SUMMARY mode=rag-ingest-3 shards=6 total_chunks=4293 wall_s=228.00 avg_thr=18.8cps errors=0 mongo=db_hunt.collection_taixingbi_dev
2026-02-26T04:10:35+00:00 RUN_START mode=rag-ingest-0 embedder=ollama model=nomic-embed-text shards=6 input_dir=/data
2026-02-26T04:11:21+00:00 rag-ingest-0 INGEST shard=wiki_shard_001.json chunks=872 total_s=46.91 thr=18.6cps lat_ms=53.8 embed_s=39.90(85%) write_s=6.05 chunk_s=0.80 db_del_s=0.07 parse_s=0.03 durable_s=46.91 errors=0 mongo=db_hunt.collection_taixingbi_dev
2026-02-26T04:12:04+00:00 rag-ingest-0 INGEST shard=wiki_shard_005.json chunks=848 total_s=43.06 thr=19.7cps lat_ms=50.8 embed_s=36.94(85%) write_s=5.84 chunk_s=0.13 db_del_s=0.08 parse_s=0.02 durable_s=43.06 errors=0 mongo=db_hunt.collection_taixingbi_dev
2026-02-26T04:13:29+00:00 rag-ingest-1 INGEST shard=wiki_shard_002.json chunks=830 total_s=30.92 thr=26.8cps lat_ms=37.3 embed_s=25.73(83%) write_s=4.27 chunk_s=0.79 db_del_s=0.06 parse_s=0.02 durable_s=30.92 errors=0 mongo=db_hunt.collection_taixingbi_dev
2026-02-26T04:13:39+00:00 rag-ingest-1 INGEST shard=wiki_shard_006.json chunks=89 total_s=9.43 thr=9.4cps lat_ms=105.9 embed_s=9.03(95%) write_s=0.34 chunk_s=0.02 db_del_s=0.03 parse_s=0.00 durable_s=9.43 errors=0 mongo=db_hunt.collection_taixingbi_dev





Done.
  Durable time: 217.84s
  Total chunks upserted: 4294
  Files skipped (unchanged): 0
  MongoDB: db_hunt.collection_taixingbi_dev


Embed: ollama (nomic-embed-text)

Found 6 files matching pattern

file 1/6: INGEST shard=wiki_shard_001.json chunks=872 total=47.012s thr=18.5c/s lat=53.9ms | embed=40.345s(85.8%) write=5.778s(12.3%) chunk=0.786s db_del=0.064s parse=0.019s

file 2/6: INGEST shard=wiki_shard_002.json chunks=831 total=30.677s thr=27.1c/s lat=36.9ms | embed=25.812s(84.1%) write=4.629s(15.1%) chunk=0.133s db_del=0.056s parse=0.022s

file 3/6: INGEST shard=wiki_shard_003.json chunks=823 total=46.923s thr=17.5c/s lat=57.0ms | embed=41.038s(87.5%) write=5.611s(12.0%) chunk=0.147s db_del=0.068s parse=0.033s

file 4/6: INGEST shard=wiki_shard_004.json chunks=831 total=39.105s thr=21.3c/s lat=47.1ms | embed=34.788s(89.0%) write=4.053s(10.4%) chunk=0.143s db_del=0.067s parse=0.028s

file 5/6: INGEST shard=wiki_shard_005.json chunks=848 total=43.155s thr=19.6c/s lat=50.9ms | embed=37.153s(86.1%) write=5.751s(13.3%) chunk=0.142s db_del=0.050s parse=0.030s

file 6/6: INGEST shard=wiki_shard_006.json chunks=89 total=9.535s thr=9.3c/s lat=107.1ms | embed=9.107s(95.5%) write=0.363s(3.8%) chunk=0.024s db_del=0.032s parse=0.003s


Done.

  Durable time: 216.42s

  Total chunks upserted: 4294

  Files skipped (unchanged): 0

  MongoDB: db_hunt.collection_taixingbi_dev


Next steps:

  1. Create Vector Search index in Atlas UI:

     - Field: embedding (knnVector, dims=1536)

     - Optional filters: source.source_id, metadata.tags

  2. Optional: Add text index for hybrid search (field: text)



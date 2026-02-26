
requests:
      memory: "2Gi"
      cpu: "2"
    limits:
      memory: "2Gi"
      cpu: "2"

Embed: ollama (nomic-embed-text)
Found 2 files; 2 to process, 0 skipped (unchanged)
file 1/2: INGEST shard=wiki_shard_001.json chunks=872 total=287.449s thr=3.0c/s lat=329.6ms | embed=282.409s(98.2%) write=4.054s(1.4%) chunk=0.827s db_del=0.079s parse=0.029s
file 2/2: INGEST shard=wiki_shard_002.json chunks=830 total=280.896s thr=3.0c/s lat=338.4ms | embed=276.561s(98.5%) write=4.100s(1.5%) chunk=0.106s db_del=0.068s parse=0.019s
  total summary: load_parse=0.048s chunk=0.933s embed=558.971s mongo_bulk_write=8.155s chunks=1702

Done (async).
  Durable time: 577.16s
  Total chunks upserted: 1702
  Files processed: 2, errors: 0
  MongoDB: db_hunt.collection_taixingbi_dev


resources:
  limits:
    memory: "8Gi"
    cpu: "1"
  requests:
    memory: "6Gi"
    cpu: "2"

Embed: ollama (nomic-embed-text)
Found 2 files; 2 to process, 0 skipped (unchanged)
file 1/2: INGEST shard=wiki_shard_001.json chunks=872 total=302.367s thr=2.9c/s lat=346.8ms | embed=297.208s(98.3%) write=4.120s(1.4%) chunk=0.890s db_del=0.069s parse=0.029s
file 2/2: INGEST shard=wiki_shard_002.json chunks=830 total=288.566s thr=2.9c/s lat=347.7ms | embed=284.829s(98.7%) write=3.518s(1.2%) chunk=0.105s db_del=0.067s parse=0.019s
  total summary: load_parse=0.048s chunk=0.995s embed=582.036s mongo_bulk_write=7.638s chunks=1702

Done (async).
  Durable time: 600.08s
  Total chunks upserted: 1702
  Files processed: 2, errors: 0
  MongoDB: db_hunt.collection_taixingbi_dev



resources:
  requests:
    memory: "6Gi"
    cpu: "6"
  limits:
    memory: "8Gi"
    cpu: "8"
Found 2 files; 2 to process, 0 skipped (unchanged)
file 1/2: INGEST shard=wiki_shard_001.json chunks=872 total=61.082s thr=14.3c/s lat=70.0ms | embed=55.244s(90.4%) write=4.029s(6.6%) chunk=1.694s db_del=0.047s parse=0.031s
file 2/2: INGEST shard=wiki_shard_002.json chunks=830 total=57.618s thr=14.4c/s lat=69.4ms | embed=53.229s(92.4%) write=4.163s(7.2%) chunk=0.115s db_del=0.053s parse=0.017s
  total summary: load_parse=0.048s chunk=1.809s embed=108.473s mongo_bulk_write=8.192s chunks=1702

Done (async).
  Durable time: 127.48s
  Total chunks upserted: 1702
  Files processed: 2, errors: 0
  MongoDB: db_hunt.collection_taixingbi_dev




h@hs-mac-mini rag-ingest-k8s-v1 % kubectl logs -f -l job-name=rag-ingest --max-log-requests=10

Embed: ollama (nomic-embed-text)
Found 1 files; 1 to process, 0 skipped (unchanged)
file 1/1: INGEST shard=wiki_shard_001.json chunks=872 total=70.138s thr=12.4c/s lat=80.4ms | embed=64.681s(92.2%) write=4.130s(5.9%) chunk=1.178s db_del=0.068s parse=0.031s
  total summary: load_parse=0.031s chunk=1.178s embed=64.681s mongo_bulk_write=4.130s chunks=872

Done (async).
  Durable time: 80.84s
  Total chunks upserted: 872
  Files processed: 1, errors: 0


Embed: ollama (nomic-embed-text)
Found 1 files; 1 to process, 0 skipped (unchanged)
file 1/1: INGEST shard=wiki_shard_002.json chunks=830 total=67.722s thr=12.3c/s lat=81.6ms | embed=62.763s(92.7%) write=4.114s(6.1%) chunk=0.725s db_del=0.057s parse=0.023s
  total summary: load_parse=0.023s chunk=0.725s embed=62.763s mongo_bulk_write=4.114s chunks=830

Done (async).
  Durable time: 77.38s
  Total chunks upserted: 830
  Files processed: 1, errors: 0
  MongoDB: db_hunt.collection_taixingbi_dev
  MongoDB: db_hunt.collection_taixingbi_dev
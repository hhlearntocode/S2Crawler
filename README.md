# arXiv Project: Milestone 1, reference crawling (Semantic Scholar)

## Setup
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r src/requirements.txt
cp .env.example .env      # then put your Semantic Scholar key in S2_API_KEY
```

## Run
```bash
python src/main.py START_MONTH START_ID END_MONTH END_ID [--out data]
python src/main.py 2310 12345 2311 00500     # example
python src/build_tables.py                   # -> tables/references.jsonl
```
Output: `data/<YYMM-NNNNN>/references.json` per paper (all references, with title, authors,
submission date, arXiv ID if any, Semantic Scholar ID), `data/_logs/s2_stats.jsonl` (time/RAM/counts).
Re-running the same command resumes and skips finished papers.

Per-paper status (in `references.json` and `data/_state/progress.jsonl`, which also has `seconds`):
`ok` (has references), `ok_empty` (found, no references), `not_found` (S2 404),
`error` (retries exhausted; no file written, retried on the next run).
`s2_stats.jsonl` reports `success_rate_pct` (= found / attempted) and `avg_refs_per_paper` (over found papers).
`references.json` also stores the paper's own S2 `venue`.

## Rate limit
The key allows 1 request/s across all endpoints. The client is single-threaded, waits 1.2 s
after each response, uses the batch endpoint (100 papers per request), and backs off on 429
(honouring `Retry-After`). **Do not run two processes with the same key at once.**

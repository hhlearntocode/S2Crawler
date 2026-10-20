# arXiv Project: Milestone 1, reference crawling (Semantic Scholar)

## Setup
Tested with Python 3.14 (3.10+ should work).
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r src/requirements.txt
cp .env.example .env      # put your Semantic Scholar key in S2_API_KEY (optional)
```

## Run
```bash
python src/main.py START_MONTH START_ID END_MONTH END_ID [--out data]
python src/main.py 2310 12345 2311 00500     # example
python src/build_tables.py                   # -> tables/references.jsonl
```
Re-running the same command resumes and skips finished papers.

## Google Colab
```python
!git clone <repo-url> && cd <repo>
!pip install -r src/requirements.txt
%env S2_API_KEY=your_key        # or skip it: runs without a key, but very slow
!python src/main.py 2310 12345 2311 00500 --out /content/data
```

## Project layout
```
.
├── src/
│   ├── main.py            CLI, RAM/disk sampler, final stats
│   ├── id_range.py        (month, id) range -> base arXiv IDs
│   ├── models.py          Outcome (one Paper's result) and Status names
│   ├── s2_source.py       S2Source.fetch(ids): throttle, retry, batch split, pagination, clean
│   ├── ledger.py          Ledger: record / pending / summary / papers (owns the files below)
│   ├── s2_refs.py         crawl loop: S2Source -> Ledger, retry passes
│   ├── build_tables.py    keep references that have an arXiv ID
│   └── config.py          paths, key, rate-limit constants
├── data/                  --out
│   ├── 2310-12345/
│   │   └── references.json
│   ├── _state/
│   │   ├── progress.jsonl     one line per paper attempt (resume)
│   │   └── s2_last_call       global throttle clock
│   └── _logs/
│       └── s2_stats.jsonl     one line per run (report numbers)
└── tables/
    └── references.jsonl
```

## Architecture
Three modules, each hides one thing. Talk to them only through their small interface.
```
 main.py ── id_range ──► list of IDs
    │
    ▼
 s2_refs.py  (crawl loop: ask, record, retry errors)
    │ ask: "what is left?"           │ ask: "fetch these IDs"
    ▼                                ▼
 ┌────────────────────┐  Outcome  ┌─────────────────────────────┐
 │ Ledger             │◄──────────│ S2Source                    │
 │ ledger.py          │           │ s2_source.py                │
 │                    │           │                             │
 │ hides: files on    │           │ hides: Semantic Scholar     │
 │ disk, resume,      │           │ rules (rate limit, retry,   │
 │ report numbers     │           │ batching, clean-up)         │
 │                    │           │                             │
 │ record(outcome)    │           │ fetch(ids) -> Outcomes      │
 │ pending(ids)       │           └─────────────────────────────┘
 │ summary(ids)       │
 │ papers()           │◄── build_tables.py
 └────────────────────┘
```
- **Outcome** (`models.py`): one paper's result.
- **Resume** is free: the Ledger knows which papers are done, so a re-run only does the rest.
- **Retry**: papers in `error` get up to 3 extra passes (120 s cool-down), then wait for the next run.

## How S2Source handles one batch
```
100 IDs ─► POST /paper/batch
            ├─ 429 / 5xx ─► wait (Retry-After) and retry ─► still failing: "error"
            ├─ 400 ───────► split the batch in two and retry each half
            └─ 200 ───────► references cut short? ─► fetch the rest page by page
                            then drop empty entries and duplicates
```

## Per-paper status
```
S2 answer                      status
├── 404                        not_found
├── found, 0 references        ok_empty
├── found, >= 1 reference      ok
└── request failed             error   (retried, never written to disk)
```

## `references.json`
```
{
 ├── arxiv_id, s2_paper_id, status, venue
 ├── reference_count, fetched_at
 └── references: [
      ├── s2_id, title, authors[]
      ├── submission_date   "YYYY-MM-DD", else "YYYY" if S2 has only the year
      ├── year, venue
      ├── arxiv_id          null if the reference is not on arXiv
      └── external_ids
     ]
}
```

## `s2_stats.jsonl` (one line per run)
```
├── Report numbers (all IDs, latest state, correct across resumes)
│   ├── papers, ok, ok_empty, not_found, error, pending
│   ├── success_rate_pct, avg_refs_per_paper, pct_refs_with_arxiv
│   └── refs, refs_with_arxiv, paginated
├── Cost
│   ├── wall_seconds, discovery_seconds
│   ├── peak_ram_bytes, avg_ram_bytes
│   └── peak_disk_bytes, final_output_bytes, disk_free_bytes
├── Requests: s2_requests, s2_429
└── run: counters of this invocation only
```

## Design decisions
```
├── One S2 call per base ID, no vN   S2 returns the same references for every version,
│                                    so they are stored once per paper
├── Keep ALL references              arXiv-only filtering happens in build_tables.py
├── Clean-up                         drop empty entries, de-dup by S2 id (else arXiv id)
└── ID validation                    YYMM; 4-digit ids up to 1412, 5-digit from 1501
```

## Rate limit
```
API key present ─► 1 call / 1.2 s   batch endpoint (100 papers), 429 -> backoff + Retry-After
No API key      ─► 1 call / 5 s     shared pool, expect many 429
```
The client is single-threaded. **Do not run two processes with the same key at once.**

"""Crawl references of arXiv papers from Semantic Scholar and store them per paper."""
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import config
from s2_client import S2Client, S2RetryError

log = logging.getLogger("s2")


def folder_name(arxiv_id: str) -> str:
    return arxiv_id.replace(".", "-").replace("/", "-")


def normalize_ref(ref: dict) -> dict:
    ext = ref.get("externalIds") or {}
    date = ref.get("publicationDate") or (str(ref["year"]) if ref.get("year") else None)
    return {
        "s2_id": ref.get("paperId"),
        "title": ref.get("title"),
        "authors": [a.get("name") for a in (ref.get("authors") or []) if a.get("name")],
        "submission_date": date,
        "year": ref.get("year"),
        "venue": ref.get("venue") or None,
        "arxiv_id": ext.get("ArXiv"),   # old-style ids (hep-th/9901001) kept as-is
        "external_ids": ext,
    }


def _write_atomic(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1))
    os.replace(tmp, path)


DONE_STATUSES = ("ok", "ok_empty", "not_found")   # "error" is retried on the next run
STATUSES = ("ok", "ok_empty", "not_found", "error")


def load_done(progress_file: Path) -> set:
    done = set()
    if progress_file.exists():
        for line in progress_file.read_text().splitlines():
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get("status") in DONE_STATUSES:
                done.add(rec["arxiv_id"])
    return done


def _fetch_refs(client, aid, data):
    """Return (raw references, paginated?) for one batch result; may raise S2RetryError."""
    raw = list(data.get("references") or [])
    if len(raw) < (data.get("referenceCount") or 0):   # truncated -> paginated endpoint
        return client.references_paged(aid) or raw, True
    return raw, False


def crawl_references(ids, out_dir: Path, client: S2Client, on_progress=None) -> dict:
    """Fetch references for every id (resumable). Returns counters for the report.

    Status per paper: ok (has refs), ok_empty (found, no refs), not_found (S2 404),
    error (retries exhausted; retried on the next run).
    """
    progress_file = out_dir / "_state" / "progress.jsonl"
    progress_file.parent.mkdir(parents=True, exist_ok=True)
    todo = [i for i in ids if i not in load_done(progress_file)]
    stats = {"requested": len(ids), "skipped": len(ids) - len(todo), "ok": 0, "ok_empty": 0,
             "not_found": 0, "error": 0, "refs": 0, "refs_with_arxiv": 0, "paginated": 0}

    for start in range(0, len(todo), config.S2_BATCH_SIZE):
        chunk = todo[start:start + config.S2_BATCH_SIZE]
        t0 = time.time()
        try:
            results = client.batch(chunk)
        except S2RetryError as e:
            log.error("batch failed: %s", e)
            results = [None] * len(chunk)
            failed = True
        else:
            failed = False
        t_batch = (time.time() - t0) / len(chunk)    # batch time shared evenly per paper

        for aid, data in zip(chunk, results):
            t1 = time.time()
            refs, s2_id, venue, paginated = [], None, None, False
            if failed:
                status = "error"
            elif data is None:
                status = "not_found"
            else:
                try:
                    raw, paginated = _fetch_refs(client, aid, data)
                    refs = [normalize_ref(r) for r in raw]
                    status = "ok" if refs else "ok_empty"
                    s2_id, venue = data.get("paperId"), data.get("venue") or None
                except S2RetryError as e:
                    log.error("%s: %s", aid, e)
                    status, paginated = "error", False
            if status != "error":
                doc = {
                    "arxiv_id": aid, "s2_paper_id": s2_id, "status": status, "venue": venue,
                    "reference_count": len(refs),
                    "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "references": refs,
                }
                _write_atomic(out_dir / folder_name(aid) / "references.json", doc)
            with progress_file.open("a") as f:
                f.write(json.dumps({"arxiv_id": aid, "status": status, "n_refs": len(refs),
                                    "seconds": round(t_batch + time.time() - t1, 3)}) + "\n")
            stats[status] += 1
            stats["paginated"] += paginated
            stats["refs"] += len(refs)
            stats["refs_with_arxiv"] += sum(1 for r in refs if r["arxiv_id"])
            if on_progress:
                on_progress(1)
    return stats

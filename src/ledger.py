"""Ledger: every Paper's latest Status and References, stored under the output directory.

Layout:  <out>/_state/progress.jsonl         one line per attempt (append-only, latest wins)
         <out>/<YYMM-NNNNN>/references.json  one file per Paper that was found
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from models import DONE_STATUSES, Outcome


def folder_name(arxiv_id: str) -> str:
    return arxiv_id.replace(".", "-").replace("/", "-")


class Ledger:
    def __init__(self, out_dir):
        self.out = Path(out_dir)
        self.progress_file = self.out / "_state" / "progress.jsonl"

    def record(self, o: Outcome) -> None:
        """Persist an Outcome. Papers in error get a progress line but no references file."""
        if o.status != "error":
            doc = {
                "arxiv_id": o.arxiv_id, "s2_paper_id": o.s2_paper_id, "status": o.status,
                "venue": o.venue, "reference_count": len(o.references),
                "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "references": o.references,
            }
            self._write_atomic(self.out / folder_name(o.arxiv_id) / "references.json", doc)
        self.progress_file.parent.mkdir(parents=True, exist_ok=True)
        with self.progress_file.open("a") as f:
            f.write(json.dumps({"arxiv_id": o.arxiv_id, "status": o.status,
                                "n_refs": len(o.references), "paginated": o.paginated,
                                "seconds": round(o.seconds, 3)}) + "\n")

    def pending(self, ids) -> list:
        """The ids that still need crawling (no finished Status yet), in the given order."""
        latest = self._latest()
        return [i for i in ids if latest.get(i, {}).get("status") not in DONE_STATUSES]

    def papers(self):
        """Yield the stored document of every found Paper, sorted by folder."""
        for path in sorted(self.out.glob("*/references.json")):
            yield json.loads(path.read_text())

    def summary(self, ids) -> dict:
        """Report numbers over ALL ids from their latest Status (correct across resumes)."""
        latest = self._latest()
        s = {"papers": len(ids), "ok": 0, "ok_empty": 0, "not_found": 0, "error": 0,
             "pending": 0, "refs": 0, "refs_with_arxiv": 0, "paginated": 0}
        for aid in ids:
            rec = latest.get(aid)
            if rec is None:
                s["pending"] += 1
                continue
            s[rec["status"]] += 1
            s["paginated"] += bool(rec.get("paginated"))
            if rec["status"] in ("ok", "ok_empty"):
                path = self.out / folder_name(aid) / "references.json"
                refs = json.loads(path.read_text())["references"]
                s["refs"] += len(refs)
                s["refs_with_arxiv"] += sum(1 for r in refs if r["arxiv_id"])
        found = s["ok"] + s["ok_empty"]
        tried = found + s["not_found"] + s["error"]
        s["success_rate_pct"] = round(100 * found / max(tried, 1), 2)
        s["avg_refs_per_paper"] = round(s["refs"] / max(found, 1), 2)
        s["pct_refs_with_arxiv"] = round(100 * s["refs_with_arxiv"] / max(s["refs"], 1), 2)
        return s

    def _latest(self) -> dict:
        latest = {}
        if self.progress_file.exists():
            for line in self.progress_file.read_text().splitlines():
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                latest[rec["arxiv_id"]] = rec
        return latest

    @staticmethod
    def _write_atomic(path: Path, obj):
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1))
        os.replace(tmp, path)

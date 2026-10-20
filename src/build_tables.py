"""Build tables/references.jsonl."""
import argparse
import json
from pathlib import Path

import config
from ledger import Ledger


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(config.ROOT / "data"))
    ap.add_argument("--out", default=str(config.ROOT / "tables"))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    n = 0
    with (out / "references.jsonl").open("w") as f:
        for doc in Ledger(args.data).papers():
            for r in doc["references"]:
                if not r["arxiv_id"]:
                    continue
                f.write(json.dumps({
                    "arxiv_id": doc["arxiv_id"],
                    "ref_arxiv_id": r["arxiv_id"],
                    "ref_title": r["title"],
                    "ref_authors": r["authors"],
                    "ref_submission_date": r["submission_date"],
                    "ref_s2_id": r["s2_id"],
                }, ensure_ascii=False) + "\n")
                n += 1
    print(f"{n} rows -> {out / 'references.jsonl'}")


if __name__ == "__main__":
    main()

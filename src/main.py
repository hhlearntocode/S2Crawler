"""CLI: python src/main.py START_MONTH START_ID END_MONTH END_ID [--out data]

Example: python src/main.py 2310 12345 2311 00500
"""
import argparse
import json
import logging
import threading
import time
from pathlib import Path

import psutil
from tqdm import tqdm

import config
from id_range import expand_range
from s2_client import S2Client
from s2_refs import crawl_references


class RamSampler(threading.Thread):
    def __init__(self, interval=1.0):
        super().__init__(daemon=True)
        self.proc, self.interval, self.samples, self._halt = psutil.Process(), interval, [], threading.Event()

    def run(self):
        while not self._halt.is_set():
            self.samples.append(self.proc.memory_info().rss)
            self._halt.wait(self.interval)

    def stop(self):
        self._halt.set()
        self.join()
        return (max(self.samples, default=0), sum(self.samples) / max(len(self.samples), 1))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("start_month")
    ap.add_argument("start_id")
    ap.add_argument("end_month")
    ap.add_argument("end_id")
    ap.add_argument("--out", default=str(config.ROOT / "data"))
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

    out = Path(args.out)
    sampler = RamSampler()
    sampler.start()
    t0 = time.time()

    ids = expand_range(args.start_month, args.start_id, args.end_month, args.end_id)
    t_discovery = time.time() - t0
    print(f"{len(ids)} papers: {ids[0]} .. {ids[-1]}")

    client = S2Client(out / "_state" / "s2_last_call")
    with tqdm(total=len(ids), unit="paper") as bar:
        stats = crawl_references(ids, out, client, on_progress=bar.update)

    peak, avg = sampler.stop()
    found = stats["ok"] + stats["ok_empty"]
    attempted = found + stats["not_found"] + stats["error"]
    stats.update({
        "success_rate_pct": round(100 * found / max(attempted, 1), 2),
        "start": [args.start_month, args.start_id], "end": [args.end_month, args.end_id],
        "s2_requests": client.n_requests, "s2_429": client.n_429,
        "discovery_seconds": round(t_discovery, 2),
        "wall_seconds": round(time.time() - t0, 2),
        "peak_ram_bytes": peak, "avg_ram_bytes": int(avg),
        "avg_refs_per_paper": round(stats["refs"] / max(found, 1), 2),
        "pct_refs_with_arxiv": round(100 * stats["refs_with_arxiv"] / max(stats["refs"], 1), 2),
    })
    log_dir = out / "_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    with (log_dir / "s2_stats.jsonl").open("a") as f:
        f.write(json.dumps(stats) + "\n")
    print(json.dumps(stats, indent=1))


if __name__ == "__main__":
    main()

"""CLI: python src/main.py START_MONTH START_ID END_MONTH END_ID [--out data]

Example: python src/main.py 2310 12345 2311 00500
"""
import argparse
import json
import logging
import os
import shutil
import threading
import time
from pathlib import Path

import psutil
from tqdm import tqdm

import config
from id_range import expand_range
from ledger import Ledger
from s2_refs import crawl_references
from s2_source import S2Source


def dir_size(path: Path) -> int:
    total = 0
    for root, _, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
    return total


class ResourceSampler(threading.Thread):
    """Samples process RSS every second and the output folder size every 5 s."""

    def __init__(self, out: Path, interval=1.0):
        super().__init__(daemon=True)
        self.out, self.interval = out, interval
        self.proc, self.ram, self.disk, self._halt = psutil.Process(), [], [], threading.Event()

    def run(self):
        tick = 0
        while not self._halt.is_set():
            self.ram.append(self.proc.memory_info().rss)
            if tick % 5 == 0:
                self.disk.append(dir_size(self.out))
            tick += 1
            self._halt.wait(self.interval)

    def stop(self):
        self._halt.set()
        self.join()
        return {"peak_ram_bytes": max(self.ram, default=0),
                "avg_ram_bytes": int(sum(self.ram) / max(len(self.ram), 1)),
                "peak_disk_bytes": max(self.disk, default=0)}


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
    out.mkdir(parents=True, exist_ok=True)
    sampler = ResourceSampler(out)
    sampler.start()
    t0 = time.time()

    ids = expand_range(args.start_month, args.start_id, args.end_month, args.end_id)
    t_discovery = time.time() - t0
    print(f"{len(ids)} papers: {ids[0]} .. {ids[-1]}")

    ledger, source = Ledger(out), S2Source(out / "_state" / "s2_last_call")
    with tqdm(total=len(ids), unit="paper") as bar:
        run_stats = crawl_references(ids, ledger, source, on_progress=bar.update)

    res = sampler.stop()
    stats = {
        "run": run_stats,                      # this invocation only
        **ledger.summary(ids),                 # all ids, latest state (use these in the report)
        "start": [args.start_month, args.start_id], "end": [args.end_month, args.end_id],
        "s2_requests": source.n_requests, "s2_429": source.n_429,
        "discovery_seconds": round(t_discovery, 2),
        "wall_seconds": round(time.time() - t0, 2),
        **res,
        "final_output_bytes": sum(dir_size(d) for d in out.iterdir() if d.is_dir() and not d.name.startswith("_")),
        "disk_free_bytes": shutil.disk_usage(out).free,
    }
    log_dir = out / "_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    with (log_dir / "s2_stats.jsonl").open("a") as f:
        f.write(json.dumps(stats) + "\n")
    print(json.dumps(stats, indent=1))


if __name__ == "__main__":
    main()

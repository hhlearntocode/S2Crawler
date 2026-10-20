"""Crawl loop: ask S2Source for References, record every Outcome in the Ledger."""
import logging
import time

import config
from ledger import Ledger
from s2_source import S2Source

log = logging.getLogger("s2")


def crawl_references(ids, ledger: Ledger, source: S2Source, on_progress=None) -> dict:
    """Fetch references for every id. Returns this run's counters.

    Papers in error are retried in up to RETRY_PASSES extra passes after a cool-down; any
    still failing are retried on the next run. Final numbers come from Ledger.summary().
    """
    stats = {"requested": len(ids), "skipped": 0, "ok": 0, "ok_empty": 0, "not_found": 0, "error": 0}
    for n_pass in range(1 + config.RETRY_PASSES):
        if n_pass:
            log.warning("pass %d: retrying %d errored papers after %ds cool-down",
                        n_pass + 1, stats["error"], config.RETRY_COOLDOWN)
            time.sleep(config.RETRY_COOLDOWN)
        final = n_pass == config.RETRY_PASSES
        todo = ledger.pending(ids)
        if n_pass == 0:
            stats["skipped"] = len(ids) - len(todo)
        counts = {"ok": 0, "ok_empty": 0, "not_found": 0, "error": 0}
        for outcome in source.fetch(todo):
            ledger.record(outcome)
            counts[outcome.status] += 1
            if on_progress and (outcome.status != "error" or final):
                on_progress(1)       # errored papers only count once no more passes remain
        stats["error"] = counts["error"]
        for k in ("ok", "ok_empty", "not_found"):
            stats[k] += counts[k]
        if not counts["error"]:
            break
    return stats

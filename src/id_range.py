"""Expand (start_month, start_id) .. (end_month, end_id) into arXiv IDs."""
import time
import xml.etree.ElementTree as ET

import requests

import config

ATOM = "{http://www.w3.org/2005/Atom}"
_last_arxiv_call = 0.0


def id_width(yymm: str) -> int:
    return 4 if int(yymm) <= 1412 else 5


def next_month(yymm: str) -> str:
    y, m = int(yymm[:2]), int(yymm[2:])
    y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return f"{y:02d}{m:02d}"


def _exists(yymm: str, n: int) -> bool:
    """True if paper YYMM.n exists (arXiv API, throttled to >= 3s/call)."""
    global _last_arxiv_call
    wait = _last_arxiv_call + config.ARXIV_MIN_INTERVAL - time.time()
    if wait > 0:
        time.sleep(wait)
    aid = f"{yymm}.{n:0{id_width(yymm)}d}"
    resp = None
    for attempt in range(6):
        try:
            resp = requests.get(config.ARXIV_API, params={"id_list": aid, "max_results": 1},
                                headers={"User-Agent": config.USER_AGENT}, timeout=30)
        except (requests.Timeout, requests.ConnectionError):
            resp = None
        _last_arxiv_call = time.time()
        if resp is not None and resp.status_code == 200:
            break
        try:
            pause = float(resp.headers.get("Retry-After")) if resp is not None else None
        except (TypeError, ValueError):
            pause = None
        time.sleep(pause if pause else min(15 * 2 ** attempt, 300))
    else:
        raise RuntimeError(f"arXiv API unavailable while checking {aid}")
    root = ET.fromstring(resp.content)
    return any("/abs/" in (e.findtext(f"{ATOM}id") or "") for e in root.findall(f"{ATOM}entry"))


def last_id_of_month(yymm: str) -> int:
    """Binary search the largest existing ID of a month (IDs are contiguous)."""
    lo, hi = 1, 10 ** id_width(yymm) - 1
    if not _exists(yymm, lo):
        return 0
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if _exists(yymm, mid):
            lo = mid
        else:
            hi = mid - 1
    return lo


def expand_range(start_month, start_id, end_month, end_id):
    start_id, end_id = int(start_id), int(end_id)
    if start_month == end_month:
        return [f"{start_month}.{n:0{id_width(start_month)}d}" for n in range(start_id, end_id + 1)]
    ids, month = [], start_month
    while month <= end_month:
        lo = start_id if month == start_month else 1
        hi = end_id if month == end_month else last_id_of_month(month)
        ids += [f"{month}.{n:0{id_width(month)}d}" for n in range(lo, hi + 1)]
        month = next_month(month)
    return ids

"""Semantic Scholar client with a single global throttle and 429-safe retries."""
import logging
import random
import time
from pathlib import Path

import requests

import config

log = logging.getLogger("s2")


class S2RetryError(RuntimeError):
    """Raised when a request still fails (429/5xx/timeout) after all retries."""


class S2Client:
    def __init__(self, state_file: Path):
        if not config.S2_API_KEY:
            raise RuntimeError("S2_API_KEY missing: put it in .env")
        self.session = requests.Session()
        self.session.headers.update({
            "x-api-key": config.S2_API_KEY,
            "User-Agent": config.USER_AGENT,
        })
        self.state_file = state_file
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.last_call = self._load_last_call()   # wall-clock time of last response
        self.penalty_left = 0
        self.n_requests = 0
        self.n_429 = 0

    def _load_last_call(self) -> float:
        try:
            return float(self.state_file.read_text())
        except (OSError, ValueError):
            return 0.0

    def _wait(self):
        interval = config.S2_PENALTY_INTERVAL if self.penalty_left > 0 else config.S2_MIN_INTERVAL
        delay = self.last_call + interval - time.time()
        if delay > 0:
            time.sleep(delay)

    def _mark_done(self):
        self.last_call = time.time()
        try:
            self.state_file.write_text(str(self.last_call))
        except OSError:
            pass
        if self.penalty_left > 0:
            self.penalty_left -= 1

    def request(self, method: str, path: str, **kwargs):
        """Throttled request. Returns parsed JSON, or None on 404."""
        url = f"{config.S2_BASE}{path}"
        for attempt in range(config.S2_MAX_RETRIES):
            self._wait()
            self.n_requests += 1
            try:
                resp = self.session.request(method, url, timeout=60, **kwargs)
            except (requests.Timeout, requests.ConnectionError) as e:
                self._mark_done()
                self._sleep_backoff(attempt, None, repr(e))
                continue
            self._mark_done()
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 404:
                return None
            if resp.status_code == 429:
                self.n_429 += 1
                self.penalty_left = config.S2_PENALTY_CALLS
            if resp.status_code == 429 or resp.status_code >= 500:
                self._sleep_backoff(attempt, resp.headers.get("Retry-After"), str(resp.status_code))
                continue
            raise RuntimeError(f"S2 {resp.status_code} on {path}: {resp.text[:300]}")
        raise S2RetryError(f"S2 request failed after {config.S2_MAX_RETRIES} attempts: {path}")

    @staticmethod
    def _sleep_backoff(attempt, retry_after, why):
        try:
            wait = float(retry_after)
        except (TypeError, ValueError):
            wait = min(2 ** (attempt + 1), config.S2_BACKOFF_CAP)
        wait += random.uniform(0, 1)
        log.warning("S2 retry (%s), sleeping %.1fs", why, wait)
        time.sleep(wait)

    def batch(self, arxiv_ids):
        """POST /paper/batch -> list aligned with arxiv_ids (None where unknown)."""
        return self.request(
            "POST", "/paper/batch",
            params={"fields": config.REF_FIELDS},
            json={"ids": [f"arXiv:{i}" for i in arxiv_ids]},
        )

    def references_paged(self, arxiv_id):
        """Fetch all references of one paper via the paginated endpoint."""
        out, offset = [], 0
        while True:
            data = self.request(
                "GET", f"/paper/arXiv:{arxiv_id}/references",
                params={"fields": config.REF_PAGE_FIELDS, "limit": 1000, "offset": offset},
            )
            if not data:
                break
            out.extend(item.get("citedPaper") or {} for item in data.get("data", []))
            if data.get("next") is None:
                break
            offset = data["next"]
        return out

"""Shared configuration: paths, API key and rate-limit constants."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

S2_API_KEY = os.getenv("S2_API_KEY", "")
S2_BASE = "https://api.semanticscholar.org/graph/v1"

# The key allows 1 request/s across ALL endpoints; stay safely below it.
S2_MIN_INTERVAL = 1.2        # seconds between end of one call and start of the next
S2_NOKEY_INTERVAL = 5.0      # no API key: shared pool, be much gentler
S2_PENALTY_INTERVAL = 1.5    # used for S2_PENALTY_CALLS calls after a 429
S2_PENALTY_CALLS = 50
S2_MAX_RETRIES = 6
S2_BACKOFF_CAP = 60
RETRY_PASSES = 3             # extra passes over papers that ended in "error"
RETRY_COOLDOWN = 120         # seconds to wait before each extra pass
S2_BATCH_SIZE = 100          # API allows 500; smaller keeps responses light

ARXIV_API = "https://export.arxiv.org/api/query"
ARXIV_MIN_INTERVAL = 3.0     # arXiv etiquette: >= 3s between calls
USER_AGENT = "S2Crawler/1.0 (student crawler; mailto:hoangnguyen.123.dz@gmail.com)"

REF_FIELDS = ",".join([
    "paperId", "externalIds", "venue", "referenceCount",
    "references.paperId", "references.title", "references.authors",
    "references.year", "references.publicationDate", "references.venue",
    "references.externalIds",
])
REF_PAGE_FIELDS = "paperId,title,authors,year,publicationDate,venue,externalIds"

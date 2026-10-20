"""Shared data types."""
from dataclasses import dataclass, field

DONE_STATUSES = ("ok", "ok_empty", "not_found")   # "error" is retried
STATUSES = DONE_STATUSES + ("error",)


@dataclass
class Outcome:
    """Result of crawling one Paper"""
    arxiv_id: str
    status: str                      
    s2_paper_id: str | None = None
    venue: str | None = None
    references: list = field(default_factory=list)
    paginated: bool = False           # references came from the paginated endpoint
    seconds: float = 0.0

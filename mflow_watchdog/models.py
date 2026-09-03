from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class CheckStatus(str, Enum):
    CLEAR = "CLEAR"
    UNPAID = "UNPAID"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    CHECK_FAILED = "CHECK_FAILED"


@dataclass(frozen=True)
class OutstandingItem:
    transaction_date: datetime | None
    amount: float | None
    source_url: str
    raw_excerpt: str = ""


@dataclass(frozen=True)
class CheckResult:
    status: CheckStatus
    items: list[OutstandingItem] = field(default_factory=list)
    detail: str = ""
    source_url: str = ""

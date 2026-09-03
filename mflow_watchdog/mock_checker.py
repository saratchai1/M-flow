from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

from .config import Vehicle
from .models import CheckResult, CheckStatus, OutstandingItem


class MockMFlowChecker:
    """Deterministic checker for demos/tests. It never contacts M-Flow."""

    def __init__(self, mode: str = "success"):
        mode = mode.strip().lower()
        if mode not in {"success", "mixed"}:
            raise ValueError("MFLOW_MOCK_MODE must be 'success' or 'mixed'")
        self.mode = mode

    @staticmethod
    def _bucket(vehicle: Vehicle) -> int:
        key = f"{vehicle.plate_number}|{vehicle.province}".encode("utf-8")
        return int(hashlib.sha256(key).hexdigest()[:8], 16)

    def check(self, vehicle: Vehicle) -> CheckResult:
        bucket = self._bucket(vehicle)
        source_url = f"mock://mflow/{vehicle.plate_number}"

        if self.mode == "mixed":
            status = (
                CheckStatus.CLEAR,
                CheckStatus.UNPAID,
                CheckStatus.REVIEW_REQUIRED,
                CheckStatus.CHECK_FAILED,
            )[bucket % 4]
            if status == CheckStatus.REVIEW_REQUIRED:
                return CheckResult(
                    status,
                    detail="Mock page changed: manual review required.",
                    source_url=source_url,
                )
            if status == CheckStatus.CHECK_FAILED:
                return CheckResult(
                    status,
                    detail="Mock human verification/CAPTCHA.",
                    source_url=source_url,
                )
        else:
            status = CheckStatus.UNPAID if bucket % 3 == 0 else CheckStatus.CLEAR

        if status == CheckStatus.CLEAR:
            return CheckResult(
                CheckStatus.CLEAR,
                detail="Mock: no outstanding item found.",
                source_url=source_url,
            )

        transaction_date = datetime.now(timezone.utc) - timedelta(hours=6 + bucket % 18)
        return CheckResult(
            CheckStatus.UNPAID,
            items=[
                OutstandingItem(
                    transaction_date=transaction_date,
                    amount=30.0,
                    source_url=source_url,
                    raw_excerpt="Mock outstanding M-Flow transaction",
                )
            ],
            detail="Mock: outstanding transaction found.",
            source_url=source_url,
        )

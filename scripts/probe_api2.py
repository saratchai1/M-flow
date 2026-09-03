from __future__ import annotations

import json

from mflow_watchdog.api_checker import MFlowApiChecker
from mflow_watchdog.config import Settings, Vehicle
from mflow_watchdog.models import CheckStatus


def main() -> int:
    settings = Settings.from_env()
    checker = MFlowApiChecker(settings)
    vehicle = Vehicle("9กก 9999", "กรุงเทพมหานคร", "safe integration probe")
    result = checker.check(vehicle)

    print("ENGINE", "MFLOW_API2")
    print("STATUS", result.status.value)
    print("DETAIL", result.detail)
    print("SOURCE", result.source_url)
    print(
        "ITEMS",
        json.dumps(
            [
                {
                    "transaction_date": item.transaction_date.isoformat()
                    if item.transaction_date
                    else None,
                    "amount": item.amount,
                    "due_date": item.due_date.isoformat() if item.due_date else None,
                }
                for item in result.items
            ],
            ensure_ascii=False,
        ),
    )

    # This test plate was verified to return an empty list on the current
    # nonmember endpoint. A parser/API failure must never be accepted as clear.
    if result.status != CheckStatus.CLEAR:
        return 2
    if result.items:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

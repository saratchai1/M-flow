from datetime import datetime, timezone

from mflow_watchdog.config import Vehicle
from mflow_watchdog.db import Store
from mflow_watchdog.models import OutstandingItem


def test_transaction_upsert_and_clear(tmp_path):
    store = Store(tmp_path / "test.db")
    vehicle = Vehicle("กก1234", "กรุงเทพมหานคร")
    now = datetime(2026, 9, 3, tzinfo=timezone.utc)
    item = OutstandingItem(now, 30.0, "https://example.test", "ค้างชำระ 30 บาท")
    row = store.upsert_transaction(vehicle, item, now, now)
    assert row["status"] == "UNPAID"
    assert store.mark_vehicle_clear(vehicle, now) == 1
    assert store.list_transactions()[0]["status"] == "PAID"
    store.close()

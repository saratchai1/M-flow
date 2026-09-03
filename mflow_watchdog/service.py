from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .checker import MFlowBrowserChecker
from .config import Settings, Vehicle
from .db import Store
from .models import CheckStatus, OutstandingItem
from .notifier import MultiNotifier

UTC = timezone.utc
BANGKOK = ZoneInfo("Asia/Bangkok")


def _as_aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=UTC)
    return dt.astimezone(UTC)


def _internal_deadline(item: OutstandingItem, now: datetime, hours: int) -> datetime:
    return (_as_aware(item.transaction_date) or now) + timedelta(hours=hours)


def _fmt_amount(amount: float | None) -> str:
    return "ไม่ทราบยอด" if amount is None else f"{amount:,.2f} บาท"


def _fmt_date(dt: datetime | None) -> str:
    return "ไม่ทราบวันที่" if dt is None else dt.strftime("%d/%m/%Y")


def _tx_notification(vehicle: Vehicle, row, now: datetime, urgent_before_hours: int, renotify_hours: int):
    last_notified = datetime.fromisoformat(row["last_notified_at"]) if row["last_notified_at"] else None
    deadline = datetime.fromisoformat(row["deadline"]) if row["deadline"] else None
    hours_left = (deadline - now).total_seconds() / 3600 if deadline else 999999
    if hours_left <= 0:
        level, headline = "OVERDUE_INTERNAL", "🔴 M-Flow: เกิน safety deadline ภายในแล้ว"
        should_send = not last_notified or (now - last_notified).total_seconds() >= renotify_hours * 3600
    elif hours_left <= urgent_before_hours:
        level, headline = "URGENT", "🔴 M-Flow: ต้องตรวจและชำระด่วน"
        should_send = row["notification_level"] != "URGENT" or not last_notified
    elif not last_notified:
        level, headline, should_send = "NEW", "🚗 M-Flow: พบรายการที่ต้องตรวจสอบ/ชำระ", True
    else:
        level, headline = "REMINDER", "⚠️ M-Flow: รายการยังค้างอยู่"
        should_send = (now - last_notified).total_seconds() >= renotify_hours * 3600
    if not should_send:
        return None, None
    tx_date = datetime.fromisoformat(row["transaction_date"]) if row["transaction_date"] else None
    text = (
        f"{headline}\nทะเบียน: {vehicle.plate_number} {vehicle.province}\n"
        f"วันที่รายการ: {_fmt_date(tx_date)}\nยอด: {_fmt_amount(row['amount'])}\n"
        f"Safety deadline ภายใน: {deadline.astimezone(BANGKOK).strftime('%d/%m/%Y %H:%M น.') if deadline else '-'}\n"
        "หมายเหตุ: safety deadline เป็นเกณฑ์ภายใน ไม่ใช่การยืนยันกำหนดชำระตามเงื่อนไข M-Flow\n"
        f"ตรวจสอบ/ชำระ: {row['source_url']}"
    )
    return level, text


class WatchdogService:
    def __init__(self, settings: Settings, store: Store, checker: MFlowBrowserChecker, notifier: MultiNotifier):
        self.settings, self.store, self.checker, self.notifier = settings, store, checker, notifier

    def check_vehicle(self, vehicle: Vehicle, now: datetime | None = None) -> CheckStatus:
        now = now or datetime.now(tz=UTC)
        result = self.checker.check(vehicle)
        self.store.record_check(vehicle, result, now)
        if result.status == CheckStatus.CLEAR:
            self.store.mark_vehicle_clear(vehicle, now)
            return result.status
        if result.status in {CheckStatus.CHECK_FAILED, CheckStatus.REVIEW_REQUIRED}:
            key = f"checker:{vehicle.plate_number}:{vehicle.province}:{result.status.value}"
            if self.store.can_send_alert(key, now, self.settings.failure_renotify_hours):
                msg = (
                    f"⚠️ M-Flow Watchdog: {result.status.value}\nทะเบียน: {vehicle.plate_number} {vehicle.province}\n"
                    f"รายละเอียด: {result.detail}\nระบบจะไม่ตีความว่า 'ไม่มียอด' เมื่อเช็กไม่สำเร็จ\n"
                    f"ตรวจด้วยตนเอง: {result.source_url or self.settings.mflow_url}"
                )
                errors = self.notifier.send(msg)
                if not errors:
                    self.store.mark_alert_sent(key, now)
            return result.status
        for item in result.items:
            deadline = _internal_deadline(item, now, self.settings.safety_deadline_hours)
            row = self.store.upsert_transaction(vehicle, item, now, deadline)
            level, message = _tx_notification(vehicle, row, now, self.settings.urgent_before_hours, self.settings.renotify_after_hours)
            if message:
                errors = self.notifier.send(message)
                if not errors:
                    self.store.set_notified(row["id"], now, level)
        return result.status

    def run(self) -> dict[str, int]:
        counts = {status.value: 0 for status in CheckStatus}
        for vehicle in self.settings.load_vehicles():
            status = self.check_vehicle(vehicle)
            counts[status.value] += 1
        return counts

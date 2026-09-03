from __future__ import annotations

import json
import logging
import mimetypes
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .checker import MFlowBrowserChecker
from .config import Settings
from .db import Store
from .mock_checker import MockMFlowChecker
from .notifier import MultiNotifier, Notifier, build_notifier
from .service import WatchdogService

log = logging.getLogger(__name__)
UTC = timezone.utc
WEB_DIR = Path(__file__).with_name("web")


@dataclass
class DashboardRunState:
    running: bool = False
    last_started: str | None = None
    last_finished: str | None = None
    last_counts: dict[str, int] | None = None
    last_error: str | None = None
    demo_notifications: list[str] = field(default_factory=list)
    lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    def snapshot(self) -> dict:
        with self.lock:
            return {
                "running": self.running,
                "last_started": self.last_started,
                "last_finished": self.last_finished,
                "last_counts": self.last_counts,
                "last_error": self.last_error,
            }

    def add_demo_notification(self, message: str) -> None:
        with self.lock:
            self.demo_notifications = (self.demo_notifications + [message])[-20:]


class DashboardDemoNotifier(Notifier):
    name = "dashboard-demo"

    def __init__(self, state: DashboardRunState):
        self.state = state

    def send(self, message: str) -> None:
        self.state.add_demo_notification(message)


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    except ValueError:
        return None


def _mode() -> str:
    return "DEMO" if os.getenv("MFLOW_MOCK_MODE", "").strip() else "LIVE"


def _build_runtime(settings: Settings, state: DashboardRunState):
    mock_mode = os.getenv("MFLOW_MOCK_MODE", "").strip().lower()
    if mock_mode:
        return MockMFlowChecker(mock_mode), MultiNotifier([DashboardDemoNotifier(state)])
    return MFlowBrowserChecker(settings), build_notifier(settings)


def _run_check(settings: Settings, state: DashboardRunState) -> None:
    now = datetime.now(tz=UTC).isoformat()
    with state.lock:
        state.running = True
        state.last_started = now
        state.last_error = None
        if _mode() == "DEMO":
            state.demo_notifications = []

    store = Store(settings.database_path)
    try:
        checker, notifier = _build_runtime(settings, state)
        counts = WatchdogService(settings, store, checker, notifier).run()
        with state.lock:
            state.last_counts = counts
    except Exception as exc:  # web boundary: preserve error for admin UI
        log.exception("Dashboard check failed")
        with state.lock:
            state.last_error = f"{type(exc).__name__}: {exc}"
    finally:
        store.close()
        with state.lock:
            state.running = False
            state.last_finished = datetime.now(tz=UTC).isoformat()


def start_check(settings: Settings, state: DashboardRunState) -> bool:
    with state.lock:
        if state.running:
            return False
        state.running = True
    thread = threading.Thread(target=_run_check, args=(settings, state), daemon=True, name="mflow-dashboard-check")
    thread.start()
    return True


def build_summary(settings: Settings, state: DashboardRunState) -> dict:
    configuration_error = None
    try:
        vehicles = settings.load_vehicles()
    except Exception as exc:
        vehicles = []
        configuration_error = f"{type(exc).__name__}: {exc}"

    store = Store(settings.database_path)
    try:
        transactions = [dict(row) for row in store.list_transactions(limit=1000)]
        checks = [dict(row) for row in store.latest_checks()]
    finally:
        store.close()

    tx_by_vehicle: dict[tuple[str, str], list[dict]] = {}
    for tx in transactions:
        if tx["status"] == "UNPAID":
            tx_by_vehicle.setdefault((tx["plate_number"], tx["province"]), []).append(tx)

    check_by_vehicle = {(row["plate_number"], row["province"]): row for row in checks}
    now = datetime.now(tz=UTC)
    urgent_cutoff = now + timedelta(hours=settings.urgent_before_hours)
    vehicle_rows: list[dict] = []

    for vehicle in vehicles:
        key = (vehicle.plate_number, vehicle.province)
        latest = check_by_vehicle.get(key)
        unpaid = tx_by_vehicle.get(key, [])
        deadlines = [dt for dt in (_parse_iso(row.get("deadline")) for row in unpaid) if dt]
        nearest_deadline = min(deadlines) if deadlines else None

        if latest and latest["status"] in {"CHECK_FAILED", "REVIEW_REQUIRED"}:
            status = "ATTENTION"
        elif unpaid and nearest_deadline and nearest_deadline <= urgent_cutoff:
            status = "URGENT"
        elif unpaid:
            status = "UNPAID"
        elif latest and latest["status"] == "CLEAR":
            status = "CLEAR"
        else:
            status = "NOT_CHECKED"

        amount_values = [row["amount"] for row in unpaid if row["amount"] is not None]
        payment_url = None
        if _mode() == "LIVE":
            for row in unpaid:
                source = row.get("source_url") or ""
                if urlparse(source).scheme in {"http", "https"}:
                    payment_url = source
                    break
            payment_url = payment_url or (settings.mflow_url if unpaid else None)

        vehicle_rows.append(
            {
                "plate_number": vehicle.plate_number,
                "province": vehicle.province,
                "driver_name": vehicle.driver_name,
                "status": status,
                "outstanding_count": len(unpaid),
                "outstanding_amount": round(sum(amount_values), 2) if amount_values else (None if unpaid else 0),
                "nearest_deadline": nearest_deadline.isoformat() if nearest_deadline else None,
                "last_checked": latest.get("checked_at") if latest else None,
                "last_check_status": latest.get("status") if latest else None,
                "detail": latest.get("detail", "") if latest else "",
                "payment_url": payment_url,
            }
        )

    counts = {
        "total": len(vehicle_rows),
        "urgent": sum(row["status"] == "URGENT" for row in vehicle_rows),
        "unpaid": sum(row["status"] == "UNPAID" for row in vehicle_rows),
        "attention": sum(row["status"] == "ATTENTION" for row in vehicle_rows),
        "clear": sum(row["status"] == "CLEAR" for row in vehicle_rows),
        "not_checked": sum(row["status"] == "NOT_CHECKED" for row in vehicle_rows),
    }
    last_updated_values = [dt for dt in (_parse_iso(row.get("checked_at")) for row in checks) if dt]

    with state.lock:
        notifications = list(state.demo_notifications)

    run = state.snapshot()
    if configuration_error and not run["last_error"]:
        run["last_error"] = configuration_error

    return {
        "mode": _mode(),
        "summary": counts,
        "vehicles": vehicle_rows,
        "last_updated": max(last_updated_values).isoformat() if last_updated_values else None,
        "run": run,
        "demo_notifications": notifications,
    }


def _json_bytes(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def serve(settings: Settings, host: str = "127.0.0.1", port: int = 8080) -> None:
    state = DashboardRunState()

    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_json(self, status: int, payload: dict) -> None:
            self._send(status, _json_bytes(payload), "application/json; charset=utf-8")

        def do_GET(self):  # noqa: N802
            path = self.path.split("?", 1)[0]
            if path == "/api/summary":
                self._send_json(200, build_summary(settings, state))
                return
            if path == "/health":
                self._send_json(200, {"ok": True, "mode": _mode()})
                return

            file_map = {
                "/": WEB_DIR / "index.html",
                "/index.html": WEB_DIR / "index.html",
                "/assets/styles.css": WEB_DIR / "styles.css",
                "/assets/app.js": WEB_DIR / "app.js",
            }
            file_path = file_map.get(path)
            if not file_path or not file_path.exists():
                self._send_json(404, {"error": "not found"})
                return
            content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
            if content_type.startswith("text/") or content_type in {"application/javascript"}:
                content_type += "; charset=utf-8"
            self._send(200, file_path.read_bytes(), content_type)

        def do_POST(self):  # noqa: N802
            path = self.path.split("?", 1)[0]
            if path != "/api/check":
                self._send_json(404, {"error": "not found"})
                return
            try:
                settings.load_vehicles()
            except Exception as exc:
                self._send_json(400, {"error": f"ยังไม่ได้ตั้งค่ารายการรถ: {exc}"})
                return
            started = start_check(settings, state)
            self._send_json(202, {"started": started, "running": True})

        def log_message(self, fmt, *args):
            log.debug(fmt, *args)

    server = ThreadingHTTPServer((host, port), Handler)
    print(f"M-Flow Fleet Admin: http://{host}:{port}  mode={_mode()}")
    server.serve_forever()

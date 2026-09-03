from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .api_checker import MFlowApiChecker
from .config import Settings, Vehicle
from .models import CheckStatus

UTC = timezone.utc
HOST = "127.0.0.1"
PORT = 8765
AGENT_VERSION = "0.3"
ALLOWED_ORIGINS = {
    "https://mflow-admin-demo.vercel.app",
    "https://mflow-admin-demo-saratchais-projects-fe70d048.vercel.app",
    "http://127.0.0.1:8080",
    "http://localhost:8080",
}
CHECK_LOCK = threading.Lock()


def _as_aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _iso_date(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _serialize_result(vehicle: Vehicle, result, settings: Settings) -> dict:
    now = datetime.now(tz=UTC)
    items = []
    for item in result.items:
        tx = _as_aware(item.transaction_date)
        official_due = _as_aware(item.due_date)
        deadline = official_due or ((tx or now) + timedelta(hours=settings.safety_deadline_hours))
        items.append(
            {
                "transaction_date": _iso_date(tx),
                "amount": item.amount,
                "source_url": item.source_url,
                "internal_deadline": deadline.isoformat(),
                "official_due_date": _iso_date(official_due),
            }
        )
    return {
        "plate_number": vehicle.plate_number,
        "province": vehicle.province,
        "driver_name": vehicle.driver_name,
        "status": result.status.value,
        "detail": result.detail,
        "source_url": result.source_url or settings.mflow_url,
        "items": items,
        "checked_at": now.isoformat(),
        "is_live": True,
        "engine": "MFLOW_API2",
    }


class AgentHandler(BaseHTTPRequestHandler):
    server_version = f"MFlowLocalAgent/{AGENT_VERSION}"

    def _origin_allowed(self) -> bool:
        origin = self.headers.get("Origin")
        return origin is None or origin in ALLOWED_ORIGINS

    def _cors(self) -> None:
        origin = self.headers.get("Origin")
        if origin in ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-MFlow-Agent")
        self.send_header("Access-Control-Allow-Private-Network", "true")

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):  # noqa: N802
        if not self._origin_allowed():
            self.send_response(403)
            self.end_headers()
            return
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):  # noqa: N802
        if not self._origin_allowed():
            self._json(403, {"ok": False, "error": "origin_not_allowed"})
            return
        if self.path == "/health":
            settings = Settings.from_env()
            self._json(
                200,
                {
                    "ok": True,
                    "mode": "LIVE_LOCAL_AGENT",
                    "engine": "MFLOW_API2",
                    "mflow_url": settings.mflow_url,
                    "headless": settings.headless,
                    "version": AGENT_VERSION,
                },
            )
            return
        self._json(404, {"ok": False, "error": "not_found"})

    def do_POST(self):  # noqa: N802
        if not self._origin_allowed():
            self._json(403, {"ok": False, "error": "origin_not_allowed"})
            return
        if self.headers.get("X-MFlow-Agent") != "1":
            self._json(400, {"ok": False, "error": "missing_agent_header"})
            return
        if self.path != "/api/check":
            self._json(404, {"ok": False, "error": "not_found"})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0 or length > 100_000:
            self._json(400, {"ok": False, "error": "invalid_body_size"})
            return

        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
            raw_vehicles = data.get("vehicles", [])
            if not isinstance(raw_vehicles, list) or not (1 <= len(raw_vehicles) <= 30):
                raise ValueError("vehicles must contain 1-30 items")
            vehicles = [Vehicle.from_dict(item) for item in raw_vehicles]
        except Exception as exc:
            self._json(400, {"ok": False, "error": f"invalid_request: {exc}"})
            return

        if not CHECK_LOCK.acquire(blocking=False):
            self._json(409, {"ok": False, "error": "check_in_progress"})
            return

        try:
            settings = Settings.from_env()
            checker = MFlowApiChecker(settings)
            results = []
            for vehicle in vehicles:
                result = checker.check(vehicle)
                results.append(_serialize_result(vehicle, result, settings))
            failed = sum(
                1
                for row in results
                if row["status"]
                in {CheckStatus.CHECK_FAILED.value, CheckStatus.REVIEW_REQUIRED.value}
            )
            self._json(
                200,
                {
                    "ok": True,
                    "is_live": True,
                    "engine": "MFLOW_API2",
                    "source": "M-Flow current nonmember API via local agent",
                    "results": results,
                    "failed": failed,
                },
            )
        finally:
            CHECK_LOCK.release()

    def log_message(self, fmt, *args):
        return


def main() -> None:
    print("M-Flow LIVE Local Agent")
    print("Engine: current M-Flow API2 nonmember lookup")
    print(f"Listening only on http://{HOST}:{PORT}")
    print("Allowed web app: https://mflow-admin-demo.vercel.app")
    print("Press Ctrl+C to stop.")
    server = ThreadingHTTPServer((HOST, PORT), AgentHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

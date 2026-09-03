from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class Vehicle:
    plate_number: str
    province: str
    driver_name: str = ""
    active: bool = True

    @classmethod
    def from_dict(cls, data: dict) -> "Vehicle":
        plate = str(data.get("plate_number", "")).strip()
        province = str(data.get("province", "")).strip()
        if not plate or not province:
            raise ValueError("Each vehicle requires plate_number and province")
        return cls(
            plate_number=plate,
            province=province,
            driver_name=str(data.get("driver_name", "")).strip(),
            active=bool(data.get("active", True)),
        )


@dataclass(frozen=True)
class Settings:
    mflow_url: str
    headless: bool
    timeout_seconds: int
    safety_deadline_hours: int
    renotify_after_hours: int
    urgent_before_hours: int
    failure_renotify_hours: int
    database_path: Path
    artifact_dir: Path
    vehicles_file: Path
    vehicles_json: str | None
    line_channel_access_token: str | None
    line_to: str | None
    telegram_bot_token: str | None
    telegram_chat_id: str | None
    slack_webhook_url: str | None

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            mflow_url=os.getenv("MFLOW_URL", "https://mflowthai.com/mflow/checkunbilled"),
            headless=_as_bool(os.getenv("MFLOW_HEADLESS"), True),
            timeout_seconds=int(os.getenv("MFLOW_TIMEOUT_SECONDS", "30")),
            safety_deadline_hours=int(os.getenv("MFLOW_SAFETY_DEADLINE_HOURS", "48")),
            renotify_after_hours=int(os.getenv("MFLOW_RENOTIFY_AFTER_HOURS", "24")),
            urgent_before_hours=int(os.getenv("MFLOW_URGENT_BEFORE_HOURS", "12")),
            failure_renotify_hours=int(os.getenv("MFLOW_FAILURE_RENOTIFY_HOURS", "8")),
            database_path=Path(os.getenv("DATABASE_PATH", "data/mflow.db")),
            artifact_dir=Path(os.getenv("ARTIFACT_DIR", "artifacts")),
            vehicles_file=Path(os.getenv("VEHICLES_FILE", "vehicles.json")),
            vehicles_json=os.getenv("VEHICLES_JSON"),
            line_channel_access_token=os.getenv("LINE_CHANNEL_ACCESS_TOKEN"),
            line_to=os.getenv("LINE_TO"),
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN"),
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID"),
            slack_webhook_url=os.getenv("SLACK_WEBHOOK_URL"),
        )

    def load_vehicles(self) -> list[Vehicle]:
        if self.vehicles_json:
            raw = json.loads(self.vehicles_json)
        else:
            if not self.vehicles_file.exists():
                raise FileNotFoundError(
                    f"Vehicle list not found: {self.vehicles_file}. "
                    "Create vehicles.json or set VEHICLES_JSON."
                )
            raw = json.loads(self.vehicles_file.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise ValueError("Vehicle configuration must be a JSON array")
        vehicles = [Vehicle.from_dict(item) for item in raw]
        return [vehicle for vehicle in vehicles if vehicle.active]

from __future__ import annotations

import hashlib
import json
import re
import secrets
from datetime import datetime
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import requests

from .config import Settings, Vehicle
from .models import CheckResult, CheckStatus, OutstandingItem

ENV_URL = "https://mflowthai.com/mflowspf/assets/.env"
WEB_URL = "https://mflowthai.com/mflowspf/"
BANGKOK = ZoneInfo("Asia/Bangkok")
ALLOWED_API_HOSTS = {"api2.mflowthai.com"}
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/152.0.0.0 Safari/537.36"
)


class MFlowApiError(RuntimeError):
    """Raised when the current public M-Flow API configuration is unusable."""


def parse_public_env(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if value and value[0] in {"'", '"'} and value[-1:] == value[0]:
            value = value[1:-1]
        values[key.strip()] = value.strip()
    return values


def normalize_province(value: str) -> str:
    normalized = re.sub(r"[\s.]+", "", value.strip().lower())
    if normalized.startswith("จังหวัด"):
        normalized = normalized[len("จังหวัด") :]
    aliases = {
        "กทม": "กรุงเทพมหานคร",
        "กรุงเทพ": "กรุงเทพมหานคร",
        "bangkok": "กรุงเทพมหานคร",
        "bkk": "กรุงเทพมหานคร",
    }
    return aliases.get(normalized, normalized)


def split_plate_number(value: str) -> tuple[str, str]:
    display = value.strip()
    if not display:
        raise ValueError("กรุณากรอกทะเบียนรถ")

    normalized = re.sub(r"[\u00a0\s\-–—_/]+", " ", display).strip()
    parts = normalized.split()
    if len(parts) >= 2 and parts[-1].isdigit():
        plate1 = "".join(parts[:-1])
        plate2 = parts[-1]
    else:
        compact = re.sub(r"[\u00a0\s\-–—_/]+", "", display)
        match = re.fullmatch(r"(.+?)(\d{1,4})", compact)
        if not match:
            raise ValueError("รูปแบบทะเบียนไม่ชัดเจน กรุณาใส่เช่น 7ขก 1181")
        plate1, plate2 = match.groups()

    if not plate1 or len(plate1) > 8 or not re.fullmatch(r"\d{1,4}", plate2):
        raise ValueError("รูปแบบทะเบียนไม่ถูกต้อง กรุณาใส่เช่น 7ขก 1181")
    return plate1, plate2


def parse_mflow_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        if number > 10_000_000_000:
            number /= 1000
        try:
            return datetime.fromtimestamp(number, tz=BANGKOK)
        except (ValueError, OSError, OverflowError):
            return None

    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
        return parsed.replace(tzinfo=BANGKOK) if parsed.tzinfo is None else parsed
    except ValueError:
        pass
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y",
    ):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=BANGKOK)
        except ValueError:
            continue
    return None


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = re.sub(r"[^0-9.\-]", "", str(value))
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _safe_excerpt(value: Any, limit: int = 800) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        text = str(value)
    return text[:limit]


def parse_transaction_response(payload: Any, source_url: str = WEB_URL) -> CheckResult:
    if not isinstance(payload, dict):
        return CheckResult(
            CheckStatus.REVIEW_REQUIRED,
            detail="M-Flow ตอบกลับมาในรูปแบบที่ระบบอ่านไม่ได้",
            source_url=source_url,
        )

    status = payload.get("status")
    message = str(payload.get("message") or "").strip()
    if status is not True:
        detail = message or "M-Flow ไม่ยืนยันว่าการค้นหาสำเร็จ"
        return CheckResult(CheckStatus.REVIEW_REQUIRED, detail=detail, source_url=source_url)

    plates = payload.get("plate")
    if not isinstance(plates, list):
        return CheckResult(
            CheckStatus.REVIEW_REQUIRED,
            detail="M-Flow แจ้งว่าสำเร็จ แต่ไม่มีฟิลด์รายการทะเบียนที่ตรวจสอบได้",
            source_url=source_url,
        )
    if not plates:
        return CheckResult(
            CheckStatus.CLEAR,
            detail=message or "M-Flow ไม่พบรายการค้างชำระ",
            source_url=source_url,
        )

    items: list[OutstandingItem] = []
    for plate_row in plates:
        if not isinstance(plate_row, dict):
            continue
        plate_due = parse_mflow_datetime(plate_row.get("dueDate"))
        plate_total = _number(plate_row.get("totalAmount"))
        invoices = plate_row.get("invoice")

        if isinstance(invoices, list) and invoices:
            for invoice in invoices:
                if not isinstance(invoice, dict):
                    continue
                amount = _number(invoice.get("totalAmount"))
                if amount is None:
                    amount = _number(invoice.get("feeAmount"))
                tx_date = parse_mflow_datetime(invoice.get("transactionDatetime"))
                due_date = parse_mflow_datetime(invoice.get("dueDate")) or plate_due
                items.append(
                    OutstandingItem(
                        transaction_date=tx_date,
                        amount=amount,
                        source_url=source_url,
                        raw_excerpt=_safe_excerpt(invoice),
                        due_date=due_date,
                    )
                )
        else:
            items.append(
                OutstandingItem(
                    transaction_date=None,
                    amount=plate_total,
                    source_url=source_url,
                    raw_excerpt=_safe_excerpt(plate_row),
                    due_date=plate_due,
                )
            )

    if not items:
        return CheckResult(
            CheckStatus.REVIEW_REQUIRED,
            detail="M-Flow พบข้อมูลทะเบียน แต่ระบบอ่านรายการภายในไม่ได้",
            source_url=source_url,
        )

    return CheckResult(
        CheckStatus.UNPAID,
        items=items,
        detail=message or f"M-Flow พบ {len(items)} รายการที่ต้องตรวจสอบ/ชำระ",
        source_url=source_url,
    )


class MFlowApiChecker:
    """Read-only checker using the same public API flow as the current M-Flow SPA."""

    def __init__(self, settings: Settings, session: requests.Session | None = None):
        self.settings = settings
        self.session = session or requests.Session()
        self.timeout = max(5, settings.timeout_seconds)
        self.device_id = hashlib.sha256(secrets.token_bytes(32)).hexdigest()[:20]
        self._config: dict[str, str] | None = None
        self._province_map: dict[str, str] | None = None

    def _load_config(self) -> dict[str, str]:
        if self._config is not None:
            return self._config
        response = self.session.get(
            ENV_URL,
            headers={"User-Agent": USER_AGENT, "Accept": "text/plain,*/*"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        config = parse_public_env(response.text)
        required = ("API_KEY", "MASTER_SERVICE_BASE_URL", "BILLING_SERVICE_BASE_URL")
        missing = [key for key in required if not config.get(key)]
        if missing:
            raise MFlowApiError("M-Flow public configuration missing: " + ", ".join(missing))
        for key in ("MASTER_SERVICE_BASE_URL", "BILLING_SERVICE_BASE_URL"):
            parsed = urlparse(config[key])
            if parsed.scheme != "https" or parsed.hostname not in ALLOWED_API_HOSTS:
                raise MFlowApiError(f"M-Flow returned an unexpected API host for {key}")
        self._config = config
        return config

    def _headers(self) -> dict[str, str]:
        config = self._load_config()
        now = datetime.now(tz=BANGKOK)
        millis = now.strftime("%Y%m%d%H%M%S%f")[:-3]
        return {
            "TransactionId": f"T{millis}{secrets.randbelow(1000):03d}",
            "RequestDate": now.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3],
            "Source": "WEB",
            "DeviceId": self.device_id,
            "Language": "TH",
            "System": "M00000",
            "apiKey": config["API_KEY"],
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Origin": "https://mflowthai.com",
            "Referer": WEB_URL,
            "User-Agent": USER_AGENT,
        }

    @staticmethod
    def _error_detail(payload: Any, fallback: str) -> str:
        if isinstance(payload, dict):
            parts: list[str] = []
            message = payload.get("message")
            if message:
                parts.append(str(message))
            errors = payload.get("errors")
            if isinstance(errors, list):
                for row in errors[:3]:
                    if isinstance(row, dict):
                        error = row.get("error", row)
                        if isinstance(error, dict):
                            desc = error.get("description") or error.get("message") or error.get("code")
                            if desc:
                                parts.append(str(desc))
            if parts:
                return " — ".join(dict.fromkeys(parts))
        return fallback

    def _load_provinces(self) -> dict[str, str]:
        if self._province_map is not None:
            return self._province_map
        config = self._load_config()
        url = config["MASTER_SERVICE_BASE_URL"].rstrip("/") + "/v1/masterDropdown/dropdownProvince"
        response = self.session.get(
            url,
            params={"specialRegionFlag": "0"},
            headers=self._headers(),
            timeout=self.timeout,
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise MFlowApiError("M-Flow province service returned invalid JSON") from exc
        if response.status_code != 200 or not isinstance(payload, dict) or payload.get("status") is not True:
            raise MFlowApiError(self._error_detail(payload, f"province service HTTP {response.status_code}"))
        rows = payload.get("data")
        if not isinstance(rows, list):
            raise MFlowApiError("M-Flow province list is missing")
        result: dict[str, str] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            name = row.get("provinceName")
            code = row.get("provinceCode")
            if name and code:
                result[normalize_province(str(name))] = str(code)
        if not result:
            raise MFlowApiError("M-Flow returned an empty province list")
        self._province_map = result
        return result

    def _province_code(self, province: str) -> str:
        key = normalize_province(province)
        code = self._load_provinces().get(key)
        if not code:
            raise ValueError(f"ไม่พบจังหวัด ‘{province}’ ในรายการของ M-Flow")
        return code

    def check(self, vehicle: Vehicle) -> CheckResult:
        try:
            plate1, plate2 = split_plate_number(vehicle.plate_number)
            province_code = self._province_code(vehicle.province)
            config = self._load_config()
            url = config["BILLING_SERVICE_BASE_URL"].rstrip("/") + "/v1/nonmember/transaction-payment"
            payload = {
                "customerId": None,
                "customerType": None,
                "licensePlateGroupType": "NORMAL",
                "plate1": plate1,
                "plate2": plate2,
                "provinceCode": province_code,
                "startDate": None,
                "endDate": None,
                "selectType": "1",
            }
            response = self.session.post(url, headers=self._headers(), json=payload, timeout=self.timeout)
            try:
                data = response.json()
            except ValueError:
                return CheckResult(
                    CheckStatus.CHECK_FAILED,
                    detail=f"M-Flow API ตอบกลับไม่ใช่ JSON (HTTP {response.status_code})",
                    source_url=WEB_URL,
                )
            if response.status_code != 200:
                return CheckResult(
                    CheckStatus.CHECK_FAILED,
                    detail=self._error_detail(data, f"M-Flow API HTTP {response.status_code}"),
                    source_url=WEB_URL,
                )
            return parse_transaction_response(data, WEB_URL)
        except ValueError as exc:
            return CheckResult(CheckStatus.REVIEW_REQUIRED, detail=str(exc), source_url=WEB_URL)
        except (requests.RequestException, MFlowApiError) as exc:
            return CheckResult(
                CheckStatus.CHECK_FAILED,
                detail=f"เชื่อมต่อ M-Flow API ไม่สำเร็จ: {exc}",
                source_url=WEB_URL,
            )
        except Exception as exc:
            return CheckResult(
                CheckStatus.CHECK_FAILED,
                detail=f"ตรวจ M-Flow ไม่สำเร็จ: {type(exc).__name__}: {exc}",
                source_url=WEB_URL,
            )

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

WEB_BASE = "https://mflowthai.com/mflowspf/"
API_BASE = "https://api2.mflowthai.com"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/152 Safari/537.36"


def request(url: str, method: str = "GET", headers: dict[str, str] | None = None, body: dict | None = None):
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    merged = {"User-Agent": UA, "Accept": "application/json, text/plain, */*", **(headers or {})}
    if payload is not None:
        merged["Content-Type"] = "application/json"
    req = Request(url, data=payload, headers=merged, method=method)
    try:
        with urlopen(req, timeout=45) as response:
            raw = response.read()
            return response.status, dict(response.headers), raw.decode("utf-8", errors="replace")
    except HTTPError as exc:
        raw = exc.read()
        return exc.code, dict(exc.headers), raw.decode("utf-8", errors="replace")
    except URLError as exc:
        return 0, {}, str(exc)


def parse_env(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.split(" #", 1)[0].strip().strip("'\"")
        out[key.strip()] = value
    return out


def safe_print(label: str, status: int, text: str):
    # Never print tokens/API keys. Only show upstream response body.
    compact = " ".join(text.split())
    print(label, "STATUS", status, "BODY", compact[:6000])


status, _, env_text = request(WEB_BASE + "assets/.env")
print("ENV_STATUS", status)
env = parse_env(env_text)
api_key = env.get("API_KEY", "")
if not api_key:
    raise SystemExit("API_KEY missing from public web runtime config")

common = {
    "apikey": api_key,
    "TransactionId": str(uuid.uuid4()),
    "RequestDate": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
    "Source": "WEB",
    "DeviceId": str(uuid.uuid4()),
    "Language": "TH",
    "System": "M00000",
    "Origin": "https://mflowthai.com",
    "Referer": WEB_BASE,
}

province_url = API_BASE + "/masterservice/api/v1/masterDropdown/dropdownProvince"
plate_type_url = API_BASE + "/masterservice/api/v1/masterDropdown/licensePlateType"
for label, url in (("PROVINCES", province_url), ("PLATE_TYPES", plate_type_url)):
    s, _, t = request(url, headers=common)
    safe_print(label, s, t)

now = datetime.now(timezone.utc)
start = (now - timedelta(days=30)).strftime("%Y-%m-%d")
end = now.strftime("%Y-%m-%d")
endpoint = API_BASE + "/billing-service/api/v1/nonmember/transaction-payment"

bodies = [
    {
        "customerId": "",
        "customerType": "NON_MEMBER",
        "licensePlateGroupType": "1",
        "plate1": "1กก",
        "plate2": "0000",
        "provinceCode": "10",
        "startDate": start,
        "endDate": end,
        "selectType": "LICENSE_PLATE",
    },
    {
        "customerId": "",
        "customerType": "GUEST",
        "licensePlateGroupType": "1",
        "plate1": "1กก",
        "plate2": "0000",
        "provinceCode": "10",
        "startDate": start,
        "endDate": end,
        "selectType": "1",
    },
]

for index, body in enumerate(bodies, 1):
    s, _, t = request(endpoint, method="POST", headers=common, body=body)
    safe_print(f"PAYMENT_TRY_{index}", s, t)

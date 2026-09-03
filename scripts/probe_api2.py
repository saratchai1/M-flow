from __future__ import annotations

import base64
import json
import random
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ENV_URL = "https://mflowthai.com/mflowspf/assets/.env"
FAKE_PLATE_1 = "9กก"
FAKE_PLATE_2 = "9999"
DEVICE_ID = "mflowwatchdogprobe01"
DEVICE_NAME = "MFlow Watchdog Probe"


def fetch_text(url: str) -> str:
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=60) as response:
        return response.read().decode("utf-8", errors="replace")


def parse_env(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.split("#", 1)[0].strip().strip("'\"")
        result[key.strip()] = value
    return result


def common_headers(api_key: str) -> dict[str, str]:
    now = datetime.now()
    return {
        "TransactionId": "T" + now.strftime("%Y%m%d%H%M%S%f")[:-3] + f"{random.randint(0, 999):03d}",
        "RequestDate": now.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3],
        "Source": "WEB",
        "DeviceId": DEVICE_ID,
        "Language": "TH",
        "System": "M00000",
        "apiKey": api_key,
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/152 Safari/537.36",
    }


def request_json(method: str, url: str, headers: dict[str, str], payload=None):
    data = None
    request_headers = dict(headers)
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    req = Request(url, data=data, headers=request_headers, method=method)
    try:
        with urlopen(req, timeout=60) as response:
            raw = response.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = raw
            return response.status, dict(response.headers), parsed
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = raw
        return exc.code, dict(exc.headers), parsed


def redact(value):
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if any(token in key.lower() for token in ("token", "authorization", "apikey", "secret")):
                out[key] = "<redacted>" if item else item
            else:
                out[key] = redact(item)
        return out
    if isinstance(value, list):
        return [redact(item) for item in value[:10]]
    if isinstance(value, str) and len(value) > 600:
        return value[:600] + "…"
    return value


def print_result(label: str, status: int, payload) -> None:
    print(label + "_STATUS", status)
    print(label + "_RESPONSE", json.dumps(redact(payload), ensure_ascii=False)[:7000])


def find_province_code(payload, names=("กรุงเทพมหานคร", "กรุงเทพ", "Bangkok")) -> str | None:
    if isinstance(payload, dict):
        name = str(payload.get("provinceName", ""))
        if any(candidate.lower() in name.lower() for candidate in names):
            code = payload.get("provinceCode")
            if code is not None:
                return str(code)
        for value in payload.values():
            found = find_province_code(value, names)
            if found:
                return found
    elif isinstance(payload, list):
        for item in payload:
            found = find_province_code(item, names)
            if found:
                return found
    return None


def main() -> int:
    env = parse_env(fetch_text(ENV_URL))
    required = ("API_KEY", "CUSTOMER_SERVICE_BASE_URL", "MASTER_SERVICE_BASE_URL", "BILLING_SERVICE_BASE_URL")
    missing = [key for key in required if not env.get(key)]
    if missing:
        print("MISSING_ENV", missing)
        return 2

    base_headers = common_headers(env["API_KEY"])
    master_url = env["MASTER_SERVICE_BASE_URL"].rstrip("/") + "/v1/masterDropdown/dropdownProvince"

    province_code = None
    for auth_label, authorization in (("NOAUTH", None), ("RAWGUEST", "Basic [GUEST]")):
        headers = dict(base_headers)
        if authorization:
            headers["Authorization"] = authorization
        for special in ("N", "false", "0", ""):
            url = master_url + ("?" + urlencode({"specialRegionFlag": special}) if special else "")
            status, _, payload = request_json("GET", url, headers)
            print_result(f"PROVINCE_{auth_label}_{special or 'OMITTED'}", status, payload)
            code = find_province_code(payload)
            if status < 400 and code:
                province_code = code
                break
        if province_code:
            break

    if not province_code:
        print("NO_BANGKOK_PROVINCE_CODE")
        return 4
    print("BANGKOK_PROVINCE_CODE", province_code)

    billing_url = env["BILLING_SERVICE_BASE_URL"].rstrip("/") + "/v1/nonmember/transaction-payment"
    body = {
        "customerId": None,
        "customerType": None,
        "licensePlateGroupType": "NORMAL",
        "plate1": FAKE_PLATE_1,
        "plate2": FAKE_PLATE_2,
        "provinceCode": province_code,
        "startDate": None,
        "endDate": None,
        "selectType": "1",
    }

    auth_variants = (
        ("NOAUTH", None),
        ("RAWGUEST", "Basic [GUEST]"),
        ("B64BRACKETGUEST", "Basic " + base64.b64encode(b"[GUEST]").decode()),
        ("B64GUEST", "Basic " + base64.b64encode(b"GUEST").decode()),
    )
    best_status = 999
    for label, authorization in auth_variants:
        headers = common_headers(env["API_KEY"])
        if authorization:
            headers["Authorization"] = authorization
        status, _, payload = request_json("POST", billing_url, headers, body)
        print_result("TRANSACTION_" + label, status, payload)
        best_status = min(best_status, status)
        if status < 400:
            print("WORKING_AUTH_VARIANT", label)
            return 0

    # Retain a focused auth probe for diagnosis, but it is no longer assumed to
    # be required by the nonmember endpoint.
    auth_url = env["CUSTOMER_SERVICE_BASE_URL"].rstrip("/") + "/v1/auth/sign-in/app"
    for label, authorization in auth_variants[1:]:
        auth_headers = {
            **common_headers(env["API_KEY"]),
            "Authorization": authorization,
            "LoginType": "GUEST",
            "AccountType": "CUSTOMER",
            "X-Device-Id": DEVICE_ID,
            "X-Device-Name": DEVICE_NAME,
        }
        status, _, payload = request_json("POST", auth_url, auth_headers)
        print_result("AUTH_" + label, status, payload)

    return 5 if best_status >= 500 else 6


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (URLError, TimeoutError) as exc:
        print("NETWORK_ERROR", type(exc).__name__, str(exc))
        raise SystemExit(10)

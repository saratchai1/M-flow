from __future__ import annotations

import json
import random
import string
import time
import uuid
from datetime import datetime, timezone, timedelta
from urllib.error import HTTPError
from urllib.request import Request, urlopen

WEB_ENV = "https://mflowthai.com/mflowspf/assets/.env"
MASTER = "https://api2.mflowthai.com/masterservice/api/v1/masterDropdown/dropdownProvince"
PAYMENT = "https://api2.mflowthai.com/billing-service/api/v1/nonmember/transaction-payment"
UA = "Mozilla/5.0 AppleWebKit/537.36 Chrome/152 Safari/537.36"


def fetch(url, method="GET", headers=None, body=None):
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    h = {"User-Agent": UA, "Accept": "application/json, text/plain, */*", **(headers or {})}
    if data is not None:
        h["Content-Type"] = "application/json"
    req = Request(url, data=data, headers=h, method=method)
    try:
        with urlopen(req, timeout=30) as response:
            return response.status, response.read().decode(errors="replace")
    except HTTPError as exc:
        return exc.code, exc.read().decode(errors="replace")


def parse_env(text):
    out = {}
    for line in text.splitlines():
        if "=" not in line or line.lstrip().startswith("#"):
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.split(" #", 1)[0].strip().strip("'\"")
    return out


_, env_text = fetch(WEB_ENV)
api_key = parse_env(env_text)["API_KEY"]
bkk = datetime.now(timezone(timedelta(hours=7)))
utc = datetime.now(timezone.utc)

def rand_digits(n):
    return "".join(random.choice(string.digits) for _ in range(n))

request_dates = [
    ("bkk_yyyyMMddHHmmss", bkk.strftime("%Y%m%d%H%M%S")),
    ("utc_yyyyMMddHHmmss", utc.strftime("%Y%m%d%H%M%S")),
    ("bkk_yyyyMMddHHmmssSSS", bkk.strftime("%Y%m%d%H%M%S") + f"{bkk.microsecond//1000:03d}"),
    ("utc_yyyyMMddHHmmssSSS", utc.strftime("%Y%m%d%H%M%S") + f"{utc.microsecond//1000:03d}"),
    ("bkk_iso_seconds", bkk.strftime("%Y-%m-%dT%H:%M:%S")),
    ("utc_iso_z", utc.strftime("%Y-%m-%dT%H:%M:%SZ")),
    ("bkk_space", bkk.strftime("%Y-%m-%d %H:%M:%S")),
    ("bkk_dmy", bkk.strftime("%d/%m/%Y %H:%M:%S")),
    ("epoch_ms", str(int(time.time()*1000))),
]

base_headers = {
    "apikey": api_key,
    "Source": "WEB",
    "DeviceId": str(uuid.uuid4()),
    "Language": "TH",
    "System": "M00000",
    "Origin": "https://mflowthai.com",
    "Referer": "https://mflowthai.com/mflowspf/",
}

valid_date = None
print("REQUEST_DATE_TESTS")
for label, value in request_dates:
    headers = {**base_headers, "RequestDate": value, "TransactionId": rand_digits(20)}
    status, text = fetch(MASTER, headers=headers)
    compact = " ".join(text.split())
    print(label, "len", len(value), "status", status, "body", compact[:500])
    if "SGP_ERR_90002" not in text:
        valid_date = value
        print("REQUEST_DATE_CHANGED", label)
        break

if valid_date is None:
    raise SystemExit("No request date candidate passed validation")

transaction_ids = [
    ("uuid36", str(uuid.uuid4())),
    ("uuid32", uuid.uuid4().hex),
    ("digits13", str(int(time.time()*1000))),
    ("digits14", bkk.strftime("%Y%m%d%H%M%S")),
    ("digits17", bkk.strftime("%Y%m%d%H%M%S") + f"{bkk.microsecond//1000:03d}"),
    ("digits20", bkk.strftime("%Y%m%d%H%M%S") + rand_digits(6)),
    ("digits24", bkk.strftime("%Y%m%d%H%M%S") + rand_digits(10)),
    ("web32", "WEB" + uuid.uuid4().hex[:29]),
]
body = {
    "customerId": "",
    "customerType": "GUEST",
    "licensePlateGroupType": "1",
    "plate1": "1กก",
    "plate2": "0000",
    "provinceCode": "10",
    "startDate": (bkk - timedelta(days=30)).strftime("%Y-%m-%d"),
    "endDate": bkk.strftime("%Y-%m-%d"),
    "selectType": "1",
}
print("TRANSACTION_ID_TESTS")
for label, value in transaction_ids:
    headers = {**base_headers, "RequestDate": valid_date, "TransactionId": value}
    status, text = fetch(PAYMENT, method="POST", headers=headers, body=body)
    compact = " ".join(text.split())
    print(label, "len", len(value), "status", status, "body", compact[:700])
    if "BIL_ERR_00002" not in text:
        print("TRANSACTION_ID_CHANGED", label)
        break

from __future__ import annotations

import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE = "https://mflowthai.com/mflowspf/"
FILES = (
    "assets/.env",
    "assets/AssetManifest.json",
    "version.json",
    "manifest.json",
    "flutter_service_worker.js",
    "index.html",
)


def fetch(path: str) -> tuple[int, str, bytes]:
    request = Request(BASE + path, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urlopen(request, timeout=30) as response:
            return response.status, response.headers.get("Content-Type", ""), response.read()
    except HTTPError as exc:
        return exc.code, exc.headers.get("Content-Type", ""), exc.read()
    except URLError as exc:
        return 0, "", str(exc).encode()


for path in FILES:
    status, content_type, raw = fetch(path)
    text = raw.decode("utf-8", errors="ignore")
    print("\nFILE", path, "STATUS", status, "TYPE", content_type, "BYTES", len(raw))
    print("CONTENT", text[:250000])

status, _, raw = fetch("main.dart.js")
bundle = raw.decode("utf-8", errors="ignore")
print("\nBUNDLE_STATUS", status, "BYTES", len(raw))
for keyword in (
    "apiBaseUrl", "customerServiceBaseUrl", "authServiceBaseUrl", "masterServiceBaseUrl",
    "vehicleServiceBaseUrl", "apwBillingServiceBaseUrl", "strapiBaseUrl", "disputeBaseUrl",
    "/v1/nonmember/transaction-payment", "Basic [GUEST]", "apiKey",
):
    positions = [m.start() for m in re.finditer(re.escape(keyword), bundle, flags=re.I)]
    print("KEYWORD", keyword, "COUNT", len(positions))
    for pos in positions[:10]:
        start = max(0, pos - 700)
        end = min(len(bundle), pos + len(keyword) + 1000)
        print("CONTEXT", " ".join(bundle[start:end].replace("\x00", " ").split())[:2500])

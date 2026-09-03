from __future__ import annotations

import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE = "https://mflowthai.com/mflowspf/"
CANDIDATES = (
    "assets/AssetManifest.json",
    "assets/AssetManifest.bin.json",
    "assets/AssetManifest.bin",
    "AssetManifest.json",
    "AssetManifest.bin.json",
    "version.json",
    "flutter_service_worker.js",
    "flutter_bootstrap.js",
    "main.dart.js",
)


def fetch(path: str) -> tuple[int, str, bytes]:
    url = BASE + path
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urlopen(request, timeout=90) as response:
            return response.status, response.headers.get("Content-Type", ""), response.read()
    except HTTPError as exc:
        return exc.code, exc.headers.get("Content-Type", ""), exc.read()
    except URLError as exc:
        return 0, "", str(exc).encode()


manifest_texts: list[str] = []
for path in CANDIDATES:
    status, content_type, raw = fetch(path)
    print("FILE", path, "STATUS", status, "TYPE", content_type, "BYTES", len(raw))
    text = raw.decode("utf-8", errors="ignore")
    if len(raw) <= 500_000:
        print("HEAD", " ".join(text[:2500].split()))
    if "manifest" in path.lower() or path.endswith(".js"):
        manifest_texts.append(text)

all_text = "\n".join(manifest_texts)

asset_candidates = sorted(set(re.findall(r"(?:assets/)?[A-Za-z0-9_./@-]+\.(?:json|yaml|yml|env|txt|config)", all_text)))
print("ASSET_CANDIDATES")
for item in asset_candidates[:1000]:
    print(item)

bundle_status, _, bundle_raw = fetch("main.dart.js")
bundle = bundle_raw.decode("utf-8", errors="ignore")
print("BUNDLE_STATUS", bundle_status, "BYTES", len(bundle_raw))

domains = sorted(set(re.findall(r"(?<![A-Za-z0-9_-])(?:[A-Za-z0-9-]+\.)+(?:go\.th|co\.th|or\.th|com|net|org|io|app|dev|th)(?::\d+)?", bundle, flags=re.I)))
print("DOMAIN_LITERALS")
for domain in domains[:1000]:
    print(domain)

for keyword in (
    "baseUrl", "baseURL", "apiUrl", "apiURL", "gateway", "environment", "production",
    "apiKey", "M00000", "bill-payment-nonmember", "nonmember/transaction-payment",
    "AuthGrantType", "Basic [GUEST]", "grantType", "customerType", "licensePlateGroupType",
):
    positions = [m.start() for m in re.finditer(re.escape(keyword), bundle, flags=re.I)]
    print("KEYWORD", keyword, "COUNT", len(positions))
    for pos in positions[:12]:
        start = max(0, pos - 450)
        end = min(len(bundle), pos + len(keyword) + 650)
        context = " ".join(bundle[start:end].replace("\x00", " ").split())
        print("CONTEXT", context[:1400])

for asset in asset_candidates:
    if not any(token in asset.lower() for token in ("config", "env", "setting", "flavor", "prod", "endpoint", "api")):
        continue
    status, content_type, raw = fetch(asset.removeprefix("assets/") if asset.startswith("assets/assets/") else asset)
    print("CONFIG_FETCH", asset, "STATUS", status, "TYPE", content_type, "BYTES", len(raw))
    print("CONFIG_HEAD", " ".join(raw.decode("utf-8", errors="ignore")[:5000].split()))

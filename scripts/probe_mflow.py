from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

TARGETS = (
    "https://mflowthai.com/",
    "https://mflowthai.com/mflowspf/",
)
BASE = "https://mflowthai.com/mflowspf/"
DIAG = Path("mflow-diagnostics")
DIAG.mkdir(exist_ok=True)


def safe_url(url: str) -> str:
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}{p.path}"


def fetch_bytes(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=120) as response:
        return response.read()


def compact(value: str, limit: int = 340) -> str:
    return " ".join(value.replace("\x00", " ").split())[:limit]


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(
        locale="th-TH",
        timezone_id="Asia/Bangkok",
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/152.0.0.0 Safari/537.36"
        ),
    )

    for index, target in enumerate(TARGETS):
        print("\n=== TARGET", target, "===")
        page = context.new_page()
        seen: set[tuple[str, str]] = set()

        def on_request(req):
            if req.resource_type in {"document", "xhr", "fetch", "script"}:
                key = (req.method, safe_url(req.url))
                if key not in seen:
                    seen.add(key)
                    print("REQUEST", req.resource_type, req.method, safe_url(req.url))

        page.on("request", on_request)
        try:
            response = page.goto(target, wait_until="domcontentloaded", timeout=60000)
            print("MAIN_STATUS", response.status if response else None)
            try:
                page.wait_for_load_state("networkidle", timeout=20000)
            except PlaywrightTimeoutError:
                print("NETWORKIDLE_TIMEOUT")
            page.wait_for_timeout(8000)
            print("TITLE", page.title())
            print("FINAL_URL", safe_url(page.url))
            body = page.locator("body").inner_text(timeout=10000)
            print("BODY_HEAD", " | ".join(body.splitlines()[:100]))
            page.screenshot(path=str(DIAG / f"mflow-spa-{index}.png"), full_page=True)
        except Exception as exc:
            print("PROBE_ERROR", type(exc).__name__, str(exc))
        finally:
            page.close()

    browser.close()

print("\n=== DOWNLOAD PUBLIC SPA ASSETS ===")
assets = {
    "index.html": BASE,
    "flutter_bootstrap.js": urljoin(BASE, "flutter_bootstrap.js"),
    "flutter.js": urljoin(BASE, "flutter.js"),
    "main.dart.js": urljoin(BASE, "main.dart.js"),
    "AssetManifest.bin.json": urljoin(BASE, "assets/AssetManifest.bin.json"),
    "FontManifest.json": urljoin(BASE, "assets/FontManifest.json"),
    "manifest.json": urljoin(BASE, "manifest.json"),
    "flutter_service_worker.js": urljoin(BASE, "flutter_service_worker.js"),
}
for filename, url in assets.items():
    try:
        data = fetch_bytes(url)
        (DIAG / filename).write_bytes(data)
        print("DOWNLOADED", filename, len(data), url)
    except Exception as exc:
        print("DOWNLOAD_ERROR", filename, type(exc).__name__, str(exc))

bundle_path = DIAG / "main.dart.js"
if bundle_path.exists():
    text = bundle_path.read_text(encoding="utf-8", errors="ignore")
    print("BUNDLE_BYTES", bundle_path.stat().st_size)

    urls = sorted(set(re.findall(r"https?://[^\s\"'<>\\]+", text)))
    (DIAG / "absolute_urls.txt").write_text("\n".join(urls), encoding="utf-8")

    path_pattern = re.compile(r"[\"'](/[^\"'\\\s]{2,220})[\"']")
    interesting_paths = sorted({
        match.group(1)
        for match in path_pattern.finditer(text)
        if any(token in match.group(1).lower() for token in (
            "api", "payment", "invoice", "bill", "vehicle", "license", "plate",
            "province", "toll", "transaction", "guest", "anonymous", "member",
            "unpaid", "search", "fee", "mflow", "auth", "token",
        ))
    })
    (DIAG / "interesting_paths.txt").write_text("\n".join(interesting_paths), encoding="utf-8")

    keywords = (
        "nonmember/transaction-payment", "bill-payment-nonmember", "grantType", "GUEST",
        "apiKey", "DeviceId", "M00000", "licensePlate", "plate1", "plate2",
        "provinceCode", "baseUrl", "apiUrl", "auth/token", "accessToken",
    )
    chunks: list[str] = []
    for keyword in keywords:
        positions = [m.start() for m in re.finditer(re.escape(keyword), text, flags=re.IGNORECASE)]
        chunks.append(f"\n===== {keyword} COUNT {len(positions)} =====")
        for pos in positions[:80]:
            start = max(0, pos - 900)
            end = min(len(text), pos + len(keyword) + 1300)
            chunks.append(compact(text[start:end], 2600))
    (DIAG / "keyword_contexts.txt").write_text("\n".join(chunks), encoding="utf-8")

manifest_path = DIAG / "AssetManifest.bin.json"
if manifest_path.exists():
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        pretty = json.dumps(manifest, ensure_ascii=False, indent=2)
        (DIAG / "AssetManifest.pretty.json").write_text(pretty, encoding="utf-8")
        candidates = []
        for key in manifest:
            lowered = key.lower()
            if any(token in lowered for token in ("config", "env", "setting", "constant", "json", "yaml", "yml")):
                candidates.append(key)
        (DIAG / "candidate_assets.txt").write_text("\n".join(candidates), encoding="utf-8")
        for asset in candidates[:100]:
            try:
                data = fetch_bytes(urljoin(BASE, "assets/" + asset.removeprefix("assets/")))
                safe_name = asset.replace("/", "__")
                (DIAG / ("asset__" + safe_name)).write_bytes(data)
            except Exception as exc:
                print("ASSET_ERROR", asset, type(exc).__name__, str(exc))
    except Exception as exc:
        print("MANIFEST_PARSE_ERROR", type(exc).__name__, str(exc))

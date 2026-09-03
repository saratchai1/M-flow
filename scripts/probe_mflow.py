from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

TARGETS = (
    "https://mflowthai.com/",
    "https://mflowthai.com/mflowspf/",
)
BUNDLE = "https://mflowthai.com/mflowspf/main.dart.js"


def safe_url(url: str) -> str:
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}{p.path}"


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

    for target in TARGETS:
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

            print("ANCHORS")
            anchors = page.locator("a")
            for i in range(min(anchors.count(), 100)):
                el = anchors.nth(i)
                text = " ".join((el.inner_text() or "").split())[:160]
                href = el.get_attribute("href")
                if text or href:
                    print(i, text, urljoin(page.url, href) if href else None)

            print("INPUTS")
            inputs = page.locator("input")
            for i in range(min(inputs.count(), 100)):
                el = inputs.nth(i)
                print(i, {
                    "type": el.get_attribute("type"),
                    "name": el.get_attribute("name"),
                    "id": el.get_attribute("id"),
                    "placeholder": el.get_attribute("placeholder"),
                    "aria": el.get_attribute("aria-label"),
                })

            print("BUTTONS")
            buttons = page.locator("button")
            for i in range(min(buttons.count(), 100)):
                el = buttons.nth(i)
                text = " ".join((el.inner_text() or "").split())[:160]
                print(i, text, {
                    "type": el.get_attribute("type"),
                    "id": el.get_attribute("id"),
                    "aria": el.get_attribute("aria-label"),
                })

            page.screenshot(path="mflow-spa.png", full_page=True)
        except Exception as exc:
            print("PROBE_ERROR", type(exc).__name__, str(exc))
        finally:
            page.close()

    browser.close()

print("\n=== FLUTTER BUNDLE ANALYSIS ===")
request = Request(BUNDLE, headers={"User-Agent": "Mozilla/5.0"})
with urlopen(request, timeout=90) as response:
    raw = response.read()
text = raw.decode("utf-8", errors="ignore")
print("BUNDLE_BYTES", len(raw))

urls = sorted(set(re.findall(r"https?://[^\s\"'<>\\]+", text)))
print("ABSOLUTE_URLS")
for value in urls[:300]:
    print(compact(value, 500))

path_pattern = re.compile(r"[\"'](/[^\"'\\\s]{2,180})[\"']")
interesting_paths = sorted({
    match.group(1)
    for match in path_pattern.finditer(text)
    if any(token in match.group(1).lower() for token in (
        "api", "payment", "invoice", "bill", "vehicle", "license", "plate",
        "province", "toll", "transaction", "guest", "anonymous", "member",
        "unpaid", "search", "fee", "mflow",
    ))
})
print("INTERESTING_PATHS")
for value in interesting_paths[:500]:
    print(compact(value, 500))

keywords = (
    "unuserpayment", "checkunbilled", "licensePlate", "license_plate", "plateNumber",
    "vehicleRegistration", "province", "outstanding", "unpaid", "invoice", "payment",
    "transaction", "anonymous", "guest", "nonmember", "non-member", "ทะเบียน",
    "จังหวัด", "ชำระ", "ยอดค้าง",
)
for keyword in keywords:
    positions = [m.start() for m in re.finditer(re.escape(keyword), text, flags=re.IGNORECASE)]
    print("KEYWORD", keyword, "COUNT", len(positions))
    for pos in positions[:8]:
        start = max(0, pos - 220)
        end = min(len(text), pos + len(keyword) + 260)
        print("CONTEXT", compact(text[start:end], 700))

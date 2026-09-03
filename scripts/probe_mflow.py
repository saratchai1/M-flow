from __future__ import annotations

from urllib.parse import urljoin, urlparse

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

TARGETS = (
    "https://mflowthai.com/",
    "https://mflowthai.com/mflowspf/",
)


def safe_url(url: str) -> str:
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}{p.path}"


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

            print("SCRIPTS")
            scripts = page.locator("script[src]")
            for i in range(min(scripts.count(), 100)):
                src = scripts.nth(i).get_attribute("src")
                if src:
                    print(urljoin(page.url, src))
        except Exception as exc:
            print("PROBE_ERROR", type(exc).__name__, str(exc))
        finally:
            page.close()

    browser.close()

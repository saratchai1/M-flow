from playwright.sync_api import sync_playwright
from urllib.parse import urlparse

TARGET = "https://mflowthai.com/mflow/checkunbilled"


def safe_url(url: str) -> str:
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}{p.path}"


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(locale="th-TH", timezone_id="Asia/Bangkok")
    seen = set()

    def on_request(req):
        if req.resource_type in {"xhr", "fetch"}:
            u = safe_url(req.url)
            if u not in seen:
                seen.add(u)
                print("XHR", req.method, u)

    page.on("request", on_request)
    page.goto(TARGET, wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(2500)
    print("TITLE", page.title())
    print("FINAL_URL", safe_url(page.url))
    print("BODY_HEAD", " | ".join(page.locator("body").inner_text().splitlines()[:35]))

    print("INPUTS")
    for i in range(page.locator("input").count()):
        el = page.locator("input").nth(i)
        print(i, {
            "type": el.get_attribute("type"),
            "name": el.get_attribute("name"),
            "id": el.get_attribute("id"),
            "placeholder": el.get_attribute("placeholder"),
            "aria": el.get_attribute("aria-label"),
        })

    print("SELECTS")
    for i in range(page.locator("select").count()):
        el = page.locator("select").nth(i)
        print(i, {"name": el.get_attribute("name"), "id": el.get_attribute("id")})

    print("BUTTONS")
    for i in range(page.locator("button").count()):
        el = page.locator("button").nth(i)
        txt = " ".join((el.inner_text() or "").split())[:120]
        print(i, txt, {"type": el.get_attribute("type"), "id": el.get_attribute("id")})

    print("SCRIPTS")
    for i in range(page.locator("script[src]").count()):
        src = page.locator("script[src]").nth(i).get_attribute("src")
        if src:
            print(safe_url(page.url if src.startswith("/") else src))

    browser.close()

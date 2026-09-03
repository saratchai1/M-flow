from __future__ import annotations

import json
from playwright.sync_api import sync_playwright

TARGET = "https://mflowthai.com/mflowspf/search"

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True,
        args=["--use-gl=swiftshader", "--enable-webgl", "--ignore-gpu-blocklist"],
    )
    context = browser.new_context(
        viewport={"width": 1440, "height": 1000},
        locale="th-TH",
        timezone_id="Asia/Bangkok",
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36"
        ),
    )
    page = context.new_page()

    def on_request(req):
        if "api2.mflowthai.com" not in req.url:
            return
        headers = dict(req.headers)
        for key in list(headers):
            if key.lower() in {"apikey", "authorization", "cookie"}:
                value = headers[key]
                headers[key] = f"<redacted len={len(value)}>"
        print("REQUEST", req.method, req.url)
        print("HEADERS", json.dumps(headers, ensure_ascii=False, sort_keys=True))
        if req.post_data:
            print("BODY", req.post_data[:5000])

    def on_response(resp):
        if "api2.mflowthai.com" in resp.url:
            print("RESPONSE", resp.status, resp.url)

    page.on("request", on_request)
    page.on("response", on_response)
    page.goto(TARGET, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(25000)
    browser.close()

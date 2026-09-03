from __future__ import annotations

import json
from urllib.parse import urlparse

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

TARGETS = (
    "https://mflowthai.com/mflowspf/#/search",
    "https://mflowthai.com/mflowspf/search",
    "https://mflowthai.com/mflowspf/",
)


def safe_url(url: str) -> str:
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}{p.path}"


with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True,
        args=["--use-gl=swiftshader", "--enable-webgl", "--ignore-gpu-blocklist"],
    )
    context = browser.new_context(
        viewport={"width": 1440, "height": 1200},
        locale="th-TH",
        timezone_id="Asia/Bangkok",
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/152.0.0.0 Safari/537.36"
        ),
    )

    for index, target in enumerate(TARGETS):
        print("\n===", target, "===")
        page = context.new_page()
        requests: list[dict] = []

        def on_request(req):
            if req.resource_type in {"xhr", "fetch"}:
                requests.append({
                    "method": req.method,
                    "url": safe_url(req.url),
                    "post_data": (req.post_data or "")[:1000],
                    "headers": {
                        key: value
                        for key, value in req.headers.items()
                        if key.lower() in {"authorization", "apikey", "api-key", "content-type", "x-api-key"}
                    },
                })

        page.on("request", on_request)
        try:
            response = page.goto(target, wait_until="domcontentloaded", timeout=60000)
            print("STATUS", response.status if response else None, "FINAL", page.url)
            try:
                page.wait_for_load_state("networkidle", timeout=25000)
            except PlaywrightTimeoutError:
                print("NETWORKIDLE_TIMEOUT")
            page.wait_for_timeout(12000)

            summary = page.evaluate(
                """() => {
                  const nodes = [...document.querySelectorAll('*')];
                  const flt = nodes.filter(n => n.tagName.toLowerCase().startsWith('flt-'));
                  return {
                    title: document.title,
                    bodyText: document.body.innerText,
                    tags: [...new Set(nodes.map(n => n.tagName.toLowerCase()))].sort(),
                    flt: flt.slice(0, 300).map(n => ({
                      tag: n.tagName.toLowerCase(),
                      id: n.id || null,
                      role: n.getAttribute('role'),
                      aria: n.getAttribute('aria-label'),
                      text: (n.innerText || '').slice(0, 300),
                      attrs: [...n.attributes].reduce((o,a)=>(o[a.name]=a.value,o),{}),
                      shadow: !!n.shadowRoot,
                    })),
                    htmlHead: document.documentElement.outerHTML.slice(0, 12000),
                  };
                }"""
            )
            print("DOM_SUMMARY", json.dumps(summary, ensure_ascii=False)[:50000])

            placeholders = page.locator("flt-semantics-placeholder")
            print("SEMANTICS_PLACEHOLDERS", placeholders.count())
            for i in range(placeholders.count()):
                item = placeholders.nth(i)
                try:
                    print("PLACEHOLDER", i, item.evaluate("e => e.outerHTML"))
                    item.click(force=True, timeout=5000)
                    print("PLACEHOLDER_CLICKED", i)
                except Exception as exc:
                    print("PLACEHOLDER_CLICK_ERROR", i, type(exc).__name__, str(exc))

            try:
                page.keyboard.press("Tab")
                page.keyboard.press("Enter")
            except Exception as exc:
                print("KEYBOARD_ERROR", type(exc).__name__, str(exc))

            page.wait_for_timeout(5000)

            cdp = context.new_cdp_session(page)
            ax = cdp.send("Accessibility.getFullAXTree")
            printable = []
            for node in ax.get("nodes", []):
                role = (node.get("role") or {}).get("value")
                name = (node.get("name") or {}).get("value")
                value = (node.get("value") or {}).get("value")
                if name or value or role not in {"generic", "none", "RootWebArea", "StaticText", "InlineTextBox"}:
                    printable.append({"role": role, "name": name, "value": value})
            print("AX_TREE", json.dumps(printable[:1000], ensure_ascii=False)[:100000])

            after = page.evaluate(
                """() => [...document.querySelectorAll('flt-semantics, flt-semantics-host, input, button, [role]')]
                  .slice(0,1000).map(n=>({tag:n.tagName.toLowerCase(),role:n.getAttribute('role'),aria:n.getAttribute('aria-label'),text:(n.innerText||'').slice(0,200),value:n.value||null,outer:n.outerHTML.slice(0,500)}))"""
            )
            print("AFTER_SEMANTICS", json.dumps(after, ensure_ascii=False)[:100000])
            print("XHR_FETCH", json.dumps(requests, ensure_ascii=False)[:100000])
            page.screenshot(path=f"mflow-flutter-{index}.png", full_page=True)
        except Exception as exc:
            print("ERROR", type(exc).__name__, str(exc))
        finally:
            page.close()

    browser.close()

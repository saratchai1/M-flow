from __future__ import annotations

import hashlib
import re
from datetime import datetime
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from .config import Settings, Vehicle
from .models import CheckResult, CheckStatus, OutstandingItem

CLEAR_PATTERNS = (
    "ไม่พบรายการ", "ไม่มีรายการ", "ไม่มียอดค้าง", "ไม่พบยอดค้าง",
    "ไม่พบข้อมูลการใช้ทาง", "ไม่พบข้อมูล", "ไม่พบรายการค้างชำระ",
)
UNPAID_PATTERNS = ("ค้างชำระ", "ยอดค้าง", "ยอดที่ต้องชำระ", "รายการค้าง", "รอชำระ")
CAPTCHA_PATTERNS = (
    "captcha", "turnstile", "verify you are human",
    "ยืนยันว่าคุณเป็นมนุษย์", "ยืนยันว่าคุณไม่ใช่หุ่นยนต์",
)
UPSTREAM_ERROR_PATTERNS = ("an error occurred", "currently unavailable", "faithfully yours, nginx")
DATE_RE = re.compile(r"(?<!\d)(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})(?!\d)")
AMOUNT_RE = re.compile(r"(?:ยอด(?:เงิน|ที่ต้องชำระ)?|จำนวนเงิน)?\s*[:=]?\s*(\d{1,4}(?:\.\d{1,2})?)\s*(?:บาท|฿)")


def _parse_date(text: str) -> datetime | None:
    match = DATE_RE.search(text)
    if not match:
        return None
    day, month, year = (int(part) for part in match.groups())
    if year < 100:
        year += 2000
    if year > 2400:
        year -= 543
    try:
        return datetime(year, month, day)
    except ValueError:
        return None


def _parse_amount(text: str) -> float | None:
    values = []
    for match in AMOUNT_RE.finditer(text):
        try:
            values.append(float(match.group(1)))
        except ValueError:
            continue
    plausible = [value for value in values if 1 <= value <= 5000]
    return plausible[0] if plausible else None


def _new_text(before: str, after: str) -> str:
    before_lines = {" ".join(line.split()) for line in before.splitlines() if line.strip()}
    after_lines = [" ".join(line.split()) for line in after.splitlines() if line.strip()]
    return "\n".join(line for line in after_lines if line not in before_lines)


def _extract_items(normalized: str, source_url: str) -> list[OutstandingItem]:
    date_matches = list(DATE_RE.finditer(normalized))
    if not date_matches:
        amount = _parse_amount(normalized)
        return [OutstandingItem(None, amount, source_url, normalized[:500])] if amount is not None else []

    items: list[OutstandingItem] = []
    for index, match in enumerate(date_matches):
        start = match.start()
        end = date_matches[index + 1].start() if index + 1 < len(date_matches) else min(len(normalized), start + 600)
        segment = normalized[start:end]
        date = _parse_date(match.group(0))
        amount = _parse_amount(segment)
        if amount is not None or any(pattern in segment for pattern in UNPAID_PATTERNS):
            items.append(OutstandingItem(date, amount, source_url, segment[:500]))
    return items


def parse_result_text(text: str, source_url: str) -> CheckResult:
    normalized = " ".join(text.split())
    lowered = normalized.lower()
    if any(pattern in lowered for pattern in UPSTREAM_ERROR_PATTERNS):
        return CheckResult(CheckStatus.CHECK_FAILED, detail="M-Flow upstream returned an error page.", source_url=source_url)
    if any(pattern in lowered for pattern in CAPTCHA_PATTERNS):
        return CheckResult(CheckStatus.CHECK_FAILED, detail="Human verification/CAPTCHA detected. Manual check required.", source_url=source_url)
    if any(pattern in normalized for pattern in CLEAR_PATTERNS):
        return CheckResult(CheckStatus.CLEAR, detail="M-Flow explicitly reported no matching/outstanding item.", source_url=source_url)
    if any(pattern in normalized for pattern in UNPAID_PATTERNS):
        items = _extract_items(normalized, source_url)
        if not items:
            return CheckResult(CheckStatus.REVIEW_REQUIRED, detail="Outstanding-payment wording found, but transaction details could not be parsed safely.", source_url=source_url)
        return CheckResult(CheckStatus.UNPAID, items=items, detail=f"{len(items)} outstanding item(s) detected from M-Flow result.", source_url=source_url)
    return CheckResult(CheckStatus.REVIEW_REQUIRED, detail="M-Flow page loaded, but its result could not be classified safely.", source_url=source_url)


class MFlowBrowserChecker:
    """Conservative browser automation. It never bypasses CAPTCHA/human verification."""

    def __init__(self, settings: Settings):
        self.settings = settings
        settings.artifact_dir.mkdir(parents=True, exist_ok=True)

    def _artifact_prefix(self, vehicle: Vehicle) -> Path:
        digest = hashlib.sha256(f"{vehicle.plate_number}|{vehicle.province}".encode()).hexdigest()[:10]
        return self.settings.artifact_dir / f"vehicle-{digest}"

    @staticmethod
    def _first_visible(locator):
        for i in range(locator.count()):
            candidate = locator.nth(i)
            if candidate.is_visible():
                return candidate
        return None

    def _fill_plate(self, page, vehicle: Vehicle) -> None:
        candidates = [
            page.get_by_label(re.compile("ทะเบียน|เลขทะเบียน|หมายเลขทะเบียน", re.I)),
            page.locator('input[placeholder*="ทะเบียน"]'),
            page.locator('input[name*="plate" i], input[id*="plate" i], input[name*="license" i], input[id*="license" i]'),
        ]
        for locator in candidates:
            target = self._first_visible(locator)
            if target:
                target.fill(vehicle.plate_number)
                return

        text_inputs = page.locator('input:not([type]), input[type="text"], input[type="search"]')
        visible = [text_inputs.nth(i) for i in range(text_inputs.count()) if text_inputs.nth(i).is_visible()]
        if len(visible) == 1:
            visible[0].fill(vehicle.plate_number)
            return
        raise RuntimeError("Could not locate the vehicle plate input")

    def _fill_province(self, page, vehicle: Vehicle) -> bool:
        """Best-effort because some M-Flow non-member screens only ask for plate number."""
        selects = page.locator("select")
        for i in range(selects.count()):
            select = selects.nth(i)
            if not select.is_visible():
                continue
            try:
                select.select_option(label=vehicle.province)
                return True
            except Exception:
                pass

        combos = [
            page.get_by_label(re.compile("จังหวัด", re.I)),
            page.locator('input[placeholder*="จังหวัด"]'),
            page.locator('[role="combobox"]'),
            page.locator('mat-select'),
        ]
        for locator in combos:
            target = self._first_visible(locator)
            if not target:
                continue
            try:
                target.click()
                option = page.get_by_text(vehicle.province, exact=True)
                visible_option = self._first_visible(option)
                if visible_option:
                    visible_option.click()
                    return True
                if target.evaluate("el => el.tagName === 'INPUT'"):
                    target.fill(vehicle.province)
                    page.keyboard.press("ArrowDown")
                    page.keyboard.press("Enter")
                    return True
            except Exception:
                continue
        return False

    def _submit(self, page) -> None:
        buttons = [
            page.get_by_role("button", name=re.compile("ค้นหา|ตรวจสอบ|เช็ก|เช็ค|ตกลง|ยืนยัน", re.I)),
            page.locator('button[type="submit"], input[type="submit"]'),
        ]
        for locator in buttons:
            target = self._first_visible(locator)
            if target:
                target.click()
                return
        raise RuntimeError("Could not locate the search/submit button")

    def check(self, vehicle: Vehicle) -> CheckResult:
        prefix = self._artifact_prefix(vehicle)
        timeout_ms = self.settings.timeout_seconds * 1000
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=self.settings.headless)
                context = browser.new_context(locale="th-TH", timezone_id="Asia/Bangkok")
                page = context.new_page()
                page.set_default_timeout(timeout_ms)
                page.goto(self.settings.mflow_url, wait_until="domcontentloaded", timeout=timeout_ms)
                page.wait_for_timeout(900)
                initial_text = page.locator("body").inner_text(timeout=timeout_ms)
                initial_lower = initial_text.lower()

                if any(pattern in initial_lower for pattern in UPSTREAM_ERROR_PATTERNS):
                    browser.close()
                    return CheckResult(CheckStatus.CHECK_FAILED, detail="M-Flow is unavailable from this network (upstream nginx error).", source_url=page.url)
                if any(pattern in initial_lower for pattern in CAPTCHA_PATTERNS):
                    page.screenshot(path=str(prefix) + "-captcha.png", full_page=True)
                    source_url = page.url
                    browser.close()
                    return CheckResult(CheckStatus.CHECK_FAILED, detail="Human verification/CAPTCHA detected before search.", source_url=source_url)

                self._fill_plate(page, vehicle)
                self._fill_province(page, vehicle)
                self._submit(page)
                page.wait_for_timeout(2200)
                try:
                    page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 8000))
                except PlaywrightTimeoutError:
                    pass

                text = page.locator("body").inner_text(timeout=timeout_ms)
                delta = _new_text(initial_text, text)
                result = parse_result_text(delta or text, page.url)
                if result.status in {CheckStatus.REVIEW_REQUIRED, CheckStatus.CHECK_FAILED}:
                    page.screenshot(path=str(prefix) + "-review.png", full_page=True)
                    Path(str(prefix) + "-review.txt").write_text(text[:20000], encoding="utf-8")
                browser.close()
                return result
        except PlaywrightTimeoutError as exc:
            return CheckResult(CheckStatus.CHECK_FAILED, detail=f"Browser timeout: {exc}", source_url=self.settings.mflow_url)
        except Exception as exc:
            return CheckResult(CheckStatus.CHECK_FAILED, detail=f"Browser automation failed: {type(exc).__name__}: {exc}", source_url=self.settings.mflow_url)

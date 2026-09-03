from mflow_watchdog.checker import parse_result_text
from mflow_watchdog.models import CheckStatus


def test_clear_result():
    result = parse_result_text("ไม่พบรายการค้างชำระสำหรับรถคันนี้", "https://example.test")
    assert result.status == CheckStatus.CLEAR


def test_unpaid_result_parses_thai_buddhist_date_and_amount():
    result = parse_result_text(
        "สถานะ ค้างชำระ วันที่ 02/09/2569 ยอดที่ต้องชำระ 30 บาท",
        "https://example.test/pay",
    )
    assert result.status == CheckStatus.UNPAID
    assert result.items[0].transaction_date.year == 2026
    assert result.items[0].amount == 30.0


def test_captcha_is_failure_not_clear():
    result = parse_result_text("Please complete Turnstile CAPTCHA", "https://example.test")
    assert result.status == CheckStatus.CHECK_FAILED


def test_multiple_unpaid_items_are_split():
    result = parse_result_text(
        "ค้างชำระ 01/09/2569 ยอด 30 บาท 02/09/2569 ยอด 30 บาท",
        "https://example.test/pay",
    )
    assert result.status == CheckStatus.UNPAID
    assert len(result.items) == 2
    assert [item.transaction_date.day for item in result.items] == [1, 2]

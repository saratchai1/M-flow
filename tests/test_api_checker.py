from datetime import datetime

from mflow_watchdog.api_checker import (
    normalize_province,
    parse_mflow_datetime,
    parse_public_env,
    parse_transaction_response,
    split_plate_number,
)
from mflow_watchdog.models import CheckStatus


def test_split_plate():
    assert split_plate_number("7ขก 1181") == ("7ขก", "1181")
    assert split_plate_number("1กก1234") == ("1กก", "1234")
    assert split_plate_number("กก-42") == ("กก", "42")


def test_province_aliases():
    assert normalize_province("กทม.") == "กรุงเทพมหานคร"
    assert normalize_province("จังหวัด กระบี่") == "กระบี่"


def test_env_parser():
    values = parse_public_env(
        "API_KEY='abc'\n"
        'BILLING_SERVICE_BASE_URL="https://api2.mflowthai.com/billing-service/api"\n'
    )
    assert values["API_KEY"] == "abc"


def test_empty_success_is_clear():
    result = parse_transaction_response(
        {"status": True, "message": "ok", "plate": []}
    )
    assert result.status == CheckStatus.CLEAR


def test_nonempty_response_is_unpaid():
    result = parse_transaction_response(
        {
            "status": True,
            "message": "ok",
            "plate": [
                {
                    "totalAmount": 30,
                    "dueDate": "2026-09-07T23:59:59+07:00",
                    "plate1": "7ขก",
                    "plate2": "1181",
                    "invoice": [
                        {
                            "transactionId": "tx-1",
                            "transactionDatetime": "2026-09-03T08:30:00+07:00",
                            "feeAmount": 30,
                            "totalAmount": 30,
                        }
                    ],
                }
            ],
        }
    )
    assert result.status == CheckStatus.UNPAID
    assert result.items[0].amount == 30
    assert isinstance(result.items[0].transaction_date, datetime)
    assert result.items[0].due_date is not None


def test_false_status_is_review():
    result = parse_transaction_response({"status": False, "message": "invalid"})
    assert result.status == CheckStatus.REVIEW_REQUIRED


def test_parse_epoch_and_iso():
    assert parse_mflow_datetime("2026-09-03T08:30:00+07:00") is not None
    assert parse_mflow_datetime(1788400000000) is not None

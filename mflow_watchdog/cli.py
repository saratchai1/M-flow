from __future__ import annotations

import argparse
import json
import logging
import os
import sys

from .api_checker import MFlowApiChecker
from .config import Settings
from .dashboard import serve
from .db import Store
from .mock_checker import MockMFlowChecker
from .notifier import MultiNotifier, Notifier, build_notifier
from .service import WatchdogService


class ConsoleNotifier(Notifier):
    """Safe notification sink used only in mock mode."""

    name = "console"

    def send(self, message: str) -> None:
        print("\n--- MOCK NOTIFICATION ---")
        print(message)
        print("--- END MOCK NOTIFICATION ---\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mflow-watchdog")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="Check all configured vehicles once")
    dashboard = sub.add_parser("dashboard", help="Serve the admin-friendly web application")
    dashboard.add_argument("--host", default="127.0.0.1")
    dashboard.add_argument("--port", type=int, default=8080)
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = build_parser().parse_args(argv)
    settings = Settings.from_env()

    if args.command == "dashboard":
        serve(settings, host=args.host, port=args.port)
        return 0

    store = Store(settings.database_path)
    try:
        mock_mode = os.getenv("MFLOW_MOCK_MODE", "").strip().lower()
        if mock_mode:
            checker = MockMFlowChecker(mock_mode)
            notifier = MultiNotifier([ConsoleNotifier()])
            logging.info(
                "Running in MFLOW_MOCK_MODE=%s; no M-Flow or notification API calls will be made",
                mock_mode,
            )
        else:
            checker = MFlowApiChecker(settings)
            notifier = build_notifier(settings)

        counts = WatchdogService(settings, store, checker, notifier).run()
        print(json.dumps(counts, ensure_ascii=False))
        return 2 if counts["CHECK_FAILED"] or counts["REVIEW_REQUIRED"] else 0
    finally:
        store.close()


if __name__ == "__main__":
    sys.exit(main())

from __future__ import annotations

import argparse
import json
import logging
import sys

from .checker import MFlowBrowserChecker
from .config import Settings
from .dashboard import serve
from .db import Store
from .notifier import build_notifier
from .service import WatchdogService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mflow-watchdog")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="Check all configured vehicles once")
    dashboard = sub.add_parser("dashboard", help="Serve local read-only dashboard")
    dashboard.add_argument("--host", default="127.0.0.1")
    dashboard.add_argument("--port", type=int, default=8080)
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = build_parser().parse_args(argv)
    settings = Settings.from_env()
    store = Store(settings.database_path)
    try:
        if args.command == "dashboard":
            serve(store, host=args.host, port=args.port)
            return 0
        notifier = build_notifier(settings)
        checker = MFlowBrowserChecker(settings)
        counts = WatchdogService(settings, store, checker, notifier).run()
        print(json.dumps(counts, ensure_ascii=False))
        return 2 if counts["CHECK_FAILED"] or counts["REVIEW_REQUIRED"] else 0
    finally:
        store.close()


if __name__ == "__main__":
    sys.exit(main())

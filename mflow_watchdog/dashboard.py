from __future__ import annotations

import html
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .db import Store


def render_dashboard(store: Store) -> str:
    transactions = store.list_transactions()
    checks = store.latest_checks()
    unpaid = sum(1 for row in transactions if row["status"] == "UNPAID")
    paid = sum(1 for row in transactions if row["status"] == "PAID")
    failed = sum(1 for row in checks if row["status"] in {"CHECK_FAILED", "REVIEW_REQUIRED"})

    tx_rows = []
    for row in transactions:
        amount = "-" if row["amount"] is None else f"{row['amount']:.2f}"
        tx_rows.append(
            "<tr>"
            f"<td>{html.escape(row['plate_number'])}</td>"
            f"<td>{html.escape(row['province'])}</td>"
            f"<td>{html.escape(row['transaction_date'] or '-')}</td>"
            f"<td>{amount}</td>"
            f"<td>{html.escape(row['status'])}</td>"
            f"<td>{html.escape(row['deadline'] or '-')}</td>"
            "</tr>"
        )

    check_rows = []
    for row in checks:
        check_rows.append(
            "<tr>"
            f"<td>{html.escape(row['plate_number'])}</td>"
            f"<td>{html.escape(row['province'])}</td>"
            f"<td>{html.escape(row['status'])}</td>"
            f"<td>{html.escape(row['checked_at'])}</td>"
            f"<td>{html.escape(row['detail'][:180])}</td>"
            "</tr>"
        )

    return f"""<!doctype html>
<html lang="th"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>M-Flow Fleet Watchdog</title>
<style>
body{{font-family:system-ui,-apple-system,sans-serif;margin:0;background:#f5f7fb;color:#172033}}
main{{max-width:1100px;margin:32px auto;padding:0 18px}}
.cards{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:18px 0}}
.card,section{{background:white;border:1px solid #dde3ee;border-radius:14px;padding:18px}}
.big{{font-size:32px;font-weight:700}} table{{width:100%;border-collapse:collapse}}
th,td{{padding:10px;border-bottom:1px solid #edf0f5;text-align:left;font-size:14px}}
small{{color:#687386}} @media(max-width:700px){{.cards{{grid-template-columns:1fr}} table{{display:block;overflow-x:auto}}}}
</style></head><body><main>
<h1>M-Flow Fleet Watchdog</h1><small>Generated {datetime.now().isoformat(timespec='seconds')}</small>
<div class="cards"><div class="card"><div class="big">{unpaid}</div>Outstanding</div><div class="card"><div class="big">{paid}</div>Resolved/Paid</div><div class="card"><div class="big">{failed}</div>Checker attention</div></div>
<section><h2>Transactions</h2><table><thead><tr><th>Plate</th><th>Province</th><th>Date</th><th>Amount</th><th>Status</th><th>Internal deadline</th></tr></thead><tbody>{''.join(tx_rows) or '<tr><td colspan="6">No transactions yet</td></tr>'}</tbody></table></section>
<br><section><h2>Latest checks</h2><table><thead><tr><th>Plate</th><th>Province</th><th>Status</th><th>Checked</th><th>Detail</th></tr></thead><tbody>{''.join(check_rows) or '<tr><td colspan="5">No checks yet</td></tr>'}</tbody></table></section>
</main></body></html>"""


def serve(store: Store, host: str = "127.0.0.1", port: int = 8080) -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            if self.path not in {"/", "/index.html"}:
                self.send_response(404)
                self.end_headers()
                return
            body = render_dashboard(store).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt, *args):
            return

    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Dashboard: http://{host}:{port}")
    server.serve_forever()

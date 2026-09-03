#!/bin/bash
set -euo pipefail

APP_DIR="$HOME/.mflow-live"
TMP_DIR="$(mktemp -d)"
ZIP_URL="https://github.com/saratchai1/M-flow/archive/refs/heads/main.zip"
WEB_URL="https://mflow-admin-demo.vercel.app"

cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

printf '\n==========================================\n'
printf ' M-Flow LIVE Agent — Mac installer\n'
printf '==========================================\n\n'

PY=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1; then
    if "$candidate" - <<'PYTEST' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
PYTEST
    then
      PY="$candidate"
      break
    fi
  fi
done

if [ -z "$PY" ]; then
  echo "ไม่พบ Python 3.11+"
  echo "ติดตั้ง Python ก่อนจาก https://www.python.org/downloads/ แล้วรันคำสั่งเดิมอีกครั้ง"
  exit 1
fi

echo "[1/4] ดาวน์โหลด M-Flow Agent ล่าสุด..."
curl -LfsS "$ZIP_URL" -o "$TMP_DIR/mflow.zip"
unzip -q "$TMP_DIR/mflow.zip" -d "$TMP_DIR"
rm -rf "$APP_DIR"
mkdir -p "$APP_DIR"
cp -R "$TMP_DIR/M-flow-main/." "$APP_DIR/"

echo "[2/4] เตรียม Python environment..."
"$PY" -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/python" -m pip install --upgrade pip >/dev/null
"$APP_DIR/.venv/bin/pip" install -e "$APP_DIR" >/dev/null

echo "[3/4] ติดตั้ง Chromium สำหรับตรวจ M-Flow..."
"$APP_DIR/.venv/bin/python" -m playwright install chromium >/dev/null

echo "[4/4] เปิด LIVE Agent และหน้าเว็บ..."
export MFLOW_URL="https://mflowthai.com/mflow/unuserpayment"
export MFLOW_HEADLESS="true"
open "$WEB_URL" >/dev/null 2>&1 || true

printf '\nพร้อมแล้ว — อย่าปิด Terminal หน้าต่างนี้ระหว่างใช้งาน\n'
printf 'บนเว็บควรเปลี่ยนเป็น: LIVE AGENT ONLINE\n\n'

exec "$APP_DIR/.venv/bin/python" -m mflow_watchdog.local_agent

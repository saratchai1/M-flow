# M-Flow Fleet Watchdog

ระบบ watchdog สำหรับรถหลายคัน: ตรวจ M-Flow ด้วย Playwright, เก็บ state ใน SQLite, แจ้งเตือนฝ่ายธุรการ และ fail-safe เมื่อหน้าเว็บตรวจไม่ได้

> v0.1 MVP: browser checker ใช้ heuristic selectors เพราะไม่ได้พึ่ง public API contract ของ M-Flow จึงควร Run workflow แบบ manual ครั้งแรกและตรวจ diagnostics ก่อนถือว่า production-ready

## Features

- รถจริงเก็บใน `VEHICLES_JSON` GitHub Secret ไม่ลง public repo
- สถานะ `CLEAR`, `UNPAID`, `REVIEW_REQUIRED`, `CHECK_FAILED`
- วิเคราะห์เฉพาะข้อความใหม่หลัง submit เพื่อลด false positive จากหัวข้อ/เมนูบนหน้า
- รองรับหลายรายการค้างต่อรถหนึ่งคัน
- SQLite state + deduplication
- internal safety deadline ค่าเริ่มต้น 48 ชั่วโมง (เป็น SLA ภายใน ไม่ใช่ legal deadline)
- LINE Messaging API, Telegram, Slack
- local dashboard
- Schedule 08:00 / 12:00 / 16:00 / 20:00 เวลาไทย
- ถ้าเจอ human verification หรือหน้าเว็บเปลี่ยน ระบบไม่ถือว่า CLEAR
- diagnostic screenshot/text ใช้ชื่อไฟล์ที่ hash ทะเบียน

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .
playwright install chromium
cp vehicles.example.json vehicles.json
```

แก้ `vehicles.json` แล้วรัน:

```bash
python -m mflow_watchdog.cli check
```

Dashboard:

```bash
python -m mflow_watchdog.cli dashboard --port 8080
```

เปิด `http://127.0.0.1:8080`

## GitHub Actions setup

สร้าง Repository Secret `VEHICLES_JSON` เป็น JSON array เช่น:

```json
[{"plate_number":"กก1234","province":"กรุงเทพมหานคร","driver_name":"Admin","active":true}]
```

เลือก notification อย่างน้อยหนึ่งช่องทาง:

### LINE Messaging API

- `LINE_CHANNEL_ACCESS_TOKEN`
- `LINE_TO` (userId/groupId/roomId ที่ bot push message ได้)

### Telegram

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

### Slack

- `SLACK_WEBHOOK_URL`

จากนั้นไป Actions → **M-Flow Fleet Watchdog** → **Run workflow** เพื่อทดสอบก่อน schedule รอบจริง

## Fail-safe

- human verification/anti-bot challenge → `CHECK_FAILED`
- หา plate/province/submit control ไม่เจอ → `CHECK_FAILED`
- หน้าโหลดได้แต่ผลไม่ชัดเจน → `REVIEW_REQUIRED`
- รายการเก่าจะเป็น `PAID` ต่อเมื่อรอบตรวจได้ `CLEAR` อย่างชัดเจน
- ระบบไม่พยายามหลบ human verification อัตโนมัติ

## Configuration

```text
MFLOW_URL=https://mflowthai.com/mflow/checkunbilled
MFLOW_SAFETY_DEADLINE_HOURS=48
MFLOW_RENOTIFY_AFTER_HOURS=24
MFLOW_URGENT_BEFORE_HOURS=12
MFLOW_FAILURE_RENOTIFY_HOURS=8
```

`MFLOW_SAFETY_DEADLINE_HOURS` เป็นเป้าหมายภายในบริษัทเพื่อให้จ่ายเร็ว ไม่ได้ยืนยันว่าทุกเส้นทางของ M-Flow มีกำหนดชำระเท่ากัน

## Tests

```bash
pip install -e '.[dev]'
pytest -q
```

Local test suite ปัจจุบัน: 5 tests ครอบคลุม clear/unpaid, พ.ศ.→ค.ศ., หลายรายการ, human-verification failure และ SQLite lifecycle

## ข้อจำกัด

หน้า M-Flow สามารถเปลี่ยน DOM/ข้อความได้โดยไม่แจ้งล่วงหน้า ดังนั้นหลัง commit นี้สิ่งสำคัญที่สุดคือใส่ทะเบียนทดสอบผ่าน Secret แล้วรัน workflow จริงหนึ่งครั้งเพื่อดูว่า selectors ตรงกับ production page หรือไม่ หากไม่ตรง workflow จะ fail-safe พร้อม diagnostics แทนการรายงานว่าไม่มีหนี้

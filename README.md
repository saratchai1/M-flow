# M-Flow Fleet Watchdog

ระบบ watchdog + เว็บแอปสำหรับฝ่ายธุรการ: ตรวจรถหลายคัน, เก็บสถานะใน SQLite, แจ้งเตือน และแสดงรถที่ต้องจัดการในหน้าเดียว

> v0.1 MVP: browser checker ใช้ heuristic selectors เพราะไม่ได้พึ่ง public API contract ของ M-Flow จึงควรทดสอบหน้า production ก่อนถือว่า live-ready

## หน้าเว็บสำหรับแอดมิน

หน้าเว็บออกแบบให้ผู้ใช้ไม่ต้องเข้า GitHub Actions หรือ command line ระหว่างใช้งานประจำ:

- การ์ดสรุป **ต้องจัดการด่วน / มียอดค้าง / ระบบเช็กไม่ได้ / ปกติ**
- ตารางรถ 10 คัน พร้อมผู้ใช้รถ ยอดค้าง deadline และเวลาที่ตรวจล่าสุด
- ค้นหาทะเบียน/คนขับ/จังหวัด
- กรองเฉพาะรถที่ต้องจัดการ
- ปุ่ม **ตรวจสอบตอนนี้** สั่ง backend เช็กรถทั้งหมด
- หน้าเว็บ refresh สถานะอัตโนมัติ
- Responsive สำหรับมือถือ
- แยก **DEMO** และ **LIVE** ชัดเจน
- Demo ไม่เข้า M-Flow และไม่ส่ง LINE/Telegram จริง

### ทดลองเว็บแบบปลอดภัย (Demo)

ติดตั้งครั้งแรก:

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .
```

macOS / Linux:

```bash
MFLOW_MOCK_MODE=success VEHICLES_FILE=vehicles.example.json python -m mflow_watchdog.cli dashboard --port 8080
```

Windows PowerShell:

```powershell
$env:MFLOW_MOCK_MODE="success"
$env:VEHICLES_FILE="vehicles.example.json"
python -m mflow_watchdog.cli dashboard --port 8080
```

จากนั้นเปิด `http://127.0.0.1:8080` แล้วกด **ตรวจสอบตอนนี้**

## Core features

- รถจริงเก็บใน `VEHICLES_JSON` Secret/Environment ไม่ลง public repo
- สถานะ backend `CLEAR`, `UNPAID`, `REVIEW_REQUIRED`, `CHECK_FAILED`
- วิเคราะห์เฉพาะข้อความใหม่หลัง submit เพื่อลด false positive
- รองรับหลายรายการค้างต่อรถหนึ่งคัน
- SQLite state + deduplication
- internal safety deadline ค่าเริ่มต้น 48 ชั่วโมง (เป็น SLA ภายใน ไม่ใช่ legal deadline)
- LINE Messaging API, Telegram, Slack
- Schedule 08:00 / 12:00 / 16:00 / 20:00 เวลาไทย
- ถ้าเจอ human verification หรือหน้าเว็บเปลี่ยน ระบบไม่ถือว่า CLEAR
- diagnostic screenshot/text ใช้ชื่อไฟล์ที่ hash ทะเบียน

## Local live setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .
playwright install chromium
cp vehicles.example.json vehicles.json
```

แก้ `vehicles.json` แล้วรัน checker ครั้งเดียว:

```bash
python -m mflow_watchdog.cli check
```

หรือเปิดเว็บแอดมิน:

```bash
python -m mflow_watchdog.cli dashboard --host 0.0.0.0 --port 8080
```

> ก่อนนำ LIVE web app ออกอินเทอร์เน็ต ควรเพิ่ม authentication / reverse proxy และใช้ HTTPS เพราะข้อมูลทะเบียนรถไม่ควรเปิดเป็น public dashboard

## GitHub Actions setup

สร้าง Repository Secret `VEHICLES_JSON` เป็น JSON array เช่น:

```json
[{"plate_number":"กก1234","province":"กรุงเทพมหานคร","driver_name":"Admin","active":true}]
```

เลือก notification อย่างน้อยหนึ่งช่องทาง:

### LINE Messaging API

- `LINE_CHANNEL_ACCESS_TOKEN`
- `LINE_TO`

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

Test suite ครอบคลุม parser, SQLite lifecycle และ dashboard demo end-to-end

## ข้อจำกัด

หน้า M-Flow สามารถเปลี่ยน DOM/ข้อความได้โดยไม่แจ้งล่วงหน้า ดังนั้นก่อนเปิด LIVE ควรรันกับทะเบียนที่ได้รับอนุญาตและตรวจ diagnostics อย่างน้อยหนึ่งรอบ หาก selector ไม่ตรง ระบบจะ fail-safe แทนการรายงานว่าไม่มีหนี้

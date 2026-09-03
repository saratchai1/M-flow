from urllib.request import Request, urlopen
import re

url = "https://mflowthai.com/mflowspf/main.dart.js"
request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
with urlopen(request, timeout=120) as response:
    text = response.read().decode("utf-8", errors="ignore")

for keyword in (
    "RequestDate", "TransactionId", "DeviceId", "Source", "Language", "System",
    "yyyyMMdd", "yyyy-MM-dd", "HHmmss", "HH:mm:ss", "millisecondsSinceEpoch",
    "microsecondsSinceEpoch", "uuid", "Uuid", "v4()", "requestDate",
):
    positions = [m.start() for m in re.finditer(re.escape(keyword), text, flags=re.I)]
    print("\nKEYWORD", keyword, "COUNT", len(positions))
    for pos in positions[:20]:
        start = max(0, pos - 650)
        end = min(len(text), pos + len(keyword) + 900)
        print("CONTEXT", " ".join(text[start:end].replace("\x00", " ").split())[:2200])

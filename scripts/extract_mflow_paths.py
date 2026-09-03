from __future__ import annotations

import re
from urllib.request import Request, urlopen

URL = "https://mflowthai.com/mflowspf/main.dart.js"
request = Request(URL, headers={"User-Agent": "Mozilla/5.0"})
with urlopen(request, timeout=90) as response:
    text = response.read().decode("utf-8", errors="ignore")

paths = sorted(set(re.findall(r'"(/v\d+/[^"\\]{1,180})"', text)))
print("PATH_COUNT", len(paths))
for path in paths:
    print("PATH", path)

for keyword in (
    "/token", "token", "AuthGrantType", "Basic [GUEST]", "guest", "GUEST",
    "dropdownProvince", "licensePlateType", "transaction-payment", "selectType",
):
    positions = [m.start() for m in re.finditer(re.escape(keyword), text, flags=re.I)]
    print("\nKEYWORD", keyword, "COUNT", len(positions))
    for pos in positions[:25]:
        start = max(0, pos - 900)
        end = min(len(text), pos + len(keyword) + 1300)
        print("CONTEXT", " ".join(text[start:end].replace("\x00", " ").split())[:3200])

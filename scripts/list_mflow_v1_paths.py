from urllib.request import Request, urlopen
import re

url = "https://mflowthai.com/mflowspf/main.dart.js"
request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
with urlopen(request, timeout=90) as response:
    text = response.read().decode("utf-8", errors="ignore")

paths = sorted(set(re.findall(r'["\'](/v\d+/[^"\'\\\s]{1,160})["\']', text)))
for path in paths:
    print(path)
print("TOTAL", len(paths))

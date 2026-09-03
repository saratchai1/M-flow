from urllib.request import Request, urlopen

url = "https://mflowthai.com/mflowspf/assets/.env"
request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
with urlopen(request, timeout=30) as response:
    raw = response.read()
print("STATUS", response.status)
print("TYPE", response.headers.get("Content-Type"))
print("BYTES", len(raw))
print(raw.decode("utf-8", errors="replace"))

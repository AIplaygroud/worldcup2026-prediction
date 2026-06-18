import json
import re
import urllib.request

url = "https://www.fotmob.com/en-GB/matches/south-africa-vs-mexico/1einvt"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
data = json.loads(re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S).group(1))
ticker = data["props"]["pageProps"]["content"]["liveticker"]
print(type(ticker), list(ticker.keys()) if isinstance(ticker, dict) else len(ticker))
events = ticker.get("events", ticker) if isinstance(ticker, dict) else ticker
if isinstance(events, list):
    for e in events:
        t = e.get("type")
        if t in ("substitution", "card", "redCard", "yellowCard") or "sub" in str(t).lower():
            print(json.dumps(e, ensure_ascii=False)[:300])
elif isinstance(ticker, dict):
    print(json.dumps(ticker, ensure_ascii=False)[:4000])

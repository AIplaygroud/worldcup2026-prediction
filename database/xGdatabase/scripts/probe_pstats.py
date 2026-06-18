import json
import re
import urllib.request

url = "https://www.fotmob.com/en-GB/matches/south-africa-vs-mexico/1einvt"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
data = json.loads(re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S).group(1))
pstats = data["props"]["pageProps"]["content"]["playerStats"]
for pid, p in pstats.items():
    stats = p.get("stats", [])
    for s in stats:
        if "minute" in str(s).lower() or s.get("title") == "Minutes played":
            print(p["name"], s)
    if p.get("minutesPlayed"):
        print("direct", p["name"], p["minutesPlayed"])

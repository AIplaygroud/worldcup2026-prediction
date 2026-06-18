import json
import re
import urllib.request

url = "https://www.fotmob.com/en-GB/matches/south-africa-vs-mexico/1einvt"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
data = json.loads(re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S).group(1))
lineup = data["props"]["pageProps"]["content"]["lineup"]
pstats = data["props"]["pageProps"]["content"].get("playerStats", {})
print("home subs sample:")
print(json.dumps(lineup["homeTeam"].get("subs", [])[:2], indent=2))
print("\naway subs sample:")
print(json.dumps(lineup["awayTeam"].get("subs", [])[:2], indent=2))
print("\nplayerStats keys", list(pstats.keys())[:10] if isinstance(pstats, dict) else type(pstats))
if isinstance(pstats, dict):
    for k in list(pstats.keys())[:1]:
        print(json.dumps(pstats[k], indent=2)[:1500])

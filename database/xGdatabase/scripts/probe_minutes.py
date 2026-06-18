import json
import re
import urllib.request

url = "https://www.fotmob.com/en-GB/matches/south-africa-vs-mexico/1einvt"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
data = json.loads(re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S).group(1))
lineup = data["props"]["pageProps"]["content"]["lineup"]
for side in ("homeTeam", "awayTeam"):
    team = lineup[side]
    print("===", team["name"], team["formation"])
    for p in team["starters"]:
        perf = p.get("performance", {})
        print(p["shirtNumber"], p["name"], "mins", perf.get("minutesPlayed"), perf.get("substitutionEvents"), perf.get("events"))
    for p in team["subs"]:
        perf = p.get("performance", {})
        if perf.get("substitutionEvents"):
            print("SUB", p["shirtNumber"], p["name"], perf.get("minutesPlayed"), perf.get("substitutionEvents"), perf.get("events"))

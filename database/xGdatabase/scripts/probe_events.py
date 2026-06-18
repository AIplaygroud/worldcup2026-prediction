import json
import re
import urllib.request

url = "https://www.fotmob.com/en-GB/matches/south-africa-vs-mexico/1einvt"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
data = json.loads(re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S).group(1))
content = data["props"]["pageProps"]["content"]

# search for substitution / card events anywhere
hits = []

def walk(obj, path=""):
    if isinstance(obj, dict):
        t = obj.get("type", "")
        if t in ("substitution", "subIn", "subOut", "redCard", "yellowCard", "card") or "Substitution" in str(obj):
            hits.append((path, obj))
        for k, v in obj.items():
            walk(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            walk(v, f"{path}[{i}]")

walk(content)
with open(r"e:\WORLDCUP2026\prediction-skill\database\xGdatabase\scripts\hits.json", "w", encoding="utf-8") as f:
    json.dump(hits[:80], f, ensure_ascii=False, indent=2)
print("hits", len(hits))

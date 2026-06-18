import json
import re
import urllib.request

url = "https://www.fotmob.com/en-GB/matches/south-africa-vs-mexico/1einvt"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
print("len", len(html))
for pat in ["__NEXT_DATA__", "lineup", "formation", "matchDetails"]:
    print(pat, html.find(pat))

m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
if m:
    data = json.loads(m.group(1))
    props = data.get("props", {}).get("pageProps", {})
    print("pageProps keys", list(props.keys()))
    content = props.get("content", {})
    print("content keys", list(content.keys()) if isinstance(content, dict) else type(content))
    # dig for lineup
    md = content.get("matchFacts") or content.get("lineup") or content
    print(json.dumps(md, indent=2)[:3000] if isinstance(md, dict) else str(md)[:500])
else:
    print("no __NEXT_DATA__")
    # try api pattern
    mid = "1einvt"
    api = f"https://www.fotmob.com/api/matchDetails?matchId={mid}"
    print("trying", api)
    req2 = urllib.request.Request(api, headers={"User-Agent": "Mozilla/5.0"})
    try:
        raw = urllib.request.urlopen(req2, timeout=30).read().decode()
        print(raw[:2000])
    except Exception as e:
        print("api err", e)

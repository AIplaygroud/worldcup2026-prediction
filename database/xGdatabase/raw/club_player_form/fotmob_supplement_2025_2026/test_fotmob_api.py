import base64
import hashlib
import json
import re
import time
import urllib.error
import urllib.request


GIST_RAW = "https://gist.githubusercontent.com/AlexGodard/0514a35b769e942acec796efa0a8c7a4/raw"


def fetch_text(url):
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(request, timeout=30).read().decode("utf-8", "replace")


def load_secret():
    text = fetch_text(GIST_RAW)
    match = re.search(r"const secretLyrics = `(.+?)`;", text, re.S)
    if not match:
        raise RuntimeError("Could not extract FotMob secret lyrics from reference gist.")
    return match.group(1)


def make_header(path, secret):
    body = {"url": path, "code": int(time.time() * 1000)}
    compact = json.dumps(body, separators=(",", ":"), ensure_ascii=False)
    signature = hashlib.md5((compact + secret).encode("utf-8")).hexdigest().upper()
    token = {"body": body, "signature": signature}
    return base64.b64encode(json.dumps(token, separators=(",", ":")).encode("utf-8")).decode("ascii")


def fetch_fotmob(path):
    secret = load_secret()
    request = urllib.request.Request(
        "https://www.fotmob.com" + path,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Content-Type": "application/json",
            "x-mas": make_header(path, secret),
        },
    )
    return urllib.request.urlopen(request, timeout=30).read().decode("utf-8", "replace")


def main():
    # Example from public reverse-engineering notes. The goal is only to confirm access shape.
    path = "/api/leagueseasondeepstats?id=67&season=22583&type=players&stat=expected_goals"
    try:
        text = fetch_fotmob(path)
    except urllib.error.HTTPError as exc:
        print(f"status={exc.code}")
        print(exc.read().decode("utf-8", "replace")[:300])
        return
    print(f"status=200 bytes={len(text)}")
    print(text[:500].encode("ascii", "backslashreplace").decode("ascii"))


if __name__ == "__main__":
    main()

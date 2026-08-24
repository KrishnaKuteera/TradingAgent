#!/usr/bin/env python3
"""Recovery tool: force-push local Chandu/Nandu Questrade tokens into the shared gist.

The gist (not local files or Streamlit secrets) is read first by QuestradeAPI, so if
the gist goes stale, pasting fresh tokens anywhere else is silently ignored. Run this
after pasting fresh tokens into Config/ChanduAPITracker / NanduAPITracker to make the
gist match again. See PROJECT.md > "Questrade Token Rotation" for the full runbook.
"""
import re
import requests
from pathlib import Path

CONFIG = Path(__file__).parent / "Config"
GIST_ID = "1bedc23f2daa0523457e63518d80c5c4"
GIST_API = f"https://api.github.com/gists/{GIST_ID}"


def load_gist_token():
    rtf = CONFIG / "GitHub_GIST_Token.rtf"
    tokens = re.findall(r"[A-Za-z0-9_]{20,}", rtf.read_text())
    if not tokens:
        raise SystemExit("Could not find a token in GitHub_GIST_Token.rtf")
    return tokens[-1]


def main():
    gist_token = load_gist_token()
    headers = {"Authorization": f"token {gist_token}", "Accept": "application/vnd.github.v3+json"}

    files = {}
    for name in ("ChanduAPITracker", "NanduAPITracker"):
        content = (CONFIG / name).read_text().strip()
        files[name] = {"content": content}

    r = requests.patch(GIST_API, headers=headers, json={"files": files}, timeout=10)
    r.raise_for_status()
    print("Gist updated:", r.json()["updated_at"])


if __name__ == "__main__":
    main()

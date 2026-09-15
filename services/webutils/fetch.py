"""Honest web fetch: plain HTTP(S) document retrieval, stdlib only.

Scope (documented, no overselling):
- GET + redirects, 20 s timeout, 512 KB cap, http/https only (no file://, no JS).
- Returns title + plain text (HTML tags/scripts stripped).
- There is NO search engine here: to "research" a topic, the agent fetches
  known URLs (docs, raw files, release pages). Search stays out of scope.
"""

from __future__ import annotations

import html as _html
import re
import urllib.request
from typing import Dict

MAX_BYTES = 512 * 1024


def _html_to_text(page: str) -> tuple:
    title = ""
    m = re.search(r"<title[^>]*>(.*?)</title>", page, re.IGNORECASE | re.DOTALL)
    if m:
        title = _html.unescape(re.sub(r"\s+", " ", m.group(1))).strip()[:300]
    body = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", page)
    body = re.sub(r"(?s)<!--.*?-->", " ", body)
    text = re.sub(r"<[^>]+>", " ", body)
    text = _html.unescape(re.sub(r"\s+", " ", text)).strip()
    return title, text[:20000]


def fetch_url(url: str, timeout: int = 20) -> Dict:
    """Fetch a URL, return {url, status, title, text} or {url, error}."""
    if not url.lower().startswith(("http://", "https://")):
        return {"url": url, "error": "only http(s) allowed"}
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "hcscoder/3.2 (+local agent)"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            ctype = resp.headers.get("Content-Type", "")
            raw = resp.read(MAX_BYTES + 1)
            truncated = len(raw) > MAX_BYTES
            text = raw[:MAX_BYTES].decode("utf-8", errors="replace")
            final_url = resp.geturl()
    except Exception as e:
        return {"url": url, "error": f"{type(e).__name__}: {e}"[:300]}
    if "html" in ctype or "<html" in text[:2000].lower():
        title, clean = _html_to_text(text)
    else:
        title, clean = "", text[:20000]
    out = {"url": final_url, "status": status, "title": title, "text": clean}
    if truncated:
        out["truncated"] = True
    return out

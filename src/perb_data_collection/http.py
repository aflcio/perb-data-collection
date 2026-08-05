"""HTTP fetch helpers with a polite, identifiable User-Agent."""

from __future__ import annotations

import re
import time
import urllib.error
import urllib.request
from html import unescape

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (compatible; perb-data-collection/0.1; "
    "+https://github.com/aflcio/perb-data-collection)"
)


def fetch_bytes(
    url: str,
    *,
    timeout: int = 120,
    delay_seconds: float = 0.0,
    user_agent: str = DEFAULT_USER_AGENT,
) -> bytes:
    if delay_seconds > 0:
        time.sleep(delay_seconds)
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} fetching {url}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Failed to fetch {url}: {exc}") from exc


def fetch_url(
    url: str,
    *,
    timeout: int = 120,
    delay_seconds: float = 0.0,
    user_agent: str = DEFAULT_USER_AGENT,
) -> str:
    raw = fetch_bytes(
        url,
        timeout=timeout,
        delay_seconds=delay_seconds,
        user_agent=user_agent,
    )
    return raw.decode("utf-8", errors="replace")


def strip_html_text(fragment: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", fragment, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s+", "\n", text)
    return text.strip()

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


# Several boards' document hosts reject a non-browser client outright: Delaware
# PERB's WAF answers "Request Rejected" (HTTP 200, an HTML page, 244 bytes) to
# the identifiable user agent above, and serves the PDF to this header set.
# The same set is what the CLRR curation server sends when it reads these
# documents, and Florida PERC serves its dossiers to it.
BROWSER_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/pdf,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Upgrade-Insecure-Requests": "1",
}


def fetch_bytes(
    url: str,
    *,
    timeout: int = 120,
    delay_seconds: float = 0.0,
    user_agent: str = DEFAULT_USER_AGENT,
    headers: dict[str, str] | None = None,
) -> bytes:
    if delay_seconds > 0:
        time.sleep(delay_seconds)
    request = urllib.request.Request(url, headers=headers or {"User-Agent": user_agent})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} fetching {url}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Failed to fetch {url}: {exc}") from exc


def fetch_document_bytes(url: str, *, timeout: int = 120, delay_seconds: float = 0.0) -> bytes:
    """Fetch a board's document with the browser header set.

    A WAF that rejects the request usually still answers 200 with a small HTML
    page. That is not the document, so it raises here rather than reaching a
    PDF parser as bytes that "read" as nothing.
    """
    data = fetch_bytes(url, timeout=timeout, delay_seconds=delay_seconds, headers=BROWSER_HEADERS)
    if len(data) < 4096 and b"request rejected" in data[:2048].lower():
        raise RuntimeError(f"HTTP 200 but the host rejected the request (WAF page) fetching {url}")
    return data


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

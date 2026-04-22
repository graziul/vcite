"""Wayback Machine snapshot integration for VCITE.

Given a source URL, this module either:
  1. Returns the most-recent existing Wayback snapshot (if fresh enough), or
  2. Requests a new Save Page Now (SPN) snapshot from web.archive.org.

Populating ``source.archive_url`` is the difference between L2 and L3
conformance (spec Sec. 3) — archive URLs address the link-rot axis of
the problem statement (spec Sec. 1.1).

Stdlib only. Anonymous SPN usage — no auth tokens. Failures log to stderr
and return None; callers can continue with an L2 citation.
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Optional

USER_AGENT = (
    "VCITE-archive/0.1 (https://github.com/graziul/vcite; mailto:vcite@idep.pub)"
)
REQUEST_TIMEOUT = 30  # seconds — SPN can be slow

AVAILABLE_API = "https://archive.org/wayback/available"
SAVE_URL = "https://web.archive.org/save"

# Polite rate limiting: minimum gap between outbound Wayback calls.
_MIN_INTERVAL_SECONDS = 1.0
_LAST_CALL_AT: float = 0.0


def _log(msg: str) -> None:
    """Emit a diagnostic to stderr."""
    print(msg, file=sys.stderr)


def _respect_rate_limit() -> None:
    """Sleep just long enough to keep a 1s minimum gap between Wayback calls."""
    global _LAST_CALL_AT
    elapsed = time.monotonic() - _LAST_CALL_AT
    if _LAST_CALL_AT and elapsed < _MIN_INTERVAL_SECONDS:
        time.sleep(_MIN_INTERVAL_SECONDS - elapsed)
    _LAST_CALL_AT = time.monotonic()


def _parse_wayback_timestamp(ts: str) -> Optional[datetime]:
    """Parse a Wayback 14-digit timestamp (YYYYMMDDHHMMSS) to UTC datetime."""
    if not ts or len(ts) < 8:
        return None
    try:
        return datetime.strptime(ts[:14].ljust(14, "0"), "%Y%m%d%H%M%S").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return None


def lookup_existing_snapshot(url: str, *, timeout: int = 15) -> Optional[str]:
    """Query the Wayback `available` API for the most recent snapshot of ``url``.

    Returns the archived URL if one exists, otherwise None. Never POSTs.
    Returns None on any network / parsing error.
    """
    _respect_rate_limit()
    params = urllib.parse.urlencode({"url": url})
    api_url = f"{AVAILABLE_API}?{params}"
    req = urllib.request.Request(api_url)
    req.add_header("User-Agent", USER_AGENT)
    req.add_header("Accept", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        _log(f"archive: wayback available HTTP {e.code} for {url}")
        return None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        _log(f"archive: wayback available network error for {url}: {e}")
        return None

    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        _log(f"archive: wayback available returned non-JSON for {url}")
        return None

    snapshot = (
        data.get("archived_snapshots", {}).get("closest", {})
        if isinstance(data, dict)
        else {}
    )
    if not snapshot or not snapshot.get("available"):
        return None
    archived_url = snapshot.get("url")
    if not archived_url:
        return None
    # Wayback sometimes returns http — upgrade to https.
    if archived_url.startswith("http://web.archive.org/"):
        archived_url = "https://" + archived_url[len("http://") :]
    return archived_url


def _snapshot_age_days(archived_url: str) -> Optional[float]:
    """Extract the timestamp from a Wayback URL and return its age in days."""
    # Wayback URLs look like https://web.archive.org/web/YYYYMMDDHHMMSS/<orig>
    m = re.search(r"/web/(\d{8,14})", archived_url)
    if not m:
        return None
    ts = _parse_wayback_timestamp(m.group(1))
    if not ts:
        return None
    age = datetime.now(timezone.utc) - ts
    return age.total_seconds() / 86400.0


def _request_save_page_now(url: str, *, timeout: int) -> Optional[str]:
    """POST to Save Page Now and return the resulting snapshot URL, or None."""
    _respect_rate_limit()
    # SPN accepts both /save/<url> and POSTed form data. We POST the URL as
    # form data so that URLs containing slashes / query strings are handled
    # reliably by the server without double-encoding concerns.
    data = urllib.parse.urlencode({"url": url}).encode("ascii")
    req = urllib.request.Request(SAVE_URL, data=data, method="POST")
    req.add_header("User-Agent", USER_AGENT)
    req.add_header("Accept", "text/html, */*")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = getattr(resp, "status", 200)
            # Preferred: the `Content-Location` / `Location` header on 200/302.
            headers = resp.headers
            body_bytes = resp.read()
    except urllib.error.HTTPError as e:
        if e.code == 429:
            _log(f"archive: save-page-now rate-limited (HTTP 429) for {url}")
        else:
            _log(f"archive: save-page-now HTTP {e.code} for {url}")
        return None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        _log(f"archive: save-page-now network error for {url}: {e}")
        return None

    if status >= 500:
        _log(f"archive: save-page-now server error {status} for {url}")
        return None

    # 1. Check redirect-style headers first.
    loc = headers.get("Content-Location") or headers.get("Location")
    if loc and "/web/" in loc:
        if loc.startswith("/"):
            return "https://web.archive.org" + loc
        return loc

    # 2. Parse a snapshot URL out of the response body (SPN returns an
    #    interstitial HTML page that embeds the archived URL).
    body = body_bytes.decode("utf-8", errors="replace")
    m = re.search(
        r'https?://web\.archive\.org/web/\d{8,14}/[^\s"\'<>]+',
        body,
    )
    if m:
        return m.group(0)

    _log(f"archive: save-page-now returned no snapshot URL for {url}")
    return None


def snapshot_source(
    url: str,
    *,
    prefer_existing_within_days: int = 30,
    timeout: int = REQUEST_TIMEOUT,
) -> Optional[str]:
    """Return a Wayback Machine archive URL for ``url``.

    Strategy:
      1. Ask the Wayback `available` API for the latest snapshot. If one
         exists and is fresher than ``prefer_existing_within_days``, return
         it (no POST).
      2. Otherwise, POST to Save Page Now and return the resulting snapshot
         URL.

    On any failure (timeout, 5xx, rate-limit 429, captcha, malformed
    response) this logs to stderr and returns None — the caller should
    continue without an archive URL (L2 conformance).
    """
    if not url:
        return None

    existing = lookup_existing_snapshot(url, timeout=min(timeout, 15))
    if existing:
        age = _snapshot_age_days(existing)
        if age is not None and age <= prefer_existing_within_days:
            return existing
        # Existing snapshot is too stale — fall through to SPN.

    return _request_save_page_now(url, timeout=timeout)

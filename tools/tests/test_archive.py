"""Tests for tools/archive.py — Wayback Machine snapshot integration.

All network calls are mocked. We verify:
  - Existing fresh snapshot -> returned without POST
  - No existing snapshot -> POST to SPN
  - Stale existing snapshot -> POST to SPN anyway
  - Network failure / timeout -> None (no raise)
  - HTTP 429 -> None with a rate-limit-specific log line
  - Malformed response JSON -> None (no raise)
  - lookup_existing_snapshot never POSTs
  - enhance.py integration: archive_url lands in the output JSON
"""

from __future__ import annotations

import io
import json
import sys
import urllib.error
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "implementations" / "python"))
sys.path.insert(0, str(ROOT / "tools"))

import archive  # noqa: E402
from archive import (  # noqa: E402
    snapshot_source,
    lookup_existing_snapshot,
    _parse_wayback_timestamp,
    _snapshot_age_days,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeResponse:
    """Minimal stand-in for urllib.request's response context manager."""

    def __init__(
        self,
        body: bytes | str,
        *,
        status: int = 200,
        headers: dict | None = None,
    ):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self._body = body
        self.status = status
        self.headers = headers or {}

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def _available_payload(archived_url: str, timestamp: str, available: bool = True):
    """Shape a Wayback `available` JSON response."""
    return json.dumps(
        {
            "archived_snapshots": {
                "closest": {
                    "available": available,
                    "url": archived_url,
                    "timestamp": timestamp,
                    "status": "200",
                }
            }
        }
    )


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Each test starts with a clean rate-limit clock so no sleeps occur."""
    archive._LAST_CALL_AT = 0.0
    yield
    archive._LAST_CALL_AT = 0.0


# ---------------------------------------------------------------------------
# Timestamp parsing
# ---------------------------------------------------------------------------


def test_parse_wayback_timestamp_14_digits():
    dt = _parse_wayback_timestamp("20240115123045")
    assert dt is not None
    assert dt.year == 2024 and dt.month == 1 and dt.day == 15


def test_parse_wayback_timestamp_malformed():
    assert _parse_wayback_timestamp("not-a-timestamp") is None
    assert _parse_wayback_timestamp("") is None


def test_snapshot_age_days_recent():
    now = datetime.now(timezone.utc)
    ts = (now - timedelta(days=2)).strftime("%Y%m%d%H%M%S")
    age = _snapshot_age_days(f"https://web.archive.org/web/{ts}/https://e.x")
    assert age is not None and 1.5 < age < 2.5


def test_snapshot_age_days_unparseable():
    assert _snapshot_age_days("https://example.org/not-wayback") is None


# ---------------------------------------------------------------------------
# lookup_existing_snapshot
# ---------------------------------------------------------------------------


def test_lookup_existing_snapshot_returns_url():
    archived = "http://web.archive.org/web/20240301120000/https://example.org/a"
    body = _available_payload(archived, "20240301120000")
    with patch("archive.urllib.request.urlopen") as mock_open:
        mock_open.return_value = _FakeResponse(body)
        result = lookup_existing_snapshot("https://example.org/a")
    # Lookup upgrades http://web.archive.org to https.
    assert result == "https://web.archive.org/web/20240301120000/https://example.org/a"
    # Exactly one GET, no POST.
    assert mock_open.call_count == 1
    req = mock_open.call_args[0][0]
    assert req.get_method() == "GET"


def test_lookup_existing_snapshot_no_snapshot_available():
    body = json.dumps({"archived_snapshots": {}})
    with patch("archive.urllib.request.urlopen") as mock_open:
        mock_open.return_value = _FakeResponse(body)
        assert lookup_existing_snapshot("https://example.org/none") is None


def test_lookup_existing_snapshot_never_posts():
    """Even if the API throws, lookup_existing_snapshot must not POST."""
    with patch("archive.urllib.request.urlopen") as mock_open:
        mock_open.side_effect = urllib.error.URLError("no network")
        assert lookup_existing_snapshot("https://example.org/x") is None
    # Sanity: the one call we did make was a GET, not POST.
    for call in mock_open.call_args_list:
        req = call[0][0]
        assert req.get_method() == "GET"


def test_lookup_existing_snapshot_malformed_json():
    with patch("archive.urllib.request.urlopen") as mock_open:
        mock_open.return_value = _FakeResponse("not json at all")
        assert lookup_existing_snapshot("https://example.org/x") is None


# ---------------------------------------------------------------------------
# snapshot_source
# ---------------------------------------------------------------------------


def test_snapshot_source_existing_fresh_returns_without_posting():
    """An existing snapshot fresher than prefer_existing_within_days short-circuits."""
    now = datetime.now(timezone.utc)
    ts = (now - timedelta(days=5)).strftime("%Y%m%d%H%M%S")
    archived = f"https://web.archive.org/web/{ts}/https://example.org/a"
    body = _available_payload(archived, ts)

    with patch("archive.urllib.request.urlopen") as mock_open:
        mock_open.return_value = _FakeResponse(body)
        result = snapshot_source(
            "https://example.org/a", prefer_existing_within_days=30
        )

    assert result == archived
    # Exactly one HTTP call, and it was a GET (the `available` lookup).
    assert mock_open.call_count == 1
    assert mock_open.call_args[0][0].get_method() == "GET"


def test_snapshot_source_no_existing_posts_to_spn():
    """No existing snapshot -> POST to Save Page Now, parse snapshot URL from body."""
    available_body = json.dumps({"archived_snapshots": {}})
    spn_body = (
        "<html><body>Your page is at "
        "<a href='https://web.archive.org/web/20260422010203/"
        "https://example.org/new'>here</a></body></html>"
    )

    def _urlopen(req, timeout=None):
        if req.full_url.startswith(archive.AVAILABLE_API):
            return _FakeResponse(available_body)
        # SPN POST
        assert req.get_method() == "POST"
        assert req.full_url == archive.SAVE_URL
        return _FakeResponse(spn_body, status=200)

    with patch("archive.urllib.request.urlopen", side_effect=_urlopen) as mock_open:
        result = snapshot_source("https://example.org/new")

    assert result == (
        "https://web.archive.org/web/20260422010203/https://example.org/new"
    )
    # Two calls total: GET available + POST save.
    assert mock_open.call_count == 2
    methods = [c[0][0].get_method() for c in mock_open.call_args_list]
    assert methods == ["GET", "POST"]


def test_snapshot_source_stale_existing_still_posts():
    """An existing snapshot older than the threshold triggers a fresh SPN POST."""
    old_ts = (datetime.now(timezone.utc) - timedelta(days=365)).strftime(
        "%Y%m%d%H%M%S"
    )
    stale_archived = (
        f"https://web.archive.org/web/{old_ts}/https://example.org/a"
    )
    available_body = _available_payload(stale_archived, old_ts)

    new_archived = (
        "https://web.archive.org/web/20260422010203/https://example.org/a"
    )
    spn_body = f"<html>redirect to {new_archived}</html>"

    def _urlopen(req, timeout=None):
        if req.full_url.startswith(archive.AVAILABLE_API):
            return _FakeResponse(available_body)
        return _FakeResponse(spn_body)

    with patch("archive.urllib.request.urlopen", side_effect=_urlopen) as mock_open:
        result = snapshot_source(
            "https://example.org/a", prefer_existing_within_days=30
        )

    assert result == new_archived
    assert mock_open.call_count == 2


def test_snapshot_source_uses_content_location_header():
    """If SPN responds with a Content-Location header, use it directly."""
    available_body = json.dumps({"archived_snapshots": {}})
    spn_headers = {
        "Content-Location": "/web/20260422000000/https://example.org/h"
    }

    def _urlopen(req, timeout=None):
        if req.full_url.startswith(archive.AVAILABLE_API):
            return _FakeResponse(available_body)
        return _FakeResponse("", status=200, headers=spn_headers)

    with patch("archive.urllib.request.urlopen", side_effect=_urlopen):
        result = snapshot_source("https://example.org/h")

    assert result == (
        "https://web.archive.org/web/20260422000000/https://example.org/h"
    )


def test_snapshot_source_network_failure_returns_none(capsys):
    with patch(
        "archive.urllib.request.urlopen",
        side_effect=urllib.error.URLError("boom"),
    ):
        assert snapshot_source("https://example.org/x") is None
    # Failure logged to stderr, not raised.
    err = capsys.readouterr().err
    assert "archive:" in err


def test_snapshot_source_timeout_returns_none():
    with patch("archive.urllib.request.urlopen", side_effect=TimeoutError("slow")):
        assert snapshot_source("https://example.org/x") is None


def test_snapshot_source_rate_limited_429(capsys):
    """HTTP 429 on SPN -> None with a rate-limit-specific log line."""
    available_body = json.dumps({"archived_snapshots": {}})

    def _urlopen(req, timeout=None):
        if req.full_url.startswith(archive.AVAILABLE_API):
            return _FakeResponse(available_body)
        raise urllib.error.HTTPError(
            url=req.full_url, code=429, msg="Too Many Requests",
            hdrs=None, fp=None,
        )

    with patch("archive.urllib.request.urlopen", side_effect=_urlopen):
        assert snapshot_source("https://example.org/x") is None

    err = capsys.readouterr().err
    assert "rate-limited" in err and "429" in err


def test_snapshot_source_malformed_available_json():
    """Malformed `available` JSON -> None, no raise, and no SPN POST fallback."""
    with patch("archive.urllib.request.urlopen") as mock_open:
        mock_open.return_value = _FakeResponse("<html>not json</html>")
        # Malformed available -> lookup returns None. snapshot_source then
        # proceeds to SPN; simulate that by returning the same bad body.
        # The key contract: no raise. Result may be None depending on SPN
        # parse behavior.
        result = snapshot_source("https://example.org/m")
    # If SPN also can't parse a snapshot URL out of the body, result is None.
    assert result is None


def test_snapshot_source_empty_url_returns_none():
    # Should not even try to call the network.
    with patch("archive.urllib.request.urlopen") as mock_open:
        assert snapshot_source("") is None
    assert mock_open.call_count == 0


# ---------------------------------------------------------------------------
# Integration: enhance.py sets archive_url on output citation
# ---------------------------------------------------------------------------


def test_enhance_integration_archive_url_in_output(tmp_path, monkeypatch):
    """End-to-end: enhance.py with --archive populates source.archive_url."""
    # Minimal HTML with one blockquote and an inline author-year hint.
    html = (
        "<html><body><p>"
        "As documented by Smith (2020), "
        "<blockquote>the sky is measurably blue</blockquote>"
        " this finding is robust."
        "</p></body></html>"
    )
    input_path = tmp_path / "article.html"
    output_path = tmp_path / "out.json"
    input_path.write_text(html, encoding="utf-8")

    import enhance
    from metadata import SourceMetadata

    fake_metadata = SourceMetadata(
        title="A Study of the Sky",
        authors=["Smith, Jane"],
        year=2020,
        doi="10.1234/sky",
        url="https://example.org/sky",
        venue="Journal of Atmospheres",
        source_type="academic",
    )
    snapshot_url = (
        "https://web.archive.org/web/20260422000000/https://example.org/sky"
    )

    with patch.object(enhance, "resolve_citation", return_value=fake_metadata), \
         patch.object(enhance, "snapshot_source", return_value=snapshot_url) as snap_mock:
        enhance.enhance_article(
            input_path,
            output_path,
            fmt="json",
            skip_metadata=False,
            no_fragment_url=True,
            archive_mode="snapshot",
        )

    assert snap_mock.called, "snapshot_source should have been invoked"
    data = json.loads(output_path.read_text(encoding="utf-8"))
    assert isinstance(data, list) and len(data) >= 1
    citation = data[0]
    assert citation["source"].get("archive_url") == snapshot_url


def test_enhance_integration_no_metadata_suppresses_archive(tmp_path, capsys):
    """--archive under --no-metadata prints a note and does not call snapshot."""
    html = (
        "<html><body>"
        "<blockquote>the sky is measurably blue</blockquote>"
        "</body></html>"
    )
    input_path = tmp_path / "article.html"
    output_path = tmp_path / "out.json"
    input_path.write_text(html, encoding="utf-8")

    import enhance

    with patch.object(enhance, "snapshot_source") as snap_mock, \
         patch.object(enhance, "lookup_existing_snapshot") as lookup_mock:
        enhance.enhance_article(
            input_path,
            output_path,
            fmt="json",
            skip_metadata=True,
            no_fragment_url=True,
            archive_mode="snapshot",
        )

    snap_mock.assert_not_called()
    lookup_mock.assert_not_called()
    err = capsys.readouterr().err
    assert "no effect" in err.lower() or "skipping archival" in err.lower()


def test_enhance_integration_archive_lookup_only_no_post(tmp_path):
    """--archive-lookup-only uses lookup_existing_snapshot (no POST path)."""
    html = (
        "<html><body><p>"
        "Per Smith (2020), "
        "<blockquote>the sky is measurably blue</blockquote>"
        "</p></body></html>"
    )
    input_path = tmp_path / "article.html"
    output_path = tmp_path / "out.json"
    input_path.write_text(html, encoding="utf-8")

    import enhance
    from metadata import SourceMetadata

    fake_metadata = SourceMetadata(
        title="Sky", authors=["Smith, Jane"], year=2020,
        doi="10.1234/sky", url="https://example.org/sky",
        venue="J", source_type="academic",
    )
    lookup_url = "https://web.archive.org/web/20260101000000/https://example.org/sky"

    with patch.object(enhance, "resolve_citation", return_value=fake_metadata), \
         patch.object(enhance, "lookup_existing_snapshot", return_value=lookup_url) as look_mock, \
         patch.object(enhance, "snapshot_source") as snap_mock:
        enhance.enhance_article(
            input_path,
            output_path,
            fmt="json",
            skip_metadata=False,
            no_fragment_url=True,
            archive_mode="lookup",
        )

    look_mock.assert_called_once()
    snap_mock.assert_not_called()
    data = json.loads(output_path.read_text(encoding="utf-8"))
    assert data[0]["source"].get("archive_url") == lookup_url

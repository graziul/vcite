"""Tests for the VCITE verification database (hashdb)."""

import json
import sys
from pathlib import Path

import pytest

TOOLS_DIR = Path(__file__).parent.parent
REPO_ROOT = TOOLS_DIR.parent
sys.path.insert(0, str(REPO_ROOT / "implementations" / "python"))
sys.path.insert(0, str(TOOLS_DIR))

from hashdb import HashDB, _hash_content
from verify import VerificationResult, PassageMatch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_result(
    citation_id="vcite-001",
    status="verified",
    source_url="https://example.com/paper",
    **kwargs,
) -> VerificationResult:
    defaults = dict(
        citation_id=citation_id,
        source_title="Test Paper",
        status=status,
        internal_hash_valid=True,
        conformance_level=2,
        relation="supports",
        captured_by="author",
        source_url=source_url,
    )
    defaults.update(kwargs)
    return VerificationResult(**defaults)


# ---------------------------------------------------------------------------
# Schema and init
# ---------------------------------------------------------------------------

class TestInit:
    def test_creates_tables(self, tmp_path):
        db_path = tmp_path / "test.db"
        with HashDB(db_path) as db:
            s = db.stats()
            assert s["total_verifications"] == 0
            assert s["total_sources"] == 0
            assert s["total_drift_events"] == 0

    def test_idempotent_init(self, tmp_path):
        db_path = tmp_path / "test.db"
        with HashDB(db_path):
            pass
        # Re-open same DB — should not fail
        with HashDB(db_path) as db:
            assert db.stats()["total_verifications"] == 0


# ---------------------------------------------------------------------------
# Verification results
# ---------------------------------------------------------------------------

class TestStoreAndRetrieve:
    def test_store_and_retrieve(self, tmp_path):
        db_path = tmp_path / "test.db"
        result = _make_result(warnings=["test warning"])
        with HashDB(db_path) as db:
            row_id = db.store_result(result, input_file="article.html")
            assert row_id > 0

            rows = db.get_results(citation_id="vcite-001")
            assert len(rows) == 1
            assert rows[0]["status"] == "verified"
            assert rows[0]["input_file"] == "article.html"
            assert "test warning" in rows[0]["warnings"]

    def test_store_with_passage_match(self, tmp_path):
        db_path = tmp_path / "test.db"
        pm = PassageMatch(
            found=True, matched_text="the passage",
            char_start=100, char_end=112,
            match_type="exact", similarity=1.0,
        )
        result = _make_result(passage_match=pm)
        with HashDB(db_path) as db:
            db.store_result(result)
            rows = db.get_results()
            assert rows[0]["match_type"] == "exact"
            assert rows[0]["match_similarity"] == 1.0

    def test_latest_result(self, tmp_path):
        db_path = tmp_path / "test.db"
        with HashDB(db_path) as db:
            db.store_result(_make_result(status="passage_not_found"))
            db.store_result(_make_result(status="verified"))

            latest = db.latest_result("vcite-001")
            assert latest["status"] == "verified"

    def test_latest_result_not_found(self, tmp_path):
        db_path = tmp_path / "test.db"
        with HashDB(db_path) as db:
            assert db.latest_result("nonexistent") is None

    def test_filter_by_status(self, tmp_path):
        db_path = tmp_path / "test.db"
        with HashDB(db_path) as db:
            db.store_result(_make_result(citation_id="v1", status="verified"))
            db.store_result(_make_result(citation_id="v2", status="hash_mismatch"))
            db.store_result(_make_result(citation_id="v3", status="verified"))

            verified = db.get_results(status="verified")
            assert len(verified) == 2
            mismatched = db.get_results(status="hash_mismatch")
            assert len(mismatched) == 1


# ---------------------------------------------------------------------------
# Source tracking and drift detection
# ---------------------------------------------------------------------------

class TestSourceTracking:
    def test_record_new_source(self, tmp_path):
        db_path = tmp_path / "test.db"
        with HashDB(db_path) as db:
            is_drift, h = db.record_source(
                "https://example.com", "Hello world", "text/html"
            )
            assert not is_drift
            assert h.startswith("sha256:")
            assert db.stats()["total_sources"] == 1

    def test_record_unchanged_source(self, tmp_path):
        db_path = tmp_path / "test.db"
        with HashDB(db_path) as db:
            db.record_source("https://example.com", "Hello world")
            is_drift, _ = db.record_source("https://example.com", "Hello world")
            assert not is_drift
            # Still one source (same content)
            history = db.get_source_history("https://example.com")
            assert len(history) == 1
            assert history[0]["fetch_count"] == 2

    def test_record_source_drift(self, tmp_path):
        db_path = tmp_path / "test.db"
        with HashDB(db_path) as db:
            # First store a verification result so drift has affected citations
            db.store_result(_make_result(source_url="https://example.com"))

            db.record_source("https://example.com", "Original content")
            is_drift, _ = db.record_source("https://example.com", "Changed content")
            assert is_drift

            # Check drift events
            events = db.check_drift("https://example.com")
            assert len(events) == 1
            assert events[0]["old_hash"] != events[0]["new_hash"]

            # Check affected citations
            report = db.drift_report()
            assert len(report) == 1
            assert "vcite-001" in report[0]["affected_citations"]

    def test_no_drift_for_new_url(self, tmp_path):
        db_path = tmp_path / "test.db"
        with HashDB(db_path) as db:
            is_drift, _ = db.record_source("https://new.example.com", "content")
            assert not is_drift
            assert db.check_drift("https://new.example.com") == []


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

class TestStats:
    def test_stats_aggregate(self, tmp_path):
        db_path = tmp_path / "test.db"
        with HashDB(db_path) as db:
            db.store_result(_make_result(citation_id="v1", status="verified"))
            db.store_result(_make_result(citation_id="v2", status="verified"))
            db.store_result(_make_result(citation_id="v3", status="hash_mismatch"))
            db.record_source("https://a.com", "content a")
            db.record_source("https://b.com", "content b")

            s = db.stats()
            assert s["total_verifications"] == 3
            assert s["by_status"]["verified"] == 2
            assert s["by_status"]["hash_mismatch"] == 1
            assert s["total_sources"] == 2
            assert s["total_drift_events"] == 0


# ---------------------------------------------------------------------------
# Content hashing
# ---------------------------------------------------------------------------

class TestContentHashing:
    def test_deterministic(self):
        h1 = _hash_content("hello world")
        h2 = _hash_content("hello world")
        assert h1 == h2
        assert h1.startswith("sha256:")

    def test_nfc_normalization(self):
        # e + combining accent vs precomposed e-acute
        h1 = _hash_content("caf\u00e9")     # precomposed
        h2 = _hash_content("cafe\u0301")    # decomposed
        assert h1 == h2

    def test_different_content_different_hash(self):
        h1 = _hash_content("content version 1")
        h2 = _hash_content("content version 2")
        assert h1 != h2


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------

class TestContextManager:
    def test_context_manager(self, tmp_path):
        db_path = tmp_path / "test.db"
        with HashDB(db_path) as db:
            db.store_result(_make_result())
        # After exiting, operations should work on a new connection
        with HashDB(db_path) as db:
            assert db.stats()["total_verifications"] == 1

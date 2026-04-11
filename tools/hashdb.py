#!/usr/bin/env python3
"""VCITE verification database — persist results and detect source drift.

SQLite-backed store for verification results. Tracks source content
over time and detects when cited URLs change (source drift).

Zero external dependencies — stdlib sqlite3 only.

Usage as library:
    from hashdb import HashDB
    with HashDB("verifications.db") as db:
        db.store_result(result, input_file="article.html")
        db.record_source(url, content)
        print(db.stats())

Usage as CLI:
    python tools/hashdb.py init --db verifications.db
    python tools/hashdb.py stats --db verifications.db
    python tools/hashdb.py check vcite-001 --db verifications.db
    python tools/hashdb.py drift-check --db verifications.db
"""

import argparse
import hashlib
import json
import sqlite3
import sys
import unicodedata
from pathlib import Path
from typing import Optional


_SCHEMA = """\
CREATE TABLE IF NOT EXISTS verifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    citation_id TEXT NOT NULL,
    source_title TEXT NOT NULL,
    status TEXT NOT NULL,
    internal_hash_valid INTEGER NOT NULL,
    source_hash_valid INTEGER,
    source_hash_recomputed TEXT,
    match_type TEXT,
    match_similarity REAL,
    source_url TEXT,
    fetch_error TEXT,
    conformance_level INTEGER,
    relation TEXT,
    page_ref TEXT,
    captured_by TEXT,
    warnings TEXT,
    verified_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    input_file TEXT
);

CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    content_length INTEGER,
    content_type TEXT,
    first_seen TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    last_seen TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    fetch_count INTEGER NOT NULL DEFAULT 1,
    UNIQUE(url, content_hash)
);

CREATE TABLE IF NOT EXISTS drift_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL,
    old_hash TEXT NOT NULL,
    new_hash TEXT NOT NULL,
    old_content_length INTEGER,
    new_content_length INTEGER,
    detected_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    citation_ids TEXT
);

CREATE INDEX IF NOT EXISTS idx_verifications_citation_id ON verifications(citation_id);
CREATE INDEX IF NOT EXISTS idx_verifications_status ON verifications(status);
CREATE INDEX IF NOT EXISTS idx_sources_url ON sources(url);
CREATE INDEX IF NOT EXISTS idx_drift_events_url ON drift_events(url);
"""


def _hash_content(text: str) -> str:
    """SHA-256 of full source text for drift detection.

    NFC-normalized before hashing for consistency across fetches.
    Uses sha256: prefix for consistency with VCITE passage hashes.
    """
    normalized = unicodedata.normalize("NFC", text)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


class HashDB:
    """SQLite-backed verification result store with drift detection."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()

    def _init_schema(self):
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "HashDB":
        return self

    def __exit__(self, *exc):
        self.close()

    # ------------------------------------------------------------------
    # Verification results
    # ------------------------------------------------------------------

    def store_result(self, result, input_file: str = "") -> int:
        """Store a VerificationResult. Returns the row ID."""
        match_type = None
        match_similarity = None
        if result.passage_match and result.passage_match.found:
            match_type = result.passage_match.match_type
            match_similarity = result.passage_match.similarity

        warnings_json = json.dumps(result.warnings) if result.warnings else "[]"

        cur = self._conn.execute(
            """INSERT INTO verifications
               (citation_id, source_title, status, internal_hash_valid,
                source_hash_valid, source_hash_recomputed, match_type,
                match_similarity, source_url, fetch_error, conformance_level,
                relation, page_ref, captured_by, warnings, input_file)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                result.citation_id,
                result.source_title,
                result.status,
                int(result.internal_hash_valid),
                int(result.source_hash_valid) if result.source_hash_valid is not None else None,
                result.source_hash_recomputed or None,
                match_type,
                match_similarity,
                result.source_url or None,
                result.fetch_error or None,
                result.conformance_level,
                result.relation,
                result.page_ref or None,
                result.captured_by,
                warnings_json,
                input_file or None,
            ),
        )
        self._conn.commit()
        return cur.lastrowid

    def get_results(
        self,
        citation_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict]:
        """Query stored verification results, optionally filtered."""
        clauses = []
        params = []
        if citation_id:
            clauses.append("citation_id = ?")
            params.append(citation_id)
        if status:
            clauses.append("status = ?")
            params.append(status)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)

        rows = self._conn.execute(
            f"SELECT * FROM verifications {where} ORDER BY verified_at DESC LIMIT ?",
            params,
        ).fetchall()
        return [dict(r) for r in rows]

    def latest_result(self, citation_id: str) -> Optional[dict]:
        """Get the most recent verification result for a citation."""
        row = self._conn.execute(
            "SELECT * FROM verifications WHERE citation_id = ? ORDER BY id DESC LIMIT 1",
            (citation_id,),
        ).fetchone()
        return dict(row) if row else None

    # ------------------------------------------------------------------
    # Source tracking and drift detection
    # ------------------------------------------------------------------

    def record_source(
        self, url: str, content: str, content_type: str = ""
    ) -> tuple[bool, str]:
        """Record a source fetch. Returns (is_drift, content_hash).

        If this URL+hash pair exists, updates last_seen/fetch_count.
        If the URL exists with a different hash, records a drift event.
        If the URL is new, inserts a fresh record.
        """
        content_hash = _hash_content(content)
        content_length = len(content)

        # Check if this exact URL+hash exists
        existing = self._conn.execute(
            "SELECT id FROM sources WHERE url = ? AND content_hash = ?",
            (url, content_hash),
        ).fetchone()

        if existing:
            # Same content — update last_seen and fetch_count
            self._conn.execute(
                """UPDATE sources SET last_seen = strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
                   fetch_count = fetch_count + 1
                   WHERE url = ? AND content_hash = ?""",
                (url, content_hash),
            )
            self._conn.commit()
            return False, content_hash

        # Check if the URL exists with a different hash (drift)
        prev = self._conn.execute(
            "SELECT content_hash, content_length FROM sources WHERE url = ? ORDER BY last_seen DESC LIMIT 1",
            (url,),
        ).fetchone()

        is_drift = prev is not None

        if is_drift:
            # Find affected citations
            affected = self._conn.execute(
                "SELECT DISTINCT citation_id FROM verifications WHERE source_url = ?",
                (url,),
            ).fetchall()
            citation_ids = json.dumps([r["citation_id"] for r in affected])

            self._conn.execute(
                """INSERT INTO drift_events
                   (url, old_hash, new_hash, old_content_length,
                    new_content_length, citation_ids)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (url, prev["content_hash"], content_hash,
                 prev["content_length"], content_length, citation_ids),
            )

        # Insert new source record
        self._conn.execute(
            """INSERT INTO sources (url, content_hash, content_length, content_type)
               VALUES (?, ?, ?, ?)""",
            (url, content_hash, content_length, content_type or None),
        )
        self._conn.commit()
        return is_drift, content_hash

    def check_drift(self, url: str) -> list[dict]:
        """Return all drift events for a URL, ordered by detected_at."""
        rows = self._conn.execute(
            "SELECT * FROM drift_events WHERE url = ? ORDER BY detected_at",
            (url,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_source_history(self, url: str) -> list[dict]:
        """Return all known content hashes for a URL with timestamps."""
        rows = self._conn.execute(
            "SELECT * FROM sources WHERE url = ? ORDER BY first_seen",
            (url,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Aggregate queries
    # ------------------------------------------------------------------

    def stats(self) -> dict:
        """Return aggregate statistics."""
        total = self._conn.execute(
            "SELECT COUNT(*) as n FROM verifications"
        ).fetchone()["n"]

        by_status = {}
        for row in self._conn.execute(
            "SELECT status, COUNT(*) as n FROM verifications GROUP BY status"
        ).fetchall():
            by_status[row["status"]] = row["n"]

        total_sources = self._conn.execute(
            "SELECT COUNT(DISTINCT url) as n FROM sources"
        ).fetchone()["n"]

        sources_with_drift = self._conn.execute(
            "SELECT COUNT(DISTINCT url) as n FROM drift_events"
        ).fetchone()["n"]

        total_drift = self._conn.execute(
            "SELECT COUNT(*) as n FROM drift_events"
        ).fetchone()["n"]

        last_v = self._conn.execute(
            "SELECT MAX(verified_at) as t FROM verifications"
        ).fetchone()["t"]

        return {
            "total_verifications": total,
            "by_status": by_status,
            "total_sources": total_sources,
            "sources_with_drift": sources_with_drift,
            "total_drift_events": total_drift,
            "last_verification": last_v,
        }

    def drift_report(self) -> list[dict]:
        """Return all drift events with associated citation info."""
        rows = self._conn.execute(
            "SELECT * FROM drift_events ORDER BY detected_at DESC"
        ).fetchall()
        results = []
        for r in rows:
            d = dict(r)
            d["affected_citations"] = json.loads(d.get("citation_ids") or "[]")
            results.append(d)
        return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _log(msg: str):
    print(msg, file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description="VCITE verification database — store results and detect source drift",
    )
    parser.add_argument(
        "--db", default=".vcite-verifications.db",
        help="Path to SQLite database (default: .vcite-verifications.db)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init", help="Create or validate database")

    sp_store = subparsers.add_parser("store", help="Store verification results from JSON")
    sp_store.add_argument("results", help="JSON file with verification results")
    sp_store.add_argument("--input-file", default="", help="Original input file name")

    sp_check = subparsers.add_parser("check", help="Show latest result for a citation")
    sp_check.add_argument("citation_id", help="Citation ID to look up")

    subparsers.add_parser("drift-check", help="Show all source drift events")
    subparsers.add_parser("stats", help="Print aggregate statistics")

    args = parser.parse_args()

    if args.command == "init":
        with HashDB(args.db) as db:
            _log(f"Database ready: {args.db}")
            s = db.stats()
            _log(f"  {s['total_verifications']} verifications, "
                 f"{s['total_sources']} sources tracked")
        return

    if args.command == "store":
        results_path = Path(args.results)
        if not results_path.exists():
            _log(f"File not found: {results_path}")
            sys.exit(1)

        data = json.loads(results_path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            data = [data]

        # Import here to avoid circular dependency when used as library
        TOOLS_DIR = Path(__file__).parent
        REPO_ROOT = TOOLS_DIR.parent
        sys.path.insert(0, str(REPO_ROOT / "implementations" / "python"))
        sys.path.insert(0, str(TOOLS_DIR))

        from verify import VerificationResult, PassageMatch

        with HashDB(args.db) as db:
            for item in data:
                # Reconstruct a minimal VerificationResult from JSON dict
                pm = None
                if "passage_match" in item and item["passage_match"]:
                    pm_data = item["passage_match"]
                    pm = PassageMatch(
                        found=pm_data.get("found", False),
                        matched_text=pm_data.get("matched_text", ""),
                        char_start=pm_data.get("char_start", -1),
                        char_end=pm_data.get("char_end", -1),
                        context_before=pm_data.get("context_before", ""),
                        context_after=pm_data.get("context_after", ""),
                        match_type=pm_data.get("match_type", ""),
                        similarity=pm_data.get("similarity", 0.0),
                    )

                result = VerificationResult(
                    citation_id=item["citation_id"],
                    source_title=item.get("source_title", ""),
                    status=item["status"],
                    internal_hash_valid=item.get("internal_hash_valid", False),
                    source_hash_valid=item.get("source_hash_valid"),
                    source_hash_recomputed=item.get("source_hash_recomputed", ""),
                    passage_match=pm,
                    source_url=item.get("source_url", ""),
                    fetch_error=item.get("fetch_error", ""),
                    conformance_level=item.get("conformance_level", 0),
                    relation=item.get("relation", ""),
                    page_ref=item.get("page_ref", ""),
                    captured_by=item.get("captured_by", ""),
                    warnings=item.get("warnings", []),
                )
                db.store_result(result, input_file=args.input_file)

            _log(f"Stored {len(data)} result(s) in {args.db}")
        return

    if args.command == "check":
        with HashDB(args.db) as db:
            result = db.latest_result(args.citation_id)
            if not result:
                _log(f"No results found for {args.citation_id}")
                sys.exit(1)
            print(json.dumps(result, indent=2, default=str))
        return

    if args.command == "drift-check":
        with HashDB(args.db) as db:
            report = db.drift_report()
            if not report:
                print("No source drift detected.")
                return
            for event in report:
                print(f"  URL: {event['url']}")
                print(f"    Old hash: {event['old_hash']}")
                print(f"    New hash: {event['new_hash']}")
                print(f"    Detected: {event['detected_at']}")
                affected = event.get("affected_citations", [])
                if affected:
                    print(f"    Affected: {', '.join(affected)}")
                print()
        return

    if args.command == "stats":
        with HashDB(args.db) as db:
            s = db.stats()
            print(f"Verifications: {s['total_verifications']}")
            if s["by_status"]:
                for status, count in sorted(s["by_status"].items()):
                    print(f"  {status}: {count}")
            print(f"Sources tracked: {s['total_sources']}")
            print(f"Sources with drift: {s['sources_with_drift']}")
            print(f"Total drift events: {s['total_drift_events']}")
            if s["last_verification"]:
                print(f"Last verification: {s['last_verification']}")
        return


if __name__ == "__main__":
    main()

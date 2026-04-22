"""Fetch source metadata from CrossRef and Unpaywall APIs."""

import json
import re
import urllib.request
import urllib.parse
import urllib.error
from dataclasses import dataclass
from typing import Optional

CROSSREF_API = "https://api.crossref.org/works"
UNPAYWALL_API = "https://api.unpaywall.org/v2"
USER_AGENT = (
    "VCITE-enhance/0.1 (https://github.com/graziul/vcite; mailto:vcite@idep.pub)"
)

# Timeout for all HTTP requests (seconds)
REQUEST_TIMEOUT = 10

# Parse "(Author & Author, Year)" or "(Author et al., Year)" or "(ACRONYM, Year)"
_CITE_HINT_RE = re.compile(
    r"([A-Z][A-Za-z]+(?:\s(?:&|and)\s[A-Z][A-Za-z]+)*"
    r"(?:\s(?:et\s+al\.?))?)"
    r",?\s*(\d{4})[a-z]?"
)
_DOI_RE = re.compile(r"(10\.\d{4,}/[^\s,;)\"']+)")


@dataclass
class SourceMetadata:
    """Metadata fetched from external APIs."""

    title: str
    authors: list[str]
    year: Optional[int]
    doi: Optional[str]
    url: Optional[str]
    venue: Optional[str]
    source_type: str  # academic, journalism, web, grey
    oa_url: Optional[str] = None  # Open access full-text URL from Unpaywall
    archive_url: Optional[str] = None  # Wayback Machine / Perma.cc snapshot


def _make_request(url: str) -> Optional[dict]:
    """Make an HTTP GET request with polite headers and return parsed JSON."""
    req = urllib.request.Request(url)
    req.add_header("User-Agent", USER_AGENT)
    req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw)
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError,
            TimeoutError, OSError):
        return None


def _parse_crossref_item(item: dict) -> SourceMetadata:
    """Parse a CrossRef work item into SourceMetadata."""
    # Title
    titles = item.get("title", [])
    title = titles[0] if titles else "Unknown"

    # Authors
    authors = []
    for a in item.get("author", []):
        family = a.get("family", "")
        given = a.get("given", "")
        if family:
            authors.append(f"{family}, {given}".strip(", "))

    # Year from published-print or published-online or issued
    year = None
    for date_field in ("published-print", "published-online", "issued"):
        date_parts = item.get(date_field, {}).get("date-parts", [[]])
        if date_parts and date_parts[0] and date_parts[0][0]:
            year = int(date_parts[0][0])
            break

    # DOI
    doi = item.get("DOI")

    # URL
    url = f"https://doi.org/{doi}" if doi else item.get("URL")

    # Venue: container-title
    containers = item.get("container-title", [])
    venue = containers[0] if containers else None

    # Source type heuristic
    item_type = item.get("type", "")
    if item_type in ("journal-article", "proceedings-article", "book-chapter"):
        source_type = "academic"
    elif item_type in ("report", "monograph"):
        source_type = "grey"
    else:
        source_type = "academic"

    return SourceMetadata(
        title=title,
        authors=authors,
        year=year,
        doi=doi,
        url=url,
        venue=venue,
        source_type=source_type,
    )


def fetch_crossref(doi: str) -> Optional[SourceMetadata]:
    """Fetch metadata from CrossRef API for a given DOI."""
    clean_doi = doi.strip().removeprefix("https://doi.org/")
    encoded = urllib.parse.quote(clean_doi, safe="/")
    url = f"{CROSSREF_API}/{encoded}"
    data = _make_request(url)
    if not data or "message" not in data:
        return None
    return _parse_crossref_item(data["message"])


def search_crossref(
    query: str, author: str = "", year: int = 0
) -> Optional[SourceMetadata]:
    """Search CrossRef by title/author/year when DOI is unknown.

    Returns the best match if the CrossRef confidence score is reasonable.
    """
    params: dict[str, str] = {"query": query, "rows": "3"}
    if author:
        params["query.author"] = author
    if year:
        params["filter"] = f"from-pub-date:{year},until-pub-date:{year}"
    url = f"{CROSSREF_API}?{urllib.parse.urlencode(params)}"
    data = _make_request(url)
    if not data or "message" not in data:
        return None

    items = data["message"].get("items", [])
    if not items:
        return None

    # Take the first (highest-score) result
    best = items[0]
    score = best.get("score", 0)
    # CrossRef scores vary widely; accept anything above a low threshold
    if score < 1.0:
        return None

    metadata = _parse_crossref_item(best)

    # If we searched by year and the result year doesn't match, reject
    if year and metadata.year and abs(metadata.year - year) > 1:
        return None

    return metadata


def fetch_unpaywall(doi: str, email: str = "vcite@idep.pub") -> Optional[str]:
    """Get open access URL from Unpaywall for a DOI.

    Returns the best OA location URL, or None.
    """
    clean_doi = doi.strip().removeprefix("https://doi.org/")
    encoded = urllib.parse.quote(clean_doi, safe="/")
    url = f"{UNPAYWALL_API}/{encoded}?email={urllib.parse.quote(email)}"
    data = _make_request(url)
    if not data:
        return None

    # Best OA location
    best = data.get("best_oa_location")
    if best:
        return best.get("url_for_pdf") or best.get("url") or best.get("url_for_landing_page")
    return None


def resolve_citation(hint: str) -> Optional[SourceMetadata]:
    """Try to resolve a citation hint like '(Smith, 2020)' to metadata.

    Strategy:
    1. If hint contains a DOI, fetch directly from CrossRef
    2. Otherwise, parse author/year and search CrossRef
    3. If DOI found, also check Unpaywall for OA URL
    """
    # Strip parentheses from hint
    hint = hint.strip().strip("()")

    # 1. Check for DOI
    doi_match = _DOI_RE.search(hint)
    if doi_match:
        doi = doi_match.group(1)
        metadata = fetch_crossref(doi)
        if metadata and metadata.doi:
            oa_url = fetch_unpaywall(metadata.doi)
            if oa_url:
                metadata.oa_url = oa_url
        return metadata

    # 2. Parse author/year
    cite_match = _CITE_HINT_RE.search(hint)
    if not cite_match:
        return None

    author_str = cite_match.group(1)
    year = int(cite_match.group(2))

    # Extract first author's last name for search
    first_author = author_str.split("&")[0].split(" and ")[0].strip()
    # Remove "et al." if present
    first_author = re.sub(r"\s+et\s+al\.?", "", first_author).strip()

    # Search CrossRef
    metadata = search_crossref(
        query=f"{first_author} {year}",
        author=first_author,
        year=year,
    )

    # 3. If we got a DOI, check Unpaywall
    if metadata and metadata.doi:
        oa_url = fetch_unpaywall(metadata.doi)
        if oa_url:
            metadata.oa_url = oa_url

    return metadata

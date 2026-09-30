"""Column detection and number parsing.

The exact column headers of the two exports are not published by either vendor, so columns are
found by alias (case and punctuation ignored) and can always be set by hand with --gsc-col and
--bing-col.
"""
import re

ROLES = ("page", "query", "impressions", "citations", "share", "date", "country", "device")

_ALIASES = {
    "page": {
        "page", "pages", "url", "urls", "pageurl", "pageurls", "toppage", "toppages",
        "citedpage", "citedpages", "citedurl", "citedurls", "topcitedpages", "landingpage",
        "landingpages",
    },
    "query": {
        "groundingquery", "groundingqueries", "query", "queries", "topquery", "topqueries",
        "groundingphrase", "groundingphrases", "groundingquerytext", "phrase", "phrases",
        "topgroundingqueries",
    },
    "impressions": {"impressions", "impression", "aiimpressions", "totalimpressions"},
    "citations": {
        "citations", "citation", "totalcitations", "citationcount", "citationscount",
        "timescited", "citedcount",
    },
    "share": {"citationshare", "share"},
    "date": {"date", "dates", "day", "days"},
    "country": {"country", "countries"},
    "device": {"device", "devices"},
}

# How many leading rows to scan for the header row (exports may carry title rows).
HEADER_SCAN_ROWS = 10


def norm(header):
    return re.sub(r"[^a-z0-9]", "", str(header).lower())


def parse_overrides(pairs):
    """['page=Top pages', 'citations=Cites'] -> {'page': 'toppages', ...}"""
    out = {}
    for p in pairs or []:
        if "=" not in p:
            raise ValueError(f"column override must look like role=Header, got {p!r}")
        role, header = p.split("=", 1)
        role = role.strip().lower()
        if role not in ROLES:
            raise ValueError(f"unknown column role {role!r}; use one of {', '.join(ROLES)}")
        out[role] = norm(header)
    return out


def map_header(header_row, overrides=None):
    """Return {role: column index} for one candidate header row."""
    overrides = overrides or {}
    normed = [norm(h) for h in header_row]
    cols = {}
    for role in ROLES:
        want = overrides.get(role)
        for i, h in enumerate(normed):
            if not h:
                continue
            if (want is not None and h == want) or (want is None and h in _ALIASES[role]):
                cols[role] = i
                break
    return cols


def locate_header(rows, overrides=None):
    """Find the header row. Returns (index, {role: col}) or (None, {})."""
    for i, row in enumerate(rows[:HEADER_SCAN_ROWS]):
        cols = map_header(row, overrides)
        if len(cols) >= 2:
            return i, cols
    return None, {}


_EMPTY = {"", "~", "-", "\u2013", "\u2014", "n/a", "na", "null"}


def parse_number(text):
    """Parse an export cell. Google writes '~' and '-' for tiny or missing values, which its
    help page says become zero in downloaded files, so they count as 0. Returns None when the
    cell is text that is not a number."""
    s = str(text).strip().lower().replace("\u00a0", "").replace("\u202f", "")
    if s in _EMPTY:
        return 0
    s = s.rstrip("%").replace(",", "").replace(" ", "")
    try:
        f = float(s)
    except ValueError:
        return None
    return int(f) if f == int(f) else f


def kind_of(cols):
    """Classify a table by the roles it has."""
    if "page" in cols and "impressions" in cols:
        return "gsc-pages"
    if "page" in cols and "query" in cols:
        return "bing-pairs"
    if "page" in cols and "citations" in cols:
        return "bing-pages"
    if "query" in cols:
        return "bing-queries"
    return "other"

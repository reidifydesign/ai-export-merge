"""Join the two exports per page.

Google's report gives impressions per page. Bing's gives citations per page and, separately,
the grounding queries. The join is Google impressions beside Bing citations and queries. They
are different measures from different systems and are never added or divided.
"""
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .columns import kind_of, locate_header, parse_number
from .urls import bare_host, normalize


class MergeError(Exception):
    pass


@dataclass
class Analysed:
    name: str
    kind: str
    cols: dict
    header: list
    body: list


def analyse(tables, overrides=None):
    out = []
    for t in tables:
        idx, cols = locate_header(t.rows, overrides)
        if idx is None:
            out.append(Analysed(t.name, "other", {}, t.rows[0] if t.rows else [], []))
        else:
            out.append(Analysed(t.name, kind_of(cols), cols, t.rows[idx], t.rows[idx + 1:]))
    return out


def describe(analysed):
    lines = [f"  {a.name}: {a.kind}, columns {a.header}" for a in analysed]
    return "\n".join(lines) or "  (no tables)"


def _pick(analysed, kinds, table_filter):
    chosen = [a for a in analysed if a.kind in kinds]
    if table_filter:
        chosen = [a for a in chosen if table_filter.lower() in a.name.lower()]
    return chosen


@dataclass
class Result:
    pages: list = field(default_factory=list)
    summary: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)
    queries_without_page: list = field(default_factory=list)


class _Keys:
    """Collects page keys, their display form and hosts, and applies the --site filter."""

    def __init__(self, site):
        self.site = bare_host(site) if site else None
        self.display = {}
        self.hosts = Counter()
        self.dropped = 0

    def get(self, raw):
        n = normalize(raw, self.site)
        if n is None:
            return None
        key, display, host = n
        if self.site and host and host != self.site:
            self.dropped += 1
            return None
        self.display.setdefault(key, display)
        if host:
            self.hosts[host] += 1
        return key


def _cell(row, cols, role):
    i = cols.get(role)
    return row[i] if i is not None and i < len(row) else ""


def merge(gsc_tables, bing_tables, site=None, top_queries=5, gsc_over=None, bing_over=None,
          gsc_filter=None, bing_filter=None):
    gsc = analyse(gsc_tables, gsc_over)
    bing = analyse(bing_tables, bing_over)
    res = Result()
    keys = _Keys(site)
    bad = 0

    g_used = _pick(gsc, {"gsc-pages"}, gsc_filter)
    if not g_used:
        raise MergeError("no Search Console table with a page column and an impressions column.\n"
                         "Tables read:\n" + describe(gsc) +
                         "\nSet the columns by hand, for example --gsc-col page=\"Top pages\".")
    b_pages = _pick(bing, {"bing-pages"}, bing_filter)
    b_pairs = _pick(bing, {"bing-pairs"}, bing_filter)
    b_queries = _pick(bing, {"bing-queries"}, bing_filter)
    if not (b_pages or b_pairs):
        raise MergeError("no Bing table with a page column plus a citations or query column.\n"
                         "Tables read:\n" + describe(bing) +
                         "\nSet the columns by hand, for example --bing-col page=\"Cited URL\".")
    for label, used in (("Search Console page tables", g_used), ("Bing cited-page tables", b_pages),
                        ("Bing query-to-page tables", b_pairs)):
        if len(used) > 1:
            res.warnings.append(f"{len(used)} {label} were read ({', '.join(a.name for a in used)}) and "
                                "their rows are summed. Use --gsc-table or --bing-table to pick one.")

    def number(text):
        nonlocal bad
        n = parse_number(text)
        if n is None:
            bad += 1
            return 0
        return n

    impressions = defaultdict(int)
    g_rows = 0
    for a in g_used:
        for row in a.body:
            k = keys.get(_cell(row, a.cols, "page"))
            if k is None:
                continue
            g_rows += 1
            impressions[k] += number(_cell(row, a.cols, "impressions"))

    page_cites = defaultdict(int)
    for a in b_pages:
        for row in a.body:
            k = keys.get(_cell(row, a.cols, "page"))
            if k is None:
                continue
            page_cites[k] += number(_cell(row, a.cols, "citations")) if "citations" in a.cols else 1

    pair_cites = defaultdict(int)
    per_page_queries = defaultdict(lambda: defaultdict(int))
    query_label = {}
    for a in b_pairs:
        for row in a.body:
            k = keys.get(_cell(row, a.cols, "page"))
            q = _cell(row, a.cols, "query").strip()
            if k is None or not q:
                continue
            c = number(_cell(row, a.cols, "citations")) if "citations" in a.cols else 1
            pair_cites[k] += c
            per_page_queries[k][q.lower()] += c
            query_label.setdefault(q.lower(), q)

    loose = defaultdict(int)
    for a in b_queries:
        for row in a.body:
            q = _cell(row, a.cols, "query").strip()
            if q:
                loose[q] += number(_cell(row, a.cols, "citations")) if "citations" in a.cols else 1

    bing_keys = set(page_cites) | set(pair_cites)
    for k in sorted(set(impressions) | bing_keys):
        in_g, in_b = k in impressions, k in bing_keys
        basis = "" if not in_b else ("page-table" if k in page_cites else "sum-of-query-rows")
        qs = sorted(per_page_queries.get(k, {}).items(), key=lambda kv: (-kv[1], kv[0]))
        res.pages.append({
            "url": keys.display[k],
            "status": "both" if in_g and in_b else ("google-only" if in_g else "bing-only"),
            "gsc_impressions": impressions[k] if in_g else None,
            "bing_citations": (page_cites[k] if k in page_cites else pair_cites[k]) if in_b else None,
            "bing_citations_basis": basis,
            "bing_grounding_queries": len(qs),
            "top_grounding_queries": [{"query": query_label[q], "citations": c} for q, c in qs[:top_queries]],
        })
    paired = {q for qs in per_page_queries.values() for q in qs}
    res.queries_without_page = [{"query": q, "citations": c}
                                for q, c in sorted(loose.items(), key=lambda kv: (-kv[1], kv[0]))
                                if q.lower() not in paired]

    if len(keys.hosts) > 1 and not keys.site:
        hosts = ", ".join(f"{h} ({n})" for h, n in keys.hosts.most_common(5))
        res.warnings.append(f"URLs from {len(keys.hosts)} hosts were joined together: {hosts}. "
                            "Use --site to keep one host.")
    if keys.dropped:
        res.warnings.append(f"{keys.dropped} rows on a host other than {keys.site} were left out.")
    if bad:
        res.warnings.append(f"{bad} cells were not numbers and counted as 0.")
    if any(p["bing_citations_basis"] == "sum-of-query-rows" for p in res.pages):
        res.warnings.append("Some Bing citation totals are the sum of query-to-page rows, because no "
                            "cited-page total was given for them. See bing_citations_basis.")

    both = [p for p in res.pages if p["status"] == "both"]
    g_only = [p for p in res.pages if p["status"] == "google-only"]
    b_only = [p for p in res.pages if p["status"] == "bing-only"]
    res.summary = {
        "pages": len(res.pages),
        "in_both": len(both),
        "google_only": len(g_only),
        "bing_only": len(b_only),
        "gsc_impressions": sum(p["gsc_impressions"] or 0 for p in res.pages),
        "bing_citations": sum(p["bing_citations"] or 0 for p in res.pages),
        "impressions_on_pages_bing_does_not_cite": sum(p["gsc_impressions"] for p in g_only),
        "citations_on_pages_google_shows_no_impressions_for": sum(p["bing_citations"] for p in b_only),
        "grounding_queries_without_page": len(res.queries_without_page),
        "gsc_rows_read": g_rows,
    }
    return res


def sort_pages(pages, how):
    def n(v):
        return -(v or 0)

    if how == "impressions":
        return sorted(pages, key=lambda p: (n(p["gsc_impressions"]), n(p["bing_citations"]), p["url"]))
    if how == "citations":
        return sorted(pages, key=lambda p: (n(p["bing_citations"]), n(p["gsc_impressions"]), p["url"]))
    if how == "status":
        order = {"both": 0, "google-only": 1, "bing-only": 2}
        return sorted(pages, key=lambda p: (order[p["status"]], n(p["gsc_impressions"]),
                                            n(p["bing_citations"]), p["url"]))
    return sorted(pages, key=lambda p: p["url"])

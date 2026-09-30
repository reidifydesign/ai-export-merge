"""Output formats: terminal table, CSV, JSON, Markdown."""
import csv
import io
import json


def _num(v):
    return "" if v is None else f"{v:,}" if isinstance(v, int) else f"{v:,.2f}"


def _short(url, n):
    u = url.split("://", 1)[-1]
    return u if len(u) <= n else u[: n - 3] + "..."


def _queries(p, n=None):
    qs = p["top_grounding_queries"][:n] if n else p["top_grounding_queries"]
    return " | ".join(q["query"] for q in qs)


def summary_lines(s):
    return [
        f"{s['pages']} pages: {s['in_both']} in both exports, {s['google_only']} Google only, {s['bing_only']} Bing only.",
        f"Google impressions {s['gsc_impressions']:,} (on Bing-uncited pages: {s['impressions_on_pages_bing_does_not_cite']:,}). "
        f"Bing citations {s['bing_citations']:,} (on pages with no Google impressions: "
        f"{s['citations_on_pages_google_shows_no_impressions_for']:,}).",
        "Impressions and citations are different measures. They are shown side by side, never added.",
    ]


def as_table(res, pages, limit=None):
    shown = pages[:limit] if limit else pages
    rows = [("PAGE", "GOOGLE IMPR", "BING CITES", "STATUS", "TOP GROUNDING QUERIES (BING)")]
    for p in shown:
        rows.append((_short(p["url"], 40), _num(p["gsc_impressions"]) or "-", _num(p["bing_citations"]) or "-",
                     p["status"], _short(_queries(p, 2), 46) if p["top_grounding_queries"] else ""))
    w = [max(len(r[i]) for r in rows) for i in range(5)]
    out = []
    for n, r in enumerate(rows):
        out.append("  ".join([r[0].ljust(w[0]), r[1].rjust(w[1]), r[2].rjust(w[2]), r[3].ljust(w[3]), r[4]]).rstrip())
        if n == 0:
            out.append("  ".join("-" * x for x in w[:4]) + "  " + "-" * 28)
    if limit and len(pages) > limit:
        out.append(f"... {len(pages) - limit} more pages (use --limit 0 or -o file.csv for all)")
    return "\n".join(out + [""] + summary_lines(res.summary))


def as_csv(pages):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["url", "status", "gsc_impressions", "bing_citations", "bing_citations_basis",
                "bing_grounding_queries", "top_grounding_queries"])
    for p in pages:
        w.writerow([p["url"], p["status"], "" if p["gsc_impressions"] is None else p["gsc_impressions"],
                    "" if p["bing_citations"] is None else p["bing_citations"], p["bing_citations_basis"],
                    p["bing_grounding_queries"], _queries(p)])
    return buf.getvalue()


def as_json(res, pages):
    return json.dumps({"summary": res.summary, "warnings": res.warnings, "pages": pages,
                       "grounding_queries_without_page": res.queries_without_page},
                      indent=2, ensure_ascii=False) + "\n"


def as_markdown(res, pages):
    def esc(s):
        return str(s).replace("|", "\\|")

    lines = ["| Page | Google impressions | Bing citations | Status | Top grounding queries (Bing) |",
             "|---|---:|---:|---|---|"]
    for p in pages:
        lines.append(f"| {esc(p['url'])} | {_num(p['gsc_impressions'])} | {_num(p['bing_citations'])} | "
                     f"{p['status']} | {esc(_queries(p, 3))} |")
    return "\n".join(lines + [""] + [f"- {l}" for l in summary_lines(res.summary)]) + "\n"

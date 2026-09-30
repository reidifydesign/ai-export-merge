import argparse
import sys
from pathlib import Path

from . import __version__, render
from .columns import parse_overrides
from .merge import MergeError, analyse, merge, sort_pages
from .readers import ReadError, load_tables


def _parser():
    p = argparse.ArgumentParser(
        prog="ai-export-merge",
        description="Join a Search Console generative AI export and a Bing AI Performance export per page. "
                    "Runs locally and never uses the network.")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    m = sub.add_parser("merge", help="join the two exports")
    m.add_argument("gsc", help="Search Console export: a .csv or .xlsx file, a .zip, or a folder")
    m.add_argument("bing", nargs="+", help="Bing AI Performance export file(s) or folder(s)")
    m.add_argument("--site", help="keep one host, and give relative paths a host (example.com)")
    m.add_argument("--format", choices=["table", "csv", "json", "md"],
                   help="default: table on screen, or from the extension of -o")
    m.add_argument("-o", "--output", help="write the result to this file")
    m.add_argument("--sort", choices=["impressions", "citations", "status", "url"], default="impressions")
    m.add_argument("--limit", type=int, default=25, help="rows in the table view, 0 for all (default 25)")
    m.add_argument("--top-queries", type=int, default=5, help="grounding queries kept per page (default 5)")
    m.add_argument("--gsc-col", action="append", metavar="ROLE=HEADER", help="set a Search Console column by hand")
    m.add_argument("--bing-col", action="append", metavar="ROLE=HEADER", help="set a Bing column by hand")
    m.add_argument("--gsc-table", help="only use Search Console tables whose name contains this")
    m.add_argument("--bing-table", help="only use Bing tables whose name contains this")

    i = sub.add_parser("inspect", help="show the tables and columns found in a file, without merging")
    i.add_argument("paths", nargs="+")
    i.add_argument("--col", action="append", metavar="ROLE=HEADER", help="set a column by hand")
    return p


def _load_all(paths):
    tables = []
    for path in paths:
        tables += load_tables(path)
    return tables


def _inspect(args):
    over = parse_overrides(args.col)
    for path in args.paths:
        print(path)
        for a in analyse(load_tables(path), over):
            mapped = ", ".join(f'{r}="{a.header[i]}"' for r, i in a.cols.items()) or "no known columns"
            print(f"  {a.name}  [{a.kind}]  {len(a.body)} rows  {mapped}")
            if a.kind == "other":
                print(f"    headers: {a.header}")
    return 0


def _merge(args):
    g_over, b_over = parse_overrides(args.gsc_col), parse_overrides(args.bing_col)
    res = merge(load_tables(args.gsc), _load_all(args.bing), site=args.site, top_queries=args.top_queries,
                gsc_over=g_over, bing_over=b_over, gsc_filter=args.gsc_table, bing_filter=args.bing_table)
    pages = sort_pages(res.pages, args.sort)
    fmt = args.format or ({".csv": "csv", ".json": "json", ".md": "md"}.get(Path(args.output).suffix.lower())
                          if args.output else None) or "table"
    text = {"table": lambda: render.as_table(res, pages, args.limit or None) + "\n",
            "csv": lambda: render.as_csv(pages), "json": lambda: render.as_json(res, pages),
            "md": lambda: render.as_markdown(res, pages)}[fmt]()
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8", newline="")
        print(f"wrote {len(pages)} pages to {args.output}", file=sys.stderr)
        for l in render.summary_lines(res.summary)[:1]:
            print(l, file=sys.stderr)
    else:
        sys.stdout.write(text)
    for w in res.warnings:
        print(f"warning: {w}", file=sys.stderr)
    return 0


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    args = _parser().parse_args(argv)
    try:
        return _inspect(args) if args.cmd == "inspect" else _merge(args)
    except (ReadError, MergeError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

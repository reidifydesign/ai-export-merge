import contextlib
import csv
import io
import json
import tempfile
import unittest
from pathlib import Path

from ai_export_merge.cli import main

EX = Path(__file__).resolve().parent.parent / "examples"
GSC, BING = str(EX / "gsc"), str(EX / "bing")


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


class ExampleRun(unittest.TestCase):
    def test_table(self):
        code, out, err = run("merge", GSC, BING, "--site", "example.com")
        self.assertEqual(code, 0)
        self.assertIn("example.com/blog/what-is-aeo", out)
        self.assertIn("11 pages: 6 in both exports, 3 Google only, 2 Bing only.", out)
        self.assertIn("warning:", err)

    def test_json_numbers(self):
        code, out, _ = run("merge", GSC, BING, "--site", "example.com", "--format", "json")
        self.assertEqual(code, 0)
        data = json.loads(out)
        pages = {p["url"]: p for p in data["pages"]}
        aeo = pages["https://example.com/blog/what-is-aeo"]
        self.assertEqual((aeo["gsc_impressions"], aeo["bing_citations"], aeo["bing_grounding_queries"]), (1260, 74, 3))
        # the www/http/trailing-slash/utm variants in the Bing files joined to the Google URLs
        install = pages["https://example.com/docs/install"]
        self.assertEqual((install["gsc_impressions"], install["bing_citations"]), (388, 41))
        self.assertEqual(data["summary"]["gsc_impressions"], 5370)
        self.assertEqual(data["summary"]["bing_citations"], 199)
        self.assertEqual(data["grounding_queries_without_page"],
                         [{"query": "best answer engine optimization tools", "citations": 8}])
        self.assertEqual(pages["https://example.com/about"]["gsc_impressions"], 0)

    def test_csv_to_file_infers_format(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "merged.csv"
            code, stdout, err = run("merge", GSC, BING, "-o", str(out), "--sort", "url")
            self.assertEqual((code, stdout), (0, ""))
            with out.open(encoding="utf-8") as fh:
                rows = list(csv.DictReader(fh))
            self.assertEqual(len(rows), 11)
            self.assertEqual([r["url"] for r in rows], sorted(r["url"] for r in rows))
            self.assertEqual(rows[0].keys() >= {"url", "status", "gsc_impressions", "bing_citations"}, True)
            self.assertIn("wrote 11 pages", err)

    def test_markdown(self):
        code, out, _ = run("merge", GSC, BING, "--format", "md", "--site", "example.com")
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("| Page | Google impressions"))

    def test_limit(self):
        _, out, _ = run("merge", GSC, BING, "--site", "example.com", "--limit", "3")
        self.assertIn("... 8 more pages", out)

    def test_inspect(self):
        code, out, _ = run("inspect", GSC, BING)
        self.assertEqual(code, 0)
        self.assertIn("Pages  [gsc-pages]  9 rows", out)
        self.assertIn("Countries  [other]", out)
        self.assertIn("queries-by-page  [bing-pairs]", out)


class Errors(unittest.TestCase):
    def test_missing_file_is_a_message_not_a_traceback(self):
        code, out, err = run("merge", "nope.csv", BING)
        self.assertEqual(code, 2)
        self.assertIn("error: not found: nope.csv", err)

    def test_swapped_arguments_explain_themselves(self):
        code, _, err = run("merge", BING, GSC)
        self.assertEqual(code, 2)
        self.assertIn("Tables read", err)

    def test_bad_override(self):
        code, _, err = run("merge", GSC, BING, "--gsc-col", "page")
        self.assertEqual(code, 2)
        self.assertIn("role=Header", err)


if __name__ == "__main__":
    unittest.main()

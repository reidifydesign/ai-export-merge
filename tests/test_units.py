import unittest

from ai_export_merge.columns import kind_of, locate_header, map_header, parse_number, parse_overrides
from ai_export_merge.urls import bare_host, normalize


class Numbers(unittest.TestCase):
    def test_plain_and_grouped(self):
        self.assertEqual(parse_number("1,234"), 1234)
        self.assertEqual(parse_number(" 42 "), 42)
        self.assertEqual(parse_number("12.5%"), 12.5)

    def test_google_placeholders_are_zero(self):
        for s in ("~", "-", "", "–"):
            self.assertEqual(parse_number(s), 0)

    def test_text_is_none(self):
        self.assertIsNone(parse_number("lots"))


class Columns(unittest.TestCase):
    def test_aliases_ignore_case_and_punctuation(self):
        cols = map_header(["Top pages", "IMPRESSIONS"])
        self.assertEqual(cols, {"page": 0, "impressions": 1})
        self.assertEqual(map_header(["Grounding_Query", "Citation count"]), {"query": 0, "citations": 1})

    def test_override_wins(self):
        cols = map_header(["Cited asset", "Times seen"], parse_overrides(["page=Cited asset", "citations=Times seen"]))
        self.assertEqual(cols, {"page": 0, "citations": 1})

    def test_bad_override(self):
        with self.assertRaises(ValueError):
            parse_overrides(["nonsense"])
        with self.assertRaises(ValueError):
            parse_overrides(["colour=Red"])

    def test_header_below_title_rows(self):
        rows = [["Report for example.com"], ["Generated 2026-09-30"], ["Page", "Impressions"], ["/a", "3"]]
        idx, cols = locate_header(rows)
        self.assertEqual(idx, 2)
        self.assertEqual(kind_of(cols), "gsc-pages")

    def test_kinds(self):
        self.assertEqual(kind_of({"page": 0, "citations": 1}), "bing-pages")
        self.assertEqual(kind_of({"page": 0, "query": 1}), "bing-pairs")
        self.assertEqual(kind_of({"query": 0, "citations": 1}), "bing-queries")
        self.assertEqual(kind_of({"country": 0, "impressions": 1}), "other")


class Urls(unittest.TestCase):
    def key(self, u, site=None):
        return normalize(u, site)[0]

    def test_same_page_written_differently(self):
        a = "https://example.com/blog/post"
        for b in ("http://www.example.com/blog/post/", "HTTPS://Example.com/blog/post#intro",
                  "example.com/blog/post", "https://example.com:443/blog/post?utm_source=x&gclid=1"):
            self.assertEqual(self.key(a), self.key(b), b)

    def test_percent_encoding(self):
        self.assertEqual(self.key("https://example.com/a%20b"), self.key("https://example.com/a b"))

    def test_real_query_params_kept_and_sorted(self):
        self.assertEqual(self.key("https://example.com/p?b=2&a=1"), self.key("https://example.com/p?a=1&b=2"))
        self.assertNotEqual(self.key("https://example.com/p?a=1"), self.key("https://example.com/p"))

    def test_path_case_is_kept(self):
        self.assertNotEqual(self.key("https://example.com/A"), self.key("https://example.com/a"))

    def test_root(self):
        self.assertEqual(self.key("https://example.com"), self.key("https://www.example.com/"))

    def test_relative_paths(self):
        self.assertEqual(self.key("/docs", site="example.com"), self.key("https://example.com/docs"))
        k, display, host = normalize("/docs")
        self.assertEqual((host, display), ("", "/docs"))

    def test_empty(self):
        self.assertIsNone(normalize("  "))

    def test_bare_host(self):
        self.assertEqual(bare_host("https://www.Example.com/x"), "example.com")
        self.assertEqual(bare_host("example.com"), "example.com")


if __name__ == "__main__":
    unittest.main()

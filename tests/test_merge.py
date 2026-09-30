import unittest

from ai_export_merge.columns import parse_overrides
from ai_export_merge.merge import MergeError, merge, sort_pages

from helpers import t

G = t("Pages", ["Top pages", "Impressions"], ["https://example.com/a", 100], ["https://example.com/b/", 40],
      ["https://example.com/only-google", "~"])
B_PAGES = t("cited", ["Page", "Citations"], ["http://www.example.com/a", 7], ["https://example.com/b?utm_medium=x", 3],
            ["https://example.com/only-bing", 2])
B_PAIRS = t("pairs", ["Grounding query", "Page", "Citations"],
            ["what is a", "https://example.com/a", 4], ["How is a used", "https://example.com/a", 3],
            ["what is b", "https://example.com/b", 3], ["derived only", "https://example.com/pairs-only", 5])


def by_url(res):
    return {p["url"].split("://", 1)[-1]: p for p in res.pages}


class Join(unittest.TestCase):
    def setUp(self):
        self.res = merge([G], [B_PAGES, B_PAIRS])
        self.pages = by_url(self.res)

    def test_statuses(self):
        self.assertEqual(self.pages["example.com/a"]["status"], "both")
        self.assertEqual(self.pages["example.com/only-google"]["status"], "google-only")
        self.assertEqual(self.pages["example.com/only-bing"]["status"], "bing-only")

    def test_url_variants_join_and_numbers_match(self):
        a = self.pages["example.com/a"]
        self.assertEqual((a["gsc_impressions"], a["bing_citations"]), (100, 7))
        b = self.pages["example.com/b/"]
        self.assertEqual((b["gsc_impressions"], b["bing_citations"]), (40, 3))

    def test_tilde_is_zero_not_missing(self):
        self.assertEqual(self.pages["example.com/only-google"]["gsc_impressions"], 0)
        self.assertIsNone(self.pages["example.com/only-bing"]["gsc_impressions"])

    def test_queries_attach_sorted_with_original_case(self):
        qs = self.pages["example.com/a"]["top_grounding_queries"]
        self.assertEqual([q["query"] for q in qs], ["what is a", "How is a used"])
        self.assertEqual(self.pages["example.com/a"]["bing_grounding_queries"], 2)

    def test_citation_basis_is_labelled(self):
        self.assertEqual(self.pages["example.com/a"]["bing_citations_basis"], "page-table")
        derived = self.pages["example.com/pairs-only"]
        self.assertEqual((derived["bing_citations"], derived["bing_citations_basis"]), (5, "sum-of-query-rows"))
        self.assertTrue(any("sum of query-to-page rows" in w for w in self.res.warnings))

    def test_summary(self):
        s = self.res.summary
        self.assertEqual((s["pages"], s["in_both"], s["google_only"], s["bing_only"]), (5, 2, 1, 2))
        self.assertEqual(s["gsc_impressions"], 140)
        self.assertEqual(s["impressions_on_pages_bing_does_not_cite"], 0)
        self.assertEqual(s["citations_on_pages_google_shows_no_impressions_for"], 7)

    def test_top_queries_limit(self):
        res = merge([G], [B_PAGES, B_PAIRS], top_queries=1)
        self.assertEqual(len(by_url(res)["example.com/a"]["top_grounding_queries"]), 1)


class Rows(unittest.TestCase):
    def test_duplicate_rows_are_summed(self):
        g = t("p", ["Page", "Impressions"], ["/a", 5], ["/a/", 6])
        b = t("b", ["Page", "Citations"], ["/a", 1], ["/a", 2])
        res = merge([g], [b], site="example.com")
        self.assertEqual((res.pages[0]["gsc_impressions"], res.pages[0]["bing_citations"]), (11, 3))

    def test_site_filter_drops_other_hosts_and_fills_relative(self):
        g = t("p", ["Page", "Impressions"], ["https://example.com/a", 5], ["https://other.org/z", 9])
        b = t("b", ["Page", "Citations"], ["/a", 2])
        res = merge([g], [b], site="https://www.example.com")
        self.assertEqual(len(res.pages), 1)
        self.assertEqual(res.pages[0]["status"], "both")
        self.assertTrue(any("other than example.com" in w for w in res.warnings))

    def test_mixed_hosts_warn_without_site(self):
        g = t("p", ["Page", "Impressions"], ["https://example.com/a", 5], ["https://other.org/z", 9])
        b = t("b", ["Page", "Citations"], ["https://example.com/a", 2])
        self.assertTrue(any("2 hosts" in w for w in merge([g], [b]).warnings))

    def test_non_numbers_are_counted(self):
        g = t("p", ["Page", "Impressions"], ["/a", "many"])
        b = t("b", ["Page", "Citations"], ["/a", 1])
        res = merge([g], [b], site="example.com")
        self.assertEqual(res.pages[0]["gsc_impressions"], 0)
        self.assertTrue(any("1 cells were not numbers" in w for w in res.warnings))

    def test_loose_queries_exclude_those_already_joined(self):
        loose = t("q", ["Grounding query", "Citations"], ["what is a", 4], ["unmapped query", 8])
        res = merge([G], [B_PAGES, B_PAIRS, loose])
        self.assertEqual(res.queries_without_page, [{"query": "unmapped query", "citations": 8}])

    def test_pairs_without_citation_column_count_rows(self):
        pairs = t("p", ["Grounding query", "Page"], ["q1", "/a"], ["q2", "/a"])
        res = merge([t("g", ["Page", "Impressions"], ["/a", 3])], [pairs], site="example.com")
        self.assertEqual(res.pages[0]["bing_citations"], 2)


class Failures(unittest.TestCase):
    def test_no_gsc_table_explains_itself(self):
        with self.assertRaises(MergeError) as ctx:
            merge([t("countries", ["Country", "Impressions"], ["India", 1])], [B_PAGES])
        self.assertIn("countries", str(ctx.exception))
        self.assertIn("--gsc-col", str(ctx.exception))

    def test_no_bing_page_table(self):
        with self.assertRaises(MergeError) as ctx:
            merge([G], [t("q", ["Grounding query", "Citations"], ["x", 1])])
        self.assertIn("--bing-col", str(ctx.exception))

    def test_override_rescues_unknown_headers(self):
        g = t("g", ["Landing", "Seen"], ["/a", 4])
        b = t("b", ["Cited asset", "Hits"], ["/a", 2])
        with self.assertRaises(MergeError):
            merge([g], [b], site="example.com")
        res = merge([g], [b], site="example.com",
                    gsc_over=parse_overrides(["page=Landing", "impressions=Seen"]),
                    bing_over=parse_overrides(["page=Cited asset", "citations=Hits"]))
        self.assertEqual((res.pages[0]["gsc_impressions"], res.pages[0]["bing_citations"]), (4, 2))

    def test_table_filter_avoids_double_counting(self):
        a = t("Pages-2026-08", ["Page", "Impressions"], ["/a", 5])
        b = t("Pages-2026-09", ["Page", "Impressions"], ["/a", 7])
        bing = t("b", ["Page", "Citations"], ["/a", 1])
        both = merge([a, b], [bing], site="example.com")
        self.assertEqual(both.pages[0]["gsc_impressions"], 12)
        self.assertTrue(any("rows are summed" in w for w in both.warnings))
        one = merge([a, b], [bing], site="example.com", gsc_filter="2026-09")
        self.assertEqual(one.pages[0]["gsc_impressions"], 7)


class Sorting(unittest.TestCase):
    def test_orders(self):
        pages = merge([G], [B_PAGES, B_PAIRS]).pages
        self.assertEqual(sort_pages(pages, "impressions")[0]["url"], "https://example.com/a")
        self.assertEqual(sort_pages(pages, "citations")[0]["url"], "https://example.com/a")
        self.assertEqual([p["status"] for p in sort_pages(pages, "status")][:2], ["both", "both"])
        urls = [p["url"] for p in sort_pages(pages, "url")]
        self.assertEqual(urls, sorted(urls))


if __name__ == "__main__":
    unittest.main()

import codecs
import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from ai_export_merge.readers import ReadError, load_tables, parse_csv

from helpers import make_xlsx


class Csv(unittest.TestCase):
    def test_delimiters(self):
        self.assertEqual(parse_csv("a,b\n1,2\n"), [["a", "b"], ["1", "2"]])
        self.assertEqual(parse_csv("a;b\n1;2\n"), [["a", "b"], ["1", "2"]])
        self.assertEqual(parse_csv("a\tb\n1\t2\n"), [["a", "b"], ["1", "2"]])

    def test_quoted_commas_and_blank_rows(self):
        self.assertEqual(parse_csv('q,n\n"a, b",3\n\n,,\n'), [["q", "n"], ["a, b", "3"]])


class Files(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_utf8_bom_and_utf16(self):
        (self.dir / "a.csv").write_bytes(codecs.BOM_UTF8 + "Page,Impressions\n/x,1\n".encode())
        (self.dir / "b.csv").write_bytes("Page,Impressions\n/y,2\n".encode("utf-16"))
        self.assertEqual(load_tables(self.dir / "a.csv")[0].rows[0], ["Page", "Impressions"])
        self.assertEqual(load_tables(self.dir / "b.csv")[0].rows[1], ["/y", "2"])

    def test_xlsx_sheets(self):
        data = make_xlsx({"Pages": [["Top pages", "Impressions"], ["/a", 10], ["/b", 5]],
                          "Countries": [["Country", "Impressions"], ["India", 9]]})
        (self.dir / "export.xlsx").write_bytes(data)
        tables = load_tables(self.dir / "export.xlsx")
        self.assertEqual([t.name for t in tables], ["export:Pages", "export:Countries"])
        self.assertEqual(tables[0].rows, [["Top pages", "Impressions"], ["/a", "10"], ["/b", "5"]])

    def test_zip_of_csvs(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("Pages.csv", "Page,Impressions\n/a,1\n")
            z.writestr("Dates.csv", "Date,Impressions\n2026-09-01,1\n")
            z.writestr("__MACOSX/Pages.csv", "junk")
            z.writestr("notes.md", "ignored")
        (self.dir / "export.zip").write_bytes(buf.getvalue())
        self.assertEqual([t.name for t in load_tables(self.dir / "export.zip")], ["export/Dates", "export/Pages"])

    def test_zip_holding_xlsx(self):
        (self.dir / "sheet.zip").write_bytes(make_xlsx({"S": [["Page", "Impressions"], ["/a", 1]]}))
        self.assertEqual(load_tables(self.dir / "sheet.zip")[0].rows[1], ["/a", "1"])

    def test_folder_is_sorted_and_recursive(self):
        (self.dir / "sub").mkdir()
        (self.dir / "b.csv").write_text("Page,Citations\n/b,2\n", encoding="utf-8")
        (self.dir / "sub" / "a.csv").write_text("Page,Citations\n/a,1\n", encoding="utf-8")
        (self.dir / "readme.txt").write_text("skip me", encoding="utf-8")
        self.assertEqual([t.name for t in load_tables(self.dir)], ["b", "a"])

    def test_errors(self):
        with self.assertRaises(ReadError):
            load_tables(self.dir / "missing.csv")
        with self.assertRaises(ReadError):
            load_tables(self.dir)  # empty folder
        (self.dir / "bad.xlsx").write_bytes(b"not a workbook")
        with self.assertRaises(ReadError):
            load_tables(self.dir / "bad.xlsx")


if __name__ == "__main__":
    unittest.main()

"""Read CSV, XLSX, ZIP and folders of them into plain tables. Standard library only."""
import codecs
import csv
import io
import posixpath
import re
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_PKG_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
_EXTS = {".csv", ".tsv", ".xlsx", ".zip"}


class ReadError(Exception):
    pass


@dataclass
class Table:
    name: str
    rows: list = field(default_factory=list)  # list of list[str], header row included


def decode(data):
    if data.startswith(codecs.BOM_UTF8):
        return data[3:].decode("utf-8")
    if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return data.decode("utf-16")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def parse_csv(text):
    first = next((l for l in text.splitlines() if l.strip()), "")
    delim = max(",;\t", key=first.count) if first else ","
    rows = [[c.strip() for c in r] for r in csv.reader(io.StringIO(text), delimiter=delim)]
    return [r for r in rows if any(c for c in r)]


def _col_index(ref):
    letters = re.match(r"[A-Z]+", ref).group(0)
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n - 1


def read_xlsx(data, stem):
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            shared = ["".join(t.text or "" for t in si.iter(_MAIN + "t")) for si in root.iter(_MAIN + "si")]
        rels = {}
        for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels")).iter(_PKG_REL + "Relationship"):
            target = r.get("Target")
            rels[r.get("Id")] = target.lstrip("/") if target.startswith("/") else posixpath.join("xl", target)
        tables = []
        for sheet in ET.fromstring(z.read("xl/workbook.xml")).iter(_MAIN + "sheet"):
            path = rels.get(sheet.get(_REL + "id"))
            if not path or path not in z.namelist():
                continue
            rows = []
            for row in ET.fromstring(z.read(path)).iter(_MAIN + "row"):
                cells = {}
                for c in row.iter(_MAIN + "c"):
                    t = c.get("t")
                    if t == "inlineStr":
                        val = "".join(x.text or "" for x in c.iter(_MAIN + "t"))
                    else:
                        v = c.find(_MAIN + "v")
                        val = "" if v is None or v.text is None else v.text
                        if t == "s" and val != "":
                            val = shared[int(val)]
                    cells[_col_index(c.get("r"))] = val.strip()
                if cells:
                    line = [cells.get(i, "") for i in range(max(cells) + 1)]
                    if any(line):
                        rows.append(line)
            tables.append(Table(f"{stem}:{sheet.get('name')}", rows))
        return tables
    except (zipfile.BadZipFile, KeyError, ET.ParseError, ValueError) as e:
        raise ReadError(f"{stem}: could not read as .xlsx ({e})") from e


def _from_bytes(name, data):
    stem = Path(name).stem
    ext = Path(name).suffix.lower()
    if data[:2] == b"PK":
        z = zipfile.ZipFile(io.BytesIO(data))
        if ext == ".xlsx" or "xl/workbook.xml" in z.namelist():
            return read_xlsx(data, stem)
        out = []
        for member in sorted(z.namelist()):
            if member.endswith("/") or "__MACOSX" in member or Path(member).suffix.lower() not in _EXTS - {".zip"}:
                continue
            for tb in _from_bytes(Path(member).name, z.read(member)):
                tb.name = f"{stem}/{tb.name}"
                out.append(tb)
        return out
    if ext == ".xlsx":
        raise ReadError(f"{name}: not a valid .xlsx file")
    return [Table(stem, parse_csv(decode(data)))]


def load_tables(path):
    """Every table found in a file or folder. A folder is read recursively, sorted by name."""
    p = Path(path)
    if not p.exists():
        raise ReadError(f"not found: {path}")
    if p.is_dir():
        tables = []
        for f in sorted(x for x in p.rglob("*") if x.is_file() and x.suffix.lower() in _EXTS):
            tables += _from_bytes(f.name, f.read_bytes())
        if not tables:
            raise ReadError(f"no .csv, .tsv, .xlsx or .zip files in {path}")
        return tables
    return _from_bytes(p.name, p.read_bytes())

"""URL normalisation, so the same page written two ways joins as one row."""
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit

_TRACKING = {"gclid", "fbclid", "msclkid", "mc_cid", "mc_eid", "dclid", "yclid"}


def bare_host(site):
    """'https://www.Example.com/' -> 'example.com'"""
    s = site.strip()
    if "//" not in s:
        s = "//" + s
    host = (urlsplit(s).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def normalize(raw, site=None):
    """Return (key, display, host) for a URL cell, or None for an empty cell.

    key     comparison form: host (no www), decoded path (no trailing slash), query without
            tracking parameters. Scheme, fragment and port are ignored.
    display the URL as written, minus its fragment.
    host    the bare host, '' for a relative path with no --site.
    """
    s = str(raw).strip()
    if not s:
        return None
    s = s.split("#", 1)[0]
    relative = False
    if s.startswith("//"):
        s = "https:" + s
    elif s.startswith("/"):
        s = ("https://" + site + s) if site else "https://x.invalid" + s
        relative = site is None
    elif "://" not in s:
        s = "https://" + s
    parts = urlsplit(s)
    host = "" if relative else (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = unquote(parts.path or "/")
    if len(path) > 1:
        path = path.rstrip("/") or "/"
    q = sorted((k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
               if not (k.lower().startswith("utm_") or k.lower() in _TRACKING))
    key = host + path + ("?" + urlencode(q) if q else "")
    display = s if not relative else s.replace("https://x.invalid", "", 1)
    return key, display, host

#!/usr/bin/env python3
"""
Nature crawler (merged): API discovery + authorized content fetch + figure<->source-data pairing.

This single tool unifies two earlier scripts:
  - download_nature_pairs.py   (Playwright crawl of nature.com search; figure<->source-data PAIRING)
  - nature_all_in_one.py       (Crossref + Europe PMC discovery; search/fig/source/postfetch/auto)

Subcommands
-----------
  search     Crossref (+Europe PMC enrich) discovery -> articles.jsonl / .csv
  fig        Fetch one nature.com figure page (image + caption)            [requests/bs4]
  source     Fetch Source-data files from one nature.com article page      [requests/bs4]
  postfetch  For each article in a JSONL: fetch ALL figures + source data  [requests/bs4]
  auto       Multi-keyword search -> immediate fetch (optional streaming)  [requests/bs4]
  pairs      Playwright crawl of nature.com search; download figure images
             AND their matched Source-data files, emitting figure<->data PAIRS.

Pick by goal
------------
  * Want (figure image  <->  the data table that figure was drawn from) PAIRS  -> use `pairs`.
  * Want broad keyword discovery / metadata / open-access enrichment           -> use `search`/`auto`.
  * Have a list of article URLs and just want everything fetched              -> use `postfetch`.

Output layout
-------------
  search/auto : <out>/articles.jsonl + articles.csv
  fig/source/postfetch/auto content : <out>/<article-id>/{figures,source_data,meta}
  pairs       : <out>/articles/<article-id>/{images,data} + <out>/pairs.jsonl (+ state/errors/skipped)

Dependencies
------------
  requests, beautifulsoup4  (always)
  playwright                (only for `pairs`; lazily imported)
  rich                      (optional; nicer progress for search/auto/postfetch)
  pandas/openpyxl           (not required here; used downstream when reading xlsx)
"""
from __future__ import annotations

import argparse
import csv
import importlib
import json
import mimetypes
import multiprocessing as mp
import os
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import (
    FIRST_COMPLETED,
    ProcessPoolExecutor,
    ThreadPoolExecutor,
    as_completed,
    wait,
)
from dataclasses import dataclass
from email.message import Message
from pathlib import Path
from typing import Any, Iterable, Optional
from urllib.parse import (
    parse_qsl,
    unquote,
    urlencode,
    urljoin,
    urlparse,
    urlsplit,
    urlunsplit,
)
from uuid import uuid4

# ======================================================================================
# Dependency bootstrap (shared) — requests/bs4 always; rich optional; playwright lazy.
# ======================================================================================


def ensure_package(module_name: str, pip_name: Optional[str] = None):
    """Import a module, pip-installing it on first miss (kept from all_in_one)."""
    try:
        return importlib.import_module(module_name)
    except ImportError:
        to_install = pip_name or module_name
        print(f"[setup] Installing missing dependency: {to_install} ...", flush=True)
        subprocess.check_call([sys.executable, "-m", "pip", "install", to_install])
        return importlib.import_module(module_name)


requests = ensure_package("requests")
ensure_package("bs4", "beautifulsoup4")
from bs4 import BeautifulSoup  # type: ignore  # noqa: E402

try:
    ensure_package("rich")
    from rich.console import Console
    from rich.progress import (
        BarColumn,
        Progress,
        SpinnerColumn,
        TextColumn,
        TimeElapsedColumn,
    )

    console = Console()
except Exception:
    console = None


API_USER_AGENT = "PheroViz-NatureCrawler/1.0 (+compliant; authorized when required)"
BROWSER_USER_AGENT = "Mozilla/5.0"
NATURE_SEARCH_RESULT_CAP_MESSAGE = "We only show the first 1000 results for any query"
DEFAULT_SEARCH_URL = (
    "https://www.nature.com/search?q=%22Source%20Data%22&journal=nature&order=date_desc"
)


# ======================================================================================
# Shared utilities (deduplicated from both scripts)
# ======================================================================================


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())


def safe_console(text: str) -> str:
    """Encode text safely for the active stdout encoding (kept from all_in_one)."""
    try:
        enc = sys.stdout.encoding or "utf-8"
        return text.encode(enc, errors="replace").decode(enc, errors="replace")
    except Exception:
        try:
            return text.encode("ascii", errors="replace").decode("ascii")
        except Exception:
            return "<unprintable>"


def sanitize(s: str) -> str:
    """Loose slug for ids/labels (all_in_one semantics)."""
    return re.sub(r"[^a-zA-Z0-9_.\-]+", "_", s).strip("_.-") or "item"


def _safe_filename(name: str) -> str:
    """Filesystem-safe filename preserving spaces (pairs semantics)."""
    name = re.sub(r'[\\/:*?"<>|]', "_", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:180] if len(name) > 180 else name


def _ensure_https(url: str) -> str:
    if url.startswith("//"):
        return "https:" + url
    return url


def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".part")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp_path, path)


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})


def append_jsonl(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def load_processed_set(path: Path) -> set[str]:
    s: set[str] = set()
    if path.exists():
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    s.add(line)
        except Exception:
            pass
    return s


def append_processed(path: Path, article_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(article_id + "\n")


def append_skipped(path: Path, article_id: str, reason: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    safe_reason = reason.strip() or "unknown"
    with path.open("a", encoding="utf-8") as f:
        f.write(f"{article_id}\t{safe_reason}\n")


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def upsert_json_list(path: Path, item: dict, key: str) -> None:
    data: list[dict] = []
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8") or "[]")
        except Exception:
            data = []
    existing_keys = {str(d.get(key)) for d in data}
    if str(item.get(key)) not in existing_keys:
        data.append(item)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ---- HTTP layer (single source of truth; merges polite_get + plain requests usage) ----


def polite_get(
    url: str,
    params=None,
    timeout: float = 60,
    sleep: float = 1.0,
    max_retries: int = 3,
    headers: Optional[dict[str, str]] = None,
    *,
    user_agent: str = API_USER_AGENT,
):
    """GET with exponential backoff. Used by both API calls and HTML page fetches."""
    hdrs = {"User-Agent": user_agent, "Accept": "*/*", "Connection": "close"}
    if headers:
        hdrs.update(headers)
    attempt = 0
    backoff = sleep if sleep else 0.5
    while True:
        attempt += 1
        try:
            # Tuple (connect, read) timeout: a scalar timeout is unreliable at the
            # SSL read stage (a server that completes TLS then stops sending can
            # hang recv() indefinitely on macOS). The read leg bounds that.
            resp = requests.get(url, params=params, headers=hdrs, timeout=(15, timeout))
            if sleep:
                time.sleep(sleep)
            resp.raise_for_status()
            return resp
        except Exception as e:
            if attempt >= max_retries:
                raise
            wait_s = backoff * (2 ** (attempt - 1))
            print(safe_console(f"  [retry] {url} failed ({e}); waiting {wait_s:.1f}s"))
            time.sleep(wait_s)


def parse_content_disposition_filename(header: Optional[str]) -> Optional[str]:
    """Extract filename / filename* from a Content-Disposition header (all_in_one)."""
    if not header:
        return None
    try:
        msg = Message()
        msg["content-disposition"] = header
        filename = msg.get_param("filename", header="content-disposition")
        if filename:
            return unquote(filename.strip())
        filename_star = msg.get_param("filename*", header="content-disposition")
        if filename_star:
            parts = filename_star.split("''", 1)
            if len(parts) == 2:
                filename_star = parts[1]
            return unquote(filename_star.strip())
    except Exception:
        pass
    match = re.search(r'filename\*?=\s*"?([^";]+)', header, re.I)
    if match:
        candidate = match.group(1)
        if "''" in candidate:
            candidate = candidate.split("''", 1)[1]
        return unquote(candidate.strip())
    return None


def guess_extension_from_type(content_type: Optional[str]) -> str:
    if not content_type:
        return ""
    ctype = content_type.split(";", 1)[0].strip().lower()
    if not ctype:
        return ""
    ext = mimetypes.guess_extension(ctype)
    if ext in (None, "", ".bin") and ctype.startswith("text/"):
        return ".txt"
    return ext or ""


class FileTooLargeError(Exception):
    """Raised when a download exceeds max_bytes (skip, don't retry)."""


def download_binary(
    url: str,
    out_path: Path,
    referer: Optional[str] = None,
    timeout: float = 180,
    sleep: float = 1.0,
    max_retries: int = 3,
    *,
    overwrite: bool = False,
    return_meta: bool = False,
    user_agent: str = API_USER_AGENT,
    max_bytes: Optional[int] = None,
):
    """
    Stream a file to disk with retry + atomic rename (.part).

    Merges download_file (pairs: overwrite/skip-existing) and download_binary
    (all_in_one: Content-Length verify + Content-Disposition meta).
    If max_bytes is set and the server-declared Content-Length exceeds it, raise
    FileTooLargeError immediately (no body download, no retry).
    Returns str(out_path), or (str(out_path), remote_name, content_type) when return_meta.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if (not overwrite) and (not return_meta) and out_path.exists() and out_path.stat().st_size > 0:
        return str(out_path)

    headers = {"User-Agent": user_agent, "Accept": "*/*", "Connection": "close"}
    if referer:
        headers["Referer"] = referer
    attempt = 0
    backoff = sleep if sleep else 0.5
    while True:
        attempt += 1
        try:
            with requests.get(url, headers=headers, stream=True, timeout=(15, timeout)) as resp:
                resp.raise_for_status()
                expected = resp.headers.get("Content-Length")
                if max_bytes is not None and expected is not None:
                    try:
                        if int(expected) > max_bytes:
                            raise FileTooLargeError(f"{int(expected)} bytes > limit {max_bytes}")
                    except ValueError:
                        pass
                remote_name = parse_content_disposition_filename(resp.headers.get("Content-Disposition"))
                content_type = resp.headers.get("Content-Type")
                tmp = out_path.with_suffix(out_path.suffix + ".part")
                total = 0
                with tmp.open("wb") as f:
                    for chunk in resp.iter_content(chunk_size=1024 * 256):
                        if chunk:
                            f.write(chunk)
                            total += len(chunk)
                            # Guard against missing/lying Content-Length: stop mid-stream too.
                            if max_bytes is not None and total > max_bytes:
                                f.close()
                                tmp.unlink(missing_ok=True)
                                raise FileTooLargeError(f"exceeded limit {max_bytes} mid-stream")
                if expected and total != int(expected):
                    raise IOError(f"incomplete download: {total} != {expected}")
                os.replace(tmp, out_path)
                if return_meta:
                    return str(out_path), remote_name, content_type
                return str(out_path)
        except FileTooLargeError:
            raise  # never retry an oversized file
        except Exception as e:
            if attempt >= max_retries:
                raise
            wait_s = backoff * (2 ** (attempt - 1))
            print(safe_console(f"  [retry-dl] {url} ({e}); waiting {wait_s:.1f}s"))
            time.sleep(wait_s)


# ---- Article-id / URL helpers (merged) ----


def parse_article_id(url: str) -> str:
    """nature.com/articles/<id> -> <id> (all_in_one semantics; tolerant of #?)."""
    m = re.search(r"/articles/([^/#?]+)", url)
    return m.group(1) if m else "unknown"


def parse_article_id_and_fig(url: str) -> tuple[str, Optional[int]]:
    m = re.search(r"/articles/([^/]+)(?:/figures/(\d+))?", url)
    if not m:
        return ("unknown", None)
    return (m.group(1), int(m.group(2)) if m.group(2) else None)


def _normalize_article_id(article_url: str) -> str:
    """Pairs-route id: prefer /articles/<id>, else slugged path."""
    parsed = urlparse(article_url)
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) >= 2 and parts[0] == "articles":
        return parts[1]
    return _safe_filename(parsed.path.strip("/")) or "article"


def norm_article_url(url: Optional[str], doi: Optional[str]) -> Optional[str]:
    if url:
        m = re.search(r"https?://(?:www\.)?nature\.com/articles/([^/?#]+)", url)
        if m:
            return f"https://www.nature.com/articles/{m.group(1)}"
    if doi and doi.lower().startswith("10.1038/"):
        suffix = doi.split("/", 1)[1]
        return f"https://www.nature.com/articles/{suffix}"
    return None


def filename_from_url(url: str) -> str:
    path = urlparse(url).path
    name = os.path.basename(path)
    return unquote(name) or "source_data.bin"


def _basename_from_url(url: str) -> str:
    path = urlsplit(url).path
    base = Path(path).name
    return _safe_filename(base) if base else "download.bin"


# ---- Image URL helpers (merged: full-res upgrade + likely-image filter) ----


def to_full_media_url(url: str) -> str:
    """media.springernature.com/<size>/<rest> -> /full/<rest> (pairs semantics)."""
    url = _ensure_https(url)
    try:
        parts = urlsplit(url)
        if parts.netloc != "media.springernature.com":
            return url
        path = parts.path.lstrip("/")
        m = re.match(r"^(?:lw\d+|m\d+|w\d+h\d+|full)/(.+)$", path)
        if not m:
            return url
        new_path = "/full/" + m.group(1)
        return urlunsplit((parts.scheme, parts.netloc, new_path, parts.query, parts.fragment))
    except Exception:
        return url


def is_likely_image_url(u: str) -> bool:
    try:
        p = urlparse(u)
        if p.scheme not in ("http", "https"):
            return False
        host = (p.netloc or "").lower()
        if any(bad in host for bad in ["doubleclick.net", "googletagservices.com", "gampad"]):
            return False
        path = (p.path or "").lower()
        if any(path.endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".gif", ".webp")):
            return True
        if "media.springernature.com" in host:
            return True
        return False
    except Exception:
        return False


def normalize_img_url(u: str) -> str:
    u = u.strip()
    if u.startswith("//"):
        u = "https:" + u
    m = re.search(r"(https?://images\.nature\.com/[^\s\"]+)", u)
    if m:
        return m.group(1)
    return u


# ======================================================================================
# Discovery layer: Crossref + Europe PMC  (from nature_all_in_one.py)
# ======================================================================================


def is_nature_family(container_titles) -> bool:
    if not container_titles:
        return False
    titles = [container_titles] if isinstance(container_titles, str) else container_titles
    for t in titles:
        if not t:
            continue
        tt = t.strip()
        if tt == "Nature" or tt.lower().startswith("nature "):
            return True
    return False


def crossref_search(query, rows=20, mailto=None, sleep=1.0, timeout=30, max_retries=3, family_bias=True):
    base = "https://api.crossref.org/works"
    params = {"query": query, "filter": "type:journal-article", "rows": rows}
    if family_bias:
        params["query.container-title"] = "Nature"
    if mailto:
        params["mailto"] = mailto
    r = polite_get(base, params=params, sleep=sleep, timeout=timeout, max_retries=max_retries)
    items = r.json().get("message", {}).get("items", [])
    return [it for it in items if is_nature_family(it.get("container-title"))]


def crossref_cursor_stream(query, total_max, mailto=None, sleep=1.0, timeout=30, max_retries=3, family_bias=True, page_rows=1000):
    """Yield Nature-family items via Crossref cursor pagination (beyond single-request caps)."""
    base = "https://api.crossref.org/works"
    fetched = 0
    cursor = "*"
    page_rows = min(max(1, int(page_rows)), 1000)
    while fetched < total_max:
        remaining = total_max - fetched
        rows = min(page_rows, remaining)
        params = {"query": query, "filter": "type:journal-article", "rows": rows, "cursor": cursor}
        if family_bias:
            params["query.container-title"] = "Nature"
        if mailto:
            params["mailto"] = mailto
        try:
            r = polite_get(base, params=params, sleep=sleep, timeout=timeout, max_retries=max_retries)
        except requests.HTTPError as exc:
            status = getattr(exc.response, "status_code", None)
            if status == 404:
                msg = safe_console(f"[warn] Crossref cursor 404 for query {query!r}; skipping remainder")
                console.log(msg) if console else print(msg)
                break
            raise
        data = r.json()
        items = data.get("message", {}).get("items", [])
        for it in items:
            if is_nature_family(it.get("container-title")):
                yield it
                fetched += 1
                if fetched >= total_max:
                    break
        next_cursor = data.get("message", {}).get("next-cursor") or data.get("message", {}).get("next_cursor")
        if not next_cursor:
            break
        cursor = next_cursor


def europe_pmc_by_doi(doi, sleep=1.0, timeout=30, max_retries=3):
    url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    params = {"query": f"DOI:{doi}", "format": "json", "pageSize": 1}
    r = polite_get(url, params=params, sleep=sleep, timeout=timeout, max_retries=max_retries)
    results = r.json().get("resultList", {}).get("result", [])
    return results[0] if results else None


def fetch_pmc_figure_urls(pmcid, sleep=1.0, timeout=30, max_retries=3):
    base = f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/"
    r = polite_get(base, sleep=sleep, timeout=timeout, max_retries=max_retries)
    soup = BeautifulSoup(r.text, "html.parser")
    urls: list[str] = []
    for fig in soup.find_all("figure"):
        for img in fig.find_all("img"):
            src = img.get("src") or img.get("data-src")
            if not src:
                continue
            if src.startswith("//"):
                full = "https:" + src
            elif src.startswith("/"):
                full = "https://pmc.ncbi.nlm.nih.gov" + src
            elif src.startswith("http"):
                full = src
            else:
                full = base + src
            urls.append(full)
    seen, unique = set(), []
    for u in urls:
        if u not in seen:
            seen.add(u)
            unique.append(u)
    return unique


def format_authors_crossref(author_list) -> str:
    try:
        parts = []
        for a in author_list or []:
            given = (a.get("given") or "").strip()
            family = (a.get("family") or "").strip()
            name = (family + ", " + given).strip(", ") if (given or family) else (a.get("name") or "")
            if name:
                parts.append(name)
        return "; ".join(parts)
    except Exception:
        return ""


def merge_append(records: list[dict], existing_path: Path) -> list[dict]:
    if not existing_path.exists():
        return records
    seen: set[str] = set()
    merged: list[dict] = []
    try:
        with existing_path.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    obj = json.loads(line)
                    doi = (obj.get("doi") or "").lower()
                    if doi and doi not in seen:
                        seen.add(doi)
                        merged.append(obj)
                except Exception:
                    continue
    except Exception:
        pass
    for r in records:
        doi = (r.get("doi") or "").lower()
        if doi and doi not in seen:
            seen.add(doi)
            merged.append(r)
    return merged


def _crossref_item_to_record(it: dict, *, sleep, timeout, max_retries) -> dict:
    """Crossref item (+Europe PMC enrich) -> unified article record."""
    doi = it.get("DOI")
    title_list = it.get("title") or []
    title = title_list[0] if title_list else ""
    container = (it.get("container-title") or [""])[0]
    issued = it.get("issued", {}).get("date-parts", [[None]])[0]
    year = issued[0] if issued else None
    url = it.get("URL")
    abstract = it.get("abstract")
    epmc = europe_pmc_by_doi(doi, sleep=sleep, timeout=timeout, max_retries=max_retries) if doi else None
    pmcid = epmc.get("pmcid") if epmc else None
    abstract_epmc = epmc.get("abstractText") if epmc else None
    is_oa = bool(epmc.get("isOpenAccess") or pmcid) if epmc else False
    pmc_url = f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/" if pmcid else None
    pmid = epmc.get("pmid") if epmc else None
    authors = format_authors_crossref(it.get("author")) or (epmc.get("authorString") if epmc else "")
    return {
        "doi": doi,
        "title": title,
        "journal": container,
        "year": year,
        "url": url,
        "pmcid": pmcid,
        "pmc_url": pmc_url,
        "pmid": pmid,
        "is_open_access": is_oa,
        "abstract": abstract_epmc or abstract or "",
        "authors": authors,
    }


ARTICLE_CSV_FIELDS = ["doi", "title", "journal", "year", "url", "pmcid", "pmc_url", "pmid", "is_open_access", "abstract", "authors"]


def cmd_search(args):
    print(f"[info] Query: {safe_console(args.query)}")
    print(f"[info] Max: {args.max} | Sleep: {args.sleep}s")
    if args.max and args.max > 1000:
        items = list(crossref_cursor_stream(
            args.query, total_max=args.max, mailto=args.mailto, sleep=args.sleep,
            timeout=args.timeout, max_retries=args.max_retries, family_bias=not args.no_family_bias, page_rows=1000,
        ))
    else:
        items = crossref_search(
            args.query, rows=args.max, mailto=args.mailto, sleep=args.sleep,
            timeout=args.timeout, max_retries=args.max_retries, family_bias=not args.no_family_bias,
        )
    print(f"[info] Crossref filtered results (Nature family): {len(items)}")
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    for i, it in enumerate(items, 1):
        rec = _crossref_item_to_record(it, sleep=args.sleep, timeout=args.timeout, max_retries=args.max_retries)
        print(f"[{i}/{len(items)}] {safe_console(rec['title'])[:80]}...")
        print(f"      DOI: {rec['doi']} | Journal: {safe_console(rec['journal'])} | Year: {rec['year']}")
        records.append(rec)

    jsonl_path = outdir / "articles.jsonl"
    if args.append and jsonl_path.exists():
        write_jsonl(jsonl_path, merge_append(records, jsonl_path))
    else:
        write_jsonl(jsonl_path, records)
    write_csv(outdir / "articles.csv", records, ARTICLE_CSV_FIELDS)
    print(f"[done] Saved {len(records)} records to {outdir}")


# ======================================================================================
# Authorized single-page fetch: figure image + caption  (from nature_all_in_one.py)
# ======================================================================================


def pick_largest_src(soup: BeautifulSoup, base_url: str):
    og = soup.find("meta", attrs={"property": "og:image"})
    if og and og.get("content"):
        cand = normalize_img_url(urljoin(base_url, og["content"].strip()))
        if is_likely_image_url(cand):
            return cand
    fig = soup.find("figure")
    img = None
    if fig:
        src = fig.find("source")
        if src and src.get("srcset"):
            entries = [x.strip() for x in src["srcset"].split(",") if x.strip()]
            for entry in reversed(entries):
                u = normalize_img_url(urljoin(base_url, entry.split()[0]))
                if is_likely_image_url(u):
                    return u
        img = fig.find("img")
    else:
        img = soup.find("img")
    if img:
        src_attr = img.get("src") or img.get("data-src") or img.get("data-original")
        if src_attr:
            cand = normalize_img_url(urljoin(base_url, src_attr.strip()))
            if is_likely_image_url(cand):
                return cand

    best = None

    def score(u: str) -> int:
        s = 0
        uu = u.lower()
        if any(k in uu for k in ("original", "download", "full")):
            s += 5
        if uu.endswith(".tif") or ".tif?" in uu:
            s += 4
        elif uu.endswith(".png") or ".png?" in uu:
            s += 3
        elif uu.endswith(".jpg") or uu.endswith(".jpeg") or ".jpg?" in uu or ".jpeg?" in uu:
            s += 2
        elif uu.endswith(".webp") or ".webp?" in uu:
            s += 1
        return s

    for a in soup.find_all("a"):
        href = a.get("href")
        if not href:
            continue
        u = normalize_img_url(urljoin(base_url, href))
        if is_likely_image_url(u):
            sc = score(u)
            if not best or sc > best[0]:
                best = (sc, u)
    return best[1] if best else None


def extract_caption(soup: BeautifulSoup):
    cap_el = soup.find("figcaption")
    if cap_el:
        t = cap_el.get_text(" ", strip=True)
        if t:
            return t
    cap_div = soup.find(class_=re.compile(r"c-figure__caption|figure__caption|caption"))
    if cap_div:
        t = cap_div.get_text(" ", strip=True)
        if t:
            return t
    cap_dt = soup.find(attrs={"data-test": re.compile(r"caption", re.I)})
    if cap_dt:
        t = cap_dt.get_text(" ", strip=True)
        if t:
            return t
    ogd = soup.find("meta", attrs={"property": "og:description"})
    if ogd and ogd.get("content"):
        return ogd["content"].strip()
    md = soup.find("meta", attrs={"name": "description"})
    if md and md.get("content"):
        return md["content"].strip()
    for sc in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(sc.string or "{}")
        except Exception:
            continue

        def walk(obj):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if k in ("caption", "description") and isinstance(v, str) and v.strip():
                        return v.strip()
                    got = walk(v)
                    if got:
                        return got
            elif isinstance(obj, list):
                for it in obj:
                    got = walk(it)
                    if got:
                        return got
            return None

        found = walk(data)
        if found:
            return found
    return ""


def cmd_fig(args):
    url = args.url
    aid, fno = parse_article_id_and_fig(url)
    print(f"[info] Article: {aid} | Figure: {fno if fno else 'all/unknown'}")
    try:
        r = polite_get(url, timeout=args.timeout, sleep=args.sleep, max_retries=args.max_retries)
    except Exception as e:
        print(safe_console(f"[warn] figure page not available: {url} ({e})"))
        return
    soup = BeautifulSoup(r.text, "html.parser")
    img_url = pick_largest_src(soup, r.url)
    caption = extract_caption(soup)

    base = Path(args.out) / aid
    figures_dir = base / "figures"
    meta_dir = base / "meta"
    ensure_dir(figures_dir)
    ensure_dir(meta_dir)

    fig_id = fno if fno is not None else "page"
    fig_tag = f"fig_{fig_id:03d}" if isinstance(fig_id, int) else f"fig_{fig_id}"

    saved_img = None
    if img_url:
        ext = ".jpg"
        m = re.search(r"\.(png|jpg|jpeg|gif|webp)(?:\?|$)", img_url, re.I)
        if m:
            ext = "." + m.group(1).lower().replace("jpeg", "jpg")
        out_img = figures_dir / f"{fig_tag}{ext}"
        saved_img = download_binary(
            img_url, out_img, referer=r.url, timeout=args.timeout, sleep=args.sleep,
            max_retries=args.max_retries, user_agent=API_USER_AGENT,
        )
        print(f"[done] Image saved: {saved_img}")
    else:
        print("[warn] No image URL found on the page")

    saved_cap = None
    if saved_img and caption:
        out_cap = figures_dir / f"{fig_tag}.txt"
        out_cap.write_text(caption, encoding="utf-8")
        saved_cap = str(out_cap)
        print("[done] Caption saved.")
    elif not caption:
        print("[warn] No caption text found.")

    if saved_img:
        entry = {"figure_tag": fig_tag, "figure_no": fno, "image_file": saved_img, "caption_file": saved_cap, "image_url": img_url, "source_url": url}
        upsert_json_list(meta_dir / "figures.json", entry, key="figure_tag")

    return bool(saved_img)


# ======================================================================================
# Authorized single-article fetch: Source-data files  (from nature_all_in_one.py)
# ======================================================================================


def scoped_section_nodes(soup: BeautifulSoup, section_id: Optional[str]):
    if not section_id:
        return [soup]
    sec = soup.find(id=section_id)
    if not sec:
        return []
    container = sec.find_parent("section") or sec.find_parent("div", class_=re.compile(r"section|content", re.I))
    if container and container is not soup:
        return [container]
    nodes = [sec]
    heading_level = int(sec.name[1]) if getattr(sec, "name", "") in {"h1", "h2", "h3", "h4", "h5", "h6"} else None
    for sibling in sec.next_siblings:
        name = getattr(sibling, "name", None)
        if heading_level and name in {"h1", "h2", "h3", "h4", "h5", "h6"} and int(name[1]) <= heading_level:
            break
        nodes.append(sibling)
    return nodes


def find_source_data_links(soup: BeautifulSoup, base_url: str, section_id: Optional[str], text_filter: Optional[str]):
    links = []
    rx = re.compile(r"source\s*data", re.I)
    base_parsed = urlparse(base_url)

    def add_links_from(container) -> None:
        if not hasattr(container, "find_all"):
            return
        for a in container.find_all("a"):
            label = (a.get_text(" ", strip=True) or "").strip()
            if not label or not rx.search(label):
                continue
            if text_filter and (text_filter.lower() not in label.lower()):
                continue
            href = a.get("href")
            if not href:
                continue
            abs_url = urljoin(base_url, href)
            parsed = urlparse(abs_url)
            if (parsed.fragment and parsed.scheme == base_parsed.scheme and parsed.netloc == base_parsed.netloc
                    and parsed.path == base_parsed.path and not parsed.query):
                continue
            links.append({"label": label, "url": abs_url})

    for container in scoped_section_nodes(soup, section_id):
        add_links_from(container)
    if section_id and not links:
        add_links_from(soup)

    seen, uniq = set(), []
    for L in links:
        if L["url"] not in seen:
            seen.add(L["url"])
            uniq.append(L)
    return uniq


def cmd_source(args):
    url = args.url
    art_id = parse_article_id(url)
    print(f"[info] Article: {art_id} | section: {args.section_id or 'all'} | filter: {args.filter or 'none'}")
    r = polite_get(url, timeout=args.timeout, sleep=args.sleep, max_retries=args.max_retries)
    soup = BeautifulSoup(r.text, "html.parser")
    links = find_source_data_links(soup, r.url, args.section_id, args.filter)
    print(f"[info] Source data links found: {len(links)}")
    base = Path(args.out) / art_id
    sd_dir = base / "source_data"
    meta_dir = base / "meta"
    manifest_path = meta_dir / "_source_data_manifest.json"
    json_path = meta_dir / "source_data.json"

    def cleanup_empty():
        if sd_dir.exists():
            shutil.rmtree(sd_dir, ignore_errors=True)
        if manifest_path.exists():
            manifest_path.unlink()
        if json_path.exists():
            json_path.unlink()

    if not links:
        print("[warn] No Source data links present; skip article")
        cleanup_empty()
        return False

    ensure_dir(sd_dir)
    ensure_dir(meta_dir)
    manifest = []
    saved_count = 0
    used_names: set[str] = set()

    def allocate_name(candidates: list[tuple[str, str]], fallback_stem: str, ext_hint: str) -> str:
        for stem, suffix in candidates:
            suffix = suffix or ext_hint
            stem = stem or fallback_stem
            attempt = stem + (suffix or "")
            counter = 2
            while attempt.lower() in used_names:
                attempt = f"{stem}_{counter}{suffix or ''}"
                counter += 1
            used_names.add(attempt.lower())
            return attempt
        suffix = ext_hint or ""
        stem = fallback_stem or "source_data"
        attempt = stem + suffix
        counter = 2
        while attempt.lower() in used_names:
            attempt = f"{stem}_{counter}{suffix}"
            counter += 1
        used_names.add(attempt.lower())
        return attempt

    for i, L in enumerate(links, 1):
        label = L["label"]
        file_url = L["url"]
        fname_url = filename_from_url(file_url)
        fallback_stem = f"source_data_{i:02d}"
        tmp_path = sd_dir / f".tmp_{uuid4().hex}"
        print(f"  [{i}/{len(links)}] {safe_console(label)} -> downloading...")
        try:
            saved_tmp, remote_name, content_type = download_binary(
                file_url, tmp_path, referer=r.url, timeout=args.timeout, sleep=args.sleep,
                max_retries=args.max_retries, return_meta=True, user_agent=API_USER_AGENT,
            )
            tmp_file = Path(saved_tmp)
            ext_candidates = []
            for raw in (remote_name, fname_url):
                if raw and Path(raw).suffix:
                    ext_candidates.append(Path(raw).suffix)
            type_ext = guess_extension_from_type(content_type)
            if type_ext:
                ext_candidates.append(type_ext)
            ext_hint = next((e for e in ext_candidates if e), "")
            candidate_pairs: list[tuple[str, str]] = []
            seen_pairs: set[tuple[str, str]] = set()

            def add_candidate(raw: Optional[str]):
                if not raw:
                    return
                cleaned = sanitize(raw)
                if not cleaned:
                    return
                stem, suffix = os.path.splitext(cleaned)
                if not suffix and ext_hint:
                    suffix = ext_hint
                stem = stem or fallback_stem
                pair = (stem, suffix or "")
                if pair not in seen_pairs:
                    seen_pairs.add(pair)
                    candidate_pairs.append(pair)

            add_candidate(remote_name)
            add_candidate(fname_url)
            add_candidate(label)
            if not candidate_pairs:
                candidate_pairs.append((fallback_stem, ext_hint or ""))

            chosen_name = allocate_name(candidate_pairs, fallback_stem, ext_hint)
            final_path = sd_dir / chosen_name
            if final_path.exists():
                final_path.unlink()
            tmp_file.replace(final_path)
            print(f"      saved as {chosen_name}")
            entry = {"label": label, "url": file_url, "saved_as": str(final_path), "saved_name": chosen_name, "orig_name": fname_url, "content_name": remote_name, "content_type": content_type}
            manifest.append(entry)
            upsert_json_list(json_path, entry, key="label")
            saved_count += 1
        except Exception as e:
            for p in (tmp_path, tmp_path.with_suffix(tmp_path.suffix + ".part")):
                if p.exists():
                    try:
                        p.unlink()
                    except Exception:
                        pass
            entry = {"label": label, "url": file_url, "error": str(e), "saved_name": None, "orig_name": fname_url, "content_name": None, "content_type": None}
            manifest.append(entry)
            upsert_json_list(json_path, entry, key="label")

    if saved_count == 0:
        print("[warn] Source data downloads all failed; skip article")
        cleanup_empty()
        return False

    manifest_path.write_text(json.dumps({"article_url": url, "links": manifest}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[done] Saved manifest and files under {base}")
    return True


# ======================================================================================
# Post-fetch: for each article fetch ALL figures + source data  (from nature_all_in_one.py)
# ======================================================================================


def postfetch_one(art_url, out, max_figs, sleep, timeout, max_retries, max_empty_figs=2):
    """Walk /figures/1..N for one article; stop after max_empty_figs consecutive misses."""
    aid = parse_article_id(art_url)
    print(f"[stream] Fetch: {aid}")
    try:
        polite_get(art_url, timeout=timeout, sleep=sleep, max_retries=1)
    except Exception as e:
        print(safe_console(f"[warn] article page not available: {art_url} ({e})"))
        return None
    empty_streak = 0
    found_count = 0
    for i in range(1, max_figs + 1):
        fig_url = f"{art_url}/figures/{i}"
        try:
            found = cmd_fig(argparse.Namespace(url=fig_url, out=out, sleep=sleep, timeout=timeout, max_retries=max_retries))
            if not found:
                empty_streak += 1
                if empty_streak >= max_empty_figs:
                    print(f"[info] Stop figures loop for {aid}: consecutive empty pages {empty_streak}")
                    break
            else:
                empty_streak = 0
                found_count += 1
        except Exception as he:
            if "404" in str(he):
                print(f"[info] Stop figures loop for {aid}: 404 on {i}")
                break
        time.sleep(sleep)
    return found_count


def postfetch_article(art_url, out, max_figs, max_empty_figs, sleep, timeout, max_retries):
    """Fetch source data + figures for one article. Returns (aid, code): code>0 ok, -1 drop."""
    aid = parse_article_id(art_url)
    source_ok = cmd_source(argparse.Namespace(url=art_url, out=out, section_id=None, filter=None, sleep=sleep, timeout=timeout, max_retries=max_retries))
    found = postfetch_one(art_url, out, max_figs, sleep, timeout, max_retries, max_empty_figs)
    figure_count = int(found or 0)
    if source_ok:
        return (aid, max(figure_count, 1))
    base = Path(out) / aid
    if base.exists():
        shutil.rmtree(base, ignore_errors=True)
    return (aid, -1)


def cmd_postfetch(args):
    rows = []
    with Path(args.jsonl).open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    print(f"[info] Loaded {len(rows)} records from {args.jsonl}")
    if args.sort != "input":
        def year_key(x):
            try:
                y = x.get("year")
                return int(y) if y is not None else -10**9
            except Exception:
                return -10**9
        rows = sorted(rows, key=year_key, reverse=(args.sort == "year_desc"))

    processed_file_arg = getattr(args, "processed_file", None)
    processed_file = Path(processed_file_arg) if processed_file_arg else (Path(args.out) / "_processed.txt")
    processed = load_processed_set(processed_file)
    skipped_file = processed_file.with_name("_skipped.txt")
    tasks: list[str] = []
    for r in rows:
        art_url = norm_article_url(r.get("url"), r.get("doi"))
        if not art_url:
            continue
        if parse_article_id(art_url) in processed:
            continue
        tasks.append(art_url)
        if args.max_articles and len(tasks) >= args.max_articles:
            break

    total = len(tasks)
    if total == 0:
        print("[info] No tasks to fetch (all processed or none found).")
        return

    workers = getattr(args, "workers", 1)
    max_empty = getattr(args, "max_empty_figs", 2)

    def _record_result(aid, found):
        if found > 0:
            append_processed(processed_file, aid)
        else:
            reason = "no-source-data" if found == -1 else "no-figures"
            append_processed(processed_file, aid)
            append_skipped(skipped_file, aid, reason)

    if workers > 1:
        progress_ctx = None
        if console:
            progress_ctx = Progress(
                SpinnerColumn(spinner_name="line"),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("{task.completed}/{task.total}"),
                TimeElapsedColumn(),
                console=console,
            )
        if progress_ctx:
            with progress_ctx as progress:
                t = progress.add_task("Postfetch", total=total)
                with ProcessPoolExecutor(max_workers=workers) as ex:
                    futures = {ex.submit(postfetch_article, u, args.out, args.max_figs, max_empty, args.sleep, args.timeout, args.max_retries): u for u in tasks}
                    for fut in as_completed(futures):
                        try:
                            aid, found = fut.result()
                        except Exception as e:
                            console.log(safe_console(f"[warn] postfetch failed: {e}"))
                            art = futures.get(fut)
                            if art:
                                aid = parse_article_id(art)
                                append_processed(processed_file, aid)
                                append_skipped(skipped_file, aid, "fetch-error")
                            progress.advance(t, 1)
                            continue
                        _record_result(aid, found)
                        progress.advance(t, 1)
        else:
            with ProcessPoolExecutor(max_workers=workers) as ex:
                futures = {ex.submit(postfetch_article, u, args.out, args.max_figs, max_empty, args.sleep, args.timeout, args.max_retries): u for u in tasks}
                for fut in as_completed(futures):
                    try:
                        aid, found = fut.result()
                    except Exception as e:
                        print(safe_console(f"[warn] postfetch failed: {e}"))
                        art = futures.get(fut)
                        if art:
                            aid = parse_article_id(art)
                            append_processed(processed_file, aid)
                            append_skipped(skipped_file, aid, "fetch-error")
                        continue
                    _record_result(aid, found)
    else:
        for idx, u in enumerate(tasks, 1):
            aid = parse_article_id(u)
            print(f"[{idx}/{total}] Nature article: {aid}")
            aid_out, found = postfetch_article(u, args.out, args.max_figs, max_empty, args.sleep, args.timeout, args.max_retries)
            _record_result(aid_out, found)
            time.sleep(args.sleep)
    print("[done] Post-fetch complete.")


# ======================================================================================
# Auto: multi-keyword search -> immediate fetch (optional streaming)  (from all_in_one)
# ======================================================================================


DEFAULT_KEYWORDS_EXPANDED = [
    "cancer", "tumor microenvironment", "immunotherapy", "checkpoint inhibitor",
    "PD-1", "CTLA-4", "CAR-T", "tumour biomarker", "precision oncology",
    "genomics", "transcriptomics", "single-cell", "scRNA-seq", "epigenomics",
    "multi-omics", "CRISPR", "gene editing",
    "machine learning", "deep learning", "foundation model", "graph neural network",
    "metabolism", "metabolomics", "microbiome", "gut microbiota",
    "neuroscience", "brain", "neurodegeneration", "Alzheimer",
    "materials", "quantum", "superconductivity", "perovskite", "catalysis",
    "climate change", "carbon", "ocean", "biodiversity", "ecosystem",
    "bioinformatics", "systems biology", "network biology",
    "COVID-19", "vaccination", "rare disease", "drug discovery",
    "proteomics", "lipidomics", "spatial transcriptomics", "spatial omics",
    "single-cell ATAC-seq", "multiome", "perturb-seq", "lineage tracing",
    "organoid", "organoids", "iPSC", "stem cell", "regenerative medicine",
    "CRISPR screen", "base editing", "prime editing", "epigenetic editing",
    "long-read sequencing", "nanopore sequencing", "PacBio", "cryo-EM",
    "X-ray crystallography", "structural biology", "synthetic biology",
    "metabolic engineering", "systems immunology", "metagenomics", "virome",
    "phage therapy", "antibiotic resistance", "exosomes",
    "extracellular vesicles", "liquid biopsy", "circulating tumor DNA",
    "methylation", "ATAC-seq", "ChIP-seq", "Hi-C", "3D genome", "chromatin",
    "enhancer", "super-enhancer", "noncoding RNA", "lncRNA", "microRNA",
    "circRNA", "RNA editing", "m6A", "autophagy", "apoptosis", "ferroptosis",
    "pyroptosis", "cuproptosis", "cellular senescence", "aging", "longevity",
    "mitochondria", "metabolic reprogramming", "immunometabolism",
    "angiogenesis", "metastasis", "epithelial-mesenchymal transition",
    "tumor heterogeneity", "clonal evolution", "phylogenetics",
    "network medicine", "drug repurposing", "AI in medicine",
    "federated learning", "privacy-preserving learning", "causal inference",
    "Mendelian randomization", "GWAS", "fine-mapping", "polygenic risk score",
    "rare variant", "structural variant", "copy number variation", "pangenome",
    "genome assembly", "de novo assembly", "pan-cancer", "AlphaFold",
    "protein design", "deep mutational scanning", "PROTAC", "degrader",
    "antibody-drug conjugate", "nanoparticle delivery", "gene therapy", "AAV",
    "lipid nanoparticles", "mRNA vaccine", "neoantigen", "TCR repertoire",
    "BCR repertoire", "immunopeptidomics", "single-cell multi-omics", "GeoMx",
    "CosMx",
]


def build_default_keywords(min_count: int = 500) -> list[str]:
    base: list[str] = []
    seen: set[str] = set()

    def add(term: str):
        t = term.strip()
        if t and t not in seen:
            seen.add(t)
            base.append(t)

    for t in DEFAULT_KEYWORDS_EXPANDED:
        add(t)
    if len(base) >= min_count:
        return base

    diseases = [
        "breast cancer", "lung cancer", "prostate cancer", "colorectal cancer", "melanoma",
        "glioblastoma", "glioma", "leukemia", "lymphoma", "pancreatic cancer",
        "ovarian cancer", "gastric cancer", "liver cancer", "hepatocellular carcinoma",
        "esophageal cancer", "renal cell carcinoma", "endometrial cancer", "sarcoma",
        "multiple myeloma", "head and neck cancer", "pediatric cancer", "rare cancer",
        "metastatic cancer", "brain tumor", "Alzheimer disease", "Parkinson disease",
        "ALS", "multiple sclerosis", "diabetes", "obesity", "NAFLD",
        "cardiovascular disease", "atherosclerosis", "stroke", "hypertension",
        "autoimmune disease", "inflammation", "infection", "COVID-19", "tuberculosis",
        "malaria", "HIV",
    ]
    modalities = [
        "single-cell", "scRNA-seq", "spatial transcriptomics", "multi-omics", "proteomics",
        "metabolomics", "lipidomics", "epigenomics", "ATAC-seq", "ChIP-seq", "Hi-C",
        "CRISPR", "CRISPR screen", "GWAS", "machine learning", "deep learning",
        "foundation model", "graph neural network", "immunotherapy", "checkpoint inhibitor",
        "organoid", "organoids", "gene editing", "base editing", "prime editing",
        "clinical trial", "biomarker", "liquid biopsy",
    ]
    for d in diseases:
        for m in modalities:
            add(f"{d} {m}")
            if len(base) >= min_count:
                return base
    return base


def cmd_auto(args):
    if args.keywords_file:
        kwds = [ln.strip() for ln in Path(args.keywords_file).read_text(encoding="utf-8").splitlines() if ln.strip()]
    else:
        kwds = build_default_keywords(500)
    print(f"[info] Keywords: {len(kwds)} items")

    search_out = Path(args.search_out)
    jsonl_path = search_out / "articles.jsonl"
    seen: set[str] = set()
    if jsonl_path.exists():
        try:
            with jsonl_path.open("r", encoding="utf-8") as f:
                for line in f:
                    try:
                        doi = (json.loads(line).get("doi") or "").lower()
                        if doi:
                            seen.add(doi)
                    except Exception:
                        continue
        except Exception:
            pass

    # Non-streaming: search all keywords, then postfetch
    if not getattr(args, "stream", False):
        for kw in kwds:
            cmd_search(argparse.Namespace(
                query=kw, max=args.max_per_keyword, out=args.search_out, sleep=args.sleep,
                timeout=args.timeout, max_retries=args.max_retries, mailto=args.mailto,
                no_family_bias=False, append=True,
            ))
        cmd_postfetch(argparse.Namespace(
            jsonl=str(jsonl_path), out=args.content_out, max_figs=args.max_figs,
            max_articles=args.max_articles, max_empty_figs=args.max_empty_figs, sort=args.sort,
            sleep=args.sleep, timeout=args.timeout, max_retries=args.max_retries,
            workers=getattr(args, "workers", 1),
            processed_file=(args.processed_file or str(Path(args.content_out) / "_processed.txt")),
        ))
        return

    # Streaming: per-article immediate fetch as search discovers them
    processed_file_stream = Path(args.content_out) / "_processed.txt"
    processed_stream = load_processed_set(processed_file_stream)
    skipped_file_stream = processed_file_stream.with_name("_skipped.txt")
    stream_workers = max(1, getattr(args, "stream_workers", 1))
    executor = ThreadPoolExecutor(max_workers=stream_workers, thread_name_prefix="stream-fetch")
    inflight: dict[Any, tuple[int, str]] = {}
    free_slots = list(range(stream_workers))
    stop_stream = False
    processed = 0
    total_keywords = len(kwds)
    progress = None
    search_task = fetch_task = None
    worker_tasks: list[int] = []

    def set_worker(slot: int, status: str, detail: Optional[str] = None) -> None:
        if progress is None or slot >= len(worker_tasks):
            return
        msg = f"worker-{slot + 1} {status}"
        if detail:
            msg += f" [{detail[:48]}]"
        progress.update(worker_tasks[slot], description=msg)

    def update_fetch_task() -> None:
        if progress is None or fetch_task is None:
            return
        goal = str(args.max_articles) if args.max_articles else "inf"
        progress.update(fetch_task, description=f"success {processed}/{goal}")

    if console:
        progress = Progress(
            SpinnerColumn(spinner_name="line"),
            TextColumn("[progress.description]{task.description}"),
            TimeElapsedColumn(),
            console=console,
            transient=False,
        )
        progress.start()
        search_task = progress.add_task(f"keywords 0/{total_keywords}", total=None)
        fetch_task = progress.add_task(f"success 0/{args.max_articles if args.max_articles else 'inf'}", total=None)
        worker_tasks = [progress.add_task(f"worker-{idx + 1} idle", total=None) for idx in range(stream_workers)]

    def process_futures(blocking: bool) -> None:
        nonlocal processed, stop_stream
        if not inflight:
            return
        futures = list(inflight.keys())
        if blocking:
            done_set, _ = wait(futures, return_when=FIRST_COMPLETED)
        else:
            done_set = [f for f in futures if f.done()]
        for fut in list(done_set):
            slot, aid_hint = inflight.pop(fut)
            free_slots.append(slot)
            try:
                result = fut.result()
            except Exception as exc:
                msg = safe_console(f"[warn] stream fetch failed: {exc}")
                console.log(msg) if console else print(msg)
                if aid_hint:
                    append_processed(processed_file_stream, aid_hint)
                    append_skipped(skipped_file_stream, aid_hint, "fetch-error")
                    processed_stream.add(aid_hint)
                set_worker(slot, "idle", f"{aid_hint} error")
                continue
            if not result:
                append_processed(processed_file_stream, aid_hint)
                append_skipped(skipped_file_stream, aid_hint, "fetch-error")
                processed_stream.add(aid_hint)
                set_worker(slot, "idle", f"{aid_hint} no-result")
                continue
            aid_out, found = result
            if found > 0:
                if args.max_articles and processed >= args.max_articles:
                    base = Path(args.content_out) / aid_out
                    if base.exists():
                        shutil.rmtree(base, ignore_errors=True)
                    set_worker(slot, "idle", f"{aid_out} drop-limit")
                    stop_stream = True
                else:
                    append_processed(processed_file_stream, aid_out)
                    processed_stream.add(aid_out)
                    processed += 1
                    set_worker(slot, "idle", f"{aid_out} ok")
                    update_fetch_task()
                    if args.max_articles and processed >= args.max_articles:
                        stop_stream = True
            elif found == -1:
                append_processed(processed_file_stream, aid_out)
                append_skipped(skipped_file_stream, aid_out, "no-source-data")
                processed_stream.add(aid_out)
                set_worker(slot, "idle", f"{aid_out} no-source")
            else:
                append_processed(processed_file_stream, aid_out)
                append_skipped(skipped_file_stream, aid_out, "no-figures")
                processed_stream.add(aid_out)
                set_worker(slot, "idle", f"{aid_out} no-image")

    try:
        for idx, kw in enumerate(kwds, 1):
            if stop_stream:
                break
            print(f"[stream] Searching: {safe_console(kw)}")
            if progress is not None and search_task is not None:
                progress.update(search_task, description=f"keywords {idx}/{total_keywords}")
            if args.max_per_keyword > 1000:
                items_iter = crossref_cursor_stream(kw, total_max=args.max_per_keyword, mailto=args.mailto, sleep=args.sleep, timeout=args.timeout, max_retries=args.max_retries, family_bias=True, page_rows=1000)
            else:
                items_iter = crossref_search(kw, rows=args.max_per_keyword, mailto=args.mailto, sleep=args.sleep, timeout=args.timeout, max_retries=args.max_retries, family_bias=True)
            for it in items_iter:
                process_futures(blocking=False)
                if stop_stream:
                    break
                doi = (it.get("DOI") or "").lower()
                if doi and doi in seen:
                    continue
                rec = _crossref_item_to_record(it, sleep=args.sleep, timeout=args.timeout, max_retries=args.max_retries)
                append_jsonl(jsonl_path, rec)
                if doi:
                    seen.add(doi)
                art_url = norm_article_url(rec.get("url"), it.get("DOI"))
                if not art_url:
                    continue
                aid2 = parse_article_id(art_url)
                if aid2 in processed_stream:
                    continue
                while not free_slots:
                    process_futures(blocking=True)
                    if stop_stream:
                        break
                if stop_stream:
                    break
                slot = free_slots.pop()
                set_worker(slot, "busy", aid2)
                future = executor.submit(postfetch_article, art_url, args.content_out, args.max_figs, getattr(args, "max_empty_figs", 2), args.sleep, args.timeout, args.max_retries)
                inflight[future] = (slot, aid2)
            if stop_stream:
                break
            process_futures(blocking=False)
            if args.sleep:
                time.sleep(args.sleep)
    finally:
        while inflight:
            process_futures(blocking=True)
        executor.shutdown(wait=True)
        if progress is not None:
            progress.stop()

    print("[done] Streaming search + fetch completed.")


# ======================================================================================
# pairs: Playwright crawl of nature.com search; figure<->source-data PAIRING
#        (the crown jewel from download_nature_pairs.py)
# ======================================================================================


def _render_progress(done: int, total: int, *, width: int = 24) -> str:
    total = max(int(total), 0)
    if total == 0:
        return "[------------------------] 0/0 (  0.0%)"
    done = min(max(int(done), 0), total)
    frac = done / total
    filled = int(round(frac * width))
    bar = "#" * filled + "-" * (width - filled)
    return f"[{bar}] {done}/{total} ({frac * 100:5.1f}%)"


def _get_query_param(url: str, key: str) -> Optional[str]:
    parts = urlsplit(url)
    for k, v in reversed(parse_qsl(parts.query, keep_blank_values=True)):
        if k == key:
            return v
    return None


def _replace_query_param(url: str, key: str, value: Optional[str]) -> str:
    parts = urlsplit(url)
    q = [(k, v) for (k, v) in parse_qsl(parts.query, keep_blank_values=True) if k != key]
    if value is not None:
        q.append((key, value))
    query = urlencode(q, doseq=True)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


def _extract_search_results_count(soup: BeautifulSoup) -> Optional[int]:
    text = soup.get_text(" ", strip=True)
    lowered = text.lower()
    if "no results were found" in lowered or "no results found" in lowered:
        return 0
    m = re.search(r"\b([0-9][0-9,]*)\s+results\b", text, flags=re.IGNORECASE)
    if m:
        try:
            return int(m.group(1).replace(",", ""))
        except Exception:
            return None
    if re.search(r"\b0\s+results\b", text, flags=re.IGNORECASE):
        return 0
    return None


def _has_nature_search_result_cap_message(soup: BeautifulSoup) -> bool:
    return NATURE_SEARCH_RESULT_CAP_MESSAGE.lower() in soup.get_text(" ", strip=True).lower()


@dataclass(frozen=True)
class SearchFetchResult:
    urls: list[str]
    total_results: Optional[int]
    hit_result_cap: bool


def fetch_search_article_urls(search_url, *, max_articles, start_page=1, max_pages=None, session=None, sleep_s=0.2):
    article_urls: list[str] = []
    seen: set[str] = set()
    total_results: Optional[int] = None
    hit_result_cap = False
    end_page = 10_000 if max_pages is None else (start_page + max_pages - 1)
    for page in range(start_page, end_page + 1):
        if len(article_urls) >= max_articles:
            break
        url = _replace_query_param(search_url, "page", str(page)) if page != 1 else _replace_query_param(search_url, "page", None)
        # Use shared polite_get so transient 5xx/429/network blips are retried, not fatal.
        resp = polite_get(url, timeout=60, sleep=sleep_s, max_retries=3, user_agent=BROWSER_USER_AGENT)
        soup = BeautifulSoup(resp.text, "html.parser")
        if total_results is None:
            total_results = _extract_search_results_count(soup)
        if _has_nature_search_result_cap_message(soup):
            hit_result_cap = True
            break
        new_on_page = 0
        for a in soup.select('a[href^="/articles/"]'):
            href = a.get("href")
            if not href:
                continue
            abs_url = urljoin("https://www.nature.com", href)
            if abs_url in seen:
                continue
            seen.add(abs_url)
            article_urls.append(abs_url)
            new_on_page += 1
            if len(article_urls) >= max_articles:
                break
        if new_on_page == 0:
            break
        time.sleep(sleep_s)
    return SearchFetchResult(urls=article_urls, total_results=total_results, hit_result_cap=hit_result_cap)


def fetch_search_results_count(search_url, *, session=None):
    """Return parsed result count, or None on transient failure (retried via polite_get)."""
    url = _replace_query_param(search_url, "page", None)
    try:
        resp = polite_get(url, timeout=60, sleep=0.5, max_retries=3, user_agent=BROWSER_USER_AGENT)
    except Exception:
        return None
    return _extract_search_results_count(BeautifulSoup(resp.text, "html.parser"))


def _infer_years_for_search(search_url, *, session, sleep_s, min_year=1869):
    total = fetch_search_results_count(search_url, session=session)
    if total is None:
        raise SystemExit("Could not parse total result count from Nature search page.")
    years: list[int] = []
    cumulative = 0
    current_year = time.localtime().tm_year
    for y in range(current_year, min_year - 1, -1):
        year_url = _replace_query_param(search_url, "date_range", f"{y}-{y}")
        count = fetch_search_results_count(year_url, session=session)
        if count is None:
            # A single year's count is non-fatal: skip it and keep inferring.
            print(f"[warn] Could not parse result count for year {y}; skipping that year.", file=sys.stderr)
            time.sleep(sleep_s)
            continue
        if count > 0:
            years.append(y)
            cumulative += count
        if cumulative >= total:
            break
        time.sleep(sleep_s)
    if not years:
        raise SystemExit("No results found for any year while inferring year range.")
    return years


def fetch_search_article_urls_split_by_year(search_url, *, max_articles, max_pages, session, sleep_s, year_start, year_end):
    if year_start <= 0 or year_end <= 0:
        raise ValueError("year_start/year_end must be positive when splitting by year.")
    y0, y1 = (year_start, year_end) if year_start <= year_end else (year_end, year_start)
    years = list(range(y1, y0 - 1, -1))
    base_order = (_get_query_param(search_url, "order") or "").strip().lower()
    primary_order = "date_asc" if base_order == "date_asc" else "date_desc"
    secondary_order = "date_desc" if primary_order == "date_asc" else "date_asc"
    urls: list[str] = []
    seen: set[str] = set()
    hit_cap_any = False
    for y in years:
        if len(urls) >= max_articles:
            break
        year_url = _replace_query_param(search_url, "date_range", f"{y}-{y}")
        first = fetch_search_article_urls(_replace_query_param(year_url, "order", primary_order), max_articles=max_articles - len(urls), start_page=1, max_pages=max_pages, session=session, sleep_s=sleep_s)
        for u in first.urls:
            if u in seen:
                continue
            seen.add(u)
            urls.append(u)
            if len(urls) >= max_articles:
                break
        hit_cap_any = hit_cap_any or first.hit_result_cap
        if len(urls) >= max_articles or not first.hit_result_cap:
            continue
        second = fetch_search_article_urls(_replace_query_param(year_url, "order", secondary_order), max_articles=max_articles - len(urls), start_page=1, max_pages=max_pages, session=session, sleep_s=sleep_s)
        for u in second.urls:
            if u in seen:
                continue
            seen.add(u)
            urls.append(u)
            if len(urls) >= max_articles:
                break
    return SearchFetchResult(urls=urls, total_results=None, hit_result_cap=hit_cap_any)


def _ensure_playwright_runtime_env() -> None:
    conda_prefix = os.environ.get("CONDA_PREFIX")
    if not conda_prefix:
        return
    lib_path = str(Path(conda_prefix) / "lib")
    if not Path(lib_path).exists():
        return
    ld_path = os.environ.get("LD_LIBRARY_PATH", "")
    parts = [p for p in ld_path.split(":") if p]
    if lib_path in parts:
        return
    os.environ["LD_LIBRARY_PATH"] = ":".join([lib_path] + parts) if parts else lib_path


def _maybe_dismiss_cookies(page) -> None:
    for button_name in ("Reject optional cookies", "Accept all cookies"):
        try:
            page.get_by_role("button", name=button_name).click(timeout=1500)
            break
        except Exception:
            continue


def _maybe_close_popups(page) -> None:
    for button_name in ("Close", "Close banner Close"):
        try:
            page.get_by_role("button", name=button_name).click(timeout=800)
        except Exception:
            pass


def _is_metadata_only_article_dir(article_dir: Path) -> bool:
    if not article_dir.is_dir():
        return False
    article_json = article_dir / "article.json"
    if not article_json.is_file():
        return False
    for p in article_dir.rglob("*"):
        if p.is_file() and p.name != "article.json":
            return False
    return True


def _prune_metadata_only_article_dir(article_dir: Path) -> bool:
    if not _is_metadata_only_article_dir(article_dir):
        return False
    shutil.rmtree(article_dir)
    return True


@dataclass(frozen=True)
class PairRecord:
    article_url: str
    article_id: str
    doi: Optional[str]
    title: Optional[str]
    figure_index: int
    figure_kind: Optional[str]
    figure_number: Optional[int]
    figure_key: Optional[str]
    figure_caption: Optional[str]
    figure_page_url: Optional[str]
    figure_page_caption: Optional[str]
    data_label: Optional[str]
    image_url: str
    data_url: str
    image_path: str
    data_path: str

    def to_json(self) -> str:
        return json.dumps({
            "article_url": self.article_url, "article_id": self.article_id, "doi": self.doi,
            "title": self.title, "figure_index": self.figure_index, "figure_kind": self.figure_kind,
            "figure_number": self.figure_number, "figure_key": self.figure_key,
            "figure_caption": self.figure_caption, "figure_page_url": self.figure_page_url,
            "figure_page_caption": self.figure_page_caption, "data_label": self.data_label,
            "image_url": self.image_url, "data_url": self.data_url,
            "image_path": self.image_path, "data_path": self.data_path, "created_at": _now_iso(),
        }, ensure_ascii=False)


# The big in-browser extractor: maps each figure to its Source-data file(s).
_PAIRS_EXTRACT_JS = r"""(articleUrl) => {
  const norm = (t) => (t || '').replace(/\s+/g, ' ').trim();
  const abs = (href) => { try { return new URL(href, location.href).toString(); } catch { return href; } };
  const metaDoi =
    document.querySelector('meta[name="citation_doi"]')?.getAttribute('content') ||
    document.querySelector('meta[name="dc.identifier"]')?.getAttribute('content') ||
    document.querySelector('meta[name="dc.Identifier"]')?.getAttribute('content') || null;
  const doi = metaDoi ? metaDoi.replace(/^doi\s*:/i, '').trim() : null;
  const title = norm(document.querySelector('h1')?.textContent) || null;
  const parseFigureIdentity = (caption, fallbackIndex) => {
    const text = norm(caption);
    let m = text.match(/extended\s+data\s+fig(?:ure)?\.?\s*(\d+)/i);
    if (m && m[1]) return { figureKind: 'extended', figureNumber: parseInt(m[1], 10) };
    m = text.match(/^(?:fig\.?|figure)\s*(\d+)\b/i);
    if (m && m[1]) return { figureKind: 'main', figureNumber: parseInt(m[1], 10) };
    return { figureKind: 'main', figureNumber: fallbackIndex };
  };
  const rawFigures = Array.from(document.querySelectorAll('figure')).map((fig, idx) => {
    const caption = norm(fig.querySelector('figcaption')?.textContent) || null;
    const img = fig.querySelector('img');
    let imgUrl = null;
    if (img) {
      imgUrl = img.currentSrc || img.getAttribute('src') || img.getAttribute('data-src') ||
               img.getAttribute('data-original') || img.getAttribute('data-lazy-src') || null;
    }
    if (imgUrl && imgUrl.startsWith('//')) imgUrl = 'https:' + imgUrl;
    let figurePageUrl = null;
    const figureLink = fig.querySelector('a[href*="/figures/"]');
    if (figureLink) figurePageUrl = abs(figureLink.getAttribute('href'));
    const sourceAnchorIds = Array.from(fig.querySelectorAll('a[href]'))
      .map(a => a.getAttribute('href') || '').filter(h => h.includes('#'))
      .map(h => h.split('#').pop()).filter(id => /^MOESM\d+$/i.test(id));
    const ident = parseFigureIdentity(caption, idx + 1);
    return { figureIndex: ident.figureNumber, figureKind: ident.figureKind, figureNumber: ident.figureNumber,
             figureKey: `${ident.figureKind}:${ident.figureNumber}`, caption, imgUrl, figurePageUrl,
             sourceAnchorIds: Array.from(new Set(sourceAnchorIds)) };
  }).filter(f => f.imgUrl);
  const figures = [];
  const seenFigures = new Set();
  for (const fig of rawFigures) {
    const key = `${fig.figureKey}|${fig.imgUrl}`;
    if (seenFigures.has(key)) continue;
    seenFigures.add(key);
    figures.push(fig);
  }
  const moesmToFiles = {};
  const pickDataLinks = (root) => {
    const links = Array.from(root.querySelectorAll('a[href]')).map(a => abs(a.getAttribute('href'))).filter(Boolean);
    return Array.from(new Set(links)).filter(u =>
      u.includes('static-content.springer.com') && /\.(xlsx?|xlsm|csv|tsv|zip|txt)(?:\?|$)/i.test(u));
  };
  const allMoesmIds = new Set(figures.flatMap(f => f.sourceAnchorIds));
  for (const id of allMoesmIds) {
    const el = document.getElementById(id);
    if (!el) continue;
    const files = pickDataLinks(el);
    if (files.length) moesmToFiles[id] = files;
  }
  const expandFigureRefs = (text) => {
    const out = new Set();
    const normalized = (text || '').replace(/[‒–—−]/g, '-');
    const withoutRanges = normalized.replace(/(\d+)\s*-\s*(\d+)/g, (_m, a, b) => {
      const start = parseInt(a, 10); const end = parseInt(b, 10);
      if (Number.isFinite(start) && Number.isFinite(end)) {
        const lo = Math.min(start, end); const hi = Math.max(start, end);
        for (let n = lo; n <= hi; n++) out.add(n);
      }
      return ' ';
    });
    for (const m of withoutRanges.matchAll(/\d+/g)) out.add(parseInt(m[0], 10));
    return Array.from(out);
  };
  const sourceKeysFromLabel = (label) => {
    const cleaned = norm(label).replace(/\([^)]*\)/g, ' ');
    const patterns = [
      { kind: 'extended', re: /source\s+data\s+extended\s+data\s+fig(?:ure)?s?\.?\s*([0-9,\sand‒–—−-]+)/i },
      { kind: 'main', re: /source\s+data\s+fig(?:ure)?s?\.?\s*([0-9,\sand‒–—−-]+)/i },
    ];
    for (const item of patterns) {
      const m = cleaned.match(item.re);
      if (!m || !m[1]) continue;
      return expandFigureRefs(m[1]).map(n => `${item.kind}:${n}`);
    }
    return [];
  };
  const sourceData = [];
  for (const a of Array.from(document.querySelectorAll('a[href]'))) {
    const label = norm(a.textContent);
    const href = abs(a.getAttribute('href'));
    if (!label || !/source\s*data/i.test(label)) continue;
    if (!href.includes('static-content.springer.com')) continue;
    if (!/\.(xlsx?|xlsm|csv|tsv|zip|txt)(?:\?|$)/i.test(href)) continue;
    sourceData.push({ label, url: href, sourceKeys: sourceKeysFromLabel(label) });
  }
  const pairs = [];
  const seenPairs = new Set();
  const addPair = (fig, dataUrl, sourceLabel) => {
    const pairKey = `${fig.figureKey}|${fig.imgUrl}|${dataUrl}`;
    if (seenPairs.has(pairKey)) return;
    seenPairs.add(pairKey);
    pairs.push({ figureIndex: fig.figureIndex, figureKind: fig.figureKind, figureNumber: fig.figureNumber,
      figureKey: fig.figureKey, figureCaption: fig.caption, imageUrl: fig.imgUrl, dataUrl,
      dataLabel: sourceLabel || null, figurePageUrl: fig.figurePageUrl });
  };
  for (const fig of figures) {
    const dataUrls = fig.sourceAnchorIds.flatMap(id => moesmToFiles[id] || []);
    for (const dataUrl of Array.from(new Set(dataUrls))) addPair(fig, dataUrl, null);
    for (const source of sourceData) {
      if (!source.sourceKeys.includes(fig.figureKey)) continue;
      addPair(fig, source.url, source.label);
    }
  }
  return { articleUrl, doi, title, figureCount: figures.length, sourceDataCount: sourceData.length,
           pairCount: pairs.length, figures, sourceData, pairs };
}"""


def extract_figure_page_caption(page, figure_page_url: str) -> Optional[str]:
    last_err = None
    for _ in range(3):
        try:
            page.goto(figure_page_url, wait_until="domcontentloaded", timeout=90_000)
            last_err = None
            break
        except Exception as e:
            last_err = e
            page.wait_for_timeout(1200)
    if last_err is not None:
        raise last_err
    _maybe_dismiss_cookies(page)
    _maybe_close_popups(page)
    try:
        page.wait_for_selector(".c-article-figure-description", timeout=10_000)
    except Exception:
        pass
    return page.evaluate(
        """() => {
      const norm = (t) => (t || '').replace(/\\s+/g, ' ').replace(/\\s+([,.;:])/g, '$1').trim();
      const el = document.querySelector('.c-article-figure-description');
      if (!el) return null;
      let txt = norm(el.textContent);
      txt = txt.replace(/\\s*source\\s*data\\s*$/i, '').trim();
      return txt || null;
    }"""
    )


def extract_pairs_from_article(page, article_url: str) -> dict:
    last_err = None
    for _ in range(3):
        try:
            page.goto(article_url, wait_until="domcontentloaded", timeout=90_000)
            last_err = None
            break
        except Exception as e:
            last_err = e
            page.wait_for_timeout(1200)
    if last_err is not None:
        raise last_err
    _maybe_dismiss_cookies(page)
    for _ in range(3):
        page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(900)
    _maybe_close_popups(page)
    return page.evaluate(_PAIRS_EXTRACT_JS, article_url)


def ensure_pairs_downloaded(pairs, *, out_dir, article_id, session, overwrite, download_timeout_s, download_retries, retry_backoff_s, max_data_bytes=None) -> list[PairRecord]:
    records: list[PairRecord] = []
    article_dir = out_dir / "articles" / article_id
    images_dir = article_dir / "images"
    data_dir = article_dir / "data"
    for p in pairs:
        fig_idx = int(p["figureIndex"])
        img_url = to_full_media_url(str(p["imageUrl"]))
        data_url = str(p["dataUrl"])
        img_path = images_dir / _basename_from_url(img_url)
        data_path = data_dir / _basename_from_url(data_url)
        # Download the data file first under the size cap; skip the whole pair if
        # it is oversized (a pair without its data file is useless for fidelity).
        try:
            download_binary(data_url, data_path, overwrite=overwrite, timeout=download_timeout_s, sleep=retry_backoff_s, max_retries=download_retries, user_agent=BROWSER_USER_AGENT, max_bytes=max_data_bytes)
        except FileTooLargeError as e:
            print(safe_console(f"  [skip-large] {article_id} {p.get('figureKey')} data {_basename_from_url(data_url)}: {e}"))
            continue
        download_binary(img_url, img_path, overwrite=overwrite, timeout=download_timeout_s, sleep=retry_backoff_s, max_retries=download_retries, user_agent=BROWSER_USER_AGENT)
        records.append(PairRecord(
            article_url=str(p.get("articleUrl", "")), article_id=article_id, doi=p.get("doi"),
            title=p.get("title"), figure_index=fig_idx, figure_kind=p.get("figureKind"),
            figure_number=p.get("figureNumber"), figure_key=p.get("figureKey"),
            figure_caption=p.get("figureCaption"), figure_page_url=p.get("figurePageUrl"),
            figure_page_caption=p.get("figurePageCaption"), data_label=p.get("dataLabel"),
            image_url=img_url, data_url=data_url,
            image_path=str(img_path.relative_to(out_dir)).replace("\\", "/"),
            data_path=str(data_path.relative_to(out_dir)).replace("\\", "/"),
        ))
    return records


def _pairs_process_one_article(page, session, article_url, *, out_path, overwrite, download_timeout_s, download_retries, retry_backoff_s, fetch_figure_page_captions, keep_metadata_only_article_dirs, max_data_bytes=None):
    """Extract + download pairs for one article via an open Playwright page. Returns records list."""
    article_id = _normalize_article_id(article_url)
    extracted = extract_pairs_from_article(page, article_url)
    extracted["articleUrl"] = article_url
    extracted["articleId"] = article_id

    if fetch_figure_page_captions:
        unique_urls: list[str] = []
        seen_urls: set[str] = set()
        for fig in extracted.get("figures", []):
            u = fig.get("figurePageUrl")
            if u and u not in seen_urls:
                seen_urls.add(u)
                unique_urls.append(str(u))
        url_to_caption: dict[str, Optional[str]] = {}
        for u in unique_urls:
            try:
                url_to_caption[u] = extract_figure_page_caption(page, u)
            except Exception:
                url_to_caption[u] = None
        for fig in extracted.get("figures", []):
            u = fig.get("figurePageUrl")
            if u:
                fig["figurePageCaption"] = url_to_caption.get(str(u))
        for p0 in extracted.get("pairs", []):
            u = p0.get("figurePageUrl")
            if u:
                p0["figurePageCaption"] = url_to_caption.get(str(u))

    article_dir = out_path / "articles" / article_id
    article_dir.mkdir(parents=True, exist_ok=True)
    (article_dir / "article.json").write_text(json.dumps(extracted, ensure_ascii=False, indent=2), encoding="utf-8")

    normalized_pairs = [{**p0, "articleUrl": article_url, "doi": extracted.get("doi"), "title": extracted.get("title")} for p0 in extracted.get("pairs", [])]
    records = ensure_pairs_downloaded(
        normalized_pairs, out_dir=out_path, article_id=article_id, session=session, overwrite=overwrite,
        download_timeout_s=download_timeout_s, download_retries=download_retries, retry_backoff_s=retry_backoff_s,
        max_data_bytes=max_data_bytes,
    )
    if not keep_metadata_only_article_dirs:
        _prune_metadata_only_article_dir(article_dir)
    return extracted, records


def _pairs_launch_browser(p, headed: bool, browser_channel: str):
    channel = (browser_channel or "").strip()
    if channel.lower() in {"none", "playwright", "bundled", "default"}:
        return p.chromium.launch(headless=not headed)
    return p.chromium.launch(channel=channel, headless=not headed)


def _pairs_worker_process(worker_id, urls, *, out_dir, overwrite, headed, browser_channel, sleep_s, download_timeout_s, download_retries, retry_backoff_s, fetch_figure_page_captions, keep_metadata_only_article_dirs, queue, max_data_bytes=None):
    from playwright.sync_api import sync_playwright  # lazy
    _ensure_playwright_runtime_env()
    out_path = Path(out_dir).resolve()
    session = requests.Session()
    with sync_playwright() as p:
        browser = _pairs_launch_browser(p, headed, browser_channel)
        context = browser.new_context()
        page = context.new_page()
        try:
            page.goto("https://www.nature.com", wait_until="domcontentloaded", timeout=60_000)
            _maybe_dismiss_cookies(page)
        except Exception:
            pass
        for idx, article_url in enumerate(urls, start=1):
            article_id = _normalize_article_id(article_url)
            print(f"[w{worker_id} {idx}/{len(urls)}] {article_id} {article_url}", flush=True)
            try:
                extracted, records = _pairs_process_one_article(
                    page, session, article_url, out_path=out_path, overwrite=overwrite,
                    download_timeout_s=download_timeout_s, download_retries=download_retries,
                    retry_backoff_s=retry_backoff_s, fetch_figure_page_captions=fetch_figure_page_captions,
                    keep_metadata_only_article_dirs=keep_metadata_only_article_dirs,
                    max_data_bytes=max_data_bytes,
                )
                if not records:
                    queue.put({"type": "skipped", "line": json.dumps({
                        "article_url": article_url, "article_id": article_id, "doi": extracted.get("doi"),
                        "title": extracted.get("title"), "figure_count": extracted.get("figureCount", 0),
                        "source_data_count": extracted.get("sourceDataCount", 0), "pair_count": extracted.get("pairCount", 0),
                        "reason": "no-figure-source-data-pairs", "at": _now_iso(), "worker_id": worker_id,
                    }, ensure_ascii=False)})
                for r in records:
                    queue.put({"type": "pair", "line": r.to_json()})
                queue.put({"type": "processed", "url": article_url})
            except Exception as e:
                queue.put({"type": "error", "line": json.dumps({"article_url": article_url, "article_id": article_id, "error": repr(e), "at": _now_iso(), "worker_id": worker_id}, ensure_ascii=False)})
            time.sleep(sleep_s)
        context.close()
        browser.close()


def _pairs_writer_process(queue, *, out_dir, initial_processed_urls, run_total, show_progress, flush_state_interval_s=2.0):
    out_path = Path(out_dir)
    pairs_path = out_path / "pairs.jsonl"
    errors_path = out_path / "errors.jsonl"
    skipped_path = out_path / "skipped.jsonl"
    state_path = out_path / "state.json"
    processed: set[str] = set(initial_processed_urls)
    pending_state_write = False
    next_state_flush = time.time() + flush_state_interval_s
    run_done = pair_lines = error_lines = skipped_lines = 0
    pairs_path.parent.mkdir(parents=True, exist_ok=True)
    pairs_f = open(pairs_path, "a", encoding="utf-8")
    errors_f = open(errors_path, "a", encoding="utf-8")
    skipped_f = open(skipped_path, "a", encoding="utf-8")
    try:
        while True:
            msg = queue.get()
            if msg is None:
                break
            kind = msg.get("type")
            if kind == "pair":
                pairs_f.write(msg["line"] + "\n"); pair_lines += 1
            elif kind == "error":
                errors_f.write(msg["line"] + "\n"); error_lines += 1
            elif kind == "skipped":
                skipped_f.write(msg["line"] + "\n"); skipped_lines += 1
            elif kind == "processed":
                url = msg["url"]
                if url not in processed:
                    processed.add(url); run_done += 1; pending_state_write = True
            else:
                continue
            now = time.time()
            if now >= next_state_flush:
                pairs_f.flush(); errors_f.flush()
                if pending_state_write:
                    _atomic_write_json(state_path, {"processed_article_urls": sorted(processed), "updated_at": _now_iso()})
                    pending_state_write = False
                if show_progress:
                    print(f"{_render_progress(run_done, run_total)} pairs={pair_lines} skipped={skipped_lines} errors={error_lines}", file=sys.stderr, flush=True)
                next_state_flush = now + flush_state_interval_s
        pairs_f.flush(); errors_f.flush(); skipped_f.flush()
        if pending_state_write:
            _atomic_write_json(state_path, {"processed_article_urls": sorted(processed), "updated_at": _now_iso()})
        if show_progress:
            print(f"{_render_progress(run_done, run_total)} pairs={pair_lines} skipped={skipped_lines} errors={error_lines}", file=sys.stderr, flush=True)
    finally:
        pairs_f.close(); errors_f.close(); skipped_f.close()


def _pairs_resolve_article_urls(args, session) -> SearchFetchResult:
    """Resolve candidate article URLs from --urls-file or Nature search (optionally split-by-year)."""
    candidate_limit = args.max_candidates if args.max_candidates > 0 else 10_000
    max_pages = None if args.max_pages == 0 else args.max_pages
    if args.urls_file:
        urls = []
        for line in Path(args.urls_file).read_text(encoding="utf-8").splitlines():
            u = line.strip()
            if u and not u.startswith("#"):
                urls.append(u)
        file_urls = urls[:candidate_limit]
        return SearchFetchResult(urls=file_urls, total_results=len(file_urls), hit_result_cap=False)
    if args.split_by_year:
        if args.start_page != 1:
            print("Note: --start-page is ignored when --split-by-year is used.", file=sys.stderr)
        year_start = int(args.year_start or 0)
        year_end = int(args.year_end or 0)
        if year_start > 0 and year_end <= 0:
            year_end = time.localtime().tm_year
        if year_end > 0 and year_start <= 0:
            year_start = year_end
        if year_start <= 0 or year_end <= 0:
            dr = (_get_query_param(args.search_url, "date_range") or "").strip()
            m = re.match(r"^(\d{4})-(\d{4})$", dr)
            if m:
                if year_start <= 0:
                    year_start = int(m.group(1))
                if year_end <= 0:
                    year_end = int(m.group(2))
        if year_start <= 0 or year_end <= 0:
            # No explicit/derivable range: walk back from the current year on demand.
            # split_by_year stops as soon as candidate_limit URLs are collected, so we
            # don't need the fragile global year-count inference — empty years are skipped.
            year_end = year_end if year_end > 0 else time.localtime().tm_year
            year_start = year_start if year_start > 0 else 1869
            print(f"[info] split-by-year range (on-demand, stops once enough collected): {year_start}-{year_end}", file=sys.stderr)
        return fetch_search_article_urls_split_by_year(args.search_url, max_articles=candidate_limit, max_pages=max_pages, session=session, sleep_s=args.sleep_s, year_start=year_start, year_end=year_end)
    result = fetch_search_article_urls(args.search_url, max_articles=candidate_limit, start_page=args.start_page, max_pages=max_pages, session=session, sleep_s=args.sleep_s)
    if result.hit_result_cap:
        total = result.total_results
        if total is not None:
            print(f"Note: Nature search caps results at 1000 per query (this query reports {total}). Use --split-by-year for more.", file=sys.stderr)
        else:
            print("Note: Nature search caps results at 1000 per query. Use --split-by-year for more.", file=sys.stderr)
    return result


def cmd_pairs(args):
    from playwright.sync_api import sync_playwright  # lazy import; only `pairs` needs it

    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    # 0 = no cap; otherwise convert MB -> bytes for oversized source-data skipping.
    max_data_bytes = int(args.max_file_size_mb * 1024 * 1024) if args.max_file_size_mb and args.max_file_size_mb > 0 else None
    if max_data_bytes:
        print(f"[info] data-file size cap: {args.max_file_size_mb} MB (oversized source-data files are skipped)", file=sys.stderr)

    if not args.keep_metadata_only_article_dirs:
        articles_root = out_dir / "articles"
        if articles_root.is_dir():
            pruned = 0
            for p in articles_root.iterdir():
                if not p.is_dir():
                    continue
                try:
                    if _prune_metadata_only_article_dir(p):
                        pruned += 1
                except Exception:
                    continue
            if pruned:
                print(f"Pruned {pruned} metadata-only article dirs.")

    state_path = out_dir / "state.json"
    state = {}
    if not args.ignore_state and state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except Exception:
            state = {}
    processed: set[str] = set(state.get("processed_article_urls", []))

    if args.max_articles < 0:
        raise SystemExit("--max-articles must be >= 0")
    if args.max_candidates < 0:
        raise SystemExit("--max-candidates must be >= 0")

    target_success_articles = args.max_articles if args.max_articles > 0 else None
    if target_success_articles is not None and args.workers > 1:
        print("Note: --max-articles is an exact successful-article target; forcing --workers=1.", file=sys.stderr)
        args.workers = 1

    session = requests.Session()
    search_result = _pairs_resolve_article_urls(args, session)
    article_urls = search_result.urls
    pairs_path = out_dir / "pairs.jsonl"
    errors_path = out_dir / "errors.jsonl"
    skipped_path = out_dir / "skipped.jsonl"

    if not article_urls:
        print(f"Done. Output: {out_dir}")
        print(f"- pairs: {pairs_path if pairs_path.exists() else '(none)'}")
        return 0
    if args.workers < 1:
        raise SystemExit("--workers must be >= 1")
    if args.workers > 1 and args.headed:
        raise SystemExit("Cannot use --headed with --workers > 1")

    remaining_urls = [u for u in article_urls if u not in processed]
    if not remaining_urls:
        print(f"Done. Output: {out_dir}")
        print(f"- pairs: {pairs_path if pairs_path.exists() else '(none)'}")
        return 0

    successful_articles = 0
    attempted_articles = 0

    if args.workers == 1:
        _ensure_playwright_runtime_env()
        with sync_playwright() as p:
            browser = _pairs_launch_browser(p, args.headed, args.browser_channel)
            context = browser.new_context()
            page = context.new_page()
            try:
                page.goto("https://www.nature.com", wait_until="domcontentloaded", timeout=60_000)
                _maybe_dismiss_cookies(page)
            except Exception:
                pass
            total = len(remaining_urls)
            for idx, article_url in enumerate(remaining_urls, start=1):
                if target_success_articles is not None and successful_articles >= target_success_articles:
                    break
                article_id = _normalize_article_id(article_url)
                if args.no_progress:
                    print(f"[{idx}/{total}] success={successful_articles}/{target_success_articles if target_success_articles is not None else 'inf'} {article_id} {article_url}")
                else:
                    print(f"{_render_progress(idx - 1, total)} success={successful_articles}/{target_success_articles if target_success_articles is not None else 'inf'} {article_id} {article_url}")
                attempted_articles += 1
                try:
                    extracted, records = _pairs_process_one_article(
                        page, session, article_url, out_path=out_dir, overwrite=args.overwrite,
                        download_timeout_s=args.download_timeout_s, download_retries=args.download_retries,
                        retry_backoff_s=args.retry_backoff_s, fetch_figure_page_captions=args.fetch_figure_page_captions,
                        keep_metadata_only_article_dirs=args.keep_metadata_only_article_dirs,
                        max_data_bytes=max_data_bytes,
                    )
                    if not records:
                        with open(skipped_path, "a", encoding="utf-8") as f:
                            f.write(json.dumps({
                                "article_url": article_url, "article_id": article_id, "doi": extracted.get("doi"),
                                "title": extracted.get("title"), "figure_count": extracted.get("figureCount", 0),
                                "source_data_count": extracted.get("sourceDataCount", 0), "pair_count": extracted.get("pairCount", 0),
                                "reason": "no-figure-source-data-pairs", "at": _now_iso(),
                            }, ensure_ascii=False) + "\n")
                    with open(pairs_path, "a", encoding="utf-8") as f:
                        for r in records:
                            f.write(r.to_json() + "\n")
                    if records:
                        successful_articles += 1
                    processed.add(article_url)
                    _atomic_write_json(state_path, {"processed_article_urls": sorted(processed), "updated_at": _now_iso()})
                except Exception as e:
                    with open(errors_path, "a", encoding="utf-8") as f:
                        f.write(json.dumps({"article_url": article_url, "article_id": article_id, "error": repr(e), "at": _now_iso()}, ensure_ascii=False) + "\n")
                time.sleep(args.sleep_s)
            if target_success_articles is not None and successful_articles < target_success_articles:
                print(f"Warning: requested {target_success_articles} successful articles, but only got {successful_articles} after {attempted_articles} candidates. Increase --max-candidates or use --split-by-year.", file=sys.stderr)
            context.close()
            browser.close()
    else:
        ctx = mp.get_context("spawn")
        queue: "mp.Queue" = ctx.Queue(maxsize=max(1000, args.workers * 50))
        run_total = len(remaining_urls)
        writer = ctx.Process(target=_pairs_writer_process, kwargs={"queue": queue, "out_dir": str(out_dir), "initial_processed_urls": sorted(processed), "run_total": run_total, "show_progress": not args.no_progress})
        writer.start()
        shards: list[list[str]] = [[] for _ in range(args.workers)]
        for i, url in enumerate(remaining_urls):
            shards[i % args.workers].append(url)
        workers: list[mp.Process] = []
        for worker_id, urls in enumerate(shards, start=1):
            if not urls:
                continue
            proc = ctx.Process(target=_pairs_worker_process, args=(worker_id, urls), kwargs={
                "out_dir": str(out_dir), "overwrite": args.overwrite, "headed": args.headed,
                "browser_channel": args.browser_channel, "sleep_s": args.sleep_s,
                "download_timeout_s": args.download_timeout_s, "download_retries": args.download_retries,
                "retry_backoff_s": args.retry_backoff_s, "fetch_figure_page_captions": args.fetch_figure_page_captions,
                "keep_metadata_only_article_dirs": args.keep_metadata_only_article_dirs, "queue": queue,
                "max_data_bytes": max_data_bytes,
            })
            proc.start()
            workers.append(proc)
        exit_code = 0
        for proc in workers:
            proc.join()
            if proc.exitcode != 0:
                exit_code = 1
        queue.put(None)
        writer.join()
        if writer.exitcode != 0:
            exit_code = 1
        if errors_path.exists() and errors_path.stat().st_size == 0:
            errors_path.unlink()
        if skipped_path.exists() and skipped_path.stat().st_size == 0:
            skipped_path.unlink()
        if exit_code != 0:
            print("One or more workers exited with errors.")
            return exit_code

    print(f"Done. Output: {out_dir}")
    print(f"- pairs: {pairs_path}")
    if attempted_articles:
        target_label = str(target_success_articles) if target_success_articles is not None else "unlimited"
        print(f"- successful_articles: {successful_articles}/{target_label}")
        print(f"- inspected_candidates: {attempted_articles}")
    print(f"- skipped: {skipped_path if skipped_path.exists() else '(none)'}")
    print(f"- errors: {errors_path if errors_path.exists() else '(none)'}")
    return 0


# ======================================================================================
# CLI
# ======================================================================================


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="nature_crawler",
        description="Nature crawler (merged): API discovery + authorized fetch + figure<->source-data pairing.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    # --- search (Crossref + Europe PMC) ---
    s = sub.add_parser("search", help="Search Nature family via Crossref + Europe PMC")
    s.add_argument("--query", required=True)
    s.add_argument("--max", type=int, default=10)
    s.add_argument("--out", default="outputs/search_run")
    s.add_argument("--mailto", default=None)
    s.add_argument("--sleep", type=float, default=1.0)
    s.add_argument("--timeout", type=float, default=300)
    s.add_argument("--max-retries", type=int, default=3)
    s.add_argument("--append", action="store_true")
    s.add_argument("--no-family-bias", action="store_true")
    s.set_defaults(func=cmd_search)

    # --- fig (single figure page) ---
    f = sub.add_parser("fig", help="Fetch image+caption from a nature.com figure page (authorized)")
    f.add_argument("--url", required=True)
    f.add_argument("--out", default="outputs/nature_content")
    f.add_argument("--sleep", type=float, default=1.0)
    f.add_argument("--timeout", type=float, default=300)
    f.add_argument("--max-retries", type=int, default=3)
    f.set_defaults(func=cmd_fig)

    # --- source (single article Source data) ---
    sd = sub.add_parser("source", help="Fetch Source data from a nature.com article page (authorized)")
    sd.add_argument("--url", required=True)
    sd.add_argument("--out", default="outputs/nature_content")
    sd.add_argument("--section-id", default=None)
    sd.add_argument("--filter", default=None)
    sd.add_argument("--sleep", type=float, default=1.0)
    sd.add_argument("--timeout", type=float, default=300)
    sd.add_argument("--max-retries", type=int, default=3)
    sd.set_defaults(func=cmd_source)

    # --- postfetch (figures + source data for a JSONL of articles) ---
    pf = sub.add_parser("postfetch", help="Fetch ALL (figures + source data) for articles in a JSONL")
    pf.add_argument("--jsonl", required=True)
    pf.add_argument("--out", default="outputs/nature_content")
    pf.add_argument("--max-figs", type=int, default=12)
    pf.add_argument("--max-articles", type=int, default=0)
    pf.add_argument("--max-empty-figs", type=int, default=2, help="Max consecutive empty figure pages before stopping")
    pf.add_argument("--sort", choices=["year_desc", "year_asc", "input"], default="year_desc")
    pf.add_argument("--sleep", type=float, default=1.0)
    pf.add_argument("--timeout", type=float, default=300)
    pf.add_argument("--max-retries", type=int, default=3)
    pf.add_argument("--max-per-keyword", type=int, default=None, help="(compat) accepted but ignored in postfetch")
    pf.add_argument("--workers", type=int, default=1, help="Worker processes for fetching")
    pf.add_argument("--processed-file", default=None, help="Processed record file (default: <out>/_processed.txt)")
    pf.set_defaults(func=cmd_postfetch)

    # --- auto (multi-keyword search -> fetch all) ---
    au = sub.add_parser("auto", help="Search multiple keywords then fetch ALL content (optional streaming)")
    au.add_argument("--keywords-file", default=None)
    au.add_argument("--max-per-keyword", type=int, default=50)
    au.add_argument("--search-out", default="outputs/search_auto")
    au.add_argument("--content-out", default="outputs/nature_content")
    au.add_argument("--mailto", default=None)
    au.add_argument("--sleep", type=float, default=1.0)
    au.add_argument("--timeout", type=float, default=300)
    au.add_argument("--max-retries", type=int, default=3)
    au.add_argument("--max-articles", type=int, default=0)
    au.add_argument("--max-figs", type=int, default=12)
    au.add_argument("--max-empty-figs", type=int, default=2)
    au.add_argument("--sort", choices=["year_desc", "year_asc", "input"], default="year_desc")
    au.add_argument("--workers", type=int, default=1, help="Workers for postfetch in non-stream mode")
    au.add_argument("--processed-file", default=None, help="Processed record file (default: <content-out>/_processed.txt)")
    au.add_argument("--stream", action="store_true", help="Streaming mode: per-article immediate fetch")
    au.add_argument("--stream-workers", type=int, default=1, help="Streaming fetch worker threads (>=1)")
    au.set_defaults(func=cmd_auto)

    # --- pairs (Playwright figure<->source-data pairing) ---
    pr = sub.add_parser("pairs", help="Crawl nature.com search; download figure images AND their matched Source-data files as PAIRS (Playwright)")
    src = pr.add_mutually_exclusive_group(required=False)
    src.add_argument("--search-url", dest="search_url", default=DEFAULT_SEARCH_URL)
    src.add_argument("--urls-file", help="Text file with one article URL per line.")
    pr.add_argument("--max-articles", type=int, default=10, help="Target successful articles (>=1 pair). 0 = no success cap.")
    pr.add_argument("--max-candidates", type=int, default=0, help="Max candidate URLs to inspect. 0 = search cap.")
    pr.add_argument("--start-page", type=int, default=1)
    pr.add_argument("--max-pages", type=int, default=0, help="0 = no limit.")
    pr.add_argument("--split-by-year", action="store_true", help="Split search per-year to bypass the 1000-results cap.")
    pr.add_argument("--year-start", type=int, default=0, help="Start year for --split-by-year. 0 = infer.")
    pr.add_argument("--year-end", type=int, default=0, help="End year for --split-by-year. 0 = current year.")
    pr.add_argument("--out", default="downloads")
    pr.add_argument("--overwrite", action="store_true")
    pr.add_argument("--headed", action="store_true")
    pr.add_argument("--browser-channel", default="none", help='Chromium channel ("msedge","chrome"). "none" = bundled.')
    pr.add_argument("--sleep-s", type=float, default=0.2)
    pr.add_argument("--download-timeout-s", type=int, default=60, help="Per-file read timeout (s). Connect timeout is fixed at 15s. A stuck socket aborts and retries after this.")
    pr.add_argument("--download-retries", type=int, default=3)
    pr.add_argument("--retry-backoff-s", type=float, default=1.0)
    pr.add_argument("--max-file-size-mb", type=float, default=50.0, help="Skip source-data files larger than this many MB (0 = no cap). Default 50.")
    pr.add_argument("--fetch-figure-page-captions", action="store_true", help="Fetch long captions from /figures/N pages.")
    pr.add_argument("--keep-metadata-only-article-dirs", action="store_true", help="Keep article dirs with only article.json.")
    pr.add_argument("--ignore-state", action="store_true", help="Ignore state.json and reprocess URLs.")
    pr.add_argument("--workers", type=int, default=1, help="Parallel worker processes (1 = sequential).")
    pr.add_argument("--no-progress", action="store_true", help="Disable progress output.")
    pr.set_defaults(func=cmd_pairs)

    return p


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    result = args.func(args)
    return int(result) if isinstance(result, int) else 0


if __name__ == "__main__":
    raise SystemExit(main())

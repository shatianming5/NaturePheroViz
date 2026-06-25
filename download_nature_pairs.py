import argparse
import json
import os
import multiprocessing as mp
import re
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import Page, sync_playwright


DEFAULT_SEARCH_URL = (
    'https://www.nature.com/search?q=%22Source%20Data%22&journal=nature&order=date_desc'
)

NATURE_SEARCH_RESULT_CAP_MESSAGE = "We only show the first 1000 results for any query"

# A realistic browser UA reduces (but does not eliminate) Nature/Springer bot
# challenges on the search endpoint; a bare "Mozilla/5.0" is challenged more readily.
_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def _is_bot_challenge(html: str) -> bool:
    """Detect the Akamai/Cloudflare-style 'Client Challenge' interstitial that Nature
    serves to rate-limited / automated clients (a tiny JS page with no real content)."""
    if not html or len(html) > 20000:
        return False
    low = html.lower()
    return ("client challenge" in low) or ("just a moment" in low and "enable javascript" in low)


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())


def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".part")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp_path, path)


def _render_progress(done: int, total: int, *, width: int = 24) -> str:
    total = max(int(total), 0)
    if total == 0:
        return "[------------------------] 0/0 (  0.0%)"
    done = min(max(int(done), 0), total)
    frac = done / total
    filled = int(round(frac * width))
    bar = "#" * filled + "-" * (width - filled)
    return f"[{bar}] {done}/{total} ({frac * 100:5.1f}%)"


def _safe_filename(name: str) -> str:
    name = re.sub(r"[\\/:*?\"<>|]", "_", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:180] if len(name) > 180 else name


def _ensure_https(url: str) -> str:
    if url.startswith("//"):
        return "https:" + url
    return url


def to_full_media_url(url: str) -> str:
    url = _ensure_https(url)
    try:
        parts = urlsplit(url)
        if parts.netloc != "media.springernature.com":
            return url
        path = parts.path.lstrip("/")
        # Common patterns: lw685/..., lw1200/..., m312/..., w215h120/..., full/...
        m = re.match(r"^(?:lw\d+|m\d+|w\d+h\d+|full)/(.+)$", path)
        if not m:
            return url
        new_path = "/full/" + m.group(1)
        return urlunsplit((parts.scheme, parts.netloc, new_path, parts.query, parts.fragment))
    except Exception:
        return url


def _basename_from_url(url: str) -> str:
    path = urlsplit(url).path
    base = Path(path).name
    return _safe_filename(base) if base else "download.bin"


def _normalize_article_id(article_url: str) -> str:
    parsed = urlparse(article_url)
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) >= 2 and parts[0] == "articles":
        return parts[1]
    return _safe_filename(parsed.path.strip("/")) or "article"


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


class SearchBlockedError(RuntimeError):
    """Raised when Nature's search endpoint serves a bot-challenge (rate-limited)."""


def fetch_search_article_urls(
    search_url: str,
    *,
    max_articles: int,
    start_page: int = 1,
    max_pages: Optional[int] = None,
    session: Optional[requests.Session] = None,
    sleep_s: float = 0.2,
) -> SearchFetchResult:
    sess = session or requests.Session()
    headers = {"User-Agent": _BROWSER_UA}

    article_urls: list[str] = []
    seen: set[str] = set()

    total_results: Optional[int] = None
    hit_result_cap = False

    end_page = 10_000 if max_pages is None else (start_page + max_pages - 1)
    for page in range(start_page, end_page + 1):
        if len(article_urls) >= max_articles:
            break

        url = (
            _replace_query_param(search_url, "page", str(page))
            if page != 1
            else _replace_query_param(search_url, "page", None)
        )
        # Retry with backoff on a bot-challenge interstitial (rate-limit), so a
        # transient challenge doesn't silently look like "0 results".
        resp = None
        for attempt in range(1, 5):
            resp = sess.get(url, headers=headers, timeout=60)
            resp.raise_for_status()
            if not _is_bot_challenge(resp.text):
                break
            if attempt < 4:
                time.sleep(min(2.0 * attempt, 8.0))
        if resp is not None and _is_bot_challenge(resp.text):
            raise SearchBlockedError(
                "Nature search is serving a bot-challenge (rate-limited). Wait and retry, "
                "raise --sleep-s, or run from a different IP."
            )

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

    return SearchFetchResult(
        urls=article_urls,
        total_results=total_results,
        hit_result_cap=hit_result_cap,
    )


def fetch_search_results_count(
    search_url: str,
    *,
    session: Optional[requests.Session] = None,
) -> Optional[int]:
    sess = session or requests.Session()
    headers = {"User-Agent": _BROWSER_UA}
    url = _replace_query_param(search_url, "page", None)
    resp = sess.get(url, headers=headers, timeout=60)
    resp.raise_for_status()
    if _is_bot_challenge(resp.text):
        return None  # rate-limited: treat as unparseable (caller skips / handles)
    soup = BeautifulSoup(resp.text, "html.parser")
    return _extract_search_results_count(soup)


def _infer_years_for_search(
    search_url: str,
    *,
    session: requests.Session,
    sleep_s: float,
    min_year: int = 1869,
) -> list[int]:
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
            # One unparseable year must not kill the whole crawl — skip it.
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


def fetch_search_article_urls_split_by_year(
    search_url: str,
    *,
    max_articles: int,
    max_pages: Optional[int],
    session: requests.Session,
    sleep_s: float,
    year_start: int,
    year_end: int,
) -> SearchFetchResult:
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

        first = fetch_search_article_urls(
            _replace_query_param(year_url, "order", primary_order),
            max_articles=max_articles - len(urls),
            start_page=1,
            max_pages=max_pages,
            session=session,
            sleep_s=sleep_s,
        )
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

        second = fetch_search_article_urls(
            _replace_query_param(year_url, "order", secondary_order),
            max_articles=max_articles - len(urls),
            start_page=1,
            max_pages=max_pages,
            session=session,
            sleep_s=sleep_s,
        )
        for u in second.urls:
            if u in seen:
                continue
            seen.add(u)
            urls.append(u)
            if len(urls) >= max_articles:
                break

    return SearchFetchResult(urls=urls, total_results=None, hit_result_cap=hit_cap_any)


def _maybe_dismiss_cookies(page: Page) -> None:
    for button_name in ("Reject optional cookies", "Accept all cookies"):
        try:
            page.get_by_role("button", name=button_name).click(timeout=1500)
            break
        except Exception:
            continue


def _maybe_close_popups(page: Page) -> None:
    # Best-effort close of newsletter / banner popups.
    for button_name in ("Close", "Close banner Close"):
        try:
            page.get_by_role("button", name=button_name).click(timeout=800)
        except Exception:
            pass


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
        return json.dumps(
            {
                "article_url": self.article_url,
                "article_id": self.article_id,
                "doi": self.doi,
                "title": self.title,
                "figure_index": self.figure_index,
                "figure_kind": self.figure_kind,
                "figure_number": self.figure_number,
                "figure_key": self.figure_key,
                "figure_caption": self.figure_caption,
                "figure_page_url": self.figure_page_url,
                "figure_page_caption": self.figure_page_caption,
                "data_label": self.data_label,
                "image_url": self.image_url,
                "data_url": self.data_url,
                "image_path": self.image_path,
                "data_path": self.data_path,
                "created_at": _now_iso(),
            },
            ensure_ascii=False,
        )


def extract_figure_page_caption(page: Page, figure_page_url: str) -> Optional[str]:
    last_err: Optional[BaseException] = None
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
      const norm = (t) =>
        (t || '')
          .replace(/\\s+/g, ' ')
          .replace(/\\s+([,.;:])/g, '$1')
          .trim();
      const el = document.querySelector('.c-article-figure-description');
      if (!el) return null;
      let txt = norm(el.textContent);
      txt = txt.replace(/\\s*source\\s*data\\s*$/i, '').trim();
      return txt || null;
    }"""
    )


def extract_pairs_from_article(page: Page, article_url: str) -> dict:
    last_err: Optional[BaseException] = None
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

    # Trigger lazy content.
    for _ in range(3):
        page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(900)

    _maybe_close_popups(page)

    return page.evaluate(
        """(articleUrl) => {
      const norm = (t) => (t || '').replace(/\\s+/g, ' ').trim();
      const abs = (href) => {
        try { return new URL(href, location.href).toString(); } catch { return href; }
      };
      const metaDoi =
        document.querySelector('meta[name=\"citation_doi\"]')?.getAttribute('content') ||
        document.querySelector('meta[name=\"dc.identifier\"]')?.getAttribute('content') ||
        document.querySelector('meta[name=\"dc.Identifier\"]')?.getAttribute('content') ||
        null;
      const doi = metaDoi ? metaDoi.replace(/^doi\\s*:/i, '').trim() : null;

      const title = norm(document.querySelector('h1')?.textContent) || null;

      const parseFigureIdentity = (caption, fallbackIndex) => {
        const text = norm(caption);
        let m = text.match(/extended\\s+data\\s+fig(?:ure)?\\.?\\s*(\\d+)/i);
        if (m && m[1]) {
          return { figureKind: 'extended', figureNumber: parseInt(m[1], 10) };
        }
        m = text.match(/^(?:fig\\.?|figure)\\s*(\\d+)\\b/i);
        if (m && m[1]) {
          return { figureKind: 'main', figureNumber: parseInt(m[1], 10) };
        }
        return { figureKind: 'main', figureNumber: fallbackIndex };
      };

      const rawFigures = Array.from(document.querySelectorAll('figure')).map((fig, idx) => {
        const caption = norm(fig.querySelector('figcaption')?.textContent) || null;
        const img = fig.querySelector('img');
        let imgUrl = null;
        if (img) {
          imgUrl =
            img.currentSrc ||
            img.getAttribute('src') ||
            img.getAttribute('data-src') ||
            img.getAttribute('data-original') ||
            img.getAttribute('data-lazy-src') ||
            null;
        }
        if (imgUrl && imgUrl.startsWith('//')) imgUrl = 'https:' + imgUrl;

        let figurePageUrl = null;
        const figureLink = fig.querySelector('a[href*=\"/figures/\"]');
        if (figureLink) figurePageUrl = abs(figureLink.getAttribute('href'));

        const sourceAnchorIds = Array.from(fig.querySelectorAll('a[href]'))
          .map(a => a.getAttribute('href') || '')
          .filter(h => h.includes('#'))
          .map(h => h.split('#').pop())
          .filter(id => /^MOESM\\d+$/i.test(id));

        const ident = parseFigureIdentity(caption, idx + 1);
        const figureIndex = ident.figureNumber;
        const figureKey = `${ident.figureKind}:${ident.figureNumber}`;

        return {
          figureIndex,
          figureKind: ident.figureKind,
          figureNumber: ident.figureNumber,
          figureKey,
          caption,
          imgUrl,
          figurePageUrl,
          sourceAnchorIds: Array.from(new Set(sourceAnchorIds)),
        };
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
        const links = Array.from(root.querySelectorAll('a[href]'))
          .map(a => abs(a.getAttribute('href')))
          .filter(Boolean);
        return Array.from(new Set(links)).filter(u =>
          u.includes('static-content.springer.com') &&
          /\\.(xlsx?|xlsm|csv|tsv|zip|txt)(?:\\?|$)/i.test(u)
        );
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
        const normalized = (text || '').replace(/[\\u2012\\u2013\\u2014\\u2212]/g, '-');
        const withoutRanges = normalized.replace(/(\\d+)\\s*-\\s*(\\d+)/g, (_m, a, b) => {
          const start = parseInt(a, 10);
          const end = parseInt(b, 10);
          if (Number.isFinite(start) && Number.isFinite(end)) {
            const lo = Math.min(start, end);
            const hi = Math.max(start, end);
            for (let n = lo; n <= hi; n++) out.add(n);
          }
          return ' ';
        });
        for (const m of withoutRanges.matchAll(/\\d+/g)) {
          out.add(parseInt(m[0], 10));
        }
        return Array.from(out);
      };

      const sourceKeysFromLabel = (label) => {
        const cleaned = norm(label).replace(/\\([^)]*\\)/g, ' ');
        const patterns = [
          { kind: 'extended', re: /source\\s+data\\s+extended\\s+data\\s+fig(?:ure)?s?\\.?\\s*([0-9,\\sand\\u2012\\u2013\\u2014\\u2212-]+)/i },
          { kind: 'main', re: /source\\s+data\\s+fig(?:ure)?s?\\.?\\s*([0-9,\\sand\\u2012\\u2013\\u2014\\u2212-]+)/i },
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
        if (!label || !/source\\s*data/i.test(label)) continue;
        if (!href.includes('static-content.springer.com')) continue;
        if (!/\\.(xlsx?|xlsm|csv|tsv|zip|txt)(?:\\?|$)/i.test(href)) continue;
        sourceData.push({
          label,
          url: href,
          sourceKeys: sourceKeysFromLabel(label),
        });
      }

      const pairs = [];
      const seenPairs = new Set();
      const addPair = (fig, dataUrl, sourceLabel) => {
        const pairKey = `${fig.figureKey}|${fig.imgUrl}|${dataUrl}`;
        if (seenPairs.has(pairKey)) return;
        seenPairs.add(pairKey);
        pairs.push({
          figureIndex: fig.figureIndex,
          figureKind: fig.figureKind,
          figureNumber: fig.figureNumber,
          figureKey: fig.figureKey,
          figureCaption: fig.caption,
          imageUrl: fig.imgUrl,
          dataUrl,
          dataLabel: sourceLabel || null,
          figurePageUrl: fig.figurePageUrl,
        });
      };

      for (const fig of figures) {
        const dataUrls = fig.sourceAnchorIds.flatMap(id => moesmToFiles[id] || []);
        const uniqueDataUrls = Array.from(new Set(dataUrls));
        for (const dataUrl of uniqueDataUrls) {
          addPair(fig, dataUrl, null);
        }
        for (const source of sourceData) {
          if (!source.sourceKeys.includes(fig.figureKey)) continue;
          addPair(fig, source.url, source.label);
        }
      }

      return { articleUrl, doi, title, figureCount: figures.length, sourceDataCount: sourceData.length, pairCount: pairs.length, figures, sourceData, pairs };
    }""",
        article_url,
    )


# ---------------------------------------------------------------------------
# requests + BeautifulSoup port of extract_pairs_from_article.
#
# Nature/Springer serves automation browsers (playwright headless AND headed) a
# "Client Challenge" bot-wall (0 figures), while a plain requests.get returns the
# full article HTML with all figures + source-data links. This static port mirrors
# the JS DOM extraction above so article discovery works without a real browser.
# ---------------------------------------------------------------------------
_DATA_EXT_RE = re.compile(r"\.(xlsx?|xlsm|csv|tsv|zip|txt)(?:\?|$)", re.I)
_MOESM_ID_RE = re.compile(r"^MOESM\d+$", re.I)


def _norm_text(t: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (t or "")).strip()


def _abs_url(href: Optional[str], base: str) -> str:
    if not href:
        return ""
    try:
        return urljoin(base, href)
    except Exception:
        return href


def _parse_figure_identity(caption: Optional[str], fallback_index: int) -> tuple[str, int]:
    text = _norm_text(caption)
    m = re.search(r"extended\s+data\s+fig(?:ure)?\.?\s*(\d+)", text, re.I)
    if m:
        return ("extended", int(m.group(1)))
    m = re.search(r"^(?:fig\.?|figure)\s*(\d+)\b", text, re.I)
    if m:
        return ("main", int(m.group(1)))
    return ("main", fallback_index)


def _expand_figure_refs(text: str) -> list[int]:
    out: set[int] = set()
    normalized = re.sub(r"[\u2012\u2013\u2014\u2212]", "-", text or "")

    def _range_sub(mm: "re.Match") -> str:
        a, b = int(mm.group(1)), int(mm.group(2))
        lo, hi = min(a, b), max(a, b)
        for n in range(lo, hi + 1):
            out.add(n)
        return " "

    without_ranges = re.sub(r"(\d+)\s*-\s*(\d+)", _range_sub, normalized)
    for mm in re.finditer(r"\d+", without_ranges):
        out.add(int(mm.group(0)))
    return sorted(out)


def _source_keys_from_label(label: Optional[str]) -> list[str]:
    cleaned = re.sub(r"\([^)]*\)", " ", _norm_text(label))
    patterns = [
        ("extended", re.compile(r"source\s+data\s+extended\s+data\s+fig(?:ure)?s?\.?\s*([0-9,\sand\u2012\u2013\u2014\u2212-]+)", re.I)),
        ("main", re.compile(r"source\s+data\s+fig(?:ure)?s?\.?\s*([0-9,\sand\u2012\u2013\u2014\u2212-]+)", re.I)),
    ]
    for kind, rgx in patterns:
        m = rgx.search(cleaned)
        if not m or not m.group(1):
            continue
        return [f"{kind}:{n}" for n in _expand_figure_refs(m.group(1))]
    return []


def _pick_data_links(root_el, base: str) -> list[str]:
    seen: list[str] = []
    for a in root_el.find_all("a", href=True):
        u = _abs_url(a["href"], base)
        if u and u not in seen:
            seen.append(u)
    return [u for u in seen if "static-content.springer.com" in u and _DATA_EXT_RE.search(u)]


def extract_pairs_from_article_html(html: str, article_url: str) -> dict:
    """Static (requests+BS4) equivalent of the playwright extract_pairs_from_article.
    Returns the same dict shape: {articleUrl, doi, title, figureCount, sourceDataCount,
    pairCount, figures, sourceData, pairs}."""
    soup = BeautifulSoup(html, "html.parser")
    base = article_url

    meta_doi = None
    for name in ("citation_doi", "dc.identifier", "dc.Identifier"):
        el = soup.find("meta", attrs={"name": name})
        if el and el.get("content"):
            meta_doi = el["content"]
            break
    doi = re.sub(r"^doi\s*:", "", meta_doi, flags=re.I).strip() if meta_doi else None
    h1 = soup.find("h1")
    title = _norm_text(h1.get_text()) if h1 else None

    raw_figures: list[dict] = []
    for idx, fig in enumerate(soup.find_all("figure")):
        figcap = fig.find("figcaption")
        caption = _norm_text(figcap.get_text()) if figcap else None
        img = fig.find("img")
        img_url = None
        if img:
            for attr in ("src", "data-src", "data-original", "data-lazy-src"):
                v = img.get(attr)
                if v:
                    img_url = v
                    break
        if img_url and img_url.startswith("//"):
            img_url = "https:" + img_url
        figure_page_url = None
        link = fig.find("a", href=lambda h: h and "/figures/" in h)
        if link:
            figure_page_url = _abs_url(link.get("href"), base)
        source_anchor_ids: list[str] = []
        for a in fig.find_all("a", href=True):
            h = a["href"]
            if "#" in h:
                anchor = h.split("#")[-1]
                if _MOESM_ID_RE.match(anchor):
                    source_anchor_ids.append(anchor)
        kind, number = _parse_figure_identity(caption, idx + 1)
        if not img_url:
            continue  # JS filters out figures without an image
        raw_figures.append({
            "figureIndex": number, "figureKind": kind, "figureNumber": number,
            "figureKey": f"{kind}:{number}", "caption": caption, "imgUrl": img_url,
            "figurePageUrl": figure_page_url,
            "sourceAnchorIds": list(dict.fromkeys(source_anchor_ids)),
        })

    figures: list[dict] = []
    seen_figs: set[str] = set()
    for fig in raw_figures:
        key = f"{fig['figureKey']}|{fig['imgUrl']}"
        if key in seen_figs:
            continue
        seen_figs.add(key)
        figures.append(fig)

    moesm_to_files: dict[str, list[str]] = {}
    all_moesm: set[str] = set()
    for f in figures:
        all_moesm.update(f["sourceAnchorIds"])
    for mid in all_moesm:
        el = soup.find(id=mid)
        if el is None:
            continue
        files = _pick_data_links(el, base)
        if files:
            moesm_to_files[mid] = files

    source_data: list[dict] = []
    for a in soup.find_all("a", href=True):
        label = _norm_text(a.get_text())
        href = _abs_url(a["href"], base)
        if not label or not re.search(r"source\s*data", label, re.I):
            continue
        if "static-content.springer.com" not in href:
            continue
        if not _DATA_EXT_RE.search(href):
            continue
        source_data.append({"label": label, "url": href, "sourceKeys": _source_keys_from_label(label)})

    pairs: list[dict] = []
    seen_pairs: set[str] = set()

    def _add_pair(fig: dict, data_url: str, source_label: Optional[str]) -> None:
        pk = f"{fig['figureKey']}|{fig['imgUrl']}|{data_url}"
        if pk in seen_pairs:
            return
        seen_pairs.add(pk)
        pairs.append({
            "figureIndex": fig["figureIndex"], "figureKind": fig["figureKind"],
            "figureNumber": fig["figureNumber"], "figureKey": fig["figureKey"],
            "figureCaption": fig["caption"], "imageUrl": fig["imgUrl"],
            "dataUrl": data_url, "dataLabel": source_label, "figurePageUrl": fig["figurePageUrl"],
        })

    for fig in figures:
        data_urls: list[str] = []
        for mid in fig["sourceAnchorIds"]:
            data_urls.extend(moesm_to_files.get(mid, []))
        for du in list(dict.fromkeys(data_urls)):
            _add_pair(fig, du, None)
        for source in source_data:
            if fig["figureKey"] not in source["sourceKeys"]:
                continue
            _add_pair(fig, source["url"], source["label"])

    return {
        "articleUrl": article_url, "doi": doi, "title": title,
        "figureCount": len(figures), "sourceDataCount": len(source_data),
        "pairCount": len(pairs), "figures": figures, "sourceData": source_data, "pairs": pairs,
    }


def extract_pairs_from_article_requests(
    session: requests.Session,
    article_url: str,
    *,
    timeout_s: int = 60,
    retries: int = 3,
    retry_backoff_s: float = 1.0,
) -> dict:
    """Fetch the article HTML with requests (bypasses the playwright bot-wall) and
    extract figure/source-data pairs statically."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
    }
    last_err: Optional[BaseException] = None
    for attempt in range(1, retries + 1):
        try:
            resp = session.get(article_url, headers=headers, timeout=timeout_s)
            resp.raise_for_status()
            return extract_pairs_from_article_html(resp.text, article_url)
        except Exception as e:
            last_err = e
            if attempt >= retries:
                break
            time.sleep(retry_backoff_s * attempt)
    assert last_err is not None
    raise last_err


def download_file(
    session: requests.Session,
    url: str,
    dest_path: Path,
    *,
    overwrite: bool,
    timeout_s: int = 180,
    retries: int = 3,
    retry_backoff_s: float = 1.0,
    max_bytes: Optional[int] = None,
) -> str:
    """Download `url` to `dest_path`. Returns a status string:
    "exists" (already present), "ok" (downloaded), "too_large" (skipped because the
    file exceeds `max_bytes` — checked via Content-Length and enforced while streaming),
    or raises on a hard error. `max_bytes=None` means no cap.
    """
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    if dest_path.exists() and not overwrite and dest_path.stat().st_size > 0:
        return "exists"

    headers = {"User-Agent": "Mozilla/5.0"}
    last_err: Optional[BaseException] = None
    for attempt in range(1, retries + 1):
        try:
            with session.get(url, headers=headers, stream=True, timeout=timeout_s) as resp:
                resp.raise_for_status()
                # Pre-download skip when the server advertises a size over the cap.
                if max_bytes is not None:
                    clen = resp.headers.get("Content-Length")
                    if clen is not None:
                        try:
                            if int(clen) > max_bytes:
                                return "too_large"
                        except ValueError:
                            pass
                tmp_path = dest_path.with_suffix(dest_path.suffix + ".part")
                total = 0
                too_large = False
                with open(tmp_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=1024 * 256):
                        if not chunk:
                            continue
                        total += len(chunk)
                        # Enforce the cap mid-stream for servers without Content-Length.
                        if max_bytes is not None and total > max_bytes:
                            too_large = True
                            break
                        f.write(chunk)
                if too_large:
                    try:
                        tmp_path.unlink()
                    except OSError:
                        pass
                    return "too_large"
                os.replace(tmp_path, dest_path)
                return "ok"
        except Exception as e:
            last_err = e
            if attempt >= retries:
                break
            time.sleep(retry_backoff_s * attempt)
    if last_err is not None:
        raise last_err
    return "error"


def ensure_pairs_downloaded(
    pairs: list[dict],
    *,
    out_dir: Path,
    article_id: str,
    session: requests.Session,
    overwrite: bool,
    download_timeout_s: int,
    download_retries: int,
    retry_backoff_s: float,
    skip_images: bool = False,
    max_data_bytes: Optional[int] = None,
) -> list[PairRecord]:
    records: list[PairRecord] = []

    article_dir = out_dir / "articles" / article_id
    images_dir = article_dir / "images"
    data_dir = article_dir / "data"

    for p in pairs:
        fig_idx = int(p["figureIndex"])
        fig_page_url = p.get("figurePageUrl")
        fig_page_caption = p.get("figurePageCaption")
        raw_img_url = str(p["imageUrl"])
        img_url = to_full_media_url(raw_img_url)
        data_url = str(p["dataUrl"])

        img_name = _basename_from_url(img_url)
        data_name = _basename_from_url(data_url)

        img_path = images_dir / img_name
        data_path = data_dir / data_name

        # Download the source-data file FIRST and honor the size cap: if it exceeds the
        # cap (e.g. a multi-hundred-MB raw archive, not a usable table) the pair is
        # unusable, so we drop it before wasting bandwidth on its image.
        data_status = download_file(
            session,
            data_url,
            data_path,
            overwrite=overwrite,
            timeout_s=download_timeout_s,
            retries=download_retries,
            retry_backoff_s=retry_backoff_s,
            max_bytes=max_data_bytes,
        )
        if data_status == "too_large":
            continue

        if not skip_images:
            download_file(
                session,
                img_url,
                img_path,
                overwrite=overwrite,
                timeout_s=download_timeout_s,
                retries=download_retries,
                retry_backoff_s=retry_backoff_s,
            )

        records.append(
            PairRecord(
                article_url=str(p.get("articleUrl", "")),
                article_id=article_id,
                doi=p.get("doi"),
                title=p.get("title"),
                figure_index=fig_idx,
                figure_kind=p.get("figureKind"),
                figure_number=p.get("figureNumber"),
                figure_key=p.get("figureKey"),
                figure_caption=p.get("figureCaption"),
                figure_page_url=fig_page_url,
                figure_page_caption=fig_page_caption,
                data_label=p.get("dataLabel"),
                image_url=img_url,
                data_url=data_url,
                image_path=("" if skip_images else str(img_path.relative_to(out_dir)).replace("\\", "/")),
                data_path=str(data_path.relative_to(out_dir)).replace("\\", "/"),
            )
        )

    return records


def _writer_process(
    queue: "mp.Queue",
    *,
    out_dir: str,
    initial_processed_urls: list[str],
    run_total: int,
    show_progress: bool,
    flush_state_interval_s: float = 2.0,
) -> None:
    out_path = Path(out_dir)
    pairs_path = out_path / "pairs.jsonl"
    errors_path = out_path / "errors.jsonl"
    skipped_path = out_path / "skipped.jsonl"
    state_path = out_path / "state.json"

    processed: set[str] = set(initial_processed_urls)
    pending_state_write = False
    next_state_flush = time.time() + flush_state_interval_s
    run_done = 0
    pair_lines = 0
    error_lines = 0
    skipped_lines = 0

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
                pairs_f.write(msg["line"] + "\n")
                pair_lines += 1
            elif kind == "error":
                errors_f.write(msg["line"] + "\n")
                error_lines += 1
            elif kind == "skipped":
                skipped_f.write(msg["line"] + "\n")
                skipped_lines += 1
            elif kind == "processed":
                url = msg["url"]
                if url not in processed:
                    processed.add(url)
                    run_done += 1
                    pending_state_write = True
            else:
                continue

            now = time.time()
            if now >= next_state_flush:
                pairs_f.flush()
                errors_f.flush()
                if pending_state_write:
                    _atomic_write_json(
                        state_path,
                        {
                            "processed_article_urls": sorted(processed),
                            "updated_at": _now_iso(),
                        },
                    )
                    pending_state_write = False
                if show_progress:
                    line = (
                        f"{_render_progress(run_done, run_total)} "
                        f"pairs={pair_lines} skipped={skipped_lines} errors={error_lines}"
                    )
                    print(line, file=sys.stderr, flush=True)
                next_state_flush = now + flush_state_interval_s

        pairs_f.flush()
        errors_f.flush()
        skipped_f.flush()
        if pending_state_write:
            _atomic_write_json(
                state_path,
                {
                    "processed_article_urls": sorted(processed),
                    "updated_at": _now_iso(),
                },
            )
        if show_progress:
            line = f"{_render_progress(run_done, run_total)} pairs={pair_lines} skipped={skipped_lines} errors={error_lines}"
            print(line, file=sys.stderr, flush=True)
    finally:
        pairs_f.close()
        errors_f.close()
        skipped_f.close()


def _worker_process(
    worker_id: int,
    urls: list[str],
    *,
    out_dir: str,
    overwrite: bool,
    headed: bool,
    browser_channel: str,
    sleep_s: float,
    download_timeout_s: int,
    download_retries: int,
    retry_backoff_s: float,
    fetch_figure_page_captions: bool,
    keep_metadata_only_article_dirs: bool,
    queue: "mp.Queue",
    skip_images: bool = False,
    max_data_bytes: Optional[int] = None,
) -> None:
    _ensure_playwright_runtime_env()

    out_path = Path(out_dir).resolve()
    session = requests.Session()

    with sync_playwright() as p:
        channel = (browser_channel or "").strip()
        if channel.lower() in {"none", "playwright", "bundled", "default"}:
            browser = p.chromium.launch(headless=not headed)
        else:
            browser = p.chromium.launch(channel=channel, headless=not headed)
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
                extracted = extract_pairs_from_article_requests(
                    session, article_url, retries=download_retries, retry_backoff_s=retry_backoff_s
                )
                extracted["articleUrl"] = article_url
                extracted["articleId"] = article_id

                if fetch_figure_page_captions:
                    figure_page_urls: list[str] = []
                    for fig in extracted.get("figures", []):
                        u = fig.get("figurePageUrl")
                        if u:
                            figure_page_urls.append(str(u))

                    unique_urls: list[str] = []
                    seen_urls: set[str] = set()
                    for u in figure_page_urls:
                        if u in seen_urls:
                            continue
                        seen_urls.add(u)
                        unique_urls.append(u)

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
                (article_dir / "article.json").write_text(
                    json.dumps(extracted, ensure_ascii=False, indent=2), encoding="utf-8"
                )

                normalized_pairs = []
                for p0 in extracted.get("pairs", []):
                    normalized_pairs.append(
                        {
                            **p0,
                            "articleUrl": article_url,
                            "doi": extracted.get("doi"),
                            "title": extracted.get("title"),
                        }
                    )

                records = ensure_pairs_downloaded(
                    normalized_pairs,
                    out_dir=out_path,
                    article_id=article_id,
                    session=session,
                    overwrite=overwrite,
                    download_timeout_s=download_timeout_s,
                    download_retries=download_retries,
                    retry_backoff_s=retry_backoff_s,
                    skip_images=skip_images,
                    max_data_bytes=max_data_bytes,
                )

                if not records:
                    skipped = {
                        "article_url": article_url,
                        "article_id": article_id,
                        "doi": extracted.get("doi"),
                        "title": extracted.get("title"),
                        "figure_count": extracted.get("figureCount", 0),
                        "source_data_count": extracted.get("sourceDataCount", 0),
                        "pair_count": extracted.get("pairCount", 0),
                        "reason": "no-figure-source-data-pairs",
                        "at": _now_iso(),
                        "worker_id": worker_id,
                    }
                    queue.put({"type": "skipped", "line": json.dumps(skipped, ensure_ascii=False)})

                for r in records:
                    queue.put({"type": "pair", "line": r.to_json()})

                if not keep_metadata_only_article_dirs:
                    _prune_metadata_only_article_dir(article_dir)

                queue.put({"type": "processed", "url": article_url})

            except Exception as e:
                err = {
                    "article_url": article_url,
                    "article_id": article_id,
                    "error": repr(e),
                    "at": _now_iso(),
                    "worker_id": worker_id,
                }
                queue.put({"type": "error", "line": json.dumps(err, ensure_ascii=False)})

            time.sleep(sleep_s)

        context.close()
        browser.close()


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Download Nature figure images + source-data file pairs."
    )
    src = parser.add_mutually_exclusive_group(required=False)
    src.add_argument("--search-url", default=DEFAULT_SEARCH_URL)
    src.add_argument("--urls-file", help="Text file with one article URL per line.")
    parser.add_argument(
        "--max-articles",
        type=int,
        default=10,
        help="Target number of articles with at least one downloaded image/source-data pair. 0 means no success-count limit.",
    )
    parser.add_argument(
        "--max-candidates",
        type=int,
        default=0,
        help="Maximum candidate article URLs to inspect. 0 means use the built-in search cap.",
    )
    parser.add_argument("--start-page", type=int, default=1)
    parser.add_argument("--max-pages", type=int, default=0, help="0 means no limit.")
    parser.add_argument(
        "--split-by-year",
        action="store_true",
        help="Split Nature search into per-year queries to bypass the 1000-results cap.",
    )
    parser.add_argument(
        "--year-start",
        type=int,
        default=0,
        help="Start year (inclusive) for --split-by-year. 0 = infer automatically.",
    )
    parser.add_argument(
        "--year-end",
        type=int,
        default=0,
        help="End year (inclusive) for --split-by-year. 0 = current year.",
    )
    parser.add_argument("--out-dir", default="downloads")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument(
        "--browser-channel",
        default="none",
        help='Chromium channel (e.g. "msedge", "chrome"). Default "none" uses Playwright-bundled Chromium.',
    )
    parser.add_argument("--sleep-s", type=float, default=0.2)
    parser.add_argument("--download-timeout-s", type=int, default=180)
    parser.add_argument("--download-retries", type=int, default=3)
    parser.add_argument("--retry-backoff-s", type=float, default=1.0)
    parser.add_argument(
        "--skip-images",
        action="store_true",
        help="Do not download figure images (source-data tables only). "
             "~40%% smaller; use when only the data-transform line is needed.",
    )
    parser.add_argument(
        "--max-data-file-mb",
        type=float,
        default=0.0,
        help="Skip any single source-data file larger than this many MB (0 = no cap). "
             "A handful of huge raw archives dominate storage; e.g. 20 keeps all tabular "
             "data while cutting ~60%% of data volume.",
    )
    parser.add_argument(
        "--fetch-figure-page-captions",
        action="store_true",
        help="Fetch long figure captions from /figures/N pages.",
    )
    parser.add_argument(
        "--keep-metadata-only-article-dirs",
        action="store_true",
        help="Keep article dirs that only contain article.json (default: delete them).",
    )
    parser.add_argument(
        "--ignore-state",
        action="store_true",
        help="Ignore state.json and reprocess URLs.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of parallel worker processes (1 = sequential).",
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable progress output.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.max_data_file_mb < 0:
        raise SystemExit("--max-data-file-mb must be >= 0")
    max_data_bytes: Optional[int] = (
        int(args.max_data_file_mb * 1024 * 1024) if args.max_data_file_mb > 0 else None
    )

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
    if not args.ignore_state and state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except Exception:
            state = {}
    else:
        state = {}

    processed: set[str] = set(state.get("processed_article_urls", []))

    if args.max_articles < 0:
        raise SystemExit("--max-articles must be >= 0")
    if args.max_candidates < 0:
        raise SystemExit("--max-candidates must be >= 0")

    target_success_articles: Optional[int] = args.max_articles if args.max_articles > 0 else None
    if target_success_articles is not None and args.workers > 1:
        print(
            "Note: --max-articles is now an exact successful-article target; forcing --workers=1.",
            file=sys.stderr,
        )
        args.workers = 1

    candidate_limit = args.max_candidates if args.max_candidates > 0 else 10_000

    session = requests.Session()
    max_pages = None if args.max_pages == 0 else args.max_pages

    search_result: SearchFetchResult
    if args.urls_file:
        urls = []
        for line in Path(args.urls_file).read_text(encoding="utf-8").splitlines():
            u = line.strip()
            if not u or u.startswith("#"):
                continue
            urls.append(u)
        file_urls = urls[:candidate_limit]
        search_result = SearchFetchResult(
            urls=file_urls,
            total_results=len(file_urls),
            hit_result_cap=False,
        )
    else:
        if args.split_by_year:
            if args.start_page != 1:
                print(
                    "Note: --start-page is ignored when --split-by-year is used (each year starts at page 1).",
                    file=sys.stderr,
                )

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
                inferred_years = _infer_years_for_search(
                    args.search_url,
                    session=session,
                    sleep_s=args.sleep_s,
                )
                year_start = min(inferred_years)
                year_end = max(inferred_years)
                print(f"Inferred year range: {year_start}-{year_end}", file=sys.stderr)

            search_result = fetch_search_article_urls_split_by_year(
                args.search_url,
                max_articles=candidate_limit,
                max_pages=max_pages,
                session=session,
                sleep_s=args.sleep_s,
                year_start=year_start,
                year_end=year_end,
            )
        else:
            search_result = fetch_search_article_urls(
                args.search_url,
                max_articles=candidate_limit,
                start_page=args.start_page,
                max_pages=max_pages,
                session=session,
                sleep_s=args.sleep_s,
            )
            if search_result.hit_result_cap:
                total = search_result.total_results
                if total is not None:
                    print(
                        f"Note: Nature search caps results at 1000 per query (this query reports {total} results). "
                        "Use --split-by-year to fetch beyond the first 1000.",
                        file=sys.stderr,
                    )
                else:
                    print(
                        "Note: Nature search caps results at 1000 per query. Use --split-by-year to fetch beyond the first 1000.",
                        file=sys.stderr,
                    )

    article_urls = search_result.urls

    pairs_path = out_dir / "pairs.jsonl"
    errors_path = out_dir / "errors.jsonl"
    skipped_path = out_dir / "skipped.jsonl"

    if not article_urls:
        print(f"Done. Output: {out_dir}")
        print(f"- pairs: {pairs_path if pairs_path.exists() else '(none)'}")
        print(f"- skipped: {skipped_path if skipped_path.exists() else '(none)'}")
        print(f"- errors: {errors_path if errors_path.exists() else '(none)'}")
        return 0

    if args.workers < 1:
        raise SystemExit("--workers must be >= 1")
    if args.workers > 1 and args.headed:
        raise SystemExit("Cannot use --headed with --workers > 1")

    remaining_urls = [u for u in article_urls if u not in processed]
    if not remaining_urls:
        print(f"Done. Output: {out_dir}")
        print(f"- pairs: {pairs_path if pairs_path.exists() else '(none)'}")
        print(f"- skipped: {skipped_path if skipped_path.exists() else '(none)'}")
        print(f"- errors: {errors_path if errors_path.exists() else '(none)'}")
        return 0

    successful_articles = 0
    attempted_articles = 0

    if args.workers == 1:
        _ensure_playwright_runtime_env()

        with sync_playwright() as p:
            channel = (args.browser_channel or "").strip()
            if channel.lower() in {"none", "playwright", "bundled", "default"}:
                browser = p.chromium.launch(headless=not args.headed)
            else:
                browser = p.chromium.launch(channel=channel, headless=not args.headed)
            context = browser.new_context()
            page = context.new_page()

            try:
                # Seed cookie banner once.
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
                    print(
                        f"[{idx}/{total}] success={successful_articles}"
                        f"/{target_success_articles if target_success_articles is not None else 'inf'} "
                        f"{article_id} {article_url}"
                    )
                else:
                    print(
                        f"{_render_progress(idx - 1, total)} "
                        f"success={successful_articles}"
                        f"/{target_success_articles if target_success_articles is not None else 'inf'} "
                        f"{article_id} {article_url}"
                    )
                attempted_articles += 1

                try:
                    extracted = extract_pairs_from_article_requests(
                        session, article_url, retries=args.download_retries, retry_backoff_s=args.retry_backoff_s
                    )
                    extracted["articleUrl"] = article_url
                    extracted["articleId"] = article_id

                    if args.fetch_figure_page_captions:
                        figure_page_urls: list[str] = []
                        for fig in extracted.get("figures", []):
                            u = fig.get("figurePageUrl")
                            if u:
                                figure_page_urls.append(str(u))

                        unique_urls: list[str] = []
                        seen_urls: set[str] = set()
                        for u in figure_page_urls:
                            if u in seen_urls:
                                continue
                            seen_urls.add(u)
                            unique_urls.append(u)

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

                    article_dir = out_dir / "articles" / article_id
                    article_dir.mkdir(parents=True, exist_ok=True)
                    (article_dir / "article.json").write_text(
                        json.dumps(extracted, ensure_ascii=False, indent=2), encoding="utf-8"
                    )

                    # Download & write pairs.
                    normalized_pairs = []
                    for p0 in extracted.get("pairs", []):
                        normalized_pairs.append(
                            {
                                **p0,
                                "articleUrl": article_url,
                                "doi": extracted.get("doi"),
                                "title": extracted.get("title"),
                            }
                        )

                    records = ensure_pairs_downloaded(
                        normalized_pairs,
                        out_dir=out_dir,
                        article_id=article_id,
                        session=session,
                        overwrite=args.overwrite,
                        download_timeout_s=args.download_timeout_s,
                        download_retries=args.download_retries,
                        retry_backoff_s=args.retry_backoff_s,
                        skip_images=args.skip_images,
                        max_data_bytes=max_data_bytes,
                    )

                    if not records:
                        skipped = {
                            "article_url": article_url,
                            "article_id": article_id,
                            "doi": extracted.get("doi"),
                            "title": extracted.get("title"),
                            "figure_count": extracted.get("figureCount", 0),
                            "source_data_count": extracted.get("sourceDataCount", 0),
                            "pair_count": extracted.get("pairCount", 0),
                            "reason": "no-figure-source-data-pairs",
                            "at": _now_iso(),
                        }
                        with open(skipped_path, "a", encoding="utf-8") as f:
                            f.write(json.dumps(skipped, ensure_ascii=False) + "\n")

                    with open(pairs_path, "a", encoding="utf-8") as f:
                        for r in records:
                            f.write(r.to_json() + "\n")

                    if records:
                        successful_articles += 1

                    if not args.keep_metadata_only_article_dirs:
                        _prune_metadata_only_article_dir(article_dir)

                    processed.add(article_url)
                    _atomic_write_json(
                        state_path,
                        {
                            "processed_article_urls": sorted(processed),
                            "updated_at": _now_iso(),
                        },
                    )

                except Exception as e:
                    err = {
                        "article_url": article_url,
                        "article_id": article_id,
                        "error": repr(e),
                        "at": _now_iso(),
                    }
                    with open(errors_path, "a", encoding="utf-8") as f:
                        f.write(json.dumps(err, ensure_ascii=False) + "\n")

                time.sleep(args.sleep_s)

            if target_success_articles is not None and successful_articles < target_success_articles:
                print(
                    f"Warning: requested {target_success_articles} successful articles, "
                    f"but only downloaded {successful_articles} after inspecting {attempted_articles} candidates. "
                    "Increase --max-candidates, adjust --search-url, or use --split-by-year if needed.",
                    file=sys.stderr,
                )

            context.close()
            browser.close()
    else:
        ctx = mp.get_context("spawn")
        queue: "mp.Queue" = ctx.Queue(maxsize=max(1000, args.workers * 50))

        run_total = len(remaining_urls)
        writer = ctx.Process(
            target=_writer_process,
            kwargs={
                "queue": queue,
                "out_dir": str(out_dir),
                "initial_processed_urls": sorted(processed),
                "run_total": run_total,
                "show_progress": not args.no_progress,
            },
        )
        writer.start()

        shards: list[list[str]] = [[] for _ in range(args.workers)]
        for i, url in enumerate(remaining_urls):
            shards[i % args.workers].append(url)

        workers: list[mp.Process] = []
        for worker_id, urls in enumerate(shards, start=1):
            if not urls:
                continue
            proc = ctx.Process(
                target=_worker_process,
                args=(worker_id, urls),
                kwargs={
                    "out_dir": str(out_dir),
                    "overwrite": args.overwrite,
                    "headed": args.headed,
                    "browser_channel": args.browser_channel,
                    "sleep_s": args.sleep_s,
                    "download_timeout_s": args.download_timeout_s,
                    "download_retries": args.download_retries,
                    "retry_backoff_s": args.retry_backoff_s,
                    "fetch_figure_page_captions": args.fetch_figure_page_captions,
                    "keep_metadata_only_article_dirs": args.keep_metadata_only_article_dirs,
                    "queue": queue,
                    "skip_images": args.skip_images,
                    "max_data_bytes": max_data_bytes,
                },
            )
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


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SearchBlockedError as e:
        print(f"\n[blocked] {e}", file=sys.stderr)
        raise SystemExit(2)

#!/usr/bin/env python3
"""
Daily-Brief · Fetcher
读 sources.md → 并发抓取 coverage_window_hours 内条目 → raw_items.jsonl + fetcher.log
规范见 agents/fetcher.md
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import json
import logging
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

import feedparser
import httpx
from dateutil import parser as date_parser
from readability import Document
from bs4 import BeautifulSoup

# --- 可选 curl_cffi 传输层（仅在 src.extra["transport"]=="curl_cffi" 的源启用） ---
try:
    from curl_cffi import requests as _cfx_requests  # type: ignore[import-not-found]
    from curl_cffi.requests.errors import RequestsError as _CffiRequestsError  # type: ignore
    _CURL_CFFI_AVAILABLE = True
except ImportError:
    _cfx_requests = None
    _CffiRequestsError = Exception  # 占位，使 _RETRY_EXC tuple 构造不失败
    _CURL_CFFI_AVAILABLE = False

import archive_adapters  # side-effect: registers adapters
from archive_adapters import get_adapter, scan_detail_page_for_date, scan_detail_page_for_title

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
HTTP_TIMEOUT = 30.0
PARSE_TIMEOUT = 10.0
RETRY = 2
MAX_WORKERS = 20
ARCHIVE_DETAIL_CAP_DEFAULT = 8   # archive_scrape 页面扫 detail 的上限；可由 --archive-detail-cap 覆盖
FAILURE_ABORT_RATIO = 0.5        # 失败信源占比超过此值则 Pipeline 中止
_FAILURE_EXIT_CODE = 3           # 区别于 parse sources 失败的 return 2

# --- 状态化增量抓取（Problem 1） ---
STATE_FILE_DEFAULT = Path("./tmp/.fetcher_state.json")
STATE_SCHEMA_VERSION = 1
SEEN_URLS_CAP = 200              # 每源保留最近 N 条 URL，防止状态无限膨胀
SEEN_URL_TTL_DAYS = 30           # seen_url 超过 N 天自动过期，允许被再次抓（应对历史文章 URL 修订）


@dataclass
class Source:
    source_id: str
    name: str
    url: str
    source_type: str  # rss / web / github / podcast
    priority: int = 3
    freshness_expectation_days: int = 7
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class RawItem:
    item_id: str
    source_id: str
    source_name: str
    source_url: str
    original_title: str
    published_at: str | None
    fetched_at: str
    lang: str
    content_type: str
    full_content: str | None
    full_content_tokens: int
    rss_summary: str | None
    compressed_summary: str | None
    fetch_status: str
    fetch_error: str | None
    freshness_state: str


# --- sources.md parsing ---------------------------------------------------

# 每个信源以 `### N. Name` 开头；N 为序号（区分与非信源 section 如 `### Schema`）
SOURCE_HEADER_RE = re.compile(r"^###\s+\d+\.\s+(?P<name>.+?)\s*$")
# 字段项：`- `field`: `value`` 或 `- `field`: 自由文本`
FIELD_LINE_RE = re.compile(
    r"^\s*-\s+`(?P<key>[\w_]+)`\s*:\s*(?P<val>.+?)\s*$"
)

# freshness 枚举 → 健康检查基线天数（与 sources.md §staleness_check 一致）
FRESHNESS_DAYS = {"daily": 2, "weekly": 10, "monthly": 40, "irregular": 90}


def _slug(name: str) -> str:
    """把显示名转成 source_id：小写、非字母数字→_、折叠连续 _"""
    s = re.sub(r"[^\w]+", "_", name.strip().lower(), flags=re.UNICODE)
    return re.sub(r"_+", "_", s).strip("_") or "unnamed"


def _strip_backticks(val: str) -> str:
    v = val.strip()
    if len(v) >= 2 and v.startswith("`") and v.endswith("`"):
        return v[1:-1].strip()
    return v


def parse_sources(path: Path) -> list[Source]:
    """
    解析 sources.md（v1.1 Markdown 格式）。
    每个信源：
        ### N. Display Name
        - `url_primary`: `https://...`
        - `url_fallback`: `...`        # 可选
        - `fetch_method`: `rss` / `archive_scrape` / `hybrid`
        - `freshness`: `daily` / `weekly` / `monthly` / `irregular`
        - `depth`: `full_text` / `rich_description` / `summary_only`
        - `lang`: `en` / `zh`
        - `note`: 自由文本
    """
    text = path.read_text(encoding="utf-8")
    sources: list[Source] = []
    current_name: str | None = None
    current_fields: dict[str, str] = {}

    def flush() -> None:
        if not current_name:
            return
        url = current_fields.get("url_primary")
        if not url:
            return
        fetch_method = current_fields.get("fetch_method", "rss")
        freshness = current_fields.get("freshness", "weekly")
        sources.append(
            Source(
                source_id=_slug(current_name),
                name=current_name,
                url=url,
                source_type=fetch_method,
                priority=3,  # sources.md 不再按优先级，统一默认
                freshness_expectation_days=FRESHNESS_DAYS.get(freshness, 7),
                extra={
                    "url_fallback": current_fields.get("url_fallback"),
                    "freshness": freshness,
                    "depth": current_fields.get("depth", "full_text"),
                    "lang": current_fields.get("lang"),
                    "note": current_fields.get("note"),
                    # transport：默认 httpx；需 TLS 指纹伪装时在 sources.md 声明 `- \`transport\`: `curl_cffi``
                    "transport": current_fields.get("transport", "httpx"),
                },
            )
        )

    for line in text.splitlines():
        header = SOURCE_HEADER_RE.match(line)
        if header:
            flush()
            current_name = header.group("name")
            current_fields = {}
            continue
        if line.startswith("#"):
            # 其他层级 heading 视为信源块结束（遇到下一个 ## 等）
            flush()
            current_name = None
            current_fields = {}
            continue
        if current_name is None:
            continue
        m = FIELD_LINE_RE.match(line)
        if m:
            current_fields[m.group("key")] = _strip_backticks(m.group("val"))
    flush()
    return sources


# --- utility -------------------------------------------------------------


def sha1_short(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]


def rough_token_count(text: str | None) -> int:
    if not text:
        return 0
    # 粗估：英文 ≈ 单词数 * 1.3；中文 ≈ 字符数
    chinese = len(re.findall(r"[\u4e00-\u9fff]", text))
    words = len(re.findall(r"[a-zA-Z]+", text))
    return int(chinese + words * 1.3)


def detect_lang(text: str | None) -> str:
    if not text:
        return "unknown"
    chinese = len(re.findall(r"[\u4e00-\u9fff]", text))
    total = max(len(text), 1)
    return "zh" if chinese / total > 0.2 else "en"


def parse_datetime(raw: Any) -> datetime | None:
    if raw is None:
        return None
    if isinstance(raw, time.struct_time):
        return datetime.fromtimestamp(time.mktime(raw), tz=timezone.utc)
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    try:
        return date_parser.parse(str(raw))
    except (ValueError, TypeError):
        return None


def freshness_state(latest: datetime | None, now: datetime) -> str:
    if latest is None:
        return "irregular"
    delta = now - latest
    if delta <= timedelta(hours=48):
        return "fresh"
    if delta <= timedelta(days=7):
        return "stale"
    if delta <= timedelta(days=90):
        return "irregular"
    return "dead"


# --- fetchers ------------------------------------------------------------


class _CurlCffiResponse:
    """适配 curl_cffi.Response → httpx.Response 子集（status_code/content/text/headers）。
    仅在 fetch 管线读取的属性上提供兼容；不做完整仿真。"""
    __slots__ = ("status_code", "content", "text", "headers")

    def __init__(self, r: Any) -> None:
        self.status_code = r.status_code
        self.content = r.content
        self.text = r.text
        # 大小写不敏感的 headers（httpx.Headers 自带；curl_cffi 返回 dict）
        self.headers = {str(k).lower(): v for k, v in dict(r.headers).items()}


class CurlCffiTransport:
    """shim：对外暴露与 httpx.Client 一致的 get() + 上下文管理；底层走 curl_cffi.Session。
    用途：对 *.substack.com 子域等做 JA3/TLS 指纹伪装（impersonate=chrome）。
    仅当 src.extra["transport"]=="curl_cffi" 时由 fetch_one 创建。"""
    def __init__(self, headers: dict[str, str]) -> None:
        if not _CURL_CFFI_AVAILABLE:
            raise RuntimeError("curl_cffi unavailable; install with `pip install curl-cffi>=0.7`")
        self._session = _cfx_requests.Session()  # type: ignore[union-attr]
        self._headers = dict(headers)

    def get(self, url: str, timeout: float = HTTP_TIMEOUT,
            follow_redirects: bool = True,
            headers: dict[str, str] | None = None) -> _CurlCffiResponse:
        hdrs = dict(self._headers)
        if headers:
            hdrs.update(headers)
        r = self._session.get(
            url,
            impersonate="chrome",
            timeout=timeout,
            allow_redirects=follow_redirects,
            headers=hdrs,
        )
        return _CurlCffiResponse(r)

    def __enter__(self) -> "CurlCffiTransport":
        return self

    def __exit__(self, *exc_info: Any) -> bool:
        try:
            self._session.close()
        except Exception:
            pass
        return False


# curl_cffi 运行时异常 → 纳入重试池（与 httpx 的 TimeoutException/TransportError 同等级）
_RETRY_EXC: tuple[type[Exception], ...] = (httpx.TimeoutException, httpx.TransportError)
if _CURL_CFFI_AVAILABLE:
    _RETRY_EXC = _RETRY_EXC + (_CffiRequestsError,)


def http_get(client: Any, url: str, extra_headers: dict[str, str] | None = None) -> Any:
    """通用 HTTP GET w/ 指数回退重试。client 可以是 httpx.Client 或 CurlCffiTransport。
    返回对象需具备 status_code / content / text / headers 四个属性（duck-typed）。"""
    last_exc: Exception | None = None
    delay = 1.0
    for _ in range(RETRY + 1):
        try:
            resp = client.get(url, timeout=HTTP_TIMEOUT, follow_redirects=True, headers=extra_headers)
            return resp
        except _RETRY_EXC as e:
            last_exc = e
            time.sleep(delay)
            delay *= 4
    raise last_exc  # type: ignore[misc]


# --- 状态化增量抓取 helpers (Problem 1) -----------------------------------


def load_fetcher_state(path: Path) -> dict:
    """读入状态文件。缺失/损坏时返回空状态（不崩）。"""
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or data.get("version") != STATE_SCHEMA_VERSION:
            return {"version": STATE_SCHEMA_VERSION, "sources": {}}
        data.setdefault("sources", {})
        return data
    except FileNotFoundError:
        return {"version": STATE_SCHEMA_VERSION, "sources": {}}
    except (OSError, json.JSONDecodeError) as e:
        logging.getLogger("fetcher").warning(
            "state file %s unreadable (%s); starting with empty state", path, e
        )
        return {"version": STATE_SCHEMA_VERSION, "sources": {}}


def save_fetcher_state_atomic(path: Path, state: dict, now: datetime) -> None:
    """原子写状态（tmp → rename）。失败记日志不抛。"""
    try:
        state["updated_at"] = now.isoformat()
        state["version"] = STATE_SCHEMA_VERSION
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        tmp.replace(path)
    except OSError as e:
        logging.getLogger("fetcher").warning("failed to persist state %s: %s", path, e)


def _head_hash(urls: list[str], n: int = 3) -> str:
    """取前 n 个 URL 拼接的 sha256 前 16 位，作为列表页"指纹"。"""
    h = hashlib.sha256("\n".join(urls[:n]).encode("utf-8")).hexdigest()
    return "sha256:" + h[:16]


def _prune_seen_urls(seen: dict, now: datetime) -> dict:
    """按 TTL 过滤过期 URL，再按 first_seen_at 降序保留前 SEEN_URLS_CAP 条。"""
    ttl_cutoff = now - timedelta(days=SEEN_URL_TTL_DAYS)

    def _ts(entry: dict) -> datetime:
        try:
            t = parse_datetime(entry.get("first_seen_at"))
            return t or datetime.min.replace(tzinfo=timezone.utc)
        except Exception:
            return datetime.min.replace(tzinfo=timezone.utc)

    kept = {u: e for u, e in seen.items() if _ts(e) >= ttl_cutoff}
    if len(kept) <= SEEN_URLS_CAP:
        return kept
    ordered = sorted(kept.items(), key=lambda kv: _ts(kv[1]), reverse=True)
    return dict(ordered[:SEEN_URLS_CAP])


def extract_readability(html: str) -> str | None:
    try:
        doc = Document(html)
        summary_html = doc.summary(html_partial=True)
        # 剥 HTML 标签
        return re.sub(r"<[^>]+>", "", summary_html).strip() or None
    except Exception:
        return None


def normalize_text(text: str | None) -> str | None:
    if not text:
        return None
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def extract_article_text(html: str, url: str | None = None) -> tuple[str | None, str | None]:
    """Return (text, warning).

    Some newsletter sites render the real post in stable app containers while
    readability picks a signup block. Keep host-specific selectors small and
    fall back to readability for general pages.
    """
    host = urlparse(url or "").netloc.lower()
    if host.endswith("superhuman.ai"):
        soup = BeautifulSoup(html, "lxml")
        node = soup.select_one(".rendered-post")
        if node:
            text = normalize_text(node.get_text(" ", strip=True))
            if text and rough_token_count(text) >= 80:
                return text, None

    text = normalize_text(extract_readability(html))
    if looks_like_boilerplate_only(text):
        return text, "boilerplate_only"
    return text, None


def looks_like_boilerplate_only(text: str | None) -> bool:
    if not text:
        return True
    low = text.lower()
    boiler_signals = [
        "keep up with the latest ai news",
        "join 1,500,000+ professionals",
        "subscribe",
        "sign up",
    ]
    return rough_token_count(text) < 80 and any(sig in low for sig in boiler_signals)


def fetch_rss(client: httpx.Client, src: Source, cutoff: datetime, now: datetime) -> list[RawItem]:
    items: list[RawItem] = []
    try:
        resp = http_get(client, src.url)
        if resp.status_code >= 400:
            raise RuntimeError(f"http_{resp.status_code}")
        feed = feedparser.parse(resp.content)
    except Exception as e:
        return [make_failed_item(src, str(e), now)]

    entries = feed.entries or []
    for entry in entries:
        pub = parse_datetime(entry.get("published_parsed") or entry.get("updated_parsed") or entry.get("published") or entry.get("updated"))
        if pub and pub < cutoff:
            continue
        url = entry.get("link") or ""
        title = entry.get("title") or "(no title)"

        content_html = ""
        if "content" in entry and entry.content:
            content_html = entry.content[0].get("value", "")
        summary_html = entry.get("summary") or entry.get("description") or ""

        full_text: str | None = None
        summary_text = re.sub(r"<[^>]+>", "", summary_html).strip() or None
        if content_html and rough_token_count(re.sub(r"<[^>]+>", "", content_html)) >= 300:
            full_text = re.sub(r"<[^>]+>", "", content_html).strip()
        else:
            # 摘要 + 回源网页抽取；回源 4xx/5xx/异常时保底用 summary（不再丢）
            if url:
                try:
                    page = http_get(client, url)
                    if page.status_code < 400:
                        extracted, warning = extract_article_text(page.text, url)
                        full_text = extracted or summary_text
                    else:
                        full_text = summary_text
                except Exception:
                    full_text = summary_text
            else:
                full_text = summary_text

        item = RawItem(
            item_id=f"src:{src.source_id}:{sha1_short(url or title)}",
            source_id=src.source_id,
            source_name=src.name,
            source_url=url,
            original_title=title.strip(),
            published_at=pub.isoformat() if pub else None,
            fetched_at=now.isoformat(),
            lang=detect_lang(full_text),
            content_type=guess_content_type(src),
            full_content=full_text,
            full_content_tokens=rough_token_count(full_text),
            rss_summary=summary_text,
            compressed_summary=None,
            fetch_status="ok",
            fetch_error=None,
            freshness_state="fresh",  # 占位，汇总时覆盖
        )
        items.append(item)
    return items


def fetch_web(client: httpx.Client, src: Source, cutoff: datetime, now: datetime) -> list[RawItem]:
    """单页抓取（博客首页 / GitHub README）。不做历史回溯，只取当前快照。"""
    try:
        resp = http_get(client, src.url)
        if resp.status_code >= 400:
            raise RuntimeError(f"http_{resp.status_code}")
    except Exception as e:
        return [make_failed_item(src, str(e), now)]

    full_text, warning = extract_article_text(resp.text, src.url)
    fetch_status = "content_extraction_failed" if warning == "boilerplate_only" else "ok"
    item = RawItem(
        item_id=f"src:{src.source_id}:{sha1_short(src.url)}",
        source_id=src.source_id,
        source_name=src.name,
        source_url=src.url,
        original_title=src.name,
        published_at=now.isoformat(),
        fetched_at=now.isoformat(),
        lang=detect_lang(full_text),
        content_type=guess_content_type(src),
        full_content=full_text,
        full_content_tokens=rough_token_count(full_text),
        rss_summary=None,
        compressed_summary=None,
        fetch_status=fetch_status,
        fetch_error=warning,
        freshness_state="fresh",
    )
    return [item]


def guess_content_type(src: Source) -> str:
    if src.source_type == "rss":
        host = urlparse(src.url).netloc.lower()
        if "podcast" in host or "anchor.fm" in host or "feeds.megaphone" in host:
            return "podcast"
        if "youtube" in host:
            return "video"
        if "arxiv" in host:
            return "research_paper"
        if "news" in host:
            return "news"
        return "blog_post"
    if src.source_type == "github":
        return "github"
    if src.source_type == "podcast":
        return "podcast"
    return "other"


def make_failed_item(src: Source, err: str, now: datetime) -> RawItem:
    return RawItem(
        item_id=f"src:{src.source_id}:failed:{sha1_short(err)}",
        source_id=src.source_id,
        source_name=src.name,
        source_url=src.url,
        original_title="(fetch failed)",
        published_at=None,
        fetched_at=now.isoformat(),
        lang="unknown",
        content_type=guess_content_type(src),
        full_content=None,
        full_content_tokens=0,
        rss_summary=None,
        compressed_summary=None,
        fetch_status=classify_error(err),
        fetch_error=err[:200],
        freshness_state="irregular",
    )


_HTTP_CODE_RE = re.compile(r"\b(?:http[_ -]?)?([1-5]\d{2})\b", re.IGNORECASE)


def classify_error(err: str) -> str:
    low = err.lower()
    if "timeout" in low or "timed out" in low:
        return "timeout"
    # 精确匹配 HTTP 状态码，不再用模糊的 "4" / "5" 子串检测（旧实现会把 "ERR_CERTIFICATE_404_FOO" 这种字符误判）
    m = _HTTP_CODE_RE.search(err)
    if m:
        code = int(m.group(1))
        if 400 <= code < 500:
            return "http_4xx"
        if 500 <= code < 600:
            return "http_5xx"
    if "parse" in low or "feed" in low or "xml" in low:
        return "parse_error"
    return "blocked"


# --- orchestration -------------------------------------------------------


def fetch_one(
    src: Source,
    cutoff: datetime,
    now: datetime,
    detail_cap: int = ARCHIVE_DETAIL_CAP_DEFAULT,
    source_state: dict | None = None,
) -> list[RawItem]:
    """source_state：本源的状态切片，archive_scrape 会读写；其它类型忽略。
    线程安全：每个线程只访问自己 source_id 对应的 dict，主线程 save 时已 join。"""
    headers = {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,zh;q=0.8",
    }
    transport = (src.extra or {}).get("transport", "httpx")
    if transport == "curl_cffi":
        if not _CURL_CFFI_AVAILABLE:
            return [make_failed_item(src, "curl_cffi_unavailable", now)]
        client_cm: Any = CurlCffiTransport(headers=headers)
    else:
        client_cm = httpx.Client(headers=headers, http2=True)
    with client_cm as client:
        if src.source_type in {"rss", "podcast"}:
            return fetch_rss(client, src, cutoff, now)
        if src.source_type == "archive_scrape":
            return fetch_archive(client, src, cutoff, now, detail_cap=detail_cap, source_state=source_state)
        return fetch_web(client, src, cutoff, now)


def fetch_archive(
    client: httpx.Client,
    src: Source,
    cutoff: datetime,
    now: datetime,
    detail_cap: int = ARCHIVE_DETAIL_CAP_DEFAULT,
    source_state: dict | None = None,
) -> list[RawItem]:
    """archive_scrape：拉列表页 → 抽文章 URL → 单独抓 detail → readability。

    v0.10.3 增量策略（source_state 非 None 时启用）：
      1. LIST GET 带 If-None-Match / If-Modified-Since → 304 直接返回空
      2. LIST head_hash（前 3 个 URL 指纹）未变 → 跳过所有 detail GET
      3. detail_cap 只作用于"新 URL"（不在 seen_urls 里）
      4. seen_urls 记录 first_seen_at，按 TTL+LRU 裁剪
    """
    log = logging.getLogger("fetcher")
    adapter = get_adapter(src.url)
    if adapter is None:
        # 无 adapter 时回退到单页抓取（与 fetch_web 一致）
        return fetch_web(client, src, cutoff, now)

    # --- 状态读取 ---
    state_enabled = source_state is not None
    prev_etag = source_state.get("list_etag") if state_enabled else None
    prev_last_mod = source_state.get("list_last_modified") if state_enabled else None
    prev_head_hash = source_state.get("list_head_hash") if state_enabled else None
    seen_urls: dict = dict(source_state.get("seen_urls") or {}) if state_enabled else {}

    # --- LIST 条件 GET ---
    cond_headers: dict[str, str] = {}
    if state_enabled and prev_etag:
        cond_headers["If-None-Match"] = prev_etag
    if state_enabled and prev_last_mod:
        cond_headers["If-Modified-Since"] = prev_last_mod

    try:
        resp = http_get(client, src.url, extra_headers=cond_headers or None)
    except Exception as e:
        return [make_failed_item(src, str(e), now)]

    if state_enabled and resp.status_code == 304:
        log.info("source=%s list 304 Not Modified; skipping detail", src.source_id)
        # 状态不变，seen_urls 也不做 pruning 以免无新数据时反复 rewrite
        return []

    if resp.status_code >= 400:
        return [make_failed_item(src, f"http_{resp.status_code}", now)]

    new_etag = resp.headers.get("etag") or resp.headers.get("ETag")
    new_last_mod = resp.headers.get("last-modified") or resp.headers.get("Last-Modified")

    try:
        entries = adapter(resp.text, src.url)
    except Exception as e:
        return [make_failed_item(src, f"adapter_error:{e}", now)]

    if not entries:
        return fetch_web(client, src, cutoff, now)

    # head_hash 快路径：前 3 个 URL 未变 → 不再扫 detail
    urls_in_order = [e.url for e in entries]
    cur_head_hash = _head_hash(urls_in_order)
    head_unchanged = state_enabled and prev_head_hash and cur_head_hash == prev_head_hash

    # 候选分流：已知窗口内 / 已知窗口外 / 未知日期
    fresh: list[tuple[Any, datetime]] = []
    needs_detail: list[Any] = []
    for e in entries:
        if e.published_at and e.published_at >= cutoff:
            fresh.append((e, e.published_at))
        elif e.published_at and e.published_at < cutoff:
            continue
        else:
            needs_detail.append(e)

    # 增量筛：只保留 seen_urls 不认识的 URL（head_unchanged 时直接清空，走 early-return）
    if state_enabled:
        if head_unchanged:
            log.info("source=%s list head unchanged; skipping all detail GETs", src.source_id)
            needs_detail = []
            fresh = [(e, pub) for e, pub in fresh if e.url not in seen_urls]
        else:
            before = len(needs_detail)
            needs_detail = [e for e in needs_detail if e.url not in seen_urls]
            skipped = before - len(needs_detail)
            if skipped:
                log.info("source=%s state_hit: skipped %d known URLs, %d new to probe",
                         src.source_id, skipped, len(needs_detail))

    # 对"需扫 detail"的 URL 应用 cap（detail_cap 对象：新 URL）
    if len(needs_detail) > detail_cap:
        log.warning(
            "source=%s needs_detail=%d > cap=%d; truncating (raise ARCHIVE_DETAIL_CAP_DEFAULT "
            "or pass --archive-detail-cap if this source has more new posts per day)",
            src.source_id, len(needs_detail), detail_cap,
        )
    detail_cache: dict[str, tuple[str, datetime | None]] = {}
    for e in needs_detail[:detail_cap]:
        try:
            r = http_get(client, e.url)
            if r.status_code >= 400:
                continue
            dt = scan_detail_page_for_date(r.text)
            detail_cache[e.url] = (r.text, dt)
            if dt and dt >= cutoff:
                fresh.append((e, dt))
            elif state_enabled:
                # 已知窗口外，也记入 seen_urls 免得下次 head_hash 变化时再次白抓 detail
                seen_urls[e.url] = {
                    "first_seen_at": (seen_urls.get(e.url, {}).get("first_seen_at") or now.isoformat()),
                    "title": (e.title or "")[:200],
                }
        except Exception:
            continue

    items: list[RawItem] = []
    for e, pub in fresh:
        html = detail_cache.get(e.url, (None, None))[0]
        if html is None:
            try:
                r = http_get(client, e.url)
                if r.status_code >= 400:
                    continue
                html = r.text
            except Exception:
                continue
        full_text, warning = extract_article_text(html, e.url)
        # Fix 3：detail 页标题覆盖 adapter 的 placeholder（beehiiv 列表无卡片文本）
        detail_title = None
        try:
            detail_title = scan_detail_page_for_title(html)
        except Exception:
            pass
        final_title = (detail_title or (e.title.strip() if e.title else "") or e.url.rsplit("/", 1)[-1])
        items.append(
            RawItem(
                item_id=f"src:{src.source_id}:{sha1_short(e.url)}",
                source_id=src.source_id,
                source_name=src.name,
                source_url=e.url,
                original_title=final_title,
                published_at=pub.isoformat(),
                fetched_at=now.isoformat(),
                lang=detect_lang(full_text),
                content_type=guess_content_type(src),
                full_content=full_text,
                full_content_tokens=rough_token_count(full_text),
                rss_summary=None,
                compressed_summary=None,
                fetch_status="content_extraction_failed" if warning == "boilerplate_only" else "ok",
                fetch_error=warning,
                freshness_state="fresh",
            )
        )
        # 登记 seen
        if state_enabled:
            seen_urls[e.url] = {
                "first_seen_at": (seen_urls.get(e.url, {}).get("first_seen_at") or now.isoformat()),
                "title": final_title[:200],
            }

    # --- 状态写回（原地修改切片，主线程统一 save）---
    if state_enabled:
        # 即便本次没有新条目，也刷新 head_hash/etag，下次好走快路径
        source_state["last_run_at"] = now.isoformat()
        source_state["list_head_hash"] = cur_head_hash
        if new_etag:
            source_state["list_etag"] = new_etag
        if new_last_mod:
            source_state["list_last_modified"] = new_last_mod
        source_state["seen_urls"] = _prune_seen_urls(seen_urls, now)

    if not items:
        return []
    return items


def annotate_freshness(
    items: list[RawItem],
    sources: list["Source"] | None,
    now: datetime,
) -> dict[str, str]:
    """按 source_id 汇总最新 published_at → freshness_state，回填到每条。

    v0.10.2：补全全量源覆盖 —— sources.md 中注册但本次抓取未拉到 item 的信源，
    默认登记为 `no_new_items`（通道健康、今日无新内容）。下游 Writer 以独立
    "今日无新内容" 段渲染，避免信源健康度只有 fresh 档。
    """
    latest_by_source: dict[str, datetime | None] = {}
    for it in items:
        pub = parse_datetime(it.published_at) if it.published_at else None
        if it.fetch_status != "ok" or not pub:
            continue
        cur = latest_by_source.get(it.source_id)
        if cur is None or pub > cur:
            latest_by_source[it.source_id] = pub

    source_state: dict[str, str] = {}

    # 先用 items 的 freshness_state 回填（fresh/stale/irregular/dead）
    for it in items:
        latest = latest_by_source.get(it.source_id)
        state = freshness_state(latest, now)
        it.freshness_state = state
        source_state[it.source_id] = state

    # 再补齐 sources.md 中注册但本次 0 item 的源 → no_new_items（第五档）
    if sources:
        for s in sources:
            if s.source_id not in source_state:
                source_state[s.source_id] = "no_new_items"

    return source_state


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sources", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--coverage-hours", type=int, default=24)
    parser.add_argument("--log", type=Path, default=Path("./tmp/fetcher.log"))
    parser.add_argument("--archive-detail-cap", type=int, default=ARCHIVE_DETAIL_CAP_DEFAULT,
                        help="archive_scrape 信源每次扫 detail 页的上限，防止单源一次抓太多。默认 8。"
                             "v0.10.3 起该上限只作用于'新 URL'。")
    parser.add_argument("--failure-ratio-abort", type=float, default=FAILURE_ABORT_RATIO,
                        help="失败信源占比超过此值则以非零 code 退出，让主 Agent 中止下游。默认 0.5。")
    parser.add_argument("--state-file", type=Path, default=STATE_FILE_DEFAULT,
                        help="archive_scrape 增量状态文件路径，默认 ./tmp/.fetcher_state.json。"
                             "存在即用条件 GET + head_hash + seen_urls 跳过已知 URL。")
    parser.add_argument("--no-state", action="store_true",
                        help="禁用增量状态机，退化到 v0.10.2 行为（每源全量 GET detail_cap 条）。")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(args.log, mode="w", encoding="utf-8"), logging.StreamHandler(sys.stderr)],
    )
    log = logging.getLogger("fetcher")

    sources = parse_sources(args.sources)
    log.info("loaded %d sources from %s", len(sources), args.sources)
    if not sources:
        log.error("no sources parsed; aborting")
        return 2

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=args.coverage_hours)

    # 加载增量状态（--no-state 时置 None，所有 archive_scrape 走全量路径）
    state: dict | None = None
    if not args.no_state:
        state = load_fetcher_state(args.state_file)
        log.info("loaded fetcher state from %s (sources=%d)",
                 args.state_file, len(state.get("sources", {})))

    all_items: list[RawItem] = []
    failures = 0
    with cf.ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        # 为每个 archive_scrape 源预分配状态切片（避免多线程首次写入竞态）
        src_state_slices: dict[str, dict | None] = {}
        if state is not None:
            for s in sources:
                if s.source_type == "archive_scrape":
                    src_state_slices[s.source_id] = state["sources"].setdefault(s.source_id, {})

        futs = {
            pool.submit(
                fetch_one, s, cutoff, now, args.archive_detail_cap,
                src_state_slices.get(s.source_id),
            ): s for s in sources
        }
        for fut in cf.as_completed(futs):
            s = futs[fut]
            try:
                items = fut.result()
                ok = [i for i in items if i.fetch_status == "ok"]
                all_items.extend(items)
                log.info("source=%s fetched=%d ok=%d", s.source_id, len(items), len(ok))
                if items and all(i.fetch_status != "ok" for i in items):
                    failures += 1
            except Exception as e:  # pragma: no cover
                log.exception("source=%s crashed: %s", s.source_id, e)
                failures += 1

    # 原子写状态
    if state is not None:
        save_fetcher_state_atomic(args.state_file, state, now)
        log.info("saved fetcher state → %s", args.state_file)

    source_state = annotate_freshness(all_items, sources, now)
    log.info("freshness summary: %s", json.dumps(source_state, ensure_ascii=False))

    # 先把已有产物写盘（即使失败率过高，这些条目对下游 debug 仍有价值）
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as f:
        for it in all_items:
            f.write(json.dumps(asdict(it), ensure_ascii=False) + "\n")
    log.info("wrote %d items → %s", len(all_items), args.output)

    # 失败率校验：超阈值以非零退出码退出，让主 Agent 在 Pipeline 层中止下游
    failure_ratio = failures / len(sources) if sources else 0.0
    if failure_ratio > args.failure_ratio_abort:
        log.error(
            "failure_ratio=%.2f > threshold=%.2f (%d/%d sources failed); "
            "exiting with code %d to signal main agent to abort pipeline",
            failure_ratio, args.failure_ratio_abort, failures, len(sources), _FAILURE_EXIT_CODE,
        )
        return _FAILURE_EXIT_CODE

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""
archive_scrape adapter registry.

每个 adapter 按 hostname 注册，输入 list-page HTML 与 base_url，
返回 list[ListEntry(url, title, published_at_hint)]。

对于 published_at_hint 为 None 的条目，调用方负责在 detail 页面再次扫描日期。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from dateutil import parser as date_parser


@dataclass
class ListEntry:
    url: str
    title: str
    published_at: datetime | None  # None ⇒ 需在 detail 页面抽


Adapter = Callable[[str, str], list[ListEntry]]
_REGISTRY: dict[str, Adapter] = {}


def register(host: str) -> Callable[[Adapter], Adapter]:
    def deco(fn: Adapter) -> Adapter:
        _REGISTRY[host] = fn
        return fn
    return deco


def get_adapter(url: str) -> Adapter | None:
    host = urlparse(url).netloc.lower()
    return _REGISTRY.get(host)


# ---- 日期解析辅助 -----------------------------------------------------

MONTH_DATE_RE = re.compile(
    r"\b((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s*\d{4})\b"
)


def parse_loose_date(text: str) -> datetime | None:
    m = MONTH_DATE_RE.search(text)
    if not m:
        return None
    try:
        dt = date_parser.parse(m.group(1))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


_TITLE_SEP_RE = re.compile(r"\s+[|\-—–]\s+")


def scan_detail_page_for_title(html: str) -> str | None:
    """从 detail 页面优先级提取真实标题：og:title > twitter:title > <title>。

    Fix 3 根治 beehiiv 列表 adapter 无法拿到卡片文本的问题。
    同次 detail GET 的 HTML 复用，不产生额外 HTTP。
    对 `Article | Newsletter Name` 类型 title 剥后缀。"""
    # 1) og:title
    for pat in [
        r'<meta\s+[^>]*property="og:title"\s+[^>]*content="([^"]+)"',
        r'<meta\s+[^>]*content="([^"]+)"\s+property="og:title"',
        r'<meta\s+[^>]*name="twitter:title"\s+[^>]*content="([^"]+)"',
        r'<meta\s+[^>]*content="([^"]+)"\s+name="twitter:title"',
    ]:
        m = re.search(pat, html, re.IGNORECASE)
        if m:
            t = m.group(1).strip()
            if t:
                return t
    # 2) <title>，剥 site-name 后缀
    m = re.search(r"<title[^>]*>([^<]+)</title>", html, re.IGNORECASE)
    if m:
        t = m.group(1).strip()
        if t:
            parts = _TITLE_SEP_RE.split(t)
            if len(parts) >= 2:
                # 取最长的段，通常是文章标题（不是站点名）
                t = max(parts, key=len).strip()
            return t or None
    return None


def scan_detail_page_for_date(html: str) -> datetime | None:
    """在 detail 页面扫描日期元数据：ISO 优先，其次可见 Month DD, YYYY。"""
    # 1) JSON-LD / meta 标签
    for pat in [
        r'"datePublished"\s*:\s*"([^"]+)"',
        r'<meta\s+[^>]*(?:property|name)="article:published_time"\s+content="([^"]+)"',
        r'<meta\s+[^>]*content="([^"]+)"\s+(?:property|name)="article:published_time"',
        r'<time[^>]*datetime="([^"]+)"',
    ]:
        m = re.search(pat, html, re.IGNORECASE)
        if m:
            try:
                dt = date_parser.parse(m.group(1))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except (ValueError, TypeError):
                pass
    # 2) 正文可见日期
    return parse_loose_date(html)


# ---- 具体 adapter ----------------------------------------------------


@register("www.anthropic.com")
def _anthropic(list_html: str, base_url: str) -> list[ListEntry]:
    """
    Anthropic research + engineering archives 同构。
    链接形如 `/research/<slug>` 或 `/engineering/<slug>`。
    title 与日期从 anchor 文本里抠。"""
    soup = BeautifulSoup(list_html, "lxml")
    path_prefix = urlparse(base_url).path.rstrip("/")  # /research or /engineering
    link_re = re.compile(rf"^{re.escape(path_prefix)}/[a-z0-9\-]+$")
    out: list[ListEntry] = []
    seen: set[str] = set()
    for a in soup.select(f'a[href^="{path_prefix}/"]'):
        href = a.get("href", "")
        if not link_re.match(href):
            continue
        if href in seen:
            continue
        seen.add(href)
        txt = a.get_text(" ", strip=True)
        date = parse_loose_date(txt)
        # 清洗 title：移除日期和 "Featured" 前缀
        title = txt
        if date:
            # 日期之前的第一段；列表项里通常是 "<Title> Month DD, YYYY <description>"
            m = MONTH_DATE_RE.search(txt)
            if m:
                title = txt[: m.start()].strip()
        title = re.sub(r"^Featured\s+", "", title).strip()
        # 首个冒号后是副标题，取整段较为稳妥；限长
        if len(title) > 180:
            title = title[:180].rstrip() + "…"
        out.append(
            ListEntry(
                url=urljoin(base_url, href),
                title=title or href.rsplit("/", 1)[-1],
                published_at=date,
            )
        )
    return out


@register("www.deeplearning.ai")
def _deeplearning(list_html: str, base_url: str) -> list[ListEntry]:
    """The Batch archive at https://www.deeplearning.ai/the-batch/
    每期路径 `/the-batch/<slug>/`。
    """
    soup = BeautifulSoup(list_html, "lxml")
    link_re = re.compile(r"^/the-batch/([a-z0-9\-]+)/?$")
    out: list[ListEntry] = []
    seen: set[str] = set()
    for a in soup.select('a[href^="/the-batch/"]'):
        href = a.get("href", "")
        m = link_re.match(href)
        if not m:
            continue
        # 排除主 archive 入口
        if href.rstrip("/") in {"/the-batch", "/the-batch/tag"}:
            continue
        if href in seen:
            continue
        seen.add(href)
        txt = a.get_text(" ", strip=True)
        title = txt or _slug_to_placeholder(m.group(1))
        if len(title) > 180:
            title = title[:180].rstrip() + "…"
        out.append(
            ListEntry(
                url=urljoin(base_url, href),
                title=title,
                published_at=parse_loose_date(txt),
            )
        )
    return out


@register("developers.openai.com")
def _openai_developers(list_html: str, base_url: str) -> list[ListEntry]:
    """OpenAI Developer Blog archive at https://developers.openai.com/blog/
    每期路径 `/blog/<slug>/` 或 `/blog/<slug>`。
    """
    soup = BeautifulSoup(list_html, "lxml")
    link_re = re.compile(r"^/blog/([a-z0-9\-]+)/?$")
    out: list[ListEntry] = []
    seen: set[str] = set()
    for a in soup.select('a[href^="/blog/"]'):
        href = a.get("href", "")
        m = link_re.match(href)
        if not m:
            continue
        if href in seen:
            continue
        seen.add(href)
        txt = a.get_text(" ", strip=True)
        title = txt or _slug_to_placeholder(m.group(1))
        if len(title) > 180:
            title = title[:180].rstrip() + "…"
        out.append(
            ListEntry(
                url=urljoin(base_url, href),
                title=title,
                published_at=parse_loose_date(txt),
            )
        )
    return out


@register("openai.com")
def _openai_main(list_html: str, base_url: str) -> list[ListEntry]:
    """OpenAI News / Research archive at openai.com/news/ or openai.com/research/.
    每期路径 `/index/<slug>/` 或 `/research/<slug>/` 或 `/blog/<slug>`。
    """
    soup = BeautifulSoup(list_html, "lxml")
    # 多种可能前缀
    candidates = []
    for prefix in ["/index/", "/research/", "/blog/", "/news/"]:
        for a in soup.select(f'a[href^="{prefix}"]'):
            href = a.get("href", "")
            # 过滤根页面
            if href.rstrip("/") == prefix.rstrip("/"):
                continue
            # 过滤带查询的
            if "?" in href:
                continue
            candidates.append(a)
    out: list[ListEntry] = []
    seen: set[str] = set()
    for a in candidates:
        href = a.get("href", "")
        if href in seen:
            continue
        seen.add(href)
        txt = a.get_text(" ", strip=True)
        if len(txt) < 3:
            continue
        title = txt
        if len(title) > 180:
            title = title[:180].rstrip() + "…"
        out.append(
            ListEntry(
                url=urljoin(base_url, href),
                title=title or href.rsplit("/", 2)[-2],
                published_at=parse_loose_date(txt),
            )
        )
    return out


_BEEHIIV_SLUG_RE = re.compile(r"^/p/([a-z0-9\-]+)/?$")


def _slug_to_placeholder(slug: str) -> str:
    """kebab-case slug → Title Case placeholder.
    例：openai-is-building-an-ai-first-phone → Openai Is Building An Ai First Phone。
    detail 阶段 fetch.py 会用 og:title/title 覆盖；若覆盖失败，这个 placeholder
    至少是可读的，不会出现 'p' 这种歧义 fallback。"""
    s = (slug or "").replace("-", " ").strip()
    return s.title() if s else "(no title)"


@register("www.theaivalley.com")
def _ai_valley(list_html: str, base_url: str) -> list[ListEntry]:
    """AI Valley beehiiv archive. 每期 `/p/<slug>`。
    beehiiv 列表页的 <a> 只包卡片图片，没有可见文本 → adapter 只给 slug 派生
    placeholder，真标题交由 detail 阶段从 og:title/<title> 抽取后覆盖。"""
    soup = BeautifulSoup(list_html, "lxml")
    out: list[ListEntry] = []
    seen: set[str] = set()
    for a in soup.select('a[href*="/p/"]'):
        href = a.get("href", "")
        path = urlparse(href).path
        m = _BEEHIIV_SLUG_RE.match(path)
        if not m:
            continue
        url = urljoin(base_url, href)
        if url in seen:
            continue
        seen.add(url)
        slug = m.group(1)  # 正则捕获，避免 rsplit 索引陷阱
        # 列表页文本也尝试抽一次（beehiiv 偶尔把标题放在卡片 aria-label 或兄弟节点）
        txt = a.get_text(" ", strip=True)
        title = txt if txt and len(txt) >= 3 else _slug_to_placeholder(slug)
        if len(title) > 180:
            title = title[:180].rstrip() + "…"
        out.append(
            ListEntry(
                url=url,
                title=title,
                published_at=parse_loose_date(txt),
            )
        )
    return out


@register("www.superhuman.ai")
def _superhuman(list_html: str, base_url: str) -> list[ListEntry]:
    """Superhuman AI beehiiv archive（结构同 ai_valley）。"""
    return _ai_valley(list_html, base_url)


_MARKETING_BREW_URL_RE = re.compile(
    r"^/stories/(\d{4})/(\d{2})/(\d{2})/([a-z0-9\-]+)/?$"
)


@register("www.marketingbrew.com")
def _marketing_brew(list_html: str, base_url: str) -> list[ListEntry]:
    """Marketing Brew（Morning Brew 旗下）— 无 RSS，从首页 + /archive 收割。
    URL 模式 `/stories/YYYY/MM/DD/slug-name`：**日期内嵌于路径**，adapter 阶段
    直接解析，无需 detail 页面日期 probe（archive_scrape 的最优形态）。

    标题在列表页部分为空（卡片结构），统一用 slug 派生 placeholder，
    detail 阶段用 og:title 覆盖（见 fetch.py scan_detail_page_for_title）。"""
    soup = BeautifulSoup(list_html, "lxml")
    out: list[ListEntry] = []
    seen: set[str] = set()
    for a in soup.select('a[href*="/stories/"]'):
        href = a.get("href", "") or ""
        path = urlparse(href).path
        m = _MARKETING_BREW_URL_RE.match(path)
        if not m:
            continue
        url = urljoin(base_url, href)
        if url in seen:
            continue
        seen.add(url)
        y, mo, d, slug = m.groups()
        try:
            pub = datetime(int(y), int(mo), int(d), tzinfo=timezone.utc)
        except ValueError:
            pub = None
        # 列表页文本可能为空字符串；有时会拿到 section chip + title 拼接
        txt = a.get_text(" ", strip=True)
        title = txt if txt and len(txt) >= 5 else _slug_to_placeholder(slug)
        if len(title) > 180:
            title = title[:180].rstrip() + "…"
        out.append(ListEntry(url=url, title=title, published_at=pub))
    return out

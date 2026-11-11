# -*- coding: utf-8 -*-
"""
抓取与解析层 —— 纯标准库，零依赖。
"""
import gzip
import html
import io
import re
import socket
import urllib.error
import urllib.request
import zlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import xml.etree.ElementTree as ET

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "dc": "http://purl.org/dc/elements/1.1/",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "media": "http://search.yahoo.com/mrss/",
}

_BLOCK_RE = re.compile(
    r"<(script|style|noscript|iframe|svg|form)\b[^>]*>.*?</\1>", re.S | re.I
)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t\u3000\xa0]+")
_LEAD_WS = re.compile(r"\n{3,}")


def strip_html(raw: str) -> str:
    """把一段 HTML 变成干净的纯文本段落。"""
    if not raw:
        return ""
    s = _BLOCK_RE.sub(" ", raw)
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"</(p|div|li|h[1-6]|tr)>", "\n", s, flags=re.I)
    s = _TAG_RE.sub("", s)
    s = html.unescape(s)
    s = s.replace("\u200b", "").replace("\ufeff", "")
    s = _WS_RE.sub(" ", s)
    s = _LEAD_WS.sub("\n\n", s)
    return s.strip()


def http_get(url: str, timeout: int = 15) -> str:
    """带 UA、gzip 兜底的 GET。"""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        enc = (resp.headers.get("Content-Encoding") or "").lower()
    if enc == "gzip":
        try:
            raw = gzip.decompress(raw)
        except OSError:
            pass
    elif enc == "deflate":
        try:
            raw = zlib.decompress(raw, -zlib.MAX_WBITS)
        except zlib.error:
            pass
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return _decode(raw)


def _decode(raw: bytes) -> str:
    for enc in ("utf-8", "gb18030", "big5", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def parse_date(*candidates):
    """尽量从一堆候选字符串里解析出 UTC 时间戳；失败返回 None。"""
    for c in candidates:
        if not c:
            continue
        c = c.strip()
        try:
            dt = parsedate_to_datetime(c)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).timestamp()
        except (TypeError, ValueError, IndexError):
            pass
        # ISO 8601 各种变体
        iso = c.replace("Z", "+00:00")
        for fmt in (
            None,
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y/%m/%d %H:%M:%S",
            "%Y-%m-%d",
            "%Y年%m月%d日 %H:%M",
        ):
            try:
                dt = datetime.fromisoformat(iso) if fmt is None else datetime.strptime(c, fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc).timestamp()
            except ValueError:
                continue
    return None


def _text(node):
    return (node.text or "").strip() if node is not None else ""


def _find(item, *paths):
    for p in paths:
        n = item.find(p, NS)
        if n is not None:
            v = _text(n)
            if v:
                return v
    return ""


def parse_feed(xml_bytes: str, source: dict) -> list:
    """解析 RSS 2.0 / Atom，返回统一结构。"""
    items = []
    text = xml_bytes.lstrip("\ufeff \r\n\t")
    if not text:
        return items
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        # 部分源有非法字符，粗暴清洗后重试
        cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
        try:
            root = ET.fromstring(cleaned)
        except ET.ParseError:
            return items

    is_atom = root.tag.endswith("}feed") or root.tag == "feed"
    nodes = (
        root.findall(".//atom:entry", NS) if is_atom else root.findall(".//item")
    )

    for it in nodes:
        if is_atom:
            title = _find(it, "atom:title")
            link_el = it.find("atom:link[@rel='alternate']", NS) or it.find("atom:link", NS)
            link = link_el.get("href", "") if link_el is not None else _find(it, "atom:id")
            summary = _find(it, "atom:summary") or _find(it, "atom:content")
            published = _find(it, "atom:published", "atom:updated")
            guid = _find(it, "atom:id") or link
        else:
            title = _find(it, "title")
            link = _find(it, "link") or _find(it, "guid")
            summary = (
                _find(it, "description")
                or _find(it, "content:encoded")
                or _find(it, "atom:summary")
            )
            published = _find(it, "pubDate", "dc:date", "published")
            guid = _find(it, "guid") or link

        link = link.strip()
        if not link.startswith("http"):
            continue
        if not title:
            continue

        clean_title = re.sub(r"\s+", " ", strip_html(title)).strip()
        items.append(
            {
                "raw_title": clean_title,
                "url": link,
                "guid": guid,
                "raw_summary": summary,
                "published": parse_date(published),
                "source_id": source["id"],
                "source_name": source["name"],
                "category": source["category"],
                "lang": source["lang"],
                "weight": source["weight"],
            }
        )

    # 单源截断：按时间倒序只留最新的 N 条，防止大站（新华网 300+、OpenAI 1300+）刷屏
    cap = source.get("max")
    if cap and len(items) > cap:
        items.sort(key=lambda x: x["published"] or 0, reverse=True)
        items = items[:cap]
    return items


def fetch_source(source: dict) -> tuple:
    """抓一个源。返回 (source_id, items, error)。"""
    try:
        body = http_get(source["url"], timeout=18)
        items = parse_feed(body, source)
        return source["id"], items, None
    except (urllib.error.URLError, socket.timeout, TimeoutError, OSError) as e:
        return source["id"], [], f"{type(e).__name__}: {e}"
    except Exception as e:  # noqa: BLE001  —— 单源失败不能拖垮全局
        return source["id"], [], f"{type(e).__name__}: {e}"


def fetch_all(sources: list, max_workers: int = 10) -> tuple:
    """并发抓全部源。返回 (items, status_map)。"""
    items, status = [], {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(fetch_source, s): s for s in sources}
        for fut in as_completed(futures):
            sid, got, err = fut.result()
            status[sid] = {"ok": err is None, "count": len(got), "error": err}
            items.extend(got)
    return items, status


# ---------------- 正文抽取 ----------------

_ARTICLE_HINT = re.compile(
    r"<(article|div|section)[^>]*(id|class)=[\"'][^\"']*"
    r"(article|content|post|detail|main|body|text|story)[^\"']*[\"'][^>]*>",
    re.I,
)


def extract_article(html_text: str) -> str:
    """
    轻量正文抽取：剥离噪声块 → 找候选容器 → 按段落密度取最长文本块。
    比 readability 粗糙，但对主流新闻站足够，且零依赖。
    """
    if not html_text:
        return ""
    s = re.sub(r"<!--.*?-->", " ", html_text, flags=re.S)
    s = re.sub(
        r"<(script|style|noscript|nav|header|footer|aside|form|svg|iframe)\b[^>]*>.*?</\1>",
        " ",
        s,
        flags=re.S | re.I,
    )

    best, best_len = "", 0
    # 策略一：候选容器
    for m in _ARTICLE_HINT.finditer(s):
        start = m.start()
        chunk = s[start : start + 60000]
        paras = re.findall(r"<p\b[^>]*>(.*?)</p>", chunk, flags=re.S | re.I)
        joined = "\n\n".join(strip_html(p) for p in paras)
        joined = "\n".join(l for l in joined.split("\n") if len(l.strip()) > 25)
        if len(joined) > best_len:
            best, best_len = joined, len(joined)

    # 策略二：全文所有 <p>
    if best_len < 400:
        paras = re.findall(r"<p\b[^>]*>(.*?)</p>", s, flags=re.S | re.I)
        joined = "\n\n".join(strip_html(p) for p in paras)
        joined = "\n".join(l for l in joined.split("\n") if len(l.strip()) > 25)
        if len(joined) > best_len:
            best, best_len = joined, len(joined)

    if best_len >= 120:
        return _tidy_paragraphs(best)

    # 策略三：整页纯文本兜底
    plain = strip_html(s)
    return _tidy_paragraphs(plain[:4000]) if len(plain) > 200 else ""


def _tidy_paragraphs(text: str) -> str:
    lines, seen = [], set()
    for raw in text.split("\n"):
        line = raw.strip()
        if len(line) < 20:
            continue
        key = line[:40]
        if key in seen:
            continue
        seen.add(key)
        lines.append(line)
    return "\n\n".join(lines[:80])

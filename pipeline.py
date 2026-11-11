# -*- coding: utf-8 -*-
"""
聚合管线 —— 唯一的业务入口。
本地服务（server.py）和静态构建（build.py）都调这里，保证两条路径内容完全一致。
"""
import time
from concurrent.futures import ThreadPoolExecutor

import fetcher
import filtering
import health as H
import sources as S
from translate import Translator

CATEGORIES = ("ai", "politics", "health")
CATEGORY_LABEL = {"ai": "前沿 AI", "politics": "时政", "health": "养生"}


def aggregate(
    cfg: dict,
    with_articles: int = 0,
    translator: Translator | None = None,
    verbose: bool = True,
    translate_mode: str = "full",
) -> dict:
    """
    跑完整条管线。

    参数
      with_articles  : 为每个类目预抓多少篇正文（0 = 不抓，仅用 RSS 摘要）
      translate_mode : full = 标题 + 摘要；title = 只翻标题（高频构建用）；
                       none = 完全不翻（原文照出）
    返回
      {"data": {cat: [items]}, "stats": {cat: {...}}, "sources": {...},
       "articles": {id: {...}}, "engine": str, "generated_at": float}
    """
    tr = translator or Translator(cfg.get("llm"))
    t0 = time.time()

    raw, status = fetcher.fetch_all(S.SOURCES, max_workers=12)
    # 并发抓取的完成顺序每次不同，先按来源/时间排一次，
    # 让去重"保留谁"和同分排序都只由内容决定，结果可复现
    raw.sort(
        key=lambda r: (
            r.get("source_id") or "",
            r.get("published") or 0,
            r.get("guid") or r.get("url") or "",
        )
    )
    for r in raw:
        r["category"] = filtering.route_category(r)
    if verbose:
        print(f"[1/4] 抓取完成 {time.time()-t0:.1f}s — 原始 {len(raw)} 条")

    data, stats = {}, {}
    for cat in ("ai", "politics"):
        subset = [r for r in raw if r["category"] == cat]
        clean, st = filtering.process(subset, max_age_hours=cfg.get("max_age_hours", 120))
        for it in clean:
            it["tags"] = filtering.extract_tags(it)
        cap = cfg.get("max_items_per_category", 90)
        data[cat] = clean[:cap]
        st["sources_ok"] = sum(1 for v in status.values() if v["ok"])
        st["sources_total"] = len(status)
        stats[cat] = st
        if verbose:
            print(f"      {CATEGORY_LABEL[cat]}: {len(subset)} → {len(data[cat])} 条  {st.get('reasons')}")

    # ---- 养生：主题定向聚合 ----
    h_items, h_stat = _build_health(raw, cfg)
    data["health"] = h_items
    h_stat["sources_ok"] = sum(1 for v in status.values() if v["ok"])
    h_stat["sources_total"] = len(status)
    stats["health"] = h_stat
    if verbose:
        print(f"      {CATEGORY_LABEL['health']}: {h_stat['input']} → {len(h_items)} 条  {h_stat['by_topic']}")

    # ---- 翻译标题与摘要 ----
    t1 = time.time()
    _translate_feed(data, tr, translate_mode)
    if verbose:
        print(f"[2/4] 翻译完成 {time.time()-t1:.1f}s — 引擎 {tr.engine} 档位 {translate_mode}")

    # ---- 预抓正文 ----
    articles = {}
    if with_articles > 0:
        t2 = time.time()
        articles = _prefetch_articles(data, with_articles, tr, verbose)
        if verbose:
            print(f"[3/4] 正文 {time.time()-t2:.1f}s — {len(articles)} 篇")

    return {
        "data": data,
        "stats": stats,
        "sources": {"status": status, "list": S.SOURCES},
        "articles": articles,
        "engine": tr.engine,
        "generated_at": time.time(),
        "elapsed": round(time.time() - t0, 1),
    }


def _build_health(raw, cfg):
    """养生类目：中文资讯按主题过滤 + Europe PMC 循证文献。"""
    now = time.time()
    hitems = [r for r in raw if r["category"] == "health"]
    out = []

    for it in hitems:
        topic = H.route_health_item(it)
        if not topic:
            continue                      # 与四个主题无关的泛健康新闻，一律不进
        summary = fetcher.strip_html(it.get("raw_summary") or "")
        it.update(
            {
                "id": filtering.item_id(it["url"]),
                "topic": topic,
                "title": it["raw_title"],
                "summary": summary[:700],
                "summary_len": len(summary),
                "tags": [H.TOPIC_BY_ID[topic]["name"]],
                "kind": "news",
            }
        )
        it["score"] = H.score_health(it, now)
        out.append(it)

    papers = H.fetch_all_epmc(cfg.get("epmc_per_topic", 5))
    for p in papers:
        summary = fetcher.strip_html(p.get("raw_summary") or "")
        p.update(
            {
                "id": filtering.item_id(p["url"]),
                "title": p["raw_title"],
                "summary": summary[:900],
                "summary_len": len(summary),
                "tags": [H.TOPIC_BY_ID[p["topic"]]["name"], "循证文献"],
            }
        )
        p["score"] = H.score_health(p, now)
        out.append(p)

    out.sort(key=lambda x: (x["score"], x.get("published") or 0), reverse=True)
    by = {}
    for it in out:
        by[it["topic"]] = by.get(it["topic"], 0) + 1

    stat = {
        "input": len(hitems),
        "kept": len(out),
        "by_topic": by,
        "paper_count": len(papers),
        "news_count": len(out) - len(papers),
    }
    return out, stat


def _translate_feed(data, tr, mode="full"):
    """
    翻译英文条目的标题与摘要。
    注意：译文存 title_zh / summary_zh，不覆盖原文——
    前端默认展示原文，由用户点「译」按钮或开启自动翻译后切换。

    mode:
      full  → 标题 + 摘要都要（每天两次的全量构建）
      title → 只翻标题（高频增量构建，省掉大头耗时）
      none  → 全跳过
    """
    need_summary = mode == "full"
    pending = []
    for items in data.values():
        for it in items:
            if it["lang"] == "en":
                it["title_orig"] = it["title"]
                if it.get("summary"):
                    it["summary_orig"] = it["summary"]
                pending.append(it["title"])
                if need_summary and it.get("summary"):
                    pending.append(it["summary"][:260])
    if mode == "none" or not pending:
        for items in data.values():
            for it in items:
                if it["lang"] == "en":
                    it["translated"] = False
        return
    try:
        mapping = tr.translate_many(pending, workers=4)
    except Exception as e:  # noqa: BLE001
        print("[translate] 批量失败:", e)
        mapping = {}
    for items in data.values():
        for it in items:
            if it["lang"] != "en":
                continue
            t = mapping.get(it["title"])
            if t:
                it["title_zh"] = t
                it["translated"] = True
            else:
                it["translated"] = False
            if need_summary:
                s = mapping.get((it.get("summary") or "")[:260])
                if s:
                    it["summary_zh"] = s


def _prefetch_articles(data, per_cat, tr, verbose=False):
    """并发抓取头部条目的正文，英文的整篇翻译。"""
    targets = []
    for cat in CATEGORIES:
        targets.extend(data[cat][:per_cat])

    def work(item):
        try:
            page = fetcher.http_get(item["url"], timeout=18)
            body = fetcher.extract_article(page)
        except Exception:  # noqa: BLE001
            return item["id"], None
        if not body or len(body) < 120:
            return item["id"], None

        art = {
            "id": item["id"],
            "body": body,
            "body_orig": "",
            "translated": False,
        }
        if item["lang"] == "en":
            art["body_orig"] = body[:8000]
            zh = _translate_body(body, tr)
            if zh:
                art["body"] = zh
                art["translated"] = True
        item["has_body"] = True
        return item["id"], art

    out = {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        for aid, art in pool.map(work, targets):
            if art:
                out[aid] = art
    return out


def _translate_body(body, tr):
    paras = [p for p in body.split("\n\n") if p.strip()]
    acc, total = [], 0
    for p in paras:
        if total + len(p) > 6000:
            break
        acc.append(p)
        total += len(p)
    if not acc:
        return ""
    mapping = tr.translate_many(acc, workers=4)
    if not mapping:
        return ""
    return "\n\n".join(mapping.get(p, "") for p in acc if mapping.get(p))


def public_item(it: dict) -> dict:
    """给前端的精简结构，去掉内部字段。"""
    return {
        "id": it["id"],
        "title": it["title"],
        "title_zh": it.get("title_zh", ""),
        "title_orig": it.get("title_orig", ""),
        "summary": it.get("summary", ""),
        "summary_zh": it.get("summary_zh", ""),
        "summary_orig": it.get("summary_orig", ""),
        "url": it["url"],
        "source": it["source_name"],
        "source_id": it["source_id"],
        "category": it["category"],
        "lang": it["lang"],
        "published": it.get("published"),
        "tags": it.get("tags", []),
        "score": it.get("score", 0),
        "translated": it.get("translated", False),
        "has_body": it.get("has_body", False),
        "topic": it.get("topic", ""),
        "kind": it.get("kind", "news"),
        "journal": it.get("journal", ""),
        "year": it.get("year", ""),
    }

# -*- coding: utf-8 -*-
"""
信号塔 · 静态构建
==================
跑一次聚合，把结果写成纯静态文件，交给 GitHub Pages / 任意 CDN 托管。
GitHub Actions 每天定时调用本脚本即可实现"一劳永逸"。

用法：
    python3 build.py                 # 默认：每类预抓 20 篇正文
    python3 build.py --articles 0    # 不抓正文，构建最快
    python3 build.py --out docs      # 自定义输出目录
"""
import argparse
import json
import os
import shutil
import sys
import time

import pipeline
import health
from pipeline import CATEGORIES, CATEGORY_LABEL, public_item

BASE = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE, "static")

def make_standalone(out_dir: str):
    """
    生成 offline.html：把三个类目的 JSON 内联进页面。
    这样双击文件就能看，不受 file:// 的 fetch 限制，也方便发给别人。
    """
    import re

    html_path = os.path.join(out_dir, "index.html")
    if not os.path.exists(html_path):
        return
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()

    bundle = {"meta": None, "articles": {}}
    for cat in CATEGORIES:
        p = os.path.join(out_dir, "data", f"{cat}.json")
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                bundle[cat] = json.load(f)
    mp = os.path.join(out_dir, "data", "meta.json")
    if os.path.exists(mp):
        with open(mp, "r", encoding="utf-8") as f:
            bundle["meta"] = json.load(f)
    ap = os.path.join(out_dir, "data", "articles.json")
    if os.path.exists(ap):
        with open(ap, "r", encoding="utf-8") as f:
            bundle["articles"] = json.load(f)

    payload = json.dumps(bundle, ensure_ascii=False, separators=(",", ":"))
    # 防止 JSON 里出现 </script> 提前闭合标签
    payload = payload.replace("</", "<\\/")

    inject = f'<script>window.__DATA__={payload};</script>\n'
    marker = "<script>\n(() =>"
    if marker in html:
        html = html.replace(marker, inject + marker, 1)
    else:
        i = html.find("<script>")
        html = html[:i] + inject + html[i:]

    out = os.path.join(out_dir, "offline.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"      单文件离线版 → {os.path.relpath(out, out_dir)} ({os.path.getsize(out)//1024} KB)")


def default_config():
    cfg_path = os.path.join(BASE, "config.json")
    base = {"max_items_per_category": 90, "max_age_hours": 120, "llm": {}}
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                base.update(json.load(f))
        except (OSError, ValueError):
            pass
    return base


def write_json(path, obj, pretty=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2 if pretty else None,
                  separators=None if pretty else (",", ":"))
    os.replace(tmp, path)


def content_fingerprint(data: dict) -> str:
    """
    内容指纹：只取"用户能看到的内容"，不含时间戳、耗时、源状态。
    两次构建筛出的条目与译文一致 → 指纹一致 → 无需重新发布。
    """
    import hashlib

    rows = []
    for cat in CATEGORIES:
        for it in data.get(cat, []):
            rows.append(
                "|".join(
                    [
                        cat,
                        str(it.get("id", "")),
                        str(it.get("title", "")),
                        str(it.get("title_zh") or ""),
                        str(it.get("summary_zh") or ""),
                        str(it.get("published") or ""),
                    ]
                )
            )
    blob = "\n".join(sorted(rows))
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:16]


def build(
    out_dir: str,
    articles_per_cat: int,
    cfg: dict | None = None,
    translate_mode: str = "full",
    skip_if_unchanged: bool = False,
):
    cfg = cfg or default_config()
    t0 = time.time()
    print(f"信号塔构建 · 输出 → {out_dir} · 翻译档位 {translate_mode}")

    result = pipeline.aggregate(
        cfg, with_articles=articles_per_cat, translate_mode=translate_mode
    )
    data = result["data"]
    fingerprint = content_fingerprint(data)

    # 内容没变就不重写、不发布——高频构建时避免无意义的仓库变动与 Pages 重部署
    if skip_if_unchanged:
        meta_path = os.path.join(out_dir, "data", "meta.json")
        if os.path.exists(meta_path):
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    old = json.load(f)
            except (OSError, ValueError):
                old = {}
            if old.get("content_hash") == fingerprint:
                print(f"内容无变化（指纹 {fingerprint}），跳过发布 · {time.time()-t0:.1f}s")
                return {**result, "skipped": True}

    # 清理旧目录（只动自己生成的东西）
    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir, ignore_errors=True)
    os.makedirs(out_dir, exist_ok=True)

    # 前端
    for name in os.listdir(STATIC_DIR):
        src = os.path.join(STATIC_DIR, name)
        dst = os.path.join(out_dir, name)
        if os.path.isdir(src):
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)

    # 每个类目一个文件，前端按需加载
    index = {}
    for cat in CATEGORIES:
        items = [public_item(it) for it in data[cat]]
        payload = {
            "category": cat,
            "label": CATEGORY_LABEL[cat],
            "items": items,
            "stats": result["stats"][cat],
            "generated_at": result["generated_at"],
        }
        if cat == "health":
            payload["topics"] = [
                {"id": t["id"], "name": t["name"], "short": t["short"]}
                for t in health.TOPICS
            ]
            payload["guides"] = health.GUIDES
            payload["disclaimer"] = health.DISCLAIMER
        write_json(os.path.join(out_dir, "data", f"{cat}.json"), payload)
        index[cat] = {"label": CATEGORY_LABEL[cat], "count": len(items)}

    # 正文库
    arts = {k: {"body": v["body"], "body_orig": v.get("body_orig", ""),
                "translated": v.get("translated", False)}
            for k, v in result["articles"].items()}
    write_json(os.path.join(out_dir, "data", "articles.json"), arts)

    # 元信息
    src_status = result["sources"]["status"]
    write_json(
        os.path.join(out_dir, "data", "meta.json"),
        {
            "generated_at": result["generated_at"],
            "generated_at_iso": time.strftime(
                "%Y-%m-%d %H:%M:%S", time.localtime(result["generated_at"])
            ),
            "generated_at_utc_iso": time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime(result["generated_at"])
            ),
            "content_hash": fingerprint,
            "translate_mode": translate_mode,
            "engine": result["engine"],
            "elapsed": result["elapsed"],
            "categories": index,
            "sources": [
                {
                    "id": s["id"],
                    "name": s["name"],
                    "category": s["category"],
                    "lang": s["lang"],
                    "desc": s.get("desc", ""),
                    "ok": src_status.get(s["id"], {}).get("ok", False),
                    "count": src_status.get(s["id"], {}).get("count", 0),
                }
                for s in result["sources"]["list"]
            ],
            "totals": {
                "fetched": sum(v.get("count", 0) for v in src_status.values()),
                "kept": sum(len(data[c]) for c in CATEGORIES),
                "sources_ok": sum(1 for v in src_status.values() if v["ok"]),
                "sources_total": len(src_status),
            },
        },
        pretty=True,
    )

    # GitHub Pages 需要跳过 Jekyll 处理
    open(os.path.join(out_dir, ".nojekyll"), "w").close()

    # 单文件离线版：把数据内联进 HTML，双击即可打开，无需服务器
    make_standalone(out_dir)

    total_kb = sum(
        os.path.getsize(os.path.join(dp, f)) / 1024
        for dp, _, fs in os.walk(out_dir)
        for f in fs
    )
    print(
        f"完成 · {time.time()-t0:.1f}s · "
        + " / ".join(f"{v['label']} {v['count']}" for v in index.values())
        + f" 条 · 正文 {len(arts)} 篇 · {total_kb:.0f} KB"
    )
    return result


def main():
    ap = argparse.ArgumentParser(description="信号塔静态构建")
    ap.add_argument("--out", default=os.path.join(BASE, "dist"), help="输出目录")
    ap.add_argument("--articles", type=int, default=20, help="每类预抓正文篇数")
    ap.add_argument(
        "--translate",
        choices=("full", "title", "none"),
        default="full",
        help="翻译档位：full 标题+摘要（全量构建）；title 只翻标题（高频构建）",
    )
    ap.add_argument(
        "--skip-if-unchanged",
        action="store_true",
        help="内容指纹与上一版一致时不重写产物（供定时任务用，减少无意义发布）",
    )
    args = ap.parse_args()
    try:
        build(
            args.out,
            args.articles,
            translate_mode=args.translate,
            skip_if_unchanged=args.skip_if_unchanged,
        )
    except Exception as e:  # noqa: BLE001
        print(f"构建失败: {type(e).__name__}: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

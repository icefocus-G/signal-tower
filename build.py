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


def build(out_dir: str, articles_per_cat: int, cfg: dict | None = None):
    cfg = cfg or default_config()
    t0 = time.time()
    print(f"信号塔构建 · 输出 → {out_dir}")

    result = pipeline.aggregate(cfg, with_articles=articles_per_cat)
    data = result["data"]

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
    args = ap.parse_args()
    try:
        build(args.out, args.articles)
    except Exception as e:  # noqa: BLE001
        print(f"构建失败: {type(e).__name__}: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

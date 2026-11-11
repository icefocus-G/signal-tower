"""构建摘要：把 docs/data/meta.json 渲染成 GitHub Step Summary 用的 Markdown。

由 .github/workflows/daily.yml 调用，输出直接追加到 $GITHUB_STEP_SUMMARY。
"""

import json
import os
import sys

META = os.path.join("docs", "data", "meta.json")


def main() -> int:
    try:
        with open(META, encoding="utf-8") as f:
            meta = json.load(f)
    except (OSError, ValueError) as e:
        print(f"读取 meta.json 失败：{e}")
        return 0

    totals = meta.get("totals", {})
    print(f"- 生成时间：{meta.get('generated_at_iso', '—')}")
    print(f"- 翻译引擎：{meta.get('engine', '—')}")
    print(f"- 来源在线：{totals.get('sources_ok', 0)}/{totals.get('sources_total', 0)}")
    print(f"- 抓取 {totals.get('fetched', 0)} 条 → 保留 {totals.get('kept', 0)} 条")
    print(f"- 耗时：{meta.get('elapsed', 0)} 秒")
    print()

    cats = meta.get("categories", {})
    if cats:
        print("| 栏目 | 条目数 |")
        print("| --- | --- |")
        for c in cats.values():
            print(f"| {c.get('label', '—')} | {c.get('count', 0)} |")

    dead = [s["name"] for s in meta.get("sources", []) if not s.get("ok")]
    if dead:
        print()
        print(f"**异常源（{len(dead)} 个）**：" + "、".join(dead))

    return 0


if __name__ == "__main__":
    sys.exit(main())

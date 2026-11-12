#!/usr/bin/env python3
"""列出「金融行业skill精选」清单内容，打的是线上 catalog.json（永远是当前版本）。

用法：
    python3 scripts/list_catalog.py                 # 按分类列出全部
    python3 scripts/list_catalog.py --category risk-management
    python3 scripts/list_catalog.py --search 投诉    # 在 id / 名称 / 摘要 / 标签里搜
    python3 scripts/list_catalog.py --json          # 原始条目，给后续处理用
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request

# jsDelivr 的 fastly 节点更新最快；raw 作为兜底
SOURCES = [
    "https://fastly.jsdelivr.net/gh/openfcp/awesome-financial-skills@main/catalog.json",
    "https://raw.githubusercontent.com/openfcp/awesome-financial-skills/main/catalog.json",
]


def fetch_catalog() -> dict:
    last = ""
    for url in SOURCES:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "financial-skills-market/list"})
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # 换下一个源
            last = f"{url} → {e}"
    raise SystemExit(f"[list] 取不到清单：{last}")


def pick(text, lang: str) -> str:
    if isinstance(text, dict):
        return text.get(lang) or text.get("zh") or text.get("en") or ""
    return text or ""


def main() -> int:
    ap = argparse.ArgumentParser(description="列出金融技能精选清单")
    ap.add_argument("--category", help="只看某个分类 id")
    ap.add_argument("--search", help="关键词（匹配 id / 名称 / 摘要 / 标签）")
    ap.add_argument("--lang", default="zh", choices=["zh", "en"])
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

    cat = fetch_catalog()
    skills = cat.get("skills", [])
    cats = {c["id"]: c for c in cat.get("categories", [])}

    if args.search:
        kw = args.search.lower()
        skills = [
            s for s in skills
            if kw in json.dumps(
                {k: s.get(k) for k in ("id", "name", "summary", "tags")},
                ensure_ascii=False,
            ).lower()
        ]
    if args.category:
        skills = [s for s in skills if s.get("category") == args.category]

    if args.json:
        print(json.dumps(skills, ensure_ascii=False, indent=2))
        return 0

    if not skills:
        print("[list] 没匹配到技能；去掉 --category / --search 再看全量。")
        return 1

    order = [c["id"] for c in cat.get("categories", [])]
    skills.sort(key=lambda s: (order.index(s["category"]) if s.get("category") in order else 99, s["id"]))

    print(f"{pick(cat.get('title'), args.lang)} · 共 {len(skills)} 项 · updated {cat.get('updated', '—')}")
    current = None
    for s in skills:
        cid = s.get("category", "other")
        if cid != current:
            current = cid
            title = pick(cats.get(cid, {}).get("title"), args.lang) if cid in cats else cid
            print(f"\n{title}")
        src = (s.get("source") or {}).get("type", "—")
        print(
            f"  {s['id']:<42} {pick(s.get('name'), args.lang):<14} "
            f"{src:<9} v{s.get('version', '—')}"
        )
        print(f"  {'':<42} {pick(s.get('summary'), args.lang)}")
    print("\n装市场：python3 scripts/add_market.py    只装一个：python3 scripts/install_one.py <id>")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""把本清单装进 WorkBuddy 的「套件」市场，跳过手工点界面。

WorkBuddy 的「添加市场」在磁盘上只留下两样东西，这个脚本照着复现：

  1. `~/.workbuddy/plugins/marketplaces/<name>/`   —— zip 解压后的目录
     ├─ .codebuddy-plugin/marketplace.json
     ├─ plugins/<id>/...
     └─ .zip-metadata.json                          —— 下载元数据（ETag 等）
  2. `~/.workbuddy/plugins/known_marketplaces.json` —— 一条登记项

两者都在，重启 WorkBuddy 后「技能 → 套件」里就能看到。

⚠️ 前提：**先退出 WorkBuddy 再跑**。应用在运行中会把 known_marketplaces.json
按内存里的状态回写，跑完不重启的话这一条会被覆盖掉。

用法：
    python3 scripts/add_market.py                      # 用本仓库的 zip 地址
    python3 scripts/add_market.py <zip-url>            # 装别家的 zip 市场
    python3 scripts/add_market.py --dry-run            # 只检查，不落盘
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_URL = "https://openfcp.github.io/awesome-financial-skills/awesome-financial-skills.zip"

WB_HOME = Path.home() / ".workbuddy"
MARKETS_DIR = WB_HOME / "plugins" / "marketplaces"
REGISTRY = WB_HOME / "plugins" / "known_marketplaces.json"

MANIFEST_REL = Path(".codebuddy-plugin") / "marketplace.json"


def now_iso() -> str:
    t = datetime.now(timezone.utc)
    return t.strftime("%Y-%m-%dT%H:%M:%S.") + f"{t.microsecond // 1000:03d}Z"


def download(url: str, dest: Path) -> dict:
    """下载 zip，顺手把 ETag / Last-Modified 记下来（应用自己也存这两个）。"""
    req = urllib.request.Request(url, headers={"User-Agent": "awesome-financial-skills/add-market"})
    with urllib.request.urlopen(req, timeout=60) as r:
        ctype = r.headers.get("Content-Type", "")
        if "zip" not in ctype and not r.headers.get("Content-Length"):
            raise SystemExit(f"[add-market] 失败：{url} 不像是 zip（Content-Type: {ctype}）")
        dest.write_bytes(r.read())
        return {
            "url": url,
            "lastModified": r.headers.get("Last-Modified", ""),
            "etag": r.headers.get("ETag", ""),
            "downloadedAt": now_iso(),
            "installComplete": True,
        }


def extract(zip_path: Path, staging: Path) -> str:
    """解压到 staging，返回市场名（取自包内清单）。"""
    with zipfile.ZipFile(zip_path) as z:
        bad = z.testzip()
        if bad is not None:
            raise SystemExit(f"[add-market] 失败：zip 已损坏（{bad}）")
        names = z.namelist()
        # 有的 zip 会多包一层同名目录，剥掉，保证清单落在根上
        roots = {n.split("/", 1)[0] for n in names if "/" in n}
        prefix = ""
        if MANIFEST_REL.as_posix() not in names and len(roots) == 1:
            candidate = next(iter(roots)) + "/"
            if candidate + MANIFEST_REL.as_posix() in names:
                prefix = candidate
        staging.mkdir(parents=True, exist_ok=True)
        for n in names:
            if not n.startswith(prefix):
                continue
            rel = n[len(prefix):]
            if not rel or rel.endswith("/"):
                continue
            target = (staging / rel).resolve()
            if not str(target).startswith(str(staging.resolve())):
                raise SystemExit(f"[add-market] 失败：zip 内路径越界（{n}）")
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(n) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)

    manifest = staging / MANIFEST_REL
    if not manifest.is_file():
        raise SystemExit("[add-market] 失败：包里没有 .codebuddy-plugin/marketplace.json")
    name = json.loads(manifest.read_text(encoding="utf-8")).get("name", "")
    if not name:
        raise SystemExit("[add-market] 失败：包内清单没有 name 字段")
    return name


def load_registry() -> dict:
    if not REGISTRY.is_file():
        return {}
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def install(name: str, staging: Path, meta: dict, registry: dict) -> Path:
    MARKETS_DIR.mkdir(parents=True, exist_ok=True)
    target = MARKETS_DIR / name

    # 旧目录不直接删：改名留档，装坏了还能手工退回去
    if target.exists():
        backup = MARKETS_DIR / f"{name}.old-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        shutil.move(str(target), str(backup))
        print(f"[add-market] 旧目录已留档：{backup}")

    (staging / ".zip-metadata.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    shutil.move(str(staging), str(target))

    registry[name] = {
        "manifestName": name,
        "type": "zip",
        "source": {"source": "zip", "path": meta["url"], "url": meta["url"]},
        "installLocation": str(target),
        "description": f"Marketplace from {meta['url']}",
        "lastUpdated": now_iso(),
        "autoUpdate": True,
    }

    if REGISTRY.is_file():
        shutil.copyfile(REGISTRY, REGISTRY.with_suffix(".json.bak"))
    REGISTRY.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def main() -> int:
    ap = argparse.ArgumentParser(description="把 zip 市场装进 WorkBuddy，跳过手工点界面")
    ap.add_argument("url", nargs="?", default=DEFAULT_URL, help=f"zip 地址（默认 {DEFAULT_URL}）")
    ap.add_argument("--dry-run", action="store_true", help="只下载校验，不写任何文件")
    args = ap.parse_args()

    if not WB_HOME.is_dir():
        raise SystemExit(f"[add-market] 失败：没找到 {WB_HOME}，WorkBuddy 装过吗？")

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        zip_path = tmpdir / "market.zip"
        staging = tmpdir / "staging"

        print(f"[add-market] 下载 {args.url}")
        meta = download(args.url, zip_path)
        print(f"[add-market] {zip_path.stat().st_size / 1024:.1f} KB · ETag {meta['etag'] or '—'}")

        name = extract(zip_path, staging)
        n_plugins = len(list((staging / "plugins").glob("*"))) if (staging / "plugins").is_dir() else 0
        print(f"[add-market] 市场名 {name} · {n_plugins} 个插件")

        if args.dry_run:
            print("[add-market] --dry-run，未写入任何文件")
            return 0

        target = install(name, staging, meta, load_registry())
        print(f"[add-market] 已装到 {target}")
        print("[add-market] 现在退出并重新打开 WorkBuddy，「技能 → 套件」里即可看到。")
        print(f"[add-market] 登记文件备份：{REGISTRY.with_suffix('.json.bak')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

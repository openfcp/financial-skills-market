#!/usr/bin/env python3
"""只装清单里的某一个技能：把该技能目录拉到 ~/.workbuddy/skills/<id>/。

不装整个市场、不走套件界面——落盘就是一个独立的用户级技能，重启 WorkBuddy 后
在「技能」里单独出现。

用法：
    python3 scripts/install_one.py --list                 # 先看有哪些 id
    python3 scripts/install_one.py consumer-protection-review
    python3 scripts/install_one.py complaint-management --dry-run
    python3 scripts/install_one.py complaint-management --force   # 覆盖已装的（旧目录留档）

拉的是 GitHub 上的插件目录，但**只取技能本体**：`SKILL.md` 及其 assets/references，
跳过 `index.js` / `package.json` / `cordis.patch.yml` / `.codebuddy-plugin/`
（那是 dsh 与市场用的包装，独立技能不需要）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

REPO = "openfcp/awesome-financial-skills"
REF = "main"
TREE_API = f"https://api.github.com/repos/{REPO}/git/trees/{REF}?recursive=1"
BASES = [
    f"https://raw.githubusercontent.com/{REPO}/{REF}/",
    f"https://fastly.jsdelivr.net/gh/{REPO}@{REF}/",
]
API_FILE = f"https://api.github.com/repos/{REPO}/contents/{{path}}?ref={REF}"

SKILLS_DIR = Path.home() / ".workbuddy" / "skills"
PREFIX = "plugins/"
# 市场 / dsh 的包装文件，独立技能用不上
WRAPPER = {"package.json", "index.js", "cordis.patch.yml"}
SKIP_DIRS = (".codebuddy-plugin/",)


# 只允许把凭证发给 GitHub 自己的域名。第三方 CDN（jsDelivr）一律匿名请求，
# 否则 token 会落到别人家的访问日志里。
AUTH_HOSTS = {"api.github.com", "raw.githubusercontent.com"}


def auth_headers(url: str) -> dict:
    """有 gh 登录且目标是 GitHub 域名时，才带 token（5000 次/小时，否则 60 次/小时）。"""
    h = {"User-Agent": "financial-skills-market/install-one"}
    if urllib.parse.urlparse(url).hostname not in AUTH_HOSTS:
        return h
    try:
        tok = subprocess.check_output(
            ["gh", "auth", "token"], stderr=subprocess.DEVNULL, timeout=5
        ).decode().strip()
        if tok:
            h["Authorization"] = f"Bearer {tok}"
    except Exception:
        pass
    return h


def get(url: str, timeout: int = 30, accept: str | None = None) -> bytes:
    headers = auth_headers(url)
    if accept:
        headers["Accept"] = accept
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def git_blob_sha(data: bytes) -> str:
    """Git 的 blob sha1：sha1("blob <len>\\0" + content)。

    tree API 里每个文件都带这个 sha，所以下载完可以在本地算一遍比对——
    等于免费拿到了内容校验，不需要额外的清单文件或签名。
    """
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def list_plugin_blobs() -> dict[str, dict[str, str]]:
    """返回 {技能id: {相对该目录的文件路径: git blob sha}}。

    sha 用来在下载后校验内容——tree API 白送的一份完整性凭据。
    """
    tree = json.loads(get(TREE_API).decode("utf-8"))
    if "tree" not in tree:
        raise SystemExit(f"[install-one] GitHub 返回异常：{str(tree)[:200]}")
    out: dict[str, dict[str, str]] = {}
    for e in tree["tree"]:
        if e.get("type") != "blob":
            continue
        p = e["path"]
        if not p.startswith(PREFIX):
            continue
        rest = p[len(PREFIX):]
        if "/" not in rest:
            continue
        sid, rel = rest.split("/", 1)
        out.setdefault(sid, {})[rel] = e.get("sha", "")
    return {k: v for k, v in out.items() if "SKILL.md" in v}


def download(rel_from_repo: str) -> bytes:
    """三条通道依次试：GitHub 内容 API → raw → jsDelivr。

    API 排第一不是因为快，是因为它最稳：本机网络常只放行 api.github.com，
    raw 会静默超时；jsDelivr 对新仓库是冷缓存，首次请求会卡在回源上。
    """
    last = ""
    try:
        return get(API_FILE.format(path=rel_from_repo), timeout=20,
                   accept="application/vnd.github.raw")
    except Exception as e:
        last = f"api → {e}"
    for base in BASES:
        try:
            return get(base + rel_from_repo, timeout=25)
        except Exception as e:
            last = f"{last} | {base} → {e}"
    raise SystemExit(f"[install-one] 取不到 {rel_from_repo}：{last}")


def main() -> int:
    ap = argparse.ArgumentParser(description="只装清单里的某一个技能")
    ap.add_argument("id", nargs="?", help="技能 id（就是 plugins/ 下的目录名）")
    ap.add_argument("--list", action="store_true", help="列出可装的 id")
    ap.add_argument("--dry-run", action="store_true", help="只看会写哪些文件，不落盘")
    ap.add_argument("--force", action="store_true", help="已存在则覆盖（旧目录留档）")
    args = ap.parse_args()

    blobs = list_plugin_blobs()

    if args.list or not args.id:
        if not args.id and not args.list:
            ap.print_help()
        print(f"\n可装技能 {len(blobs)} 个：")
        for sid in sorted(blobs):
            installed = "（已装）" if (SKILLS_DIR / sid).is_dir() else ""
            print(f"  {sid:<42} {len(blobs[sid])} 个文件 {installed}")
        return 0 if args.list else 2

    sid = args.id.strip().strip("/")
    if sid not in blobs:
        near = [k for k in blobs if sid.lower() in k.lower()]
        hint = f"；相近的有：{', '.join(near)}" if near else ""
        raise SystemExit(f"[install-one] 没有这个技能：{sid}{hint}\n用 --list 看全量。")

    files = [rel for rel in blobs[sid] if rel not in WRAPPER and not rel.startswith(SKIP_DIRS)]
    target = SKILLS_DIR / sid

    print(f"[install-one] {sid} · {len(files)} 个文件 → {target}")
    if args.dry_run:
        for rel in sorted(files):
            print(f"  + {rel}")
        print("[install-one] --dry-run，未写入任何文件")
        return 0

    if target.exists():
        if not args.force:
            raise SystemExit(
                f"[install-one] 已存在 {target}\n想重装加 --force（旧目录会留档）。"
            )
        backup = target.with_name(f"{sid}.old-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
        shutil.move(str(target), str(backup))
        print(f"[install-one] 旧目录已留档：{backup}")

    target.mkdir(parents=True, exist_ok=True)
    for rel in sorted(files):
        dest = (target / rel).resolve()
        if not str(dest).startswith(str(target.resolve()) + "/"):
            raise SystemExit(f"[install-one] 路径越界：{rel}")
        data = download(f"{PREFIX}{sid}/{rel}")
        want = blobs[sid][rel]
        if want and git_blob_sha(data) != want:
            raise SystemExit(
                f"[install-one] {rel} 内容校验失败（不是 GitHub 上那份），已中止。"
            )
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        print(f"  ✓ {rel}" + ("" if want else "（无 sha，跳过校验）"))

    print(f"[install-one] 已装到 {target}")
    print("[install-one] 重启 WorkBuddy 后，「技能」里会单独出现这一项。")
    return 0


if __name__ == "__main__":
    sys.exit(main())

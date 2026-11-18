#!/usr/bin/env python3
"""只装清单里的某一个技能：把该技能拉到 ~/.workbuddy/skills/<id>/。

不装整个市场、不走套件界面——落盘就是一个独立的用户级技能，重启 WorkBuddy 后
在「技能」里单独出现。

数据源是线上 `catalog.json`（format 3，只存坐标不存正文），按每条技能的
`source.type` 回原件取：

- `skillhub`：GET `resolve.skillhub.url`（`{slug}` 替换）拿到 zip，解压；
  `SKILL.md` 在根目录，或包在唯一的顶层目录里（那层剥掉）。
- `github`：按 `repo` / `path` / `ref` 取 `path` 目录下的全部文件。`path` 为空
  表示技能就在仓库根；`source.exclude` 里的前缀（`examples/` 之类）跳过。

GitHub 来源用 git blob sha 校验内容：tree API 白送一份完整性凭据，下载后本地
算一遍比对，不一致就中止。`SKILL.md` 必须是取回结果里的文件，否则不落盘。

用法：
    python3 scripts/install_one.py --list                 # 先看有哪些 id
    python3 scripts/install_one.py consumer-protection-review
    python3 scripts/install_one.py complaint-management --dry-run
    python3 scripts/install_one.py complaint-management --force   # 覆盖已装的（旧目录留档）
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path

CATALOG_SOURCES = [
    "https://fastly.jsdelivr.net/gh/openfcp/awesome-financial-skills@main/catalog.json",
    "https://raw.githubusercontent.com/openfcp/awesome-financial-skills/main/catalog.json",
]

SKILLS_DIR = Path.home() / ".workbuddy" / "skills"
# 市场 / dsh 的包装文件，独立技能用不上
WRAPPER = {"package.json", "index.js", "cordis.patch.yml"}
SKIP_DIRS = (".codebuddy-plugin/",)
# 取件时一律跳过的杂项文件名
IGNORE_NAMES = {"_meta.json", ".DS_Store"}

DEFAULT_SKILLHUB_URL = "https://api.skillhub.cn/api/v1/download?slug={slug}"


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


def get_json(url: str, timeout: int = 25) -> dict:
    return json.loads(get(url, timeout=timeout).decode("utf-8"))


def git_blob_sha(data: bytes) -> str:
    """Git 的 blob sha1：sha1("blob <len>\\0" + content)。

    tree API 里每个文件都带这个 sha，所以下载完可以在本地算一遍比对——
    等于免费拿到了内容校验，不需要额外的清单文件或签名。
    """
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


# ---------------------------------------------------------------------------
# 清单
# ---------------------------------------------------------------------------


def fetch_catalog() -> dict:
    """拉线上 catalog.json：两条镜像依次试，全挂才报错。"""
    last = ""
    for url in CATALOG_SOURCES:
        try:
            cat = get_json(url)
            if isinstance(cat, dict) and isinstance(cat.get("skills"), list):
                return cat
            last = f"{url} → 清单形状异常"
        except Exception as e:  # 换下一个源
            last = f"{url} → {e}"
    raise SystemExit(f"[install-one] 取不到清单：{last}")


def catalog_skills(cat: dict) -> dict[str, dict]:
    return {s["id"]: s for s in cat.get("skills", []) if isinstance(s.get("id"), str)}


def pick(text, lang: str = "zh") -> str:
    if isinstance(text, dict):
        return text.get(lang) or text.get("zh") or text.get("en") or ""
    return text or ""


# ---------------------------------------------------------------------------
# GitHub 来源：列目录（tree API 优先，太大就退回 contents 逐层）
# ---------------------------------------------------------------------------


def excluded(rel: str, exclude: list[str]) -> bool:
    return any(rel == e or rel.startswith(e + "/") for e in exclude)


def wrappers(rel: str) -> bool:
    return rel in WRAPPER or rel.startswith(SKIP_DIRS)


def github_tree(repo: str, ref: str) -> dict:
    url = (
        "https://api.github.com/repos/"
        f"{repo}/git/trees/{urllib.parse.quote(ref)}?recursive=1"
    )
    tree = get_json(url, timeout=30)
    if "tree" not in tree:
        raise RuntimeError(f"tree API 返回异常：{str(tree)[:160]}")
    return tree


def github_contents_walk(repo: str, path: str, ref: str) -> dict[str, str]:
    """tree API 被截断（超大仓库）时的兜底：逐层 contents，拿不到 sha。"""
    out: dict[str, str] = {}
    stack = [path]
    while stack:
        cur = stack.pop().strip("/")
        suffix = "/" + urllib.parse.quote(cur) if cur else ""
        url = (
            f"https://api.github.com/repos/{repo}/contents{suffix}"
            f"?ref={urllib.parse.quote(ref)}"
        )
        items = get_json(url, timeout=30)
        if not isinstance(items, list):
            raise RuntimeError(f"contents 未返回目录列表：{repo}@{ref}/{cur}")
        for item in items:
            kind = item.get("type")
            if kind == "dir":
                stack.append(item["path"])
            elif kind == "file":
                full = item["path"]
                rel = full[len(path) + 1:] if path else full
                out[rel] = ""
    return out


def list_github_files(source: dict) -> dict[str, str]:
    """返回 {技能目录内相对路径: git blob sha}；sha 为空表示只能下载后不校验。"""
    repo = (source.get("repo") or "").strip()
    if not repo:
        raise SystemExit("[install-one] 清单里这条 github 来源缺 repo")
    path = (source.get("path") or "").strip("/")
    ref = (source.get("ref") or "main").strip() or "main"
    exclude = [
        e.strip("/") for e in (source.get("exclude") or []) if isinstance(e, str) and e.strip("/")
    ]

    tree = github_tree(repo, ref)
    if tree.get("truncated"):
        # 超大仓库的 tree 会被截断：退回逐层 contents，拿不到 sha，也就不做内容校验
        raw = github_contents_walk(repo, path, ref)
    else:
        raw = {}
        for entry in tree["tree"]:
            if entry.get("type") != "blob":
                continue
            full = entry["path"]
            if path and not full.startswith(path + "/"):
                continue
            rel = full[len(path) + 1:] if path else full
            raw[rel] = entry.get("sha", "")

    files = {
        rel: sha
        for rel, sha in raw.items()
        if rel.split("/")[-1] not in IGNORE_NAMES
        and not wrappers(rel)
        and not excluded(rel, exclude)
    }
    if "SKILL.md" not in files:
        raise SystemExit(
            f"[install-one] {repo}@{ref}/{path or '.'} 下没有 SKILL.md（已排除 {len(exclude)} 个前缀）"
        )
    return files


def github_raw_urls(source: dict, rel: str) -> list[str]:
    repo = (source.get("repo") or "").strip()
    path = (source.get("path") or "").strip("/")
    ref = (source.get("ref") or "main").strip() or "main"
    quoted = urllib.parse.quote(f"{path}/{rel}" if path else rel)
    return [
        f"https://raw.githubusercontent.com/{repo}/{ref}/{quoted}",
        f"https://fastly.jsdelivr.net/gh/{repo}@{ref}/{quoted}",
    ]


def download_github_file(source: dict, rel: str) -> bytes:
    last = ""
    for url in github_raw_urls(source, rel):
        try:
            return get(url, timeout=30)
        except Exception as e:
            last = f"{last} | {url} → {e}"
    raise SystemExit(f"[install-one] 取不到 {rel}：{last}")


# ---------------------------------------------------------------------------
# SkillHub 来源：下载 zip 并解压
# ---------------------------------------------------------------------------


def list_skillhub_files(source: dict, resolve: dict | None) -> dict[str, bytes]:
    slug = (source.get("slug") or "").strip()
    if not slug:
        raise SystemExit("[install-one] 清单里这条 skillhub 来源缺 slug")
    template = (resolve or {}).get("url") or DEFAULT_SKILLHUB_URL
    url = str(template).replace("{slug}", urllib.parse.quote(slug))

    data = get(url, timeout=60)
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise SystemExit(f"[install-one] {slug} 下载到的不是 zip（{len(data)} 字节）")

    with archive:
        names = [n for n in archive.namelist() if not n.endswith("/")]
        names = [n for n in names if n.split("/")[-1] not in IGNORE_NAMES]
        prefix = ""
        if "SKILL.md" not in names:
            roots = {n.split("/", 1)[0] for n in names if "/" in n}
            if len(roots) == 1 and f"{next(iter(roots))}/SKILL.md" in names:
                prefix = f"{next(iter(roots))}/"
        out: dict[str, bytes] = {}
        for name in names:
            if not name.startswith(prefix):
                continue
            rel = name[len(prefix):]
            if rel == "" or wrappers(rel):
                continue
            if rel.startswith("/") or ".." in rel.split("/"):
                raise SystemExit(f"[install-one] zip 内路径不安全：{name}")
            out[rel] = archive.read(name)

    if "SKILL.md" not in out:
        raise SystemExit(f"[install-one] {slug} 的 zip 里没有 SKILL.md")
    return out


# ---------------------------------------------------------------------------
# 落盘
# ---------------------------------------------------------------------------


def write_files(target: Path, files: dict[str, bytes]) -> None:
    target.mkdir(parents=True, exist_ok=True)
    root = target.resolve()
    for rel in sorted(files):
        dest = (target / rel).resolve()
        if not str(dest).startswith(str(root) + "/"):
            raise SystemExit(f"[install-one] 路径越界：{rel}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(files[rel])
        print(f"  ✓ {rel}")


def main() -> int:
    ap = argparse.ArgumentParser(description="只装清单里的某一个技能")
    ap.add_argument("id", nargs="?", help="技能 id（清单里的 id 字段）")
    ap.add_argument("--list", action="store_true", help="列出可装的 id")
    ap.add_argument("--dry-run", action="store_true", help="只看会写哪些文件，不落盘")
    ap.add_argument("--force", action="store_true", help="已存在则覆盖（旧目录留档）")
    args = ap.parse_args()

    cat = fetch_catalog()
    skills = catalog_skills(cat)
    resolve = cat.get("resolve") or {}

    if args.list or not args.id:
        if not args.id and not args.list:
            ap.print_help()
        print(f"\n可装技能 {len(skills)} 个（清单 updated {cat.get('updated', '—')}）：")
        for sid in sorted(skills):
            skill = skills[sid]
            src = (skill.get("source") or {}).get("type", "—")
            installed = "（已装）" if (SKILLS_DIR / sid).is_dir() else ""
            print(f"  {sid:<42} {src:<9} {pick(skill.get('name'))} {installed}")
        return 0 if args.list else 2

    sid = args.id.strip().strip("/")
    if sid not in skills:
        near = [k for k in skills if sid.lower() in k.lower()]
        hint = f"；相近的有：{', '.join(near[:5])}" if near else ""
        raise SystemExit(f"[install-one] 没有这个技能：{sid}{hint}\n用 --list 看全量。")

    skill = skills[sid]
    source = skill.get("source") or {}
    stype = source.get("type")
    target = SKILLS_DIR / sid

    print(f"[install-one] {sid} · {pick(skill.get('name'))} · {stype} → {target}")

    # 先取内容（dry-run 也要真的取一次，否则「会写哪些文件」是猜的）
    if stype == "skillhub":
        payload = list_skillhub_files(source, resolve.get("skillhub"))
        files = {rel: len(data) for rel, data in payload.items()}
    elif stype == "github":
        files = list_github_files(source)
        payload = {}
    else:
        raise SystemExit(f"[install-one] 不认识的来源类型：{stype}")

    print(f"[install-one] {len(files)} 个文件")
    if args.dry_run:
        for rel in sorted(files):
            print(f"  + {rel}")
        print("[install-one] --dry-run，未写入任何文件")
        return 0

    # github 来源逐文件下载 + sha 校验
    if stype == "github":
        for rel in sorted(files):
            data = download_github_file(source, rel)
            want = files[rel]
            if want and git_blob_sha(data) != want:
                raise SystemExit(
                    f"[install-one] {rel} 内容校验失败（不是 GitHub 上那份），已中止。"
                )
            payload[rel] = data

    if target.exists():
        if not args.force:
            raise SystemExit(f"[install-one] 已存在 {target}\n想重装加 --force（旧目录会留档）。")
        backup = target.with_name(f"{sid}.old-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
        shutil.move(str(target), str(backup))
        print(f"[install-one] 旧目录已留档：{backup}")

    write_files(target, payload)
    print(f"[install-one] 已装到 {target}")
    print("[install-one] 重启 WorkBuddy 后，「技能」里会单独出现这一项。")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""给 WorkBuddy 开放平台打上传包：把 frontmatter 的 name 换成 kebab-case 标识符。

为什么要单独打这个包
--------------------
开放平台把 `name` 当**标识符**校验，只收小写字母 / 数字 / 连字符：
    解析失败：Skill 标识名（name）格式不正确，仅支持小写字母、数字和连字符（kebab-case）
而 WorkBuddy 客户端把 `name` 当**显示名 + 触发名**（`Skill(skill="金融技能市场")` 就是靠它命中）。
同一个字段两边语义冲突，又没法各写一份 SKILL.md 还保持单一真相源——
所以：源仓库保持中文 name，上传时由本脚本派生出标识符版本。

改写规则（只动 frontmatter 里那一行，正文一字不改）：
    name: 金融技能市场  →  name: financial-skills-market
并且确保 display_name / displayName 存在，让平台上的展示名仍是中文。

用法：
    python3 scripts/pack_open.py                     # 输出到 ./dist/
    python3 scripts/pack_open.py --out ~/Desktop
"""

from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
IDENT = "financial-skills-market"          # 平台的 kebab-case 标识符
DISPLAY_ZH = "金融技能市场"
DISPLAY_EN = "Finance Skill Market"
EXCLUDE = {"pack_open.py"}


def split_frontmatter(text: str) -> tuple[str, str]:
    """返回 (frontmatter, 正文)。没有 frontmatter 就报错，别悄悄产出坏包。"""
    if not text.startswith("---\n"):
        raise SystemExit("[pack-open] SKILL.md 没有 frontmatter，拒绝打包")
    end = text.find("\n---\n", 3)
    if end < 0:
        raise SystemExit("[pack-open] frontmatter 没有闭合的 --- 行")
    return text[4:end + 1], text[end + 5:]


def rewrite(fm: str) -> str:
    lines = [ln for ln in fm.splitlines()]
    out: list[str] = []
    have_display = {"display_name": False, "displayName": False}
    for ln in lines:
        if ln.startswith("name:"):
            out.append(f"name: {IDENT}")
            continue
        for k in have_display:
            if ln.startswith(f"{k}:"):
                have_display[k] = True
                out.append(f"{k}: {DISPLAY_ZH}")
                break
        else:
            out.append(ln)
    # 缺的显示名补在最前面，保持 name 紧跟着的阅读顺序
    inject = []
    if not have_display["displayName"]:
        inject.append(f"displayName: {DISPLAY_ZH}")
    if not have_display["display_name"]:
        inject.append(f"display_name: {DISPLAY_ZH}")
    if "display_name_en" not in fm:
        inject.append(f"display_name_en: {DISPLAY_EN}")
    i = next((n for n, ln in enumerate(out) if ln.startswith("name:")), 0)
    out[i + 1:i + 1] = inject
    return "\n".join(out) + "\n"


def read_version(fm: str) -> str:
    for ln in fm.splitlines():
        if ln.startswith("version:"):
            return ln.split(":", 1)[1].strip().strip('"\'')
    return "0.0.0"


def build(out_dir: Path) -> Path:
    skill_md = SKILL_DIR / "SKILL.md"
    fm, body = split_frontmatter(skill_md.read_text(encoding="utf-8"))
    new_fm = rewrite(fm)
    version = read_version(new_fm)
    out_dir.mkdir(parents=True, exist_ok=True)
    zip_path = out_dir / f"{IDENT}-{version}.zip"

    files = sorted(p for p in SKILL_DIR.rglob("*")
                   if p.is_file() and not p.name.startswith(".")
                   and "__pycache__" not in p.parts
                   # 打包脚本自己是开发工具，不随技能分发
                   and p.name not in EXCLUDE)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for p in files:
            rel = p.relative_to(SKILL_DIR)
            if rel.as_posix() == "SKILL.md":
                z.writestr(f"{IDENT}/SKILL.md",
                           ("---\n" + new_fm + "---\n" + body).encode("utf-8"))
            else:
                z.write(p, f"{IDENT}/{rel.as_posix()}")

    print(f"[pack-open] {zip_path}  {round(zip_path.stat().st_size / 1024, 1)} KB / {len(files)} 个文件")
    print(f"[pack-open] name → {IDENT}   display_name → {DISPLAY_ZH}   version → {version}")
    # 自检：包内 name 必须真的是 kebab-case
    with zipfile.ZipFile(zip_path) as z:
        head = z.read(f"{IDENT}/SKILL.md").decode("utf-8").split("---")[1]
    got = next((ln.split(":", 1)[1].strip() for ln in head.splitlines()
                if ln.startswith("name:")), "")
    print(f"[pack-open] 包内 name = {got!r}  "
          f"{'✅ kebab-case' if got == IDENT else '❌ 改写失败'}")
    if got != IDENT:
        raise SystemExit(1)
    return zip_path


def main() -> int:
    ap = argparse.ArgumentParser(description="打 WorkBuddy 开放平台上传包（name 转 kebab-case）")
    ap.add_argument("--out", default=str(SKILL_DIR.parent.parent / "publish" / "open"),
                    help="输出目录（默认 ~/.workbuddy/skills/../publish/open 之外请显式指定）")
    args = ap.parse_args()
    out = Path(args.out).expanduser()
    if not out.is_absolute():
        out = Path.cwd() / out
    build(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

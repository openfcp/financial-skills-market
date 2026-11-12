# 金融技能市场 · Finance Skill Market

一个 WorkBuddy 技能：把 [金融行业skill精选](https://openfcp.github.io/awesome-financial-skills/) 这份策展清单装进 WorkBuddy——整包市场、单个技能，或按场景检索。

清单本身是给金融从业者用的：按业务场景分九类，标注来源与能力边界。当前收录 6 个消保类技能——消保审查、投诉管理、合规销售、消保检查、消保评价、官方口径问答。

## 三种用法

| 想要 | 走哪条 |
|---|---|
| 一次性看到全部技能、以后按分类挑着装 | 装整个市场 |
| 只要某一个技能 | `install_one.py <id>` |
| 问「有没有 xx 场景的技能」 | `list_catalog.py` |

### 装整个市场

```bash
python3 scripts/add_market.py --dry-run   # 先验：下载、解压、校验清单，不落盘
python3 scripts/add_market.py             # 落盘
```

它复现的是 WorkBuddy「添加市场」在磁盘上留下的两样东西：`~/.workbuddy/plugins/marketplaces/<name>/` 与 `known_marketplaces.json` 的一条登记项（原文件备份为 `.json.bak`）。

**跑之前先退出 WorkBuddy。** 应用运行中会按内存状态回写登记文件，装完必须重启才在「技能 → 套件」里可见。

### 只装一个技能

```bash
python3 scripts/install_one.py --list
python3 scripts/install_one.py consumer-protection-review
```

落盘到 `~/.workbuddy/skills/<id>/`，只取技能本体，不带 `index.js`、`package.json` 这类插件包装。

### 查清单

```bash
python3 scripts/list_catalog.py                 # 按分类列全部
python3 scripts/list_catalog.py --search 投诉
```

## 安装

**作为 WorkBuddy 技能**：把这个仓库的 `skills/financial-skills-market/` 复制到 `~/.workbuddy/skills/`，重启 WorkBuddy。

**SkillHub**：`skillhub install financial-skills-market`

**WorkBuddy 开放平台**：在开放平台「添加技能 → 上传技能」选 zip 包，审核通过后进技能市场。

## 目录结构

```
skills/financial-skills-market/
├── SKILL.md
└── scripts/
    ├── add_market.py     整包市场安装
    ├── install_one.py    单个技能安装
    └── list_catalog.py   清单检索
```

## 依赖

只用 Python 3 标准库，无第三方依赖。

## 相关

- 清单仓库：[openfcp/awesome-financial-skills](https://github.com/openfcp/awesome-financial-skills)
- 在线浏览：https://openfcp.github.io/awesome-financial-skills/

## License

MIT

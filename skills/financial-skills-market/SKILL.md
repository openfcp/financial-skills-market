---
name: 金融技能市场
slug: financial-skills-market
displayName: 金融技能市场
display_name: 金融技能市场
display_name_en: Finance Skill Market
version: 1.0.0
author: openfcp
license: MIT
homepage: https://openfcp.github.io/awesome-financial-skills/
tags:
  - 金融
  - 技能市场
  - 安装
  - WorkBuddy
description: 把策展好的金融技能装进 WorkBuddy——挂成整包市场，或只装其中某一个技能——并列出清单里的技能、分类、来源与版本。当用户说想装金融技能、订阅金融技能市场、在「技能 / 套件」里找不到这些金融技能，或问某个金融业务场景（消保审查、投诉管理、合规销售、消保检查、监管评价、官方口径问答）有没有现成技能时使用。
description_zh: 把策展好的金融技能装进 WorkBuddy：挂整包市场、只装单个技能、或按场景检索清单，六个消保类技能开箱可用。
description_en: Install curated finance skills into WorkBuddy, either as a whole marketplace or as a single skill, and list what the catalogue contains by category, source and version. Use when a user wants the finance skill market installed, cannot find these finance skills under Skills / Plugins, or asks whether a finance workflow already has a ready-made skill.
examples_zh:
  - 帮我把金融技能市场装上
  - 只装消保审查这一个技能，不要整个市场
  - 有没有做投诉数据分析的技能
examples_en:
  - Install the finance skill market for me
  - Install only the consumer protection review skill, not the whole market
  - Is there a skill for complaint data analysis
agent_created: true
---

# 金融技能市场

## 这份清单是什么

面向金融从业者的策展清单：按业务场景分九类（消费者保护、办公与设计、数据与技术、研究与分析、合规与法律、风险管理、投资与交易、产品与业务、其他），每一类标注来源与能力边界。核心技能来自 SkillHub，同一份数据同时分发成 dsh 插件索引与 WorkBuddy 市场。

这份清单线上叫「金融行业skill精选」，本技能是它的安装与检索入口。

- 站点：https://openfcp.github.io/awesome-financial-skills/
- 仓库：`openfcp/awesome-financial-skills`（`plugins/<id>/` 每个目录就是一个技能）
- 真相源：`catalog.json`（技能元数据），下面的脚本都从线上读它，所以永远是最新版本

## 先判断要哪一种

| 用户想要 | 走哪条 |
|---|---|
| 一次性看到全部技能、以后能按分类挑着装 | **装整个市场**（推荐） |
| 只要某一个技能，不想多出个市场 | **只装一个** |
| 只是问「有没有 xx 场景的技能」 | **查清单**，别装 |

## 装整个市场

```bash
cd ~/.workbuddy/skills/financial-skills-market
python3 scripts/add_market.py --dry-run   # 先验：下载、解压、校验清单，不落盘
python3 scripts/add_market.py             # 落盘
```

脚本复现的是「添加市场」在磁盘上留下的两样东西，等价于手工点一遍：

```
~/.workbuddy/plugins/marketplaces/<name>/        zip 解压后的目录（含 .zip-metadata.json）
~/.workbuddy/plugins/known_marketplaces.json     一条登记项（原文件备份为 .json.bak）
```

**跑之前先退出 WorkBuddy。** 应用运行中会按内存里的状态回写 `known_marketplaces.json`，在你退出之前写进去的登记项可能被覆盖。可行顺序只有一种：退出 → 跑脚本 → 打开。若当前正在 WorkBuddy 会话里、没法先退出，就告知用户这一步的顺序，让他自己在终端跑；不要一边运行一边写文件然后声称已生效。

装完告诉用户三件事：装到了哪个目录、登记了哪一条、需要重启才可见。市场装好后，在「技能 → 套件」里可以逐个勾选安装，不必全装。

## 只装一个技能

```bash
python3 scripts/install_one.py --list                       # 看有哪些 id、哪些已装
python3 scripts/install_one.py consumer-protection-review   # 装
python3 scripts/install_one.py <id> --force                 # 重装，旧目录留档
```

落盘位置 `~/.workbuddy/skills/<id>/`，直接就是一个独立用户级技能，不依赖市场。只取技能本体（`SKILL.md` 与 assets/references），跳过 `index.js`、`package.json`、`cordis.patch.yml`、`.codebuddy-plugin/`——那是 dsh 和市场的包装，独立技能用不上。同样需要重启才在「技能」里出现。

## 查清单

```bash
python3 scripts/list_catalog.py                    # 按分类列全部，带来源与版本
python3 scripts/list_catalog.py --search 投诉       # 按关键词找
python3 scripts/list_catalog.py --category consumer-protection
python3 scripts/list_catalog.py --json             # 原始条目
```

回答「有没有 xx 技能」时先跑这个，再回答；不要凭记忆列技能名。清单里没有的场景，直说没有，不要拿相近技能顶替。

## 出问题怎么查

- **`--dry-run` 就失败**：网络到不了 zip 地址。让用户确认 `https://openfcp.github.io/awesome-financial-skills/awesome-financial-skills.zip` 能下载；墙内可先用浏览器打开站点确认可达。
- **装完在「套件」里看不到**：九成是没重启，或登记项被应用回写覆盖。查 `~/.workbuddy/plugins/known_marketplaces.json` 里有没有这个市场的键；没有就退出应用重跑一次。
- **`install_one.py` 取不到文件**：脚本按「GitHub 内容 API → raw → jsDelivr」三条通道依次试，有 `gh` 登录还会带上 token 提高额度。三条全失败才是网络问题；这台机器上 raw 常静默超时、jsDelivr 对新仓库会卡在回源，属正常现象，不用改配置。
- **技能 id 记错**：`--list` 会给出全量 id，并在输错时提示相近项。
- **要退回上一个版本**：`add_market.py` 和 `install_one.py` 都会把旧目录改名成 `<name>.old-<时间戳>` 留着，移回去即可。

## 资源

- `scripts/add_market.py` — 整包市场安装（下载 zip / 解压 / 校验 / 登记 / 备份）
- `scripts/install_one.py` — 单个技能安装（GitHub 目录克隆式下载）
- `scripts/list_catalog.py` — 读线上 `catalog.json`，按分类或关键词列出

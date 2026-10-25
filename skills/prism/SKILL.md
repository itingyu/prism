---
name: prism
description: A 股 / 港股 / 美股 / 韩股行情与选股命令行工具 `prism` 的使用手册。触发词：「prism / 行情 / 报价 / K线 / 分时 / 涨停池 / 龙虎榜 / 资金流 / 板块 / 概念 / 财务三表 / 估值分位 / 解禁 / 融资融券 / 公告 / 新闻 / 研报 / 评级 / 机构调研 / 股东户数 / 大宗交易 / 可转债 / ETF / 基金 / 期货 / 债券 / 宏观 / 美股 / 港股 / 韩股 / JSON 输出 / 出图 / mermaid」。包含：79 条命令地图、统一选项（-f/-o/--kind/--list/--source/--arg/-n）、JSON 信封契约、1094 个扩展口径的用法、数据源点名、SVG·PNG·mermaid 出图、以及不要踩的坑。
---

# prism

命令行股票数据工具。一条命令直接出表、出图或出 JSON，不需要写代码。

```bash
prism quote 600519                 # 个股实时行情
prism kline 600519 --bars 60 --chart --png --chart-out /tmp/k.png
prism pool --date last             # 昨日涨停池
prism macro cpi                    # 宏观 CPI
```

**先确认装了没有**：`prism --version`。没有就 `pip install -e <prism 仓路径>`。

---

## 一、三条入口

| 想知道 | 命令 |
|---|---|
| 有哪些命令 | `prism`（无参给纯文本目录）或 `prism schema --all -f json` |
| 这条命令怎么用 | `prism <命令> -h`（纯文本，无 rich 边框） |
| 这个命令支持哪些扩展口径 | `prism <命令> --list` |
| 有没有现成命令能满足需求 | `prism lookup <关键词>` |
| 某个接口的原生参数与返回字段 | `prism schema <命令> -f json` |

---

## 二、命令地图（按任务找命令）

**行情**：`quote`（多代码，A/港/美混填）· `hk-quote` · `us-quote` · `kr-quote` · `index` · `world`（全球指数/外汇/加密/能源）· `spot`（金银/原油/农产品）

**K 线与盘口**：`kline`（`--period day/week/month`、`--bars`、`--chart --png`）· `hk-kline` · `us-kline` · `kr-kline` · `intraday`（分时，默认含集合竞价，`--combo` 三合一）· `changes`（盘口异动）· `patterns`（技术形态）

**选股与池子**：`screen --pool short|mid|long --min-score N` · `pool`（涨停/强势/炸板/昨涨停/跌停）· `screener <市场>`（涨跌幅/PE/PB 排行）· `hot`（人气榜/百度热搜）· `comment`（千股千评）

**个股深度**：`analyze`（技术面+评分+决策信号）· `check`（可买性：板块归属+ST/退市）· `risk`（重组/减持/立案/预亏）· `valuation`（估值分位，`--market` 全市场）· `diagram`（mermaid：logic/tree/chain）

**财务**：`financials` · `income` · `balance` · `cashflow` · `dupont`（ROE 拆解）· `growth` · `company` · `business` · `shares`（股本）· `goodwill`（商誉）· `fhps`（分红送配）· `dividend`（分红排行）

**资金面**：`flow --scope industry|individual` · `lhb`（龙虎榜，`--yyb` 看席位）· `stock-connect`（陆股通/南向）· `margin`（融资融券）· `block-trade`（大宗）· `insider-trade` · `shareholding-change` · `holders`（十大股东，`--free` 看流通）· `holder-count`（股东户数）· `pledge`（质押）· `unlock`（解禁，**前瞻窗口**）· `survey`（机构调研）

**事件与消息**：`announcement <代码> [--keyword 减持] [--days 30]` · `notice`（当日全市场公告流 1800+ 条）· `news <代码>`（个股新闻，美股代码也认）· `sentiment <代码>`（消息面打分 -100~+100）· `disclosure-schedule`（财报预约披露日）· `earnings-preview`（业绩预告/快报）· `earnings-report`（业绩报表）· `analyst-report`（个股研报）· `rating`（机构评级）· `ipo` · `buyback`（回购）· `calendar`（交易日历）

**板块**：`industry` · `concept` · `boards [--spot]` · `breadth`（涨跌家数/涨跌停）

**其他资产**：`cb`（可转债）· `etf` · `fund`（净值排行/历史/`--hold` 重仓股）· `futures` · `option` · `bond` · `macro`（234 个口径）· `misc`

**工具**：`lookup` · `schema` · `data-health`（传输层/生态库/东财配方体检）· `report`（成稿研报 markdown）· `excel`（选股池导 xlsx）· `position`（持仓台账）· `config`（配置）· `pydata`（透传 pandas）

---

## 三、统一选项（每条命令都有）

```
-f, --format text|markdown|json   输出格式
-o, --output <路径>               写文件；给目录则按时间命名
    --kind <口径>                 该命令的扩展口径
    --list                        列出该命令的全部扩展口径
    --source <方法名>              点名数据源（27 条命令支持）
    --arg k=v                     给底层接口额外传参，可重复
-n, --limit <int>                 条数
```

**口径怎么用**：`prism financials --list` 看有哪些口径 → `prism financials 600519 --kind financial_abstract`。不知道口径名就用 `prism lookup --family <命令>`。

**点名数据源**：`prism lookup --by site` 列出 163 个源方法（`tencent_quote` / `em_lhb` / `sina_*` …），然后 `prism quote 600519 --source tencent_quote`。默认走回退链，只有怀疑某源数据不对时才点名。

---

## 四、JSON 契约（写脚本只认这个）

所有 `-f json` 顶层是**信封**，不是裸数组：

```json
{"ok": true, "source": "tencent", "as_of": "2026-10-26",
 "count": 1, "rows": [{"代码": "600519", "现价": 1335.0}], "note": null}
```

| 键 | 含义 |
|---|---|
| `ok` | 是否取到数据（个别命令用 `data` 装非表格结果） |
| `source` | 实际命中的数据源 |
| `as_of` | 数据日期/时间戳 |
| `count` / `rows` | 行数与行数组；行字段由上游决定 |
| `note` | 提示（口径降级、专用命令互指等），可为 null |

取行字段：`prism schema <命令> -f json` 看 `json.rows` 说明，或直接跑一次看实际键。**不要凭记忆猜中文字段名。**

`as_of` 是判断"数据是不是新的"的唯一依据——见到 `as_of` 不是当天/上一交易日，先别急着用。

---

## 五、出图

```bash
# 单图：SVG 或 PNG（PNG 需要 --png）
prism kline 600519 --bars 60 --chart --png --chart-out /tmp/k.png
prism intraday 600519 --combo --chart --png --chart-out /tmp/i.png   # 分时+量+盘口三合一
prism diagram 600519 --type tree                                       # mermaid，直接贴 markdown
```

`--chart-out` 给 `.png` 时自动出 PNG（字体缺字会回退方块，先 `prism data-health` 看生态库）。`diagram` 输出 ```mermaid 代码块，不自带图片。

---

## 六、会踩的坑

1. **没有 `prism stock` 这一层**，动作就是顶层命令；也没有 `docs-*` 系列（已删除，改用 `prism lookup`）。
2. **财务三表必须带代码**：`prism income 600519`。裸跑会得到 `error: income 需要股票代码`（exit 2）。
3. **`unlock` 是前瞻窗口**：默认取"今天起 30 天"，不是过去 30 天。看长一点的供给压力用 `--days 180`；某票无解禁会明确报"无解禁记录"，不是缺数据源。
4. **港股没有新闻/公告**：`prism news 00700` 会失败，`announcement 00700` 同。港股只能用 `hk-quote` / `hk-kline`。
5. **`quote` 多代码用空格分隔**，不是逗号：`prism quote 600519 000001 sh000001`。
6. **`screener` 的位置参数是市场**（`cn_a` / `cn_b` / `hk` / `us`），不是股票代码。
7. **`--arg` 是透传给底层接口的逃生舱**，改参数前先 `prism lookup --call <接口>` 看签名。
8. **复杂查询先 `prism lookup <关键词>`**：79 条命令 + 1094 个口径里大概率已经有现成的，别自己拼 HTTP。
9. `prism data-health` 是排障第一步：传输层、生态库（openpyxl/字体）、东财配方三项分开报。

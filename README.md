# prism

A 股 / 港股 / 美股 / 韩股行情与选股命令行工具。79 个命令、1094 个扩展口径、
163 个数据源方法，自带网络层（代理路由、TLS 指纹、限流重试、证书规则），
不依赖任何外网 SDK 的登录态。

```bash
prism quote 600519                  # 实时行情
prism pool --only-buy               # 涨停池里能买的
prism kline 600519 --chart          # K 线图
prism analyze 600519                # 单股深度（技术面 + 评分 + 信号）
prism quote 600519 -f json          # 给脚本用
```

## 三条设计取舍

**一个动作一条命令，没有 `prism stock` 这一层。** 早期所有动作挤在一个函数签名里，
`prism --help` 要列 55 个选项，而每个动作实际只用 0–3 个。现在按动作拆开，每条的
`-h` 只列自己认识的参数。

**JSON 输出套同一个信封。** 改造前各命令顶层形态各异（数组 / 对象 / 扁平三种），
表格容器叫 `rows` / `items` / `data` 三种，`ok` 时有时无 —— 消费方没法写通用代码。
现在 `-f json` 至少都有 `ok` / `source` / `count`，表格统一在 `rows`，原有键一个不删。
详见 [输出格式](docs/output.md)。

**数据源可以点名。** 同一个数据 163 个取数方法里常有多个能拿，默认走回退链；
需要指定时 `--source <方法名>` 直接点名，不必改代码，也不必知道它属于哪个源。

## 安装

```bash
pip install -e .                # 核心：行情 / 财报 / K线 / 选股
pip install -e '.[events]'      # 加 akshare：龙虎榜 / 大宗 / 解禁 / 调研 / 研报 / 宏观
pip install -e '.[finance]'     # 加 baostock：财务质量（杜邦 / 成长）
```

可选依赖只影响对应命令，没装会报缺依赖并说明装哪个 extra，其余命令照常。

## 常用命令

```bash
# 行情与盘口
prism quote 600519 000001 上证指数      # 支持代码、逗号分隔多只、中文别名
prism kline 600519 --bars 60 --ma 5,20
prism intraday 600519 --days 5
prism pool                              # --type zt/strong/zb/prev/dt/sub
prism changes --type 火箭发射            # 盘口异动
prism flow --scope industry             # 资金流

# 财报与估值
prism financials 600519                 # --list 看 12 个口径
prism income 600519 --kind lrb
prism valuation 600519                  # --market 全市场 / --index 000300
prism dupont 600519                     # 源 baostock

# 事件
prism lhb --yyb                         # 龙虎榜 + 游资席位
prism block-trade --days 7
prism unlock --days 30
prism announcement 600519 --type 回购
prism earnings-preview --type flash

# 选股与研判
prism screen --pool short               # 池: short / mid / long
prism screener cn_a                     # 涨跌幅 / PE / PB 排行
prism analyze 600519
prism patterns 600519                   # 背离 / 跳空 / 平台突破 / 量价背离

# 域外市场
prism hk-quote 00700
prism us-quote AAPL
prism kr-quote 005930
prism macro cpi                         # --list 看 234 个宏观口径
```

完整清单：`prism -h`（按面板密排）、[命令参考](docs/commands.md)（逐条含选项）。

## 发现与自描述

命令多的时候，真正的入口不是记命令名，而是搜：

```bash
prism lookup 龙虎榜                # 搜命令 / 口径 / 源方法 / 接口
prism lookup --by site             # 163 个数据源方法按站点分组
prism lookup --family lhb          # 某命令的全部口径（含接口真名与存活状态）
prism schema quote                 # 命令参数 + JSON 输出结构（给脚本和 agent）
prism schema --all                 # 全部命令目录，机器可读
prism <命令> -h                    # 该命令的纯文本帮助
prism config list                  # 配置键一览（* = 显式设置过）
```

## 结构

```
src/prism/
  cli/        typer 入口、纯文本帮助、config 命令、最小运行时
  stock/
    command/  动作层：参数 → 取数 → 输出
    bridge/   取数层：按源拆分的方法 + 编排 + 回退
    engine/   业务口径：评分、选股、形态、估值、研报
    data/     内置数据（分类表、路由规则、口径表、交易日历）
  render/     图表：终端字符画 / K 线 SVG / 分时 SVG
  net/        网络层：代理路由、指纹、证书、限流重试
  core/ dao/  配置、状态、缓存
  util/       与业务无关的小工具
skills/prism/SKILL.md    给 AI agent 的命令地图（安装到 /var/minis/skills/prism/）
```

分层理由、取数三条路径、错误模型见 [架构](docs/architecture.md)。

## 文档

| 文档 | 内容 |
| --- | --- |
| [命令参考](docs/commands.md) | 79 个命令的用法与选项（从注册表生成） |
| [输出格式](docs/output.md) | text / markdown / JSON 信封、退出码、落盘 |
| [数据源](docs/sources.md) | 源清单、`--source`、`lookup`、口径、`pydata` |
| [配置](docs/config.md) | `~/.prism/`、代理规则、证书、缓存、环境变量 |
| [架构](docs/architecture.md) | 分层、数据流、错误模型、net 层设计 |
| [开发](docs/development.md) | 环境、测试、加命令、文档生成、发布 |
| [SKILL.md](skills/prism/SKILL.md) | agent 用的命令地图：任务 → 命令、坑与护栏 |

## 开发

```bash
pip install -e .
python -m pytest tests -q          # 契约、选项纪律、帮助形态、文档新鲜度
python tools/gen_docs.py           # 改过命令后重新生成命令参考
```


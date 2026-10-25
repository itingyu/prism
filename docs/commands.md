# 命令参考

> 本文件由 `python tools/gen_docs.py` 从命令注册表生成，**不要手改**。
> 改了命令就跑一次生成，`tests/test_docs.py` 会拦住过期版本。

共 79 个命令；其中 42 个带扩展口径，合计 1094 个口径。

## 通用选项

每条命令都可用的选项（各自命令的 `-h` 里也有）：

| 选项 | 含义 |
| --- | --- |
| `-f/--format` | 输出格式：`text`（默认）/ `markdown` / `json` |
| `-o/--output` | 写入文件；给目录则按时间命名；`-o -` 仍是标准输出 |
| `--kind <口径>` | 走该命令的扩展口径（先 `--list` 看清单） |
| `--list` | 列出该命令的扩展口径 |
| `--source <方法名>` | 点名数据源层方法（仅部分命令，见 [数据源](sources.md)） |
| `--arg k=v` | 给底层接口额外传参，可重复 |
| `-n/--limit <N>` | 条数（仅部分命令） |

JSON 输出统一信封与退出码见 [输出格式](output.md)。

## 行情与数据

### `quote` · 实时行情

`prism quote [codes] [选项]` · 口径 66 个（`prism quote --list`）
- `<codes>` 股票代码, 逗号分隔多只; 也支持 上证指数/创业板指 等别名

### `pool` · 涨停池 / 强势股池 / 炸板池 / 昨日涨停 / 跌停池

`prism pool [选项]` · 口径 7 个（`prism pool --list`）

- `--date <str>` 数据日 YYYYMMDD 或 last (上一交易日)
- `--only-buy` 只留可买板块
- `--type <str>` 池: zt(涨停)/strong(强势)/zb(炸板)/prev(昨日涨停)/dt(跌停)/sub(次新) (默认 zt)

### `check` · 可买性核查 (板块归属 + ST/退市风险)

`prism check <codes> [选项]`
- `<codes>` 股票代码, 逗号分隔多只

### `calendar` · 交易日历

`prism calendar [选项]`

- `--date <str>` 起算日 YYYYMMDD 或 last (上一交易日)
- `--days <int>` 往后几个交易日 (默认 3)

### `flow` · 资金流榜单

`prism flow [选项]` · 口径 11 个（`prism flow --list`）

- `--scope <str>` 口径: industry(行业)/individual(个股)/north(北向) (默认 industry)

### `news` · 个股新闻

`prism news [code] [选项]` · 口径 7 个（`prism news --list`）
- `<code>` 股票代码

### `announcement` · 公告列表 (可按类型/时间窗/关键词过滤)

`prism announcement <code> [选项]`
- `<code>` 股票代码

- `--days <int>` 只看最近 N 天 (0=不限) (默认 0)
- `--keyword <str>` 标题包含关键词
- `--type <str>` 按类型过滤: 增持/减持/回购/业绩预告/问询函/分红/停复牌/重大合同/股权激励/诉讼/解禁/担保/资产重组

### `financials` · 核心财务指标

`prism financials [code] [选项]` · 口径 12 个（`prism financials --list`）
- `<code>` 股票代码

### `valuation` · 估值分位: 个股历史分位 / --market 全市场 / --index 中证指数 PE-BD

`prism valuation [code] [选项]` · 口径 11 个（`prism valuation --list`）
- `<code>` 股票代码 (--market 时可省)

- `--years <int>` 回看几年 (默认 3) (默认 3)
- `--market` 改看全市场 PE/PB 分位历史
- `--index <str>` 改看中证指数估值, 如 000300

### `patterns` · 技术形态识别 (背离 / 跳空 / 平台突破 / 量价背离 / 金叉死叉)

`prism patterns <code> [选项]`
- `<code>` 股票代码

- `--bars <int>` 回看多少根 K 线 (默认 120)

### `boards` · 板块目录 (行业 + 概念); --spot 看板块即时涨跌

`prism boards [keyword] [选项]`
- `<keyword>` 板块关键词 (不填列全部)

- `--spot` 改看新浪行业板块即时行情

### `hk-quote` · 港股行情 (只取港股)

`prism hk-quote <codes> [选项]`
- `<codes>` 港股代码, 如 700 / 00700

### `us-quote` · 美股行情 (只取美股)

`prism us-quote <codes> [选项]`
- `<codes>` 美股代码, 如 AAPL

### `kr-quote` · 韩股行情 (Naver, 只取韩股)

`prism kr-quote <codes> [选项]`
- `<codes>` 韩股代码, 如 005930

## 分析与选股

### `analyze` · 单股深度 (技术面 + 评分 + 决策信号 + 画像)

`prism analyze <code> [选项]`
- `<code>` 股票代码

### `screen` · 选股池

`prism screen [选项]` · 口径 14 个（`prism screen --list`）

- `--pool <str>` 池: short(1-5日)/mid(3-6月)/long(6-18月) (默认 short)
- `--min-score <int>` 技术面分门槛 (short 池) (默认 60)
- `--codes <str>` 候选代码, 逗号分隔 (mid/long 池必填; short 池自跑全市场)

### `risk` · 风险核查 (重组/减持/立案/预亏)

`prism risk <codes> [选项]`
- `<codes>` 股票代码, 逗号分隔多只

### `report` · 成稿研报 (markdown)

`prism report [code] [选项]`
- `<code>` 股票代码 (与 --pool 二选一)

- `--pool <str>` 短线池成稿: short
- `--point <文本>` 补充论点, 可多次

### `excel` · 选股池导出 xlsx (需 openpyxl)

`prism excel [选项]`

- `--min-score <int>` 技术面分门槛 (默认 60)

### `sentiment` · 消息面打分 -100~+100

`prism sentiment [code] [选项]`
- `<code>` 股票代码 (不给则必须给 --text)

- `--text <文本>` 直接打分的文本, 可多次

### `diagram` · mermaid 图 (logic/tree/chain)

`prism diagram [code] [选项]`
- `<code>` 股票代码 (logic 用)

- `--type <str>` 图类型: logic(投资逻辑)/tree(产业链树)/chain(链条) (默认 tree)
- `--name <str>` 标的/产业链名
- `--thesis <str>` 投资逻辑主线 (logic)
- `--driver <str>` 驱动因素 (logic) / 上游 (chain), 可多次
- `--mid <str>` 产业链中游 (chain), 可多次
- `--catalyst <str>` 催化剂 (logic) / 下游 (chain), 可多次
- `--risk <str>` 风险 (logic), 可多次

## 图表

### `kline` · K 线

`prism kline [code] [选项]` · 口径 14 个（`prism kline --list`）
- `<code>` 股票代码 (A股/港股/美股)

- `--bars <int>` K 线根数 (默认 120)
- `--start <str>` 起始日期 YYYY-MM-DD
- `--end <str>` 结束日期 YYYY-MM-DD
- `--period <str>` 周期: day/week/month (默认 day)
- `--ma <str>` 均线, 逗号分隔 (默认 5,10,20)
- `--macd` 加 MACD(12,26,9) 副图
- `--chart` 出 SVG 图 (红涨绿跌 + 均线 + 量能)
- `--chart-out <str>` 图输出路径 (默认 <代码>-<周期>.svg)
- `--png` 图表输出 PNG (默认 SVG)
- `--ascii` 终端字符画
- `--ascii-style <str>` 字符画风格: thin|wide|plain (默认 thin)
- `--ascii-h <int>` 字符画高度 (行) (默认 20)
- `--ascii-w <int>` 字符画宽度 (0=自适应) (默认 0)

### `intraday` · 分时图 (默认含集合竞价)

`prism intraday <code> [选项]`
- `<code>` 股票代码

- `--days <int>` 1=当日, 5=五日 (默认 1)
- `--no-auction` 不含集合竞价
- `--after-hours` 保留 15:05 后盘后交易
- `--bar-seconds <int>` 量柱粒度(秒): 60=分钟, 30/15 用逐笔聚合 (默认 60)
- `--ma-daily <str>` 叠加日线均线, 逗号分隔; 空串关闭 (默认 5,10,20,60)
- `--ma <str>` 分时均线, 逗号分隔, 如 5,20
- `--full-axis` 纵轴强制撑满涨跌停
- `--auto-y` 纵轴按实际波动自适应
- `--combo` 三合一长图 (当日/30秒/五日)
- `--chart` 出 SVG 图
- `--chart-out <str>` 图输出路径
- `--png` 图表输出 PNG
- `--ascii` 终端字符画
- `--ascii-style <str>` 字符画风格: thin|wide|plain (默认 thin)
- `--ascii-h <int>` 字符画高度 (行) (默认 20)
- `--ascii-w <int>` 字符画宽度 (0=自适应) (默认 0)

### `hk-kline` · 港股 K 线 (只取港股)

`prism hk-kline <code> [选项]`
- `<code>` 港股代码

- `--bars <int>` K 线根数 (默认 120)
- `--start <str>`
- `--end <str>`
- `--period <str>`  (默认 day)
- `--ma <str>`  (默认 5,10,20)
- `--macd`
- `--chart`
- `--chart-out <str>`
- `--png`
- `--ascii`
- `--ascii-style <str>`  (默认 thin)
- `--ascii-h <int>`  (默认 20)
- `--ascii-w <int>`  (默认 0)

### `us-kline` · 美股 K 线 (只取美股)

`prism us-kline <code> [选项]`
- `<code>` 美股代码

- `--bars <int>` K 线根数 (默认 120)
- `--start <str>`
- `--end <str>`
- `--period <str>`  (默认 day)
- `--ma <str>`  (默认 5,10,20)
- `--macd`
- `--chart`
- `--chart-out <str>`
- `--png`
- `--ascii`
- `--ascii-style <str>`  (默认 thin)
- `--ascii-h <int>`  (默认 20)
- `--ascii-w <int>`  (默认 0)

### `kr-kline` · 韩股 K 线 (Naver, 只取韩股)

`prism kr-kline <code> [选项]`
- `<code>` 韩股代码

- `--bars <int>` K 线根数 (默认 120)
- `--start <str>`
- `--end <str>`
- `--period <str>`  (默认 day)
- `--ma <str>`  (默认 5,10,20)
- `--macd`
- `--chart`
- `--chart-out <str>`
- `--png`
- `--ascii`
- `--ascii-style <str>`  (默认 thin)
- `--ascii-h <int>`  (默认 20)
- `--ascii-w <int>`  (默认 0)

## 财务与要素

### `income` · 利润表

`prism income [code] [选项]` · 口径 7 个（`prism income --list`）
- `<code>` 股票代码 / 指数别名

### `balance` · 资产负债表

`prism balance [code] [选项]` · 口径 7 个（`prism balance --list`）
- `<code>` 股票代码 / 指数别名

### `cashflow` · 现金流量表

`prism cashflow [code] [选项]` · 口径 7 个（`prism cashflow --list`）
- `<code>` 股票代码 / 指数别名

### `company` · 公司概况

`prism company [code] [选项]` · 口径 17 个（`prism company --list`）
- `<code>` 股票代码

### `business` · 主营业务构成

`prism business [code] [选项]`
- `<code>` 股票代码

### `holders` · 十大股东; --free 看十大流通股东 (券商/基金/QFII 明细)

`prism holders [code] [选项]` · 口径 29 个（`prism holders --list`）
- `<code>` 股票代码

- `--free` 看十大流通股东 (季报口径)
- `--research` 东财股东研究 (持仓变动/机构调研)
- `--chg` 股东增减持变动
- `--date <str>` 报告期 YYYYMMDD, 缺省取最近已披露

### `industry` · 行业板块列表

`prism industry [keyword] [选项]` · 口径 24 个（`prism industry --list`）
- `<keyword>` 行业名关键字 (可省)

- `--of <str>` 看某只股票属于哪些行业/概念

### `concept` · 概念板块列表

`prism concept [code] [选项]` · 口径 11 个（`prism concept --list`）
- `<code>` 概念名关键字 (可省)

### `dividend` · 分红排行

`prism dividend [code] [选项]` · 口径 6 个（`prism dividend --list`）
- `<code>` 股票代码 (看该股分红历史, 可省)

### `margin` · 融资融券: 当日列表 / --detail 逐股明细 / --history 余额历史

`prism margin [code] [选项]` · 口径 11 个（`prism margin --list`）
- `<code>` 股票代码 (明细时筛单只)

- `--detail` 逐股两融明细 (需 --date)
- `--history` 两融余额/账户历史
- `--date <str>` 明细日期 YYYYMMDD (默认上一交易日)
- `--exchange <str>` 交易所: sse(沪)/szse(深) (默认 sse)

### `screener` · 涨跌幅/PE/PB 排行 (按市场)

`prism screener [code] [选项]`
- `<code>` 市场: cn_a(A股) / cn_b / hk / us

### `ipo` · 新股

`prism ipo [code] [选项]` · 口径 22 个（`prism ipo --list`）
- `<code>` 市场范围 (如 沪市主板, 可省)

### `index` · 指数行情

`prism index [code] [选项]` · 口径 51 个（`prism index --list`）
- `<code>` 指数代码或别名 (如 沪深300 / 000300)

### `forecast` · 盈利预测 (东财)

`prism forecast [code] [选项]`
- `<code>` 股票代码

### `dupont` · 杜邦拆解 (ROE = 净利率 × 周转 × 权益乘数, 逐季); 源 baostock

`prism dupont <code> [选项]`
- `<code>` 股票代码

- `--quarters <int>` 回看几个季度 (默认 8)

### `growth` · 成长能力 (营收/净利/净资产/EPS 同比, 逐季); 源 baostock

`prism growth <code> [选项]`
- `<code>` 股票代码

- `--quarters <int>` 回看几个季度 (默认 8)

## 事件与宏观

### `lhb` · 龙虎榜 (净买额 / 上榜原因 / 上榜后表现; --yyb 看席位)

`prism lhb [codes] [选项]` · 口径 18 个（`prism lhb --list`）
- `<codes>` 只看某只票 (可省)

- `--days <int>` 回看自然日 (默认 7)
- `--start <str>` 起始日 YYYY-MM-DD
- `--end <str>` 截止日 YYYY-MM-DD
- `--yyb` 改看活跃营业部 (游资席位)
- `--stats <str>` 统计口径: stock(个股)/jg(机构席位)/yyb(营业部)/trader(游资)
- `--span <str>` 统计区间 近一月/近三月/近六月/近一年 (默认 近一月)

### `block-trade` · 大宗交易 (成交价 / 折溢率 / 买卖营业部)

`prism block-trade [codes] [选项]` · 口径 5 个（`prism block-trade --list`）
- `<codes>` 只看某只票 (可省)

- `--days <int>` 回看自然日 (默认 7)
- `--start <str>` 起始日
- `--end <str>` 截止日

### `unlock` · 限售解禁 (解禁市值 / 占流通比 / 解禁前后表现)

`prism unlock [codes] [选项]` · 口径 6 个（`prism unlock --list`）
- `<codes>` 只看某只票 (可省)

- `--days <int>` 往后看几天 (默认 30)
- `--start <str>` 起始日
- `--end <str>` 截止日
- `--summary` 按日汇总 (供给压力日历)

### `survey` · 机构调研 (调研机构 / 类型 / 接待方式)

`prism survey [codes] [选项]`
- `<codes>` 只看某只票 (可省)

- `--date <str>` 调研日 (默认上一交易日)

### `holder-count` · 股东户数历史 (筹码集中度 / 户均持股)

`prism holder-count <code> [选项]`
- `<code>` 股票代码

### `analyst-report` · 个股研报 (评级 / 覆盖机构 / 未来三年 EPS·PE 预测)

`prism analyst-report <code> [选项]` · 口径 2 个（`prism analyst-report --list`）
- `<code>` 股票代码

### `earnings-preview` · 业绩预告 / 业绩快报 (按报告期)

`prism earnings-preview [codes] [选项]`
- `<codes>` 只看某只票 (可省)

- `--date <str>` 报告期 YYYYMMDD (默认最近已结束季度)
- `--type <str>` preview(业绩预告)/flash(业绩快报) (默认 preview)

### `pledge` · 股权质押 (质押比例 / 爆仓风险); --profile 看全市场概况

`prism pledge [codes] [选项]` · 口径 7 个（`prism pledge --list`）
- `<codes>` 只看某只票 (可省)

- `--date <str>` 统计日 YYYYMMDD (默认最新)
- `--profile` 改看全市场质押概况

### `goodwill` · 商誉规模 (减值风险面)

`prism goodwill [codes] [选项]` · 口径 3 个（`prism goodwill --list`）
- `<codes>` 只看某只票 (可省)

- `--date <str>` 报告期 YYYYMMDD

### `rating` · 机构评级 (全市场最新评级 / 上调 / 下调 / 首次覆盖)

`prism rating [选项]` · 口径 5 个（`prism rating --list`）

### `comment` · 千股千评 (全市场综合得分 / 关注度 / 机构参与度 / 主力控盘)

`prism comment [选项]` · 口径 5 个（`prism comment --list`）

- `--sort <str>` 排序字段: 综合得分/关注指数/机构参与度/主力控盘 (默认 综合得分)
- `--asc` 升序

### `macro` · 宏观指标 (CPI/PPI/PMI/LPR/M2/GDP/Shibor/社融/汇率/杠杆率 + 各国宏观)

`prism macro [indicator] [选项]` · 口径 234 个（`prism macro --list`）
- `<indicator>` cpi/ppi/pmi/lpr/m2/gdp/shibor/shrzgm/rmb/cnbs/us_nfp/us_cpi

### `stock-connect` · 陆股通资金 (当日快照 / 北向历史 / 南向历史)

`prism stock-connect [选项]` · 口径 8 个（`prism stock-connect --list`）

- `--scope <str>` summary(当日快照)/north(北向历史, 止于 2024-08)/south(南向历史) (默认 summary)
- `--days <int>` 历史口径下最近几天 (默认 10)

### `breadth` · 市场宽度 (涨跌家数 / 涨跌停家数); --history 看 20/60/120 日新高新低家数

`prism breadth [选项]`

- `--history` 改看创新高/新低家数序列

### `cb` · 可转债 (转股价值 / 溢价率 / 评级)

`prism cb [codes] [选项]`
- `<codes>` 正股代码 (可省)

### `etf` · ETF 行情列表 (按涨跌幅/成交额排序)

`prism etf [选项]`

- `--sort <str>` 排序字段: 涨跌幅/成交额/最新价 (默认 涨跌幅)
- `--asc` 升序

### `changes` · 盘口异动 (大笔买入 / 封涨停 / 火箭发射 / 60日新高等)

`prism changes [选项]`

- `--type <str>` 异动类型: 大笔买入/大笔卖出/封涨停板/火箭发射/60日新高... (默认 大笔买入)

### `hot` · 人气榜 (东财) / 百度股市热搜

`prism hot [选项]` · 口径 11 个（`prism hot --list`）

- `--date <str>` baidu 口径日期 YYYYMMDD

### `buyback` · 全市场回购 (计划金额 / 实施进度 / 已回购), 按最新公告日倒序

`prism buyback [选项]`

- `--progress <str>` 筛选进度, 如 实施中/完成

### `notice` · 全市场公告流 (当日 1800+ 条), 可按类型过滤

`prism notice [选项]` · 口径 2 个（`prism notice --list`）

- `--date <str>` 公告日期 YYYYMMDD

### `shares` · 股本结构变动 (总股本/流通/限售, 单位亿股)

`prism shares <code> [选项]`
- `<code>` 股票代码

### `disclosure-schedule` · 财报预约披露日 (首次预约与三次改期)

`prism disclosure-schedule [选项]` · 口径 1 个（`prism disclosure-schedule --list`）

- `--date <str>` 报告期 YYYYMMDD (默认最近已结束季度)
- `--scope <str>` 范围: 沪深A股/上证A股/深证A股 (默认 沪深A股)

### `earnings-report` · 业绩报表 (营收/净利/同比/ROE), 按净利同比降序

`prism earnings-report [选项]` · 口径 3 个（`prism earnings-report --list`）

- `--date <str>` 报告期 YYYYMMDD

### `fhps` · 分红送配明细 (送转/现金分红/股息率), 按股息率降序

`prism fhps [选项]`

- `--date <str>` 报告期 YYYYMMDD

### `shareholding-change` · 股东增减持 (全市场, 首次 120s 后落盘缓存 12h)

`prism shareholding-change [code] [选项]`
- `<code>` 股票代码 (不填看全市场)

- `--refresh` 强制重取 (全量约 120s)

### `insider-trade` · 董监高持股变动明细 (全市场, 首次 230s 后落盘缓存 12h)

`prism insider-trade [code] [选项]` · 口径 1 个（`prism insider-trade --list`）
- `<code>` 股票代码 (不填看全市场)

- `--refresh` 强制重取 (全量约 230s)

### `futures` · 期货行情 (主力连续日线/分钟线)、库存、合约信息、交易所数据

`prism futures [code] [选项]` · 口径 97 个（`prism futures --list`）
- `<code>` 合约代码: RB0(螺纹主连)/AU0/I0/M0...

- `--minute <int>` 切分钟线: 1/5/15/30/60 (默认 0)
- `--realtime <str>` 实时行情, 传中文品种名如 螺纹钢
- `--inventory <str>` 期货库存, 传中文品种名
- `--contracts` 看上期所合约信息
- `--date <str>` 合约/交易日 YYYYMMDD

### `option` · 期权: 成交统计 / 希腊值 / 保证金 / 商品期权 / 龙虎榜

`prism option [选项]` · 口径 62 个（`prism option --list`）

- `--date <str>` 交易日 YYYYMMDD
- `--symbol <str>` 合约口径, 如 白糖期权

### `fund` · 基金: 不给参数看净值排行, 给代码看净值历史, --hold 看重仓股

`prism fund [code] [选项]` · 口径 94 个（`prism fund --list`）
- `<code>` 基金代码 (给代码看净值历史)

- `--hold <str>` 看该基金重仓股
- `--year <str>` 重仓股年份, 如 2025
- `--order <str>` 排行方向: desc/asc (默认 desc)

### `bond` · 债券: 中债收益率曲线 / 中美国债对比 / 现券成交

`prism bond [选项]` · 口径 46 个（`prism bond --list`）

- `--start <str>` 起始日 YYYYMMDD (yield)
- `--end <str>` 结束日 YYYYMMDD (yield)

### `hk` · 港股实时快照 (2810 只)

`prism hk [code] [选项]` · 口径 34 个（`prism hk --list`）
- `<code>` 港股代码/名称 (不填看全市场)

### `spot` · 现货与商品 (金银/原油/农产品/伦交所库存等)

`prism spot [kind_pos] [选项]` · 口径 16 个（`prism spot --list`）
- `<kind_pos>` 口径名 (简写; 等价 --kind)

### `world` · 海外市场 (全球指数/外汇/加密/能源)

`prism world [kind_pos] [选项]` · 口径 33 个（`prism world --list`）
- `<kind_pos>` 口径名 (简写; 等价 --kind)

### `misc` · 杂项数据 (汽车/电影/游戏/榜单一类, 与行情弱相关)

`prism misc [kind_pos] [选项]` · 口径 67 个（`prism misc --list`）
- `<kind_pos>` 口径名 (简写; 等价 --kind)

## 取数入口与自描述

### `lookup` · 查命令/口径/源方法/接口, 或直接按名调接口 (--call / --url / --health)

`prism lookup [keyword] [选项]`
- `<keyword>` 关键词: 命令/口径/方法/接口/中文说法

- `--only <str>` 只看一层: commands|kinds|sources|api
- `--family <str>` 看某个命令的全部口径 (含接口真名/状态)
- `--by <str>` 源方法分组: site 按站点 / function 按功能
- `--list-domains` 列出全部 akshare 数据域
- `--domain <str>` 某个数据域的接口明细, 如 股东
- `--call <str>` 按名调接口, 如 stock_zt_pool_em
- `--url <str>` 裸 HTTP 直调
- `--health` 数据面体检
- `--post` --url 时用 POST

### `schema` · 命令参数与 JSON 输出结构自描述 (给脚本和 agent 用)

`prism schema [name] [选项]`
- `<name>` 命令名 (例: lhb); --all 列全部

- `--all` 列出全部命令

## 其他

### `data-health` · 数据面体检: 传输层 / 生态库 / 东财配方各是否可用

`prism data-health [选项]`

## 其他命令

### `position` · 持仓台账与盈亏 (本地 JSON, 默认 ~/.prism/positions.json)

- `prism position add` — 建仓/加仓 (同代码自动按加权成本合并)
- `prism position list` — 列出持仓与浮动盈亏
- `prism position remove` — 减仓/清仓

### `config` · 查看/修改 ~/.prism/config.json

- `prism config get` — 读一个键的当前生效值
- `prism config list` — 列出全部配置键 (标 * 的是配置文件里写死的)
- `prism config pass` — 写入代理密码 (密文存 config.json 的 proxy_auth)
- `prism config set` — 写一个键 (当场校验)
- `prism config unpass` — 删掉某个代理密码
- `prism config unset` — 删掉一个键, 回到默认值

### `pydata` · 外部金融库任意函数, 走 prism 传输层出网 (chrome 指纹/代理路由/限流重试)

用法见 `prism pydata -h`。

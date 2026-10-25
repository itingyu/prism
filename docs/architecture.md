# 架构

## 分层

```
cli/        typer 命令注册、纯文本帮助、config、最小运行时（读参数 → dispatch → 渲染）
  ↓
stock/
  command/  动作层：参数归一 → 取数 → 包装成信封
  bridge/   取数层：按源拆分的方法 + 编排 + 回退 + 口径路由
  engine/   业务口径：评分、选股、形态、估值、研报、导出
  data/     内置数据：分类表、路由规则、逆向文档、交易日历
  ↓
net/        网络层：代理路由、TLS 指纹、证书规则、限流、重试、熔断
core/ dao/  配置、密钥、状态、缓存
render/     图表：终端字符画、K 线 SVG、分时 SVG
util/       与业务无关的小工具（数值转换、单位格式化）
```

依赖只能向下。`render/` 与 `util/` 是叶子，不认识 stock；`bridge/` 不认识 `command/`；
`core/` 不知道 net 和 stock 的存在，只描述"配置文件长什么样"。

## 取数三条路径

同样是"拿一份数据"，prism 里有三种粒度，用途不同：

| 路径 | 入口 | 粒度 | 什么时候用 |
|---|---|---|---|
| 源方法 | `bridge/sources/*.py` | 一次 HTTP + 解析，返回原始形状 | `--source` 点名、`pydata` 透传 |
| 编排 | `bridge/srv.py` | 跨源回退，统一字段 | 大多数命令的默认路径 |
| 业务 | `engine/` | 多份数据合成一个结论 | 评分、选股、形态、估值 |

`bridge/sources/` 按站点分文件，163 个方法：东财 38（行情 / datacenter / F10）、
同花顺 35、雪球 30、新浪 21、腾讯 19、巨潮 6、中证 4、efinance 3、上交所 3、
Naver 2、公告老域 2。每个方法只做"发请求 + 解析成 dict"，不做业务判断。

`bridge/ak_*.py` 是 akshare 的接入层：`ak.py` 核心行情与事件，`ak_ext.py` 扩展数据集，
`ak_via.py` 记录"上游接口 → 专用命令"的映射（由 `tools/gen_ak_via.py` 生成并校验），
`source_pick.py` 负责把 `--source` 的方法名映射到具体调用。

## 错误模型

七条取数通道的异常（engine / srv / 原始接口 / 生态库 / 文档 / 东财 / HTTP）全部继承
`StockError`，通道信息收进 `source` 字段，调用方只需 `except StockError`。

`exit_code` 由异常类自己声明，CLI 不逐个 if 转发：

| 码 | 含义 |
|---|---|
| 0 | 成功（可能含行级失败，见下） |
| 1 | 取数失败 |
| 2 | 用法错误（缺参数 / 参数冲突） |
| 3 | 底层 HTTP 直调失败（证书类问题单列在这里） |

三条硬规矩：

1. **数据源失败 ≠ 没有数据。** 失败必须带原因，不静默返回空表。
2. **接口返回 0 或空不当正常值。** 由各桥透传上游 status，不自己解释。
3. **拿不到就明说。** 北向资金不可用时标注不可用，不填 0。

## 输出契约

动作返回 dict → `_envelope` 统一成信封 → `_render` 按格式渲染。信封只增不改：
表格统一进 `rows`，原有业务键一个不删。细节见 [输出格式](output.md)。

## 渲染层

`render/` 零依赖手写，不用 matplotlib：沙盒和用户机器都未必有图形栈，而 SVG 是
纯文本，生成即可预览，也能直接贴进 HTML 报告。

- `ascii_chart.py` — 终端字符画 K 线 / 分时，ANSI 红涨绿跌
- `kline_svg.py` — K 线 SVG：蜡烛 + 均线 + 量能 + 十字轴
- `intraday_svg.py` — 分时 SVG：单日 / 五日，左右双轴
- `png.py` — SVG → PNG，降级链 `rsvg-convert` → `cairosvg` → 明确报错

分时图的纵轴必须对称（0% 落在正中），否则同一只票的 ±1% 看起来不一样长，看图的人
会误判强弱。五日图的涨幅轴统一以最后一天的昨收为基准，否则轴上只有一个 % 却混用
每天各自的昨收，自相矛盾。

`stock/command/_render.py` 是另一层"渲染"：它把动作结果格式化成 text / markdown /
json，与画图无关。

## net 层

`net/pyshim.py` 是 prism 的出网收口：它 patch `requests.Session.request`，
让第三方库（akshare 等）的出网落到 prism 的传输层 —— 否则那些库会绕过代理、
指纹和限流，出现"命令行能取到、脚本里取不到"的怪事。

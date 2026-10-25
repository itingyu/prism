# 数据源

prism 的价值不在"能查到"，而在**同一个数据有多个来源可选，且能点名**。外部库
（akshare / efinance / baostock）只是其中一路，站内直连的源才是主力 —— 它们更稳、
字段更全、不受上游库版本影响。

## 三条取数路径

| 路径 | 是什么 | 怎么用 |
| --- | --- | --- |
| 站内直连 | 163 个方法，直接打站点接口（带指纹与路由） | 命令默认走这条；`--source` 点名 |
| 外部库 | akshare / efinance / baostock / tushare | `--kind` 口径、`pydata` 任意函数 |
| 内置口径 | 逆向得到的东财 reportName 配方 | `lookup --family`、`lookup --call` |

## 源清单

163 个方法，按站点归属（不按方法名前缀，见文末）：

| 模块 | 站点 | 方法数 | 反爬手段 |
| --- | --- | --- | --- |
| `em/` | 东方财富 | 38 | 固定 `ut` token；datacenter 需 `source=WEB` |
| `ths.py` | 同花顺 | 35 | v cookie（qjs 跑 akshare 的 js）+ chrome120 指纹 |
| `xueqiu.py` | 雪球 | 30 | chrome110 TLS 指纹 + 3 页 warmup，无 token |
| `sina.py` | 新浪财经 | 21 | Referer 校验 |
| `tencent.py` | 腾讯财经 | 19 | 部分端点需 curl_cffi 指纹 |
| `cninfo.py` | 巨潮 | 6 | 先 GET 首页收 cookie 再 POST |
| `csindex.py` | 中证指数 | 4 | Referer 校验 |
| `ef.py` | efinance | 3 | 本地库，无网络栈直控 |
| `sse.py` | 上交所 | 3 | 直连 |
| `naver.py` | Naver（韩股） | 2 | 直连 |
| `np.py` | 东财公告老域 | 2 | 统一会话 + 固定 UA |

```bash
prism lookup --by site      # 按站点分组的完整清单
prism lookup --by function  # 按功能分组
prism lookup --health       # 方法数 / 外部库安装情况 / 路由覆盖
```

## 点名一个源

27 个命令支持 `--source`（`lookup`、`quote`、`kline`、`financials`、`pool`、
`holders`、`flow` 等）。方法必须属于该命令的功能类，否则直接报错并告诉你去哪个命令：

```bash
prism quote 600519 --source tencent_a        # 腾讯单只快照
prism quote 600519 --source gtimg_hq         # 腾讯批量接口
prism kline 600519 --source xueqiu_kline --arg period=week
prism pool --source ths_rank_cxfl       # 涨停池，同花顺原始载荷
```

参数由方法签名自动适配（代码形态自动补前缀、条数、日期窗），其余透传：

```bash
prism <命令> --source <方法名> [位置参数] --arg k=v [--arg k2=v2]
```

注意 `--source` 是**绕过回退链**的：点名的方法失败就是失败，不会静默换个源给你
一个"看起来正常"的结果。这也是它的用处 —— 排查"到底哪个源在给数"。

## 扩展口径 `--kind`

站内直连方法覆盖不到的细分数据，挂在各命令的 `--kind` 下，共 42 个命令、
1094 个口径，全部来自 akshare 接口的封装（`bridge/ak_families.py`）：

```bash
prism quote --list                 # 该命令有哪些口径
prism kline 600519 --kind stock_intraday_em
prism macro --list                 # 234 个宏观口径，按国家分组
prism macro "australia cpi quarterly"   # 分词匹配，唯一命中直接出数
prism lookup --family lhb          # 某命令的全部口径（含接口真名与存活状态）
```

口径名就是 akshare 的接口名，所以 `prism lookup stock_bid_ask_em` 能反查到它
挂在哪个命令下。

## 任意外部函数 `pydata`

不属于任何命令、但 akshare / efinance / baostock 里有、又想走 prism 指纹通道的：

```bash
prism pydata <库.函数> [payload] [-n 条数]
prism pydata akshare.stock_zt_pool_em '{"date":"20261024"}'
```

`payload` 是 JSON：对象 → 关键字参数，数组 → 位置参数，其他 → 单个位置参数。
外部库返回的 DataFrame 会被归一成表格（列名保留中文原始列名）。

它和 `--kind` 的区别：`--kind` 是**登记过**的接口（有命令、有口径、有存活状态），
`pydata` 是逃生口 —— 能跑，但不保证字段归一与错误语义。

## 回退与来源

内置方法的默认选择写在 `stock/data/api_categories.json`：每类给出 `primary`
（首选链）与 `fallback`（兜底池）。返回结果里的 `source` 字段说明这次实际是谁给的：

```bash
prism quote 600519 -f json | grep -o '"source": *"[^"]*"'
{"ok": true, "count": 1, "rows": [...]}   # 行内字段 "源": "tencent"
```

多源结果不一致时以 `source` 为准去复核 —— 不同源的复权口径、字段含义不完全相同。

## 为什么按域名而不是按方法名分源

`gtimg_*` 七个方法名字像"腾讯行情"，实际打的是 `vip.stock.finance.sina.com.cn`，
所以归在 `sina.py`，名字不改（改名会连带坏掉上层引用与分类表）。

同理，传输层不属于任何源：`_xueqiu_session` 名义属雪球，但 `tencent_kline_global`
等也借它 —— 要 curl_cffi 指纹才过 `web.ifzq.gtimg.cn`。指纹是传输层属性，
放在 `_base.py` 的 `SourceBase`。

## 东财配方

东财的接口不靠拼 URL，靠 `data/reverse/em_recipes.json` 里的配方表
（reportName + filter 模板 + 列序）。它是**源码数据**，不是文档：

```bash
rg -n 'RPT_F10_FINANCE' src/prism/stock/data/reverse/em_recipes.json
```

改接口配方要连带跑 `prism data-health`：它会报配方条数与可用性。

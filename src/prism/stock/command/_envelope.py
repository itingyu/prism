"""JSON 输出信封: 所有命令 `-f json` 的结果套同一层外壳

## 为什么

改造前各命令的 JSON 形态各写各的, 调用方只能逐命令硬编码:

    prism quote       → [{"现价": 1335.0, ...}]        顶层是数组
    prism pool        → {"ok":true,"date":...,"count":82,"rows":[...]}
    prism financials  → {"ok":true,"source":"xueqiu","data":{"symbol":...,"items":[...]}}
    prism calendar    → {"今天":"2026-10-26 Monday", ...}   没有 ok
    prism breadth     → {"source":"akshare","count":12,"data":{...}}   没有 ok

三种顶层形态 (数组 / 对象 / 扁平)、三种表格容器名 (rows / items / data)、
`ok` 字段时有时无 —— 程序消费方 (agent、脚本、别的仓) 没法写通用代码。

## 现在的约定

所有 `-f json` 输出至少有 `ok` / `source` / `count`, 表格型载荷统一在 `rows`。
**采用加法而不是搬家**: 原有的键一个不删 (rows / data / items / title / date
全留在原位), 只在缺的时候补标准键, 所以老脚本读 out['rows'] 照样能用,
只有"顶层是数组"的命令 (quote 等) 变成对象 —— 这是唯一一处形状变化。
"""

# 标准信封键 (顺序即输出顺序)
_ENV_KEYS = ('ok', 'source', 'as_of', 'count', 'rows', 'note')

# 这些键从别处搬过来当标准键 (上游各命令的叫法不统一)
_SOURCE_ALIASES = ('source', '源', 'src')
_ASOF_ALIASES = ('as_of', 'date', 'data_date', 'qdate', '交易日')


def _first(d, names):
    for n in names:
        if n in d and d[n] not in (None, ''):
            return d[n]
    return None


def envelope(out):
    """给一个动作的返回值套上标准信封 (加法式, 不删原有键)"""
    if isinstance(out, list):
        # 顶层是数组的只有一种含义: 一张表
        return {'ok': True, 'count': len(out), 'rows': out}
    if isinstance(out, str):
        return {'ok': True, 'source': 'http', 'data': out}
    if not isinstance(out, dict):
        return {'ok': True, 'data': out}

    env = dict(out)
    if 'ok' not in env:
        env['ok'] = True
    else:
        env['ok'] = bool(env['ok'])
    src = _first(env, _SOURCE_ALIASES)
    if src is not None and 'source' not in env:
        env['source'] = src

    # 表格载荷统一叫 rows: items / data.items 都并过来, 原键保留
    rows = env.get('rows')
    if not isinstance(rows, list):
        items = env.get('items')
        if not isinstance(items, list):
            data = env.get('data')
            if isinstance(data, dict) and isinstance(data.get('items'), list):
                items = data['items']
        if isinstance(items, list):
            env['rows'] = items
            rows = items
    if 'count' not in env:
        env['count'] = len(rows) if isinstance(rows, list) else (
            len(env.get('data', {})) if isinstance(env.get('data'), dict) else 1)
    asof = _first(env, _ASOF_ALIASES)
    if asof is not None and 'as_of' not in env:
        env['as_of'] = asof
    # 标准键排前面: 调用方读 json 时第一眼就看到 ok/count/rows
    head = {}
    for k in _ENV_KEYS:
        if k in env:
            head[k] = env.pop(k)
    head.update(env)
    return head


def describe(action=None):
    """信封本身的形状说明 (给 prism schema 用)"""
    return {
        'ok': 'bool — 动作是否成功 (缺省 true; 失败时 false)',
        'source': 'str — 数据源标识 (tencent / akshare / xueqiu / baostock ...)',
        'as_of': 'str — 数据日期或取数窗口 (有才出现)',
        'count': 'int — rows 的条数',
        'rows': 'list — 表格型载荷的行; 行内字段由上游接口决定',
        'data': 'object — 非表格型载荷 (目录/统计/单值) 放这里',
        'note': 'str — 口径说明或告警 (有才出现)',
    }

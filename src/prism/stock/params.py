"""`--kind` 入参归一: 同一个命令换数据源, 参数名/写法不用跟着换

问题: `prism holders --kind xxx --arg symbol=600519` 与 `--arg code=600519`
在不同 akshare 接口上名不一样 (symbol / code / stock_code / ts_code ...),
以前不在签名里的键会被静默丢掉, 表现为"缺必填参数"。

做法: 按"语义组"匹配目标函数的实参名, 再统一值的写法 (日期去横线、整数
参数转 int)。只补不覆盖: 用户显式写了接口真名就原样用。
"""
from __future__ import annotations

import inspect
import re

# 语义组: 组内名字等价, 按顺序优先 (靠前的更像"通用叫法")
GROUPS: dict[str, tuple[str, ...]] = {
    'code': ('code', 'symbol', 'stock_code', 'stock', 'ts_code', 'secid',
             'security', 'symbol_code', 'ticker', 'item', 'fund_code',
             'bond_code', 'index_code', 'em_code'),
    'start': ('start_date', 'start', 'begin', 'beg', 'start_time', 'stime',
              'from_date', 'startdate', 'begin_date'),
    'end': ('end_date', 'end', 'finish', 'end_time', 'etime', 'to_date',
            'enddate'),
    'date': ('date', 'day', 'trade_date', 'qdate', 'report_date', 'period',
             'month', 'year'),
    'limit': ('limit', 'count', 'rows', 'num', 'n', 'top', 'size', 'page_size'),
    'period': ('period', 'freq', 'frequency', 'timeframe', 'klt', 'cycle',
               'interval'),
    'adjust': ('adjust', 'fq', 'qfq'),
}
_LOOKUP = {alias: g for g, names in GROUPS.items() for alias in names}
_DATE_HINT = ('date', 'time', 'day', 'qdate', 'month', 'year')
_INT_HINT = ('limit', 'count', 'rows', 'num', 'size', 'top', 'page_size')


def _norm_value(name: str, v):
    """统一值写法: 日期 2026-10-25 → 20261025; 条数 '20' → 20"""
    if isinstance(v, str):
        s = v.strip()
        low = name.lower()
        if s and re.fullmatch(r'\d{4}-\d{2}-\d{2}', s) and any(h in low for h in _DATE_HINT):
            return s.replace('-', '')
        if s.isdigit() and len(s) <= 6 and any(h in low for h in _INT_HINT):
            return int(s)
    return v


def fit(func_name: str, params: dict, names=None, strict: bool = False) -> dict:
    """把 params 的键名迁到 func_name 的实参名上; strict 时丢掉对不上的键"""
    if names is None:
        names = list(_signature_names(func_name))
    if not params:
        return dict(params)
    names = list(names)
    nameset = set(names)
    out = {}
    for k, v in params.items():
        if k in nameset:
            out[k] = _norm_value(k, v)
            continue
        grp = _LOOKUP.get(k)
        tgt = None
        if grp:
            for cand in GROUPS[grp]:
                if cand in nameset and cand not in params and cand not in out:
                    tgt = cand
                    break
        if tgt:
            out[tgt] = _norm_value(tgt, v)
        elif not strict:
            out[k] = v
    return out


def _signature_names(func_name: str):
    try:
        import akshare as ak
        fn = getattr(ak, func_name, None)
        if fn is None:
            return []
        sig = inspect.signature(fn)
        if any(p.kind == p.VAR_KEYWORD for p in sig.parameters.values()):
            return []
        return [n for n, p in sig.parameters.items()
                if p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY)]
    except Exception:  # noqa: BLE001
        return []


def explain(func_name: str, params: dict) -> list[str]:
    """调试用: 返回 '旧名 → 新名' 的迁移明细"""
    names = set(_signature_names(func_name))
    moved = []
    for k in params:
        if k in names:
            continue
        grp = _LOOKUP.get(k)
        if not grp:
            continue
        for cand in GROUPS[grp]:
            if cand in names:
                moved.append(f'{k} → {cand}')
                break
    return moved

"""估值分位

绝对 PE(20.49) 没什么信息量 —— 同一个数在不同行业、不同周期里含义完全不同。
真正有用的是**当前值在自己历史里的分位**: "PE 20.5, 处于近 3 年 12% 分位"
比"PE 20.5"信息量大一个量级。

分位口径 (与常见看盘软件一致):
    百分位 = 历史中低于当前值的样本数 / 有效样本数 × 100
分档:
    <20 低位 / 20-40 中低 / 40-60 中位 / 60-80 中高 / >80 高位
"""

__all__ = ['percentile', 'band', 'summarize', 'summarize_series']

BANDS = ((20.0, '低位'), (40.0, '中低'), (60.0, '中位'), (80.0, '中高'))


def _valid(values):
    out = []
    for v in values or []:
        if v is None:
            continue
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if f == f:            # 排除 NaN
            out.append(f)
    return out


def percentile(values, current) -> float:
    """当前值在历史样本中的百分位 (0-100); 无有效样本返回 NaN"""
    vs = _valid(values)
    if not vs or current is None:
        return float('nan')
    try:
        cur = float(current)
    except (TypeError, ValueError):
        return float('nan')
    if cur != cur:
        return float('nan')
    below = sum(1 for v in vs if v < cur)
    equal = sum(1 for v in vs if v == cur)
    # 与当前值相等的样本算一半, 避免"当前值就是历史最大"时给出 100 而不是 ~99
    return (below + equal / 2.0) / len(vs) * 100.0


def band(pct) -> str:
    """分位 → 档位标签"""
    if pct is None or pct != pct:
        return '—'
    for lim, name in BANDS:
        if pct < lim:
            return name
    return '高位'


def summarize(values, current, label='') -> dict:
    """一次算完: 当前值/分位/分档/最小/中位/最大/样本数"""
    vs = _valid(values)
    pct = percentile(vs, current)
    out = {
        'label': label, 'current': current, 'percentile': None if pct != pct else round(pct, 1),
        'band': band(pct), 'samples': len(vs),
    }
    if vs:
        s = sorted(vs)
        mid = len(s) // 2
        median = s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2
        out.update({'min': round(s[0], 4), 'median': round(median, 4),
                    'max': round(s[-1], 4)})
    else:
        out.update({'min': None, 'median': None, 'max': None})
    return out


def summarize_series(items, years=None) -> dict:
    """历史序列 → {pe: 摘要, pb: 摘要, 最新一行}"""
    rows = [it for it in (items or []) if isinstance(it, dict)]
    rows.sort(key=lambda r: r.get('date') or '')
    latest = rows[-1] if rows else {}
    pe = summarize([r.get('pe') for r in rows], latest.get('pe'), 'PE(TTM)')
    pb = summarize([r.get('pb') for r in rows], latest.get('pb'), 'PB(MRQ)')
    return {
        'pe': pe, 'pb': pb, 'latest': latest,
        'count': len(rows),
        'range': [rows[0].get('date'), rows[-1].get('date')] if rows else [None, None],
        'years': years,
    }

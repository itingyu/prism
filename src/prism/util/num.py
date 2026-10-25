"""数值转换与单位格式化 —— 全仓唯一的实现

原先同一件事散在 10 个文件里各写一遍 try/except, 行为还不完全一致:
    to_float   安全转 float  —— 8 处 (失败给 None 的 6 处、给 -1e9 的 1 处、
                                 给 0.0 的 1 处), 还有带除数的变体
    fmt_vol    成交量折亿/万 —— 2 处逐字相同
    千分位/定小数 格式化     —— 2 处, 语义不同但实现雷同

现在都收在这里, 各层按需 import。这个模块是叶子 (不 import 仓内任何东西),
所以 bridge / engine / command / render 都能用, 不会成环。

放在 util/ 而不是 core/ 是有意的: core/ 是版本/配置/stdin 这类全局设施,
往里塞业务无关的小函数会让它变成杂物间。
"""


def to_float(v, default=None):
    """安全转 float; 转不了返回 default (默认 None)

    数据源返回的列里混着 None / '' / '1,234' / '12%' / numpy 标量,
    每个调用点自己 try/except 早就写腻了, 而且默认值各不相同
    (None / -1e9 / 0.0 各有各的用处, -1e9 是"取不到"时代的哨兵值)。
    """
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def fmt_vol(v):
    """成交量/成交额折单位: 亿 / 万 / 原值

    单位折算的口径必须全仓一致 —— 同一只票在 quote 里写 '1.23亿'、
    在 lhb 里写 '12300万', 用户没法比。
    """
    f = to_float(v)
    if f is None:
        return str(v)
    for unit, div in (('亿', 1e8), ('万', 1e4)):
        if abs(f) >= div:
            return f'{f / div:.2f}{unit}'
    return f'{f:.0f}'


def fmt_thousand(v, nd=2):
    """千分位定点: 1,234.56 (用于坐标轴/价格标签这类要对齐的数字)"""
    f = to_float(v)
    if f is None:
        return str(v)
    return f'{f:,.{nd}f}'


def fmt_fixed(v, nd=2):
    """定点小数; 取不到值时给占位符 '—' (表格里不留空洞)"""
    try:
        return f'{float(v):.{nd}f}'
    except (TypeError, ValueError):
        return '—' if v is None else str(v)


def sort_rows(rows, key, desc=True):
    """按数值字段排序, 取不到值/null 的行一律排最后

    直接 sorted(key=lambda r: to_float(r.get(key))) 在数据里有 None 时会抛
    TypeError: '<' not supported between instances of 'NoneType' and 'float'
    —— 上游缺值不是偶发, 是常态 (停牌、未披露、字段变更)。
    这里把缺值行单独摘出来贴到末尾, 让"排最后"成为确定行为。
    """
    present, missing = [], []
    for r in rows:
        v = to_float(r.get(key)) if isinstance(r, dict) else None
        if v is None:
            missing.append(r)
        else:
            present.append((v, r))
    present.sort(key=lambda x: x[0], reverse=desc)
    return [r for _, r in present] + missing

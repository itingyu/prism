"""数据源层方法点名调用 (`<子命令> --source <方法名>`)

分类表里 161 个数据源方法都有归口的子命令, 每个都能在功能命令上点名调用
(没有通用入口命令, 清单见 `prism lookup --by site`):

    prism quote  --source tencent_batch 600519,000001
    prism holders --source xueqiu_top_holders 600519
    prism flow   --source em_zt_pool --arg date=20260106

参数按方法签名自动适配: 代码位 (code/symbol/codes/symbols/stock/stock_list)
按该方法自己的默认值推断需要哪种代码形态 (600519 / sh600519 / SH600519 /
600519.SH), 条数位 (num/page_size/size/count) 接命令的 -n, 日期位接 --date,
其余参数一律走 --arg k=v。签名里没有的参数不静默吞掉 (交给 rawapi 报错)。
"""

import inspect
import re

from prism.stock.bridge import rawapi

# 代码类参数名 -> 单只/多只
CODE_ONE = ('code', 'symbol', 'stock', 'stock_code', 'secid')
CODE_MANY = ('codes', 'symbols', 'stock_list')
CODE_PARAMS = CODE_ONE + CODE_MANY

DATE_PARAMS = ('date', 'trade_date', 'day', 'start_date', 'end_date',
               'beg', 'se_date')
COUNT_PARAMS = ('num', 'page_size', 'size', 'count', 'lmt', 'rows', 'datalen')

# 没有默认值可参考时, 按方法前缀猜代码形态
_PREFIX_FORM = (
    ('xueqiu_', 'xq'),
    ('sina_', 'sina'),
    ('tencent_', 'sina'),
    ('gtimg_', 'sina'),
    ('em_dmsk_', 'secu'),
    ('em_f10_lico', 'secu'),
    ('em_valuation_history', 'secu'),
)


def categories():
    return rawapi.categories()


def methods_for(command):
    """某子命令可点名的方法 (分类表里 cli 含该命令的类)"""
    out = []
    for code, v in categories().items():
        if code == 'uncategorized':
            continue
        if command in (v.get('cli') or []):
            out += list(v.get('primary') or []) + list(v.get('fallback') or [])
    return out


def commands_with_sources():
    """有数据源方法可点名的子命令 -> 方法列表"""
    out = {}
    for code, v in categories().items():
        if code == 'uncategorized':
            continue
        for cmd in (v.get('cli') or []):
            out.setdefault(cmd, []).extend(
                list(v.get('primary') or []) + list(v.get('fallback') or []))
    return out


def all_methods():
    """方法 -> 功能类 code"""
    out = {}
    for code, v in categories().items():
        if code == 'uncategorized':
            continue
        for m in (v.get('primary') or []) + (v.get('fallback') or []):
            out.setdefault(m, code)
    return out


# ---- 代码形态 ---------------------------------------------------------------
# 形态从方法自己的默认值推断: em_f10_income(code='600519.SH') 就该传 600519.SH,
# gtimg_hq(symbols='sh600519,...') 就该传 sh600519。比按方法名前缀硬猜准。

_SECU = re.compile(r'^\d{6}\.[A-Z]{2}$')
_SINA = re.compile(r'^(sh|sz|bj|hk)\d{4,6}$')
_XQ = re.compile(r'^(SH|SZ|BJ|HK)\d{4,6}$')
_BARE = re.compile(r'^\d{4,6}$')


def _shape_of(sample):
    """从默认值样本看代码形态; 认不出返回 None"""
    if sample is None:
        return None
    s = str(sample).strip()
    if not s or s.lower() in ('none', 'null'):
        return None
    if ',' in s:
        s = s.split(',')[0].strip()
    if _SECU.match(s):
        return 'secu'
    if _XQ.match(s):
        return 'xq'
    if _SINA.match(s):
        return 'sina'
    if _BARE.match(s):
        return 'bare'
    return None


def _shape_from_prefix(method):
    for pre, shape in _PREFIX_FORM:
        if method.startswith(pre):
            return shape
    return 'bare'


def _norm_market(code):
    """(市场, 纯代码) —— 交易所交给数据源层自己的 _symbol.parse"""
    from prism.stock.bridge.sources import _symbol
    s = str(code).strip()
    p = _symbol.parse(s)
    if p:
        return p[0].lower(), p[1]
    m = re.match(r'^(hk|HK)(\d{4,5})$', s)
    if m:
        return 'hk', m.group(2).zfill(5)
    if re.match(r'^\d{4,5}$', s):
        return 'hk', s.zfill(5)
    if re.match(r'^[A-Za-z][A-Za-z.\-]{0,9}$', s):
        return 'us', s.upper()
    return 'cn', s


def _fmt_code(code, shape):
    """把用户输入的代码转成目标形态"""
    mk, c = _norm_market(code)
    if mk == 'hk':
        if shape == 'xq':
            return f'HK{c}'
        if shape in ('sina', 'bare', 'secu'):
            return c if shape != 'sina' else f'hk{c}'
        return c
    if mk == 'us':
        if shape == 'secu':
            return c
        if shape == 'sina':
            return f'us{c}'
        return c
    # A 股
    if shape == 'secu':
        return f'{c}.{mk.upper()}' if mk in ('sh', 'sz', 'bj') else c
    if shape == 'xq':
        return f'{mk.upper()}{c}'
    if shape == 'sina':
        return f'{mk}{c}'
    return c


def _client_method(method):
    from prism.stock.bridge.sources import APIClient
    fn = getattr(APIClient(), method, None)
    if fn is None or method.startswith('_') or not callable(fn):
        raise ValueError(f'未知数据源方法: {method} '
                         f'(prism lookup --by site 看清单)')
    return fn


def build_kwargs(method, codes=None, date=None, limit=None, extra=None):
    """按方法签名组装参数 —— 纯函数, 不联网, 可直接单测"""
    fn = _client_method(method)
    sig = inspect.signature(fn)
    kwargs = dict(extra or {})
    codes = [str(c) for c in (codes or []) if str(c).strip()]
    missing = []
    for name, p in sig.parameters.items():
        if name in kwargs or p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD):
            continue
        has_default = p.default is not inspect.Parameter.empty
        shape = _shape_of(p.default) or _shape_from_prefix(method)
        if name in CODE_PARAMS:
            if not codes:
                if not has_default:
                    missing.append(name)
                continue
            vals = [_fmt_code(c, shape) for c in codes]
            if name in CODE_MANY:
                # 默认值是 list 或压根没默认值 -> 传 list; 默认值是逗号串 -> 传串
                as_list = isinstance(p.default, (list, tuple)) or has_default is False
                kwargs[name] = vals if as_list else ','.join(vals)
            else:
                kwargs[name] = vals[0]
        elif name in DATE_PARAMS:
            if date:
                kwargs[name] = date
            elif not has_default:
                missing.append(name)
        elif name in COUNT_PARAMS:
            if limit:
                kwargs[name] = int(limit)
        elif not has_default:
            missing.append(name)
    if missing:
        raise ValueError(
            f'{method} 还缺参数: {", ".join(missing)} —— 用 --arg ' +
            ', '.join(f'{m}=值' for m in missing))
    return kwargs


def call(method, codes=None, date=None, limit=None, extra=None):
    """点名调一个数据源方法, 返回原始载荷 ({ok, data, ...})"""
    return rawapi.call(method, build_kwargs(method, codes, date, limit, extra))


def describe(command):
    """某子命令下可点名的方法清单 (用于 --source 报错/展示)"""
    from prism.stock.bridge.sources import APIClient
    c = APIClient()
    rows = []
    for m in methods_for(command):
        fn = getattr(c, m, None)
        if fn is None:
            continue
        params = [n for n in inspect.signature(fn).parameters]
        rows.append({'方法': m, '参数': ','.join(params) or '-'})
    return rows

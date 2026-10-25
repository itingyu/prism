"""prism 分发参数 (取代 60+ 字段的 dict + SimpleNamespace)

## 为什么是 dataclass

每条命令的实参最终塞进一个命名空间交给动作。原来是 `_DEFAULTS` 字典 +
`SimpleNamespace`, 字段拼错要等运行到那一行才 `AttributeError`, 而且
"有哪些字段、什么类型"只存在于读代码的经验里。改成 dataclass 后:

- 字段与默认值是一张带类型的声明, `fields()` 可直接查;
- 写入未经声明的名字当场报错 (`_DYNAMIC` 列出合法的动态字段);
- 列表/字典默认值走 `default_factory`, 不会在多次分发间串味。

## 为什么还有 _DYNAMIC

有些字段由命令签名或动作自己挂上去 (如 `family`/`stats`/`yyb`),
它们不是全局默认值的一部分。这里显式列出来, 是为了让"合法写入"
有据可查: 不在这两张表里的写入一律报错, 而不是悄悄成为一个死字段。
"""
from dataclasses import dataclass, field, fields


@dataclass
class Args:
    """一次命令分发的全部实参"""
    action: str = ''
    codes: list[str] = field(default_factory=list)
    date: str | None = None
    only_buy: bool = False
    scope: str = 'industry'
    pool: str = 'short'
    min_score: int = 60
    limit: int = 10
    n: int = 3
    tool: str | None = None
    params: str | None = None
    keyword: str = ''
    timeout: float = 60.0
    method: str | None = None
    by: str = 'source'
    url: str = ''
    referer: str = ''
    encoding: str = ''
    pick: str = ''
    raw: bool = False
    form: dict[str, str] = field(default_factory=dict)
    http_timeout: float = 20.0
    post: bool = False
    method_only: bool = False
    lib: str = 'akshare'
    full: bool = False
    texts: list[str] = field(default_factory=list)
    excel: str | None = None
    kind: str | None = None
    name: str | None = None
    thesis: str | None = None
    drivers: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    catalysts: list[str] = field(default_factory=list)
    mid: list[str] = field(default_factory=list)
    bars: int = 120
    period: str = 'day'
    chart: bool = False
    chart_out: str | None = None
    ma: str | None = None
    start: str | None = None
    end: str | None = None
    days: int = 30
    no_auction: bool = False
    png: bool = False
    macd: bool = False
    after_hours: bool = False
    bar_seconds: int = 60
    auto_y: bool = False
    combo: bool = False
    ma_daily: str = '5,10,20,60'
    ascii_art: bool = False
    full_axis: bool = False

    def __setattr__(self, name, value):
        if name not in _DECLARED and name not in _DYNAMIC:
            raise AttributeError(
                f"Args 没有字段 {name!r}; 新字段要么进 Args, 要么进 _DYNAMIC")
        object.__setattr__(self, name, value)


_DECLARED = frozenset(f.name for f in fields(Args))

# 由命令签名 / 显式分发 / 动作自赋产生的字段 (不是全局默认值)
_DYNAMIC = frozenset({
    'exchange',
    '_data_domain',
    'all_cmds',
    'arg',
    'asc',
    'ascii_h',
    'ascii_style',
    'ascii_w',
    'call',
    'catalyst',
    'chg',
    'code',
    'contracts',
    'cost',
    'detail',
    'domain',
    'domains',
    'driver',
    'family',
    'file',
    'fmt',
    'format',
    'free',
    'health',
    'history',
    'hold',
    'index',
    'indicator',
    'inventory',
    'kind_pos',
    'list_domains',
    'list_kinds',
    'list_what',
    'market',
    'minute',
    'note',
    'of',
    'only',
    'order',
    'output',
    'point',
    'pos_action',
    'profile',
    'progress',
    'quarters',
    'realtime',
    'refresh',
    'research',
    'risk',
    'shares',
    'sort',
    'source',
    'span',
    'spot',
    'stats',
    'stop',
    'summary',
    'symbol',
    'target',
    'text',
    'type_',
    'year',
    'years',
    'yyb',
})


def build(**kw) -> Args:
    """构造一份干净的实参; 非 None 的 kw 覆盖默认值"""
    a = Args()
    for k, v in kw.items():
        if v is None:
            continue
        setattr(a, k, list(v) if isinstance(v, list) else v)
    return a

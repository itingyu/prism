"""CLI 动作层: 每个动作一个子命令, 直接挂在 prism 顶层

历史: 原来所有 60+ 动作共用一个函数签名, `prism --help` 要列 55 个选项,
而每个动作实际只用 0-3 个。现在按动作拆成子命令, 冷门动作统一走

本仓只有股票一件事, 所以不再套一层 `prism` —— 动作本身就是顶层命令:
`prism quote 600519` / `prism pool` / `prism position list`。
这里只负责"把命令登记出去", 路由与帮助由 cli/app.py 收口。
"""
import functools
import inspect
import sys

import typer

from prism.cli.runtime import _CTX, _entry_fn, _run, Fmt, Output
from prism.stock.command._args import build as _build_args
from prism.cli.spec import FMT, OUT, Arg, Cmd, Opt, build, family_opts

# 命令注册表: 名字 -> 处理函数。cli/app.py 统一挂到顶层 app 上。
COMMANDS = {}
# 分类表(api_categories.json)挂了子命令的功能类 -> 这些命令才有 --source
from prism.stock.bridge.source_pick import commands_with_sources as _cws
_SOURCE_CMDS = _cws()
# 注册时的额外 typer 参数 (如 context_settings)
CMD_OPTS = {}


def catalog(panels=None):
    """按面板生成命令目录 (名字 + 一句话说明)

    目录从 COMMANDS 注册表生成, 不手写 —— 手写的目录在命令改名/删除后
    会一直躺在帮助里, 指向不存在的命令 (本仓就发生过: USAGE 里长期写着
    已删除的 `data call` / `sources`)。
    """
    panels = panels or {}
    lines = []
    assigned = set()
    for panel, names in panels.items():
        rows = []
        for n in names:
            fn = COMMANDS.get(n)
            if fn is None:
                continue
            assigned.add(n)
            doc = (fn.__doc__ or '').strip().splitlines()
            summary = doc[0] if doc else ''
            rows.append(f'  {n:20} {summary}')
        if rows:
            lines.append(f'{panel} ({len(rows)})')
            lines.extend(rows)
            lines.append('')
    rest = sorted(n for n in COMMANDS if n not in assigned)
    if rest:
        lines.append(f'其他 ({len(rest)})')
        for n in rest:
            doc = (COMMANDS[n].__doc__ or '').strip().splitlines()
            lines.append(f'  {n:20} {doc[0] if doc else ""}')
        lines.append('')
    return '\n'.join(lines)


def cmd(name, **opts):
    """把函数登记成顶层子命令 (装饰器)

    分类表里挂了子命令的功能类, 额外注入 `--source <方法名>` / `--arg` /
    `-n`: 让"点哪个数据源"有正经入口, 不需要通用入口命令。
    """
    def deco(fn):
        if name in _SOURCE_CMDS:
            fn = _with_source(name, fn)

        @functools.wraps(fn)
        def stash(*a, **kw):
            """记住这次命令实际收到的参数

            通用入口 (--kind / --source) 由包装器转发参数, 而各命令的
            选项名五花八门 (days/start/end/date...), 包装器不可能挨个转发。
            这里在最外层把用户真正给的参数存下来, _dispatch 合并进 args ——
            否则 `prism lhb --kind xxx --days 30` 的 --days 会在转发时丢掉,
            取数窗口退化成 1 天, 上游返回空 (实测报 'NoneType' 天书错误)。
            """
            _CTX['cmd_kwargs'] = {k: v for k, v in kw.items() if v is not None}
            return fn(*a, **kw)

        COMMANDS[name] = stash
        if opts:
            CMD_OPTS[name] = opts
        return stash
    return deco



def declare(name, action, help, args=(), opts=()):
    """登记一条声明式命令: 一个调用写完

    等价于 COMMANDS[name] = cmd(name)(build(Cmd(...))), 但不用套三层括号。
    选项以数据形式给出, 因此能被测试和内省工具读取 (见 cli/spec.py)。
    """
    COMMANDS[name] = cmd(name)(build(Cmd(name, action, help, args=args,
                                         opts=opts)))


def _explicit(sig, kw, *names):
    """取用户真正显式给的值: 与签名默认值相同就当没给"""
    for n in names:
        if n not in kw:
            continue
        p = sig.parameters.get(n)
        d = getattr(p.default, 'default', None) if p else None
        if kw[n] is not None and kw[n] != d:
            return kw[n]
    return None

def _subject_of(kw):
    """从命令函数的原始 kwargs 里取"主语"(位置参数里的股票代码)

    与 stock/command/_common.py 的 subject() 同一套候选名 —— 两个注入器
    (--kind 与 --source) 各猜各的, 是"位置代码传不进去"幽灵 bug 的根源。
    """
    for name in ('codes', 'code', 'symbol'):
        v = kw.get(name)
        if not v:
            continue
        if isinstance(v, (list, tuple)):
            vals = [str(x) for x in v if x]
            if vals:
                return vals
            continue
        return [str(v)]
    return []


def _with_kind(name):
    """给没有 --kind 的命令补扩展口径入口

    原本只有 33 个族支持 `--kind`, 其余 akshare 接口只能走 data call。
    补上 --kind/--list/--arg 后, 每个接口都能从所属命令点名调用。
    """
    def deco(fn):
        sig = inspect.signature(fn)
        have = set(sig.parameters)
        params = list(sig.parameters.values())
        if 'kind' not in have:
            params.append(inspect.Parameter(
                'kind', inspect.Parameter.KEYWORD_ONLY, annotation=str,
                default=typer.Option(None, '--kind', metavar='口径',
                                     help='扩展口径 / akshare 接口名, 见 --list')))
        if 'arg' not in have:
            params.append(inspect.Parameter(
                'arg', inspect.Parameter.KEYWORD_ONLY, annotation=list[str],
                default=typer.Option(None, '--arg', metavar='K=V', help='额外参数 K=V, 可重复')))
        if 'list_kinds' not in have:
            params.append(inspect.Parameter(
                'list_kinds', inspect.Parameter.KEYWORD_ONLY, annotation=bool,
                default=typer.Option(False, '--list', help='列本命令可用的口径')))

        @functools.wraps(fn)
        def inner(**kw):
            kind = kw.pop('kind', None)
            arg = kw.pop('arg', None)
            show = kw.pop('list_kinds', False)
            if show:
                return _dispatch('fam-list', kw.get('fmt'), kw.get('output'), family=name)
            if not kind:
                return fn(**kw)
            codes = _subject_of(kw)
            return _dispatch('fam', kw.get('fmt'), kw.get('output'), family=name,
                             kind=kind, codes=[str(c) for c in codes],
                             params=list(arg or []))
        inner.__signature__ = sig.replace(parameters=params)
        return inner
    return deco


def _with_source(name, fn):
    """给子命令补 --source / --arg / -n 三个选项

    --source 是"点名数据源方法"; 之所以顺手补 --arg 与 -n, 是为了让
    通用入口的能力在功能子命令上原样等价 (方法参数、条数)。
    """
    sig = inspect.signature(fn)
    params = list(sig.parameters.values())
    have = set(sig.parameters)
    extra = []

    def add(pname, ann, opt, kw):
        params.append(inspect.Parameter(pname, inspect.Parameter.KEYWORD_ONLY,
                                        default=opt, annotation=ann))
        extra.append((pname, kw))

    if 'source' not in have:
        add('source', str, typer.Option(None, '--source', metavar='方法名',
                                        help='点名数据源方法, 清单见 prism lookup --by site'), 'source')
    if 'arg' not in have:
        add('arg', list[str], typer.Option(None, '--arg', metavar='K=V',
                                             help='额外参数 K=V, 可重复'), 'arg')
    if not ({'limit', 'bars', 'n'} & have):
        add('limit', int, typer.Option(10, '-n', '--limit', help='条数'), 'limit')

    @functools.wraps(fn)
    def inner(**kw):
        src = kw.get('source')
        if not src:
            for _n, _ in extra:
                kw.pop(_n, None)
            return fn(**kw)
        codes = _subject_of(kw)
        return _dispatch('source', kw.get('fmt'), kw.get('output'),
                         method=src, source=src, family=name,
                         codes=[str(c) for c in codes],
                         date=_explicit(sig, kw, 'date'),
                         limit=_explicit(sig, kw, 'limit', 'bars', 'n'),
                         params=list(kw.get('arg') or []))
    inner.__signature__ = sig.replace(parameters=params)
    return inner

def _norm_date_arg(v):
    """--date 统一: 2026-09-30 与 20260930 等价; last 交给各动作处理"""
    if isinstance(v, str) and len(v) == 10 and v[4] == '-' and v[7] == '-':
        if all(c.isdigit() for c in v.replace('-', '')):
            return v.replace('-', '')
    return v


def _dispatch(action, fmt, output, **kw):
    """把子命令参数塞进 _CTX 的 args 后交给 do_stock 分发

    -f/-o 写在子命令前面 (prism -f json quote ...) 时由顶层 callback
    存进 _CTX, 这里兜底取 —— 两处都认。
    """
    fmt = fmt or _CTX.get('stock_fmt')
    output = output or _CTX.get('stock_output')
    # 每次分发用**干净**的 Args: 共用同一份实参会让上一条命令的残留值
    # (codes/kind/params) 漏到下一条, 表现为"位置代码传不进去"这类幽灵 bug。
    # 先并入本次命令真正收到的参数 (非 None 才算), 再让显式分发的值覆盖它。
    a = _build_args(**_CTX.get('cmd_kwargs', {}))
    _CTX['args'] = a
    a.action = action
    for k, v in kw.items():
        setattr(a, k, v)
    a.date = _norm_date_arg(getattr(a, 'date', None))
    return _run(None, _entry_fn('stock'), fmt, output, False, False)



def _fam_route(family, kind, list_kinds, fmt, output, codes=None,
               params=None, limit=None):
    """扩展口径路由: --list 列口径, --kind 调口径; 两者都没给返回 None"""
    if list_kinds:
        return _dispatch('fam-list', fmt, output, family=family)
    if kind:
        return _dispatch('fam', fmt, output, family=family, kind=kind,
                         codes=list(codes or []), params=list(params or []),
                         limit=limit)
    return None


_HELP = {
    'lookup': """用法: prism lookup [关键词] [选项]

查 (四层一次搜, 每条给下一步命令):
  prism lookup holders            命令
  prism lookup 十大股东            口径 (--kind)
  prism lookup 北向               源方法 (--source)
  prism lookup 涨停池             接口
  prism lookup RPT_BOND_CB_LIST   东财数据中心报表

展开视角:
  --family holders       某命令全部口径 (接口真名/状态/主备)
  --by site              163 个源方法按站点分组 (带签名/docstring)
  --list-domains        15 个数据域导航
  --domain 股东           某域全部接口明细
  --only commands|kinds|sources|api|reports   只看一层

直接取数:
  --call stock_zt_pool_em --arg date=20261024
  --url https://qt.gtimg.cn/q=sh600519 [--post]
  --health

-n 每类显示几条 (默认 10)
""",
}


def _echo_help(name):
    """无参时打印本命令的帮助 (而不是把全量清单灌一屏)"""
    typer.echo(_HELP[name].rstrip())


def _run_lookup(keyword, only, family, by, list_domains, domain, call, url, health, arg, post, limit, fmt, output):
    if not any([keyword, family, by, list_domains, domain, call, url, health]):
        return _echo_help('lookup')
    return _dispatch('lookup', fmt, output, codes=[keyword] if keyword else [],
                     only=only, family=family, by=by, domains=list_domains,
                     domain=domain, call=call, url=url, health=health,
                     params=arg, post=post, limit=limit)


declare('lookup', _run_lookup, '查命令/口径/源方法/接口, 或直接按名调接口 (--call / --url / --health)',
    args=(
        Arg('keyword', '关键词: 命令/口径/方法/接口/中文说法', required=False),
    ),
    opts=(
        Opt('--only', default=None, help='只看一层: commands|kinds|sources|api'),
        Opt('--family', default=None, help='看某个命令的全部口径 (含接口真名/状态)'),
        Opt('--by', default=None, help='源方法分组: site 按站点 / function 按功能'),
        Opt('--list-domains', type=bool, default=False, help='列出全部 akshare 数据域'),
        Opt('--domain', default=None, help='某个数据域的接口明细, 如 股东'),
        Opt('--call', default=None, help='按名调接口, 如 stock_zt_pool_em'),
        Opt('--url', default=None, help='裸 HTTP 直调'),
        Opt('--health', type=bool, default=False, help='数据面体检'),
        Opt('--arg', default=[], multiple=True, metavar='K=V', help='额外参数 K=V, 可重复'),
        Opt('--post', type=bool, default=False, help='--url 时用 POST'),
        Opt('--limit', type=int, default=10, short=('-n',), help='每类/每站点显示几条'),
        FMT,
        OUT,
    ))


def _run_quote(codes, kind, list_kinds, arg, fmt, output):
    if kind or list_kinds:
        return _fam_route('quote', kind, list_kinds, fmt, output,
                          list(codes or []), list(arg or []), limit=None)
    return _dispatch('quote', fmt, output, codes=list(codes or []))


declare('quote', _run_quote, '实时行情',
    args=(Arg('codes', '股票代码, 逗号分隔多只; 也支持 上证指数/创业板指 等别名',
              multiple=True, required=False),),
    opts=family_opts('quote') + (FMT, OUT))


def _run_pool(date, only_buy, type_, fmt, output):
    return _dispatch('pool', fmt, output, date=date, only_buy=only_buy,
                     type_=type_)


declare('pool', _run_pool,
    '涨停池 / 强势股池 / 炸板池 / 昨日涨停 / 跌停池',
    opts=(
        Opt('--date', help='数据日 YYYYMMDD 或 last (上一交易日)'),
        Opt('--only-buy', type=bool, default=False, help='只留可买板块'),
        Opt('--type', dest='type_', default='zt',
            help='池: zt(涨停)/strong(强势)/zb(炸板)/prev(昨日涨停)/dt(跌停)/sub(次新)'),
        FMT, OUT,
    ))


def _run_check(codes, fmt, output):
    return _dispatch('check', fmt, output, codes=list(codes or []))


declare('check', _run_check, '可买性核查 (板块归属 + ST/退市风险)',
    args=(
        Arg('codes', '股票代码, 逗号分隔多只', multiple=True),
    ),
    opts=(
        FMT,
        OUT,
    ))


def _run_calendar(date, days, fmt, output):
    return _dispatch('calendar', fmt, output, date=date, n=days)


declare('calendar', _run_calendar, '交易日历',
    opts=(
        Opt('--date', default=None, help='起算日 YYYYMMDD 或 last (上一交易日)'),
        Opt('--days', type=int, default=3, help='往后几个交易日'),
        FMT,
        OUT,
    ))


def _run_flow(scope, fmt, output):
    return _dispatch('flow', fmt, output, scope=scope)


declare('flow', _run_flow, '资金流榜单',
    opts=(
        Opt('--scope', default='industry', help='口径: industry(行业)/individual(个股)/north(北向)'),
        FMT,
        OUT,
    ))


def _run_news(code, limit, kind, list_kinds, arg, fmt, output):
    if kind or list_kinds:
        return _fam_route('news', kind, list_kinds, fmt, output,
                           [code] if code else [], list(arg or []), limit=limit)
    if not code:
        raise typer.BadParameter('需要股票代码 (或用 --kind / --list 看扩展口径)')
    return _dispatch('news', fmt, output, codes=[code], limit=limit)


declare('news', _run_news, '个股新闻',
    args=(
        Arg('code', '股票代码', required=False),
    ),
    opts=(
        *family_opts('news'),
        Opt('--limit', type=int, default=10, short=('-n',), help='条数'),
        FMT,
        OUT,
    ))


def _run_announcement(code, limit, days, keyword, type_, fmt, output):
    return _dispatch('announcement', fmt, output, codes=[code], limit=limit,
                     days=days, keyword=keyword, type_=type_)


declare('announcement', _run_announcement, '公告列表 (可按类型/时间窗/关键词过滤)',
    args=(
        Arg('code', '股票代码'),
    ),
    opts=(
        Opt('--limit', type=int, default=10, short=('-n',), help='条数'),
        Opt('--days', type=int, default=0, help='只看最近 N 天 (0=不限)'),
        Opt('--keyword', default='', help='标题包含关键词'),
        Opt('--type', default='', dest='type_', help='按类型过滤: 增持/减持/回购/业绩预告/问询函/分红/停复牌/重大合同/股权激励/诉讼/解禁/担保/资产重组'),
        FMT,
        OUT,
    ))


def _run_financials(code, kind, list_kinds, arg, fmt, output):
    if kind or list_kinds:
        return _fam_route('financials', kind, list_kinds, fmt, output,
                           [code] if code else [], list(arg or []), limit=None)
    if not code:
        raise typer.BadParameter('需要股票代码 (或用 --kind / --list 看扩展口径)')
    return _dispatch('financials', fmt, output, codes=[code])


declare('financials', _run_financials, '核心财务指标',
    args=(
        Arg('code', '股票代码', required=False),
    ),
    opts=(
        *family_opts('financials'),
        FMT,
        OUT,
    ))


# ── akshare 数据域: 原生源拿不到的事件/宏观数据 ──────────────────
def _run_lhb(codes, days, start, end, yyb, stats, span, limit, kind, list_kinds, arg,
    fmt, output):
    if kind or list_kinds:
        return _fam_route('lhb', kind, list_kinds, fmt, output,
                           list(codes or []), list(arg or []), limit=limit)
    return _dispatch('lhb', fmt, output, codes=list(codes or []), days=days,
                     start=start, end=end, yyb=yyb, stats=stats, span=span,
                     limit=limit)


declare('lhb', _run_lhb, '龙虎榜 (净买额 / 上榜原因 / 上榜后表现; --yyb 看席位)',
    args=(
        Arg('codes', '只看某只票 (可省)', multiple=True, required=False),
    ),
    opts=(
        *family_opts('lhb'),
        Opt('--days', type=int, default=7, help='回看自然日'),
        Opt('--start', help='起始日 YYYY-MM-DD'),
        Opt('--end', help='截止日 YYYY-MM-DD'),
        Opt('--yyb', type=bool, default=False, help='改看活跃营业部 (游资席位)'),
        Opt('--stats', help='统计口径: stock(个股)/jg(机构席位)/yyb(营业部)/trader(游资)'),
        Opt('--span', default='近一月', help='统计区间 近一月/近三月/近六月/近一年'),
        Opt('--limit', type=int, default=10, short=('-n',), help='条数'),
        FMT,
        OUT,
    ))

def _run_block_trade(codes, days, start, end, limit, kind, list_kinds, arg, fmt,
    output):
    if kind or list_kinds:
        return _fam_route('block-trade', kind, list_kinds, fmt, output,
                           list(codes or []), list(arg or []), limit=limit)
    return _dispatch('dzjy', fmt, output, codes=list(codes or []), days=days,
                     start=start, end=end, limit=limit)


declare('block-trade', _run_block_trade, '大宗交易 (成交价 / 折溢率 / 买卖营业部)',
    args=(
        Arg('codes', '只看某只票 (可省)', multiple=True, required=False),
    ),
    opts=(
        *family_opts('block-trade'),
        Opt('--days', type=int, default=7, help='回看自然日'),
        Opt('--start', help='起始日'),
        Opt('--end', help='截止日'),
        Opt('--limit', type=int, default=10, short=('-n',), help='条数'),
        FMT,
        OUT,
    ))

def _run_unlock(codes, days, start, end, summary, limit, kind, list_kinds, arg, fmt,
    output):
    if kind or list_kinds:
        return _fam_route('unlock', kind, list_kinds, fmt, output,
                           list(codes or []), list(arg or []), limit=limit)
    return _dispatch('unlock', fmt, output, codes=list(codes or []), days=days,
                     start=start, end=end, summary=summary, limit=limit)


declare('unlock', _run_unlock, '限售解禁 (解禁市值 / 占流通比 / 解禁前后表现)',
    args=(
        Arg('codes', '只看某只票 (可省)', multiple=True, required=False),
    ),
    opts=(
        *family_opts('unlock'),
        Opt('--days', type=int, default=30, help='往后看几天'),
        Opt('--start', help='起始日'),
        Opt('--end', help='截止日'),
        Opt('--summary', type=bool, default=False, help='按日汇总 (供给压力日历)'),
        Opt('--limit', type=int, default=10, short=('-n',), help='条数'),
        FMT,
        OUT,
    ))

def _run_survey(codes, date, limit, fmt, output):
    return _dispatch('jgdy', fmt, output, codes=list(codes or []), date=date,
                     limit=limit)


declare('survey', _run_survey, '机构调研 (调研机构 / 类型 / 接待方式)',
    args=(
        Arg('codes', '只看某只票 (可省)', multiple=True, required=False),
    ),
    opts=(
        Opt('--date', default=None, help='调研日 (默认上一交易日)'),
        Opt('--limit', type=int, default=10, short=('-n',), help='条数'),
        FMT,
        OUT,
    ))

def _run_analyst_report(code, limit, fmt, output):
    return _dispatch('yanbao', fmt, output, codes=[code], limit=limit)


declare('analyst-report', _run_analyst_report, '个股研报 (评级 / 覆盖机构 / 未来三年 EPS·PE 预测)',
    args=(
        Arg('code', '股票代码'),
    ),
    opts=(
        Opt('--limit', type=int, default=10, short=('-n',), help='最多几篇'),
        FMT,
        OUT,
    ))

def _run_holder_count(code, limit, fmt, output):
    return _dispatch('gdhs', fmt, output, codes=[code], limit=limit)


declare('holder-count', _run_holder_count, '股东户数历史 (筹码集中度 / 户均持股)',
    args=(
        Arg('code', '股票代码'),
    ),
    opts=(
        Opt('--limit', type=int, default=10, short=('-n',), help='条数'),
        FMT,
        OUT,
    ))

def _run_macro(indicator, kind, list_kinds, arg, limit, fmt, output):
    if kind or list_kinds:
        return _fam_route('macro', kind or indicator, list_kinds, fmt, output,
                          [], list(arg or []), limit=limit)
    return _dispatch('macro', fmt, output, indicator=indicator, limit=limit)


declare('macro', _run_macro, '宏观指标 (CPI/PPI/PMI/LPR/M2/GDP/Shibor/社融/汇率/杠杆率 + 各国宏观)',
    args=(
        Arg('indicator', 'cpi/ppi/pmi/lpr/m2/gdp/shibor/shrzgm/rmb/cnbs/us_nfp/us_cpi',
        required=False, default='cpi'),
    ),
    opts=(
        Opt('--kind', help='扩展口径, 可用空格分词 (如 "australia cpi")'),
        Opt('--list', dest='list_kinds', type=bool, default=False, help='列出全部宏观口径 (含各国)'),
        Opt('--arg', multiple=True, metavar='K=V', help='额外参数 K=V, 可重复'),
        Opt('--limit', type=int, default=10, short=('-n',), help='条数'),
        FMT,
        OUT,
    ))

def _run_stock_connect(scope, days, fmt, output):
    return _dispatch('hsgt', fmt, output, days=days, scope=scope)


declare('stock-connect', _run_stock_connect, '陆股通资金 (当日快照 / 北向历史 / 南向历史)',
    opts=(
        Opt('--scope', default='summary', help='summary(当日快照)/north(北向历史, 止于 2024-08)/south(南向历史)'),
        Opt('--days', type=int, default=10, help='历史口径下最近几天'),
        FMT,
        OUT,
    ))

def _run_dupont(code, quarters, fmt, output):
    return _dispatch('dupont', fmt, output, codes=[code], n=quarters)


declare('dupont', _run_dupont, '杜邦拆解 (ROE = 净利率 × 周转 × 权益乘数, 逐季); 源 baostock',
    args=(
        Arg('code', '股票代码'),
    ),
    opts=(
        Opt('--quarters', type=int, default=8, help='回看几个季度'),
        FMT,
        OUT,
    ))

def _run_growth(code, quarters, fmt, output):
    return _dispatch('growth', fmt, output, codes=[code], n=quarters)


declare('growth', _run_growth, '成长能力 (营收/净利/净资产/EPS 同比, 逐季); 源 baostock',
    args=(
        Arg('code', '股票代码'),
    ),
    opts=(
        Opt('--quarters', type=int, default=8, help='回看几个季度'),
        FMT,
        OUT,
    ))

def _run_comment(sort, asc, limit, kind, list_kinds, arg, fmt, output):
    if kind or list_kinds:
        return _fam_route('comment', kind, list_kinds, fmt, output, [], list(arg or []), limit=limit)
    return _dispatch('comment', fmt, output, sort=sort, asc=asc, limit=limit)


declare('comment', _run_comment, '千股千评 (全市场综合得分 / 关注度 / 机构参与度 / 主力控盘)',
    opts=(
        *family_opts('comment'),
        Opt('--sort', default='综合得分', help='排序字段: 综合得分/关注指数/机构参与度/主力控盘'),
        Opt('--asc', type=bool, default=False, help='升序'),
        Opt('--limit', type=int, default=10, short=('-n',), help='条数'),
        FMT,
        OUT,
    ))

def _run_earnings_preview(codes, date, type_, limit, fmt, output):
    type_ = {'preview': 'yjyg', 'flash': 'yjkb'}.get(type_, type_)
    if type_ not in ('yjyg', 'yjkb'):
        raise typer.BadParameter('--type 只支持 preview(业绩预告)/flash(业绩快报)')
    return _dispatch('yjyg', fmt, output, codes=list(codes or []), date=date,
                     type_=type_, limit=limit)


declare('earnings-preview', _run_earnings_preview, '业绩预告 / 业绩快报 (按报告期)',
    args=(
        Arg('codes', '只看某只票 (可省)', multiple=True, required=False),
    ),
    opts=(
        Opt('--date', default=None, help='报告期 YYYYMMDD (默认最近已结束季度)'),
        Opt('--type', default='preview', dest='type_', help='preview(业绩预告)/flash(业绩快报)'),
        Opt('--limit', type=int, default=10, short=('-n',), help='条数'),
        FMT,
        OUT,
    ))

def _run_pledge(codes, date, profile, limit, kind, list_kinds, arg, fmt, output):
    if kind or list_kinds:
        return _fam_route('pledge', kind, list_kinds, fmt, output,
                           list(codes or []), list(arg or []), limit=limit)
    return _dispatch('pledge', fmt, output, codes=list(codes or []), date=date,
                     profile=profile, limit=limit)


declare('pledge', _run_pledge, '股权质押 (质押比例 / 爆仓风险); --profile 看全市场概况',
    args=(
        Arg('codes', '只看某只票 (可省)', multiple=True, required=False),
    ),
    opts=(
        *family_opts('pledge'),
        Opt('--date', help='统计日 YYYYMMDD (默认最新)'),
        Opt('--profile', type=bool, default=False, help='改看全市场质押概况'),
        Opt('--limit', type=int, default=10, short=('-n',), help='条数'),
        FMT,
        OUT,
    ))

def _run_rating(kind, limit, list_kinds, arg, fmt, output):
    if kind and kind not in ('最新投资评级', '上调', '下调', '首次', '综合', '目标价',
                             '机构关注', '行业关注'):
        return _fam_route('rating', kind, list_kinds, fmt, output, [], list(arg or []), limit=limit)
    if list_kinds:
        return _fam_route('rating', kind, list_kinds, fmt, output, limit=limit)
    return _dispatch('rating', fmt, output, kind=kind, limit=limit)


declare('rating', _run_rating, '机构评级 (全市场最新评级 / 上调 / 下调 / 首次覆盖)',
    opts=(
        Opt('--kind', default='最新投资评级', help='最新/上调/下调/首次/综合/目标价/机构关注/行业关注'),
        Opt('--limit', type=int, default=10, short=('-n',), help='条数'),
        Opt('--list', dest='list_kinds', type=bool, default=False, help='列出 rating 的扩展口径'),
        Opt('--arg', multiple=True, metavar='K=V', help='额外参数 K=V, 可重复'),
        FMT,
        OUT,
    ))

def _run_goodwill(codes, date, limit, kind, list_kinds, arg, fmt, output):
    if kind or list_kinds:
        return _fam_route('goodwill', kind, list_kinds, fmt, output,
                           list(codes or []), list(arg or []), limit=limit)
    return _dispatch('goodwill', fmt, output, codes=list(codes or []), date=date,
                     limit=limit)


declare('goodwill', _run_goodwill, '商誉规模 (减值风险面)',
    args=(
        Arg('codes', '只看某只票 (可省)', multiple=True, required=False),
    ),
    opts=(
        *family_opts('goodwill'),
        Opt('--date', help='报告期 YYYYMMDD'),
        Opt('--limit', type=int, default=10, short=('-n',), help='条数'),
        FMT,
        OUT,
    ))

def _run_breadth(history, limit, fmt, output):
    return _dispatch('breadth', fmt, output, history=history, limit=limit)


declare('breadth', _run_breadth, '市场宽度 (涨跌家数 / 涨跌停家数); --history 看 20/60/120 日新高新低家数',
    opts=(
        Opt('--history', type=bool, default=False, help='改看创新高/新低家数序列'),
        Opt('--limit', type=int, default=10, short=('-n',), help='条数'),
        FMT,
        OUT,
    ))

def _run_cb(codes, limit, fmt, output):
    return _dispatch('cb', fmt, output, codes=list(codes or []), limit=limit)


declare('cb', _run_cb, '可转债 (转股价值 / 溢价率 / 评级)',
    args=(
        Arg('codes', '正股代码 (可省)', multiple=True, required=False),
    ),
    opts=(
        Opt('--limit', type=int, default=10, short=('-n',), help='条数'),
        FMT,
        OUT,
    ))

def _run_etf(sort, asc, limit, fmt, output):
    return _dispatch('etf', fmt, output, sort=sort, asc=asc, limit=limit)


declare('etf', _run_etf, 'ETF 行情列表 (按涨跌幅/成交额排序)',
    opts=(
        Opt('--sort', default='涨跌幅', help='排序字段: 涨跌幅/成交额/最新价'),
        Opt('--asc', type=bool, default=False, help='升序'),
        Opt('--limit', type=int, default=10, short=('-n',), help='条数'),
        FMT,
        OUT,
    ))

position_app = typer.Typer(no_args_is_help=True,
                              rich_markup_mode=None, pretty_exceptions_enable=False,
                           help='持仓台账与盈亏 (本地 JSON, 默认 ~/.prism/positions.json)')


@position_app.command('list')
def _position_list(file: str = typer.Option(None, '--file', help='台账文件 (默认 ~/.prism/positions.json)'),
                   fmt: str = Fmt, output: str = Output):
    """列出持仓与浮动盈亏"""
    return _dispatch('position', fmt, output, pos_action='list', file=file)


@position_app.command('add')
def _position_add(code: str = typer.Argument(..., help='股票代码'),
                  shares: int = typer.Argument(..., help='股数'),
                  cost: float = typer.Argument(..., help='每股成本价'),
                  name: str = typer.Option('', '--name', help='名称 (可省, 取行情名)'),
                  note: str = typer.Option('', '--note', help='备注'),
                  stop: float = typer.Option(None, '--stop', help='止损价'),
                  target: float = typer.Option(None, '--target', help='止盈价'),
                  file: str = typer.Option(None, '--file', help='台账文件'),
                  fmt: str = Fmt, output: str = Output):
    """建仓/加仓 (同代码自动按加权成本合并)"""
    return _dispatch('position', fmt, output, pos_action='add', code=code,
                     shares=shares, cost=cost, name=name, note=note,
                     stop=stop, target=target, file=file)


@position_app.command('remove')
def _position_remove(code: str = typer.Argument(..., help='股票代码'),
                     shares: int = typer.Option(None, '--shares', help='减多少股; 不给=清仓'),
                     file: str = typer.Option(None, '--file', help='台账文件'),
                     fmt: str = Fmt, output: str = Output):
    """减仓/清仓"""
    return _dispatch('position', fmt, output, pos_action='remove', code=code,
                     shares=shares, file=file)


def _run_patterns(code, bars, fmt, output):
    return _dispatch('patterns', fmt, output, codes=[code], bars=bars)


declare('patterns', _run_patterns, '技术形态识别 (背离 / 跳空 / 平台突破 / 量价背离 / 金叉死叉)',
    args=(
        Arg('code', '股票代码'),
    ),
    opts=(
        Opt('--bars', type=int, default=120, help='回看多少根 K 线'),
        FMT,
        OUT,
    ))


def _run_valuation(code, years, market, limit, index, kind, list_kinds, arg, fmt,
    output):
    if kind or list_kinds:
        return _fam_route('valuation', kind, list_kinds, fmt, output,
                           [code] if code else [], list(arg or []), limit=limit)
    if index:
        return _dispatch('valuation', fmt, output, index=index, limit=limit)
    if not market and not code:
        raise typer.BadParameter('要么给股票代码, 要么加 --market / --index')
    return _dispatch('valuation', fmt, output, codes=[code] if code else [],
                     years=years, market=market, limit=limit)


declare('valuation', _run_valuation, '估值分位: 个股历史分位 / --market 全市场 / --index 中证指数 PE-BD',
    args=(
        Arg('code', '股票代码 (--market 时可省)', required=False),
    ),
    opts=(
        *family_opts('valuation'),
        Opt('--years', type=int, default=3, help='回看几年 (默认 3)'),
        Opt('--market', type=bool, default=False, help='改看全市场 PE/PB 分位历史'),
        Opt('--limit', type=int, default=10, short=('-n',), help='条数'),
        Opt('--index', help='改看中证指数估值, 如 000300'),
        FMT,
        OUT,
    ))


def _run_analyze(code, fmt, output):
    return _dispatch('analyze', fmt, output, codes=[code])


declare('analyze', _run_analyze, '单股深度 (技术面 + 评分 + 决策信号 + 画像)',
    args=(
        Arg('code', '股票代码'),
    ),
    opts=(
        FMT,
        OUT,
    ))


def _run_screen(pool, min_score, codes, fmt, output):
    return _dispatch('screen', fmt, output, pool=pool, min_score=min_score,
                     codes=[c.strip() for c in codes.split(',') if c.strip()])


declare('screen', _run_screen, '选股池',
    opts=(
        Opt('--pool', default='short', help='池: short(1-5日)/mid(3-6月)/long(6-18月)'),
        Opt('--min-score', type=int, default=60, help='技术面分门槛 (short 池)'),
        Opt('--codes', default='', help='候选代码, 逗号分隔 (mid/long 池必填; short 池自跑全市场)'),
        FMT,
        OUT,
    ))


def _run_risk(codes, fmt, output):
    return _dispatch('risk', fmt, output, codes=list(codes or []))


declare('risk', _run_risk, '风险核查 (重组/减持/立案/预亏)',
    args=(
        Arg('codes', '股票代码, 逗号分隔多只', multiple=True),
    ),
    opts=(
        FMT,
        OUT,
    ))


def _run_report(code, pool, point, fmt, output):
    codes = [code] if code else []
    return _dispatch('report', fmt, output, codes=codes, pool=pool,
                     texts=list(point or []))


declare('report', _run_report, '成稿研报 (markdown)',
    args=(
        Arg('code', '股票代码 (与 --pool 二选一)', required=False),
    ),
    opts=(
        Opt('--pool', default=None, help='短线池成稿: short'),
        Opt('--point', default=None, multiple=True, metavar='文本', help='补充论点, 可多次'),
        FMT,
        OUT,
    ))


def _run_excel(min_score, fmt, output):
    return _dispatch('excel', fmt, output, min_score=min_score)


declare('excel', _run_excel, '选股池导出 xlsx (需 openpyxl)',
    opts=(
        Opt('--min-score', type=int, default=60, help='技术面分门槛'),
        FMT,
        OUT,
    ))


def _run_sentiment(code, text, fmt, output):
    codes = [code] if code else []
    return _dispatch('sentiment', fmt, output, codes=codes, texts=list(text or []))


declare('sentiment', _run_sentiment, '消息面打分 -100~+100',
    args=(
        Arg('code', '股票代码 (不给则必须给 --text)', required=False),
    ),
    opts=(
        Opt('--text', default=None, multiple=True, metavar='文本', help='直接打分的文本, 可多次'),
        FMT,
        OUT,
    ))


def _run_boards(keyword, spot, limit, fmt, output):
    return _dispatch('boards', fmt, output, codes=[keyword] if keyword else [],
                     spot=spot, limit=limit)


declare('boards', _run_boards, '板块目录 (行业 + 概念); --spot 看板块即时涨跌',
    args=(
        Arg('keyword', '板块关键词 (不填列全部)', required=False, default=''),
    ),
    opts=(
        Opt('--spot', type=bool, default=False, help='改看新浪行业板块即时行情'),
        Opt('--limit', type=int, default=10, short=('-n',), help='条数'),
        FMT,
        OUT,
    ))


def _run_diagram(code, type_, name, thesis, driver, mid, catalyst, risk, fmt, output):
    return _dispatch('diagram', fmt, output, type_=type_, name=name, thesis=thesis,
                     drivers=list(driver or []), mid=list(mid or []),
                     catalysts=list(catalyst or []), risks=list(risk or []),
                     codes=[code] if code else [])


declare('diagram', _run_diagram, 'mermaid 图 (logic/tree/chain)',
    args=(
        Arg('code', '股票代码 (logic 用)', required=False),
    ),
    opts=(
        Opt('--type', default='tree', dest='type_', help='图类型: logic(投资逻辑)/tree(产业链树)/chain(链条)'),
        Opt('--name', default=None, help='标的/产业链名'),
        Opt('--thesis', default=None, help='投资逻辑主线 (logic)'),
        Opt('--driver', default=None, multiple=True, help='驱动因素 (logic) / 上游 (chain), 可多次'),
        Opt('--mid', default=None, multiple=True, help='产业链中游 (chain), 可多次'),
        Opt('--catalyst', default=None, multiple=True, help='催化剂 (logic) / 下游 (chain), 可多次'),
        Opt('--risk', default=None, multiple=True, help='风险 (logic), 可多次'),
        FMT,
        OUT,
    ))


def _run_kline(code, bars, start, end, period, ma, macd, chart, chart_out, png,
               ascii_art, ascii_style, ascii_h, ascii_w,
               kind, list_kinds, arg, fmt, output):
    if kind or list_kinds:
        return _fam_route('kline', kind, list_kinds, fmt, output,
                          [code] if code else [], list(arg or []), limit=None)
    return _dispatch('kline', fmt, output, codes=[code], bars=bars, start=start,
                     end=end, period=period, ma=ma, macd=macd, chart=chart,
                     chart_out=chart_out, png=png, ascii_art=ascii_art,
                     ascii_style=ascii_style, ascii_h=ascii_h, ascii_w=ascii_w)


declare('kline', _run_kline, 'K 线',
    args=(Arg('code', '股票代码 (A股/港股/美股)', required=False),),
    opts=(
        Opt('--bars', type=int, default=120, help='K 线根数'),
        Opt('--start', help='起始日期 YYYY-MM-DD'),
        Opt('--end', help='结束日期 YYYY-MM-DD'),
        Opt('--period', default='day', help='周期: day/week/month'),
        Opt('--ma', default='5,10,20', help='均线, 逗号分隔'),
        Opt('--macd', type=bool, default=False, help='加 MACD(12,26,9) 副图'),
        Opt('--chart', type=bool, default=False, help='出 SVG 图 (红涨绿跌 + 均线 + 量能)'),
        Opt('--chart-out', help='图输出路径 (默认 <代码>-<周期>.svg)'),
        Opt('--png', type=bool, default=False, help='图表输出 PNG (默认 SVG)'),
        Opt('--ascii', dest='ascii_art', type=bool, default=False, help='终端字符画'),
        Opt('--ascii-style', default='thin', help='字符画风格: thin|wide|plain'),
        Opt('--ascii-h', type=int, default=20, help='字符画高度 (行)'),
        Opt('--ascii-w', type=int, default=0, help='字符画宽度 (0=自适应)'),
        *family_opts('kline'), FMT, OUT,
    ))


# ---------------------------------------------------------------- 港股/美股/韩股
# A 股命令 (quote/kline) 不再兼职别的市场; 各市场用自己的前缀命令, 代码归属
# 由命令决定 (hk-quote 700 → hk00700), 不再靠"猜代码位数"。

def _mk_quote_cmd(market):
    def _f(codes: list[str] = typer.Argument(..., help='代码, 逗号分隔多只'),
           fmt: str = Fmt, output: str = Output):
        from prism.stock.name_index import to_market
        try:
            codes = to_market([c for c in (codes or []) if c], market)
        except ValueError as e:
            raise typer.BadParameter(str(e), param_hint='代码')
        return _dispatch('quote', fmt, output, codes=codes, market=market)
    return _f


def _mk_kline_cmd(market):
    def _f(code: str = typer.Argument(..., help='代码'),
           bars: int = typer.Option(120, '--bars', help='K 线根数'),
           start: str = typer.Option(None, '--start', help='起始日期 YYYY-MM-DD'),
           end: str = typer.Option(None, '--end', help='结束日期 YYYY-MM-DD'),
           period: str = typer.Option('day', '--period', help='周期: day/week/month'),
           ma: str = typer.Option('5,10,20', '--ma', help='均线, 逗号分隔'),
           macd: bool = typer.Option(False, '--macd', help='加 MACD 副图'),
           chart: bool = typer.Option(False, '--chart', help='出 SVG 图'),
           chart_out: str = typer.Option(None, '--chart-out', help='图输出路径'),
           png: bool = typer.Option(False, '--png', help='图表输出 PNG'),
           ascii_art: bool = typer.Option(False, '--ascii', help='终端字符画'),
           ascii_style: str = typer.Option('thin', '--ascii-style',
                                           help='字符画风格: thin|wide|plain'),
           ascii_h: int = typer.Option(20, '--ascii-h', help='字符画高度 (行)'),
           ascii_w: int = typer.Option(0, '--ascii-w', help='字符画宽度 (0=自适应)'),
           fmt: str = Fmt, output: str = Output):
        from prism.stock.name_index import to_market
        try:
            code = to_market([code], market)[0]
        except ValueError as e:
            raise typer.BadParameter(str(e), param_hint='代码')
        return _dispatch('kline', fmt, output,
                         codes=[code], market=market,
                         bars=bars, start=start, end=end, period=period, ma=ma,
                         macd=macd, chart=chart, chart_out=chart_out, png=png,
                         ascii_art=ascii_art, ascii_style=ascii_style,
                         ascii_h=ascii_h, ascii_w=ascii_w)
    return _f


def _run_hk_quote(codes, fmt, output):
    return _mk_quote_cmd('hk')(codes, fmt, output)


declare('hk-quote', _run_hk_quote, '港股行情 (只取港股)',
    args=(
        Arg('codes', '港股代码, 如 700 / 00700', multiple=True),
    ),
    opts=(
        FMT,
        OUT,
    ))


def _run_us_quote(codes, fmt, output):
    return _mk_quote_cmd('us')(codes, fmt, output)


declare('us-quote', _run_us_quote, '美股行情 (只取美股)',
    args=(
        Arg('codes', '美股代码, 如 AAPL', multiple=True),
    ),
    opts=(
        FMT,
        OUT,
    ))


def _run_kr_quote(codes, fmt, output):
    return _mk_quote_cmd('kr')(codes, fmt, output)


declare('kr-quote', _run_kr_quote, '韩股行情 (Naver, 只取韩股)',
    args=(
        Arg('codes', '韩股代码, 如 005930', multiple=True),
    ),
    opts=(
        FMT,
        OUT,
    ))


def _run_hk_kline(code, bars, start, end, period, ma, macd, chart, chart_out, png, ascii_art, ascii_style, ascii_h, ascii_w, fmt, output):
    return _mk_kline_cmd('hk')(code, bars, start, end, period, ma, macd, chart,
                               chart_out, png, ascii_art, ascii_style, ascii_h,
                               ascii_w, fmt, output)


declare('hk-kline', _run_hk_kline, '港股 K 线 (只取港股)',
    args=(
        Arg('code', '港股代码'),
    ),
    opts=(
        Opt('--bars', type=int, default=120, help='K 线根数'),
        Opt('--start', default=None),
        Opt('--end', default=None),
        Opt('--period', default='day'),
        Opt('--ma', default='5,10,20'),
        Opt('--macd', type=bool, default=False),
        Opt('--chart', type=bool, default=False),
        Opt('--chart-out', default=None),
        Opt('--png', type=bool, default=False),
        Opt('--ascii', type=bool, default=False, dest='ascii_art'),
        Opt('--ascii-style', default='thin'),
        Opt('--ascii-h', type=int, default=20),
        Opt('--ascii-w', type=int, default=0),
        FMT,
        OUT,
    ))


def _run_us_kline(code, bars, start, end, period, ma, macd, chart, chart_out, png, ascii_art, ascii_style, ascii_h, ascii_w, fmt, output):
    return _mk_kline_cmd('us')(code, bars, start, end, period, ma, macd, chart,
                               chart_out, png, ascii_art, ascii_style, ascii_h,
                               ascii_w, fmt, output)


declare('us-kline', _run_us_kline, '美股 K 线 (只取美股)',
    args=(
        Arg('code', '美股代码'),
    ),
    opts=(
        Opt('--bars', type=int, default=120, help='K 线根数'),
        Opt('--start', default=None),
        Opt('--end', default=None),
        Opt('--period', default='day'),
        Opt('--ma', default='5,10,20'),
        Opt('--macd', type=bool, default=False),
        Opt('--chart', type=bool, default=False),
        Opt('--chart-out', default=None),
        Opt('--png', type=bool, default=False),
        Opt('--ascii', type=bool, default=False, dest='ascii_art'),
        Opt('--ascii-style', default='thin'),
        Opt('--ascii-h', type=int, default=20),
        Opt('--ascii-w', type=int, default=0),
        FMT,
        OUT,
    ))


def _run_kr_kline(code, bars, start, end, period, ma, macd, chart, chart_out, png, ascii_art, ascii_style, ascii_h, ascii_w, fmt, output):
    return _mk_kline_cmd('kr')(code, bars, start, end, period, ma, macd, chart,
                               chart_out, png, ascii_art, ascii_style, ascii_h,
                               ascii_w, fmt, output)


declare('kr-kline', _run_kr_kline, '韩股 K 线 (Naver, 只取韩股)',
    args=(
        Arg('code', '韩股代码'),
    ),
    opts=(
        Opt('--bars', type=int, default=120, help='K 线根数'),
        Opt('--start', default=None),
        Opt('--end', default=None),
        Opt('--period', default='day'),
        Opt('--ma', default='5,10,20'),
        Opt('--macd', type=bool, default=False),
        Opt('--chart', type=bool, default=False),
        Opt('--chart-out', default=None),
        Opt('--png', type=bool, default=False),
        Opt('--ascii', type=bool, default=False, dest='ascii_art'),
        Opt('--ascii-style', default='thin'),
        Opt('--ascii-h', type=int, default=20),
        Opt('--ascii-w', type=int, default=0),
        FMT,
        OUT,
    ))


def _run_intraday(code, days, no_auction, after_hours, bar_seconds, ma_daily, ma, full_axis, auto_y, combo, chart, chart_out, png, ascii_art, ascii_style, ascii_h, ascii_w, fmt, output):
    return _dispatch('intraday', fmt, output, codes=[code], days=days,
                     no_auction=no_auction, after_hours=after_hours,
                     bar_seconds=bar_seconds, ma_daily=ma_daily, ma=ma,
                     full_axis=full_axis, auto_y=auto_y,
                     combo=combo, chart=chart, chart_out=chart_out, png=png,
                     ascii_art=ascii_art, ascii_style=ascii_style,
                     ascii_h=ascii_h, ascii_w=ascii_w)


declare('intraday', _run_intraday, '分时图 (默认含集合竞价)',
    args=(
        Arg('code', '股票代码'),
    ),
    opts=(
        Opt('--days', type=int, default=1, help='1=当日, 5=五日'),
        Opt('--no-auction', type=bool, default=False, help='不含集合竞价'),
        Opt('--after-hours', type=bool, default=False, help='保留 15:05 后盘后交易'),
        Opt('--bar-seconds', type=int, default=60, help='量柱粒度(秒): 60=分钟, 30/15 用逐笔聚合'),
        Opt('--ma-daily', default='5,10,20,60', help='叠加日线均线, 逗号分隔; 空串关闭'),
        Opt('--ma', default=None, help='分时均线, 逗号分隔, 如 5,20'),
        Opt('--full-axis', type=bool, default=False, help='纵轴强制撑满涨跌停'),
        Opt('--auto-y', type=bool, default=False, help='纵轴按实际波动自适应'),
        Opt('--combo', type=bool, default=False, help='三合一长图 (当日/30秒/五日)'),
        Opt('--chart', type=bool, default=False, help='出 SVG 图'),
        Opt('--chart-out', default=None, help='图输出路径'),
        Opt('--png', type=bool, default=False, help='图表输出 PNG'),
        Opt('--ascii', type=bool, default=False, dest='ascii_art', help='终端字符画'),
        Opt('--ascii-style', default='thin', help='字符画风格: thin|wide|plain'),
        Opt('--ascii-h', type=int, default=20, help='字符画高度 (行)'),
        Opt('--ascii-w', type=int, default=0, help='字符画宽度 (0=自适应)'),
        FMT,
        OUT,
    ))


# ---------------------------------------------------------------- 工具与透传

# ---------------------------------------------------------------- 冷门动作兜底

# ---------------------------------------------------------------- 标准动作
# _act_std 系列: 单代码 + 无额外参数, 批量注册避免 15 段重复代码

_STD_ACTIONS = {
    'income': '利润表',
    'balance': '资产负债表',
    'cashflow': '现金流量表',
    'company': '公司概况',
    'business': '主营业务构成',
    
    'industry': '行业板块列表',
    'concept': '概念板块列表',
    
    'dividend': '分红排行',
    'screener': '涨跌幅/PE/PB 排行 (按市场)',
    'ipo': '新股',
    'index': '指数行情',
    
    'forecast': '盈利预测 (东财)',
}


def _run_holders(code, free, research, chg, date, limit, kind, list_kinds, arg, fmt,
    output):
    if kind or list_kinds:
        return _fam_route('holders', kind, list_kinds, fmt, output,
                           [code] if code else [], list(arg or []), limit=limit)
    if research:
        return _dispatch('holder', fmt, output, codes=[code] if code else [],
                         limit=limit)
    if chg:
        return _dispatch('holder_chg', fmt, output, codes=[code] if code else [],
                         limit=limit)
    return _dispatch('holders', fmt, output, codes=[code] if code else [],
                     free=free, date=date, limit=limit)


declare('holders', _run_holders, '十大股东; --free 看十大流通股东 (券商/基金/QFII 明细)',
    args=(
        Arg('code', '股票代码', required=False),
    ),
    opts=(
        *family_opts('holders'),
        Opt('--free', type=bool, default=False, help='看十大流通股东 (季报口径)'),
        Opt('--research', type=bool, default=False, help='东财股东研究 (持仓变动/机构调研)'),
        Opt('--chg', type=bool, default=False, help='股东增减持变动'),
        Opt('--date', help='报告期 YYYYMMDD, 缺省取最近已披露'),
        Opt('--limit', type=int, default=10, short=('-n',), help='条数'),
        FMT,
        OUT,
    ))

def _run_changes(type_, limit, fmt, output):
    return _dispatch('changes', fmt, output, type_=type_, limit=limit)


declare('changes', _run_changes, '盘口异动 (大笔买入 / 封涨停 / 火箭发射 / 60日新高等)',
    opts=(
        Opt('--type', default='大笔买入', dest='type_', help='异动类型: 大笔买入/大笔卖出/封涨停板/火箭发射/60日新高...'),
        Opt('--limit', type=int, default=10, short=('-n',), help='条数'),
        FMT,
        OUT,
    ))

def _run_hot(kind, date, limit, list_kinds, arg, fmt, output):
    if kind and kind not in ('rank', 'baidu', 'search'):
        return _fam_route('hot', kind, list_kinds, fmt, output, [], list(arg or []), limit=limit)
    if list_kinds:
        return _fam_route('hot', kind, list_kinds, fmt, output, limit=limit)
    return _dispatch('hot', fmt, output, kind=kind, date=date, limit=limit)


declare('hot', _run_hot, '人气榜 (东财) / 百度股市热搜',
    opts=(
        Opt('--kind', default='rank', help='榜: rank(东财人气)/baidu(百度热搜)'),
        Opt('--date', help='baidu 口径日期 YYYYMMDD'),
        Opt('--limit', type=int, default=10, short=('-n',), help='条数'),
        Opt('--list', dest='list_kinds', type=bool, default=False, help='列出 hot 的扩展口径'),
        Opt('--arg', multiple=True, metavar='K=V', help='额外参数 K=V, 可重复'),
        FMT,
        OUT,
    ))

def _run_buyback(progress, limit, fmt, output):
    return _dispatch('buyback', fmt, output, progress=progress, limit=limit)


declare('buyback', _run_buyback, '全市场回购 (计划金额 / 实施进度 / 已回购), 按最新公告日倒序',
    opts=(
        Opt('--progress', default=None, help='筛选进度, 如 实施中/完成'),
        Opt('--limit', type=int, default=10, short=('-n',), help='条数'),
        FMT,
        OUT,
    ))

def _run_shares(code, fmt, output):
    return _dispatch('shares', fmt, output, codes=[code])


declare('shares', _run_shares, '股本结构变动 (总股本/流通/限售, 单位亿股)',
    args=(
        Arg('code', '股票代码'),
    ),
    opts=(
        FMT,
        OUT,
    ))

def _run_notice(kind, date, limit, list_kinds, arg, fmt, output):
    if kind or list_kinds:
        return _fam_route('notice', kind, list_kinds, fmt, output, [], list(arg or []), limit=limit)
    return _dispatch('notice', fmt, output, kind=kind, date=date, limit=limit)


declare('notice', _run_notice, '全市场公告流 (当日 1800+ 条), 可按类型过滤',
    opts=(
        Opt('--kind', help='公告类型过滤, 如 重大事项/财务报告'),
        Opt('--date', help='公告日期 YYYYMMDD'),
        Opt('--limit', type=int, default=10, short=('-n',), help='条数'),
        Opt('--list', dest='list_kinds', type=bool, default=False, help='列出 notice 的扩展口径'),
        Opt('--arg', multiple=True, metavar='K=V', help='额外参数 K=V, 可重复'),
        FMT,
        OUT,
    ))

def _run_disclosure_schedule(date, scope, limit, fmt, output):
    return _dispatch('yysj', fmt, output, date=date, scope=scope, limit=limit)


declare('disclosure-schedule', _run_disclosure_schedule, '财报预约披露日 (首次预约与三次改期)',
    opts=(
        Opt('--date', default=None, help='报告期 YYYYMMDD (默认最近已结束季度)'),
        Opt('--scope', default='沪深A股', help='范围: 沪深A股/上证A股/深证A股'),
        Opt('--limit', type=int, default=10, short=('-n',), help='条数'),
        FMT,
        OUT,
    ))

def _run_earnings_report(date, limit, fmt, output):
    return _dispatch('yjbb', fmt, output, date=date, limit=limit)


declare('earnings-report', _run_earnings_report, '业绩报表 (营收/净利/同比/ROE), 按净利同比降序',
    opts=(
        Opt('--date', default=None, help='报告期 YYYYMMDD'),
        Opt('--limit', type=int, default=10, short=('-n',), help='条数'),
        FMT,
        OUT,
    ))

def _run_fhps(date, limit, fmt, output):
    return _dispatch('fhps', fmt, output, date=date, limit=limit)


declare('fhps', _run_fhps, '分红送配明细 (送转/现金分红/股息率), 按股息率降序',
    opts=(
        Opt('--date', default=None, help='报告期 YYYYMMDD'),
        Opt('--limit', type=int, default=10, short=('-n',), help='条数'),
        FMT,
        OUT,
    ))

def _run_shareholding_change(code, limit, refresh, fmt, output):
    return _dispatch('ggcg', fmt, output, codes=[code] if code else [],
                     limit=limit, refresh=refresh)


declare('shareholding-change', _run_shareholding_change, '股东增减持 (全市场, 首次 120s 后落盘缓存 12h)',
    args=(
        Arg('code', '股票代码 (不填看全市场)', required=False),
    ),
    opts=(
        Opt('--limit', type=int, default=10, short=('-n',), help='条数'),
        Opt('--refresh', type=bool, default=False, help='强制重取 (全量约 120s)'),
        FMT,
        OUT,
    ))

def _run_insider_trade(code, limit, refresh, fmt, output):
    return _dispatch('mgmt', fmt, output, codes=[code] if code else [],
                     limit=limit, refresh=refresh)


declare('insider-trade', _run_insider_trade, '董监高持股变动明细 (全市场, 首次 230s 后落盘缓存 12h)',
    args=(
        Arg('code', '股票代码 (不填看全市场)', required=False),
    ),
    opts=(
        Opt('--limit', type=int, default=10, short=('-n',), help='条数'),
        Opt('--refresh', type=bool, default=False, help='强制重取 (全量约 230s)'),
        FMT,
        OUT,
    ))

def _run_futures(code, limit, minute, realtime, inventory, contracts, date, kind,
    list_kinds, arg, fmt, output):
    if kind or list_kinds:
        return _fam_route('futures', kind, list_kinds, fmt, output,
                           [code] if code else [], list(arg or []), limit=limit)
    return _dispatch('futures', fmt, output, codes=[code], limit=limit,
                     minute=minute, realtime=realtime, inventory=inventory,
                     contracts=contracts, date=date)


declare('futures', _run_futures, '期货行情 (主力连续日线/分钟线)、库存、合约信息、交易所数据',
    args=(
        Arg('code', '合约代码: RB0(螺纹主连)/AU0/I0/M0...', required=False,
        default='RB0'),
    ),
    opts=(
        Opt('--limit', type=int, default=10, short=('-n',), help='条数'),
        Opt('--minute', type=int, default=0, help='切分钟线: 1/5/15/30/60'),
        Opt('--realtime', help='实时行情, 传中文品种名如 螺纹钢'),
        Opt('--inventory', help='期货库存, 传中文品种名'),
        Opt('--contracts', type=bool, default=False, help='看上期所合约信息'),
        Opt('--date', help='合约/交易日 YYYYMMDD'),
        Opt('--kind', help='扩展口径 (prism futures --list)'),
        Opt('--list', dest='list_kinds', type=bool, default=False, help='列出期货扩展口径'),
        Opt('--arg', multiple=True, metavar='K=V', help='额外参数 K=V, 可重复'),
        FMT,
        OUT,
    ))

def _run_option(kind, date, symbol, limit, list_kinds, arg, fmt, output):
    if list_kinds or kind not in ('stats', 'greeks', 'margin', 'comm', 'lhb', 'contract'):
        return _fam_route('option', kind, list_kinds, fmt, output, [], list(arg or []), limit=limit)
    return _dispatch('option', fmt, output, kind=kind, date=date,
                     symbol=symbol, limit=limit)


declare('option', _run_option, '期权: 成交统计 / 希腊值 / 保证金 / 商品期权 / 龙虎榜',
    opts=(
        Opt('--kind', default='stats', help='stats 成交统计/greeks 希腊值/margin 保证金/comm 商品期权/lhb 龙虎榜/contract 合约'),
        Opt('--date', help='交易日 YYYYMMDD'),
        Opt('--symbol', help='合约口径, 如 白糖期权'),
        Opt('--limit', type=int, default=10, short=('-n',), help='条数'),
        Opt('--list', dest='list_kinds', type=bool, default=False, help='列出期权扩展口径'),
        Opt('--arg', multiple=True, metavar='K=V', help='额外参数 K=V, 可重复'),
        FMT,
        OUT,
    ))

def _run_fund(code, hold, year, order, kind, list_kinds, arg, limit, fmt, output):
    if kind or list_kinds:
        return _fam_route('fund', kind, list_kinds, fmt, output,
                           [code] if code else [], list(arg or []), limit=limit)
    return _dispatch('fund', fmt, output, codes=[code] if code else [],
                     hold=hold, year=year, order=order, limit=limit)


declare('fund', _run_fund, '基金: 不给参数看净值排行, 给代码看净值历史, --hold 看重仓股',
    args=(
        Arg('code', '基金代码 (给代码看净值历史)', required=False),
    ),
    opts=(
        Opt('--hold', help='看该基金重仓股'),
        Opt('--year', help='重仓股年份, 如 2025'),
        Opt('--order', default='desc', help='排行方向: desc/asc'),
        Opt('--kind', help='扩展口径 (prism fund --list)'),
        Opt('--list', dest='list_kinds', type=bool, default=False, help='列出基金扩展口径'),
        Opt('--arg', multiple=True, metavar='K=V', help='额外参数 K=V, 可重复'),
        Opt('--limit', type=int, default=10, short=('-n',), help='条数'),
        FMT,
        OUT,
    ))

def _run_bond(kind, start, end, limit, list_kinds, arg, fmt, output):
    if list_kinds or kind not in ('yield', 'us', 'summary'):
        return _fam_route('bond', kind, list_kinds, fmt, output, [], list(arg or []), limit=limit)
    return _dispatch('bond', fmt, output, kind=kind, start=start, end=end, limit=limit)


declare('bond', _run_bond, '债券: 中债收益率曲线 / 中美国债对比 / 现券成交',
    opts=(
        Opt('--kind', default='yield', help='yield 中债收益率曲线/us 中美国债/summary 现券成交'),
        Opt('--start', help='起始日 YYYYMMDD (yield)'),
        Opt('--end', help='结束日 YYYYMMDD (yield)'),
        Opt('--limit', type=int, default=10, short=('-n',), help='条数'),
        Opt('--list', dest='list_kinds', type=bool, default=False, help='列出债券扩展口径'),
        Opt('--arg', multiple=True, metavar='K=V', help='额外参数 K=V, 可重复'),
        FMT,
        OUT,
    ))

def _run_hk(code, limit, kind, list_kinds, arg, fmt, output):
    if kind or list_kinds:
        return _fam_route('hk', kind, list_kinds, fmt, output,
                           [code] if code else [], list(arg or []), limit=limit)
    return _dispatch('hk', fmt, output, codes=[code] if code else [], limit=limit)


declare('hk', _run_hk, '港股实时快照 (2810 只)',
    args=(
        Arg('code', '港股代码/名称 (不填看全市场)', required=False),
    ),
    opts=(
        *family_opts('hk'),
        Opt('--limit', type=int, default=10, short=('-n',), help='条数'),
        FMT,
        OUT,
    ))

def _run_spot(kind_pos, kind, list_kinds, arg, limit, fmt, output):
    kind = kind or kind_pos          # 位置简写与 --kind 等价, 位置优先
    return _fam_route('spot', kind, list_kinds, fmt, output, [], list(arg or []), limit=limit)


declare('spot', _run_spot, '现货与商品 (金银/原油/农产品/伦交所库存等)',
    args=(
        Arg('kind_pos', '口径名 (简写; 等价 --kind)', required=False),
    ),
    opts=(
        Opt('--kind', help='口径名 (用 --list 看全部)'),
        Opt('--list', dest='list_kinds', type=bool, default=False, help='列出现货商品口径'),
        Opt('--arg', multiple=True, metavar='K=V', help='额外参数 K=V, 可重复'),
        Opt('--limit', type=int, default=10, short=('-n',), help='条数'),
        FMT,
        OUT,
    ))

def _run_world(kind_pos, kind, list_kinds, arg, limit, fmt, output):
    kind = kind or kind_pos          # 位置简写与 --kind 等价, 位置优先
    return _fam_route('world', kind, list_kinds, fmt, output, [], list(arg or []), limit=limit)


declare('world', _run_world, '海外市场 (全球指数/外汇/加密/能源)',
    args=(
        Arg('kind_pos', '口径名 (简写; 等价 --kind)', required=False),
    ),
    opts=(
        Opt('--kind', help='口径名 (用 --list 看全部)'),
        Opt('--list', dest='list_kinds', type=bool, default=False, help='列出海外口径'),
        Opt('--arg', multiple=True, metavar='K=V', help='额外参数 K=V, 可重复'),
        Opt('--limit', type=int, default=10, short=('-n',), help='条数'),
        FMT,
        OUT,
    ))

def _run_misc(kind_pos, kind, list_kinds, arg, limit, fmt, output):
    kind = kind or kind_pos          # 位置简写与 --kind 等价, 位置优先
    return _fam_route('misc', kind, list_kinds, fmt, output, [], list(arg or []), limit=limit)


declare('misc', _run_misc, '杂项数据 (汽车/电影/游戏/榜单一类, 与行情弱相关)',
    args=(
        Arg('kind_pos', '口径名 (简写; 等价 --kind)', required=False),
    ),
    opts=(
        Opt('--kind', help='口径名 (用 --list 看全部)'),
        Opt('--list', dest='list_kinds', type=bool, default=False, help='列出杂项口径'),
        Opt('--arg', multiple=True, metavar='K=V', help='额外参数 K=V, 可重复'),
        Opt('--limit', type=int, default=10, short=('-n',), help='条数'),
        FMT,
        OUT,
    ))

def _run_data_health(fmt, output):
    return _dispatch('data-health', fmt, output)


declare('data-health', _run_data_health, '数据面体检: 传输层 / 生态库 / 东财配方各是否可用',
    opts=(
        FMT,
        OUT,
    ))


def _run_schema(name, kind, list_kinds, all_cmds, fmt, output):
    return _dispatch('schema', fmt, output, name=name, kind=kind,
                     list_kinds=list_kinds, all_cmds=all_cmds)


declare('schema', _run_schema, '命令参数与 JSON 输出结构自描述 (给脚本和 agent 用)',
    args=(
        Arg('name', '命令名 (例: lhb); --all 列全部', required=False),
    ),
    opts=(
        Opt('--kind', default=None, help='口径名 (可选)'),
        Opt('--list', type=bool, default=False, dest='list_kinds', help='列出该命令的口径'),
        Opt('--all', type=bool, default=False, dest='all_cmds', help='列出全部命令'),
        FMT,
        OUT,
    ))


def _run_margin(code, detail, history, date, exchange, limit, kind, list_kinds, arg, fmt,
    output):
    if kind or list_kinds:
        return _fam_route('margin', kind, list_kinds, fmt, output,
                           [code] if code else [], list(arg or []), limit=limit)
    return _dispatch('margin', fmt, output, codes=[code] if code else [],
                     detail=detail, history=history, date=date, exchange=exchange,
                     limit=limit)


declare('margin', _run_margin, '融资融券: 当日列表 / --detail 逐股明细 / --history 余额历史',
    args=(
        Arg('code', '股票代码 (明细时筛单只)', required=False),
    ),
    opts=(
        *family_opts('margin'),
        Opt('--detail', type=bool, default=False, help='逐股两融明细 (需 --date)'),
        Opt('--history', type=bool, default=False, help='两融余额/账户历史'),
        Opt('--date', help='明细日期 YYYYMMDD (默认上一交易日)'),
        Opt('--exchange', default='sse', dest='exchange', help='交易所: sse(沪)/szse(深)'),
        Opt('--limit', type=int, default=10, short=('-n',), help='条数'),
        FMT,
        OUT,
    ))


# 自动生成命令的位置参数说明 (共用一句"股票代码"对 screener/index 这类不准确)
_STD_ARG_HELP = {
    'screener': '市场: cn_a(A股) / cn_b / hk / us',
    'index': '指数代码或别名 (如 沪深300 / 000300)',
    'industry_of': '股票代码 (看它属于哪些行业/概念)',
    'industry': '行业名关键字 (可省)',
    'concept': '概念名关键字 (可省)',
    'dividend': '股票代码 (看该股分红历史, 可省)',
    'business': '股票代码',
    'holder_chg': '股票代码',
    'holder': '股票代码',
    'forecast': '股票代码',
    'company': '股票代码',
    'ipo': '市场范围 (如 沪市主板, 可省)',
}


# 主语是股票代码的命令: 没给代码就直接说怎么用, 别让上游回一个
# KeyError: 'symbol' 这种天书
_NEEDS_CODE = {'income', 'balance', 'cashflow', 'company', 'business',
               'forecast'}

def _mk_std(action, desc):
    """生成一个薄命令: 原生口径 + (若该命令有扩展口径族) --kind/--list

    与手写命令一样走 build(), 因此选项是数据 (spec_of 可读), 也能被
    tests/test_prism_core.py 的签名-动作一致性检查覆盖。
    """
    from prism.stock.bridge.ak_families import FAM as _FAM
    arg_help = _STD_ARG_HELP.get(action, '股票代码 / 指数别名')
    meta = {'screener': 'MARKET', 'concept': 'KEYWORD', 'industry': 'KEYWORD',
            'ipo': 'MARKET', 'fund': 'CODE', 'screen': 'CODES'}.get(action, 'CODE')
    LIMIT = Opt('--limit', type=int, default=10, short=('-n',), help='条数')
    ARG = Opt('--arg', type=str, default=None, multiple=True, metavar='K=V',
              help='额外参数 K=V, 可重复')

    if action == 'industry':
        def _act(keyword, of, limit, kind, list_kinds, arg, fmt, output):
            if of:
                return _dispatch('industry_of', fmt, output, codes=[of], limit=limit)
            if kind or list_kinds:
                return _fam_route('industry', kind, list_kinds, fmt, output,
                                  [keyword] if keyword else [], list(arg or []),
                                  limit=limit)
            return _dispatch('industry', fmt, output,
                             codes=[keyword] if keyword else [],
                             limit=limit, params=list(arg or []))

        spec = Cmd(action, _act, desc,
                   args=(Arg('keyword', '行业名关键字 (可省)', required=False,
                             metavar='KEYWORD'),),
                   opts=(Opt('--of', help='看某只股票属于哪些行业/概念'), LIMIT,
                         Opt('--kind', help='扩展口径 (先跑 prism industry --list)'),
                         Opt('--list', dest='list_kinds', type=bool, default=False,
                             help='列出扩展口径'), ARG, FMT, OUT))

    elif action in _FAM:
        def _act(code, limit, kind, list_kinds, arg, fmt, output):
            if kind or list_kinds:
                return _fam_route(action, kind, list_kinds, fmt, output,
                                  [code] if code else [], list(arg or []),
                                  limit=limit)
            if not code and action in _NEEDS_CODE:
                # 这条命令的主语就是股票代码, 没给就直接说怎么用 ——
                # 否则下游会回 KeyError: 'symbol' 这种天书
                print(f'error: {action} 需要股票代码: prism {action} 600519',
                      file=sys.stderr)
                raise typer.Exit(code=2)
            return _dispatch(action, fmt, output, codes=[code] if code else [],
                             limit=limit, params=list(arg or []))

        spec = Cmd(action, _act, desc,
                   args=(Arg('code', arg_help, required=False, metavar=meta),),
                   opts=(LIMIT,
                         Opt('--kind', help='扩展口径 (先跑本命令 --list 看有哪些)'),
                         Opt('--list', dest='list_kinds', type=bool, default=False,
                             help='列出扩展口径'), ARG, FMT, OUT))

    else:
        def _act(code, limit, arg, fmt, output):
            if not code and action in _NEEDS_CODE:
                # 这条命令的主语就是股票代码, 没给就直接说怎么用 ——
                # 否则下游会回 KeyError: 'symbol' 这种天书
                print(f'error: {action} 需要股票代码: prism {action} 600519',
                      file=sys.stderr)
                raise typer.Exit(code=2)
            return _dispatch(action, fmt, output, codes=[code] if code else [],
                             limit=limit, params=list(arg or []))

        spec = Cmd(action, _act, desc,
                   args=(Arg('code', arg_help, required=False),),
                   opts=(LIMIT, ARG, FMT, OUT))

    return build(spec)


for _name, _desc in _STD_ACTIONS.items():
    COMMANDS[_name] = cmd(_name)(_mk_std(_name, _desc))





# 给没有 --kind 的命令补扩展口径入口 (在 app 构建 typer 命令之前完成包装)
for _n in ('flow', 'stock-connect', 'concept', 'screen', 'earnings-report',
           'analyst-report', 'insider-trade', 'disclosure-schedule'):
    if _n in COMMANDS:
        COMMANDS[_n] = _with_kind(_n)(COMMANDS[_n])

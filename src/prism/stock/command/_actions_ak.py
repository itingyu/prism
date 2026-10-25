"""akshare 数据域动作: 龙虎榜 / 大宗 / 解禁 / 调研 / 研报 / 宏观 / 北向 / 可转债

这些数据原生源 (同花顺/东财逆向/雪球) 都没有直接接口, 或接口只覆盖一部分。
统一返回形状:

    {'source': 'akshare', 'date': 'YYYY-MM-DD', 'count': N, 'rows': [...]}

渲染层按 action 取列 (见 `_textfmt_ak.COLS`), json 保持 akshare 原始中文列名。
akshare 没装时抛 AkUnavailable, do_stock 会转成"缺依赖"提示, 而不是伪装成
"没有数据"。
"""
from prism.util.num import to_float
from prism.stock.bridge import ak as _ak

def _dates(args, days: int = 7):
    """(start, end): 显式给 --start/--end 优先, 否则回看 days 个自然日

    与通用口径路径的 _date_window 是同一套逻辑 (那边在函数定义之后,
    这里直接转发), 避免两处各算一次窗口算出两个结果。
    """
    return _date_window(args, days)

def _show(d) -> str:
    """20261018 -> 2026-10-18 (给人看的日期一律带分隔符)"""

    d = str(d)
    return f'{d[:4]}-{d[4:6]}-{d[6:]}' if len(d) == 8 and d.isdigit() else d

def _span(start, end) -> str:
    return f'{_show(start)}~{_show(end)}'


# 窗口朝未来的接口: 上游数据本身是"以后会发生的事", 取过去一段等于空转。
# 只放确认过的接口, 加一条要有专用命令的实现佐证。
FORWARD_WINDOW = frozenset({
    'stock_restricted_release_detail_em',    # 限售解禁明细 (prism unlock)
    'stock_restricted_release_summary_em',   # 解禁日历     (prism unlock --summary)
})

def _date_window(args, default_days: int = 30, forward: bool = False):
    """区间型接口的取数窗口: --start/--end 优先, 其次 --days, 兜底近 N 天

    返回 (start, end), 都是 YYYYMMDD。forward=True 表示窗口朝未来推
    (解禁这类前瞻数据: 专用命令取"未来 30 天", 通用路径取"过去 30 天"就是
    完全相反的一段, 同一个接口给出互不相干的结果)。

    为什么需要它: akshare 的区间接口 (start_date/end_date) 上游自带一个
    **很旧的默认窗口** —— 不显式给日期就静默返回几年前的行情, 不报错。
    专用命令 (prism lhb 等) 自己算窗口, 通用 --kind 路径以前不算,
    于是同一个接口两条路径给的数据不一样 (实测 stock_lhb_detail_em
    走 --kind 返回 2023-04-06 的数据, 走 prism lhb 返回当周数据)。
    """
    end = _ak.ymd(getattr(args, 'end', None))
    try:
        days = int(getattr(args, 'days', None) or default_days)
    except (TypeError, ValueError):
        days = default_days
    if forward and not getattr(args, 'start', None):
        return end, _ak._shift(end, days)
    start = (_ak.ymd(getattr(args, 'start', None))
             if getattr(args, 'start', None) else _ak._shift(end, -days))
    return start, end

def _wrap(rows, date=None, **extra):
    out = {'source': 'akshare', 'count': len(rows), 'rows': rows}
    if date:
        out['date'] = date
    out.update(extra)
    return out

def _year_of(v):
    """从 '2026年第1-3季度' / '2026-09-20' / 1792713600000 里抠年份"""
    import re
    m = re.search(r'(19|20)\d{2}', str(v))
    return int(m.group(0)) if m else 0

def _code(args):
    """第一个股票代码; 多值参数叫 codes, 单值叫 code"""
    codes = [c for c in (getattr(args, 'codes', None) or []) if c]
    if codes:
        return codes[0]
    return getattr(args, 'code', None) or None

def _act_zt_pool(args, kind):
    """涨停家族 (pool --type): strong/zb/prev/dt, 数据源 akshare

    原生涨停池 (engine.do_pool) 只有"今天涨停", 强势股/炸板/昨日涨停/跌停
    都在 akshare 这边, 所以按 kind 分流而不是重写原有口径。
    """
    date = getattr(args, 'date', None)
    if not date:
        from prism.stock.engine.clients import prev_trading_day
        date = prev_trading_day() or _ak.ymd()
    rows = _ak.zt_pool(date, kind)
    if not rows:
        raise _ak.AkFailed(f'{date} 无 {_ak.ZT_FUNCS[kind][1]} 数据')
    return _wrap(rows, _show(_ak.ymd(date)), kind=kind,
                 title=_ak.ZT_FUNCS[kind][1])

# ── 龙虎榜 ──────────────────────────────────────────────────────
def _act_lhb(args, cfg):
    """龙虎榜: 默认个股明细, --yyb 营业部榜单, --stats 统计口径

    --stats 的四个口径 (stock/jg/yyb/trader) 才是"谁在持续买"的答案,
    单日明细只能回答"今天谁买了"。
    """
    if getattr(args, 'stats', None):
        return _act_lhb_stats(args, cfg)
    start, end = _dates(args, int(getattr(args, 'days', 7) or 7))
    if getattr(args, 'yyb', False):
        rows = _ak.lhb_yyb(start, end)
    else:
        rows = _ak.lhb(start, end)
        code = _code(args)
        if code:
            rows = _ak._of_code(rows, _ak.code6(code))
    if not rows:
        raise _ak.AkFailed(f'{_span(start, end)} 无龙虎榜记录')
    rows = _ak._tail(rows, int(getattr(args, 'limit', 50) or 50))
    return _wrap(rows, _span(start, end))

# ── 大宗交易 ────────────────────────────────────────────────────
def _act_dzjy(args, cfg):
    start, end = _dates(args, int(getattr(args, 'days', 7) or 7))
    rows = _ak.dzjy(start, end, _code(args))
    if not rows:
        raise _ak.AkFailed(f'{_span(start, end)} 无大宗交易记录')
    rows = _ak._tail(rows, int(getattr(args, 'limit', 50) or 50))
    return _wrap(rows, _span(start, end))

# ── 限售解禁 ────────────────────────────────────────────────────
def _act_unlock(args, cfg):
    """限售解禁: 默认未来 30 天, --summary 按日汇总 (供给压力日历)"""
    days = int(getattr(args, 'days', 0) or 30)
    if getattr(args, 'start', None) or getattr(args, 'end', None):
        start, end = _dates(args, days)
    else:
        start, end = _date_window(args, days, forward=True)
    if getattr(args, 'summary', False):
        rows = _ak.unlock_summary(start, end)
    else:
        rows = _ak.unlock(start, end, _code(args))
    if not rows:
        raise _ak.AkFailed(f'{_span(start, end)} 无解禁记录')
    rows = _ak._tail(rows, int(getattr(args, 'limit', 50) or 50))
    return _wrap(rows, _span(start, end))

# ── 机构调研 ────────────────────────────────────────────────────
def _act_jgdy(args, cfg):
    """机构调研明细。按"调研日"取, 给了代码就在当日结果里筛

    调研公告有滞后: 当天/上一交易日经常还没有数据 (上游 result 为 null),
    所以从指定日往前最多退 5 个交易日, 结果里带上实际命中的日期 ——
    否则用户会以为"昨天没人调研"。
    """
    from prism.stock.engine.clients import prev_trading_day
    date = getattr(args, 'date', None) or prev_trading_day() or _ak.ymd()
    rows, used, tries = [], date, 0
    while tries < 5:
        try:
            rows = _ak.jgdy(used, _code(args))
        except Exception:                       # noqa: BLE001 上游 result=null
            rows = []
        if rows:
            break
        nxt = prev_trading_day(used)
        if not nxt or nxt == used:
            break
        used = nxt
        tries += 1
    if not rows:
        raise _ak.AkFailed(f'{date} 起 5 个交易日内无机构调研记录')
    date = used
    rows = _ak._tail(rows, int(getattr(args, 'limit', 50) or 50))
    rows = _ak._tail(rows, int(getattr(args, 'limit', 50) or 50))
    return _wrap(rows, date)

# ── 研报 ────────────────────────────────────────────────────────
def _act_yanbao(args, cfg):
    """个股研报: 评级 / 覆盖机构 / 未来三年 EPS 与 PE 预测"""
    code = _code(args)
    if not code:
        raise ValueError('yanbao 需要股票代码 (prism yanbao 600519)')
    rows = _ak.yanbao(code)
    if not rows:
        raise _ak.AkFailed(f'{code} 无研报记录')
    # 上游按时间正序给全历史, 取"最新 N 篇"才符合看研报的动机
    rows = sorted(rows, key=lambda r: str(r.get('日期') or ''), reverse=True)
    rows = rows[:int(getattr(args, 'limit', 10) or 10)]
    return _wrap(rows, code=code)

# ── 股东户数 ────────────────────────────────────────────────────
def _act_gdhs(args, cfg):
    """股东户数历史: 户数增减 / 户均持股市值 (筹码集中度)"""
    code = _code(args)
    if not code:
        raise ValueError('gdhs 需要股票代码 (prism gdhs 600519)')
    rows = _ak.gdhs(code)
    if not rows:
        raise _ak.AkFailed(f'{code} 无股东户数数据')
    rows = _ak._tail(rows, int(getattr(args, 'limit', 12) or 12))
    return _wrap(rows, code=code)

# ── 宏观 ────────────────────────────────────────────────────────
_MACRO = {
    # CPI 用统计局口径 (macro_china_cpi_monthly 是东财经济日历, 常年滞后一季)
    'cpi': ('macro_china_cpi', 'CPI 月度'),
    'ppi': ('macro_china_ppi', 'PPI 月度'),
    'pmi': ('macro_china_pmi', 'PMI 月度'),
    'lpr': ('macro_china_lpr', 'LPR 报价'),
    'm2': ('macro_china_money_supply', '货币供应 (M0/M1/M2)'),
    'gdp': ('macro_china_gdp', 'GDP 季度'),
    'shibor': ('macro_china_shibor_all', 'Shibor 拆借利率'),
    'shrzgm': ('macro_china_shrzgm', '社会融资规模增量'),
    'rmb': ('currency_boc_safe', '人民币中间价 (中行, 100 外币兑人民币)'),
    'cnbs': ('macro_cnbs', '宏观杠杆率'),
    'us_nfp': ('macro_usa_non_farm', '美国非农就业'),
    'us_cpi': ('macro_usa_cpi_monthly', '美国 CPI 月率'),
}

def _act_macro(args, cfg):
    """宏观指标: cpi / ppi / pmi / lpr / m2 / gdp / shibor / shrzgm / rmb / cnbs"""
    key = (getattr(args, 'indicator', None) or 'cpi').strip().lower()
    if key not in _MACRO:
        # 不是原生口径: 当作扩展口径 (支持 "australia cpi" 这种分词写法)
        from prism.stock.bridge.ak_resolve import resolve
        kind, _spec = resolve('macro', key, _ak.AkFailed)
        args.indicator = kind
        args.family = 'macro'
        return _act_fam(args, cfg)
    func, title = _MACRO[key]
    rows = _ak.rows(func, timeout=30)
    if key == 'rmb':
        # macro_china_rmb 只更到 2021, 中行口径更新到当日; 26 列只留常用币种
        keep = ('日期', '美元', '欧元', '日元', '港元', '英镑')
        rows = [{k: r.get(k) for k in keep} for r in rows]
    n = int(getattr(args, 'limit', 12) or 12)
    # 上游有的表正序有的倒序 (GDP/PMI 倒序, Shibor 正序), 直接 tail 会拿到
    # 2006 年的数据。用"首行年份 vs 末行年份"判断方向后整体翻转, 不按字符串
    # 排序 —— '2026年第1-3季度' 与 '2026年第1季度' 的字典序是反的。
    dkey = next((k for k in rows[0] if any(h in str(k) for h in
                                           ('月', '季', '日', 'DATE', 'date'))), None)
    if dkey and len(rows) > 1:
        a = _year_of(rows[0].get(dkey))
        b = _year_of(rows[-1].get(dkey))
        if a and b and a > b:
            rows = rows[::-1]
    return _wrap(rows[-n:], indicator=key, title=title)

# ── 北向资金 ────────────────────────────────────────────────────
def _act_hsgt(args, cfg):
    """陆股通: 默认当日四板块快照; --scope north|south 看历史

    北向单日净买额自 2024-08-16 起停止披露。上游仍按日期出行、数值为空,
    所以历史口径按"有值的行"过滤, 并在 note 里写清截止日 —— 不能把空当 0。
    """
    scope = (getattr(args, 'scope', None) or 'summary').strip().lower()
    if scope in ('summary', 'snapshot', 'today', ''):
        rows = _ak.hsgt_snapshot()
        return _wrap(rows, '陆股通当日快照',
                     note='北向 (沪股通/深股通) 自 2024-08 起停止披露单日净买额, '
                          '净买额显示 0 为上游占位; 南向 (港股通) 仍正常')
    rows = _ak.hsgt(int(getattr(args, 'days', 10) or 10), scope)
    if not rows:
        raise _ak.AkFailed('无陆股通历史数据')
    label = '南向资金' if scope in ('south', '南向') else '北向资金'
    note = '' if scope in ('south', '南向') else \
        '北向单日数据止于 2024-08-16 (交易所停止披露)'
    out = _wrap(rows, label)
    if note:
        out['note'] = note
    return out

# ── 市场宽度 ────────────────────────────────────────────────────
def _act_breadth(args, cfg):
    """市场宽度: 涨跌家数 / 涨跌停家数 / 活跃度"""
    d = _ak.breadth()
    return {'source': 'akshare', 'count': len(d), 'data': d}

# ── 可转债 ──────────────────────────────────────────────────────
def _act_cb(args, cfg):
    """可转债: 转股价值 / 溢价率 / 评级; 给正股代码则只列相关转债"""
    rows = _ak.cb(_code(args))
    if not rows:
        raise _ak.AkFailed('无可转债记录')
    # 上游含大量已退市/未上市条目 (转股价为空), 默认只留在市的
    live = [r for r in rows if to_float(r.get('转股价'))]
    rows = sorted(live, key=lambda r: str(r.get('上市时间') or ''), reverse=True)
    rows = rows[:int(getattr(args, 'limit', 30) or 30)]
    return _wrap(rows)

# ── ETF ─────────────────────────────────────────────────────────
def _act_etf(args, cfg):
    """ETF 行情列表; 默认按涨跌幅高→低, --sort 可换 (涨跌幅/成交额)"""
    rows = _ak.etf()
    key = getattr(args, 'sort', None) or '涨跌幅'

    def _sort_key(r):
        return to_float(r.get(key) or 0, 0.0)
    if getattr(args, 'asc', False):
        rows = sorted(rows, key=_sort_key)
    else:
        rows = sorted(rows, key=_sort_key, reverse=True)
    return _wrap(rows[:int(getattr(args, 'limit', 20) or 20)], sort=key)


# ── 第二批: 情绪 / 业绩 / 风险 / 两融 / 估值 / 评级 ─────────────────

def _act_comment(args, cfg):
    """千股千评: 全市场综合得分横截面 (默认按综合得分排序)"""
    from prism.stock.bridge import ak_ext as _x
    key = getattr(args, 'sort', None) or '综合得分'
    rows = _x.comment(int(getattr(args, 'limit', 50) or 50), key=key,
                      desc=not getattr(args, 'asc', False))
    if not rows:
        raise _ak.AkFailed('千股千评无数据')
    day = rows[0].get('交易日') or ''
    return _wrap(rows, _show(str(day).replace('-', '')) if day else '', sort=key,
                 title=f'千股千评 (按{key})')


def _act_yjyg(args, cfg):
    """业绩预告 / 业绩快报 (按报告期), 可按代码筛"""
    from prism.stock.bridge import ak_ext as _x
    kind = (getattr(args, 'type_', None) or 'yjyg').lower()
    date = getattr(args, 'date', None) or _ak.quarter_end()
    rows = _x.yjyg(date, 'yjyg' if kind == 'yjyg' else 'yjkb')
    code = _code(args)
    if code:
        rows = [r for r in rows
                if str(r.get('股票代码') or r.get('代码') or '')[-6:] == code]
    if not rows:
        raise _ak.AkFailed(f'{date} 无{"业绩预告" if kind == "yjyg" else "业绩快报"}记录')
    n = int(getattr(args, 'limit', 50) or 50)
    return _wrap(rows[:n], _show(date), kind=kind,
                 title='业绩预告' if kind == 'yjyg' else '业绩快报')


def _act_pledge(args, cfg):
    """股权质押: 逐股质押比例 / --profile 看全市场概况"""
    from prism.stock.bridge import ak_ext as _x
    if getattr(args, 'profile', False):
        rows = _x.pledge_profile()
        return _wrap(rows, '全市场质押概况', title='质押概况')
    date = getattr(args, 'date', None)
    rows = _x.pledge(date)
    code = _code(args)
    if code:
        rows = [r for r in rows if str(r.get('股票代码') or '')[-6:] == code]
    if not rows:
        raise _ak.AkFailed(f'{code or "全市场"} 无质押记录')
    n = int(getattr(args, 'limit', 50) or 50)
    # 上游这两列的单位是"万股/万元" (不是元), 直接按元折 亿 会差 1e4 倍
    for r in rows:
        mv, sh = to_float(r.get('质押市值')), to_float(r.get('质押股数'))
        if mv is not None:
            r['质押市值'] = f'{mv / 1e4:.2f}亿'
        if sh is not None:
            r['质押股数'] = f'{sh / 1e4:.2f}亿股'
        r.pop('无限售股质押数', None)
        r.pop('限售股质押数', None)
    return _wrap(rows[:n], _show(date) if date else '', title='质押比例')


def _act_lhb_stats(args, cfg):
    """龙虎榜统计口径 (个股/机构席位/营业部/游资)"""
    from prism.stock.bridge import ak_ext as _x
    kind = (getattr(args, 'stats', None) or 'stock').lower()
    span = getattr(args, 'span', None) or '近一月'
    rows = _x.lhb_stats(kind, span)
    if not rows:
        raise _ak.AkFailed(f'{span} 无{kind}统计')
    n = int(getattr(args, 'limit', 50) or 50)
    return _wrap(rows[:n], span, kind=kind,
                 title=_x._LHB_STATS.get(kind, _x._LHB_STATS['stock'])[1])


def _act_rating(args, cfg):
    """全市场机构评级/目标价"""
    from prism.stock.bridge import ak_ext as _x
    kind = getattr(args, 'kind', None) or '最新投资评级'
    rows = _x.rating(kind)
    n = int(getattr(args, 'limit', 50) or 50)
    return _wrap(rows[:n], kind, title='机构评级')


def _act_goodwill(args, cfg):
    """商誉规模 (减值风险面)"""
    from prism.stock.bridge import ak_ext as _x
    date = getattr(args, 'date', None)
    rows = _x.goodwill(date)
    code = _code(args)
    if code:
        rows = [r for r in rows if str(r.get('股票代码') or '')[-6:] == code]
    if not rows:
        raise _ak.AkFailed('无商誉记录')
    n = int(getattr(args, 'limit', 50) or 50)
    # 上游给的是小数比例 (0.0194), 统一折成百分数再出, 免得读成 0.02%
    for r in rows:
        for k, v in list(r.items()):
            if any(t in k for t in ('比例', '同比')) and isinstance(v, (int, float)) \
                    and abs(v) < 1:
                r[k] = round(v * 100, 2)
    return _wrap(rows[:n], _show(date) if date else '', title='商誉')


def _act_margin_ext(args, cfg):
    """两融: 默认原生当日列表; --detail 逐股明细 / --history 余额历史"""
    from prism.stock.bridge import ak_ext as _x
    from prism.stock.command._actions import _act_std
    detail = getattr(args, 'detail', False)
    history = getattr(args, 'history', False)
    if not (detail or history):
        code0 = _code(args)
        if not code0:
            return _act_std('stock_margin_list')(args, cfg)
        # 给了代码就是查这只票的两融明细: 上游明细按市场拆分 (sse/szse),
        # 直接把 600519 丢给市场级接口会拿到上游的 KeyError
        c = _ak.code6(code0)
        market = 'sse' if c[0] in '569' else 'szse'
        from prism.stock.engine.clients import prev_trading_day
        given = _ak.ymd(getattr(args, 'date', None)) if getattr(args, 'date', None) else None
        date = (given or _ak.ymd(prev_trading_day()) or _ak.ymd()).replace('-', '')
        rows = []
        # 两融 T+1 才发布, 当天必然是空表; 往前找 5 个交易日
        for step in range(5):
            if step:
                date = _ak._shift(date, -1)
            try:
                # 沪深列名不同: 沪市 '标的证券代码', 深市 '证券代码'
                rows = [r for r in _x.margin_detail(date, market)
                        if str(r.get('标的证券代码') or r.get('证券代码')) == c]
            except Exception:
                rows = []
            if rows:
                break
            if given:
                break
        if not rows:
            raise ValueError(f'{c} 无两融数据 (最近试到 {_show(date)})')
        return _wrap(rows, date)
    if history:
        rows = _x.margin_account()
        # 上游金额列的単位是亿元 (不是元), 标进列名后渲染层不再折一次
        for r in rows:
            for k, v in list(r.items()):
                if any(t in k for t in ('余额', '买入额', '卖出额', '偿还额')) \
                        and isinstance(v, (int, float)) and '亿' not in k:
                    r[k + '(亿)'] = r.pop(k)
        n = int(getattr(args, 'limit', 50) or 50)
        # 上游是 2012 年至今的正序, 要"最近 n 期"得取尾部
        return _wrap(rows[-n:], '两融余额/账户', title='两融余额历史')
    from prism.stock.engine.clients import prev_trading_day
    date = (getattr(args, 'date', None) or prev_trading_day() or _ak.ymd())
    market = (getattr(args, 'exchange', None) or 'sse').lower()
    # 当日明细要等交易所盘后披露, 且空表会让上游抛 Length mismatch: 往前找
    rows, used, tries = [], date, 0
    while tries < 5:
        try:
            # 上游只吃 YYYYMMDD, 带横线会静默回空表
            rows = _x.margin_detail(used.replace('-', ''), market)
        except Exception:                     # noqa: BLE001 上游空表
            rows = []
        if rows:
            break
        nxt = prev_trading_day(used)
        if not nxt or nxt == used:
            break
        used, tries = nxt, tries + 1
    date = used
    if not rows:
        raise _ak.AkFailed(f'{date} 前 5 个交易日无{market}两融明细')
    n = int(getattr(args, 'limit', 50) or 50)
    return _wrap(rows[:n], _show(date), market=market,
                 title=f'两融明细 ({market})')


def _act_valuation_ext(args, cfg):
    """估值: 默认个股历史分位; --market 看全市场 PE/PB 分位"""
    from prism.stock.bridge import ak_ext as _x
    from prism.stock.command._actions import _act_valuation as _native
    idx = getattr(args, 'index', None)
    if idx:
        rows = _x.index_value(idx, int(getattr(args, 'limit', 30) or 30))
        if not rows:
            raise _ak.AkFailed(f'{idx} 指数估值无数据')
        return _wrap(rows, title=f'{idx} 指数估值')
    if not getattr(args, 'market', False):
        return _native(args, cfg)
    rows = _x.market_valuation(int(getattr(args, 'limit', 60) or 60))
    if not rows:
        raise _ak.AkFailed('全市场估值序列为空')
    return _wrap(rows, '全市场 PE/PB', title='全市场估值分位')


# ── 第三批: 盘口异动 / 人气榜 / 回购 / 股本 / 公告流 / 宽度序列 / 板块即时 / 指数估值 / 流通股东

def _act_changes(args, cfg):
    """盘口异动 (大笔买入/封涨停/火箭发射...), 按时间倒序"""
    from prism.stock.bridge import ak_ext as _x
    kind = getattr(args, 'type_', None) or '大笔买入'
    n = int(getattr(args, 'limit', 50) or 50)
    rows = _x.changes(kind, n)
    if not rows:
        raise _ak.AkFailed(f'盘口异动无数据: {kind}')
    return _wrap(rows, title=f'盘口异动 · {kind}', kind=kind)

def _act_hot(args, cfg):
    """人气榜 / 百度热搜"""
    from prism.stock.bridge import ak_ext as _x
    kind = (getattr(args, 'kind', None) or 'rank').lower()
    n = int(getattr(args, 'limit', 50) or 50)
    if kind.startswith('baidu'):
        rows = _x.hot_baidu(getattr(args, 'date', None), n)
        return _wrap(rows, title='百度股市热搜', kind='baidu')
    rows = _x.hot_rank(n)
    if not rows:
        raise _ak.AkFailed('人气榜为空')
    return _wrap(rows, title='东财人气榜', kind='rank')

def _act_buyback(args, cfg):
    """全市场回购 (计划/进度/已回购), 按最新公告日倒序"""
    from prism.stock.bridge import ak_ext as _x
    n = int(getattr(args, 'limit', 50) or 50)
    pg = getattr(args, 'progress', None)
    rows = _x.buyback(n, pg)
    if not rows:
        raise _ak.AkFailed(f'回购无数据: {pg or "全部"}')
    return _wrap(rows, title=f'回购{' · ' + pg if pg else ''}')

def _act_shares(args, cfg):
    """股本结构变动 (股本单位折 亿股)"""
    from prism.stock.bridge import ak_ext as _x
    code = _code(args)
    if not code:
        raise _ak.AkFailed('股本结构需要股票代码')
    rows = _x.shares(code)
    if not rows:
        raise _ak.AkFailed(f'{code} 无股本结构数据')
    for r in rows:
        for k, v in list(r.items()):
            if '股' in k and isinstance(v, (int, float)) and '亿' not in k:
                r[k + '(亿股)'] = round(v / 1e8, 2)
                r.pop(k)
    return _wrap(rows, title=f'{code} 股本结构', code=code)

def _act_notice(args, cfg):
    """全市场公告流 (可按公告类型过滤)"""
    from prism.stock.bridge import ak_ext as _x
    n = int(getattr(args, 'limit', 50) or 50)
    kind = getattr(args, 'kind', None)
    rows = _x.notice(getattr(args, 'date', None), kind, n)
    if not rows:
        raise _ak.AkFailed('公告流为空')
    return _wrap(rows, title=f'公告流{' · ' + kind if kind else ''}')

def _act_breadth_ext(args, cfg):
    """市场宽度: 默认当日涨跌分布; --history 看创 20/60/120 日新高新低家数序列"""
    from prism.stock.bridge import ak_ext as _x
    from prism.stock.command._actions_ak import _act_breadth as _native
    if not getattr(args, 'history', False):
        return _native(args, cfg)
    n = int(getattr(args, 'limit', 30) or 30)
    rows = _x.high_low(n)
    if not rows:
        raise _ak.AkFailed('新高新低序列为空')
    return _wrap(rows, title='创新高/新低家数')

def _act_boards_ext(args, cfg):
    """板块: 默认东财行业+概念目录; --spot 看新浪行业板块即时行情"""
    from prism.stock.bridge import ak_ext as _x
    from prism.stock.command._actions import _act_boards as _native
    if not getattr(args, 'spot', False):
        return _native(args, cfg)
    rows = _x.sector_spot(int(getattr(args, 'limit', 50) or 50))
    if not rows:
        raise _ak.AkFailed('板块即时行情为空')
    return _wrap(rows, title='新浪行业板块即时')

def _act_holders_ext(args, cfg):
    """十大股东: 默认原生; --free 看十大流通股东 (季报, 未披露自动退一季)"""
    from prism.stock.bridge import ak_ext as _x
    from prism.stock.command._actions import _act_std
    if not getattr(args, 'free', False):
        return _act_std('stock_top_holders')(args, cfg)
    code = _code(args)
    if not code:
        raise _ak.AkFailed('十大流通股东需要股票代码')
    rows = _x.free_holders(code, getattr(args, 'date', None))
    if not rows:
        raise _ak.AkFailed(f'{code} 无流通股东数据')
    rows = rows[:int(getattr(args, 'limit', 10) or 10)]
    return _wrap(rows, title=f'{code} 十大流通股东', code=code)


# ── 第四批: 预约披露 / 分红送配 / 业绩报表 / 股东增减持 / 董监高变动

def _act_yysj(args, cfg):
    """财报预约披露日: 首次预约 + 三次变更 (改期=信号)"""
    from prism.stock.bridge import ak_ext as _x
    rows = _x.yysj(getattr(args, 'date', None),
                   getattr(args, 'scope', None) or '沪深A股',
                   int(getattr(args, 'limit', 200) or 200))
    if not rows:
        raise _ak.AkFailed('预约披露表为空')
    return _wrap(rows, title='财报预约披露日')

def _act_yjbb(args, cfg):
    """业绩报表: 营收/净利/同比/ROE, 默认按净利同比降序"""
    from prism.stock.bridge import ak_ext as _x
    rows = _x.yjbb(getattr(args, 'date', None),
                   int(getattr(args, 'limit', 100) or 100))
    if not rows:
        raise _ak.AkFailed('业绩报表为空')
    # 营收/净利是元, 直接印 1e10 级数字没法读; 同比是百分数, 不能一起折
    for r in rows:
        for k in list(r):
            if k.startswith(('营业总收入-营业总收入', '净利润-净利润')):
                v = r.pop(k)
                r[k + '(亿)'] = round(v / 1e8, 2) if isinstance(v, (int, float)) else v
    return _wrap(rows, title='业绩报表')

def _act_fhps(args, cfg):
    """分红送配明细: 送转比例 / 现金分红 / 股息率, 按股息率降序"""
    from prism.stock.bridge import ak_ext as _x
    rows = _x.fhps(getattr(args, 'date', None),
                   int(getattr(args, 'limit', 100) or 100))
    if not rows:
        raise _ak.AkFailed('分红送配表为空')
    # 上游股息率是小数比例 (0.0459), 折成百分数才和行情软件对得上
    for r in rows:
        v = r.pop('现金分红-股息率', None)
        if isinstance(v, (int, float)):
            r['股息率%'] = round(v * 100, 2)
    return _wrap(rows, title='分红送配明细')

def _act_ggcg(args, cfg):
    """股东增减持 (全市场快照缓存 12h), 可按代码过滤"""
    from prism.stock.bridge import ak_ext as _x
    code = _code(args)
    rows = _x.ggcg(code, int(getattr(args, 'limit', 100) or 100),
                   bool(getattr(args, 'refresh', False)))
    if not rows:
        raise _ak.AkFailed(f'{code or "全市场"} 无股东增减持记录')
    return _wrap(rows, title=f'股东增减持{' · ' + code if code else ''}')

def _act_mgmt(args, cfg):
    """董监高持股变动明细 (全市场快照缓存 12h)"""
    from prism.stock.bridge import ak_ext as _x
    code = _code(args)
    rows = _x.mgmt(code, int(getattr(args, 'limit', 100) or 100),
                   bool(getattr(args, 'refresh', False)))
    if not rows:
        raise _ak.AkFailed(f'{code or "全市场"} 无董监高变动记录')
    return _wrap(rows, title=f'董监高持股变动{' · ' + code if code else ''}')


# ── 域外: 期货 / 期权 / 基金 / 债券 / 港股

def _act_futures(args, cfg):
    """期货: 默认主力连续日线; --minute 切分钟, --realtime 看全合约, --inventory 看库存"""
    from prism.stock.bridge import ak_ext as _x
    n = int(getattr(args, 'limit', 60) or 60)
    rt = getattr(args, 'realtime', None)
    inv = getattr(args, 'inventory', None)
    if getattr(args, 'contracts', False):
        rows = _x.futures_contracts(getattr(args, 'date', None), n)
        if not rows:
            raise _ak.AkFailed('合约信息为空')
        return _wrap(rows, title='上期所合约信息', kind='contract')
    if rt:
        rows = _x.futures_rt(rt)
        return _wrap(rows, title=f'{rt} 实时合约', kind='rt')
    if inv:
        rows = _x.futures_inventory(inv, n)
        if not rows:
            raise _ak.AkFailed(f'{inv} 无库存数据')
        return _wrap(rows, title=f'{inv} 库存', kind='inv')
    code = (getattr(args, 'codes', None) or ['RB0'])[0]
    minute = int(getattr(args, 'minute', 0) or 0)
    rows = _x.futures(code, n, minute)
    if not rows:
        raise _ak.AkFailed(f'{code} 无行情')
    tag = f'{minute}分' if minute else '日线'
    return _wrap(rows, title=f'{code} {tag}', code=code,
                 kind='min' if minute else 'day')

def _act_option(args, cfg):
    """期权: 成交统计/希腊值/保证金/商品期权/龙虎榜"""
    from prism.stock.bridge import ak_ext as _x
    kind = (getattr(args, 'kind', None) or 'stats').lower()
    rows = _x.option(kind, getattr(args, 'date', None),
                     int(getattr(args, 'limit', 100) or 100),
                     getattr(args, 'symbol', None))
    if not rows:
        raise _ak.AkFailed(f'期权 {kind} 无数据')
    if kind == 'stats':
        # 上游总成交额单位是万元, 折亿才不至于看成 5 万
        for r in rows:
            v = r.pop('总成交额', None)
            if isinstance(v, (int, float)):
                r['总成交额(亿)'] = round(v / 1e4, 2)
    title = {'stats': '期权成交统计 (SSE)', 'greeks': '期权风险指标 (希腊值)',
             'margin': '期权保证金', 'comm': '商品期权行情',
             'lhb': '期权龙虎榜', 'contract': '期权合约列表'}.get(kind, kind)
    return _wrap(rows, title=title, kind=kind)

def _act_fund(args, cfg):
    """基金: 快照排行 / 重仓股 / 净值历史"""
    from prism.stock.bridge import ak_ext as _x
    n = int(getattr(args, 'limit', 50) or 50)
    hold = getattr(args, 'hold', None)
    if hold:
        rows = _x.fund_hold(hold, getattr(args, 'year', None), n)
        if not rows:
            raise _ak.AkFailed(f'{hold} 无重仓股数据')
        for r in rows:                       # 持股数=万股, 持仓市值=万元
            mk = r.pop('持仓市值', None)
            if isinstance(mk, (int, float)):
                r['持仓市值(亿)'] = round(mk / 1e4, 2)
            sk = r.pop('持股数', None)
            if isinstance(sk, (int, float)):
                r['持股数(万股)'] = sk
        return _wrap(rows, title=f'{hold} 重仓股', kind='hold')
    code = (getattr(args, 'codes', None) or [None])[0]
    if code:
        rows = _x.fund_nav(code, n)
        if not rows:
            raise _ak.AkFailed(f'{code} 无净值数据 (仅 ETF/LOF 有历史净值)')
        return _wrap(rows, title=f'{code} 净值走势', code=code, kind='nav')
    rows = _x.fund_top(n, getattr(args, 'order', 'desc') or 'desc')
    if not rows:
        raise _ak.AkFailed('基金净值快照为空')
    # 上游列名带日期 (2026-10-23-单位净值), 折成通用列名才能跨日复用
    import re
    for r in rows:
        for k in list(r):
            if re.match(r'^\d{4}-\d{2}-\d{2}-', str(k)):
                nk = re.sub(r'^\d{4}-\d{2}-\d{2}-', '', str(k))
                if nk in ('单位净值', '累计净值'):
                    r[nk] = r.pop(k)
                else:
                    r.pop(k)
    return _wrap(rows, title='基金净值排行', kind='top')

def _act_bond(args, cfg):
    """债券: 中债收益率曲线 / 中美国债 / 现券成交"""
    from prism.stock.bridge import ak_ext as _x
    kind = (getattr(args, 'kind', None) or 'yield').lower()
    rows = _x.bond(kind, int(getattr(args, 'limit', 50) or 50),
                   getattr(args, 'start', None), getattr(args, 'end', None))
    if not rows:
        raise _ak.AkFailed(f'债券 {kind} 无数据')
    if kind == 'summary':                    # 托管市值/面值单位已是亿元
        for r in rows:
            for k in ('托管市值', '托管面值'):
                v = r.pop(k, None)
                if isinstance(v, (int, float)):
                    r[k + '(亿)'] = v
    title = {'yield': '中债收益率曲线', 'us': '中美国债收益率',
             'summary': '上交所现券成交'}.get(kind, kind)
    return _wrap(rows, title=title, kind=kind)

def _act_hk(args, cfg):
    """港股实时快照"""
    from prism.stock.bridge import ak_ext as _x
    code = (getattr(args, 'codes', None) or [None])[0]
    rows = _x.hk_spot(code, int(getattr(args, 'limit', 50) or 50))
    if not rows:
        raise _ak.AkFailed(f'港股无数据: {code or "全部"}')
    return _wrap(rows, title=f'港股{' · ' + code if code else '实时快照'}')


# ── 按功能归类: 各命令的扩展口径 (--kind) ────────────────────────

def _fam_sig(name):
    """akshare 接口的真实签名 (拿不到就返回 None)"""
    import inspect
    try:
        import akshare as ak
    except Exception:
        return None
    f = getattr(ak, name, None)
    if f is None:
        return None
    try:
        return inspect.signature(f)
    except (TypeError, ValueError):
        return None


def _fam_code(args):
    """取命令的位置参数里的股票代码 (与 _code 同一套候选名)"""
    from prism.stock.command._common import subject_one
    return subject_one(args)


def _exchange_prefixed(code):
    """600519 → sh600519; 已带前缀/非 6 位返回 None"""
    import re as _re
    s = str(code or '').strip()
    if not _re.fullmatch(r'\d{6}', s):
        return None
    from prism.stock.engine.clients import to_symbol
    try:
        return to_symbol(s)
    except Exception:  # noqa: BLE001
        return None


def _act_fam(args, cfg):
    """调用某命令名下的扩展口径 (来自 akshare 目录)

    参数优先级: --arg k=v > 命令位置代码 > 接口默认值
    """
    from prism.stock.bridge import ak as _akb
    from prism.stock.bridge.ak_families import FAM
    from prism.stock.command._common import _args_dict
    family = getattr(args, 'family', None)
    kind = getattr(args, 'kind', None) or getattr(args, 'indicator', None)
    if family not in FAM:
        raise _ak.AkFailed(f'未知功能分类: {family}')
    from prism.stock.bridge.ak_resolve import resolve
    kind, spec = resolve(family, kind, _ak.AkFailed)

    if spec.get('st') == 'err':
        raise _ak.AkFailed(
            f"{spec['n']} 上游已失效 ({spec.get('msg') or '接口异常'}); "
            f"换同族其它口径: prism {family} --list")
    params = _args_dict(args)
    sig = _fam_sig(spec['n'])
    names = list(sig.parameters) if sig else []
    defaults = {k: v.default for k, v in sig.parameters.items()} if sig else {}
    has_kwargs = bool(sig and any(p.kind == p.VAR_KEYWORD for p in sig.parameters.values()))

    # 命令位置里的股票代码 (归一成 6 位)
    code = _fam_code(args)
    if code:
        try:
            code = _akb.code6(code)
        except ValueError:
            pass
    # 只按接口的"主参数"填值: 主参数是代码类就填代码, 是日期类就填日期
    primary = None
    for pn, pv in sig.parameters.items() if sig else ():
        if pv.kind in (pv.POSITIONAL_OR_KEYWORD, pv.KEYWORD_ONLY):
            primary = pn
            break
    code_like = ('symbol', 'stock', 'code', 'security', 'ts_code')
    if code and primary in code_like and primary not in params:
        params[primary] = code
    if primary == 'date' and 'date' not in params:
        d0 = str(defaults.get('date') or '')
        if len(d0) == 8 and d0[-4:] in ('0331', '0630', '0930', '1231'):
            params['date'] = _akb.quarter_end()
        else:
            params['date'] = _akb.ymd()
    win = None
    if primary in code_like:
        if 'start_date' in names and 'start_date' not in params:
            params['start_date'] = _akb._shift(_akb.ymd(), -365)
        if 'end_date' in names and 'end_date' not in params:
            params['end_date'] = _akb.ymd()
        if 'start_date' in params and 'end_date' in params:
            win = (params['start_date'], params['end_date'])
    elif 'start_date' in names or 'end_date' in names:
        # 区间型接口 (主参不是代码): 上游默认窗口可能是几年前的, 必须显式给
        win = _date_window(args, forward=spec['n'] in FORWARD_WINDOW)
        if 'start_date' in names and 'start_date' not in params:
            params['start_date'] = win[0]
        if 'end_date' in names and 'end_date' not in params:
            params['end_date'] = win[1]
    if names and not has_kwargs:
        from prism.stock.params import fit as _fit_params
        params = _fit_params(spec['n'], params, names=names)
    miss = [p for p in spec['r'] if p not in params]
    if miss:
        raise _ak.AkFailed(f"{family} --kind {kind} 缺少必填参数: {', '.join(miss)}")

    try:
        rows = _akb.rows(spec['n'], timeout=90, **params)
    except KeyError as e:
        # 东财部分接口 (十大股东等) 只认带交易所前缀的 symbol, 裸 6 位会
        # 拿到一份缺 key 的 JSON, 报出来是 KeyError: 'sdgd' 这种天书。
        # 同接口换带前缀的写法重试一次, 还不行就给出人话提示。
        alt = _exchange_prefixed(params.get('symbol'))
        if not alt or alt == params.get('symbol'):
            raise _ak.AkFailed(
                f"{spec['n']} 返回结构异常 (缺 {e}); "
                f"多半是参数写法不对, 试 --arg symbol={alt or 'sh600519'}"
                f" --arg date=20260630") from e
        params = dict(params, symbol=alt)
        rows = _akb.rows(spec['n'], timeout=90, **params)
    if not rows:
        raise _ak.AkFailed(f"{spec['n']} 返回空表")
    # 接口按报告期返回全市场时, 用位置代码挑出这只票; 该报告期没披露就往前找
    if code:
        rows = _fam_pick(rows, code)
        tries = 0
        while (not rows) and 'date' in names and tries < 4:
            params['date'] = _akb.prev_quarter(params['date'])
            tries += 1
            more = _akb.rows(spec['n'], timeout=90, **params)
            rows = _fam_pick(more, code) if more else []
        if not rows:
            raise _ak.AkFailed(
                f"{spec['n']} 在报告期 {params['date']} 附近没有 {code} 的数据; "
                f"用 --arg date=YYYYMMDD 指定报告期")
    n = int(getattr(args, 'limit', 50) or 50)
    extra = {'title': f'{family} · {kind}', 'family': family, 'kind': kind}
    if win:
        # 取数窗口必须出现在结果里: 榜单/区间类数据不带窗口, 用户没法判断
        # 看到的是哪一段 (这正是"静默返回过期数据"最难被发现的原因)
        extra['date'] = _span(win[0], win[1])
        extra['window'] = {'start': _show(win[0]), 'end': _show(win[1])}
    # 这个接口有没有更规整的专用命令? 有就告诉用户, 免得拿到裸字段自己加工
    try:
        from prism.stock.bridge.ak_via import INTERFACE_VIA
        cmd, flags = INTERFACE_VIA.get(spec['n'], (None, {}))
    except Exception:
        cmd = None
    if cmd:
        extra['note'] = (f'该接口有专用命令 prism {cmd} '
                          f'(字段做过筛选与单位折算, 更规整); '
                          f'这里透传的是上游原始字段')
    return _wrap(rows[:n], **extra)


def _fam_pick(rows, code):
    """结果里带代码列时, 只留目标股票"""
    code = str(code).strip()
    keys = ('代码', '股票代码', '证券代码', 'symbol', 'code',
            'SECURITY_CODE', 'SECUCODE', '证券编码', '股票编码')
    for k in keys:
        if not rows or k not in rows[0]:
            continue
        return [r for r in rows if code in str(r.get(k, '')).replace('.', '')]
    return rows


def _act_fam_list(args, cfg):
    """列出某命令名下的扩展口径"""
    from prism.stock.bridge.ak_families import FAM
    family = getattr(args, 'family', None)
    if family not in FAM:
        raise _ak.AkFailed(f'未知功能分类: {family}')
    from prism.stock.bridge.ak_resolve import groups
    _st = {'ok': '可用', 'empty': '需参数', 'err': '上游失效'}
    groups_map = groups(family)
    rows = []
    for g, ks in sorted(groups_map.items()):
        rows.append({'口径': f'[{g}]', '接口': f'{len(ks)} 个口径',
                     '参数': '', '必填': '', '类型': '组',
                     '状态': '', '说明': FAM[family][ks[0]].get('s') or ''})
        for k in ks:
            v = FAM[family][k]
            rows.append({'口径': k, '接口': v['n'],
                         '参数': ','.join(v['p']) or '-',
                         '必填': ','.join(v['r']) or '-',
                         '类型': '备用源' if v['role'] == 'fallback' else '扩展口径',
                         '状态': _st.get(v.get('st'), '未测'),
                         '说明': v['s']})
    return _wrap(rows, title=f'{family} 可用的扩展口径 ({len(FAM[family])} 个 / '
                              f'{len(groups_map)} 组)')

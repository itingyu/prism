"""akshare 扩展数据集 —— 情绪/业绩/风险/两融/估值/评级

第二批接入: 每个函数只做"取数 + 排序/合并", 归一与出网复用 bridge.ak。
拆成独立模块是为了让 ak.py 保持"核心行情/事件"职责, 免得单文件继续膨胀。
"""
from prism.stock.bridge.ak import _tail
from prism.stock.bridge.ak import rows
from prism.stock.bridge.ak import ymd
from prism.util.num import sort_rows, to_float

# ── 情绪 / 业绩 / 风险 / 两融 / 估值 / 评级 ──────────────────────────

def comment(top: int = 50, key: str = '综合得分', desc: bool = True) -> list:
    """千股千评: 全市场综合得分/关注度/主力控盘 (5198 行, 4.4s)"""
    data = rows('stock_comment_em', timeout=40)
    if key and key in (data[0] if data else {}):
        data = sort_rows(data, key, desc=desc)
    # 排序后要"前 top 条" (tail 会拿到底部 = 得分最低的一批)
    return data[:top] if top else data


def yjyg(date: str, kind: str = 'yjyg') -> list:
    """业绩预告 (yjyg) / 业绩快报 (yjkb), 按报告期取"""
    func = 'stock_yjyg_em' if kind == 'yjyg' else 'stock_yjkb_em'
    return rows(func, date=date, timeout=40)


def pledge(date: str = None) -> list:
    """逐股质押比例 (2218 行)

    必须显式传日期: 上游默认值停在 2024 年的老快照, 不传会拿到两年前的数据。
    """
    if date:
        return rows('stock_gpzy_pledge_ratio_em', date=date, timeout=30)
    # 非交易日/当日还没更新时上游回 null, 往前找最多 7 天取最近一期
    from prism.stock.bridge.ak import _shift
    d = ymd()
    for _ in range(8):
        try:
            got = rows('stock_gpzy_pledge_ratio_em', date=d, timeout=30)
        except Exception:                     # noqa: BLE001 上游 null
            got = []
        if got:
            return got
        d = _shift(d, -1)
    return []


def pledge_profile() -> list:
    """全市场质押概况 (按交易日的总质押比例/公司数/市值)"""
    return rows('stock_gpzy_profile_em', timeout=30)


_LHB_STATS = {
    'stock': ('stock_lhb_stock_statistic_em', '个股上榜统计'),
    'jg': ('stock_lhb_jgstatistic_em', '机构席位统计'),
    'yyb': ('stock_lhb_yybph_em', '营业部排行'),
    'trader': ('stock_lhb_traderstatistic_em', '游资统计'),
}


def lhb_stats(kind: str = 'stock', span: str = '近一月') -> list:
    """龙虎榜统计口径: 个股/机构席位/营业部/游资"""
    func = _LHB_STATS.get(kind, _LHB_STATS['stock'])[0]
    return rows(func, symbol=span, timeout=40)


def margin_account() -> list:
    """两融余额与账户数历史 (3413 行)"""
    return rows('stock_margin_account_info', timeout=40)


def margin_detail(date: str, market: str = 'sse') -> list:
    """逐股两融明细 (沪/深各 2000 行)"""
    func = {'sse': 'stock_margin_detail_sse',
            'szse': 'stock_margin_detail_szse'}.get(str(market).lower(),
                                                    'stock_margin_detail_sse')
    return rows(func, date=date, timeout=40)


def market_valuation(days: int = 250) -> list:
    """全市场 PE/PB 分位序列 (乐咕挂掉后的替代: a_ttm_lyr + a_all_pb 按日合并)"""
    pe = rows('stock_a_ttm_lyr', timeout=40)
    pb = rows('stock_a_all_pb', timeout=40)
    by_date = {}
    for r in pe:
        d = str(r.get('date'))[:10]
        by_date.setdefault(d, {})['date'] = d
        by_date[d]['PE中位'] = r.get('middlePETTM')
        by_date[d]['PE等权'] = r.get('averagePETTM')
        by_date[d]['PE分位%'] = _pct(r.get('quantileInAllHistoryMiddlePeTtm'))
    for r in pb:
        d = str(r.get('date'))[:10]
        by_date.setdefault(d, {})['date'] = d
        by_date[d]['PB中位'] = r.get('middlePB')
        by_date[d]['PB分位%'] = _pct(r.get('quantileInAllHistoryMiddlePB'))
    out = [v for k, v in sorted(by_date.items())]
    return _tail(out, days)


_RATING_ALIAS = {
    '最新': '最新投资评级', '评级': '最新投资评级',
    '上调': '上调评级股票', '下调': '下调评级股票',
    '首次': '首次评级股票', '综合': '股票综合评级',
    '目标价': '目标涨幅排名', '目标涨幅': '目标涨幅排名',
    '机构关注': '机构关注度', '行业关注': '行业关注度',
    '选股': '投资评级选股',
}


def rating(kind: str = '最新投资评级') -> list:
    """全市场机构评级/目标价 (新浪, 4082 行)

    上游的 symbol 必须是它左菜单里的原文 (最新投资评级/上调评级股票/...),
    这里做一层中文短名映射, 免得用户记不住 "股票" 后缀。
    """
    sym = _RATING_ALIAS.get(str(kind).strip(), kind)
    return rows('stock_institute_recommend', symbol=sym, timeout=40)


def goodwill(date: str = None) -> list:
    """商誉 (减值风险面), 按报告期取"""
    kw = {'date': date} if date else {}
    return rows('stock_sy_em', timeout=30, **kw)




def _pct(v):
    try:
        return round(float(v) * 100, 1) if v is not None and float(v) <= 1.5 else v
    except (TypeError, ValueError):
        return v


# ── 第三批: 盘口异动 / 人气 / 回购 / 股本 / 公告流 / 市场宽度 / 板块 / 指数估值 / 流通股东

_CHANGES = ('大笔买入', '大笔卖出', '封涨停板', '封跌停板', '打开涨停板',
            '打开跌停板', '火箭发射', '快速反弹', '高台跳水', '加速下跌',
            '竞价上涨', '竞价下跌', '向上缺口', '向下缺口', '60日新高',
            '60日新低', '60日大幅上涨', '60日大幅下跌')


def changes(kind: str = '大笔买入', top: int = 50) -> list:
    """盘口异动 (大笔买入/封涨停/火箭发射...), 返回最新 top 条"""
    if kind not in _CHANGES:
        raise ValueError(f'不支持的异动类型: {kind}; 可用: {"/".join(_CHANGES)}')
    data = rows('stock_changes_em', symbol=kind, timeout=30)
    return sorted(data, key=lambda r: str(r.get('时间') or ''), reverse=True)[:top]


def hot_rank(top: int = 50) -> list:
    """东财人气榜 (100 只)"""
    return rows('stock_hot_rank_em', timeout=30)[:top]


def hot_baidu(date: str = None, top: int = 20) -> list:
    """百度股市热搜 (A股), 按综合热度降序"""
    from prism.stock.bridge.ak import _shift
    d = date or ymd()
    got = []
    for _ in range(4):
        try:
            got = rows('stock_hot_search_baidu', symbol='A股', date=d,
                       time='今日', timeout=30)
        except Exception:                     # noqa: BLE001 非交易日回空
            got = []
        if got:
            break
        d = _shift(d, -1)
    return sort_rows(got, '综合热度')[:top]


def buyback(top: int = 50, progress: str = None) -> list:
    """回购 (5599 条); 默认按最新公告日倒序, 可按进度筛 (如 实施中/完成)"""
    data = rows('stock_repurchase_em', timeout=60)
    if progress:
        data = [r for r in data if progress in str(r.get('实施进度') or '')]
    data = sorted(data, key=lambda r: str(r.get('最新公告日期') or ''), reverse=True)
    return data[:top]


def shares(code: str) -> list:
    """股本结构变动 (总股本/流通/限售)"""
    c = code[-6:]
    return rows('stock_zh_a_gbjg_em', symbol=c, timeout=30)


def notice(date: str = None, kind: str = None, top: int = 50) -> list:
    """全市场公告流 (1825 条/日), 可按公告类型过滤"""
    from prism.stock.bridge.ak import _shift
    d = date or ymd()
    got = []
    for _ in range(4):
        try:
            got = rows('stock_notice_report', symbol='全部', date=d, timeout=40)
        except Exception:                     # noqa: BLE001
            got = []
        if got:
            break
        d = _shift(d, -1)
    if kind:
        got = [r for r in got if kind in str(r.get('公告类型') or '')]
    return got[:top]


def high_low(top: int = 30) -> list:
    """创新高/新低家数序列 (20/60/120 日口径), 判情绪冰点的连续量"""
    data = rows('stock_a_high_low_statistics', symbol='all', timeout=30)
    return data[-top:]


def sector_spot(top: int = 50) -> list:
    """新浪行业板块即时行情 (49 个板块)"""
    data = rows('stock_sector_spot', indicator='新浪行业', timeout=30)
    return sort_rows(data, '涨跌幅')[:top]


def index_value(code: str = '000300', top: int = 20) -> list:
    """中证指数估值 (PE/股息率), 上游约滞后一个月"""
    data = rows('stock_zh_index_value_csindex', symbol=code[-6:], timeout=30)
    # 上游正序; 展示统一成"最近在前"
    return list(reversed(data[-top:]))


def _prev_q(d: str) -> str:
    y, m = int(d[:4]), int(d[4:6])
    m -= 3
    if m <= 0:
        y, m = y - 1, m + 12
    return f'{y}{m:02d}{30 if m in (6, 9) else 31}'


def free_holders(code: str, date: str = None) -> list:
    """十大流通股东 (季报口径); date 形如 20260630, 未披露则往前退一季"""
    from prism.stock.bridge.ak import quarter_end
    sym = code[-6:]
    sym = ('sh' if sym[0] == '6' else 'sz') + sym
    d = date or quarter_end()
    last = None
    for _ in range(5):
        try:
            got = rows('stock_gdfx_free_top_10_em', symbol=sym, date=d, timeout=30)
        except Exception as e:                # noqa: BLE001 该季未披露
            last, got = e, []
        if got:
            return got
        d = _prev_q(d)
    raise last or ValueError(f'{code} 近 5 季无流通股东数据')


# ── 第四批: 预约披露 / 分红送配 / 业绩报表 / 高管增减持 / 董监高明细

def _cache_dir():
    import os
    d = os.path.expanduser('~/.prism/cache')
    os.makedirs(d, exist_ok=True)
    return d


def _cached(key: str, ttl: int, fetch, refresh: bool = False) -> list:
    """全量快照类接口 (高管增减持 120s+/17 万行) 落盘缓存, 默认 12 小时有效

    用 gzip 存 —— 17 万行 JSON 明文 160MB, 压完 ~25MB。
    """
    import gzip
    import json
    import os
    import time
    p = os.path.join(_cache_dir(), key + '.json.gz')
    if not refresh:
        try:
            if time.time() - os.stat(p).st_mtime < ttl:
                with gzip.open(p, 'rt', encoding='utf-8') as f:
                    return json.load(f)
        except (OSError, ValueError):
            pass
    data = fetch()
    try:
        tmp = p + '.tmp'
        with gzip.open(tmp, 'wt', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, p)
    except OSError:
        pass
    return data


def yysj(period: str = None, scope: str = '沪深A股', top: int = 200) -> list:
    """财报预约披露日 (首次预约 + 三次变更), 按预约时间升序"""
    from prism.stock.bridge.ak import quarter_end
    d = ymd(period) if period else quarter_end()
    data = rows('stock_yysj_em', symbol=scope, date=d, timeout=90)
    return sorted(data, key=lambda r: str(r.get('首次预约时间') or ''))[:top]


def fhps(period: str = None, top: int = 100) -> list:
    """分红送配明细 (送转/现金分红/股息率/除权除息日)"""
    from prism.stock.bridge.ak import quarter_end
    d = ymd(period) if period else quarter_end()
    data = rows('stock_fhps_em', date=d, timeout=40)
    return sort_rows(data, '现金分红-股息率')[:top]


def yjbb(period: str = None, top: int = 100) -> list:
    """业绩报表 (营收/净利/同比/ROE), 按净利同比降序"""
    from prism.stock.bridge.ak import quarter_end
    d = ymd(period) if period else quarter_end()
    data = rows('stock_yjbb_em', date=d, timeout=90)
    key = next((k for k in data[0] if '净利润-同比增长' in str(k)), None)
    return sort_rows(data, key)[:top]


def ggcg(code: str = None, top: int = 100, refresh: bool = False) -> list:
    """股东增减持 (全市场, 上游 120s/14.7 万行 → 落盘缓存 12h)"""
    data = _cached('ggcg', 43200,
                   lambda: rows('stock_ggcg_em', symbol='全部', timeout=300), refresh)
    if code:
        data = [r for r in data if str(r.get('代码') or '')[-6:] == code[-6:]]
    return data[:top]


def mgmt(code: str = None, top: int = 100, refresh: bool = False) -> list:
    """董监高持股变动明细 (上游 230s/17 万行 → 落盘缓存 12h)"""
    data = _cached('mgmt', 43200,
                   lambda: rows('stock_hold_management_detail_em', timeout=360), refresh)
    if code:
        data = [r for r in data if str(r.get('代码') or '')[-6:] == code[-6:]]
    return data[:top]


# ── 域外: 期货 / 期权 / 基金 / 债券 / 港股 / 美国宏观

_FUT_BARS = ('date', 'open', 'high', 'low', 'close', 'volume', 'hold', 'settle')


def _fut_norm(r: dict) -> dict:
    if '日期' in r or 'date' not in r:
        return r
    return {('日期' if k == 'date' else '开盘价' if k == 'open' else
             '最高价' if k == 'high' else '最低价' if k == 'low' else
             '收盘价' if k == 'close' else '成交量' if k == 'volume' else
             '持仓量' if k == 'hold' else '结算价' if k == 'settle' else k): v
            for k, v in r.items()}


def futures(code: str = 'RB0', top: int = 60, minute: int = 0) -> list:
    """期货日线 (主力连续); minute=1/5/15/30/60 切分钟线"""
    if minute:
        data = rows('futures_zh_minute_sina', symbol=code, period=str(minute),
                    timeout=40)
        data = [dict(r, 日期=r.get('datetime')) for r in data]
    else:
        try:
            data = rows('futures_main_sina', symbol=code, timeout=40)
        except Exception:                     # noqa: BLE001 非主力代码走通用日线
            data = rows('futures_zh_daily_sina', symbol=code, timeout=40)
    return [_fut_norm(r) for r in data[-top:]]


def futures_rt(name: str = '螺纹钢') -> list:
    """期货实时 (按中文品种名, 返回该品种全部活跃合约)"""
    return rows('futures_zh_realtime', symbol=name, timeout=40)


def futures_inventory(name: str = '螺纹钢', top: int = 30) -> list:
    """期货库存 (交易所仓单), 看累库/去库"""
    data = rows('futures_inventory_em', symbol=name, timeout=40)
    return sorted(data, key=lambda r: str(r.get('日期') or ''))[-top:]


def futures_contracts(date: str = None, top: int = 200) -> list:
    """上期所合约信息 (上市/到期/交割日)"""
    from prism.stock.bridge.ak import _shift
    d = date or ymd()
    got = []
    for _ in range(5):
        try:
            got = rows('futures_contract_info_shfe', date=d, timeout=40)
        except Exception:                     # noqa: BLE001 非交易日回退
            got = []
        if got:
            break
        d = _shift(d, -1)
    return got[:top]


def option(kind: str = 'stats', date: str = None, top: int = 100,
           symbol: str = None) -> list:
    """期权: stats(SSE 成交统计)/greeks(风险指标)/margin(保证金)/comm(商品期权)/lhb(龙虎榜)/contract(合约)"""
    from prism.stock.bridge.ak import _shift
    if kind == 'margin':
        return rows('option_margin', timeout=40)[:top]
    if kind == 'comm':
        return rows('option_comm_info', timeout=40)[:top]
    if kind == 'lhb':
        return rows('option_lhb_em', timeout=40)[:top]
    if kind == 'contract':
        return rows('option_commodity_contract_sina',
                    symbol=symbol or '白糖期权', timeout=40)
    d = date or ymd()
    for _ in range(5):
        try:
            if kind == 'greeks':
                got = rows('option_risk_indicator_sse', date=d, timeout=40)
            else:
                got = rows('option_daily_stats_sse', date=d, timeout=40)
        except Exception:                     # noqa: BLE001 非交易日回退
            got = []
        if got:
            return got[:top]
        d = _shift(d, -1)
    return []


def fund_top(top: int = 50, order: str = 'desc') -> list:
    """公募基金当日净值快照 (2.4 万只), 按日增长率排序"""
    data = rows('fund_open_fund_daily_em', timeout=60)
    key = next((k for k in data[0] if '日增长率' in str(k)), None)
    data = sort_rows(data, key, desc=(order != 'asc'))
    return data[:top]


def fund_hold(code: str, year: str = None, top: int = 50) -> list:
    """基金重仓股 (按季), year 形如 2025"""
    y = year or str(ymd())[:4]
    return rows('fund_portfolio_hold_em', symbol=code[-6:], date=y, timeout=40)[:top]


def fund_nav(code: str, top: int = 60) -> list:
    """ETF/LOF 历史净值走势 (东财; 场外基金接口依赖 v8 引擎, 本机不可用)"""
    data = rows('fund_etf_fund_info_em', fund=code[-6:],
                start_date='20200101', end_date=ymd(), timeout=60)
    return data[-top:]


def bond(kind: str = 'yield', top: int = 50, start: str = None, end: str = None) -> list:
    """债券: yield(中债收益率曲线)/us(中美国债对比)/summary(上交所现券成交)"""
    from prism.stock.bridge.ak import _shift
    if kind == 'us':
        data = rows('bond_zh_us_rate', timeout=60)
        return data[-top:]
    if kind == 'summary':
        d = ymd()
        for _ in range(5):
            try:
                got = rows('bond_cash_summary_sse', date=d, timeout=40)
            except Exception:                 # noqa: BLE001
                got = []
            if got:
                return got[:top]
            d = _shift(d, -1)
        return []
    e = ymd(end) if end else ymd()
    s = ymd(start) if start else _shift(e, -40)
    data = rows('bond_china_yield', start_date=s, end_date=e, timeout=60)
    return data[-top:]


def hk_spot(code: str = None, top: int = 50) -> list:
    """港股实时快照 (2810 只; 可传代码/名称过滤)"""
    data = rows('stock_hk_spot', timeout=60)
    if code:
        c = str(code)
        hit = [r for r in data if c in str(r.get('代码') or '')
               or c in str(r.get('中文名称') or '')]
        if hit:
            return hit[:top]
    return data[:top]

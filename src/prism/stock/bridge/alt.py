"""替代数据源: baostock + adata (都免费, 免 token)

分工:
  - baostock: 日/周/月 K 线 (前/后/不复权), 利润·成长·杜邦, 行业分类,
    分红送配, 指数成分, 交易日历。可用性最好 —— 无 token、无频控。
  - adata: K 线 (不复权), 只做 K 线链最后一层兜底; 其余接口本机实测不可用
    , 不在这里包一层假的可用性。

不放进来的: mootdx (能握手, 服务端返回 0 行), yfinance (Yahoo 429),
qstock (py_mini_racer 只有 glibc 版 .so, musl 载不进来)。
"""
import contextlib
import io
import time

_BS_OK = None          # None=未探测 / True=可用
_AD_OK = None


def _spec(name: str) -> bool:
    try:
        import importlib.util
        return importlib.util.find_spec(name) is not None
    except Exception:                                   # noqa: BLE001
        return False


def available(lib: str = 'baostock') -> bool:
    global _BS_OK, _AD_OK
    if lib == 'baostock':
        if _BS_OK is None:
            _BS_OK = _spec('baostock')
        return _BS_OK
    if lib == 'adata':
        if _AD_OK is None:
            _AD_OK = _spec('adata')
        return _AD_OK
    return False


def _code(code: str) -> str | None:
    """6 位代码 -> baostock 的 sh./sz. 前缀; 北交所 baostock 不覆盖"""
    c = str(code).strip().split('.')[0][-6:]
    if len(c) != 6 or not c.isdigit():
        return None
    # 9 开头不全是沪市: 900xxx 是沪 B, 920xxx 是北交所 (baostock 无北交所)
    if c.startswith('920') or c[0] in '48':
        return None
    if c[0] == '6' or c.startswith('900'):
        return f'sh.{c}'
    if c[0] in '023':
        return f'sz.{c}'
    return None


@contextlib.contextmanager
def _quiet():
    """baostock 往 stdout 打 "login success!", 会把 CLI 结果挤花"""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        yield


def _bs():
    import baostock as bs
    with _quiet():
        bs.login()
    return bs


def _rows(rs) -> list[dict]:
    fields = rs.fields
    out = []
    while True:
        got = rs.next()
        if not got:
            break
        row = rs.get_row_data()
        out.append(dict(zip(fields, row)))
    return out


def kline(code: str, period: str = 'day', count: int = 120,
          adjust: str = 'qfq') -> dict:
    """baostock 日/周/月 K 线, 形状对齐原生源 (klines = [日期,开,收,高,低,量])"""
    sym = _code(code)
    if not sym:
        raise RuntimeError(f'baostock 不支持该代码: {code}')
    freq = {'day': 'd', 'week': 'w', 'month': 'm'}.get(period, 'd')
    flag = {'qfq': '2', 'hfq': '1', '': '3', None: '3'}.get(adjust, '2')
    bs = _bs()
    try:
        start = time.strftime('%Y-%m-%d',
                              time.localtime(time.time() - max(count, 30) * 3 * 86400))
        rs = bs.query_history_k_data_plus(
            sym, 'date,open,high,low,close,volume', start_date=start,
            frequency=freq, adjustflag=flag)
        data = _rows(rs)
    finally:
        with _quiet():
            bs.logout()
    keep = [r for r in data if r.get('open') and float(r['open']) > 0]
    keep = keep[-count:]
    if not keep:
        raise RuntimeError(f'baostock 无 {code} K 线')
    return {'symbol': sym, 'period': period, 'fq': adjust,
            'klines': [[r['date'], r['open'], r['close'], r['high'],
                        r['low'], r['volume']] for r in keep],
            'count': len(keep)}


def adata_kline(code: str, period: str = 'day', count: int = 120) -> dict:
    """adata K 线 (只有不复权日线), 形状同上"""
    import adata
    c = str(code).strip().split('.')[0][-6:]
    # 不给 start_date 时上游会回空表 (默认区间与实际数据错位), 显式按 count 倒推
    start = time.strftime('%Y-%m-%d',
                          time.localtime(time.time() - max(count, 30) * 3 * 86400))
    df = adata.stock.market.get_market(stock_code=c, start_date=start,
                                       k_type=1, adjust_type=1)
    rows = df.tail(count).to_dict('records')
    if not rows:
        raise RuntimeError(f'adata 无 {c} K 线')
    return {'symbol': c, 'period': period, 'fq': '',
            'klines': [[str(r['trade_date']), f"{r['open']}", f"{r['close']}",
                        f"{r['high']}", f"{r['low']}", f"{r['volume']}"]
                       for r in rows],
            'count': len(rows)}


# ── 财务 (baostock) ────────────────────────────────────────────────
# 字段名是上游的 camelCase, 这里翻成中文并统一单位 (比率 x100 成百分数)
_DUPONT = [('dupontROE', 'ROE%', 100), ('dupontPnitoni', '净利率%', 100),
           ('dupontAssetTurn', '资产周转率', 1),
           ('dupontAssetStoEquity', '权益乘数', 1),
           ('dupontNitogr', '经营利润率(EBIT/营收)%', 100),
           ('dupontTaxBurden', '税负率%', 100),
           ('dupontIntburden', '利息负担%', 100),
           ('dupontEbittogr', 'EBIT利润率%', 100)]
_GROWTH = [('YOYEquity', '净资产同比%', 100), ('YOYAsset', '总资产同比%', 100),
           ('YOYNI', '净利润同比%', 100), ('YOYEPSBasic', '基本EPS同比%', 100),
           ('YOYPNI', '归母净利同比%', 100)]
_PROFIT = [('roeAvg', 'ROE(平均)%', 100), ('npMargin', '销售净利率%', 100),
           ('gpMargin', '销售毛利率%', 100),
           ('netProfit', '净利润(元)', 1), ('epsTTM', 'EPS(TTM)', 1),
           ('MBRevenue', '主营收入(元)', 1)]

_KINDS = {'dupont': ('query_dupont_data', _DUPONT, '杜邦拆解'),
          'growth': ('query_growth_data', _GROWTH, '成长能力'),
          'profit': ('query_profit_data', _PROFIT, '利润率')}


def fin_series(code: str, kind: str = 'dupont', quarters: int = 8) -> dict:
    """按季取财务, 返回 {title, rows:[{报告期, ...指标}]} (最旧 -> 最新)

    baostock 一次只给一个季度, 所以按"上一个已披露季度"往前推 quarters 期。
    """
    import datetime
    sym = _code(code)
    if not sym:
        raise RuntimeError(f'baostock 不支持该代码: {code}')
    fn, fields, title = _KINDS[kind]
    bs = _bs()
    out = []
    try:
        today = datetime.date.today()
        y, q = today.year, (today.month - 1) // 3 + 1
        for _ in range(quarters):
            q -= 1
            if q == 0:
                y, q = y - 1, 4
            rs = getattr(bs, fn)(code=sym, year=y, quarter=q)
            for r in _rows(rs):
                if not r.get('statDate'):
                    continue
                item = {'报告期': r['statDate']}
                for k, label, mul in fields:
                    v = r.get(k)
                    if v in (None, ''):
                        continue
                    try:
                        item[label] = round(float(v) * mul, 2)
                    except ValueError:
                        continue
                out.append(item)
    finally:
        with _quiet():
            bs.logout()
    if not out:
        raise RuntimeError(f'baostock 无 {code} 的 {title} 数据')
    return {'title': title, 'rows': out}


def dividend(code: str, years: int = 5) -> list:
    """个股分红送配历史 (baostock, 按年度报告口径)"""
    import datetime
    sym = _code(code)
    if not sym:
        raise RuntimeError(f'baostock 不支持该代码: {code}')
    bs = _bs()
    keys = ['code', 'dividPreNoticeDate', 'dividAgmPumDate', 'dividPlanAnnounceDate',
            'dividPlanDate', 'dividRegistDate', 'dividOperateDate', 'dividPayDate',
            'dividStockMarketDate', 'dividCashPsBeforeTax', 'dividCashPsAfterTax',
            'dividStocksPs', 'dividCashStock', 'dividReserveToStockPs']
    out = []
    try:
        year = datetime.date.today().year
        for y in range(year, year - years, -1):
            rs = bs.query_dividend_data(code=sym, year=str(y), yearType='report')
            for r in _rows(rs):
                if not any(r.get(k) for k in ('dividCashPsBeforeTax', 'dividStocksPs')):
                    continue
                out.append({k: r.get(k, '') for k in keys if r.get(k, '') != ''})
    finally:
        with _quiet():
            bs.logout()
    return out


def industry(code: str) -> dict | None:
    """证监会行业分类 (baostock), 作为行业归属的兜底源"""
    sym = _code(code)
    if not sym:
        return None
    bs = _bs()
    try:
        rs = bs.query_stock_industry(code=sym)
        rows = _rows(rs)
    finally:
        with _quiet():
            bs.logout()
    return (rows[0] if rows else None) or None


def constituents(name: str = 'hs300') -> list:
    """指数成分 (baostock): hs300 / zz500 / sz50"""
    fn = {'hs300': 'query_hs300_stocks', 'zz500': 'query_zz500_stocks',
          'sz50': 'query_sz50_stocks'}.get(str(name).lower())
    if not fn:
        raise RuntimeError(f'baostock 无该指数成分: {name} (hs300/zz500/sz50)')
    bs = _bs()
    try:
        rows = _rows(getattr(bs, fn)())
    finally:
        with _quiet():
            bs.logout()
    return rows

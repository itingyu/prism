"""akshare 数据源 —— 原生接口取不到的事件/宏观数据, 兼部分动作的备用源

akshare 只当"取数函数库"用: 出网仍走 prism 的指纹通道 (`net.pyshim`), 所以
反爬、代理、限流与其他命令是同一套策略, 业务侧不需要另配网络。

本模块只做三件事:
  - 归一参数 (日期 20261023 / 2026-10-23 都认; 代码去市场前缀)
  - 调函数并把 DataFrame 转成 `list[dict]` (保留 akshare 的中文列名 ——
    与原生源的口径一致, 调用方不必做第二套字段映射)
  - 把异常转成带函数名的错误, 不吞掉上游原因

可用性: `available()`。akshare 没装时调用方退到原生源, 不报"功能不存在"。

数据集选择标准 (2026-10 实测, 见 `DATASETS`):
  只登记实测可取数的函数。东财 push2 的"全市场列表"类接口 (stock_*_spot_em /
  board_*_name_em / index_zh_a_hist) 在本机被上游直接掐连, 不登记;
  原生源已有等效能力的不重复登记。
"""
import importlib.util
import time

_TIMEOUT = 20
_PACE_MS = 120

class AkUnavailable(RuntimeError):
    """akshare 未安装 / 不可导入"""

class AkFailed(RuntimeError):
    """调用成功但结果为空或形状不对"""

def available() -> bool:
    """akshare 能不能用。只查模块存在, 不 import (import 要 1-2 秒)"""
    try:
        return importlib.util.find_spec('akshare') is not None
    except (ImportError, ValueError):
        return False

# ── 参数归一 ────────────────────────────────────────────────────
def ymd(d=None) -> str:
    """任意日期写法 → 'YYYYMMDD'; 缺省今天"""
    if d in (None, '', 'today', 'now'):
        return time.strftime('%Y%m%d')
    s = str(d).strip().replace('-', '').replace('/', '')
    if len(s) == 8 and s.isdigit():
        return s
    raise ValueError(f'日期不合法: {d} (要 YYYY-MM-DD 或 YYYYMMDD)')

def code6(code) -> str:
    """'sh600519' / '600519.SH' / '600519' → '600519'"""
    s = str(code or '').strip().lower()
    for pre in ('sh', 'sz', 'bj', 'hk', 'us'):
        if s.startswith(pre) and s[len(pre):].isdigit():
            s = s[len(pre):]
            break
    s = s.split('.')[0]
    if not s.isdigit():
        raise ValueError(f'代码不合法: {code} (要 6 位数字)')
    return s

def quarter_end(d=None) -> str:
    """最近一个已结束的报告期末 (YYYYMMDD) —— 业绩预告/快报按报告期取数"""
    t = time.localtime()
    y, m = t.tm_year, t.tm_mon
    if m <= 3:
        return f'{y - 1}1231'
    if m <= 6:
        return f'{y}0331'
    if m <= 9:
        return f'{y}0630'
    return f'{y}0930'


def prev_quarter(d: str) -> str:
    """报告期 (YYYYMMDD, 0331/0630/0930/1231) 往前推一个季度"""
    s = str(d)
    y, m = int(s[:4]), int(s[4:6])
    if m == 3:
        return f'{y - 1}1231'
    if m == 6:
        return f'{y}0331'
    if m == 9:
        return f'{y}0630'
    if m == 12:
        return f'{y}0930'
    raise ValueError(f'不是报告期日期: {d}')


def _shift(d: str, days: int) -> str:
    """YYYYMMDD 加减自然日"""
    import datetime as _dt
    t = _dt.datetime.strptime(d, '%Y%m%d') + _dt.timedelta(days=days)
    return t.strftime('%Y%m%d')

# ── 调用 ────────────────────────────────────────────────────────
def rows(func: str, timeout: int = _TIMEOUT, **params) -> list:
    """调 akshare 函数, 返回 list[dict]; 空结果抛 AkFailed"""
    from prism.net.pyshim import call_py
    if not available():
        raise AkUnavailable('akshare 未安装 (pip install akshare)')
    t0 = time.time()
    # akshare 内部会打 tqdm 进度条和 pandas FutureWarning 到 stderr ——
    # 那不是我们的输出, 会把 CLI 结果淹掉, 取数期间统一吞掉
    import contextlib
    import io
    with contextlib.redirect_stderr(io.StringIO()):
        r = call_py(f'akshare.{func}', params, timeout=timeout, pace_ms=_PACE_MS)
    if r.get('kind') != 'dataframe':
        raise AkFailed(f'{func} 返回非表格结果: {str(r.get("value"))[:120]}')
    data = _clean(_fix_dates(r.get('rows') or []))
    if not data:
        raise AkFailed(f'{func} 无数据 ({params}) {time.time() - t0:.1f}s')
    return data


def _clean(data: list) -> list:
    """结构归一: 列名去首尾空白, NaN/NaT → None

    取数层一次清干净, 专用命令与通用口径路径都受益:
    - NaN 序列化成 JSON 是裸 NaN (非法 JSON), 解析方得自己兜;
    - 列名带空格时, 同一列在不同接口下名字不一样, 调用方没法按名取值。
    """
    if not data:
        return data
    import math
    out = []
    for r in data:
        row = {}
        for k, v in r.items():
            key = str(k).strip()
            if isinstance(v, float) and math.isnan(v):
                v = None
            elif isinstance(v, str) and v in ('NaT', 'nan', 'None'):
                v = None
            row[key] = v
        out.append(row)
    return out

_DATE_HINT = ('日', '时间', '日期', 'DATE', 'Date', 'date', 'Month', 'MONTH')

def _fix_dates(data: list) -> list:
    """pandas to_json 把 datetime 列写成纪元毫秒, 这里按列名折回 YYYY-MM-DD

    只认"列名带日/时间且值是大整数"的组合 —— 有列名叫"日期"但存的是
    '2026-10-23' 字符串, 也有叫"成交量"存大数的, 两条一起判才不会误伤。
    """
    if not data:
        return data
    sample = data[0]
    keys = [k for k in sample if any(h in str(k) for h in _DATE_HINT)]
    for r in data:
        for k in keys:
            v = r.get(k)
            if isinstance(v, (int, float)) and 1e11 < v < 1e14:
                r[k] = time.strftime('%Y-%m-%d', time.localtime(v / 1000))
            elif isinstance(v, str) and len(v) > 10 and v[4:5] == '-' and 'T' in v:
                r[k] = v[:10]
            elif v in ('NaT', 'nan', 'None'):
                r[k] = None
    return data

def one(func: str, timeout: int = _TIMEOUT, **params) -> dict:
    """单行结果 (如市场概览)→ dict"""
    d = rows(func, timeout=timeout, **params)
    return d[0] if isinstance(d, list) else d

# ── 代码过滤 ────────────────────────────────────────────────────
_CODE_KEYS = ('代码', '股票代码', '证券代码', '正股代码')

def _of_code(data: list, code: str) -> list:
    """按代码列过滤 (akshare 各接口代码列名不统一)"""
    return [r for r in data
            if any(str(r.get(k) or '').zfill(6) == code for k in _CODE_KEYS)]

def _tail(data: list, n: int) -> list:
    return data[-n:] if n and n > 0 else data

# ── 涨停 / 跌停家族 ─────────────────────────────────────────────
ZT_FUNCS = {
    'zt': ('stock_zt_pool_em', '涨停池'),
    'strong': ('stock_zt_pool_strong_em', '强势股池'),
    'zb': ('stock_zt_pool_zbgc_em', '炸板池'),
    'prev': ('stock_zt_pool_previous_em', '昨日涨停'),
    'dt': ('stock_zt_pool_dtgc_em', '跌停池'),
    'sub': ('stock_zt_pool_sub_new_em', '次新股池'),
}

def zt_pool(date, kind: str = 'zt') -> list:
    """涨停家族明细; kind 见 ZT_FUNCS。带封单/首封时间/连板数"""
    func, _ = ZT_FUNCS.get(kind, ZT_FUNCS['zt'])
    return rows(func, date=ymd(date))

# ── 龙虎榜 ──────────────────────────────────────────────────────
def lhb(start, end) -> list:
    """龙虎榜个股明细: 净买额/上榜原因/上榜后 1-10 日表现"""
    return rows('stock_lhb_detail_em', start_date=ymd(start), end_date=ymd(end))

def lhb_yyb(start, end) -> list:
    """活跃营业部 (游资席位): 买入个股数/买卖金额/净额"""
    return rows('stock_lhb_hyyyb_em', start_date=ymd(start), end_date=ymd(end))

# ── 大宗交易 / 解禁 / 调研 / 研报 ───────────────────────────────
def dzjy(start, end, code=None) -> list:
    """大宗交易明细: 成交价/折溢率/买卖营业部

    `stock_dzjy_mrmx` 的 symbol 是**证券类型**(A股/B股/基金/债券), 不是代码 ——
    把代码传进去 akshare 内部查表直接 KeyError。所以一律按 A股 取, 再本地过滤。
    """
    data = rows('stock_dzjy_mrmx', symbol='A股',
                start_date=ymd(start), end_date=ymd(end))
    return _of_code(data, code6(code)) if code else data

def unlock(start, end, code=None) -> list:
    """限售解禁明细: 解禁市值/占流通比/解禁前后涨跌"""
    data = rows('stock_restricted_release_detail_em',
                start_date=ymd(start), end_date=ymd(end))
    return _of_code(data, code6(code)) if code else data

def unlock_summary(start, end) -> list:
    """解禁日历 (按日汇总家数/市值) —— 判断短期供给压力"""
    return rows('stock_restricted_release_summary_em', symbol='全部股票',
                start_date=ymd(start), end_date=ymd(end))

def jgdy(date=None, code=None) -> list:
    """机构调研明细: 调研机构/类型/接待方式 (按日拉, 再按股票过滤)"""
    data = rows('stock_jgdy_detail_em', date=ymd(date), timeout=40)
    return _of_code(data, code6(code)) if code else data

def yanbao(code) -> list:
    """个股研报: 评级/机构/未来三年 EPS 与 PE 预测/PDF 链接"""
    return rows('stock_research_report_em', symbol=code6(code))

def gdhs(code) -> list:
    """股东户数历史: 户数增减 / 户均持股市值 / 筹码集中趋势"""
    return rows('stock_zh_a_gdhs_detail_em', symbol=code6(code))

# ── 市场宽度 / 北向 / 可转债 / ETF ───────────────────────────────
def breadth() -> dict:
    """市场概览: 涨跌家数/涨跌停家数/涨停封板率/活跃度 (legu)

    返回 dict (item/value 两列被压平), 不是 list —— 这是一条记录。
    """
    data = rows('stock_market_activity_legu')
    out = {}
    for r in data:
        k = r.get('item') or r.get('指标')
        if k:
            out[str(k)] = r.get('value', r.get('数值'))
    return out

def hsgt(days: int = 30, scope: str = 'north') -> list:
    """陆股通历史: scope north=北向 / south=南向

    北向单日净买额自 2024-08-16 起停止披露, 之后的行全是空值 —— 调用方
    必须据此显式告知用户, 不能把空当 0。
    """
    sym = '南向资金' if str(scope).lower() in ('south', '南向') else '北向资金'
    data = rows('stock_hsgt_hist_em', symbol=sym)
    live = [r for r in data if r.get('当日成交净买额') is not None]
    return _tail(live or data, days)

def hsgt_snapshot() -> list:
    """陆股通当日快照 (沪深股通/港股通四行): 净买额 + 上涨下跌家数"""
    return rows('stock_hsgt_fund_flow_summary_em')

def cb(code=None) -> list:
    """可转债列表: 转股价/转股价值/溢价率/评级 (code 给正股代码)"""
    data = rows('bond_zh_cov', timeout=30)
    return _of_code(data, code6(code)) if code else data

def etf() -> list:
    """ETF 行情列表 (新浪, 全量约 1700 只; 调用方自己按涨跌幅/成交额排)"""
    return rows('fund_etf_category_sina', symbol='ETF基金', timeout=40)

# ── 备用源: 原生源失败时才用 ────────────────────────────────────
_PERIOD_KLT = {'day': 'daily', 'week': 'weekly', 'month': 'monthly'}

def kline(code, period: str = 'day', count: int = 120, adjust: str = 'qfq') -> dict:
    """日/周/月 K 线 (前复权), 形状对齐原生源: {klines:[[日期,开,收,高,低,量]]}"""
    code6v = code6(code)
    data = rows('stock_zh_a_hist', symbol=code6v,
                period=_PERIOD_KLT.get(period, 'daily'),
                start_date='19900101', end_date=ymd(), adjust=adjust or '')
    kl = [[str(r.get('日期'))[:10], r.get('开盘'), r.get('收盘'),
           r.get('最高'), r.get('最低'), r.get('成交量')] for r in data]
    return {'symbol': code6v, 'period': period, 'fq': adjust or 'none',
            'klines': _tail(kl, count), 'count': len(kl), 'source': 'akshare'}

def news(code, count: int = 10) -> list:
    """个股新闻 (东财): 新闻标题/内容/发布时间/来源"""
    return _tail(rows('stock_news_em', symbol=code6(code)), count)

def fin_indicator(code) -> list:
    """财务指标历史 (新浪): 每股收益/净资产/ROE/毛利率 逐季"""
    return rows('stock_financial_analysis_indicator', symbol=code6(code), timeout=30)

# ── 数据集清单 (给 `prism data find` 与文档用) ───────────────────────
DATASETS = {
    'zt_pool': '涨停池/强势股/炸板/昨日涨停/跌停 (含封单、首封时间、连板数)',
    'lhb': '龙虎榜个股明细 (净买额、上榜原因、上榜后表现)',
    'lhb_yyb': '活跃营业部 (游资席位买卖统计)',
    'dzjy': '大宗交易明细 (成交价、折溢率、买卖营业部)',
    'unlock': '限售解禁明细/日历 (解禁市值、占流通比)',
    'jgdy': '机构调研明细 (调研机构、类型、接待方式)',
    'yanbao': '个股研报 (评级、机构、EPS/PE 预测)',
    'gdhs': '股东户数历史 (筹码集中度)',
    'breadth': '市场宽度 (涨跌家数、涨跌停家数、活跃度)',
    'hsgt': '北向资金历史',
    'cb': '可转债 (转股价值、溢价率、评级)',
    'etf': 'ETF 行情列表',
    'kline': 'K 线备用源 (前复权)',
    'news': '个股新闻备用源',
    'fin_indicator': '财务指标历史备用源 (新浪)',
    'changes': '盘口异动 (大笔买卖/封板/火箭发射/新高新低)',
    'hot': '东财人气榜 / 百度股市热搜',
    'buyback': '全市场回购 (计划金额、进度、已回购)',
    'shares': '股本结构变动史',
    'notice': '全市场公告流 (按类型过滤)',
    'high_low': '创新高/新低家数序列 (20/60/120 日)',
    'sector_spot': '新浪行业板块即时行情',
    'index_value': '中证指数估值 (PE/股息率)',
    'free_holders': '十大流通股东 (季报口径)',
    'yysj': '财报预约披露日 (含三次改期)',
    'yjbb': '业绩报表 (营收/净利/同比/ROE)',
    'fhps': '分红送配明细',
    'ggcg': '股东增减持 (全市场, 缓存 12h)',
    'mgmt': '董监高持股变动明细 (缓存 12h)',
}

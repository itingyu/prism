"""baostock/adata 数据域动作 (免费替代源)

只放"原生源与 akshare 都拿不到"的口径:
  dupont  杜邦拆解 (ROE = 净利率 × 周转 × 权益乘数, 逐季趋势)
  growth  成长能力 (营收/净利/净资产/EPS 同比, 逐季)
  dividend <代码>  个股分红送配历史 (年报到实施的完整日期链)
"""
from prism.stock.bridge import alt as _alt

_DIV_LABELS = {
    'dividPlanAnnounceDate': '方案公告日',
    'dividPreNoticeDate': '预案公告日',
    'dividAgmPumDate': '股东大会日',
    'dividPlanDate': '实施公告日',
    'dividRegistDate': '股权登记日',
    'dividOperateDate': '除权除息日',
    'dividPayDate': '派息日',
    'dividStockMarketDate': '红股上市日',
    'dividCashPsBeforeTax': '每股现金(税前)',
    'dividCashPsAfterTax': '每股现金(税后)',
    'dividStocksPs': '每股送股',
    'dividReserveToStockPs': '每股转增',
}


def _code(args) -> str:
    codes = list(getattr(args, 'codes', None) or [])
    return str(codes[0]).strip() if codes else ''


def _need(cfg=None):
    if not _alt.available('baostock'):
        raise RuntimeError('baostock 未安装: pip install baostock '
                           '(免费, 无需 token)')
    return _alt


def _act_dupont(args, cfg):
    lib = _need(cfg)
    code = _code(args)
    if not code:
        raise ValueError('dupont 需要股票代码')
    n = int(getattr(args, 'n', 8) or 8)
    res = lib.fin_series(code, 'dupont', quarters=n)
    return {'source': 'baostock', 'code': code, 'rows': res['rows'],
            'title': res['title']}


def _act_growth(args, cfg):
    lib = _need(cfg)
    code = _code(args)
    if not code:
        raise ValueError('growth 需要股票代码')
    n = int(getattr(args, 'n', 8) or 8)
    res = lib.fin_series(code, 'growth', quarters=n)
    return {'source': 'baostock', 'code': code, 'rows': res['rows'],
            'title': res['title']}


def _act_dividend(args, cfg):
    """`dividend <代码>` 给该股分红送配历史; 不带代码仍是全市场分红排行"""
    code = _code(args)
    if not code:
        from prism.stock.command._actions import _act_std
        lim = int(getattr(args, 'limit', 0) or 0)
        out = _act_std('stock_dividend_rank')(args, cfg)
        if isinstance(out, dict):
            out['limit'] = lim
            rows = (out.get('data') or {}).get('rows') if isinstance(out.get('data'), dict) else None
            if lim and isinstance(rows, list):
                # 上游每只票两行 (ASSIGN_FEATURE_CODE=0/1), 按去重后的只数截断,
                # 这样 -f json / -o 拿到的也是 -n 的条数, 不是全量
                seen, keep = set(), []
                for r in rows:
                    c = r.get('SECURITY_CODE')
                    if c in seen:
                        continue
                    seen.add(c)
                    keep.append(r)
                    if len(keep) >= lim:
                        break
                out['data']['rows'] = keep
        return out
    lib = _need(cfg)
    rows = lib.dividend(code, years=int(getattr(args, 'n', 5) or 5))
    if not rows:
        raise RuntimeError(f'{code} 近 {getattr(args, "n", 5)} 年无分红记录')
    # 上游字段名是 baostock 的 camelCase, 这里翻成能直接读的中文再交给渲染层
    out = []
    for r in rows:
        item = {}
        for k, v in r.items():
            label = _DIV_LABELS.get(k)
            if label:
                item[label] = v
        out.append(item)
    return {'source': 'baostock', 'code': code, 'rows': out,
            'title': '分红送配'}

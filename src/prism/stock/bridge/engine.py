"""engine 桥 —— 业务脚本层与 CLI 之间的转发

`prism/stock/engine/` 是本仓的**第一方代码**（从 stock-master 技能搬进来的
那批：选股池、评分、可买性闸门、研报模板…）。它自带工作流编排与业务口径，
本模块只做两件事：定位它、把它的动作转发出去。

对外只有 `mod(name)` —— 静态 import `prism.stock.engine.<name>`，不找路径、
不动 sys.path。延迟 import 是为了让脚本层缺失时只让 stock 动作退 2，而不是
拖垮整个 prism。

取数不在这里：所有 HTTP 都经 `bridge/sources`，engine 侧只保留业务口径。
"""
import importlib
import os
import sys

from prism.stock.error import EngineMissing

ENGINE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'engine')


def available():
    """engine 包在不在。判据是 `engine/__init__.py`（代码），不是文档"""
    return os.path.isfile(os.path.join(ENGINE_DIR, '__init__.py'))


def mod(name):
    """import `prism.stock.engine.<name>`; 失败抛 EngineMissing (带原因)"""
    try:
        return importlib.import_module(f'prism.stock.engine.{name}')
    except ImportError as e:
        # 两种完全不同的病, 别混成一句话: engine 文件不在 = 装包不完整;
        # engine 在但它的第三方依赖不在 = 没装可选依赖 (numpy 之类)。报错要
        # 指向缺的那个依赖, 而不是叫人去查包目录。
        from prism.core import deps
        miss = getattr(e, 'name', None) or ''
        if not miss.startswith('prism'):
            raise EngineMissing(
                f'stock engine 不可用: {deps.install_hint(miss)}') from e
        raise EngineMissing(
            f'stock engine 不可用: {e}; engine 文件缺失, '
            f'{deps.install_hint("prism 本体")}') from e


def clients():
    """数据层唯一入口: quote / limit_up_pool / announcements / capital_flow / code_ok ..."""
    return mod('clients')


# 动作实现 (每个都只做参数整形 + 调用, 不加工业务口径)

def do_quote(codes):
    """实时行情。腾讯主源, 指数别名(上证指数/创业板指)可用。返回 list[dict]"""
    return clients().quote(list(codes))


def do_pool(date=None, only_buy=False):
    """涨停池。东财 push2ex; date=None/last = 上一交易日, only_buy = 只留可买板块

    返回 {"ok", "date"(真实数据日), "count", "rows"}; 非 ok 时原样透传错误,
    不把失败伪装成空池 (涨跌停池接口对无效日期会静默回旧数据, date 是唯一可信锚)。
    """
    c = clients()
    r = c.limit_up_pool(date)
    if not isinstance(r, dict) or not r.get('ok'):
        return r
    out = dict(r)
    rows = r.get('rows') or []
    if only_buy:
        rows = [it for it in rows if c.code_ok(it.get('code'), it.get('name'))[0]]
    out['rows'] = rows
    out['count'] = len(rows)
    out['filtered_only_buy'] = bool(only_buy)
    return out


def do_check(codes):
    """可买性核查: 板块归属 + 停牌/ST/退市风险 + 涨跌停制度口径

    code_ok 返回 (可买, 板块名); 不可买的也照样返回并标注 —— 调用方要的是
    "为什么被剔除", 静默丢弃等于让 Agent 以为查无此股。
    """
    c = clients()
    checks = []
    for code in codes:
        try:
            ok, board = c.code_ok(code)
        except Exception as e:                              # noqa: BLE001
            checks.append({'code': code, '可买': False, '板块': None,
                           'err': f'{type(e).__name__}: {e}'})
            continue
        checks.append({'code': code, '可买': bool(ok), '板块': board})
    return {'count': len(checks),
            '可买数': sum(1 for x in checks if x['可买']),
            'checks': checks}


def do_calendar(date=None, n=3):
    """交易日历: 基准日的交易日判定 + 前后各 n 个交易日

    日历数据在 engine.clients 里 (随包分发的 holidays-<年>.json),
    这里只做编排, 不再依赖已删掉的 short_tool 模块。
    """
    from datetime import datetime, timedelta

    from prism.stock.engine import clients as c

    if date:
        base = datetime.strptime(str(date).replace('-', ''), '%Y%m%d')
    else:
        base = datetime.now()
    prev, nxt = [], []
    d = base - timedelta(days=1)
    while len(prev) < n:
        if c.is_trading_day(d):
            prev.append(d.strftime('%Y-%m-%d'))
        d -= timedelta(days=1)
    d = base + timedelta(days=1)
    while len(nxt) < n:
        if c.is_trading_day(d):
            nxt.append(d.strftime('%Y-%m-%d'))
        d += timedelta(days=1)
    return {
        '今天': base.strftime('%Y-%m-%d %A'),
        '是否交易日': bool(c.is_trading_day(base)),
        '上一交易日': prev[0] if prev else None,
        '下一交易日': nxt[0] if nxt else None,
        '近期': {'上': prev, '下': nxt},
        '节假日表': ('已加载' if c._holidays(base.year)
                     else f'缺失（需补 {c.holidays_path(base.year)}）'),
    }


def do_capital_flow(scope='industry'):
    """资金流榜单。scope ∈ industry/individual/north; 北向不可用时显式给 unavailable"""
    return clients().capital_flow(scope)


def do_news(code, limit=10):
    """个股新闻。

    limit 只能取回后裁剪: `stock_news` 只接 symbol, 没有分页参数 —— 同花顺
    stockpage 一次给全量, 截断是这里做的。
    """
    r = clients().news(code)
    # 备用源 (akshare) 直接给 list, 没有嵌套 items: 先按同一口径裁剪再返回
    data0 = r.get('data') if isinstance(r, dict) else None
    if isinstance(data0, list) and limit and len(data0) > limit:
        out0 = dict(r)
        out0['data'] = data0[:limit]
        out0['total_items'] = len(data0)
        return out0
    items = _items(r)
    if items is None or not limit or len(items) <= limit:
        return r
    data = r.get('data') if isinstance(r, dict) else None
    if not isinstance(data, dict):
        return r
    out = dict(r)
    out['data'] = _replace_items(data, items[:limit])
    out['total_items'] = len(items)
    return out


def _replace_items(data, new_items):
    """把 payload 里那条 items/list/rows 列表换掉 (保持原嵌套形状)"""
    for k in ('items', 'list', 'rows'):
        if isinstance(data.get(k), list):
            return {**data, k: new_items}
    return {**data, 'items': new_items}


def do_announcements(code, page_size=10):
    """公告列表。page_size 透传给编排层的 stock_announcement。"""
    return clients().announcements(code, page_size)


def do_financials(code):
    """核心财务指标 (PE/PB/ROE/毛利率/营收净利同比 等)。"""
    return clients().financials(code)


def do_valuation(code, years=3):
    """估值历史分位: 当前 PE/PB 在近 N 年里的位置"""
    from prism.stock.engine import feeds
    from prism.stock.engine import valuation as _val
    items = feeds.valuation_history(code, years=years)
    if not items:
        return {'ok': False, 'error': f'无估值历史数据 ({code})'}
    out = _val.summarize_series(items, years=years)
    out['ok'] = True
    out['code'] = str(code)
    out['name'] = out['latest'].get('name')
    return out


def do_patterns(code, bars=120):
    """技术形态识别: 从 K 线里找事件形态 (背离/跳空/平台突破/量价背离/金叉...)"""
    from prism.stock.engine import feeds
    from prism.stock.engine import patterns as _pat
    from prism.stock.engine._common import to_xueqiu_symbol
    symbol = to_xueqiu_symbol(code)
    kres = feeds.kline_list(symbol, count=int(bars) + 20, period='day')
    items = (kres.get('items') if isinstance(kres, dict) else kres) or []
    if not items:
        return {'ok': False, 'error': f'无 K 线数据 ({code})'}
    found = _pat.detect(items, lookback=bars)
    return {'ok': True, 'code': str(code), 'count': len(found),
            'bars': len(items), 'items': found}


def do_positions(file=None, with_price=True):
    """持仓与盈亏: 本地台账 + 现价 (腾讯批量取)"""
    from prism.stock.engine import position as _pos
    items = _pos.positions(file)
    if not items:
        return {'ok': True, 'count': 0, 'rows': [], 'file': str(_pos.position_path(file)),
                'note': '持仓为空 (用 `prism position add` 建仓)'}
    rows = []
    quotes = {}
    if with_price:
        try:
            for q in clients().quote([it['code'] for it in items]):
                if q.get('ok'):
                    quotes[str(q.get('input'))] = q
        except Exception as e:                              # noqa: BLE001
            for it in items:
                rows.append(dict(it, price=None, note_err=f'{type(e).__name__}: {e}'))
            return {'ok': False, 'error': f'取价失败: {type(e).__name__}: {e}',
                    'rows': rows, 'count': len(rows)}
    total_mv = 0.0
    for it in items:
        q = quotes.get(it['code'], {})
        price = q.get('现价')
        row = dict(it)
        row['price'] = price
        row['change_pct'] = q.get('涨跌幅')
        row['name'] = it.get('name') or q.get('name') or it['code']
        if price:
            mv = price * it['shares']
            cost = it['cost'] * it['shares']
            row['market_value'] = round(mv, 2)
            row['cost_value'] = round(cost, 2)
            row['pnl'] = round(mv - cost, 2)
            row['pnl_pct'] = round((price / it['cost'] - 1) * 100, 2) if it['cost'] else None
            total_mv += mv
            if it.get('stop') and price <= it['stop']:
                row['alert'] = f'跌破止损 {it["stop"]}'
            elif it.get('target') and price >= it['target']:
                row['alert'] = f'达到止盈 {it["target"]}'
        else:
            row['market_value'] = None
            row['cost_value'] = round(it['cost'] * it['shares'], 2)
            row['pnl'] = None
            row['pnl_pct'] = None
            row['alert'] = row.get('alert') or '无行情 (代码/停牌?)'
        rows.append(row)
    for r in rows:
        if r.get('market_value') and total_mv:
            r['weight'] = round(r['market_value'] / total_mv * 100, 2)
        else:
            r['weight'] = None
    total_cost = sum(r.get('cost_value') or 0 for r in rows)
    total_pnl = sum(r.get('pnl') or 0 for r in rows)
    return {'ok': True, 'count': len(rows), 'rows': rows,
            'file': str(_pos.position_path(file)),
            'total_market_value': round(total_mv, 2),
            'total_cost': round(total_cost, 2),
            'total_pnl': round(total_pnl, 2),
            'total_pnl_pct': round((total_mv / total_cost - 1) * 100, 2) if total_cost else None}


def do_analyze(code, news_items=None):
    """单股深度: quote + K线 + 技术指标 + 100分制评分 + 决策信号 + 公司画像"""
    return mod('analysis.single_analysis').analyze(code, news_items)


def do_screen(pool='short', min_score=60, codes=None):
    """选股池。pool ∈ short/mid/long, 走 pool_selector 统一路由

    三个池入参不同, 不能透传: short 收 min_score (自跑全市场), mid/long 收
    codes 列表 (用户给标的), long 还要求 [{code,name}] 结构。分开组装。
    """
    if pool == 'short':
        return mod('screening.pool_selector').select('short', min_score=min_score)
    if pool == 'mid':
        return mod('screening.pool_selector').select('mid', codes=list(codes or []))
    if pool == 'long':
        items = [{'code': c, 'name': None} if isinstance(c, str) else c
                 for c in (codes or [])]
        return mod('screening.pool_selector').select('long', codes=items)
    raise ValueError(f'未知池名: {pool} (可用: short / mid / long)')


def do_risk(codes):
    """风险股核查: 重组 / 减持 / 立案 / 预亏"""
    rc = mod('screening.risk_check')
    if isinstance(codes, str):
        return rc.scan(codes)
    return rc.scan_many(list(codes))


def do_report(code=None, pool=None, news=None):
    """成稿研报 (markdown)。code=单股报告, pool=短线池报告

    报告模板在 research.report_writer, 口径全在那边; 这里只做取数 + 拼装:
    单股报告要先跑 analyze (报告模板吃的是 analyze 的输出)。
    """
    rw = mod('research.report_writer')
    if code:
        analysis = do_analyze(code)
        items = news if news is not None else _news_texts(code)
        return {'kind': 'single', 'code': code,
                'report': rw.single_stock_report(analysis, news=items)}
    if pool == 'short':
        result = do_screen('short')
        return {'kind': 'short_screen', 'report': rw.short_screen_report(result)}
    raise ValueError('report 需要位置参数给代码 (单股报告) 或 --pool short (短线池报告)')


def do_excel(path, pool='short', min_score=60):
    """选股池导出 xlsx。openpyxl 不在环境里则明确报错, 不静默不出文件"""
    try:
        import openpyxl                              # noqa: F401
    except ImportError:
        raise ValueError('导出 xlsx 需要 openpyxl (apk add py3-openpyxl)')
    result = do_screen('short', min_score=min_score)
    mod('export.short_screen_excel').build_from_screen(result, path, meta={'source': 'prism screen'})
    return {'ok': True, 'path': path, 'passed': len(result.get('passed') or []),
            'failed': len(result.get('failed') or [])}


def do_sentiment(texts):
    """消息面打分 (-100~+100)。texts: 字符串列表, 或 [{"title"/"text"}]"""
    return mod('sentiment.news_scorer').score(list(texts))


def do_diagram(kind, code=None, name=None, thesis=None,
               drivers=None, risks=None, catalysts=None, mid=None):
    """mermaid 图: logic(投资逻辑) / tree(决策树) / chain(产业链)

    chain 的上游/中游/下游分别对应 drivers/mid/catalysts —— 产业链图没有
    "风险"概念, 拿 risks 去当中游是语义错配, 所以单独用 --mid。

    logic 缺参数会画得空洞, 但那是调用方的事 —— 该由人给的判断不该由工具猜。
    """
    lr = mod('visualization.logic_renderer')
    if kind == 'tree':
        return {'kind': kind, 'md': lr.decision_tree()}
    if kind == 'chain':
        if not name:
            raise ValueError('chain 需要 --name (产业链名)')
        return {'kind': kind, 'md': lr.industry_chain(
            name, drivers or [], mid or [], catalysts or [])}
    if kind == 'logic':
        if not (code and name):
            raise ValueError('logic 需要位置参数给代码, 与 --name')
        return {'kind': kind, 'md': lr.investment_logic(
            code, name, thesis or '', drivers or [], risks or [], catalysts or [])}
    raise ValueError(f'未知图类型: {kind} (可用: logic / tree / chain)')


def _news_texts(code, limit=10):
    """取个股新闻的纯文本, 供消息面打分 / 研报附新闻。

    载荷可能是 items / data.list 等不同嵌套, 且同花顺那条路会回原始 HTML
    未解析 —— 两种情况都取不到可用文本, 此时返回空列表让下游按"无新闻"处理,
    不把 HTML 塞进打分器。
    """
    r = do_news(code, limit)
    out = []
    for it in (_items(r) or []):
        if isinstance(it, str):
            out.append(it)
        elif isinstance(it, dict):
            t = it.get('title') or it.get('text')
            if t:
                out.append(t)
    return out


def _items(payload):
    """从载荷里挖条目列表 (广度优先下钻 items/list/rows)。"""
    queue = [(payload, 0)]
    while queue:
        node, d = queue.pop(0)
        if not isinstance(node, dict) or d > 6:
            continue
        for k in ('items', 'list', 'rows'):
            v = node.get(k)
            if isinstance(v, list):
                return v
        for v in node.values():
            if isinstance(v, dict):
                queue.append((v, d + 1))
    return None

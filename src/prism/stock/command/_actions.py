"""stock 核心数据动作: 行情/资金/分析/选股/图表"""
"""prism 动作: 动作分发 + 输出渲染

两座桥 (bridge/engine.py 脚本层 / bridge/srv.py 编排层) 在这里汇合成一个扁平的动作表。动作分三类:

    数据动作  quote pool check calendar flow news announcement financials
              analyze screen risk            —— 走 engine 脚本层
    透传动作  mcp <tool>                     —— 按名调用 24 个动作 (未单独暴露的那些)
    元动作   tools health                    —— 能力清单与两侧探活

输出与 prism 其他数据命令一致: 数据动作按 args.format 自己渲染 (json 全字段 /
text 行内可读 / markdown 表格), 走 cli.app._run 的 emit 落盘通道。

口径纪律 (从 stock-master 继承, 现由 engine 维护):
  - 接口返回 0/空 不当正常值, 由各桥透传 status, 渲染时显式标注
  - 北向资金不可用必须显式 ⚠, 不填 0
  - 池/榜单类结果必带数据日 (date), 涨停池尤其 —— 接口对无效日期会静默回旧数据
"""

from prism.stock.bridge import engine as _engine
from prism.stock.bridge import rawapi as _raw
from prism.stock.bridge import srv as _srv
from prism.stock.error import UsageError


from prism.stock.command._common import _args_dict
from prism.stock.command._common import _code
from prism.stock.command._common import codes_input
from prism.stock.command._common import _index_symbol
from prism.stock.command._common import _write_kline_chart
from prism.stock.command._common import _kline_rows, _kline_title
from prism.stock.command._common import (_write_intraday_chart,
                                            _write_intraday_combo,
                                            _dma_levels)

def _act_datacenter(args, cfg):
    """东财数据中心: 123 张报表, 不给参数看目录, 给 reportName 直接跑"""
    from prism.stock.bridge import em
    from prism.stock.command._common import _args_dict
    report = (getattr(args, 'code', None) or
              (getattr(args, 'codes', None) or [None])[0])
    limit = int(getattr(args, 'limit', 20) or 20)
    params = _args_dict(args)

    if not report:
        items = em.list_reports(limit=limit).get('reports', [])
        rows = [{'报表': it['reportName'], '用途': it.get('use', ''),
                 'akshare函数': it.get('func', ''),
                 '可筛选': ','.join(it.get('vars') or []) or '-'}
                for it in items]
        return {'rows': rows, 'source': '东财数据中心',
                'title': f'东财数据中心报表目录 (共 {len(em.recipes())} 张)'}

    recipes = em.recipes()
    if report in recipes:
        rec = recipes[report]
        miss = [v for v in (rec.get('filter_vars') or []) if v not in params]
        if miss:
            return {'rows': [{'报表': report, '用途': rec.get('use', ''),
                              'akshare函数': rec.get('func', ''),
                              '缺少参数': ','.join(miss),
                              '说明': f"用 --arg {miss[0]}=... 传值"}],
                    'title': f'{report} 需要筛选参数'}
        out = em.run(report, **params)
        rows = out.get('rows') if isinstance(out, dict) else out
        rows = rows or []
        return {'rows': rows, 'source': '东财数据中心',
                'title': f'{report} · {rec.get("use", "")} ({len(rows)} 条)'}

    hits = em.list_reports(kw=report, limit=limit).get('reports', [])
    rows = [{'报表': it['reportName'], '用途': it.get('use', ''),
             'akshare函数': it.get('func', ''),
             '可筛选': ','.join(it.get('vars') or []) or '-'}
            for it in hits]
    return {'rows': rows, 'source': '东财数据中心',
            'title': f'东财报表搜索 "{report}" ({len(rows)} 条)'}


def _act_commands(args, cfg):
    """命令与口径目录 (只列不调)"""
    from prism.stock.bridge import rawapi
    from prism.stock.bridge.ak_families import FAM
    from prism.cli.stock import COMMANDS

    family = getattr(args, 'family', None)
    codes = getattr(args, 'codes', None) or []
    keyword = (getattr(args, 'code', None) or (codes[0] if codes else '') or '')
    kw = str(keyword).strip().lower()

    def _doc(name):
        fn = COMMANDS.get(name)
        d = (getattr(fn, '__doc__', '') or '').strip()
        return d.splitlines()[0] if d else ''

    if family:
        if family not in FAM:
            raise ValueError(f'没有这个功能族: {family} (prism commands 看全部)')
        rows = [{'口径': k, '接口': v['n'],
                 '状态': {'ok': '可用', 'empty': '需参数', 'err': '上游失效'}.get(v.get('st'), '未测'),
                 '类型': '备用源' if v['role'] == 'fallback' else '扩展口径',
                 '说明': v['s']}
                for k, v in sorted(FAM[family].items())]
        return {'rows': rows, 'title': f'{family} 的扩展口径 ({len(rows)})'}

    # 每个命令覆盖的数据源层方法数 (按功能类的 cli 映射)
    src_cnt = {}
    for _c, _v in rawapi.categories().items():
        for _cli in (_v.get('cli') or []):
            src_cnt[_cli] = src_cnt.get(_cli, 0) + len(_v.get('primary') or []) \
                + len(_v.get('fallback') or [])

    rows = []
    for name in sorted(COMMANDS):
        doc = _doc(name)
        kinds = FAM.get(name, {})
        if kw:
            hit = (kw in name.lower() or kw in doc.lower() or
                   any(kw in k.lower() or kw in (v.get('s') or '').lower()
                       for k, v in kinds.items()))
            if not hit:
                continue
        rows.append({'命令': name, '说明': doc,
                     '口径': len(kinds) if kinds else '-',
                     '源方法': src_cnt.get(name, '-'),
                     '类别': _cmd_category(name)})
    return {'rows': rows,
            'title': f'prism 命令目录 ({len(rows)} 个命令 / '
                     f'{sum(len(v) for v in FAM.values())} 个扩展口径)'}


def _cmd_category(name):
    if name.startswith('docs-'):
        return '文档'
    if name in ('data', 'pydata'):
        return '透传'
    return '数据'


def _act_quote(args, cfg):
    return _engine.do_quote(codes_input(args))

def _act_pool(args, cfg):
    """涨停池: 默认走原生口径 (engine); --kind 选强势股/炸板/昨日涨停/跌停
    时走 akshare (原生源没有这四个池)"""
    kind = (getattr(args, 'type_', None) or 'zt').strip().lower()
    if kind != 'zt':
        from prism.stock.command._actions_ak import _act_zt_pool, _act_fam
        from prism.stock.bridge import ak as _ak
        if kind not in _ak.ZT_FUNCS:      # 其余 akshare 接口 → 扩展口径
            args.family, args.kind = 'pool', kind
            return _act_fam(args, None)
        return _act_zt_pool(args, kind)
    return _engine.do_pool(args.date, args.only_buy)

def _act_check(args, cfg):
    return _engine.do_check(codes_input(args))

def _act_calendar(args, cfg):
    return _engine.do_calendar(args.date, args.n)

def _act_flow(args, cfg):
    return _engine.do_capital_flow(args.scope)

def _act_news(args, cfg):
    return _engine.do_news(_code(args), args.limit)

def _act_announcement(args, cfg):
    """公告: 归一成 {date,title,category,url}, 支持类型/时间窗/关键词过滤"""
    from datetime import datetime, timedelta
    from prism.stock.command._common import _items_of
    from prism.stock.engine import announce as _ann

    out = _engine.do_announcements(_code(args), getattr(args, 'limit', 10))
    if not isinstance(out, dict) or not out.get('ok', True):
        return out
    raw = _items_of(out.get('data'))
    if not raw:
        return out
    rows = []
    for it in raw:
        if not isinstance(it, dict):
            continue
        title = it.get('title') or it.get('announcementTitle') or ''
        date = (it.get('notice_date') or it.get('noticeDate') or '')[:10]
        url = it.get('attach_url') or it.get('adjunctUrl') or ''
        if not url and it.get('art_code'):
            # 东财 np-anotice 不直接给附件 URL, 用 art_code 拼详情页
            url = (f'https://data.eastmoney.com/notices/detail/'
                   f'{_code(args)}/{it["art_code"]}.html')
        cols = [c.get('column_name') for c in (it.get('columns') or [])
                if isinstance(c, dict) and c.get('column_name')]
        row = {'date': date, 'title': title, 'url': url}
        _ann.annotate(row, cols)
        rows.append(row)

    days = getattr(args, 'days', None)
    if days:
        try:
            cut = (datetime.now() - timedelta(days=int(days))).strftime('%Y-%m-%d')
            rows = [r for r in rows if not r['date'] or r['date'] >= cut]
        except (TypeError, ValueError):
            pass
    kw = (getattr(args, 'keyword', '') or '').strip()
    if kw:
        rows = [r for r in rows if kw in (r['title'] or '')]
    rows = _ann.filter_by_type(rows, getattr(args, 'type_', '') or '')
    return {'ok': True, 'source': out.get('source'),
            'data': {'count': len(rows), 'items': rows}}

def _act_patterns(args, cfg):
    return _engine.do_patterns(_code(args), getattr(args, 'bars', 120))


def _act_position(args, cfg):
    """持仓台账: list / add / remove"""
    from prism.stock.engine import position as _pos
    act = getattr(args, 'pos_action', 'list')
    f = getattr(args, 'file', None)
    if act == 'add':
        try:
            from prism.stock.name_index import looks_like_name, resolve_name
            code = args.code
            if looks_like_name(code):
                code = resolve_name(code)
            return _pos.add(code, args.shares, args.cost, name=args.name or '',
                            note=args.note or '', stop=args.stop, target=args.target,
                            file=f)
        except ValueError as e:
            return {'ok': False, 'error': str(e)}
    if act == 'remove':
        from prism.stock.name_index import looks_like_name, resolve_name
        code = args.code
        if looks_like_name(code):
            code = resolve_name(code)
        return _pos.remove(code, shares=getattr(args, 'shares', None), file=f)
    return _engine.do_positions(file=f)


def _act_valuation(args, cfg):
    return _engine.do_valuation(_code(args), getattr(args, 'years', 3))


def _act_financials(args, cfg):
    return _engine.do_financials(_code(args))

def _act_analyze(args, cfg):
    code = _code(args) or ''
    low = code.lower()
    if low.startswith(('hk', 'us', 'kr')):
        raise ValueError('analyze 只做 A 股基本面; 港/美/韩行情用 '
                         'prism hk-quote / us-quote / kr-quote')
    return _engine.do_analyze(code)

def _act_screen(args, cfg):
    return _engine.do_screen(args.pool, args.min_score, args.codes)

def _act_risk(args, cfg):
    return _engine.do_risk(codes_input(args))

def _act_holder(args, cfg):
    """股东研究 (东财) —— 持仓变动/机构调研, 比 stock_top_holders 动作更细"""
    code = _code(args)
    mkt = 'SH' if code.startswith('6') else ('SZ' if code[0] in '03' else 'BJ')
    return _raw.call('em_shareholder_research', {'code': f'{mkt}{code}'})

def _act_forecast(args, cfg):
    """盈利预测 (东财) + 主营构成 (em_business_analysis) 交叉"""
    code = _code(args)
    mkt = 'SH' if code.startswith('6') else ('SZ' if code[0] in '03' else 'BJ')
    return _raw.call('em_profit_forecast', {'code': f'{mkt}{code}'})

def _act_report(args, cfg):
    return _engine.do_report(code=_code(args, required=False), pool=args.pool,
                             news=list(args.texts or []) or None)

def _act_excel(args, cfg):
    path = getattr(args, 'output', None)
    if not path:
        raise ValueError('excel 需要 -o/--output 指定输出路径, 例: prism excel -o picks.xlsx')
    from prism.cli.runtime import _CTX
    _CTX['file_written'] = path
    return _engine.do_excel(path, pool='short', min_score=args.min_score)

def _act_sentiment(args, cfg):
    items = list(args.texts or [])
    if not items:
        # 没给 --text 就理解为"给这只票的新闻打分", 省一次取新闻的重复输入
        items = _engine._news_texts(_code(args))
    return _engine.do_sentiment(items)

def _act_diagram(args, cfg):
    return _engine.do_diagram(args.type_ or 'tree', code=_code(args, required=False),
                              name=args.name, thesis=args.thesis,
                              drivers=list(args.drivers or []),
                              risks=list(args.risks or []),
                              catalysts=list(args.catalysts or []),
                              mid=list(getattr(args, 'mid', None) or []))

def _act_kline(args, cfg):
    """K 线: 取数 (编排层 stock_kline 的多源回退) + 可选出图

    `--chart` 落一份自包含 SVG —— 零依赖, 不用装 matplotlib, 也不用联网取
    字体; 生成的文件在 app 里可直接预览。`--start/--end` 支持指定区间:
    源多按"根数"取数, 所以按区间跨度反推根数, 取回后再按日期裁 (两条源
    都能用, 不依赖某个源是否支持 beg/end)。
    """
    from prism.stock.command._common import _kline_range, _clip_kline_range
    if not (list(args.codes or ['']) or [''])[0]:
        raise UsageError('kline 需要股票代码: prism kline 600519 [--bars 120]')
    code = (list(args.codes or ['']) or [''])[0]
    start = _norm_day(getattr(args, 'start', None))
    end = _norm_day(getattr(args, 'end', None))
    bars = int(getattr(args, 'bars', 0) or 120)
    # 区间取数要给均线留预热窗口: 画 MA120 时, 可见首根之前必须有 119 根,
    # 否则图上 MA120 会"从中途才开始", 看着像数据缺失。
    ma_arg = getattr(args, 'ma', None) or '5,10,20'
    ma_vals = [int(m) for m in ma_arg.split(',') if m.strip().isdigit()]
    warm = max(ma_vals) if ma_vals else 0
    count = bars if not (start or end) else min(_kline_range(start, end) + warm, 3000)
    out = _srv.do_call('stock_kline', {'symbol': code,
                                       'period': args.period or 'day',
                                       'count': count}, timeout=args.timeout)
    # 源普遍多给一根 (腾讯按 count 返回 count+1), 裁到用户要的根数 ——
    # 否则标题写"60 根"、实际画 61 根, 图与命令不符。给了区间就按区间裁。
    d = out.get('data') if isinstance(out, dict) else None
    if isinstance(d, dict):
        # 各源对'周期'的叫法不一 (腾讯有 period, 东财没有) —— 我们要的就是
        # args.period, 统一回填, 免得渲染层把周线标成日线。
        d.setdefault('period', args.period or 'day')
        for key in ('klines', 'rows'):
            ks = d.get(key)
            if not isinstance(ks, list) or not ks:
                continue
            raw = ks[:]          # 作图要用未裁剪的全量算均线 (预热窗口)
            if start or end:
                ks = _clip_kline_range(ks, start, end, bars if not start else 0)
            elif len(ks) > bars:
                ks = ks[-bars:]
            d[key] = ks
            full_rows = raw
    if getattr(args, 'chart', False) and isinstance(out, dict):
        out['chart_path'] = _write_kline_chart(out, args, code, count,
                                               full_rows=locals().get('full_rows'))
    if getattr(args, 'ascii_art', False) and isinstance(out, dict):
        from prism.render.ascii_chart import kline_ascii, should_color
        rows_a = _kline_rows(out)
        period = getattr(args, 'period', 'day') or 'day'
        cn = {'day': '日线', 'week': '周线', 'month': '月线'}.get(period, period)
        head = f'{_kline_title(out, code)} · {cn} · {len(rows_a)} 根'
        hh = int(getattr(args, 'ascii_h', 0) or 0) or 20
        ww = int(getattr(args, 'ascii_w', 0) or 0) or None
        # 风格收敛成一个选项 (--ascii-style thin|wide|plain):
        # 原来有三个布尔 (ascii_plain/ascii_wide/ascii_gap) 没有任何命令提供,
        # 读了没人给 —— 名存实亡的空选项
        style = str(getattr(args, 'ascii_style', 'thin') or 'thin').lower()
        print(kline_ascii(rows_a,
                          ma=[m for m in (getattr(args, 'ma', '') or '').split(',') if m.strip()],
                          title=head, color=should_color(),
                          height=hh, width=ww,
                          plain=style == 'plain',
                          wide=style == 'wide'))
    return out


def _norm_day(s):
    """'20250101' / '2025-01-01' → '2025-01-01' (区间过滤统一用它比较)"""
    s = str(s or '').strip().replace('/', '-')
    if len(s) == 8 and s.isdigit():
        return f'{s[:4]}-{s[4:6]}-{s[6:8]}'
    return s[:10]


def _act_intraday(args, cfg):
    """分时: 当日 / 五日, 可出图 (左轴价格 + 右轴涨幅)

    当日图默认带集合竞价 (09:15-09:25), `--no-auction` 去掉; 竞价只有东财
    一个源, 拿不到时图照出、并在数据里写明 auction=False 与原因。
    """
    code = (list(args.codes or ['']) or [''])[0]
    ndays = 5 if int(getattr(args, 'days', 1) or 1) >= 5 else 1
    combo = bool(getattr(args, 'combo', False))
    gran = int(getattr(args, 'bar_seconds', 60) or 60)
    if combo and gran >= 60:
        gran = 30                     # 组合图默认带一张 30 秒的细粒度面板
    dma_spec = (getattr(args, 'ma_daily', None) or '').strip()
    outk = None
    if combo or dma_spec:             # 分时叠日线均线要一份 K 线; 组合图本来也要
        outk = _srv.do_call('stock_kline',
                            {'symbol': code,
                             'period': 'day',
                             'count': 200},
                            timeout=args.timeout)
    out = _srv.do_call('stock_intraday',
                       {'symbol': code, 'ndays': ndays,
                        'auction': not getattr(args, 'no_auction', False),
                        'after_hours': bool(getattr(args, 'after_hours', False)),
                        'gran': gran},
                       timeout=args.timeout)
    if isinstance(out, dict) and outk:
        levels = _dma_levels(outk, dma_spec or '5,10,20,60')
        if levels:
            out.setdefault('data', {})['dma'] = levels
    if (getattr(args, 'chart', False) or combo) and isinstance(out, dict):
        if combo:
            out5 = _srv.do_call('stock_intraday',
                                {'symbol': code, 'ndays': 5, 'auction': False},
                                timeout=args.timeout)
            out['chart_path'] = _write_intraday_combo([out, out5], args, code,
                                                      kline=outk)
        else:
            out['chart_path'] = _write_intraday_chart(out, args, code)
    if getattr(args, 'ascii_art', False) and isinstance(out, dict):
        from prism.render.ascii_chart import intraday_ascii, should_color
        d = out.get('data') or {}
        days = d.get('days') or []
        if days:
            nm = ' '.join(x for x in (d.get('name'), d.get('code')) if x)
            tag = '五日' if ndays >= 5 else '当日'
            head = f'{nm or code} · {tag}分时'
            if d.get('preclose'):
                head += f' · 昨收 {d["preclose"]:.2f}'
            hh = int(getattr(args, 'ascii_h', 0) or 0) or 16
            ww = int(getattr(args, 'ascii_w', 0) or 0) or None
            print(intraday_ascii(days, title=head,
                                 preclose=d.get('preclose'),
                                 color=should_color(),
                                 height=hh, width=ww,
                                 plain=False))
    return out


def _act_boards(args, cfg):
    """板块目录: 行业+概念全量 (东财 clist), 可选关键词过滤

    用法: prism boards [关键词] —— 给 `kline/intraday` 挑名字用。
    过滤支持: 名字含关键词 ('光' / '模块')、BK 代码 ('BK1136'/'1136');
    无过滤输出全表 (行业在前), 按 |涨跌幅| 降序, 当天活跃的排前面。
    """
    from prism.stock.bridge import orchestrate as _o
    from prism.stock.bridge.sources import APIClient
    from prism.render.ascii_chart import should_color as _sc
    col = _sc()
    up, dn, off = ('\033[31m', '\033[32m', '\033[0m') if col else ('', '', '')

    def _pct_s(v):
        if not isinstance(v, (int, float)):
            return '  -'
        s = f'{v:+.2f}'
        # A 股口径: 红涨绿跌; 环境探测关掉颜色时是纯文本, 重定向也不会混转义
        if v > 0:
            return f'{up}{s:>7}{off}'
        if v < 0:
            return f'{dn}{s:>7}{off}'
        return f'{s:>7}'
    items = _o._boards_cached(APIClient())
    if not items:
        print('板块目录未取得 (东财 clist 不可达)')
        return 1
    kw = (list(args.codes or ['']) or [''])[0].strip().upper() \
        if getattr(args, 'codes', None) else ''
    seen, rows = set(), []
    for code, name, pct in items:
        if code in seen:
            continue
        seen.add(code)
        if kw and kw not in name.upper() and kw not in code and \
                kw.replace('BK', '') != code.replace('BK', ''):
            continue
        rows.append((code, name, pct))
    rows.sort(key=lambda r: -(abs(r[2]) if isinstance(r[2], (int, float)) else 0))
    if not rows:
        print(f'没有匹配 "{args.codes[0]}" 的板块; 空过滤看全表: prism boards')
        return 1
    print(f'{"代码":<8}  {"名称":<14}  {"涨跌%":>7}')
    for code, name, pct in rows:
        print(f'{code:<8}  {name:<14}  {_pct_s(pct)}')
    print(f'共 {len(rows)} 个 (行业+概念去重)。K线/分时: prism kline <名称或BK代码>')
    return 0

def _act_std(action_name):
    """编排动作的通用子命令包装

    与 mcp 透传的区别: 位置参数直接给 symbol/codes (不用 --arg symbol=),
    渲染层按动作名走对表格, 编排层错误转 StockError 统一退出码。
    """
    def run(args, cfg):
        params = {}
        # 位置参数 → symbol (支持多个, 编排层只吃一个则取首个)
        codes = [c for c in (list(args.codes) if args.codes else []) if c]
        if codes and 'symbol' not in params:
            params['symbol'] = codes[0]
        # 指数动作: 中文别名/裸 6 位在动作层归一, 编排层只认标准形态
        if action_name == 'stock_index' and params.get('symbol'):
            params['symbol'] = _index_symbol(params['symbol'])
        params.update(_args_dict(args))
        res = _srv.do_call(action_name, params, timeout=args.timeout)
        # 板块清单类 ({data.names}): -n 作用于条目数
        try:
            names = (res or {}).get('data', {}).get('names')
            lim = int(getattr(args, 'limit', 0) or 0)
            if isinstance(names, list) and lim > 0:
                res['data']['names'] = names[:lim]
        except (AttributeError, TypeError, KeyError):
            pass
        return res
    return run


"""stock text 视图分派: action → 渲染函数"""
"""stock 子命令的 text 视图: 各 action 的纯文本渲染"""
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
import json



from prism.stock.command._common import _passthrough
from prism.stock.command._common import _j
from prism.stock.command._common import _unresolved

# 视图助手: _render 等外部调用方按本模块 (text 视图门面) 取用, 不直接
# 摸子模块 —— 子模块怎么分是内部事, 对外只认这一层
from prism.stock.command._textfmt_quote import _industry_cell as _industry_cell
from prism.stock.command._textfmt_quote import _screen_counts as _screen_counts
from prism.stock.command._textfmt_quote import _text_analyze
from prism.stock.command._textfmt_quote import _text_announcement
from prism.stock.command._textfmt_quote import _text_valuation
from prism.stock.command._textfmt_quote import _text_position
from prism.stock.command._textfmt_quote import _text_patterns
from prism.stock.command._textfmt_quote import _text_flow
from prism.stock.command._textfmt_quote import _text_holder
from prism.stock.command._textfmt_quote import _text_kline
from prism.stock.command._textfmt_quote import _text_intraday
from prism.stock.command._textfmt_data import _text_calendar
from prism.stock.command._textfmt_data import _text_check
from prism.stock.command._textfmt_data import _text_find
from prism.stock.command._textfmt_data import _text_holders_detail
from prism.stock.command._textfmt_data import _text_index_quote
from prism.stock.command._textfmt_data import _text_screener
from prism.stock.command._textfmt_data import _text_data_find
from prism.stock.command._textfmt_data import _text_domain_detail
from prism.stock.command._textfmt_data import _text_domains
from prism.stock.command._textfmt_data import _text_financials
from prism.stock.command._textfmt_data import _text_eco_list
from prism.stock.command._textfmt_data import _text_raw
from prism.stock.command._textfmt_quote import _text_risk
from prism.stock.command._textfmt_quote import _text_screen
from prism.stock.command._textfmt_quote import _text_sentiment
from prism.stock.command._textfmt_data import _text_srv
from prism.stock.command._textfmt_ak import _text_ak as _text_ak

# akshare 数据域动作: 渲染规则在自己的模块里 (列名随上游变)
_AK_ACTIONS = ('lhb', 'dzjy', 'unlock', 'jgdy', 'yanbao', 'gdhs',
               'macro', 'hsgt', 'breadth', 'cb', 'etf', 'zt_pool',
               'dupont', 'growth', 'comment', 'yjyg', 'pledge',
               'rating', 'goodwill', 'changes', 'hot', 'buyback', 'shares',
               'notice', 'yysj', 'yjbb', 'fhps', 'ggcg', 'mgmt',
               'futures', 'option', 'fund', 'bond', 'hk',
               'fam', 'fam-list', 'commands', 'datacenter')

def _text_schema(out):
    """prism schema 的可读输出"""
    if not isinstance(out, dict):
        print(_j(out, 2000))
        return
    cmds = out.get('commands')
    if cmds is not None:
        print(f"命令目录 — {out.get('count')} 个命令")
        for c in cmds:
            fam = (f" [{c['family']}·{c.get('kinds_count', 0)}口径]"
                   if c.get('family') else '')
            print(f"  {c['command']:22} {c.get('summary', '')}{fam}")
        return
    kinds = out.get('kinds')
    if isinstance(kinds, list):
        print(f"{out.get('command')} — 口径 {out.get('count')} 个"
              f" (族 {out.get('family')})")
        for k in kinds:
            st = k.get('status') or ''
            mark = {'ok': '✓', 'empty': '○', 'err': '✗'}.get(st, st)
            print(f"  {k['name']:26} {mark} {k.get('desc') or ''}")
        return
    print(f"{out.get('command')} — {out.get('summary', '')}")
    params = out.get('params') or []
    if params:
        print('  参数:')
        for p in params:
            flag = '必填' if p.get('required') else (
                f"默认 {p.get('default')}" if 'default' in p else '可选')
            print(f"    {p['name']:14} {p.get('type', 'str'):6} {flag}")
    if out.get('family'):
        print(f"  功能族: {out['family']} ({out.get('kinds_count')} 个口径)")
    if out.get('kind'):
        k = out['kind']
        print(f"  口径 {k['name']} → 接口 {k.get('interface')} "
              f"[{k.get('status')}] {k.get('desc') or ''}")
        d = k.get('dedicated')
        if d:
            print(f"  专用入口: {d['usage']}  ({d['note']})")
    env = (out.get('json') or {}).get('envelope') or {}
    if env:
        print('  JSON 信封:')
        for k, v in env.items():
            print(f'    {k:8} {v}')


def _text(out, action):
    # find 的展开视角复用其它目录的渲染器: 结果里带 _render 就切过去
    if isinstance(out, dict) and out.get('_render'):
        action = out.pop('_render')
    if action == 'dividend':
        # 带代码 → baostock 个股分红历史; 不带 → 原生全市场排行
        if isinstance(out, dict) and 'rows' in out:
            _text_ak(out, 'dividend')
        else:
            from prism.stock.command._textfmt_ak import _text_dividend_rank
            _text_dividend_rank(out)
        return
    # margin / valuation 有原生形态, 只有带 rows 的才是数据域结果
    if action in ('margin', 'valuation'):
        if isinstance(out, dict) and 'rows' in out:
            key = ('idxval' if '指数' in str(out.get('title')) else 'market_val') \
                if action == 'valuation' else (
                'margin_hist' if out.get('title', '').startswith('两融余额') else 'margin')
            _text_ak(out, key)
        elif action == 'valuation' and isinstance(out, dict) and \
                ('pe' in out or 'pb' in out):
            _text_valuation(out)
        else:
            _text_srv(out, note_only=bool(_unresolved(out)))
        return
    # fam / fam-list: 扩展口径与目录
    if action in ('fam', 'fam-list', 'commands', 'datacenter'):
        _text_ak(out, action if action in ('fam', 'fam-list') else 'fam-list')
        return
    # holders/boards/breadth 带 rows 的是数据域扩展结果 (原生口径不带 rows)
    if action in ('holders', 'boards', 'breadth') and isinstance(out, dict) and 'rows' in out:
        _text_ak(out, {'holders': 'free_holders', 'boards': 'sector',
                       'breadth': 'breadth_hist'}[action])
        return
    # 龙虎榜统计口径列名与明细不同, 按 kind 换表头
    if action == 'lhb' and isinstance(out, dict) and out.get('kind'):
        _text_ak(out, 'lhb_' + str(out['kind']))
        return
    if action in _AK_ACTIONS:
        _text_ak(out, action)
        return
    # pool --type 走 akshare 时形状是 {source, rows}, 与原生的涨停池不同
    if action == 'data' and isinstance(out, dict) and 'domains' in out:
        _text_domains(out)
        return
    if action == 'data' and isinstance(out, dict) and out.get('domain') and 'sources' in out:
        _text_domain_detail(out)
        return
    if action == 'data' and isinstance(out, dict) and 'keyword' in out:
        _text_data_find(out)
        return
    if action == 'data' and isinstance(out, dict) and out.get('layer') == 'eco':
        _text_eco_list(out)
        return
    if action == 'pool' and isinstance(out, dict) and out.get('source') == 'akshare':
        _text_ak(out, 'zt_pool')
        return
    if action and action.startswith('docs-'):
        c = out.get('content')
        if c:
            print(c)
            rest = {k: v for k, v in out.items() if k != 'content'}
            if rest:
                print('\n--- meta ---')
                print(json.dumps(rest, ensure_ascii=False, indent=1))
            return
        print(_j(out, 2000))
        return

    if action == 'schema':
        _text_schema(out)
        return
    if action == 'eco-health':
        for lib, st in (out or {}).items():
            if st.get('installed'):
                print(f"  ✓ {lib}: {st.get('funcs')} 个接口")
            else:
                print(f"  ✗ {lib}: 未安装")
        return
    if action == 'announcement':
        _text_announcement(out)
        return
    if action == 'news' and isinstance(out, dict) and out.get('source') == 'akshare':
        # akshare 口径: [{新闻标题, 新闻内容, 发布时间, 文章来源, 新闻链接}]
        print(f"新闻 (东财, {len(out.get('data') or [])} 条)")
        for it in out.get('data') or []:
            print(f"  {it.get('发布时间', '')}  {it.get('新闻标题', '')}")
            print(f"    {it.get('文章来源', '')}  {it.get('新闻链接', '')}")
        return
    if action == 'screener' and isinstance(out, dict) and isinstance(out.get('data'), list):
        _text_screener(out)
        return
    if action == 'check' and isinstance(out, dict) and 'checks' in out:
        _text_check(out)
        return
    if action == 'holders' and isinstance(out, dict) \
            and isinstance(out.get('data'), dict) and out['data'].get('items'):
        _text_holders_detail(out)
        return
    if action == 'index' and isinstance(out, dict) and (out.get('data') or {}).get('rows'):
        _text_index_quote(out)
        return
    if action == 'financials' and isinstance(out, dict):
        _text_financials(out)
        return
    if action in ('news', 'mcp'):
        _text_srv(out, note_only=bool(_unresolved(out)))
        return
    if action == 'holder':
        _text_holder(out)
        return
    if action in ('lookup', 'find'):
        _text_find(out)
        return
    if action == 'source':
        _text_srv(out, note_only=False)
        return
    if action in ('forecast', 'sources'):
        # 不跑 _unresolved 守卫: 那守卫针对 news/announcement 那类"本该给列表
        # 却回了原始 HTML"的情况。数据源层有些接口 (如 ths_stockpage_finance)
        # 本身就返回 HTML 表格, 套同一个守卫会误报成"未解析"。
        _text_raw(out, action)
        return
    if action == 'patterns':
        _text_patterns(out)
        return
    if action == 'position':
        _text_position(out)
        return
    if action == 'valuation':
        _text_valuation(out)
        return
    if action == 'analyze':
        _text_analyze(out)
        return
    if action == 'risk':
        _text_risk(out if isinstance(out, dict) else {})
        return
    if action == 'flow':
        _text_flow(out)
        return
    if action == 'kline':
        _text_kline(out)
        return
    if action == 'intraday':
        _text_intraday(out)
        return
    if action in ('report', 'diagram'):
        _passthrough(out, 'md' if action == 'diagram' else 'report')
        return
    if action == 'excel':
        if isinstance(out, dict) and out.get('ok'):
            print(f"已导出 {out.get('path')} — 通过 {out.get('passed')} / 剔除 {out.get('failed')}")
        else:
            print(json.dumps(out, ensure_ascii=False))
        return
    if action == 'sentiment':
        _text_sentiment(out)
        return
    if action == 'quote':
        for q in out:
            if not q.get('ok'):
                print(f"[{q.get('input')}] 无数据: {q.get('err')}")
                continue
            parts = [f"[{q.get('name')}] {q.get('现价')}  {q.get('涨跌幅')}%"]
            for k, tpl in (('换手%', '换手{}%'), ('量比', '量比{}'),
                           ('流通市值亿', '流通市值{}亿'), ('总市值亿', '市值{}亿'),
                           ('PE动', 'PE{}')):
                if q.get(k) not in (None, '', 'None'):
                    parts.append(tpl.format(q[k]))
            print('  '.join(parts))
        return
    if action == 'screen' and isinstance(out, dict):
        _text_screen(out)
        return
    if action == 'tools' and isinstance(out, dict) and 'tools' in out:
        for t in out['tools']:
            print(f"{t['name']}  {t.get('desc')}")
        ds = out.get('datasets') or {}
        if ds:
            print('\nakshare 数据域 (事件/宏观, 独立命令):')
            for name, desc in ds.items():
                print(f'  {name}  {desc}')
        return
    if action == 'pool' and isinstance(out, dict):
        if not out.get('ok'):
            print(f"涨停池失败: {out.get('err') or out.get('error')}")
            return
        print(f"涨停池 {out.get('date')} — {out.get('count')} 只")
        if out.get('提示'):
            print(f"⚠ {out['提示']}")
        for r in out.get('rows') or []:
            print(f"[{r.get('code')}] {r.get('name')}  {r.get('行业') or ''}  "
                  f"连板{r.get('连板', '—')}  {r.get('涨停统计') or ''}  "
                  f"封单{r.get('封单亿', '—')}亿")
        return
    if action == 'calendar' and isinstance(out, dict) and '是否交易日' in out:
        _text_calendar(out)
        return
    # 板块名列表 (industry/concept 原生口径): 直接排开
    if isinstance(out, dict) and isinstance(out.get('data'), dict) \
            and isinstance(out['data'].get('names'), list):
        junk = {'下一页', '尾页', '上一页', '首页'}
        names = [str(x) for x in out['data']['names']
                 if str(x).strip() and str(x) not in junk]
        print(f"板块 {len(names)} 个: " + '、'.join(names))
        return
    # 通用兜底: 非结构化的按 key: value 或原样 JSON
    if isinstance(out, dict):
        for k, v in out.items():
            if isinstance(v, (dict, list)):
                print(f"{k}: {_j(v, 2000)}")
            else:
                print(f"{k}: {v}")
    else:
        print(_j(out, 2000))


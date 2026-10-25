"""stock text 视图: 裸调用/生态库/服务/原始字段类 (data 与 srv 族)"""
from prism.util.num import fmt_fixed
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



from prism.stock.command._common import _items_of
from prism.stock.command._common import _j


def _text_item(it):
    """单条记录: 有标题就先给标题再列关键字段; 否则按键值列全 (截断长值)。"""
    head = next((it[k] for k in ('title', 'name', 'report_date', '公告标题')
                 if it.get(k)), None)
    if head:
        print(f'- {head}')
    for k, v in it.items():
        if v in (None, '', 0) and k != 'report_date':
            continue                      # 缺数据不显形, 别让 0/空 冒充真实值
        if isinstance(v, (dict, list)):
            print(f'  {k}: {json.dumps(v, ensure_ascii=False)[:200]}')
        else:
            print(f'  {k}: {v}')

def _text_srv(out, note_only=False):
    """动作载荷的 text 渲染: 结构化则列条目, 未解析只给提示。

    载荷固定是 {"ok", "source", "data"(可能是 dict / 字符串化 JSON / raw html)}。
    """
    if note_only:
        return
    if not isinstance(out, dict):
        print(_j(out, 2000))
        return
    source = out.get('source')
    if source:
        print(f'源: {source}')
    data = out.get('data')
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            print(data[:500])
            return
    if isinstance(data, dict):
        items = _items_of(data)
        if items is not None:
            if not items:
                print('(无条目)')
                return
            for it in items:
                if not isinstance(it, dict):
                    print(str(it)[:300])
                    continue
                _text_item(it)
            return
        for k, v in data.items():
            if k in ('html', 'raw_html'):
                continue
            if isinstance(v, (dict, list)):
                print(f'{k}: {json.dumps(v, ensure_ascii=False)[:400]}')
            else:
                print(f'{k}: {v}')
        return
    print(_j(data, 2000))

def _text_raw(out, action=''):
    """原始载荷: 摘要 + 键结构, 不倾倒原始 JSON。

    数据源层返回的数据量动辄几十 KB (股东研究一家 34KB), 全量印出来
    既刷屏又淹掉重点。这里只给: 状态 / 来源 / 各键的条目数与首条要点。
    要全量用 -f json。
    """
    if not isinstance(out, dict):
        print(_j(out, 2000))
        return
    if action == 'sources' and 'keyword' not in out:
        how = '功能' if out.get('by') == 'function' else '源站点'
        print(f"数据源层共 {out.get('count')} 个方法 (按{how}分组):")
        if out.get('by') == 'function':
            for label, c in (out.get('categories') or {}).items():
                n = len(c['primary']) + len(c['fallback'])
                cli = c.get('cli') or []
                print(f"\n{label} ({n})  {c['desc']}")
                print(f"  子命令: {' '.join(cli) if cli else '(仅通用入口)'}")
                print(f"  首选: {' '.join(c['primary'])}")
                if c['fallback']:
                    print(f"  备选: {' '.join(c['fallback'])}")
            return
        for src, ms in (out.get('methods') or {}).items():
            print(f"  {src}({len(ms)}): {' '.join(ms[:6])}{' …' if len(ms) > 6 else ''}")
        return
    if action == 'sources' and 'keyword' in out:
        if out.get('by') == 'category':
            print(f'"{out["keyword"]}" 命中 {out["count"]} 个功能类:')
            for label, c in (out.get('categories') or {}).items():
                print(f"\n{label}  {c['desc']}")
                print(f"  首选: {' '.join(c['primary'])}")
                if c['fallback']:
                    print(f"  备选: {' '.join(c['fallback'])}")
            return
        print(f'"{out["keyword"]}" 命中 {out["count"]} 个方法:')
        for m in (out.get('methods') or []):
            cat = f"[{m['category']}] " if m.get('category') else ''
            print(f"  {cat}{m['method']}{m['sig']}")
            if m.get('doc'):
                print(f"      {m['doc'][:90]}")
        return
    print(f"ok={out.get('ok')}" + (f"  源={out['source']}" if out.get('source') else '')
          + (f"  {out['raw_size']} 字符" if out.get('raw_size') else ''))
    if out.get('error'):
        print(f'  错误: {out["error"]}')
        return
    data = out.get('data')
    if not isinstance(data, dict):
        print(json.dumps(data, ensure_ascii=False)[:1000])
        return
    for k, v in data.items():
        if isinstance(v, list):
            if not v:
                print(f'  {k}: (空)')
            else:
                first = v[0]
                hint = (', '.join(list(first)[:5]) + '…'
                        if isinstance(first, dict) else str(first)[:60])
                print(f'  {k}: {len(v)} 条  首条字段[{hint}]')
        elif isinstance(v, dict):
            print(f'  {k}: {{}} {len(v)} 键 {list(v)[:5]}')
        elif v not in (None, '', []):
            print(f'  {k}: {str(v)[:80]}')

def _text_raw_tail(out):
    """给摘要渲染收尾: 剩下的键用条数说明 (不重复已展示的大块)"""
    data = out.get('data') or {}
    shown = {'gdrs', 'sdgd', 'jgcc', 'sdltgd'}
    rest = [k for k in data if k not in shown]
    if rest:
        parts = [f'{k}({len(data[k])})' if isinstance(data[k], (list, dict)) else k
                 for k in rest]
        print(f"\n其余字段: {', '.join(parts)}  (用 -f json 看全量)")

def _text_eco_list(out):
    if not isinstance(out, dict):
        print(json.dumps(out, ensure_ascii=False))
        return
    lib, n = out.get('library'), out.get('count')
    if 'signature' in out:
        print(f"{lib}.{out.get('name')}  ({out.get('lib')} 共 {n} 个接口)")
        print(f"  签名: {out['signature']}")
        doc = (out.get('doc') or '').strip().splitlines()
        for line in doc[:6]:
            print(f'  {line}')
        return
    print(f"{lib} 共 {n} 个接口")
    for f in out.get('funcs') or []:
        print(f'  {f}')
    if out.get('truncated'):
        print('  …用 --limit 调整, 或 prism data find <关键词> 精确找')


def _text_data_find(out):
    """data find: 按来源分行, 别把 JSON 糊一屏"""
    src = out.get('sources') or {}
    print(f"关键词: {out.get('keyword')}  (共 {out.get('count')} 条)")
    ak = src.get('ak') or {}
    for h in (ak.get('hits') or []):
        print(f"  {h['func']:<34} {h['desc'][:44]}  [{h['score']}]")
    if ak.get('error'):
        print(f"  akshare 目录检索不可用: {ak['error']}")
    eco = src.get('eco') or {}
    for lib, fs in (eco.get('hits') or {}).items():
        if fs:
            print(f"  eco/{lib}: " + ', '.join(fs[:8]))
    s1 = src.get('source') or {}
    if s1.get('methods'):
        print("  数据源: " + ', '.join(s1['methods'][:8])
              + (f"  (class {s1['category'].get('label')})" if s1.get('category') else ""))
    em = src.get('em') or {}
    if em.get('hits'):
        print("  em 配方: " + ', '.join(str(h.get('reportName') or h)
                                       for h in em['hits'][:6]))
    for n in (out.get('notes') or []):
        print(f"  注: {n}")


def _text_calendar(o):
    print(f"{o.get('今天')} — {'交易日' if o.get('是否交易日') else '休市'}")
    print(f"  上一交易日 {o.get('上一交易日')}   下一交易日 {o.get('下一交易日')}")
    near = o.get('近期') or {}
    if near.get('上'):
        print('  往前: ' + '  '.join(near['上']))
    if near.get('下'):
        print('  往后: ' + '  '.join(near['下']))



def _text_screener(o):
    rows = o.get('data') or []
    print(f"选股 {len(rows)} 只")
    print(f"  {'代码':<7}{'名称':<9}{'现价':>8}{'涨跌%':>8}{'PE':>8}{'PB':>6}{'换手%':>7}")
    for r in rows:
        print(f"  {str(r.get('code')):<7}{str(r.get('name'))[:8]:<9}"
              f"{fmt_fixed(r.get('trade')):>8}{fmt_fixed(r.get('changepercent')):>8}"
              f"{fmt_fixed(r.get('per')):>8}{fmt_fixed(r.get('pb')):>6}"
              f"{fmt_fixed(r.get('turnoverratio')):>7}")


def _text_check(o):
    checks = o.get('checks') or []
    print(f"可买 {o.get('可买数')}/{o.get('count')}")
    for c in checks:
        mark = '✓' if c.get('可买') else '✗'
        why = c.get('err') or c.get('板块') or ''
        print(f"  {c.get('code')}  {mark}  {why}")


def _text_holders_detail(o):
    d = o.get('data') or {}
    times = d.get('times') or []
    total = d.get('total') or {}
    print(f"机构持仓 {times[0].get('name') if times else ''}"
          f"  持股比例 {fmt_fixed(total.get('held_ratio'))}%"
          f"  变动 {fmt_fixed(total.get('chg'))}%")
    for it in (d.get('items') or [])[:10]:
        print(f"  {str(it.get('holder_name'))[:34]:<34}"
              f"{fmt_fixed(it.get('held_num'), 0):>14} 股"
              f"{fmt_fixed(it.get('held_ratio')):>7}%"
              f"{fmt_fixed(it.get('chg')):>8}%")


def _text_index_quote(o):
    rows = (o.get('data') or {}).get('rows') or []
    for r in rows:
        f = str(r.get('data') or '').split('~')
        if len(f) < 35:
            print(r)
            continue
        print(f"[{f[1]}] {f[2]}  {f[3]}  {f[31]} ({f[32]}%)  "
              f"高 {f[33]} / 低 {f[34]}")


def _text_domains(o):
    ds = (o or {}).get('domains') or {}
    if not ds:
        print(o)
        return
    print(f"数据域 {len(ds)} 个:")
    for name, d in ds.items():
        cnt = d.get('eco_akshare')
        extra = d.get('commands') or d.get('families') or ''
        line = f"  {name:<6} {d.get('desc') or ''}"
        if cnt:
            line += f"  [{cnt} 接口]"
        if extra:
            line += f"  {extra}"
        print(line)


_FIN_LABEL = {
    'report_date': '报告期', 'total_revenue': '营收', 'net_profit_atsopc': '归母净利',
    'operating_income_yoy': '营收同比%', 'net_profit_atsopc_yoy': '净利同比%',
    'avg_roe': 'ROE%', 'gross_selling_rate': '毛利率%', 'net_selling_rate': '净利率%',
    'asset_liab_ratio': '资产负债率%', 'basic_eps': '每股收益',
    'np_per_share': '每股净资产', 'pe_ttm': 'PE(TTM)', 'pb': 'PB',
    'total_shares': '总股本', 'float_shares': '流通股本',
    'market_capital': '总市值', 'float_market_capital': '流通市值',
    'dividend': '每股分红', 'dividend_yield': '股息率%',
    'pledge_ratio': '质押比例%', 'goodwill_in_net_assets': '商誉/净资产%',
    'currency': '币种',
}


def _text_financials(o):
    d = (o or {}).get('data') or {}
    items = d.get('items') or []
    print(f"财务 {d.get('symbol') or ''}  {len(items)} 期  (源 {(o or {}).get('source')})")
    for it in items:
        head = it.get('report_date') or ''
        print(f"\n{head}")
        for k, v in it.items():
            if k == 'report_date' or v is None:
                continue
            label = _FIN_LABEL.get(k, k)
            if isinstance(v, float):
                v = f'{v:.2f}'
            print(f"  {label:<10}{v}")


def _text_find(out):
    """统一检索结果: 每类一块, 每条后面跟下一步该敲什么"""
    if not isinstance(out, dict):
        print(out)
        return

    def clip(txt, n):
        t = str(txt or '').replace('\n', ' ').strip()
        return t if len(t) <= n else t[:n - 1] + '…'

    kw = out.get('keyword') or ''
    secs = out.get('sections') or []
    total = sum(len(x.get('rows') or []) for x in secs)
    shown = sum(len(x.get('rows_shown') or []) for x in secs)
    live = [x for x in secs if x.get('rows') or x.get('err')]
    print(f'关键词 "{kw}" — 命中 {total} 条 / {len(live)} 类'
          + (f', 显示 {shown} 条 (加 -n 看更多)' if total > shown else ''))
    for sec in secs:
        rows = sec.get('rows_shown') or []
        title = sec.get('title') or sec.get('key')
        if sec.get('err'):
            print(f'\n{title}  检索失败: {sec["err"]}')
            continue
        if not rows:
            continue
        allrows = sec.get('rows') or []
        head = f'\n{title} — {len(allrows)} 条'
        if len(allrows) > len(rows):
            head += f' (显示前 {len(rows)} 条, 加 -n 看更多)'
        print(head)
        def key_of(r):
            if sec['key'] == 'commands':
                return r['name']
            if sec['key'] == 'kinds':
                return f'{r["cmd"]}/{r["kind"]}'
            return r.get('method') or r.get('name') or ''
        w = min(max([len(key_of(r)) for r in rows] or [0]) + 2, 40)
        for r in rows:
            if sec['key'] == 'commands':
                left = f'  {r["name"]:<{w}}{clip(r.get("desc"), 40)}'
                extra = f'  [{r["kinds"]} 个口径]' if r.get('kinds') else ''
            elif sec['key'] == 'kinds':
                left = f'  {key_of(r):<{w}}{clip(r.get("desc"), 36)}'
                extra = '  [失效]' if r.get('st') == 'err' else ''
            elif sec['key'] == 'sources':
                left = f'  {r["method"]:<{w}}{clip(r.get("label"), 28)}'
                extra = ''
            elif sec['key'] == 'reports':
                left = f'  {r["name"]:<{w}}{clip((r.get("desc") or "").split("-")[-1], 30)}'
                extra = ''
            else:
                left = f'  {r["name"]}'
                extra = ''
            print(left + extra)
            if r.get('next'):
                print(f'  {"":<{w}}→ {r["next"]}')
    if not total:
        print('\n没命中。换个词 (命令名 / 口径名 / 方法名 / 中文说法) 再试, '
              '或 prism find <接口名> --only api')


def _text_domain_detail(o):
    """find --domain X: 域内接口清单 (按库分组, 名字一行多个)"""
    o = o or {}
    dom = o.get('domain') or ''
    desc = o.get('desc') or ''
    print(f'数据域 {dom}' + (f' — {desc}' if desc else ''))
    srcs = o.get('sources') or {}
    for lib, info in srcs.items():
        funcs = list(info.get('funcs') or [])
        total = info.get('count') or len(funcs)
        print(f'\n  {lib} ({total} 个' + (f', 显示 {len(funcs)}' if len(funcs) < total else '') + '):')
        line = '   '
        for f in funcs:
            if len(line) + len(f) > 96:
                print(line)
                line = '   '
            line += ' ' + f
        if line.strip():
            print(line)
    print('\n下一步: prism find <关键词> --only api  或  prism data call <接口>')

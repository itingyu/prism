"""stock data 域动作: 接口目录查询与裸调用 (data-*)"""
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
import re

from prism.stock.bridge import eco as _eco
from prism.stock.bridge import _eco_net
from prism.stock.bridge import rawapi as _raw


from prism.stock.command._common import _DATA_DOMAINS
from prism.stock.command._common import _args_dict
from prism.stock.command._common import _http_client

def _act_api_list(args, cfg):
    """数据源层方法清单。--by function 给功能维度 (回答"要干什么"),
    默认按数据源分组 (回答"哪个站")。"""
    lim = int(getattr(args, 'limit', 0) or 0)
    def cut(seq):
        return seq[:lim] if lim else seq
    if (getattr(args, 'by', '') or 'source') == 'function':
        groups = _raw.methods_by_function()
        return {'count': len(_raw.methods()), 'by': 'function',
                'categories': {k: {'desc': v['desc'],
                                   'cli': v.get('cli') or [],
                                   'primary': cut(v['primary']),
                                   'fallback': cut(v['fallback'])}
                               for k, v in groups.items()}}
    ms = _raw.methods_by_source()
    return {'count': sum(len(v) for v in ms.values()),
            'by': 'source',
            'by_source': {k: len(v) for k, v in ms.items()},
            'methods': {k: cut(v) for k, v in ms.items()}}

def _act_api_search(args, cfg):
    """按功能类或关键词找接口。

    Agent 的真实问题不是"有哪些方法"而是"查财报该调哪个" —— 分类表解决
    功能维度, 关键词解决 docstring 里的口语说法 (利润表/资产负债表/十大股东)。
    """
    kw = ' '.join(list(args.codes or [])).strip() or (args.keyword or '').strip()
    if not kw:
        raise ValueError('sources 检索需要关键词或功能类 '
                         '(prism lookup --by site 看全部)')
    cats = _raw.categories()
    # 先按类码/中文标签/别名精确命中 —— 给的是"财报""利润表"这类口语说法时
    # 直接列该类。必须优先于下面的模糊搜, 否则"财报"会因为公告资讯的 desc
    # 里含"财报日历"而先命中错的那一类。
    hit = _raw.by_alias(cats, kw)
    if hit is not None:
        # 精确命中也要带 keyword/by, 否则渲染层分不出是"类命中"还是"方法命中"
        return {'keyword': kw, 'by': 'category', 'count': 1,
                'categories': _raw.methods_by_function(hit['code'])}
    hits = {}
    for code, c in cats.items():
        if code == 'uncategorized':
            continue
        blob = ' '.join([code, c['label'], c['desc'], *c['alias'],
                         *c['primary'], *c['fallback']]).lower()
        if kw.lower() in blob:
            hits[c['label']] = {'code': code, 'desc': c['desc'],
                                'primary': c['primary'], 'fallback': c['fallback']}
    # 功能类没命中就落到方法级关键词 (docstring 里有口语说法)
    method_hits = []
    if not hits:
        for m in _raw.methods():
            d = _raw.method_doc(m) or {}
            blob = f'{m} {d.get("doc", "")}'.lower()
            if kw.lower() in blob:
                cat = _raw.category_of(m)
                method_hits.append({'method': m, 'category': cat,
                                    'sig': d.get('sig', ''), 'doc': d.get('doc', '')})
    if not hits and not method_hits:
        raise ValueError(f'数据源层没匹配 "{kw}"。可用功能类: '
                         + ', '.join(f'{c["label"]}({k})' for k, c in cats.items()
                                     if k != 'uncategorized')
                         + f'\n口径/AK 接口请用: prism data find {kw}')
    out = {'keyword': kw, 'count': len(hits) or len(method_hits)}
    if hits:
        out['by'] = 'category'
        out['categories'] = hits
    else:
        out['by'] = 'method'
        out['methods'] = method_hits[:args.limit] if args.limit else method_hits
        out['truncated'] = bool(args.limit) and len(method_hits) > args.limit
    return out

def _data_search_all(kw, lib, limit):
    """在四类目录里同时搜, 按命中数排来源。任何一层坏了只记 err 不拖垮全局。"""
    out = {'keyword': kw, 'sources': {}}
    total = 0
    # 生态库: 接口名 + 中文 docstring
    try:
        hits = _eco.search(kw, lib=lib, limit=limit)
        n = sum(len(v) for v in hits.values())
        out['sources']['eco'] = {'count': n, 'hits': hits}
        total += n
    except Exception as e:                                  # noqa: BLE001
        out['sources']['eco'] = {'error': f'{type(e).__name__}: {e}'}
    # akshare 目录自身的模糊检索 (支持整句, 与上面的名字匹配互补)
    try:
        ak_hits = _eco.ak_search(kw, limit=min(int(limit or 10), 20))
        if ak_hits:
            out['sources']['ak'] = {'count': len(ak_hits), 'hits': ak_hits}
            total += len(ak_hits)
    except Exception as e:                                  # noqa: BLE001
        out['sources']['ak'] = {'error': f'{type(e).__name__}: {e}'}
    # 数据源层 154 方法: 分类别名 + docstring
    try:
        cats = _raw.categories()
        hit = _raw.by_alias(cats, kw)
        if hit is not None:
            ms = list(hit['primary']) + list(hit['fallback'])
            out['sources']['source'] = {'count': len(ms), 'category': hit,
                                     'methods': ms}
            total += len(ms)
        else:
            idx = _raw.methods_by_source()
            found = {m: f"{src}" for src, ms in idx.items() for m in ms
                     if kw.lower() in m.lower()}
            if found:
                out['sources']['source'] = {'count': len(found), 'methods': found}
                total += len(found)
    except Exception as e:                                  # noqa: BLE001
        out['sources']['source'] = {'error': f'{type(e).__name__}: {e}'}
    # 东财配方 (离线)
    try:
        from prism.stock.bridge import em as _em
        reps = _em.list_reports(kw, limit=limit)
        n = reps.get('count') or 0
        if n:
            out['sources']['em'] = {'count': n, 'reports': reps}
            total += n
    except Exception as e:                                  # noqa: BLE001
        out['sources']['em'] = {'error': f'{type(e).__name__}: {e}'}
    out['count'] = total
    return out

def _data_domain_names():
    return list(_DATA_DOMAINS)

def _act_data_find(args, cfg):
    """data find <关键词>: 四类目录一次搜 (eco/数据源/em/docs), 结果带来源

    域内搜索 (data 行情 find 茅台): eco 结果按该域正则过滤, 结果标注 domain。
    """
    kw = ' '.join(list(args.codes or [])).strip() or (args.keyword or '').strip()
    if not kw:
        raise ValueError('data find 需要关键词, 例: prism data find 龙虎榜')
    out = _data_search_all(kw, args.lib, args.limit or 10)
    # 域内搜索: 过滤 eco 结果到本域
    dom = getattr(args, '_data_domain', None)
    if dom and dom in _DATA_DOMAINS and 'eco' in out.get('sources', {}):
        pat = _DATA_DOMAINS[dom][2]
        eco_src = out['sources']['eco']
        hits = eco_src.get('hits') or {}
        eco_src['hits'] = {lib: [f for f in fs if re.search(pat, f)]
                           for lib, fs in hits.items()}
        eco_src['count'] = sum(len(v) for v in eco_src['hits'].values())
        eco_src['domain'] = dom
        out['count'] = eco_src['count']
    return out

def _act_data_call(args, cfg):
    """data call <名称>: 按名路由到 数据源方法 / eco 接口 / em 配方

    路由顺序: em 配方 (RPT_ 前缀或配方表命中) → 数据源层方法 (精确命中)
    → 生态库接口。--lib 强制生态库; --full 只对 eco 生效。
    """
    name = args.method or ((list(args.codes) or [''])[0] if args.codes else '')
    if not name:
        raise ValueError('data call 需要接口/方法名; 不知道叫什么先 '
                         'prism data find <关键词>')
    kw = _args_dict(args)
    if (getattr(args, 'lib', None) or '') not in ('', 'akshare'):
        return _eco.call(args.lib, name, kw, full=args.full)
    # em 配方: RPT_ 前缀一眼定, 其余名字查配方表
    from prism.stock.bridge import em as _em
    if name.upper().startswith('RPT_'):
        pages = int(kw.pop('pages', 1) or 1)
        r = _em.run(name, max_pages=pages, http=_http_client(args), **kw)
        if args.raw:
            return {'reportName': name, 'func': r['func'], 'rows': r['rows'],
                    'columns': list(r['df'].columns),
                    'records': r['df'].head(args.limit or 10).to_dict('records')}
        return r['df']
    # 数据源层方法精确命中 → 数据源语义
    if name in _raw.methods():
        return _raw.call(name, kw)
    # 其余落生态库 (报错信息里给出最近的候选, 引导用 data find)
    from prism.stock.params import fit as _fit_params
    return _eco.call(args.lib or 'akshare', name, _fit_params(name, kw), full=args.full)

def _act_data_url(args, cfg):
    """data url <URL>: 裸 HTTP 直调, 合并原 http-get/post/rows

    --post 走 POST (--form 给表单); 默认 GET。返回默认转表格 (--raw 给 JSON)。
    """
    url = (list(args.codes or []) or [''])[0] if args.codes else args.url
    if not url:
        raise ValueError('data url 需要 URL; 用法: prism data url <URL> [--post]')
    h = _http_client(args)
    kw = dict(params=_args_dict(args), referer=args.referer, encoding=args.encoding)
    if args.post:
        t = h.post(url, data=args.form or None, **kw)
    else:
        t = h.get(url, **kw)
    if args.method_only:
        return t
    # 非 JSON 响应 (腾讯行情这类 var xxx="a~b~c") 原样返回, 不硬转表格
    if not args.post and not t.lstrip()[:1] in '{[':
        return t
    df = h.rows(t, pick=args.pick, limit=args.limit)
    if args.raw:
        return {'shape': list(df.shape), 'columns': list(df.columns),
                'records': df.head(args.limit or 10).to_dict('records')}
    return df

def _data_domain_overview(dom, limit=15):
    """单域导航: 该域下 数据源 / eco / em 各有哪些接口 (限量预览)"""
    desc, cat, pat = _DATA_DOMAINS[dom]
    out = {'domain': dom, 'desc': desc, 'sources': {}}
    # 数据源层: 按功能分类 (cat 是分类 code, 如 quote/financial)
    try:
        c = _raw.categories().get(cat)
        if c:
            ms = list(c['primary']) + list(c['fallback'])
            out['sources']['source'] = {'count': len(ms), 'methods': ms[:limit]}
    except Exception as e:                                  # noqa: BLE001
        out['sources']['source'] = {'error': f'{type(e).__name__}: {e}'}
    # eco 层: 按接口名正则 (akshare 为主); '其他' 是兜底域 = 全集减去已归类域
    try:
        fs = _eco.funcs('akshare')
        if dom == '其他':
            claimed = set()
            for d2, (_d, _c, p2) in _DATA_DOMAINS.items():
                if d2 != '其他':
                    claimed.update(f for f in fs if re.search(p2, f))
            hit = [f for f in fs if f not in claimed]
        else:
            hit = [f for f in fs if re.search(pat, f)]
        out['sources']['eco_akshare'] = {'count': len(hit),
                                         'funcs': hit[:limit]}
    except Exception as e:                                  # noqa: BLE001
        out['sources']['eco_akshare'] = {'error': f'{type(e).__name__}: {e}'}
    # em 配方: 复用全域搜
    try:
        from prism.stock.bridge import em as _em
        reps = _em.list_reports(dom, limit=limit)
        n = reps.get('count') or 0
        if n:
            out['sources']['em'] = {'count': n, 'reports': reps}
    except Exception as e:                                  # noqa: BLE001
        out['sources']['em'] = {'error': f'{type(e).__name__}: {e}'}
    out['usage'] = {
        f'data {dom} find 关键词': '域内再搜',
        f'data {dom} call 接口名': '域内调用 (同 data call 路由)',
    }
    return out

def _act_data_list(args, cfg):
    """data list [域|eco|source|em]: 按域或按层列清单

    data list            → 12 个功能域导航 (每域多少接口)
    data list 行情        → 该域下 eco/em 明细
    data list sources|eco|em → 按层
    """
    what = (getattr(args, 'list_what', None) or '').lower()
    if what in _DATA_DOMAINS:
        args.codes = list(args.codes)[1:]
        return _data_domain_overview(what, args.limit or 15)
    if not what:
        # 域总览: 每域 数据源+eco 接口数; '其他' 用差集 (兜底域不重复计数)
        eco_fs = _eco.funcs('akshare')
        claimed = set()
        rows = {}
        for dom, (desc, _cat, pat) in _DATA_DOMAINS.items():
            if dom == '其他':
                eco_n = len(eco_fs) - len(claimed)
            else:
                hit = set(f for f in eco_fs if re.search(pat, f))
                claimed |= hit
                eco_n = len(hit)
            rows[dom] = {'desc': desc, 'eco_akshare': eco_n}
        return {'domains': rows,
                'note': 'data list <域> 看明细; 也可跨域: data find 关键词'}
    what = what or 'eco'
    if what not in ('eco', 'em', 'source', 'sources') and what not in _eco.libs():
        raise ValueError(f'data list 只支持 功能域 / eco / source / em / 库名'
                         f'({", ".join(_eco.libs())}), 没有 "{what}"')
    if what in ('sources', 'source'):
        ms = _raw.methods_by_source()
        return {'layer': 'sources', 'count': sum(len(v) for v in ms.values()),
                'by_source': {k: len(v) for k, v in ms.items()}, 'methods': ms}
    if what == 'em':
        from prism.stock.bridge import em as _em
        return _em.list_reports((args.keyword or ''), limit=args.limit)
    lib = args.lib or ('akshare' if what in ('eco', 'akshare') else what)
    if args.method:                      # 给了接口名 → describe
        out = _eco.describe(args.method, lib)
        out['count'] = len(_eco.funcs(out.get('lib') or lib))
        return out
    all_names = _eco.funcs(lib)
    names = all_names[:args.limit] if args.limit else all_names
    return {'layer': 'eco', 'library': lib, 'count': len(all_names),
            'funcs': names, 'truncated': len(names) < len(all_names)}

def _act_data(args, cfg):
    """data 主动作: 按第二个词分发 (find/call/url/list/health), 无词给导航

    prism data                 → 导航
    prism data find 龙虎榜      → 四类目录一次搜
    prism data call stock_zh_a_hist --arg symbol=600519
    prism data url <URL> [--post]
    prism data list sources|eco|em
    prism data health
    """
    codes = list(args.codes) if args.codes else []
    sub = (codes[0] if codes else '').lower()
    subs = {'find': _act_data_find, 'call': _act_data_call, 'url': _act_data_url,
            'list': _act_data_list, 'health': _act_data_health}
    if sub in subs:
        args.codes = codes[1:]
        if sub == 'find' and not args.keyword:
            args.keyword = ' '.join(args.codes)
            args.codes = []
        if sub == 'list' and args.codes:
            # 层/域名放独立字段, 不能借 args.method —— 那是 --method 的接口名
            args.list_what = args.codes[0]
            args.codes = args.codes[1:]
        return subs[sub](args, cfg)
    # 第二词是功能域 → 域内路由
    if codes and codes[0] in _DATA_DOMAINS:
        dom, rest = codes[0], codes[1:]
        sub2 = (rest[0] if rest else '').lower()
        args._data_domain = dom
        args.codes = rest[1:] if sub2 in ('find', 'call', 'url') else rest
        if sub2 == 'find':
            args.keyword = args.keyword or ' '.join(args.codes)
            args.codes = []
            return _act_data_find(args, cfg)
        if sub2 == 'call':
            return _act_data_call(args, cfg)
        if sub2 == 'url':
            return _act_data_url(args, cfg)
        # 无子动词 → 域导航
        return _data_domain_overview(dom, args.limit or 15)
    if codes:
        raise ValueError(f'data 没有 "{codes[0]}" 这个子命令; 可用: '
                         'list / find / call / url / health '
                         '(取数据源方法: <命令> --source, 清单: prism lookup --by site)')
    return _data_nav()

def _data_nav():
    """data 主动作: 域总览导航 (与 data list 无参同源, 差集兜底防重计)"""
    eco_fs = _eco.funcs('akshare')
    claimed = set()
    domains = {}
    for dom, (desc, _c, pat) in _DATA_DOMAINS.items():
        if dom == '其他':
            eco_n = len(eco_fs) - len(claimed)
        else:
            hit = set(f for f in eco_fs if re.search(pat, f))
            claimed |= hit
            eco_n = len(hit)
        domains[dom] = {'desc': desc, 'eco': eco_n}
    return {
        'usage': {
            'data list': '域总览 (每域接口数)',
            'data list <域>': '域内明细 (数据源 + eco 接口 + em 配方)',
            'data <域> find <关键词>': '域内搜, 例: data 行情 find 茅台',
            'data find <关键词>': '跨域一次搜 eco/数据源/em/docs',
            'data call <名称>': '按名调 (em 配方 → 数据源方法 → eco 接口)',
            'data url <URL>': '裸 HTTP 直调, 反爬已内置',
            'data health': '数据面体检',
        },
        'domains': domains,
        'counts': {'eco_akshare': len(eco_fs), 'source': len(_raw.methods())},
        'note': '不知道接口叫什么 → data <域> 或 data find; '
                '知道名字 → data call; 都封装不了 → data url',
    }

def _act_data_health(args, cfg):
    """data health: 数据面体检 (数据源层 / 生态库 / 东财配方)"""
    from prism.stock.bridge import em as _em
    st = _em.stats()
    return {
        'source': {'ok': _raw.available(), 'methods': len(_raw.methods())},
        'eco': _eco.health(),
        'em_recipes': {'ok': bool(st.get('reports')), **st},
        'route': {'sources': 'per-request (net.transport + RoutedCffiSession)',
                  'eco': {lib: _eco_net.probe(lib)
                          for lib in ('akshare', 'tushare', 'baostock', 'efinance')}},
    }



def _act_schema(args, cfg):
    """prism schema: 命令参数与 JSON 输出结构自描述"""
    from prism.stock.command._schema import all_schema, command_schema
    from prism.cli.stock import COMMANDS  # 运行时才 import, 避免模块级成环
    if getattr(args, 'all_cmds', None):
        return all_schema(COMMANDS)
    name = getattr(args, 'name', None)
    if not name:
        raise ValueError('给一个命令名 (例: prism schema lhb), 或用 --all 列全部')
    if getattr(args, 'list_kinds', None):
        # --list: 列出该命令挂着的全部口径 (与其它命令的 --list 语义一致)
        return _schema_kinds(name, COMMANDS)
    return command_schema(name, COMMANDS, kind=getattr(args, 'kind', None))


def _schema_kinds(name, commands):
    """schema --list: 某命令可用的口径清单"""
    from prism.stock.bridge.ak_families import FAM
    if name not in commands:
        raise ValueError(f'没有这个命令: {name}')
    from prism.stock.command._schema import kind_list
    return kind_list(name, FAM)


def _act_sources(args, cfg):
    """数据源方法清单/检索

    不带关键词 -> 按功能类/来源分组列全部方法; 带关键词 -> 搜方法名与文档。
    """
    kw = ' '.join(str(c) for c in (getattr(args, 'codes', None) or [])).strip()
    kw = kw or (getattr(args, 'keyword', None) or '').strip()
    if kw:
        args.keyword = kw
        return _act_api_search(args, cfg)
    return _act_api_list(args, cfg)


def _act_source(args, cfg):
    """<子命令> --source <方法名>: 点名数据源层方法

    分类表里每类都挂着自己的子命令, 这个动作让"点哪个源"有正经入口
    (不再有通用入口命令):
    - 方法必须属于该命令的功能类, 否则直接报错并指出去哪个命令
    - 参数按方法签名自动适配 (代码形态/条数/日期), 其余走 --arg k=v
    """
    from prism.stock.bridge import source_pick as _sp
    method = (getattr(args, 'source', None)
              or getattr(args, 'method', None) or '').strip()
    if not method:
        raise ValueError('--source 需要方法名 (prism lookup --by site 看清单)')
    known = _sp.all_methods()
    if method not in known:
        nearest = [m for m in known if method in m] or \
                  [m for m in known if m.split('_')[0] == method.split('_')[0]]
        hint = f'; 相近: {", ".join(nearest[:5])}' if nearest else ''
        raise ValueError(f'未知数据源方法: {method}{hint} '
                         f'(prism lookup --by site 看清单)')
    command = getattr(args, 'family', None) or ''
    allowed = _sp.methods_for(command) if command else []
    if allowed and method not in allowed:
        cat = known[method]
        meta = _sp.categories()[cat]
        clis = ' / '.join(f'prism {c}' for c in (meta.get('cli') or []))
        raise ValueError(
            f'{method} 属于「{meta.get("label")}」类, 不在 {command} 名下; '
            f'改用 {clis} --source {method}')
    codes = list(getattr(args, 'codes', None) or [])
    if not codes and getattr(args, 'code', None):
        codes = [args.code]
    out = _sp.call(method, codes=codes,
                   date=getattr(args, 'date', None),
                   limit=getattr(args, 'limit', None),
                   extra=_args_dict(args))
    if isinstance(out, dict) and 'source' not in out:
        out['source'] = method
    return out


def _act_find(args, cfg):
    """唯一的发现入口: 一个词查四层 (命令/口径/源方法/接口)

    四种"视角"也收在这里, 不再单开命令:
      无参 + --family X   某命令的全部口径明细 (原 prism commands --family X)
      无参 + --by site    全部源方法按站点分组 (原 prism lookup --by site)
      无参 + --domain 财报 某个 akshare 域的接口明细 (原 prism data list 财报)
      有词                 四层一起搜, 每条给下一步命令
    """
    kw = ' '.join(str(c) for c in (getattr(args, 'codes', None) or [])).strip()

    # ── 取数 (原 prism data call/url/health)
    if getattr(args, 'call', None):
        args.method, args.codes = args.call, []
        out = _act_data_call(args, cfg)
        if isinstance(out, dict):
            out['_render'] = 'data'
        return out
    if getattr(args, 'url', None):
        args.codes = [args.url]
        out = _act_data_url(args, cfg)
        if isinstance(out, dict):
            out['_render'] = 'data'
        return out
    if getattr(args, 'health', False):
        out = _act_data_health(args, cfg)
        if isinstance(out, dict):
            out['_render'] = 'data'
        return out

    # ── 视角一: 某命令的口径明细 (带接口真名/状态/主备)
    fam = (getattr(args, 'family', None) or '').strip()
    if fam:
        args.action = 'commands'
        args.family, args.codes = fam, []
        from prism.stock.command._actions import _act_commands
        out = _act_commands(args, cfg)
        if isinstance(out, dict):
            out['_render'] = 'commands'
        return out

    # ── 视角二: 源方法按站点/功能分组 (带签名与 docstring)
    by = (getattr(args, 'by', None) or '').strip()
    if by:
        args.action = 'sources'
        args.codes = [kw] if kw else []
        out = _act_sources(args, cfg)
        if isinstance(out, dict):
            out['_render'] = 'sources'
        return out

    # ── 视角三a: 域导航
    if getattr(args, 'domains', False):
        args.action = 'data'
        args.list_what, args.codes = None, []
        out = _act_data_list(args, cfg)
        if isinstance(out, dict):
            out['_render'] = 'data'
        return out

    # ── 视角三b: akshare 数据域明细
    dom = (getattr(args, 'domain', None) or '').strip()
    if dom:
        args.action = 'data'
        args.list_what = dom
        out = _act_data_list(args, cfg)
        if isinstance(out, dict):
            out['_render'] = 'data'
        return out

    if not kw:
        raise ValueError('lookup 需要关键词; 例: prism lookup 股东 / prism lookup 北向')
    only = (getattr(args, 'only', None) or 'all').strip().lower()

    # 只看一层时直接复用原来那条搜索 (它能匹配站点名/docstring, 更准)
    if only in ('sources', 'source', 'src'):
        args.action = 'sources'
        args.codes = [kw]
        out = _act_sources(args, cfg)
        if isinstance(out, dict):
            out['_render'] = 'sources'
        return out
    if only in ('api', 'data'):
        args.action = 'data'
        args.codes = [kw]
        out = _act_data_find(args, cfg)
        if isinstance(out, dict):
            out['_render'] = 'data'
        return out
    only = (getattr(args, 'only', None) or 'all').strip().lower()
    limit = int(getattr(args, 'limit', 10) or 10)
    low = kw.lower()

    def hit(*vals):
        return any(low in str(v).lower() for v in vals if v)

    want = {'all', 'commands', 'kinds', 'sources', 'api', 'reports'}
    alias = {'cmd': 'commands', 'command': 'commands', 'kind': 'kinds',
             'source': 'sources', '接口': 'api', '命令': 'commands',
             '口径': 'kinds', '源': 'sources', '报表': 'reports', 'rpt': 'reports'}
    only = alias.get(only, only)
    if only not in want:
        raise ValueError(f'--only 只认 {"/".join(sorted(want - {"all"}))}')

    secs = []

    # 1) 命令
    if only in ('all', 'commands'):
        from prism.stock.bridge.ak_families import FAM
        from prism.cli.stock import COMMANDS
        rows = []
        for name, fn in COMMANDS.items():
            doc = (getattr(fn, '__doc__', '') or '').strip().splitlines()
            desc = doc[0].strip() if doc else ''
            if hit(name, desc):
                rows.append({'name': name, 'desc': desc,
                             'kinds': len(FAM.get(name) or {}),
                             'next': f'prism {name} -h'})
        secs.append({'key': 'commands', 'title': '命令', 'rows': rows,
                     'more': max(0, len(rows) - limit), 'rows_shown': rows[:limit]})

    # 2) 口径 (--kind)
    if only in ('all', 'kinds'):
        import re as _re
        from prism.stock.bridge.ak_families import FAM
        rows = []
        for fam, items in FAM.items():
            fam_hit = hit(fam)          # 直接搜命令名 → 把这个命令的口径全列出来
            per = 0
            cap = limit if (only == 'kinds' or fam_hit) else 3
            for kind, spec in (items or {}).items():
                if fam_hit or hit(kind, spec.get('n'), spec.get('s')):
                    rows.append({'cmd': fam, 'kind': kind,
                                 'desc': spec.get('s') or '',
                                 'st': spec.get('st') or '',
                                 'next': f'prism {fam} --kind {kind}'})
                    per += 1
                    if per >= cap:
                        break
        secs.append({'key': 'kinds', 'title': '口径 (加 --kind)', 'rows': rows,
                     'more': max(0, len(rows) - limit), 'rows_shown': rows[:limit]})

    # 3) 数据源方法 (--source)
    if only in ('all', 'sources'):
        from prism.stock.bridge import rawapi
        cats = rawapi.categories()
        idx = {}
        for ck, cv in cats.items():
            cli = (cv.get('cli') or [ck])[0]
            for meth in (cv.get('primary') or []) + (cv.get('fallback') or []):
                idx.setdefault(meth, (cv.get('label') or ck, cli,
                                      cv.get('desc') or ''))
        rows = []
        for meth in rawapi.methods():
            label, cli, desc = idx.get(meth, ('', '', ''))
            if hit(meth, label, desc):
                rows.append({'method': meth, 'label': label,
                             'next': f'prism {cli} --source {meth}' if cli else ''})
        secs.append({'key': 'sources', 'title': '数据源方法 (加 --source)',
                     'rows': rows, 'more': max(0, len(rows) - limit),
                     'rows_shown': rows[:limit]})

    # 4) akshare 接口 (data call)
    if only in ('all', 'api'):
        from prism.stock.bridge import eco as _eco
        rows = []
        try:
            hits = _eco.search(kw, lib='akshare', limit=limit)
            for _lib, names in (hits or {}).items():
                for n in names or []:
                    rows.append({'name': n, 'next': f'prism lookup --call {n}'})
        except Exception as e:                                    # noqa: BLE001
            secs.append({'key': 'api', 'title': 'akshare 接口 (data call)',
                         'rows': [], 'more': 0, 'rows_shown': [],
                         'err': f'{type(e).__name__}: {e}'})
        else:
            secs.append({'key': 'api', 'title': 'akshare 接口 (lookup --call)',
                         'rows': rows, 'more': max(0, len(rows) - limit),
                         'rows_shown': rows[:limit]})

    # 5) 东财数据中心报表 (原 prism datacenter, 拆成一条条可搜的报表)
    if only in ('all', 'reports'):
        from prism.stock.bridge import em as _em
        from prism.stock.bridge.ak_families import FAM as _FAM
        fmap = {}
        for fam, items in _FAM.items():
            for kind, spec in (items or {}).items():
                fmap.setdefault(spec.get('n'), (fam, kind))
        rows = []
        try:
            recs = _em.recipes() or {}
        except Exception:                                        # noqa: BLE001
            recs = {}
        for name, r in recs.items():
            use = r.get('use') or ''
            fn = r.get('func') or ''
            if hit(name, use, fn):
                if fmap.get(fn):
                    fam, kind = fmap[fn]
                    nxt = f'prism {fam} --kind {kind}'
                else:
                    nxt = f'prism lookup --call {fn}' if fn and not fn.startswith('_') else ''
                rows.append({'name': name, 'desc': use, 'func': fn, 'next': nxt})
        secs.append({'key': 'reports', 'title': '东财数据中心报表 (已并入各命令)',
                     'rows': rows, 'more': max(0, len(rows) - limit),
                     'rows_shown': rows[:limit]})
    return {'keyword': kw, 'only': only, 'sections': secs,
            'total': sum(len(s['rows_shown']) for s in secs)}

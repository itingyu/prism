"""股票名称 → 代码

akshare 的代码表 (`stock_info_a_code_name`, 沪深京 A 股) 缓存到
`~/.prism/name_map.json`, 7 天过期。只在输入不是 6 位数字 / 指数别名时才查表,
所以纯代码路径不会多花时间, 也不会因为断网而变慢。

匹配规则 (宁可不猜, 也不猜错):
  1. 名称完全一致 → 直接用
  2. 只有一个名称包含该关键词 → 用 (茅台 → 贵州茅台)
  3. 多个候选 → 报错并列出候选, 让用户自己挑
  4. 查不到 → 报错, 给出相近名称
"""
import difflib
import json
import sys
import unicodedata
import os
import re
import time

CACHE = os.path.expanduser('~/.prism/name_map.json')
TTL = 7 * 24 * 3600


def _read_cache():
    try:
        with open(CACHE, encoding='utf-8') as f:
            d = json.load(f)
        if isinstance(d.get('map'), dict):
            return d
    except (OSError, ValueError):
        pass
    return None


def _write_cache(mp):
    try:
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        tmp = CACHE + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump({'ts': int(time.time()), 'map': mp}, f, ensure_ascii=False)
        os.replace(tmp, CACHE)
    except OSError:
        pass


def _norm(s):
    """去掉名称里的空格, 全角字母转半角 (万  科Ａ → 万科A)"""
    return unicodedata.normalize('NFKC', str(s)).replace(' ', '').strip()


def _fetch():
    from prism.stock.bridge import ak as _ak

    # 首次要拉 10 秒, 交互时给一句进度; 管道/agent 场景没有 tty, 静默
    if sys.stderr.isatty():
        print('… 首次使用: 拉取股票代码表 (约 10 秒)', file=sys.stderr)
    rows = _ak.rows('stock_info_a_code_name', timeout=40)
    mp = {}
    for r in rows:
        code = str(r.get('code') or r.get('代码') or '').strip().zfill(6)
        name = _norm(r.get('name') or r.get('名称') or '')
        if re.fullmatch(r'\d{6}', code) and name:
            mp[name] = code
    if not mp:
        raise ValueError('代码表为空')
    _write_cache(mp)
    return mp


def name_map(force=False):
    """名称 → 6 位代码; 缓存过期时刷新, 刷新失败退回旧缓存"""
    d = _read_cache()
    if d and not force and time.time() - d.get('ts', 0) < TTL:
        return d['map']
    try:
        return _fetch()
    except Exception:
        if d and d.get('map'):
            return d['map']            # 过期也比没有强
        raise


def looks_like_name(tok):
    """非 6 位纯数字、且含非 ASCII 字符 —— 当成名称处理"""
    t = str(tok or '').strip()
    return bool(t) and not re.fullmatch(r'\d{6}', t) and any(ord(c) > 127 for c in t)


_ALIAS = None


def _aliases():
    """指数别名（上证指数 / 恒生指数 / 道指 …）不参与股票名称解析"""
    global _ALIAS
    if _ALIAS is None:
        from prism.stock.engine.clients import IDX, IDX_NUM
        _ALIAS = set(IDX) | set(IDX_NUM)
    return _ALIAS


def resolve_name(tok, mp=None):
    """返回 6 位代码; 查不到/多义抛 ValueError (带候选)"""
    t = _norm(tok)
    if t in _aliases():
        return t
    mp = name_map() if mp is None else mp
    if t in mp:
        return mp[t]
    hits = [n for n in mp if t in n]
    if len(hits) == 1:
        return mp[hits[0]]
    if len(hits) > 1:
        cand = '、'.join(f'{n}({mp[n]})' for n in hits[:8])
        more = f' 等 {len(hits)} 个' if len(hits) > 8 else ''
        raise ValueError(f'"{t}" 匹配到多只股票: {cand}{more}; 请写全称或直接用代码')
    near = difflib.get_close_matches(t, list(mp), n=5, cutoff=0.5)
    if near:
        raise ValueError(f'没有叫 "{t}" 的股票; 相近的有: '
                         + '、'.join(f'{n}({mp[n]})' for n in near))
    raise ValueError(f'没有叫 "{t}" 的股票; 写全称或直接用 6 位代码')


def resolve_tokens(tokens):
    """批量: 名称换代码, 数字/指数别名原样保留"""
    from prism.stock.command._common import _IDX_ALIAS

    out, mp = [], None
    for t in tokens:
        s = str(t or '').strip()
        if not s or s in _IDX_ALIAS or not looks_like_name(s):
            out.append(s)
            continue
        if mp is None:
            mp = name_map()
        out.append(resolve_name(s, mp))
    return out


# 行情命令按市场分开: quote/kline 只做 A 股, 港/美/韩各有带前缀的命令
MARKET_ACTIONS = set()
_MARKET_ACTIONS = MARKET_ACTIONS

# 这些动作的位置参数不是股票代码 (接口名/关键词/命令名), 不做代码解析与守卫
NO_CODE_ACTIONS = {
    'data', 'commands', 'lookup', 'find', 'datacenter', 'source', 'sources', 'boards',
}

_MARKET_HINT = {
    'hk': ('hk-quote', 'hk-kline'),
    'us': ('us-quote', 'us-kline'),
    'kr': ('kr-quote', 'kr-kline'),
}
_MARKET_LABEL = {'hk': '港股', 'us': '美股', 'kr': '韩股'}


def normalize_market(tokens, action):
    """兼容旧调用: 行情命令已按市场拆开, quote/kline 不再自动猜市场"""
    return list(tokens)


def to_market(tokens, market):
    """把裸代码补成该市场的规范写法 (命令已定市场, 不再猜)"""
    out = []
    for t in tokens:
        s = str(t or '').strip()
        if not s:
            continue
        if market == 'hk':
            m = re.fullmatch(r'(?i)(\d{1,5})\.hk', s)
            s = m.group(1) if m else re.sub(r'(?i)^hk', '', s)
            if not re.fullmatch(r'\d{1,5}', s):
                raise ValueError(f'{t} 不是港股代码 (应为 1~5 位数字, 如 700 / 00700)')
            s = 'hk' + s.zfill(5)
        elif market == 'us':
            s = re.sub(r'(?i)^us', '', s).upper()
            if not re.fullmatch(r'[A-Z][A-Z.\-]{0,9}', s):
                raise ValueError(f'{t} 不是美股代码 (如 AAPL / BRK.B)')
            s = 'us' + s
        elif market == 'kr':
            s = re.sub(r'(?i)^kr', '', s)
            if not re.fullmatch(r'\d{6}', s):
                raise ValueError(
                    f'{t} 不是韩股代码 (必须 6 位, 如 005930); '
                    f'1~5 位数字是港股写法, 用 prism hk-quote {s}')
            s = 'kr' + s
        out.append(s)
    return out


def guard_a_share(tokens, action, market=None):
    """A 股命令只认真 A 股代码

    - market 有值时 (hk-quote 等): 只校验代码归属, 不拦前缀
    - 无市场时: 港/美/韩写法一律拒绝并给出该用哪条命令
    """
    q, k = _MARKET_HINT.get(market or '', (action, action))
    for t in tokens:
        s = str(t or '').strip()
        m = re.match(r'(?i)^(hk|us|kr)(.+)$', s)
        if m:
            mk = m.group(1).lower()
            if market and mk == market:
                continue
            q2, k2 = _MARKET_HINT[mk]
            hint = k2 if action in ('kline', 'intraday') else q2
            raise ValueError(
                f'{s} 是{_MARKET_LABEL[mk]}代码; {action} 只支持 A 股, '
                f'请用 prism {hint} {m.group(2)}')
        if market:
            raise ValueError(
                f'{s} 不是{_MARKET_LABEL[market]}代码; 这个命令只取'
                f'{_MARKET_LABEL[market]}, A 股请用 prism quote/kline')
        if re.fullmatch(r'\d{1,5}', s):
            raise ValueError(
                f'{s} 看着像港股代码; {action} 只支持 A 股 6 位代码, '
                f'港股请用 prism hk-quote {s} / prism hk-kline {s}')
        if action in ('quote', 'kline') and re.fullmatch(r'[A-Za-z][A-Za-z.\-]{0,9}', s):
            raise ValueError(
                f'{s} 看着像美股代码; {action} 只支持 A 股, '
                f'美股请用 prism us-quote {s} / prism us-kline {s}')
    return tokens

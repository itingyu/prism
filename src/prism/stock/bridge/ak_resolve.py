"""口径解析: 把"人话"变成一个具体的数据接口

背景: 614 个扩展口径里, 有大批其实是"同一张表 + 不同参数"的切片
(各国宏观 169 个、各类交易所/商品/基金口径)。硬枚举 169 个名字没人记得住,
所以做一层通用解析:

    --kind australia_cpi_yearly   → 精确命中
    --kind "australia cpi"        → token 匹配 (候选唯一即用)
    --kind "australia cpi yearly" → 多 token 收窄
    --kind "cpi"                  → 命中多张表 → 列出候选让用户补词

token 匹配是**按段**的: 一个 token 必须整段出现在口径名里 (australia 命中
australia_cpi_yearly, 但 cpiy 不命中)。命中多于一个时不猜, 直接把候选摆出来。
"""
import difflib
import re

from prism.stock.bridge.ak_families import FAM


def _tokens(expr):
    return [t for t in re.split(r'[\s,+/]+', str(expr or '').strip().lower()) if t]


def _match(kinds, tokens):
    """token 按段匹配, 保留顺序 (australia cpi 不匹配 cpi_australia)"""
    out = []
    for k in kinds:
        segs = k.lower().split('_')
        pos = 0
        ok = True
        for t in tokens:
            found = False
            for i in range(pos, len(segs)):
                if segs[i] == t or segs[i].startswith(t) and len(t) >= 3:
                    pos = i + 1
                    found = True
                    break
            if not found:
                ok = False
                break
        if ok:
            out.append(k)
    return out


def resolve(family, expr, err_cls=None):
    """把口径表达式解析成 (kind, spec); 失败抛 err_cls (默认 RuntimeError)"""
    if err_cls is None:
        from prism.stock.bridge.ak import AkFailed as err_cls
    kinds = FAM.get(family)
    if kinds is None:
        raise err_cls(f'没有这个功能族: {family}')
    expr = str(expr or '').strip()
    if expr in kinds:
        return expr, kinds[expr]
    # 也接受 akshare 函数名本身 (口径 key 可能是去掉前缀的短名)
    for _k, _v in kinds.items():
        if str(_v.get('n') or '').lower() == expr.lower():
            return _k, _v
    toks = _tokens(expr)
    if toks:
        cand = _match(sorted(kinds), toks)
        if len(cand) == 1:
            return cand[0], kinds[cand[0]]
        if len(cand) > 1:
            raise err_cls(
                f'{family} 的 "{expr}" 命中 {len(cand)} 个口径, 请补一个词区分: '
                + ', '.join(cand[:8]) + (' …' if len(cand) > 8 else ''))
    near = difflib.get_close_matches(expr, sorted(kinds), n=5, cutoff=0.4)
    if near:
        raise err_cls(f'{family} 没有口径 "{expr}"; 接近的是: ' + ', '.join(near))
    raise err_cls(f'{family} 没有口径 "{expr}"; 用 prism {family} --list 看全部')


def groups(family):
    """按口径名的第一段分组 (australia_* / amac_* / cffex_* ...)"""
    kinds = FAM.get(family, {})
    out = {}
    for k in sorted(kinds):
        out.setdefault(k.split('_')[0], []).append(k)
    return out


def summary(family):
    """分组摘要: 组名 → (口径数, 代表说明)"""
    out = {}
    for g, ks in groups(family).items():
        doc = FAM[family][ks[0]].get('s') or ''
        out[g] = (len(ks), doc)
    return out

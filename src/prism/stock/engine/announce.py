"""公告分类

东财/巨潮的公告只有标题 + 日期, 想按"这件事是什么"筛, 只能看标题里的词。
这里给一份关键词分类表, 把标题归到人能直接用的类别上:

    增持 / 减持 / 回购 / 业绩预告 / 问询函 / 分红 / 停复牌 /
    重大合同 / 股权激励 / 诉讼 / 解禁

判定顺序按"信号强度"排 —— 一条公告可能同时命中多个 (如"关于回购股份的进展公告"
既含回购又含股份), 先命中的类别作为主类, 其余记进 also, 不丢信息。

匹配原则:
- 关键词取**可区分**的片段, 避免"回购"这种词把"回购注销"与"股份回购"混在一起
  (本来同一类, 无所谓), 但"增持"必须带上"股东/股份/计划"才命中 ——
  否则"增持信心"之类的正文词也会误伤
- 标题里的书名号/全角字符统一去掉再匹配
"""

__all__ = ['CATEGORIES', 'CATEGORY_NAMES', 'classify', 'classify_all', 'annotate',
           'filter_by_type']

# 类别 → 关键词 (小写匹配; 中文无大小写, 英文统一 lower)
CATEGORIES = {
    '业绩预告': ['业绩预告', '业绩快报', '业绩预增', '业绩预减', '业绩预亏'],
    '业绩说明会': ['业绩说明会'],
    '问询函': ['问询函', '关注函', '监管函', '警示函', '纪律处分', '立案'],
    '增持': ['增持计划', '增持股份', '增持公司', '拟增持'],
    '减持': ['减持计划', '减持股份', '减持公司', '拟减持', '股份减持'],
    '回购': ['回购股份', '回购方案', '回购公司', '股份回购', '回购注销'],
    '分红': ['权益分派', '利润分配', '现金分红', '分红派息'],
    '停复牌': ['停牌', '复牌'],
    '重大合同': ['重大合同', '中标', '签订', '重大订单', '战略合作'],
    '股权激励': ['股权激励', '员工持股', '限制性股票'],
    '诉讼': ['诉讼', '仲裁', '涉诉'],
    '解禁': ['解除限售', '限售股上市', '解禁'],
    '担保': ['担保', '对外担保'],
    '资产重组': ['重大资产重组', '资产重组', '吸收合并'],
}

CATEGORY_NAMES = tuple(CATEGORIES)


def _norm(text: str) -> str:
    """去书名号/全角括号, 统一小写"""
    if not text:
        return ''
    for ch in '《》（）()【】[]"“”\'‘’ ,，。、:：;；':
        text = text.replace(ch, '')
    return text.lower()


def classify(title: str, tags=None) -> str:
    """返回公告主类别; 不命中返回 '其它'"""
    t = _norm(title)
    # 上游给的类型标签 (东财 columns) 最准, 先用
    for tag in (tags or []):
        name = _norm(str(tag))
        for cat, kws in CATEGORIES.items():
            if name == _norm(cat) or any(_norm(k) in name for k in kws):
                return cat
    for cat, kws in CATEGORIES.items():
        if any(_norm(k) in t for k in kws):
            return cat
    return '其它'


def classify_all(item: dict) -> dict:
    """给一条公告补 category / also 字段 (原地返回)"""
    title = item.get('title') or ''
    tags = item.get('columns') or item.get('tags') or []
    t = _norm(title)
    hits = [cat for cat, kws in CATEGORIES.items()
            if any(_norm(k) in t for k in kws)]
    item['category'] = hits[0] if hits else classify(title, tags)
    item['also'] = hits[1:]
    return item


def annotate(item: dict, tags=None) -> dict:
    """给一条公告补 category / also (tags 走上游类型标签)"""
    title = item.get('title') or ''
    t = _norm(title)
    hits = [cat for cat, kws in CATEGORIES.items()
            if any(_norm(k) in t for k in kws)]
    item['category'] = hits[0] if hits else classify(title, tags)
    item['also'] = hits[1:]
    return item


def filter_by_type(items, want: str = '') -> list:
    """按类别过滤; want 为空/全部 返回原样"""
    want = (want or '').strip()
    if not want or want in ('全部', 'all', 'ALL'):
        return list(items)
    out = []
    for it in items:
        it = classify_all(it)
        cats = [it.get('category')] + list(it.get('also') or [])
        if want in cats:
            out.append(it)
    return out

"""
长线池筛选（6-18 月）
===================
来自 fsi/a-share-screen 长线规则
目的: 高股息 + 破净 + 核心资产底仓
"""
import prism.stock.engine.feeds as xueqiu
from prism.stock.engine._common import to_xueqiu_symbol, is_tradable, unbuyable_reason


def screen_one(code, name=None):
    """
    长线筛选（条件更宽松，重点是基本面）
    条件:
      1. 流通市值 > 500 亿
      2. PE 合理（< 行业中位数，粗略判断）
      3. 趋势向上（不强制）
    注: 股息率、PB 破净、ROE 等需要财务数据，雪球 f10/indicators 已下线
        这部分标记为待验证，需人工或外部搜索补充
    """

    if not is_tradable(code, name):
        return {"code": code, "name": name,
                "error": f"不可买板块：{unbuyable_reason(code, name)}",
                "failed_gate": "不可买板块"}
    symbol = to_xueqiu_symbol(code)
    # feeds.quote 回 {代码: 行情} 的映射, 不是单只行情 —— 直接当行情用会
    # 拿到空壳 dict, 后面市值/PE 全是 None (闸门恒为 0, 所有票都被误杀)。
    qmap = xueqiu.quote(symbol)
    quote = (qmap.get(symbol) or next(iter(qmap.values()), None)) \
        if isinstance(qmap, dict) and qmap else None
    if not quote or quote.get("error"):
        return {"code": code, "name": name, "error": "quote 失败"}

    name_str = quote.get("name") or name or code
    # 市值键用 flat 契约的 float_mktcap (元); float_market_capital 是雪球
    # 原始键, 展平后不存在 —— 取它等于恒为 0, 市值闸门形同虚设。
    float_cap_yi = (quote.get("float_mktcap")
                    or quote.get("float_market_capital") or 0) / 1e8

    if float_cap_yi < 500:
        return {"code": code, "name": name_str,
                "error": f"市值 {float_cap_yi:.0f} 亿 < 500 亿",
                "failed_gate": "市值"}

    pe = quote.get("pe_ttm")
    pb = quote.get("pb")

    return {
        "code": code,
        "symbol": symbol,
        "name": name_str,
        "float_market_capital_yi": round(float_cap_yi, 2),
        "pe_ttm": pe,
        "pb": pb,
        "industry": xueqiu.get_industry(symbol),
        "pool": "长线",
        "待验证": [
            "PB < 1.0x（破净优先）",
            "股息率 > 4.0%",
            "ROE > 8%（连续 3 年）",
            "资产负债率 < 70%",
        ],
    }


def suggest_typical_stocks():
    """
    长线典型标的（来自 fsi a-share-screen）
    """
    return {
        "银行": ["601288 农业银行", "601939 建设银行", "601398 工商银行"],
        "煤炭": ["601088 中国神华", "601225 陕西煤业", "601699 潞安环能"],
        "公用": ["600900 长江电力", "600886 国投电力", "600025 华能水电"],
        "高速铁路": ["001965 招商公路", "601006 大秦铁路", "600377 宁沪高速"],
        "保险": ["601601 中国太保", "601628 中国人寿", "601318 中国平安"],
        "运营商": ["600941 中国移动", "600050 中国联通"],
    }
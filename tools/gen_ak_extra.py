"""生成 ak_families_extra.json: 主表没覆盖的 akshare 接口按功能归到命令名下

规则: 先按功能前缀精确匹配 (顺序敏感, 具体在前), 未命中进 misc。
每个条目带 --list 需要的参数/必填/说明, 运行期仍按真实签名填参。

用法: PYTHONPATH=src python tools/gen_ak_extra.py
"""
import inspect
import json
import re
import sys
from collections import Counter
from pathlib import Path

from prism.stock.bridge import ak_families, eco

OUT = Path(__file__).resolve().parents[1] / 'src/prism/stock/bridge/ak_families_extra.json'

RULES = [
    (r'^bond_zh_cov|^bond_cb_|^bond_zh_hs_cov', 'bond'),
    (r'^bond_', 'bond'),
    (r'^(fund_|amac_|reits_)', 'fund'),
    (r'^futures_|^get_(czce|dce|qhkc)|^qhkc_', 'futures'),
    (r'^option_', 'option'),
    (r'^(macro_|fred_)', 'macro'),
    (r'^index_', 'index'),
    (r'^(forex_|currency_|hf_)', 'world'),
    (r'^stock_hsgt_', 'stock-connect'),
    (r'^stock_hk_|^stock_zh_ah_|^stock_zh_b_', 'hk'),
    (r'^stock_us_', 'world'),
    (r'^stock_lhb_', 'lhb'),
    (r'^stock_fund_flow_|^stock_main_fund_flow|^stock_market_fund_flow|^stock_sector_fund_flow_|^stock_individual_fund_flow', 'flow'),
    (r'^stock_board_industry_|^stock_sector_', 'industry'),
    (r'^stock_board_concept_|^stock_concept_', 'concept'),
    (r'^stock_zt_pool_|^stock_qbzf_', 'pool'),
    (r'^stock_rank_|^stock_sy_hy_|^stock_sy_jz_', 'screen'),
    (r'^stock_sy_', 'goodwill'),
    (r'^stock_gdfx_|^stock_hold_|^stock_share_change|^stock_gdhs', 'holders'),
    (r'^stock_ggcg_', 'holders'),
    (r'^stock_gpzy_', 'pledge'),
    (r'^stock_repurchase_|^stock_restricted_', 'unlock'),
    (r'^stock_dividend_|^stock_fhps_', 'dividend'),
    (r'^stock_yjbb_|^stock_yjkb_|^stock_yjyg_', 'earnings-report'),
    (r'^stock_yysj_', 'disclosure-schedule'),
    (r'^stock_zcfz_|^stock_balance_sheet', 'balance'),
    (r'^stock_profit_sheet', 'income'),
    (r'^stock_cash_flow_sheet', 'cashflow'),
    (r'^stock_financial_', 'financials'),
    (r'^stock_hot_', 'hot'),
    (r'^stock_comment_', 'comment'),
    (r'^stock_news_', 'news'),
    (r'^stock_notice_', 'notice'),
    (r'^stock_research_report_|^stock_institute_', 'analyst-report'),
    (r'^stock_ipo_|^stock_new_|^stock_xgsr_|^stock_allotment', 'ipo'),
    (r'^stock_inner_trade', 'insider-trade'),
    (r'^stock_zh_a_hist|^stock_zh_a_daily|^stock_zh_a_spot|^stock_bid_ask|^stock_intraday|^stock_individual_spot|^stock_zh_a_minute', 'kline'),
    (r'^stock_', 'quote'),
    (r'^(air_|car_|movie_|video_|sunrise_|article_|migration_|nlp_|energy_carbon_|xincaifu|business_value|online_value|bank_|stock_esg|stock_cyq|stock_info_|stock_sns|stock_market_activity)', 'misc'),
]
SKIP = {'search', 'pro_api'}


def family_of(fn):
    for pat, fam in RULES:
        if re.search(pat, fn):
            return fam
    return 'misc'


def main():
    base = getattr(ak_families, 'FAM_BASE', ak_families.FAM)
    known = {v['n'] for kinds in base.values() for v in kinds.values()}
    uncovered = [f for f in eco.funcs('akshare') if f not in known and f not in SKIP]
    out, stat = {}, Counter()
    for fn in uncovered:
        fn_obj = eco._lookup('akshare', fn)
        try:
            sig = inspect.signature(fn_obj)
            ps = [n for n, p in sig.parameters.items()
                  if p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY)]
            req = [n for n in ps if sig.parameters[n].default is inspect._empty]
        except (ValueError, TypeError):
            ps, req = [], []
        doc = (getattr(fn_obj, '__doc__', '') or '').strip().splitlines()
        fam = family_of(fn)
        out.setdefault(fam, {})[fn] = {
            'n': fn, 'p': ps[:4], 'r': req, 'role': 'kind',
            's': (doc[0][:80] if doc else ''), 'st': 'ok', 'msg': '',
        }
        stat[fam] += 1

    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1, sort_keys=True),
                   encoding='utf-8')
    print(f'未覆盖 {len(uncovered)} 个 -> 已写入 {OUT}')
    for k, v in stat.most_common():
        print(f'  {k:22} +{v}')


if __name__ == '__main__':
    sys.exit(main())

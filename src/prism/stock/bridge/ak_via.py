"""上游接口 → 专用命令的映射 (由 tools/gen_ak_via.py 生成, 勿手改)

同一份上游数据有两条入口:
  - 专用命令 (prism lhb): 字段做过筛选、单位折算、窗口取数, 结果更规整
  - 通用口径 (--kind):    原样透传上游字段, 想自己加工时用

这份表让 prism schema 能告诉用户"这个接口还有更规整的入口"。
"""

# interface → (命令名, 额外标志)
INTERFACE_VIA = {
    'bond_zh_cov': ('cb', {}),
    'fund_etf_category_sina': ('etf', {}),
    'stock_dzjy_mrmx': ('block-trade', {}),
    'stock_financial_analysis_indicator': ('financials', {}),
    'stock_hsgt_fund_flow_summary_em': ('stock-connect', {}),
    'stock_hsgt_hist_em': ('stock-connect', {}),
    'stock_jgdy_detail_em': ('survey', {}),
    'stock_lhb_detail_em': ('lhb', {}),
    'stock_lhb_hyyyb_em': ('lhb', {'yyb': True}),
    'stock_market_activity_legu': ('breadth', {}),
    'stock_news_em': ('news', {}),
    'stock_research_report_em': ('analyst-report', {}),
    'stock_restricted_release_detail_em': ('unlock', {}),
    'stock_restricted_release_summary_em': ('unlock', {}),
    'stock_zh_a_gdhs_detail_em': ('holder-count', {}),
    'stock_zh_a_hist': ('kline', {}),
}

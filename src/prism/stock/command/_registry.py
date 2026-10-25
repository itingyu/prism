"""动作表与用法文本 (单一事实来源, 入口从这里取)"""
"""prism 动作: 动作分发 + 输出渲染

两座桥 (bridge/engine.py 脚本层 / bridge/srv.py 编排层) 在这里汇合成一个扁平的动作表:

    数据动作  quote pool check calendar flow news announcement financials
              analyze screen risk            —— 走 engine 脚本层

输出与 prism 其他数据命令一致: 数据动作按 args.format 自己渲染 (json 全字段 /
text 行内可读 / markdown 表格), 走 cli.app._run 的 emit 落盘通道。

口径纪律 (从 stock-master 继承, 现由 engine 维护):
  - 接口返回 0/空 不当正常值, 由各桥透传 status, 渲染时显式标注
  - 北向资金不可用必须显式 ⚠, 不填 0
  - 池/榜单类结果必带数据日 (date), 涨停池尤其 —— 接口对无效日期会静默回旧数据
"""



from prism.stock.command._actions import _act_analyze
from prism.stock.command._actions import _act_announcement
from prism.stock.command._actions_data import _act_api_list
from prism.stock.command._actions_data import _act_api_search
from prism.stock.command._actions import _act_calendar
from prism.stock.command._actions import _act_check
from prism.stock.command._actions import _act_commands
from prism.stock.command._actions_data import _act_data
from prism.stock.command._actions_data import _act_data_call
from prism.stock.command._actions_data import _act_schema
from prism.stock.command._actions_data import _act_data_find
from prism.stock.command._actions_data import _act_data_health
from prism.stock.command._actions_data import _act_data_list
from prism.stock.command._actions_data import _act_data_url
from prism.stock.command._actions_data import _act_find
from prism.stock.command._actions_data import _act_sources
from prism.stock.command._actions_data import _act_source
from prism.stock.command._actions import _act_diagram
from prism.stock.command._actions import _act_excel
from prism.stock.command._actions import _act_financials
from prism.stock.command._actions import _act_valuation
from prism.stock.command._actions import _act_position
from prism.stock.command._actions import _act_patterns
from prism.stock.command._actions import _act_flow
from prism.stock.command._actions import _act_forecast
from prism.stock.command._actions import _act_holder
from prism.stock.command._actions import _act_kline
from prism.stock.command._actions import _act_intraday
from prism.stock.command._actions import _act_boards
from prism.stock.command._actions import _act_news
from prism.stock.command._actions import _act_pool
from prism.stock.command._actions import _act_quote
from prism.stock.command._actions import _act_report
from prism.stock.command._actions import _act_risk
from prism.stock.command._actions import _act_screen
from prism.stock.command._actions import _act_sentiment
from prism.stock.command._actions import _act_std
from prism.stock.command._actions_ak import _act_breadth
from prism.stock.command._actions_ak import _act_cb
from prism.stock.command._actions_ak import _act_dzjy
from prism.stock.command._actions_ak import _act_etf
from prism.stock.command._actions_ak import _act_gdhs
from prism.stock.command._actions_ak import _act_hsgt
from prism.stock.command._actions_ak import _act_jgdy
from prism.stock.command._actions_ak import _act_lhb
from prism.stock.command._actions_ak import _act_macro
from prism.stock.command._actions_ak import _act_unlock
from prism.stock.command._actions_ak import _act_comment
from prism.stock.command._actions_ak import _act_goodwill
from prism.stock.command._actions_ak import _act_lhb_stats
from prism.stock.command._actions_ak import _act_margin_ext
from prism.stock.command._actions_ak import _act_pledge
from prism.stock.command._actions_ak import _act_rating
from prism.stock.command._actions_ak import _act_valuation_ext
from prism.stock.command._actions_ak import _act_yjyg
from prism.stock.command._actions_ak import _act_yanbao
from prism.stock.command._actions_ak import _act_buyback
from prism.stock.command._actions_ak import _act_boards_ext
from prism.stock.command._actions_ak import _act_breadth_ext
from prism.stock.command._actions_ak import _act_changes
from prism.stock.command._actions_ak import _act_holders_ext
from prism.stock.command._actions_ak import _act_hot
from prism.stock.command._actions_ak import _act_notice
from prism.stock.command._actions_ak import _act_shares
from prism.stock.command._actions_ak import _act_fhps
from prism.stock.command._actions_ak import _act_ggcg
from prism.stock.command._actions_ak import _act_mgmt
from prism.stock.command._actions_ak import _act_yjbb
from prism.stock.command._actions_ak import _act_yysj
from prism.stock.command._actions_ak import _act_fam
from prism.stock.command._actions_ak import _act_fam_list
from prism.stock.command._actions_ak import _act_bond
from prism.stock.command._actions_ak import _act_fund
from prism.stock.command._actions_ak import _act_futures
from prism.stock.command._actions_ak import _act_hk
from prism.stock.command._actions_ak import _act_option
from prism.stock.command._actions_alt import _act_dupont
from prism.stock.command._actions_alt import _act_dividend
from prism.stock.command._actions_alt import _act_growth

ACTIONS = {
    'quote': _act_quote, 'pool': _act_pool, 'check': _act_check,
    'calendar': _act_calendar, 'flow': _act_flow, 'news': _act_news,
    'announcement': _act_announcement, 'financials': _act_financials,
    'valuation': _act_valuation_ext, 'position': _act_position,
    'patterns': _act_patterns,
    'analyze': _act_analyze, 'screen': _act_screen, 'risk': _act_risk,
    'report': _act_report, 'excel': _act_excel, 'sentiment': _act_sentiment,
    'diagram': _act_diagram,
    'holder': _act_holder, 'forecast': _act_forecast,
    'commands': _act_commands,
    'lookup': _act_find,

    # akshare 数据域 (原生源没有的事件/宏观数据)
    'lhb': _act_lhb, 'dzjy': _act_dzjy, 'unlock': _act_unlock,
    'jgdy': _act_jgdy, 'yanbao': _act_yanbao, 'gdhs': _act_gdhs,
    'macro': _act_macro, 'hsgt': _act_hsgt, 'breadth': _act_breadth_ext,
    'cb': _act_cb, 'etf': _act_etf,
    'dupont': _act_dupont, 'growth': _act_growth,
    'comment': _act_comment, 'yjyg': _act_yjyg, 'pledge': _act_pledge,
    'rating': _act_rating, 'goodwill': _act_goodwill,
    'changes': _act_changes, 'hot': _act_hot, 'buyback': _act_buyback,
    'shares': _act_shares, 'notice': _act_notice,
    'yysj': _act_yysj, 'yjbb': _act_yjbb, 'fhps': _act_fhps,
    'ggcg': _act_ggcg, 'mgmt': _act_mgmt,
    'futures': _act_futures, 'option': _act_option, 'fund': _act_fund,
    'bond': _act_bond, 'hk': _act_hk,
    'fam': _act_fam, 'fam-list': _act_fam_list,

    # 编排层动作升格 (未单独暴露的走 run <动作>)
    'kline': _act_kline,
    'intraday': _act_intraday,
    'boards': _act_boards_ext,
    'index': _act_std('stock_index'),
    'income': _act_std('stock_income_statement'),
    'balance': _act_std('stock_balance_sheet'),
    'cashflow': _act_std('stock_cashflow'),
    'company': _act_std('stock_company'),
    'business': _act_std('stock_business_analysis'),
    'holders': _act_holders_ext,
    'holder_chg': _act_std('stock_holder_change'),
    'industry': _act_std('stock_industry_list'),
    'concept': _act_std('stock_concept_list'),
    'industry_of': _act_std('stock_industry_concept'),
    # dividend 带代码时给个股分红历史 (baostock), 不带代码仍是全市场排行
    'dividend': _act_dividend,
    'margin': _act_margin_ext,
    'screener': _act_std('stock_screener'),
    'ipo': _act_std('stock_ipo'),

    # 通用取数入口 (融合 eco/http/em/docs 四组)
    'data': _act_data, 'data-find': _act_data_find, 'data-call': _act_data_call,
    'data-url': _act_data_url, 'data-list': _act_data_list,
    'data-health': _act_data_health,
    # 子命令点名数据源方法 (prism quote --source tencent_a 600519)
    'source': _act_source,

    # 兼容别名 → data 子动作 (隐藏不宣传, 下一大版本删)
    'sources': _act_sources,
    # 命令自描述 (参数/JSON 结构), 给脚本与 agent 用
    'schema': _act_schema,
}

USAGE = """用法: prism <动作> [参数]        (动作直接是顶层命令, 无 `stock` 这一层)

通用参数
  -f/--format text|markdown|json   输出格式 (json 统一信封: ok/source/count/rows)
  -o/--output 路径                  写入文件 (给目录则按时间命名)
  --kind <口径>                     该命令的扩展口径 (先跑 `<命令> --list`)
  --list                            列出该命令的扩展口径
  --source <方法名>                 点名数据源方法 (清单见 prism lookup --by site)
  --arg k=v                         给底层接口额外传参, 可重复
  -n/--limit N                      条数

发现
  prism lookup <关键词>             搜命令 / 口径 / 源方法 / 接口
  prism lookup --list-domains       域总览 (各域接口数)
  prism lookup --by site            数据源方法清单 (按站点分组)
  prism lookup --family <族>        某个功能族下的口径清单
  prism schema <命令>               命令参数与 JSON 输出结构自描述
  prism schema --all                全部命令目录 (机器可读)

用法示例
  prism quote 600519                 实时行情 (支持 上证指数/创业板指 等别名)
  prism pool --only-buy              涨停池 (可买性硬过滤)
  prism kline 600519 --chart         K 线图 (红涨绿跌 + 均线 + 量能)
  prism lhb --kind lhb_detail_daily  按口径取数
  prism quote --source tencent_a 600519   点名数据源方法
"""


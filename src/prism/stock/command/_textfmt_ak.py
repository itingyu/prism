"""akshare 数据域的 text / markdown 视图

列由 `COLS` 决定 —— 上游列名会变 (研报的预测年份、解禁的统计列), 所以列名
在渲染时按"现有列 ∩ 期望列"取交集, 交集为空才退回全部列; 不写死 index。
金额类列统一折成 亿/万, 否则"解禁市值 1234567890.0"这种数字谁也读不出量级。
"""
from prism.util.num import to_float
AMT = ('商誉', '额', '市值', '资金', '金额', '数量', '股数', '净买', '成交量')
YEARLIKE = ('盈利预测',)

COLS = {
    'futures': ['日期', '开盘价', '最高价', '最低价', '收盘价', '成交量', '持仓量'],
    'futures_rt': ['symbol', 'name', 'trade', 'settlement', 'open', 'high', 'low',
                   'volume', 'position', 'change', 'exchange'],
    'futures_inv': ['日期', '库存', '增减'],
    'futures_contract': ['合约代码', '上市日', '到期日', '开始交割日', '最后交割日'],
    'opt_stats': ['合约标的名称', '合约数量', '总成交量', '总成交额(亿)', '认购成交量',
                  '认沽成交量', '认沽/认购', '未平仓合约总数'],
    'opt_greeks': ['TRADE_DATE', 'CONTRACT_SYMBOL', 'DELTA_VALUE', 'GAMMA_VALUE',
                   'THETA_VALUE', 'VEGA_VALUE', 'RHO_VALUE', 'IMPLC_VOLATLTY'],
    'opt_margin': ['合约标的', '合约代码', '结算价', '交易乘数', '买方权利金',
                   '卖方保证金', '开仓手续费', '平今手续费'],
    'opt_comm': ['期权品种', '现价', '涨/跌停板', '成交量', '类型', '权利金',
                 '每跳毛利/元', '每跳净利/元', '交易所'],
    'opt_lhb': ['交易类型', '交易日期', '证券代码', '标的名称', '名次', '机构',
                '交易量', '增减', '净认沽量', '占总交易量比例'],
    'opt_contract': ['序号', '合约'],
    'fund_top': ['基金代码', '基金简称', '单位净值', '累计净值', '日增长率',
                 '申购状态', '赎回状态', '手续费'],
    'fund_hold': ['序号', '股票代码', '股票名称', '占净值比例', '持股数(万股)',
                  '持仓市值(亿)', '季度'],
    'fund_nav': ['净值日期', '单位净值', '累计净值', '日增长率', '申购状态', '赎回状态'],
    'bond_yield': ['曲线名称', '日期', '3月', '6月', '1年', '3年', '5年', '7年',
                   '10年', '30年'],
    'bond_us': ['日期', '中国国债收益率2年', '中国国债收益率10年',
                '中国国债收益率30年', '美国国债收益率2年', '美国国债收益率10年',
                '美国国债收益率30年'],
    'bond_summary': ['债券现货', '托管只数', '托管市值(亿)', '托管面值(亿)', '数据日期'],
    'hk': ['代码', '中文名称', '最新价', '涨跌额', '涨跌幅', '成交量', '成交额',
           '今开', '最高', '最低'],
    'yysj': ['股票代码', '股票简称', '首次预约时间', '一次变更日期',
             '二次变更日期', '实际披露时间'],
    'fhps': ['代码', '名称', '送转股份-送转总比例', '现金分红-现金分红比例',
             '股息率%', '方案进度', '除权除息日'],
    'yjbb': ['股票代码', '股票简称', '每股收益', '营业总收入-营业总收入(亿)',
             '营业总收入-同比增长', '净利润-净利润(亿)', '净利润-同比增长',
             '净资产收益率', '所处行业'],
    'ggcg': ['代码', '名称', '股东名称', '持股变动信息-增减',
             '持股变动信息-变动数量', '持股变动信息-占总股本比例',
             '变动截止日', '公告日'],
    'mgmt': ['日期', '代码', '名称', '董监高人员姓名', '职务', '变动股数',
             '成交均价', '变动金额', '变动原因'],
    'changes': ['时间', '代码', '名称', '板块', '相关信息'],
    'hot_rank': ['当前排名', '代码', '股票名称', '最新价', '涨跌幅', '人气排名变动'],
    'hot_baidu': ['名称/代码', '涨跌幅', '综合热度'],
    'buyback': ['股票代码', '股票简称', '最新价', '计划回购价格区间', '实施进度',
                '已回购股份数量', '已回购金额', '回购起始时间', '最新公告日期'],
    'shares': ['变更日期', '总股本(亿股)', '已流通股份(亿股)', '流通受限股份(亿股)',
               '变动原因'],
    'notice': ['代码', '名称', '公告类型', '公告标题', '公告日期'],
    'breadth_hist': ['date', 'close', 'high20', 'low20', 'high60', 'low60',
                     'high120', 'low120'],
    'sector': ['板块', '公司家数', '平均价格', '涨跌幅', '总成交额', '股票名称',
               '个股-涨跌幅'],
    'idxval': ['日期', '指数中文简称', '市盈率1', '市盈率2', '股息率1', '股息率2'],
    'free_holders': ['名次', '股东名称', '股东性质', '股份类型', '持股数',
                     '占总流通股本持股比例', '增减', '变动比率'],
    'lhb': ['代码', '名称', '上榜日', '收盘价', '涨跌幅', '龙虎榜净买额',
            '龙虎榜成交额', '换手率', '上榜原因'],
    'lhb_yyb': ['营业部名称', '上榜日', '买入个股数', '卖出个股数',
                '买入总金额', '卖出总金额', '总买卖净额'],
    'dzjy': ['交易日期', '证券代码', '证券简称', '成交价', '折溢率',
             '成交量', '成交额', '买方营业部'],
    'unlock': ['股票代码', '股票简称', '解禁时间', '限售股类型',
               '实际解禁市值', '占解禁前流通市值比例'],
    'unlock_summary': ['解禁时间', '当日解禁股票家数', '实际解禁数量',
                       '实际解禁市值'],
    'jgdy': ['调研日期', '代码', '名称', '调研机构', '机构类型', '接待方式'],
    'yanbao': ['日期', '股票简称', '报告名称', '东财评级', '机构'],
    'gdhs': ['股东户数统计截止日', '股东户数-本次', '股东户数-增减',
             '股东户数-增减比例', '户均持股市值'],
    'hsgt': ['日期', '当日成交净买额', '买入成交额', '卖出成交额',
             '历史累计净买额'],
    'cb': ['债券代码', '债券简称', '正股代码', '转股价', '转股价值',
           '转股溢价率', '信用评级', '上市时间'],
    'etf': ['代码', '名称', '最新价', '涨跌幅', '成交额'],
    'comment': ['代码', '名称', '最新价', '涨跌幅', '换手率', '综合得分',
                '关注指数', '机构参与度', '主力控盘', '市盈率', '所处行业'],
    'yjyg': ['股票代码', '股票简称', '预测指标', '业绩变动', '预测数值',
             '业绩变动幅度', '预告类型', '公告日期'],
    'yjkb': ['股票代码', '股票简称', '每股收益', '营业收入-营业收入',
             '营业收入-同比增长', '净利润-净利润', '净利润-同比增长',
             '每股净资产', '净资产收益率', '所处行业'],
    'pledge': ['股票代码', '股票简称', '质押比例', '质押股份数量',
               '质押市值', '质押笔数', '所属行业'],
    'rating': ['股票代码', '股票名称', '最新评级', '评级机构', '目标价',
               '行业', '分析师', '评级日期'],
    'goodwill': ['股票代码', '股票简称', '商誉', '商誉占净资产比例',
                 '净利润', '商誉减值', '报告期'],
    'market_val': ['date', 'PE中位', 'PE分位%', 'PE等权', 'PB中位', 'PB分位%'],
    # 沪深两市的列名不同 (证券代码/标的证券代码), 两套都列, 取交集
    'margin': ['信用交易日期', '标的证券代码', '标的证券简称', '证券代码', '证券简称',
               '融资余额', '融资买入额', '融资偿还额', '融券余量', '融券卖出量',
               '融券余额', '融资融券余额'],
    'margin_hist': ['日期', '融资余额(亿)', '融券余额(亿)', '融资买入额(亿)',
                    '融券卖出额(亿)', '个人投资者数量'],
    'lhb_stock': ['代码', '名称', '最近上榜日', '涨跌幅', '上榜次数',
                  '龙虎榜净买额', '机构买入净额', '近1个月涨跌幅'],
    'lhb_jg': ['代码', '名称', '涨跌幅', '上榜次数', '龙虎榜成交金额',
               '机构买入额', '机构卖出额', '机构净买额', '近1个月涨跌幅'],
    'lhb_yyb': ['营业部名称', '上榜后1天-平均涨幅', '上榜后1天-上涨概率',
                '上榜后2天-平均涨幅', '上榜后5天-平均涨幅', '上榜后10天-平均涨幅'],
    'lhb_trader': ['营业部名称', '龙虎榜成交金额', '上榜次数', '买入额', '卖出额'],
    # 涨停家族 (pool --type): 各池列名不同, 取并集再按实际列裁
    'zt_pool': ['代码', '名称', '涨跌幅', '最新价', '成交额', '换手率',
                '封板资金', '封单资金', '首次封板时间', '最后封板时间',
                '连板数', '涨停统计', '连续跌停', '开板次数', '炸板次数',
                '昨日连板数', '量比', '是否新高', '入选理由', '所属行业'],
}

def _amt(v):
    """金额折 亿/万; 负数保留符号"""
    f = v if isinstance(v, (int, float)) else to_float(v)
    if f is None:
        return str(v)
    a = abs(f)
    if a >= 1e8:
        return f'{f / 1e8:.2f}亿'
    if a >= 1e4:
        return f'{f / 1e4:.1f}万'
    return f'{f:.0f}'

def _cell(key, v):
    """单格: 金额折单位, 其余保留 2 位小数, 字符串原样"""
    if v is None or v == '':
        return '—'
    if isinstance(v, (int, float)):
        # 列名自带单位 (M2 数量(亿元)) 时不再折 亿/万, 否则 356 万亿会印成 356.8万
        if '亿' in key or '万' in key:
            return str(int(v)) if float(v).is_integer() else f'{v:.2f}'
        if any(k in key for k in AMT) and abs(v) >= 1e4:
            return _amt(v)
        if float(v).is_integer() and not isinstance(v, bool) and abs(v) >= 100:
            return str(int(v))
        if isinstance(v, float):
            return f'{v:.2f}'
    return str(v)

def _pick_cols(action, row):
    """期望列 ∩ 实际列; 再加本年/次年预测列 (研报)"""
    want = COLS.get(action) or []
    got = [c for c in want if c in row]
    if action == 'yanbao':
        got += [c for c in row if any(y in c for y in YEARLIKE)]
    return got or list(row)[:8]

def _widths(head, rows, cap=18):
    w = {}
    for c in head:
        n = max([len(str(c))] + [len(_cell(c, r.get(c))) for r in rows])
        w[c] = min(n, cap)
    return w

def _cut(s, n):
    return s if len(s) <= n else s[:n - 1] + '…'

_EXT_MAP = {
    'futures': {'day': 'futures', 'min': 'futures', 'rt': 'futures_rt',
                'inv': 'futures_inv', 'contract': 'futures_contract'},
    'option': {'stats': 'opt_stats', 'greeks': 'opt_greeks', 'margin': 'opt_margin',
               'comm': 'opt_comm', 'lhb': 'opt_lhb', 'contract': 'opt_contract'},
    'fund': {'top': 'fund_top', 'hold': 'fund_hold', 'nav': 'fund_nav'},
    'bond': {'yield': 'bond_yield', 'us': 'bond_us', 'summary': 'bond_summary'},
}


def _text_ak(out, action):
    action = _EXT_MAP.get(action, {}).get(out.get('kind'), action)
    if action == 'breadth' and not out.get('rows'):
        d = out.get('data') or {}
        print(f"市场宽度 (akshare) — {len(d)} 项")
        for k, v in d.items():
            print(f'  {k}: {v}')
        return
    if out.get('note'):
        print(f"⚠ {out['note']}", file=__import__('sys').stderr)
    rows = out.get('rows') or []
    if not rows:
        print('无数据')
        return
    if action == 'macro':
        title = out.get('title') or out.get('indicator')
        print(f'{title} — 最近 {len(rows)} 期')
        for r in rows:
            print('  ' + '  '.join(f'{k}={_cell(k, v)}' for k, v in r.items()))
        return
    sub = 'lhb_yyb' if '营业部名称' in rows[0] else (
        'unlock_summary' if '当日解禁股票家数' in rows[0] else
        'hot_baidu' if out.get('kind') == 'baidu' else 'hot_rank'
        if action == 'hot' else action)
    if action in ('fam', 'fam-list'):
        rows = [_epoch_dates(r) for r in rows]
    head = _pick_cols(sub, rows[0])
    w = _widths(head, rows, cap=34 if action in ('fam-list') else 18)
    src = out.get('source') or 'akshare'
    label = out.get('title') or action
    if action in ('fam-list', 'fam'):
        # 口径清单不是行情数据: 说"N 个口径", 别写成"N 条 (akshare)"
        # title 里已经写了 "N 个 / M 组", 这里不再重复计数
        print(label)
    else:
        print(f"{label} — {out.get('date') or out.get('code') or ''} "
              f"{len(rows)} 条 ({src})")
    print('  ' + '  '.join(_cut(str(c), w[c]).ljust(w[c]) for c in head))
    for r in rows:
        print('  ' + '  '.join(_cut(_cell(c, r.get(c)), w[c]).ljust(w[c])
                               for c in head))

def _md_ak(out, action):
    action = _EXT_MAP.get(action, {}).get(out.get('kind'), action)
    if out.get('note'):
        print(f"> ⚠ {out['note']}\n")
    if action == 'breadth' and not out.get('rows'):
        print('| 指标 | 值 |')
        print('|---|---|')
        for k, v in (out.get('data') or {}).items():
            print(f'| {k} | {v} |')
        return
    rows = out.get('rows') or []
    if not rows:
        print('无数据')
        return
    sub = 'lhb_yyb' if '营业部名称' in rows[0] else (
        'unlock_summary' if '当日解禁股票家数' in rows[0] else
        'hot_baidu' if out.get('kind') == 'baidu' else 'hot_rank'
        if action == 'hot' else action)
    head = _pick_cols(sub, rows[0])
    print('| ' + ' | '.join(head) + ' |')
    print('|' + '|'.join(['---'] * len(head)) + '|')
    for r in rows:
        print('| ' + ' | '.join(_cell(c, r.get(c)) for c in head) + ' |')


def _text_dividend_rank(out):
    """分红排行 (原生 em 口径): 只挑股息率/分红年数/股利支付率三列"""
    data = out.get('data') or {}
    rows = data.get('rows') if isinstance(data, dict) else data
    if not isinstance(rows, list) or not rows:
        print('无数据')
        return
    head = ['股票', '股息率%', '连续分红年数', '股利支付率%']
    # 上游每只票给两行 (ASSIGN_FEATURE_CODE=0/1), 去重后再按 limit 截断
    seen, uniq = set(), []
    for r in rows:
        code = r.get('SECURITY_CODE')
        if code in seen:
            continue
        seen.add(code)
        uniq.append(r)
    rows = uniq[:int(out.get('limit') or 30)]
    recs, norm = [], []
    for r in rows:
        recs.append({'股票': str(r.get('SECURITY_NAME_ABBR') or r.get('SECURITY_CODE') or ''),
                     '股息率%': f"{(r.get('DIVIDEND_RATIO') or 0) * 100:.2f}",
                     '连续分红年数': r.get('RISE_YEARS') or 0,
                     '股利支付率%': f"{(r.get('DIVIDEND_PAY_RATIO') or 0) * 100:.1f}"})
        norm.append(recs[-1])
    w = _widths(head, norm)
    print(f'分红排行 — {len(rows)} 条 (em)')
    print('  ' + '  '.join(_cut(str(c), w[c]).ljust(w[c]) for c in head))
    for r in norm:
        print('  ' + '  '.join(_cut(_cell(c, r.get(c)), w[c]).ljust(w[c])
                               for c in head))


def _epoch_dates(row):
    """把 13 位 epoch 毫秒转成日期 (部分 akshare 表的"报告期"列)"""
    out = {}
    for k, v in row.items():
        if isinstance(v, (int, float)) and 1.0e12 < v < 2.0e12:
            try:
                import datetime as _dt
                out[k] = _dt.datetime.fromtimestamp(v / 1000).strftime('%Y-%m-%d')
                continue
            except Exception:
                pass
        out[k] = v
    return out

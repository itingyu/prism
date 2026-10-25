"""Naver Finance: 韩股行情与日 K (无需 key)

行情 https://polling.finance.naver.com/api/realtime/domestic/stock/<code>
日 K https://api.finance.naver.com/siseJson.naver?symbol=<code>&...
"""
from __future__ import annotations

import json
import re
from datetime import date, timedelta

from prism.stock.bridge import http as _http


from prism.util.num import to_float



def _get(url):
    return _http.Http(timeout=20).get(url, headers={'Referer': 'https://finance.naver.com/'})


def quote_many(codes):
    rows = []
    for code in codes:
        c = re.sub(r'\D', '', str(code)).zfill(6)
        try:
            data = json.loads(_get(
                'https://polling.finance.naver.com/api/realtime/domestic/stock/' + c))['datas'][0]
        except Exception as e:  # noqa: BLE001
            rows.append({'input': code, 'symbol': 'kr' + c, 'ok': False,
                         'err': f'{type(e).__name__}: {e}'})
            continue
        close = to_float(data.get('closePriceRaw'))
        chg = to_float(data.get('compareToPreviousClosePriceRaw'))
        amt = to_float(data.get('accumulatedTradingValueRaw'))
        rows.append({
            'input': code, 'symbol': 'kr' + c, 'ok': True, '源': 'naver',
            'name': data.get('stockName'), '现价': close,
            '昨收': (close - chg) if close is not None and chg is not None else None,
            '今开': to_float(data.get('openPriceRaw')),
            '最高': to_float(data.get('highPriceRaw')),
            '最低': to_float(data.get('lowPriceRaw')),
            '涨跌': chg, '涨跌幅': to_float(data.get('fluctuationsRatio')),
            '成交量': to_float(data.get('accumulatedTradingVolumeRaw')),
            '成交额万': amt / 1e4 if amt is not None else None,   # 韩元 -> 万
            '行情时间': data.get('localTradedAt'),
            '状态': data.get('marketStatus'),
        })
    return rows


def kline_rows(code, count=120, start=None, end=None, period='day'):
    """日/周/月 K: 返回 [{date, open, high, low, close, volume}] 升序"""
    import re as _re
    c = _re.sub(r'\D', '', str(code)).zfill(6)
    tf = {'day': 'day', 'd': 'day', 'week': 'week', 'w': 'week',
          'month': 'month', 'm': 'month'}.get(str(period or 'day').lower(), 'day')
    n = max(int(count or 120), 1)
    end_d = (end or date.today().strftime('%Y%m%d')).replace('-', '')
    if start:
        start_d = str(start).replace('-', '')
    else:
        start_d = (date.today() - timedelta(days=int(n * 1.6) + 10)).strftime('%Y%m%d')
    url = ('https://api.finance.naver.com/siseJson.naver?symbol=' + c +
           '&requestType=1&timeframe=' + tf + '&startTime=' + start_d + '&endTime=' + end_d)
    txt = _get(url).strip()
    if not txt:
        return []
    txt = txt.replace("'", '"').replace('None', 'null')
    raw = json.loads(txt)
    rows = []
    for r in raw[1:]:
        if len(r) < 6 or not str(r[0]).isdigit():
            continue
        d = str(r[0])
        d = f'{d[:4]}-{d[4:6]}-{d[6:8]}' if len(d) == 8 and d.isdigit() else d
        rows.append({'date': d, 'open': float(r[1]), 'high': float(r[2]),
                     'low': float(r[3]), 'close': float(r[4]), 'volume': float(r[5])})
    return rows[-n:]


class NaverSource:
    """韩股源 mixin (方法名前缀 naver_, 与其它源不重叠)"""

    def naver_quote(self, code: str = '005930') -> dict:
        from prism.stock.bridge.sources import _ok, _err
        try:
            rows = quote_many([code])
        except Exception as e:  # noqa: BLE001
            return _err(str(e))
        return _ok({'rows': rows, 'count': len(rows)})

    def naver_kline(self, code: str = '005930', period: str = 'day',
                    count: int = 320, fq: str = None) -> dict:
        from prism.stock.bridge.sources import _ok, _err
        try:
            rows = kline_rows(code, count=count, period=period)
        except Exception as e:  # noqa: BLE001
            return _err(str(e))
        if not rows:
            return _err(f'{code} 无 K 线数据')
        return _ok({'symbol': 'kr' + str(code).lstrip('krKR'),
                    'period': period, 'fq': fq or 'none',
                    'klines': rows, 'count': len(rows)})

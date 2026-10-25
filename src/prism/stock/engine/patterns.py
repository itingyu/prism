"""技术形态识别

从 K 线里找出**有信息量的事件形态**, 而不是把均线/RSI 再抄一遍。
每个形态给出: 名称 / 方向 / 发生日期 / 一句话依据 / 强度分。

覆盖的形态 (短线客真正会盯的那几类):
  1. MACD 底背离 / 顶背离   —— 价格创新低, DIF 不创新低 (反之)
  2. 向上跳空 / 向下跳空   —— 今低 > 昨高 (今高 < 昨低)
  3. 平台突破              —— N 日横盘 (振幅窄) 后放量突破上沿
  4. 量价背离              —— 价涨量缩 / 价跌量增
  5. 均线金叉 / 死叉      —— MA5 上穿/下穿 MA20
  6. 连续涨停 / 炸板       —— 用收盘价与涨停幅度推算 (无涨停价时按 10% 估)
  7. 长上影 / 长下影       —— 影线占实体的比例过高

判定只用收盘/最高/最低/量/均线, 不引入新数据源 —— K 线从 feeds.kline_list
拿 (腾讯前复权优先), 指标复用 tech_indicators 的 numpy 实现。
"""

from prism.util.num import to_float
__all__ = ['detect', 'PATTERNS']

PATTERNS = ('MACD底背离', 'MACD顶背离', '向上跳空', '向下跳空', '平台突破',
            '量价背离', '均线金叉', '均线死叉', '连续涨停', '长上影', '长下影')


def detect(items, lookback=120) -> list:
    """items: feeds.kline_list 的 items 列表 (含 date/open/close/high/low/volume)

    返回: [{name, direction, date, detail, strength}, ...] 按时间倒序
    """
    rows = []
    for it in (items or []):
        if not isinstance(it, dict):
            continue
        r = {'date': it.get('date'),
             'open': to_float(it.get('open')), 'close': to_float(it.get('close')),
             'high': to_float(it.get('high')), 'low': to_float(it.get('low')),
             'volume': to_float(it.get('volume'))}
        if r['close'] is None:
            continue
        rows.append(r)
    if len(rows) < 20:
        return []
    rows = rows[-int(lookback):] if lookback else rows

    from prism.stock.engine.analysis import tech_indicators as ti
    from prism.stock.engine.analysis.frame import build
    df = ti.calc(build(rows))
    n = len(rows)
    out = []

    def _ma(i, col):
        try:
            v = df[col][i]
        except (KeyError, IndexError):
            return None
        return None if v is None or v != v else float(v)

    # 1/5. MACD 背离 + 均线金叉死叉
    for i in range(max(20, n - 30), n):
        r = rows[i]
        prev = rows[i - 1] if i else None
        dif = _ma(i, 'macd_dif')
        dif_prev = _ma(i - 1, 'macd_dif') if i else None
        if dif is not None and dif_prev is not None and prev:
            # 底背离: 价格创新低 (近 20 日), DIF 未创新低
            window = rows[max(0, i - 20):i]
            if window:
                min_low = min(x['low'] for x in window if x['low'] is not None)
                min_dif = min(_ma(j, 'macd_dif') or 0 for j in range(max(0, i - 20), i))
                if (r['low'] is not None and r['low'] <= min_low
                        and dif > min_dif and dif_prev is not None and dif_prev > min_dif):
                    out.append({'name': 'MACD底背离', 'direction': 'bullish', 'date': r['date'],
                                'detail': f'价格 {r["low"]:.2f} 创新低, DIF {dif:.3f} 未创新低',
                                'strength': 3})
                max_high = max(x['high'] for x in window if x['high'] is not None)
                max_dif = max(_ma(j, 'macd_dif') or 0 for j in range(max(0, i - 20), i))
                if (r['high'] is not None and r['high'] >= max_high
                        and dif < max_dif and dif_prev is not None and dif_prev < max_dif):
                    out.append({'name': 'MACD顶背离', 'direction': 'bearish', 'date': r['date'],
                                'detail': f'价格 {r["high"]:.2f} 创新高, DIF {dif:.3f} 未创新高',
                                'strength': 3})
        ma5, ma5_prev = _ma(i, 'ma5'), _ma(i - 1, 'ma5') if i else None
        ma20, ma20_prev = _ma(i, 'ma20'), _ma(i - 1, 'ma20') if i else None
        if None not in (ma5, ma5_prev, ma20, ma20_prev):
            if ma5_prev <= ma20_prev and ma5 > ma20:
                out.append({'name': '均线金叉', 'direction': 'bullish', 'date': r['date'],
                            'detail': f'MA5 {ma5:.2f} 上穿 MA20 {ma20:.2f}', 'strength': 2})
            elif ma5_prev >= ma20_prev and ma5 < ma20:
                out.append({'name': '均线死叉', 'direction': 'bearish', 'date': r['date'],
                            'detail': f'MA5 {ma5:.2f} 下穿 MA20 {ma20:.2f}', 'strength': 2})

    # 2. 跳空缺口
    for i in range(1, n):
        r, p = rows[i], rows[i - 1]
        if r['low'] is not None and p['high'] is not None and r['low'] > p['high']:
            out.append({'name': '向上跳空', 'direction': 'bullish', 'date': r['date'],
                        'detail': f'今低 {r["low"]:.2f} > 昨高 {p["high"]:.2f}', 'strength': 2})
        elif r['high'] is not None and p['low'] is not None and r['high'] < p['low']:
            out.append({'name': '向下跳空', 'direction': 'bearish', 'date': r['date'],
                        'detail': f'今高 {r["high"]:.2f} < 昨低 {p["low"]:.2f}', 'strength': 2})

    # 3. 平台突破: 前 20 日振幅 < 6%, 今日放量(>1.5x) 突破平台最高
    if n >= 22:
        for i in range(21, n):
            win = rows[i - 20:i]
            highs = [x['high'] for x in win if x['high'] is not None]
            lows = [x['low'] for x in win if x['low'] is not None]
            vols = [x['volume'] for x in win if x['volume'] is not None]
            if not highs or not lows or not vols:
                continue
            span = (max(highs) - min(lows)) / min(lows) if min(lows) else 1
            if span > 0.06:
                continue
            v_now, v_avg = rows[i]['volume'], (sum(vols) / len(vols))
            if v_now and v_avg and v_now > v_avg * 1.5 and rows[i]['close'] > max(highs):
                out.append({'name': '平台突破', 'direction': 'bullish', 'date': rows[i]['date'],
                            'detail': (f'20 日平台振幅 {span * 100:.1f}%, 放量 {v_now / v_avg:.1f}x '
                                       f'收 {rows[i]["close"]:.2f} 破前高 {max(highs):.2f}'),
                            'strength': 3})

    # 4. 量价背离
    for i in range(5, n):
        r, p = rows[i], rows[i - 1]
        if r['volume'] is None or p['volume'] is None or not r['volume'] or not p['volume']:
            continue
        vchg = r['volume'] / p['volume']
        if r['close'] > p['close'] and vchg < 0.8:
            out.append({'name': '量价背离', 'direction': 'bearish', 'date': r['date'],
                        'detail': f'价涨 ({p["close"]:.2f}→{r["close"]:.2f}) 但量缩至 {vchg:.2f}x',
                        'strength': 1})
        elif r['close'] < p['close'] and vchg > 1.5:
            out.append({'name': '量价背离', 'direction': 'bullish', 'date': r['date'],
                        'detail': f'价跌 ({p["close"]:.2f}→{r["close"]:.2f}) 但量增至 {vchg:.2f}x',
                        'strength': 1})

    # 5. 连续涨停 (按 10% 幅度估, 主板口径; 有涨停价时用涨停价更好)
    streak = 0
    for i in range(n - 1, 0, -1):
        r, p = rows[i], rows[i - 1]
        if p['close'] and r['close'] and r['close'] / p['close'] - 1 >= 0.095:
            streak += 1
        else:
            break
    if streak >= 2:
        out.append({'name': '连续涨停', 'direction': 'bullish', 'date': rows[-1]['date'],
                    'detail': f'已连涨 {streak} 个涨停 (>9.5%/日)', 'strength': 3})

    # 6. 长影线
    for i in range(n - 5, n):
        r = rows[i]
        if r['high'] is None or r['low'] is None or r['open'] is None:
            continue
        body = abs(r['close'] - r['open'])
        rng = r['high'] - r['low']
        if not rng:
            continue
        up = (r['high'] - max(r['close'], r['open'])) / rng
        down = (min(r['close'], r['open']) - r['low']) / rng
        if up >= 0.5 and body / rng < 0.3:
            out.append({'name': '长上影', 'direction': 'bearish', 'date': r['date'],
                        'detail': f'上影占 {up * 100:.0f}%, 实体仅 {body / rng * 100:.0f}%', 'strength': 1})
        if down >= 0.5 and body / rng < 0.3:
            out.append({'name': '长下影', 'direction': 'bullish', 'date': r['date'],
                        'detail': f'下影占 {down * 100:.0f}%, 实体仅 {body / rng * 100:.0f}%', 'strength': 1})

    out.sort(key=lambda x: (x['date'] or '', x['name']), reverse=True)
    return out

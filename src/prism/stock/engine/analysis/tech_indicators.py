"""
技术指标计算
============
从 a-share-short-screen 和 stock-analysis 整合去重
所有指标只用 numpy (不依赖 pandas / akshare) —— pandas 导入本机要 2.8s,
而这里只需要 rolling 均值 / EMA, 自带实现省掉这笔启动开销。
"""
import numpy as np

from prism.stock.engine.analysis.frame import Frame, build, isna

__all__ = ['calc', 'score_short', 'score_general', 'technical_levels']


# ── 数值工具 (语义对齐 pandas) ─────────────────────────────────────

def _to_float(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return float('nan')


def _col(df: Frame, name: str, n: int) -> np.ndarray:
    """取一列成 float 数组; 缺列/非数值 → NaN (pandas 兜底同义)"""
    if name not in df.columns:
        return np.full(n, np.nan)
    return np.array([_to_float(x) for x in df[name]], dtype=float)


def _roll_mean(a: np.ndarray, window: int, min_periods: int = None) -> np.ndarray:
    """rolling(window).mean(): 窗口内有效值不足 min_periods 时给 NaN

    pandas 的 rolling 默认 min_periods=window, 且窗口按位置固定 (不足窗口
    的开头段一律 NaN), NaN 值跳过不计 —— 这里照抄。
    """
    n = len(a)
    if min_periods is None:
        min_periods = window
    valid = ~np.isnan(a)
    filled = np.where(valid, a, 0.0)
    csum = np.concatenate(([0.0], np.cumsum(filled)))
    cval = np.concatenate(([0], np.cumsum(valid.astype(int))))
    out = np.full(n, np.nan)
    for i in range(n):
        lo = max(0, i - window + 1)
        cnt = int(cval[i + 1] - cval[lo])
        if cnt >= min_periods and cnt > 0:
            out[i] = (csum[i + 1] - csum[lo]) / cnt
    return out


def _ewm(a: np.ndarray, span: int) -> np.ndarray:
    """ewm(span=span, adjust=False).mean()"""
    alpha = 2.0 / (span + 1.0)
    out = np.full(len(a), np.nan)
    prev = float('nan')
    for i, v in enumerate(a):
        if np.isnan(v):
            out[i] = prev
            continue
        prev = v if np.isnan(prev) else alpha * v + (1.0 - alpha) * prev
        out[i] = prev
    return out


def _shift(a: np.ndarray) -> np.ndarray:
    out = np.full(len(a), np.nan)
    if len(a) > 1:
        out[1:] = a[:-1]
    return out


def _diff(a: np.ndarray) -> np.ndarray:
    out = np.full(len(a), np.nan)
    if len(a) > 1:
        out[1:] = a[1:] - a[:-1]
    return out


def _div(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """a / b, b 为 0 或 NaN 时给 NaN (pandas replace(0, NaN) 后再除)"""
    out = np.full(len(a), np.nan)
    with np.errstate(divide='ignore', invalid='ignore'):
        for i in range(len(a)):
            if np.isnan(b[i]) or b[i] == 0:
                continue
            out[i] = a[i] / b[i]
    return out


def _where_pos(a: np.ndarray) -> np.ndarray:
    """pandas `s.where(s > 0, 0)`: NaN 比较为 False → 记 0"""
    return np.array([v if (not np.isnan(v) and v > 0) else 0.0 for v in a])


def _where_neg(a: np.ndarray) -> np.ndarray:
    """pandas `(-s).where(s < 0, 0)`"""
    return np.array([-v if (not np.isnan(v) and v < 0) else 0.0 for v in a])


def _max3(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> np.ndarray:
    """concat(...).max(axis=1): 跳过 NaN 取最大 (全 NaN 则 NaN)"""
    out = np.full(len(a), np.nan)
    for i in range(len(a)):
        vals = [x[i] for x in (a, b, c) if not np.isnan(x[i])]
        if vals:
            out[i] = max(vals)
    return out


def calc(df):
    """
    计算所有技术指标
    输入: Frame (含 close / high / low / volume 列)
    输出: 同结构 Frame, 新增 ma5/ma10/ma20/ma60/vol_ma5/vol_ma60/vol_ratio/
          atr/bias_ma5/bias_ma20/macd_dif/macd_dea/macd_hist/rsi6
    """
    if df is None or df.empty or len(df) < 20:
        return df

    df = df.copy()
    n = len(df)

    # 必备列兜底
    for c in ("open", "close", "high", "low", "volume"):
        if c not in df.columns:
            df[c] = [float('nan')] * n

    close = _col(df, 'close', n)
    high = _col(df, 'high', n)
    low = _col(df, 'low', n)
    volume = _col(df, 'volume', n)

    # 均线
    df["ma5"] = list(_roll_mean(close, 5))
    df["ma10"] = list(_roll_mean(close, 10))
    df["ma20"] = list(_roll_mean(close, 20))
    df["ma60"] = list(_roll_mean(close, 60))

    # 量能
    vol_ma5 = _roll_mean(volume, 5)
    vol_ma60 = _roll_mean(volume, min(60, n))
    with np.errstate(divide='ignore', invalid='ignore'):
        vr = np.where((vol_ma60 != 0) & ~np.isnan(vol_ma60), vol_ma5 / vol_ma60, np.nan)
    df["vol_ma5"] = list(vol_ma5)
    df["vol_ma60"] = list(vol_ma60)
    df["vol_ratio"] = list(np.where(np.isnan(vr), 1.0, vr))   # fillna(1.0)

    # ATR (14): TR = max(高-低, |高-昨收|, |低-昨收|)
    close_prev = _shift(close)
    tr = _max3(high - low, np.abs(high - close_prev), np.abs(low - close_prev))
    df["atr"] = list(_roll_mean(tr, 14))

    # 乖离率
    with np.errstate(divide='ignore', invalid='ignore'):
        bias5 = np.where(df["ma5"] != 0, (close - np.array(df["ma5"])) / np.array(df["ma5"]) * 100, np.nan)
        bias20 = np.where(df["ma20"] != 0, (close - np.array(df["ma20"])) / np.array(df["ma20"]) * 100, np.nan)
    df["bias_ma5"] = list(bias5)
    df["bias_ma20"] = list(bias20)

    # MACD
    ema12 = _ewm(close, 12)
    ema26 = _ewm(close, 26)
    dif = ema12 - ema26
    dea = _ewm(dif, 9)
    df["macd_dif"] = list(dif)
    df["macd_dea"] = list(dea)
    df["macd_hist"] = list(2 * (dif - dea))

    # RSI (6)
    delta = _diff(close)
    gain = _roll_mean(_where_pos(delta), 6)
    loss = _roll_mean(_where_neg(delta), 6)
    rs = _div(gain, loss)
    with np.errstate(divide='ignore', invalid='ignore'):
        rsi = np.where(np.isnan(rs), np.nan, 100 - 100 / (1 + rs))
    df["rsi6"] = list(rsi)

    return df


def score_short(df):
    """
    短线技术评分 0-100（a-share-short-screen 原版逻辑）
    加分项: 均线(20) + 量能(20) + MACD(20) + RSI(20) + 乖离率(20)

    返回: (score, breakdown, last_row)
    """
    if df is None or len(df) < 20:
        return None, None, None

    last = df.iloc[-1]
    prev = df.iloc[-2]
    score = 0
    breakdown = {}

    # 1. 均线多头排列 (20)
    above_ma5 = last["close"] > last["ma5"]
    above_ma10 = last["close"] > last["ma10"]
    above_ma20 = last["close"] > last["ma20"]
    above_ma60 = last["close"] > last["ma60"] if not isna(last["ma60"]) else False
    ma20_up = last["ma20"] > prev["ma20"]
    ma60_up = (last["ma60"] > prev["ma60"]) if not isna(last["ma60"]) else False

    long_arr = sum([above_ma5, above_ma10, above_ma20, above_ma60])
    if long_arr == 4 and ma20_up and ma60_up:
        score += 20; breakdown["均线多头"] = 20
    elif long_arr >= 3 and ma20_up:
        score += 14; breakdown["均线偏多"] = 14
    elif long_arr >= 2:
        score += 8

    # 2. 量能 (20)
    vr = last["vol_ratio"]
    if isna(vr):
        vr = 1.0
    if vr >= 1.5 and last["close"] > prev["close"]:
        score += 20; breakdown["放量上涨"] = 20
    elif vr >= 1.2:
        score += 14; breakdown["温和放量"] = 14
    elif vr >= 0.8:
        score += 8
    elif vr < 0.5:
        breakdown["缩量"] = 0

    # 3. MACD (20)
    dif, dea = last["macd_dif"], last["macd_dea"]
    h_now, h_prev = last["macd_hist"], prev["macd_hist"]
    if dif > dea and h_now > 0 and h_now > h_prev:
        score += 20; breakdown["MACD金叉向上"] = 20
    elif dif > dea and h_now > 0:
        score += 14; breakdown["MACD多头"] = 14
    elif dif > dea:
        score += 8

    # 4. RSI (20)
    rsi = last["rsi6"]
    if isna(rsi):
        rsi = 50
    if 50 <= rsi <= 70:
        score += 20; breakdown["RSI健康"] = 20
    elif 40 <= rsi < 50:
        score += 14; breakdown["RSI偏弱"] = 14
    elif 70 < rsi <= 80:
        score += 10; breakdown["RSI偏强"] = 10
    elif rsi > 80 or rsi < 30:
        breakdown["RSI极值"] = 0

    # 5. 乖离率 (20)
    bias = last["bias_ma5"]
    if isna(bias):
        bias = 0
    if -2 <= bias <= 5:
        score += 20; breakdown["乖离合理"] = 20
    elif 5 < bias <= 10:
        score += 12; breakdown["轻微追高"] = 12
    elif bias > 10:
        score += 4; breakdown["追高风险"] = 4
    elif bias < -10:
        score += 8; breakdown["超跌"] = 8

    return score, breakdown, last


def score_general(df, news_items=None, macro_score=None):
    """
    综合评分 0-100（技术面 60 + 消息面 30 + 宏观 10）

    归一化说明：
      score_short 产出 0-100 → 技术面贡献 = score_short × 0.6（0-60）
      消息面 30 分由 news_scorer.score() 的 -100~+100 映射：(s + 100) / 200 × 30
      宏观 10 分由调用方传入（0-10），缺省按中性 5 计
      三项相加即为 0-100 综合分，与短选门槛「≥ 60 / 100」同口径

    硬规则:
      RSI > 80 → 禁买
      bias_ma5 > 5% → 禁买（不追高）
    """
    if df is None or len(df) < 20:
        return None, None, None, []

    last = df.iloc[-1]
    breakdown = {}
    warnings = []

    rsi = last["rsi6"] if not isna(last["rsi6"]) else 50
    bias = last["bias_ma5"] if not isna(last["bias_ma5"]) else 0

    if rsi > 80:
        warnings.append("RSI > 80 超买")
    if bias > 5:
        warnings.append(f"乖离率 MA5 = {bias:.2f}% 追高风险")

    short_score, short_bd, _ = score_short(df)
    if short_score is None:
        return None, None, None, warnings

    # 技术面 0-60
    tech_score = round(short_score * 0.6, 1)
    breakdown["技术面(60)"] = tech_score

    # 消息面 0-30（-100~+100 线性映射）
    if news_items is not None:
        from prism.stock.engine.sentiment import news_scorer
        ns = news_scorer.score(news_items)["score"]
        news_score = round((ns + 100) / 200 * 30, 1)
    else:
        ns = None
        news_score = 15.0          # 无数据按中性 15/30
    breakdown["消息面(30)"] = news_score

    # 宏观 0-10
    mac = 5.0 if macro_score is None else max(0.0, min(10.0, float(macro_score)))
    breakdown["宏观(10)"] = mac

    score = round(tech_score + news_score + mac, 1)
    return score, breakdown, last, warnings


def technical_levels(df, last=None):
    """
    计算三档入场价位 + 支撑阻力 + 止损止盈（a-share-short-screen 原版）
    输入: 已 calc 后的 Frame + last 行
    """
    if df is None or (last is None and len(df) == 0):
        return None

    if last is None:
        last = df.iloc[-1]

    close = float(last["close"])
    ma5 = float(last["ma5"]) if not isna(last["ma5"]) else close
    ma10 = float(last["ma10"]) if not isna(last["ma10"]) else close
    ma20 = float(last["ma20"]) if not isna(last["ma20"]) else close
    ma60 = float(last["ma60"]) if not isna(last["ma60"]) else close
    atr = float(last["atr"]) if not isna(last["atr"]) else close * 0.02
    vol_ratio = float(last["vol_ratio"]) if not isna(last["vol_ratio"]) else 1.0

    highs = [v for v in df["high"][-60:] if not isna(v)]
    lows = [v for v in df["low"][-60:] if not isna(v)]
    recent_high = float(max(highs)) if highs else close
    recent_low = float(min(lows)) if lows else close

    support = max([s for s in [ma20, ma60, recent_low * 0.98] if not isna(s)])
    resistance = min([r for r in [recent_high, ma5 * 1.05, close * 1.05] if not isna(r)])

    bias = float(last["bias_ma5"]) if not isna(last.get("bias_ma5", 0)) else 0
    rsi = float(last["rsi6"]) if not isna(last.get("rsi6", 50)) else 50

    return {
        "current_price": round(close, 2),
        "ma5": round(ma5, 2),
        "ma10": round(ma10, 2),
        "ma20": round(ma20, 2),
        "ma60": round(ma60, 2) if not isna(last["ma60"]) else None,
        "atr": round(atr, 2),
        "vol_ratio": round(vol_ratio, 2),
        "support": round(support, 2),
        "resistance": round(resistance, 2),
        "recent_high_60d": round(recent_high, 2),
        "recent_low_60d": round(recent_low, 2),
        "entry_breakout": round(resistance * 1.005, 2),
        "entry_pullback": round(ma10 * 0.99, 2),
        "entry_observing": round(close * (1.003 if close > ma5 else 1.0), 2),
        "hard_stop": round(close * 0.93, 2),       # -7%
        "target_1": round(close * 1.08, 2),
        "target_2": round(close * 1.15, 2),
        "bias_ma5_pct": round(bias, 2),
        "rsi6": round(rsi, 1),
        "macd_hist": round(float(last.get("macd_hist", 0)) if not isna(last.get("macd_hist", 0)) else 0, 4),
    }

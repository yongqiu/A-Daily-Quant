"""
Technical Indicator Calculation Module
全面的技术指标计算：MA、MACD、RSI、KDJ、布林带、支撑压力位、综合评分
"""
import pandas as pd
import numpy as np
from typing import Dict, Any, Tuple


def safe_round(value: float, decimals: int = 2) -> Any:
    """Safe round that returns None if value is NaN or Infinite"""
    if pd.isna(value) or np.isinf(value):
        return None
    return round(value, decimals)


def calculate_ma(df: pd.DataFrame, periods: list = [5, 10, 20, 60]) -> pd.DataFrame:
    """计算多周期均线"""
    for period in periods:
        df[f'ma{period}'] = df['close'].rolling(window=period).mean()
    return df


def calculate_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """计算MACD指标"""
    ema_fast = df['close'].ewm(span=fast, adjust=False).mean()
    ema_slow = df['close'].ewm(span=slow, adjust=False).mean()
    
    df['macd_dif'] = ema_fast - ema_slow
    df['macd_dea'] = df['macd_dif'].ewm(span=signal, adjust=False).mean()
    df['macd_hist'] = (df['macd_dif'] - df['macd_dea']) * 2
    
    return df


def calculate_rsi(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """
    计算RSI指标
    RSI > 70: 超买区域（考虑卖出）
    RSI < 30: 超卖区域（考虑买入）
    """
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    return df


def calculate_kdj(df: pd.DataFrame, n: int = 9, m1: int = 3, m2: int = 3) -> pd.DataFrame:
    """
    计算KDJ指标
    K/D > 80: 超买
    K/D < 20: 超卖
    金叉（K上穿D）: 买入信号
    死叉（K下穿D）: 卖出信号
    """
    low_list = df['low'].rolling(window=n, min_periods=1).min()
    high_list = df['high'].rolling(window=n, min_periods=1).max()
    
    rsv = (df['close'] - low_list) / (high_list - low_list) * 100
    
    df['kdj_k'] = rsv.ewm(com=m1 - 1, adjust=False).mean()
    df['kdj_d'] = df['kdj_k'].ewm(com=m2 - 1, adjust=False).mean()
    df['kdj_j'] = 3 * df['kdj_k'] - 2 * df['kdj_d']
    
    return df


def calculate_bollinger(df: pd.DataFrame, period: int = 20, std_dev: int = 2) -> pd.DataFrame:
    """
    计算布林带
    价格触及上轨: 可能超买/突破
    价格触及下轨: 可能超卖/支撑
    带宽收窄: 可能即将变盘
    """
    df['boll_mid'] = df['close'].rolling(window=period).mean()
    df['boll_std'] = df['close'].rolling(window=period).std()
    df['boll_upper'] = df['boll_mid'] + (df['boll_std'] * std_dev)
    df['boll_lower'] = df['boll_mid'] - (df['boll_std'] * std_dev)
    
    # 布林带宽度（判断波动性）
    df['boll_width'] = (df['boll_upper'] - df['boll_lower']) / df['boll_mid'] * 100
    
    # 价格在布林带中的位置 (0-100)
    df['boll_position'] = (df['close'] - df['boll_lower']) / (df['boll_upper'] - df['boll_lower']) * 100
    
    return df


def calculate_pivot_points(df: pd.DataFrame) -> pd.DataFrame:
    """
    计算经典 Pivot Points (枢轴点) 用于预测次日阻力与支撑
    Pivot = (High + Low + Close) / 3
    R1 = 2*Pivot - Low
    S1 = 2*Pivot - High
    """
    pivot = (df['high'] + df['low'] + df['close']) / 3
    
    # 阻力位
    df['pivot_point'] = pivot
    df['r1'] = 2 * pivot - df['low']
    df['r2'] = pivot + (df['high'] - df['low'])
    
    # 支撑位
    df['s1'] = 2 * pivot - df['high']
    df['s2'] = pivot - (df['high'] - df['low'])
    
    return df


def calculate_support_resistance(df: pd.DataFrame, lookback: int = 20) -> pd.DataFrame:
    """计算近期支撑位和压力位"""
    df['resistance'] = df['high'].rolling(window=lookback).max()
    df['support'] = df['low'].rolling(window=lookback).min()
    
    # 距离支撑/压力位的百分比
    df['distance_to_resistance'] = (df['resistance'] - df['close']) / df['close'] * 100
    df['distance_to_support'] = (df['close'] - df['support']) / df['close'] * 100
    
    return df


def analyze_volume_confirmation(df: pd.DataFrame, ma_period: int = 20) -> pd.DataFrame:
    """分析量价配合"""
    df['volume_ma'] = df['volume'].rolling(window=ma_period).mean()
    df['volume_ma5'] = df['volume'].rolling(window=5).mean()
    df['volume_ratio'] = df['volume'] / df['volume_ma']
    
    df['price_change'] = df['close'].pct_change()
    
    conditions = [
        (df['price_change'] > 0) & (df['volume_ratio'] > 1.2),
        (df['price_change'] > 0) & (df['volume_ratio'] <= 1.2),
        (df['price_change'] < 0) & (df['volume_ratio'] > 1.2),
        (df['price_change'] < 0) & (df['volume_ratio'] <= 1.2),
    ]
    
    choices = ['放量上涨', '缩量上涨', '放量下跌', '缩量下跌']
    df['volume_pattern'] = np.select(conditions, choices, default='平盘')
    
    return df


def analyze_ma_arrangement(df: pd.DataFrame) -> pd.DataFrame:
    """
    分析均线排列
    多头排列: MA5 > MA10 > MA20 > MA60 (强势)
    空头排列: MA5 < MA10 < MA20 < MA60 (弱势)
    """
    df['ma_bullish'] = (df['ma5'] > df['ma10']) & (df['ma10'] > df['ma20']) & (df['ma20'] > df['ma60'])
    df['ma_bearish'] = (df['ma5'] < df['ma10']) & (df['ma10'] < df['ma20']) & (df['ma20'] < df['ma60'])
    
    return df


def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """
    计算ATR (Average True Range)
    用于动态止损和仓位管理
    """
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = ranges.max(axis=1)
    
    df['atr'] = true_range.rolling(window=period).mean()
    df['atr_pct'] = (df['atr'] / df['close']) * 100
    
    return df


def calculate_indicators(df: pd.DataFrame, ma_short: int = 20, ma_long: int = 60) -> pd.DataFrame:
    """计算所有技术指标"""
    # 均线系统 (5, 10, 20, 60)
    df = calculate_ma(df, periods=[5, 10, ma_short, ma_long])
    
    # MACD
    df = calculate_macd(df)
    
    # RSI
    df = calculate_rsi(df)
    
    # KDJ
    df = calculate_kdj(df)
    
    # ATR
    df = calculate_atr(df)
    
    # 布林带
    df = calculate_bollinger(df)
    
    # 支撑压力位
    df = calculate_support_resistance(df)
    
    # Pivot Points
    df = calculate_pivot_points(df)
    
    # 量价分析
    df = analyze_volume_confirmation(df)
    
    # 均线排列
    df = analyze_ma_arrangement(df)
    
    # 其他指标
    df['volume_change_pct'] = df['volume'].pct_change() * 100
    df['distance_from_ma20'] = ((df['close'] - df[f'ma{ma_short}']) / df[f'ma{ma_short}']) * 100
    df['price_change_pct'] = df['close'].pct_change() * 100
    
    # Feature: Distance to 120-Day High (Chip Structure Proxy)
    # The closer to 1 (0% drop), the less trapped supply above.
    # We use (Close / 120-Day High)
    df['high_120'] = df['high'].rolling(window=120).max()
    df['price_vs_high120'] = df['close'] / df['high_120']
    
    return df


def detect_candlestick_patterns(df: pd.DataFrame) -> Tuple[int, list]:
    """
    识别K线形态并返回评分调整 (Bonus/Penalty)
    """
    score_adj = 0
    patterns = []
    
    if df is None or len(df) < 3:
        return 0, []

    # Get data for last 3 days
    day0 = df.iloc[-1]   # Today
    day1 = df.iloc[-2]   # Yesterday
    day2 = df.iloc[-3]   # 2 Days ago

    # Helper for Day 0 properties
    open0, close0, high0, low0 = day0['open'], day0['close'], day0['high'], day0['low']
    body0 = abs(close0 - open0)
    upper_shadow0 = high0 - max(close0, open0)
    lower_shadow0 = min(close0, open0) - low0
    
    # Helper for Day 1 properties
    open1, close1 = day1['open'], day1['close']
    
    # 0. 基础数据校验 (防止一字板导致 body0 为 0 的除法错误)
    if body0 == 0:
        body0 = 0.01

    # === 1. 锤子线 (Hammer) - 看多 [+5分] ===
    # 逻辑: 下影线 >= 实体*2, 上影线很短. 发生在回调或低位.
    is_hammer = (lower_shadow0 >= 2 * body0) and (upper_shadow0 <= 0.5 * body0)
    
    # Context Check (位置判断): RSI < 50 或 接近布林下轨/MA20
    rsi = day0.get('rsi', 50)
    boll_pos = day0.get('boll_position', 50)
    ma20 = day0.get('ma20')
    
    # Valid Context: Oversold or Near Support
    is_valid_context = (rsi < 50) or (boll_pos < 20) or (ma20 and low0 <= ma20 * 1.02)
        
    if is_hammer and is_valid_context:
        score_adj += 5
        patterns.append("✨ 锤子线/金针探底 (底部确认) (+5)")

    # === 2. 射击之星 (Shooting Star) - 看空 [-10分] ===
    # 逻辑: 上影线 >= 实体*2, 下影线很短. 发生在高位.
    is_shooting = (upper_shadow0 >= 2 * body0) and (lower_shadow0 <= 0.5 * body0)
    
    # 位置判断: 是否在高位? (RSI > 60 或 远离MA20)
    rsi = day0.get('rsi', 50)
    is_high_pos = (rsi > 60) or (ma20 and high0 > ma20 * 1.1)
    
    if is_shooting and is_high_pos:
        score_adj -= 10
        patterns.append("⚠️ 射击之星/墓碑线 (-10)")

    # === 3. 阳包阴 (Bullish Engulfing) - 强烈看多 [+8分] ===
    # 逻辑: 昨天阴线, 今天阳线. 今天实体 完全包裹 昨天实体.
    # 宽松定义: Open0 < Close1 (低开) AND Close0 > Open1 (高走覆盖)
    is_day1_bear = close1 < open1
    is_day0_bull = close0 > open0
    
    if is_day1_bear and is_day0_bull:
        if (open0 < close1) and (close0 > open1):
             score_adj += 8
             patterns.append("🔥 阳包阴/多头吞没 (+8)")

    # === 4. 乌云盖顶 (Dark Cloud Cover) - 看空 [-8分] ===
    # 逻辑: 昨天阳线, 今天高开低走阴线, 收盘跌破昨日实体中点
    is_day1_bull = close1 > open1
    is_day0_bear = close0 < open0
    midpoint1 = open1 + (close1 - open1) / 2
    
    if is_day1_bull and is_day0_bear:
        if (open0 > close1) and (close0 < midpoint1):
            score_adj -= 8
            patterns.append("💀 乌云盖顶 (-8)")

    # === 5. 早晨之星 (Morning Star) - 看多 [+10分] ===
    # 需要3天: 阴线 -> 十字星/小阴小阳 -> 大阳线
    # Day 2 (前前日): 阴线
    open2, close2 = day2['open'], day2['close']
    is_day2_bear = (close2 < open2) and abs(close2-open2)/open2 > 0.02 # 实体>2%
    
    # Day 1 (昨日): 星线 (实体很小)
    body1 = abs(close1 - open1)
    is_day1_star = body1/open1 < 0.015 # 实体<1.5%
    
    # Day 0 (今日): 阳线, 且收盘价刺入 Day2 实体一半以上
    is_day0_bull_strong = (close0 > open0) and (close0 > (close2 + open2)/2)
    
    # Context Check for Morning Star: Same as Hammer
    rsi = day0.get('rsi', 50)
    boll_pos = day0.get('boll_position', 50)
    is_valid_star_context = (rsi < 50) or (boll_pos < 20) or (ma20 and low0 <= ma20 * 1.02)

    if is_day2_bear and is_day1_star and is_day0_bull_strong and is_valid_star_context:
         score_adj += 10
         patterns.append("☀️ 早晨之星 (反转确认) (+10)")
         
    return score_adj, patterns


def get_stock_operation_suggestion(total_score: int, metrics: Dict[str, Any]) -> str:
    """
    根据个股评分给出操作建议
    """
    close = metrics.get('close')
    ma20 = metrics.get('ma20')
    
    # Handle missing data
    if close is None or ma20 is None:
        is_above_ma20 = False
    else:
        is_above_ma20 = close > ma20
    
    if total_score >= 80:
        return "【坚决持有】趋势强烈，可持有或逢低加仓"
    elif total_score >= 65:
        return "【持有】多头趋势中，继续持有"
    elif total_score >= 50:
        if is_above_ma20:
             return "【持有/观望】震荡偏多，关注支撑位"
        else:
             return "【观望】震荡偏弱，暂不介入"
    elif total_score >= 35:
        return "【减仓】趋势走弱，建议降低仓位"
    else:
        return "【清仓/回避】空头趋势，建议离场"


def calculate_composite_score(metrics: Dict[str, Any]) -> Tuple[int, str, list]:
    """
    计算综合评分 (0-100分)
    """
    scores = []
    details = []
    
    # Helper for safe float retrieval
    def get_val(key):
        return metrics.get(key)
    
    # === 趋势得分 (35分) ===
    trend_score = 0
    
    # 价格与MA20关系 (10分)
    close = get_val('close')
    ma20 = get_val('ma20')
    
    if close is not None and ma20 is not None:
        if close > ma20:
            trend_score += 10
            details.append("✅ 价格在MA20上方 (+10)")
        else:
            details.append("❌ 价格在MA20下方 (+0)")
    else:
        details.append("⚠️ 价格/MA20数据缺失 (+0)")
    
    # 均线排列 (10分)
    ma_arrangement = metrics.get('ma_arrangement')
    if ma_arrangement == '多头排列':
        trend_score += 10
        details.append("✅ 均线多头排列 (+10)")
    elif ma_arrangement == '空头排列':
        details.append("❌ 均线空头排列 (+0)")
    else:
        trend_score += 5
        details.append("⚠️ 均线交织 (+5)")

    # MACD (15分)
    macd_dif = get_val('macd_dif')
    macd_dea = get_val('macd_dea')
    macd_hist = get_val('macd_hist')
    
    if macd_dif is not None and macd_dea is not None:
        if macd_dif > macd_dea:
            trend_score += 10
            details.append("✅ MACD金叉 (+10)")
        else:
            details.append("❌ MACD死叉 (+0)")
    else:
        details.append("⚠️ MACD数据缺失 (+0)")
    
    if macd_hist is not None:
        if macd_hist > 0:
            trend_score += 5
            details.append("✅ MACD柱为正 (+5)")
        else:
            details.append("❌ MACD柱为负 (+0)")
    else:
        details.append("⚠️ MACD数据缺失 (+0)")
    
    scores.append(('趋势', trend_score, 35))
    
    # === 动量得分 (25分) ===
    momentum_score = 0
    
    # RSI趋势 (15分) - Adjusted Logic
    rsi = get_val('rsi')
    if rsi is not None:
        # New Logic: 60-80 (+15), 50-60 (+10), <50 (0), >85 (0)
        if 60 <= rsi <= 80:
            momentum_score += 15
            details.append(f"🔥 RSI主升浪强势区({rsi:.1f}) (+15)")
        elif 50 <= rsi < 60:
            momentum_score += 10
            details.append(f"✅ RSI多头趋势({rsi:.1f}) (+10)")
        elif rsi >= 85:
            momentum_score += 0
            details.append(f"❌ RSI极度超买({rsi:.1f}) (+0)")
        else:
            # RSI < 50 or 80-85 (Neutral/Weak)
            momentum_score += 0
            details.append(f"⚠️ RSI弱势或回调({rsi:.1f}) (+0)")
    else:
        details.append(f"⚠️ RSI数据缺失 (+0)")
    
    # Feature: Price Structure & Volume Check (10分)
    price_pos = get_val('price_vs_high120')
    vol_ratio_structure = get_val('volume_ratio')
    
    if price_pos is not None:
        if price_pos >= 0.95:
            # Check for Fake Breakout (High Price + Huge Volume > 3.5)
            if vol_ratio_structure and vol_ratio_structure > 3.5:
                momentum_score -= 5
                details.append(f"🛑 逼近前高但爆天量(VR:{vol_ratio_structure}) 疑似诱多 (-5)")
            else:
                momentum_score += 10
                details.append(f"🔥 逼近前高({price_pos:.2%}) (+10)")
        elif price_pos >= 0.85:
            momentum_score += 5
            details.append(f"✅ 接近高点({price_pos:.2%}) (+5)")
        else:
            details.append(f"⚠️ 距前高较远({price_pos:.2%}) (+0)")
    else:
        details.append(f"⚠️ 价格结构数据缺失 (+0)")

    scores.append(('动量', momentum_score, 25))
    
    # === 超买超卖得分 (20分) ===
    overbought_score = 0
    
    # RSI Extreme check
    if rsi is not None:
        if rsi < 80:
            overbought_score += 8
            details.append("✅ RSI安全范围 (+8)")
        else:
            details.append("⚠️ RSI超买警告 (+0)")
    else:
        details.append("⚠️ RSI数据缺失 (+0)")
    
    # KDJ (6分)
    kdj_k = get_val('kdj_k')
    if kdj_k is not None:
        if 20 <= kdj_k <= 80:
            overbought_score += 6
            details.append("✅ KDJ正常区间 (+6)")
        else:
            details.append("⚠️ KDJ极端区间 (+0)")
    else:
        details.append("⚠️ KDJ数据缺失 (+0)")
    
    # 布林带位置 (6分)
    boll_pos = get_val('boll_position')
    if boll_pos is not None:
        if 20 <= boll_pos <= 80:
            overbought_score += 6
            details.append("✅ 布林带中轨附近 (+6)")
        elif boll_pos > 80:
            details.append("⚠️ 接近布林上轨 (+0)")
        else:
            overbought_score += 3
            details.append("⚠️ 接近布林下轨 (+3)")
    else:
        # Default to safe if unknown, but give less points?
        # Let's give neutral points (3) to avoid penalizing new stocks too much
        overbought_score += 3
        details.append("⚠️ 布林带数据缺失 (+3)")
    
    scores.append(('超买超卖', overbought_score, 20))
    
    # === 量价配合得分 (15分) ===
    volume_score = 0
    
    volume_pattern = metrics.get('volume_pattern', '平盘')
    if volume_pattern == '放量上涨':
        volume_score += 15
        details.append("✅ 放量上涨 (+15)")
    elif volume_pattern == '缩量上涨':
        volume_score += 8
        details.append("⚠️ 缩量上涨（动能不足）(+8)")
    elif volume_pattern == '缩量下跌':
        volume_score += 10
        details.append("✅ 缩量下跌（抛压减轻）(+10)")
    elif volume_pattern == '放量下跌':
        details.append("❌ 放量下跌 (+0)")
    else:
        volume_score += 7
        details.append("⚠️ 平盘整理 (+7)")
    
    scores.append(('量价配合', volume_score, 15))
    
    # === 风险得分 (10分) ===
    risk_score = 0
    
    # ATR Volatility Check
    atr_pct = get_val('atr_pct')
    if atr_pct is not None:
        if 2.0 <= atr_pct <= 8.0:
            risk_score += 5
            details.append(f"✅ 波动率适中({atr_pct:.1f}%) (+5)")
        elif atr_pct < 2.0:
            details.append(f"⚠️ 波动率过低({atr_pct:.1f}%) (+0)")
        else:
            details.append(f"⚠️ 波动率过高({atr_pct:.1f}%) (+0)")
    else:
        details.append(f"⚠️ 波动率数据缺失 (+0)")
        
    # 距离MA20的风险
    dist_ma20 = get_val('distance_from_ma20')
    if dist_ma20 is not None:
        distance = abs(dist_ma20)
        if distance <= 5:
            risk_score += 3
            details.append("✅ 距MA20较近(+3)")
        elif distance <= 10:
            risk_score += 1
            details.append("⚠️ 距MA20适中(+1)")
        else:
            details.append("❌ 距MA20远(+0)")
    else:
         details.append("⚠️ MA20乖离率缺失 (+0)")
    
    # 距离支撑/压力位
    # 支撑位判定优化 (Support Logic)
    # Check proximity to MA20 or Bollinger Lower Band
    close = get_val('close')
    ma20 = get_val('ma20')
    boll_lower = get_val('boll_lower')
    
    is_at_support = False
    
    # Check MA20 Support (within 3%)
    if close and ma20 and abs(close - ma20)/ma20 <= 0.03:
         is_at_support = True
         details.append("🛡️ 获MA20支撑")
    
    # Check Boll Lower Support (within 3%)
    elif close and boll_lower and abs(close - boll_lower)/boll_lower <= 0.03:
         is_at_support = True
         details.append("🛡️ 获布林下轨支撑")

    if is_at_support:
        risk_score += 5
        details.append("✅ 支撑位确认 (+5)")
    else:
        # 如果不在支撑位，检查是否远离压力位
        dist_resistance = get_val('distance_to_resistance')
        d_res = dist_resistance if dist_resistance is not None else 5
        if d_res > 3:
             risk_score += 3
             details.append("✅ 远离压力位 (+3)")
        else:
             details.append("⚠️ 接近压力位 (+0)")
    
    scores.append(('风险控制', risk_score, 10))
    
    # === K线形态修正 (Bonus/Penalty) ===
    pat_score = metrics.get('pattern_score', 0)
    pat_details = metrics.get('pattern_details', [])
    
    if pat_score != 0 or pat_details:
         scores.append(('K线形态', pat_score, 0)) # 权重0表示额外加分项
         details.extend(pat_details)
    
    # === 计算总分和评级 ===
    total_score = sum(s[1] for s in scores)
    
    if total_score >= 80:
        rating = "强烈看多 🟢🟢🟢"
    elif total_score >= 65:
        rating = "偏多 🟢🟢"
    elif total_score >= 50:
        rating = "中性 🟡"
    elif total_score >= 35:
        rating = "偏空 🔴"
    else:
        rating = "强烈看空 🔴🔴🔴"
    
    return total_score, rating, scores, details


def get_latest_metrics(df: pd.DataFrame, cost_price: float = None) -> Dict[str, Any]:
    """提取最新一天的指标数据用于分析"""
    if df is None or df.empty:
        return {}
    
    latest = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else latest
    
    # 基础信号判断
    # Helper to safe check >
    def safe_gt(a, b):
        if pd.isna(a) or pd.isna(b): return False
        try:
            return a > b
        except:
            return False

    trend_signal = "看涨" if safe_gt(latest['close'], latest['ma20']) else "看跌"
    macd_signal = "看涨" if safe_gt(latest['macd_dif'], latest['macd_dea']) else "看跌"
    volume_signal = "放量" if safe_gt(latest['volume_change_pct'], 0) else "缩量"
    
    # RSI信号
    rsi = latest['rsi']
    if safe_gt(rsi, 70):
        rsi_signal = "超买"
    elif safe_gt(30, rsi):
        rsi_signal = "超卖"
    else:
        rsi_signal = "中性"
    
    # KDJ信号
    kdj_signal = "金叉" if safe_gt(latest['kdj_k'], latest['kdj_d']) else "死叉"
    
    # KDJ超买超卖
    if safe_gt(latest['kdj_k'], 80):
        kdj_zone = "超买区"
    elif safe_gt(20, latest['kdj_k']):
        kdj_zone = "超卖区"
    else:
        kdj_zone = "正常区"
    
    # 量价确认
    volume_confirmation = "有效" if safe_gt(latest['volume_ratio'], 1.2) else "无效"
    
    # 均线排列
    if latest.get('ma_bullish') == True:
        ma_arrangement = "多头排列"
    elif latest.get('ma_bearish') == True:
        ma_arrangement = "空头排列"
    else:
        ma_arrangement = "交织"
    
    # 布林带信号
    boll_pos = latest['boll_position']
    if safe_gt(boll_pos, 80):
        boll_signal = "接近上轨"
    elif safe_gt(20, boll_pos):
        boll_signal = "接近下轨"
    else:
        boll_signal = "中轨附近"
    
    # ATR 止损建议
    atr_val = latest.get('atr')
    close_val = latest.get('close')
    if atr_val is not None and close_val is not None and not pd.isna(atr_val) and not pd.isna(close_val):
         stop_loss_price = close_val - (2 * atr_val)
    else:
         stop_loss_price = None
    
    metrics = {
        'date': latest['date'].strftime('%Y-%m-%d'),
        'close': safe_round(latest['close'], 2),
        'open': safe_round(latest['open'], 2),
        'high': safe_round(latest['high'], 2),
        'low': safe_round(latest['low'], 2),
        
        # 均线
        'ma5': safe_round(latest['ma5'], 2),
        'ma10': safe_round(latest['ma10'], 2),
        'ma20': safe_round(latest['ma20'], 2),
        'ma60': safe_round(latest['ma60'], 2),
        'distance_from_ma20': safe_round(latest['distance_from_ma20'], 2),
        'ma_arrangement': ma_arrangement,
        
        # MACD
        'macd_dif': safe_round(latest['macd_dif'], 4),
        'macd_dea': safe_round(latest['macd_dea'], 4),
        'macd_hist': safe_round(latest['macd_hist'], 4),
        
        # RSI
        'rsi': safe_round(rsi, 2),
        'rsi_signal': rsi_signal,
        
        # KDJ
        'kdj_k': safe_round(latest['kdj_k'], 2),
        'kdj_d': safe_round(latest['kdj_d'], 2),
        'kdj_j': safe_round(latest['kdj_j'], 2),
        'kdj_signal': kdj_signal,
        'kdj_zone': kdj_zone,
        
        # 布林带
        'boll_upper': safe_round(latest['boll_upper'], 2),
        'boll_mid': safe_round(latest['boll_mid'], 2),
        'boll_lower': safe_round(latest['boll_lower'], 2),
        'boll_position': safe_round(boll_pos, 2),
        'boll_width': safe_round(latest['boll_width'], 2),
        'boll_signal': boll_signal,
        
        # 支撑压力
        'resistance': safe_round(latest['resistance'], 2),
        'support': safe_round(latest['support'], 2),
        'distance_to_resistance': safe_round(latest['distance_to_resistance'], 2),
        'distance_to_support': safe_round(latest['distance_to_support'], 2),
        
        # Pivot Points (明日预测)
        'pivot_point': safe_round(latest['pivot_point'], 2),
        'r1': safe_round(latest['r1'], 2),
        's1': safe_round(latest['s1'], 2),
        
        # 风控 (ATR)
        'atr': safe_round(latest['atr'], 3),
        'atr_pct': safe_round(latest['atr_pct'], 2),
        'stop_loss_suggest': safe_round(stop_loss_price, 2),

        # Price Structure
        'high_120': safe_round(latest['high_120'], 2),
        'price_vs_high120': safe_round(latest['price_vs_high120'], 4),
        
        # 成交量
        'volume': int(latest['volume']),
        'volume_ma': safe_round(latest['volume_ma'], 2),
        'volume_ratio': safe_round(latest['volume_ratio'], 2),
        'volume_change_pct': safe_round(latest['volume_change_pct'], 2),
        'price_change_pct': safe_round(latest['price_change_pct'], 2),
        
        # 信号汇总
        'trend_signal': trend_signal,
        'macd_signal': macd_signal,
        'volume_signal': volume_signal,
        'volume_confirmation': volume_confirmation,
        'volume_pattern': latest['volume_pattern'],
    }
    
    # 盈亏计算
    if cost_price:
        profit_loss_pct = ((latest['close'] - cost_price) / cost_price) * 100
        metrics['cost_price'] = cost_price
        metrics['profit_loss_pct'] = safe_round(profit_loss_pct, 2)
    
    # K线形态识别
    pat_score, pat_details = detect_candlestick_patterns(df)
    metrics['pattern_score'] = pat_score
    metrics['pattern_details'] = pat_details

    # 计算综合评分
    total_score, rating, scores, details = calculate_composite_score(metrics)
    metrics['composite_score'] = total_score
    metrics['rating'] = rating
    metrics['score_breakdown'] = scores
    metrics['score_details'] = details
    
    # 添加个股操作建议
    metrics['operation_suggestion'] = get_stock_operation_suggestion(total_score, metrics)
    
    return metrics

"""
Technical Indicator Calculation Module
全面的技术指标计算：MA、MACD、RSI、KDJ、布林带、支撑压力位
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
    
    return metrics


def analyze_intraday_pattern(df: pd.DataFrame, pre_close: float) -> Dict[str, str]:
    """
    分析分时图特征 (Intraday Behavior)
    
    Args:
        df: 分时数据 (date, open, close, high, low, volume)
        pre_close: 昨日收盘价
        
    Returns:
        Dict with semantic descriptions
    """
    if df is None or df.empty or pre_close == 0:
        return {
            "open_desc": "未知",
            "close_desc": "未知",
            "strength_desc": "未知"
        }
        
    # 1. 开盘形态 (前30分钟)
    # 取前30条数据 (假设1分钟1条)
    opening_30 = df.head(30)
    open_price = df.iloc[0]['open']
    
    open_pct = (open_price - pre_close) / pre_close * 100
    
    open_desc = "平开"
    if open_pct > 2.0: open_desc = f"高开({open_pct:.1f}%)"
    elif open_pct < -2.0: open_desc = f"低开({open_pct:.1f}%)"
    elif open_pct > 0.5: open_desc = "小幅高开"
    elif open_pct < -0.5: open_desc = "小幅低开"
    
    # Check if "Low Open High Go" (低开高走)
    # Start < 0, End of 30min > Start
    if open_pct < -0.5 and opening_30.iloc[-1]['close'] > open_price:
        open_desc += "且低开高走"
        
    # 2. 封板强度 (Limit Strength)
    last_price = df.iloc[-1]['close']
    limit_up_price = round(pre_close * 1.10, 2) # 简单估算10%
    is_limit_up = (last_price >= limit_up_price - 0.02) # allowing minimal float error
    
    strength_desc = "常态震荡"
    if is_limit_up:
        strength_desc = "强势封板"
        # Check if broken (did it open limit up?)
        # 简单检查: 最低价是否大幅低于涨停价
        if df['low'].min() < limit_up_price * 0.98:
            strength_desc = "烂板(曾打开)"
            
    # 3. 尾盘表现 (Last 30 mins)
    closing_30 = df.tail(30)
    if len(closing_30) > 10:
        start_close = closing_30.iloc[0]['close']
        end_close = closing_30.iloc[-1]['close']
        
        last_change = (end_close - start_close) / start_close * 100
        
        close_desc = "平稳"
        if last_change > 1.0: close_desc = "尾盘抢筹拉升"
        elif last_change < -1.0: close_desc = "尾盘跳水"
    else:
        close_desc = "数据不足"
        
    return {
        "open_desc": open_desc,
        "close_desc": close_desc,
        "strength_desc": strength_desc
    }


def process_cyq_data(cyq_row: Dict[str, float], current_price: float) -> Dict[str, Any]:
    """
    处理筹码分布数据，生成语义化描述
    """
    if not cyq_row:
        return {}
        
    profit_pct = cyq_row.get('profit_pct', 0) * 100 # Convert to %
    avg_cost = cyq_row.get('avg_cost', 0)
    concentration = cyq_row.get('concentration_90', 0) * 100
    
    # Semantic analysis
    # Cost Position
    cost_pos = "未知"
    if current_price > avg_cost * 1.05:
        cost_pos = "股价位于平均成本上方 (获利盘主导)"
    elif current_price < avg_cost * 0.95:
        cost_pos = "股价位于平均成本下方 (套牢盘主导)"
    else:
        cost_pos = "股价在平均成本附近震荡"
        
    # Concentration
    conc_desc = "筹码发散"
    if concentration < 10:
        conc_desc = "筹码高度密集 (主力控盘)"
    elif concentration < 20:
        conc_desc = "筹码相对集中"
        
    return {
        "profit_pct": f"{profit_pct:.1f}%",
        "avg_cost": f"{avg_cost:.2f}",
        "concentration": f"{concentration:.1f}%",
        "semantic_pos": cost_pos,
        "semantic_conc": conc_desc
    }

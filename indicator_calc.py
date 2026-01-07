"""
Technical Indicator Calculation Module
全面的技术指标计算：MA、MACD、RSI、KDJ、布林带、支撑压力位、综合评分
"""
import pandas as pd
import numpy as np
from typing import Dict, Any, Tuple


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
    
    return df


def calculate_composite_score(metrics: Dict[str, Any]) -> Tuple[int, str, list]:
    """
    计算综合评分 (0-100分)
    
    评分维度：
    - 趋势 (30分): 均线位置、均线排列
    - 动量 (25分): MACD、RSI
    - 超买超卖 (20分): RSI、KDJ、布林带位置
    - 量价配合 (15分): 成交量确认
    - 风险 (10分): 距离支撑/压力位
    
    Returns:
        (总分, 评级, 详细得分列表)
    """
    scores = []
    details = []
    
    # === 趋势得分 (30分) ===
    trend_score = 0
    
    # 价格与MA20关系 (15分)
    if metrics['close'] > metrics['ma20']:
        trend_score += 15
        details.append("✅ 价格在MA20上方 (+15)")
    else:
        details.append("❌ 价格在MA20下方 (+0)")
    
    # 均线排列 (15分)
    if metrics.get('ma_arrangement') == '多头排列':
        trend_score += 15
        details.append("✅ 均线多头排列 (+15)")
    elif metrics.get('ma_arrangement') == '空头排列':
        details.append("❌ 均线空头排列 (+0)")
    else:
        trend_score += 7
        details.append("⚠️ 均线交织 (+7)")
    
    scores.append(('趋势', trend_score, 30))
    
    # === 动量得分 (25分) ===
    momentum_score = 0
    
    # MACD (15分)
    if metrics['macd_dif'] > metrics['macd_dea']:
        momentum_score += 10
        details.append("✅ MACD金叉 (+10)")
    else:
        details.append("❌ MACD死叉 (+0)")
    
    if metrics['macd_hist'] > 0:
        momentum_score += 5
        details.append("✅ MACD柱为正 (+5)")
    else:
        details.append("❌ MACD柱为负 (+0)")
    
    # RSI趋势 (10分)
    rsi = metrics['rsi']
    if 40 <= rsi <= 60:
        momentum_score += 10
        details.append(f"✅ RSI中性区间({rsi:.1f}) (+10)")
    elif 30 <= rsi < 40 or 60 < rsi <= 70:
        momentum_score += 5
        details.append(f"⚠️ RSI偏离中性({rsi:.1f}) (+5)")
    else:
        details.append(f"❌ RSI极端区间({rsi:.1f}) (+0)")
    
    scores.append(('动量', momentum_score, 25))
    
    # === 超买超卖得分 (20分) ===
    overbought_score = 0
    
    # RSI超买超卖 (8分)
    if 30 <= rsi <= 70:
        overbought_score += 8
        details.append("✅ RSI未超买超卖 (+8)")
    elif rsi > 70:
        details.append("⚠️ RSI超买警告 (+0)")
    else:
        overbought_score += 4  # 超卖可能是机会
        details.append("⚠️ RSI超卖 (+4)")
    
    # KDJ (6分)
    kdj_k = metrics['kdj_k']
    if 20 <= kdj_k <= 80:
        overbought_score += 6
        details.append("✅ KDJ正常区间 (+6)")
    else:
        details.append("⚠️ KDJ极端区间 (+0)")
    
    # 布林带位置 (6分)
    boll_pos = metrics.get('boll_position', 50)
    if 20 <= boll_pos <= 80:
        overbought_score += 6
        details.append("✅ 布林带中轨附近 (+6)")
    elif boll_pos > 80:
        details.append("⚠️ 接近布林上轨 (+0)")
    else:
        overbought_score += 3
        details.append("⚠️ 接近布林下轨 (+3)")
    
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
    
    # 距离MA20的风险
    distance = abs(metrics['distance_from_ma20'])
    if distance <= 5:
        risk_score += 5
        details.append("✅ 距MA20较近（风险可控）(+5)")
    elif distance <= 10:
        risk_score += 3
        details.append("⚠️ 距MA20适中 (+3)")
    else:
        details.append("❌ 距MA20过远（追高/杀跌风险）(+0)")
    
    # 距离支撑/压力位
    dist_support = metrics.get('distance_to_support', 5)
    dist_resistance = metrics.get('distance_to_resistance', 5)
    
    if dist_support > 3 and dist_resistance > 3:
        risk_score += 5
        details.append("✅ 远离支撑压力位 (+5)")
    elif dist_support <= 3:
        risk_score += 3
        details.append("⚠️ 接近支撑位 (+3)")
    else:
        details.append("⚠️ 接近压力位 (+0)")
    
    scores.append(('风险控制', risk_score, 10))
    
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
    trend_signal = "看涨" if latest['close'] > latest['ma20'] else "看跌"
    macd_signal = "看涨" if latest['macd_dif'] > latest['macd_dea'] else "看跌"
    volume_signal = "放量" if latest['volume_change_pct'] > 0 else "缩量"
    
    # RSI信号
    rsi = latest['rsi']
    if rsi > 70:
        rsi_signal = "超买"
    elif rsi < 30:
        rsi_signal = "超卖"
    else:
        rsi_signal = "中性"
    
    # KDJ信号
    kdj_signal = "金叉" if latest['kdj_k'] > latest['kdj_d'] else "死叉"
    
    # KDJ超买超卖
    if latest['kdj_k'] > 80:
        kdj_zone = "超买区"
    elif latest['kdj_k'] < 20:
        kdj_zone = "超卖区"
    else:
        kdj_zone = "正常区"
    
    # 量价确认
    volume_confirmation = "有效" if latest['volume_ratio'] > 1.2 else "无效"
    
    # 均线排列
    if latest['ma_bullish']:
        ma_arrangement = "多头排列"
    elif latest['ma_bearish']:
        ma_arrangement = "空头排列"
    else:
        ma_arrangement = "交织"
    
    # 布林带信号
    boll_pos = latest['boll_position']
    if boll_pos > 80:
        boll_signal = "接近上轨"
    elif boll_pos < 20:
        boll_signal = "接近下轨"
    else:
        boll_signal = "中轨附近"
    
    # ATR 止损建议
    stop_loss_price = latest['close'] - (2 * latest['atr'])
    
    metrics = {
        'date': latest['date'].strftime('%Y-%m-%d'),
        'close': round(latest['close'], 2),
        'open': round(latest['open'], 2),
        'high': round(latest['high'], 2),
        'low': round(latest['low'], 2),
        
        # 均线
        'ma5': round(latest['ma5'], 2),
        'ma10': round(latest['ma10'], 2),
        'ma20': round(latest['ma20'], 2),
        'ma60': round(latest['ma60'], 2),
        'distance_from_ma20': round(latest['distance_from_ma20'], 2),
        'ma_arrangement': ma_arrangement,
        
        # MACD
        'macd_dif': round(latest['macd_dif'], 4),
        'macd_dea': round(latest['macd_dea'], 4),
        'macd_hist': round(latest['macd_hist'], 4),
        
        # RSI
        'rsi': round(rsi, 2),
        'rsi_signal': rsi_signal,
        
        # KDJ
        'kdj_k': round(latest['kdj_k'], 2),
        'kdj_d': round(latest['kdj_d'], 2),
        'kdj_j': round(latest['kdj_j'], 2),
        'kdj_signal': kdj_signal,
        'kdj_zone': kdj_zone,
        
        # 布林带
        'boll_upper': round(latest['boll_upper'], 2),
        'boll_mid': round(latest['boll_mid'], 2),
        'boll_lower': round(latest['boll_lower'], 2),
        'boll_position': round(boll_pos, 2),
        'boll_width': round(latest['boll_width'], 2),
        'boll_signal': boll_signal,
        
        # 支撑压力
        'resistance': round(latest['resistance'], 2),
        'support': round(latest['support'], 2),
        'distance_to_resistance': round(latest['distance_to_resistance'], 2),
        'distance_to_support': round(latest['distance_to_support'], 2),
        
        # Pivot Points (明日预测)
        'pivot_point': round(latest['pivot_point'], 2),
        'r1': round(latest['r1'], 2),
        's1': round(latest['s1'], 2),
        
        # 风控 (ATR)
        'atr': round(latest['atr'], 3),
        'atr_pct': round(latest['atr_pct'], 2),
        'stop_loss_suggest': round(stop_loss_price, 2),
        
        # 成交量
        'volume': int(latest['volume']),
        'volume_ma': round(latest['volume_ma'], 2),
        'volume_ratio': round(latest['volume_ratio'], 2),
        'volume_change_pct': round(latest['volume_change_pct'], 2),
        'price_change_pct': round(latest['price_change_pct'], 2),
        
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
        metrics['profit_loss_pct'] = round(profit_loss_pct, 2)
    
    # 计算综合评分
    total_score, rating, scores, details = calculate_composite_score(metrics)
    metrics['composite_score'] = total_score
    metrics['rating'] = rating
    metrics['score_breakdown'] = scores
    metrics['score_details'] = details
    
    return metrics

# -*- coding: utf-8 -*-
"""
Scoring Service Module 评分系统
统一评分逻辑，确保股票和ETF评分的一致性
"""
import logging
import pandas as pd
from typing import Dict, Any, Optional

from indicator_calc import get_latest_metrics
from strategies.trend_strategy import StockTrendAnalyzer
from etf_score import apply_etf_score

# Configure logger
logger = logging.getLogger(__name__)

def calculate_comprehensive_score(df: pd.DataFrame, symbol: str, cost_price: float = 0.0, asset_type: str = 'stock') -> Dict[str, Any]:
    """
    Orchestrates the full scoring pipeline: 统一评分流程
    1. Base Indicators (indicator_calc)
    2. Trend Analysis (TrendStrategy) - for Stocks
    3. ETF Scoring (etf_score) - for ETFs
    4. Fusion & Metadata
    
    Args: 参数
        df: DataFrame with historical data (must contain OHLCV and technical indicators if already calculated)
        symbol: Stock/ETF symbol
        cost_price: User's cost price (for profit-based scoring adjustments in base metrics)
        asset_type: 'stock' or 'etf'
        
    Returns: 返回值
        Dict containing all metrics, analysis results, and the final 'composite_score'.
    """
    if df is None or len(df) == 0:
        return {}

    # 1. Base Indicators Calculation
    # Note: df is assumed to have indicators calculated (e.g., via calculate_indicators(df))
    # If not, the caller should ensure calculate_indicators(df) is called before or we could call it here.
    # However, get_latest_metrics assumes columns exist.
    # For safety, we trust the caller has prepared the DF to avoid redundant calculation if already done.
    
    latest = get_latest_metrics(df, cost_price)
    latest['symbol'] = symbol
    
    # Ensure metadata exists
    if '__metadata__' not in latest:
        latest['__metadata__'] = {}

    # 2. Trend Analysis (For Stocks)
    # ETFs can also have trend analysis if desired, but currently logic isolates it or applies generally?
    # stock_screener.py applies it to everything it scans (which are stocks).
    # web_server.py applies it generally now (via my fix).
    # We will apply it to ALL assets for trend score, but only Average it for Stocks usually?
    # Let's apply to all, as Trend is universal. ETF score might override later.
    
    try:
        trend_analyzer = StockTrendAnalyzer()
        trend_result = trend_analyzer.analyze(df, symbol)
        
        # Add Trend Score info to result
        latest['trend_score'] = trend_result.signal_score
        latest['trend_signal'] = trend_result.buy_signal.value
        latest['__metadata__']['trend_score'] = trend_result.signal_score
        latest['__metadata__']['trend_signal'] = trend_result.buy_signal.value
        
        # Fusion Strategy: Weighted Average
        # Currently 50/50 between Base Technicals and Trend Strategy
        latest['composite_score'] = (latest['composite_score'] + trend_result.signal_score) / 2
        
    except Exception as e:
        print(f"⚠️ Trend Analysis failed for {symbol}: {e}")
        # If trend fails, we keep the composite_score as is (Base Score)

    # 3. ETF Scoring (For ETFs)
    if asset_type == 'etf':
        try:
            # apply_etf_score might modify 'composite_score' based on premium/discount/etc.
            # It takes the 'latest' dict and returns a modified one.
            latest = apply_etf_score(latest)
        except Exception as e:
            print(f"⚠️ ETF Analysis failed for {symbol}: {e}")

    return latest

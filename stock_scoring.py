# -*- coding: utf-8 -*-
"""
Unified Stock Scoring Module
统一评分模块

Consolidates all scoring logic into a single place, using Tushare as the sole data source.
Replaces logic previously scattered in web_server.py, stock_screener.py and scoring_service.py.
"""
import pandas as pd
from typing import Dict, Any, Optional
from datetime import datetime
import logging

# 获取数据
from data_fetcher_ts import fetch_stock_data_ts, fetch_daily_basic_ts, fetch_stock_name_ts
from data_fetcher import fetch_stock_news, calculate_start_date
# 指标与分析
from indicator_calc import calculate_indicators, get_latest_metrics
from strategies.trend_strategy import StockTrendAnalyzer
from etf_score import apply_etf_score
from alpha158_lightgbm_score import (
    Alpha158LightGBMScoreError,
    get_alpha158_lightgbm_score,
)

# 配置日志记录器
logger = logging.getLogger(__name__)

def get_score(
    symbol: str,
    cost_price: float = 0.0,
    asset_type: str = 'stock',
    include_news: bool = True,
    score_mode: str = "legacy",
    trade_date: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    使用 Tushare 数据获取股票/ETF 的综合评分。
    
    参数:
        symbol: 股票代码 (例如: '600519')
        cost_price: 用户持仓成本价，用于计算收益
        asset_type: 'stock' (股票) 或 'etf' (ETF)。如果不确定，默认为 'stock'，逻辑可能会自动检测。
        include_news: 是否获取最新新闻 (默认为 True)
        
    返回:
        包含评分结果的字典，如果数据获取失败则返回 None。
        返回字典包含以下关键字段:
        - symbol: 股票代码
        - name: 股票名称
        - data_date: 评分数据的最新日期 (格式: 'YYYY-MM-DD')
        - price: 当前价格
        - composite_score: 综合评分
        - trend_score: 趋势评分
        - 其他技术指标和基本面数据
    """
    try:
        # 1. 获取历史数据 (OHLCV)
        # 使用集中式的回溯周期计算
        start_date = calculate_start_date()
        
        # 尽可能确定严格的资产类型，或者直接传递
        # Tushare 通常在 data_fetcher_ts 中处理 '51'/'159' 前缀，但显式指定更好。
        # 检查代码前缀以细化资产类型，如果传入的是通用的 'stock' 但看起来像 ETF
        if asset_type == 'stock' and (symbol.startswith('5') or symbol.startswith('1')):
             # 基本启发式判断，调用者理想情况下应提供正确类型，但我们先做安全处理
             if symbol.startswith('51') or symbol.startswith('159') or symbol.startswith('56') or symbol.startswith('58'):
                 asset_type = 'etf'

        # 获取股票的日线数据（包含最新交易日数据）
        df = fetch_stock_data_ts(symbol, start_date=start_date, period='daily')
        
        if df is None or len(df) < 60:
            print(f"⚠️ Insufficient historical data for {symbol}")
            return None

        # 2. 计算指标
        df = calculate_indicators(df)

        # 3. 计算基础指标和技术评分
        # 这使用了 `scoring_service`/`indicator_calc` 中的逻辑
        latest = get_latest_metrics(df, cost_price)
        latest['symbol'] = symbol
        
        # 获取股票名称（轻量级调用，仅查询 stock_basic）
        latest['name'] = fetch_stock_name_ts(symbol)
        
        # 从 df 最后一行提取价格和日期信息
        if not df.empty:
            last_row = df.iloc[-1]
            latest['price'] = float(last_row['close'])
            latest['close'] = float(last_row['close'])
            latest['open'] = float(last_row['open'])
            latest['high'] = float(last_row['high'])
            latest['low'] = float(last_row['low'])
            latest['volume'] = int(float(last_row['volume'])) if last_row['volume'] else 0
            latest['amount'] = float(last_row['amount']) if last_row['amount'] else 0.0
            
            # 添加数据日期 (评分数据的最新日期)
            data_date = pd.to_datetime(last_row['date'])
            latest['data_date'] = data_date.strftime('%Y-%m-%d')
        else:
            latest['price'] = 0.0
            latest['close'] = 0.0
            latest['data_date'] = None
        
        # 确保元数据字典存在
        if '__metadata__' not in latest:
            latest['__metadata__'] = {}

        # 4. 趋势分析 (策略融合)
        try:
            trend_analyzer = StockTrendAnalyzer()
            trend_result = trend_analyzer.analyze(df, symbol)
            
            latest['trend_score'] = trend_result.signal_score
            latest['trend_signal'] = trend_result.buy_signal.value
            latest['trend_strength'] = trend_result.trend_strength
            latest['__metadata__']['trend_score'] = trend_result.signal_score
            latest['__metadata__']['trend_signal'] = trend_result.buy_signal.value
            latest['__metadata__']['trend_strength'] = trend_result.trend_strength
            
            # 融合: 50/50 权重
            latest['composite_score'] = (latest['composite_score'] + trend_result.signal_score) / 2
            
        except Exception as e:
            print(f"⚠️ 趋势分析失败 {symbol}: {e}")
            # 仅保留基础评分作为综合评分

        # 5. ETF 特定评分 (如果适用)
        if asset_type == 'etf':
            try:
                latest = apply_etf_score(latest)
            except Exception as e:
                print(f"⚠️ ETF 评分失败 {symbol}: {e}")

        # 6. 整合 Tushare 每日基础数据 (基本面/流动性)
        # 获取: turnover_rate, volume_ratio, pe, pb, total_mv, circ_mv
        daily_basic = fetch_daily_basic_ts(symbol)
        
        # 标记是否使用了 Tushare 的量比
        used_ts_vr = False
        
        if daily_basic:
            for k, v in daily_basic.items():
                # 注意：我们之前修复了 fetch_daily_basic_ts 返回 0.0 而不是 None
                # 所以这里 v 可能是 0.0。
                # 如果是 volume_ratio 且为 0，我们可能不希望直接覆盖（除非真的没量）
                if v is not None:
                    # 如果是量比，且值为0，且今日有成交量，说明可能是数据缺失
                    if k == 'volume_ratio' and v == 0 and latest.get('volume', 0) > 0:
                        continue 
                    
                    latest[k] = v
                    latest['__metadata__'][k] = v
                    
                    if k == 'volume_ratio' and v > 0:
                        used_ts_vr = True

        # 补救措施：如果量比缺失或为0，手动计算
        # 原因：tushare接口的daily_basic接口返回的数据中，当天的数据量比可能为0
        # 量比 = 今日成交量 / 过去5日平均成交量
        current_vr = latest.get('volume_ratio', 0)
        current_vol = latest.get('volume', 0)
        
        if (current_vr == 0 or not used_ts_vr) and current_vol > 0 and not df.empty and len(df) >= 6:
            try:
                # 获取过去5天（不含今天）的成交量均值
                # df 最后一行是今天，倒数第2行是昨天
                past_5_vols = df['volume'].iloc[-6:-1]
                avg_vol_5 = past_5_vols.mean()
                
                if avg_vol_5 > 0:
                    calculated_vr = current_vol / avg_vol_5
                    latest['volume_ratio'] = round(calculated_vr, 2)
                    latest['__metadata__']['volume_ratio'] = round(calculated_vr, 2)
                    print(f"🔄 Calculated missing Volume Ratio for {symbol}: {calculated_vr:.2f} (Vol: {current_vol}, Avg5: {avg_vol_5:.1f})")
            except Exception as calc_e:
                print(f"⚠️ Failed to calculate volume ratio: {calc_e}")
            
        # 7. 获取新闻 (可选)
        if include_news:
            latest['latest_news'] = fetch_stock_news(symbol)

        # 确保 'price' 键用于数据库（从 'close' 映射，如果有）
        if 'price' not in latest and 'close' in latest:
            latest['price'] = latest['close']

        latest['date'] = latest.get('data_date')
        latest['score_mode'] = 'legacy'
        latest['score_mode_label'] = '原评分方式'

        if score_mode == "alpha158_lightgbm":
            if asset_type == "etf":
                latest["requested_score_mode"] = score_mode
                latest["score_mode_note"] = "ETF 暂不支持 Alpha158 + LightGBM，已保留原评分方式。"
                return latest

            latest["legacy_composite_score"] = latest.get("composite_score")
            latest["legacy_rating"] = latest.get("rating")
            latest["legacy_score_breakdown"] = latest.get("score_breakdown")
            latest["legacy_score_details"] = latest.get("score_details")
            latest["legacy_operation_suggestion"] = latest.get("operation_suggestion")

            try:
                alpha_score = get_alpha158_lightgbm_score(
                    symbol, trade_date=trade_date or latest.get("data_date")
                )
                latest.update(alpha_score)
                latest["date"] = alpha_score.get("score_date") or latest.get("data_date")
            except Alpha158LightGBMScoreError as exc:
                latest["requested_score_mode"] = score_mode
                latest["score_mode_note"] = (
                    f"Alpha158 + LightGBM 暂不可用，当前展示原评分方式。原因: {exc}"
                )

        return latest

    except Exception as e:
        print(f"❌ get_score 出错 {symbol}: {e}")
        import traceback
        traceback.print_exc()
        return None

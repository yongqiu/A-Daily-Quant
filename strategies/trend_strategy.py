# -*- coding: utf-8 -*-
"""
Trend Trading Strategy - Ported from Project B
Strict Entry Rules:
1. MA5 > MA10 > MA20 (Trend)
2. Bias < 5% (Strict Entry)
3. Volume Shrink preferred
"""
import logging
import pandas as pd
from dataclasses import dataclass, field
from typing import Dict, Any, List
from enum import Enum

logger = logging.getLogger(__name__)

class TrendStatus(Enum):
    STRONG_BULL = "强势多头"
    BULL = "多头排列"
    WEAK_BULL = "弱势多头"
    CONSOLIDATION = "盘整"
    WEAK_BEAR = "弱势空头"
    BEAR = "空头排列"
    STRONG_BEAR = "强势空头"

class VolumeStatus(Enum):
    HEAVY_VOLUME_UP = "放量上涨"
    HEAVY_VOLUME_DOWN = "放量下跌"
    SHRINK_VOLUME_UP = "缩量上涨"
    SHRINK_VOLUME_DOWN = "缩量回调"
    NORMAL = "量能正常"

class BuySignal(Enum):
    STRONG_BUY = "强烈买入"
    BUY = "买入"
    HOLD = "持有"
    WAIT = "观望"
    SELL = "卖出"
    STRONG_SELL = "强烈卖出"

@dataclass
class TrendAnalysisResult:
    code: str
    trend_status: TrendStatus = TrendStatus.CONSOLIDATION
    ma_alignment: str = ""
    trend_strength: float = 0.0
    
    current_price: float = 0.0
    ma5: float = 0.0
    ma10: float = 0.0
    ma20: float = 0.0
    
    bias_ma5: float = 0.0
    
    volume_status: VolumeStatus = VolumeStatus.NORMAL
    volume_ratio_5d: float = 0.0
    
    buy_signal: BuySignal = BuySignal.WAIT
    signal_score: int = 0
    signal_reasons: List[str] = field(default_factory=list)
    risk_factors: List[str] = field(default_factory=list)

class StockTrendAnalyzer:
    BIAS_THRESHOLD = 5.0
    VOLUME_SHRINK_RATIO = 0.7
    VOLUME_HEAVY_RATIO = 1.5
    
    def analyze(self, df: pd.DataFrame, code: str) -> TrendAnalysisResult:
        result = TrendAnalysisResult(code=code)
        
        if df is None or len(df) < 20:
            return result
        
        latest = df.iloc[-1]
        result.current_price = float(latest['close'])
        
        # Ensure MAs exist (DataFetcherManager should provide them, but safe to calc)
        if 'ma5' not in df.columns:
            df['ma5'] = df['close'].rolling(5).mean()
        if 'ma10' not in df.columns:
            df['ma10'] = df['close'].rolling(10).mean()
        if 'ma20' not in df.columns:
            df['ma20'] = df['close'].rolling(20).mean()
            
        result.ma5 = float(latest['ma5'])
        result.ma10 = float(latest['ma10'])
        result.ma20 = float(latest['ma20'])
        
        self._analyze_trend(latest, result)
        self._calculate_bias(result)
        self._analyze_volume(df, result)
        self._generate_signal(result)
        
        return result

    def _analyze_trend(self, latest, result):
        ma5, ma10, ma20 = result.ma5, result.ma10, result.ma20
        if ma5 > ma10 > ma20:
            result.trend_status = TrendStatus.BULL
            result.trend_strength = 80
        elif ma5 > ma10:
            result.trend_status = TrendStatus.WEAK_BULL
            result.trend_strength = 60
        elif ma5 < ma10 < ma20:
            result.trend_status = TrendStatus.BEAR
            result.trend_strength = 20
        else:
            result.trend_status = TrendStatus.CONSOLIDATION
            result.trend_strength = 50
            
    def _calculate_bias(self, result):
        if result.ma5 > 0:
            result.bias_ma5 = (result.current_price - result.ma5) / result.ma5 * 100
            
    def _analyze_volume(self, df, result):
        if len(df) < 6: return
        latest = df.iloc[-1]
        vol_5d = df['volume'].iloc[-6:-1].mean()
        if vol_5d > 0:
            result.volume_ratio_5d = latest['volume'] / vol_5d
            
        price_change = latest.get('pct_chg', 0)
        
        if result.volume_ratio_5d >= self.VOLUME_HEAVY_RATIO:
            result.volume_status = VolumeStatus.HEAVY_VOLUME_UP if price_change > 0 else VolumeStatus.HEAVY_VOLUME_DOWN
        elif result.volume_ratio_5d <= self.VOLUME_SHRINK_RATIO:
            result.volume_status = VolumeStatus.SHRINK_VOLUME_UP if price_change > 0 else VolumeStatus.SHRINK_VOLUME_DOWN
            
    def _generate_signal(self, result):
        score = 0
        
        # Trend (40)
        if result.trend_status == TrendStatus.BULL: score += 40
        elif result.trend_status == TrendStatus.WEAK_BULL: score += 20
        
        # Bias (30)
        bias = result.bias_ma5
        if -2 < bias < 2: score += 30 # Sweet spot
        elif -5 < bias < 5: score += 20
        else: score += 0 # Too extended or too deep
        
        # Volume (20)
        if result.volume_status == VolumeStatus.SHRINK_VOLUME_DOWN: score += 20
        elif result.volume_status == VolumeStatus.SHRINK_VOLUME_UP: score += 10
        elif result.volume_status == VolumeStatus.HEAVY_VOLUME_UP: score += 15
        
        result.signal_score = score
        
        if score >= 80: result.buy_signal = BuySignal.STRONG_BUY
        elif score >= 60: result.buy_signal = BuySignal.BUY
        elif score >= 40: result.buy_signal = BuySignal.HOLD
        else: result.buy_signal = BuySignal.WAIT

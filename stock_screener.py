"""
Market Scanner Module - Filters stocks based on quantitative rules
"""
import akshare as ak
import pandas as pd
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

from data_fetcher import fetch_stock_data, calculate_start_date, fetch_sector_data, fetch_stock_news, load_sector_map

from data_fetcher_tx import get_market_snapshot_tencent
from indicator_calc import calculate_indicators, get_latest_metrics
from data_provider.base import DataFetcherManager
from strategies.trend_strategy import StockTrendAnalyzer
import database
import json
import os

# Initialize Data Manager
data_manager = DataFetcherManager()


def calculate_market_mood(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Calculate Market Sentiment based on full market snapshot
    """
    total = len(df)
    if total == 0:
        return {"mood": "未知", "index_change": 0}
        
    # Stats
    up_stocks = df[df['change_pct'] > 0]
    limit_up = len(df[df['change_pct'] > 9.0]) # Approx limit up
    limit_down = len(df[df['change_pct'] < -9.0])
    
    up_ratio = len(up_stocks) / total
    
    # Logic defining mood
    if up_ratio > 0.7:
        mood = "普涨 (高潮)"
    elif up_ratio > 0.55:
        mood = "偏暖 (多头)"
    elif up_ratio < 0.2:
        mood = "冰点 (杀跌)"
    elif limit_down > 20 and limit_down > limit_up:
         mood = "恐慌 (退潮)"
    else:
        mood = "分化 (震荡)"
        
    return {
        "market_mood": mood,
        "up_count": len(up_stocks),
        "down_count": len(df) - len(up_stocks),
        "limit_up": limit_up
    }

def get_selection_rules(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get selection rules, merging config.json with database overrides.
    Database params take precedence.
    """
    # Base rules from file
    rules = config.get('selection_rules', {}).copy()
    
    # Override with DB params if available
    try:
        strategy = database.get_strategy_by_slug('candidate_growth')
        if strategy and strategy.get('params'):
            db_params = strategy['params']
            print("⚙️ Loaded dynamic selection rules from database.")
            
            # Map DB string values back to correct types
            type_mapping = {
                'enabled': lambda x: x.lower() == 'true',
                'min_change': float,
                'max_change': float,
                'min_volume_ratio': float,
                'min_turnover': float,
                'max_turnover': float,
                'min_mcap_b': float,
                'max_mcap_b': float,
                'exclude_loss_making': lambda x: x.lower() == 'true',
                'exclude_startup_board': lambda x: x.lower() == 'true',
                'max_candidates_rough': int,
                'min_score': int,
                'max_final_candidates': int
            }
            
            for key, val_str in db_params.items():
                if key in type_mapping:
                    try:
                        rules[key] = type_mapping[key](str(val_str))
                    except ValueError:
                        print(f"⚠️ Failed to parse param {key}={val_str}, keeping default.")
                        
    except Exception as e:
        print(f"⚠️ Error loading DB rules: {e}")
        
    return rules

def check_market_risk() -> bool:
    """
    Check Market Environment (Shanghai Composite Index - 000001)
    Rule: If Index < MA20 AND Drop > 1%, Stop immediately.
    Returns: True if Market is Risky (Stop), False if Safe (Proceed).
    """
    period = 30
    start_date = calculate_start_date(lookback_days=period + 10)
    try:
        # Fetch Shanghai Composite (000001)
        # using is_index=True. Symbol '000001' for SH Index in akshare
        df = fetch_stock_data("000001", start_date, is_index=True)
        
        if df is None or len(df) < 20:
             print("⚠️ Insufficient market index data, skipping risk check.")
             return False
             
        # Calculate MA20
        df['ma20'] = df['close'].rolling(window=20).mean()
        
        # Calculate Change Pct
        df['change_pct'] = df['close'].pct_change() * 100
        
        # Check Last Row
        last = df.iloc[-1]
        
        # Log market status
        market_status = f"Market(000001): {last['close']:.2f}, MA20: {last['ma20']:.2f}, Chg: {last['change_pct']:.2f}%"
        print(f"🌍 {market_status}")
        
        # Risk Condition: Price < MA20 AND Change < -1.0% (Significant Drop/Breakdown)
        # Note: We use 'close' vs 'ma20'.
        if last['close'] < last['ma20'] and last['change_pct'] < -1.0:
            print("🛑 RISK ALERT: Market Risk Logic Triggered. Market below MA20 and dropping > 1%. Strategy Halted.")
            return True
        
        return False
        
    except Exception as e:
        print(f"⚠️ Market check error: {e}")
        return False

def get_rising_sectors() -> List[str]:
    """
    Get list of sectors with positive change today
    """
    print("🌍 Fetching sector data...")
    df = fetch_sector_data()
    if df is None or df.empty:
        return []
    
    # Filter sectors with change_pct > 0
    rising = df[df['涨跌幅'] > 0]
    return rising['板块名称'].tolist()

def get_market_snapshot() -> pd.DataFrame:
    """
    Get real-time snapshot of all A-share stocks
    """
    print("🌍 Fetching market snapshot... (This may take a moment)")
    
    # Priority: Try Tencent Interface First (More Stable)
    try:
        df = get_market_snapshot_tencent()
        if not df.empty:
            return df
        print("⚠️ Tencent fetch returned empty, falling back to EM...")
    except Exception as e:
        print(f"⚠️ Tencent fetch failed: {e}, falling back to EM...")

    # Fallback: AkShare EM Interface
    max_retries = 3
    df = None
    
    for attempt in range(max_retries):
        try:
            if attempt > 0:
                print(f"🔄 Retry attempt {attempt + 1}/{max_retries}...")
                
            # Fetch spot data for all A-shares
            df = ak.stock_zh_a_spot_em()
            break # Success, exit loop
            
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"⚠️ Market snapshot fetch failed: {e}. Retrying in 2s...")
                time.sleep(2)
            else:
                print(f"❌ Error fetching market snapshot: {e}")
                return pd.DataFrame()

    if df is None or df.empty:
        return pd.DataFrame()

    try:
        # Renaissance mapping for easier handling
        column_map = {
            '代码': 'symbol',
            '名称': 'name',
            '最新价': 'price',
            '涨跌幅': 'change_pct',
            '成交量': 'volume',
            '成交额': 'amount',
            '量比': 'volume_ratio',
            '换手率': 'turnover_rate',
            '市盈率-动态': 'pe_ttm',
            '流通市值': 'mcap_float',
            '所属板块': 'sector'
        }
        
        df = df.rename(columns=column_map)
        
        # Ensure numeric types
        numeric_cols = ['price', 'change_pct', 'volume_ratio', 'turnover_rate', 'pe_ttm', 'mcap_float']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
                
        return df
    except Exception as e:
        print(f"❌ Error processing market snapshot columns: {e}")
        return pd.DataFrame()

def run_rough_screen(df: pd.DataFrame, criteria: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Apply Step 1: Rough Screening based on basic metrics
    """
    print(f"\n🔍 Running Rough Screen on {len(df)} stocks...")
    
    # 0. Feature: Sector Beta Analysis (Optional but recommended)
    # Since checking every stock's sector is slow, we'll skip strict sector matching in Snapshot
    # Instead, we rely on the fact that strong stocks usually belong to strong sectors.
    # We will fetch sector data just to display market sentiment, or if we had sector mapping.
    # For now, we proceed with strict technical rough screen.
    
    # 0. Pre-calculate Sector Ranks & Stats (On FULL DataFrame)
    # Try to hydrate sector data if missing (e.g. when using Tencent source)
    if 'sector' not in df.columns:
        sector_map = load_sector_map()
        if sector_map:
            print(f"   🗺️ Hydrating sector info from map ({len(sector_map)} entries)...")
            # Map symbol -> sector
            df['sector'] = df['symbol'].map(sector_map)
        else:
            print("   ⚠️ No sector info available (Source missing & No local map). Skipping rank_in_sector.")

    # This ensures rank is accurate against all peers, not just filtered ones
    if 'sector' in df.columns and 'change_pct' in df.columns:
        print("   📊 Calculating sector ranks and stats...")
        # Rank: 1 is best (highest change_pct)
        # Handle NaN sectors
        df_clean = df.dropna(subset=['sector'])
        
        # Calculate on clean subset then join back?
        # Easier: calculate on full df, groupby handles NaNs (excludes them)
        df['rank_in_sector'] = df.groupby('sector')['change_pct'].rank(ascending=False, method='min')
        
        # Sector Change (Average of stocks in sector)
        # Map sector mean back to each row
        sector_means = df.groupby('sector')['change_pct'].transform('mean')
        df['sector_change'] = sector_means
    
    # 1. Price Range
    # Masking for efficiency
    mask = (df['price'] > 0)
    
    # 2. Change Pct (e.g., 2% to 8% - Avoid Limit Up)
    if 'min_change' in criteria:
        mask &= (df['change_pct'] >= criteria['min_change'])
    if 'max_change' in criteria:
        mask &= (df['change_pct'] <= criteria['max_change'])
        
    # 3. Volume Ratio (Activeness)
    if 'min_volume_ratio' in criteria:
        mask &= (df['volume_ratio'] >= criteria['min_volume_ratio'])
        
    # 4. Turnover Rate (Liquidity)
    if 'min_turnover' in criteria:
        mask &= (df['turnover_rate'] >= criteria['min_turnover'])
    if 'max_turnover' in criteria:
        mask &= (df['turnover_rate'] <= criteria['max_turnover'])
        
    # 5. Market Cap (Avoid too small or too huge) - Input usually in Billions
    if 'min_mcap_b' in criteria:
        mask &= (df['mcap_float'] >= criteria['min_mcap_b'] * 100000000)
    if 'max_mcap_b' in criteria:
        mask &= (df['mcap_float'] <= criteria['max_mcap_b'] * 100000000)
        
    # 6. PE validation (Avoid loss making info if needed)
    if criteria.get('exclude_loss_making', True):
        mask &= (df['pe_ttm'] > 0)
        
    # Exclude ST stocks (names containing ST)
    mask &= (~df['name'].str.contains('ST'))
    mask &= (~df['name'].str.contains('退'))
    
    # Exclude Beijing Stock Exchange (symbols starting with 8 or 4)
    # Filter Startup Board (30) if configured
    allowed_prefixes = ['00', '60']
    if not criteria.get('exclude_startup_board', False):
        allowed_prefixes.append('30')
        
    pattern = r'^(' + '|'.join(allowed_prefixes) + ')'
    mask &= (df['symbol'].astype(str).str.match(pattern))

    result_df = df[mask]
    
    # Sort by "Active Money" (Volume Ratio or Turnover), NOT just Price Change
    # This fixes "Crucial Fix #1: Avoid chasing fish tails"
    # Prioritize stocks with high relative volume (主力资金进场)
    if 'volume_ratio' in result_df.columns:
        # Sort by Volume Ratio desc, then by Change Pct desc
        result_df = result_df.sort_values(by=['volume_ratio', 'change_pct'], ascending=[False, False])
    else:
        result_df = result_df.sort_values(by='change_pct', ascending=False)
    
    candidate_limit = criteria.get('max_candidates_rough', 100)
    print(f"   Filtering top {candidate_limit} by Volume Ratio...")
    
    candidates = result_df.head(candidate_limit).to_dict('records')
    
    # Note on Sector Beta:
    # Accurate sector filtering requires mapping each stock to its sector, which isn't in the snapshot.
    # We will enforce sector beta logic in the Deep Screen or by fetching detailed info.
    # For now, the "Volume Ratio" sort + "2-8% Change" is a very strong filter itself.
    
    print(f"✅ Rough Screen passed: {len(candidates)} stocks")
    return candidates

def analyze_candidate(candidate: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Detailed technical analysis for a single candidate
    """
    symbol = candidate['symbol']
    
    # Fetch historical data
    # Use default lookback from config which is sufficient for all indicators
    start_date = calculate_start_date()
    # df = fetch_stock_data(symbol, start_date) # Deprecated
    try:
        df, _source = data_manager.get_daily_data(symbol, start_date=start_date)
    except Exception as e:
        print(f"   ⚠️ Failed to fetch data for {symbol}: {e}")
        return None
    
    if df is None or len(df) < 60:
        return None
        
    # Calculate indicators
    df = calculate_indicators(df)
    
    # Get latest metrics
    tech_data = get_latest_metrics(df)
    
    if not tech_data:
        return None
        
    # Merge basic info
    tech_data['symbol'] = symbol
    tech_data['name'] = candidate['name']

    # Merge rough screen metrics (turnover, pe, mcap)
    # Added: rank_in_sector, sector_change, market_mood data
    transfer_keys = [
        'turnover_rate', 'pe_ttm', 'mcap_float', 'volume_ratio',
        'rank_in_sector', 'sector_change', 'market_mood', 'market_status_data',
        'sector' # Ensure sector name is passed
    ]
    
    # Store critical metadata in a special dict to be embedded later
    tech_data['__metadata__'] = {}
    
    for key in transfer_keys:
        if key in candidate:
            tech_data[key] = candidate[key]
            tech_data['__metadata__'][key] = candidate[key]
            
    # Fetch News (Optimization: AI Prompting)
    # We'll attach news to the tech_data so LLM can read it
    tech_data['latest_news'] = fetch_stock_news(symbol)

    # === Integration: Trend Strategy Score ===
    try:
        trend_analyzer = StockTrendAnalyzer()
        trend_result = trend_analyzer.analyze(df, symbol)
        tech_data['trend_score'] = trend_result.signal_score
        tech_data['trend_signal'] = trend_result.buy_signal.value
        # Add to metadata for viewing
        tech_data['__metadata__']['trend_score'] = trend_result.signal_score
        tech_data['__metadata__']['trend_signal'] = trend_result.buy_signal.value
        tech_data['composite_score'] = (tech_data['composite_score'] + trend_result.signal_score) / 2 # Average them for now
    except Exception as e:
        print(f"   ⚠️ Trend Analysis failed: {e}")

    return tech_data

def run_deep_screen(candidates: List[Dict[str, Any]], config: Dict[str, Any], rules: Dict[str, Any] = None) -> List[Dict[str, Any]]:
    """
    Apply Step 2: Deep Technical Screening (Multi-threaded)
    """
    print(f"\n🔬 Running Deep Technical Analysis on {len(candidates)} candidates...")
    
    final_candidates = []
    # Use provided rules or fallback to config
    if rules is None:
        rules = config.get('selection_rules', {})
        
    min_score = rules.get('min_score', 70)
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_stock = {executor.submit(analyze_candidate, c, config): c for c in candidates}
        
        for future in as_completed(future_to_stock):
            stock = future_to_stock[future]
            try:
                metrics = future.result()
                if not metrics:
                    continue
                
                # --- Hard Rules ---
                # 1. Price above MA20 (Trend is King)
                if metrics['close'] <= metrics['ma20']:
                    continue
                    
                # 2. Composite Score
                if metrics['composite_score'] < min_score:
                    continue
                    
                final_candidates.append(metrics)
                print(f"  ✨ Found: {stock['name']} (Score: {metrics['composite_score']})")
                
            except Exception as e:
                print(f"  ❌ Error processing {stock['symbol']}: {e}")
                
    # Sort by Score
    final_candidates.sort(key=lambda x: x['composite_score'], reverse=True)
    
    return final_candidates[:config['selection_rules'].get('max_final_candidates', 5)]

def run_stock_selection(config: Dict[str, Any]):
    """
    Main entry point for stock selection
    """
    print("\n" + "="*60)
    print("🕵️‍♂️ AUTO-PICKER: Starting Market Scan")
    print("="*60)
    
    # 0. Get Criteria (Merge DB and Config)
    rules = get_selection_rules(config)
    
    if not rules.get('enabled', False):
        print("Stock selection is disabled in config/DB.")
        return []
        
    print(f"📋 Selection Criteria: Min Score > {rules.get('min_score')}, Max candidates: {rules.get('max_final_candidates')}")

    # 1. Market Environment Check (Risk Control)
    if check_market_risk():
        print("🛑 Force Stop triggered by Market Environment.")
        return []

    # 2. Fetch Snapshot
    snapshot_df = get_market_snapshot()
    if snapshot_df.empty:
        print("❌ Failed to get market data.")
        return []
        
    # 3. Calculate Market Mood (Global)
    mood_data = calculate_market_mood(snapshot_df)
    print(f"📊 Market Mood: {mood_data['market_mood']} (Up: {mood_data['up_count']}, LimitUp: {mood_data['limit_up']})")
    
    # 4. Rough Screen
    rough_candidates = run_rough_screen(snapshot_df, rules)
    if not rough_candidates:
        print("❌ No stocks matched rough criteria.")
        return []
        
    # Inject Market Mood into candidates
    # Also inject Index Info check (we do it in check_market_risk but let's grab it fresh or use proxy)
    # use check_market_risk's side effect? No.
    # We will assume index info comes from get_market_snapshot if it included index, but it doesn't.
    # We'll rely on mood_data and maybe fetch index separately if needed.
    # For now, put mood into each candidate so analyze_candidate can carry it.
    for cand in rough_candidates:
        cand['market_mood'] = mood_data['market_mood']
        cand['market_status_data'] = mood_data
        
    # 5. Deep Screen
    final_candidates = run_deep_screen(rough_candidates, config, rules)
    
    print(f"\n🎉 Selection Complete! Found {len(final_candidates)} high-quality targets.")
    return final_candidates
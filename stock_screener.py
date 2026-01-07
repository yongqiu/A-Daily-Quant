"""
Market Scanner Module - Filters stocks based on quantitative rules
"""
import akshare as ak
import pandas as pd
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

from data_fetcher import fetch_stock_data, calculate_start_date
from indicator_calc import calculate_indicators, get_latest_metrics

def get_market_snapshot() -> pd.DataFrame:
    """
    Get real-time snapshot of all A-share stocks
    """
    print("🌍 Fetching market snapshot... (This may take a moment)")
    try:
        # Fetch spot data for all A-shares
        df = ak.stock_zh_a_spot_em()
        
        # Renaissance mapping for easier handling
        # Columns usually: 序号, 代码, 名称, 最新价, 涨跌幅, 涨跌额, 成交量, 成交额, 振幅, 最高, 最低, 今开, 昨收, 量比, 换手率, 市盈率-动态, 市净率
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
            '流通市值': 'mcap_float'
        }
        df = df.rename(columns=column_map)
        
        # Ensure numeric types
        numeric_cols = ['price', 'change_pct', 'volume_ratio', 'turnover_rate', 'pe_ttm', 'mcap_float']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
                
        return df
    except Exception as e:
        print(f"❌ Error fetching market snapshot: {e}")
        return pd.DataFrame()

def run_rough_screen(df: pd.DataFrame, criteria: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Apply Step 1: Rough Screening based on basic metrics
    """
    print(f"\n🔍 Running Rough Screen on {len(df)} stocks...")
    
    # 1. Price Range
    # Masking for efficiency
    mask = (df['price'] > 0)
    
    # 2. Change Pct (e.g., 2% to 9%)
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
    
    # Exclude Beijing Stock Exchange (symbols starting with 8 or 4) if desired
    # Usually standard strategy focuses on 60x and 00x
    mask &= (df['symbol'].astype(str).str.match(r'^(00|60|30)'))

    result_df = df[mask]
    
    # Sort by stronger metrics (e.g., volume ratio or change pct)
    result_df = result_df.sort_values(by='change_pct', ascending=False)
    
    candidates = result_df.head(criteria.get('max_candidates_rough', 50)).to_dict('records')
    print(f"✅ Rough Screen passed: {len(candidates)} stocks")
    return candidates

def analyze_candidate(candidate: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Detailed technical analysis for a single candidate
    """
    symbol = candidate['symbol']
    
    # Fetch historical data
    start_date = calculate_start_date(lookback_days=120)
    df = fetch_stock_data(symbol, start_date)
    
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
    
    return tech_data

def run_deep_screen(candidates: List[Dict[str, Any]], config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Apply Step 2: Deep Technical Screening (Multi-threaded)
    """
    print(f"\n🔬 Running Deep Technical Analysis on {len(candidates)} candidates...")
    
    final_candidates = []
    min_score = config['selection_rules'].get('min_score', 70)
    
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
    
    # 0. Get Criteria
    rules = config.get('selection_rules', {})
    if not rules.get('enabled', False):
        print("Stock selection is disabled in config.")
        return []
        
    # 1. Fetch Snapshot
    snapshot_df = get_market_snapshot()
    if snapshot_df.empty:
        print("❌ Failed to get market data.")
        return []
        
    # 2. Rough Screen
    rough_candidates = run_rough_screen(snapshot_df, rules)
    if not rough_candidates:
        print("❌ No stocks matched rough criteria.")
        return []
        
    # 3. Deep Screen
    final_candidates = run_deep_screen(rough_candidates, config)
    
    print(f"\n🎉 Selection Complete! Found {len(final_candidates)} high-quality targets.")
    return final_candidates
"""
Tushare Data Fetcher implementation
"""
import tushare as ts
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import json
import os

# Tushare Pro API client
_pro_client = None

def get_pro_client():
    """Lazy load Tushare Pro client"""
    global _pro_client
    if _pro_client is None:
        try:
            # Load config to get token
            config_path = os.path.join(os.path.dirname(__file__), 'config.json')
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    token = config.get('data_source', {}).get('tushare_token')
                    if token and token != "YOUR_TUSHARE_TOKEN_HERE":
                        ts.set_token(token)
                        _pro_client = ts.pro_api()
                        print("✅ Tushare Pro client initialized")
                    else:
                        print("⚠️ Tushare token not configured")
        except Exception as e:
            print(f"❌ Error initializing Tushare client: {e}")
    return _pro_client

def fetch_stock_data_ts(symbol: str, start_date: str, end_date: str = None, adjust: str = 'qfq', period: str = 'daily') -> Optional[pd.DataFrame]:
    """
    Fetch historical stock data from Tushare
    
    Args:
        symbol: Stock code (e.g., '600519')
        start_date: Start date in 'YYYYMMDD' format
        end_date: End date in 'YYYYMMDD' format (optional)
        adjust: 'qfq' (default), 'hfq', or None
        period: 'daily', 'weekly', 'monthly'
    """
    pro = get_pro_client()
    if pro is None:
        return None
        
    try:
        # Tushare requires symbol format like '600519.SH'
        ts_symbol = _format_symbol(symbol)
        
        if not end_date:
            end_date = datetime.now().strftime('%Y%m%d')
            
        # Map adjust parameter
        adj = adjust if adjust else None

        # Always fetch DAILY data first to ensure reliability (Tushare pro_bar has bugs with weekly/monthly for funds)
        # freq='D' is much more stable. We will resample if needed.
        
        # Determine asset type for optimization
        # 51xxxx, 159xxx are usually Funds (ETF)
        asset_type = 'E' # Default Equity
        if symbol.startswith('5') or symbol.startswith('1'):
             # Try determining if it's a fund.
             # However, pro_bar usually auto-detects.
             pass

        # Use ts.pro_bar for easier复权 handling
        # Always use freq='D' to avoid "local variable 'data' referenced before assignment" error in tushare
        df = ts.pro_bar(
            ts_code=ts_symbol,
            adj=adj,
            freq='D',
            start_date=start_date,
            end_date=end_date
        )
        
        # Retry for Funds if empty and looks like a fund code
        if (df is None or df.empty) and (symbol.startswith('51') or symbol.startswith('159')):
             # print(f"🔄 Retrying {symbol} as Fund(FD)...")
             df = ts.pro_bar(
                ts_code=ts_symbol,
                adj=adj,
                freq='D',
                asset='FD',
                start_date=start_date,
                end_date=end_date
            )
        
        if df is None or df.empty:
            return None
            
        # Tushare returns: ts_code, trade_date, open, high, low, close, pre_close, change, pct_chg, vol, amount
        # Map to system standard: date, open, close, high, low, volume, amount
        
        df = df.rename(columns={
            'trade_date': 'date',
            'vol': 'volume'
        })
        
        # Ensure numeric types
        numeric_cols = ['open', 'high', 'low', 'close', 'volume', 'amount']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        df['date'] = pd.to_datetime(df['date'])
        
        # Filter 0 close
        if 'close' in df.columns:
            df = df[df['close'] > 0]
            
        df = df.sort_values('date').reset_index(drop=True)
        
        # Manual Resampling if Weekly or Monthly is requested
        if period != 'daily' and not df.empty:
             # Set date as index for resampling
             df.set_index('date', inplace=True)
             
             rule = 'W-FRI' if period == 'weekly' else 'M'
             
             # Resample logic
             resampled = df.resample(rule).agg({
                 'open': 'first',
                 'high': 'max',
                 'low': 'min',
                 'close': 'last',
                 'volume': 'sum',
                 'amount': 'sum'
             })
             
             # Remove rows with NaN (incomplete periods might generate them if not careful, but usually ok)
             resampled = resampled.dropna()
             
             # Reset index to make date a column again
             resampled = resampled.reset_index()
             
             # Filter out future dates (resampling might create a bin edge in the future)
             # usually W-FRI aligns to end of week.
             
             df = resampled

        # Keep consistent columns
        required_cols = ['date', 'open', 'close', 'high', 'low', 'volume', 'amount']
        # Add missing columns with 0 if needed, or select existing
        final_df = df[[c for c in required_cols if c in df.columns]].copy()
        
        print(f"✅ Fetched {len(final_df)} records ({period}) from Tushare for {symbol}")
        return final_df
        
    except Exception as e:
        print(f"❌ Error fetching Tushare data for {symbol}: {e}")
        return None

def fetch_sector_map() -> Dict[str, str]:
    """
    Fetch comprehensive sector map (symbol -> industry) from Tushare
    """
    pro = get_pro_client()
    if pro is None:
        return {}
        
    try:
        print("🌍 Fetching authoritative sector data from Tushare...")
        # L = Listed, D = Delisted, P = Paused. We want L and maybe P.
        # Fetching all listed stocks
        df = pro.stock_basic(exchange='', list_status='L', fields='symbol,industry')
        
        if df is None or df.empty:
            print("⚠️ Tushare returned empty stock list.")
            return {}
            
        # Create map
        sector_map = {}
        for _, row in df.iterrows():
            symbol = str(row['symbol'])
            industry = row['industry']
            if industry:
                sector_map[symbol] = industry
                
        print(f"✅ Successfully fetched sector info for {len(sector_map)} stocks")
        return sector_map
        
    except Exception as e:
        print(f"❌ Error fetching sector map: {e}")
        return {}

def fetch_stock_info_ts(symbol: str) -> Optional[Dict[str, Any]]:
    """
    Fetch real-time (or latest) stock info from Tushare
    """
    try:
        # Use old interface for realtime quotes (free and fast)
        # It returns a dataframe
        df = ts.get_realtime_quotes(symbol)
        
        if df is None or df.empty:
            return None
            
        row = df.iloc[0]
        
        # Mapping
        # name, price, bid, ask, volume, amount, time...
        result = {
            'symbol': symbol,
            'name': row['name'],
            'price': float(row['price']),
            # Calculate change pct manually as it might not be directly provided in clean format
            # or pre_close is needed
            'volume': int(float(row['volume'])), # returned as string usually
            'amount': float(row['amount'])
        }
        
        # Calculate change if pre_close available
        pre_close = float(row['pre_close'])
        if pre_close > 0:
            change_pct = (result['price'] - pre_close) / pre_close * 100
            result['change_pct'] = round(change_pct, 2)
        else:
            result['change_pct'] = 0.0
            
        return result
        
    except Exception as e:
        print(f"❌ Error fetching Tushare stock info for {symbol}: {e}")
        return None

def _format_symbol(symbol: str) -> str:
    """
    Convert '600519' to '600519.SH'
    """
    if '.' in symbol:
        return symbol
        
    if symbol.startswith('6'):
        return f"{symbol}.SH"
    elif symbol.startswith('0') or symbol.startswith('3'):
        return f"{symbol}.SZ"
    elif symbol.startswith('8') or symbol.startswith('4'):
        return f"{symbol}.BJ"
    elif symbol.startswith('5') or symbol.startswith('1'):
         # ETF: need to check if SH or SZ. 
         # 51xxxx/56xxxx/58xxxx is usually SH, 159xxx is SZ
         if symbol.startswith('159'):
             return f"{symbol}.SZ"
         return f"{symbol}.SH"
         
    return symbol
"""
Data Fetching Module - Handles AkShare interactions for A-Share market data
"""
import akshare as ak
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional
import requests


def fetch_crypto_data(symbol: str, days: int = 120) -> Optional[pd.DataFrame]:
    """
    Fetch Crypto history data from Binance.
    symbol: e.g. "BTC" (automatically adds USDT) or "BTCUSDT"
    """
    if not symbol.endswith("USDT"):
        symbol = f"{symbol}USDT"
    
    url = "https://api.binance.com/api/v3/klines"
    # Limit calculation: days
    params = {
        "symbol": symbol.upper(),
        "interval": "1d",
        "limit": days
    }
    
    try:
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code != 200:
            print(f"❌ Binance Error: {resp.status_code}")
            return None
            
        data = resp.json()
        # Binance Klines: [Open Time, Open, High, Low, Close, Volume, ...]
        df = pd.DataFrame(data, columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_asset_volume", "trades", "taker_buy_base", "taker_buy_quote", "ignore"
        ])
        
        df = df[["open_time", "open", "high", "low", "close", "volume"]]
        df["date"] = pd.to_datetime(df["open_time"], unit='ms')
        
        # Numeric conversion
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col], errors='coerce')
            
        df = df[["date", "open", "close", "high", "low", "volume"]]
        print(f"✅ Fetched {len(df)} days for Crypto {symbol}")
        return df
        
    except Exception as e:
        print(f"❌ Error fetching crypto {symbol}: {e}")
        return None


def fetch_future_data(symbol: str, start_date: str) -> Optional[pd.DataFrame]:
    """
    Fetch Futures history data from AkShare (Sina Source).
    symbol: e.g. "au0" (Gold Main)
    """
    try:
        # Assuming Domestic Futures Main Contract
        df = ak.futures_main_sina(symbol=symbol)
        
        if df is None or df.empty:
            return None
            
        # Standardize Columns
        # AkShare Sina Futures columns often: 日期, 开盘价, 最高价, ...
        rename_map = {
            '日期': 'date',
            '开盘价': 'open',
            '最高价': 'high',
            '最低价': 'low',
            '收盘价': 'close',
            '成交量': 'volume',
            '持仓量': 'open_interest'
        }
        df = df.rename(columns=rename_map)
        
        # Filter by date
        df['date'] = pd.to_datetime(df['date'])
        start_dt = pd.to_datetime(start_date)
        df = df[df['date'] >= start_dt].copy()
        
        df = df.sort_values('date').reset_index(drop=True)
        
        # Ensure float types
        for col in ['open', 'high', 'low', 'close', 'volume']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        print(f"✅ Fetched {len(df)} days for Future {symbol}")
        return df
        
    except Exception as e:
        print(f"❌ Error fetching future {symbol}: {e}")
        return None


def fetch_stock_data(symbol: str, start_date: str, is_index: bool = False) -> Optional[pd.DataFrame]:
    """
    Fetch historical stock data from AkShare
    
    Args:
        symbol: Stock code (e.g., '600519') or index code (e.g., '000300')
        start_date: Start date in 'YYYYMMDD' format
        is_index: True if fetching index data, False for individual stocks
    
    Returns:
        DataFrame with columns: date, open, close, high, low, volume
        Returns None if fetch fails
    """
    try:
        if is_index:
            # Fetch index data (like 沪深300)
            df = ak.index_zh_a_hist(symbol=symbol, period="daily", start_date=start_date)
        elif symbol.startswith('51') or symbol.startswith('159'):
            # ETF codes (51开头或159开头) use ETF-specific interface
            df = ak.fund_etf_hist_em(symbol=symbol, period="daily", start_date=start_date, end_date=datetime.now().strftime('%Y%m%d'))
        else:
            # Fetch individual stock data with forward adjustment (qfq)
            df = ak.stock_zh_a_hist(symbol=symbol, period="daily", start_date=start_date, adjust="qfq")
        
        if df is None or df.empty:
            print(f"⚠️  No data returned for {symbol}")
            return None
        
        # Standardize column names
        df = df.rename(columns={
            '日期': 'date',
            '开盘': 'open',
            '收盘': 'close',
            '最高': 'high',
            '最低': 'low',
            '成交量': 'volume',
            '成交额': 'amount'
        })
        
        # Ensure date is datetime type
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date').reset_index(drop=True)
        
        print(f"✅ Fetched {len(df)} days of data for {symbol}")
        return df
        
    except Exception as e:
        print(f"❌ Error fetching data for {symbol}: {str(e)}")
        return None


def fetch_data_dispatcher(symbol: str, asset_type: str, start_date: str) -> Optional[pd.DataFrame]:
    """Dispatch fetch request based on asset type"""
    if asset_type == 'crypto':
        # approximate days from start_date
        return fetch_crypto_data(symbol, days=120)
    elif asset_type == 'future':
        return fetch_future_data(symbol, start_date)
    else:
        # Default to stock/etf
        # is_index check: if symbol starts with letters (like sh000001) or specific config
        # For simplicity, if passed here, assume standard stock/ETF unless index specified elsewhere
        # If 'sh000001', it's index
        is_index = symbol.lower().startswith('sh') and len(symbol) > 6
        return fetch_stock_data(symbol, start_date, is_index=is_index)


def get_latest_trading_date() -> str:
    """
    Get the latest trading date (today or last trading day)
    Returns date in 'YYYYMMDD' format
    """
    today = datetime.now()
    # Go back up to 7 days to find a trading day
    for i in range(7):
        check_date = today - timedelta(days=i)
        return check_date.strftime('%Y%m%d')
    return today.strftime('%Y%m%d')


def calculate_start_date(lookback_days: int = 120) -> str:
    """
    Calculate start date for data fetching
    
    Args:
        lookback_days: Number of days to look back (default 120 for MA60 calculation)
    
    Returns:
        Start date in 'YYYYMMDD' format
    """
    start = datetime.now() - timedelta(days=lookback_days + 30)  # Extra buffer for weekends
    return start.strftime('%Y%m%d')

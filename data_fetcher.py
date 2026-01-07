"""
Data Fetching Module - Handles AkShare interactions for A-Share market data
"""
import akshare as ak
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional


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

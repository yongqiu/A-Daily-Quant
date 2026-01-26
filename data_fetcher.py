"""
Data Fetching Module - Handles AkShare interactions for A-Share market data
"""
import akshare as ak
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import requests
from functools import lru_cache
import time

# Stock info cache: {symbol: (data, timestamp)}
_stock_info_cache: Dict[str, tuple] = {}
_CACHE_TTL_SECONDS = 300  # 5 minutes cache
_last_cache_cleanup_time = time.time()
_CACHE_CLEANUP_INTERVAL = 600  # Clean cache every 10 minutes


def _cleanup_expired_cache():
    """Clean expired cache entries to avoid memory leak"""
    global _last_cache_cleanup_time

    current_time = time.time()

    # Only cleanup if enough time has passed
    if current_time - _last_cache_cleanup_time < _CACHE_CLEANUP_INTERVAL:
        return

    # Find and remove expired entries
    expired_symbols = [
        symbol for symbol, (_, cached_time) in _stock_info_cache.items()
        if current_time - cached_time >= _CACHE_TTL_SECONDS
    ]

    for symbol in expired_symbols:
        del _stock_info_cache[symbol]

    _last_cache_cleanup_time = current_time

    if expired_symbols:
        print(f"🧹 Cache cleanup: removed {len(expired_symbols)} expired entries, {len(_stock_info_cache)} entries remaining")


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


def fetch_stock_data_tx_fallback(symbol: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
    """
    Try fetching from Tencent (TX) as primary source for A-share stocks.
    TX requires prefix (sz/sh).
    """
    if symbol.startswith('6'):
        tx_symbol = f"sh{symbol}"
    elif symbol.startswith('0') or symbol.startswith('3'):
        tx_symbol = f"sz{symbol}"
    elif symbol.startswith('4') or symbol.startswith('8'):
        tx_symbol = f"bj{symbol}"
    else:
        return None # Unsure how to map, fallback to EM
        
    try:
        # adjust='qfq' is supported by akshare for tx
        df = ak.stock_zh_a_hist_tx(symbol=tx_symbol, start_date=start_date, end_date=end_date, adjust="qfq")
        if df is not None and not df.empty:
            # TX returns: date, open, close, high, low, amount(actually volume in hands)
            # We need to map 'amount' -> 'volume'
            # And potentially approximate 'amount'(money) if needed
            df = df.rename(columns={'amount': 'volume'})
            
            # Approximate Turnover Amount: Close * Volume * 100 (assuming 1 hand = 100 shares)
            # This is rough but sufficient for volume ratio calc if money amount is not critical
            # Most indicators use Volume, not Money Amount.
            df['amount'] = df['close'] * df['volume'] * 100
            
            # Ensure columns exist
            for col in ['date', 'open', 'close', 'high', 'low', 'volume', 'amount']:
                if col not in df.columns:
                    # 'date' might be index or named differently?
                    # Verified in test: columns are ['date', 'open', 'close', 'high', 'low', 'amount']
                    pass
            
            # Filter 0s
            if 'close' in df.columns:
                 df = df[df['close'] > 0]
                 
            return df
    except Exception as e:
        # Quiet fail to fallback
        return None
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
    max_retries = 3
    base_delay = 2
    
    # Determine the appropriate end_date
    now = datetime.now()
    # If before 09:15 (pre-open call auction), use yesterday as end_date
    # to avoid fetching potential phantom candles or "today's" data which isn't valid yet.
    if now.time() < datetime.strptime("09:15", "%H:%M").time():
        end_date = (now - timedelta(days=1)).strftime('%Y%m%d')
    else:
        end_date = now.strftime('%Y%m%d')

    for attempt in range(max_retries):
        try:
            df = None
            
            # 1. Special Handling for Stocks (Dual Source)
            if not is_index and not (symbol.startswith('51') or symbol.startswith('159')):
                # Try Tencent First (Stable)
                df = fetch_stock_data_tx_fallback(symbol, start_date, end_date)
                if df is not None:
                     pass # Got it from TX
                else:
                     # Fallback to EM
                     # Only pass end_date if function signature supports it.
                     # Standard ak.stock_zh_a_hist accepts end_date
                     df = ak.stock_zh_a_hist(symbol=symbol, period="daily", start_date=start_date, end_date=end_date, adjust="qfq")

            elif is_index:
                # Fetch index data (like 沪深300)
                df = ak.index_zh_a_hist(symbol=symbol, period="daily", start_date=start_date, end_date=end_date)
            elif symbol.startswith('51') or symbol.startswith('159'):
                # ETF codes (51开头或159开头) use ETF-specific interface
                # Wait end_date slightly? No, em interface handles it.
                df = ak.fund_etf_hist_em(symbol=symbol, period="daily", start_date=start_date, end_date=end_date)
            
            if df is None or df.empty:
                # Sometimes API returns empty for valid stocks if network glitches or start_date issue
                # But usually it's just empty. We don't retry on empty unless we suspect connection.
                # However, connection error usually raises Exception.
                print(f"⚠️  No data returned for {symbol} (Attempt {attempt+1})")
                if attempt < max_retries - 1:
                     time.sleep(base_delay * (attempt + 1))
                     continue
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
            
            # Filter out invalid rows where close price is 0 (e.g. data errors or incomplete day)
            if 'close' in df.columns:
                df = df[df['close'] > 0]
                
            df = df.sort_values('date').reset_index(drop=True)
            
            print(f"✅ Fetched {len(df)} days of data for {symbol}")
            return df
            
        except Exception as e:
            error_str = str(e)
            # Check for connection-related errors to retry
            is_conn_error = 'Connection' in error_str or 'RemoteDisconnected' in error_str or 'timeout' in error_str.lower()
            
            if is_conn_error and attempt < max_retries - 1:
                wait_time = base_delay * (2 ** attempt) # Exponential backoff: 2s, 4s, 8s
                print(f"⚠️ Connection error for {symbol}: {e}. Retrying in {wait_time}s...")
                time.sleep(wait_time)
                continue
            
            if attempt == max_retries - 1:
                print(f"❌ Error fetching data for {symbol}: {str(e)}")
                return None
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

def fetch_sector_data() -> Optional[pd.DataFrame]:
    """
    Fetch Today's Sector (Industry) Performance from EastMoney
    Returns: DataFrame with ['板块名称', '涨跌幅', '领涨股票']
    """
    try:
        # Industry Boards
        df_industry = ak.stock_board_industry_name_em()
        # Concept Boards (Optional, maybe too noisy)
        # df_concept = ak.stock_board_concept_name_em()
        
        if df_industry is None or df_industry.empty:
            return None
            
        print(f"✅ Fetched {len(df_industry)} industry sectors.")
        return df_industry
    except Exception as e:
        print(f"❌ Error fetching sector data: {str(e)}")
        return None

def fetch_stock_news(symbol: str) -> str:
    """
    Fetch latest news for a specific stock (Top 3 items)
    """
    try:
        news_df = ak.stock_news_em(symbol=symbol)
        if news_df is None or news_df.empty:
            return "暂无相关新闻"
            
        # Get top 3 news titles
        latest_news = news_df.head(3)
        news_list = []
        for _, row in latest_news.iterrows():
            title = row.get('新闻标题', '')
            time_str = row.get('发布时间', '')
            if title:
                news_list.append(f"- {time_str}: {title}")
                
        return "\n".join(news_list)
    except Exception as e:
        print(f"⚠️ Error fetching news for {symbol}: {e}")
        return "新闻获取失败"


def fetch_stock_info(symbol: str) -> Optional[Dict[str, Any]]:
    """
    Fetch stock basic information by symbol
    Returns dict with keys: name, price, change_pct, etc.

    Optimized version: Uses individual stock API with caching
    """
    # Trigger periodic cache cleanup
    _cleanup_expired_cache()

    # Check cache first
    current_time = time.time()
    if symbol in _stock_info_cache:
        cached_data, cached_time = _stock_info_cache[symbol]
        if current_time - cached_time < _CACHE_TTL_SECONDS:
            print(f"✅ Using cached data for {symbol} (age: {int(current_time - cached_time)}s)")
            return cached_data

    try:
        # Method 1: Try to get individual stock/ETF realtime quote (much faster)
        # Determine if it's an ETF based on code pattern
        is_etf = symbol.startswith('51') or symbol.startswith('159') or symbol.startswith('50')

        try:
            # Get latest day's data
            if is_etf:
                # Use ETF-specific interface
                df = ak.fund_etf_hist_em(
                    symbol=symbol,
                    period="daily",
                    start_date=(datetime.now() - timedelta(days=5)).strftime('%Y%m%d'),
                    end_date=datetime.now().strftime('%Y%m%d')
                )
            else:
                # Use stock interface
                df = ak.stock_zh_a_hist(
                    symbol=symbol,
                    period="daily",
                    start_date=(datetime.now() - timedelta(days=5)).strftime('%Y%m%d'),
                    adjust=""
                )

            if df is not None and not df.empty:
                latest = df.iloc[-1]

                # Get stock/ETF name from basic info
                stock_name = symbol  # Default to symbol if name fetch fails
                try:
                    if is_etf:
                        # For ETF, try to get name from the historical data first (faster)
                        # Some ETF hist data might contain name in metadata
                        # If not available, user can manually input the name
                        # We skip the full ETF spot query to avoid slowdown
                        stock_name = f"ETF-{symbol}"  # Placeholder, user can edit later
                    else:
                        # Get stock name from individual info
                        info_df = ak.stock_individual_info_em(symbol=symbol)
                        if info_df is not None and not info_df.empty:
                            name_row = info_df[info_df['item'] == '股票简称']
                            stock_name = name_row['value'].iloc[0] if not name_row.empty else symbol
                except Exception as e:
                    print(f"⚠️ Could not fetch name for {symbol}: {e}")

                # Calculate change_pct from latest data
                close_price = float(latest.get('收盘', 0))
                open_price = float(latest.get('开盘', 0))

                # Approximate change_pct (ideally need previous close)
                if len(df) > 1:
                    prev_close = float(df.iloc[-2].get('收盘', close_price))
                    change_pct = ((close_price - prev_close) / prev_close * 100) if prev_close > 0 else 0
                else:
                    change_pct = ((close_price - open_price) / open_price * 100) if open_price > 0 else 0

                result = {
                    'symbol': symbol,
                    'name': stock_name,
                    'price': close_price,
                    'change_pct': round(change_pct, 2),
                    'volume': int(latest.get('成交量', 0)),
                    'amount': float(latest.get('成交额', 0))
                }

                # Cache the result
                _stock_info_cache[symbol] = (result, current_time)
                print(f"✅ Fetched and cached {'ETF' if is_etf else 'stock'} info for {symbol}")
                return result
            else:
                # Empty dataframe means stock doesn't exist - don't fallback to full market query
                print(f"⚠️ {'ETF' if is_etf else 'Stock'} {symbol} not found (empty data returned)")
                return None

        except Exception as e:
            # Check if it's a "stock not found" type error
            error_msg = str(e).lower()
            if any(keyword in error_msg for keyword in ['不存在', 'not found', 'empty', '无数据', 'no data']):
                print(f"⚠️ Stock {symbol} does not exist: {e}")
                return None

            print(f"⚠️ Fast fetch failed for {symbol}, fallback to full market data: {e}")

        # Method 2: Fallback to full market data (slower but more reliable)
        # Only used when fast method fails due to network/API issues, not when stock doesn't exist
        print(f"🔄 Using fallback method (full market query) for {symbol}...")
        df = ak.stock_zh_a_spot_em()

        if df is None or df.empty:
            print(f"⚠️ No stock data returned")
            return None

        # Try to find the stock by symbol
        stock_row = df[df['代码'] == symbol]

        if stock_row.empty:
            print(f"⚠️ Stock {symbol} not found in real-time data")
            return None

        stock_info = stock_row.iloc[0]

        result = {
            'symbol': symbol,
            'name': stock_info.get('名称', ''),
            'price': float(stock_info.get('最新价', 0)) if pd.notna(stock_info.get('最新价')) else 0,
            'change_pct': float(stock_info.get('涨跌幅', 0)) if pd.notna(stock_info.get('涨跌幅')) else 0,
            'volume': int(stock_info.get('成交量', 0)) if pd.notna(stock_info.get('成交量')) else 0,
            'amount': float(stock_info.get('成交额', 0)) if pd.notna(stock_info.get('成交额')) else 0
        }

        # Cache the result
        _stock_info_cache[symbol] = (result, current_time)
        return result

    except Exception as e:
        print(f"❌ Error fetching stock info for {symbol}: {e}")
        return None

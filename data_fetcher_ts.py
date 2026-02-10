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

# --- Monkeypatch for Pandas > 2.0 Compatibility (Fix Tushare fillna error) ---
try:
    from pandas.core.generic import NDFrame
    
    _original_fillna = NDFrame.fillna
    
    def _patched_fillna(self, value=None, method=None, axis=None, inplace=False, limit=None, downcast=None):
        if method is not None:
            if method in ['ffill', 'pad']:
                return self.ffill(axis=axis, inplace=inplace, limit=limit)
            elif method in ['bfill', 'backfill']:
                return self.bfill(axis=axis, inplace=inplace, limit=limit)
        
        # Check if _original_fillna supports downcast to be safe, but usually just passing it if provided is fine
        # unless it was removed there too. For now, assume failures happen in ffill/bfill as reported.
        kwargs = {}
        if downcast is not None:
            kwargs['downcast'] = downcast
            
        return _original_fillna(self, value=value, axis=axis, inplace=inplace, limit=limit, **kwargs)

    # Apply patch if pandas version is new enough to cause issues
    if pd.__version__ >= '2.0.0':
         print("🔧 Applying pandas.fillna monkeypatch for Tushare compatibility...")
         NDFrame.fillna = _patched_fillna
except Exception as e:
    print(f"⚠️ Failed to apply pandas monkeypatch: {e}")
# ---------------------------------------------------------------------------

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
    调用的tushare的pro_bar接口，获取 open、high、low、close指标数据
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
            'vol': 'volume',
            'pct_chg': 'change_pct'
        })
        
        # Ensure numeric types
        numeric_cols = ['open', 'high', 'low', 'close', 'volume', 'amount', 'change_pct']
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
        required_cols = ['date', 'open', 'close', 'high', 'low', 'volume', 'amount', 'change_pct']
        # Add missing columns with 0 if needed, or select existing
        final_df = df[[c for c in required_cols if c in df.columns]].copy()
        
        print(f"✅ Fetched {len(final_df)} records ({period}) from Tushare for {symbol}")
        return final_df
        
    except Exception as e:
        print(f"❌ Error fetching Tushare data for {symbol}: {e}")
        return None

def fetch_daily_basic_ts(symbol: str, date: str = None) -> Optional[Dict[str, Any]]:
    """
    Fetch daily basic indicators from Tushare (daily_basic).
    Contains: turnover_rate, volume_ratio, pe, pb, float_share, etc.
    
    Args:
        symbol: Stock code (e.g., '600519')
        date: Specific date in 'YYYYMMDD' format. If None, fetches latest available.
        
    Returns:
        Dict with keys: turnover_rate, volume_ratio, pe, pb, total_mv, etc.
    """
    pro = get_pro_client()
    if pro is None:
        return None
        
    try:
        ts_symbol = _format_symbol(symbol)
        
        # If date is not provided, try to fetch a range of recent days to find the latest
        start_date = date
        end_date = date
        
        if not date:
            end_date = datetime.now().strftime('%Y%m%d')
            start_date = (datetime.now() - timedelta(days=10)).strftime('%Y%m%d')

        # Fields to fetch
        fields = 'ts_code,trade_date,turnover_rate,volume_ratio,pe,pb,total_mv,circ_mv'
        
        df = pro.daily_basic(
            ts_code=ts_symbol, 
            start_date=start_date, 
            end_date=end_date, 
            fields=fields
        )
        
        if df is None or df.empty:
            return None
            
        # Get the latest record (sort by date desc just in case)
        df = df.sort_values('trade_date', ascending=False)
        row = df.iloc[0]
        
        # 辅助函数：安全转换为 float，处理 NaN 值
        def safe_float(value, default=0.0):
            """将值安全转换为 float，NaN 和 None 都转换为默认值"""
            if pd.isna(value):  # 检测 NaN 和 None
                return default
            try:
                return float(value)
            except (ValueError, TypeError):
                return default
        
        return {
            'symbol': symbol,
            'date': row['trade_date'],
            'turnover_rate': safe_float(row['turnover_rate']),
            'volume_ratio': safe_float(row['volume_ratio']),
            'pe': safe_float(row['pe']),
            'pb': safe_float(row['pb']),
            'total_mv': safe_float(row['total_mv']),  # 总市值（万元）
            'circ_mv': safe_float(row['circ_mv'])     # 流通市值（万元）
        }
        
    except Exception as e:
        print(f"⚠️ Error fetching Tushare daily_basic for {symbol}: {e}")
        return None

def fetch_latest_daily_ts(symbol: str) -> Optional[Dict[str, Any]]:
    """
    Fetch the LATEST raw daily transaction data (unadjusted) from Tushare `daily` interface.
    Used for specific report snapshots where raw price matches user's trading software.
    """
    pro = get_pro_client()
    if pro is None:
        return None
        
    try:
        ts_symbol = _format_symbol(symbol)
        
        # Fetch last 5 days to ensure we get the latest trading day (avoiding holidays/weekends)
        # end_date = datetime.now().strftime('%Y%m%d')
        # start_date = (datetime.now() - timedelta(days=10)).strftime('%Y%m%d')
        
        df = pro.daily(ts_code=ts_symbol)
        
        if df is None or df.empty:
            return None
            
        # Sort by date desc
        df = df.sort_values('trade_date', ascending=False)
        latest = df.iloc[0]
        
        return {
            'symbol': symbol,
            'date': latest['trade_date'],
            'open': float(latest['open']),
            'high': float(latest['high']),
            'low': float(latest['low']),
            'close': float(latest['close']),
            'pre_close': float(latest['pre_close']),
            'change': float(latest['change']),
            'pct_chg': float(latest['pct_chg']),
            'volume': float(latest['vol']),
            'amount': float(latest['amount'])
        }
    except Exception as e:
        print(f"❌ Error fetching latest daily ts for {symbol}: {e}")
        return None

def fetch_daily_ts(symbol: str, trade_date: str = None) -> Optional[pd.DataFrame]:
    """
    调用 Tushare 的 daily 接口，获取指定交易日的数据（未复权）
    
    参数:
        symbol: 股票代码 (例如: '600519')
        trade_date: 交易日期，格式 'YYYYMMDD'，默认为今天
        
    返回:
        DataFrame 包含以下字段:
        - ts_code: 股票代码
        - trade_date: 交易日期
        - open: 开盘价
        - high: 最高价
        - low: 最低价
        - close: 收盘价
        - pre_close: 昨收价（除权价）
        - change: 涨跌额
        - pct_chg: 涨跌幅（基于除权后的昨收计算）
        - vol: 成交量（手）
        - amount: 成交额（千元）
    """
    pro = get_pro_client()
    if pro is None:
        return None
        
    try:
        ts_symbol = _format_symbol(symbol)
        
        # 调用 Tushare daily 接口
        df = pro.daily(
            ts_code=ts_symbol,
            trade_date=trade_date
        )
        
        if df is None or df.empty:
            print(f"⚠️ No data returned from Tushare daily for {symbol}")
            return None
        
        # 确保数值类型正确
        numeric_cols = ['open', 'high', 'low', 'close', 'pre_close', 'change', 'pct_chg', 'vol', 'amount']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # 转换日期格式
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        
        # 按日期升序排序
        df = df.sort_values('trade_date').reset_index(drop=True)
    
        return df
        
    except Exception as e:
        print(f"❌ Error fetching Tushare daily data for {symbol}: {e}")
        import traceback
        traceback.print_exc()
        return None

def fetch_index_daily_ts(symbol: str, start_date: str, end_date: str = None) -> Optional[pd.DataFrame]:
    """
    Fetch daily index data (e.g. 000001.SH) from Tushare Index Daily
    """
    pro = get_pro_client()
    if pro is None:
        return None
        
    try:
        # Tushare index symbol usually needs format but '000001.SH' is standard
        # Pass through format just in case
        ts_symbol = _format_symbol(symbol)
        
        if not end_date:
            end_date = datetime.now().strftime('%Y%m%d')
            
        print(f"📉 Fetching Index Data for {ts_symbol}...")
        df = pro.index_daily(ts_code=ts_symbol, start_date=start_date, end_date=end_date)
        
        if df is None or df.empty:
            return None
            
        # Rename cols
        # ts_code, trade_date, close, open, high, low, pre_close, change, pct_chg, vol, amount
        df = df.rename(columns={
            'trade_date': 'date',
            'vol': 'volume'
        })
        
        # Ensure numeric
        numeric_cols = ['open', 'high', 'low', 'close', 'volume', 'amount']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date').reset_index(drop=True)
        
        print(f"✅ Fetched {len(df)} index records for {ts_symbol}")
        return df
        
    except Exception as e:
        print(f"❌ Error fetching Index data for {symbol}: {e}")
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
    获取股票的最新信息（复用 fetch_stock_data_ts 逻辑）
    
    返回字典格式，包含: symbol, name, price, open, high, low, close, volume, amount, change_pct
    """
    try:
        # 获取最近5天的数据（确保能获取到最新交易日）
        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=5)).strftime('%Y%m%d')
        
        # 复用 fetch_stock_data_ts 获取数据
        df = fetch_stock_data_ts(symbol, start_date=start_date, end_date=end_date, adjust='qfq', period='daily')
        
        if df is None or df.empty:
            return None
        
        # 获取最新一条记录
        latest_row = df.iloc[-1]
        
        # 获取股票名称（从 stock_basic 接口）
        name = symbol  # 默认使用代码
        try:
            pro = get_pro_client()
            if pro:
                ts_symbol = _format_symbol(symbol)
                basic_df = pro.stock_basic(ts_code=ts_symbol, fields='ts_code,name')
                if basic_df is not None and not basic_df.empty:
                    name = basic_df.iloc[0]['name']
        except Exception as e:
            print(f"⚠️ 获取股票名称失败 {symbol}: {e}")
        
        # 构建返回结果（保持与之前相同的格式）
        result = {
            'symbol': symbol,
            'name': name,
            'price': float(latest_row['close']),  # 使用收盘价作为当前价格
            'open': float(latest_row['open']),
            'high': float(latest_row['high']),
            'low': float(latest_row['low']),
            'close': float(latest_row['close']),
            'volume': int(float(latest_row['volume'])) if latest_row['volume'] else 0,
            'amount': float(latest_row['amount']) if latest_row['amount'] else 0.0,
            'change_pct': float(latest_row['change_pct']) if 'change_pct' in latest_row and latest_row['change_pct'] else 0.0
        }
        
        return result
        
    except Exception as e:
        print(f"❌ Error fetching Tushare stock info for {symbol}: {e}")
        return None

def fetch_stock_name_ts(symbol: str) -> str:
    """
    轻量级获取股票名称（仅调用 stock_basic 接口）
    
    参数:
        symbol: 股票代码 (例如: '600519')
        
    返回:
        股票名称，如果获取失败则返回股票代码
    """
    try:
        pro = get_pro_client()
        if pro:
            ts_symbol = _format_symbol(symbol)
            basic_df = pro.stock_basic(ts_code=ts_symbol, fields='ts_code,name')
            if basic_df is not None and not basic_df.empty:
                return basic_df.iloc[0]['name']
    except Exception as e:
        print(f"⚠️ 获取股票名称失败 {symbol}: {e}")
    
    return symbol  # 失败时返回代码

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
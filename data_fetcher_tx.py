"""
Tencent Data Fetcher specific implementation
Optimized for stability and batch processing
"""
import requests
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
import akshare as ak
import time

from data_fetcher_ts import get_pro_client

def get_market_snapshot_tencent() -> pd.DataFrame:
    """
    Get real-time snapshot of all A-share stocks using Tencent Interface.
    Replaces ak.stock_zh_a_spot_em() which is unstable.
    """
    print("🌍 Fetching market snapshot from Tencent (Batch)...")
    
    # 1. Get all codes (stable akshare API for static info)
    # This might fail if EM interface is completely down, but usually code list is cacheable
    codes = []
    try:
        codes_df = ak.stock_info_a_code_name()
        if codes_df is not None and not codes_df.empty:
            codes = codes_df['code'].tolist()
    except Exception as e:
        print(f"⚠️ Failed to get code list from AkShare: {e}")
        
    # Fallback: Tushare
    if not codes:
        print("🔄 Falling back to Tushare for code list...")
        try:
            pro = get_pro_client()
            if pro:
                df_ts = pro.stock_basic(exchange='', list_status='L', fields='symbol')
                if df_ts is not None and not df_ts.empty:
                     codes = df_ts['symbol'].tolist()
                     print(f"✅ Recovered {len(codes)} codes from Tushare.")
        except Exception as e:
            print(f"❌ Failed to get code list from Tushare: {e}")

    if not codes:
        print("❌ Critical: Could not fetch stock code list from any source.")
        return pd.DataFrame()
        
    # 2. Format codes for TX API (sh prefix for 60/68, sz for 00/30, bj for 4/8/9)
    tx_codes = []
    for c in codes:
        str_code = str(c)
        if str_code.startswith('6'):
            tx_codes.append(f"sh{str_code}")
        elif str_code.startswith('0') or str_code.startswith('3'):
            tx_codes.append(f"sz{str_code}")
        elif str_code.startswith('4') or str_code.startswith('8'):
             tx_codes.append(f"bj{str_code}")
        # Note: 9xx for BJ? Beijing usually 43/83/87
    
    # 3. Chunking (Use 80 per request for balance)
    chunk_size = 80
    chunks = [tx_codes[i:i + chunk_size] for i in range(0, len(tx_codes), chunk_size)]
    
    all_data = []
    
    def fetch_chunk(chunk_codes):
        if not chunk_codes: return None
        url = f"http://qt.gtimg.cn/q={','.join(chunk_codes)}"
        try:
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                resp.encoding = 'gbk' # Critical for Chinese names
                return resp.text
            return None
        except Exception:
            return None

    # Fetch in parallel with moderate concurrency to avoid IP ban
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_chunk = {executor.submit(fetch_chunk, chunk): chunk for chunk in chunks}
        
        for future in as_completed(future_to_chunk):
            res_text = future.result()
            if not res_text: continue
            
            lines = res_text.strip().split(';')
            for line in lines:
                if not line or '~' not in line: continue
                
                parts = line.split('~')
                if len(parts) < 45: continue
                
                try:
                    # Mapping:
                    # 1: Name, 2: Code, 3: Close, 32: ChangePct, 
                    # 38: Turnover, 39: PE, 44: FloatMcap(100M), 49: VolRatio
                    
                    # Basic filters to save memory/processing
                    # We can do Rough Screen filtering HERE if we wanted, but let's keep it generic
                    
                    data = {
                        'symbol': parts[2],
                        'name': parts[1],
                        'price': float(parts[3]),
                        'change_pct': float(parts[32]),
                        'volume_ratio': float(parts[49]) if parts[49] else 0,
                        'turnover_rate': float(parts[38]) if parts[38] else 0,
                        'pe_ttm': float(parts[39]) if parts[39] else 0,
                        'mcap_float': float(parts[44]) * 100000000 if parts[44] else 0,
                        # Add extra fields if needed
                        'volume': float(parts[36]) * 100, # Hand -> Share
                        'amount': float(parts[37]) * 10000, # 10k -> Unit? Usually 'Wan'
                        'open': float(parts[5]),
                        'pre_close': float(parts[4]),
                        'high': float(parts[33]),
                        'low': float(parts[34])
                    }
                    all_data.append(data)
                except (ValueError, IndexError):
                    continue

    if not all_data:
        print("❌ No data fetched from Tencent.")
        return pd.DataFrame()
        
    df = pd.DataFrame(all_data)
    print(f"✅ Fetched snapshot for {len(df)} stocks via Tencent.")
    return df

def get_stock_realtime_tx(symbol: str) -> dict:
    """
    Get real-time data for a SINGLE stock from Tencent.
    支持输入: 
    - 纯数字代码: '000001', '603599', '399001'
    - 带市场前缀: 'sh000001', 'sz000001', 'sz399001'
    """
    # 1. 检查是否已经带有市场前缀
    str_code = str(symbol).lower().strip()
    
    if str_code.startswith(('sh', 'sz', 'bj')):
        # 已经带前缀，直接使用
        tx_code = str_code
    else:
        # 纯数字代码，根据规则添加前缀
        # 6/68 开头 -> 上海
        # 0/3 开头 -> 深圳
        # 4/8 开头 -> 北京
        if str_code.startswith('6'):
            tx_code = f"sh{str_code}"
        elif str_code.startswith('0') or str_code.startswith('3'):
            tx_code = f"sz{str_code}"
        elif str_code.startswith('4') or str_code.startswith('8'):
            tx_code = f"bj{str_code}"
        else:
            print(f"⚠️ Unknown symbol format: {symbol}")
            return None
        
    url = f"http://qt.gtimg.cn/q={tx_code}"
    
    try:
        resp = requests.get(url, timeout=3)
        if resp.status_code != 200:
            return None
            
        resp.encoding = 'gbk'
        line = resp.text.strip()
        
        # v_sh600000="浦发银行~600000~9.49~9.51~9.48~9.45~9.44~480665~45544~379684128~9.49~..."
        if not line or '~' not in line:
            return None
            
        parts = line.split('~')
        if len(parts) < 45:
            return None
            
        # Calculate VWAP
        amount_wan = float(parts[37]) if parts[37] else 0
        volume_hand = float(parts[36]) if parts[36] else 0
        vwap = 0.0
        if volume_hand > 0:
            vwap = (amount_wan * 10000) / (volume_hand * 100)
            
        # Order Book Analysis
        bid_vols = []
        ask_vols = []
        
        for i in range(5):
            # Bids
            b_idx = 10 + i * 2
            if len(parts) > b_idx and parts[b_idx]:
                bid_vols.append(int(parts[b_idx]))
            
            # Asks
            a_idx = 20 + i * 2
            if len(parts) > a_idx and parts[a_idx]:
                ask_vols.append(int(parts[a_idx]))

        total_bid_vol = sum(bid_vols)
        total_ask_vol = sum(ask_vols)
        
        # WeiBi
        weibi = 0.0
        if total_bid_vol + total_ask_vol > 0:
            weibi = (total_bid_vol - total_ask_vol) / (total_bid_vol + total_ask_vol) * 100

        data = {
            'symbol': parts[2], # 股票代码
            'name': parts[1], # 股票名称
            'price': float(parts[3]), # 当前价格
            'change_pct': float(parts[32]), # 涨跌幅
            'volume_ratio': float(parts[49]) if parts[49] else 0, # 量比
            'turnover_rate': float(parts[38]) if parts[38] else 0, # 换手率
            'pe_ttm': float(parts[39]) if parts[39] else 0, # 市盈率    
            'mcap_float': float(parts[44]) * 100000000 if parts[44] else 0, # 流通市值
            'volume': float(parts[36]) * 100, # 成交量
            'amount': float(parts[37]) * 10000, # 成交额
            'open': float(parts[5]), # 开盘价
            'pre_close': float(parts[4]), # 昨收价
            'high': float(parts[33]), # 最高价
            'low': float(parts[34]), # 最低价
            'bid1': float(parts[9]) if parts[9] else 0, # 买一价
            'bid1_vol': int(parts[10]) if parts[10] else 0, # 买一量
            'ask1': float(parts[19]) if parts[19] else 0, # 卖一价
            'ask1_vol': int(parts[20]) if parts[20] else 0, # 卖一量
            'vwap': round(vwap, 3), # 平均成交价
            'weibi': round(weibi, 2), # 委比
            'bid_vols': bid_vols, # 委买量
            'ask_vols': ask_vols # 委卖量
        }
        print(f"✅ Fetched realtime data for {symbol} from Tencent: {data}")
        return data
        
    except Exception as e:
        print(f"❌ Error fetching realtime data for {symbol} from Tencent: {e}")
        return None
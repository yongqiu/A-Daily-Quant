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
                        'amount': float(parts[37]) * 10000 # 10k -> Unit? Usually 'Wan'
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
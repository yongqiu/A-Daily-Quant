"""
Tool to generate a Stock-to-Sector mapping JSON file.
This helps supply sector information when the primary data source (e.g. Tencent)
does not provide it.

Usage:
    python generate_sector_map.py
"""
import akshare as ak
import pandas as pd
import json
import time
import os

SECTOR_MAP_FILE = "sector_map.json"

def generate_map():
    print("🌍 Fetching industry list from EastMoney...")
    try:
        # 1. Get List of Industries
        df_ind = ak.stock_board_industry_name_em()
        if df_ind is None or df_ind.empty:
            print("❌ Failed to get industry list.")
            return

        print(f"✅ Found {len(df_ind)} industries. Starting iteration...")
        
        sector_map = {} # stock_code -> sector_name
        
        # 2. Iterate each industry
        for idx, row in df_ind.iterrows():
            sector_name = row['板块名称']
            try:
                # Fetch constituents
                df_cons = ak.stock_board_industry_cons_em(symbol=sector_name)
                if df_cons is not None and not df_cons.empty:
                    # Usually returns columns like: 代码, 名称, ...
                    for _, stock in df_cons.iterrows():
                        code = str(stock['代码'])
                        # Prefer last overwrite? Or list? Usually 1 stock 1 sector in this map
                        sector_map[code] = sector_name
                
                print(f"   [{idx+1}/{len(df_ind)}] Processed {sector_name}: {len(df_cons)} stocks")
                time.sleep(0.5) # Gentle rate limit
                
            except Exception as e:
                print(f"   ⚠️ Error processing {sector_name}: {e}")
                time.sleep(2)
        
        # 3. Save to JSON
        print(f"\n✅ Generation Complete! Mapped {len(sector_map)} stocks.")
        with open(SECTOR_MAP_FILE, 'w', encoding='utf-8') as f:
            json.dump(sector_map, f, ensure_ascii=False, indent=2)
        print(f"💾 Saved to {os.path.abspath(SECTOR_MAP_FILE)}")
        
    except Exception as e:
        print(f"❌ Critical Error: {e}")

if __name__ == "__main__":
    generate_map()
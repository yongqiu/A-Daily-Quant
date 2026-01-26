import akshare as ak
import pandas as pd
from datetime import datetime
import os

# Clear proxy to avoid connection issues
# Extended proxy cleanup including ALL_PROXY
for env_var in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy']:
    if env_var in os.environ:
        print(f"POPPING ENV VAR: {env_var}")
        os.environ.pop(env_var)

# Force no_proxy to ignore any system level proxies
os.environ['no_proxy'] = '*'

# Print current environment variables for debugging
print("Current Environment (After Cleanup):")
for k, v in os.environ.items():
    if "PROXY" in k.upper():
        print(f"  {k}={v}")

def check_sector_beta():
    print("\n--- Checking Sector Beta Data ---")
    try:
        # 尝试获取行业板块当日涨幅
        # ak.stock_board_industry_name_em() 获取东方财富行业板块列表及当日涨幅
        df = ak.stock_board_industry_name_em()
        print(f"Features: Rows={len(df)}")
        print(df[['板块名称', '涨跌幅', '领涨股票']].head())
        
        # 检查是否有 '最新价' 和 '涨跌幅'
        has_required = '板块名称' in df.columns and '涨跌幅' in df.columns
        print(f"Contains required columns: {has_required}")
        return True
    except Exception as e:
        print(f"Error fetching sector data: {e}")
        return False

def check_individual_news(symbol="600519"):
    print(f"\n--- Checking Individual News for {symbol} ---")
    try:
        # 尝试获取个股新闻
        # ak.stock_news_em(symbol=symbol)
        news_df = ak.stock_news_em(symbol=symbol)
        if news_df is not None and not news_df.empty:
            print(f"Found {len(news_df)} news items.")
            print(news_df[['发布时间', '新闻标题']].head())
            return True
        else:
            print("No news found.")
            return False
    except Exception as e:
        print(f"Error fetching news: {e}")
        return False

def check_concept_data():
    print("\n--- Checking Concept/Theme Data ---")
    try:
        # 概念板块
        df = ak.stock_board_concept_name_em()
        print(f"Features: Rows={len(df)}")
        print(df[['板块名称', '涨跌幅', '领涨股票']].head())
        return True
    except Exception as e:
        print(f"Error fetching concept data: {e}")
        return False

if __name__ == "__main__":
    check_sector_beta()
    check_individual_news()
    check_concept_data()
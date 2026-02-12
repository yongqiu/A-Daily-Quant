"""
数据获取模块 - 处理 A 股市场数据的 AkShare 交互
"""
import akshare as ak
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import requests
from functools import lru_cache
import time
import json
import os
from data_fetcher_ts import fetch_stock_data_ts, fetch_stock_info_ts, fetch_sector_map

# 股票信息缓存: {symbol: (data, timestamp)}
_stock_info_cache: Dict[str, tuple] = {}
_CACHE_TTL_SECONDS = 300  # 5分钟缓存
_last_cache_cleanup_time = time.time()
_CACHE_CLEANUP_INTERVAL = 600  # 每10分钟清理一次缓存


def _cleanup_expired_cache():
    """清理过期缓存条目以避免内存泄漏"""
    global _last_cache_cleanup_time

    current_time = time.time()

    # 仅在经过足够时间后清理
    if current_time - _last_cache_cleanup_time < _CACHE_CLEANUP_INTERVAL:
        return

    # 查找并移除过期条目
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
    从币安获取加密货币历史数据。
    symbol: 例如 "BTC" (自动添加 USDT) 或 "BTCUSDT"
    """
    if not symbol.endswith("USDT"):
        symbol = f"{symbol}USDT"
    
    url = "https://api.binance.com/api/v3/klines"
    # 限制计算: days
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
        # 币安 K线数据: [Open Time, Open, High, Low, Close, Volume, ...]
        df = pd.DataFrame(data, columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_asset_volume", "trades", "taker_buy_base", "taker_buy_quote", "ignore"
        ])
        
        df = df[["open_time", "open", "high", "low", "close", "volume"]]
        df["date"] = pd.to_datetime(df["open_time"], unit='ms')
        
        # 数值转换
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
    从 AkShare (新浪源) 获取期货历史数据。
    symbol: 例如 "au0" (黄金主力)
    """
    try:
        # 假设为国内期货主力合约
        df = ak.futures_main_sina(symbol=symbol)
        
        if df is None or df.empty:
            return None
            
        # 标准化列名
        # AkShare 新浪期货列名通常为: 日期, 开盘价, 最高价, ...
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
        
        # 按日期过滤
        df['date'] = pd.to_datetime(df['date'])
        start_dt = pd.to_datetime(start_date)
        df = df[df['date'] >= start_dt].copy()
        
        df = df.sort_values('date').reset_index(drop=True)
        
        # 确保浮点类型
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
    尝试从腾讯 (TX) 作为 A 股的主要来源获取。
    TX 需要前缀 (sz/sh)。
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
        # akshare 的 tx 接口支持 adjust='qfq'
        df = ak.stock_zh_a_hist_tx(symbol=tx_symbol, start_date=start_date, end_date=end_date, adjust="qfq")
        if df is not None and not df.empty:
            # TX 返回: date, open, close, high, low, amount(实际上是手数)
            # 我们需要映射 'amount' -> 'volume'
            # 如果需要，可能需要估算 'amount' (金额)
            df = df.rename(columns={'amount': 'volume'})
            
            # 估算成交额: Close * Volume * 100 (假设 1 手 = 100 股)
            # 这是一个粗略的估算，如果金额不关键，对于量比计算足够了
            # 大多数指标使用成交量，而不是成交额。
            df['amount'] = df['close'] * df['volume'] * 100
            
            # 确保列存在
            for col in ['date', 'open', 'close', 'high', 'low', 'volume', 'amount']:
                if col not in df.columns:
                    # 'date' 可能是索引或命名不同?
                    # 测试验证: 列为 ['date', 'open', 'close', 'high', 'low', 'amount']
                    pass
            
            # 过滤 0 值
            if 'close' in df.columns:
                 df = df[df['close'] > 0]
                 
            return df
    except Exception as e:
        # Quiet fail to fallback
        return None
    return None

def _get_data_provider() -> str:
    """获取配置的数据提供商"""
    try:
        config_path = os.path.join(os.path.dirname(__file__), 'config.json')
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                return config.get('data_source', {}).get('provider', 'akshare')
    except Exception:
        pass
    return 'akshare'

def fetch_stock_data(symbol: str, start_date: str, is_index: bool = False, period: str = "daily") -> Optional[pd.DataFrame]:
    """
    从 AkShare 或 Tushare 获取历史股票数据
    
    优先级: Tushare > AkShare (腾讯/东方财富/新浪)
    
    参数:
        symbol: 股票代码 (例如 '600519') 或指数代码 (例如 '000300')
        start_date: 'YYYYMMDD' 格式的开始日期
        is_index: 如果获取指数数据则为 True，个股为 False
        period: 'daily' (日), 'weekly' (周), 'monthly' (月)
    
    返回:
        带有 date, open, close, high, low, volume 列的 DataFrame
        如果获取失败返回 None
    """
    # 1. 首先尝试 Tushare (主要来源)
    # 如果 Tushare 未配置用于 ETF/指数，或者我们知道 akshare 更好，则跳过
    # 但用户请求 "Tushare 作为主要来源"，所以我们对标准股票尝试它。
    
    # 简单启发式: 股票代码通常不以 5/1 开头，除非是 ETF/基金
    # 然而，Tushare 也支持 ETF。
    
    # 对所有周期 (日、周、月) 首先尝试 Tushare
    try:
        print(f"🔄 [DataFetcher] Attempting Tushare history ({period}) for: {symbol}")
        df_ts = fetch_stock_data_ts(symbol, start_date, period=period)
        if df_ts is not None and not df_ts.empty:
            # Check length reasonable?
            if len(df_ts) > 0:
                    print(f"✅ [DataFetcher] Tushare success for {symbol} ({len(df_ts)} rows)")
                    return df_ts
        print(f"⚠️ [DataFetcher] Tushare returned no data for {symbol}, initiating FALLBACK to AkShare...")
    except Exception as e:
        print(f"⚠️ [DataFetcher] Tushare error for {symbol}: {e}, initiating FALLBACK to AkShare...")

    # 2. 回退到 AkShare/腾讯 逻辑
    print(f"🔄 [DataFetcher] Fallback: Trying AkShare/Tencent for {symbol}...")
    max_retries = 3
    base_delay = 2
    
    # 确定合适的结束日期
    now = datetime.now()
    # 如果早于 09:15 (盘前集合竞价)，使用昨天作为结束日期
    # 以避免获取可能存在的虚假 K 线或尚未有效的 "今日" 数据。
    if now.time() < datetime.strptime("09:15", "%H:%M").time():
        end_date = (now - timedelta(days=1)).strftime('%Y%m%d')
    else:
        end_date = now.strftime('%Y%m%d')

    for attempt in range(max_retries):
        try:
            df = None
            
            # 1. 股票的特殊处理 (双源)
            if not is_index and not (symbol.startswith('51') or symbol.startswith('159')):
                # 日线首先尝试腾讯 (稳定)
                if period == 'daily':
                    df = fetch_stock_data_tx_fallback(symbol, start_date, end_date)
                    if df is not None:
                         pass # 从 TX 获取
                    else:
                         # 回退到东方财富
                         df = ak.stock_zh_a_hist(symbol=symbol, period="daily", start_date=start_date, end_date=end_date, adjust="qfq")
                else:
                    # 周/月: 使用东方财富接口
                    # ak.stock_zh_a_hist 参数 'period' 支持 'daily', 'weekly', 'monthly'
                    df = ak.stock_zh_a_hist(symbol=symbol, period=period, start_date=start_date, end_date=end_date, adjust="qfq")

            elif is_index:
                # 获取指数数据 (如 沪深300)
                df = ak.index_zh_a_hist(symbol=symbol, period=period, start_date=start_date, end_date=end_date)
            elif symbol.startswith('51') or symbol.startswith('159'):
                # ETF 代码 (51开头或159开头) 使用 ETF 专用接口
                # ak.fund_etf_hist_em 支持 daily, weekly, monthly
                df = ak.fund_etf_hist_em(symbol=symbol, period=period, start_date=start_date, end_date=end_date)
            
            if df is None or df.empty:
                # 有时 API 对有效股票返回空，如果网络故障或 start_date 问题
                # 但通常只是空的。除非我们怀疑连接问题，否则我们在空时不重试。
                # 然而，连接错误通常会引发异常。
                print(f"⚠️  No data returned for {symbol} (Attempt {attempt+1})")
                if attempt < max_retries - 1:
                     time.sleep(base_delay * (attempt + 1))
                     continue
                return None
            
            # 标准化列名
            df = df.rename(columns={
                '日期': 'date',
                '开盘': 'open',
                '收盘': 'close',
                '最高': 'high',
                '最低': 'low',
                '成交量': 'volume',
                '成交额': 'amount'
            })
            
            # 确保日期为 datetime 类型
            df['date'] = pd.to_datetime(df['date'])
            
            # 过滤无效行，收盘价为 0 (例如数据错误或不完整的一天)
            if 'close' in df.columns:
                df = df[df['close'] > 0]
                
            df = df.sort_values('date').reset_index(drop=True)
            
            print(f"✅ Fetched {len(df)} days of data for {symbol}")
            return df
            
        except Exception as e:
            error_str = str(e)
            # 检查连接相关错误以重试
            is_conn_error = 'Connection' in error_str or 'RemoteDisconnected' in error_str or 'timeout' in error_str.lower()
            
            if is_conn_error and attempt < max_retries - 1:
                wait_time = base_delay * (2 ** attempt) # 指数退避: 2s, 4s, 8s
                print(f"⚠️ Connection error for {symbol}: {e}. Retrying in {wait_time}s...")
                time.sleep(wait_time)
                continue
            
            if attempt == max_retries - 1:
                print(f"❌ Error fetching data for {symbol}: {str(e)}")
                return None
    return None


def fetch_data_dispatcher(symbol: str, asset_type: str, start_date: str, period: str = "daily") -> Optional[pd.DataFrame]:
    """
    根据资产类型分发获取请求
    周期: 'daily', 'weekly', 'monthly'
    """
    if asset_type == 'crypto':
        # 从开始日期估算天数
        # TODO: 如果需要，支持加密货币周期映射 (Binance '1d', '1w', '1M')
        return fetch_crypto_data(symbol, days=120)
    elif asset_type == 'future':
        # TODO: 如果 API 允许，支持期货周期
        return fetch_future_data(symbol, start_date)
    else:
        # 默认为股票/ETF
        # 指数检查: 如果代码以字母开头 (如 sh000001) 或特定配置
        # 为简单起见，如果传递到这里，假设为标准股票/ETF，除非在其他地方指定了指数
        # 如果 'sh000001'，它是指数
        is_index = symbol.lower().startswith('sh') and len(symbol) > 6
        return fetch_stock_data(symbol, start_date, is_index=is_index, period=period)


def get_latest_trading_date() -> str:
    """
    获取最近的交易日期 (今天或最后一个交易日)
    返回 'YYYYMMDD' 格式的日期
    """
    today = datetime.now()
    # 最多回溯7天以找到交易日
    for i in range(7):
        check_date = today - timedelta(days=i)
        return check_date.strftime('%Y%m%d')
    return today.strftime('%Y%m%d')


def calculate_start_date(lookback_days: int = None) -> str:
    """
    计算数据获取的开始日期
    
    参数:
        lookback_days: 回溯天数 (默认从配置读取或 365)
    
    返回:
        'YYYYMMDD' 格式的开始日期
    """
    if lookback_days is None:
        # 尝试从配置加载
        try:
            config_path = os.path.join(os.path.dirname(__file__), 'config.json')
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    lookback_days = config.get('analysis', {}).get('lookback_days', 365)
        except Exception:
            pass
            
    if lookback_days is None:
         lookback_days = 365
         
    start = datetime.now() - timedelta(days=lookback_days + 30)  # 周末的额外缓冲
    return start.strftime('%Y%m%d')

def fetch_sector_data() -> Optional[pd.DataFrame]:
    """
    从东方财富获取今日板块(行业)表现
    返回: 包含 ['板块名称', '涨跌幅', '领涨股票'] 的 DataFrame
    """
    try:
        # 行业板块
        df_industry = ak.stock_board_industry_name_em()
        # 概念板块 (可选，可能太嘈杂)
        # df_concept = ak.stock_board_concept_name_em()
        
        if df_industry is None or df_industry.empty:
            return None
            
        print(f"✅ Fetched {len(df_industry)} industry sectors.")
        return df_industry
    except Exception as e:
        print(f"❌ Error fetching sector data: {str(e)}")
        return None

SECTOR_MAP_FILE = "sector_map.json"

def load_sector_map() -> Dict[str, str]:
    """
    加载板块映射。如果本地文件丢失或为空，则从 Tushare 获取并保存。
    """
    # 1. 尝试本地文件
    try:
        if os.path.exists(SECTOR_MAP_FILE):
            with open(SECTOR_MAP_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data:
                    return data
    except Exception as e:
        print(f"⚠️ Failed to load local sector_map.json: {e}")

    # 2. 如果缺失则获取
    print("🌍 Local sector map missing. Fetching from Tushare...")
    sector_map = fetch_sector_map()
    
    if sector_map:
        try:
            with open(SECTOR_MAP_FILE, "w", encoding="utf-8") as f:
                json.dump(sector_map, f, ensure_ascii=False, indent=2)
            print(f"💾 Saved sector map to {SECTOR_MAP_FILE}")
        except Exception as e:
            print(f"⚠️ Failed to save sector map: {e}")
            
    return sector_map

def get_sector_performance(sector_name: str, sector_df: pd.DataFrame = None) -> float:
    """
    获取特定板块的表现 (涨跌幅)
    """
    if not sector_name or sector_name == 'N/A':
        return 0.0
        
    try:
        if sector_df is None:
            sector_df = fetch_sector_data()
            
        if sector_df is not None and not sector_df.empty:
             # 1. 精确匹配
             row = sector_df[sector_df['板块名称'] == sector_name]
             if not row.empty:
                 return float(row.iloc[0]['涨跌幅'])

             # 2. 别名映射 (Tushare/申万 -> 东方财富)
             # 东方财富板块: '农牧饲渔', '软件开发', '房地产开发', '电子元件', 等等。
             alias_map = {
                 "种植业": "农牧饲渔",
                 "林业": "农牧饲渔",
                 "畜禽养殖": "农牧饲渔",
                 "渔业": "农牧饲渔",
                 "饲料": "农牧饲渔",
                 "农产品加工": "农牧饲渔",
                 "农业综合": "农牧饲渔",
                 "软件服务": "软件开发",
                 "IT设备": "计算机设备",
                 "元器件": "电子元件",
                 "全国地产": "房地产开发",
                 "区域地产": "房地产开发",
                 "房产服务": "房地产服务",
                 "建筑工程": "工程建设",
                 "运输设备": "交运设备",
                 "电气设备": "电网设备", # or 电机, 电源设备
                 "其他商业": "商业百货",
                 "综合类": "综合行业",
                 "服饰": "纺织服装",
                 "普钢": "钢铁行业",
                 "特钢": "钢铁行业",
                 "煤炭开采": "煤炭行业"
             }
             
             mapped_name = alias_map.get(sector_name)
             if mapped_name:
                 row = sector_df[sector_df['板块名称'] == mapped_name]
                 if not row.empty:
                     print(f"✅ Mapped sector '{sector_name}' -> '{mapped_name}'")
                     return float(row.iloc[0]['涨跌幅'])

             # 3. 模糊匹配 (包含)
             # 例如 "汽车" -> "汽车整车", "汽车零部件"
             # 例如 "半导体" -> "半导体"
             # 反向包含: 如果 sector_name 在 EM_name 中
             for _, r in sector_df.iterrows():
                 em_name = r['板块名称']
                 if sector_name in em_name or em_name in sector_name:
                      # 小心短匹配
                      if len(sector_name) > 1 and len(em_name) > 1:
                           print(f"⚠️ Fuzzy matched sector '{sector_name}' ~= '{em_name}'")
                           return float(r['涨跌幅'])
                           
    except Exception as e:
        print(f"Error getting sector performance for {sector_name}: {e}")
        
    return 0.0

def fetch_stock_news(symbol: str) -> str:
    """
    获取特定股票的最新新闻 (前3条)
    """
    try:
        news_df = ak.stock_news_em(symbol=symbol)
        if news_df is None or news_df.empty:
            return "暂无相关新闻"
            
        # 获取前3条新闻标题
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


def fetch_money_flow(symbol: str) -> Dict[str, Any]:
    """
    获取资金流向数据 (大单/超大单)
    返回包含流向数据的字典
    """
    try:
        # 获取个股资金流向
        df = ak.stock_individual_fund_flow(stock=symbol, market="sh" if symbol.startswith("6") else "sz")
        
        if df is None or df.empty:
            return {"status": "no_data"}
            
        # 获取最新行
        # 典型列: 日期, 收盘价, 涨跌幅, 主力净流入-净额, 主力净流入-净占比, 超大单...
        latest = df.iloc[0] # 通常按日期降序排列，但检查日期
        
        # 确保是最新的 (例如 3 天内)
        # AkShare 通常返回历史数据，第 0 行可能是最新的
        # df 通常按日期排序？检查文档或假设第一行是最新的或排序
        # 实际上 stock_individual_fund_flow 返回历史数据
        # 我们需要按日期降序排序
        if '日期' in df.columns:
            df['日期'] = pd.to_datetime(df['日期'])
            df = df.sort_values('日期', ascending=False)
            latest = df.iloc[0]
            
        return {
            "date": latest['日期'].strftime('%Y-%m-%d'),
            "net_amount_main": float(latest.get('主力净流入-净额', 0)) / 10000, # Convert to Wan
            "net_pct_main": float(latest.get('主力净流入-净占比', 0)),
            "net_amount_super": float(latest.get('超大单净流入-净额', 0)) / 10000,
            "net_amount_large": float(latest.get('大单净流入-净额', 0)) / 10000,
            "status": "success"
        }
    except Exception as e:
        print(f"⚠️ Error fetching money flow for {symbol}: {e}")
        return {"status": "error", "message": str(e)}

def fetch_dragon_tiger_data(symbol: str) -> Dict[str, Any]:
    """
    获取龙虎榜数据 (如果最近可用)
    """
    try:
        # 获取股票的最新日期
        # 该 API 可能较慢，所以捕获超时
        # ak.stock_lhb_detail_em(symbol=symbol, date=...)
        # 但我们不知道日期。
        # 使用 ak.stock_lhb_stock_statistic_em 查看最近出现情况?
        
        # 更简单: 仅检查最近 (过去5天) 是否上榜
        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=5)).strftime('%Y%m%d')
        
        # 获取龙虎榜历史
        df = ak.stock_lhb_detail_daily_sina(symbol=symbol, date=end_date) # 新浪检查特定日期
        # 东方财富接口可能对 "最近" 更好
        # ak.stock_lhb_detail_em 需要特定日期
        
        # 尝试获取最近的龙虎榜摘要，如果需要复杂查询则留空
        # 策略: 我们暂时跳过复杂的龙虎榜查询以避免延迟，
        # 除非我们有快速的 API。
        # 回退: 暂时返回 "无数据"，或者如果用户坚持则实现。
        # 用户请求了它，所以我们尝试特定日期 (今天/昨天)
        
        target_date = get_latest_trading_date()
        df = ak.stock_lhb_detail_em(symbol=symbol, date=target_date)
        
        if df is None or df.empty:
            return {"on_list": False}
        
        # 总结
        buy_total = df['买入金额'].sum() if '买入金额' in df.columns else 0
        sell_total = df['卖出金额'].sum() if '卖出金额' in df.columns else 0
        net_amount = buy_total - sell_total
        
        # 检查特定席位
        seats = df['营业部名称'].tolist() if '营业部名称' in df.columns else []
        jg_seats = [s for s in seats if '机构专用' in s]
        lsca_seats = [s for s in seats if '拉萨' in s] # 散户大本营
        hk_seats = [s for s in seats if '深股通' in s or '沪股通' in s] # 北向资金
        
        return {
            "on_list": True,
            "date": target_date,
            "net_amount": net_amount,
            "buy_total": buy_total,
            "sell_total": sell_total,
            "jg_count": len(jg_seats), # 机构
            "lsca_count": len(lsca_seats), # 散户
            "hk_count": len(hk_seats), # 外资
            "top_seats": seats[:3] # 前 3
        }
        
    except Exception as e:
        # print(f"LHB fetch error (might not be on list): {e}")
        return {"on_list": False}

def fetch_stock_info(symbol: str) -> Optional[Dict[str, Any]]:
    """
    通过代码获取股票基本信息
    返回包含键: name, price, change_pct 等的字典
    优先级: Tushare -> AkShare
    """
    # 验证代码格式 (必须至少 6 位数字)
    if not symbol or len(symbol) < 6 or not symbol.isdigit():
        # 如果是以字母开头的有效指数或正确格式则允许
        if not (symbol.startswith('sh') or symbol.startswith('sz')):
             return None
    # 触发定期缓存清理
    _cleanup_expired_cache()

    # 首先检查缓存
    current_time = time.time()
    if symbol in _stock_info_cache:
        cached_data, cached_time = _stock_info_cache[symbol]
        if current_time - cached_time < _CACHE_TTL_SECONDS:
            print(f"✅ Using cached data for {symbol} (age: {int(current_time - cached_time)}s)")
            return cached_data

    # 1. 尝试 Tushare 获取实时数据
    # 注意: ts.get_realtime_quotes 是旧版但适用于 A 股
    try:
        # 检查 Tushare 实时数据是否支持该资产 (主要是股票)
        # 如果已知不支持，跳过加密货币/期货/部分基金
        is_crypto_future = len(symbol) > 6 and not symbol.isdigit() # 粗略检查
        
        if not is_crypto_future:
            print(f"🔄 [DataFetcher] Attempting Tushare Realtime for: {symbol}")
            res = fetch_stock_info_ts(symbol)
            if res:
                 _stock_info_cache[symbol] = (res, current_time)
                 print(f"✅ [DataFetcher] Tushare Realtime success for {symbol}: {res['price']}")
                 return res
            print(f"⚠️ [DataFetcher] Tushare Realtime failed/empty for {symbol}, initiating FALLBACK...")
    except Exception as e:
        print(f"⚠️ [DataFetcher] Tushare Realtime error for {symbol}: {e}, initiating FALLBACK...")

    # 2. 回退到 AkShare/东方财富/腾讯
    print(f"🔄 [DataFetcher] Fallback: Trying AkShare Realtime for {symbol}...")
    try:
        # 方法 1: 尝试获取个股/ETF 实时报价 (快得多)
        # 根据代码模式确定是否为 ETF
        is_etf = symbol.startswith('51') or symbol.startswith('159') or symbol.startswith('50')

        try:
            # 获取最近一天的数据
            if is_etf:
                # 使用 ETF 专用接口
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

                # 从基本信息获取股票/ETF 名称
                stock_name = symbol  # 如果获取名称失败，默认为代码
                try:
                    if is_etf:
                        # 对于 ETF，尝试从历史数据获取名称 (更快)
                        # 一些 ETF 历史数据可能在元数据中包含名称
                        # 如果不可用，用户可以手动输入名称
                        # 我们跳过完整的 ETF 现货查询以避免减速
                        stock_name = f"ETF-{symbol}"  # 占位符，用户稍后可以编辑
                    else:
                        # 从个股信息获取名称
                        info_df = ak.stock_individual_info_em(symbol=symbol)
                        if info_df is not None and not info_df.empty:
                            name_row = info_df[info_df['item'] == '股票简称']
                            stock_name = name_row['value'].iloc[0] if not name_row.empty else symbol
                except Exception as e:
                    print(f"⚠️ Could not fetch name for {symbol}: {e}")

                # 从最新数据计算涨跌幅
                close_price = float(latest.get('收盘', 0))
                open_price = float(latest.get('开盘', 0))

                # 估算涨跌幅 (理想情况下需要昨收)
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

                # 缓存结果
                _stock_info_cache[symbol] = (result, current_time)
                print(f"✅ Fetched and cached {'ETF' if is_etf else 'stock'} info for {symbol}")
                return result
            else:
                # 空数据框意味着股票不存在 - 不要回退到完整的市场查询
                print(f"⚠️ {'ETF' if is_etf else 'Stock'} {symbol} not found (empty data returned)")
                return None

        except Exception as e:
            # 检查是否为 "股票未找到" 类型的错误
            error_msg = str(e).lower()
            if any(keyword in error_msg for keyword in ['不存在', 'not found', 'empty', '无数据', 'no data']):
                print(f"⚠️ Stock {symbol} does not exist: {e}")
                return None

            print(f"⚠️ Fast fetch failed for {symbol}: {e}")
            return None


    except Exception as e:
        print(f"❌ Error fetching stock info for {symbol}: {e}")
        return None


def fetch_intraday_data(symbol: str) -> Optional[pd.DataFrame]:
    """
    获取今日分时数据 (1分钟级)
    返回: date, open, high, low, close, volume DataFrame
    """
    try:
        # AkShare 分时接口需要特定前缀
        if symbol.startswith('6'):
            code = f"sh{symbol}"
        elif symbol.startswith('0') or symbol.startswith('3'):
            code = f"sz{symbol}"
        else:
            return None
            
        # period='1' 代表1分钟
        df = ak.stock_zh_a_minute(symbol=code, period='1', adjust='qfq')
        print("df",df)
        
        if df is None or df.empty:
            return None
            
        # 确保列名标准化
        # akshare返回: day, open, high, low, close, volume
        df = df.rename(columns={'day': 'date'})
        df['date'] = pd.to_datetime(df['date'])
        
        # 转换数值类型
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
            
        return df
        
    except Exception as e:
        print(f"⚠️ Error fetching intraday data for {symbol}: {e}")
        return None


def fetch_cyq_data(symbol: str) -> Optional[Dict[str, float]]:
    """
    获取最新筹码分布数据 (CYQ - Cost Distribution)
    返回: 包含获利比例、平均成本、集中度等的字典
    """
    try:
        # 获取最新可用的筹码数据
        df = ak.stock_cyq_em(symbol=symbol, adjust="qfq")
        
        if df is None or df.empty:
            return None
            
        # 取最新的一行
        latest = df.iloc[-1]
        
        return {
            "date": str(latest['日期']),
            "profit_pct": float(latest.get('获利比例', 0)),
            "avg_cost": float(latest.get('平均成本', 0)),
            # 集中度通常是 (高-低)/(高+低) 或者直接由API提供
            # AkShare 返回: 90集中度, 70集中度
            "concentration_90": float(latest.get('90集中度', 0)),
            "concentration_70": float(latest.get('70集中度', 0)),
            "cost_90_low": float(latest.get('90成本-低', 0)),
            "cost_90_high": float(latest.get('90成本-高', 0)),
            "cost_70_low": float(latest.get('70成本-低', 0)),
            "cost_70_high": float(latest.get('70成本-高', 0))
        }
        
    except Exception as e:
        print(f"⚠️ Error fetching CYQ data for {symbol}: {e}")
        return None

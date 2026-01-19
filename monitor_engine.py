"""
Monitor Engine for A-Share Strategy
Handles real-time data fetching and strategy check execution.
"""
import akshare as ak
import pandas as pd
import json
import os
import re
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from data_fetcher import fetch_data_dispatcher, calculate_start_date
from indicator_calc import calculate_indicators, get_latest_metrics
from llm_analyst import generate_analysis
from etf_score import apply_etf_score
import database

# --- Configuration ---
CONFIG_PATH = "config.json"
REPORTS_DIR = "reports"
# Supporting generic pattern in case format changes
CANDIDATES_FILE_PATTERN = r"daily_strategy_.*_(\d{8})\.md"

def load_config() -> Dict[str, Any]:
    """Load system configuration"""
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ Error loading config: {e}")
        return {}

def get_latest_candidate_file() -> Optional[str]:
    """Find the most recent candidates markdown file"""
    search_dir = REPORTS_DIR if os.path.exists(REPORTS_DIR) else "."
    
    files = [f for f in os.listdir(search_dir) if re.match(CANDIDATES_FILE_PATTERN, f)]
    if not files:
        return None
    # Sort by date in filename (YYYYMMDD) descending
    files.sort(key=lambda x: re.search(CANDIDATES_FILE_PATTERN, x).group(1), reverse=True)
    return os.path.join(search_dir, files[0])

def parse_candidates_from_md(filename: str) -> List[Dict[str, Any]]:
    """
    Parse candidate stocks from the generated markdown report.
    This is a simple parser assuming the standard format.
    """
    candidates = []
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Regex to find stock headers like "### 1. 600123 - 兰花科创"
        pattern = r"### \d+\.\s+(\d{6})\s+-\s+(.+)"
        matches = re.findall(pattern, content)
        
        for symbol, name in matches:
            candidates.append({
                "symbol": symbol,
                "name": name.strip(),
                "type": "candidate"
            })
            
    except Exception as e:
        print(f"❌ Error parsing candidates file: {e}")
        
    return candidates

def get_realtime_data(targets: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Fetch real-time data for various asset types.
    targets: List of dicts {symbol, asset_type, ...}
    Returns a dictionary keyed by symbol.
    """
    results = {}
    
    # Group by asset type
    stocks = [t['symbol'] for t in targets if t.get('asset_type') in ['stock', 'etf', None]]
    cryptos = [t['symbol'] for t in targets if t.get('asset_type') == 'crypto']
    futures = [t['symbol'] for t in targets if t.get('asset_type') == 'future']
    
    # 1. Stocks/ETFs (Tencent API)
    if stocks:
        try:
            query_list = []
            for s in stocks:
                prefix = ""
                if s.startswith('6') or s.startswith('5') or s.startswith('11') or s.startswith('12'):
                    prefix = "sh" # Shanghai
                else:
                    prefix = "sz" # Shenzhen (0xx, 3xx, 1xx)
                query_list.append(f"{prefix}{s}")
                
            q_str = ",".join(query_list)
            url = f"http://qt.gtimg.cn/q={q_str}"
            resp = requests.get(url, timeout=3)
            
            if resp.status_code == 200:
                for line in resp.text.split(';'):
                    if '=' not in line: continue
                    data_str = line.split('=')[1].strip('"')
                    parts = data_str.split('~')
                    if len(parts) < 30: continue
                    
                    symbol = parts[2]
                    # Map back logic if needed, but here simple symbol matching
                    
                    results[symbol] = {
                        "symbol": symbol,
                        "name": parts[1],
                        "price": float(parts[3]),
                        "pre_close": float(parts[4]),
                        "open": float(parts[5]),
                        "high": float(parts[33]),
                        "low": float(parts[34]),
                        "change_pct": float(parts[32]),
                        "volume": float(parts[36]) * 100,
                        "amount": float(parts[37]) * 10000,
                        "volume_ratio": float(parts[49]) if len(parts)>49 and parts[49] else 0.0,
                        "asset_type": "stock" # Default
                    }
        except Exception as e:
            print(f"❌ Stock API Error: {e}")

    # 2. Crypto (Binance Public API)
    for s in cryptos:
        try:
            # Add USDT if missing and typically traded
            query_sym = s.upper()
            if not query_sym.endswith("USDT") and not query_sym.endswith("BUSD"):
                query_sym += "USDT"
                
            url = f"https://api.binance.com/api/v3/ticker/24hr?symbol={query_sym}"
            resp = requests.get(url, timeout=2)
            if resp.status_code == 200:
                data = resp.json()
                results[s] = {
                    "symbol": s,
                    "name": s.upper(),
                    "price": float(data['lastPrice']),
                    "change_pct": float(data['priceChangePercent']),
                    "volume": float(data['volume']), # Base asset volume
                    "high": float(data['highPrice']),
                    "low": float(data['lowPrice']),
                    "asset_type": "crypto",
                    "volume_ratio": 1.0 # Binance doesn't give VR easily
                }
        except Exception as e:
             # print(f"❌ Crypto Error {s}: {e}")
             pass

    # 3. Futures (Sina Futures via Headers)
    for s in futures:
        try:
            # Sina Future codes often need uppercase for main contracts (e.g. nf_AU0)
            # symbol 'au0' -> 'nf_AU0'
            # Try both raw and uppercase just in case
            sina_code_raw = f"nf_{s}"
            sina_code_upper = f"nf_{s.upper()}"
            
            # Request both codes
            url = f"https://hq.sinajs.cn/list={sina_code_raw},{sina_code_upper}"
            headers = {"Referer": "https://finance.sina.com.cn"}
            resp = requests.get(url, headers=headers, timeout=3)
            
            # Determine which one returned valid data
            valid_parts = None
            
            # Check Upper first (more likely for main contracts like AU0)
            if f'hq_str_{sina_code_upper}="' in resp.text:
                seg = resp.text.split(f'hq_str_{sina_code_upper}="')[1].split('";')[0]
                if len(seg) > 10: valid_parts = seg.split(',')
            
            # Check Raw if Upper failed
            if not valid_parts and f'hq_str_{sina_code_raw}="' in resp.text:
                seg = resp.text.split(f'hq_str_{sina_code_raw}="')[1].split('";')[0]
                if len(seg) > 10: valid_parts = seg.split(',')

            if valid_parts and len(valid_parts) > 10:
                # Sina Future Format: [0]Name, [1]Time, [2]Open, [3]High, [4]Low, [5]LastClose
                # [6]Bid, [7]Ask, [8]Latest Price, [9]Settle, [10]Yesterday Settle, [11]OpenInterest...
                # Note: Index 8 is usually Latest Price. Index 10 is Pre Settle.
                
                price = float(valid_parts[8])
                pre_settle = float(valid_parts[10])
                
                change_pct = 0.0
                if pre_settle > 0:
                    change_pct = (price - pre_settle) / pre_settle * 100
                
                # Volume at 14?
                vol = 0
                if len(valid_parts) > 14:
                     vol = float(valid_parts[14])

                results[s] = {
                    "symbol": s,
                    "name": valid_parts[0] or s,
                    "price": price,
                    "change_pct": round(change_pct, 2),
                    "high": float(valid_parts[3]),
                    "low": float(valid_parts[4]),
                    "volume": vol,
                    "asset_type": "future"
                }
        except Exception as e:
            # print(f"❌ Future Error {s}: {e}")
            pass

    return results

# --- Strategy Configuration ---
# Default rules as fallback
DEFAULT_STRATEGY_RULES = {
    "stock": {
        "change_threshold": 4.0,       # A股大涨大跌阈值
        "volume_ratio_threshold": 2.0, # 量比阈值
        "gap_threshold": 2.0,          # 跳空阈值
        "check_volume": True,
        "check_gap": True
    },
    "etf": {
        "change_threshold": 1.5,       # ETF波动小，阈值降低
        "volume_ratio_threshold": 1.5, # 温和放量即可
        "gap_threshold": 1.0,
        "check_volume": True,
        "check_gap": True
    },
    "crypto": {
        "change_threshold": 5.0,       # Crypto波动大，阈值调高
        "check_volume": False,         # 数据源通常无准确量比
        "check_gap": False             # 7x24小时无开盘跳空概念
    },
    "future": {
        "change_threshold": 0.8,       # 期货含杠杆，微小波动即是大行情
        "check_volume": False,         # 量比数据通常不可用
        "check_gap": False
    }
}

def get_realtime_rules(asset_type: str = 'stock') -> Dict[str, Any]:
    """
    Get realtime monitoring rules, merging logic:
    DB (realtime_intraday) > Default Code
    """
    # 1. Start with defaults
    rules = DEFAULT_STRATEGY_RULES.get(asset_type, DEFAULT_STRATEGY_RULES['stock']).copy()
    
    # 2. If it's stock/general, try to load from DB 'realtime_intraday'
    if asset_type in ['stock', 'etf']: # Currently we only migrated stock params mainly
        try:
            strategy = database.get_strategy_by_slug('realtime_intraday')
            if strategy and strategy.get('params'):
                db_params = strategy['params']
                
                # Careful mapping needed as DB uses flat keys currently
                # We map specifically for what we use in check_strategy
                type_mapping = {
                    'change_threshold': float,
                    'volume_ratio_threshold': float,
                    'gap_threshold': float,
                    'check_volume': lambda x: str(x).lower() == 'true',
                    'check_gap': lambda x: str(x).lower() == 'true'
                }
                
                for key, val_str in db_params.items():
                    if key in type_mapping and key in rules:
                         try:
                             rules[key] = type_mapping[key](val_str)
                         except ValueError:
                             pass
        except Exception as e:
            # Silent fail to default
            pass
            
    return rules

def check_strategy(stock_data: Dict[str, Any], strategy_type: str = "general") -> Dict[str, Any]:
    """
    Check if a stock meets alert criteria based on real-time data AND asset type.
    """
    alerts = []
    status = "normal" # normal, watch, warning
    
    price = stock_data.get('price')
    change_pct = stock_data.get('change_pct')
    volume_ratio = stock_data.get('volume_ratio')
    asset_type = stock_data.get('asset_type', 'stock')
    
    # Get rules for this asset type, with DB override support
    rules = get_realtime_rules(asset_type)
    
    if price is None:
        return {"status": "error", "alerts": []}
        
    # --- Rule 1: Volume Spike (放量异动) ---
    if rules.get('check_volume', True):
        threshold = rules.get('volume_ratio_threshold', 2.0)
        # Condition: Volume Ratio > threshold AND Price is rising
        if volume_ratio and volume_ratio > threshold and change_pct > 0.3:
            alerts.append(f"量比爆发 ({volume_ratio})")
            status = "warning"
        
    # --- Rule 2: Surge/Plunge (急涨急跌) ---
    limit = rules.get('change_threshold', 4.0)
    if change_pct > limit:
        alerts.append(f"大涨 ({change_pct}%)")
        status = "warning"
    elif change_pct < -limit:
        alerts.append(f"大跌 ({change_pct}%)")
        status = "warning"
        
    # --- Rule 3: Gap Opening (跳空高开) ---
    if rules.get('check_gap', True):
        open_price = stock_data.get('open')
        pre_close = stock_data.get('pre_close')
        gap_limit = rules.get('gap_threshold', 2.0)
        
        if open_price and pre_close and pre_close > 0:
            open_pct = (open_price - pre_close) / pre_close * 100
            if open_pct > gap_limit and price >= open_price:
                 alerts.append(f"高开强势 ({open_pct:.1f}%)")
                 status = "warning"

    return {
        "status": status,
        "alerts": alerts,
        "raw_data": stock_data
    }

class MonitorEngine:
    def __init__(self):
        self.config = load_config()
        self.targets = []
        self.last_update = None
        self.cache = {}
        self.ai_cache = {} # Store LLM analysis results: {symbol: "Analysis text..."}
        
    def load_config(self):
        """Proxy to module-level load_config"""
        self.config = load_config()
        return self.config

    def refresh_targets(self):
        """Reload targets from config and latest candidate file"""
        new_targets = []
        
        # 0. Watch List (from config.monitor.watch_list)
        monitor_config = self.config.get('monitor', {})
        if 'watch_list' in monitor_config:
            for w in monitor_config['watch_list']:
                # Detect asset type from config, default stock
                asset_type = w.get('asset_type') or w.get('type') or 'stock'
                if asset_type == 'etf': asset_type = 'etf' # explicit check if needed
                
                new_targets.append({
                    "symbol": w['symbol'],
                    "name": w['name'],
                    "type": "watch",
                    "asset_type": asset_type
                })

        # 1. Portfolio (Merged with higher priority for display)
        # Load from Config (Legacy)
        if 'portfolio' in self.config:
            for p in self.config['portfolio']:
                existing = next((t for t in new_targets if t['symbol'] == p['symbol']), None)
                asset_type = p.get('asset_type') or p.get('type') or 'stock'
                if existing:
                    existing['type'] = 'holding'
                    existing['asset_type'] = asset_type
                else:
                    new_targets.append({
                        "symbol": p['symbol'],
                        "name": p['name'],
                        "type": "holding",
                        "asset_type": asset_type
                    })
        
        # Load from Database (Primary)
        try:
            db_holdings = database.get_all_holdings()
            for h in db_holdings:
                existing = next((t for t in new_targets if t['symbol'] == h['symbol']), None)
                asset_type = h.get('asset_type') or h.get('type') or 'stock'
                
                if existing:
                    existing['type'] = 'holding'
                    existing['asset_type'] = asset_type
                else:
                    new_targets.append({
                        "symbol": h['symbol'],
                        "name": h['name'],
                        "type": "holding",
                        "asset_type": asset_type
                    })
        except Exception as e:
            print(f"⚠️ Error loading holdings from DB: {e}")
                
        # 2. Daily Candidates
        # DISABLED: Explicitly using watch_list only as per user request
        # candidate_file = get_latest_candidate_file()
        # if candidate_file:
        #     candidates = parse_candidates_from_md(candidate_file)
        #     # Avoid duplicates
        #     existing_symbols = {t['symbol'] for t in new_targets}
        #     for c in candidates:
        #         if c['symbol'] not in existing_symbols:
        #             new_targets.append(c)
        
        self.targets = new_targets
        print(f"🎯 Watch list updated: {len(self.targets)} targets loaded.")
        return len(self.targets)

    def run_ai_analysis_for_target(self, symbol: str) -> str:
        """
        Run deep AI analysis for a specific target.
        Combines History (Indicators) + Realtime Data.
        """
        print(f"🧠 Running AI Analysis for {symbol}...")
        
        # 1. Find target info
        target = next((t for t in self.targets if t['symbol'] == symbol), None)
        if not target:
            return "Target not found"
            
        # 2. Get Realtime Data
        # Must pass full target info to get_realtime_data because it needs asset_type now
        rt_dict = get_realtime_data([target])
        rt_data = rt_dict.get(symbol)
        if not rt_data:
            return "Realtime data unavailable"
            
        # 3. Get Historical Data & Indicators
        try:
            start_date = calculate_start_date(120)
            # Use Dispatcher
            df = fetch_data_dispatcher(symbol, target.get('asset_type', 'stock'), start_date)
            
            if df is None or df.empty:
                return "Historical data unavailable"
            
            df = calculate_indicators(df)
            tech_data = get_latest_metrics(df) # Based on yesterday close
            if not tech_data:
                return "Indicator calculation failed"
            
            # Apply ETF-specific scoring if asset_type is 'etf'
            if target.get('asset_type') == 'etf':
                tech_data = apply_etf_score(tech_data)
        except Exception as e:
            print(f"❌ Error fetching history for {symbol}: {e}")
            return f"Data Error: {str(e)}"
            
        # 3.5 Get Market Index (Context)
        market_index = self.get_market_index()
        
        # Inject Market Context into realtime_data
        rt_data['market_index_price'] = market_index['price']
        rt_data['market_index_change'] = market_index['change_pct']

        # 4. Call LLM
        # Determine provider config
        provider = self.config['api'].get('provider', 'openai')
        api_config_key = f"api_{provider}"
        api_config = self.config.get(api_config_key, self.config['api'])
        
        try:
            # Pass asset_type info to LLM
            # target already includes 'asset_type' from refresh_targets logic
            analysis = generate_analysis(
                stock_info=target,
                tech_data=tech_data,
                api_config=api_config,
                analysis_type="realtime",
                realtime_data=rt_data
            )
            # Update cache
            self.ai_cache[symbol] = analysis
            return analysis
        except Exception as e:
            print(f"❌ LLM Error: {e}")
            return f"AI Error: {str(e)}"

    def run_check(self):
        """Execute one round of checks"""
        if not self.targets:
            self.refresh_targets()
            
        # Pass full targets list to get_realtime_data
        realtime_data = get_realtime_data(self.targets)
        
        results = []
        for target in self.targets:
            symbol = target['symbol']
            data = realtime_data.get(symbol)
            
            if data:
                check_res = check_strategy(data)
                
                # Combine info
                item = {
                    "symbol": symbol,
                    "name": target['name'],
                    "type": target['type'],
                    "asset_type": target.get('asset_type', 'stock'),
                    "price": data.get('price'),
                    "change_pct": data.get('change_pct'),
                    "volume_ratio": data.get('volume_ratio'),
                    "status": check_res['status'],
                    "alerts": check_res['alerts'],
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                    "ai_analysis": self.ai_cache.get(symbol, None) # Attach cached AI result
                }
                results.append(item)
            else:
                # No data (halted or error)
                results.append({
                    "symbol": symbol,
                    "name": target['name'],
                    "type": target['type'],
                    "status": "offline",
                    "alerts": ["无数据"],
                    "price": 0,
                    "change_pct": 0,
                    "volume_ratio": 0
                })
                
        # Sort Rule:
        # 1. Status == Warning (Highest priority)
        # 2. Type == 'holding' (Second priority)
        # 3. Change Pct (desc)
        results.sort(key=lambda x: (
            0 if x['status'] == 'warning' else 1,  # Warning first
            0 if x['type'] == 'holding' else 1,    # Holdings next
            -x['change_pct']                       # High gainers next
        ))
        
        self.cache = results
        self.last_update = datetime.now()
        return results

    def get_market_index(self):
        """Get simple index status for header using Tencent API"""
        try:
            # sh000001 is the code for Shanghai Composite
            url = "http://qt.gtimg.cn/q=s_sh000001"
            resp = requests.get(url, timeout=2)
            
            if resp.status_code == 200:
                # v_s_sh000001="1~上证指数~000001~3050.55~30.45~1.01~2500000~30000000";
                # Indices: 1:Name, 3:Price, 4:Change, 5:ChangePct, 6:Volume, 7:Amount
                content = resp.text
                if '=' in content:
                    data = content.split('=')[1].strip('"').split('~')
                    if len(data) > 5:
                        return {
                            "name": data[1],
                            "price": float(data[3]),
                            "change_val": float(data[4]), # +30.45
                            "change_pct": float(data[5]), # +1.01
                            "amount": float(data[7]) * 10000 # Usually in Wan
                        }
            
            # Fallback
            return {"name": "上证指数", "price": 0, "change_pct": 0}
        except Exception as e:
            print(f"⚠️ Index fetch error: {e}")
            return {"name": "上证指数", "price": 0, "change_pct": 0}

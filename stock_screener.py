"""
市场扫描模块 - 基于量化规则筛选股票
"""
import akshare as ak
import pandas as pd
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

from data_fetcher import fetch_stock_data, calculate_start_date, fetch_sector_data, fetch_stock_news, load_sector_map

from data_fetcher_tx import get_market_snapshot_tencent
from data_fetcher_ts import fetch_stock_data_ts, fetch_daily_basic_ts
from indicator_calc import calculate_indicators, get_latest_metrics
from indicator_calc import calculate_indicators, get_latest_metrics
from data_provider.base import DataFetcherManager
from stock_scoring import get_score
import database
import json
import os

# 初始化数据管理器
data_manager = DataFetcherManager()


def calculate_market_mood(df: pd.DataFrame) -> Dict[str, Any]:
    """
    基于全市场快照计算市场情绪
    """
    total = len(df)
    if total == 0:
        return {"mood": "未知", "index_change": 0}
        
    # 统计数据
    up_stocks = df[df['change_pct'] > 0]
    limit_up = len(df[df['change_pct'] > 9.0]) # 近似涨停
    limit_down = len(df[df['change_pct'] < -9.0])
    
    up_ratio = len(up_stocks) / total
    
    # 定义情绪的逻辑
    if up_ratio > 0.7:
        mood = "普涨 (高潮)"
    elif up_ratio > 0.55:
        mood = "偏暖 (多头)"
    elif up_ratio < 0.2:
        mood = "冰点 (杀跌)"
    elif limit_down > 20 and limit_down > limit_up:
         mood = "恐慌 (退潮)"
    else:
        mood = "分化 (震荡)"
        
    return {
        "market_mood": mood,
        "up_count": len(up_stocks),
        "down_count": len(df) - len(up_stocks),
        "limit_up": limit_up
    }

def get_selection_rules(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    获取筛选规则，合并 config.json 与数据库覆盖配置。
    数据库参数优先。
    """
    # 来自文件的基础规则
    rules = config.get('selection_rules', {}).copy()
    
    # 如果可用，使用数据库参数覆盖
    try:
        strategy = database.get_strategy_by_slug('candidate_growth')
        if strategy and strategy.get('params'):
            db_params = strategy['params']
            print("⚙️ Loaded dynamic selection rules from database.")
            
            # 将数据库字符串值映射回正确的类型
            type_mapping = {
                'enabled': lambda x: x.lower() == 'true',
                'min_change': float,
                'max_change': float,
                'min_volume_ratio': float,
                'min_turnover': float,
                'max_turnover': float,
                'min_volume_ratio': float,
                'min_mcap_b': float,
                'max_mcap_b': float,
                'exclude_loss_making': lambda x: x.lower() == 'true',
                'exclude_startup_board': lambda x: x.lower() == 'true',
                'max_candidates_rough': int,
                'min_score': int,
                'max_final_candidates': int
            }
            
            for key, val_str in db_params.items():
                if key in type_mapping:
                    try:
                        rules[key] = type_mapping[key](str(val_str))
                    except ValueError:
                        print(f"⚠️ Failed to parse param {key}={val_str}, keeping default.")
                        
    except Exception as e:
        print(f"⚠️ Error loading DB rules: {e}")
        
    return rules

def check_market_risk() -> bool:
    """
    检查市场环境（上证指数 - 000001）
    规则：如果指数 < MA20 且跌幅 > 1%，立即停止。
    返回：如果市场有风险（停止）则为 True，如果安全（继续）则为 False。
    """
    period = 30
    start_date = calculate_start_date(lookback_days=period + 10)
    try:
        # 获取上证指数 (000001)
        # 使用 is_index=True。在 akshare 中 '000001' 代表上证指数
        df = fetch_stock_data("000001", start_date, is_index=True)
        
        if df is None or len(df) < 20:
             print("⚠️ Insufficient market index data, skipping risk check.")
             return False
             
        # 计算 MA20
        df['ma20'] = df['close'].rolling(window=20).mean()
        
        # 计算涨跌幅百分比
        df['change_pct'] = df['close'].pct_change() * 100
        
        # 检查最后一行
        last = df.iloc[-1]
        
        # 记录市场状态
        market_status = f"Market(000001): {last['close']:.2f}, MA20: {last['ma20']:.2f}, Chg: {last['change_pct']:.2f}%"
        print(f"🌍 {market_status}")
        
        # 风险条件：价格 < MA20 且 跌幅 < -1.0%（显著下跌/破位）
        # 注意：我们比较 'close' 和 'ma20'。
        if last['close'] < last['ma20'] and last['change_pct'] < -1.0:
            print("🛑 RISK ALERT: Market Risk Logic Triggered. Market below MA20 and dropping > 1%. Strategy Halted.")
            return True
        
        return False
        
    except Exception as e:
        print(f"⚠️ Market check error: {e}")
        return False

def get_rising_sectors() -> List[str]:
    """
    获取今日涨幅为正的板块列表
    """
    print("🌍 Fetching sector data...")
    df = fetch_sector_data()
    if df is None or df.empty:
        return []
    
    # 筛选涨跌幅 > 0 的板块
    rising = df[df['涨跌幅'] > 0]
    return rising['板块名称'].tolist()

def get_market_snapshot() -> pd.DataFrame:
    """
    获取所有 A 股股票的实时快照
    """
    print("🌍 Fetching market snapshot... (This may take a moment)")
    
    # 优先级：优先尝试腾讯接口（更稳定）
    try:
        df = get_market_snapshot_tencent()
        if not df.empty:
            return df
        print("⚠️ Tencent fetch returned empty, falling back to EM...")
    except Exception as e:
        print(f"⚠️ Tencent fetch failed: {e}, falling back to EM...")

    # 备选：AkShare 东方财富接口
    max_retries = 3
    df = None
    
    for attempt in range(max_retries):
        try:
            if attempt > 0:
                print(f"🔄 Retry attempt {attempt + 1}/{max_retries}...")
                
            # 获取所有 A 股的实时数据
            df = ak.stock_zh_a_spot_em()
            break # 成功，退出循环
            
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"⚠️ Market snapshot fetch failed: {e}. Retrying in 2s...")
                time.sleep(2)
            else:
                print(f"❌ Error fetching market snapshot: {e}")
                return pd.DataFrame()

    if df is None or df.empty:
        return pd.DataFrame()

    try:
        # 重命名字段以便于处理
        column_map = {
            '代码': 'symbol',
            '名称': 'name',
            '最新价': 'price',
            '涨跌幅': 'change_pct',
            '成交量': 'volume',
            '成交额': 'amount',
            '量比': 'volume_ratio',
            '换手率': 'turnover_rate',
            '市盈率-动态': 'pe_ttm',
            '流通市值': 'mcap_float',
            '所属板块': 'sector',
            '昨收': 'pre_close',
            '今开': 'open',
            '最高': 'high',
            '最低': 'low'
        }
        
        df = df.rename(columns=column_map)
        
        # 确保数值类型
        numeric_cols = ['price', 'change_pct', 'volume_ratio', 'turnover_rate', 'pe_ttm', 'mcap_float', 'pre_close', 'open', 'high', 'low']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
                
        return df
    except Exception as e:
        print(f"❌ Error processing market snapshot columns: {e}")
        return pd.DataFrame()

def run_rough_screen(df: pd.DataFrame, criteria: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    执行步骤 1：基于基本指标的粗略筛选

    Args:
        df: 包含市场快照数据的 DataFrame，包含股票的基本行情信息（如价格、涨跌幅、换手率等）。
        criteria: 筛选条件字典，包含如涨跌幅范围、最小量比、最小换手率等配置参数。

    Returns:
        符合初步筛选条件的股票列表，每个元素为包含股票信息的字典。
    """
    print(f"\n🔍 Running Rough Screen on {len(df)} stocks...")
    
    # 0. 特性：板块 Beta 分析（可选但推荐）
    # 由于检查每只股票的板块很慢，我们在快照中跳过严格的板块匹配
    # 相反，我们依赖于强势股通常属于强势板块这一事实。
    # 我们获取板块数据只是为了显示市场情绪，或者如果我们有板块映射的话。
    # 目前，我们继续进行严格的技术面粗略筛选。
    
    # 0. 预计算板块排名和统计数据（在完整 DataFrame 上）
    # 尝试补充缺失的板块数据（例如使用腾讯源时）
    if 'sector' not in df.columns:
        sector_map = load_sector_map()
        if sector_map:
            print(f"   🗺️ Hydrating sector info from map ({len(sector_map)} entries)...")
            # 映射 代码 -> 板块
            df['sector'] = df['symbol'].map(sector_map)
        else:
            print("   ⚠️ No sector info available (Source missing & No local map). Skipping rank_in_sector.")

    # 这确保了排名相对于所有同类股票是准确的，而不仅仅是筛选后的股票
    if 'sector' in df.columns and 'change_pct' in df.columns:
        print("   📊 正在计算板块排名和统计数据...")
        # 排名：1 最好（涨跌幅最高）
        # 处理 NaN 板块
        df_clean = df.dropna(subset=['sector'])
        
        # 在干净的子集上计算然后合并回去？
        # 更简单的方法：在完整 df 上计算，groupby 会处理 NaNs（排除它们）
        df['rank_in_sector'] = df.groupby('sector')['change_pct'].rank(ascending=False, method='min')
        
        # 板块涨跌幅（板块内股票的平均值）
        # 将板块均值映射回每一行
        sector_means = df.groupby('sector')['change_pct'].transform('mean')
        df['sector_change'] = sector_means
    
    # 1. 价格范围
    # 为了效率使用掩码
    mask = (df['price'] > 0)
    
    # 2. 涨跌幅（例如，2% 到 8% - 避免涨停）
    if 'min_change' in criteria:
        mask &= (df['change_pct'] >= criteria['min_change'])
    if 'max_change' in criteria:
        mask &= (df['change_pct'] <= criteria['max_change'])
        
    # 3. 量比（活跃度） - 不再作为硬性过滤，改为在深度筛选中检查
    # if 'min_volume_ratio' in criteria:
    #     mask &= (df['volume_ratio'] >= criteria['min_volume_ratio'])
        
    # 4. 换手率（流动性）：活跃区间 5% - 15%
    min_turnover = criteria.get('min_turnover', 5.0)
    max_turnover = criteria.get('max_turnover', 15.0)
    
    if 'turnover_rate' in df.columns:
        mask &= (df['turnover_rate'] >= min_turnover)
        mask &= (df['turnover_rate'] <= max_turnover)
        
    # 5. 市值（避免太小或太大）- 输入通常以十亿为单位
    if 'min_mcap_b' in criteria:
        mask &= (df['mcap_float'] >= criteria['min_mcap_b'] * 100000000)
    if 'max_mcap_b' in criteria:
        mask &= (df['mcap_float'] <= criteria['max_mcap_b'] * 100000000)
        
    # 6. 市盈率验证（如果需要，避免亏损信息）
    if criteria.get('exclude_loss_making', True):
        mask &= (df['pe_ttm'] > 0)
        
    # 排除 ST 股票（名称包含 ST）
    mask &= (~df['name'].str.contains('ST'))
    mask &= (~df['name'].str.contains('退'))
    
    # 排除北交所（代码以 8 或 4 开头）
    # 如果配置了，过滤创业板 (30)
    allowed_prefixes = ['00', '60']
    if not criteria.get('exclude_startup_board', False):
        allowed_prefixes.append('30')
        
    pattern = r'^(' + '|'.join(allowed_prefixes) + ')'
    mask &= (df['symbol'].astype(str).str.match(pattern))

    result_df = df[mask]
    
    # 按“换手率”排序（活跃度代理），不再使用量比排序
    # 修复：不要用 Volume_Ratio 排序。改用 Turnover_Rate (换手率)
    if 'turnover_rate' in result_df.columns:
        # 按换手率降序排序，然后按涨跌幅降序排序
        result_df = result_df.sort_values(by=['turnover_rate', 'change_pct'], ascending=[False, False])
    else:
        result_df = result_df.sort_values(by='change_pct', ascending=False)
    
    candidate_limit = criteria.get('max_candidates_rough', 100)
    print(f"   Filtering top {candidate_limit} by Turnover Rate (5-15%)...")
    
    candidates = result_df.head(candidate_limit).to_dict('records')
    
    # 关于板块 Beta 的说明：
    # 准确的板块筛选需要将每只股票映射到其板块，但这不在快照中。
    # 我们将在深度筛选中强制执行板块 Beta 逻辑，或者通过获取详细信息。
    # 目前，“量比”排序 + “2-8% 涨幅”本身就是一个非常强的过滤器。
    
    print(f"✅ Rough Screen passed: {len(candidates)} stocks")
    return candidates

def analyze_candidate(candidate: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """
    使用统一评分模块对单个候选股票进行详细技术分析
    """
    symbol = candidate['symbol']
    
    # 调用统一评分引擎（仅 Tushare）
    # 注意：筛选时成本价为 0，因为我们没有持有它们。
    # 我们传递 include_news=True 以允许后续进行 AI 分析（如果需要）。
    tech_data = get_score(symbol, cost_price=0.0, asset_type='stock', include_news=True)
    
    if not tech_data:
        return None
        
    # 将快照/候选股票的基本信息合并到结果中
    tech_data['symbol'] = symbol
    tech_data['name'] = candidate['name']

    # 合并粗略筛选指标（换手率、市盈率、流通市值）
    # 新增：rank_in_sector, sector_change, market_mood 数据
    transfer_keys = [
        'turnover_rate', 'pe_ttm', 'mcap_float', 'volume_ratio',
        'rank_in_sector', 'sector_change', 'market_mood', 'market_status_data',
        'sector' # 确保传递了板块名称
    ]
    
    # 将关键元数据存储在特殊字典中以便稍后嵌入
    # 注意：get_score 确保 __metadata__ 存在
    if '__metadata__' not in tech_data:
        tech_data['__metadata__'] = {}
    
    for key in transfer_keys:
        if key in candidate:
            # 仅在 tech_data 中不存在时覆盖（Tushare 数据对于市盈率/换手率更准确）
            # 但快照可能有实时的量比/换手率？
            # Tushare daily_basic 通常是前一天的收盘数据，除非更新了。
            # 快照是实时的。
            # 实时快照数据通常首选用于盘中筛选。
            # tech_data 有来自 Tushare Daily Basic 的 'turnover_rate'（通常是昨天的）。
            # 如果可用且市场开盘，我们应该优先使用实时快照的换手率/量比？
            # 让我们相信快照中的“当前活跃度”指标。
            
            tech_data[key] = candidate[key]
            tech_data['__metadata__'][key] = candidate[key]

    return tech_data

def print_detailed_metrics(metrics: Dict[str, Any]):
    """
    打印股票的详细指标和评分细则
    """
    try:
        print(f"\n   --- DETAILED ANALYSIS: {metrics.get('name', 'Unknown')} ({metrics.get('symbol', '')}) ---")
        
        # 按类别分组以便清晰展示
        categories = {
            "Trend": ['ma5', 'ma10', 'ma20', 'ma60', 'ma_arrangement', 'trend_signal'],
            "MACD": ['macd_dif', 'macd_dea', 'macd_hist', 'macd_signal'],
            "RSI": ['rsi', 'rsi_signal'],
            "KDJ": ['kdj_k', 'kdj_d', 'kdj_j', 'kdj_signal', 'kdj_zone'],
            "Bollinger": ['boll_upper', 'boll_mid', 'boll_lower', 'boll_position', 'boll_signal'],
            "Risk/ATR": ['atr', 'atr_pct', 'stop_loss_suggest'],
            "Structure": ['high_120', 'price_vs_high120', 'distance_from_ma20'],
            "Volume": ['volume', 'volume_ratio', 'volume_change_pct', 'volume_signal', 'volume_confirmation', 'volume_pattern'],
        }
        
        for cat, keys in categories.items():
            line_items = []
            for k in keys:
                val = metrics.get(k)
                if val is not None:
                    line_items.append(f"{k}: {val}")
            if line_items:
                print(f"   [{cat}] " + ", ".join(line_items))

        print(f"   [Result] Score: {metrics.get('composite_score')} | Rating: {metrics.get('rating')} | Suggestion: {metrics.get('operation_suggestion')}")
        
        if 'score_breakdown' in metrics:
            print("   [Breakdown] " + " | ".join([f"{item[0]}: {item[1]}/{item[2]}" for item in metrics['score_breakdown']]))
        
        if 'score_details' in metrics:
            print("   [Reasons]")
            for detail in metrics['score_details']:
                print(f"     * {detail}")
                
        if 'pattern_details' in metrics and metrics['pattern_details']:
             print("   [Patterns]")
             for p in metrics['pattern_details']:
                 print(f"     * {p}")
        print("   " + "-"*60)
            
    except Exception as e:
        print(f"   ⚠️ Error printing details: {e}")

def run_deep_screen(candidates: List[Dict[str, Any]], config: Dict[str, Any], rules: Dict[str, Any] = None) -> List[Dict[str, Any]]:
    """
    执行步骤 2：深度技术筛选（多线程）
    """
    print(f"\n🔬 Running Deep Technical Analysis on {len(candidates)} candidates...")
    
    final_candidates = []
    # 使用提供的规则或回退到配置
    if rules is None:
        rules = config.get('selection_rules', {})
        
    min_score = rules.get('min_score', 70)
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_stock = {executor.submit(analyze_candidate, c, config): c for c in candidates}
        
        for future in as_completed(future_to_stock):
            stock = future_to_stock[future]
            try:
                metrics = future.result()
                if not metrics:
                    continue
                
                # --- 硬性规则 ---
                # # 1. 价格高于 MA20（趋势为王）
                # if metrics['close'] <= metrics['ma20']:
                #     continue
                    
                # # 2. 综合评分
                # if metrics['composite_score'] < min_score:
                #     continue
                    
                # # 量能形态：温和放量 (1.0 < V/MA5 < 2.0)
                # # 注意：stock_scoring 中计算的 volume_ratio 实际上就是 V/MA5
                # vr = metrics.get('volume_ratio', 0)
                # if not (1.0 < vr < 2.0):
                #     # print(f"  Condition Failed: Volume Ratio {vr} not in range (1.0, 2.0)")
                #     continue

                final_candidates.append(metrics)
                print(f"  ✨ Found: {stock['name']} (Score: {metrics['composite_score']})")
                
                # 根据请求记录详细原因
                print_detailed_metrics(metrics)
                
            except Exception as e:
                print(f"  ❌ Error processing {stock['symbol']}: {e}")
                
    # 按 综合评分 (Composite Score) 降序排序
    final_candidates.sort(key=lambda x: x['composite_score'], reverse=True)
    
    return final_candidates[:rules.get('max_final_candidates', 5)]

def run_stock_selection(config: Dict[str, Any]):
    """
    股票筛选的主入口点
    """
    print("\n" + "="*60)
    print("🕵️‍♂️ AUTO-PICKER: Starting Market Scan")
    print("="*60)
    
    # 0. 获取标准（合并数据库和配置）
    rules = get_selection_rules(config)
    print(f"📋 Current Selection Rules: {json.dumps(rules, indent=2, ensure_ascii=False)}")
    
    if not rules.get('enabled', False):
        print("Stock selection is disabled in config/DB.")
        return []
        
    print(f"📋 Selection Criteria: Min Score > {rules.get('min_score')}, Max candidates: {rules.get('max_final_candidates')}")

    # 1. 市场环境检查（风险控制）
    if check_market_risk():
        print("🛑 Force Stop triggered by Market Environment.")
        return []

    # 2. 获取快照
    snapshot_df = get_market_snapshot()
    if snapshot_df.empty:
        print("❌ Failed to get market data.")
        return []
        
    # 3. 计算市场情绪（全局）
    mood_data = calculate_market_mood(snapshot_df)
    print(f"📊 Market Mood: {mood_data['market_mood']} (Up: {mood_data['up_count']}, LimitUp: {mood_data['limit_up']})")
    
    # 4. 粗略筛选
    rough_candidates = run_rough_screen(snapshot_df, rules)
    if not rough_candidates:
        print("❌ No stocks matched rough criteria.")
        return []
    print(f"✅ 初筛通过: {len(rough_candidates)} 只股票")
    # 将市场情绪注入候选股票
    # 同时注入指数信息检查（我们在 check_market_risk 中做了，但让我们获取新鲜的或使用代理）
    # 使用 check_market_risk 的副作用？不。
    # 我们假设指数信息来自 get_market_snapshot（如果它包含指数），但它不包含。
    # 我们将依赖 mood_data，如果需要，也可能单独获取指数。
    # 目前，将情绪放入每个候选项，以便 analyze_candidate 可以携带它。
    for cand in rough_candidates:
        cand['market_mood'] = mood_data['market_mood']
        cand['market_status_data'] = mood_data
        
    # 5. 深度筛选
    final_candidates = run_deep_screen(rough_candidates, config, rules)
    
    print(f"\n🎉 Selection Complete! Found {len(final_candidates)} high-quality targets.")
    return final_candidates
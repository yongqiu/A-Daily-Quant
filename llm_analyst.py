"""
LLM Analysis Module - Generates trading recommendations using AI
Implements strict risk management framework
Supports multiple LLM providers: OpenAI-compatible, Gemini (Google Gen AI SDK)
"""
from openai import OpenAI
from typing import Dict, Any
import os

try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False


import database
from data_fetcher import fetch_intraday_data, fetch_cyq_data
from indicator_calc import analyze_intraday_pattern, process_cyq_data
from jinja2 import Template

def get_prompt_from_db(slug: str, context: Dict[str, Any]) -> str:
    """
    Fetch prompt template from database and format with context using Jinja2
    """
    strategy = database.get_strategy_by_slug(slug)
    if not strategy or not strategy.get('template_content'):
        print(f"⚠️ Strategy {slug} not found in DB or empty. Fallback needed.")
        return None
        
    try:
        # DB content is now repaired to valid Jinja2 syntax by repair_db_prompts.py
        template_str = strategy['template_content']
        
        # Create Jinja2 template and render
        template = Template(template_str)
        return template.render(**context)
        
    except Exception as e:
        print(f"❌ Error generating prompt for {slug}: {e}")
        return None
        

    except Exception as e:
        print(f"❌ Error generating prompt for {slug}: {e}")
        return None

def create_risk_prompt(stock_info: Dict[str, Any], tech_data: Dict[str, Any]) -> str:
    """
    Create a strict RISK-FOCUSED prompt for existing HOLDINGS.
    NOW: Tries to load from DB 'stock_holding_risk', else fallback.
    """
    print(f"股票：{stock_info['symbol']} - {stock_info['name']} AI 分析（个股风控 - Strategy）")
    
    # 1. Fetch dynamic params for context optimization
    context_params = {}
    try:
        strategy = database.get_strategy_by_slug('stock_holding_risk')
        if strategy and strategy.get('params'):
            # Pass these params to Jinja2 context so prompt can use them
            # e.g. {{ params.risk_sensitivity }}
            context_params = strategy['params']
            
            # Logic hook: If 'enable_news_analysis' is explicitly false in DB, we could hide news
            # But currently we let the Prompt Template decide how to use the variable
    except Exception:
        pass

    db_prompt = get_prompt_from_db('stock_holding_risk', {
        'stock_info': stock_info,
        'tech_data': tech_data,
        'params': context_params  # Expose params to template
    })
    
    if db_prompt:
        return db_prompt

    # Fallback (Hardcoded)
    prompt = f"""作为严格的A股风险控制官... (DB Fetch Failed)
    请分析 {stock_info['symbol']} ..."""
    return prompt


def create_crypto_prompt(stock_info: Dict[str, Any], tech_data: Dict[str, Any]) -> str:
    """
    Create a VOLATILITY-FOCUSED prompt for CRYPTO.
    """
    print(f"Crypto: {stock_info['symbol']} - {stock_info['name']} AI Analysis")
    
    # Calculate derived stats for context if needed
    # (The simple template mostly uses raw tech_data values)
    
    db_prompt = get_prompt_from_db('crypto_holding', {
        'stock_info': stock_info,
        'tech_data': tech_data
    })
    
    if db_prompt:
        return db_prompt
        
    return "DB Error: crypto_holding prompt not found."

def create_future_prompt(stock_info: Dict[str, Any], tech_data: Dict[str, Any]) -> str:
    """
    Create a LEVERAGE-FOCUSED prompt for FUTURES.
    """
    print(f"Future: {stock_info['symbol']} - {stock_info['name']} AI Analysis")
    
    db_prompt = get_prompt_from_db('future_holding', {
        'stock_info': stock_info,
        'tech_data': tech_data
    })
    
    if db_prompt:
        return db_prompt
        
    return "DB Error: future_holding prompt not found."


def create_etf_holding_prompt(stock_info: Dict[str, Any], tech_data: Dict[str, Any]) -> str:
    """
    Create a LONG-TERM FOCUSED prompt for ETFs.
    NOW: Tries to load from DB 'etf_holding_steady'.
    """
    print(f"股票：{stock_info['symbol']} - {stock_info['name']} AI 分析（ETF定投 - Strategy）")
    
    db_prompt = get_prompt_from_db('etf_holding_steady', {
        'stock_info': stock_info,
        'tech_data': tech_data
    })
    
    if db_prompt:
        return db_prompt
        
    # Fallback
    return "DB Error: etf_holding_steady prompt not found."


def create_speculator_prompt(stock_info: Dict[str, Any], tech_data: Dict[str, Any]) -> str:
    """
    Create a 'Speculator' (游资) style prompt based on DB template 'speculator_mode'.
    """
    # 1. Prepare Data for Computed Context
    price = tech_data.get('close', 0)
    
    # Position Logic
    ma5 = tech_data.get('ma5')
    ma20 = tech_data.get('ma20')
    ma5_pos = "上方" if ma5 and price > ma5 else "下方"
    ma20_pos = "上方" if ma20 and price > ma20 else "下方"
    
    # Resistance/Support
    res = tech_data.get('resistance', tech_data.get('pivot_point', price * 1.1)) # Fallback
    sup = tech_data.get('support', tech_data.get('s1', price * 0.9))
    
    # Extract strengths from score_details
    details = tech_data.get('score_details', [])
    # Filter only "✅" items
    strengths = [d.replace('✅ ', '') for d in details if '✅' in d]
    strength_str = ", ".join(strengths[:3]) if strengths else "暂无明显优势"
    
    computed = {
        'ma5_pos': ma5_pos,
        'ma20_pos': ma20_pos,
        'res': f"{res:.2f}",
        'sup': f"{sup:.2f}",
        'strength_str': strength_str
    }
    
    db_prompt = get_prompt_from_db('speculator_mode', {
        'stock_info': stock_info,
        'tech_data': tech_data,
        'computed': computed
    })
    
    if db_prompt:
        return db_prompt

    return "DB Error: speculator_mode prompt not found."

def create_opportunity_prompt(stock_info: Dict[str, Any], tech_data: Dict[str, Any]) -> str:
    """
    Create an OPPORTUNITY-FOCUSED prompt for STOCK CANDIDATES.
    NOW: Checks if 'rank_in_sector' exists to switch to Speculator Mode.
    """
    # Auto-switch to Speculator Mode if we have enhanced data (Sector Rank)
    if 'rank_in_sector' in tech_data:
        return create_speculator_prompt(stock_info, tech_data)

    db_prompt = get_prompt_from_db('candidate_growth', {
        'stock_info': stock_info,
        'tech_data': tech_data
    })
    
    if db_prompt:
        return db_prompt

    return "DB Error: candidate_growth prompt not found."


def create_realtime_prompt(stock_info: Dict[str, Any], history_data: Dict[str, Any], realtime_data: Dict[str, Any]) -> str:
    """
    Create a REAL-TIME ACTION prompt.
    NOW: Tries to load from DB 'realtime_intraday'.
    """
    db_prompt = get_prompt_from_db('realtime_intraday', {
        'stock_info': stock_info,
        'tech_data': history_data,
        'realtime_data': realtime_data
    })
    
    if db_prompt:
        return db_prompt

    return "DB Error: realtime_intraday prompt not found."



def create_intraday_prompt(
    stock_info: Dict[str, Any], 
    tech_data: Dict[str, Any], 
    realtime_data: Dict[str, Any],
    market_context: Dict[str, Any] = None
) -> str:
    """
    Create a specific INTRADAY prompt for real-time monitoring.
    Uses 'intraday_monitor' template provided by User.
    """
    print(f"Intraday: {stock_info['symbol']} - {stock_info['name']}")
    
    # --- Prepare Data ---
    
    # 1. Real-time Basic
    price = realtime_data.get('price', 0)
    change_pct = realtime_data.get('change_pct', 0)
    change_desc = f"{change_pct}%"
    if change_pct > 0: change_desc = f"+{change_pct}%"
    
    vwap = realtime_data.get('vwap', 0)
    
    # 2. Market Context (from market_context or fallback)
    if not market_context:
        market_context = {}
    
    print(f"🔍 [create_intraday_prompt] market_context = {market_context}")
        
    index_name = market_context.get('market_index', {}).get('name', '大盘')
    index_change = market_context.get('market_index', {}).get('change_pct', 0)
    index_trend = market_context.get('market_index', {}).get('trend', '横盘')
    index_desc = f"{index_change}% (分时走势：{index_trend})"
    
    print(f"🔍 [create_intraday_prompt] index_desc = {index_desc}")
    
    sector_name = market_context.get('sector_info', {}).get('name', 'N/A')
    sector_change = market_context.get('sector_info', {}).get('change_pct', 0)
    # Mock rank for now
    sector_desc = f"[{sector_name}] 板块 (涨跌: {sector_change}%)"
    
    sentiment_limit_up = market_context.get('sentiment', {}).get('limit_up_count', 'N/A')
    sentiment_desc = f"连板高度 {sentiment_limit_up} 板"
    
    # 3. Technical & Real-time Details
    
    # Deviate from VWAP (乖离率)
    deviate_msg = "分时均价线附近"
    if vwap > 0:
        deviate = (price - vwap) / vwap * 100
        if deviate > 2: deviate_msg = "偏离均价线过远 (上方悬浮)"
        elif deviate < -2: deviate_msg = "偏离均价线过远 (下方超跌)"
        elif price < vwap: deviate_msg = "承压于分时均价线"
        elif price > vwap: deviate_msg = "运行于分时均价线上方"
        
    # Volume Ratio & Status
    vol_ratio = realtime_data.get('volume_ratio', 0)
    vol_status = "平量震荡"
    if vol_ratio > 1.5: vol_status = "放量拉升" if change_pct > 0 else "放量下跌"
    elif vol_ratio < 0.8: vol_status = "缩量震荡"
    
    # Order Flow (WeiBi)
    weibi = realtime_data.get('weibi', 0)
    flow_desc = "买卖均衡"
    if weibi > 30: flow_desc = f"主动买盘占优 (委比 {weibi}%)"
    elif weibi < -30: flow_desc = f"主动卖盘远大于主动买盘 (委比 {weibi}%)"
    else: flow_desc = f"盘口委比 {weibi}%"
    
    # Support/Resistance (Yesterday or Pivot)
    last_close = tech_data.get('close', price) # Fallback
    support_price = tech_data.get('s1', last_close * 0.98)
    res_price = tech_data.get('r1', last_close * 1.02)
    pressure_desc = f"支撑位 {support_price:.2f}, 压力位 {res_price:.2f}"
    
    # Yesterday Score
    score = tech_data.get('composite_score', 'N/A')

    # Construct the Prompt
    prompt = f"""# Role
你是一名资深A股短线操盘手，擅长捕捉分时博弈与情绪拐点。当前目标：{stock_info['name']} ({stock_info['symbol']})。

# Market Context (大环境)
- 大盘指数: {index_desc}
- 板块热度: {sector_desc}
- 市场情绪: {sentiment_desc}

# Technical & Real-time Data (实时多空)
- 现价: {price} ({change_desc})
- 分时位置: {deviate_msg} (VWAP: {vwap})
- 成交异动: 量比 {vol_ratio} ({vol_status})
- 关键点位: {pressure_desc}
- 筹码博弈: {flow_desc}

# Strategy Rules (执行准则)
1. 严禁在分时均价线下方左侧买入。
2. 若缩量跌破 [{support_price:.2f}]，必须无条件触发止损。
3. 若放量突破 [{res_price:.2f}] 压力位，视为转强信号。

# Task
结合昨日技术形态 (Score: {score}) 与当前盘口多空力量对比，判断当前是“诱多陷阱”还是“缩量洗盘”？给出即时动作。

# Output (JSON)
{{
  "market_mood": "恐慌/观望/修复/高潮",
  "logic": "100字内，重点分析价格与分时均价线、成交量的配合关系...",
  "action": "BUY | SELL | HOLD | REDUCE (减仓) | WAIT",
  "target_price": "预期的反弹高度或下一个止损观察点",
  "confidence": "High/Medium/Low"
}}"""
    
    return prompt


def create_realtime_etf_prompt(stock_info: Dict[str, Any], tech_data: Dict[str, Any], realtime_data: Dict[str, Any]) -> str:
    """
    Create a REAL-TIME ACTION prompt for ETFs using the specific "Right-Side Trading + Sector Rotation" template.
    """
    # 1. Prepare Data Variables
    
    # Context
    market_change = realtime_data.get('market_index_change', 0)
    market_theme = realtime_data.get('market_theme', realtime_data.get('sector', '未知')) # Use Sector as Theme proxy if Global Theme not avail
    
    # Target
    etf_name = f"{stock_info['name']} ({stock_info['symbol']})"
    price = realtime_data.get('price', tech_data.get('close', 0))
    change_pct = realtime_data.get('change_pct', 0)
    
    vol_ratio = realtime_data.get('volume_ratio', tech_data.get('volume_ratio', 0))
    # Vol Status Logic
    if vol_ratio > 2.0: vol_status = "放量"
    elif vol_ratio < 0.8: vol_status = "缩量"
    else: vol_status = "正常"
    
    # Relative Strength (Simple: Stock Change - Market Change)
    rel_strength_val = change_pct - market_change
    if rel_strength_val > 0.5: rel_strength = "跑赢"
    elif rel_strength_val < -0.5: rel_strength = "跑输"
    else: rel_strength = "跟随"
    
    # Technicals
    ma20 = tech_data.get('ma20', 0)
    ma60 = tech_data.get('ma60', 0)
    
    # Position vs MA20
    if price > ma20: pos_ma20 = "MA20上方 (支撑)"
    elif price < ma20: pos_ma20 = "MA20下方 (压制)"
    else: pos_ma20 = "MA20附近"
    
    # MACD
    dif = tech_data.get('macd_dif', 0)
    dea = tech_data.get('macd_dea', 0)
    if dif > dea: macd_status = "金叉"
    elif dif < dea: macd_status = "死叉"
    else: macd_status = "粘合"
    if dif > 0 and dea > 0: macd_status += " (零轴上方)"
    else: macd_status += " (零轴下方)"
    
    rsi = tech_data.get('rsi', 50)
    
    # Fund Flow
    funds = realtime_data.get('money_flow', {})
    if funds and funds.get('status') == 'success':
        net_main = funds.get('net_amount_main', 0) / 10000
        fund_flow = f"主力净流入 {net_main:.0f}万"
    else:
        fund_flow = "暂无数据"

    # News Sentiment
    # We just pass the summary and ask LLM to evaluate score.
    news_summary = realtime_data.get('news_summary', "暂无特殊消息")
    sentiment_score = "请模型根据新闻内容自行评估" 
    
    # 2. Fill Template
    prompt = f"""# Role
你是一个专注于A股市场的量化交易决策系统。你的核心逻辑是“右侧交易”结合“板块轮动”。你的风格是：客观、严守纪律、厌恶回撤。

# Input Data
## 1. 市场环境 (Context)
- 上证指数涨跌幅：{market_change}%
- 市场核心主线/所属板块：{market_theme}

## 2. 标的实时数据 (Target: {etf_name})
- 现价：{price} (涨跌: {change_pct}%)
- 成交量能：量比 {vol_ratio}，当前成交额状态 ({vol_status})
- 相对强弱：相对于上证指数 {rel_strength}

## 3. 技术指标 (Technical Indicators)
- 均线系统：
    - MA20 (生命线): {ma20} (现价在 {pos_ma20})
    - MA60 (牛熊线): {ma60}
- 动量指标：
    - MACD：{macd_status}
    - RSI(14)：{rsi}
- 资金/筹码：
    - 主力资金流向：{fund_flow}

## 4. 资讯情绪 (News Sentiment)
- 关键摘要：{news_summary}
- 请根据摘要自行评估综合情绪分 (-10 到 +10)

# ETF Specific Decision Logic (ETF 专属决策逻辑)
1. **轮动核心 (Rotation Rule)**：
   - 比较对象：当前 ETF vs 沪深300 (或上证指数)。
   - 规则：如果连续 3 日 `相对强弱` 为“跑输”，且缺乏重大利好资讯支撑，建议【换仓】(Switch)。
2. **波动敏感度 (Sensitivity)**：
   - 噪音过滤：日内涨跌幅绝对值 < 0.8% 视为震荡，原则上【不操作】。
   - 趋势确认：只有当涨跌幅 > 1.2% 且配合量能放大，才视为有效突破/破位。
3. **网格/定投视角 (Grid Trading)**：
   - 不同于个股的止损逻辑，ETF 不会归零。
   - 如果 价格 < MA60 但 RSI < 30 (超卖)，且新闻面无根本性利空，**禁止**发出强力止损信号，应提示【左侧观察】或【分批补仓】。
4. **折溢价风控 (Premium Check)**：
   - (如果你能获取IOPV数据) 如果当前价格溢价率 > 3% (通常发生在跨境或停牌股复牌)，提示【追高风险】，禁止买入。

# Output Format
请严格按照以下步骤思考，并输出 JSON 格式结果：
1. **分析思考 (Thinking)**：简要分析量价关系、指标配合情况以及新闻对盘面的支撑。
2. **态势定义 (Status)**：用 4 个字概括 (如：放量杀跌、缩量企稳、多头排列)。
3. **操作指令 (Action)**：只能从 [STRONG_BUY, BUY, HOLD, SELL, STRONG_SELL, WAIT] 中选择一个。
4. **风控建议 (Risk_Tip)**：如果指令是买入，给出止损位；如果指令是持有，给出预警位。

# Output Example
{{
  "thinking": "当前价格虽然回踩MA20，但量能极度萎缩，说明抛压不重。结合新闻面'设备更新'利好，且MACD处于零轴上方，判断为良性回调。",
  "status": "缩量回踩",
  "action": "HOLD",
  "risk_tip": "关注MA20支撑，跌破{ma20}止损。"
}}
"""
    return prompt



def create_deep_candidate_prompt(
    stock_info: Dict[str, Any], 
    tech_data: Dict[str, Any], 
    realtime_data: Dict[str, Any],
    market_context: Dict[str, Any] = None,
    extra_indicators: Dict[str, Any] = None
) -> str:
    """
    Create a DEEP MONITOR prompt for A-share stocks using 'deep_monitor' template.
    Now uses EXPLICIT market_context argument.
    """
    # Ensure money_flow safety for template access
    if not realtime_data.get('money_flow'):
        realtime_data['money_flow'] = {}

    # --- Prepare Computed Context (Shared with Speculator Mode) ---
    # Use Realtime Price if available, else tech_data close
    price = realtime_data.get('price', tech_data.get('close', 0))
    if price == 0: price = tech_data.get('close', 0)
    
    # Position Logic
    ma5 = tech_data.get('ma5')
    ma20 = tech_data.get('ma20')
    ma5_pos = "上方" if ma5 and price > ma5 else "下方"
    ma20_pos = "上方" if ma20 and price > ma20 else "下方"
    
    # Resistance/Support
    res = tech_data.get('resistance', tech_data.get('pivot_point', price * 1.1)) # Fallback
    sup = tech_data.get('support', tech_data.get('s1', price * 0.9))
    
    # Extract strengths from score_details
    details = tech_data.get('score_details', [])
    # Filter only "✅" items
    strengths = [d.replace('✅ ', '') for d in details if '✅' in d]
    strength_str = ", ".join(strengths[:3]) if strengths else "暂无明显优势"
    
    computed = {
        'ma5_pos': ma5_pos,
        'ma20_pos': ma20_pos,
        'res': f"{res:.2f}",
        'sup': f"{sup:.2f}",
        'strength_str': strength_str
    }
    
    # 兼容旧代码：如果 market_context 为空，尝试构建默认值
    if not market_context:
        market_context = {
            'market_index': {},
            'sector_info': {},
            'sentiment': {}
        }
        
    db_prompt = get_prompt_from_db('deep_monitor', {
        'stock_info': stock_info,
        'tech_data': tech_data,
        'realtime_data': realtime_data,
        'market_context': market_context, # Explicit Context
        'computed': computed,
        'extra': extra_indicators or {}
    })
    
    if db_prompt:
        return db_prompt

    return "DB Error: deep_monitor prompt not found."


def create_realtime_crypto_prompt(stock_info: Dict[str, Any], history_data: Dict[str, Any], realtime_data: Dict[str, Any]) -> str:
    """
    Create a REAL-TIME ACTION prompt for CRYPTO.
    """
    db_prompt = get_prompt_from_db('realtime_crypto', {
        'stock_info': stock_info,
        'tech_data': history_data, # Note: history_data maps to tech_data in template
        'realtime_data': realtime_data
    })
    
    if db_prompt:
        return db_prompt

    return "DB Error: realtime_crypto prompt not found."


def create_realtime_future_prompt(stock_info: Dict[str, Any], history_data: Dict[str, Any], realtime_data: Dict[str, Any]) -> str:
    """
    Create a REAL-TIME ACTION prompt for FUTURES.
    """
    db_prompt = get_prompt_from_db('realtime_future', {
        'stock_info': stock_info,
        'tech_data': history_data,
        'realtime_data': realtime_data
    })
    
    if db_prompt:
        return db_prompt

    return "DB Error: realtime_future prompt not found."


    return "DB Error: realtime_future prompt not found."


def create_analysis_prompt(
    stock_info: Dict[str, Any], 
    tech_data: Dict[str, Any], 
    analysis_type: str = "holding", 
    realtime_data: Dict[str, Any] = None, 
    market_context: Dict[str, Any] = None,
    extra_indicators: Dict[str, Any] = None
) -> str:
    """
    Dispatcher for prompt creation. 根据分析类型分发到具体的 Prompt 生成函数。

    Args:
        stock_info (Dict[str, Any]): 股票基础信息
            - symbol (str): 股票代码 (如 '600519')
            - name (str): 股票名称 (如 '贵州茅台')
            - asset_type (str): 资产类型 ('stock', 'etf', 'crypto', 'future')
        
        tech_data (Dict[str, Any]): 技术面数据 (通常基于日线)
            - close, open, high, low (float): 基础行情
            - ma5, ma20, ma60 (float): 均线系统
            - macd_dif, macd_dea, macd_signal (float): MACD指标
            - rsi (float): RSI指标
            - kdj_k, kdj_d (float): KDJ指标
            - composite_score (float): 综合技术评分
            - resistance, support (float): 压力位与支撑位
            - score_details (list): 评分详情标签

        analysis_type (str): 分析模式
            - 'holding': 持仓日报分析 (默认)
            - 'candidate': 选股/机会分析
            - 'realtime': 实时盘中分析 (通用)
            - 'intraday': 盘中盯盘分析 (主要用于 A股 Monitor)

        realtime_data (Dict[str, Any], optional): 实时行情数据 (用于盘中分析)
            - price (float): 当前现价
            - change_pct (float): 当前涨跌幅
            - volume_ratio (float): 量比
            - vwap (float): 分时均价 (Intraday)
            - weibi (float): 委比 (Intraday)
            - money_flow (dict): 资金流向数据

        market_context (Dict[str, Any], optional): 市场大环境上下文
            - market_index (dict): 大盘指数信息 {'name', 'change_pct', 'trend'}
            - sector_info (dict): 板块信息 {'name', 'change_pct'}
            - sentiment (dict): 市场情绪 {'limit_up_count': int}
    """
    print("create_analysis_prompt received stock_info", stock_info)
    print("create_analysis_prompt received tech_data", tech_data)
    print("create_analysis_prompt received realtime_data", realtime_data)
    print("create_analysis_prompt received market_context", market_context)
    print("create_analysis_prompt received extra_indicators", extra_indicators)
    # Use explicitly configured asset_type (from config), usually 'etf' or 'stock'
    # 'stock' is default if not specified
    # Also support 'type' field from raw config
    asset_type = stock_info.get('asset_type', stock_info.get('type', 'stock'))
    is_etf = (asset_type == 'etf')

    if analysis_type == "intraday":
        return create_intraday_prompt(stock_info, tech_data, realtime_data, market_context)

    if analysis_type == "realtime":
        if asset_type == 'crypto':
            return create_realtime_crypto_prompt(stock_info, tech_data, realtime_data)
        elif asset_type == 'future':
            return create_realtime_future_prompt(stock_info, tech_data, realtime_data)
        elif is_etf:
            return create_realtime_etf_prompt(stock_info, tech_data, realtime_data)
        else:
            # A股专家分析
            return create_deep_candidate_prompt(stock_info, tech_data, realtime_data, market_context=market_context, extra_indicators=extra_indicators)
            
    elif analysis_type == "candidate":
        # Candidates are usually stocks, but could technically be ETFs
        return create_opportunity_prompt(stock_info, tech_data)
        
    else:
        # Holdings analysis / Daily Report
        if asset_type == 'crypto':
            return create_crypto_prompt(stock_info, tech_data)
        elif asset_type == 'future':
            return create_future_prompt(stock_info, tech_data)
        elif is_etf:
            return create_etf_holding_prompt(stock_info, tech_data)
        else:
            return create_risk_prompt(stock_info, tech_data)





def _fetch_extra_indicators(stock_info: Dict[str, Any], analysis_type: str, realtime_data: Dict[str, Any], tech_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Helper to fetch extra indicators (Advanced Technical Factors & Chips Distribution)
    Updated to use Tushare Pro interfaces: stk_factor_pro & cyq_chips
    """
    extra_indicators = {}
    if analysis_type == "realtime" and stock_info.get('asset_type', 'stock') == 'stock':
        symbol = stock_info['symbol']
        print(f"🔎 Fetching Advanced Factors & Chips for {symbol}...")
        
        # 1. Advanced Technical Factors (stk_factor_pro)
        try:
            from data_fetcher_ts import fetch_stk_factor_pro
            
            factors = fetch_stk_factor_pro(symbol)
            if factors:
                summary = []
                # Select key factors
                if 'asi_qfq' in factors: summary.append(f"ASI振动升降: {factors['asi_qfq']:.2f}")
                if 'dmi_pdi_qfq' in factors and 'dmi_mdi_qfq' in factors: 
                    summary.append(f"DMI动向: PDI={factors['dmi_pdi_qfq']:.2f}, MDI={factors['dmi_mdi_qfq']:.2f}")
                if 'obv_qfq' in factors: summary.append(f"OBV能量潮: {factors['obv_qfq']:.2f}")
                if 'mass_qfq' in factors: summary.append(f"梅斯线Mass: {factors['mass_qfq']:.2f}")
                if 'cci_qfq' in factors: summary.append(f"CCI: {factors['cci_qfq']:.2f}")
                if 'wr_qfq' in factors: summary.append(f"W&R: {factors['wr_qfq']:.2f}")
                
                factor_str = " | ".join(summary)
                
                # Provide structured data
                extra_indicators['advanced_factors'] = {
                     "desc": factor_str,
                     "raw": factors
                }
                # Also provide a text summary for generic templates if they try to print extra
                extra_indicators['technical_plus'] = factor_str
                
                # Fallback/Compat: Fill 'intraday' with factor info if template expects it
                extra_indicators['intraday'] = {
                    "strength_desc": f"技术面因子: {factor_str}" 
                }
                
        except Exception as e:
            print(f"⚠️ Factor analysis failed: {e}")
            import traceback
            traceback.print_exc()
            
        # 2. Chips Distribution (cyq_chips)
        try:
            from data_fetcher_ts import fetch_cyq_chips
            
            chips_df = fetch_cyq_chips(symbol)
            if chips_df is not None and not chips_df.empty:
                current_price = realtime_data.get('price') or tech_data.get('close')
                
                total_percent = chips_df['percent'].sum()
                if total_percent > 0:
                    # Avg Cost
                    avg_cost = (chips_df['price'] * chips_df['percent']).sum() / total_percent
                    
                    # Winner Pct (Profit Ratio)
                    winner_percent = chips_df[chips_df['price'] < current_price]['percent'].sum()
                    
                    # Concentration 90%
                    chips_df = chips_df.sort_values('price')
                    chips_df['cumsum_pct'] = chips_df['percent'].cumsum()
                    
                    try:
                        p05 = chips_df[chips_df['cumsum_pct'] >= 5]['price'].iloc[0]
                        p95 = chips_df[chips_df['cumsum_pct'] >= 95]['price'].iloc[0]
                        concentration = (p95 - p05) / (p95 + p05) 
                        conc_desc = f"{concentration:.2%}"
                    except:
                        p05, p95 = 0, 0
                        concentration = 0
                        conc_desc = "N/A"

                    # Description
                    cyq_desc = f"获利盘: {winner_percent:.2f}% | 平均成本: {avg_cost:.2f} | 90%成本区间: {p05:.2f}-{p95:.2f} (集中度 {conc_desc})"
                    
                    # Use 'vap' key for compatibility with existing prompt templates
                    extra_indicators['vap'] = {
                        "desc": cyq_desc,
                        "winner_rate": winner_percent,
                        "avg_cost": avg_cost,
                        "concentration": concentration,
                        "cost_range": f"{p05:.2f}-{p95:.2f}"
                    }
                    
        except Exception as e:
            print(f"⚠️ VAP analysis failed: {e}")
            import traceback
            traceback.print_exc()
            
    return extra_indicators

def _get_system_instruction(analysis_type: str, stock_info: Dict[str, Any]) -> str:
    """
    Helper to determine the system instruction based on analysis type and asset type
    """
    asset_type = stock_info.get('asset_type', stock_info.get('type', 'stock'))
    is_etf = (asset_type == 'etf')

    system_instruction = "你是一名严格的风险控制官，首要任务是保护资本。"
    
    if analysis_type == "candidate":
        system_instruction = "你是一名拥有20年实战经验的A股游资操盘手。你的风格是：犀利、客观、风险厌恶，只做大概率的确定性交易。"
    elif analysis_type == "realtime":
        if is_etf:
            system_instruction = "你是一名稳健的资产配置专家，擅长ETF投资，注重长期趋势，过滤短期噪音。"
        elif asset_type == 'crypto':
            system_instruction = "你是一名资深的加密货币交易员，习惯高波动风险和7x24小时市场。"
        elif asset_type == 'future':
            system_instruction = "你是一名专业的期货交易员，极其重视杠杆风险管理。"
        else:
            system_instruction = "你是一名深谙A股主力资金运作模式的资深策略分析师。你擅长通过技术面、资金面和基本面的共振来寻找确定性机会。你的风格是：客观、犀利、重实战、不讲废话。"
    elif is_etf: # Static holding analysis for ETF
            system_instruction = "你是一名稳健的资产配置专家，擅长ETF投资。"
    elif asset_type == 'crypto':
            system_instruction = "你是一名资深的加密货币交易员，风格激进但重视止损。"
    elif asset_type == 'future':
            system_instruction = "你是一名专业的期货交易员，擅长日内和波段交易。"
            
    return system_instruction


def generate_analysis_gemini(
    stock_info: Dict[str, Any],
    tech_data: Dict[str, Any],
    project_id: str,
    location: str,
    credentials_path: str = None,
    model: str = "gemini-2.5-flash",
    analysis_type: str = "holding",
    realtime_data: Dict[str, Any] = None,
    market_context: Dict[str, Any] = None
) -> str:
    """
    Generate LLM-based trading analysis using Google Gemini
    """
    if not GENAI_AVAILABLE:
        error_msg = "❌ Google Gen AI SDK 未安装。请运行: pip install google-genai"
        print(error_msg)
        return f"**分析失败**：{error_msg}"
    
    try:
        if credentials_path and os.path.exists(credentials_path):
            os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = credentials_path
        
        
        client = genai.Client(
            vertexai=True,
            project=project_id,
            location=location
        )
        
        
        # [Refactored] Use shared helper for indicators
        extra_indicators = _fetch_extra_indicators(stock_info, analysis_type, realtime_data, tech_data)

        prompt = create_analysis_prompt(stock_info, tech_data, analysis_type, realtime_data, market_context, extra_indicators=extra_indicators)
        
        # Log the full prompt
        print(f"\n======== [Gemini Prompt Debug ({analysis_type})] ========\n{prompt}\n=========================================================\n")

        # [Refactored] Use shared helper for system instruction
        system_instruction = _get_system_instruction(analysis_type, stock_info)

        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=8192,
                system_instruction=system_instruction
            )
        )
        
        if hasattr(response, 'text'):
            analysis = response.text
        elif hasattr(response, 'candidates') and len(response.candidates) > 0:
            candidate = response.candidates[0]
            if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                analysis = ''.join([part.text for part in candidate.content.parts if hasattr(part, 'text')])
            else:
                analysis = str(candidate)
        else:
            analysis = str(response)
        
        return analysis
        
    except Exception as e:
        error_msg = f"❌ Gemini分析错误：{str(e)}"
        print(error_msg)
        return f"**分析失败**：{error_msg}"


def generate_analysis_openai(
    stock_info: Dict[str, Any],
    tech_data: Dict[str, Any],
    api_key: str,
    base_url: str,
    model: str = "deepseek-chat",
    analysis_type: str = "holding",
    realtime_data: Dict[str, Any] = None,
    provider: str = "openai",
    market_context: Dict[str, Any] = None
) -> str:
    """
    Generate LLM-based trading analysis using OpenAI-compatible API
    """
    try:
        client = OpenAI(
            api_key=api_key,
            base_url=base_url
        )
        
        
        # [Refactored] Use shared helper for indicators
        extra_indicators = _fetch_extra_indicators(stock_info, analysis_type, realtime_data, tech_data)

        prompt = create_analysis_prompt(stock_info, tech_data, analysis_type, realtime_data, market_context=market_context, extra_indicators=extra_indicators)
        
        # Log the full prompt
        print(f"\n======== [OpenAI Prompt Debug ({analysis_type})] ========\n{prompt}\n=========================================================\n")

        # [Refactored] Use shared helper for system instruction
        system_content = _get_system_instruction(analysis_type, stock_info)

        # Prepare API call parameters
        api_params = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": system_content
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.3,  # Low temp for consistent trading signals
            "max_tokens": 4096
        }

        # Add thinking parameter for GLM provider
        if provider == "glm":
            api_params["extra_body"] = {
                "thinking":{
                    "type": "disabled"
                }
            }

        response = client.chat.completions.create(**api_params)
        
        analysis = response.choices[0].message.content
        return analysis
        
    except Exception as e:
        error_msg = f"❌ LLM分析错误：{str(e)}"
        print(error_msg)
        return f"**分析失败**：{error_msg}"


def generate_analysis(
    stock_info: Dict[str, Any],
    tech_data: Dict[str, Any],
    api_config: Dict[str, Any],
    analysis_type: str = "holding",
    realtime_data: Dict[str, Any] = None,
    market_context: Dict[str, Any] = None
) -> str:
    """
    Generate LLM-based trading analysis (supports multiple providers)
    """
    provider = api_config.get('provider', 'openai')
    
    if provider == 'gemini':
        return generate_analysis_gemini(
            stock_info=stock_info,
            tech_data=tech_data,
            project_id=api_config['project_id'],
            location=api_config['location'],
            credentials_path=api_config.get('credentials_path'),
            model=api_config.get('model', 'gemini-2.5-flash'),
            analysis_type=analysis_type,
            realtime_data=realtime_data,
            market_context=market_context
        )
    else:
        # OpenAI 兼容的 API（包括 OpenAI, DeepSeek, GLM 等）
        return generate_analysis_openai(
            stock_info=stock_info,
            tech_data=tech_data,
            api_key=api_config['api_key'],
            base_url=api_config['base_url'],
            model=api_config['model'],
            analysis_type=analysis_type,
            realtime_data=realtime_data,
            provider=provider,
            market_context=market_context
        )


def format_etf_section(stock_info: Dict[str, Any], tech_data: Dict[str, Any], llm_analysis: str) -> str:
    """
    Format a complete ETF analysis section in Markdown (simplified, long-term focused)
    """
    # 综合评分显示
    score = tech_data.get('composite_score', 'N/A')
    rating = tech_data.get('rating', '未知')
    
    # 评分详情
    score_breakdown = tech_data.get('score_breakdown', [])
    score_details = tech_data.get('score_details', [])
    
    # 构建评分进度条
    score_section = ""
    if score_breakdown:
        score_section = "\n**评分明细：**\n"
        for name, got, total in score_breakdown:
            # 计算填充进度条
            filled = int(got / total * 10) if total > 0 else 0
            bar = "█" * filled + "░" * (10 - filled)
            score_section += f"- {name}：[{bar}] {got}/{total}分\n"
    
    # 操作建议
    operation_suggestion = tech_data.get('operation_suggestion', '暂无建议')
    
    # 判断价格与MA60关系
    close = tech_data.get('close', 0)
    ma60 = tech_data.get('ma60', 0)
    ma60_status = "上方 (多头)" if close > ma60 else "下方 (调整)"
    
    section = f"""
## {stock_info['symbol']} - {stock_info['name']} 【ETF】
### 📅 报告日期：{tech_data.get('date', '未知')}

### 📊 ETF长期持有评分：{score}分 - {rating}

**💡 操作建议：{operation_suggestion}**

{score_section}

**价格数据（{tech_data['date']}）：**
- 当前价：¥{tech_data['close']} | 开盘：¥{tech_data['open']} | 最高：¥{tech_data['high']} | 最低：¥{tech_data['low']}
- 成本价：¥{stock_info.get('cost_price', '未设置')} | 盈亏：{tech_data.get('profit_loss_pct', '未知')}%

**📈 趋势状态（核心指标）：**
- **MA60 (牛熊线)**：¥{tech_data['ma60']} → 当前价在 **{ma60_status}**
- MA20 (波段线)：¥{tech_data['ma20']} | MA5：¥{tech_data.get('ma5', 'N/A')}
- 均线排列：**{tech_data.get('ma_arrangement', '未知')}**

**📉 估值指标：**
- RSI（14）：**{tech_data.get('rsi', 'N/A')}** → {tech_data.get('rsi_signal', '未知')} {'🟢 加仓机会' if tech_data.get('rsi', 50) < 35 else ''}
- 布林带位置：**{tech_data.get('boll_position', 'N/A')}%** → {tech_data.get('boll_signal', '未知')} {'🟢 加仓机会' if tech_data.get('boll_position', 50) < 25 else ''}
- KDJ：K={tech_data.get('kdj_k', 'N/A')}, D={tech_data.get('kdj_d', 'N/A')} → {tech_data.get('kdj_zone', '未知')}

**🔄 动量指标：**
- MACD：{tech_data['macd_signal']} (DIF={tech_data['macd_dif']}, DEA={tech_data['macd_dea']})

**📊 波动率：**
- ATR波动率：{tech_data.get('atr_pct', 'N/A')}%

**信号汇总（ETF视角）：**
| 指标 | 状态 | ETF解读 |
|------|------|---------|
| 趋势（MA60）| {'多头' if close > ma60 else '空头/调整'} | {'持有' if close > ma60 else '可能是加仓机会'} |
| RSI | {tech_data.get('rsi_signal', '未知')} | {'超卖=加仓点' if tech_data.get('rsi', 50) < 30 else '正常'} |
| 布林带 | {tech_data.get('boll_signal', '未知')} | {'下轨=加仓点' if tech_data.get('boll_position', 50) < 20 else '正常'} |
| MACD | {tech_data['macd_signal']} | 参考趋势方向 |

> ⚠️ **ETF投资提醒**：此评分系统专为长期持有设计。低分代表加仓机会，而非卖出信号。

**🤖 AI分析：**
{llm_analysis}

---
"""
    return section


import re
import json

def format_json_plan(text: str) -> str:
    """
    Helper to extract and format JSON trading plan from LLM output
    """
    json_str = None
    
    # 1. Try to find Markdown code block first (Most reliable)
    # Match ```json ... ``` or just ``` ... ``` containing buy_trigger
    code_block_match = re.search(r'```(?:json)?\s*(\{.*?"buy_trigger".*?\})\s*```', text, re.DOTALL)
    if code_block_match:
        json_str = code_block_match.group(1)
    else:
        # 2. Fallback to raw JSON object search
        # Use non-greedy match for content to avoid capturing too much
        # But we need to balance braces... Regex is bad at recursion.
        # Simple heuristic: Match from first { to last }
        match = re.search(r'(\{.*"buy_trigger".*\})', text, re.DOTALL)
        if match:
             # Refine: Try to cut off at the last valid closing brace if multiple present
             # This is a bit hacky but works for simple LLM outputs
             candidate = match.group(1)
             json_str = candidate

    if not json_str:
        return text

    try:
        # Cleanups for common LLM JSON errors
        # 1. Remove comments // ...
        json_str_clean = re.sub(r'//.*', '', json_str)
        # 2. Fix trailing commas (simple case: , before })
        json_str_clean = re.sub(r',\s*\}', '}', json_str_clean)
        
        plan = json.loads(json_str_clean)
        
        # Build Table
        table = "\n\n**🎯 交易执行计划 (Action Plan)**\n\n"
        table += "| 项目 | 内容 | 备注 |\n"
        table += "|---|---|---|\n"
        
        # Mapping keys to readable names
        mapping = {
            "buy_trigger": "🚀 买入触发",
            "buy_price_max": "🚫 最高追涨",
            "buy_dip_price": "💰 低吸参考",
            "stop_loss_price": "🛡 严格止损",
            "take_profit_target": "🎯 止盈目标",
            "risk_rating": "⚠️ 风险等级"
        }
        
        for key, label in mapping.items():
            val = plan.get(key, "--")
            # Ensure value is string
            if not isinstance(val, str):
                val = str(val)
            # Escape pipes to avoid breaking markdown table
            val = val.replace("|", "\|")
            table += f"| **{label}** | {val} | |\n"
            
        # Replace the JSON part in original text with the table
        # Note: We replace the originally matched string (json_str) which comes from text
        # If we cleaned it, we still replace the original subset in 'text'
        
        # If we successfully parsed, we want to replace the whole code block if it existed
        if code_block_match:
            return text.replace(code_block_match.group(0), table)
        else:
            return text.replace(json_str, table)
        
    except Exception as e:
        print(f"JSON Parse Error: {e}")
        return text

def format_stock_section(stock_info: Dict[str, Any], tech_data: Dict[str, Any], llm_analysis: str) -> str:
    """
    Format a complete stock analysis section in Markdown
    Automatically selects ETF or Stock format based on score_type
    """
    # 检查是否为ETF评分类型
    if tech_data.get('score_type') == 'etf':
        return format_etf_section(stock_info, tech_data, llm_analysis)
    
    # 注意：现在 LLM 直接输出 Markdown 表格，无需再调用 format_json_plan 解析
    # formatted_analysis = format_json_plan(llm_analysis)
    
    # 综合评分显示
    score = tech_data.get('composite_score', 'N/A')
    rating = tech_data.get('rating', '未知')
    
    # 评分详情
    score_breakdown = tech_data.get('score_breakdown', [])
    
    score_section = ""
    if score_breakdown:
        score_section = "\n**📊 评分明细：**\n"
        for name, got, total in score_breakdown:
             # 计算填充进度条 (visual bar)
            filled = int(got / total * 10) if total > 0 else 0
            bar = "▮" * filled + "▯" * (10 - filled)
            score_section += f"- {name}：`{bar}` {got}/{total}\n"
    
    # 操作建议
    operation_suggestion = tech_data.get('operation_suggestion', '暂无建议')

    # 新闻区块
    news_content = tech_data.get('latest_news', None)
    news_block = ""
    if news_content and news_content != "暂无新闻":
        news_block = f"""
**📰 消息面/题材 (News/Catalyst)：**
> {news_content}
"""

    section = f"""
## {stock_info['symbol']} - {stock_info['name']}
### 📅 报告日期：{tech_data.get('date', '未知')}

### 🚀 综合评分：{score}分 - {rating}

**💡 策略建议：{operation_suggestion}**

{score_section}

**📈 核心技术信号 (Key Signals)：**
- **趋势**：MA20排列 **{tech_data.get('ma_arrangement', '未知')}** (价格在MA20{'上方' if tech_data.get('distance_from_ma20', 0) > 0 else '下方'})
- **形态**：**{", ".join(tech_data.get('pattern_details', [])) or "无明显反转形态"}**
- **动量**：RSI(14)=**{tech_data.get('rsi', 'N/A')}** | 量比=**{tech_data.get('volume_ratio', 'N/A')}**
- **结构**：距120日高点 **{f"{tech_data['price_vs_high120']:.2%}" if tech_data.get('price_vs_high120') is not None else 'N/A'}** (越近越好)
- **风控**：ATR波动率 **{tech_data.get('atr_pct', 'N/A')}%** | 建议止损 **¥{tech_data.get('stop_loss_suggest', 'N/A')}**

{news_block}

**🤖 AI 深度复盘与计划：**
{llm_analysis}

---
"""
    return section

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
        # print(f"Template was: {strategy.get('template_content', '')[:100]}...")
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


def create_realtime_etf_prompt(stock_info: Dict[str, Any], tech_data: Dict[str, Any], realtime_data: Dict[str, Any]) -> str:
    """
    Create a REAL-TIME ACTION prompt for ETFs (Stable, long-term).
    Now uses DB strategy 'realtime_etf_dca'.
    """
    db_prompt = get_prompt_from_db('realtime_etf_dca', {
        'stock_info': stock_info,
        'tech_data': tech_data,
        'realtime_data': realtime_data
    })
    
    if db_prompt:
        return db_prompt

    return "DB Error: realtime_etf_dca prompt not found."


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


def create_analysis_prompt(stock_info: Dict[str, Any], tech_data: Dict[str, Any], analysis_type: str = "holding", realtime_data: Dict[str, Any] = None) -> str:
    """
    Dispatcher for prompt creation.
    """
    # Use explicitly configured asset_type (from config), usually 'etf' or 'stock'
    # 'stock' is default if not specified
    # Also support 'type' field from raw config
    asset_type = stock_info.get('asset_type', stock_info.get('type', 'stock'))
    is_etf = (asset_type == 'etf')

    if analysis_type == "realtime":
        if asset_type == 'crypto':
            return create_realtime_crypto_prompt(stock_info, tech_data, realtime_data)
        elif asset_type == 'future':
            return create_realtime_future_prompt(stock_info, tech_data, realtime_data)
        elif is_etf:
            return create_realtime_etf_prompt(stock_info, tech_data, realtime_data)
        else:
            return create_realtime_prompt(stock_info, tech_data, realtime_data)
            
def create_deep_candidate_prompt(stock_info: Dict[str, Any], tech_data: Dict[str, Any], realtime_data: Dict[str, Any]) -> str:
    """
    Create a DEEP EVALUATION prompt for REAL-TIME analysis.
    Uses DB 'deep_monitor' strategy.
    """
    # 1. Unpack Data and Prepare Computed Context
    score = tech_data.get('composite_score', 0)
    score_breakdown = tech_data.get('score_breakdown', [])
    
    funds = realtime_data.get('money_flow', {})
    lhb = realtime_data.get('lhb_data', {})
    
    # Format Score details
    score_str = ""
    if score_breakdown:
        score_str = ", ".join([f"{item}:{got}/{total}" for item, got, total in score_breakdown])
    
    # Format Funds
    funds_str = "暂无数据"
    if funds.get('status') == 'success':
        net_main = funds.get('net_amount_main', 0) / 10000
        net_main_str = f"{net_main:.2f}万" if abs(net_main) < 10000 else f"{net_main/10000:.2f}亿"
        funds_str = f"主力净流入: {net_main_str} (占比{funds.get('net_pct_main', 0)}%)"
        
    # Format LHB
    lhb_str = "近期未上榜"
    if lhb.get('on_list'):
        net = lhb.get('net_amount', 0) / 10000
        net_str = f"{net:.2f}万" if abs(net) < 10000 else f"{net/10000:.2f}亿"
        lhb_str = f"上榜日期: {lhb.get('date')}, 净买入: {net_str}, 机构席位: {lhb.get('jg_count')}家"

    # --- Data Refinement for Prompt ---
    # 1. Scenario Thresholds (Fix 0 value issue)
    current_price = realtime_data.get('price', 0)
    high_val = realtime_data.get('high', 0)
    low_val = realtime_data.get('low', 0)
    
    if high_val == 0 and current_price > 0: 
        high_val = round(current_price * 1.02, 2) # Est +2%
    if low_val == 0 and current_price > 0:
        low_val = round(current_price * 0.98, 2)  # Est -2%
        
    # --- Refined Technical Indicators ---
    
    # 2. MA Arrangement & Pattern
    ma_str = tech_data.get('ma_arrangement')
    if not ma_str or ma_str == 'None':
        ma5 = tech_data.get('ma5')
        ma10 = tech_data.get('ma10')
        ma20 = tech_data.get('ma20')
        if ma5 and ma10 and ma20:
             if ma5 > ma10 > ma20: ma_str = "多头排列"
             elif ma5 < ma10 < ma20: ma_str = "空头排列"
             else: ma_str = "震荡交织"
        else:
             ma_str = "均线粘合/未知" # Fallback if data missing

    # 3. Calculate Resistance/Support
    price = tech_data.get('close', current_price)
    res = tech_data.get('resistance')
    if not res: res = tech_data.get('pivot_point')
    if not res: res = price * 1.1 # Last resort fallback

    sup = tech_data.get('support') 
    if not sup: sup = tech_data.get('s1')
    if not sup: sup = price * 0.9

    # 4. Extended Tech Indicators
    ma60 = tech_data.get('ma60', 0)
    vol_ratio = tech_data.get('volume_ratio', realtime_data.get('volume_ratio', 'N/A'))
    rsi = tech_data.get('rsi', 'N/A')
    
    macd_str = "N/A"
    dif = tech_data.get('macd_dif')
    dea = tech_data.get('macd_dea')
    if dif is not None and dea is not None:
        macd_str = "金叉" if dif > dea else "死叉"
        if dif > 0 and dea > 0: macd_str += " (零轴上)"
        else: macd_str += " (零轴下)"

    computed = {
        'score_str': score_str,
        'funds_str': funds_str,
        'lhb_str': lhb_str,
        'high_val': high_val,
        'low_val': low_val,
        'ma_str': ma_str,
        'ma60': ma60,
        'res': f"{res:.2f}",
        'sup': f"{sup:.2f}",
        'vol_ratio': vol_ratio,
        'rsi': rsi,
        'macd_str': macd_str,
        'sector': tech_data.get('sector', '未知板块'),
        'sector_change': tech_data.get('sector_change', 0)
    }

    db_prompt = get_prompt_from_db('deep_monitor', {
        'stock_info': stock_info,
        'tech_data': tech_data,
        'realtime_data': realtime_data,
        'computed': computed
    })
    
    if db_prompt:
        return db_prompt

    return "DB Error: deep_monitor prompt not found."

def create_analysis_prompt(stock_info: Dict[str, Any], tech_data: Dict[str, Any], analysis_type: str = "holding", realtime_data: Dict[str, Any] = None) -> str:
    """
    Dispatcher for prompt creation.
    """
    # Use explicitly configured asset_type (from config), usually 'etf' or 'stock'
    # 'stock' is default if not specified
    # Also support 'type' field from raw config
    asset_type = stock_info.get('asset_type', stock_info.get('type', 'stock'))
    is_etf = (asset_type == 'etf')

    if analysis_type == "realtime":
        if asset_type == 'crypto':
            return create_realtime_crypto_prompt(stock_info, tech_data, realtime_data)
        elif asset_type == 'future':
            return create_realtime_future_prompt(stock_info, tech_data, realtime_data)
        elif is_etf:
            return create_realtime_etf_prompt(stock_info, tech_data, realtime_data)
        else:
            # Upgrade: Use Deep Candidate Prompt for Stocks
            return create_deep_candidate_prompt(stock_info, tech_data, realtime_data)
            
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


def generate_analysis_gemini(
    stock_info: Dict[str, Any],
    tech_data: Dict[str, Any],
    project_id: str,
    location: str,
    credentials_path: str = None,
    model: str = "gemini-2.5-flash",
    analysis_type: str = "holding",
    realtime_data: Dict[str, Any] = None
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
        
        prompt = create_analysis_prompt(stock_info, tech_data, analysis_type, realtime_data)
        
        # Log the full prompt
        print(f"\n======== [Gemini Prompt Debug ({analysis_type})] ========\n{prompt}\n=========================================================\n")

        # Dynamic System Instruction based on asset type
        asset_type = stock_info.get('asset_type', stock_info.get('type', 'stock'))
        is_etf = (asset_type == 'etf')

        system_instruction = "你是一名严格的风险控制官，首要任务是保护资本。"
        if analysis_type == "candidate":
            # Check if we are in Speculator mode (implicitly via prompt content or config)
            # But here we set system instruction.
            # Let's set a punchy persona for candidate analysis.
            system_instruction = "你是一名拥有20年实战经验的A股游资操盘手。你的风格是：犀利、客观、风险厌恶，只做大概率的确定性交易。"
        elif analysis_type == "realtime":
            if is_etf:
                system_instruction = "你是一名稳健的资产配置专家，擅长ETF投资，注重长期趋势，过滤短期噪音。"
            elif asset_type == 'crypto':
                system_instruction = "你是一名资深的加密货币交易员，习惯高波动风险和7x24小时市场。"
            elif asset_type == 'future':
                system_instruction = "你是一名专业的期货交易员，极其重视杠杆风险管理。"
            else:
                # Upgraded System Instruction for Stocks
                system_instruction = "你是一名深谙A股主力资金运作模式的资深策略分析师。你擅长通过技术面、资金面和基本面的共振来寻找确定性机会。你的风格是：客观、犀利、重实战、不讲废话。"
        elif is_etf: # Static holding analysis for ETF
             system_instruction = "你是一名稳健的资产配置专家，擅长ETF投资。"
        elif asset_type == 'crypto':
             system_instruction = "你是一名资深的加密货币交易员，风格激进但重视止损。"
        elif asset_type == 'future':
             system_instruction = "你是一名专业的期货交易员，擅长日内和波段交易。"

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
    provider: str = "openai"
) -> str:
    """
    Generate LLM-based trading analysis using OpenAI-compatible API
    """
    try:
        client = OpenAI(
            api_key=api_key,
            base_url=base_url
        )
        
        prompt = create_analysis_prompt(stock_info, tech_data, analysis_type, realtime_data)
        
        # Log the full prompt
        print(f"\n======== [OpenAI Prompt Debug ({analysis_type})] ========\n{prompt}\n=========================================================\n")

        # Dynamic System Instruction based on asset type
        asset_type = stock_info.get('asset_type', stock_info.get('type', 'stock'))
        is_etf = (asset_type == 'etf')

        system_content = "你是一名严格的风险控制官。你的首要任务是保护资本。"
        if analysis_type == "candidate":
            system_content = "你是一名拥有20年实战经验的A股游资操盘手。你的风格是：犀利、客观、风险厌恶，只做大概率的确定性交易。"
        elif analysis_type == "realtime":
            if is_etf:
                system_content = "你是一名稳健的资产配置专家，擅长ETF投资，注重长期趋势，过滤短期噪音。"
            elif asset_type == 'crypto':
                system_content = "你是一名资深的加密货币交易员，习惯高波动风险。"
            elif asset_type == 'future':
                system_content = "你是一名专业的期货交易员，极其重视杠杆风险。"
            else:
                # Upgraded System Instruction for Stocks
                system_content = "你是一名深谙A股主力资金运作模式的资深策略分析师。你擅长通过技术面、资金面和基本面的共振来寻找确定性机会。你的风格是：客观、犀利、重实战、不讲废话。"
        elif is_etf: # Static holding analysis for ETF
             system_content = "你是一名稳健的资产配置专家，擅长ETF投资。"
        elif asset_type == 'crypto':
             system_content = "你是一名资深的加密货币交易员。"
        elif asset_type == 'future':
             system_content = "你是一名专业的期货交易员。"

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
    realtime_data: Dict[str, Any] = None
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
            realtime_data=realtime_data
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
            provider=provider
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

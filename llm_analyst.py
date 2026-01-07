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


def create_risk_prompt(stock_info: Dict[str, Any], tech_data: Dict[str, Any]) -> str:
    """
    Create a strict RISK-FOCUSED prompt for existing HOLDINGS.
    Focus: Capital preservation, stop-loss, profit taking.
    """
    prompt = f"""作为严格的A股风险控制官，你的核心任务是保护本金。请基于以下数据分析这只【持仓股】。

**股票：** {stock_info['symbol']} - {stock_info['name']}
**价格：** ¥{tech_data['close']} (成本价 ¥{stock_info.get('cost_price', '未设置')}, 盈亏 {tech_data.get('profit_loss_pct', '未知')}%)

**📊 综合评分：{tech_data.get('composite_score', 'N/A')}分 - {tech_data.get('rating', '未知')}**

**技术指标（{tech_data['date']}）：**

1. 均线系统：
   - MA5=¥{tech_data.get('ma5', 'N/A')}, MA10=¥{tech_data.get('ma10', 'N/A')}, MA20=¥{tech_data['ma20']}, MA60=¥{tech_data['ma60']}
   - 均线排列：{tech_data.get('ma_arrangement', '未知')}
   - 距MA20：{tech_data['distance_from_ma20']}% ({'上方' if tech_data.get('distance_from_ma20', 0) > 0 else '下方'})

2. MACD：DIF={tech_data['macd_dif']}, DEA={tech_data['macd_dea']}, 柱={tech_data['macd_hist']} ({tech_data['macd_signal']})

3. RSI（14日）：{tech_data.get('rsi', 'N/A')} - {tech_data.get('rsi_signal', '未知')}

4. KDJ：K={tech_data.get('kdj_k', 'N/A')}, D={tech_data.get('kdj_d', 'N/A')}, J={tech_data.get('kdj_j', 'N/A')}
   - 信号：{tech_data.get('kdj_signal', '未知')} | 区域：{tech_data.get('kdj_zone', '未知')}

5. 布林带：
   - 上轨=¥{tech_data.get('boll_upper', 'N/A')}, 中轨=¥{tech_data.get('boll_mid', 'N/A')}, 下轨=¥{tech_data.get('boll_lower', 'N/A')}
   - 位置：{tech_data.get('boll_signal', '未知')}（{tech_data.get('boll_position', 'N/A')}%）

6. 支撑压力：
   - 压力位=¥{tech_data.get('resistance', 'N/A')}（距离{tech_data.get('distance_to_resistance', 'N/A')}%）
   - 支撑位=¥{tech_data.get('support', 'N/A')}（距离{tech_data.get('distance_to_support', 'N/A')}%）

8. ⚠️ 动态风控 (ATR)：
   - ATR(14)=¥{tech_data.get('atr', 'N/A')} (波动率 {tech_data.get('atr_pct', 'N/A')}%)
   - 建议止损位 (2ATR)=¥{tech_data.get('stop_loss_suggest', 'N/A')}
   - 仓位控制：波动越大，仓位越小

9. 量价分析：
   - 量比：{tech_data.get('volume_ratio', 'N/A')}
   - 量价形态：{tech_data.get('volume_pattern', '未知')}

**持仓纪律规则（防守优先）：**
1. 价格<MA20 且 均线空头排列 → 必须建议减仓/等待。
2. RSI>70 或 KDJ>80 或 布林带位置>80% → 警告超买风险（考虑止盈）。
3. ATR风控：必须参考ATR建议的动态止损位。
4. 放量下跌=严重警告。
5. 综合评分<50偏空，50-65中性，>65偏多。

**请提供：**
1. 趋势健康度评估（是否破坏？）
2. 明确的操作建议：**坚定持有** / **减仓止盈** / **止损离场** / **观望**
3. 重点风控位：止损价和压力位。

用中文，简洁直接，条理清晰。"""
    return prompt


def create_opportunity_prompt(stock_info: Dict[str, Any], tech_data: Dict[str, Any]) -> str:
    """
    Create an OPPORTUNITY-FOCUSED prompt for STOCK CANDIDATES.
    Focus: Trend strength, entry points, breakout validity.
    """
    prompt = f"""作为一名激进的成长股交易员，你的任务是挖掘具有爆发潜力的【选股标的】。请基于以下数据分析这只股票的买入价值。

**股票：** {stock_info['symbol']} - {stock_info['name']}
**现价：** ¥{tech_data['close']}

**📊 综合评分：{tech_data.get('composite_score', 'N/A')}分 - {tech_data.get('rating', '未知')}**
*(评分逻辑：偏重强势动量和量价配合)*

**技术关键点（{tech_data['date']}）：**

1. **趋势强度**：
   - 价格相对于MA20：{tech_data['distance_from_ma20']}% (正值代表多头强势)
   - 均线排列：{tech_data.get('ma_arrangement', '未知')} (多头排列最佳)
   - MA5/MA10/MA20/MA60：¥{tech_data.get('ma5', 'N/A')} / ¥{tech_data.get('ma10', 'N/A')} / ¥{tech_data['ma20']} / ¥{tech_data['ma60']}

2. **动量指标**：
   - RSI (14)：{tech_data.get('rsi', 'N/A')} (注意：强势股RSI往往维持在60-80区间)
   - MACD：{tech_data['macd_signal']} (DIF={tech_data['macd_dif']}, 柱={tech_data['macd_hist']})

3. **量能确认**：
   - 量比：{tech_data.get('volume_ratio', 'N/A')} (大于1.5视为活跃)
   - 形态：{tech_data.get('volume_pattern', '未知')} (放量上涨最理想)

4. **位置与空间**：
   - 布林带位置：{tech_data.get('boll_position', 'N/A')}% (接近上轨可能即将突破或回调)
   - 上方压力位：¥{tech_data.get('resistance', 'N/A')}
   - ATR波动率：{tech_data.get('atr_pct', 'N/A')}%

**选股判断逻辑（进攻优先）：**
1. **强势股特征**：高RSI (>60) 和 布林带上轨运行 对于强势股是常态，不视为单纯的卖出信号，而是动量强劲的表现。
2. **买点确认**：重点关注是否有“放量突破”、“回踩MA20不破”或“均线刚发散”等买入形态。
3. **陷阱识别**：如果量比太小(<0.8)或高位放巨量滞涨，提示风险。
4. **盈亏比**：上涨空间是否大于下跌空间？

**请提供：**
1. **主要看点**：为什么这只股票值得关注？（动量、突破、量能）
2. **交易计划**：
   - 建议入场区域（如：回踩MA5或突破某价位）
   - 止损位建议（参考ATR或关键均线）
3. **结论**：**强烈推荐** / **逢低关注** / **谨慎参与** / **放弃**

用中文，语气要像资深交易员一样犀利，重点突出机会与时机。"""
    return prompt


def create_analysis_prompt(stock_info: Dict[str, Any], tech_data: Dict[str, Any], analysis_type: str = "holding") -> str:
    """
    Dispatcher for prompt creation based on analysis type.
    
    Args:
        analysis_type: 'holding' (default) or 'candidate'
    """
    if analysis_type == "candidate":
        return create_opportunity_prompt(stock_info, tech_data)
    else:
        return create_risk_prompt(stock_info, tech_data)


def generate_analysis_gemini(
    stock_info: Dict[str, Any],
    tech_data: Dict[str, Any],
    project_id: str,
    location: str,
    credentials_path: str = None,
    model: str = "gemini-2.5-flash",
    analysis_type: str = "holding"
) -> str:
    """
    Generate LLM-based trading analysis using Google Gemini (New Gen AI SDK)
    """
    if not GENAI_AVAILABLE:
        error_msg = "❌ Google Gen AI SDK 未安装。请运行: pip install google-genai"
        print(error_msg)
        return f"**分析失败**：{error_msg}"
    
    try:
        # 如果提供了凭证文件路径，设置环境变量
        if credentials_path and os.path.exists(credentials_path):
            os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = credentials_path
        
        # 使用新的 Google Gen AI SDK
        client = genai.Client(
            vertexai=True,
            project=project_id,
            location=location
        )
        
        prompt = create_analysis_prompt(stock_info, tech_data, analysis_type)
        
        # 系统指令根据类型微调
        system_instruction = "你是一名严格的风险控制官，首要任务是保护资本。"
        if analysis_type == "candidate":
            system_instruction = "你是一名激进的成长股交易员，擅长捕捉市场热点和主升浪机会。"

        # 使用新的 API 调用方式
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=8192,
                system_instruction=system_instruction
            )
        )
        
        # 获取完整的文本内容
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
        
        # 检查是否被截断
        if hasattr(response, 'candidates') and len(response.candidates) > 0:
            finish_reason = getattr(response.candidates[0], 'finish_reason', None)
            if finish_reason and 'MAX_TOKENS' in str(finish_reason):
                print(f"⚠️  警告：响应因达到 token 限制被截断，建议增加 max_output_tokens 参数")
        
        # 调试信息
        print(f"📝 AI 回复长度: {len(analysis)} 字符")
        
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
    analysis_type: str = "holding"
) -> str:
    """
    Generate LLM-based trading analysis using OpenAI-compatible API
    """
    try:
        client = OpenAI(
            api_key=api_key,
            base_url=base_url
        )
        
        prompt = create_analysis_prompt(stock_info, tech_data, analysis_type)
        
        system_content = "你是一名严格的风险控制官。你的首要任务是保护资本，而不是追求利润最大化。请用中文回答。"
        if analysis_type == "candidate":
            system_content = "你是一名敏锐的交易员，擅长发现强势股的买点。请用中文回答。"

        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": system_content
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.3,
            max_tokens=4096
        )
        
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
    analysis_type: str = "holding"
) -> str:
    """
    Generate LLM-based trading analysis (supports multiple providers)
    
    Args:
        stock_info: Stock metadata
        tech_data: Technical indicators
        api_config: API configuration dict
        analysis_type: 'holding' (default) or 'candidate'
    """
    provider = api_config.get('provider', 'openai')
    
    print(f"🤖 Using LLM provider: {provider} | Type: {analysis_type}")
    
    if provider == 'gemini':
        return generate_analysis_gemini(
            stock_info=stock_info,
            tech_data=tech_data,
            project_id=api_config['project_id'],
            location=api_config['location'],
            credentials_path=api_config.get('credentials_path'),
            model=api_config.get('model', 'gemini-2.5-flash'),
            analysis_type=analysis_type
        )
    else:
        # OpenAI 兼容的 API（包括 OpenAI, DeepSeek 等）
        return generate_analysis_openai(
            stock_info=stock_info,
            tech_data=tech_data,
            api_key=api_config['api_key'],
            base_url=api_config['base_url'],
            model=api_config['model'],
            analysis_type=analysis_type
        )


def format_stock_section(stock_info: Dict[str, Any], tech_data: Dict[str, Any], llm_analysis: str) -> str:
    """
    Format a complete stock analysis section in Markdown
    """
    # 综合评分显示
    score = tech_data.get('composite_score', 'N/A')
    rating = tech_data.get('rating', '未知')
    
    # 评分详情
    score_breakdown = tech_data.get('score_breakdown', [])
    score_details = tech_data.get('score_details', [])
    
    score_section = ""
    if score_breakdown:
        score_section = "\n**评分明细：**\n"
        for name, got, total in score_breakdown:
            score_section += f"- {name}：{got}/{total}分\n"
    
    section = f"""
## {stock_info['symbol']} - {stock_info['name']}

### 📊 综合评分：{score}分 - {rating}
{score_section}
**价格数据（{tech_data['date']}）：**
- 当前价：¥{tech_data['close']} | 开盘：¥{tech_data['open']} | 最高：¥{tech_data['high']} | 最低：¥{tech_data['low']}
- 成本价：¥{stock_info.get('cost_price', '未设置')} | 盈亏：{tech_data.get('profit_loss_pct', '未知')}%
- 涨跌幅：{tech_data['price_change_pct']}%

**均线系统：**
- MA5：¥{tech_data.get('ma5', 'N/A')} | MA10：¥{tech_data.get('ma10', 'N/A')} | MA20：¥{tech_data['ma20']} | MA60：¥{tech_data['ma60']}
- 均线排列：**{tech_data.get('ma_arrangement', '未知')}**
- 距离MA20：**{tech_data['distance_from_ma20']}%** ({'上方' if tech_data['distance_from_ma20'] > 0 else '下方'})

**动量指标：**
- MACD：DIF={tech_data['macd_dif']}, DEA={tech_data['macd_dea']}, 柱={tech_data['macd_hist']} → **{tech_data['macd_signal']}**
- RSI（14）：**{tech_data.get('rsi', 'N/A')}** → {tech_data.get('rsi_signal', '未知')}
- KDJ：K={tech_data.get('kdj_k', 'N/A')}, D={tech_data.get('kdj_d', 'N/A')}, J={tech_data.get('kdj_j', 'N/A')} → **{tech_data.get('kdj_signal', '未知')}** ({tech_data.get('kdj_zone', '未知')})

**布林带：**
- 上轨：¥{tech_data.get('boll_upper', 'N/A')} | 中轨：¥{tech_data.get('boll_mid', 'N/A')} | 下轨：¥{tech_data.get('boll_lower', 'N/A')}
- 位置：**{tech_data.get('boll_signal', '未知')}**（{tech_data.get('boll_position', 'N/A')}%）| 带宽：{tech_data.get('boll_width', 'N/A')}%

**⚡️ 动态风控 (ATR)：**
- ATR(14)=**¥{tech_data.get('atr', 'N/A')}** | 波动率：{tech_data.get('atr_pct', 'N/A')}%
- 建议止损位：**¥{tech_data.get('stop_loss_suggest', 'N/A')}** (2倍ATR)

**支撑压力：**
- 压力位：¥{tech_data.get('resistance', 'N/A')}（距离 {tech_data.get('distance_to_resistance', 'N/A')}%）
- 支撑位：¥{tech_data.get('support', 'N/A')}（距离 {tech_data.get('distance_to_support', 'N/A')}%）

**🔮 明日预测 (Pivot Points)：**
- 中轴：**¥{tech_data.get('pivot_point', 'N/A')}**
- 阻力(R1)：¥{tech_data.get('r1', 'N/A')} | 支撑(S1)：¥{tech_data.get('s1', 'N/A')}

**量价分析：**
- 成交量：{tech_data.get('volume', 'N/A')} | 均量：{tech_data.get('volume_ma', 'N/A')} | 量比：**{tech_data.get('volume_ratio', 'N/A')}**
- 量价形态：**{tech_data.get('volume_pattern', '未知')}** | 确认：{tech_data.get('volume_confirmation', '未知')}

**信号汇总：**
| 指标 | 信号 |
|------|------|
| 趋势（MA20）| {tech_data['trend_signal']} |
| MACD | {tech_data['macd_signal']} |
| RSI | {tech_data.get('rsi_signal', '未知')} |
| KDJ | {tech_data.get('kdj_signal', '未知')} |
| 量价 | {tech_data.get('volume_pattern', '未知')} |

**🤖 AI分析：**
{llm_analysis}

---
"""
    return section

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
    print(f"股票：{stock_info['symbol']} - {stock_info['name']} AI 分析（非ETF）")
    prompt = f"""作为严格的A股风险控制官，你的核心任务是保护本金。请基于以下数据分析这只【个股持仓】（非ETF）。

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


def create_crypto_prompt(stock_info: Dict[str, Any], tech_data: Dict[str, Any]) -> str:
    """
    Create a VOLATILITY-FOCUSED prompt for CRYPTO.
    """
    print(f"Crypto: {stock_info['symbol']} - {stock_info['name']} AI Analysis")
    prompt = f"""作为一名资深的加密货币(Crypto)交易员，请基于以下数据分析这只标的。注意：Crypto市场波动极大，且7x24小时交易。
    
**标的：** {stock_info['symbol']} - {stock_info['name']}
**价格：** ${tech_data['close']} (注意是美元计价)

**📊 趋势指标：**
- MA20 (均价): {tech_data['ma20']}
- MA60 (牛熊线): {tech_data['ma60']}
- 相对MA20位置：{'强势区' if tech_data.get('close') > tech_data.get('ma20') else '弱势区'}

**📉 震荡指标：**
- RSI (14): {tech_data.get('rsi', 'N/A')} (Crypto中，RSI>80才算极度超买，<20极度超卖)
- 布林带位置：{tech_data.get('boll_position', 'N/A')}%
- ATR波动率：{tech_data.get('atr_pct', 'N/A')}% (注意高波动风险)

**交易策略 (高波动风控)：**
1. **趋势为王**：Crypto往往具有很强的动量效应，顺势交易优于逆势抄底。
2. **止损纪律**：由于无涨跌停限制，必须严格设置止损 (建议ATR值的2-3倍)。
3. **关键点位**：是否突破了近期的High/Low点？

**请提供：**
1. **当前趋势判断**：(多头趋势 / 震荡 / 空头趋势)
2. **操作建议**：**持有** / **做多(买入)** / **减仓** / **清仓/做空** / **观望**
3. **风控位**：给出具体的止损价格。

用中文，简练直接。"""
    return prompt

def create_future_prompt(stock_info: Dict[str, Any], tech_data: Dict[str, Any]) -> str:
    """
    Create a LEVERAGE-FOCUSED prompt for FUTURES.
    """
    print(f"Future: {stock_info['symbol']} - {stock_info['name']} AI Analysis")
    prompt = f"""作为一名专业的期货(Futures)交易员，请分析以下合约。注意：期货含杠杆，风险敞口大。
    
**合约：** {stock_info['symbol']} - {stock_info['name']}
**最新价：** ¥{tech_data['close']}

**📊 技术面：**
- MA5: ¥{tech_data.get('ma5', 'N/A')} | MA20: ¥{tech_data['ma20']}
- MACD信号: {tech_data['macd_signal']}
- KDJ信号: {tech_data.get('kdj_signal', '未知')}

**🛡 风控关键：**
1. **杠杆管理**：当前波动率下，建议轻仓还是正常仓位？
2. **日内与波段**：当前形态适合日内短打还是波段持有？

**请提供：**
1. **多空方向**：(看多 / 看空 / 震荡)
2. **操作建议**：**开多** / **开空** / **平仓** / **观望**
3. **关键点位**：支撑位与压力位。

用中文，专业。"""
    return prompt


def create_etf_holding_prompt(stock_info: Dict[str, Any], tech_data: Dict[str, Any]) -> str:
    """
    Create a LONG-TERM FOCUSED prompt for ETFs.
    Focus: Macro trend, moving averages, overbought/oversold, less noise.
    """
    print(f"股票：{stock_info['symbol']} - {stock_info['name']} AI 分析（ETF）")
    prompt = f"""作为一名资产配置专家，你注重【ETF】的长期趋势和稳健收益。请基于以下数据分析这只【ETF持仓】。
    
**ETF：** {stock_info['symbol']} - {stock_info['name']}
**价格：** ¥{tech_data['close']} (成本价 ¥{stock_info.get('cost_price', '未设置')})

**📈 趋势状态：**
- MA20=¥{tech_data['ma20']} | MA60=¥{tech_data['ma60']}
- 当前价格与MA60关系：{'上方 (多头)' if tech_data.get('close') > tech_data.get('ma60') else '下方 (空头/调整)'}
- 均线排列：{tech_data.get('ma_arrangement', '未知')}

**📉 波动指标：**
- RSI (14)：{tech_data.get('rsi', 'N/A')} (高于80为严重超买，低于20为严重超卖)
- KDJ：{tech_data.get('kdj_signal', '未知')} ({tech_data.get('kdj_zone', '未知')})
- MACD：{tech_data['macd_signal']}

**ETF策略规则（稳健）：**
1. **忽略日内波动**：不要被1-2%的涨跌幅惊扰，除非发生趋势性逆转。
2. **生命线原则**：只要价格在 MA60 (中期趋势线) 之上，原则上保持持有。
3. **左侧交易机会**：如果 RSI < 30 或 价格触及布林下轨，往往是分批补仓（定投）的好机会，而不是止损点。
4. **右侧止盈**：只有当明显跌破 MA20 且无法收回，或 RSI > 80 时，才考虑做波段减仓。

**请提供：**
1. **趋势研判**：当前处于上涨中继、底部震荡还是下跌趋势？
2. **操作建议**：**继续持有** / **逢低加仓** / **分批减仓** / **清仓观望**
3. **理由**：请用稳健投资者的口吻简述理由。

用中文，简洁稳重。"""
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

2. **明日开盘剧本推演（重要）：**
   请分别针对以下三种开盘情况给出具体操作指令：
   - **剧本A（高开强势 >2%）：** 追涨条件（如：量比>3且不破分时均线）与入场点。
   - **剧本B（平开/小幅震荡）：** 最佳低吸位置（如：回踩MA5或关键均线时的止跌信号）。
   - **剧本C（不及预期/低开）：** 观望条件（如：跌破某价位直接放弃）。

3. **风控计划**：
   - 止损位：必须给出具体价格。
   - 目标位：第一目标位。

用中文，语气要像资深交易员一样犀利。**对于开盘剧本的推演要具体、有操作性，不要讲空话。**"""
    return prompt


def create_realtime_prompt(stock_info: Dict[str, Any], history_data: Dict[str, Any], realtime_data: Dict[str, Any]) -> str:
    """
    Create a REAL-TIME ACTION prompt.
    Combines historical tech context with current live market data AND market sentiment.
    """
    # Safe retrieval for new fields
    index_price = realtime_data.get('market_index_price', 'N/A')
    index_change = realtime_data.get('market_index_change', 0)
    turnover = realtime_data.get('turnover_rate', 'N/A')
    
    # Simple market sentiment text
    market_sentiment = "震荡"
    if isinstance(index_change, (int, float)):
        if index_change > 1.0: market_sentiment = "强势上涨"
        elif index_change > 0.3: market_sentiment = "温和反弹"
        elif index_change < -1.0: market_sentiment = "恐慌下跌"
        elif index_change < -0.3: market_sentiment = "弱势调整"

    prompt = f"""作为一名拥有10年经验的A股短线交易员，正在进行紧张的实盘盯盘。请结合【大盘环境】、【个股实时走势】和【历史技术面】做出现场决策。

**一、大盘环境 (Market Context)**
- **上证指数**：{index_price} (涨跌幅: {index_change}%) -> **市场情绪：{market_sentiment}**
- *(注意：个股逆势拉升往往更显强势，但如果大盘跳水，需警惕补跌风险)*

**二、个股实时数据 (Real-time Snapshot)**
- **标的**：{stock_info['name']} ({stock_info['symbol']})
- **现价**：¥{realtime_data['price']} (涨跌: **{realtime_data['change_pct']}%**)
- **量能**：量比 **{realtime_data.get('volume_ratio', 'N/A')}** (关键指标！>1.5为放量, >3为巨量攻击)
- **换手率**：{turnover}% (结合分时图判断交投活跃度)
- **开盘形态**：今开¥{realtime_data.get('open', 'N/A')} | 昨收¥{realtime_data.get('pre_close', 'N/A')}
- **日内振幅**：最高¥{realtime_data.get('high', 'N/A')} / 最低¥{realtime_data.get('low', 'N/A')}

**三、技术面锚点 (Technical Anchors)**
- **趋势生命线**：MA20 = ¥{history_data.get('ma20', 'N/A')} (现价在此之{'上' if realtime_data['price'] > history_data.get('ma20', 0) else '下'})
- **短期攻击线**：MA5 = ¥{history_data.get('ma5', 'N/A')}
- **关键位置**：上方压力=¥{history_data.get('resistance', 'N/A')}，下方支撑=¥{history_data.get('support', 'N/A')}
- **超买超卖**：昨日RSI(14)= {history_data.get('rsi', 'N/A')}

**四、决策逻辑链**
1. **异动定性**：
   - 当前上涨是“放量突破”还是“无量诱多”？（看量比）
   - 当前下跌是“缩量洗盘”还是“放量出逃”？
2. **位置确认**：
   - 如果价格在压力位附近且量能不足 -> 风险！
   - 如果价格回踩MA5/支撑位且止跌回升 -> 机会！
3. **环境共振**：
   - 大盘{market_sentiment}背景下，该股表现是强于大盘还是弱于大盘？

**五、请给出明确指令 (Output Format)**
请模拟实战喊单风格，极简、果断：

1. **【态势判定】**：(例如：放量逆势突破 / 缩量回踩支撑 / 跟风下跌破位)
2. **【核心信号】**：(列出最促使你做出决策的1-2个数据，如：量比3.5且突破压力位)
3. **【操作指令】**：**【买入】(激进/稳健) / 【加仓】 / 【减仓】(止盈/止损) / 【观望】** (必选其一)
4. **【盯盘红线】**：(给出具体的**止损价**或**目标价**，例如：跌破 15.20 必须走)

"""
    return prompt


def create_realtime_etf_prompt(stock_info: Dict[str, Any], history_data: Dict[str, Any], realtime_data: Dict[str, Any]) -> str:
    """
    Create a REAL-TIME ACTION prompt for ETFs (Stable, long-term).
    """
    index_price = realtime_data.get('market_index_price', 'N/A')
    index_change = realtime_data.get('market_index_change', 0)
    
    prompt = f"""作为一名资产配置专家，你正在监控【ETF】实盘走势。你的风格是稳健、过滤噪音、关注大趋势。
    
**一、大盘环境**
- 上证指数：{index_price} ({index_change}%)

**二、ETF实时数据**
- **标的**：{stock_info['name']} ({stock_info['symbol']})
- **现价**：¥{realtime_data['price']} (涨跌: **{realtime_data['change_pct']}%**)
- **量能**：量比 {realtime_data.get('volume_ratio', 'N/A')}

**三、核心趋势线**
- MA60 (牛熊分界)：¥{history_data.get('ma60', 'N/A')}
- MA20 (波段支撑)：¥{history_data.get('ma20', 'N/A')}
- 当前位置：{'MA20上方 (安全)' if realtime_data['price'] > history_data.get('ma20', 0) else 'MA20下方 (注意)'} 且 {'MA60上方 (多头)' if realtime_data['price'] > history_data.get('ma60', 0) else 'MA60下方 (空头)'}

**四、决策逻辑**
1. **对于ETF，日内涨跌幅 < 1.5% 通常视为正常波动，无需操作。**
2. 只有当价格 **有效跌破MA20** 或 **放量跌破MA60** 时，才提示减仓/避险。
3. 如果价格回踩MA20/MA60且企稳，是良好的加仓/定投点。
4. **切勿频繁交易**。

**五、请给出指令**
1. **【态势】**：(例如：缩量回调 / 趋势向上 / 破位下跌)
2. **【指令】**：**【持有 (躺平)】 / 【加仓 (定投)】 / 【减仓 (止盈/避险)】 / 【观望】**
3. **【理由】**：一句话简述理由。

用中文，稳重。"""
    return prompt


def create_realtime_crypto_prompt(stock_info: Dict[str, Any], history_data: Dict[str, Any], realtime_data: Dict[str, Any]) -> str:
    """
    Create a REAL-TIME ACTION prompt for CRYPTO (24/7, High Volatility).
    """
    prompt = f"""作为一名深耕币圈的资深交易员(Degen)，你正在进行7x24小时的实盘监控。请忽略传统金融市场的开盘收盘概念，专注于动量、情绪和关键点位。

**一、标的实时状态**
- **标的**：{stock_info['name']} ({stock_info['symbol']})
- **现价**：${realtime_data['price']} (24h涨跌: **{realtime_data['change_pct']}%**)
- **日内极值**：High=${realtime_data.get('high', 'N/A')} / Low=${realtime_data.get('low', 'N/A')}

**二、技术趋势 (Trend Is King)**
- **MA20 (短期趋势)**：${history_data.get('ma20', 'N/A')} ({'多头排列' if realtime_data['price'] > history_data.get('ma20', 0) else '空头压制'})
- **MA60 (牛熊分界)**：${history_data.get('ma60', 'N/A')}
- **ATR波动率**：{history_data.get('atr_pct', 'N/A')}% (注意：若波动率突然放大，往往意味着变盘)

**三、决策逻辑 (Crypto Style)**
1. **突破确认**：Crypto市场假突破很多。如果价格突破High点但迅速回落（插针），是看空信号。
2. **动量效应**：强者恒强。如果24h涨幅 > 5% 且价格在高位横盘，大概率会继续拉升。
3. **止损纪律**：合约交易必须带止损。建议止损位设在 MA20 或 ATR 下轨。

**四、操作指令**
请给出直截了当的建议：
1. **【多空研判】**：(例如：多头趋势加速 / 震荡洗盘 / 空头破位)
2. **【核心理由】**：(一句话解释，例如：突破关键阻力位且站稳 MA20)
3. **【操作建议】**：**【做多 (Long)】 / 【做空 (Short)】 / 【加仓】 / 【减仓】 / 【观望】**
4. **【风控位】**：给出具体的**止损价格**。

用中文，风格干练，不要讲废话。"""
    return prompt


def create_realtime_future_prompt(stock_info: Dict[str, Any], history_data: Dict[str, Any], realtime_data: Dict[str, Any]) -> str:
    """
    Create a REAL-TIME ACTION prompt for FUTURES (Leverage, Risk Control).
    """
    prompt = f"""作为一名专业的期货交易员，你正在盯盘。你知道当前账户持有高杠杆头寸，**风控是第一生命线**。

**一、盘面实时数据**
- **合约**：{stock_info['name']} ({stock_info['symbol']})
- **最新价**：¥{realtime_data['price']} (涨跌: **{realtime_data['change_pct']}%**)
- **日内振幅**：High=¥{realtime_data.get('high', 'N/A')} / Low=¥{realtime_data.get('low', 'N/A')}

**二、关键技术位**
- **5日均线 (攻击线)**：¥{history_data.get('ma5', 'N/A')}
- **20日均线 (趋势线)**：¥{history_data.get('ma20', 'N/A')}
- **MACD信号**：{history_data.get('macd_signal', '未知')}

**三、风控逻辑**
1. **杠杆警觉**：即使只是 0.5% 的反向波动，加杠杆后也可能造成较大回撤。
2. **顺势而为**：期货不建议逆势抄底。如果价格跌破 MA5 且无力收回，应考虑平多或开空。
3. **日内与波段**：判断当前波动是日内杂波，还是趋势性行情的开始。

**四、交易指令**
1. **【当前状态】**：(例如：多头趋势良好 / 回调触及支撑 / 破位下跌)
2. **【操作方向】**：**【开多】 / 【开空】 / 【平仓 (止盈/止损)】 / 【锁仓/观望】**
3. **【关键点位】**：
   - 压力位：¥{history_data.get('resistance', 'N/A')}
   - 支撑位：¥{history_data.get('support', 'N/A')}

用中文，专业冷静。"""
    return prompt


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
        
        # Dynamic System Instruction based on asset type
        asset_type = stock_info.get('asset_type', stock_info.get('type', 'stock'))
        is_etf = (asset_type == 'etf')

        system_instruction = "你是一名严格的风险控制官，首要任务是保护资本。"
        if analysis_type == "candidate":
            system_instruction = "你是一名激进的成长股交易员，擅长捕捉市场热点和主升浪机会。"
        elif analysis_type == "realtime":
            if is_etf:
                system_instruction = "你是一名稳健的资产配置专家，擅长ETF投资，注重长期趋势，过滤短期噪音。"
            elif asset_type == 'crypto':
                system_instruction = "你是一名资深的加密货币交易员，习惯高波动风险和7x24小时市场。"
            elif asset_type == 'future':
                system_instruction = "你是一名专业的期货交易员，极其重视杠杆风险管理。"
            else:
                system_instruction = "你是一名实战操盘手，你需要根据盘中实时数据给出果断、明确的操作指令，不要模棱两可。"
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
                max_output_tokens=2048,
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
    realtime_data: Dict[str, Any] = None
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
        
        # Dynamic System Instruction based on asset type
        asset_type = stock_info.get('asset_type', stock_info.get('type', 'stock'))
        is_etf = (asset_type == 'etf')

        system_content = "你是一名严格的风险控制官。你的首要任务是保护资本。"
        if analysis_type == "candidate":
            system_content = "你是一名敏锐的交易员，擅长发现强势股的买点。"
        elif analysis_type == "realtime":
            if is_etf:
                system_content = "你是一名稳健的资产配置专家，擅长ETF投资，注重长期趋势，过滤短期噪音。"
            elif asset_type == 'crypto':
                system_content = "你是一名资深的加密货币交易员，习惯高波动风险。"
            elif asset_type == 'future':
                system_content = "你是一名专业的期货交易员，极其重视杠杆风险。"
            else:
                system_content = "你是一名实战操盘手，请根据实时数据给出果断指令。"
        elif is_etf: # Static holding analysis for ETF
             system_content = "你是一名稳健的资产配置专家，擅长ETF投资。"
        elif asset_type == 'crypto':
             system_content = "你是一名资深的加密货币交易员。"
        elif asset_type == 'future':
             system_content = "你是一名专业的期货交易员。"

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
            temperature=0.3, # Low temp for consistent trading signals
            max_tokens=2048
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
        # OpenAI 兼容的 API（包括 OpenAI, DeepSeek 等）
        return generate_analysis_openai(
            stock_info=stock_info,
            tech_data=tech_data,
            api_key=api_config['api_key'],
            base_url=api_config['base_url'],
            model=api_config['model'],
            analysis_type=analysis_type,
            realtime_data=realtime_data
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


def format_stock_section(stock_info: Dict[str, Any], tech_data: Dict[str, Any], llm_analysis: str) -> str:
    """
    Format a complete stock analysis section in Markdown
    Automatically selects ETF or Stock format based on score_type
    """
    # 检查是否为ETF评分类型
    if tech_data.get('score_type') == 'etf':
        return format_etf_section(stock_info, tech_data, llm_analysis)
    
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

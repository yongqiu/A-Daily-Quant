"""
LLM Analysis Module - Generates trading recommendations using AI
Implements strict risk management framework
Supports multiple LLM providers: OpenAI-compatible, Gemini (Google Gen AI SDK)
"""

from openai import OpenAI
from typing import Dict, Any
import os

from analysis_snapshot import flatten_snapshot_for_legacy, get_machine_snapshot_lines

try:
    from google import genai
    from google.genai import types

    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False


import database
from data_fetcher import fetch_intraday_data, fetch_cyq_data
from indicator_calc import analyze_intraday_pattern, process_cyq_data


def _normalize_context_from_snapshot(context: Dict[str, Any]) -> Dict[str, Any]:
    context = dict(context or {})
    snapshot = context.get("snapshot")
    if not snapshot:
        return context

    flattened = flatten_snapshot_for_legacy(snapshot)
    raw_data = snapshot.get("raw_data", {})
    context.setdefault("stock_info", snapshot.get("stock_info", {}))
    context["tech_data"] = flattened
    context.setdefault("realtime_data", raw_data.get("realtime_data", {}))
    context.setdefault("market_context", raw_data.get("market_context", {}))
    context.setdefault("extra_indicators", raw_data.get("extra_indicators", {}))
    context.setdefault("extra", raw_data.get("extra_indicators", {}))
    context.setdefault("intraday", raw_data.get("intraday", {}))
    context.setdefault("machine_snapshot_lines", get_machine_snapshot_lines(snapshot))
    context.setdefault("machine_snapshot_markdown", "\n".join(context["machine_snapshot_lines"]))
    return context


def _safe_float(value):
    try:
        if value in (None, "", "N/A", "None"):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _ensure_prompt_derived_fields(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Backfill template aliases so DB prompts can use stable names even when the
    canonical source field lives elsewhere in the context.
    """
    tech_data = context.get("tech_data", {}) or {}
    realtime_data = context.get("realtime_data", {}) or {}
    extra = dict(context.get("extra_indicators") or context.get("extra") or {})

    deviate_pct = _safe_float(extra.get("deviate_pct"))
    if deviate_pct is None:
        deviate_pct = _safe_float(tech_data.get("distance_from_ma20"))

    if deviate_pct is None:
        price = _safe_float(realtime_data.get("price"))
        if price is None:
            price = _safe_float(tech_data.get("close"))
        ma20 = _safe_float(tech_data.get("ma20"))
        if price is not None and ma20 not in (None, 0):
            deviate_pct = (price - ma20) / ma20 * 100

    if deviate_pct is not None:
        extra["deviate_pct"] = round(deviate_pct, 2)

    context["extra_indicators"] = extra
    context["extra"] = extra
    return context


def get_prompt_from_db(slug: str, context: Dict[str, Any]) -> str:
    """
    Fetch prompt template from database and format with context using Jinja2
    """
    context = _ensure_prompt_derived_fields(_normalize_context_from_snapshot(context))
    strategy = database.get_strategy_by_slug(slug)
    if not strategy or not strategy.get("template_content"):
        print(f"⚠️ Strategy {slug} not found in DB or empty. Fallback needed.")
        return None

    try:
        from context_builder import build_strategy_context

        # Respect an already prepared ctx from StrategyDataFactory. Rebuilding here
        # can overwrite fresher values (for example volume_ratio from the factory path).
        stock_info = context.get("stock_info", {})
        tech_data = context.get("tech_data", {})
        existing_ctx = context.get("ctx")
        if not existing_ctx and (stock_info or tech_data):
            realtime_data = context.get("realtime_data", {})
            market_context = context.get("market_context", {})
            extra_indicators = context.get(
                "extra_indicators", context.get("extra", {})
            )
            intraday = context.get("intraday", {})

            clean_context = build_strategy_context(
                stock_info=stock_info,
                tech_data=tech_data,
                realtime_data=realtime_data,
                market_context=market_context,
                extra_indicators=extra_indicators,
                intraday=intraday,
            )
            # Inject new unified object, keeping old keys for backwards compatibility
            context["ctx"] = clean_context

        # DB content is now repaired to valid Jinja2 syntax by repair_db_prompts.py
        template_str = strategy["template_content"]

        # 使用 Undefined 容错：模板引用不存在的变量时不报错，输出空字符串
        from jinja2 import Environment, Undefined

        env = Environment(undefined=Undefined)
        template = env.from_string(template_str)
        result = template.render(**context)
        return result

    except Exception as e:
        print(f"❌ Error generating prompt for {slug}: {e}")
        import traceback

        traceback.print_exc()
        return None


def create_risk_prompt(context: Dict[str, Any], **kwargs) -> str:
    """
    Create a strict RISK-FOCUSED prompt for existing HOLDINGS.
    NOW: Tries to load from DB 'stock_holding_risk', else fallback.
    """
    context = _normalize_context_from_snapshot(context)
    stock_info = context.get("stock_info", {})
    tech_data = context.get("tech_data", {})
    print(
        f"股票：{stock_info.get('symbol', 'N/A')} - {stock_info.get('name', 'N/A')} AI 分析（个股风控 - Strategy）"
    )

    # 1. Fetch dynamic params for context optimization
    context_params = {}
    try:
        strategy = database.get_strategy_by_slug("stock_holding_risk")
        if strategy and strategy.get("params"):
            # Pass these params to Jinja2 context so prompt can use them
            # e.g. {{ params.risk_sensitivity }}
            context_params = strategy["params"]
    except Exception:
        pass

    # Expose params to template dictionary
    context["params"] = context_params

    db_prompt = get_prompt_from_db("stock_holding_risk", context)

    if db_prompt:
        return db_prompt

    # Fallback (Hardcoded)
    machine_snapshot = "\n".join(context.get("machine_snapshot_lines", []))
    prompt = f"""# Machine Snapshot
{machine_snapshot}

# Raw Evidence
- 当前价格: {tech_data.get("close", "N/A")}
- MA20/MA60: {tech_data.get("ma20", "N/A")} / {tech_data.get("ma60", "N/A")}
- RSI: {tech_data.get("rsi", "N/A")}
- 量比: {tech_data.get("volume_ratio", "N/A")}

# Task Contract
你是严格的A股风险控制官。先判断是否同意机器评分，再说明原因，最后给出明确动作。
输出必须包含：
1. 对机器评分的态度（agree/partial/disagree）
2. 关键证据
3. 最终动作（BUY/HOLD/REDUCE/SELL/WAIT）
4. 如要推翻机器结论，必须明确说明依据。
"""
    return prompt


def create_crypto_prompt(context: Dict[str, Any], **kwargs) -> str:
    """
    Create a VOLATILITY-FOCUSED prompt for CRYPTO.
    """
    stock_info = context.get("stock_info", {})
    print(
        f"Crypto: {stock_info.get('symbol', 'N/A')} - {stock_info.get('name', 'N/A')} AI Analysis"
    )

    db_prompt = get_prompt_from_db("crypto_holding", context)

    if db_prompt:
        return db_prompt

    return "DB Error: crypto_holding prompt not found."


def create_future_prompt(context: Dict[str, Any], **kwargs) -> str:
    """
    Create a LEVERAGE-FOCUSED prompt for FUTURES.
    """
    stock_info = context.get("stock_info", {})
    print(
        f"Future: {stock_info.get('symbol', 'N/A')} - {stock_info.get('name', 'N/A')} AI Analysis"
    )

    db_prompt = get_prompt_from_db("future_holding", context)

    if db_prompt:
        return db_prompt

    return "DB Error: future_holding prompt not found."


def create_etf_holding_prompt(context: Dict[str, Any], **kwargs) -> str:
    """
    Create a LONG-TERM FOCUSED prompt for ETFs.
    NOW: Tries to load from DB 'etf_holding_steady'.
    """
    stock_info = context.get("stock_info", {})
    print(
        f"股票：{stock_info.get('symbol', 'N/A')} - {stock_info.get('name', 'N/A')} AI 分析（ETF定投 - Strategy）"
    )

    db_prompt = get_prompt_from_db("etf_holding_steady", context)

    if db_prompt:
        return db_prompt

    # Fallback
    return "DB Error: etf_holding_steady prompt not found."


def create_speculator_prompt(context: Dict[str, Any], **kwargs) -> str:
    """
    Create a 'Speculator' (游资) style prompt based on DB template 'speculator_mode'.
    """
    tech_data = context.get("tech_data", {})

    # 1. Prepare Data for Computed Context
    price = tech_data.get("close", 0)

    # Position Logic
    ma5 = tech_data.get("ma5")
    ma20 = tech_data.get("ma20")
    ma5_pos = "上方" if ma5 and price > ma5 else "下方"
    ma20_pos = "上方" if ma20 and price > ma20 else "下方"

    # Resistance/Support
    res = tech_data.get(
        "resistance", tech_data.get("pivot_point", price * 1.1)
    )  # Fallback
    sup = tech_data.get("support", tech_data.get("s1", price * 0.9))

    # Extract strengths from score_details
    details = tech_data.get("score_details", [])
    # Filter only "✅" items
    strengths = [d.replace("✅ ", "") for d in details if "✅" in d]
    strength_str = ", ".join(strengths[:3]) if strengths else "暂无明显优势"

    context["computed"] = {
        "ma5_pos": ma5_pos,
        "ma20_pos": ma20_pos,
        "res": f"{res:.2f}",
        "sup": f"{sup:.2f}",
        "strength_str": strength_str,
    }

    db_prompt = get_prompt_from_db("speculator_mode", context)

    if db_prompt:
        return db_prompt

    return "DB Error: speculator_mode prompt not found."


def create_opportunity_prompt(context: Dict[str, Any], **kwargs) -> str:
    """
    Create an OPPORTUNITY-FOCUSED prompt for STOCK CANDIDATES.
    NOW: Checks if 'rank_in_sector' exists to switch to Speculator Mode.
    """
    tech_data = context.get("tech_data", {})
    # Auto-switch to Speculator Mode if we have enhanced data (Sector Rank)
    if "rank_in_sector" in tech_data:
        return create_speculator_prompt(context)

    db_prompt = get_prompt_from_db("candidate_growth", context)

    if db_prompt:
        return db_prompt

    return "DB Error: candidate_growth prompt not found."


def create_realtime_prompt(context: Dict[str, Any], **kwargs) -> str:
    """
    Create a REAL-TIME ACTION prompt.
    NOW: Tries to load from DB 'realtime_intraday'.
    """
    # If the user passed history_data inside context logic previously,
    # we just pass context. The original mapping was {"tech_data": history_data}.
    # Ensure tech_data is there.
    if "history_data" in kwargs:
        context["tech_data"] = kwargs["history_data"]

    db_prompt = get_prompt_from_db("realtime_intraday", context)

    if db_prompt:
        return db_prompt

    return "DB Error: realtime_intraday prompt not found."


def create_intraday_prompt(context: Dict[str, Any], **kwargs) -> str:
    """
    Create a specific INTRADAY prompt for real-time monitoring.
    Uses 'intraday_monitor' template provided by User.
    """
    stock_info = context.get("stock_info", {})
    tech_data = context.get("tech_data", {})
    realtime_data = context.get("realtime_data", {})
    market_context = context.get("market_context", {})

    print(
        f"Intraday: {stock_info.get('symbol', 'N/A')} - {stock_info.get('name', 'N/A')}"
    )

    # --- Prepare Data ---

    # 1. Real-time Basic
    price = realtime_data.get("price", 0)
    change_pct = realtime_data.get("change_pct", 0)
    change_desc = f"{change_pct}%"
    if change_pct > 0:
        change_desc = f"+{change_pct}%"

    vwap = realtime_data.get("vwap", 0)

    # 2. Market Context (from market_context or fallback)
    if not market_context:
        market_context = {}

    print(f"🔍 [create_intraday_prompt] market_context = {market_context}")

    index_name = market_context.get("market_index", {}).get("name", "大盘")
    index_change = market_context.get("market_index", {}).get("change_pct", 0)
    index_trend = market_context.get("market_index", {}).get("trend", "横盘")
    index_desc = f"{index_change}% (分时走势：{index_trend})"

    print(f"🔍 [create_intraday_prompt] index_desc = {index_desc}")

    sector_name = market_context.get("sector_info", {}).get("name", "N/A")
    sector_change = market_context.get("sector_info", {}).get("change_pct", 0)
    # Mock rank for now
    sector_desc = f"[{sector_name}] 板块 (涨跌: {sector_change}%)"

    sentiment_limit_up = market_context.get("sentiment", {}).get(
        "limit_up_count", "N/A"
    )
    sentiment_desc = f"连板高度 {sentiment_limit_up} 板"

    # 3. Technical & Real-time Details

    # Deviate from VWAP (乖离率)
    deviate_msg = "分时均价线附近"
    if vwap > 0:
        deviate = (price - vwap) / vwap * 100
        if deviate > 2:
            deviate_msg = "偏离均价线过远 (上方悬浮)"
        elif deviate < -2:
            deviate_msg = "偏离均价线过远 (下方超跌)"
        elif price < vwap:
            deviate_msg = "承压于分时均价线"
        elif price > vwap:
            deviate_msg = "运行于分时均价线上方"

    # Volume Ratio & Status
    vol_ratio = realtime_data.get("volume_ratio", 0)
    vol_status = "平量震荡"
    if vol_ratio > 1.5:
        vol_status = "放量拉升" if change_pct > 0 else "放量下跌"
    elif vol_ratio < 0.8:
        vol_status = "缩量震荡"

    # Order Flow (WeiBi)
    weibi = realtime_data.get("weibi", 0)
    flow_desc = "买卖均衡"
    if weibi > 30:
        flow_desc = f"主动买盘占优 (委比 {weibi}%)"
    elif weibi < -30:
        flow_desc = f"主动卖盘远大于主动买盘 (委比 {weibi}%)"
    else:
        flow_desc = f"盘口委比 {weibi}%"

    # Support/Resistance (Yesterday or Pivot)
    last_close = tech_data.get("close", price)  # Fallback
    support_price = tech_data.get("s1", last_close * 0.98)
    res_price = tech_data.get("r1", last_close * 1.02)
    pressure_desc = f"支撑位 {support_price:.2f}, 压力位 {res_price:.2f}"

    # Yesterday Score
    score = tech_data.get("composite_score", "N/A")

    # Construct the Prompt
    prompt = f"""# Role
你是一名资深A股短线操盘手，擅长捕捉分时博弈与情绪拐点。当前目标：{stock_info["name"]} ({stock_info["symbol"]})。

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


def create_realtime_etf_prompt(context: Dict[str, Any], **kwargs) -> str:
    """
    Create a REAL-TIME ACTION prompt for ETFs using the specific "Right-Side Trading + Sector Rotation" template.
    """
    stock_info = context.get("stock_info", {})
    tech_data = context.get("tech_data", {})
    realtime_data = context.get("realtime_data", {})
    # 1. Prepare Data Variables

    # Context
    market_change = realtime_data.get("market_index_change", 0)
    market_theme = realtime_data.get(
        "market_theme", realtime_data.get("sector", "未知")
    )  # Use Sector as Theme proxy if Global Theme not avail

    # Target
    etf_name = f"{stock_info['name']} ({stock_info['symbol']})"
    price = realtime_data.get("price", tech_data.get("close", 0))
    change_pct = realtime_data.get("change_pct", 0)

    vol_ratio = realtime_data.get("volume_ratio", tech_data.get("volume_ratio", 0))
    # Vol Status Logic
    if vol_ratio > 2.0:
        vol_status = "放量"
    elif vol_ratio < 0.8:
        vol_status = "缩量"
    else:
        vol_status = "正常"

    # Relative Strength (Simple: Stock Change - Market Change)
    rel_strength_val = change_pct - market_change
    if rel_strength_val > 0.5:
        rel_strength = "跑赢"
    elif rel_strength_val < -0.5:
        rel_strength = "跑输"
    else:
        rel_strength = "跟随"

    # Technicals
    ma20 = tech_data.get("ma20", 0)
    ma60 = tech_data.get("ma60", 0)

    # Position vs MA20
    if price > ma20:
        pos_ma20 = "MA20上方 (支撑)"
    elif price < ma20:
        pos_ma20 = "MA20下方 (压制)"
    else:
        pos_ma20 = "MA20附近"

    # MACD
    dif = tech_data.get("macd_dif", 0)
    dea = tech_data.get("macd_dea", 0)
    if dif > dea:
        macd_status = "金叉"
    elif dif < dea:
        macd_status = "死叉"
    else:
        macd_status = "粘合"
    if dif > 0 and dea > 0:
        macd_status += " (零轴上方)"
    else:
        macd_status += " (零轴下方)"

    rsi = tech_data.get("rsi", 50)

    # Fund Flow
    funds = realtime_data.get("money_flow", {})
    if funds and funds.get("status") == "success":
        net_main = funds.get("net_amount_main", 0)
        fund_flow = f"主力净流入 {net_main:.0f}万"
    else:
        fund_flow = "暂无数据"

    # News Sentiment
    # We just pass the summary and ask LLM to evaluate score.
    news_summary = realtime_data.get("news_summary", "暂无特殊消息")
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


def create_agent_prompt(
    context: Dict[str, Any],
    slug: str = "agent_technician",
    **kwargs,
) -> str:
    """
    统一的 Multi-Agent 辩论专家 Prompt 生成器。
    优先从数据库加载 Jinja2 模板（slug 即为 DB 中的策略标识），兜底使用硬编码。
    """
    from datetime import datetime

    stock_info = context.get("stock_info", {})
    tech_data = context.get("tech_data", {})
    realtime_data = context.get("realtime_data", {}) or {}
    market_context = context.get("market_context", {}) or {
        "market_index": {},
        "sector_info": {},
        "sentiment": {},
    }
    extra_indicators = context.get("extra_indicators", {})

    # 确保安全访问
    if not realtime_data.get("money_flow"):
        realtime_data["money_flow"] = {}

    # 计算衍生值（与 deep_candidate 共享逻辑）
    price = realtime_data.get("price", tech_data.get("close", 0))
    if not price or float(price) == 0:
        price = tech_data.get("close", 0)

    ma5 = tech_data.get("ma5")
    ma20 = tech_data.get("ma20")
    ma5_pos = "上方" if ma5 and float(price) > float(ma5) else "下方"
    ma20_pos = "上方" if ma20 and float(price) > float(ma20) else "下方"

    res = tech_data.get("resistance", tech_data.get("pivot_point", float(price) * 1.1))
    sup = tech_data.get("support", tech_data.get("s1", float(price) * 0.9))

    details = tech_data.get("score_details", [])
    strengths = [d.replace("✅ ", "") for d in details if "✅" in d]
    strength_str = ", ".join(strengths[:3]) if strengths else "暂无明显优势"

    pattern_str = ", ".join(tech_data.get("pattern_details", [])) or "无明显形态"

    # 1. 衍生资金流字符串
    funds = realtime_data.get("money_flow", {})
    net_main = funds.get("net_amount_main", 0)
    net_pct = funds.get("net_pct_main", 0)

    if funds.get("status") == "success" and net_main != 0:
        net_main_val = float(net_main)
        pct_abs = abs(float(net_pct))
        flow_dir = "流出" if net_main_val < 0 else "流入"

        if pct_abs > 5:
            magnitude = "大幅"
        elif pct_abs > 2:
            magnitude = "中幅"
        else:
            magnitude = "小幅"

        net_main_funds_str = f"{net_main_val:.0f}万 (占全天成交额 {float(net_pct):.1f}%, {magnitude}{flow_dir})"
    else:
        net_main_funds_str = "暂无数据"

    # 2. 衍生筹码字符串
    extra = extra_indicators or {}
    vap = extra.get("vap", {})
    winner_rate = vap.get("winner_rate", "N/A")

    if winner_rate != "N/A":
        wr = float(winner_rate)
        if wr > 80:
            winner_rate_label = "筹码处于低位集中状态，获利盘多"
        elif wr < 20:
            winner_rate_label = "筹码处于高位套牢状态，获利盘少"
        else:
            winner_rate_label = "筹码分散，多空博弈激烈"
        winner_rate_str = f"获利盘 {wr:.2f}% ({winner_rate_label})"
    else:
        winner_rate_str = "暂无数据"

    computed = {
        "ma5_pos": ma5_pos,
        "ma20_pos": ma20_pos,
        "res": f"{float(res):.2f}",
        "sup": f"{float(sup):.2f}",
        "strength_str": strength_str,
        "pattern_str": pattern_str,
        "net_main_funds_str": net_main_funds_str,
        "winner_rate_str": winner_rate_str,
    }

    # 优先从 DB 加载模板
    db_prompt = get_prompt_from_db(
        slug,
        {
            **context,  # Unpack the original context
            "computed": computed,  # Add computed values
            "extra": extra_indicators or {},
            "intraday": realtime_data.get("pre_daily_features", {}),
        },
    )

    if db_prompt:
        return db_prompt

    # 兜底：根据 slug 构建差异化上下文
    current_date = datetime.now().strftime("%Y-%m-%d")
    common_header = f"""**分析对象**：{stock_info.get("name", "")} ({stock_info.get("symbol", "")}) [{stock_info.get("asset_type", "stock").upper()}]
**分析日期**：{current_date}
**当前价格**：{price} (涨跌: {realtime_data.get("change_pct", 0)}%)
**市场大盘**：{market_context.get("market_index", {}).get("price", "N/A")} ({market_context.get("market_index", {}).get("change_pct", 0)}%)"""

    if slug == "agent_technician":
        # 技术派：侧重均线、形态、资金流
        funds = realtime_data.get("money_flow", {})
        net_main = funds.get("net_amount_main", 0)
        net_main_val = float(net_main) if net_main else 0
        funds_str = (
            f"主力净流入：{net_main_val:.2f}万 (占比: {funds.get('net_pct_main', 0)}%)"
            if funds.get("status") == "success"
            else "暂无资金流数据"
        )

        context = f"""{common_header}

**技术面深度数据**：
- 均线系统：MA5={tech_data.get("ma5")}, MA20={tech_data.get("ma20")}, MA60={tech_data.get("ma60")}
- 均线排列：{tech_data.get("ma_arrangement", "未知")}
- K线形态：{pattern_str} (形态分: {tech_data.get("pattern_score", 0)})
- 相对强弱(RSI)：{tech_data.get("rsi", "N/A")}
- 支撑/压力：支撑位 {computed["sup"]}, 压力位 {computed["res"]}
- 波动率(ATR)：{tech_data.get("atr_pct", "N/A")}%
- 资金流向：{funds_str}
"""
    elif slug == "agent_fundamentalist":
        # 基本面派：侧重估值、财务、长期趋势
        context = f"""{common_header}

**基本面深度数据**：
- 估值指标：PE(动态)={realtime_data.get("pe_ratio", "N/A")}, PB={realtime_data.get("pb_ratio", "N/A")}, 总市值={realtime_data.get("total_mv", "N/A")}
- 长期趋势：MA60={tech_data.get("ma60")} (牛熊分界)
- 综合评分：{tech_data.get("composite_score", "N/A")}
- 核心优势：{strength_str}
"""
    elif slug == "agent_risk_officer":
        # 风控官：侧重波动、盈亏比、市场环境
        ma20_val = (
            float(tech_data.get("ma20", price))
            if tech_data.get("ma20")
            else float(price)
        )
        deviate_pct = (float(price) - ma20_val) / ma20_val * 100 if ma20_val > 0 else 0
        context = f"""{common_header}

**风控核心指标**：
- 波动率(ATR%)：{tech_data.get("atr_pct", "N/A")}% (高波动需降仓)
- 市场环境：{market_context.get("market_index", {}).get("change_pct", 0)}% (大盘涨跌)
- 盈亏比评估：上方压力 {computed["res"]} vs 下方支撑 {computed["sup"]}
- 乖离率：当前价格距离 MA20 {deviate_pct:.2f}%
"""
    else:
        context = common_header

    # 从 DB 加载 Agent 角色名和描述
    strategy = database.get_strategy_by_slug(slug)
    agent_name = strategy["name"] if strategy else slug
    agent_role = (
        strategy["params"].get("role", "专家")
        if strategy and strategy.get("params")
        else "专家"
    )
    agent_desc = strategy.get("description", "") if strategy else ""

    prompt = f"""请你扮演【{agent_name}】（{agent_role}）。
你的核心职责是：{agent_desc}

{context}

请根据以上数据，给出你的专业分析意见。
要求：
1. 严格遵守你的人设，不要试图平衡观点，那是CIO的工作。
2. 观点必须鲜明，有理有据。
3. 如果数据不足以支持你的领域分析，直接指出。
4. 输出格式为Markdown，不要包含寒暄。
"""
    return prompt


def create_agent_washout_prompt(context: Dict[str, Any], **kwargs) -> str:
    """
    异动/洗盘分析师（Agent B）的 Prompt 生成器。
    专注于发现"错杀"和"诱空"机会，分析量价背离、缩量下跌、关键支撑位测试等。
    优先从数据库加载 Jinja2 模板（slug='agent_washout_hunter'），兜底使用硬编码。
    """
    context = _normalize_context_from_snapshot(context)
    from datetime import datetime

    stock_info = context.get("stock_info", {})
    tech_data = context.get("tech_data", {})
    realtime_data = context.get("realtime_data", {}) or {}
    market_context = context.get("market_context", {}) or {
        "market_index": {},
        "sector_info": {},
        "sentiment": {},
    }
    extra_indicators = context.get("extra_indicators", {})

    if not realtime_data.get("money_flow"):
        realtime_data["money_flow"] = {}

    # 计算衍生值
    price = realtime_data.get("price", tech_data.get("close", 0))
    if not price or float(price) == 0:
        price = tech_data.get("close", 0)

    ma5 = tech_data.get("ma5")
    ma20 = tech_data.get("ma20")
    ma5_pos = "上方" if ma5 and float(price) > float(ma5) else "下方"
    ma20_pos = "上方" if ma20 and float(price) > float(ma20) else "下方"

    res = tech_data.get("resistance", tech_data.get("pivot_point", float(price) * 1.1))
    sup = tech_data.get("support", tech_data.get("s1", float(price) * 0.9))

    details = tech_data.get("score_details", [])
    strengths = [d.replace("✅ ", "") for d in details if "✅" in d]
    strength_str = ", ".join(strengths[:3]) if strengths else "暂无明显优势"

    pattern_str = ", ".join(tech_data.get("pattern_details", [])) or "无明显形态"

    computed = {
        "ma5_pos": ma5_pos,
        "ma20_pos": ma20_pos,
        "res": f"{float(res):.2f}",
        "sup": f"{float(sup):.2f}",
        "strength_str": strength_str,
        "pattern_str": pattern_str,
    }

    # 优先从 DB 加载模板
    db_prompt = get_prompt_from_db(
        "agent_washout_hunter",
        {
            **context,
            "computed": computed,
            "extra": extra_indicators or {},
            "intraday": realtime_data.get("pre_daily_features", {}),
        },
    )

    if db_prompt:
        return db_prompt

    # 兜底硬编码：构建异动/洗盘分析专用 prompt
    current_date = datetime.now().strftime("%Y-%m-%d")
    funds = realtime_data.get("money_flow", {})
    net_main = funds.get("net_amount_main", 0)
    net_main_val = float(net_main) if net_main else 0

    # 量比和换手率（判断缩量的关键）
    volume_ratio = tech_data.get(
        "volume_ratio", realtime_data.get("volume_ratio", "N/A")
    )

    # 大盘涨跌 vs 个股涨跌（判断筹码锁定/错杀）
    market_chg = market_context.get("market_index", {}).get("change_pct", 0)
    stock_chg = realtime_data.get("change_pct", 0)

    # 筹码分布数据
    extra = extra_indicators or {}
    vap_info = extra.get("vap", {})
    vap_desc = vap_info.get("desc", "暂无筹码数据") if vap_info else "暂无筹码数据"

    # 乖离率
    ma20_val = (
        float(tech_data.get("ma20", price)) if tech_data.get("ma20") else float(price)
    )
    deviate_pct = (float(price) - ma20_val) / ma20_val * 100 if ma20_val > 0 else 0

    machine_snapshot = "\n".join(context.get("machine_snapshot_lines", []))
    prompt = f"""# Machine Snapshot
{machine_snapshot}

请你扮演【异动/洗盘分析师】（逆向思维专家）。
你的核心职责是：专门寻找"错杀"和"诱空"机会——当市场恐慌性抛售或主力刻意打压洗盘时，识别真正的买入良机。

**分析对象**：{stock_info.get("name", "")} ({stock_info.get("symbol", "")}) [{stock_info.get("asset_type", "stock").upper()}]
**分析日期**：{current_date}
**当前价格**：{price} (涨跌: {stock_chg}%)
**市场大盘**：{market_context.get("market_index", {}).get("price", "N/A")} ({market_chg}%)

**【核心分析数据 - 量价背离与洗盘信号】**

1. **量价关系**：
   - 量比：{volume_ratio} (低于0.8视为缩量)
   - 主力净流入：{net_main_val:.2f}万 (占比: {funds.get("net_pct_main", 0)}%)
   - 资金流向状态：{funds.get("status", "未知")}

2. **关键支撑位测试**：
   - 当前价在MA5 {ma5_pos} (MA5={ma5})
   - 当前价在MA20 {ma20_pos} (MA20={ma20})
   - MA60（牛熊线）：{tech_data.get("ma60", "N/A")}
   - 下方支撑：{computed["sup"]}，上方压力：{computed["res"]}
   - 乖离率（距MA20）：{deviate_pct:.2f}%

3. **大盘涨个股跌 / 筹码锁定分析**：
   - 大盘涨跌：{market_chg}%，个股涨跌：{stock_chg}%
   - 差异：{float(stock_chg) - float(market_chg):.2f}% {"⚠️ 个股明显弱于大盘" if float(stock_chg) - float(market_chg) < -1 else ""}
   - 筹码分布：{vap_desc}

4. **K线形态与RSI超卖**：
   - K线形态：{pattern_str}
   - RSI：{tech_data.get("rsi", "N/A")} {"🟢 超卖区域" if tech_data.get("rsi") and float(tech_data.get("rsi", 50)) < 30 else ""}
   - KDJ：K={tech_data.get("kdj_k", "N/A")}, D={tech_data.get("kdj_d", "N/A")}
   - MACD：DIF={tech_data.get("macd_dif", "N/A")}, DEA={tech_data.get("macd_dea", "N/A")}

**请按照以下框架进行分析：**

1. **洗盘 vs 出货判定**：结合成交量和价格走势，判断当前下跌是"缩量洗盘"还是"放量出货"
2. **关键支撑位有效性**：是否跌破了MA20/MA60/前低等关键支撑？未放量跌破则倾向洗盘
3. **筹码锁定度**：获利盘占比、成本集中度，判断主力是否仍在控盘
4. **错杀/诱空信号**：大盘涨个股跌、缩量回调至支撑位、RSI超卖等反向买入信号
5. **买点预案**：如果判定为洗盘，给出具体的入场价位和止损位

要求：
1. 你的立场是"逆向思维"——即便资金流出，只要未放量跌破关键位，倾向于判定为洗盘。
2. 观点必须鲜明，有理有据，不要试图平衡观点。
3. 如果确认是真正的出货/破位，必须直接指出，不能强行看多。
4. 先判断是否同意机器评分，再给出你的逆向观点。
5. 最后必须输出一个 JSON 对象，字段为 stance、machine_score_judgement、key_evidence、risk_override、final_action。
"""
    return prompt


def create_agent_fundamentals_prompt(context: Dict[str, Any], **kwargs) -> str:
    """
    基本面分析师（Agent C）的 Prompt 生成器。
    通过市盈率、市净率、每股净资产、净资产收益率等指标判断股票基本面。
    优先从数据库加载 Jinja2 模板（slug='agent_fundamentals'），兜底使用硬编码。
    """
    context = _normalize_context_from_snapshot(context)
    from datetime import datetime

    stock_info = context.get("stock_info", {})
    tech_data = context.get("tech_data", {})
    realtime_data = context.get("realtime_data", {}) or {}
    market_context = context.get("market_context", {}) or {
        "market_index": {},
        "sector_info": {},
        "sentiment": {},
    }
    extra_indicators = context.get("extra_indicators", {})

    price = realtime_data.get("price", tech_data.get("close", 0))
    if not price or float(price) == 0:
        price = tech_data.get("close", 0)

    # 提取基本面指标（优先从 extra_indicators，其次 realtime_data）
    extra = extra_indicators or {}
    pe_ratio = extra.get("pe_ratio", realtime_data.get("pe_ratio", "N/A"))
    pb_ratio = extra.get("pb_ratio", realtime_data.get("pb_ratio", "N/A"))
    bvps = extra.get("bvps", realtime_data.get("bvps", "N/A"))  # 每股净资产
    roe = extra.get("roe", realtime_data.get("roe", "N/A"))  # 净资产收益率
    total_mv = extra.get("total_mv", realtime_data.get("total_mv", "N/A"))  # 总市值
    eps = extra.get("eps", realtime_data.get("eps", "N/A"))  # 每股收益

    computed = {
        "pe_ratio": pe_ratio,
        "pb_ratio": pb_ratio,
        "bvps": bvps,
        "roe": roe,
        "total_mv": total_mv,
        "eps": eps,
    }

    # 优先从 DB 加载模板
    db_prompt = get_prompt_from_db(
        "agent_fundamentals",
        {
            **context,
            "computed": computed,
            "extra": extra,
        },
    )

    if db_prompt:
        return db_prompt

    # 兜底硬编码
    current_date = datetime.now().strftime("%Y-%m-%d")

    machine_snapshot = "\n".join(context.get("machine_snapshot_lines", []))
    prompt = f"""# Machine Snapshot
{machine_snapshot}

请你扮演【基本面分析师】（价值投资研究员）。
你的核心职责是：通过财务指标和估值体系判断这只股票的基本面质量和投资价值。

**分析对象**：{stock_info.get("name", "")} ({stock_info.get("symbol", "")}) [{stock_info.get("asset_type", "stock").upper()}]
**分析日期**：{current_date}
**当前价格**：{price} (涨跌: {realtime_data.get("change_pct", 0)}%)
**所属板块**：{market_context.get("sector_info", {}).get("name", "N/A")} ({market_context.get("sector_info", {}).get("change_pct", 0)}%)

**【核心基本面指标】**

| 指标 | 数值 | 说明 |
|------|------|------|
| 市盈率 (PE-TTM) | {pe_ratio} | 低于行业均值为低估 |
| 市净率 (PB) | {pb_ratio} | 低于1可能被低估，但需结合行业 |
| 每股净资产 (BVPS) | {bvps} | 反映公司账面价值 |
| 净资产收益率 (ROE) | {roe} | 高于15%为优秀，核心盈利指标 |
| 每股收益 (EPS) | {eps} | 反映公司盈利能力 |
| 总市值 | {total_mv} | 反映公司规模 |

**【辅助参考 - 技术面快照】**

- 综合评分：{tech_data.get("composite_score", "N/A")}
- 均线排列：{tech_data.get("ma_arrangement", "未知")}
- MA60（牛熊线）：{tech_data.get("ma60", "N/A")}
- 核心优势：{", ".join([d.replace("✅ ", "") for d in tech_data.get("score_details", []) if "✅" in d][:3]) or "暂无"}

**请按照以下框架进行分析：**

1. **估值判断**：当前PE/PB是否合理？相对于行业平均水平是高估还是低估？
2. **盈利质量**：ROE水平如何？EPS趋势如何？公司盈利能力是否可持续？
3. **资产质量**：每股净资产与当前股价的关系，PB是否有安全边际？
4. **综合评级**：从基本面角度，当前价位是否具有投资价值？
5. **风险提示**：基本面存在的隐患或不确定性

要求：
1. 严格基于财务指标和估值体系分析，不要过多涉及技术面。
2. 观点必须鲜明，有理有据，不要试图平衡观点。
3. 如果基本面数据不足（N/A较多），直接指出数据缺失，不要凭空推测。
4. 先判断是否同意机器评分。
5. 最后必须输出一个 JSON 对象，字段为 stance、machine_score_judgement、key_evidence、risk_override、final_action。
"""
    return prompt


def create_agent_cio_prompt(
    context: Dict[str, Any],
    agent_results: list = None,
    **kwargs,
) -> str:
    """
    CIO（首席投资官）的 Prompt 生成器。
    汇总各专家意见后进行综合裁决。
    优先从数据库加载 Jinja2 模板（slug='agent_cio'），兜底使用硬编码。
    """
    context = _normalize_context_from_snapshot(context)
    from datetime import datetime

    stock_info = context.get("stock_info", {})
    tech_data = context.get("tech_data", {})
    realtime_data = context.get("realtime_data", {}) or {}
    market_context = context.get("market_context", {}) or {
        "market_index": {},
        "sector_info": {},
        "sentiment": {},
    }

    if not agent_results:
        agent_results = []

    price = realtime_data.get("price", tech_data.get("close", 0))
    current_date = datetime.now().strftime("%Y-%m-%d")

    common_header = f"""**分析对象**：{stock_info.get("name", "")} ({stock_info.get("symbol", "")}) [{stock_info.get("asset_type", "stock").upper()}]
**分析日期**：{current_date}
**当前价格**：{price} (涨跌: {realtime_data.get("change_pct", 0)}%)
**市场大盘**：{market_context.get("market_index", {}).get("price", "N/A")} ({market_context.get("market_index", {}).get("change_pct", 0)}%)"""

    # 拼接各专家意见
    debate_summary = "\n".join(agent_results)
    machine_snapshot = "\n".join(context.get("machine_snapshot_lines", []))

    # 获取策略属性以填充模板
    import database

    strategy = database.get_strategy_by_slug("agent_cio")
    name = strategy["name"] if strategy else "首席投资官"
    role = (
        strategy["params"].get("role", "CIO")
        if strategy and strategy.get("params")
        else "CIO"
    )
    description = (
        strategy.get("description", "整合多维度分析意见并做出最终投资决策。")
        if strategy
        else "整合多维度分析意见并做出最终投资决策。"
    )
    context_str = f"{common_header}\n\n**专家团队辩论摘要**：\n{debate_summary}"

    # 优先从 DB 加载模板
    db_prompt = get_prompt_from_db(
        "agent_cio",
        {
            **context,
            "common_header": common_header,
            "debate_summary": debate_summary,
            "agent_results": agent_results,
            "name": name,
            "role": role,
            "description": description,
            "context": context_str,
            "machine_snapshot": machine_snapshot,
        },
    )

    if db_prompt:
        return db_prompt

    # 兜底
    prompt = f"""# Machine Snapshot
{machine_snapshot}

{common_header}

**专家团队辩论摘要**：
{debate_summary}

请根据以上信息，进行最终总结和决策。
你必须显式判断：
1. 最终动作
2. 风险等级
3. 共识强弱
4. 机器评分是否需要被 override
"""
    return prompt


def create_deep_candidate_prompt(context: Dict[str, Any], **kwargs) -> str:
    """
    Create a DEEP MONITOR prompt for A-share stocks using 'deep_monitor' template.
    Now uses EXPLICIT market_context argument.
    """
    tech_data = context.get("tech_data", {})
    realtime_data = context.get("realtime_data", {}) or {}
    extra_indicators = context.get("extra_indicators", {})

    # Ensure money_flow safety for template access
    if not realtime_data.get("money_flow"):
        realtime_data["money_flow"] = {}

    # --- Prepare Computed Context (Shared with Speculator Mode) ---
    # Use Realtime Price if available, else tech_data close
    price = realtime_data.get("price", tech_data.get("close", 0))
    if price == 0:
        price = tech_data.get("close", 0)

    # Position Logic
    ma5 = tech_data.get("ma5")
    ma20 = tech_data.get("ma20")
    ma5_pos = "上方" if ma5 and price > ma5 else "下方"
    ma20_pos = "上方" if ma20 and price > ma20 else "下方"

    # Resistance/Support
    res = tech_data.get(
        "resistance", tech_data.get("pivot_point", price * 1.1)
    )  # Fallback
    sup = tech_data.get("support", tech_data.get("s1", price * 0.9))

    # Extract strengths from score_details
    details = tech_data.get("score_details", [])
    # Filter only "✅" items
    strengths = [d.replace("✅ ", "") for d in details if "✅" in d]
    strength_str = ", ".join(strengths[:3]) if strengths else "暂无明显优势"

    computed = {
        "ma5_pos": ma5_pos,
        "ma20_pos": ma20_pos,
        "res": f"{res:.2f}",
        "sup": f"{sup:.2f}",
        "strength_str": strength_str,
    }

    db_prompt = get_prompt_from_db(
        "deep_monitor",
        {
            **context,
            "computed": computed,
            "extra": extra_indicators or {},
            "intraday": context.get(
                "intraday", realtime_data.get("pre_daily_features", {})
            ),
        },
    )

    if db_prompt:
        return db_prompt
    return "DB Error: deep_monitor prompt not found."


def create_agent_trend_follower_prompt(context: Dict[str, Any], **kwargs) -> str:
    """
    Create a TRENDFOLLOWER prompt for A-share stocks using 'deep_monitor' template.
    Now uses EXPLICIT market_context argument.
    """
    context = _normalize_context_from_snapshot(context)
    tech_data = context.get("tech_data", {})
    realtime_data = context.get("realtime_data", {}) or {}
    extra_indicators = context.get("extra_indicators", {})

    # Ensure money_flow safety for template access
    if not realtime_data.get("money_flow"):
        realtime_data["money_flow"] = {}

    # --- Prepare Computed Context (Shared with Speculator Mode) ---
    # Use Realtime Price if available, else tech_data close
    price = realtime_data.get("price", tech_data.get("close", 0))
    if price == 0:
        price = tech_data.get("close", 0)

    # Position Logic
    ma5 = tech_data.get("ma5")
    ma20 = tech_data.get("ma20")
    ma5_pos = "上方" if ma5 and price > ma5 else "下方"
    ma20_pos = "上方" if ma20 and price > ma20 else "下方"

    # Resistance/Support
    res = tech_data.get(
        "resistance", tech_data.get("pivot_point", price * 1.1)
    )  # Fallback
    sup = tech_data.get("support", tech_data.get("s1", price * 0.9))

    # Extract strengths from score_details
    details = tech_data.get("score_details", [])
    # Filter only "✅" items
    strengths = [d.replace("✅ ", "") for d in details if "✅" in d]
    strength_str = ", ".join(strengths[:3]) if strengths else "暂无明显优势"

    computed = {
        "ma5_pos": ma5_pos,
        "ma20_pos": ma20_pos,
        "res": f"{res:.2f}",
        "sup": f"{sup:.2f}",
        "strength_str": strength_str,
    }

    db_prompt = get_prompt_from_db(
        "agent_trend_follower",
        {
            **context,
            "computed": computed,
            "extra": extra_indicators or {},
            "intraday": context.get(
                "intraday", realtime_data.get("pre_daily_features", {})
            ),
        },
    )

    if db_prompt:
        return db_prompt

    machine_snapshot = "\n".join(context.get("machine_snapshot_lines", []))
    return f"""# Machine Snapshot
{machine_snapshot}

# Raw Evidence
- 均线: MA5={tech_data.get("ma5")} MA20={tech_data.get("ma20")} MA60={tech_data.get("ma60")}
- 均线排列: {tech_data.get("ma_arrangement", "未知")}
- MACD: DIF={tech_data.get("macd_dif", "N/A")} DEA={tech_data.get("macd_dea", "N/A")}
- RSI: {tech_data.get("rsi", "N/A")}
- 量比: {tech_data.get("volume_ratio", "N/A")}

# Task Contract
你是趋势跟随者。先判断是否同意机器评分，只从趋势和延续性角度给结论。
最后必须输出一个 JSON 对象，字段为 stance、machine_score_judgement、key_evidence、risk_override、final_action。
"""


def create_realtime_crypto_prompt(context: Dict[str, Any], **kwargs) -> str:
    """
    Create a REAL-TIME ACTION prompt for CRYPTO.
    """
    if "history_data" in kwargs:
        context["tech_data"] = kwargs["history_data"]

    db_prompt = get_prompt_from_db("realtime_crypto", context)

    if db_prompt:
        return db_prompt

    return "DB Error: realtime_crypto prompt not found."


def create_realtime_future_prompt(context: Dict[str, Any], **kwargs) -> str:
    """
    Create a REAL-TIME ACTION prompt for FUTURES.
    """
    if "history_data" in kwargs:
        context["tech_data"] = kwargs["history_data"]

    db_prompt = get_prompt_from_db("realtime_future", context)

    if db_prompt:
        return db_prompt

    return "DB Error: realtime_future prompt not found."

    return "DB Error: realtime_future prompt not found."


def create_analysis_prompt(
    context: Dict[str, Any],
    analysis_type: str = "holding",
    **kwargs,
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
    context = _normalize_context_from_snapshot(context)
    stock_info = context.get("stock_info", {})
    asset_type = stock_info.get("asset_type", stock_info.get("type", "stock"))
    is_etf = asset_type == "etf"

    if analysis_type == "intraday":
        return create_intraday_prompt(context)

    # --- Multi-Agent 辩论角色分支 ---
    if analysis_type == "agent_trend_follower":
        # Agent A：趋势跟随者（绝对右侧），直接复用 deep_candidate 的 prompt
        return create_agent_trend_follower_prompt(context)
    elif analysis_type == "agent_washout_hunter":
        # Agent B：异动/洗盘分析师（逆向思维）
        return create_agent_washout_prompt(context)
    elif analysis_type == "agent_fundamentals":
        # Agent C：基本面分析师
        return create_agent_fundamentals_prompt(context)
    elif analysis_type == "agent_cio":
        return create_agent_cio_prompt(
            context, agent_results=kwargs.get("agent_results", [])
        )

    if analysis_type == "realtime":
        if asset_type == "crypto":
            return create_realtime_crypto_prompt(context)
        elif asset_type == "future":
            return create_realtime_future_prompt(context)
        elif is_etf:
            return create_realtime_etf_prompt(context)
    elif analysis_type == "deep_candidate":
        # A股专家分析
        return create_deep_candidate_prompt(context)

    elif analysis_type == "candidate":
        # Candidates are usually stocks, but could technically be ETFs
        return create_opportunity_prompt(context)

    else:
        # Holdings analysis / Daily Report
        if asset_type == "crypto":
            return create_crypto_prompt(context)
        elif asset_type == "future":
            return create_future_prompt(context)
        elif is_etf:
            return create_etf_holding_prompt(context)
        else:
            return create_risk_prompt(context)


def _get_system_instruction(analysis_type: str, stock_info: Dict[str, Any]) -> str:
    """
    Helper to determine the system instruction based on analysis type and asset type.
    Multi-Agent 角色优先从 DB 加载 system_prompt 参数。
    """
    asset_type = stock_info.get("asset_type", stock_info.get("type", "stock"))
    is_etf = asset_type == "etf"

    # --- Multi-Agent 角色分支（优先从 DB 读取 system_prompt） ---
    agent_slugs = {
        "agent_trend_follower": "你是一位绝对右侧交易的趋势跟随者，只做已经确认趋势启动的股票，擅长通过均线系统、量价共振和资金流向来确认趋势。",
        "agent_washout_hunter": "你是一位专注于发现'错杀'和'诱空'机会的异动分析师，擅长分析量价背离、缩量洗盘、关键支撑位测试等反向信号。",
        "agent_fundamentals": "你是一位资深的基本面研究员，擅长通过市盈率、市净率、每股净资产、净资产收益率等核心指标判断股票的内在价值。",
        "agent_cio": "你是一位拥有全局视野的首席投资官(CIO)，擅长整合多维度分析意见并做出最终投资决策。",
    }

    if analysis_type in agent_slugs:
        # 优先从 DB 加载
        strategy = database.get_strategy_by_slug(analysis_type)
        if strategy and strategy.get("params", {}).get("system_prompt"):
            return strategy["params"]["system_prompt"]
        # 兜底
        return agent_slugs[analysis_type]

    system_instruction = "你是一名严格的风险控制官，首要任务是保护资本。"

    if analysis_type == "candidate":
        system_instruction = "你是一名拥有20年实战经验的A股游资操盘手。你的风格是：犀利、客观、风险厌恶，只做大概率的确定性交易。"
    elif analysis_type == "realtime":
        if is_etf:
            system_instruction = (
                "你是一名稳健的资产配置专家，擅长ETF投资，注重长期趋势，过滤短期噪音。"
            )
        elif asset_type == "crypto":
            system_instruction = (
                "你是一名资深的加密货币交易员，习惯高波动风险和7x24小时市场。"
            )
        elif asset_type == "future":
            system_instruction = "你是一名专业的期货交易员，极其重视杠杆风险管理。"
        else:
            system_instruction = "你是一名深谙A股主力资金运作模式的资深策略分析师。你擅长通过技术面、资金面和基本面的共振来寻找确定性机会。你的风格是：客观、犀利、重实战、不讲废话。"
    elif is_etf:  # Static holding analysis for ETF
        system_instruction = "你是一名稳健的资产配置专家，擅长ETF投资。"
    elif asset_type == "crypto":
        system_instruction = "你是一名资深的加密货币交易员，风格激进但重视止损。"
    elif asset_type == "future":
        system_instruction = "你是一名专业的期货交易员，擅长日内和波段交易。"

    return system_instruction


def generate_analysis_gemini(
    context: Dict[str, Any],
    project_id: str,
    location: str,
    credentials_path: str = None,
    model: str = "gemini-2.5-flash",
    analysis_type: str = "holding",
    **kwargs,
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
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path

        client = genai.Client(vertexai=True, project=project_id, location=location)

        # [Refactored] passing context directly down
        prompt = create_analysis_prompt(
            context=context,
            analysis_type=analysis_type,
            **kwargs,
        )

        stock_info = context.get("stock_info", {})

        # Log the full prompt
        print(
            f"\n======== [Gemini Prompt Debug ({analysis_type})] ========\n{prompt}\n=========================================================\n"
        )

        # [Refactored] Use shared helper for system instruction
        system_instruction = _get_system_instruction(analysis_type, stock_info)

        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=8192,
                system_instruction=system_instruction,
            ),
        )

        if hasattr(response, "text"):
            analysis = response.text
        elif hasattr(response, "candidates") and len(response.candidates) > 0:
            candidate = response.candidates[0]
            if hasattr(candidate, "content") and hasattr(candidate.content, "parts"):
                analysis = "".join(
                    [
                        part.text
                        for part in candidate.content.parts
                        if hasattr(part, "text")
                    ]
                )
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
    context: Dict[str, Any],
    api_key: str,
    base_url: str,
    model: str,
    analysis_type: str = "holding",
    provider: str = "openai",
    **kwargs,
) -> str:
    """
    Generate LLM-based trading analysis using OpenAI-compatible API
    """
    try:
        client = OpenAI(api_key=api_key, base_url=base_url)

        # [Refactored] passing context directly down
        prompt = create_analysis_prompt(
            context=context,
            analysis_type=analysis_type,
            **kwargs,
        )

        stock_info = context.get("stock_info", {})

        # Log the full prompt
        print(
            f"\n======== [OpenAI Prompt Debug ({model} - {analysis_type})] ========\n{prompt}\n========================================================================\n"
        )

        # [Refactored] Use setup system instruction
        system_content = _get_system_instruction(analysis_type, stock_info)

        # Prepare API call parameters
        api_params = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_content},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,  # Low temp for consistent trading signals
            "max_tokens": 4096,
        }

        # Add thinking parameter for GLM provider
        if provider == "glm":
            api_params["extra_body"] = {"thinking": {"type": "disabled"}}

        response = client.chat.completions.create(**api_params)

        analysis = response.choices[0].message.content
        return analysis

    except Exception as e:
        error_msg = f"❌ LLM分析错误：{str(e)}"
        print(error_msg)
        return f"**分析失败**：{error_msg}"


def generate_analysis(
    context: Dict[str, Any],
    api_config: Dict[str, Any],
    analysis_type: str = "holding",
    **kwargs,
) -> str:
    """
    Generate LLM-based trading analysis (supports multiple providers)
    """
    provider = api_config.get("provider", "openai")

    if provider == "gemini":
        return generate_analysis_gemini(
            context=context,
            project_id=api_config["project_id"],
            location=api_config["location"],
            credentials_path=api_config.get("credentials_path"),
            model=api_config.get("model", "gemini-2.5-flash"),
            analysis_type=analysis_type,
            **kwargs,
        )
    else:
        # OpenAI 兼容的 API（包括 OpenAI, DeepSeek, GLM 等）
        return generate_analysis_openai(
            context=context,
            api_key=api_config["api_key"],
            base_url=api_config["base_url"],
            model=api_config["model"],
            analysis_type=analysis_type,
            provider=provider,
            **kwargs,
        )


def format_etf_section(
    stock_info: Dict[str, Any], tech_data: Dict[str, Any], llm_analysis: str
) -> str:
    """
    Format a complete ETF analysis section in Markdown (simplified, long-term focused)
    """
    # 综合评分显示
    score = tech_data.get("composite_score", "N/A")
    rating = tech_data.get("rating", "未知")

    # 评分详情
    score_breakdown = tech_data.get("score_breakdown", [])
    score_details = tech_data.get("score_details", [])

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
    operation_suggestion = tech_data.get("operation_suggestion", "暂无建议")

    # 判断价格与MA60关系
    close = tech_data.get("close", 0)
    ma60 = tech_data.get("ma60", 0)
    ma60_status = "上方 (多头)" if close > ma60 else "下方 (调整)"

    section = f"""
## {stock_info["symbol"]} - {stock_info["name"]} 【ETF】
### 📅 报告日期：{tech_data.get("date", "未知")}

### 📊 ETF长期持有评分：{score}分 - {rating}

**💡 操作建议：{operation_suggestion}**

{score_section}

**价格数据（{tech_data["date"]}）：**
- 当前价：¥{tech_data["close"]} | 开盘：¥{tech_data["open"]} | 最高：¥{tech_data["high"]} | 最低：¥{tech_data["low"]}
- 成本价：¥{stock_info.get("cost_price", "未设置")} | 盈亏：{tech_data.get("profit_loss_pct", "未知")}%

**📈 趋势状态（核心指标）：**
- **MA60 (牛熊线)**：¥{tech_data["ma60"]} → 当前价在 **{ma60_status}**
- MA20 (波段线)：¥{tech_data["ma20"]} | MA5：¥{tech_data.get("ma5", "N/A")}
- 均线排列：**{tech_data.get("ma_arrangement", "未知")}**

**📉 估值指标：**
- RSI（14）：**{tech_data.get("rsi", "N/A")}** → {tech_data.get("rsi_signal", "未知")} {"🟢 加仓机会" if tech_data.get("rsi", 50) < 35 else ""}
- 布林带位置：**{tech_data.get("boll_position", "N/A")}%** → {tech_data.get("boll_signal", "未知")} {"🟢 加仓机会" if tech_data.get("boll_position", 50) < 25 else ""}
- KDJ：K={tech_data.get("kdj_k", "N/A")}, D={tech_data.get("kdj_d", "N/A")} → {tech_data.get("kdj_zone", "未知")}

**🔄 动量指标：**
- MACD：{tech_data["macd_signal"]} (DIF={tech_data["macd_dif"]}, DEA={tech_data["macd_dea"]})

**📊 波动率：**
- ATR波动率：{tech_data.get("atr_pct", "N/A")}%

**信号汇总（ETF视角）：**
| 指标 | 状态 | ETF解读 |
|------|------|---------|
| 趋势（MA60）| {"多头" if close > ma60 else "空头/调整"} | {"持有" if close > ma60 else "可能是加仓机会"} |
| RSI | {tech_data.get("rsi_signal", "未知")} | {"超卖=加仓点" if tech_data.get("rsi", 50) < 30 else "正常"} |
| 布林带 | {tech_data.get("boll_signal", "未知")} | {"下轨=加仓点" if tech_data.get("boll_position", 50) < 20 else "正常"} |
| MACD | {tech_data["macd_signal"]} | 参考趋势方向 |

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
    code_block_match = re.search(
        r'```(?:json)?\s*(\{.*?"buy_trigger".*?\})\s*```', text, re.DOTALL
    )
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
        json_str_clean = re.sub(r"//.*", "", json_str)
        # 2. Fix trailing commas (simple case: , before })
        json_str_clean = re.sub(r",\s*\}", "}", json_str_clean)

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
            "risk_rating": "⚠️ 风险等级",
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


def format_deep_json_plan(text: str) -> str:
    """Format the AI deep reasoning JSON into Markdown"""
    print("🚀 format_deep_json_plan received text", text)
    json_str = None
    code_block_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if code_block_match:
        json_str = code_block_match.group(1)
    else:
        # Match from { to }
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            json_str = text[start : end + 1]

    if not json_str:
        return text

    try:
        json_str_clean = re.sub(r"//.*", "", json_str)
        json_str_clean = re.sub(r",\s*\}", "}", json_str_clean)
        plan = json.loads(json_str_clean)

        md_parts = []

        # 1. 深度推演 (Thinking / analysis_process)
        thinking_match = re.search(r"<thinking>(.*?)</thinking>", text, re.DOTALL)
        if thinking_match:
            thinking_content = thinking_match.group(1).strip()
            if thinking_content:
                md_parts.append(f"**🧠 深度逻辑推演：**\n{thinking_content}\n")

        if "analysis_process" in plan and isinstance(plan["analysis_process"], dict):
            ap = plan["analysis_process"]
            md_parts.append("**🧠 深度逻辑推演 (分析过程)：**")

            # Compatible with both 'trend_and_resonance' and old 'market_resonance'
            trend_res = ap.get("trend_and_resonance", ap.get("market_resonance"))
            if trend_res:
                md_parts.append(f"- **趋势与共振**：{trend_res}")

            if "main_force_intention" in ap:
                md_parts.append(f"- **主力意图**：{ap['main_force_intention']}")
            if "early_trade_logic" in ap:
                md_parts.append(f"- **早盘推演**：{ap['early_trade_logic']}")
            if "late_trade_logic" in ap:
                md_parts.append(f"- **尾盘推演**：{ap['late_trade_logic']}")
            md_parts.append("")

        # 2. 交易计划表
        table = "**🎯 交易执行计划 (Action Plan)**\n\n"
        table += "| 项目 | 内容 |\n"
        table += "|---|---|\n"

        if plan.get("trading_action"):
            action_map = {
                "BUY_EARLY": "早盘买入",
                "BUY_LATE": "尾盘买入",
                "HOLD": "持股观望 / 暂不加仓",
                "NO_TRADE": "放弃交易 / 空仓回避",
            }
            raw_action = str(plan.get("trading_action")).strip()
            # If the output somehow contains something unexpected, it will just show the original string
            display_action = action_map.get(raw_action.upper(), raw_action)
            table += (
                f"| ⚡ **交易决策 (Action)** | **{display_action} ({raw_action})** |\n"
            )
        if plan.get("action_reason"):
            val = str(plan["action_reason"]).replace("|", "\|")
            table += f"| 💡 **核心逻辑 (Reason)** | {val} |\n"

        if plan.get("early_trading_strategy"):
            val = str(plan["early_trading_strategy"]).replace("|", "\|")
            table += f"| 🌅 **早盘策略(09:30-10:00)** | {val} |\n"
        if plan.get("late_trading_strategy"):
            val = str(plan["late_trading_strategy"]).replace("|", "\|")
            table += f"| 🌇 **尾盘策略(14:30-15:00)** | {val} |\n"

        table += f"| 🚀 **最高追涨 (买入上限)** | {plan.get('buy_price_max', '--')} |\n"
        table += f"| 💰 **低吸参考 (企稳低吸)** | {plan.get('buy_dip_price', '--')} |\n"
        table += (
            f"| 🛡 **严格止损 (破位离场)** | {plan.get('stop_loss_price', '--')} |\n"
        )
        table += (
            f"| 🎯 **止盈目标 (压力位)** | {plan.get('take_profit_target', '--')} |\n"
        )
        table += f"| ⚠️ **风控等级** | {plan.get('risk_rating', '--')} |\n"
        table += f"| 📦 **建议仓位** | {plan.get('position_advice', '--')} |\n"

        md_parts.append(table)

        # Replace the json string from the original text if it was outside code blocks
        if code_block_match:
            return text.replace(code_block_match.group(0), "\n".join(md_parts))
        else:
            return text.replace(json_str, "\n".join(md_parts))
    except Exception as e:
        print(f"Deep JSON Parse Error: {e}")
        return text


def format_stock_section(
    stock_info: Dict[str, Any],
    tech_data: Dict[str, Any],
    llm_analysis: str,
    pre_daily_features: Dict[str, Any] = None,
) -> str:
    """
    Format a complete stock analysis section in Markdown
    Automatically selects ETF or Stock format based on score_type
    """
    # 检查是否为ETF评分类型
    if tech_data.get("score_type") == "etf":
        return format_etf_section(stock_info, tech_data, llm_analysis)

    # 兼容旧调用：pre_daily_features 不传时降级为空字典
    if pre_daily_features is None:
        pre_daily_features = {}

    # 注意：现在 LLM 直接输出 Markdown 表格，无需再调用 format_json_plan 解析
    # formatted_analysis = format_json_plan(llm_analysis)

    # 综合评分显示
    score = tech_data.get("composite_score", "N/A")
    rating = tech_data.get("rating", "未知")

    # 评分详情
    score_breakdown = tech_data.get("score_breakdown", [])
    entry_score = tech_data.get("entry_score")
    holding_score = tech_data.get("holding_score")
    holding_state_label = tech_data.get("holding_state_label", tech_data.get("holding_state"))

    score_section = ""
    if score_breakdown:
        score_section = "\n**📊 评分明细：**\n"
        for name, got, total in score_breakdown:
            # 计算填充进度条 (visual bar)
            filled = int(got / total * 10) if total > 0 else 0
            bar = "▮" * filled + "▯" * (10 - filled)
            score_section += f"- {name}：`{bar}` {got}/{total}\n"

    # 操作建议
    operation_suggestion = tech_data.get("operation_suggestion", "暂无建议")

    # 新闻区块
    news_content = tech_data.get("latest_news", None)
    news_block = ""
    if news_content and news_content != "暂无新闻":
        news_block = f"""
**📰 消息面/题材 (News/Catalyst)：**
> {news_content}
"""

    dual_score_block = ""
    if entry_score is not None or holding_score is not None:
        dual_score_block = (
            "\n**🎯 双评分快照：**\n"
            f"- Entry Score: **{entry_score if entry_score is not None else 'N/A'}**\n"
            f"- Holding Score: **{holding_score if holding_score is not None else 'N/A'}**\n"
            f"- Holding State: **{holding_state_label or 'N/A'}**\n"
        )

    section = f"""
## {stock_info["symbol"]} - {stock_info["name"]}
### 📅 报告日期：{tech_data.get("date", "未知")}

### 🚀 综合评分：{score}分 - {rating}

**💡 策略建议：{operation_suggestion}**

{dual_score_block}

{score_section}

**📈 核心技术信号 (Key Signals)：**
- **趋势**：MA20排列 **{tech_data.get("ma_arrangement", "未知")}** (价格在MA20{"上方" if tech_data.get("distance_from_ma20", 0) > 0 else "下方"})
- **形态**：**{", ".join(tech_data.get("pattern_details", [])) or "无明显反转形态"}**
- **动量**：RSI(14)=**{tech_data.get("rsi", "N/A")}** | 量比=**{tech_data.get("volume_ratio", "N/A")}**
- **结构**：距120日高点 **{f"{tech_data['price_vs_high120']:.2%}" if tech_data.get("price_vs_high120") is not None else "N/A"}** (越近越好)
- **风控**：ATR波动率 **{tech_data.get("atr_pct", "N/A")}%** | 建议止损 **¥{tech_data.get("stop_loss_suggest", "N/A")}**

**日内分时特征**
- 均价线控盘: 日内均价 {pre_daily_features.get("vwap", "N/A")} | 收盘价较均价 {pre_daily_features.get("close_vs_vwap_pct", "N/A")}% ({pre_daily_features.get("vwap_status", "N/A")})
- 早盘动作(9:30-10:00): {pre_daily_features.get("morning_action", "N/A")} (最高触及 {pre_daily_features.get("morning_high", "N/A")})
- 尾盘动作(14:30-15:00): {pre_daily_features.get("late_action", "N/A")} (区间量能占全天 {pre_daily_features.get("late_volume_ratio", "N/A")}%)  

{news_block}

**🤖 AI 深度复盘与计划：**
\n
{format_deep_json_plan(llm_analysis)}

---
"""
    return section

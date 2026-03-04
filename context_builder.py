from typing import Dict, Any


def build_market_context(monitor_engine, stock_symbol: str = None) -> Dict[str, Any]:
    """
    通用市场上下文构建器

    统一获取：
    1. 大盘指数 (Market Index) - 上证指数
    2. 板块信息 (Sector Info) - 涨跌幅、排名
    3. 市场情绪 (Market Sentiment) - 连板数、涨跌家数比 (Advanced)
    4. 宏观状态 (Macro Status) - 牛熊线位置

    Args:
        monitor_engine: MonitorEngine 实例 (用于获取缓存的市场数据)
        stock_symbol: 目标股票代码 (用于查找所属板块)

    Returns:
        Dict[str, Any]: 标准化的 Market Context 结构
    """

    # Init context structure
    context = {
        "market_index": {
            "name": "上证指数",
            "price": 0.0,
            "change_pct": 0.0,
            "trend": "震荡",
            "status_desc": "未知",
        },
        "sector_info": {"name": "N/A", "change_pct": 0.0, "rank": "N/A"},
        "sentiment": {"limit_up_count": "N/A", "score": 50},
    }

    try:
        # 1. 获取基础指数数据 (Realtime)
        index_data = monitor_engine.get_market_index()
        context["market_index"]["price"] = index_data.get("price", 0)
        context["market_index"]["change_pct"] = index_data.get("change_pct", 0)

        # 2. 计算高级大盘状态 (Trend + Volume)
        # 使用 monitor_engine 的缓存获取历史
        if hasattr(monitor_engine, "get_market_history_cached"):
            index_df = monitor_engine.get_market_history_cached()

            if index_df is not None and not index_df.empty:
                # Calculate MA5
                index_df["ma5"] = index_df["close"].rolling(5).mean()
                last_row = index_df.iloc[-1]

                current_price = index_data.get("price")
                if not current_price or current_price == 0:
                    current_price = last_row["close"]

                ma5_price = last_row["ma5"]

                # Trend Logic
                trend = "震荡"
                if current_price > ma5_price * 1.005:
                    trend = "上涨"
                elif current_price < ma5_price * 0.995:
                    trend = "下跌"

                # Position
                pos_desc = "均线上方" if current_price > ma5_price else "均线下方"

                context["market_index"]["trend"] = trend
                context["market_index"]["status_desc"] = f"{trend} ({pos_desc})"

        # 3. 注入板块信息 (如果有股票代码)
        if stock_symbol:
            from data_fetcher import load_sector_map, get_sector_performance

            sector_map = load_sector_map()
            sector_name = sector_map.get(stock_symbol, "N/A")
            context["sector_info"]["name"] = sector_name

            if sector_name and sector_name != "N/A":
                sector_change = get_sector_performance(sector_name)
                context["sector_info"]["change_pct"] = sector_change

        # 4. 其它情绪指标 (Placeholder for now, or fetch from DB/API)
        # context["sentiment"]["limit_up_count"] = ...

    except Exception as e:
        print(f"⚠️ Market Context Build Error: {e}")

    print(
        f"🌍 Market Context Built: Index={context['market_index']['change_pct']}%, Sector={context['sector_info']['name']}"
    )
    return context


def build_strategy_context(
    stock_info: Dict[str, Any],
    tech_data: Dict[str, Any],
    realtime_data: Dict[str, Any] = None,
    market_context: Dict[str, Any] = None,
    extra_indicators: Dict[str, Any] = None,
    intraday: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """
    将散落的各类数据源，清洗并封装为一个对 Prompt 极其友好的统一上下文对象。
    为后续的前端智能补全（Monaco Editor）提供 Schema 基础。
    """
    if not realtime_data:
        realtime_data = {}
    if not tech_data:
        tech_data = {}
    if not market_context:
        market_context = {"market_index": {}, "sector_info": {}, "sentiment": {}}
    if not extra_indicators:
        extra_indicators = {}
    if not intraday:
        intraday = {}

    # 1. 核心价格与涨跌
    price = realtime_data.get("price") or tech_data.get("close") or 0.0
    try:
        price = float(price)
    except (ValueError, TypeError):
        price = 0.0

    change_pct = realtime_data.get("change_pct", 0.0)
    try:
        change_pct = float(change_pct)
    except (ValueError, TypeError):
        change_pct = 0.0

    # 2. 均线与点位
    try:
        ma5 = float(tech_data.get("ma5") or 0.0)
    except (ValueError, TypeError):
        ma5 = 0.0
    try:
        ma20 = float(tech_data.get("ma20") or 0.0)
    except (ValueError, TypeError):
        ma20 = 0.0
    try:
        ma60 = float(tech_data.get("ma60") or 0.0)
    except (ValueError, TypeError):
        ma60 = 0.0

    ma5_pos = "上方" if price > ma5 else "下方"
    ma20_pos = "上方" if price > ma20 else "下方"

    try:
        res = float(
            tech_data.get("resistance") or tech_data.get("pivot_point") or (price * 1.1)
        )
    except (ValueError, TypeError):
        res = price * 1.1
    try:
        sup = float(tech_data.get("support") or tech_data.get("s1") or (price * 0.9))
    except (ValueError, TypeError):
        sup = price * 0.9

    # 3. 优势形态
    details = tech_data.get("score_details", [])
    strengths = [d.replace("✅ ", "") for d in details if "✅" in d]
    strength_str = ", ".join(strengths[:3]) if strengths else "暂无明显优势"
    pattern_str = ", ".join(tech_data.get("pattern_details", [])) or "无明显形态"

    # 4. 资金流向
    funds = realtime_data.get("money_flow", {})
    net_main = funds.get("net_amount_main", 0)
    net_pct = funds.get("net_pct_main", 0)

    fund_status_desc = "暂无数据"
    if funds.get("status") == "success" and net_main != 0:
        net_main_val = float(net_main) / 10000.0
        pct_abs = abs(float(net_pct))
        flow_dir = "流出" if net_main_val < 0 else "流入"
        magnitude = "大幅" if pct_abs > 5 else "中幅" if pct_abs > 2 else "小幅"
        fund_status_desc = f"主力净{flow_dir}: {abs(net_main_val):.0f}万 (占成交额 {float(net_pct):.1f}%, {magnitude}{flow_dir})"

    # 5. 筹码状态
    vap = extra_indicators.get("vap", {})
    winner_rate = vap.get("winner_rate", "N/A")
    winner_rate_str = "暂无数据"
    if winner_rate != "N/A":
        wr = float(winner_rate)
        if wr > 80:
            label = "筹码低位集中，获利盘多"
        elif wr < 20:
            label = "筹码高位套牢，获利盘少"
        else:
            label = "筹码分散"
        winner_rate_str = f"获利盘 {wr:.1f}% ({label})"

    # 6. 基本面指标
    pe_ratio = extra_indicators.get("pe_ratio", realtime_data.get("pe_ratio", "N/A"))
    pb_ratio = extra_indicators.get("pb_ratio", realtime_data.get("pb_ratio", "N/A"))
    bvps = extra_indicators.get("bvps", realtime_data.get("bvps", "N/A"))
    roe = extra_indicators.get("roe", realtime_data.get("roe", "N/A"))
    total_mv = extra_indicators.get("total_mv", realtime_data.get("total_mv", "N/A"))
    eps = extra_indicators.get("eps", realtime_data.get("eps", "N/A"))

    # 7. 量价指标
    try:
        volume_ratio = float(
            tech_data.get("volume_ratio", realtime_data.get("volume_ratio", 0.0))
        )
    except (ValueError, TypeError):
        volume_ratio = 0.0
    try:
        rsi = float(tech_data.get("rsi", 50.0))
    except (ValueError, TypeError):
        rsi = 50.0
    atr_pct = tech_data.get("atr_pct", "N/A")

    # 组装扁平化上下文
    clean_context = {
        "stock": {
            "name": stock_info.get("name", ""),
            "symbol": stock_info.get("symbol", ""),
            "type": stock_info.get("asset_type", "stock"),
        },
        "price": price,
        "change_pct": change_pct,
        "volume_ratio": volume_ratio,
        "indicators": {
            "ma5": round(ma5, 2),
            "ma20": round(ma20, 2),
            "ma60": round(ma60, 2),
            "rsi": round(rsi, 2),
            "atr_pct": atr_pct,
            "resistance": round(res, 2),
            "support": round(sup, 2),
        },
        "fundamental": {
            "pe_ratio": pe_ratio,
            "pb_ratio": pb_ratio,
            "roe": roe,
            "bvps": bvps,
            "eps": eps,
            "total_mv": total_mv,
        },
        "computed": {
            "ma5_position": ma5_pos,
            "ma20_position": ma20_pos,
            "fund_status": fund_status_desc,
            "winner_rate": winner_rate_str,
            "strength": strength_str,
            "pattern": pattern_str,
        },
        "market": market_context,
        "intraday": intraday,
    }
    return clean_context

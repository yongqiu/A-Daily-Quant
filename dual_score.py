from __future__ import annotations

from typing import Any, Dict, List, Tuple


def _clamp_score(value: float) -> int:
    return int(max(0, min(100, round(value))))


def calculate_entry_score(metrics: Dict[str, Any]) -> Tuple[int, Dict[str, int], List[str]]:
    reasons: List[str] = []
    sections = {
        "trend": 0,
        "breakout": 0,
        "risk": 0,
        "momentum": 0,
        "overheat_penalty": 0,
    }

    close = metrics.get("close")
    ma20 = metrics.get("ma20")
    macd_dif = metrics.get("macd_dif")
    macd_dea = metrics.get("macd_dea")
    macd_hist = metrics.get("macd_hist")
    price_vs_high120 = metrics.get("price_vs_high120")
    volume_pattern = metrics.get("volume_pattern")
    volume_ratio = metrics.get("volume_ratio")
    distance_from_ma20 = metrics.get("distance_from_ma20")
    atr_pct = metrics.get("atr_pct")
    rsi = metrics.get("rsi")
    kdj_k = metrics.get("kdj_k")
    pattern_score = metrics.get("pattern_score", 0) or 0
    boll_position = metrics.get("boll_position")
    ma_arrangement = metrics.get("ma_arrangement")

    if close is not None and ma20 is not None and close > ma20:
        sections["trend"] += 10
        reasons.append("价格站上 MA20")
    if ma_arrangement == "多头排列":
        sections["trend"] += 12
        reasons.append("均线多头排列")
    if macd_dif is not None and macd_dea is not None and macd_dif > macd_dea:
        sections["trend"] += 8
        reasons.append("MACD 金叉")
    if macd_hist is not None and macd_hist > 0:
        sections["trend"] += 5
        reasons.append("MACD 柱体为正")

    if price_vs_high120 is not None:
        if 0.92 <= price_vs_high120 < 0.98:
            sections["breakout"] += 10
            reasons.append("接近前高但仍保留突破空间")
        elif price_vs_high120 >= 0.98:
            sections["breakout"] += 6
            reasons.append("已逼近前高，突破空间收窄")
        elif price_vs_high120 >= 0.88:
            sections["breakout"] += 5
            reasons.append("靠近阶段高点")
    if volume_pattern == "放量上涨":
        sections["breakout"] += 8
        reasons.append("放量上涨确认")
    elif volume_pattern == "缩量上涨":
        sections["breakout"] += 6
        reasons.append("缩量上涨，趋势仍在")
    if volume_ratio is not None:
        if 1.0 <= volume_ratio <= 2.2:
            sections["breakout"] += 5
            reasons.append("量比处于健康突破区间")
        elif 2.2 < volume_ratio <= 3.0:
            sections["breakout"] += 2
            reasons.append("量比偏大，继续观察承接")

    if distance_from_ma20 is not None:
        if 0 <= distance_from_ma20 <= 4:
            sections["risk"] += 12
            reasons.append("距离 MA20 合理，追涨风险可控")
        elif 4 < distance_from_ma20 <= 7:
            sections["risk"] += 6
            reasons.append("略有乖离，但尚未失控")
        elif 7 < distance_from_ma20 <= 10:
            sections["risk"] += 1
            reasons.append("乖离偏大，追价性价比下降")
    if atr_pct is not None and 2 <= atr_pct <= 7:
        sections["risk"] += 5
        reasons.append("波动率适中")
    if metrics.get("distance_to_support") is not None and metrics["distance_to_support"] <= 6:
        sections["risk"] += 5
        reasons.append("下方仍有支撑缓冲")

    if rsi is not None:
        if 55 <= rsi <= 68:
            sections["momentum"] += 14
            reasons.append("RSI 处于主升浪甜蜜区")
        elif 50 <= rsi < 55 or 68 < rsi <= 74:
            sections["momentum"] += 8
            reasons.append("RSI 保持偏强")
        elif 74 < rsi <= 80:
            sections["momentum"] += 2
            reasons.append("RSI 偏热，动量仍在")
    if kdj_k is not None and 25 <= kdj_k <= 80:
        sections["momentum"] += 4
        reasons.append("KDJ 未进入极端区间")
    if pattern_score > 0:
        sections["momentum"] += min(4, pattern_score)
        reasons.append("K线形态提供额外加分")

    if rsi is not None:
        if rsi >= 85:
            sections["overheat_penalty"] -= 12
            reasons.append("RSI 严重过热")
        elif rsi >= 80:
            sections["overheat_penalty"] -= 6
            reasons.append("RSI 进入过热区")
    if distance_from_ma20 is not None:
        if distance_from_ma20 > 10:
            sections["overheat_penalty"] -= 10
            reasons.append("乖离率过大")
        elif distance_from_ma20 > 7:
            sections["overheat_penalty"] -= 4
            reasons.append("乖离率偏大")
    if (
        volume_ratio is not None
        and volume_ratio > 3.0
        and price_vs_high120 is not None
        and price_vs_high120 >= 0.95
    ):
        sections["overheat_penalty"] -= 10
        reasons.append("高位爆量，疑似过热")
    if boll_position is not None:
        if boll_position > 92:
            sections["overheat_penalty"] -= 8
            reasons.append("价格极度贴近布林上轨")
        elif boll_position > 85:
            sections["overheat_penalty"] -= 4
            reasons.append("价格贴近布林上轨")

    total = sum(sections.values())
    return _clamp_score(total), sections, reasons


def calculate_holding_score(metrics: Dict[str, Any]) -> Tuple[int, Dict[str, int], List[str]]:
    reasons: List[str] = []
    sections = {
        "trend_survival": 0,
        "pullback_quality": 0,
        "risk_structure": 0,
        "continuation": 0,
        "break_penalty": 0,
    }

    close = metrics.get("close")
    ma20 = metrics.get("ma20")
    ma60 = metrics.get("ma60")
    macd_dif = metrics.get("macd_dif")
    macd_dea = metrics.get("macd_dea")
    macd_hist = metrics.get("macd_hist")
    volume_pattern = metrics.get("volume_pattern")
    distance_from_ma20 = metrics.get("distance_from_ma20")
    boll_position = metrics.get("boll_position")
    atr_pct = metrics.get("atr_pct")
    stop_loss = metrics.get("stop_loss_suggest")
    rsi = metrics.get("rsi")
    pattern_score = metrics.get("pattern_score", 0) or 0
    ma_arrangement = metrics.get("ma_arrangement")

    # 趋势存活：引入相对均线位置的细分，而不是简单站上/跌破二元判断。
    if close is not None and ma20 is not None and ma20 > 0:
        ma20_gap = (close - ma20) / ma20 * 100
        if ma20_gap >= 5:
            sections["trend_survival"] += 20
            reasons.append("显著站稳 MA20 之上")
        elif ma20_gap >= 2:
            sections["trend_survival"] += 18
            reasons.append("稳定位于 MA20 上方")
        elif ma20_gap >= 0:
            sections["trend_survival"] += 14
            reasons.append("仍站在 MA20 上方")
        elif ma20_gap >= -2:
            sections["trend_survival"] += 8
            reasons.append("仅小幅跌破 MA20")

    if close is not None and ma60 is not None and ma60 > 0:
        ma60_gap = (close - ma60) / ma60 * 100
        if ma60_gap >= 8:
            sections["trend_survival"] += 12
            reasons.append("远离 MA60，长趋势安全垫充足")
        elif ma60_gap >= 3:
            sections["trend_survival"] += 10
            reasons.append("仍位于 MA60 上方")
        elif ma60_gap >= 0:
            sections["trend_survival"] += 7
            reasons.append("贴近 MA60 但未失守")
        elif ma60_gap >= -3:
            sections["trend_survival"] += 2
            reasons.append("接近 MA60 临界位")

    if macd_hist is not None:
        if macd_hist >= 0.2:
            sections["trend_survival"] += 6
            reasons.append("MACD 柱体维持扩张")
        elif macd_hist >= 0:
            sections["trend_survival"] += 5
            reasons.append("MACD 柱体仍为正")
        elif macd_hist >= -0.08:
            sections["trend_survival"] += 3
            reasons.append("MACD 虽回落但未明显转坏")

    if ma_arrangement == "多头排列":
        sections["trend_survival"] += 6
        reasons.append("均线维持多头结构")
    elif ma_arrangement == "交织":
        sections["trend_survival"] += 3
        reasons.append("均线结构中性，尚未转空")

    # 回调质量：强调“怎么回调”，而不是仅判断是否回调。
    if volume_pattern in {"缩量下跌", "缩量回调"}:
        sections["pullback_quality"] += 12
        reasons.append("缩量回调，偏洗盘")
    elif volume_pattern == "平盘":
        sections["pullback_quality"] += 8
        reasons.append("量价中性")
    elif volume_pattern == "放量上涨":
        sections["pullback_quality"] += 10
        reasons.append("放量上攻，趋势延续")
    elif volume_pattern == "缩量上涨":
        sections["pullback_quality"] += 7
        reasons.append("缩量上涨，抛压可控")

    if distance_from_ma20 is not None:
        if -1.5 <= distance_from_ma20 <= 2.5:
            sections["pullback_quality"] += 10
            reasons.append("价格围绕 MA20 附近震荡，回撤质量较高")
        elif -3 <= distance_from_ma20 < -1.5:
            sections["pullback_quality"] += 8
            reasons.append("回踩 MA20 下方不深")
        elif 2.5 < distance_from_ma20 <= 5:
            sections["pullback_quality"] += 6
            reasons.append("强势运行但乖离尚可")
        elif -5 <= distance_from_ma20 < -3:
            sections["pullback_quality"] += 3
            reasons.append("回撤稍深，需看承接")

    if boll_position is not None:
        if 25 <= boll_position <= 55:
            sections["pullback_quality"] += 5
            reasons.append("布林位置处于理想整理区")
        elif 15 <= boll_position < 25 or 55 < boll_position <= 70:
            sections["pullback_quality"] += 3
            reasons.append("布林位置仍属正常整理")
        elif 70 < boll_position <= 85:
            sections["pullback_quality"] += 1
            reasons.append("布林位置偏高，回撤缓冲有限")

    # 结构风险：用更细颗粒反映止损和支撑缓冲。
    distance_to_support = metrics.get("distance_to_support")
    if distance_to_support is not None:
        if 1 <= distance_to_support <= 4:
            sections["risk_structure"] += 8
            reasons.append("贴近支撑且未失守")
        elif 4 < distance_to_support <= 8:
            sections["risk_structure"] += 6
            reasons.append("下方仍有支撑缓冲")
        elif 8 < distance_to_support <= 12:
            sections["risk_structure"] += 3
            reasons.append("距离支撑尚可")

    if atr_pct is not None:
        if 2 <= atr_pct <= 5:
            sections["risk_structure"] += 6
            reasons.append("波动率适中，利于持仓")
        elif 1.5 <= atr_pct < 2 or 5 < atr_pct <= 7:
            sections["risk_structure"] += 4
            reasons.append("波动率仍在可承受区间")
        elif 7 < atr_pct <= 9:
            sections["risk_structure"] += 1
            reasons.append("波动率偏高，需控制回撤")

    if stop_loss is not None and close is not None and stop_loss > 0:
        stop_gap = (close - stop_loss) / stop_loss * 100
        if stop_gap >= 8:
            sections["risk_structure"] += 7
            reasons.append("距离 ATR 止损位较远")
        elif stop_gap >= 3:
            sections["risk_structure"] += 5
            reasons.append("仍高于 ATR 止损参考")
        elif stop_gap >= 0:
            sections["risk_structure"] += 2
            reasons.append("接近 ATR 止损位")

    # 持有延续：更细化 RSI / MACD 动量延续能力。
    if rsi is not None:
        if 52 <= rsi <= 68:
            sections["continuation"] += 8
            reasons.append("RSI 处于持仓甜蜜区")
        elif 45 <= rsi < 52 or 68 < rsi <= 75:
            sections["continuation"] += 6
            reasons.append("RSI 仍处于可持有区")
        elif 40 <= rsi < 45 or 75 < rsi <= 80:
            sections["continuation"] += 3
            reasons.append("RSI 开始偏弱或偏热")

    if macd_dif is not None and macd_dea is not None:
        macd_gap = macd_dif - macd_dea
        if macd_gap >= 0.08:
            sections["continuation"] += 4
            reasons.append("MACD 多头动量仍占优")
        elif macd_gap >= -0.03:
            sections["continuation"] += 3
            reasons.append("MACD 未明显转弱")
        elif macd_gap >= -0.08:
            sections["continuation"] += 1
            reasons.append("MACD 轻微走弱")

    if pattern_score > 0:
        sections["continuation"] += min(3, pattern_score)
        reasons.append("K线形态对持有有正面加分")
    elif pattern_score < 0:
        sections["continuation"] += max(-3, pattern_score)
        reasons.append("K线形态削弱持有信心")

    # 破位惩罚：按破位深度递增惩罚。
    if close is not None and ma20 is not None and ma20 > 0:
        ma20_gap = (close - ma20) / ma20 * 100
        if ma20_gap < -6:
            sections["break_penalty"] -= 12
            reasons.append("深度跌破 MA20")
        elif ma20_gap < -3:
            sections["break_penalty"] -= 8
            reasons.append("明显跌破 MA20")
        elif ma20_gap < 0:
            sections["break_penalty"] -= 4
            reasons.append("跌破 MA20")

    if close is not None and ma60 is not None and ma60 > 0:
        ma60_gap = (close - ma60) / ma60 * 100
        if ma60_gap < -5:
            sections["break_penalty"] -= 12
            reasons.append("深度跌破 MA60")
        elif ma60_gap < -2:
            sections["break_penalty"] -= 8
            reasons.append("明显跌破 MA60")
        elif ma60_gap < 0:
            sections["break_penalty"] -= 4
            reasons.append("跌破 MA60")

    if volume_pattern == "放量下跌":
        sections["break_penalty"] -= 8
        reasons.append("放量下跌，抛压偏重")
    elif volume_pattern == "缩量下跌":
        sections["break_penalty"] -= 2
        reasons.append("仍有下跌压力")

    if distance_from_ma20 is not None and distance_from_ma20 < -8:
        sections["break_penalty"] -= 6
        reasons.append("偏离 MA20 过深")
    elif distance_from_ma20 is not None and distance_from_ma20 < -5:
        sections["break_penalty"] -= 3
        reasons.append("下破 MA20 后回撤偏深")

    total = sum(sections.values())
    return _clamp_score(total), sections, reasons


def classify_holding_state(score: int) -> str:
    if score >= 70:
        return "HOLD"
    if score >= 55:
        return "OBSERVE"
    if score >= 40:
        return "REDUCE_ALERT"
    return "EXIT"

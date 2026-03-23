from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any, Dict, List, Optional


SNAPSHOT_VERSION = 1


def _safe_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    return []


def build_decision_hints(metrics: Dict[str, Any], scores: Dict[str, Any]) -> Dict[str, Any]:
    dual = scores.get("dual", {})
    entry_score = dual.get("entry_score", 0) or 0
    holding_score = dual.get("holding_score", 0) or 0
    holding_state = dual.get("holding_state", "")

    risk_flags: List[str] = []
    conflicts: List[str] = []

    if holding_score < 40:
        risk_flags.append("holding_score_below_40")
    if holding_state == "EXIT":
        risk_flags.append("holding_state_exit")
    if metrics.get("close") is not None and metrics.get("ma20") is not None:
        if metrics.get("close", 0) < metrics.get("ma20", 0):
            risk_flags.append("price_below_ma20")
    if (metrics.get("rsi") or 0) >= 80:
        risk_flags.append("rsi_overheated")

    if entry_score > 70 and holding_score < 50:
        conflicts.append("high_entry_low_holding")
    if entry_score >= 65 and holding_state in {"REDUCE_ALERT", "EXIT"}:
        conflicts.append("entry_holding_state_conflict")

    machine_bias = "neutral"
    if holding_state in {"REDUCE_ALERT", "EXIT"} or holding_score < 45:
        machine_bias = "defensive"
    elif entry_score >= 65 and holding_score >= 55:
        machine_bias = "bullish"

    primary_mode = "holding" if holding_state else "entry"
    if entry_score >= holding_score:
        primary_mode = "entry"

    return {
        "primary_mode": primary_mode,
        "machine_bias": machine_bias,
        "risk_flags": risk_flags,
        "conflicts": conflicts,
    }


def build_analysis_snapshot(
    stock_info: Dict[str, Any],
    metrics: Dict[str, Any],
    realtime_data: Optional[Dict[str, Any]] = None,
    market_context: Optional[Dict[str, Any]] = None,
    extra_indicators: Optional[Dict[str, Any]] = None,
    intraday: Optional[Dict[str, Any]] = None,
    scores: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    realtime_data = realtime_data or {}
    market_context = market_context or {}
    extra_indicators = extra_indicators or {}
    intraday = intraday or {}
    scores = scores or {}

    symbol = stock_info.get("symbol", metrics.get("symbol", ""))
    trade_date = metrics.get("date") or datetime.now().strftime("%Y-%m-%d")
    as_of = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    snapshot = {
        "snapshot_version": SNAPSHOT_VERSION,
        "snapshot_id": f"{symbol}:{trade_date}:{as_of}",
        "symbol": symbol,
        "trade_date": trade_date,
        "as_of": as_of,
        "stock_info": deepcopy(stock_info),
        "raw_data": {
            "realtime_data": deepcopy(realtime_data),
            "market_context": deepcopy(market_context),
            "extra_indicators": deepcopy(extra_indicators),
            "intraday": deepcopy(intraday),
        },
        "metrics": deepcopy(metrics),
        "scores": deepcopy(scores),
        "decision_hints": build_decision_hints(metrics, scores),
    }
    return snapshot


def get_machine_snapshot_lines(snapshot: Dict[str, Any]) -> List[str]:
    metrics = snapshot.get("metrics", {})
    legacy = snapshot.get("scores", {}).get("legacy", {})
    dual = snapshot.get("scores", {}).get("dual", {})
    hints = snapshot.get("decision_hints", {})

    lines = [
        f"- Legacy 综合评分: {legacy.get('composite_score', 'N/A')} ({legacy.get('rating', 'N/A')})",
        f"- Entry Score: {dual.get('entry_score', 'N/A')}",
        f"- Holding Score: {dual.get('holding_score', 'N/A')}",
        f"- Holding State: {dual.get('holding_state_label', dual.get('holding_state', 'N/A'))}",
        f"- Machine Bias: {hints.get('machine_bias', 'neutral')}",
        f"- Primary Mode: {hints.get('primary_mode', 'entry')}",
    ]

    if dual.get("entry_score_details"):
        lines.append(
            "- Entry 理由: " + "；".join(_safe_list(dual.get("entry_score_details"))[:4])
        )
    if dual.get("holding_score_details"):
        lines.append(
            "- Holding 理由: "
            + "；".join(_safe_list(dual.get("holding_score_details"))[:4])
        )
    if hints.get("risk_flags"):
        lines.append("- 风险标记: " + "、".join(_safe_list(hints.get("risk_flags"))))
    if hints.get("conflicts"):
        lines.append("- 冲突标记: " + "、".join(_safe_list(hints.get("conflicts"))))

    lines.extend(
        [
            f"- 现价: {metrics.get('close', 'N/A')}",
            f"- MA20/MA60: {metrics.get('ma20', 'N/A')} / {metrics.get('ma60', 'N/A')}",
            f"- RSI: {metrics.get('rsi', 'N/A')}",
            f"- 量比: {metrics.get('volume_ratio', 'N/A')}",
        ]
    )
    return lines


def flatten_snapshot_for_legacy(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    stock_info = snapshot.get("stock_info", {})
    metrics = deepcopy(snapshot.get("metrics", {}))
    legacy = snapshot.get("scores", {}).get("legacy", {})
    dual = snapshot.get("scores", {}).get("dual", {})
    hints = snapshot.get("decision_hints", {})

    metrics["symbol"] = stock_info.get("symbol", snapshot.get("symbol"))
    metrics["name"] = stock_info.get("name", metrics.get("name"))
    metrics["snapshot_version"] = snapshot.get("snapshot_version", SNAPSHOT_VERSION)
    metrics["analysis_snapshot"] = snapshot
    metrics["composite_score"] = legacy.get(
        "composite_score", metrics.get("composite_score")
    )
    metrics["rating"] = legacy.get("rating", metrics.get("rating"))
    metrics["score_breakdown"] = legacy.get(
        "score_breakdown", metrics.get("score_breakdown", [])
    )
    metrics["score_details"] = legacy.get(
        "score_details", metrics.get("score_details", [])
    )
    metrics["entry_score"] = dual.get("entry_score", metrics.get("entry_score"))
    metrics["entry_score_breakdown"] = dual.get(
        "entry_score_breakdown", metrics.get("entry_score_breakdown", [])
    )
    metrics["entry_score_details"] = dual.get(
        "entry_score_details", metrics.get("entry_score_details", [])
    )
    metrics["holding_score"] = dual.get("holding_score", metrics.get("holding_score"))
    metrics["holding_score_breakdown"] = dual.get(
        "holding_score_breakdown", metrics.get("holding_score_breakdown", [])
    )
    metrics["holding_score_details"] = dual.get(
        "holding_score_details", metrics.get("holding_score_details", [])
    )
    metrics["holding_state"] = dual.get("holding_state", metrics.get("holding_state"))
    metrics["holding_state_label"] = dual.get(
        "holding_state_label", metrics.get("holding_state_label")
    )
    metrics["machine_bias"] = hints.get("machine_bias", "neutral")
    metrics["risk_flags"] = hints.get("risk_flags", [])
    metrics["conflicts"] = hints.get("conflicts", [])
    return metrics


def build_snapshot_storage_view(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    metrics = snapshot.get("metrics", {})
    legacy = snapshot.get("scores", {}).get("legacy", {})
    dual = snapshot.get("scores", {}).get("dual", {})
    hints = snapshot.get("decision_hints", {})
    return {
        "snapshot_version": snapshot.get("snapshot_version", SNAPSHOT_VERSION),
        "snapshot_id": snapshot.get("snapshot_id"),
        "symbol": snapshot.get("symbol"),
        "trade_date": snapshot.get("trade_date"),
        "as_of": snapshot.get("as_of"),
        "stock_info": snapshot.get("stock_info", {}),
        "metrics": {
            "close": metrics.get("close"),
            "ma20": metrics.get("ma20"),
            "ma60": metrics.get("ma60"),
            "rsi": metrics.get("rsi"),
            "volume_ratio": metrics.get("volume_ratio"),
            "price_vs_high120": metrics.get("price_vs_high120"),
            "atr_pct": metrics.get("atr_pct"),
            "trend_signal": metrics.get("trend_signal"),
            "ma_arrangement": metrics.get("ma_arrangement"),
        },
        "scores": {
            "legacy": legacy,
            "dual": dual,
        },
        "decision_hints": hints,
    }

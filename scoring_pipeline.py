from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict

from analysis_snapshot import build_analysis_snapshot
from dual_score import (
    calculate_entry_score,
    calculate_holding_score,
    classify_holding_state,
)


def _format_dual_score_breakdown(section_scores: Dict[str, int], label_map: Dict[str, str]) -> list:
    max_score_map = {
        "trend": 35,
        "breakout": 25,
        "risk": 20,
        "momentum": 20,
        "overheat_penalty": 20,
        "trend_survival": 40,
        "pullback_quality": 25,
        "risk_structure": 20,
        "continuation": 15,
        "break_penalty": 30,
    }
    formatted = []
    for key, score in section_scores.items():
        formatted.append((label_map.get(key, key), score, max_score_map.get(key, 0)))
    return formatted


def build_score_views(metrics: Dict[str, Any]) -> Dict[str, Any]:
    metrics = deepcopy(metrics)
    entry_score, entry_breakdown, entry_reasons = calculate_entry_score(metrics)
    holding_score, holding_breakdown, holding_reasons = calculate_holding_score(metrics)
    holding_state = classify_holding_state(holding_score)

    legacy = {
        "composite_score": metrics.get("composite_score", 0),
        "rating": metrics.get("rating", ""),
        "score_breakdown": metrics.get("score_breakdown", []),
        "score_details": metrics.get("score_details", []),
    }
    dual = {
        "entry_score": entry_score,
        "entry_score_breakdown": _format_dual_score_breakdown(
            entry_breakdown,
            {
                "trend": "趋势结构",
                "breakout": "突破质量",
                "risk": "位置风险",
                "momentum": "动量质量",
                "overheat_penalty": "过热惩罚",
            },
        ),
        "entry_score_details": entry_reasons,
        "holding_score": holding_score,
        "holding_score_breakdown": _format_dual_score_breakdown(
            holding_breakdown,
            {
                "trend_survival": "趋势存活",
                "pullback_quality": "回调质量",
                "risk_structure": "结构风险",
                "continuation": "持有延续",
                "break_penalty": "破位惩罚",
            },
        ),
        "holding_score_details": holding_reasons,
        "holding_state": holding_state,
        "holding_state_label": {
            "HOLD": "持有",
            "OBSERVE": "观察",
            "REDUCE_ALERT": "减仓预警",
            "EXIT": "退出",
        }.get(holding_state, holding_state),
    }
    return {"legacy": legacy, "dual": dual}


def enrich_metrics_with_scores(metrics: Dict[str, Any]) -> Dict[str, Any]:
    metrics = deepcopy(metrics)
    score_views = build_score_views(metrics)
    legacy = score_views["legacy"]
    dual = score_views["dual"]
    metrics["composite_score"] = legacy["composite_score"]
    metrics["rating"] = legacy["rating"]
    metrics["score_breakdown"] = legacy["score_breakdown"]
    metrics["score_details"] = legacy["score_details"]
    metrics.update(dual)
    return metrics


def attach_scores_to_snapshot(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    snapshot = deepcopy(snapshot)
    score_views = build_score_views(snapshot.get("metrics", {}))
    snapshot["scores"] = score_views
    rebuilt = build_analysis_snapshot(
        stock_info=snapshot.get("stock_info", {}),
        metrics=snapshot.get("metrics", {}),
        realtime_data=snapshot.get("raw_data", {}).get("realtime_data", {}),
        market_context=snapshot.get("raw_data", {}).get("market_context", {}),
        extra_indicators=snapshot.get("raw_data", {}).get("extra_indicators", {}),
        intraday=snapshot.get("raw_data", {}).get("intraday", {}),
        scores=score_views,
    )
    return rebuilt

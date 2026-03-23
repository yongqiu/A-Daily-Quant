from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any, Dict, List, Optional


VALID_ACTIONS = {"BUY", "HOLD", "REDUCE", "SELL", "WAIT"}
ACTION_RANK = {"SELL": 0, "REDUCE": 1, "WAIT": 2, "HOLD": 3, "BUY": 4}


def extract_structured_opinion(text: str) -> Dict[str, Any]:
    default = {
        "stance": "partial",
        "machine_score_judgement": "",
        "key_evidence": [],
        "risk_override": False,
        "final_action": "WAIT",
        "raw_text": text or "",
    }
    if not text:
        return default

    candidates = re.findall(r"\{[\s\S]*\}", text)
    for candidate in reversed(candidates):
        try:
            parsed = json.loads(candidate)
        except Exception:
            continue
        action = str(parsed.get("final_action", "WAIT")).upper()
        if action not in VALID_ACTIONS:
            action = "WAIT"
        default.update(
            {
                "stance": parsed.get("stance", default["stance"]),
                "machine_score_judgement": parsed.get(
                    "machine_score_judgement", default["machine_score_judgement"]
                ),
                "key_evidence": parsed.get("key_evidence", []) or [],
                "risk_override": bool(parsed.get("risk_override", False)),
                "final_action": action,
            }
        )
        return default
    return default


def _consensus_level(actions: List[str]) -> str:
    if not actions:
        return "low"
    counts = Counter(actions)
    _, top_count = counts.most_common(1)[0]
    ratio = top_count / len(actions)
    if ratio >= 0.8:
        return "high"
    if ratio >= 0.5:
        return "medium"
    return "low"


def derive_final_decision(
    snapshot: Dict[str, Any],
    agent_outputs: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    dual = snapshot.get("scores", {}).get("dual", {})
    hints = snapshot.get("decision_hints", {})
    agent_outputs = agent_outputs or []

    entry_score = dual.get("entry_score", 0) or 0
    holding_score = dual.get("holding_score", 0) or 0
    holding_state = dual.get("holding_state", "")

    parsed = []
    actions = []
    for output in agent_outputs:
        parsed_output = output
        if isinstance(output, str):
            parsed_output = extract_structured_opinion(output)
        elif "structured" in output:
            parsed_output = output["structured"]
        parsed.append(parsed_output)
        action = str(parsed_output.get("final_action", "WAIT")).upper()
        if action in VALID_ACTIONS:
            actions.append(action)

    consensus_level = _consensus_level(actions)
    final_action = "WAIT"
    if actions:
        final_action = Counter(actions).most_common(1)[0][0]

    reasons: List[str] = []
    risk_level = "medium"

    if holding_state == "EXIT":
        risk_level = "high"
        reasons.append("holding_state=EXIT")
        if not any(o.get("risk_override") for o in parsed):
            final_action = "SELL"
    elif holding_score < 40:
        risk_level = "high"
        reasons.append("holding_score_below_40")
        if ACTION_RANK.get(final_action, 2) > ACTION_RANK["REDUCE"]:
            final_action = "REDUCE"
    elif holding_score < 55:
        risk_level = "medium"
        reasons.append("holding_score_below_55")
    elif entry_score >= 70 and holding_score >= 55:
        risk_level = "low"
        if final_action == "WAIT":
            final_action = "HOLD"

    if "high_entry_low_holding" in hints.get("conflicts", []):
        reasons.append("high_entry_low_holding")
        if final_action == "BUY":
            final_action = "WAIT"

    if consensus_level == "low":
        reasons.append("low_agent_consensus")
        if final_action == "BUY":
            final_action = "WAIT"

    if final_action == "WAIT" and holding_state == "HOLD":
        final_action = "HOLD"

    final_reasoning = " | ".join(reasons) if reasons else "machine_and_agents_balanced"
    return {
        "final_action": final_action,
        "risk_level": risk_level,
        "consensus_level": consensus_level,
        "final_reasoning": final_reasoning,
        "agent_outputs": parsed,
    }

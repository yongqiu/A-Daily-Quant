# -*- coding: utf-8 -*-
"""
Unified Stock Scoring Module
统一评分模块

The scoring entrypoint now consumes the shared analysis snapshot so that
machine scoring, prompt building, persistence and UI all read the same facts.
"""
from typing import Any, Dict, Optional
import logging

from analysis_snapshot import flatten_snapshot
from strategy_data_factory import StrategyDataFactory


logger = logging.getLogger(__name__)


def get_score(
    symbol: str,
    cost_price: float = 0.0,
    asset_type: str = "stock",
    include_news: bool = True,
    trade_date: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    获取统一评分结果。

    Notes:
    - Data is loaded via StrategyDataFactory so score and AI analysis share the same snapshot.
    - `include_news` and `trade_date` are currently kept for API compatibility.
    """
    try:
        stock_info = {
            "symbol": symbol,
            "name": symbol,
            "asset_type": asset_type,
            "type": asset_type,
            "cost_price": cost_price,
        }
        StrategyDataFactory._set_to_cache(symbol, "stock_info", stock_info)

        context_type = "deep_candidate" if cost_price <= 0 else "holding"
        snapshot = StrategyDataFactory.build_analysis_snapshot(
            symbol=symbol,
            context_type=context_type,
        )
        if not snapshot:
            return None

        flattened = flatten_snapshot(snapshot)
        flattened["snapshot"] = snapshot
        flattened["data_date"] = snapshot.get("trade_date")

        if not include_news:
            flattened.pop("latest_news", None)

        return flattened

    except Exception as e:
        print(f"❌ get_score 出错 {symbol}: {e}")
        import traceback

        traceback.print_exc()
        return None

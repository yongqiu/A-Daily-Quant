import traceback
from typing import Dict, Any, Optional
from datetime import datetime
import json

from analysis_snapshot import build_analysis_snapshot, flatten_snapshot_for_legacy
from context_builder import build_strategy_context
from scoring_pipeline import attach_scores_to_snapshot


class StrategyDataFactory:
    """
    统一的策略数据加载工厂
    负责在进行大模型分析前，一次性准备好所有的上下文补充数据。
    包含多级缓存机制：在同一天内获取的基础信息和技术面数据可以进行内存缓存。
    """

    _cache = {}
    _current_date = datetime.now().strftime("%Y-%m-%d")

    @classmethod
    def _get_from_cache(cls, symbol: str, key: str) -> Optional[Any]:
        today = datetime.now().strftime("%Y-%m-%d")
        if cls._current_date != today:
            cls._cache.clear()
            cls._current_date = today

        if symbol in cls._cache and key in cls._cache[symbol]:
            return cls._cache[symbol][key]
        return None

    @classmethod
    def _set_to_cache(cls, symbol: str, key: str, value: Any):
        today = datetime.now().strftime("%Y-%m-%d")
        if cls._current_date != today:
            cls._cache.clear()
            cls._current_date = today

        if symbol not in cls._cache:
            cls._cache[symbol] = {}
        cls._cache[symbol][key] = value

    @classmethod
    def _detect_asset_type(cls, symbol: str, stock_info: Dict[str, Any]) -> str:
        asset_type = stock_info.get("asset_type", stock_info.get("type", "stock"))
        if asset_type == "stock" and symbol.startswith(("51", "56", "58", "159")):
            return "etf"
        return asset_type

    @classmethod
    def _safe_float(cls, value: Any) -> Optional[float]:
        try:
            if value in (None, "", "N/A", "None"):
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _get_or_compute_tech_data(
        cls, symbol: str, stock_info: Dict[str, Any]
    ) -> Dict[str, Any]:
        """抓取并计算技术面指标（缓存日线级别）"""
        cached = cls._get_from_cache(symbol, "tech_data")
        if cached:
            return cached

        from data_fetcher import fetch_data_dispatcher, calculate_start_date
        from indicator_calc import calculate_indicators, get_latest_metrics

        try:
            with open("config.json", "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception:
            config = {"analysis": {"lookback_days": 180, "ma_short": 5, "ma_long": 20}}

        lookback = config.get("analysis", {}).get("lookback_days", 180)
        start_date = calculate_start_date(lookback)
        asset_type = cls._detect_asset_type(symbol, stock_info)

        df = fetch_data_dispatcher(symbol, asset_type, start_date)
        if df is None or df.empty:
            return {}

        df = calculate_indicators(
            df,
            ma_short=config.get("analysis", {}).get("ma_short", 5),
            ma_long=config.get("analysis", {}).get("ma_long", 20),
        )
        tech_data = get_latest_metrics(df, cost_price=stock_info.get("cost_price"))
        if tech_data:
            if asset_type == "etf":
                from etf_score import apply_etf_score

                tech_data = apply_etf_score(tech_data)

            cls._set_to_cache(symbol, "tech_data", tech_data)
            return tech_data
        return {}

    @classmethod
    def build_analysis_snapshot(
        cls, symbol: str, context_type: str, monitor_engine=None
    ) -> Dict[str, Any]:
        payload = cls.build_full_strategy_context(
            symbol=symbol,
            context_type=context_type,
            monitor_engine=monitor_engine,
        )
        if payload.get("snapshot"):
            return payload["snapshot"]
        return {}

    @classmethod
    def build_full_strategy_context(
        cls, symbol: str, context_type: str, monitor_engine=None
    ) -> Dict[str, Any]:
        """门面模式：传入一个代码，出厂一个终极完整的大字典，包含按需加载和缓存"""
        print(
            f"🏭 [DataFactory] Building full context for {symbol} (type: {context_type})..."
        )

        # 1. 【缓存层】基础信息 (每天只需获取一次)
        from data_fetcher import fetch_stock_info

        stock_info = cls._get_from_cache(symbol, "stock_info")
        if not stock_info:
            stock_info = fetch_stock_info(symbol)
            if not stock_info:
                stock_info = {
                    "symbol": symbol,
                    "name": symbol,
                    "type": "stock",
                    "asset_type": "stock",
                }
            cls._set_to_cache(symbol, "stock_info", stock_info)

        tech_data = {}
        realtime_data = {}
        market_context = {}
        extra_info = {}

        # 2. 动态拔插层：按照策略类型判定需要组装哪些模块
        # 包含绝大多数分析类型
        standard_types = [
            "holding",
            "realtime",
            "candidate",
            "deep_candidate",
            "intraday",
            "agent_trend_follower",
            "agent_washout_hunter",
            "agent_fundamentals",
            "agent_cio",
        ]

        if context_type in standard_types:
            tech_data = cls._get_or_compute_tech_data(symbol, stock_info)

            # Realtime data is high-frequency, no caching
            from monitor_engine import get_realtime_data

            rt_dict = get_realtime_data([stock_info])
            realtime_data = rt_dict.get(symbol, {})
            # Update tech_data with realtime price if available
            if realtime_data and realtime_data.get("price"):
                tech_data["close"] = round(realtime_data.get("price"), 3)
                tech_data["realtime_price"] = round(realtime_data.get("price"), 3)
                tech_data["change_pct_today"] = round(
                    realtime_data.get("change_pct", 0), 2
                )
                tech_data["date"] = datetime.now().strftime("%Y-%m-%d")

        if context_type in standard_types:
            from context_builder import build_market_context

            if monitor_engine:
                market_context = build_market_context(monitor_engine, symbol)
            else:
                market_context = {}

        # 复杂因子和筹码计算 (Tushare接口) 仅在特定策略类型加载
        if context_type in [
            "candidate",
            "deep_candidate",
            "agent_washout_hunter",
            "agent_fundamentals",
            "agent_trend_follower",
            "realtime",
            "intraday",
        ]:
            extra_info = cls.fetch_extra_indicators(
                stock_info, context_type, realtime_data, tech_data
            )

            # Enrich realtime_data internally with money flow and intraday features
            from data_fetcher import (
                fetch_money_flow,
                fetch_dragon_tiger_data,
                get_intraday_features,
            )

            today = datetime.now().strftime("%Y-%m-%d")

            if "money_flow" not in realtime_data:
                realtime_data["money_flow"] = fetch_money_flow(symbol)
            if "lhb_data" not in realtime_data:
                realtime_data["lhb_data"] = fetch_dragon_tiger_data(symbol)
            if "pre_daily_features" not in realtime_data:
                realtime_data["pre_daily_features"] = get_intraday_features(
                    symbol=symbol, date=today
                )

        # 3. 压轴：直接调用 context_builder.py 进行彻底扁平化
        snapshot = attach_scores_to_snapshot(
            build_analysis_snapshot(
                stock_info=stock_info,
                metrics=tech_data,
                realtime_data=realtime_data,
                market_context=market_context,
                extra_indicators=extra_info,
                intraday=realtime_data.get("pre_daily_features", {}),
            )
        )

        tech_view = flatten_snapshot_for_legacy(snapshot)

        ctx = build_strategy_context(
            stock_info=stock_info,
            tech_data=tech_view,
            realtime_data=realtime_data,
            market_context=market_context,
            extra_indicators=extra_info,
        )
        print(
            f"🏭 [DataFactory] Built full context finished for {symbol} (type: {context_type}). ctx: {ctx}"
        )

        return {
            "stock_info": stock_info,
            "tech_data": tech_view,
            "realtime_data": realtime_data,
            "market_context": market_context,
            "extra_indicators": extra_info,
            "intraday": realtime_data.get("pre_daily_features", {}),
            "ctx": ctx,
            "snapshot": snapshot,
        }

    @classmethod
    def fetch_extra_indicators(
        cls,
        stock_info: Dict[str, Any],
        analysis_type: str,
        realtime_data: Dict[str, Any],
        tech_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        拉取高阶技术面因子和筹码分布数据
        """
        extra_indicators = {}
        price = cls._safe_float(realtime_data.get("price"))
        if price is None:
            price = cls._safe_float(tech_data.get("close"))
        ma20 = cls._safe_float(tech_data.get("ma20"))
        distance_from_ma20 = cls._safe_float(tech_data.get("distance_from_ma20"))

        if distance_from_ma20 is None and price is not None and ma20 not in (None, 0):
            distance_from_ma20 = (price - ma20) / ma20 * 100

        if distance_from_ma20 is not None:
            extra_indicators["deviate_pct"] = round(distance_from_ma20, 2)

        if (
            analysis_type
            in [
                "realtime",
                "candidate",
                "deep_candidate",
                "intraday",
                "agent_trend_follower",
                "agent_washout_hunter",
                "agent_fundamentals",
            ]
            and stock_info.get("asset_type", "stock") == "stock"
        ):
            symbol = stock_info.get("symbol")
            if not symbol:
                return {}

            print(f"🏭 [DataFactory] Fetching Advanced Factors & Chips for {symbol}...")

            # 1. Advanced Technical Factors (stk_factor_pro)
            try:
                from data_fetcher_ts import fetch_stk_factor_pro

                factors = fetch_stk_factor_pro(symbol)
                if factors:
                    summary = []
                    # Select key factors
                    if "asi_qfq" in factors:
                        summary.append(f"ASI振动升降: {factors['asi_qfq']:.2f}")
                    if "dmi_pdi_qfq" in factors and "dmi_mdi_qfq" in factors:
                        summary.append(
                            f"DMI动向: PDI={factors['dmi_pdi_qfq']:.2f}, MDI={factors['dmi_mdi_qfq']:.2f}"
                        )
                    if "obv_qfq" in factors:
                        summary.append(f"OBV能量潮: {factors['obv_qfq']:.2f}")
                    if "mass_qfq" in factors:
                        summary.append(f"梅斯线Mass: {factors['mass_qfq']:.2f}")
                    if "cci_qfq" in factors:
                        summary.append(f"CCI顺势: {factors['cci_qfq']:.2f}")
                    if "wr_qfq" in factors:
                        summary.append(f"W&R: {factors['wr_qfq']:.2f}")

                    factor_str = " | ".join(summary)

                    # Provide structured data
                    extra_indicators["advanced_factors"] = {
                        "desc": factor_str,
                        "raw": factors,
                    }
                    extra_indicators["technical_plus"] = factor_str
                    extra_indicators["intraday"] = {
                        "strength_desc": f"技术面因子: {factor_str}"
                    }

            except Exception as e:
                print(f"⚠️ Factor analysis failed: {e}")
                traceback.print_exc()

            # 1.5. Fundamental Indicators for Fundamental Agent
            try:
                from data_fetcher_ts import fetch_fina_indicator_ts

                fina = fetch_fina_indicator_ts(symbol)
                if fina:
                    extra_indicators["eps"] = fina.get("eps", "N/A")
                    extra_indicators["bvps"] = fina.get("bps", "N/A")
                    extra_indicators["roe"] = fina.get("roe", "N/A")

                if "factors" in locals() and factors:
                    pe = factors.get("pe_ttm") or factors.get("pe", "N/A")
                    if str(pe) == "nan":
                        pe = "N/A"
                    extra_indicators["pe_ratio"] = pe

                    pb = factors.get("pb", "N/A")
                    if str(pb) == "nan":
                        pb = "N/A"
                    extra_indicators["pb_ratio"] = pb

                    total_mv = factors.get("total_mv")
                    if total_mv and str(total_mv) != "nan":
                        extra_indicators["total_mv"] = (
                            f"{float(total_mv) / 10000:.2f}亿"
                        )
                    else:
                        extra_indicators["total_mv"] = "N/A"

            except Exception as e:
                print(f"⚠️ Fundamentals analysis failed: {e}")
                traceback.print_exc()

            # 2. Chips Distribution (cyq_chips)
            try:
                from data_fetcher_ts import fetch_cyq_chips

                chips_df = fetch_cyq_chips(symbol)
                if chips_df is not None and not chips_df.empty:
                    current_price = realtime_data.get("price") or tech_data.get("close")

                    total_percent = chips_df["percent"].sum()
                    if total_percent > 0:
                        avg_cost = (
                            chips_df["price"] * chips_df["percent"]
                        ).sum() / total_percent

                        winner_percent = chips_df[chips_df["price"] < current_price][
                            "percent"
                        ].sum()

                        chips_df = chips_df.sort_values("price")
                        chips_df["cumsum_pct"] = chips_df["percent"].cumsum()

                        try:
                            p05 = chips_df[chips_df["cumsum_pct"] >= 5]["price"].iloc[0]
                            p95 = chips_df[chips_df["cumsum_pct"] >= 95]["price"].iloc[
                                0
                            ]
                            concentration = (p95 - p05) / (p95 + p05)
                            conc_desc = f"{concentration:.2%}"
                        except Exception:
                            p05, p95 = 0, 0
                            concentration = 0
                            conc_desc = "N/A"

                        cyq_desc = f"获利盘: {winner_percent:.2f}% | 平均成本: {avg_cost:.2f} | 90%成本区间: {p05:.2f}-{p95:.2f} (集中度 {conc_desc})"

                        extra_indicators["vap"] = {
                            "desc": cyq_desc,
                            "winner_rate": winner_percent,
                            "avg_cost": avg_cost,
                            "concentration": concentration,
                            "cost_range": f"{p05:.2f}-{p95:.2f}",
                        }

            except Exception as e:
                print(f"⚠️ VAP analysis failed: {e}")
                traceback.print_exc()

        return extra_indicators

"""
A-Share Trading Discipline Assistant - Main Orchestrator
Generates daily objective analysis reports to enforce trading discipline
"""

import json
import os
import argparse
import sys
from datetime import datetime
from typing import List, Dict, Any

# Clear proxy environments to prevent connection issues with akshare
for env_var in [
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "http_proxy",
    "https_proxy",
    "ALL_PROXY",
    "all_proxy",
]:
    if env_var in os.environ:
        print(f"⚠️ Clearing proxy environment variable: {env_var}")
        os.environ.pop(env_var)

# Force no_proxy to ignore any system level proxies
os.environ["no_proxy"] = "*"
from concurrent.futures import ThreadPoolExecutor, as_completed

from data_fetcher import fetch_stock_data, calculate_start_date
from indicator_calc import calculate_indicators, get_latest_metrics
from llm_analyst import generate_analysis, format_stock_section
from report_generator import generate_html_report
from scoring_pipeline import enrich_metrics_with_scores
from stock_screener import run_stock_selection
import portfolio_manager
import database


def load_config(config_path: str = "config.json") -> Dict[str, Any]:
    """Load configuration from JSON file"""
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        print("✅ Configuration loaded successfully")
        return config
    except Exception as e:
        print(f"❌ Error loading config: {e}")
        raise


def analyze_stock(stock_info: Dict[str, Any], config: Dict[str, Any]) -> str:
    """
    Wrapper for analyze_stock_with_data to maintain backward compatibility
    """
    res = analyze_stock_with_data(stock_info, config)
    return res["markdown"]


def generate_report_header() -> str:
    """Generate report header with timestamp"""
    now = datetime.now()
    header = f"""# A股交易纪律报告
**生成时间：** {now.strftime("%Y年%m月%d日 %H:%M:%S")}

---

## 📋 交易纪律铁律

1. **趋势为王**：永远不要逆势而为。价格 < MA20 时，减仓或等待。
2. **拒绝情绪化交易**：跟随数据，不跟随炒作。
3. **风险管理**：保护本金第一，盈利第二。
4. **耐心等待**：等待明确信号。"等待"也是一种策略。

---

"""
    return header


def get_market_status(lookback_days: int = 120) -> Dict[str, Any]:
    """
    Get composite index status (Shanghai Composite)
    Acts as a 'Beta Shield' - if market is weak, be cautious.
    """
    print(f"\n{'=' * 60}")
    print(f"🌍 Analyzing Market Environment (Beta Shield)...")

    symbol = "000001"  # 上证指数
    start_date = calculate_start_date(lookback_days)

    df = fetch_stock_data(symbol, start_date, is_index=True)
    if df is None or df.empty:
        print("⚠️ Failed to fetch market index data")
        return {}

    # Calculate simple MA20
    df["ma20"] = df["close"].rolling(window=20).mean()
    latest = df.iloc[-1]

    status = {
        "name": "上证指数",
        "close": round(latest["close"], 2),
        "ma20": round(latest["ma20"], 2),
        "trend": "看涨 (牛市)"
        if latest["close"] > latest["ma20"]
        else "看跌 (熊市/震荡)",
    }

    print(
        f"🌍 Market Status: {status['trend']} (Close={status['close']}, MA20={status['ma20']})"
    )
    print(f"{'=' * 60}\n")
    return status


def generate_report_footer() -> str:
    """Generate report footer with disclaimer"""
    footer = f"""
---

## ⚠️ 免责声明

本报告由自动化系统生成，仅供个人参考，不构成投资建议。
所有交易决策由您自行负责。过往表现不代表未来结果。

**请记住：** 最好的交易有时就是不交易。纪律胜过情绪。

---
*报告由 A股交易纪律助手 生成*
"""
    return footer


def process_portfolio(config: Dict[str, Any], date_str: str) -> str:
    """
    Process portfolio analysis (to be run in parallel)
    """
    # Replace config['portfolio'] with DB call
    portfolio = portfolio_manager.get_portfolio()
    print(f"\n📊 Portfolio contains {len(portfolio)} positions")

    content = f"\n# 📊 持仓分析日报 ({date_str})\n\n"

    # --- 1. Generate Summary Table ---
    content += "## 📈 持仓概览\n\n"
    content += "| 代码 | 名称 | 当前价 | 趋势状态 | 入场评分 | 持仓评分 |\n"
    content += "|---|---|---|---|---|---|\n"

    full_sections = ""

    for i, stock_info in enumerate(portfolio, 1):
        print(f"\n[{i}/{len(portfolio)}] Processing {stock_info['symbol']}...")

        try:
            # Analyze stock and append to report
            # We need to capture the results first to build the summary table
            # analyze_stock returns the markdown string. We need to refactor slightly or extract data here?
            # To avoid refactoring analyze_stock too much, let's keep it simple:
            # We will use analyze_stock as is, but we might want to capture metadata better in the future.
            # For now, since analyze_stock prints to stdout and returns a string, we can't easily get the dict back
            # without parsing or refactoring.
            # Let's do a quick refactor of analyze_stock or just fetch data again?
            # Fetching again is wasteful.

            # Let's modify the loop to do the work here or split analyze_stock.
            # Ideally, analyze_stock should return (metadata_dict, markdown_section).

            # Since I cannot easily change the signature of analyze_stock widely (used elsewhere?),
            # I will assume I can create a helper or just move logic here.
            # But analyze_stock is used below. Let's create a temporary improved version or use regex to extract from markdown?
            # Regex is fragile.
            # Let's inspect analyze_stock. It's defined above. I will modify analyze_stock to return a tuple.

            res = analyze_stock_with_data(stock_info, config)
            section = res["markdown"]
            data = res["data"]

            full_sections += section

            # Add row to summary table
            # Status: Trend Signal or Rating
            status = data.get("trend_signal", "未知")
            entry_score = data.get("entry_score", "N/A")
            holding_score = data.get("holding_score", "N/A")

            content += f"| {stock_info['symbol']} | [{stock_info['name']}](#{stock_info['symbol']}-{stock_info['name']}) | ¥{data['close']} | {status} | {entry_score} | {holding_score} |\n"

        except Exception as e:
            # Continue to next stock even if one fails
            print(f"❌ Error analyzing {stock_info['symbol']}: {e}")
            content += f"| {stock_info['symbol']} | {stock_info['name']} | Error | -- | -- | -- |\n"
            full_sections += f"\n## {stock_info['symbol']} - {stock_info['name']}\n\n"
            full_sections += f"**❌ 分析失败：** {str(e)}\n\n---\n"
            continue

    content += "\n---\n\n" + full_sections
    return content


def analyze_stock_with_data(
    stock_info: Dict[str, Any], config: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Modified version of analyze_stock that returns both data and markdown
    """
    symbol = stock_info["symbol"]
    name = stock_info["name"]

    print(f"\n{'=' * 60}")
    print(f"📊 Analyzing: {symbol} - {name}")
    print(f"{'=' * 60}")

    # Step 1: Fetch historical data
    is_index = symbol.startswith("0003") or symbol.startswith("3999")
    start_date = calculate_start_date(config["analysis"]["lookback_days"])

    # Determine asset_type from config
    asset_type = stock_info.get("asset_type", stock_info.get("type", "stock"))

    # Use dispatcher instead of direct fetch_stock_data
    from data_fetcher import fetch_data_dispatcher

    df = fetch_data_dispatcher(symbol, asset_type, start_date)

    if df is None or df.empty:
        return {
            "markdown": f"\n## {symbol} - {name}\n\n**❌ 数据获取失败，跳过分析。**\n\n---\n",
            "data": {"close": 0, "trend_signal": "Error"},
        }

    # Step 2: Calculate technical indicators
    df = calculate_indicators(
        df,
        ma_short=config["analysis"]["ma_short"],
        ma_long=config["analysis"]["ma_long"],
    )

    # Step 3: Extract latest metrics (基于昨日收盘价的技术指标)
    tech_data = get_latest_metrics(df, cost_price=stock_info.get("cost_price"))
    if not tech_data:
        return {
            "markdown": f"\n## {symbol} - {name}\n\n**❌ 指标计算失败，跳过分析。**\n\n---\n",
            "data": {"close": 0, "trend_signal": "Error"},
        }
    # Step 3.5: Get realtime price (获取实时价格) - 与web_server.py保持一致
    from monitor_engine import get_realtime_data

    realtime_dict = get_realtime_data([stock_info])
    realtime_data = realtime_dict.get(symbol)

    # Step 3.6: Update tech_data with realtime price if available
    if realtime_data and realtime_data.get("price"):
        print(
            f"📊 {symbol} - 历史收盘价: {tech_data.get('close')}, 实时价格: {realtime_data.get('price')}"
        )
        # Override close price with realtime price
        tech_data["close"] = round(realtime_data.get("price"), 3)
        tech_data["realtime_price"] = round(realtime_data.get("price"), 3)
        tech_data["change_pct_today"] = round(realtime_data.get("change_pct", 0), 2)
        # Update date to today since we have realtime data
        tech_data["date"] = datetime.now().strftime("%Y-%m-%d")

        # Recalculate profit/loss with realtime price
        if stock_info.get("cost_price"):
            cost_price = stock_info["cost_price"]
            profit_loss_pct = ((tech_data["close"] - cost_price) / cost_price) * 100
            tech_data["profit_loss_pct"] = round(profit_loss_pct, 2)
    else:
        print(
            f"⚠️ {symbol} - 无法获取实时价格，使用历史收盘价: {tech_data.get('close')}"
        )

    tech_data = enrich_metrics_with_scores(tech_data)

    print(
        f"📈 当前价格: ¥{tech_data['close']} | Trend: {tech_data['trend_signal']}"
    )

    # Step 4: Determine which API to use
    provider = config["api"].get("provider", "openai")
    api_config_key = f"api_{provider}"

    if api_config_key in config:
        api_config = config[api_config_key]
        print(f"🤖 Using LLM provider: {provider} (from {api_config_key})")
    else:
        api_config = config["api"]
        print(f"🤖 Using LLM provider: {provider} (from api)")

    # Step 5: Generate LLM analysis (使用包含实时价格的tech_data)
    from strategy_data_factory import StrategyDataFactory

    extra = StrategyDataFactory.fetch_extra_indicators(
        stock_info, "holding", realtime_data or {}, tech_data
    )

    context = {
        "stock_info": stock_info,
        "tech_data": tech_data,  # 现在包含实时价格
        "realtime_data": realtime_data or {},
        "extra": extra,
    }

    llm_analysis = generate_analysis(
        context=context,
        api_config=api_config,
        analysis_type="holding",
    )

    # Step 6: Format the complete section (Ensure full report is saved to DB)
    # 先生成完整的 Markdown 报告（含指标头部）
    formatted_report = format_stock_section(stock_info, tech_data, llm_analysis)

    # Step 7: Save analysis to database (保存完整的 Markdown 报告)
    try:
        analysis_data = {
            "price": tech_data["close"],  # 现在是实时价格
            "ma20": tech_data["ma20"],
            "trend_signal": tech_data.get("trend_signal", "未知"),
            "entry_score": tech_data.get("entry_score"),
            "holding_score": tech_data.get("holding_score"),
            "holding_state": tech_data.get("holding_state"),
            "holding_state_label": tech_data.get("holding_state_label"),
            "ai_analysis": formatted_report,  # 🔥 关键修改：存入完整的格式化报告
        }
        database.save_holding_analysis(
            symbol, datetime.now().strftime("%Y-%m-%d"), analysis_data
        )
    except Exception as e:
        print(f"❌ Error saving analysis to DB for {symbol}: {e}")

    # Step 8: Return result for file output
    section = f'<div id="{symbol}-{name}"></div>\n\n'  # Anchor
    section += formatted_report

    print(f"✅ Analysis complete for {symbol}")

    return {"markdown": section, "data": tech_data}


def process_candidates(
    config: Dict[str, Any], api_config: Dict[str, Any], date_str: str
) -> str:
    """
    Process stock selection and analysis (to be run in parallel)
    """
    print("\n🔍 Running Market Scanner...")

    content = f"\n# 🎯 今日选股参考 ({date_str}) (AI精选)\n\n"

    try:
        selected_stocks = run_stock_selection(config)

        if selected_stocks:
            content += "> *注意：以下标的由算法基于技术指标筛选，非投资建议。请严格遵守交易纪律。*\n\n"

            # --- 1. Table Header ---
            table_content = "## 📋 选股概览\n\n"
            table_content += "| 代码 | 名称 | 当前价 | 量比 | 评分 | 核心看点 |\n"
            table_content += "|---|---|---|---|---|---|\n"

            details_content = ""

            for i, tech_data in enumerate(selected_stocks, 1):
                stock_info = {
                    "symbol": tech_data["symbol"],
                    "name": tech_data["name"],
                    "cost_price": None,  # No cost price for potential buys
                }

                # Skip AI Analysis by default for selection list
                # Optimization: Only generate if user clicks detail (handled by ScreenerView.vue calling /analyze)
                print(
                    f"🤖 Skipping AI analysis for {stock_info['name']} (Deferred to click)..."
                )

                # We still generate the technical section but without the heavy AI text
                # We can put a placeholder or basic technical summary

                # Generate a purely technical report first
                technical_summary = "__AI分析等待生成__\n\n*(请点击详情页 '生成最新分析' 按钮以获取完整AI解读)*"

                # Embedding Metadata into hidden comment for later retrieval
                if "__metadata__" in tech_data:
                    import json

                    meta_json = json.dumps(
                        tech_data["__metadata__"], ensure_ascii=False
                    )
                    technical_summary += f"\n<!-- METADATA: {meta_json} -->"

                # Format Detail Section (Prepare full report with placeholder)
                formatted_report = format_stock_section(
                    stock_info, tech_data, technical_summary
                )

                # Save to database (Save report with metrics but placeholder AI text)
                try:
                    selection_data = {
                        "symbol": stock_info["symbol"],
                        "name": stock_info["name"],
                        "close_price": tech_data["close"],
                        "volume_ratio": tech_data["volume_ratio"],
                        "entry_score": tech_data.get("entry_score"),
                        "holding_score": tech_data.get("holding_score"),
                        "holding_state": tech_data.get("holding_state"),
                        "holding_state_label": tech_data.get("holding_state_label"),
                        "ai_analysis": formatted_report,  # Save the technical report
                    }
                    database.save_daily_selection(date_str, selection_data)

                    # 同步保存评分快照，避免前端列表必须进入详情并重新计算后才显示双评分。
                    metrics_payload = dict(tech_data)
                    metrics_payload["price"] = metrics_payload.get(
                        "price", metrics_payload.get("close", 0)
                    )
                    metrics_payload["change_pct"] = metrics_payload.get(
                        "change_pct",
                        metrics_payload.get(
                            "change_pct_today", metrics_payload.get("price_change_pct", 0)
                        ),
                    )
                    if not metrics_payload.get("entry_score_details"):
                        metrics_payload["entry_score_details"] = metrics_payload.get(
                            "entry_score_reasons", []
                        )

                    pattern_list = metrics_payload.get("pattern_details", [])
                    metrics_payload["pattern_flags"] = (
                        ",".join(pattern_list) if pattern_list else ""
                    )

                    database.save_daily_metrics(date_str, metrics_payload)
                except Exception as e:
                    print(
                        f"❌ Error saving selection to DB for {stock_info['symbol']}: {e}"
                    )

                # Add to Table
                # Short Summary
                summary = tech_data.get("holding_state_label", tech_data.get("holding_state", "观察"))

                table_content += f"| {stock_info['symbol']} | [{stock_info['name']}](#{stock_info['symbol']}-{stock_info['name']}) | ¥{tech_data['close']} | {tech_data['volume_ratio']} | {tech_data.get('entry_score', 'N/A')} | {summary} |\n"

                # Format Detail Section
                details_content += (
                    f'<div id="{stock_info["symbol"]}-{stock_info["name"]}"></div>\n\n'
                )
                details_content += formatted_report

            content += table_content + "\n---\n\n" + details_content

        else:
            content += "**今日无符合严格筛选标准的标的。**\n\n*(建议休息观望，好猎手擅长等待)*\n\n---\n"

    except Exception as e:
        print(f"❌ Error in market scanner: {e}")
        content += f"**❌ 选股系统运行出错：** {str(e)}\n\n---\n"

    return content


def save_section(content: str, section_name: str, date_str: str):
    """Save a specific report section to a file"""
    filename = os.path.join("reports", f"section_{section_name}_{date_str}.md")
    with open(filename, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"✅ Saved section [{section_name}] to {filename}")


def main():
    """Main execution function"""
    parser = argparse.ArgumentParser(description="A-Share Strategy Generator")
    parser.add_argument(
        "--section",
        type=str,
        default="all",
        choices=["all", "market", "holdings", "candidates"],
        help="Specify which section to generate (market, holdings, candidates, or all)",
    )
    args = parser.parse_args()

    print("\n" + "=" * 60)
    print(f"🚀 A-Share Trading Discipline Assistant - Mode: {args.section.upper()}")
    print("=" * 60)

    # Ensure reports directory exists
    os.makedirs("reports", exist_ok=True)
    date_str = datetime.now().strftime("%Y%m%d")
    display_date = datetime.now().strftime("%Y-%m-%d")

    # Load configuration
    config = load_config()

    # Validate API configuration
    provider = config["api"].get("provider", "openai")
    api_config_key = f"api_{provider}"

    if api_config_key in config:
        api_config = config[api_config_key]
    else:
        api_config = config["api"]

    # API Check (omitted for brevity, assume valid if config exists)
    print(f"\n🤖 LLM Provider: {provider}")

    # --- EXECUTION ---

    # 1. Market Section
    if args.section in ["all", "market"]:
        header = generate_report_header()
        market_status = get_market_status(config["analysis"]["lookback_days"])

        market_section = header  # Header goes with market section usually
        if market_status:
            market_section += f"## 🌍 大盘环境 (Beta Shield)\n\n"
            market_section += f"- **指数**：{market_status['name']}\n"
            market_section += f"- **状态**：**{market_status['trend']}**\n"
            market_section += f"- **数据**：当前 {market_status['close']} / MA20 {market_status['ma20']}\n"
            if "看跌" in market_status["trend"]:
                market_section += f"- **警示**：大盘处于弱势区域，建议**严格控制仓位**，所有买入信号需打折处理！\n"
            else:
                market_section += f"- **提示**：大盘处于强势区域，可正常操作。\n"
            market_section += f"\n---\n\n"

        save_section(market_section, "market", date_str)

    # 2. Holdings Section
    if args.section in ["all", "holdings"]:
        print("\n🔄 Starting Holdings Analysis...")
        holdings_result = process_portfolio(config, display_date)
        save_section(holdings_result, "holdings", date_str)

    # 3. Candidates Section
    if args.section in ["all", "candidates"]:
        print("\n🔍 Starting Candidate Scanning...")
        candidates_result = process_candidates(config, api_config, display_date)
        save_section(candidates_result, "candidates", date_str)

    # 4. Merge for Legacy Full Report (Only if running 'all')
    if args.section == "all":
        try:
            # We already have the variables in scope if running all
            # But let's read from files to be safe/consistent or just use vars?
            # Using vars is faster.
            full_content = (
                market_section
                + holdings_result
                + "\n\n---\n\n"
                + candidates_result
                + generate_report_footer()
            )

            output_filename_full = os.path.join(
                "reports", f"daily_strategy_full_{date_str}.md"
            )
            with open(output_filename_full, "w", encoding="utf-8") as f:
                f.write(full_content)
            print(f"✅ Full Markdown Report saved to: {output_filename_full}")

            # HTML Gen
            output_filename_html = os.path.join(
                "reports", f"daily_strategy_{date_str}.html"
            )
            generate_html_report(
                holdings_result, candidates_result, output_filename_html
            )
            print("✅ HTML Report saved")

        except Exception as e:
            print(f"⚠️ Error creating full report: {e}")

    print(f"\n{'-' * 60}")
    print(f"🏁 Task [{args.section}] Completed.")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()

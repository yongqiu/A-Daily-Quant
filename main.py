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
from concurrent.futures import ThreadPoolExecutor, as_completed

from data_fetcher import fetch_stock_data, calculate_start_date
from indicator_calc import calculate_indicators, get_latest_metrics
from llm_analyst import generate_analysis, format_stock_section
from report_generator import generate_html_report
from stock_screener import run_stock_selection
from etf_score import apply_etf_score, format_etf_score_section


def load_config(config_path: str = "config.json") -> Dict[str, Any]:
    """Load configuration from JSON file"""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        print("✅ Configuration loaded successfully")
        return config
    except Exception as e:
        print(f"❌ Error loading config: {e}")
        raise


def analyze_stock(
    stock_info: Dict[str, Any],
    config: Dict[str, Any]
) -> str:
    """
    Analyze a single stock and return formatted markdown section
    
    Args:
        stock_info: Stock metadata from portfolio
        config: Full configuration dict
    
    Returns:
        Markdown-formatted analysis section
    """
    symbol = stock_info['symbol']
    name = stock_info['name']
    
    print(f"\n{'='*60}")
    print(f"📊 Analyzing: {symbol} - {name}")
    print(f"{'='*60}")
    
    # Step 1: Fetch historical data
    is_index = symbol.startswith('0003') or symbol.startswith('3999')
    start_date = calculate_start_date(config['analysis']['lookback_days'])
    
    df = fetch_stock_data(symbol, start_date, is_index=is_index)
    if df is None or df.empty:
        return f"\n## {symbol} - {name}\n\n**❌ 数据获取失败，跳过分析。**\n\n---\n"
    
    # Step 2: Calculate technical indicators
    df = calculate_indicators(
        df,
        ma_short=config['analysis']['ma_short'],
        ma_long=config['analysis']['ma_long']
    )
    
    # Step 3: Extract latest metrics
    tech_data = get_latest_metrics(df, cost_price=stock_info.get('cost_price'))
    if not tech_data:
        return f"\n## {symbol} - {name}\n\n**❌ 指标计算失败，跳过分析。**\n\n---\n"
    
    # Step 3.5: Apply ETF-specific scoring if asset_type is 'etf'
    asset_type = stock_info.get('asset_type', stock_info.get('type', 'stock'))
    if asset_type == 'etf':
        tech_data = apply_etf_score(tech_data)
        print(f"📈 Latest Price: ¥{tech_data['close']} | ETF Score: {tech_data['composite_score']} ({tech_data['rating']})")
    else:
        print(f"📈 Latest Price: ¥{tech_data['close']} | Trend: {tech_data['trend_signal']}")
    
    # Step 4: Determine which API to use based on api.provider
    # 根据 api.provider 选择对应的配置（api_gemini 或 api_deepseek）
    provider = config['api'].get('provider', 'openai')
    api_config_key = f"api_{provider}"
    
    if api_config_key in config:
        api_config = config[api_config_key]
        print(f"🤖 Using LLM provider: {provider} (from {api_config_key})")
    else:
        # 如果找不到对应的配置，使用默认的 api 配置
        api_config = config['api']
        print(f"🤖 Using LLM provider: {provider} (from api)")
    
    # Step 5: Generate LLM analysis
    asset_type = stock_info.get('asset_type', stock_info.get('type', 'stock'))
    print(f"🤖 Generating AI analysis... (Type: {asset_type})")
    
    llm_analysis = generate_analysis(
        stock_info=stock_info,
        tech_data=tech_data,
        api_config=api_config,
        analysis_type="holding"
    )
    
    # Step 6: Format the complete section
    section = format_stock_section(stock_info, tech_data, llm_analysis)
    
    print(f"✅ Analysis complete for {symbol}")
    return section


def generate_report_header() -> str:
    """Generate report header with timestamp"""
    now = datetime.now()
    header = f"""# A股交易纪律报告
**生成时间：** {now.strftime('%Y年%m月%d日 %H:%M:%S')}

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
    print(f"\n{'='*60}")
    print(f"🌍 Analyzing Market Environment (Beta Shield)...")
    
    symbol = "000001" # 上证指数
    start_date = calculate_start_date(lookback_days)
    
    df = fetch_stock_data(symbol, start_date, is_index=True)
    if df is None or df.empty:
        print("⚠️ Failed to fetch market index data")
        return {}
        
    # Calculate simple MA20
    df['ma20'] = df['close'].rolling(window=20).mean()
    latest = df.iloc[-1]
    
    status = {
        'name': "上证指数",
        'close': round(latest['close'], 2),
        'ma20': round(latest['ma20'], 2),
        'trend': "看涨 (牛市)" if latest['close'] > latest['ma20'] else "看跌 (熊市/震荡)"
    }
    
    print(f"🌍 Market Status: {status['trend']} (Close={status['close']}, MA20={status['ma20']})")
    print(f"{'='*60}\n")
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
    portfolio = config['portfolio']
    print(f"\n📊 Portfolio contains {len(portfolio)} positions")
    
    content = f"\n# 📊 持仓分析日报 ({date_str})\n\n"
    
    for i, stock_info in enumerate(portfolio, 1):
        print(f"\n[{i}/{len(portfolio)}] Processing {stock_info['symbol']}...")
        
        try:
            # Analyze stock and append to report
            section = analyze_stock(stock_info, config)
            content += section
            
        except Exception as e:
            # Continue to next stock even if one fails
            print(f"❌ Error analyzing {stock_info['symbol']}: {e}")
            content += f"\n## {stock_info['symbol']} - {stock_info['name']}\n\n"
            content += f"**❌ 分析失败：** {str(e)}\n\n---\n"
            continue
            
    return content


def process_candidates(config: Dict[str, Any], api_config: Dict[str, Any], date_str: str) -> str:
    """
    Process stock selection and analysis (to be run in parallel)
    """
    print("\n🔍 Running Market Scanner...")
    
    content = f"\n# 🎯 今日选股参考 ({date_str}) (AI精选)\n\n"
    
    try:
        selected_stocks = run_stock_selection(config)
        
        if selected_stocks:
            content += "> *注意：以下标的由算法基于技术指标筛选，非投资建议。请严格遵守交易纪律。*\n\n"
            
            for i, tech_data in enumerate(selected_stocks, 1):
                stock_info = {
                    'symbol': tech_data['symbol'],
                    'name': tech_data['name'],
                    'cost_price': None # No cost price for potential buys
                }
                
                # Generate AI Analysis for picked stock
                print(f"🤖 Generating analysis for picked stock: {stock_info['name']}...")
                try:
                    llm_analysis = generate_analysis(
                        stock_info=stock_info,
                        tech_data=tech_data,
                        api_config=api_config,
                        analysis_type="candidate"
                    )
                except Exception as e:
                    llm_analysis = f"AI分析失败 ({str(e)})"
                
                # Format (Simplified version for picks)
                content += f"### {i}. {stock_info['symbol']} - {stock_info['name']}\n\n"
                content += f"**📊 综合评分：{tech_data['composite_score']}分 ({tech_data['rating']})**\n\n"
                
                content += f"**入选理由：**\n"
                content += f"- **强势趋势**：价格 ¥{tech_data['close']} > MA20\n"
                content += f"- **量能活跃**：量比 {tech_data['volume_ratio']}，{tech_data['volume_pattern']}\n"
                content += f"- **动量充沛**：MACD {tech_data['macd_signal']}，RSI {tech_data['rsi']}\n"
                
                content += f"\n**🤖 AI点评：**\n{llm_analysis}\n\n"
                content += "---\n"
        else:
            content += "**今日无符合严格筛选标准的标的。**\n\n*(建议休息观望，好猎手擅长等待)*\n\n---\n"
            
    except Exception as e:
        print(f"❌ Error in market scanner: {e}")
        content += f"**❌ 选股系统运行出错：** {str(e)}\n\n---\n"
        
    return content


def save_section(content: str, section_name: str, date_str: str):
    """Save a specific report section to a file"""
    filename = os.path.join("reports", f"section_{section_name}_{date_str}.md")
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"✅ Saved section [{section_name}] to {filename}")

def main():
    """Main execution function"""
    parser = argparse.ArgumentParser(description='A-Share Strategy Generator')
    parser.add_argument('--section', type=str, default='all', choices=['all', 'market', 'holdings', 'candidates'],
                      help='Specify which section to generate (market, holdings, candidates, or all)')
    args = parser.parse_args()

    print("\n" + "="*60)
    print(f"🚀 A-Share Trading Discipline Assistant - Mode: {args.section.upper()}")
    print("="*60)
    
    # Ensure reports directory exists
    os.makedirs("reports", exist_ok=True)
    date_str = datetime.now().strftime('%Y%m%d')
    display_date = datetime.now().strftime('%Y-%m-%d')

    # Load configuration
    config = load_config()
    
    # Validate API configuration
    provider = config['api'].get('provider', 'openai')
    api_config_key = f"api_{provider}"
    
    if api_config_key in config:
        api_config = config[api_config_key]
    else:
        api_config = config['api']
    
    # API Check (omitted for brevity, assume valid if config exists)
    print(f"\n🤖 LLM Provider: {provider}")

    # --- EXECUTION ---
    
    # 1. Market Section
    if args.section in ['all', 'market']:
        header = generate_report_header()
        market_status = get_market_status(config['analysis']['lookback_days'])
        
        market_section = header # Header goes with market section usually
        if market_status:
            market_section += f"## 🌍 大盘环境 (Beta Shield)\n\n"
            market_section += f"- **指数**：{market_status['name']}\n"
            market_section += f"- **状态**：**{market_status['trend']}**\n"
            market_section += f"- **数据**：当前 {market_status['close']} / MA20 {market_status['ma20']}\n"
            if "看跌" in market_status['trend']:
                market_section += f"- **警示**：大盘处于弱势区域，建议**严格控制仓位**，所有买入信号需打折处理！\n"
            else:
                market_section += f"- **提示**：大盘处于强势区域，可正常操作。\n"
            market_section += f"\n---\n\n"
        
        save_section(market_section, "market", date_str)

    # 2. Holdings Section
    if args.section in ['all', 'holdings']:
        print("\n🔄 Starting Holdings Analysis...")
        holdings_result = process_portfolio(config, display_date)
        save_section(holdings_result, "holdings", date_str)

    # 3. Candidates Section
    if args.section in ['all', 'candidates']:
        print("\n🔍 Starting Candidate Scanning...")
        candidates_result = process_candidates(config, api_config, display_date)
        save_section(candidates_result, "candidates", date_str)

    # 4. Merge for Legacy Full Report (Only if running 'all')
    if args.section == 'all':
        try:
            # We already have the variables in scope if running all
            # But let's read from files to be safe/consistent or just use vars?
            # Using vars is faster.
            full_content = market_section + holdings_result + "\n\n---\n\n" + candidates_result + generate_report_footer()
            
            output_filename_full = os.path.join("reports", f"daily_strategy_full_{date_str}.md")
            with open(output_filename_full, 'w', encoding='utf-8') as f:
                f.write(full_content)
            print(f"✅ [Legacy] Full Markdown Report saved to: {output_filename_full}")
            
            # HTML Gen
            output_filename_html = os.path.join("reports", f"daily_strategy_{date_str}.html")
            generate_html_report(holdings_result, candidates_result, output_filename_html)
            print(f"✅ [Legacy] HTML Report saved")
            
        except Exception as e:
            print(f"⚠️ Error creating legacy full report: {e}")

    print(f"\n{'-'*60}")
    print(f"🏁 Task [{args.section}] Completed.")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()

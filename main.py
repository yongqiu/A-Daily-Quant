"""
A-Share Trading Discipline Assistant - Main Orchestrator
Generates daily objective analysis reports to enforce trading discipline
"""
import json
from datetime import datetime
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

from data_fetcher import fetch_stock_data, calculate_start_date
from indicator_calc import calculate_indicators, get_latest_metrics
from llm_analyst import generate_analysis, format_stock_section
from report_generator import generate_html_report
from stock_screener import run_stock_selection


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
    print(f"🤖 Generating AI analysis...")
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


def process_portfolio(config: Dict[str, Any]) -> str:
    """
    Process portfolio analysis (to be run in parallel)
    """
    portfolio = config['portfolio']
    print(f"\n📊 Portfolio contains {len(portfolio)} positions")
    
    content = "\n# 📊 持仓分析日报\n\n"
    
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


def process_candidates(config: Dict[str, Any], api_config: Dict[str, Any]) -> str:
    """
    Process stock selection and analysis (to be run in parallel)
    """
    print("\n🔍 Running Market Scanner...")
    
    content = "\n# 🎯 今日选股参考 (AI精选)\n\n"
    
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


def main():
    """Main execution function"""
    print("\n" + "="*60)
    print("🚀 A-Share Trading Discipline Assistant - Starting")
    print("="*60)
    
    # Load configuration
    config = load_config()
    
    # Validate API configuration
    provider = config['api'].get('provider', 'openai')
    api_config_key = f"api_{provider}"
    
    if api_config_key in config:
        api_config = config[api_config_key]
    else:
        api_config = config['api']
    
    if provider == 'openai':
        if api_config.get('api_key') == "YOUR_API_KEY_HERE":
            print("\n⚠️  WARNING: Please update your API key in config.json")
            print("The script will continue but LLM analysis will fail.\n")
    elif provider == 'gemini':
        if api_config.get('credentials_path') == "/path/to/your/google-credentials.json":
            print("\n⚠️  WARNING: Please update your Google Cloud credentials path in config.json")
            print("The script will continue but LLM analysis will fail.\n")
    elif provider == 'deepseek':
        if not api_config.get('api_key'):
            print("\n⚠️  WARNING: Please update your DeepSeek API key in config.json")
            print("The script will continue but LLM analysis will fail.\n")
    
    print(f"\n🤖 LLM Provider: {provider}")
    
    # Initialize separate report contents
    header = generate_report_header()
    footer = generate_report_footer()
    
    content_holdings = header
    content_candidates = header
    
    # Step 0: Analyze Market Environment
    market_status = get_market_status(config['analysis']['lookback_days'])
    
    if market_status:
        market_section = f"## 🌍 大盘环境 (Beta Shield)\n\n"
        market_section += f"- **指数**：{market_status['name']}\n"
        market_section += f"- **状态**：**{market_status['trend']}**\n"
        market_section += f"- **数据**：当前 {market_status['close']} / MA20 {market_status['ma20']}\n"
        if "看跌" in market_status['trend']:
            market_section += f"- **警示**：大盘处于弱势区域，建议**严格控制仓位**，所有买入信号需打折处理！\n"
        else:
            market_section += f"- **提示**：大盘处于强势区域，可正常操作。\n"
        market_section += f"\n---\n\n"
        
        # Add market status to both sections
        content_holdings += market_section
        content_candidates += market_section
    
    # Run Portfolio Analysis and Candidate Scanning in Parallel
    print("\n🔄 Starting Parallel Processing: Holdings Analysis & Candidate Scanning...")
    
    with ThreadPoolExecutor(max_workers=2) as executor:
        future_holdings = executor.submit(process_portfolio, config)
        future_candidates = executor.submit(process_candidates, config, api_config)
        
        # Wait for results
        holdings_result = future_holdings.result()
        candidates_result = future_candidates.result()
        
    print("\n✅ Parallel Processing Complete.")
    
    # Append results
    content_holdings += holdings_result
    content_candidates += candidates_result
    
    # Add footer to both
    content_holdings += footer
    content_candidates += footer
    
    # Save reports to files (Markdown)
    date_str = datetime.now().strftime('%Y%m%d')
    output_filename_holdings = f"daily_strategy_holdings_{date_str}.md"
    output_filename_candidates = f"daily_strategy_candidates_{date_str}.md"
    
    try:
        with open(output_filename_holdings, 'w', encoding='utf-8') as f:
            f.write(content_holdings)
        with open(output_filename_candidates, 'w', encoding='utf-8') as f:
            f.write(content_candidates)
            
        print(f"\n{'='*60}")
        print(f"✅ Markdown Reports saved to:\n  - {output_filename_holdings}\n  - {output_filename_candidates}")
    except Exception as e:
        print(f"\n❌ Error saving MD report: {e}\n")
        raise

    # Generate HTML Report (Combined with tabs)
    output_filename_html = f"daily_strategy_{date_str}.html"
    try:
        generate_html_report(content_holdings, content_candidates, output_filename_html)
        print(f"✅ HTML Report saved to: {output_filename_html}")
        print(f"👉 You can open it in browser: open {output_filename_html}")
        print(f"{'='*60}\n")
    except Exception as e:
        print(f"\n❌ Error generating HTML report: {e}\n")


if __name__ == "__main__":
    main()

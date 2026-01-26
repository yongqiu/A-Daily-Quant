"""
Backtest Runner Script
"""
import argparse
from backtester.engine import BacktestEngine
from backtester.analysis import calculate_performance_metrics, print_performance_report

def main():
    parser = argparse.ArgumentParser(description='Run Daily Strategy Backtest')
    parser.add_argument('--symbol', type=str, default='600519', help='Stock symbol to test (default: 600519 Moutai)')
    parser.add_argument('--start', type=str, default='20240101', help='Start date YYYYMMDD')
    parser.add_argument('--end', type=str, default='20250101', help='End date YYYYMMDD')
    parser.add_argument('--capital', type=float, default=100000.0, help='Initial capital')
    parser.add_argument('--pool', type=str, help='Comma separated list of symbols for portfolio backtest (e.g. "600519,601899,000858")')
    parser.add_argument('--max_pos', type=int, default=3, help='Max positions in portfolio mode (default: 3)')

    args = parser.parse_args()
    
    engine = BacktestEngine(args.start, args.end, args.capital)
    
    if args.pool:
        # Portfolio Mode
        symbols = [s.strip() for s in args.pool.split(',')]
        print(f"🚀 Starting Portfolio Backtest for {len(symbols)} stocks")
        print(f"📦 Pool: {symbols}")
        print(f"📅 Period: {args.start} to {args.end}")
        print(f"🔢 Max Positions: {args.max_pos}")
        
        result = engine.run_portfolio(symbols, max_positions=args.max_pos)
    else:
        # Single Stock Mode
        print(f"🚀 Starting Single Stock Backtest for {args.symbol}")
        print(f"📅 Period: {args.start} to {args.end}")
        
        result = engine.run(args.symbol)
    
    if not result:
        print("❌ Backtest failed (no data or error).")
        return
        
    metrics = calculate_performance_metrics(result['history'], args.capital)
    trades = engine.account.trades
    
    print_performance_report(metrics, trades)
    
    # Optional: Plotting could go here

if __name__ == "__main__":
    main()
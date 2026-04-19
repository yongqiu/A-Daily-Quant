"""
Backtest Runner Script
"""
import argparse
from pathlib import Path

import pandas as pd

from backtester.engine import BacktestEngine
from backtester.parquet_loader import (
    load_universe_symbols_from_parquet,
    resolve_default_quant_lab_bars_path,
    resolve_default_quant_lab_memberships_path,
)
from backtester.analysis import (
    calculate_performance_metrics,
    calculate_score_layer_metrics,
    print_performance_report,
    print_score_layer_report,
)


def build_default_trades_path(args, symbols) -> Path:
    outputs_dir = Path("outputs")
    outputs_dir.mkdir(parents=True, exist_ok=True)
    mode_label = "portfolio" if symbols else "single"
    universe_label = args.universe_name or args.symbol
    safe_universe = str(universe_label).replace("/", "_").replace(" ", "_")
    return outputs_dir / (
        f"trades_{mode_label}_{safe_universe}_{args.start}_{args.end}.csv"
    )


def export_trades_csv(trades, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if trades:
        df = pd.DataFrame(trades)
    else:
        df = pd.DataFrame(
            columns=["date", "action", "symbol", "price", "volume", "fee", "amount", "pnl"]
        )
    df.to_csv(output_path, index=False, encoding="utf-8-sig")


def main():
    parser = argparse.ArgumentParser(description='Run Daily Strategy Backtest')
    parser.add_argument('--symbol', type=str, default='600519', help='Stock symbol to test (default: 600519 Moutai)')
    parser.add_argument('--start', type=str, default='20240101', help='Start date YYYYMMDD')
    parser.add_argument('--end', type=str, default='20250101', help='End date YYYYMMDD')
    parser.add_argument('--capital', type=float, default=100000.0, help='Initial capital')
    parser.add_argument('--pool', type=str, help='Comma separated list of symbols for portfolio backtest (e.g. "600519,601899,000858")')
    parser.add_argument('--max_pos', type=int, default=3, help='Max positions in portfolio mode (default: 3)')
    parser.add_argument(
        '--universe-name',
        type=str,
        default=None,
        help='Universe name from a memberships parquet, e.g. tradable_core. Enables portfolio backtest when --pool is not set.',
    )
    parser.add_argument(
        '--universe-path',
        type=str,
        default=None,
        help='Path to universe memberships parquet. Defaults to quant-lab storage when --use-quant-lab-data is set.',
    )
    parser.add_argument(
        '--universe-as-of',
        type=str,
        default=None,
        help='Optional universe membership date filter. By default, uses the latest snapshot members.',
    )
    parser.add_argument(
        '--bars-path',
        type=str,
        default=None,
        help='Optional local parquet daily bars path. When set, backtest loads history from this file before falling back to online sources.',
    )
    parser.add_argument(
        '--use-quant-lab-data',
        action='store_true',
        help='Use the default quant-lab parquet daily bars path if it exists.',
    )
    parser.add_argument(
        '--slippage-rate',
        type=float,
        default=0.001,
        help='One-way slippage rate applied to execution price (default: 0.001 = 10 bps).',
    )
    parser.add_argument(
        '--commission-rate',
        type=float,
        default=0.0003,
        help='Broker commission rate per trade side (default: 0.0003 = 3 bps).',
    )
    parser.add_argument(
        '--min-commission',
        type=float,
        default=5.0,
        help='Minimum broker commission per trade (default: 5 RMB).',
    )
    parser.add_argument(
        '--stamp-duty-rate',
        type=float,
        default=0.001,
        help='Stamp duty rate for sells only (default: 0.001 = 10 bps).',
    )
    parser.add_argument(
        '--trades-csv',
        type=str,
        default=None,
        help='Optional path to export executed trades CSV. Defaults to outputs/trades_*.csv.',
    )

    args = parser.parse_args()

    bars_path = args.bars_path
    if args.use_quant_lab_data and not bars_path:
        resolved = resolve_default_quant_lab_bars_path()
        bars_path = resolved.as_posix() if resolved else None

    universe_path = args.universe_path
    if (args.use_quant_lab_data or args.universe_name) and not universe_path:
        resolved = resolve_default_quant_lab_memberships_path()
        universe_path = resolved.as_posix() if resolved else None

    symbols = []
    pool_label = ""
    if args.pool:
        symbols = [s.strip() for s in args.pool.split(',') if s.strip()]
        pool_label = "CLI pool"
    elif args.universe_name:
        if not universe_path:
            raise FileNotFoundError(
                "Universe path is required. Pass --universe-path or use --use-quant-lab-data."
            )
        symbols = list(
            load_universe_symbols_from_parquet(
                universe_path,
                args.universe_name,
                as_of_date=args.universe_as_of,
            )
        )
        if not symbols:
            raise ValueError(
                f"No symbols found for universe '{args.universe_name}'"
                + (f" as of {args.universe_as_of}" if args.universe_as_of else "")
            )
        pool_label = f"Universe {args.universe_name}"
        if args.universe_as_of:
            pool_label += f" as of {args.universe_as_of}"
        else:
            pool_label += " latest snapshot"
        if not bars_path:
            resolved = resolve_default_quant_lab_bars_path()
            bars_path = resolved.as_posix() if resolved else None

    engine = BacktestEngine(
        args.start,
        args.end,
        args.capital,
        bars_path=bars_path,
        slippage_rate=args.slippage_rate,
        commission_rate=args.commission_rate,
        min_commission=args.min_commission,
        stamp_duty_rate=args.stamp_duty_rate,
    )
    
    if symbols:
        # Portfolio Mode
        print(f"🚀 Starting Portfolio Backtest for {len(symbols)} stocks")
        print(f"📦 Pool: {pool_label}")
        print(f"🔎 Symbols sample: {symbols[:10]}{' ...' if len(symbols) > 10 else ''}")
        print(f"📅 Period: {args.start} to {args.end}")
        print(f"🔢 Max Positions: {args.max_pos}")
        print("🧠 Score: dual entry/holding")
        print(
            f"💸 Costs: slippage={args.slippage_rate:.4%}, "
            f"commission={args.commission_rate:.4%}, min_commission={args.min_commission:.2f}, "
            f"stamp_duty={args.stamp_duty_rate:.4%}"
        )
        if bars_path:
            print(f"🗂️ Bars Path: {bars_path}")
        if universe_path:
            print(f"🧺 Universe Path: {universe_path}")
        
        result = engine.run_portfolio(symbols, max_positions=args.max_pos)
    else:
        # Single Stock Mode
        print(f"🚀 Starting Single Stock Backtest for {args.symbol}")
        print(f"📅 Period: {args.start} to {args.end}")
        print("🧠 Score: dual entry/holding")
        print(
            f"💸 Costs: slippage={args.slippage_rate:.4%}, "
            f"commission={args.commission_rate:.4%}, min_commission={args.min_commission:.2f}, "
            f"stamp_duty={args.stamp_duty_rate:.4%}"
        )
        if bars_path:
            print(f"🗂️ Bars Path: {bars_path}")
        
        result = engine.run(args.symbol)
    
    if not result:
        print("❌ Backtest failed (no data or error).")
        return
        
    metrics = calculate_performance_metrics(result['history'], args.capital)
    trades = engine.account.trades
    trades_csv_path = Path(args.trades_csv) if args.trades_csv else build_default_trades_path(args, symbols)
    export_trades_csv(trades, trades_csv_path)
    
    print_performance_report(metrics, trades)
    if symbols and engine.score_samples:
        layer_report = calculate_score_layer_metrics(engine.score_samples)
        print_score_layer_report(layer_report)
    print(f"🧾 Trades CSV: {trades_csv_path.resolve()}")
    
    # Optional: Plotting could go here

if __name__ == "__main__":
    main()

"""
Performance Analysis Module
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Any

def calculate_performance_metrics(history: List[Dict[str, Any]], initial_capital: float) -> Dict[str, Any]:
    """
    Calculate generic performance metrics from account history.
    """
    if not history:
        return {}
        
    df = pd.DataFrame(history)
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date')
    
    # 1. Total Return
    final_value = df.iloc[-1]['total_value']
    total_return_pct = ((final_value - initial_capital) / initial_capital) * 100
    
    # 2. Annualized Return (CAGR)
    days = (df.iloc[-1]['date'] - df.iloc[0]['date']).days
    if days > 0:
        cagr = ((final_value / initial_capital) ** (365 / days) - 1) * 100
    else:
        cagr = 0.0
        
    # 3. Max Drawdown
    df['peak'] = df['total_value'].cummax()
    df['drawdown'] = (df['total_value'] - df['peak']) / df['peak']
    max_drawdown = df['drawdown'].min() * 100 # Percentage
    
    return {
        'initial_capital': initial_capital,
        'final_value': round(final_value, 2),
        'total_return_pct': round(total_return_pct, 2),
        'cagr_pct': round(cagr, 2),
        'max_drawdown_pct': round(max_drawdown, 2)
    }

def print_performance_report(metrics: Dict[str, Any], trades: List[Dict[str, Any]]):
    """
    Print a formatted report to console
    """
    print("\n" + "="*40)
    print("📊 BACKTEST PERFORMANCE REPORT")
    print("="*40)
    
    print(f"💰 Initial Capital:   {metrics['initial_capital']:,.2f}")
    print(f"🏁 Final Value:       {metrics['final_value']:,.2f}")
    
    ret_color = "\033[92m" if metrics['total_return_pct'] > 0 else "\033[91m"
    reset = "\033[0m"
    
    print(f"📈 Total Return:      {ret_color}{metrics['total_return_pct']}%{reset}")
    print(f"📅 CAGR (Annualized): {metrics['cagr_pct']}%")
    print(f"📉 Max Drawdown:      {metrics['max_drawdown_pct']}%")
    
    print("-" * 40)
    
    # Trade Analysis
    if trades:
        win_trades = [t for t in trades if t['action'] == 'SELL' and t.get('pnl', 0) > 0]
        loss_trades = [t for t in trades if t['action'] == 'SELL' and t.get('pnl', 0) <= 0]
        total_sells = len(win_trades) + len(loss_trades)
        
        if total_sells > 0:
            win_rate = (len(win_trades) / total_sells) * 100
            print(f"🔄 Total Trades:      {total_sells} (Round trips)")
            print(f"✅ Win Rate:          {win_rate:.1f}%")
            
            total_profit = sum(t['pnl'] for t in win_trades)
            total_loss = sum(t['pnl'] for t in loss_trades)
            avg_win = total_profit / len(win_trades) if win_trades else 0
            avg_loss = abs(total_loss / len(loss_trades)) if loss_trades else 1
            
            pl_ratio = avg_win / avg_loss if avg_loss > 0 else float('inf')
            print(f"⚖️ Profit/Loss Ratio: {pl_ratio:.2f}")
    else:
        print("No trades executed.")
        
    print("="*40 + "\n")

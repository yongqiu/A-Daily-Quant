"""
Backtest Engine Module
"""
import pandas as pd
import numpy as np
from typing import List, Dict, Any, Optional
from datetime import datetime
import time

from backtester.account import VirtualAccount
from indicator_calc import calculate_indicators, get_latest_metrics, calculate_composite_score
from data_fetcher import fetch_stock_data

class BacktestEngine:
    """
    Main engine to run backtests on specific symbols.
    """
    def __init__(self, start_date: str, end_date: str, initial_capital: float = 100000.0):
        self.start_date = pd.to_datetime(start_date)
        self.end_date = pd.to_datetime(end_date)
        self.account = VirtualAccount(initial_capital)
        self.logs: List[str] = []
        
        # Cache for fetched data
        self.data_cache: Dict[str, pd.DataFrame] = {}

    def log(self, message: str):
        """Add log message"""
        print(f"[Backtest] {message}")
        self.logs.append(message)

    def load_data(self, symbols: List[str]):
        """
        Pre-fetch data for all symbols to minimize network calls during loop.
        We fetch a bit more than start_date calculation needs to ensure MA stability.
        """
        # We need data BEFORE start_date for indicator calculation (e.g. MA60)
        # 120 days lookback buffer
        fetch_start_date = (self.start_date - pd.Timedelta(days=150)).strftime('%Y%m%d')
        
        for symbol in symbols:
            self.log(f"Fetching history for {symbol} from {fetch_start_date}...")
            # If it's a list scan, we might want to be careful with API limits, but for single/few stocks it's fine.
            df = fetch_stock_data(symbol, fetch_start_date)
            
            if df is not None and not df.empty:
                # Ensure date is datetime
                df['date'] = pd.to_datetime(df['date'])
                self.data_cache[symbol] = df
            else:
                self.log(f"⚠️ Failed to fetch data for {symbol}")

    def run(self, symbol: str) -> Dict[str, Any]:
        """
        Run backtest for a single symbol.
        Assumption: We are testing a "buy and hold" or "swing trade" strategy on this specific stock.
        """
        if symbol not in self.data_cache:
            self.load_data([symbol])
            
        full_df = self.data_cache.get(symbol)
        if full_df is None or len(full_df) < 60:
            self.log(f"Insufficient data for {symbol}, aborting.")
            return {}
            
        self.log(f"Starting simulation for {symbol}...")
        
        # Slice Main Loop
        # We iterate day by day from start_date to end_date
        # For each day, we look at window [current_date - lookback : current_date]
        
        # Filter trade dates within range
        trade_dates = full_df[(full_df['date'] >= self.start_date) & (full_df['date'] <= self.end_date)]['date'].tolist()
        
        if not trade_dates:
            self.log("No trading dates in specified range.")
            return {}
            
        # OPTIMIZED APPROACH:
        # Calculate all indicators on the entire dataframe ONCE.
        # This avoids re-calculating MA60 thousands of times.
        self.log("Calculating indicators on full history...")
        analyzed_df = calculate_indicators(full_df)
        
        # Now iterate relevant rows
        mask = (analyzed_df['date'] >= self.start_date) & (analyzed_df['date'] <= self.end_date)
        sim_df = analyzed_df[mask]
        
        for idx, row in sim_df.iterrows():
            date_str = row['date'].strftime('%Y-%m-%d')
            close_price = row['close']
            
            # --- STRATEGY LOGIC ---
            
            # Construct metrics dict similar to what 'get_latest_metrics' returns
            # We need to adapt the row data to match the expected dictionary format of calculate_composite_score
            metrics = row.to_dict()
            
            # Supplement missing keys if necessary (volume signals, etc handled in calculate_indicators)
            score, _, _, _ = calculate_composite_score(metrics)
            
            # Decisions
            current_holdings = self.account.holdings.get(symbol, {'volume': 0})['volume']
            
            # BUY SIGNAL
            # Logic: High Score + Bullish Trend
            if current_holdings == 0:
                if score >= 75 and row['ma20'] < close_price:
                    # Position Sizing: Use 95% of cash (All in for single stock test)
                    amount_to_invest = self.account.cash * 0.95
                    if amount_to_invest > 2000: # Min trade
                         vol = int(amount_to_invest / close_price / 100) * 100
                         if vol > 0:
                             self.account.buy(date_str, symbol, close_price, vol)
                             self.log(f"[{date_str}] 🟢 BUY {vol} @ {close_price:.2f} (Score: {score})")
            
            # SELL SIGNAL
            # Logic: Low Score OR Stop Loss (Close < MA20 * 0.95?)
            elif current_holdings > 0:
                # Sell if score drops or strict stop loss
                is_stop_loss = close_price < (row['ma20'] * 0.95)
                if score < 45 or is_stop_loss:
                    reason = "Stop Loss" if is_stop_loss else f"Score Drop ({score})"
                    self.account.sell(date_str, symbol, close_price)
                    self.log(f"[{date_str}] 🔴 SELL ALL @ {close_price:.2f} - {reason}")

            # Update Account Stats
            self.account.update_daily_stats(date_str, {symbol: close_price})
            
        self.log("Backtest complete.")
        return {
            'final_value': self.account.history[-1]['total_value'] if self.account.history else self.account.initial_capital,
            'trades': len(self.account.trades),
            'history': self.account.history
        }

    def run_portfolio(self, symbols: List[str], max_positions: int = 3) -> Dict[str, Any]:
        """
        Run backtest on a portfolio of provided stocks.
        Logic:
          - Daily: Calculate score for all stocks
          - Rebalance:
             - Sell stocks that hit Sell Logic
             - If holdings < max_positions: Buy best available stock from pool
        """
        if not symbols:
            self.log("No symbols provided for portfolio backtest.")
            return {}

        self.load_data(symbols)
        
        # 1. Pre-calculate indicators for ALL stocks to speed up loop
        # Store as dict of DataFrames, indexed by date for fast lookup
        # Actually, iterating by date is better.
        # Let's create a huge merged lookup or just keep dict.
        
        stock_dfs = {}
        all_dates = set()
        
        self.log("Pre-calculating indicators for all stocks in pool...")
        for symbol, df in self.data_cache.items():
            if len(df) < 60:
                continue
            
            analyzed = calculate_indicators(df)
            mask = (analyzed['date'] >= self.start_date) & (analyzed['date'] <= self.end_date)
            sim_df = analyzed[mask].copy()
            sim_df.set_index('date', inplace=True)
            stock_dfs[symbol] = sim_df
            all_dates.update(sim_df.index)
            
        sorted_dates = sorted(list(all_dates))
        self.log(f"Simulation range: {len(sorted_dates)} trading days.")
        
        for current_date in sorted_dates:
            date_str = current_date.strftime('%Y-%m-%d')
            
            # --- 1. SELL LOGIC FIRST ---
            # Check current holdings
            current_symbols = list(self.account.holdings.keys())
            
            for symbol in current_symbols:
                if symbol not in stock_dfs or current_date not in stock_dfs[symbol].index:
                    continue # No data for today (suspension?)
                    
                row = stock_dfs[symbol].loc[current_date]
                close_price = row['close']
                metrics = row.to_dict()
                score, _, _, _ = calculate_composite_score(metrics)
                
                # Sell Logic
                is_stop_loss = close_price < (row['ma20'] * 0.95)
                if score < 45 or is_stop_loss:
                    reason = "Stop Loss" if is_stop_loss else f"Score Drop ({score})"
                    self.account.sell(date_str, symbol, close_price)
                    self.log(f"[{date_str}] 🔴 SELL {symbol} @ {close_price:.2f} - {reason}")

            # --- 2. BUY LOGIC ---
            # If we have free slots
            free_slots = max_positions - len(self.account.holdings)
            
            if free_slots > 0:
                # Scan pool for candidates
                candidates = []
                
                for symbol in symbols:
                    if symbol in self.account.holdings:
                        continue # Already hold
                    if symbol not in stock_dfs or current_date not in stock_dfs[symbol].index:
                        continue
                        
                    row = stock_dfs[symbol].loc[current_date]
                    close_price = row['close']
                    metrics = row.to_dict()
                    score, _, _, _ = calculate_composite_score(metrics)
                    
                    # Buy Criteria
                    if score >= 80 and row['ma20'] < close_price:
                         candidates.append({
                             'symbol': symbol,
                             'score': score,
                             'price': close_price,
                             'vol_ratio': row.get('volume_ratio', 1.0)
                         })
                         
                # Sort by score desc, then vol_ratio
                candidates.sort(key=lambda x: (x['score'], x['vol_ratio']), reverse=True)
                
                # Buy top N
                for cand in candidates[:free_slots]:
                    # Position Sizing: Equal weight of CURRENT NAV / max_positions or Cash / free_slots?
                    # Let's use: Available Cash / free_slots
                    # But if we just sold, we have cash.
                    # Simple model: Allocate `total_capital / max_positions` per slot.
                    # But cash changes. Let's just use `cash / free_slots` to fully utilize cash.
                    
                    amount_per_slot = self.account.cash / free_slots
                    if amount_per_slot > 5000:
                        vol = int(amount_per_slot / cand['price'] / 100) * 100
                        if vol > 0:
                            if self.account.buy(date_str, cand['symbol'], cand['price'], vol):
                                self.log(f"[{date_str}] 🟢 BUY {cand['symbol']} @ {cand['price']:.2f} (Score: {cand['score']})")
                                free_slots -= 1 # Decr slot
            
            # --- 3. Update Stats ---
            # Get prices for all holdings
            current_prices = {}
            for s in self.account.holdings:
                if s in stock_dfs and current_date in stock_dfs[s].index:
                    current_prices[s] = stock_dfs[s].loc[current_date]['close']
                # else keep old price (or 0 if missing, which is risky)
            
            self.account.update_daily_stats(date_str, current_prices)
            
        return {
            'final_value': self.account.history[-1]['total_value'] if self.account.history else self.account.initial_capital,
            'trades': len(self.account.trades),
            'history': self.account.history
        }

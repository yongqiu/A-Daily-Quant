"""
Virtual Account Module for Backtesting
"""
from typing import Dict, List, Any
from datetime import datetime

class VirtualAccount:
    """
    Simulates a trading account with cash and holdings.
    """
    def __init__(self, initial_capital: float = 100000.0):
        self.initial_capital = initial_capital
        self.cash = initial_capital
        
        # Holdings: {symbol: {'volume': int, 'cost_price': float, 'market_value': float}}
        self.holdings: Dict[str, Dict[str, Any]] = {}
        
        # Trade History: list of dicts
        self.trades: List[Dict[str, Any]] = []
        
        # Daily Equity History: list of {'date': date, 'total_value': float, 'cash': float}
        self.history: List[Dict[str, Any]] = []

        # Fee structure
        self.commission_rate = 0.0003  # 0.03%
        self.min_commission = 5.0      # Minimum 5 RMB
        self.stamp_duty_rate = 0.001   # 0.1% (Sell only)

    def calculate_commission(self, amount: float) -> float:
        """Calculate commission fee"""
        return max(amount * self.commission_rate, self.min_commission)

    def calculate_tax(self, amount: float) -> float:
        """Calculate stamp duty (Sell only)"""
        return amount * self.stamp_duty_rate

    def buy(self, date: str, symbol: str, price: float, volume: int) -> bool:
        """
        Execute a buy order.
        Returns True if successful, False if insufficient funds.
        """
        if volume <= 0 or price <= 0:
            return False
            
        amount = price * volume
        commission = self.calculate_commission(amount)
        total_cost = amount + commission
        
        if self.cash < total_cost:
            # print(f"⚠️ Insufficient cash to buy {symbol}. Need {total_cost:.2f}, Have {self.cash:.2f}")
            return False
            
        self.cash -= total_cost
        
        # Update Holdings
        if symbol not in self.holdings:
            self.holdings[symbol] = {'volume': 0, 'cost_price': 0.0}
            
        # Weighted Average Cost
        current_vol = self.holdings[symbol]['volume']
        current_cost = self.holdings[symbol]['cost_price']
        new_vol = current_vol + volume
        new_avg_cost = ((current_vol * current_cost) + (volume * price)) / new_vol
        
        self.holdings[symbol]['volume'] = new_vol
        self.holdings[symbol]['cost_price'] = new_avg_cost
        
        # Record Trade
        self.trades.append({
            'date': date,
            'action': 'BUY',
            'symbol': symbol,
            'price': price,
            'volume': volume,
            'fee': commission,
            'amount': amount
        })
        
        return True

    def sell(self, date: str, symbol: str, price: float, volume: int = 0) -> bool:
        """
        Execute a sell order. 
        If volume is 0 or not specified, sell all.
        Returns True if successful.
        """
        if symbol not in self.holdings:
            return False
            
        current_vol = self.holdings[symbol]['volume']
        
        if volume <= 0 or volume > current_vol:
            volume = current_vol # Sell all
            
        if volume == 0:
            return False
            
        amount = price * volume
        commission = self.calculate_commission(amount)
        tax = self.calculate_tax(amount)
        net_income = amount - commission - tax
        
        self.cash += net_income
        
        # Capture cost for PnL before modifying holdings
        cost_price = self.holdings[symbol]['cost_price']
        
        # Update Holdings
        remaining_vol = current_vol - volume
        if remaining_vol > 0:
            self.holdings[symbol]['volume'] = remaining_vol
        else:
            del self.holdings[symbol]
            
        # Record Trade
        self.trades.append({
            'date': date,
            'action': 'SELL',
            'symbol': symbol,
            'price': price,
            'volume': volume,
            'fee': commission + tax,
            'amount': amount,
            'pnl': (price - cost_price) * volume
        })
        
        return True

    def update_daily_stats(self, date: str, current_prices: Dict[str, float]):
        """
        Update daily equity value based on close prices
        """
        holdings_value = 0.0
        for symbol, data in self.holdings.items():
            price = current_prices.get(symbol)
            if price:
                holdings_value += data['volume'] * price
            else:
                # Fallback to cost if no price (shouldn't happen in proper backtest)
                holdings_value += data['volume'] * data['cost_price']
                
        total_value = self.cash + holdings_value
        
        self.history.append({
            'date': date,
            'total_value': total_value,
            'cash': self.cash,
            'holdings_value': holdings_value
        })

    def get_total_value(self, current_prices: Dict[str, float]) -> float:
        """Get instant total value"""
        holdings_value = 0.0
        for symbol, data in self.holdings.items():
            price = current_prices.get(symbol, data['cost_price'])
            holdings_value += data['volume'] * price
        return self.cash + holdings_value
"""
Risk Management Module with Balance-Based Mode Switching

This module handles:
- Automatic detection of trading mode (SPOT vs FUTURES) based on balance
- Position sizing according to current mode
- Stop-loss and take-profit calculations
- Loss streak monitoring and trading pauses
- Concurrent trade limits
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
from enum import Enum

from config.settings import (
    BALANCE_THRESHOLD_USDT,
    # Futures parameters
    FUTURES_POSITION_SIZE_PERCENT,
    FUTURES_LEVERAGE,
    FUTURES_MAX_LEVERAGE,
    FUTURES_STOP_LOSS_PERCENT,
    FUTURES_TAKE_PROFIT_1_USDT,
    FUTURES_TAKE_PROFIT_2_USDT,
    FUTURES_TRAILING_STOP_ACTIVATION_USDT,
    FUTURES_TIMEOUT_NO_MOVEMENT_MINUTES,
    MAX_CONCURRENT_TRADES,
    MAX_CONCURRENT_COINS,
    MAX_LOSS_STREAK,
    TRADING_PAUSE_HOURS,
    # Spot parameters
    SPOT_POSITION_SIZE_PERCENT,
    SPOT_LEVERAGE,
    SPOT_TARGET_PROFIT_PERCENT,
    SPOT_STOP_LOSS_PERCENT,
    SPOT_TAKE_PROFIT_1_PERCENT,
    SPOT_TAKE_PROFIT_2_PERCENT,
    SPOT_TRAILING_STOP_ACTIVATION_PERCENT,
    SPOT_TIMEOUT_NO_MOVEMENT_MINUTES,
    SPOT_MAX_CONCURRENT_TRADES,
    SPOT_MAX_CONCURRENT_COINS,
    SPOT_MAX_LOSS_STREAK,
    SPOT_TRADING_PAUSE_HOURS,
    SPOT_ALLOW_SHORT,
)

logger = logging.getLogger(__name__)


class TradingMode(Enum):
    """Trading mode enumeration"""
    SPOT = "SPOT"
    FUTURES = "FUTURES"


class TradeInfo:
    """Information about an open trade"""
    
    def __init__(
        self,
        symbol: str,
        side: str,  # 'BUY' or 'SELL'
        entry_price: float,
        quantity: float,
        mode: TradingMode,
        timestamp: datetime
    ):
        self.symbol = symbol
        self.side = side
        self.entry_price = entry_price
        self.quantity = quantity
        self.mode = mode
        self.timestamp = timestamp
        self.last_update = timestamp
        
        # Get parameters based on mode
        if mode == TradingMode.FUTURES:
            self.stop_loss_percent = FUTURES_STOP_LOSS_PERCENT
            self.tp1_value = FUTURES_TAKE_PROFIT_1_USDT
            self.tp2_value = FUTURES_TAKE_PROFIT_2_USDT
            self.trailing_activation = FUTURES_TRAILING_STOP_ACTIVATION_USDT
            self.timeout_minutes = FUTURES_TIMEOUT_NO_MOVEMENT_MINUTES
        else:  # SPOT
            self.stop_loss_percent = SPOT_STOP_LOSS_PERCENT
            self.tp1_percent = SPOT_TAKE_PROFIT_1_PERCENT
            self.tp2_percent = SPOT_TAKE_PROFIT_2_PERCENT
            self.trailing_activation_percent = SPOT_TRAILING_STOP_ACTIVATION_PERCENT
            self.timeout_minutes = SPOT_TIMEOUT_NO_MOVEMENT_MINUTES
        
        # Calculate levels
        self._calculate_levels()
        
        # Trailing stop state
        self.trailing_stop_active = False
        self.trailing_stop_price: Optional[float] = None
        self.max_profit_reached = 0.0
    
    def _calculate_levels(self):
        """Calculate stop-loss and take-profit levels"""
        if self.side == 'BUY':
            # Long position
            self.stop_loss_price = self.entry_price * (1 - self.stop_loss_percent / 100)
            
            if self.mode == TradingMode.FUTURES:
                # Futures: TP in USDT
                position_value = self.entry_price * self.quantity
                self.tp1_price = self.entry_price + (self.tp1_value / self.quantity)
                self.tp2_price = self.entry_price + (self.tp2_value / self.quantity)
            else:
                # Spot: TP in percentage
                self.tp1_price = self.entry_price * (1 + self.tp1_percent / 100)
                self.tp2_price = self.entry_price * (1 + self.tp2_percent / 100)
        else:
            # Short position
            self.stop_loss_price = self.entry_price * (1 + self.stop_loss_percent / 100)
            
            if self.mode == TradingMode.FUTURES:
                # Futures: TP in USDT
                self.tp1_price = self.entry_price - (self.tp1_value / self.quantity)
                self.tp2_price = self.entry_price - (self.tp2_value / self.quantity)
            else:
                # Spot: TP in percentage
                self.tp1_price = self.entry_price * (1 - self.tp1_percent / 100)
                self.tp2_price = self.entry_price * (1 - self.tp2_percent / 100)
    
    def update_price(self, current_price: float) -> Dict:
        """
        Update trade with current price and check for exit conditions
        
        Returns dict with exit signals:
        - 'action': None, 'CLOSE_ALL', 'CLOSE_HALF', 'UPDATE_STOP'
        - 'reason': Reason for action
        - 'profit_usdt': Current profit in USDT
        """
        self.last_update = datetime.now()
        
        # Calculate current profit
        if self.side == 'BUY':
            profit_usdt = (current_price - self.entry_price) * self.quantity
            profit_percent = ((current_price - self.entry_price) / self.entry_price) * 100
        else:
            profit_usdt = (self.entry_price - current_price) * self.quantity
            profit_percent = ((self.entry_price - current_price) / self.entry_price) * 100
        
        self.max_profit_reached = max(self.max_profit_reached, profit_usdt)
        
        result = {
            'action': None,
            'reason': None,
            'profit_usdt': profit_usdt,
            'profit_percent': profit_percent,
            'current_price': current_price
        }
        
        # Check stop-loss
        if self.side == 'BUY' and current_price <= self.stop_loss_price:
            result['action'] = 'CLOSE_ALL'
            result['reason'] = 'STOP_LOSS'
            return result
        
        if self.side == 'SELL' and current_price >= self.stop_loss_price:
            result['action'] = 'CLOSE_ALL'
            result['reason'] = 'STOP_LOSS'
            return result
        
        # Check take-profit levels (Futures mode)
        if self.mode == TradingMode.FUTURES:
            # Check TP1 - close 50%
            if self.side == 'BUY' and current_price >= self.tp1_price:
                result['action'] = 'CLOSE_HALF'
                result['reason'] = 'TAKE_PROFIT_1'
                # Update remaining position TP to TP2
                return result
            
            if self.side == 'SELL' and current_price <= self.tp1_price:
                result['action'] = 'CLOSE_HALF'
                result['reason'] = 'TAKE_PROFIT_1'
                return result
            
            # Check TP2 - close remaining 50%
            if self.side == 'BUY' and current_price >= self.tp2_price:
                result['action'] = 'CLOSE_ALL'
                result['reason'] = 'TAKE_PROFIT_2'
                return result
            
            if self.side == 'SELL' and current_price <= self.tp2_price:
                result['action'] = 'CLOSE_ALL'
                result['reason'] = 'TAKE_PROFIT_2'
                return result
            
            # Check trailing stop activation
            if not self.trailing_stop_active and profit_usdt >= self.trailing_activation:
                self.trailing_stop_active = True
                self.trailing_stop_price = self.entry_price  # Move to breakeven
                result['action'] = 'UPDATE_STOP'
                result['reason'] = 'TRAILING_STOP_ACTIVATED'
                result['new_stop_price'] = self.entry_price
                logger.info(f"Trailing stop activated for {self.symbol}, moved to breakeven")
                return result
            
            # Update trailing stop
            if self.trailing_stop_active:
                if self.side == 'BUY':
                    new_trail = current_price - (self.trailing_activation / self.quantity)
                    if new_trail > self.trailing_stop_price:
                        self.trailing_stop_price = new_trail
                        result['action'] = 'UPDATE_STOP'
                        result['reason'] = 'TRAILING_STOP_UPDATED'
                        result['new_stop_price'] = new_trail
                        return result
                else:
                    new_trail = current_price + (self.trailing_activation / self.quantity)
                    if new_trail < self.trailing_stop_price:
                        self.trailing_stop_price = new_trail
                        result['action'] = 'UPDATE_STOP'
                        result['reason'] = 'TRAILING_STOP_UPDATED'
                        result['new_stop_price'] = new_trail
                        return result
                
                # Check if trailing stop hit
                if self.side == 'BUY' and current_price <= self.trailing_stop_price:
                    result['action'] = 'CLOSE_ALL'
                    result['reason'] = 'TRAILING_STOP_HIT'
                    return result
                
                if self.side == 'SELL' and current_price >= self.trailing_stop_price:
                    result['action'] = 'CLOSE_ALL'
                    result['reason'] = 'TRAILING_STOP_HIT'
                    return result
        
        else:  # Spot mode
            # Check TP1
            if self.side == 'BUY' and current_price >= self.tp1_price:
                result['action'] = 'CLOSE_HALF'
                result['reason'] = 'TAKE_PROFIT_1'
                return result
            
            if self.side == 'SELL' and current_price <= self.tp1_price:
                result['action'] = 'CLOSE_HALF'
                result['reason'] = 'TAKE_PROFIT_1'
                return result
            
            # Check TP2
            if self.side == 'BUY' and current_price >= self.tp2_price:
                result['action'] = 'CLOSE_ALL'
                result['reason'] = 'TAKE_PROFIT_2'
                return result
            
            if self.side == 'SELL' and current_price <= self.tp2_price:
                result['action'] = 'CLOSE_ALL'
                result['reason'] = 'TAKE_PROFIT_2'
                return result
            
            # Check trailing stop activation (spot uses percentage)
            if not self.trailing_stop_active and profit_percent >= self.trailing_activation_percent:
                self.trailing_stop_active = True
                self.trailing_stop_price = self.entry_price  # Move to breakeven
                result['action'] = 'UPDATE_STOP'
                result['reason'] = 'TRAILING_STOP_ACTIVATED'
                result['new_stop_price'] = self.entry_price
                logger.info(f"Trailing stop activated for {self.symbol} (SPOT), moved to breakeven")
                return result
        
        # Check timeout (no movement)
        time_since_update = datetime.now() - self.last_update
        if time_since_update.total_seconds() > self.timeout_minutes * 60:
            result['action'] = 'CLOSE_ALL'
            result['reason'] = 'TIMEOUT'
            return result
        
        return result


class RiskManager:
    """
    Risk Management system with automatic mode switching
    
    Automatically switches between SPOT and FUTURES trading based on account balance:
    - Balance < 500 USDT → SPOT mode (safer, no leverage)
    - Balance >= 500 USDT → FUTURES mode (with leverage, all strategies)
    """
    
    def __init__(self):
        self.trading_mode: TradingMode = TradingMode.SPOT
        self.current_balance: float = 0.0
        self.open_trades: Dict[str, TradeInfo] = {}
        
        # Loss tracking
        self.consecutive_losses = 0
        self.last_loss_time: Optional[datetime] = None
        self.is_paused = False
        self.pause_until: Optional[datetime] = None
        
        # Statistics
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.total_profit = 0.0
    
    def update_balance(self, balance: float):
        """Update balance and potentially switch trading mode"""
        old_mode = self.trading_mode
        self.current_balance = balance
        
        # Determine trading mode based on balance
        if balance >= BALANCE_THRESHOLD_USDT:
            self.trading_mode = TradingMode.FUTURES
        else:
            self.trading_mode = TradingMode.SPOT
        
        # Log mode change
        if old_mode != self.trading_mode:
            logger.warning(
                f"TRADING MODE CHANGED: {old_mode.value} → {self.trading_mode.value} | "
                f"Balance: {balance:.2f} USDT (threshold: {BALANCE_THRESHOLD_USDT} USDT)"
            )
    
    def get_mode_params(self) -> Dict:
        """Get current mode parameters"""
        if self.trading_mode == TradingMode.FUTURES:
            return {
                'mode': 'FUTURES',
                'position_size_percent': FUTURES_POSITION_SIZE_PERCENT,
                'leverage': FUTURES_LEVERAGE,
                'max_leverage': FUTURES_MAX_LEVERAGE,
                'stop_loss_percent': FUTURES_STOP_LOSS_PERCENT,
                'tp1_value': FUTURES_TAKE_PROFIT_1_USDT,
                'tp2_value': FUTURES_TAKE_PROFIT_2_USDT,
                'trailing_activation': FUTURES_TRAILING_STOP_ACTIVATION_USDT,
                'timeout_minutes': FUTURES_TIMEOUT_NO_MOVEMENT_MINUTES,
                'max_concurrent_trades': MAX_CONCURRENT_TRADES,
                'max_concurrent_coins': MAX_CONCURRENT_COINS,
                'max_loss_streak': MAX_LOSS_STREAK,
                'pause_hours': TRADING_PAUSE_HOURS,
                'allow_short': True
            }
        else:
            return {
                'mode': 'SPOT',
                'position_size_percent': SPOT_POSITION_SIZE_PERCENT,
                'leverage': SPOT_LEVERAGE,
                'max_leverage': SPOT_LEVERAGE,
                'stop_loss_percent': SPOT_STOP_LOSS_PERCENT,
                'tp1_percent': SPOT_TAKE_PROFIT_1_PERCENT,
                'tp2_percent': SPOT_TAKE_PROFIT_2_PERCENT,
                'trailing_activation_percent': SPOT_TRAILING_STOP_ACTIVATION_PERCENT,
                'timeout_minutes': SPOT_TIMEOUT_NO_MOVEMENT_MINUTES,
                'max_concurrent_trades': SPOT_MAX_CONCURRENT_TRADES,
                'max_concurrent_coins': SPOT_MAX_CONCURRENT_COINS,
                'max_loss_streak': SPOT_MAX_LOSS_STREAK,
                'pause_hours': SPOT_TRADING_PAUSE_HOURS,
                'allow_short': SPOT_ALLOW_SHORT
            }
    
    def can_open_trade(self, symbol: str, side: str) -> Tuple[bool, str]:
        """
        Check if a new trade can be opened
        
        Returns: (can_open, reason)
        """
        # Check if trading is paused
        if self.is_paused:
            if datetime.now() >= self.pause_until:
                self.is_paused = False
                self.pause_until = None
                logger.info("Trading pause ended, resuming operations")
            else:
                remaining = (self.pause_until - datetime.now()).total_seconds() / 60
                return False, f"Trading paused due to loss streak ({remaining:.0f} min remaining)"
        
        # Check consecutive losses
        params = self.get_mode_params()
        if self.consecutive_losses >= params['max_loss_streak']:
            return False, f"Consecutive loss limit reached ({self.consecutive_losses})"
        
        # Check concurrent trades limit
        if len(self.open_trades) >= params['max_concurrent_trades']:
            return False, f"Maximum concurrent trades reached ({len(self.open_trades)})"
        
        # Check concurrent coins limit
        coins_in_trades = set(trade.symbol for trade in self.open_trades.values())
        if symbol in coins_in_trades:
            return False, f"Already trading {symbol}"
        
        if len(coins_in_trades) >= params['max_concurrent_coins']:
            return False, f"Maximum concurrent coins reached ({len(coins_in_trades)})"
        
        # Check short selling in spot mode
        if self.trading_mode == TradingMode.SPOT and side == 'SELL' and not params['allow_short']:
            return False, "Short selling not allowed in SPOT mode"
        
        # Check minimum balance for position
        min_position_value = 5.0  # Minimum $5 position
        if self.current_balance < min_position_value:
            return False, f"Insufficient balance ({self.current_balance:.2f} USDT)"
        
        return True, "OK"
    
    def calculate_position_size(
        self,
        symbol: str,
        price: float,
        risk_percent: Optional[float] = None
    ) -> float:
        """
        Calculate position size based on current mode and risk parameters
        
        Args:
            symbol: Trading pair symbol
            price: Current price
            risk_percent: Optional custom risk percent (uses default if None)
        
        Returns:
            Quantity to trade
        """
        params = self.get_mode_params()
        
        if risk_percent is None:
            risk_percent = params['position_size_percent']
        
        # Calculate position value in USDT
        position_value = self.current_balance * (risk_percent / 100)
        
        # Apply leverage for futures
        if self.trading_mode == TradingMode.FUTURES:
            effective_value = position_value * params['leverage']
        else:
            effective_value = position_value
        
        # Calculate quantity
        quantity = effective_value / price
        
        # Round to appropriate precision
        if price < 1:
            quantity = round(quantity, 2)
        elif price < 100:
            quantity = round(quantity, 3)
        else:
            quantity = round(quantity, 4)
        
        return max(quantity, 0.001)  # Minimum quantity
    
    def open_trade(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        quantity: float
    ) -> Optional[TradeInfo]:
        """
        Open a new trade
        
        Returns TradeInfo if successful, None otherwise
        """
        # Validate
        can_open, reason = self.can_open_trade(symbol, side)
        if not can_open:
            logger.warning(f"Cannot open trade: {reason}")
            return None
        
        # Create trade
        trade = TradeInfo(
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            quantity=quantity,
            mode=self.trading_mode,
            timestamp=datetime.now()
        )
        
        # Store trade
        self.open_trades[symbol] = trade
        self.total_trades += 1
        
        logger.info(
            f"OPENED {self.trading_mode.value} TRADE: {side} {symbol} | "
            f"Qty: {quantity} @ {entry_price} | "
            f"SL: {trade.stop_loss_price:.4f} | "
            f"TP1: {trade.tp1_price:.4f} | "
            f"TP2: {trade.tp2_price:.4f}"
        )
        
        return trade
    
    def close_trade(self, symbol: str, close_price: float, reason: str):
        """Close a trade and update statistics"""
        if symbol not in self.open_trades:
            logger.warning(f"Attempted to close non-existent trade: {symbol}")
            return
        
        trade = self.open_trades[symbol]
        
        # Calculate P&L
        if trade.side == 'BUY':
            pnl = (close_price - trade.entry_price) * trade.quantity
        else:
            pnl = (trade.entry_price - close_price) * trade.quantity
        
        # Update statistics
        self.total_profit += pnl
        if pnl > 0:
            self.winning_trades += 1
            self.consecutive_losses = 0  # Reset loss streak
        else:
            self.losing_trades += 1
            self.consecutive_losses += 1
            self.last_loss_time = datetime.now()
            
            # Check if need to pause
            params = self.get_mode_params()
            if self.consecutive_losses >= params['max_loss_streak']:
                self.is_paused = True
                self.pause_until = datetime.now() + timedelta(hours=params['pause_hours'])
                logger.error(
                    f"TRADING PAUSED: {self.consecutive_losses} consecutive losses | "
                    f"Pause duration: {params['pause_hours']} hours"
                )
        
        # Remove trade
        del self.open_trades[symbol]
        
        logger.info(
            f"CLOSED TRADE: {symbol} | "
            f"P&L: {pnl:.2f} USDT | "
            f"Reason: {reason} | "
            f"Consecutive losses: {self.consecutive_losses}"
        )
    
    def update_trades(self, prices: Dict[str, float]) -> Dict[str, Dict]:
        """
        Update all open trades with current prices
        
        Returns dict of actions needed for each symbol
        """
        actions = {}
        
        for symbol, trade in list(self.open_trades.items()):
            if symbol in prices:
                result = trade.update_price(prices[symbol])
                if result['action']:
                    actions[symbol] = result
                    
                    if result['action'] == 'CLOSE_ALL':
                        self.close_trade(symbol, prices[symbol], result['reason'])
                    elif result['action'] == 'UPDATE_STOP':
                        trade.stop_loss_price = result.get('new_stop_price', trade.stop_loss_price)
        
        return actions
    
    def get_statistics(self) -> Dict:
        """Get trading statistics"""
        win_rate = (self.winning_trades / self.total_trades * 100) if self.total_trades > 0 else 0
        
        return {
            'mode': self.trading_mode.value,
            'balance': self.current_balance,
            'open_trades': len(self.open_trades),
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'losing_trades': self.losing_trades,
            'win_rate': win_rate,
            'total_profit': self.total_profit,
            'consecutive_losses': self.consecutive_losses,
            'is_paused': self.is_paused
        }
    
    def force_close_all(self, prices: Dict[str, float], reason: str = "MANUAL"):
        """Force close all open trades"""
        for symbol in list(self.open_trades.keys()):
            if symbol in prices:
                self.close_trade(symbol, prices[symbol], reason)
            else:
                logger.warning(f"Cannot close {symbol}: price not available")

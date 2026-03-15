"""
Short Trading Strategies
Implements 3 strategies for short positions:
1. Breakdown below support
2. Rejection from resistance
3. Overbought scalping
"""

import logging
import numpy as np
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class ShortStrategies:
    """
    Implements all short trading strategies with entry conditions and trade management.
    """
    
    def __init__(self, client, config):
        self.client = client
        self.config = config
    
    def check_breakdown_strategy(self, symbol: str, ohlcv: List[Dict]) -> Optional[Dict]:
        """
        Агрессивная стратегия пробоя поддержки для скальпинга SHORT.
        Минимум фильтров для максимального количества сделок.
        
        Conditions:
        1. Price breaks below local low (last 5 candles)
        2. EMA 9 < EMA 21 (minimal trend confirmation)
        """
        try:
            if len(ohlcv) < 20:
                return None
            
            prices = np.array([c['close'] for c in ohlcv])
            lows = np.array([c['low'] for c in ohlcv])
            
            # Calculate indicators
            ema9 = self._calculate_ema(prices, 9)
            ema21 = self._calculate_ema(prices, 21)
            
            current_price = prices[-1]
            
            # Find local min (last 5 candles)
            lookback = 5
            local_min = np.min(lows[-lookback-1:-1])
            
            # Check conditions - максимально упрощенные
            breakdown = current_price < local_min
            trend_confirmed = ema9[-1] < ema21[-1]
            
            if breakdown and trend_confirmed:
                logger.info(f"[AGGRESSIVE SHORT] {symbol}: Breakdown scalp at {current_price:.4f} (local min: {local_min:.4f})")
                
                position_size = self._calculate_position_size(symbol, current_price)
                
                return {
                    'action': 'SELL',
                    'symbol': symbol,
                    'entry_price': current_price,
                    'position_size': position_size,
                    'stop_loss': current_price * (1 + self.config.STOP_LOSS_PERCENT / 100),
                    'take_profit_1': current_price - self.config.TAKE_PROFIT_1_USDT,
                    'take_profit_2': current_price - self.config.TAKE_PROFIT_2_USDT,
                    'strategy': 'aggressive_breakdown',
                    'reason': f'Aggressive breakdown below {local_min:.4f}'
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error in aggressive breakdown strategy for {symbol}: {e}")
            return None
    
    def check_resistance_rejection_strategy(self, symbol: str, ohlcv: List[Dict]) -> Optional[Dict]:
        """
        Агрессивный отскок от сопротивления для скальпинга SHORT.
        Минимум фильтров для максимального количества сделок.
        
        Conditions:
        1. Price touches upper Bollinger Band
        2. Price starts moving down (current < high)
        """
        try:
            if len(ohlcv) < 20:
                return None
            
            prices = np.array([c['close'] for c in ohlcv])
            highs = np.array([c['high'] for c in ohlcv])
            
            # Calculate Bollinger Bands
            bb_upper, bb_middle, bb_lower = self._calculate_bollinger_bands(prices)
            
            current_price = prices[-1]
            current_high = highs[-1]
            
            # Check if price touched upper band and rejecting
            touched_upper = current_high >= bb_upper[-1] * 0.998  # 0.2% tolerance
            rejecting = current_price < current_high
            
            if touched_upper and rejecting:
                logger.info(f"[AGGRESSIVE SHORT] {symbol}: Resistance rejection scalp at {current_price:.4f} (BB upper: {bb_upper[-1]:.4f})")
                
                position_size = self._calculate_position_size(symbol, current_price)
                
                return {
                    'action': 'SELL',
                    'symbol': symbol,
                    'entry_price': current_price,
                    'position_size': position_size,
                    'stop_loss': current_price * (1 + self.config.STOP_LOSS_PERCENT / 100),
                    'take_profit_1': current_price - self.config.TAKE_PROFIT_1_USDT,
                    'take_profit_2': current_price - self.config.TAKE_PROFIT_2_USDT,
                    'strategy': 'aggressive_rejection',
                    'reason': f'Rejection from BB upper at {bb_upper[-1]:.4f}'
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error in aggressive rejection strategy for {symbol}: {e}")
            return None
    
    def check_overbought_scalping_strategy(self, symbol: str, ohlcv: List[Dict]) -> Optional[Dict]:
        """
        Агрессивный скальпинг перекупленности для SHORT.
        Минимум фильтров для максимального количества сделок.
        
        Conditions:
        1. Price near lower Bollinger Band (momentum down)
        2. Bands expanding (volatility increasing)
        """
        try:
            if len(ohlcv) < 20:
                return None
            
            prices = np.array([c['close'] for c in ohlcv])
            
            # Calculate Bollinger Bands
            bb_upper, bb_middle, bb_lower = self._calculate_bollinger_bands(prices)
            
            current_price = prices[-1]
            
            # Check if bands are expanding (volatility increasing)
            current_bb_width = (bb_upper[-1] - bb_lower[-1]) / bb_middle[-1]
            avg_bb_width = np.mean([(bb_upper[i] - bb_lower[i]) / bb_middle[i] 
                                   for i in range(-20, -1)])
            bands_expanding = current_bb_width > avg_bb_width * 0.9
            
            # Check if price has downward momentum (below middle band and near lower)
            has_momentum = current_price < bb_middle[-1] and current_price <= bb_lower[-1] * 1.02
            
            if bands_expanding and has_momentum:
                logger.info(f"[AGGRESSIVE SHORT] {symbol}: Overbought scalp at {current_price:.4f} (BB expanding down)")
                
                position_size = self._calculate_position_size(symbol, current_price)
                
                return {
                    'action': 'SELL',
                    'symbol': symbol,
                    'entry_price': current_price,
                    'position_size': position_size,
                    'stop_loss': current_price * (1 + self.config.STOP_LOSS_PERCENT / 100),
                    'take_profit_1': current_price - self.config.TAKE_PROFIT_1_USDT,
                    'take_profit_2': current_price - self.config.TAKE_PROFIT_2_USDT,
                    'strategy': 'aggressive_overbought',
                    'reason': f'Volatility scalp with expanding BB down'
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error in aggressive overbought strategy for {symbol}: {e}")
            return None
    
    def manage_position(self, position: Dict, current_price: float) -> Dict:
        """
        Manage open short position:
        - Check stop loss
        - Check take profit levels
        - Implement trailing stop
        - Check timeout
        """
        entry_price = position['entry_price']
        current_profit_usdt = (entry_price - current_price) * position['quantity']
        
        actions = {
            'close': False,
            'close_partial': False,
            'adjust_stop_loss': False,
            'new_stop_loss': None,
            'reason': ''
        }
        
        # Check stop loss
        if current_price >= position['stop_loss']:
            actions['close'] = True
            actions['reason'] = 'Stop loss hit'
            return actions
        
        # Check take profit 1 (2 USDT)
        if current_profit_usdt >= self.config.TAKE_PROFIT_1_USDT and not position.get('tp1_hit', False):
            actions['close_partial'] = True
            actions['close_percent'] = 50
            actions['reason'] = 'Take profit 1 reached (2 USDT)'
            position['tp1_hit'] = True
            return actions
        
        # Check take profit 2 (3-4 USDT)
        if current_profit_usdt >= self.config.TAKE_PROFIT_2_USDT:
            actions['close'] = True
            actions['reason'] = 'Take profit 2 reached (3-4 USDT)'
            return actions
        
        # Trailing stop: move to breakeven after +1.5 USDT profit
        if current_profit_usdt >= self.config.TRAILING_STOP_ACTIVATION_USDT:
            if position['stop_loss'] > entry_price:
                actions['adjust_stop_loss'] = True
                actions['new_stop_loss'] = entry_price * 0.999  # Slightly below entry
                actions['reason'] = 'Trailing stop activated - moved to breakeven'
        
        # Check timeout (no movement for 7 minutes)
        if self._check_timeout(position, current_price):
            actions['close'] = True
            actions['reason'] = 'Timeout - no price movement'
        
        return actions
    
    def _calculate_position_size(self, symbol: str, entry_price: float) -> float:
        """Calculate position size based on risk parameters"""
        balance = 1000  # USDT
        position_value = balance * self.config.POSITION_SIZE_PERCENT / 100
        quantity = position_value / entry_price
        return quantity
    
    def _check_timeout(self, position: Dict, current_price: float) -> bool:
        """Check if position has exceeded timeout without movement"""
        import time
        
        entry_time = position.get('entry_time', time.time())
        elapsed_minutes = (time.time() - entry_time) / 60
        
        price_change = abs(current_price - position['entry_price']) / position['entry_price']
        
        if elapsed_minutes > self.config.TIMEOUT_NO_MOVEMENT_MINUTES and price_change < 0.001:
            return True
        
        return False
    
    # Helper methods
    def _calculate_ema(self, prices: np.ndarray, period: int) -> np.ndarray:
        """Calculate Exponential Moving Average"""
        ema = np.zeros_like(prices)
        ema[0] = prices[0]
        multiplier = 2 / (period + 1)
        
        for i in range(1, len(prices)):
            ema[i] = (prices[i] - ema[i-1]) * multiplier + ema[i-1]
        
        return ema
    
    def _calculate_rsi(self, prices: np.ndarray, period: int) -> np.ndarray:
        """Calculate Relative Strength Index"""
        deltas = np.diff(prices)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gains = np.convolve(gains, np.ones(period)/period, mode='valid')
        avg_losses = np.convolve(losses, np.ones(period)/period, mode='valid')
        
        rs = avg_gains / (avg_losses + np.float64(1e-10))
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    def _calculate_bollinger_bands(self, prices: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Calculate Bollinger Bands"""
        middle = np.convolve(prices, np.ones(self.config.BOLLINGER_PERIOD)/self.config.BOLLINGER_PERIOD, mode='valid')
        
        std = np.zeros_like(middle)
        for i in range(len(middle)):
            window = prices[i:i+self.config.BOLLINGER_PERIOD]
            std[i] = np.std(window)
        
        upper = middle + self.config.BOLLINGER_STD * std
        lower = middle - self.config.BOLLINGER_STD * std
        
        return upper, middle, lower
    
    def _calculate_stochastic(self, highs: np.ndarray, lows: np.ndarray, 
                             closes: np.ndarray, k_period: int = 14, 
                             d_period: int = 3) -> Tuple[np.ndarray, np.ndarray]:
        """Calculate Stochastic Oscillator"""
        lowest_low = np.minimum.accumulate(lows)
        highest_high = np.maximum.accumulate(highs)
        
        # Lookback period
        k = np.zeros_like(closes, dtype=float)
        for i in range(k_period, len(closes)):
            lowest = np.min(lows[i-k_period+1:i+1])
            highest = np.max(highs[i-k_period+1:i+1])
            k[i] = 100 * (closes[i] - lowest) / (highest - lowest + 1e-10)
        
        # %D is SMA of %K
        d = np.convolve(k, np.ones(d_period)/d_period, mode='same')
        
        return k, d

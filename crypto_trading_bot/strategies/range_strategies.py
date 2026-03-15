"""
Range Trading Strategies
Implements 3 strategies for range-bound markets:
1. Range trading (buy low, sell high)
2. Mean reversion
3. Pattern scalping
"""

import logging
import numpy as np
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class RangeStrategies:
    """
    Implements all range trading strategies with entry conditions and trade management.
    """
    
    def __init__(self, client, config):
        self.client = client
        self.config = config
    
    def check_range_trading_strategy(self, symbol: str, ohlcv: List[Dict]) -> Optional[Dict]:
        """
        Агрессивная стратегия для RANGE рынка.
        Минимум фильтров для максимального количества сделок.
        
        Conditions for BUY:
        - Price at lower Bollinger Band
        
        Conditions for SELL:
        - Price at upper Bollinger Band
        """
        try:
            if len(ohlcv) < 20:
                return None
            
            prices = np.array([c['close'] for c in ohlcv])
            
            # Calculate Bollinger Bands
            bb_upper, bb_middle, bb_lower = self._calculate_bollinger_bands(prices)
            
            current_price = prices[-1]
            
            # Check for BUY signal - price at lower band
            if current_price <= bb_lower[-1] * 1.002:
                logger.info(f"[AGGRESSIVE RANGE BUY] {symbol}: Range buy at {current_price:.4f} (BB lower: {bb_lower[-1]:.4f})")
                position_size = self._calculate_position_size(symbol, current_price)
                
                return {
                    'action': 'BUY',
                    'symbol': symbol,
                    'entry_price': current_price,
                    'position_size': position_size,
                    'stop_loss': current_price * (1 - self.config.STOP_LOSS_PERCENT / 100),
                    'take_profit_1': current_price + self.config.TAKE_PROFIT_1_USDT,
                    'take_profit_2': current_price + self.config.TAKE_PROFIT_2_USDT,
                    'strategy': 'aggressive_range_buy',
                    'reason': f'Range buy at BB lower {bb_lower[-1]:.4f}'
                }
            
            # Check for SELL signal - price at upper band
            if current_price >= bb_upper[-1] * 0.998:
                logger.info(f"[AGGRESSIVE RANGE SELL] {symbol}: Range sell at {current_price:.4f} (BB upper: {bb_upper[-1]:.4f})")
                position_size = self._calculate_position_size(symbol, current_price)
                
                return {
                    'action': 'SELL',
                    'symbol': symbol,
                    'entry_price': current_price,
                    'position_size': position_size,
                    'stop_loss': current_price * (1 + self.config.STOP_LOSS_PERCENT / 100),
                    'take_profit_1': current_price - self.config.TAKE_PROFIT_1_USDT,
                    'take_profit_2': current_price - self.config.TAKE_PROFIT_2_USDT,
                    'strategy': 'aggressive_range_sell',
                    'reason': f'Range sell at BB upper {bb_upper[-1]:.4f}'
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error in aggressive range strategy for {symbol}: {e}")
            return None
    
    def check_mean_reversion_strategy(self, symbol: str, ohlcv: List[Dict]) -> Optional[Dict]:
        """
        Агрессивная стратегия возврата к среднему.
        Минимум фильтров для максимального количества сделок.
        
        Conditions for BUY:
        - Price below middle Bollinger Band
        
        Conditions for SELL:
        - Price above middle Bollinger Band
        """
        try:
            if len(ohlcv) < 20:
                return None
            
            prices = np.array([c['close'] for c in ohlcv])
            
            # Calculate Bollinger Bands
            bb_upper, bb_middle, bb_lower = self._calculate_bollinger_bands(prices)
            
            current_price = prices[-1]
            
            # Check for BUY signal - price significantly below middle
            if current_price < bb_middle[-1] * 0.995:
                logger.info(f"[AGGRESSIVE RANGE BUY] {symbol}: Mean reversion buy at {current_price:.4f}")
                position_size = self._calculate_position_size(symbol, current_price)
                
                return {
                    'action': 'BUY',
                    'symbol': symbol,
                    'entry_price': current_price,
                    'position_size': position_size,
                    'stop_loss': current_price * (1 - self.config.STOP_LOSS_PERCENT / 100),
                    'take_profit_1': current_price + self.config.TAKE_PROFIT_1_USDT,
                    'take_profit_2': current_price + self.config.TAKE_PROFIT_2_USDT,
                    'strategy': 'aggressive_mean_reversion_buy',
                    'reason': f'Mean reversion buy below middle BB'
                }
            
            # Check for SELL signal - price significantly above middle
            if current_price > bb_middle[-1] * 1.005:
                logger.info(f"[AGGRESSIVE RANGE SELL] {symbol}: Mean reversion sell at {current_price:.4f}")
                position_size = self._calculate_position_size(symbol, current_price)
                
                return {
                    'action': 'SELL',
                    'symbol': symbol,
                    'entry_price': current_price,
                    'position_size': position_size,
                    'stop_loss': current_price * (1 + self.config.STOP_LOSS_PERCENT / 100),
                    'take_profit_1': current_price - self.config.TAKE_PROFIT_1_USDT,
                    'take_profit_2': current_price - self.config.TAKE_PROFIT_2_USDT,
                    'strategy': 'aggressive_mean_reversion_sell',
                    'reason': f'Mean reversion sell above middle BB'
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error in aggressive mean reversion strategy for {symbol}: {e}")
            return None
    
    def check_pattern_scalping_strategy(self, symbol: str, ohlcv: List[Dict]) -> Optional[Dict]:
        """
        Агрессивный скальпинг паттернов для RANGE рынка.
        Минимум фильтров для максимального количества сделок.
        
        Conditions for BUY:
        - Price moved down significantly (potential reversal)
        
        Conditions for SELL:
        - Price moved up significantly (potential reversal)
        """
        try:
            if len(ohlcv) < 20:
                return None
            
            prices = np.array([c['close'] for c in ohlcv])
            
            current_price = prices[-1]
            avg_price = np.mean(prices[-10:])
            
            # Check for BUY signal - price dropped below average (potential bounce)
            if current_price < avg_price * 0.995:
                logger.info(f"[AGGRESSIVE RANGE BUY] {symbol}: Pattern scalp buy at {current_price:.4f}")
                position_size = self._calculate_position_size(symbol, current_price)
                
                return {
                    'action': 'BUY',
                    'symbol': symbol,
                    'entry_price': current_price,
                    'position_size': position_size,
                    'stop_loss': current_price * (1 - self.config.STOP_LOSS_PERCENT / 100),
                    'take_profit_1': current_price + self.config.TAKE_PROFIT_1_USDT,
                    'take_profit_2': current_price + self.config.TAKE_PROFIT_2_USDT,
                    'strategy': 'aggressive_pattern_buy',
                    'reason': 'Quick bounce scalp'
                }
            
            # Check for SELL signal - price rose above average (potential drop)
            if current_price > avg_price * 1.005:
                logger.info(f"[AGGRESSIVE RANGE SELL] {symbol}: Pattern scalp sell at {current_price:.4f}")
                position_size = self._calculate_position_size(symbol, current_price)
                
                return {
                    'action': 'SELL',
                    'symbol': symbol,
                    'entry_price': current_price,
                    'position_size': position_size,
                    'stop_loss': current_price * (1 + self.config.STOP_LOSS_PERCENT / 100),
                    'take_profit_1': current_price - self.config.TAKE_PROFIT_1_USDT,
                    'take_profit_2': current_price - self.config.TAKE_PROFIT_2_USDT,
                    'strategy': 'aggressive_pattern_sell',
                    'reason': 'Quick drop scalp'
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error in aggressive pattern strategy for {symbol}: {e}")
            return None
    
    def manage_position(self, position: Dict, current_price: float, direction: str) -> Dict:
        """
        Manage open range position.
        Similar to long/short management but with longer timeout (10 minutes).
        """
        entry_price = position['entry_price']
        
        if direction == 'LONG':
            current_profit_usdt = (current_price - entry_price) * position['quantity']
        else:
            current_profit_usdt = (entry_price - current_price) * position['quantity']
        
        actions = {
            'close': False,
            'close_partial': False,
            'adjust_stop_loss': False,
            'new_stop_loss': None,
            'reason': ''
        }
        
        # Check stop loss
        if direction == 'LONG' and current_price <= position['stop_loss']:
            actions['close'] = True
            actions['reason'] = 'Stop loss hit'
            return actions
        elif direction == 'SHORT' and current_price >= position['stop_loss']:
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
            if direction == 'LONG' and position['stop_loss'] < entry_price:
                actions['adjust_stop_loss'] = True
                actions['new_stop_loss'] = entry_price * 1.001
                actions['reason'] = 'Trailing stop activated - moved to breakeven'
            elif direction == 'SHORT' and position['stop_loss'] > entry_price:
                actions['adjust_stop_loss'] = True
                actions['new_stop_loss'] = entry_price * 0.999
                actions['reason'] = 'Trailing stop activated - moved to breakeven'
        
        # Check timeout (10 minutes for range trading)
        if self._check_timeout(position, current_price):
            actions['close'] = True
            actions['reason'] = 'Timeout - no price movement'
        
        return actions
    
    def _detect_bullish_pattern(self, opens: np.ndarray, highs: np.ndarray, 
                                lows: np.ndarray, closes: np.ndarray) -> bool:
        """Detect bullish reversal candlestick patterns"""
        # Hammer pattern
        o, h, l, c = opens[-1], highs[-1], lows[-1], closes[-1]
        body = abs(c - o)
        lower_shadow = min(o, c) - l
        upper_shadow = h - max(o, c)
        
        is_hammer = (lower_shadow > body * 2 and 
                    upper_shadow < body * 0.5 and
                    c > o)  # Green candle
        
        # Bullish Engulfing
        prev_o, prev_c = opens[-2], closes[-2]
        is_engulfing = (c > o and prev_c < prev_o and 
                       o < prev_c and c > prev_o)
        
        # Morning Star (3-candle pattern)
        if len(closes) >= 3:
            is_morning_star = (closes[-3] < opens[-3] and  # First candle red
                              abs(closes[-2] - opens[-2]) < (opens[-2] - closes[-2]) * 0.3 and  # Small middle
                              closes[-1] > opens[-1] and  # Third candle green
                              closes[-1] > (opens[-3] + closes[-3]) / 2)  # Closes into first candle
        else:
            is_morning_star = False
        
        return is_hammer or is_engulfing or is_morning_star
    
    def _detect_bearish_pattern(self, opens: np.ndarray, highs: np.ndarray, 
                                lows: np.ndarray, closes: np.ndarray) -> bool:
        """Detect bearish reversal candlestick patterns"""
        o, h, l, c = opens[-1], highs[-1], lows[-1], closes[-1]
        body = abs(c - o)
        lower_shadow = min(o, c) - l
        upper_shadow = h - max(o, c)
        
        # Shooting Star
        is_shooting_star = (upper_shadow > body * 2 and 
                           lower_shadow < body * 0.5 and
                           c < o)  # Red candle
        
        # Bearish Engulfing
        prev_o, prev_c = opens[-2], closes[-2]
        is_engulfing = (c < o and prev_c > prev_o and 
                       o > prev_c and c < prev_o)
        
        # Evening Star (3-candle pattern)
        if len(closes) >= 3:
            is_evening_star = (closes[-3] > opens[-3] and  # First candle green
                              abs(closes[-2] - opens[-2]) < (closes[-2] - opens[-2]) * 0.3 and  # Small middle
                              closes[-1] < opens[-1] and  # Third candle red
                              closes[-1] < (opens[-3] + closes[-3]) / 2)  # Closes into first candle
        else:
            is_evening_star = False
        
        return is_shooting_star or is_engulfing or is_evening_star
    
    def _calculate_position_size(self, symbol: str, entry_price: float) -> float:
        """Calculate position size based on risk parameters"""
        balance = 1000  # USDT
        
        # Determine correct attribute based on trading mode
        if hasattr(self.config, 'trading_mode') and self.config.trading_mode == 'FUTURES':
            position_size_percent = getattr(self.config, 'FUTURES_POSITION_SIZE_PERCENT', 2.5)
        else:
            position_size_percent = getattr(self.config, 'SPOT_POSITION_SIZE_PERCENT', 12.0)
        
        position_value = balance * position_size_percent / 100
        quantity = position_value / entry_price
        return quantity
    
    def _check_timeout(self, position: Dict, current_price: float) -> bool:
        """Check if position has exceeded timeout without movement"""
        import time
        
        entry_time = position.get('entry_time', time.time())
        elapsed_minutes = (time.time() - entry_time) / 60
        
        price_change = abs(current_price - position['entry_price']) / position['entry_price']
        
        # 10 minutes timeout for range trading
        if elapsed_minutes > 10 and price_change < 0.001:
            return True
        
        return False
    
    # Helper methods
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
    
    def _calculate_z_score(self, prices: np.ndarray, period: int = 50) -> np.ndarray:
        """Calculate Z-Score (standardized deviation from mean)"""
        z_scores = np.zeros_like(prices, dtype=float)
        
        for i in range(period, len(prices)):
            window = prices[i-period:i]
            mean = np.mean(window)
            std = np.std(window)
            z_scores[i] = (prices[i] - mean) / (std + 1e-10)
        
        return z_scores
    
    def _calculate_stochastic(self, highs: np.ndarray, lows: np.ndarray, 
                             closes: np.ndarray, k_period: int = 14, 
                             d_period: int = 3) -> Tuple[np.ndarray, np.ndarray]:
        """Calculate Stochastic Oscillator"""
        k = np.zeros_like(closes, dtype=float)
        
        for i in range(k_period, len(closes)):
            lowest = np.min(lows[i-k_period+1:i+1])
            highest = np.max(highs[i-k_period+1:i+1])
            k[i] = 100 * (closes[i] - lowest) / (highest - lowest + 1e-10)
        
        d = np.convolve(k, np.ones(d_period)/d_period, mode='same')
        
        return k, d

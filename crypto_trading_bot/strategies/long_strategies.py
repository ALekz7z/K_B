"""
Long Trading Strategies
Implements 3 strategies for long positions:
1. Breakout above resistance
2. Bounce from support
3. Volatility scalping
"""

import logging
import numpy as np
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class LongStrategies:
    """
    Implements all long trading strategies with entry conditions and trade management.
    """
    
    def __init__(self, client, config):
        self.client = client
        self.config = config
    
    def check_breakout_strategy(self, symbol: str, ohlcv: List[Dict]) -> Optional[Dict]:
        """
        Strategy 1: Breakout above resistance
        
        Conditions (ALL must be true):
        1. Price breaks above key resistance level (previous local high)
        2. Volume on breakout > 150% of average volume (last 20 candles)
        3. EMA 9 > EMA 21 (trend confirmation)
        4. RSI <= 70 (not overbought)
        """
        try:
            if len(ohlcv) < 50:
                return None
            
            prices = np.array([c['close'] for c in ohlcv])
            volumes = np.array([c['volume'] for c in ohlcv])
            highs = np.array([c['high'] for c in ohlcv])
            
            # Calculate indicators
            ema9 = self._calculate_ema(prices, 9)
            ema21 = self._calculate_ema(prices, 21)
            rsi = self._calculate_rsi(prices, self.config.RSI_PERIOD)
            
            current_price = prices[-1]
            current_volume = volumes[-1]
            avg_volume = np.mean(volumes[-20:-1])
            
            # Find resistance level (previous local high)
            resistance = np.max(highs[-20:-1])
            
            # Check conditions
            breakout = current_price > resistance
            volume_confirmed = current_volume > avg_volume * 1.5
            trend_confirmed = ema9[-1] > ema21[-1]
            rsi_ok = rsi[-1] <= 70
            
            if breakout and volume_confirmed and trend_confirmed and rsi_ok:
                logger.info(f"Breakout strategy triggered for {symbol}")
                
                # Calculate position size
                position_size = self._calculate_position_size(symbol, current_price)
                
                return {
                    'action': 'BUY',
                    'symbol': symbol,
                    'entry_price': current_price,
                    'position_size': position_size,
                    'stop_loss': current_price * (1 - self.config.STOP_LOSS_PERCENT / 100),
                    'take_profit_1': current_price + self.config.TAKE_PROFIT_1_USDT,
                    'take_profit_2': current_price + self.config.TAKE_PROFIT_2_USDT,
                    'strategy': 'breakout',
                    'reason': f'Breakout above {resistance:.4f} with volume confirmation'
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error in breakout strategy: {e}")
            return None
    
    def check_support_bounce_strategy(self, symbol: str, ohlcv: List[Dict]) -> Optional[Dict]:
        """
        Strategy 2: Bounce from support
        
        Conditions (ALL must be true):
        1. Price bounces from key support (previous local low or Fibonacci 61.8%)
        2. RSI between 25 and 35
        3. Volume on bounce > 130% of average
        4. Bullish candle forms (green with lower shadow)
        """
        try:
            if len(ohlcv) < 50:
                return None
            
            prices = np.array([c['close'] for c in ohlcv])
            volumes = np.array([c['volume'] for c in ohlcv])
            lows = np.array([c['low'] for c in ohlcv])
            highs = np.array([c['high'] for c in ohlcv])
            opens = np.array([c['open'] for c in ohlcv])
            
            # Calculate RSI
            rsi = self._calculate_rsi(prices, self.config.RSI_PERIOD)
            
            current_price = prices[-1]
            current_volume = volumes[-1]
            avg_volume = np.mean(volumes[-20:-1])
            
            # Find support level (previous local low)
            support = np.min(lows[-20:-1])
            
            # Calculate Fibonacci levels from recent swing
            recent_high = np.max(highs[-50:-1])
            recent_low = np.min(lows[-50:-1])
            fib_618 = recent_high - (recent_high - recent_low) * 0.618
            
            # Use the higher of the two support levels
            key_support = max(support, fib_618)
            
            # Check if price bounced from support
            price_near_support = abs(current_price - key_support) / key_support < 0.01
            prev_low = lows[-2]
            bounce = current_price > prev_low and prev_low <= key_support * 1.005
            
            # Check RSI condition
            rsi_ok = 25 < rsi[-1] < 35
            
            # Check volume condition
            volume_confirmed = current_volume > avg_volume * 1.3
            
            # Check for bullish candle (green with lower shadow)
            current_open = opens[-1]
            current_close = prices[-1]
            current_low = lows[-1]
            is_bullish = current_close > current_open
            has_lower_shadow = (current_open - current_low) > (current_close - current_open) * 0.5
            
            if bounce and rsi_ok and volume_confirmed and is_bullish and has_lower_shadow:
                logger.info(f"Support bounce strategy triggered for {symbol}")
                
                position_size = self._calculate_position_size(symbol, current_price)
                
                return {
                    'action': 'BUY',
                    'symbol': symbol,
                    'entry_price': current_price,
                    'position_size': position_size,
                    'stop_loss': key_support * (1 - 0.015),  # 1.5% below support
                    'take_profit_1': current_price + self.config.TAKE_PROFIT_1_USDT,
                    'take_profit_2': current_price + self.config.TAKE_PROFIT_2_USDT,
                    'strategy': 'support_bounce',
                    'reason': f'Bounce from support at {key_support:.4f}'
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error in support bounce strategy: {e}")
            return None
    
    def check_volatility_scalping_strategy(self, symbol: str, ohlcv: List[Dict]) -> Optional[Dict]:
        """
        Strategy 3: Volatility scalping
        
        Conditions (ALL must be true):
        1. Price touches or near lower Bollinger Band
        2. Bollinger Bands compressed (width < average of last 50 periods)
        3. Volume starting to increase (> 120% of average)
        4. Previous 3 candles were red (bearish)
        """
        try:
            if len(ohlcv) < 100:
                return None
            
            prices = np.array([c['close'] for c in ohlcv])
            volumes = np.array([c['volume'] for c in ohlcv])
            opens = np.array([c['open'] for c in ohlcv])
            
            # Calculate Bollinger Bands
            bb_upper, bb_middle, bb_lower = self._calculate_bollinger_bands(prices)
            
            current_price = prices[-1]
            current_volume = volumes[-1]
            avg_volume = np.mean(volumes[-20:-1])
            
            # Check if bands are compressed
            current_bb_width = (bb_upper[-1] - bb_lower[-1]) / bb_middle[-1]
            avg_bb_width = np.mean([(bb_upper[i] - bb_lower[i]) / bb_middle[i] 
                                   for i in range(-51, -1)])
            bands_compressed = current_bb_width < avg_bb_width
            
            # Check if price at lower band
            at_lower_band = current_price <= bb_lower[-1] * 1.002  # Within 0.2%
            
            # Check volume increase
            volume_increasing = current_volume > avg_volume * 1.2
            
            # Check previous 3 candles were red
            prev_3_red = all(opens[i] > prices[i] for i in range(-4, -1))
            
            if at_lower_band and bands_compressed and volume_increasing and prev_3_red:
                logger.info(f"Volatility scalping strategy triggered for {symbol}")
                
                position_size = self._calculate_position_size(symbol, current_price)
                
                return {
                    'action': 'BUY',
                    'symbol': symbol,
                    'entry_price': current_price,
                    'position_size': position_size,
                    'stop_loss': current_price * (1 - 0.01),  # 1% below entry
                    'take_profit_1': current_price + self.config.TAKE_PROFIT_1_USDT,
                    'take_profit_2': current_price + self.config.TAKE_PROFIT_2_USDT,
                    'strategy': 'volatility_scalp',
                    'reason': f'Price at lower BB ({bb_lower[-1]:.4f}) with compression'
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error in volatility scalping strategy: {e}")
            return None
    
    def manage_position(self, position: Dict, current_price: float) -> Dict:
        """
        Manage open long position:
        - Check stop loss
        - Check take profit levels
        - Implement trailing stop
        - Check timeout
        """
        entry_price = position['entry_price']
        current_profit_usdt = (current_price - entry_price) * position['quantity']
        
        actions = {
            'close': False,
            'close_partial': False,
            'adjust_stop_loss': False,
            'new_stop_loss': None,
            'reason': ''
        }
        
        # Check stop loss
        if current_price <= position['stop_loss']:
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
            if position['stop_loss'] < entry_price:
                actions['adjust_stop_loss'] = True
                actions['new_stop_loss'] = entry_price * 1.001  # Slightly above entry
                actions['reason'] = 'Trailing stop activated - moved to breakeven'
        
        # Check timeout (no movement for 7 minutes)
        if self._check_timeout(position, current_price):
            actions['close'] = True
            actions['reason'] = 'Timeout - no price movement'
        
        return actions
    
    def _calculate_position_size(self, symbol: str, entry_price: float) -> float:
        """Calculate position size based on risk parameters"""
        # Get account balance (placeholder - would call API in production)
        balance = 1000  # USDT
        
        # Position size = 2-3% of deposit
        position_value = balance * self.config.POSITION_SIZE_PERCENT / 100
        
        # Calculate quantity
        quantity = position_value / entry_price
        
        return quantity
    
    def _check_timeout(self, position: Dict, current_price: float) -> bool:
        """Check if position has exceeded timeout without movement"""
        import time
        
        entry_time = position.get('entry_time', time.time())
        elapsed_minutes = (time.time() - entry_time) / 60
        
        # Check if price moved less than 0.1%
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
        
        rs = avg_gains / (avg_losses + 1e-10)
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

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
        Strategy 1: Breakdown below support
        
        Conditions (ALL must be true):
        1. Price breaks below key support level (previous local low)
        2. Volume on breakdown > 150% of average volume (last 20 candles)
        3. EMA 9 < EMA 21 (trend confirmation)
        4. RSI >= 30 (not oversold)
        """
        try:
            if len(ohlcv) < 50:
                logger.debug(f"[{symbol}] Breakdown: Insufficient data ({len(ohlcv)} < 50)")
                return None
            
            prices = np.array([c['close'] for c in ohlcv])
            volumes = np.array([c['volume'] for c in ohlcv])
            lows = np.array([c['low'] for c in ohlcv])
            
            # Calculate indicators
            ema9 = self._calculate_ema(prices, 9)
            ema21 = self._calculate_ema(prices, 21)
            rsi = self._calculate_rsi(prices, self.config.RSI_PERIOD)
            
            current_price = prices[-1]
            current_volume = volumes[-1]
            avg_volume = np.mean(volumes[-20:-1])
            
            # Find support level (previous local low)
            support = np.min(lows[-20:-1])
            
            # Check conditions
            breakdown = current_price < support
            volume_confirmed = current_volume > avg_volume * 1.5
            trend_confirmed = ema9[-1] < ema21[-1]
            rsi_ok = rsi[-1] >= 30
            
            # Log rejection reasons if any condition fails
            if not (breakdown and volume_confirmed and trend_confirmed and rsi_ok):
                reasons = []
                if not breakdown:
                    reasons.append(f"price {current_price:.4f} >= support {support:.4f}")
                if not volume_confirmed:
                    vol_ratio = current_volume / avg_volume if avg_volume > 0 else 0
                    reasons.append(f"volume ratio {vol_ratio:.2f}x < 1.5x")
                if not trend_confirmed:
                    reasons.append(f"EMA9 {ema9[-1]:.4f} >= EMA21 {ema21[-1]:.4f}")
                if not rsi_ok:
                    reasons.append(f"RSI {rsi[-1]:.1f} < 30 (oversold)")
                logger.debug(f"[{symbol}] Breakdown rejected: {', '.join(reasons)}")
            
            if breakdown and volume_confirmed and trend_confirmed and rsi_ok:
                logger.info(f"Breakdown strategy triggered for {symbol}")
                
                position_size = self._calculate_position_size(symbol, current_price)
                
                return {
                    'action': 'SELL',
                    'symbol': symbol,
                    'entry_price': current_price,
                    'position_size': position_size,
                    'stop_loss': current_price * (1 + self.config.STOP_LOSS_PERCENT / 100),
                    'take_profit_1': current_price - self.config.TAKE_PROFIT_1_USDT,
                    'take_profit_2': current_price - self.config.TAKE_PROFIT_2_USDT,
                    'strategy': 'breakdown',
                    'reason': f'Breakdown below {support:.4f} with volume confirmation'
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error in breakdown strategy for {symbol}: {e}")
            return None
    
    def check_resistance_rejection_strategy(self, symbol: str, ohlcv: List[Dict]) -> Optional[Dict]:
        """
        Strategy 2: Rejection from resistance
        
        Conditions (ALL must be true):
        1. Price rejected from key resistance (previous local high or Fibonacci 38.2%)
        2. RSI between 65 and 75
        3. Volume on rejection > 130% of average
        4. Bearish candle forms (red with upper shadow)
        """
        try:
            if len(ohlcv) < 50:
                logger.debug(f"[{symbol}] Resistance rejection: Insufficient data ({len(ohlcv)} < 50)")
                return None
            
            prices = np.array([c['close'] for c in ohlcv])
            volumes = np.array([c['volume'] for c in ohlcv])
            highs = np.array([c['high'] for c in ohlcv])
            lows = np.array([c['low'] for c in ohlcv])
            opens = np.array([c['open'] for c in ohlcv])
            
            # Calculate RSI
            rsi = self._calculate_rsi(prices, self.config.RSI_PERIOD)
            
            current_price = prices[-1]
            current_volume = volumes[-1]
            avg_volume = np.mean(volumes[-20:-1])
            
            # Find resistance level (previous local high)
            resistance = np.max(highs[-20:-1])
            
            # Calculate Fibonacci levels from recent swing
            recent_high = np.max(highs[-50:-1])
            recent_low = np.min(lows[-50:-1])
            fib_382 = recent_low + (recent_high - recent_low) * 0.382
            
            # Use the lower of the two resistance levels
            key_resistance = min(resistance, fib_382)
            
            # Check if price rejected from resistance
            prev_high = highs[-2]
            rejection = current_price < prev_high and prev_high >= key_resistance * 0.995
            
            # Check RSI condition
            rsi_ok = 65 < rsi[-1] < 75
            
            # Check volume condition
            volume_confirmed = current_volume > avg_volume * 1.3
            
            # Check for bearish candle (red with upper shadow)
            current_open = opens[-1]
            current_close = prices[-1]
            current_high = highs[-1]
            is_bearish = current_close < current_open
            has_upper_shadow = (current_high - current_open) > (current_open - current_close) * 0.5
            
            # Log rejection reasons if any condition fails
            if not (rejection and rsi_ok and volume_confirmed and is_bearish and has_upper_shadow):
                reasons = []
                if not rejection:
                    reasons.append(f"no rejection (price {current_price:.4f}, prev_high {prev_high:.4f})")
                if not rsi_ok:
                    reasons.append(f"RSI {rsi[-1]:.1f} not in 65-75 range")
                if not volume_confirmed:
                    vol_ratio = current_volume / avg_volume if avg_volume > 0 else 0
                    reasons.append(f"volume ratio {vol_ratio:.2f}x < 1.3x")
                if not is_bearish:
                    reasons.append("bullish candle")
                if not has_upper_shadow:
                    reasons.append("no upper shadow")
                logger.debug(f"[{symbol}] Resistance rejection rejected: {', '.join(reasons)}")
            
            if rejection and rsi_ok and volume_confirmed and is_bearish and has_upper_shadow:
                logger.info(f"Resistance rejection strategy triggered for {symbol}")
                
                position_size = self._calculate_position_size(symbol, current_price)
                
                return {
                    'action': 'SELL',
                    'symbol': symbol,
                    'entry_price': current_price,
                    'position_size': position_size,
                    'stop_loss': key_resistance * (1 + 0.015),  # 1.5% above resistance
                    'take_profit_1': current_price - self.config.TAKE_PROFIT_1_USDT,
                    'take_profit_2': current_price - self.config.TAKE_PROFIT_2_USDT,
                    'strategy': 'resistance_rejection',
                    'reason': f'Rejection from resistance at {key_resistance:.4f}'
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error in resistance rejection strategy for {symbol}: {e}")
            return None
    
    def check_overbought_scalping_strategy(self, symbol: str, ohlcv: List[Dict]) -> Optional[Dict]:
        """
        Strategy 3: Overbought scalping
        
        Conditions (ALL must be true):
        1. Price touches or near upper Bollinger Band
        2. Stochastic above 80 (overbought)
        3. Bollinger Bands compressed (width < average of last 50 periods)
        4. Previous 3 candles were green (bullish)
        """
        try:
            if len(ohlcv) < 100:
                logger.debug(f"[{symbol}] Overbought scalp: Insufficient data ({len(ohlcv)} < 100)")
                return None
            
            prices = np.array([c['close'] for c in ohlcv])
            volumes = np.array([c['volume'] for c in ohlcv])
            opens = np.array([c['open'] for c in ohlcv])
            highs = np.array([c['high'] for c in ohlcv])
            lows = np.array([c['low'] for c in ohlcv])
            
            # Calculate Bollinger Bands
            bb_upper, bb_middle, bb_lower = self._calculate_bollinger_bands(prices)
            
            # Calculate Stochastic
            stoch_k, stoch_d = self._calculate_stochastic(highs, lows, prices)
            
            current_price = prices[-1]
            current_volume = volumes[-1]
            avg_volume = np.mean(volumes[-20:-1])
            
            # Check if bands are compressed
            current_bb_width = (bb_upper[-1] - bb_lower[-1]) / bb_middle[-1]
            avg_bb_width = np.mean([(bb_upper[i] - bb_lower[i]) / bb_middle[i] 
                                   for i in range(-51, -1)])
            bands_compressed = current_bb_width < avg_bb_width
            
            # Check if price at upper band
            at_upper_band = current_price >= bb_upper[-1] * 0.998  # Within 0.2%
            
            # Check overbought condition
            overbought = stoch_k[-1] > 80
            
            # Check volume increase
            volume_increasing = current_volume > avg_volume * 1.2
            
            # Check previous 3 candles were green
            prev_3_green = all(opens[i] < prices[i] for i in range(-4, -1))
            
            # Log rejection reasons if any condition fails
            if not (at_upper_band and overbought and bands_compressed and prev_3_green):
                reasons = []
                if not at_upper_band:
                    reasons.append(f"price {current_price:.4f} not at upper BB {bb_upper[-1]:.4f}")
                if not overbought:
                    reasons.append(f"Stochastic K {stoch_k[-1]:.1f} <= 80")
                if not bands_compressed:
                    reasons.append(f"BB width {current_bb_width:.4f} >= avg {avg_bb_width:.4f}")
                if not prev_3_green:
                    reasons.append("previous 3 candles not all green")
                logger.debug(f"[{symbol}] Overbought scalp rejected: {', '.join(reasons)}")
            
            if at_upper_band and overbought and bands_compressed and prev_3_green:
                logger.info(f"Overbought scalping strategy triggered for {symbol}")
                
                position_size = self._calculate_position_size(symbol, current_price)
                
                return {
                    'action': 'SELL',
                    'symbol': symbol,
                    'entry_price': current_price,
                    'position_size': position_size,
                    'stop_loss': current_price * (1 + 0.01),  # 1% above entry
                    'take_profit_1': current_price - self.config.TAKE_PROFIT_1_USDT,
                    'take_profit_2': current_price - self.config.TAKE_PROFIT_2_USDT,
                    'strategy': 'overbought_scalp',
                    'reason': f'Price at upper BB ({bb_upper[-1]:.4f}) and overbought'
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error in overbought scalping strategy for {symbol}: {e}")
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

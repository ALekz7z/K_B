"""
Market Analyzer Module
Determines market phase and selects coins for trading
"""

import logging
from typing import Dict, List, Optional, Tuple
from enum import Enum
import numpy as np

logger = logging.getLogger(__name__)


class MarketPhase(Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    RANGE = "RANGE"
    UNCERTAIN = "UNCERTAIN"


class MarketAnalyzer:
    """
    Analyzes market conditions and determines the current phase.
    Selects top coins for trading based on multiple filters.
    """
    
    def __init__(self, bybit_client, config, get_ohlcv_func=None, get_ticker_func=None, get_orderbook_func=None):
        self.client = bybit_client
        self.config = config
        # Use wrapper functions if provided (for compatibility with different API versions)
        # Default to None - will be set by main bot if not provided
        self._get_ohlcv = get_ohlcv_func
        self._get_ticker = get_ticker_func
        self._get_orderbook = get_orderbook_func
        self.adaptive_params = {
            'ema_period': 50,
            'adx_threshold': 25,
            'volatility_min': 0.03,
            'volatility_max': 0.08
        }
        self.performance_history = []  # Track indicator performance
    
    def fetch_symbols_from_bybit(self, category=None, quote_filter=None, min_price=None, sort_by=None, limit=None):
        """
        Fetch available trading symbols from Bybit API with filtering and sorting.
        
        Args:
            category: Trading category ("spot" or "linear")
            quote_filter: Filter by quote currency (e.g., "USDT")
            min_price: Minimum price threshold
            sort_by: Indicator to sort by ("volume24h", "price_change_pct", "turnover_rate")
            limit: Maximum number of symbols to return (overrides TOP_SYMBOLS_TO_FETCH if specified)
            
        Returns:
            List of symbol dictionaries sorted by the specified indicator
        """
        try:
            # Use config defaults if not specified
            category = category or getattr(self.config, 'SYMBOL_FETCH_CATEGORY', 'spot')
            quote_filter = quote_filter or getattr(self.config, 'SYMBOL_FILTER_BY_QUOTE', 'USDT')
            min_price = min_price if min_price is not None else getattr(self.config, 'MIN_SYMBOL_PRICE', 0.0001)
            sort_by = sort_by or getattr(self.config, 'SORT_BY_INDICATOR', 'volume24h')
            # Use provided limit, or config's TOP_SYMBOLS_TO_FETCH, or fallback to TOP_COINS_TO_SELECT
            limit = limit or getattr(self.config, 'TOP_SYMBOLS_TO_FETCH', getattr(self.config, 'TOP_COINS_TO_SELECT', 30))
            
            logger.info(f"Fetching symbols from Bybit: category={category}, quote={quote_filter}, sort_by={sort_by}")
            
            # Fetch all tickers for the category
            response = self.client.get_tickers(category=category)
            
            if isinstance(response, dict) and response.get("retCode") == 0:
                result = response.get("result", {})
                tickers_list = result.get("list", [])
                
                if not tickers_list:
                    logger.warning("No tickers returned from Bybit API")
                    return []
                
                # Filter and process symbols
                filtered_symbols = []
                for ticker in tickers_list:
                    symbol = ticker.get("symbol", "")
                    
                    # Skip if symbol is None or empty
                    if not symbol:
                        continue
                    
                    # Filter by quote currency
                    if quote_filter and not str(symbol).endswith(quote_filter):
                        continue
                    
                    # Parse price and filter by minimum price
                    try:
                        last_price = float(ticker.get("lastPrice", 0))
                        if last_price < min_price:
                            continue
                    except (ValueError, TypeError):
                        continue
                    
                    # Parse volume and other metrics
                    try:
                        volume_24h = float(ticker.get("volume24h", 0))
                        turnover_24h = float(ticker.get("turnover24h", 0))
                        
                        # Calculate price change percentage
                        prev_price = float(ticker.get("prevPrice24h", last_price))
                        if prev_price > 0:
                            price_change_pct = ((last_price - prev_price) / prev_price) * 100
                        else:
                            price_change_pct = 0.0
                    except (ValueError, TypeError):
                        volume_24h = 0
                        turnover_24h = 0
                        price_change_pct = 0.0
                    
                    # Skip symbols with zero volume (likely not available on TESTNET)
                    if volume_24h == 0:
                        logger.debug(f"Skipping {symbol} - zero volume (not available on TESTNET)")
                        continue
                    
                    filtered_symbols.append({
                        'symbol': symbol,
                        'lastPrice': last_price,
                        'volume24h': volume_24h,
                        'turnover24h': turnover_24h,
                        'price_change_pct': price_change_pct
                    })
                
                # Sort by specified indicator
                if sort_by == "volume24h":
                    filtered_symbols.sort(key=lambda x: x['volume24h'], reverse=True)
                elif sort_by == "price_change_pct":
                    # Sort by absolute price change (most volatile first)
                    filtered_symbols.sort(key=lambda x: abs(x['price_change_pct']), reverse=True)
                elif sort_by == "turnover_rate":
                    filtered_symbols.sort(key=lambda x: x['turnover24h'], reverse=True)
                else:
                    # Default: sort by volume
                    filtered_symbols.sort(key=lambda x: x['volume24h'], reverse=True)
                
                # Limit the number of results
                result_symbols = [s['symbol'] for s in filtered_symbols[:limit]]
                
                logger.info(f"Fetched {len(result_symbols)} symbols from Bybit (top {limit} by {sort_by})")
                logger.debug(f"Top symbols: {result_symbols[:10]}")
                
                return result_symbols
            else:
                error_msg = response.get('retMsg', 'Unknown error') if isinstance(response, dict) else 'Invalid response'
                logger.error(f"Failed to fetch symbols from Bybit: {error_msg}")
                return []
                
        except Exception as e:
            logger.error(f"Error fetching symbols from Bybit: {e}")
            return []
    
    def determine_market_phase(self, symbol: str, timeframe: str = "5m") -> MarketPhase:
        """
        Determine the current market phase using multiple indicators.
        All conditions must be met for LONG or SHORT phase.
        """
        try:
            # Get OHLCV data using wrapper function
            if self._get_ohlcv is None:
                logger.warning(f"No OHLCV function available for {symbol}")
                return MarketPhase.UNCERTAIN
            ohlcv = self._get_ohlcv(symbol, timeframe)
            if ohlcv is None or len(ohlcv) < 200:
                logger.warning(f"Not enough data for {symbol}")
                return MarketPhase.UNCERTAIN
            
            prices = np.array([candle['close'] for candle in ohlcv])
            
            # Calculate indicators
            ema50 = self._calculate_ema(prices, self.adaptive_params['ema_period'])
            ema100 = self._calculate_ema(prices, 100)
            ema200 = self._calculate_ema(prices, 200)
            adx = self._calculate_adx(ohlcv, self.config.ADX_PERIOD)
            macd_line, macd_signal = self._calculate_macd(prices)
            rsi = self._calculate_rsi(prices, self.config.RSI_PERIOD)
            
            current_price = prices[-1]
            current_adx = adx[-1] if len(adx) > 0 else 0
            current_macd = macd_line[-1] if len(macd_line) > 0 else 0
            current_macd_signal = macd_signal[-1] if len(macd_signal) > 0 else 0
            current_rsi = rsi[-1] if len(rsi) > 0 else 50
            
            # Check LONG phase conditions (ALL must be true)
            long_conditions = [
                current_price > ema200[-1],  # Price above EMA 200
                ema50[-1] > ema200[-1],  # Golden cross
                current_adx > self.adaptive_params['adx_threshold'],  # Strong trend
                current_macd > current_macd_signal,  # MACD above signal
                current_macd > 0  # Positive MACD
            ]
            
            # Check SHORT phase conditions (ALL must be true)
            short_conditions = [
                current_price < ema200[-1],  # Price below EMA 200
                ema50[-1] < ema200[-1],  # Death cross
                current_adx > self.adaptive_params['adx_threshold'],  # Strong trend
                current_macd < current_macd_signal,  # MACD below signal
                current_macd < 0  # Negative MACD
            ]
            
            # Check RANGE phase conditions (ALL must be true)
            price_deviation = abs(current_price - ema200[-1]) / ema200[-1]
            range_conditions = [
                price_deviation <= self.config.RANGE_PHASE_PRICE_DEVIATION,  # Near EMA 200
                current_adx < self.config.RANGE_PHASE_MAX_ADX,  # Weak trend
                abs(current_macd) < self.config.RANGE_PHASE_MACD_THRESHOLD  # MACD near zero
            ]
            
            # Determine phase
            if all(long_conditions):
                logger.info(f"LONG phase detected for {symbol}")
                return MarketPhase.LONG
            elif all(short_conditions):
                logger.info(f"SHORT phase detected for {symbol}")
                return MarketPhase.SHORT
            elif all(range_conditions):
                logger.info(f"RANGE phase detected for {symbol}")
                return MarketPhase.RANGE
            else:
                logger.info(f"UNCERTAIN phase for {symbol}")
                return MarketPhase.UNCERTAIN
                
        except Exception as e:
            logger.error(f"Error determining market phase: {e}")
            return MarketPhase.UNCERTAIN
    
    def select_coins(self, all_symbols: List[str]) -> List[Dict]:
        """
        Select top coins for trading based on multiple filters.
        Returns list of coins with their scores and metrics.
        """
        coin_scores = []
        
        for symbol in all_symbols:
            try:
                # Apply all filters sequentially
                score = 0
                metrics = {}
                
                # Filter 1: Liquidity
                liquidity_ok, liq_metrics = self._check_liquidity(symbol)
                if not liquidity_ok:
                    continue
                score += liq_metrics['score']
                metrics.update(liq_metrics)
                
                # Filter 2: Volatility
                volatility_ok, vol_metrics = self._check_volatility(symbol)
                if not volatility_ok:
                    continue
                score += vol_metrics['score']
                metrics.update(vol_metrics)
                
                # Filter 3: Correlation with BTC
                corr_ok, corr_metrics = self._check_correlation(symbol)
                if not corr_ok:
                    continue
                score += corr_metrics['score']
                metrics.update(corr_metrics)
                
                # Filter 4: Sentiment analysis
                sentiment_ok, sent_metrics = self._check_sentiment(symbol)
                if sentiment_ok:
                    score += sent_metrics['score']
                metrics.update(sent_metrics)
                
                # Filter 5: Orderbook analysis
                orderbook_ok, ob_metrics = self._check_orderbook(symbol)
                if orderbook_ok:
                    score += ob_metrics['score']
                metrics.update(ob_metrics)
                
                # Filter 6: Technical conditions
                tech_ok, tech_metrics = self._check_technical(symbol)
                if not tech_ok:
                    continue
                score += tech_metrics['score']
                metrics.update(tech_metrics)
                
                coin_scores.append({
                    'symbol': symbol,
                    'score': score,
                    'metrics': metrics
                })
                
            except Exception as e:
                logger.warning(f"Error analyzing {symbol}: {e}")
                continue
        
        # Sort by score and return top coins
        coin_scores.sort(key=lambda x: x['score'], reverse=True)
        return coin_scores[:self.config.TOP_COINS_TO_SELECT]
    
    def _check_liquidity(self, symbol: str) -> Tuple[bool, Dict]:
        """Check liquidity filter: volume > 50M USDT (SPOT) or 10M USDT (FUTURES), spread < 0.1%"""
        try:
            # Get ticker data - handle both dict and float return types
            if self._get_ticker is None:
                logger.error(f"No ticker function available for {symbol}")
                return False, {'score': 0}
            
            ticker_data = self._get_ticker(symbol)
            
            # If ticker_data has zero values, API returned no data
            if isinstance(ticker_data, dict):
                volume_24h = float(ticker_data.get('volume_24h', ticker_data.get('volume24h', 0)))
                bid = float(ticker_data.get('bid_price', ticker_data.get('bid1Price', 0)))
                ask = float(ticker_data.get('ask_price', ticker_data.get('ask1Price', 0)))
                
                # Check if we got valid data from API
                if volume_24h == 0 or bid == 0 or ask == 0:
                    logger.error(f"Invalid ticker data for {symbol} - API returned zero values")
                    return False, {'score': 0}
            else:
                logger.error(f"Unexpected ticker data format for {symbol}: {type(ticker_data)}")
                return False, {'score': 0}
            
            if bid > 0 and ask > 0:
                spread = (ask - bid) / bid * 100
            else:
                spread = 100
            
            # Determine min volume based on trading mode
            # Check for mode-specific settings first, then fall back to general setting
            if hasattr(self.config, 'trading_mode'):
                from modules.risk_manager import TradingMode
                if self.config.trading_mode == TradingMode.FUTURES:
                    min_volume = getattr(self.config, 'FUTURES_MIN_VOLUME_24H_USDT', 10000000)
                    logger.debug(f"Using FUTURES min volume filter: {min_volume / 1000000:.1f}M USDT")
                else:
                    min_volume = getattr(self.config, 'SPOT_MIN_VOLUME_24H_USDT', 50000000)
                    logger.debug(f"Using SPOT min volume filter: {min_volume / 1000000:.1f}M USDT")
            else:
                min_volume = getattr(self.config, 'MIN_VOLUME_24H_USDT', 50000000)
            
            score = 0
            if volume_24h >= min_volume:
                score += 20
            if spread <= self.config.MAX_SPREAD_PERCENT:
                score += 10
            
            passed = volume_24h >= min_volume and spread <= self.config.MAX_SPREAD_PERCENT
            
            return passed, {
                'score': score,
                'volume_24h': volume_24h,
                'spread_percent': spread
            }
        except Exception as e:
            logger.error(f"Liquidity check error for {symbol}: {e}")
            return False, {'score': 0}
    
    def _check_volatility(self, symbol: str) -> Tuple[bool, Dict]:
        """Check volatility filter: 24h change between 3-8%, ATR > 0.5%"""
        try:
            # Use wrapper function for API compatibility
            if self._get_ohlcv is None:
                logger.error(f"No OHLCV function available for {symbol}")
                return False, {'score': 0}
            
            # Try to get daily candles first (limit=2 for 24h change calculation)
            ohlcv_daily = self._get_ohlcv(symbol, "1d", limit=2)
            
            # If not enough daily data, fall back to 5m candles and calculate 24h change from them
            if not ohlcv_daily or len(ohlcv_daily) < 2:
                logger.debug(f"Insufficient daily data for {symbol}, trying 5m candles...")
                ohlcv_5m = self._get_ohlcv(symbol, "5m", limit=288)  # 288 * 5min = 24h
                if not ohlcv_5m or len(ohlcv_5m) < 288:
                    logger.warning(f"Insufficient historical data for {symbol} volatility check - need at least 24h of data")
                    return False, {'score': 0}
                
                # Calculate price change from 5m data (compare first and last candle in 24h window)
                price_change = abs(ohlcv_5m[-1]['close'] - ohlcv_5m[0]['close']) / ohlcv_5m[0]['close']
                
                # Calculate ATR from 5m data
                atr = self._calculate_atr(ohlcv_5m, self.config.ATR_PERIOD)
                current_atr = atr[-1] if len(atr) > 0 else 0
                current_price = ohlcv_5m[-1]['close']
                atr_percent = (current_atr / current_price * 100) if current_price > 0 else 0
            else:
                # Use daily data as before
                price_change = abs(ohlcv_daily[-1]['close'] - ohlcv_daily[-2]['close']) / ohlcv_daily[-2]['close']
                
                # Calculate ATR
                atr = self._calculate_atr(ohlcv_daily, self.config.ATR_PERIOD)
                current_atr = atr[-1] if len(atr) > 0 else 0
                current_price = ohlcv_daily[-1]['close']
                atr_percent = (current_atr / current_price * 100) if current_price > 0 else 0
            
            # Determine volatility thresholds based on trading mode
            if hasattr(self.config, 'trading_mode'):
                from modules.risk_manager import TradingMode
                if self.config.trading_mode == TradingMode.FUTURES:
                    min_vol = getattr(self.config, 'FUTURES_MIN_VOLATILITY_24H', 0.02)
                    max_vol = getattr(self.config, 'FUTURES_MAX_VOLATILITY_24H', 0.15)
                    logger.debug(f"Using FUTURES volatility filter: {min_vol*100:.1f}% - {max_vol*100:.1f}%")
                else:
                    min_vol = getattr(self.config, 'SPOT_MIN_VOLATILITY_24H', 0.03)
                    max_vol = getattr(self.config, 'SPOT_MAX_VOLATILITY_24H', 0.08)
                    logger.debug(f"Using SPOT volatility filter: {min_vol*100:.1f}% - {max_vol*100:.1f}%")
            else:
                min_vol = getattr(self.config, 'MIN_VOLATILITY_24H', 0.03)
                max_vol = getattr(self.config, 'MAX_VOLATILITY_24H', 0.08)
            
            score = 0
            if min_vol <= price_change <= max_vol:
                score += 15
            if atr_percent >= 0.5:
                score += 10
            
            passed = (min_vol <= price_change <= max_vol and atr_percent >= 0.5)
            
            return passed, {
                'score': score,
                'price_change_24h': price_change * 100,
                'atr_percent': atr_percent
            }
        except Exception as e:
            error_msg = str(e)
            # Handle insufficient data gracefully
            if 'insufficient' in error_msg.lower() or 'not enough' in error_msg.lower() or 'empty' in error_msg.lower():
                logger.warning(f"Insufficient historical data for {symbol} volatility check - skipping")
                return False, {'score': 0}
            logger.error(f"Volatility check error for {symbol}: {e}")
            return False, {'score': 0}
    
    def _check_correlation(self, symbol: str) -> Tuple[bool, Dict]:
        """Check correlation with BTC: between 0.3 and 0.8"""
        try:
            # Use wrapper function for API compatibility
            if self._get_ohlcv is None:
                logger.error(f"No OHLCV function available for {symbol}")
                return False, {'score': 0}
            
            # Get price data for symbol and BTC
            symbol_ohlcv = self._get_ohlcv(symbol, "1h", limit=24)
            btc_ohlcv = self._get_ohlcv("BTCUSDT", "1h", limit=24)
            
            if len(symbol_ohlcv) < 24 or len(btc_ohlcv) < 24:
                return False, {'score': 0}
            
            symbol_returns = np.diff([c['close'] for c in symbol_ohlcv])
            btc_returns = np.diff([c['close'] for c in btc_ohlcv])
            
            correlation = np.corrcoef(symbol_returns, btc_returns)[0, 1]
            
            score = 0
            if self.config.MIN_CORRELATION_BTC <= correlation <= self.config.MAX_CORRELATION_BTC:
                score = 15
            
            passed = self.config.MIN_CORRELATION_BTC <= correlation <= self.config.MAX_CORRELATION_BTC
            
            return passed, {
                'score': score,
                'btc_correlation': correlation
            }
        except Exception as e:
            logger.error(f"Correlation check error for {symbol}: {e}")
            return False, {'score': 0}
    
    def _check_sentiment(self, symbol: str) -> Tuple[bool, Dict]:
        """Check sentiment from external sources (placeholder)"""
        # In production, this would connect to Twitter, Reddit, Telegram APIs
        # For now, return neutral score
        return True, {'score': 5, 'sentiment': 'neutral'}
    
    def _check_orderbook(self, symbol: str) -> Tuple[bool, Dict]:
        """Analyze orderbook depth and detect large walls"""
        try:
            # Use wrapper function for API compatibility
            if self._get_orderbook is None:
                logger.error(f"No orderbook function available for {symbol}")
                return False, {'score': 0}
            
            orderbook = self._get_orderbook(symbol, depth=5)
            
            bids = orderbook.get('bids', [])
            asks = orderbook.get('asks', [])
            
            if not bids or not asks:
                return False, {'score': 0}
            
            # Calculate average order size
            bid_sizes = [float(b[1]) for b in bids]
            ask_sizes = [float(a[1]) for a in asks]
            
            avg_bid_size = np.mean(bid_sizes)
            avg_ask_size = np.mean(ask_sizes)
            
            # Detect large walls (orders > 3x average)
            large_walls = any(s > 3 * avg_bid_size for s in bid_sizes) or \
                         any(s > 3 * avg_ask_size for s in ask_sizes)
            
            score = 10 if not large_walls else 0
            
            return True, {
                'score': score,
                'has_large_walls': large_walls,
                'bid_depth': sum(bid_sizes),
                'ask_depth': sum(ask_sizes)
            }
        except Exception as e:
            logger.error(f"Orderbook check error for {symbol}: {e}")
            return False, {'score': 0}
    
    def _check_technical(self, symbol: str) -> Tuple[bool, Dict]:
        """Check technical conditions: RSI 30-70, price within Bollinger Bands"""
        try:
            # Use wrapper function for API compatibility
            if self._get_ohlcv is None:
                logger.error(f"No OHLCV function available for {symbol}")
                return False, {'score': 0}
            
            ohlcv = self._get_ohlcv(symbol, "5m", limit=50)
            if len(ohlcv) < 50:
                return False, {'score': 0}
            
            prices = np.array([candle['close'] for candle in ohlcv])
            
            rsi = self._calculate_rsi(prices, self.config.RSI_PERIOD)
            bb_upper, bb_middle, bb_lower = self._calculate_bollinger_bands(prices)
            
            current_rsi = rsi[-1] if len(rsi) > 0 else 50
            current_price = prices[-1]
            
            score = 0
            rsi_ok = self.config.RSI_OVERSOLD < current_rsi < self.config.RSI_OVERBOUGHT
            bb_ok = bb_lower[-1] < current_price < bb_upper[-1]
            
            if rsi_ok:
                score += 10
            if bb_ok:
                score += 10
            
            passed = rsi_ok and bb_ok
            
            return passed, {
                'score': score,
                'rsi': current_rsi,
                'price_vs_bb': (current_price - bb_lower[-1]) / (bb_upper[-1] - bb_lower[-1])
            }
        except Exception as e:
            logger.error(f"Technical check error for {symbol}: {e}")
            return False, {'score': 0}
    
    def update_adaptive_parameters(self, trades_history: List[Dict]):
        """
        Update adaptive parameters based on recent trade performance.
        Uses simple machine learning to optimize indicator parameters.
        """
        if len(trades_history) < 100:
            return
        
        # Analyze which parameter settings were most profitable
        recent_trades = trades_history[-100:]
        
        # Simple adaptation: adjust EMA period based on win rate
        winning_trades = [t for t in recent_trades if t['profit'] > 0]
        win_rate = len(winning_trades) / len(recent_trades)
        
        if win_rate < 0.4:
            # Poor performance, try different parameters
            self.adaptive_params['ema_period'] = np.random.randint(40, 60)
            self.adaptive_params['adx_threshold'] = np.random.randint(20, 30)
            logger.info(f"Adjusted adaptive params: EMA={self.adaptive_params['ema_period']}, "
                       f"ADX={self.adaptive_params['adx_threshold']}")
    
    # Helper methods for indicator calculations
    def _calculate_ema(self, prices: np.ndarray, period: int) -> np.ndarray:
        """Calculate Exponential Moving Average"""
        ema = np.zeros_like(prices)
        ema[0] = prices[0]
        multiplier = 2 / (period + 1)
        
        for i in range(1, len(prices)):
            ema[i] = (prices[i] - ema[i-1]) * multiplier + ema[i-1]
        
        return ema
    
    def _calculate_adx(self, ohlcv: List[Dict], period: int) -> np.ndarray:
        """Calculate Average Directional Index"""
        # Simplified ADX calculation
        highs = np.array([c['high'] for c in ohlcv])
        lows = np.array([c['low'] for c in ohlcv])
        closes = np.array([c['close'] for c in ohlcv])
        
        tr = np.maximum(highs[1:] - lows[1:], 
                       np.maximum(np.abs(highs[1:] - closes[:-1]), 
                                 np.abs(lows[1:] - closes[:-1])))
        
        dm_plus = np.maximum(highs[1:] - highs[:-1], 0)
        dm_minus = np.maximum(lows[:-1] - lows[1:], 0)
        
        atr = np.convolve(tr, np.ones(period)/period, mode='valid')
        
        # Add small epsilon to prevent division by zero
        di_plus = 100 * np.convolve(dm_plus, np.ones(period)/period, mode='valid') / (atr + 1e-10)
        di_minus = 100 * np.convolve(dm_minus, np.ones(period)/period, mode='valid') / (atr + 1e-10)
        
        dx = 100 * np.abs(di_plus - di_minus) / (di_plus + di_minus + 1e-10)
        adx = np.convolve(dx, np.ones(period)/period, mode='valid')
        
        return adx
    
    def _calculate_macd(self, prices: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Calculate MACD line and signal line"""
        ema12 = self._calculate_ema(prices, 12)
        ema26 = self._calculate_ema(prices, 26)
        
        macd_line = ema12 - ema26
        macd_signal = self._calculate_ema(macd_line, 9)
        
        return macd_line, macd_signal
    
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
    
    def _calculate_atr(self, ohlcv: List[Dict], period: int) -> np.ndarray:
        """Calculate Average True Range"""
        highs = np.array([c['high'] for c in ohlcv])
        lows = np.array([c['low'] for c in ohlcv])
        closes = np.array([c['close'] for c in ohlcv])
        
        tr = np.maximum(highs[1:] - lows[1:], 
                       np.maximum(np.abs(highs[1:] - closes[:-1]), 
                                 np.abs(lows[1:] - closes[:-1])))
        
        atr = np.convolve(tr, np.ones(period)/period, mode='valid')
        return atr

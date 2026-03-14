"""
Crypto Trading Bot - Main Controller
Master controller that orchestrates all modules for automated crypto trading on Bybit

Features:
- Automatic SPOT/FUTURES mode switching based on balance
- Balance < 500 USDT → SPOT mode (safer, no leverage)
- Balance >= 500 USDT → FUTURES mode (with leverage, all strategies)
"""

import logging
import time
from typing import Dict, List, Optional
from enum import Enum

from config.settings import *
from modules.analyzer import MarketAnalyzer, MarketPhase
from modules.risk_manager import RiskManager, TradingMode
from strategies.long_strategies import LongStrategies
from strategies.short_strategies import ShortStrategies
from strategies.range_strategies import RangeStrategies

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class TradingState(Enum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"


class CryptoTradingBot:
    def __init__(self, initial_balance: float = 100.0):
        """
        Initialize the trading bot
        
        Args:
            initial_balance: Starting balance in USDT (default: 100 for testing)
        """
        self.config = Config()
        self.state = TradingState.STOPPED
        self.client = self._initialize_bybit_client()
        
        # Initialize Risk Manager with balance-based mode switching
        self.risk_manager = RiskManager()
        self.risk_manager.update_balance(initial_balance)
        
        self.analyzer = MarketAnalyzer(self.client, self.config)
        self.long_trader = LongStrategies(self.client, self.config)
        self.short_trader = ShortStrategies(self.client, self.config)
        self.range_trader = RangeStrategies(self.client, self.config)
        
        self.current_phase = None
        self.selected_coins = []
        self.trades_history = []
        self.last_analysis_time = 0
        self.last_balance_update = 0
        
        logger.info(f"Crypto Trading Bot initialized with {initial_balance:.2f} USDT")
        logger.info(f"Trading Mode: {self.risk_manager.trading_mode.value}")
        self._log_mode_parameters()

    def _log_mode_parameters(self):
        """Log current mode parameters for transparency"""
        params = self.risk_manager.get_mode_params()
        logger.info(f"=== {params['mode']} MODE PARAMETERS ===")
        logger.info(f"Position Size: {params['position_size_percent']}% of balance")
        logger.info(f"Leverage: {params['leverage']}x")
        logger.info(f"Stop Loss: {params['stop_loss_percent']}%")
        if params['mode'] == 'FUTURES':
            logger.info(f"Take Profit 1: {params['tp1_value']} USDT")
            logger.info(f"Take Profit 2: {params['tp2_value']} USDT")
            logger.info(f"Trailing Stop Activation: {params['trailing_activation']} USDT")
        else:
            logger.info(f"Take Profit 1: {params['tp1_percent']}%")
            logger.info(f"Take Profit 2: {params['tp2_percent']}%")
            logger.info(f"Trailing Stop Activation: {params['trailing_activation_percent']}%")
        logger.info(f"Max Concurrent Trades: {params['max_concurrent_trades']}")
        logger.info(f"Max Loss Streak: {params['max_loss_streak']}")
        logger.info(f"Short Selling Allowed: {params['allow_short']}")
        logger.info("=" * 40)

    def _initialize_bybit_client(self):
        """Initialize real Bybit API client"""
        try:
            from pybit.unified_trading import HTTP
            
            api_key = BYBIT_CONFIG["API_KEY"]
            secret_key = BYBIT_CONFIG["SECRET_KEY"]
            testnet = BYBIT_CONFIG["TESTNET"]
            
            if not api_key or not secret_key:
                logger.warning("API keys not configured. Using mock client for testing.")
                return self._create_mock_client()
            
            # Initialize real Bybit client
            session = HTTP(
                testnet=testnet,
                api_key=api_key,
                api_secret=secret_key,
            )
            
            logger.info(f"Connected to Bybit {'TESTNET' if testnet else 'MAINNET'}")
            return session
            
        except ImportError:
            logger.error("pybit library not installed. Install with: pip install pybit")
            return self._create_mock_client()
        except Exception as e:
            logger.error(f"Failed to initialize Bybit client: {e}. Using mock client.")
            return self._create_mock_client()
    
    def _create_mock_client(self):
        """Create mock client for testing without API keys"""
        import numpy as np
        
        class MockClient:
            def get_ohlcv(self, symbol, timeframe, limit=200):
                # Generate realistic mock OHLCV data
                base_price = 50000 if "BTC" in symbol else 3000 if "ETH" in symbol else 300
                data = []
                current_price = base_price
                
                for i in range(limit):
                    change = np.random.randn() * 0.01  # 1% volatility
                    open_price = current_price
                    close_price = open_price * (1 + change)
                    high_price = max(open_price, close_price) * (1 + abs(np.random.randn() * 0.005))
                    low_price = min(open_price, close_price) * (1 - abs(np.random.randn() * 0.005))
                    
                    data.append({
                        "timestamp": time.time() - (limit - i) * 300,
                        "open": open_price,
                        "high": high_price,
                        "low": low_price,
                        "close": close_price,
                        "volume": np.random.uniform(1000, 10000)
                    })
                    current_price = close_price
                
                return data
            
            def get_ticker(self, symbol):
                base_price = 50000 if "BTC" in symbol else 3000 if "ETH" in symbol else 300
                return {
                    "symbol": symbol,
                    "bid_price": base_price * 0.999,
                    "ask_price": base_price * 1.001,
                    "volume_24h": 100000000,
                    "last_price": base_price
                }
            
            def get_orderbook(self, symbol, depth=5):
                base_price = 50000 if "BTC" in symbol else 3000 if "ETH" in symbol else 300
                return {
                    "bids": [[base_price - i * 0.5, 10] for i in range(depth)],
                    "asks": [[base_price + i * 0.5, 10] for i in range(depth)]
                }
            
            def get_balance(self):
                return {"balance": 100.0}
        
        return MockClient()

    def _get_ohlcv_data(self, symbol, timeframe="5m", limit=100):
        """Get OHLCV data from client (wrapper for compatibility)"""
        try:
            if hasattr(self.client, 'get_ohlcv'):
                return self.client.get_ohlcv(symbol, timeframe, limit)
            else:
                # Fallback for different API versions
                return self.client.get_kline(symbol=symbol, interval=timeframe, limit=limit)
        except Exception as e:
            logger.error(f"Error getting OHLCV for {symbol}: {e}")
            return []

    def _get_ticker_price(self, symbol):
        """Get current ticker price (wrapper for compatibility)"""
        try:
            if hasattr(self.client, 'get_ticker'):
                ticker = self.client.get_ticker(symbol)
                return float(ticker.get("last_price", 0))
            else:
                # Fallback for different API versions
                ticker = self.client.get_tickers(category="spot", symbol=symbol)
                return float(ticker.get("list", [{}])[0].get("lastPrice", 0))
        except Exception as e:
            logger.error(f"Error getting ticker for {symbol}: {e}")
            return 0.0

    def start(self):
        logger.info("Starting crypto trading bot...")
        self.state = TradingState.ACTIVE
        self._main_loop()

    def stop(self):
        logger.info("Stopping crypto trading bot...")
        self.state = TradingState.STOPPED
        self._close_all_positions()

    def pause(self):
        self.state = TradingState.PAUSED

    def resume(self):
        self.state = TradingState.ACTIVE

    def _main_loop(self):
        while self.state == TradingState.ACTIVE:
            try:
                current_time = time.time()
                
                # Update balance periodically (every minute)
                if current_time - self.last_balance_update >= 60:
                    self._update_balance()
                    self.last_balance_update = current_time
                
                # Market analysis every 15 minutes
                if current_time - self.last_analysis_time >= ANALYSIS_INTERVAL_MINUTES * 60:
                    self._perform_market_analysis()
                    self.last_analysis_time = current_time
                
                # Check trading opportunities
                if self.state == TradingState.ACTIVE and self.current_phase:
                    self._check_trading_opportunities()
                
                # Manage open positions using risk manager
                self._manage_open_positions()
                
                # Update monitoring
                self._update_monitoring()
                
                time.sleep(PRICE_UPDATE_INTERVAL_SECONDS)
            except KeyboardInterrupt:
                self.stop()
                break
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                time.sleep(5)

    def _update_balance(self):
        """Update balance from exchange and check for mode switch"""
        try:
            # In real implementation, fetch from Bybit API
            # balance_response = self.client.get_wallet_balance()
            # current_balance = float(balance_response['balance'])
            
            # For now, use mock balance with simulation
            current_balance = self.risk_manager.current_balance  # Would be fetched from API
            
            self.risk_manager.update_balance(current_balance)
            
            # Log if mode changed
            if self.risk_manager.trading_mode == TradingMode.FUTURES and current_balance >= BALANCE_THRESHOLD_USDT:
                logger.info(f"Balance: {current_balance:.2f} USDT - Trading FUTURES with leverage")
            elif self.risk_manager.trading_mode == TradingMode.SPOT and current_balance < BALANCE_THRESHOLD_USDT:
                logger.info(f"Balance: {current_balance:.2f} USDT - Trading SPOT (no leverage)")
        except Exception as e:
            logger.error(f"Error updating balance: {e}")

    def _perform_market_analysis(self):
        logger.info("Performing market analysis...")
        symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
        phases = {s: self.analyzer.determine_market_phase(s) for s in symbols}
        for s, p in phases.items():
            logger.info(f"{s}: {p.value}")
        phase_counts = {}
        for p in phases.values():
            phase_counts[p] = phase_counts.get(p, 0) + 1
        
        # Find the most common phase
        self.current_phase = max(phase_counts.keys(), key=lambda k: phase_counts[k])
        logger.info(f"Dominant market phase: {self.current_phase.value}")
        self.selected_coins = self.analyzer.select_coins(symbols)
        self.analyzer.update_adaptive_parameters(self.trades_history)

    def _check_trading_opportunities(self):
        """Check for trading opportunities based on current phase"""
        params = self.risk_manager.get_mode_params()
        
        if not self.selected_coins:
            return
        
        # Respect concurrent trade limits from risk manager
        if len(self.risk_manager.open_trades) >= params['max_concurrent_trades']:
            return
        
        for coin in self.selected_coins[:params['max_concurrent_coins']]:
            symbol = coin["symbol"] if isinstance(coin, dict) else coin
            
            # Skip if already trading this symbol
            if symbol in self.risk_manager.open_trades:
                continue
            
            # Get OHLCV data
            ohlcv = self._get_ohlcv_data(symbol, "5m", limit=100)
            current_price = self._get_ticker_price(symbol)
            if current_price == 0:
                current_price = ohlcv[-1]['close'] if ohlcv else 50000
            
            signal = None
            
            # Select strategy based on market phase
            if self.current_phase == MarketPhase.LONG:
                signal = self._check_long_strategies(symbol, ohlcv)
            elif self.current_phase == MarketPhase.SHORT:
                # Only allow short if mode permits
                if params['allow_short']:
                    signal = self._check_short_strategies(symbol, ohlcv)
                else:
                    logger.debug(f"Short selling not allowed in {params['mode']} mode, skipping")
            elif self.current_phase == MarketPhase.RANGE:
                signal = self._check_range_strategies(symbol, ohlcv)
            
            if signal:
                # Use risk manager to validate and open position
                can_open, reason = self.risk_manager.can_open_trade(symbol, signal['action'])
                if can_open:
                    # Calculate position size
                    quantity = self.risk_manager.calculate_position_size(symbol, current_price)
                    signal['quantity'] = quantity
                    self._open_position(signal)
                else:
                    logger.debug(f"Cannot open position for {symbol}: {reason}")

    def _check_long_strategies(self, symbol, ohlcv):
        for s in [self.long_trader.check_breakout_strategy, self.long_trader.check_support_bounce_strategy, self.long_trader.check_volatility_scalping_strategy]:
            sig = s(symbol, ohlcv)
            if sig: return sig
        return None

    def _check_short_strategies(self, symbol, ohlcv):
        for s in [self.short_trader.check_breakdown_strategy, self.short_trader.check_resistance_rejection_strategy, self.short_trader.check_overbought_scalping_strategy]:
            sig = s(symbol, ohlcv)
            if sig: return sig
        return None

    def _check_range_strategies(self, symbol, ohlcv):
        for s in [self.range_trader.check_range_trading_strategy, self.range_trader.check_mean_reversion_strategy, self.range_trader.check_pattern_scalping_strategy]:
            sig = s(symbol, ohlcv)
            if sig: return sig
        return None

    def _open_position(self, signal):
        """Open a new position using risk manager"""
        try:
            symbol = signal['symbol']
            side = signal['action']
            quantity = signal.get('quantity', 0)
            
            # Get current price
            entry_price = self._get_ticker_price(symbol)
            if entry_price == 0:
                logger.error(f"Cannot get price for {symbol}, skipping")
                return
            
            # Open trade through risk manager
            trade = self.risk_manager.open_trade(symbol, side, entry_price, quantity)
            
            if trade:
                logger.info(
                    f"✓ OPENED {trade.mode.value} POSITION: {side} {symbol} | "
                    f"Qty: {quantity} @ {entry_price} | "
                    f"SL: {trade.stop_loss_price:.4f} | "
                    f"TP1: {trade.tp1_price:.4f} | "
                    f"TP2: {trade.tp2_price:.4f} | "
                    f"Strategy: {signal.get('strategy', 'Unknown')}"
                )
            else:
                logger.warning(f"Failed to open position for {symbol}")
        except Exception as e:
            logger.error(f"Error opening position: {e}")

    def _manage_open_positions(self):
        """Manage open positions using risk manager"""
        # Get current prices for all symbols
        prices = {}
        for symbol in self.risk_manager.open_trades.keys():
            try:
                price = self._get_ticker_price(symbol)
                if price > 0:
                    prices[symbol] = price
            except Exception as e:
                logger.error(f"Error getting price for {symbol}: {e}")
        
        if not prices:
            return
        
        # Update trades and get actions
        actions = self.risk_manager.update_trades(prices)
        
        # Execute actions
        for symbol, action_data in actions.items():
            action = action_data.get('action')
            reason = action_data.get('reason')
            
            if action == 'CLOSE_ALL':
                logger.info(f"Closing {symbol}: {reason}")
            elif action == 'CLOSE_HALF':
                logger.info(f"Closing 50% of {symbol}: {reason}")
            elif action == 'UPDATE_STOP':
                new_stop = action_data.get('new_stop_price')
                logger.info(f"Updated stop loss for {symbol} to {new_stop:.4f}: {reason}")

    def _close_all_positions(self):
        """Close all open positions"""
        prices = {}
        for symbol in self.risk_manager.open_trades.keys():
            try:
                price = self._get_ticker_price(symbol)
                if price > 0:
                    prices[symbol] = price
            except Exception as e:
                logger.error(f"Error getting price for {symbol}: {e}")
        
        self.risk_manager.force_close_all(prices, "Bot stopped")
        logger.info("All positions closed")

    def _update_monitoring(self):
        """Update monitoring and log statistics periodically"""
        stats = self.risk_manager.get_statistics()
        
        # Log summary every 30 seconds
        if int(time.time()) % 30 == 0:
            logger.info(
                f"STATS | Mode: {stats['mode']} | "
                f"Balance: {stats['balance']:.2f} USDT | "
                f"Open: {stats['open_trades']} | "
                f"Total: {stats['total_trades']} | "
                f"Win Rate: {stats['win_rate']:.1f}% | "
                f"P&L: {stats['total_profit']:+.2f} USDT | "
                f"Loss Streak: {stats['consecutive_losses']} | "
                f"Paused: {stats['is_paused']}"
            )

    def get_statistics(self):
        """Get comprehensive trading statistics"""
        return self.risk_manager.get_statistics()


class Config:
    def __init__(self):
        import config.settings as s
        for a in dir(s):
            if a.isupper(): setattr(self, a, getattr(s, a))


if __name__ == "__main__":
    # Example: Start with 100 USDT (will use SPOT mode)
    # Change to 500+ USDT to enable FUTURES mode
    initial_balance = 100.0
    
    print(f"\n{'='*60}")
    print(f"CRYPTO TRADING BOT - STARTING")
    print(f"{'='*60}")
    print(f"Initial Balance: {initial_balance} USDT")
    print(f"Mode Threshold: {BALANCE_THRESHOLD_USDT} USDT")
    print(f"Expected Mode: {'FUTURES' if initial_balance >= BALANCE_THRESHOLD_USDT else 'SPOT'}")
    print(f"{'='*60}\n")
    
    bot = CryptoTradingBot(initial_balance=initial_balance)
    try:
        bot.start()
    except KeyboardInterrupt:
        print("\nShutting down...")
        bot.stop()

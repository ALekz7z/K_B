"""
Crypto Trading Bot - Main Controller
Master controller that orchestrates all modules for automated crypto trading on Bybit
"""

import logging
import time
from typing import Dict, List, Optional
from enum import Enum

from config.settings import *
from modules.analyzer import MarketAnalyzer, MarketPhase
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
    def __init__(self):
        self.config = Config()
        self.state = TradingState.STOPPED
        self.client = self._initialize_bybit_client()
        self.analyzer = MarketAnalyzer(self.client, self.config)
        self.long_trader = LongStrategies(self.client, self.config)
        self.short_trader = ShortStrategies(self.client, self.config)
        self.range_trader = RangeStrategies(self.client, self.config)
        self.current_phase = None
        self.selected_coins = []
        self.open_positions = []
        self.trades_history = []
        self.loss_streak = 0
        self.last_analysis_time = 0
        self.stats = {"total_trades": 0, "winning_trades": 0, "losing_trades": 0, "total_profit": 0, "total_loss": 0}
        logger.info("Crypto Trading Bot initialized")

    def _initialize_bybit_client(self):
        class MockClient:
            def get_ohlcv(self, symbol, timeframe, limit=100):
                import numpy as np
                base_price = 50000 if "BTC" in symbol else 3000
                return [{"timestamp": time.time() - i*300, "open": base_price*(1+np.random.randn()*0.01), "high": base_price*1.002, "low": base_price*0.998, "close": base_price, "volume": np.random.uniform(100, 1000)} for i in range(limit)]
            def get_ticker(self, symbol):
                return {"symbol": symbol, "bid_price": 50000, "ask_price": 50001, "volume_24h": 100000000, "last_price": 50000}
            def get_orderbook(self, symbol, depth=5):
                return {"bids": [[50000-i*0.5, 10] for i in range(depth)], "asks": [[50001+i*0.5, 10] for i in range(depth)]}
        return MockClient()

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
                if current_time - self.last_analysis_time >= ANALYSIS_INTERVAL_MINUTES * 60:
                    self._perform_market_analysis()
                    self.last_analysis_time = current_time
                if self.state == TradingState.ACTIVE and self.current_phase:
                    self._check_trading_opportunities()
                self._manage_open_positions()
                self._update_monitoring()
                time.sleep(PRICE_UPDATE_INTERVAL_SECONDS)
            except KeyboardInterrupt:
                self.stop()
                break
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                time.sleep(5)

    def _perform_market_analysis(self):
        logger.info("Performing market analysis...")
        symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
        phases = {s: self.analyzer.determine_market_phase(s) for s in symbols}
        for s, p in phases.items():
            logger.info(f"{s}: {p.value}")
        phase_counts = {}
        for p in phases.values():
            phase_counts[p] = phase_counts.get(p, 0) + 1
        self.current_phase = max(phase_counts, key=phase_counts.get)
        logger.info(f"Dominant market phase: {self.current_phase.value}")
        self.selected_coins = self.analyzer.select_coins(symbols)
        self.analyzer.update_adaptive_parameters(self.trades_history)

    def _check_trading_opportunities(self):
        if not self.selected_coins or len(self.open_positions) >= MAX_CONCURRENT_TRADES:
            return
        for coin in self.selected_coins[:MAX_CONCURRENT_COINS]:
            ohlcv = self.client.get_ohlcv(coin["symbol"], "5m", limit=100)
            signal = None
            if self.current_phase == MarketPhase.LONG:
                signal = self._check_long_strategies(coin["symbol"], ohlcv)
            elif self.current_phase == MarketPhase.SHORT:
                signal = self._check_short_strategies(coin["symbol"], ohlcv)
            elif self.current_phase == MarketPhase.RANGE:
                signal = self._check_range_strategies(coin["symbol"], ohlcv)
            if signal and self._can_open_new_position(coin["symbol"]):
                self._open_position(signal)

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

    def _can_open_new_position(self, symbol):
        if len(self.open_positions) >= MAX_CONCURRENT_TRADES: return False
        if any(p["symbol"] == symbol for p in self.open_positions): return False
        if self.loss_streak >= MAX_LOSS_STREAK:
            logger.warning(f"Loss streak limit reached ({self.loss_streak})")
            return False
        return True

    def _open_position(self, signal):
        try:
            logger.info(f"Opening {signal['action']} position for {signal['symbol']}")
            position = {**signal, "quantity": signal["position_size"], "entry_time": time.time(), "tp1_hit": False}
            self.open_positions.append(position)
            logger.info(f"Position opened: {signal['strategy']} on {signal['symbol']}")
        except Exception as e:
            logger.error(f"Error opening position: {e}")

    def _manage_open_positions(self):
        to_remove = []
        for i, pos in enumerate(self.open_positions):
            ticker = self.client.get_ticker(pos["symbol"])
            price = float(ticker.get("last_price", pos["entry_price"]))
            if pos["action"] == "BUY":
                actions = self.long_trader.manage_position(pos, price)
            else:
                actions = self.short_trader.manage_position(pos, price)
            if actions["close"]:
                self._close_position(pos, price, actions["reason"])
                to_remove.append(i)
            elif actions["close_partial"]:
                logger.info(f"Closing {actions.get('close_percent', 50)}% of {pos['symbol']}")
            elif actions["adjust_stop_loss"]:
                pos["stop_loss"] = actions["new_stop_loss"]
                logger.info(f"Adjusted stop loss for {pos['symbol']}")
        for i in sorted(to_remove, reverse=True):
            self.open_positions.pop(i)

    def _close_position(self, pos, exit_price, reason):
        entry = pos["entry_price"]
        qty = pos["quantity"]
        profit = (exit_price - entry) * qty if pos["action"] == "BUY" else (entry - exit_price) * qty
        self.stats["total_trades"] += 1
        if profit > 0:
            self.stats["winning_trades"] += 1
            self.stats["total_profit"] += profit
            self.loss_streak = 0
        else:
            self.stats["losing_trades"] += 1
            self.stats["total_loss"] += abs(profit)
            self.loss_streak += 1
        self.trades_history.append({"symbol": pos["symbol"], "profit": profit, "strategy": pos["strategy"]})
        logger.info(f"Closed {pos['action']} {pos['symbol']}: Profit={profit:.2f} USDT, Reason={reason}")
        if self.loss_streak >= MAX_LOSS_STREAK:
            logger.warning(f"Loss streak of {self.loss_streak} reached. Pausing.")
            self.pause()

    def _close_all_positions(self):
        for pos in self.open_positions:
            ticker = self.client.get_ticker(pos["symbol"])
            self._close_position(pos, float(ticker.get("last_price", pos["entry_price"])), "Bot stopped")
        self.open_positions = []

    def _update_monitoring(self):
        if self.open_positions:
            logger.debug(f"Open positions: {len(self.open_positions)}")

    def get_statistics(self):
        return {**self.stats, "loss_streak": self.loss_streak, "open_positions": len(self.open_positions), "current_phase": self.current_phase.value if self.current_phase else None}


class Config:
    def __init__(self):
        import config.settings as s
        for a in dir(s):
            if a.isupper(): setattr(self, a, getattr(s, a))


if __name__ == "__main__":
    bot = CryptoTradingBot()
    try:
        bot.start()
    except KeyboardInterrupt:
        print("Shutting down...")
        bot.stop()

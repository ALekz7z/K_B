"""
Main entry point for MEXC Trading Bot.
Orchestrates all components and runs the trading loop.
"""

import asyncio
import signal
import sys
from typing import Optional

from config import Config
from logger import BotLogger
from risk_manager import RiskManager
from mexc_client import ExchangeClient
from strategy import Strategy


class TradingBot:
    """
    Main trading bot class that orchestrates all components.
    """
    
    def __init__(self):
        """
        Initialize the trading bot.
        """
        self.logger = BotLogger()
        self.exchange: Optional[ExchangeClient] = None
        self.risk_manager: Optional[RiskManager] = None
        self.strategy: Optional[Strategy] = None
        self._running = False
        self._shutdown_requested = False
        
    async def initialize(self) -> bool:
        """
        Initialize all bot components.
        
        Returns:
            bool: True if initialization successful, False otherwise.
        """
        self.logger.info("=" * 60)
        self.logger.info("MEXC Trading Bot Starting...")
        self.logger.info("=" * 60)
        
        # Validate configuration
        if not Config.validate():
            self.logger.critical(
                "Configuration validation failed! "
                "Please check your .env file and ensure API keys are set correctly."
            )
            return False
        
        self.logger.info(f"Paper Trading Mode: {Config.PAPER_TRADING}")
        self.logger.info(f"Max Position Size: ${Config.MAX_POSITION_SIZE}")
        self.logger.info(f"Max Daily Loss: ${Config.MAX_DAILY_LOSS}")
        self.logger.info(f"Min Spread: {Config.MIN_SPREAD_PERCENT * 100}%")
        
        # Initialize exchange client
        self.exchange = ExchangeClient(self.logger, paper_trading=Config.PAPER_TRADING)
        
        if not await self.exchange.connect():
            self.logger.critical("Failed to connect to exchange")
            return False
        
        # Initialize risk manager
        self.risk_manager = RiskManager(self.logger)
        
        # Initialize strategy
        self.strategy = Strategy(self.logger, self.exchange, self.risk_manager)
        
        self.logger.info("All components initialized successfully")
        return True
    
    async def run(self) -> None:
        """
        Run the main trading loop.
        """
        if not await self.initialize():
            self.logger.critical("Bot initialization failed. Exiting.")
            return
        
        self._running = True
        self.logger.info("Starting trading loop...")
        
        cycle_count = 0
        
        try:
            while self._running and not self._shutdown_requested:
                cycle_count += 1
                self.logger.info(f"=== Trading Cycle {cycle_count} ===")
                
                # Check connection timeout
                if not await self.risk_manager.check_connection_timeout(
                    self.exchange.get_last_api_call_time()
                ):
                    self.logger.error("Connection timeout detected. Stopping bot.")
                    break
                
                # Check daily loss limit before each cycle
                if not self.risk_manager.check_daily_loss_limit():
                    self.logger.info("Daily loss limit reached. Stopping trading.")
                    break
                
                # Check minimum balance
                balance = await self.exchange.get_usdt_balance()
                if balance < 5.0:
                    self.logger.critical(
                        f"Balance too low (${balance:.2f}). Minimum $5 required. Stopping."
                    )
                    break
                
                # Run strategy cycle
                await self.strategy.run_strategy_cycle()
                
                # Log statistics periodically
                if cycle_count % 10 == 0:
                    stats = self.risk_manager.get_daily_statistics()
                    self.logger.info(
                        f"Daily Stats - Loss: ${stats['daily_loss']:.2f}/${stats['daily_loss_limit']:.2f}, "
                        f"Positions: {stats['open_positions']}/{stats['max_positions']}"
                    )
        
        except KeyboardInterrupt:
            self.logger.info("Keyboard interrupt received")
        except Exception as e:
            self.logger.critical(f"Unexpected error in trading loop: {e}")
        finally:
            await self.shutdown()
    
    async def shutdown(self) -> None:
        """
        Gracefully shutdown the bot.
        """
        self.logger.info("Shutting down bot...")
        self._running = False
        
        # Cancel all open orders
        if self.exchange and not Config.PAPER_TRADING:
            try:
                # Get all open orders
                markets = await self.exchange.get_markets()
                usdt_pairs = [m for m in markets.keys() if '/USDT' in m]
                
                for symbol in usdt_pairs[:10]:  # Limit to prevent rate issues
                    await self.exchange.cancel_all_orders(symbol)
                    
            except Exception as e:
                self.logger.error(f"Error during cleanup: {e}")
        
        # Disconnect from exchange
        if self.exchange:
            await self.exchange.disconnect()
        
        # Log final statistics
        if self.risk_manager:
            stats = self.risk_manager.get_daily_statistics()
            self.logger.info("=" * 60)
            self.logger.info("Final Statistics:")
            self.logger.info(f"  Daily Loss: ${stats['daily_loss']:.2f}")
            self.logger.info(f"  Open Positions: {stats['open_positions']}")
            self.logger.info("=" * 60)
        
        self.logger.info("Bot shutdown complete")


async def main():
    """
    Main function to run the trading bot.
    """
    bot = TradingBot()
    
    # Setup signal handlers for graceful shutdown
    def signal_handler(sig, frame):
        print("\nShutdown requested...")
        bot._shutdown_requested = True
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Run the bot
    try:
        await bot.run()
    finally:
        # Ensure proper cleanup
        if bot.exchange:
            await bot.exchange.disconnect()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBot stopped by user")
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)

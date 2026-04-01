"""
Strategy module for MEXC Trading Bot.
Implements the market making strategy with spread collection logic.
"""

import asyncio
import csv
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from decimal import Decimal

import pandas as pd

from config import Config
from logger import BotLogger
from risk_manager import RiskManager
from mexc_client import ExchangeClient


class Strategy:
    """
    Market making strategy implementation.
    Scans for opportunities and executes trades based on spread analysis.
    """
    
    def __init__(
        self,
        logger: BotLogger,
        exchange: ExchangeClient,
        risk_manager: RiskManager
    ):
        """
        Initialize the strategy.
        
        Args:
            logger: Logger instance.
            exchange: Exchange client instance.
            risk_manager: Risk manager instance.
        """
        self.logger = logger
        self.exchange = exchange
        self.risk_manager = risk_manager
        self.trades_file = "logs/trades.csv"
        self._ensure_trades_file()
        
        # Position tracking
        self.active_positions: Dict[str, Dict] = {}
        
    def _ensure_trades_file(self) -> None:
        """
        Ensure trades CSV file exists with headers.
        """
        os.makedirs("logs", exist_ok=True)
        if not os.path.exists(self.trades_file):
            with open(self.trades_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'Date', 'Pair', 'Side', 'Entry Price', 'Exit Price',
                    'Amount', 'Profit/Loss', 'Reason'
                ])
    
    def _record_trade(
        self,
        pair: str,
        side: str,
        entry_price: float,
        exit_price: float,
        amount: float,
        profit_loss: float,
        reason: str
    ) -> None:
        """
        Record a trade to CSV file.
        
        Args:
            pair: Trading pair.
            side: Buy or Sell.
            entry_price: Entry price.
            exit_price: Exit price.
            amount: Amount traded.
            profit_loss: Profit or loss in USDT.
            reason: Reason for trade closure.
        """
        timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        with open(self.trades_file, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                timestamp,
                pair,
                side,
                f"{entry_price:.8f}",
                f"{exit_price:.8f}",
                f"{amount:.8f}",
                f"{profit_loss:.4f}",
                reason
            ])
    
    async def scan_market(self) -> List[Dict]:
        """
        Scan market for trading opportunities.
        
        Returns:
            List[Dict]: List of candidate pairs with their metrics.
        """
        self.logger.info("Scanning market for opportunities...")
        candidates = []
        
        try:
            # Get all tickers
            tickers = await self.exchange.get_tickers()
            if not tickers:
                self.logger.warning("No ticker data available")
                return []
            
            excluded_coins = Config.get_excluded_coins()
            
            for symbol, ticker in tickers.items():
                try:
                    # Skip non-USDT pairs
                    if '/USDT' not in symbol:
                        continue
                    
                    base_currency = symbol.split('/')[0]
                    
                    # Skip excluded coins (top 20 by volume)
                    if base_currency in excluded_coins:
                        continue
                    
                    # Check 24h volume
                    quote_volume = ticker.get('quoteVolume', 0) or 0
                    if quote_volume < Config.MIN_24H_VOLUME:
                        continue
                    
                    # Calculate spread
                    bid = ticker.get('bid', 0) or 0
                    ask = ticker.get('ask', 0) or 0
                    
                    if bid <= 0 or ask <= 0 or bid >= ask:
                        continue
                    
                    spread_percent = (ask - bid) / bid * 100
                    
                    # Check minimum spread
                    if spread_percent < Config.MIN_SPREAD_PERCENT * 100:
                        continue
                    
                    # Check price change (avoid pumps/dumps)
                    # We'll use percentage change if available, otherwise skip this check
                    percentage_change = ticker.get('percentage', 0) or 0
                    if abs(percentage_change) > Config.MAX_PRICE_CHANGE_PERCENT * 100:
                        self.logger.debug(
                            f"Skipping {symbol}: Price change {percentage_change:.2f}% exceeds threshold"
                        )
                        continue
                    
                    candidates.append({
                        'symbol': symbol,
                        'bid': bid,
                        'ask': ask,
                        'spread_percent': spread_percent,
                        'volume_24h': quote_volume,
                        'price_change': percentage_change
                    })
                    
                except Exception as e:
                    self.logger.debug(f"Error processing {symbol}: {e}")
                    continue
            
            # Sort by spread (highest first)
            candidates.sort(key=lambda x: x['spread_percent'], reverse=True)
            
            self.logger.info(
                f"Found {len(candidates)} candidate pairs meeting criteria"
            )
            
            return candidates
            
        except Exception as e:
            self.logger.error(f"Error during market scan: {e}")
            return []
    
    async def analyze_orderbook(self, symbol: str) -> Optional[Dict]:
        """
        Analyze order book for a specific pair.
        
        Args:
            symbol: Trading pair symbol.
            
        Returns:
            Optional[Dict]: Order book analysis results, or None if invalid.
        """
        try:
            orderbook = await self.exchange.get_orderbook(
                symbol,
                limit=Config.ORDER_BOOK_DEPTH
            )
            
            bids = orderbook.get('bids', [])
            asks = orderbook.get('asks', [])
            
            if not bids or not asks:
                self.logger.debug(f"Empty order book for {symbol}")
                return None
            
            # Check best bid/ask volumes
            best_bid_price, best_bid_volume = bids[0]
            best_ask_price, best_ask_volume = asks[0]
            
            # Calculate volume in USDT at best levels
            bid_volume_usdt = best_bid_price * best_bid_volume
            ask_volume_usdt = best_ask_price * best_ask_volume
            
            # Check minimum liquidity
            if bid_volume_usdt < Config.MIN_ORDERBOOK_VOLUME_USDT:
                self.logger.debug(
                    f"Insufficient bid liquidity for {symbol}: ${bid_volume_usdt:.2f}"
                )
                return None
            
            if ask_volume_usdt < Config.MIN_ORDERBOOK_VOLUME_USDT:
                self.logger.debug(
                    f"Insufficient ask liquidity for {symbol}: ${ask_volume_usdt:.2f}"
                )
                return None
            
            # Calculate spread
            spread = best_ask_price - best_bid_price
            spread_percent = spread / best_bid_price * 100
            
            return {
                'symbol': symbol,
                'best_bid': best_bid_price,
                'best_ask': best_ask_price,
                'best_bid_volume': best_bid_volume,
                'best_ask_volume': best_ask_volume,
                'spread': spread,
                'spread_percent': spread_percent,
                'bid_volume_usdt': bid_volume_usdt,
                'ask_volume_usdt': ask_volume_usdt
            }
            
        except Exception as e:
            self.logger.error(f"Error analyzing order book for {symbol}: {e}")
            return None
    
    def calculate_entry_prices(self, orderbook_data: Dict) -> Optional[Tuple[float, float]]:
        """
        Calculate entry prices for buy and sell orders.
        
        Args:
            orderbook_data: Order book analysis data.
            
        Returns:
            Optional[Tuple[float, float]]: (buy_price, sell_price) or None if invalid.
        """
        best_bid = orderbook_data['best_bid']
        best_ask = orderbook_data['best_ask']
        
        # Calculate prices
        buy_price = best_bid * 1.001  # 0.1% above best bid
        sell_price = best_ask * 0.999  # 0.1% below best ask
        
        # Ensure sell price > buy price
        if sell_price <= buy_price:
            self.logger.debug(
                f"Invalid price structure: sell_price ({sell_price}) <= buy_price ({buy_price})"
            )
            return None
        
        return buy_price, sell_price
    
    def calculate_position_size(
        self,
        buy_price: float,
        balance_usdt: float
    ) -> float:
        """
        Calculate position size based on balance and limits.
        
        Args:
            buy_price: Buy price.
            balance_usdt: Available USDT balance.
            
        Returns:
            float: Amount of base currency to buy.
        """
        # Use configured max position size or available balance (whichever is smaller)
        trade_value = min(Config.MAX_POSITION_SIZE, balance_usdt)
        
        # Leave some buffer for fees
        trade_value *= 0.99
        
        # Calculate amount
        amount = trade_value / buy_price
        
        return amount
    
    async def execute_trade_cycle(self, symbol: str, orderbook_data: Dict) -> bool:
        """
        Execute a complete trade cycle (buy -> wait -> sell).
        
        Args:
            symbol: Trading pair symbol.
            orderbook_data: Order book analysis data.
            
        Returns:
            bool: True if trade completed successfully, False otherwise.
        """
        # Calculate prices
        prices = self.calculate_entry_prices(orderbook_data)
        if not prices:
            return False
        
        buy_price, sell_price = prices
        
        # Get balance
        balance_usdt = await self.exchange.get_usdt_balance()
        
        # Calculate position size
        amount = self.calculate_position_size(buy_price, balance_usdt)
        
        if amount <= 0:
            self.logger.warning("Calculated position size is zero or negative")
            return False
        
        order_value = amount * buy_price
        
        # Validate trade with risk manager
        if not self.risk_manager.validate_trade(symbol, order_value, balance_usdt):
            self.logger.warning(f"Trade validation failed for {symbol}")
            return False
        
        self.logger.info(
            f"Executing trade on {symbol}: Buy {amount:.6f} @ {buy_price:.6f}, "
            f"Sell @ {sell_price:.6f}"
        )
        
        # Create position record
        position_data = {
            'symbol': symbol,
            'buy_price': buy_price,
            'sell_price': sell_price,
            'amount': amount,
            'entry_time': datetime.now(timezone.utc),
            'buy_order_id': None,
            'sell_order_id': None,
            'status': 'pending_buy'
        }
        
        try:
            # Place buy order
            buy_order = await self.exchange.create_limit_order(
                symbol, 'buy', amount, buy_price
            )
            
            if not buy_order:
                self.logger.error("Failed to create buy order")
                return False
            
            position_data['buy_order_id'] = buy_order['id']
            position_data['status'] = 'waiting_for_buy_fill'
            
            # Wait for buy order to fill
            buy_filled = await self._wait_for_order_fill(
                symbol, buy_order['id'], Config.ORDER_TIMEOUT
            )
            
            if not buy_filled:
                self.logger.warning(f"Buy order not filled within timeout for {symbol}")
                await self.exchange.cancel_order(symbol, buy_order['id'])
                return False
            
            # Update position
            position_data['status'] = 'buy_filled'
            self.risk_manager.add_position(symbol, position_data)
            
            # Place sell order
            sell_order = await self.exchange.create_limit_order(
                symbol, 'sell', amount, sell_price
            )
            
            if not sell_order:
                self.logger.error("Failed to create sell order")
                # Emergency: sell at market
                await self._emergency_exit(symbol, amount, buy_price, "sell_order_failed")
                return False
            
            position_data['sell_order_id'] = sell_order['id']
            position_data['status'] = 'waiting_for_sell_fill'
            
            # Monitor sell order with stop-loss check
            sell_result = await self._monitor_sell_order(
                symbol,
                sell_order['id'],
                amount,
                buy_price,
                sell_price
            )
            
            # Remove position from tracking
            self.risk_manager.remove_position(symbol)
            
            return sell_result
            
        except Exception as e:
            self.logger.error(f"Error during trade execution: {e}")
            # Emergency cleanup
            await self._emergency_exit(symbol, amount, buy_price, f"error: {str(e)}")
            return False
    
    async def _wait_for_order_fill(
        self,
        symbol: str,
        order_id: str,
        timeout: int
    ) -> bool:
        """
        Wait for an order to be filled.
        
        Args:
            symbol: Trading pair symbol.
            order_id: Order ID.
            timeout: Timeout in seconds.
            
        Returns:
            bool: True if filled, False if timeout.
        """
        start_time = asyncio.get_event_loop().time()
        
        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > timeout:
                return False
            
            order_status = await self.exchange.get_order_status(symbol, order_id)
            
            if order_status:
                remaining = order_status.get('remaining', 0) or 0
                status = order_status.get('status', '')
                
                if status == 'closed' or remaining == 0:
                    return True
                
                if status == 'canceled' or status == 'rejected':
                    return False
            
            await asyncio.sleep(Config.POLLING_INTERVAL)
    
    async def _monitor_sell_order(
        self,
        symbol: str,
        sell_order_id: str,
        amount: float,
        buy_price: float,
        sell_price: float
    ) -> bool:
        """
        Monitor sell order with stop-loss functionality.
        
        Args:
            symbol: Trading pair symbol.
            sell_order_id: Sell order ID.
            amount: Amount held.
            buy_price: Original buy price.
            sell_price: Target sell price.
            
        Returns:
            bool: True if profitable exit, False if stop-loss or timeout.
        """
        start_time = asyncio.get_event_loop().time()
        stop_loss_price = buy_price * (1 - Config.STOP_LOSS_PERCENT)
        
        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            
            # Check timeout
            if elapsed > Config.ORDER_TIMEOUT:
                self.logger.info(f"Sell order timeout for {symbol}. Closing at market.")
                # Cancel limit order
                await self.exchange.cancel_order(symbol, sell_order_id)
                # Market sell
                exit_price = await self._market_sell(symbol, amount)
                profit_loss = (exit_price - buy_price) * amount
                self._record_trade(
                    symbol, 'SELL', buy_price, exit_price, amount,
                    profit_loss, 'timeout'
                )
                self._update_pnl(profit_loss)
                return profit_loss >= 0
            
            # Check stop-loss
            current_price = await self._get_current_price(symbol)
            if current_price and current_price <= stop_loss_price:
                self.logger.warning(
                    f"Stop-loss triggered for {symbol}! "
                    f"Price: {current_price:.6f}, Stop: {stop_loss_price:.6f}"
                )
                # Cancel limit order
                await self.exchange.cancel_order(symbol, sell_order_id)
                # Market sell
                exit_price = await self._market_sell(symbol, amount)
                profit_loss = (exit_price - buy_price) * amount
                self._record_trade(
                    symbol, 'SELL', buy_price, exit_price, amount,
                    profit_loss, 'stop_loss'
                )
                self._update_pnl(profit_loss)
                return False
            
            # Check if order filled
            order_status = await self.exchange.get_order_status(symbol, sell_order_id)
            if order_status:
                status = order_status.get('status', '')
                remaining = order_status.get('remaining', 0) or 0
                
                if status == 'closed' or remaining == 0:
                    # Order filled
                    filled_price = order_status.get('average', sell_price) or sell_price
                    profit_loss = (filled_price - buy_price) * amount
                    # Deduct fees
                    fee = filled_price * amount * Config.FEE_PERCENT
                    profit_loss -= fee
                    
                    self._record_trade(
                        symbol, 'SELL', buy_price, filled_price, amount,
                        profit_loss, 'target_reached'
                    )
                    self._update_pnl(profit_loss)
                    return profit_loss >= 0
                
                if status == 'canceled':
                    return False
            
            await asyncio.sleep(Config.POLLING_INTERVAL)
    
    async def _get_current_price(self, symbol: str) -> Optional[float]:
        """
        Get current market price.
        
        Args:
            symbol: Trading pair symbol.
            
        Returns:
            Optional[float]: Current price or None.
        """
        try:
            ticker = await self.exchange.get_tickers()
            if symbol in ticker:
                return ticker[symbol].get('last', None)
        except Exception as e:
            self.logger.debug(f"Error getting price for {symbol}: {e}")
        return None
    
    async def _market_sell(self, symbol: str, amount: float) -> float:
        """
        Execute market sell order.
        
        Args:
            symbol: Trading pair symbol.
            amount: Amount to sell.
            
        Returns:
            float: Execution price.
        """
        try:
            order = await self.exchange.create_market_order(symbol, 'sell', amount)
            if order:
                return order.get('average', order.get('price', 0)) or 0
        except Exception as e:
            self.logger.error(f"Market sell failed for {symbol}: {e}")
        return 0.0
    
    async def _emergency_exit(
        self,
        symbol: str,
        amount: float,
        buy_price: float,
        reason: str
    ) -> None:
        """
        Emergency exit from a position.
        
        Args:
            symbol: Trading pair symbol.
            amount: Amount to sell.
            buy_price: Original buy price.
            reason: Reason for emergency exit.
        """
        self.logger.warning(f"Emergency exit for {symbol}: {reason}")
        
        try:
            # Cancel any open orders
            await self.exchange.cancel_all_orders(symbol)
            
            # Market sell
            exit_price = await self._market_sell(symbol, amount)
            
            if exit_price > 0:
                profit_loss = (exit_price - buy_price) * amount
                self._record_trade(
                    symbol, 'SELL', buy_price, exit_price, amount,
                    profit_loss, reason
                )
                self._update_pnl(profit_loss)
            
            # Remove from risk manager
            self.risk_manager.remove_position(symbol)
            
        except Exception as e:
            self.logger.critical(f"Emergency exit failed for {symbol}: {e}")
    
    def _update_pnl(self, profit_loss: float) -> None:
        """
        Update PnL tracking in risk manager.
        
        Args:
            profit_loss: Profit or loss amount.
        """
        if profit_loss >= 0:
            self.risk_manager.add_profit(profit_loss)
        else:
            self.risk_manager.add_loss(abs(profit_loss))
    
    async def run_strategy_cycle(self) -> None:
        """
        Run one complete strategy cycle.
        """
        # Scan market
        candidates = await self.scan_market()
        
        if not candidates:
            self.logger.info("No trading opportunities found")
            await asyncio.sleep(Config.POLLING_INTERVAL)
            return
        
        # Try to trade the best candidate
        for candidate in candidates[:5]:  # Check top 5 candidates
            # Check if we can open more positions
            if not self.risk_manager.check_concurrent_positions():
                break
            
            # Check daily loss limit
            if not self.risk_manager.check_daily_loss_limit():
                break
            
            # Analyze order book
            orderbook_data = await self.analyze_orderbook(candidate['symbol'])
            
            if not orderbook_data:
                continue
            
            # Execute trade
            success = await self.execute_trade_cycle(
                candidate['symbol'],
                orderbook_data
            )
            
            if success:
                self.logger.info(f"Trade cycle completed successfully")
                break
            
            # Small delay between attempts
            await asyncio.sleep(1)
        
        # Wait before next cycle
        await asyncio.sleep(Config.POLLING_INTERVAL)

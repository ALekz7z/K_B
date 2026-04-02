"""
Exchange Client module for MEXC Trading Bot.
Handles all API interactions with MEXC exchange using ccxt.
"""

import asyncio
import time
from typing import Dict, List, Optional, Tuple
from decimal import Decimal

import ccxt.async_support as ccxt
from config import Config
from logger import BotLogger


class ExchangeClient:
    """
    Asynchronous exchange client for MEXC using ccxt.
    Handles all API calls with proper error handling and rate limiting.
    """
    
    def __init__(self, logger: BotLogger, paper_trading: bool = False):
        """
        Initialize the exchange client.
        
        Args:
            logger: Logger instance for recording events.
            paper_trading: If True, simulate trades without executing them.
        """
        self.logger = logger
        self.paper_trading = paper_trading
        self.exchange: Optional[ccxt.mexc] = None
        self.last_api_call_time = 0
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 3
        
    async def connect(self) -> bool:
        """
        Connect to MEXC exchange.
        
        Returns:
            bool: True if connection successful, False otherwise.
        """
        try:
            if self.paper_trading:
                self.logger.info("PAPER TRADING MODE - No real orders will be executed")
                # Still initialize exchange for market data
                self.exchange = ccxt.mexc({
                    'enableRateLimit': True,
                    'options': {
                        'defaultType': 'spot',
                    }
                })
                # Load markets with retry
                for attempt in range(3):
                    try:
                        await self.exchange.load_markets()
                        self.last_api_call_time = time.time()
                        self.logger.info("Connected to MEXC (paper trading mode)")
                        return True
                    except ccxt.NetworkError as e:
                        if attempt == 2:
                            raise
                        self.logger.warning(f"Network error loading markets (attempt {attempt + 1}): {e}")
                        await asyncio.sleep(2 ** attempt)
            
            # Validate credentials
            if not Config.MEXC_API_KEY or not Config.MEXC_SECRET_KEY:
                self.logger.error("API credentials not found. Please check .env file.")
                return False
            
            self.exchange = ccxt.mexc({
                'apiKey': Config.MEXC_API_KEY,
                'secret': Config.MEXC_SECRET_KEY,
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'spot',
                }
            })
            
            # Load markets with retry
            for attempt in range(3):
                try:
                    await self.exchange.load_markets()
                    break
                except ccxt.NetworkError as e:
                    if attempt == 2:
                        raise
                    self.logger.warning(f"Network error loading markets (attempt {attempt + 1}): {e}")
                    await asyncio.sleep(2 ** attempt)
            
            # Test connection by fetching balance
            await self.get_balance()
            
            self.logger.info("Successfully connected to MEXC exchange")
            self.last_api_call_time = time.time()
            self._reconnect_attempts = 0
            return True
            
        except ccxt.AuthenticationError as e:
            self.logger.critical(f"Authentication failed! Invalid API keys: {e}")
            return False
        except ccxt.NetworkError as e:
            self.logger.error(f"Network error during connection: {e}")
            return False
        except Exception as e:
            self.logger.critical(f"Unexpected error during connection: {e}")
            return False
    
    async def disconnect(self) -> None:
        """
        Disconnect from the exchange gracefully.
        """
        try:
            if self.exchange:
                await self.exchange.close()
                self.exchange = None
                self.logger.info("Disconnected from exchange")
        except Exception as e:
            self.logger.error(f"Error during disconnect: {e}")
    
    async def _handle_rate_limit(self, retry_count: int = 3) -> None:
        """
        Handle rate limit errors with exponential backoff.
        
        Args:
            retry_count: Number of retries remaining.
        """
        if retry_count <= 0:
            raise Exception("Max retry attempts reached for rate limit")
        
        wait_time = 2 ** (3 - retry_count)  # Exponential backoff: 2, 4, 8 seconds
        self.logger.warning(f"Rate limit hit. Waiting {wait_time}s before retry...")
        await asyncio.sleep(wait_time)
    
    async def _retry_request(self, func, *args, max_retries: int = 3, **kwargs):
        """
        Retry a request with exponential backoff on server errors.
        
        Args:
            func: Async function to call.
            args: Positional arguments for the function.
            max_retries: Maximum number of retry attempts.
            kwargs: Keyword arguments for the function.
            
        Returns:
            Result from the function call.
        """
        for attempt in range(max_retries):
            try:
                result = await func(*args, **kwargs)
                self.last_api_call_time = time.time()
                return result
            except ccxt.DDoSProtection as e:
                self.logger.warning(f"DDoS protection/rate limit (attempt {attempt + 1}): {e}")
                retry_after = int(e.headers.get('Retry-After', 2 ** attempt))
                await asyncio.sleep(retry_after)
            except ccxt.ExchangeNotAvailable as e:
                self.logger.warning(f"Exchange not available (attempt {attempt + 1}): {e}")
                await asyncio.sleep(2 ** attempt)
            except ccxt.NetworkError as e:
                self.logger.warning(f"Network error (attempt {attempt + 1}): {e}")
                await asyncio.sleep(2 ** attempt)
            except Exception as e:
                self.logger.error(f"Unexpected error (attempt {attempt + 1}): {e}")
                if attempt == max_retries - 1:
                    raise
                await asyncio.sleep(2 ** attempt)
        
        raise Exception("Max retries exceeded")
    
    async def get_balance(self) -> Dict[str, float]:
        """
        Get account balance.
        
        Returns:
            Dict[str, float]: Dictionary of asset balances.
        """
        if self.paper_trading:
            # Simulated balance for paper trading
            return {'USDT': 100.0}
        
        try:
            balance = await self._retry_request(self.exchange.fetch_balance)
            return balance['total']
        except Exception as e:
            self.logger.error(f"Error fetching balance: {e}")
            return {}
    
    async def get_usdt_balance(self) -> float:
        """
        Get USDT balance specifically.
        
        Returns:
            float: USDT balance.
        """
        balance = await self.get_balance()
        return balance.get('USDT', 0.0)
    
    async def get_markets(self) -> List[Dict]:
        """
        Get all available markets.
        
        Returns:
            List[Dict]: List of market information.
        """
        try:
            if self.exchange is None:
                await self.connect()
            
            markets = await self._retry_request(self.exchange.load_markets)
            return markets
        except Exception as e:
            self.logger.error(f"Error fetching markets: {e}")
            return []
    
    async def get_tickers(self) -> Dict:
        """
        Get all tickers.
        
        Returns:
            Dict: Dictionary of tickers.
        """
        try:
            tickers = await self._retry_request(self.exchange.fetch_tickers)
            return tickers
        except Exception as e:
            self.logger.error(f"Error fetching tickers: {e}")
            return {}
    
    async def get_orderbook(self, symbol: str, limit: int = 20) -> Dict:
        """
        Get order book for a symbol.
        
        Args:
            symbol: Trading pair symbol (e.g., 'BTC/USDT').
            limit: Order book depth.
            
        Returns:
            Dict: Order book with bids and asks.
        """
        try:
            orderbook = await self._retry_request(
                self.exchange.fetch_order_book,
                symbol,
                limit=limit
            )
            return orderbook
        except Exception as e:
            self.logger.error(f"Error fetching order book for {symbol}: {e}")
            return {'bids': [], 'asks': []}
    
    async def get_ohlcv(self, symbol: str, timeframe: str = '1h', limit: int = 24) -> List:
        """
        Get OHLCV data for a symbol.
        
        Args:
            symbol: Trading pair symbol.
            timeframe: Candlestick timeframe.
            limit: Number of candles to fetch.
            
        Returns:
            List: OHLCV data.
        """
        try:
            ohlcv = await self._retry_request(
                self.exchange.fetch_ohlcv,
                symbol,
                timeframe=timeframe,
                limit=limit
            )
            return ohlcv
        except Exception as e:
            self.logger.error(f"Error fetching OHLCV for {symbol}: {e}")
            return []
    
    async def create_limit_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        price: float
    ) -> Optional[Dict]:
        """
        Create a limit order.
        
        Args:
            symbol: Trading pair symbol.
            side: 'buy' or 'sell'.
            amount: Amount of base currency.
            price: Limit price.
            
        Returns:
            Optional[Dict]: Order information if successful, None otherwise.
        """
        if self.paper_trading:
            self.logger.info(
                f"[PAPER] Limit {side.upper()} order: {amount} {symbol.split('/')[0]} @ {price} USDT"
            )
            # Simulate order
            return {
                'id': f'paper_{int(time.time())}',
                'symbol': symbol,
                'side': side,
                'type': 'limit',
                'amount': amount,
                'price': price,
                'status': 'open',
                'filled': 0.0,
                'remaining': amount,
                'cost': amount * price
            }
        
        try:
            order = await self._retry_request(
                self.exchange.create_limit_order,
                symbol,
                side,
                amount,
                price
            )
            self.logger.info(
                f"Order created: {side.upper()} {amount} {symbol.split('/')[0]} @ {price} USDT"
            )
            return order
        except ccxt.InsufficientFunds as e:
            self.logger.error(f"Insufficient funds for order: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Error creating order: {e}")
            return None
    
    async def create_market_order(
        self,
        symbol: str,
        side: str,
        amount: float
    ) -> Optional[Dict]:
        """
        Create a market order.
        
        Args:
            symbol: Trading pair symbol.
            side: 'buy' or 'sell'.
            amount: Amount of base currency.
            
        Returns:
            Optional[Dict]: Order information if successful, None otherwise.
        """
        if self.paper_trading:
            self.logger.info(
                f"[PAPER] Market {side.upper()} order: {amount} {symbol.split('/')[0]}"
            )
            return {
                'id': f'paper_market_{int(time.time())}',
                'symbol': symbol,
                'side': side,
                'type': 'market',
                'amount': amount,
                'status': 'closed',
                'filled': amount,
                'remaining': 0.0
            }
        
        try:
            order = await self._retry_request(
                self.exchange.create_market_order,
                symbol,
                side,
                amount
            )
            self.logger.info(f"Market order executed: {side.upper()} {amount} {symbol.split('/')[0]}")
            return order
        except Exception as e:
            self.logger.error(f"Error creating market order: {e}")
            return None
    
    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        """
        Cancel an order.
        
        Args:
            symbol: Trading pair symbol.
            order_id: Order ID to cancel.
            
        Returns:
            bool: True if cancelled successfully, False otherwise.
        """
        if self.paper_trading:
            self.logger.info(f"[PAPER] Cancelled order: {order_id}")
            return True
        
        try:
            await self._retry_request(
                self.exchange.cancel_order,
                order_id,
                symbol
            )
            self.logger.info(f"Order cancelled: {order_id}")
            return True
        except Exception as e:
            self.logger.error(f"Error cancelling order: {e}")
            return False
    
    async def get_order_status(self, symbol: str, order_id: str) -> Optional[Dict]:
        """
        Get order status.
        
        Args:
            symbol: Trading pair symbol.
            order_id: Order ID.
            
        Returns:
            Optional[Dict]: Order information if found, None otherwise.
        """
        if self.paper_trading:
            # Simulate order filling after some time
            return {
                'id': order_id,
                'symbol': symbol,
                'status': 'closed',
                'filled': 1.0,
                'remaining': 0.0
            }
        
        try:
            order = await self._retry_request(
                self.exchange.fetch_order,
                order_id,
                symbol
            )
            return order
        except Exception as e:
            self.logger.error(f"Error fetching order status: {e}")
            return None
    
    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict]:
        """
        Get open orders.
        
        Args:
            symbol: Optional symbol filter.
            
        Returns:
            List[Dict]: List of open orders.
        """
        if self.paper_trading:
            return []
        
        try:
            if symbol:
                orders = await self._retry_request(
                    self.exchange.fetch_open_orders,
                    symbol
                )
            else:
                orders = await self._retry_request(self.exchange.fetch_open_orders)
            return orders
        except Exception as e:
            self.logger.error(f"Error fetching open orders: {e}")
            return []
    
    async def cancel_all_orders(self, symbol: str) -> bool:
        """
        Cancel all open orders for a symbol.
        
        Args:
            symbol: Trading pair symbol.
            
        Returns:
            bool: True if successful, False otherwise.
        """
        if self.paper_trading:
            self.logger.info(f"[PAPER] Cancelled all orders for {symbol}")
            return True
        
        try:
            await self._retry_request(
                self.exchange.cancel_all_orders,
                symbol
            )
            self.logger.info(f"Cancelled all orders for {symbol}")
            return True
        except Exception as e:
            self.logger.error(f"Error cancelling all orders: {e}")
            return False
    
    def get_last_api_call_time(self) -> float:
        """
        Get timestamp of last successful API call.
        
        Returns:
            float: Timestamp.
        """
        return self.last_api_call_time

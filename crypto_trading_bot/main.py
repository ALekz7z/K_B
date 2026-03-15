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
        
        # Pass wrapper functions to analyzer for API compatibility
        self.analyzer = MarketAnalyzer(
            self.client, 
            self.config,
            get_ohlcv_func=self._get_ohlcv_data,
            get_ticker_func=self._get_ticker_price,
            get_orderbook_func=self._get_orderbook_data
        )
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
            
            # Check if API keys are properly configured
            if not api_key or not secret_key:
                logger.error("API keys not configured in config/settings.py")
                logger.error("Please add your Bybit API_KEY and SECRET_KEY to use real data")
                logger.error("Without API keys, the bot will use mock data for testing only")
                return self._create_mock_client()
            
            # Initialize real Bybit client
            session = HTTP(
                testnet=testnet,
                api_key=api_key,
                api_secret=secret_key,
            )
            
            # Verify connection by making a test request
            try:
                test_response = session.get_kline(category='spot', symbol='BTCUSDT', interval='5', limit=1)
                if test_response.get('retCode') != 0:
                    error_msg = test_response.get('retMsg', 'Unknown error').replace('→', '->').replace('\u2192', '->')
                    logger.error(f"Bybit API test failed: {error_msg}")
                    logger.error("Check your API keys and network connection")
                    return self._create_mock_client()
                
                # Check if we actually got data
                result = test_response.get('result', {})
                klines_list = result.get('list', []) if isinstance(result, dict) else []
                if not klines_list:
                    logger.warning("Bybit API returned empty data - check symbol and category")
                    logger.warning("Falling back to mock client for testing")
                    return self._create_mock_client()
                    
            except Exception as e:
                error_msg = str(e).replace('→', '->').replace('\u2192', '->')
                logger.error(f"Failed to test Bybit connection: {error_msg}")
                return self._create_mock_client()
            
            logger.info(f"Connected to Bybit {'TESTNET' if testnet else 'MAINNET'}")
            logger.info("API keys verified successfully")
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
            def get_kline(self, category=None, symbol=None, interval=None, limit=None):
                # Generate realistic mock OHLCV data (pybit v5 format with 'result' -> 'list')
                base_price = 50000 if symbol and "BTC" in str(symbol) else 3000 if symbol and "ETH" in str(symbol) else 300
                data = {"retCode": 0, "retMsg": "OK", "result": {"category": category or "spot", "symbol": symbol, "list": []}}
                
                current_price = base_price
                for i in range(limit if limit else 100):
                    change = np.random.randn() * 0.01  # 1% volatility
                    open_price = current_price
                    close_price = open_price * (1 + change)
                    high_price = max(open_price, close_price) * (1 + abs(np.random.randn() * 0.005))
                    low_price = min(open_price, close_price) * (1 - abs(np.random.randn() * 0.005))
                    
                    # Pybit v5 format: [timestamp, open, high, low, close, volume]
                    timestamp = int((time.time() - (limit if limit else 100 - i) * 300) * 1000)  # ms
                    data["result"]["list"].append([
                        str(timestamp),
                        str(open_price),
                        str(high_price),
                        str(low_price),
                        str(close_price),
                        str(np.random.uniform(1000, 10000))
                    ])
                    current_price = close_price
                
                return data
            
            def get_tickers(self, category=None, symbol=None):
                # Generate mock ticker data (pybit v5 format with 'result' -> 'list')
                # If symbol is None, return multiple mock tickers for testing dynamic fetching
                if symbol is None:
                    mock_tickers = []
                    base_prices = {
                        "BTCUSDT": 50000, "ETHUSDT": 3000, "BNBUSDT": 600,
                        "SOLUSDT": 150, "XRPUSDT": 0.5, "ADAUSDT": 0.45,
                        "DOGEUSDT": 0.08, "DOTUSDT": 7, "MATICUSDT": 0.8,
                        "AVAXUSDT": 35, "LINKUSDT": 15, "UNIUSDT": 6,
                        "ATOMUSDT": 9, "LTCUSDT": 70, "BCHUSDT": 250,
                        "NEARUSDT": 3, "FILUSDT": 5, "APTUSDT": 8,
                        "ARBUSDT": 1.2, "OPUSDT": 2.5, "INJUSDT": 25,
                        "SUIUSDT": 1.5, "SEIUSDT": 0.4, "TIAUSDT": 7,
                        "RUNEUSDT": 4, "FETUSDT": 1.2, "RENDERUSDT": 5,
                        "GRTUSDT": 0.2, "IMXUSDT": 1.5, "STXUSDT": 1.8
                    }
                    for sym, base_price in base_prices.items():
                        last_price = base_price * (1 + np.random.randn() * 0.001)
                        mock_tickers.append({
                            "symbol": sym,
                            "lastPrice": str(last_price),
                            "bid1Price": str(last_price * 0.999),
                            "ask1Price": str(last_price * 1.001),
                            "volume24h": str(np.random.uniform(10000000, 500000000)),
                            "turnover24h": str(np.random.uniform(50000000, 1000000000)),
                            "prevPrice24h": str(base_price)
                        })
                    
                    return {
                        "retCode": 0,
                        "retMsg": "OK",
                        "result": {
                            "category": category or "spot",
                            "list": mock_tickers
                        }
                    }
                else:
                    # Single symbol request
                    base_price = 50000 if symbol and "BTC" in str(symbol) else 3000 if symbol and "ETH" in str(symbol) else 300
                    last_price = base_price * (1 + np.random.randn() * 0.001)
                    
                    return {
                        "retCode": 0,
                        "retMsg": "OK",
                        "result": {
                            "category": category or "spot",
                            "list": [{
                                "symbol": symbol,
                                "lastPrice": str(last_price),
                                "bid1Price": str(last_price * 0.999),
                                "ask1Price": str(last_price * 1.001),
                                "volume24h": str(100000000),
                                "turnover24h": str(500000000),
                                "prevPrice24h": str(base_price)
                            }]
                        }
                    }
            
            def get_orderbook(self, category="linear", symbol=None, limit=5):
                # Support both old and new signature (with/without category)
                base_price = 50000 if symbol and "BTC" in str(symbol) else 3000 if symbol and "ETH" in str(symbol) else 300
                # Return in pybit v5 format with 'result' -> 'list' containing 'b' and 'a'
                return {
                    "retCode": 0,
                    "retMsg": "OK",
                    "result": {
                        "s": symbol,
                        "b": [[str(base_price - i * 0.5), str(10)] for i in range(limit)],
                        "a": [[str(base_price + i * 0.5), str(10)] for i in range(limit)],
                        "ts": int(time.time() * 1000)
                    }
                }
            
            def get_balance(self, accountType=None):
                # Mock balance for testing without API keys
                return {"retCode": 0, "retMsg": "OK", "result": {"list": [{"coin": "USDT", "walletBalance": "100.0"}]}}
            
            def get_wallet_balance(self, accountType=None):
                # Mock wallet balance for _get_real_balance method
                return {"retCode": 0, "retMsg": "OK", "result": {"list": [{"coin": [{"coin": "USDT", "walletBalance": "100.0"}], "totalEquity": "100.0"}]}}
        
        return MockClient()
    
    def _get_real_balance(self) -> float:
        """Fetch real balance from Bybit API"""
        try:
            # For unified margin account, use wallet_balance endpoint
            # pybit returns a tuple: (response_data, headers) or just response_data dict
            raw_response = self.client.get_wallet_balance(accountType="UNIFIED")
            
            # Handle both dict and tuple responses from pybit
            if isinstance(raw_response, tuple):
                response = raw_response[0] if len(raw_response) > 0 else {}
            else:
                response = raw_response
            
            if response.get("retCode") == 0:
                result = response.get("result", {})
                coin_list = result.get("list", [])
                
                for coin_data in coin_list:
                    coins = coin_data.get("coin", [])
                    for c in coins:
                        if c.get("coin") == "USDT":
                            wallet_balance = float(c.get("walletBalance", "0"))
                            logger.info(f"Real USDT balance from Bybit: {wallet_balance}")
                            return wallet_balance
                
                # If USDT not found, try to get total equity
                for coin_data in coin_list:
                    total_equity = float(coin_data.get("totalEquity", "0"))
                    if total_equity > 0:
                        logger.info(f"Total equity from Bybit: {total_equity} USDT")
                        return total_equity
            
            logger.warning(f"Could not fetch balance: {response}")
            return 100.0
            
        except Exception as e:
            logger.error(f"Error fetching real balance: {e}")
            return 100.0

    def _convert_timeframe(self, timeframe: str) -> str:
        """Convert timeframe to Bybit v5 format (numeric string without 'm')"""
        if not timeframe:
            return "5"  # Default to 5 minutes
            
        timeframe = str(timeframe).strip()
        
        if timeframe.endswith('m'):
            mins = timeframe[:-1]  # Remove 'm' suffix: "5m" -> "5"
            # For minute intervals that are standard, use numeric format
            # For non-standard intervals, Bybit may require alternative format
            try:
                mins_int = int(mins)
                # Standard minute intervals supported by Bybit spot
                if mins_int in [1, 3, 5, 15, 30]:
                    return mins
                else:
                    # Non-standard, will need fallback
                    return mins
            except ValueError:
                return "5"
        elif timeframe.endswith('h'):
            hours = timeframe[:-1]
            return f"{int(hours) * 60}"  # Convert hours to minutes: "1h" -> "60"
        elif timeframe.endswith('d'):
            # For daily timeframe, use numeric format first (will be converted to "D" if needed)
            return "1440"  # "1d" -> "1440"
        
        # If already numeric, return as is
        try:
            int(timeframe)
            return timeframe
        except ValueError:
            return "5"  # Default fallback
    
    def _get_ohlcv_data(self, symbol, timeframe="5m", limit=250):
        """Get OHLCV data from client (wrapper for pybit v5 compatibility)"""
        try:
            # Determine category based on trading mode
            category = "spot" if self.risk_manager.trading_mode.value == "SPOT" else "linear"
            
            # Convert timeframe to Bybit v5 format
            bybit_interval = self._convert_timeframe(timeframe)
            
            logger.debug(f"Requesting kline data for {symbol}: category={category}, interval={bybit_interval}, limit={limit}")
            
            # For SPOT category, use string interval format directly (more reliable for spot)
            # For LINEAR category, use numeric format
            if category == "spot":
                string_interval = self._get_string_interval(bybit_interval)
                if string_interval and string_interval != bybit_interval:
                    logger.debug(f"Using string interval format for spot: {string_interval}")
                    bybit_interval = string_interval
            
            # Try first with the determined interval format
            response = self.client.get_kline(
                category=category,
                symbol=symbol,
                interval=bybit_interval,
                limit=limit
            )
            
            # Check if error is "Invalid period" - try alternative format
            if isinstance(response, dict) and response.get("retCode") != 0:
                error_msg = response.get('retMsg', '')
                ret_code = response.get("retCode")
                # Check for Invalid period error (ErrCode: 10001) or any period-related error
                if 'Invalid period' in error_msg or 'period' in error_msg.lower() or ret_code == 10001:
                    logger.info(f"Interval '{bybit_interval}' not supported for {symbol}, trying alternative format...")
                    # Try with alternative interval format
                    alt_interval = self._get_alternative_interval(bybit_interval)
                    if alt_interval and alt_interval != bybit_interval:
                        logger.debug(f"Retrying with alternative interval: {alt_interval}")
                        response = self.client.get_kline(
                            category=category,
                            symbol=symbol,
                            interval=alt_interval,
                            limit=limit
                        )
            
            # Extract list from response and convert to expected format
            if isinstance(response, dict) and "retCode" in response:
                if response["retCode"] != 0:
                    error_msg_full = response.get('retMsg', 'Unknown error').replace('→', '->').replace('\u2192', '->')
                    # Handle insufficient data gracefully
                    if 'info' in error_msg_full.lower() or 'empty' in error_msg_full.lower() or 'no data' in error_msg_full.lower():
                        logger.warning(f"Insufficient historical data for {symbol} - skipping volatility check")
                        return []
                    logger.error(f"API error for {symbol}: {error_msg_full}")
                    return []
                
                # Pybit v5 returns data in 'result' -> 'list'
                result = response.get("result", {})
                klines_list = result.get("list", []) if isinstance(result, dict) else response.get("list", [])
                
                if not klines_list:
                    logger.warning(f"No data returned for {symbol} from Bybit API - may have insufficient history")
                    return []
                    
                data = []
                for k in klines_list:
                    data.append({
                        "timestamp": int(k[0]) / 1000,  # Convert ms to seconds
                        "open": float(k[1]),
                        "high": float(k[2]),
                        "low": float(k[3]),
                        "close": float(k[4]),
                        "volume": float(k[5])
                    })
                return data
            elif isinstance(response, list):
                # Already in list format (mock client)
                return response
            else:
                logger.warning(f"Unexpected response format for {symbol}")
                return []
                
        except Exception as e:
            # Convert exception to string safely, avoiding special characters
            error_msg = str(e).replace('→', '->').replace('\u2192', '->')
            # Handle insufficient data gracefully
            if 'insufficient' in error_msg.lower() or 'not enough' in error_msg.lower() or 'empty' in error_msg.lower():
                logger.warning(f"Insufficient historical data for {symbol} - skipping volatility check")
                return []
            logger.error(f"Error getting OHLCV for {symbol}: {error_msg}")
            return []
    
    def _get_alternative_interval(self, interval: str) -> Optional[str]:
        """
        Get alternative interval format for Bybit API v5.
        Tries to convert between numeric and string formats.
        
        Args:
            interval: Original interval (e.g., "1440", "60", "5")
            
        Returns:
            Alternative interval string or None if no alternative exists
        """
        try:
            interval_num = int(interval)
            
            # For spot category, some intervals work better with string format
            # Daily intervals - use string format for spot category
            if interval_num == 1440:
                return "D"
            elif interval_num == 720:
                return "12H"
            elif interval_num == 360:
                return "6H"
            elif interval_num == 240:
                return "4H"
            elif interval_num == 120:
                return "2H"
            elif interval_num == 60:
                # Try numeric format as alternative to "H"
                return "60"
            # For minute intervals, keep numeric format (they work fine)
            elif interval_num in [30, 15, 5, 3, 1]:
                # These work fine as numeric, but provide string alternative if needed
                return str(interval_num)
            else:
                # For other values, no alternative format available
                return None
        except (ValueError, TypeError):
            # If already a string, try to convert back to numeric or provide fallback
            interval_str = str(interval).upper()
            if interval_str == "D":
                return "1440"
            elif interval_str == "H":
                # "H" not supported for some spot pairs, use numeric
                return "60"
            elif interval_str.endswith("H"):
                hours = interval_str[:-1]
                return str(int(hours) * 60)
            else:
                # Last resort: try 5-minute interval as universal fallback
                return "5"

    def _get_string_interval(self, interval: str) -> Optional[str]:
        """
        Convert numeric interval to string format for Bybit SPOT category.
        String format is more reliable for spot trading pairs.
        
        Args:
            interval: Numeric interval (e.g., "1440", "60", "5")
            
        Returns:
            String interval format or None if conversion not needed
        """
        try:
            interval_num = int(interval)
            
            # Daily intervals - use string format for spot category
            if interval_num == 1440:
                return "D"
            elif interval_num == 720:
                return "12H"
            elif interval_num == 360:
                return "6H"
            elif interval_num == 240:
                return "4H"
            elif interval_num == 120:
                return "2H"
            elif interval_num == 60:
                # Use numeric format for hourly - more compatible with spot
                return "60"
            # For minute intervals, keep numeric format (they work fine)
            elif interval_num in [30, 15, 5, 3, 1]:
                return str(interval_num)
            else:
                # For other values, no string format available
                return None
        except (ValueError, TypeError):
            # If already a string, return as is
            return interval

    def _get_ticker_price(self, symbol):
        """Get current ticker price and full data (wrapper for pybit v5 compatibility)"""
        try:
            # Determine category based on trading mode
            category = "spot" if self.risk_manager.trading_mode.value == "SPOT" else "linear"
            
            # Pybit v5+ uses get_tickers with category parameter
            response = self.client.get_tickers(
                category=category,
                symbol=symbol
            )
            
            # Extract full ticker data from response
            if isinstance(response, dict) and "retCode" in response:
                if response["retCode"] != 0:
                    logger.error(f"Ticker API error for {symbol}: {response.get('retMsg', 'Unknown error')}")
                    return {'lastPrice': 0.0, 'bid1Price': 0.0, 'ask1Price': 0.0, 'volume24h': 0.0}
                
                # Pybit v5 returns data in 'result' -> 'list'
                result = response.get("result", {})
                tickers_list = result.get("list", []) if isinstance(result, dict) else response.get("list", [])
                
                if not tickers_list or len(tickers_list) == 0:
                    logger.warning(f"No ticker data returned for {symbol} from Bybit API")
                    return {'lastPrice': 0.0, 'bid1Price': 0.0, 'ask1Price': 0.0, 'volume24h': 0.0}
                    
                ticker_data = tickers_list[0]
                # Return full dictionary with all needed fields
                # Safely convert string values to float, handling empty strings
                def safe_float(value, default=0.0):
                    try:
                        if value is None or value == '':
                            return default
                        return float(value)
                    except (ValueError, TypeError):
                        logger.warning(f"Could not convert '{value}' to float for {symbol}, using default {default}")
                        return default
                
                return {
                    'lastPrice': safe_float(ticker_data.get("lastPrice"), 0.0),
                    'bid1Price': safe_float(ticker_data.get("bid1Price"), 0.0),
                    'ask1Price': safe_float(ticker_data.get("ask1Price"), 0.0),
                    'volume24h': safe_float(ticker_data.get("volume24h"), 0.0)
                }
            elif isinstance(response, dict):
                # Mock client or old API format - return as dict
                last_price = float(response.get("last_price", response.get("lastPrice", 0)))
                return {
                    'lastPrice': last_price,
                    'bid1Price': float(response.get("bid1Price", last_price * 0.999)),
                    'ask1Price': float(response.get("ask1Price", last_price * 1.001)),
                    'volume24h': float(response.get("volume24h", 100000000))
                }
            else:
                logger.warning(f"Unexpected ticker response format for {symbol}")
                return {'lastPrice': 0.0, 'bid1Price': 0.0, 'ask1Price': 0.0, 'volume24h': 0.0}
                
        except Exception as e:
            # Convert exception to string safely, avoiding special characters
            error_msg = str(e).replace('→', '->').replace('\u2192', '->')
            logger.error(f"Error getting ticker for {symbol}: {error_msg}")
            return {'lastPrice': 0.0, 'bid1Price': 0.0, 'ask1Price': 0.0, 'volume24h': 0.0}

    def _get_orderbook_data(self, symbol, depth=5):
        """Get orderbook data from client (wrapper for pybit v5 compatibility)"""
        try:
            # Determine category based on trading mode
            category = "spot" if self.risk_manager.trading_mode.value == "SPOT" else "linear"
            
            # Pybit v5+ uses get_orderbook with category parameter
            response = self.client.get_orderbook(
                category=category,
                symbol=symbol,
                limit=depth
            )
            
            # Extract orderbook data from response
            if isinstance(response, dict) and "retCode" in response:
                if response["retCode"] != 0:
                    logger.error(f"Orderbook API error for {symbol}: {response.get('retMsg', 'Unknown error')}")
                    return {'bids': [], 'asks': []}
                
                # Pybit v5 returns data in 'result' (can be dict with 'b'/'a' or list)
                result = response.get("result", {})
                
                # Handle both formats: direct result with 'b'/'a' or list format
                if isinstance(result, dict) and 'b' in result:
                    # Direct format: result contains 'b' and 'a' directly
                    bids = result.get("b", [])
                    asks = result.get("a", [])
                else:
                    # List format: result['list'][0] contains 'b' and 'a'
                    orderbook_list = result.get("list", []) if isinstance(result, dict) else response.get("list", [])
                    
                    if not orderbook_list or len(orderbook_list) == 0:
                        logger.warning(f"No orderbook data returned for {symbol} from Bybit API")
                        return {'bids': [], 'asks': []}
                    
                    orderbook_data = orderbook_list[0]
                    bids = orderbook_data.get("b", [])
                    asks = orderbook_data.get("a", [])
                
                # Convert to expected format [[price, size], ...]
                formatted_bids = [[float(b[0]), float(b[1])] for b in bids]
                formatted_asks = [[float(a[0]), float(a[1])] for a in asks]
                
                return {
                    'bids': formatted_bids,
                    'asks': formatted_asks
                }
            elif isinstance(response, dict) and 'bids' in response:
                # Mock client or old API format
                return {
                    'bids': response.get('bids', []),
                    'asks': response.get('asks', [])
                }
            else:
                logger.warning(f"Unexpected orderbook response format for {symbol}")
                return {'bids': [], 'asks': []}
                
        except Exception as e:
            # Convert exception to string safely, avoiding special characters
            error_msg = str(e).replace('→', '->').replace('\\u2192', '->')
            logger.error(f"Error getting orderbook for {symbol}: {error_msg}")
            return {'bids': [], 'asks': []}

    def _fetch_symbols_from_bybit_with_fallback(self):
        """Fetch symbols from Bybit with fallback to hardcoded list if TESTNET has no volume data"""
        try:
            # First try to fetch from Bybit
            symbols = self.analyzer.fetch_symbols_from_bybit()
            
            if symbols and len(symbols) > 0:
                logger.info(f"Successfully fetched {len(symbols)} symbols from Bybit")
                return symbols
            
            # If no symbols returned (TESTNET limitation), use fallback list
            logger.warning("No symbols with volume data from Bybit (TESTNET limitation), using fallback list")
            fallback_symbols = [
                "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
                "ADAUSDT", "DOGEUSDT", "TRXUSDT", "DOTUSDT", "MATICUSDT",
                "LTCUSDT", "SHIBUSDT", "AVAXUSDT", "UNIUSDT", "LINKUSDT",
                "ATOMUSDT", "ETCUSDT", "XLMUSDT", "BCHUSDT", "FILUSDT",
                "APTUSDT", "ARBUSDT", "OPUSDT", "NEARUSDT", "VETUSDT",
                "ICPUSDT", "ALGOUSDT", "QNTUSDT", "GRTUSDT", "SANDUSDT"
            ]
            limit = getattr(self.config, 'TOP_SYMBOLS_TO_FETCH', 30)
            return fallback_symbols[:limit]
            
        except Exception as e:
            logger.error(f"Error fetching symbols, using fallback: {e}")
            return ["BTCUSDT", "ETHUSDT", "BNBUSDT"]

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
        
        # Fetch symbols dynamically from Bybit if enabled
        if getattr(self.config, 'FETCH_SYMBOLS_ENABLED', False):
            symbols = self._fetch_symbols_from_bybit_with_fallback()
        else:
            # Use hardcoded symbol list if dynamic fetching is disabled
            symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
        
        logger.info(f"Analyzing {len(symbols)} symbols: {symbols[:10]}{'...' if len(symbols) > 10 else ''}")
        
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
    # Get real balance from Bybit account at startup
    print(f"\n{'='*60}")
    print(f"CRYPTO TRADING BOT - STARTING")
    print(f"{'='*60}")
    
    # Initialize bot temporarily to fetch real balance
    temp_bot = CryptoTradingBot(initial_balance=100.0)
    try:
        real_balance = temp_bot._get_real_balance()
        logger.info(f"Real balance fetched from Bybit: {real_balance} USDT")
    except Exception as e:
        logger.warning(f"Could not fetch real balance: {e}. Using default 100.0 USDT")
        real_balance = 100.0
    
    initial_balance = real_balance
    
    print(f"Initial Balance: {initial_balance} USDT")
    print(f"Mode Threshold: {BALANCE_THRESHOLD_USDT} USDT")
    print(f"Expected Mode: {'FUTURES' if initial_balance >= BALANCE_THRESHOLD_USDT else 'SPOT'}")
    print(f"{'='*60}\n")
    
    # Stop temporary bot and create new one with real balance
    temp_bot.stop()
    
    bot = CryptoTradingBot(initial_balance=initial_balance)
    try:
        bot.start()
    except KeyboardInterrupt:
        print("\nShutting down...")
        bot.stop()

# Configuration settings for the crypto trading bot

# === API Settings ===
BYBIT_CONFIG = {
    "API_KEY": "",  # Вставьте ваш API ключ здесь
    "SECRET_KEY": "",  # Вставьте ваш Secret ключ здесь
    "TESTNET": True,  # True для демо-счета, False для реального
}

# === BALANCE-BASED TRADING MODE ===
INITIAL_BALANCE_USDT = 100.0  # Начальный баланс для торговли (указывается вручную)
BALANCE_THRESHOLD_USDT = 500  # Threshold to switch between SPOT and FUTURES
# Mode will be automatically determined: 'SPOT' if balance < threshold, 'FUTURES' otherwise

# Trading Parameters - FUTURES MODE (balance >= 500 USDT)
FUTURES_POSITION_SIZE_PERCENT = 2.5  # % of deposit per trade (risk-based)
FUTURES_LEVERAGE = 10  # Default leverage for futures (5-20x recommended)
FUTURES_MAX_LEVERAGE = 20  # Maximum allowed leverage
TARGET_PROFIT_USDT = 3.5  # Target profit per trade (3-4 USDT)
MAX_CONCURRENT_TRADES = 3
MAX_CONCURRENT_COINS = 2
MAX_LOSS_STREAK = 4  # Stop trading after this many consecutive losses
TRADING_PAUSE_HOURS = 1  # Pause duration after loss streak

# Trading Parameters - SPOT MODE (balance < 500 USDT)
SPOT_POSITION_SIZE_PERCENT = 12.0  # % of deposit per trade (larger since no leverage)
SPOT_LEVERAGE = 1  # No leverage in spot mode
SPOT_TARGET_PROFIT_PERCENT = 2.0  # Target profit % in spot mode
SPOT_MAX_CONCURRENT_TRADES = 2  # Fewer concurrent trades in spot
SPOT_MAX_CONCURRENT_COINS = 2
SPOT_MAX_LOSS_STREAK = 5  # More lenient loss streak in spot
SPOT_TRADING_PAUSE_HOURS = 0.5  # Shorter pause in spot mode
SPOT_ALLOW_SHORT = False  # Disable short selling in spot mode

# Risk Management - FUTURES
FUTURES_STOP_LOSS_PERCENT = 2.0  # Default stop loss %
FUTURES_TAKE_PROFIT_1_USDT = 2.0  # First take profit level
FUTURES_TAKE_PROFIT_2_USDT = 3.5  # Second take profit level
FUTURES_TRAILING_STOP_ACTIVATION_USDT = 1.5  # Activate trailing stop after this profit
FUTURES_TIMEOUT_NO_MOVEMENT_MINUTES = 7  # Close trade if no movement after this time

# Risk Management - SPOT
SPOT_STOP_LOSS_PERCENT = 4.0  # Softer stop loss for spot (no liquidation risk)
SPOT_TAKE_PROFIT_1_PERCENT = 1.5  # First take profit % in spot
SPOT_TAKE_PROFIT_2_PERCENT = 3.0  # Second take profit % in spot
SPOT_TRAILING_STOP_ACTIVATION_PERCENT = 2.0  # Activate trailing stop after this % profit
SPOT_TIMEOUT_NO_MOVEMENT_MINUTES = 15  # Longer timeout for spot (slower movements)

# Analysis Settings
ANALYSIS_INTERVAL_MINUTES = 15
PRICE_UPDATE_INTERVAL_SECONDS = 5

# Indicator Parameters
EMA_PERIODS = [50, 100, 200]
EMA_ADAPTIVE_RANGE = (40, 60)
ADX_PERIOD = 14
ADX_THRESHOLD = 25
ADX_ADAPTIVE_RANGE = (20, 30)
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
RSI_PERIOD = 14
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30
BOLLINGER_PERIOD = 20
BOLLINGER_STD = 2
ATR_PERIOD = 14

# Market Phase Thresholds
LONG_PHASE_MIN_ADX = 25
SHORT_PHASE_MIN_ADX = 25
RANGE_PHASE_MAX_ADX = 20
RANGE_PHASE_PRICE_DEVIATION = 0.02  # ±2% from EMA200
RANGE_PHASE_MACD_THRESHOLD = 0.5

# Coin Selection Filters - FUTURES (balance >= 500 USDT)
FUTURES_MIN_VOLUME_24H_USDT = 10000000  # Minimum 10M USDT for futures (more lenient)
FUTURES_MIN_VOLATILITY_24H = 0.02  # Minimum 2% change for futures
FUTURES_MAX_VOLATILITY_24H = 0.15  # Maximum 15% change for futures (higher volatility accepted)

# Coin Selection Filters - SPOT (balance < 500 USDT)
SPOT_MIN_VOLUME_24H_USDT = 50000000  # Minimum 50M USDT for spot
SPOT_MIN_VOLATILITY_24H = 0.03  # Minimum 3% change for spot
SPOT_MAX_VOLATILITY_24H = 0.08  # Maximum 8% change for spot

# General filters (used if mode-specific not available)
MIN_VOLUME_24H_USDT = 50000000  # Default: 50M USDT
MAX_SPREAD_PERCENT = 0.1  # Maximum bid-ask spread
MIN_VOLATILITY_24H = 0.03  # Minimum 3% change
MAX_VOLATILITY_24H = 0.08  # Maximum 8% change
MIN_CORRELATION_BTC = 0.3
MAX_CORRELATION_BTC = 0.8
TOP_COINS_TO_SELECT = 3  # Number of top coins to select for trading

# Dynamic Symbol Fetching Settings
FETCH_SYMBOLS_ENABLED = True  # Enable automatic symbol fetching from Bybit
SYMBOL_FETCH_CATEGORY = "spot"  # Category: "spot" or "linear" (futures)
SYMBOL_FILTER_BY_QUOTE = "USDT"  # Filter symbols by quote currency (e.g., "USDT", "USD")
MIN_SYMBOL_PRICE = 0.0001  # Minimum symbol price to exclude very cheap coins
SORT_BY_INDICATOR = "volume24h"  # Indicator for sorting: "volume24h", "price_change_pct", "turnover_rate"
TOP_SYMBOLS_TO_FETCH = 30  # Number of top symbols to fetch from Bybit (can be changed anytime)

# Logging
LOG_LEVEL = "INFO"
LOG_FILE = "logs/trading_bot.log"

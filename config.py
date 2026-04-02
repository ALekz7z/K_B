"""
Configuration module for MEXC Trading Bot.
All trading parameters and constants are defined here.
"""

import os
from dotenv import load_dotenv
from typing import List, Set

# Load environment variables
load_dotenv()


class Config:
    """
    Configuration class containing all bot settings.
    Loads values from environment variables with sensible defaults.
    """
    
    # API Credentials
    MEXC_API_KEY: str = os.getenv("MEXC_API_KEY", "")
    MEXC_SECRET_KEY: str = os.getenv("MEXC_SECRET_KEY", "")
    
    # Telegram Settings (Optional)
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")
    
    # Trading Mode
    PAPER_TRADING: bool = os.getenv("PAPER_TRADING", "True").lower() == "true"
    
    # Risk Management
    MAX_POSITION_SIZE: float = float(os.getenv("MAX_POSITION_SIZE", "10"))
    MAX_DAILY_LOSS: float = float(os.getenv("MAX_DAILY_LOSS", "5"))
    STOP_LOSS_PERCENT: float = float(os.getenv("STOP_LOSS_PERCENT", "2")) / 100
    MAX_CONCURRENT_POSITIONS: int = int(os.getenv("MAX_CONCURRENT_POSITIONS", "2"))
    
    # Strategy Parameters
    MIN_SPREAD_PERCENT: float = float(os.getenv("MIN_SPREAD_PERCENT", "1.5")) / 100
    MIN_24H_VOLUME: float = float(os.getenv("MIN_24H_VOLUME", "50000"))
    ORDER_TIMEOUT: int = int(os.getenv("ORDER_TIMEOUT", "600"))
    POLLING_INTERVAL: float = float(os.getenv("POLLING_INTERVAL", "5"))
    
    # Fees
    FEE_PERCENT: float = float(os.getenv("FEE_PERCENT", "0")) / 100
    
    # Excluded coins (top 20 by volume)
    EXCLUDED_COINS: Set[str] = set(
        os.getenv("EXCLUDED_COINS", "BTC,ETH,SOL,BNB,XRP,ADA,DOGE,AVAX,DOT,MATIC,LINK,LTC,UNI,ATOM,ETC,FIL,NEAR,ALGO,VET,ICP").split(",")
    )
    
    # Order book settings
    ORDER_BOOK_DEPTH: int = 20
    MIN_ORDERBOOK_VOLUME_USDT: float = 10.0
    
    # Price change threshold (exclude pumps/dumps)
    MAX_PRICE_CHANGE_PERCENT: float = 15.0 / 100
    
    @classmethod
    def validate(cls) -> bool:
        """
        Validate that required configuration is present.
        
        Returns:
            bool: True if configuration is valid, False otherwise.
        """
        # In paper trading mode, API keys are not required
        if cls.PAPER_TRADING:
            return True
        
        # In live trading mode, API keys are required
        if not cls.MEXC_API_KEY or cls.MEXC_API_KEY == "your_api_key_here":
            return False
        if not cls.MEXC_SECRET_KEY or cls.MEXC_SECRET_KEY == "your_secret_key_here":
            return False
        return True
    
    @classmethod
    def get_excluded_coins(cls) -> Set[str]:
        """
        Get the set of excluded coin symbols.
        
        Returns:
            Set[str]: Set of coin symbols to exclude from trading.
        """
        return cls.EXCLUDED_COINS

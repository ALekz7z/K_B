"""
Risk Manager module for MEXC Trading Bot.
Handles all risk management logic including position limits, daily loss limits, and balance checks.
"""

import asyncio
from datetime import datetime, timezone
from typing import Dict, Optional
from decimal import Decimal

from config import Config
from logger import BotLogger


class RiskManager:
    """
    Risk management class that validates all trading actions.
    Ensures safe trading within defined risk parameters.
    """
    
    def __init__(self, logger: BotLogger):
        """
        Initialize the Risk Manager.
        
        Args:
            logger: Logger instance for recording risk events.
        """
        self.logger = logger
        self.daily_loss = 0.0
        self.daily_loss_reset_time = datetime.now(timezone.utc).date()
        self.open_positions: Dict[str, Dict] = {}
        self.total_traded_today = 0.0
        self._last_balance_check = None
        self._balance_cache = None
        self._balance_cache_time = 0
        
    def reset_daily_loss_if_new_day(self) -> None:
        """
        Reset daily loss counter if a new day has started (UTC).
        """
        current_date = datetime.now(timezone.utc).date()
        if current_date > self.daily_loss_reset_time:
            self.logger.info(f"New trading day started. Resetting daily loss counter.")
            self.daily_loss = 0.0
            self.daily_loss_reset_time = current_date
            self.total_traded_today = 0.0
    
    def check_daily_loss_limit(self) -> bool:
        """
        Check if daily loss limit has been reached.
        
        Returns:
            bool: True if trading can continue, False if limit reached.
        """
        self.reset_daily_loss_if_new_day()
        
        if self.daily_loss >= Config.MAX_DAILY_LOSS:
            self.logger.warning(
                f"Daily loss limit reached! Current loss: ${self.daily_loss:.2f}, "
                f"Limit: ${Config.MAX_DAILY_LOSS:.2f}. Trading halted until 00:00 UTC."
            )
            return False
        return True
    
    def add_loss(self, loss_amount: float) -> None:
        """
        Record a loss amount.
        
        Args:
            loss_amount: The amount of loss in USDT.
        """
        if loss_amount > 0:
            self.daily_loss += loss_amount
            self.logger.info(f"Recorded loss: ${loss_amount:.2f}. Total daily loss: ${self.daily_loss:.2f}")
    
    def add_profit(self, profit_amount: float) -> None:
        """
        Record a profit amount (reduces daily loss counter).
        
        Args:
            profit_amount: The amount of profit in USDT.
        """
        if profit_amount > 0:
            self.daily_loss -= profit_amount
            if self.daily_loss < 0:
                self.daily_loss = 0.0
            self.logger.info(f"Recorded profit: ${profit_amount:.2f}. Total daily loss: ${self.daily_loss:.2f}")
    
    def check_position_size(self, order_value_usdt: float) -> bool:
        """
        Check if order size is within limits.
        
        Args:
            order_value_usdt: The value of the order in USDT.
            
        Returns:
            bool: True if order size is acceptable, False otherwise.
        """
        if order_value_usdt > Config.MAX_POSITION_SIZE:
            self.logger.warning(
                f"Order size ${order_value_usdt:.2f} exceeds maximum position size "
                f"${Config.MAX_POSITION_SIZE:.2f}"
            )
            return False
        return True
    
    def check_concurrent_positions(self) -> bool:
        """
        Check if we can open more positions.
        
        Returns:
            bool: True if under the limit, False if max positions reached.
        """
        if len(self.open_positions) >= Config.MAX_CONCURRENT_POSITIONS:
            self.logger.warning(
                f"Maximum concurrent positions ({Config.MAX_CONCURRENT_POSITIONS}) reached"
            )
            return False
        return True
    
    def check_balance_sufficient(self, balance_usdt: float, required_usdt: float) -> bool:
        """
        Check if balance is sufficient for the trade.
        
        Args:
            balance_usdt: Current USDT balance.
            required_usdt: Required USDT for the trade.
            
        Returns:
            bool: True if balance is sufficient, False otherwise.
        """
        # Minimum balance threshold to continue trading
        min_balance = 5.0
        
        if balance_usdt < min_balance:
            self.logger.critical(
                f"Insufficient balance! Current: ${balance_usdt:.2f}, "
                f"Minimum required: ${min_balance:.2f}. Stopping trading."
            )
            return False
        
        if balance_usdt < required_usdt:
            self.logger.warning(
                f"Insufficient balance for this trade. Available: ${balance_usdt:.2f}, "
                f"Required: ${required_usdt:.2f}"
            )
            return False
        
        return True
    
    def add_position(self, pair: str, position_data: Dict) -> None:
        """
        Add an open position to tracking.
        
        Args:
            pair: Trading pair symbol.
            position_data: Dictionary containing position details.
        """
        self.open_positions[pair] = position_data
        self.logger.info(f"Position opened: {pair}. Total open positions: {len(self.open_positions)}")
    
    def remove_position(self, pair: str) -> Optional[Dict]:
        """
        Remove a closed position from tracking.
        
        Args:
            pair: Trading pair symbol.
            
        Returns:
            Optional[Dict]: Position data if found, None otherwise.
        """
        position = self.open_positions.pop(pair, None)
        if position:
            self.logger.info(
                f"Position closed: {pair}. Remaining open positions: {len(self.open_positions)}"
            )
        return position
    
    def get_open_positions_count(self) -> int:
        """
        Get the number of currently open positions.
        
        Returns:
            int: Number of open positions.
        """
        return len(self.open_positions)
    
    def is_pair_already_trading(self, pair: str) -> bool:
        """
        Check if we already have an open position for this pair.
        
        Args:
            pair: Trading pair symbol.
            
        Returns:
            bool: True if pair is already being traded, False otherwise.
        """
        return pair in self.open_positions
    
    def validate_trade(self, pair: str, order_value_usdt: float, balance_usdt: float) -> bool:
        """
        Perform comprehensive trade validation.
        
        Args:
            pair: Trading pair symbol.
            order_value_usdt: Order value in USDT.
            balance_usdt: Current USDT balance.
            
        Returns:
            bool: True if trade is valid, False otherwise.
        """
        # Check daily loss limit
        if not self.check_daily_loss_limit():
            return False
        
        # Check concurrent positions
        if not self.check_concurrent_positions():
            return False
        
        # Check if already trading this pair
        if self.is_pair_already_trading(pair):
            self.logger.warning(f"Already have an open position for {pair}")
            return False
        
        # Check position size
        if not self.check_position_size(order_value_usdt):
            return False
        
        # Check balance
        if not self.check_balance_sufficient(balance_usdt, order_value_usdt):
            return False
        
        return True
    
    async def check_connection_timeout(self, last_api_call_time: float) -> bool:
        """
        Check if connection to exchange has been lost.
        
        Args:
            last_api_call_time: Timestamp of last successful API call.
            
        Returns:
            bool: True if connection is OK, False if timeout exceeded.
        """
        timeout_threshold = 60  # 1 minute
        current_time = asyncio.get_event_loop().time()
        
        if current_time - last_api_call_time > timeout_threshold:
            self.logger.error(
                f"Connection timeout! No successful API calls for {current_time - last_api_call_time:.0f} seconds"
            )
            return False
        return True
    
    def get_daily_statistics(self) -> Dict:
        """
        Get daily trading statistics.
        
        Returns:
            Dict: Dictionary containing daily stats.
        """
        return {
            "daily_loss": self.daily_loss,
            "daily_loss_limit": Config.MAX_DAILY_LOSS,
            "open_positions": len(self.open_positions),
            "max_positions": Config.MAX_CONCURRENT_POSITIONS,
            "total_traded_today": self.total_traded_today
        }

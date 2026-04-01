"""
Logging module for MEXC Trading Bot.
Handles console and file logging with proper formatting.
"""

import logging
import os
from datetime import datetime
from typing import Optional


class BotLogger:
    """
    Custom logger class for the trading bot.
    Provides structured logging to both console and file.
    """
    
    def __init__(self, name: str = "MEXC_BOT", log_dir: str = "logs"):
        """
        Initialize the logger.
        
        Args:
            name: Logger name identifier.
            log_dir: Directory to store log files.
        """
        self.name = name
        self.log_dir = log_dir
        
        # Create logs directory if it doesn't exist
        os.makedirs(log_dir, exist_ok=True)
        
        # Generate log filename with date
        log_filename = f"{log_dir}/bot_log_{datetime.now().strftime('%Y%m%d')}.txt"
        
        # Create logger
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)
        
        # Clear existing handlers
        self.logger.handlers.clear()
        
        # File handler - detailed logs
        file_handler = logging.FileHandler(log_filename, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_format = logging.Formatter(
            '[%(asctime)s] [%(levelname)s] [%(module)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_format)
        
        # Console handler - info and above
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_format = logging.Formatter(
            '[%(asctime)s] [%(levelname)s] %(message)s',
            datefmt='%H:%M:%S'
        )
        console_handler.setFormatter(console_format)
        
        # Add handlers
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)
    
    def info(self, message: str) -> None:
        """
        Log an info message.
        
        Args:
            message: Message to log.
        """
        self.logger.info(message)
    
    def warning(self, message: str) -> None:
        """
        Log a warning message.
        
        Args:
            message: Message to log.
        """
        self.logger.warning(message)
    
    def error(self, message: str) -> None:
        """
        Log an error message.
        
        Args:
            message: Message to log.
        """
        self.logger.error(message)
    
    def debug(self, message: str) -> None:
        """
        Log a debug message.
        
        Args:
            message: Message to log.
        """
        self.logger.debug(message)
    
    def critical(self, message: str) -> None:
        """
        Log a critical message.
        
        Args:
            message: Message to log.
        """
        self.logger.critical(message)
    
    def get_logger(self) -> logging.Logger:
        """
        Get the underlying logger instance.
        
        Returns:
            logging.Logger: The configured logger instance.
        """
        return self.logger

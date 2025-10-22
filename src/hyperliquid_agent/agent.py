"""Main trading agent orchestration."""

import logging
import time
from pathlib import Path
from typing import Callable, NoReturn, TypeVar

from hyperliquid_agent.config import Config
from hyperliquid_agent.decision import DecisionEngine, PromptTemplate
from hyperliquid_agent.executor import TradeExecutor
from hyperliquid_agent.monitor import PositionMonitor

T = TypeVar("T")


def retry_with_backoff(
    func: Callable[[], T], max_retries: int, backoff_base: float
) -> T:
    """Retry a function with exponential backoff.

    Args:
        func: Function to retry
        max_retries: Maximum number of retry attempts
        backoff_base: Base for exponential backoff calculation

    Returns:
        Result of the function call

    Raises:
        Exception: If all retries are exhausted
    """
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            wait_time = backoff_base**attempt
            logging.getLogger(__name__).warning(
                f"Attempt {attempt + 1}/{max_retries} failed: {e}. "
                f"Retrying in {wait_time:.1f}s..."
            )
            time.sleep(wait_time)
    # This should never be reached, but satisfies type checker
    raise RuntimeError("Retry logic failed unexpectedly")


class TradingAgent:
    """Main trading agent that orchestrates the trading loop."""

    def __init__(self, config: Config) -> None:
        """Initialize the trading agent.

        Args:
            config: Config instance
        """
        self.config = config
        self.logger = self._setup_logging()
        
        # Initialize all components
        self.monitor = PositionMonitor(config.hyperliquid)
        
        prompt_template = PromptTemplate(config.agent.prompt_template_path)
        self.decision_engine = DecisionEngine(config.llm, prompt_template)
        
        self.executor = TradeExecutor(config.hyperliquid)
        
        # Initialize tick counter
        self.tick_count = 0
        self.last_portfolio_value: float | None = None

    def run(self) -> NoReturn:
        """Run the main agent loop indefinitely."""
        self.logger.info(
            "Starting trading agent",
            extra={
                "tick_interval": self.config.agent.tick_interval_seconds,
                "max_retries": self.config.agent.max_retries,
                "log_level": self.config.agent.log_level,
            },
        )
        
        while True:
            try:
                self._execute_tick()
            except Exception as e:
                self.logger.error(
                    f"Tick {self.tick_count} failed with unhandled exception",
                    exc_info=e,
                    extra={"tick": self.tick_count},
                )
            
            # Sleep until next tick
            time.sleep(self.config.agent.tick_interval_seconds)

    def _execute_tick(self) -> None:
        """Execute one iteration of the trading loop."""
        self.tick_count += 1
        self.logger.info(f"Starting tick {self.tick_count}", extra={"tick": self.tick_count})
        
        # Step 1: Monitor positions with retry logic
        try:
            account_state = retry_with_backoff(
                self.monitor.get_current_state,
                self.config.agent.max_retries,
                self.config.agent.retry_backoff_base,
            )
        except Exception as e:
            self.logger.error(
                "Failed to retrieve account state after retries",
                exc_info=e,
                extra={"tick": self.tick_count},
            )
            return
        
        # Log account state
        self.logger.info(
            "Account state retrieved",
            extra={
                "tick": self.tick_count,
                "portfolio_value": account_state.portfolio_value,
                "available_balance": account_state.available_balance,
                "num_positions": len(account_state.positions),
                "is_stale": account_state.is_stale,
            },
        )
        
        # Log portfolio value change
        if self.last_portfolio_value is not None:
            value_change = account_state.portfolio_value - self.last_portfolio_value
            pct_change = (
                (value_change / self.last_portfolio_value * 100)
                if self.last_portfolio_value != 0
                else 0.0
            )
            self.logger.info(
                "Portfolio value change",
                extra={
                    "tick": self.tick_count,
                    "previous_value": self.last_portfolio_value,
                    "current_value": account_state.portfolio_value,
                    "change": value_change,
                    "change_pct": pct_change,
                },
            )
        
        self.last_portfolio_value = account_state.portfolio_value
        
        # Step 2: Get decision from LLM
        decision = self.decision_engine.get_decision(account_state)
        
        if not decision.success:
            self.logger.error(
                f"Decision engine failed: {decision.error}",
                extra={"tick": self.tick_count, "error": decision.error},
            )
            return
        
        self.logger.info(
            f"Decision received: {len(decision.actions)} actions",
            extra={
                "tick": self.tick_count,
                "num_actions": len(decision.actions),
                "selected_strategy": decision.selected_strategy,
            },
        )
        
        # Step 3: Execute trades with retry logic
        for i, action in enumerate(decision.actions):
            self.logger.info(
                f"Executing action {i + 1}/{len(decision.actions)}",
                extra={
                    "tick": self.tick_count,
                    "action_type": action.action_type,
                    "coin": action.coin,
                    "market_type": action.market_type,
                    "size": action.size,
                    "price": action.price,
                    "reasoning": action.reasoning,
                },
            )
            
            try:
                result = retry_with_backoff(
                    lambda: self.executor.execute_action(action),
                    self.config.agent.max_retries,
                    self.config.agent.retry_backoff_base,
                )
            except Exception as e:
                self.logger.error(
                    f"Failed to execute action after retries: {action.action_type} {action.coin}",
                    exc_info=e,
                    extra={
                        "tick": self.tick_count,
                        "action_type": action.action_type,
                        "coin": action.coin,
                    },
                )
                continue
            
            # Log execution result
            log_level = logging.INFO if result.success else logging.ERROR
            self.logger.log(
                log_level,
                "Trade execution result",
                extra={
                    "tick": self.tick_count,
                    "action_type": action.action_type,
                    "coin": action.coin,
                    "market_type": action.market_type,
                    "success": result.success,
                    "order_id": result.order_id,
                    "error": result.error,
                },
            )
        
        self.logger.info(
            f"Tick {self.tick_count} completed",
            extra={"tick": self.tick_count, "actions_executed": len(decision.actions)},
        )

    def _setup_logging(self) -> logging.Logger:
        """Configure structured logging.

        Returns:
            Configured logger instance
        """
        # Create logger
        logger = logging.getLogger("hyperliquid_agent")
        logger.setLevel(self.config.agent.log_level)
        
        # Remove existing handlers to avoid duplicates
        logger.handlers.clear()
        
        # Create formatters
        # Use JSON-like structured format for file logs
        file_formatter = logging.Formatter(
            '{"timestamp": "%(asctime)s", "level": "%(levelname)s", '
            '"logger": "%(name)s", "message": "%(message)s"%(extra)s}',
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
        
        # Use simpler format for console
        console_formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        )
        
        # Create logs directory if it doesn't exist
        logs_dir = Path("logs")
        logs_dir.mkdir(exist_ok=True)
        
        # File handler
        file_handler = logging.FileHandler(logs_dir / "agent.log")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)
        
        return logger

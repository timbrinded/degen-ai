"""Main trading agent orchestration."""

import json
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any, NoReturn, TypeVar

from colorama import Fore, Style, init
from hyperliquid.info import Info

from hyperliquid_agent.config import Config
from hyperliquid_agent.decision import DecisionEngine, PromptTemplate
from hyperliquid_agent.executor import TradeExecutor
from hyperliquid_agent.funding import FundingPlanner
from hyperliquid_agent.market_registry import MarketRegistry
from hyperliquid_agent.monitor import PositionMonitor
from hyperliquid_agent.portfolio import PortfolioRebalancer, PortfolioState, TargetAllocation

# Initialize colorama for cross-platform colored output
init(autoreset=True)

T = TypeVar("T")


class ColoredConsoleFormatter(logging.Formatter):
    """Custom formatter that outputs colored logs for console."""

    COLORS = {
        "DEBUG": Fore.CYAN,
        "INFO": Fore.GREEN,
        "WARNING": Fore.YELLOW,
        "ERROR": Fore.RED,
        "CRITICAL": Fore.RED + Style.BRIGHT,
    }

    def format(self, record: logging.LogRecord) -> str:
        """Format log record with colors.

        Args:
            record: Log record to format

        Returns:
            Colored log string
        """
        level_color = self.COLORS.get(record.levelname, "")
        record.levelname = f"{level_color}{record.levelname}{Style.RESET_ALL}"
        return super().format(record)


class JSONFormatter(logging.Formatter):
    """Custom formatter that outputs logs as valid JSON."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON.

        Args:
            record: Log record to format

        Returns:
            JSON-formatted log string
        """
        log_data: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add extra fields if present
        if hasattr(record, "tick"):
            log_data["tick"] = record.tick
        if hasattr(record, "portfolio_value"):
            log_data["portfolio_value"] = record.portfolio_value
        if hasattr(record, "available_balance"):
            log_data["available_balance"] = record.available_balance
        if hasattr(record, "num_positions"):
            log_data["num_positions"] = record.num_positions
        if hasattr(record, "is_stale"):
            log_data["is_stale"] = record.is_stale
        if hasattr(record, "previous_value"):
            log_data["previous_value"] = record.previous_value
        if hasattr(record, "current_value"):
            log_data["current_value"] = record.current_value
        if hasattr(record, "change"):
            log_data["change"] = record.change
        if hasattr(record, "change_pct"):
            log_data["change_pct"] = record.change_pct
        if hasattr(record, "num_actions"):
            log_data["num_actions"] = record.num_actions
        if hasattr(record, "selected_strategy"):
            log_data["selected_strategy"] = record.selected_strategy
        if hasattr(record, "action_type"):
            log_data["action_type"] = record.action_type
        if hasattr(record, "coin"):
            log_data["coin"] = record.coin
        if hasattr(record, "market_type"):
            log_data["market_type"] = record.market_type
        if hasattr(record, "size"):
            log_data["size"] = record.size
        if hasattr(record, "price"):
            log_data["price"] = record.price
        if hasattr(record, "reasoning"):
            log_data["reasoning"] = record.reasoning
        if hasattr(record, "success"):
            log_data["success"] = record.success
        if hasattr(record, "order_id"):
            log_data["order_id"] = record.order_id
        if hasattr(record, "error"):
            log_data["error"] = record.error
        if hasattr(record, "actions_executed"):
            log_data["actions_executed"] = record.actions_executed
        if hasattr(record, "tick_interval"):
            log_data["tick_interval"] = record.tick_interval
        if hasattr(record, "max_retries"):
            log_data["max_retries"] = record.max_retries
        if hasattr(record, "log_level"):
            log_data["log_level"] = record.log_level
        if hasattr(record, "llm_response_length"):
            log_data["llm_response_length"] = record.llm_response_length
        if hasattr(record, "llm_actions_count"):
            log_data["llm_actions_count"] = record.llm_actions_count
        if hasattr(record, "llm_input_tokens"):
            log_data["llm_input_tokens"] = record.llm_input_tokens
        if hasattr(record, "llm_output_tokens"):
            log_data["llm_output_tokens"] = record.llm_output_tokens
        if hasattr(record, "llm_cost_usd"):
            log_data["llm_cost_usd"] = record.llm_cost_usd
        if hasattr(record, "llm_total_cost_usd"):
            log_data["llm_total_cost_usd"] = record.llm_total_cost_usd
        if hasattr(record, "llm_total_calls"):
            log_data["llm_total_calls"] = record.llm_total_calls

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data)


def retry_with_backoff(func: Callable[[], T], max_retries: int, backoff_base: float) -> T:
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
                f"Attempt {attempt + 1}/{max_retries} failed: {e}. Retrying in {wait_time:.1f}s..."
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

        # Initialize market registry
        info = Info(config.hyperliquid.base_url, skip_ws=True)
        self.registry = MarketRegistry(info)

        self.executor = TradeExecutor(config.hyperliquid, self.registry)

        # Initialize portfolio rebalancer
        self.rebalancer = PortfolioRebalancer(
            min_trade_value=10.0,
            max_slippage_pct=0.005,
            rebalance_threshold=0.05,
        )

        # Funding planner for deterministic wallet transfers
        self.funding_planner = FundingPlanner(config.risk, self.executor, self.logger)

        # Initialize tick counter
        self.tick_count = 0
        self.last_portfolio_value: float | None = None

    def run(self) -> NoReturn:
        """Run the main agent loop indefinitely."""
        import asyncio

        # Hydrate market registry before starting the loop
        asyncio.run(self.registry.hydrate())

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

        # Log LLM response summary with cost tracking
        self.logger.info(
            f"LLM Response Summary: {len(decision.actions)} actions proposed, "
            f"response length: {len(decision.raw_response)} chars, "
            f"tokens: {decision.input_tokens}→{decision.output_tokens}, "
            f"cost: ${decision.cost_usd:.6f}",
            extra={
                "tick": self.tick_count,
                "llm_response_length": len(decision.raw_response),
                "llm_actions_count": len(decision.actions),
                "llm_input_tokens": decision.input_tokens,
                "llm_output_tokens": decision.output_tokens,
                "llm_cost_usd": decision.cost_usd,
            },
        )

        # Log running total cost
        self.logger.info(
            f"LLM Running Total: {self.decision_engine.total_calls} calls, "
            f"${self.decision_engine.total_cost_usd:.6f} total cost",
            extra={
                "tick": self.tick_count,
                "llm_total_cost_usd": self.decision_engine.total_cost_usd,
                "llm_total_calls": self.decision_engine.total_calls,
            },
        )

        # Log strategy being followed
        if decision.selected_strategy:
            self.logger.info(
                f"Strategy Selected: {decision.selected_strategy}",
                extra={
                    "tick": self.tick_count,
                    "selected_strategy": decision.selected_strategy,
                },
            )
        else:
            self.logger.info(
                "No specific strategy selected - using general decision making",
                extra={"tick": self.tick_count},
            )

        # Step 2.5: If LLM provided target allocation, generate rebalancing plan
        actions_to_execute = decision.actions

        if decision.target_allocation:
            self.logger.info(
                f"Target allocation provided: {decision.target_allocation}",
                extra={"tick": self.tick_count},
            )

            # Convert account state to portfolio state
            portfolio_state = PortfolioState.from_account_state(account_state)

            # Create target allocation object
            target = TargetAllocation(
                allocations=decision.target_allocation,
                strategy_id=decision.selected_strategy,
            )

            # Generate rebalancing plan
            plan = self.rebalancer.create_rebalancing_plan(portfolio_state, target)

            self.logger.info(
                f"Rebalancing plan generated: {len(plan.actions)} actions, "
                f"estimated cost: ${plan.estimated_cost:.2f}",
                extra={
                    "tick": self.tick_count,
                    "num_rebalance_actions": len(plan.actions),
                    "estimated_cost": plan.estimated_cost,
                },
            )

            if plan.reasoning:
                self.logger.info(
                    f"Rebalancing reasoning: {plan.reasoning}",
                    extra={"tick": self.tick_count},
                )

            # Use rebalancing plan actions instead of direct LLM actions
            actions_to_execute = plan.actions

        funding_result = self.funding_planner.plan(account_state, actions_to_execute)
        actions_to_execute = funding_result.actions

        if funding_result.inserted_transfers:
            self.logger.info(
                "Funding planner inserted %s transfer actions",
                funding_result.inserted_transfers,
                extra={
                    "tick": self.tick_count,
                    "inserted_transfers": funding_result.inserted_transfers,
                },
            )

        for message in funding_result.clamped_transfers:
            self.logger.warning(
                "Funding planner clamped transfer: %s",
                message,
                extra={"tick": self.tick_count},
            )

        for message in funding_result.skipped_actions:
            self.logger.warning(
                "Funding planner skipped action: %s",
                message,
                extra={"tick": self.tick_count},
            )

        self.logger.info(
            f"Decision received: {len(actions_to_execute)} actions to execute",
            extra={
                "tick": self.tick_count,
                "num_actions": len(actions_to_execute),
                "selected_strategy": decision.selected_strategy,
            },
        )

        # Step 3: Execute trades with retry logic
        for i, action in enumerate(actions_to_execute):
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
                    partial(self.executor.execute_action, action),
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
            extra={"tick": self.tick_count, "actions_executed": len(actions_to_execute)},
        )

    def _setup_logging(self) -> logging.Logger:
        """Configure structured logging with JSON format for files and human-readable format for console.

        Returns:
            Configured logger instance
        """
        # Create logger
        logger = logging.getLogger("hyperliquid_agent")
        logger.setLevel(self.config.agent.log_level)

        # Remove existing handlers to avoid duplicates
        logger.handlers.clear()

        # Prevent propagation to root logger
        logger.propagate = False

        # Create logs directory if it doesn't exist
        logs_dir = Path("logs")
        logs_dir.mkdir(exist_ok=True)

        # File handler with structured JSON logging
        file_handler = logging.FileHandler(logs_dir / "agent.log")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(JSONFormatter())
        logger.addHandler(file_handler)

        # Console handler with colored human-readable format
        console_handler = logging.StreamHandler()
        # Use the same log level as the logger for console output
        console_handler.setLevel(self.config.agent.log_level)
        console_formatter = ColoredConsoleFormatter(
            "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        )
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

        return logger

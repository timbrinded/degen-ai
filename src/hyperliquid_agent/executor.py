"""Trade execution on Hyperliquid."""

from dataclasses import dataclass
from typing import Any


@dataclass
class ExecutionResult:
    """Result of a trade execution."""

    action: Any  # TradeAction
    success: bool
    order_id: str | None = None
    error: str | None = None


class TradeExecutor:
    """Executes trades on Hyperliquid."""

    def __init__(self, config) -> None:
        """Initialize the trade executor.

        Args:
            config: HyperliquidConfig instance
        """
        # TODO: Initialize Hyperliquid Exchange client
        raise NotImplementedError("TradeExecutor not yet implemented")

    def execute_action(self, action) -> ExecutionResult:
        """Execute a single trade action.

        Args:
            action: TradeAction instance

        Returns:
            Execution result
        """
        # TODO: Implement execution logic
        raise NotImplementedError("Execution logic not yet implemented")

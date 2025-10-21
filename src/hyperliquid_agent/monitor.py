"""Position monitoring and account state retrieval."""

from dataclasses import dataclass
from typing import Literal


@dataclass
class Position:
    """Represents a trading position."""

    coin: str
    size: float
    entry_price: float
    current_price: float
    unrealized_pnl: float
    market_type: Literal["spot", "perp"]


@dataclass
class AccountState:
    """Current account state snapshot."""

    portfolio_value: float
    available_balance: float
    positions: list[Position]
    timestamp: float
    is_stale: bool = False


class PositionMonitor:
    """Monitors positions and retrieves account state from Hyperliquid."""

    def __init__(self, config) -> None:
        """Initialize the position monitor.

        Args:
            config: HyperliquidConfig instance
        """
        # TODO: Initialize Hyperliquid Info client
        raise NotImplementedError("PositionMonitor not yet implemented")

    def get_current_state(self) -> AccountState:
        """Retrieve current account state from Hyperliquid.

        Returns:
            Current account state

        Raises:
            Exception: If unable to retrieve state and no cached state available
        """
        # TODO: Implement state retrieval
        raise NotImplementedError("State retrieval not yet implemented")

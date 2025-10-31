"""Position monitoring and account state retrieval."""

import time
from dataclasses import dataclass
from typing import Literal

from hyperliquid.info import Info

from hyperliquid_agent.config import HyperliquidConfig


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
    available_balance: float  # Perp margin balance
    positions: list[Position]
    spot_balances: dict[str, float]  # coin -> balance (e.g., {"USDC": 100.0})
    timestamp: float
    is_stale: bool = False


class PositionMonitor:
    """Monitors positions and retrieves account state from Hyperliquid."""

    def __init__(self, config: HyperliquidConfig) -> None:
        """Initialize the position monitor.

        Args:
            config: HyperliquidConfig instance
        """
        self.info = Info(config.base_url, skip_ws=True)
        self.account_address = config.account_address
        self.last_valid_state: AccountState | None = None

    def get_current_state(self) -> AccountState:
        """Retrieve current account state from Hyperliquid.

        Returns:
            Current account state

        Raises:
            Exception: If unable to retrieve state and no cached state available
        """
        try:
            user_state = self.info.user_state(self.account_address)
            spot_state = self.info.spot_user_state(self.account_address)
            state = self._parse_user_state(user_state, spot_state)
            self.last_valid_state = state
            return state
        except Exception as e:
            # Return last known state with staleness flag if available
            if self.last_valid_state:
                self.last_valid_state.is_stale = True
                return self.last_valid_state
            raise Exception(
                f"Failed to retrieve account state and no cached state available: {e}"
            ) from e

    def _parse_user_state(self, raw_state: dict, spot_state: dict) -> AccountState:
        """Parse Hyperliquid API response into AccountState.

        Args:
            raw_state: Raw API response from user_state endpoint (perp)
            spot_state: Raw API response from spot_user_state endpoint

        Returns:
            Parsed AccountState object
        """
        # Extract account value and margin summary
        margin_summary = raw_state.get("marginSummary", {})
        account_value = float(margin_summary.get("accountValue", 0.0))

        # Extract withdrawable balance (available balance for perp)
        withdrawable = float(raw_state.get("withdrawable", 0.0))

        # Parse spot balances
        spot_balances: dict[str, float] = {}
        balances = spot_state.get("balances", [])
        for balance in balances:
            coin = balance.get("coin", "")
            total = float(balance.get("total", 0.0))
            if total > 0:
                spot_balances[coin] = total

        # Calculate total spot value (for now, just USDC since it's 1:1)
        spot_value = spot_balances.get("USDC", 0.0)

        # Parse positions from assetPositions (perp positions)
        positions = []
        asset_positions = raw_state.get("assetPositions", [])

        for asset_pos in asset_positions:
            position_data = asset_pos.get("position", {})
            coin = position_data.get("coin", "")

            # Skip if no position size
            size_str = position_data.get("szi", "0")
            size = float(size_str)
            if size == 0:
                continue

            # Extract position details
            entry_price = float(position_data.get("entryPx", 0.0))

            # Get current price from position data or mark price
            mark_px = float(position_data.get("positionValue", 0.0))
            current_price = abs(mark_px / size) if size != 0 and mark_px != 0 else entry_price

            # Extract unrealized PnL
            unrealized_pnl = float(position_data.get("unrealizedPnl", 0.0))

            # Determine market type (perp is default for Hyperliquid positions)
            market_type: Literal["spot", "perp"] = "perp"

            positions.append(
                Position(
                    coin=coin,
                    size=abs(size),  # Use absolute value for size
                    entry_price=entry_price,
                    current_price=current_price,
                    unrealized_pnl=unrealized_pnl,
                    market_type=market_type,
                )
            )

        # Add spot balances as Position objects (excluding USDC which is cash)
        for coin, size in spot_balances.items():
            if coin == "USDC":
                continue  # USDC is cash, not a position

            # For spot positions, we need to fetch current price
            # For now, use a simple approach: spot positions have no unrealized PnL tracking
            # The agent will see the position and can make decisions based on it
            # Entry price is unknown for existing balances, so we use 0.0
            positions.append(
                Position(
                    coin=coin,
                    size=size,
                    entry_price=0.0,  # Unknown for existing spot balances
                    current_price=0.0,  # Will be fetched by monitor_enhanced if needed
                    unrealized_pnl=0.0,  # Unknown without entry price
                    market_type="spot",
                )
            )

        # Total portfolio value includes perp account value + spot balances
        total_portfolio_value = account_value + spot_value

        return AccountState(
            portfolio_value=total_portfolio_value,
            available_balance=withdrawable,
            positions=positions,
            spot_balances=spot_balances,
            timestamp=time.time(),
            is_stale=False,
        )

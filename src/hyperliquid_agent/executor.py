"""Trade execution module for submitting orders to Hyperliquid."""

import logging
from dataclasses import dataclass

import eth_account
from eth_account.signers.local import LocalAccount

from hyperliquid.exchange import Exchange
from hyperliquid.info import Info

from hyperliquid_agent.config import HyperliquidConfig
from hyperliquid_agent.decision import TradeAction


@dataclass
class ExecutionResult:
    """Result of a trade execution attempt."""

    action: TradeAction
    success: bool
    order_id: str | None = None
    error: str | None = None


class TradeExecutor:
    """Executes trades on Hyperliquid platform."""

    def __init__(self, config: HyperliquidConfig) -> None:
        """Initialize the trade executor.

        Args:
            config: Hyperliquid configuration with credentials
        """
        self.config = config
        account: LocalAccount = eth_account.Account.from_key(config.secret_key)  # type: ignore[misc]
        self.exchange = Exchange(
            account_address=config.account_address,
            wallet=account,
            base_url=config.base_url,
        )
        self.logger = logging.getLogger(__name__)

    def execute_action(self, action: TradeAction) -> ExecutionResult:
        """Execute a single trade action.

        Args:
            action: Trade action to execute

        Returns:
            Execution result with success status and details
        """
        try:
            # Validate action parameters
            if not self._validate_action(action):
                return ExecutionResult(
                    action=action, success=False, error="Invalid action parameters"
                )

            # Handle hold action (no-op)
            if action.action_type == "hold":
                self.logger.info(f"Hold action for {action.coin}, no order submitted")
                return ExecutionResult(action=action, success=True)

            # Submit order to Hyperliquid
            result = self._submit_order(action)

            # Extract order ID from response
            order_id = None
            if isinstance(result, dict):
                status = result.get("status", {})
                if isinstance(status, dict):
                    resting = status.get("resting")
                    if isinstance(resting, dict):
                        order_id = resting.get("oid")

            self.logger.info(
                f"Order executed: {action.action_type} {action.size} {action.coin} "
                f"on {action.market_type} market, order_id={order_id}"
            )

            return ExecutionResult(action=action, success=True, order_id=order_id)

        except Exception as e:
            error_msg = str(e)
            self.logger.error(
                f"Failed to execute {action.action_type} {action.coin}: {error_msg}",
                exc_info=True,
            )
            return ExecutionResult(action=action, success=False, error=error_msg)

    def _validate_action(self, action: TradeAction) -> bool:
        """Validate action parameters before submission.

        Args:
            action: Trade action to validate

        Returns:
            True if action is valid, False otherwise
        """
        # Check action type
        if action.action_type not in ["buy", "sell", "hold", "close"]:
            self.logger.error(f"Invalid action type: {action.action_type}")
            return False

        # Check coin is specified
        if not action.coin:
            self.logger.error("Coin not specified in action")
            return False

        # Check market type
        if action.market_type not in ["spot", "perp"]:
            self.logger.error(f"Invalid market type: {action.market_type}")
            return False

        # For buy/sell actions, size must be specified and positive
        if action.action_type in ["buy", "sell"] and (action.size is None or action.size <= 0):
            self.logger.error(f"Invalid size for {action.action_type}: {action.size}")
            return False

        # For close actions, size is optional (will close entire position)
        # Price is optional (None means market order)

        return True

    def _submit_order(self, action: TradeAction) -> dict:
        """Submit order to Hyperliquid API.

        Args:
            action: Trade action to submit

        Returns:
            API response dictionary

        Raises:
            Exception: If order submission fails
        """
        is_buy = action.action_type in ["buy", "close"]

        # Handle close action
        if action.action_type == "close":
            # Close position by selling (for long) or buying (for short)
            # For simplicity, we'll use market order to close
            # Size should be the position size (caller should provide this)
            if action.size is None:
                raise ValueError("Size must be specified for close action")

            # Submit market order to close
            return self.exchange.market_open(
                name=action.coin,
                is_buy=is_buy,
                sz=action.size,
                px=None,  # Market order
            )

        # Handle buy/sell actions
        if action.size is None:
            raise ValueError(f"Size must be specified for {action.action_type} action")

        # Market order (price is None)
        if action.price is None:
            return self.exchange.market_open(
                name=action.coin,
                is_buy=is_buy,
                sz=action.size,
                px=None,
            )

        # Limit order
        return self.exchange.order(
            name=action.coin,
            is_buy=is_buy,
            sz=action.size,
            limit_px=action.price,
            order_type={"limit": {"tif": "Gtc"}},  # Good-til-cancel
        )

"""Wallet funding planner for coordinating spot/perp transfers."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace

from hyperliquid_agent.config import RiskConfig
from hyperliquid_agent.decision import TradeAction
from hyperliquid_agent.executor import TradeExecutor
from hyperliquid_agent.monitor import AccountState


@dataclass
class FundingPlanResult:
    """Summary of funding adjustments applied to an action queue."""

    actions: list[TradeAction]
    inserted_transfers: int = 0
    skipped_actions: list[str] = field(default_factory=list)
    clamped_transfers: list[str] = field(default_factory=list)


class FundingPlanner:
    """Injects deterministic wallet transfers to safely fund spot trades."""

    def __init__(
        self,
        risk_config: RiskConfig,
        executor: TradeExecutor,
        logger: logging.Logger | None = None,
    ) -> None:
        self.risk_config = risk_config
        self.executor = executor
        self.logger = logger or logging.getLogger(__name__)

    def plan(self, account_state: AccountState, actions: list[TradeAction]) -> FundingPlanResult:
        """Return new action list with safe transfer actions inserted or adjusted."""

        if not self.risk_config.enable_auto_transfers or not actions:
            return FundingPlanResult(actions=list(actions))

        # Simulated wallet balances as we step through proposed actions.
        spot_usdc = float(account_state.spot_balances.get("USDC", 0.0))
        perp_withdrawable = float(account_state.available_balance)
        account_value = float(account_state.account_value or 0.0)
        total_initial_margin = float(account_state.total_initial_margin or 0.0)

        if account_value <= 0.0:
            # Fall back to withdrawable + initial margin when account value is missing
            account_value = perp_withdrawable + total_initial_margin

        required_capital = max(
            total_initial_margin * self.risk_config.target_initial_margin_ratio,
            self.risk_config.min_perp_balance_usd,
        )

        planned_actions: list[TradeAction] = []
        inserted_transfers = 0
        skipped: list[str] = []
        clamped: list[str] = []

        # Phase 1 – refill perp wallet if under the required buffer.
        perp_deficit = max(0.0, required_capital - account_value)
        if perp_deficit > 0.0:
            reclaimable = max(0.0, spot_usdc - self.risk_config.target_spot_usdc_buffer_usd)
            reclaim_amount = min(perp_deficit, reclaimable)
            if reclaim_amount > 0.0:
                planned_actions.append(
                    TradeAction(
                        action_type="transfer",
                        coin="USDC",
                        market_type="perp",
                        size=reclaim_amount,
                        reasoning="Auto-transfer to restore perp margin buffer",
                    )
                )
                inserted_transfers += 1
                spot_usdc -= reclaim_amount
                perp_withdrawable += reclaim_amount
                account_value += reclaim_amount

        for action in actions:
            if action.action_type == "transfer":
                adjusted, clamp_reason = self._process_existing_transfer(
                    action,
                    required_capital,
                    account_value,
                    perp_withdrawable,
                    spot_usdc,
                )

                if adjusted is None:
                    skipped.append(
                        f"transfer {action.size} {action.coin} -> {action.market_type} skipped (insufficient funds)"
                    )
                    continue

                if clamp_reason:
                    clamped.append(clamp_reason)

                action = adjusted

                if action.market_type == "spot":
                    perp_withdrawable -= action.size or 0.0
                    account_value -= action.size or 0.0
                    spot_usdc += action.size or 0.0
                else:
                    spot_usdc -= action.size or 0.0
                    perp_withdrawable += action.size or 0.0
                    account_value += action.size or 0.0

                planned_actions.append(action)
                continue

            if action.market_type != "spot" or action.action_type not in {"buy", "sell"}:
                planned_actions.append(action)
                continue

            notional = self._estimate_notional(action)
            if action.action_type == "buy":
                spot_requirement = notional + self.risk_config.target_spot_usdc_buffer_usd
                deficit = max(0.0, spot_requirement - spot_usdc)

                if deficit > 0.0:
                    safe_transferable = self._safe_transferable(
                        required_capital, account_value, perp_withdrawable
                    )
                    transfer_amount = min(deficit, safe_transferable)

                    if transfer_amount > 0.0:
                        planned_actions.append(
                            TradeAction(
                                action_type="transfer",
                                coin="USDC",
                                market_type="spot",
                                size=transfer_amount,
                                reasoning=f"Auto-transfer to fund spot buy of {action.coin}",
                            )
                        )
                        inserted_transfers += 1
                        perp_withdrawable -= transfer_amount
                        account_value -= transfer_amount
                        spot_usdc += transfer_amount
                        deficit = max(0.0, deficit - transfer_amount)

                if deficit > 0.0:
                    skipped.append(
                        f"spot buy {action.coin} size={action.size} skipped (deficit={deficit:.2f} USDC)"
                    )
                    self.logger.warning(
                        "Skipping spot buy for %s: need %.2f USDC, transferable %.2f",
                        action.coin,
                        notional + self.risk_config.target_spot_usdc_buffer_usd,
                        self._safe_transferable(required_capital, account_value, perp_withdrawable),
                    )
                    continue

                spot_usdc -= notional
                planned_actions.append(action)

            else:  # spot sell
                spot_usdc += notional
                planned_actions.append(action)

        return FundingPlanResult(
            actions=planned_actions,
            inserted_transfers=inserted_transfers,
            skipped_actions=skipped,
            clamped_transfers=clamped,
        )

    def _process_existing_transfer(
        self,
        action: TradeAction,
        required_capital: float,
        account_value: float,
        perp_withdrawable: float,
        spot_usdc: float,
    ) -> tuple[TradeAction | None, str | None]:
        """Validate a transfer provided by the LLM."""

        size = action.size or 0.0
        if size <= 0.0:
            return None, None

        if action.market_type == "spot":
            safe_transferable = self._safe_transferable(
                required_capital, account_value, perp_withdrawable
            )
            if safe_transferable <= 0.0:
                return None, None

            if size > safe_transferable:
                clamped_action = replace(action, size=safe_transferable)
                reason = f"transfer to spot clamped from {size:.2f} to {safe_transferable:.2f} (safety buffer)"
                self.logger.warning(
                    "Clamping transfer to spot: requested %.2f exceeds safe limit %.2f",
                    size,
                    safe_transferable,
                )
                return clamped_action, reason

            return action, None

        # transfer back to perp wallet
        max_to_perp = max(0.0, spot_usdc - self.risk_config.target_spot_usdc_buffer_usd)
        if max_to_perp <= 0.0:
            return None, None

        if size > max_to_perp:
            clamped_action = replace(action, size=max_to_perp)
            reason = f"transfer to perp clamped from {size:.2f} to {max_to_perp:.2f} (spot buffer)"
            self.logger.warning(
                "Clamping transfer to perp: requested %.2f exceeds available %.2f",
                size,
                max_to_perp,
            )
            return clamped_action, reason

        return action, None

    def _safe_transferable(
        self, required_capital: float, account_value: float, perp_withdrawable: float
    ) -> float:
        """Return the maximum USD that can be moved from perp to spot."""

        headroom = max(0.0, account_value - required_capital)
        return max(0.0, min(perp_withdrawable, headroom))

    def _estimate_notional(self, action: TradeAction) -> float:
        """Estimate notional value for a spot trade."""

        if not action.size:
            return 0.0

        price = action.price
        if price is None:
            try:
                market_name = self.executor._get_market_name(action.coin, action.market_type)
                reference = self.executor._get_reference_price(
                    action.coin, action.market_type, market_name
                )
                price = float(reference)
            except Exception as exc:  # pragma: no cover - defensive logging
                self.logger.debug(
                    "Failed to fetch reference price for %s %s trade: %s",
                    action.coin,
                    action.market_type,
                    exc,
                )
                price = 0.0

        return float(action.size) * max(float(price or 0.0), 0.0)

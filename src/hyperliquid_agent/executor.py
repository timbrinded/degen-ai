"""Trade execution module for submitting orders to Hyperliquid."""

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import ROUND_DOWN, ROUND_UP, Decimal
from typing import Any

import eth_account
from eth_account.signers.local import LocalAccount
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info

from hyperliquid_agent.asset_identity import AssetIdentity
from hyperliquid_agent.config import HyperliquidConfig
from hyperliquid_agent.decision import TradeAction
from hyperliquid_agent.identity_registry import AssetIdentityRegistry
from hyperliquid_agent.market_registry import MarketRegistry


@dataclass
class ExecutionResult:
    """Result of a trade execution attempt."""

    action: TradeAction
    success: bool
    order_id: str | None = None
    error: str | None = None


class TradeExecutor:
    """Executes trades on Hyperliquid platform."""

    MIN_NOTIONAL_USDC = Decimal("5")

    def __init__(
        self,
        config: HyperliquidConfig,
        registry: MarketRegistry,
        *,
        identity_registry: AssetIdentityRegistry | None = None,
    ) -> None:
        """Initialize the trade executor.

        Args:
            config: Hyperliquid configuration with credentials
            registry: Market registry for symbol resolution (must be hydrated)
        """
        self.logger = logging.getLogger(__name__)
        self.config = config
        self.registry = registry
        self.identity_registry = identity_registry
        account: LocalAccount = eth_account.Account.from_key(config.secret_key)  # type: ignore[misc]

        # Initialize Info first to get spot metadata
        self.info = Info(config.base_url, skip_ws=True)
        spot_meta = self._load_spot_metadata()

        self.exchange = Exchange(
            account_address=config.account_address,
            wallet=account,
            base_url=config.base_url,
            spot_meta=spot_meta,  # type: ignore[arg-type]  # Pass spot metadata
        )

        self._asset_metadata_cache: dict[str, Any] = {}

    def _load_spot_metadata(self) -> dict[str, Any]:
        spot_meta = self.info.spot_meta()

        if not isinstance(spot_meta, dict):
            raise RuntimeError("Invalid spot metadata format returned by Hyperliquid")

        universe = spot_meta.get("universe")
        if not isinstance(universe, list):
            raise RuntimeError("Spot metadata missing 'universe' list")

        self.logger.debug("Spot metadata keys: %s", list(spot_meta.keys()))

        market_count = len(universe)
        self.logger.info("Loaded %s spot markets from Hyperliquid", market_count)

        if market_count == 0:
            self.logger.warning(
                "No spot markets found in metadata - spot trading may be unavailable"
            )
        else:
            sample = [market.get("name", "unknown") for market in universe[:5]]
            self.logger.debug("Sample spot markets: %s", sample)

        return spot_meta

    def execute_action(self, action: TradeAction) -> ExecutionResult:
        """Execute a single trade action.

        Args:
            action: Trade action to execute

        Returns:
            Execution result with success status and details
        """
        try:
            if not self._validate_action(action):
                return ExecutionResult(
                    action=action, success=False, error="Invalid action parameters"
                )

            handlers = {
                "hold": self._execute_hold,
                "transfer": self._execute_transfer,
            }
            handler = handlers.get(action.action_type, self._execute_trade)
            return handler(action)

        except Exception as e:
            error_msg = str(e)
            self.logger.error(
                f"Failed to execute {action.action_type} {action.coin}: {error_msg}",
                exc_info=True,
            )
            return ExecutionResult(action=action, success=False, error=error_msg)

    def _execute_hold(self, action: TradeAction) -> ExecutionResult:
        self.logger.info(f"Hold action for {action.coin}, no order submitted")
        return ExecutionResult(action=action, success=True)

    def _execute_transfer(self, action: TradeAction) -> ExecutionResult:
        self._submit_transfer(action)
        direction = "TO SPOT" if action.market_type == "spot" else "TO PERP"
        self.logger.info(f"Transfer executed: {action.size} {action.coin} [{direction}]")
        return ExecutionResult(action=action, success=True)

    def _execute_trade(self, action: TradeAction) -> ExecutionResult:
        response = self._submit_order(action)
        order_id = self._extract_order_id(response)

        self.logger.info(
            "Order executed: %s %s %s [%s MARKET], order_id=%s",
            action.action_type.upper(),
            action.size,
            action.coin,
            action.market_type.upper(),
            order_id,
        )

        return ExecutionResult(action=action, success=True, order_id=order_id)

    @staticmethod
    def _extract_order_id(response: Any) -> str | None:
        if not isinstance(response, dict):
            return None

        status = response.get("status")
        if not isinstance(status, dict):
            return None

        resting = status.get("resting")
        if isinstance(resting, dict):
            return resting.get("oid")

        return None

    def _get_asset_metadata(self, coin: str) -> Any:
        if coin in self._asset_metadata_cache:
            return self._asset_metadata_cache[coin]

        try:
            meta = self.info.meta()
            universe = meta.get("universe", [])

            for asset in universe:
                if asset.get("name") == coin:
                    self._asset_metadata_cache[coin] = asset
                    return asset

            raise ValueError(f"Asset {coin} not found in universe")
        except Exception as e:
            self.logger.error(f"Failed to get metadata for {coin}: {e}")
            raise

    def _round_size(self, size: float, coin: str, market_type: str) -> float:
        try:
            # Use registry to get sz_decimals
            sz_decimals = self.registry.get_sz_decimals(coin, market_type)  # type: ignore

            # Use Decimal for precise rounding
            size_decimal = Decimal(str(size))

            # Round down to szDecimals places
            quantizer = Decimal(10) ** -sz_decimals
            rounded = size_decimal.quantize(quantizer, rounding=ROUND_DOWN)

            result = float(rounded)

            if result != size:
                self.logger.debug(
                    f"Rounded {coin} size from {size} to {result} (szDecimals={sz_decimals})"
                )

            return result
        except Exception as e:
            self.logger.warning(f"Failed to round size for {coin}, using original value: {e}")
            return size

    def _get_reference_price(self, coin: str, market_type: str, market_name: str) -> Decimal:
        try:
            if market_type == "spot":
                return self._spot_reference_price(coin, market_name)

            return self._perp_reference_price(coin)

        except Exception as exc:
            raise ValueError(
                f"Unable to determine reference price for {coin} ({market_type})"
            ) from exc

    def _spot_reference_price(self, coin: str, market_name: str) -> Decimal:
        identifier_candidates: set[str] = {market_name.upper()}

        try:
            spot_info = self.registry.get_spot_market_info(  # type: ignore[attr-defined]
                coin,
                market_identifier=market_name,
            )
        except Exception as resolver_err:
            self.logger.debug(
                "Failed to resolve spot market info for %s (%s): %s",
                coin,
                market_name,
                resolver_err,
            )
            spot_info = None

        if spot_info:
            identifier_candidates.add(spot_info.market_name.upper())
            if spot_info.native_symbol:
                identifier_candidates.add(spot_info.native_symbol.upper())
            identifier_candidates.update(alias.upper() for alias in spot_info.aliases if alias)

        _, spot_ctxs = self.info.spot_meta_and_asset_ctxs()
        ctx_lookup = {
            ctx_coin.upper(): ctx
            for ctx in spot_ctxs
            if (ctx_coin := ctx.get("coin")) and isinstance(ctx_coin, str)
        }

        for identifier in identifier_candidates:
            price = self._ctx_price(ctx_lookup.get(identifier))
            if price is not None:
                return price

        self.logger.warning(
            "Spot reference price lookup failed for %s (%s). Candidates: %s. Available keys: %s",
            coin,
            market_name,
            sorted(identifier_candidates),
            sorted(ctx_lookup.keys())[:10],
        )
        raise ValueError(f"Spot reference price not found for market {market_name}")

    def _perp_reference_price(self, coin: str) -> Decimal:
        meta, perp_ctxs = self.info.meta_and_asset_ctxs()
        universe = meta.get("universe", [])

        for asset, ctx in zip(universe, perp_ctxs, strict=False):
            if asset.get("name") != coin:
                continue

            price = self._ctx_price(ctx)
            if price is not None:
                return price
            break

        raise ValueError(f"Perp reference price not found for coin {coin}")

    @staticmethod
    def _ctx_price(ctx: Mapping[str, Any] | None) -> Decimal | None:
        if not ctx:
            return None

        for key in ("markPx", "midPx"):
            price_str = ctx.get(key)
            if not price_str:
                continue
            price = Decimal(price_str)
            if price > 0:
                return price

        return None

    def _ensure_min_notional(
        self, size: float, reference_price: Decimal, coin: str, market_type: str
    ) -> float:
        if reference_price <= 0:
            raise ValueError(f"Invalid reference price {reference_price} for {coin}")

        size_decimal = Decimal(str(size))
        notional = size_decimal * reference_price

        if notional >= self.MIN_NOTIONAL_USDC:
            return size

        sz_decimals = self.registry.get_sz_decimals(coin, market_type)  # type: ignore
        quantizer = Decimal(10) ** -sz_decimals

        min_size = (self.MIN_NOTIONAL_USDC / reference_price).quantize(quantizer, rounding=ROUND_UP)

        adjusted_size = max(min_size, size_decimal).quantize(quantizer, rounding=ROUND_UP)

        if adjusted_size <= 0:
            raise ValueError(f"Adjusted order size is non-positive for {coin}")

        if adjusted_size != size_decimal:
            self.logger.info(
                "Adjusted %s order size from %s to %s to satisfy %s USDC minimum notional",
                market_type,
                size_decimal,
                adjusted_size,
                self.MIN_NOTIONAL_USDC,
            )

        return float(adjusted_size)

    def _get_market_name(
        self,
        coin: str,
        market_type: str,
        *,
        identity: AssetIdentity | None = None,
        native_symbol: str | None = None,
    ) -> str:
        self.logger.debug(f"Resolving market name for coin='{coin}', market_type='{market_type}'")

        resolved_identity = identity

        if self.identity_registry:
            if resolved_identity is None:
                resolved_identity = self.identity_registry.resolve(coin)
            if resolved_identity is None and native_symbol:
                resolved_identity = self.identity_registry.resolve(native_symbol)
            if resolved_identity is None and coin.upper().startswith("U"):
                resolved_identity = self.identity_registry.resolve(coin[1:])

            if resolved_identity:
                if market_type == "spot":
                    descriptor = self.identity_registry.get_spot_market(resolved_identity)
                    if descriptor and descriptor.display_symbol:
                        return descriptor.display_symbol
                elif market_type == "perp":
                    descriptor = self.identity_registry.get_perp_market(resolved_identity)
                    if descriptor and descriptor.display_symbol:
                        return descriptor.display_symbol

        try:
            market_name = self.registry.get_market_name(coin, market_type)  # type: ignore
            self.logger.debug(
                f"Market name resolved: coin='{coin}', market_type='{market_type}' -> '{market_name}'"
            )
            return market_name
        except ValueError as e:
            self.logger.error(f"Market name resolution failed: {e}")
            raise

    def _validate_action(self, action: TradeAction) -> bool:
        if action.action_type not in {"buy", "sell", "hold", "close", "transfer"}:
            self.logger.error(f"Invalid action type: {action.action_type}")
            return False

        if not action.coin:
            self.logger.error("Coin not specified in action")
            return False

        if action.market_type not in {"spot", "perp"}:
            self.logger.error(f"Invalid market type: {action.market_type}")
            return False

        if action.action_type in {"buy", "sell", "transfer"} and (
            action.size is None or action.size <= 0
        ):
            self.logger.error(f"Invalid size for {action.action_type}: {action.size}")
            return False

        if action.action_type == "close" and action.size is not None and action.size <= 0:
            self.logger.error(f"Invalid size for close: {action.size}")
            return False

        return True

    def _submit_order(self, action: TradeAction) -> dict:
        is_buy = action.action_type in {"buy", "close"}
        market_name = self._get_market_name(
            action.coin,
            action.market_type,
            identity=getattr(action, "asset_identity", None),
            native_symbol=getattr(action, "native_symbol", None),
        )

        self.logger.debug(
            "Submitting %s %s order for '%s'",
            action.market_type.upper(),
            action.action_type,
            market_name,
        )

        if action.action_type == "close":
            return self._submit_close_order(action, market_name, is_buy)

        size = self._require_size(action.size, action.action_type)
        rounded_size = self._round_size(size, action.coin, action.market_type)
        reference_price = self._reference_price_for(action, market_name)
        adjusted_size, _ = self._apply_min_notional(action, rounded_size, reference_price)

        if action.price is None:
            return self._submit_market_order(action, market_name, is_buy, adjusted_size)

        return self._submit_limit_order(action, market_name, is_buy, adjusted_size)

    def _submit_close_order(self, action: TradeAction, market_name: str, is_buy: bool) -> dict:
        size = self._require_size(action.size, "close")
        rounded_size = self._round_size(size, action.coin, action.market_type)
        reference_price = self._reference_price_for(action, market_name)
        adjusted_size, min_enforced = self._apply_min_notional(
            action,
            rounded_size,
            reference_price,
        )

        if min_enforced and action.market_type == "spot":
            raise ValueError(
                f"Cannot close {action.coin} spot position below {self.MIN_NOTIONAL_USDC} USDC notional"
            )

        if min_enforced and action.market_type == "perp":
            return self._submit_reduce_only_close(
                action,
                market_name,
                is_buy,
                adjusted_size,
                reference_price,
            )

        return self._submit_market_order(action, market_name, is_buy, adjusted_size)

    def _submit_reduce_only_close(
        self,
        action: TradeAction,
        market_name: str,
        is_buy: bool,
        size: float,
        reference_price: Decimal,
    ) -> dict:
        limit_price = float(reference_price)
        if hasattr(self.exchange, "_slippage_price"):
            try:
                limit_price = float(
                    self.exchange._slippage_price(
                        market_name,
                        is_buy,
                        0.05,
                        float(reference_price),
                    )
                )
            except Exception as err:  # pragma: no cover - debug logging only
                self.logger.debug(
                    "Falling back to reference price for reduce-only close: %s",
                    err,
                )

        self.logger.info(
            "Perp CLOSE reduce-only order -> market=%s, is_buy=%s, size=%s, limit_px=%s",
            market_name,
            is_buy,
            size,
            limit_price,
        )

        return self.exchange.order(
            name=market_name,
            is_buy=is_buy,
            sz=size,
            limit_px=limit_price,
            order_type={"limit": {"tif": "Ioc"}},
            reduce_only=True,
        )

    @staticmethod
    def _require_size(size: float | None, label: str) -> float:
        if size is None:
            raise ValueError(f"Size must be specified for {label} action")
        return size

    def _reference_price_for(self, action: TradeAction, market_name: str) -> Decimal:
        if action.price is not None:
            return Decimal(str(action.price))
        return self._get_reference_price(action.coin, action.market_type, market_name)

    def _apply_min_notional(
        self, action: TradeAction, size: float, reference_price: Decimal
    ) -> tuple[float, bool]:
        adjusted = self._ensure_min_notional(
            size,
            reference_price,
            action.coin,
            action.market_type,
        )

        changed = Decimal(str(adjusted)) > Decimal(str(size))
        return adjusted, changed

    def _submit_market_order(
        self,
        action: TradeAction,
        market_name: str,
        is_buy: bool,
        size: float,
    ) -> dict:
        label = action.action_type.upper()
        if action.market_type == "spot":
            self.logger.info(
                "Spot %s market order -> market=%s, is_buy=%s, size=%s",
                label,
                market_name,
                is_buy,
                size,
            )

        response = self.exchange.market_open(
            name=market_name,
            is_buy=is_buy,
            sz=size,
            px=None,
        )

        if action.market_type == "spot":
            self.logger.info("Spot %s market order response: %s", label, response)

        return response

    def _submit_limit_order(
        self,
        action: TradeAction,
        market_name: str,
        is_buy: bool,
        size: float,
    ) -> dict:
        if action.price is None:
            raise ValueError("Limit order requires a price")

        label = action.action_type.upper()
        if action.market_type == "spot":
            self.logger.info(
                "Spot %s limit order -> market=%s, is_buy=%s, size=%s, limit_px=%s",
                label,
                market_name,
                is_buy,
                size,
                action.price,
            )

        response = self.exchange.order(
            name=market_name,
            is_buy=is_buy,
            sz=size,
            limit_px=action.price,
            order_type={"limit": {"tif": "Gtc"}},
        )

        if action.market_type == "spot":
            self.logger.info("Spot %s limit order response: %s", label, response)

        return response

    def _submit_transfer(self, action: TradeAction) -> dict:
        """Submit transfer between spot and perp wallets.

        Args:
            action: Transfer action (market_type indicates destination)

        Returns:
            API response dictionary

        Raises:
            Exception: If transfer submission fails
        """
        if action.size is None:
            raise ValueError("Size must be specified for transfer action")

        # Determine transfer direction based on market_type
        # market_type "spot" means transfer TO spot (from perp)
        # market_type "perp" means transfer TO perp (from spot)
        to_perp = action.market_type == "perp"

        # Submit transfer using usd_class_transfer
        # This transfers USDC between spot and perp wallets
        return self.exchange.usd_class_transfer(
            amount=action.size,
            to_perp=to_perp,
        )

"""Trade execution module for submitting orders to Hyperliquid."""

import logging
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

        # Get spot metadata for Exchange to support spot trading
        spot_meta = self.info.spot_meta()

        # Validate spot_meta structure
        if not spot_meta:
            raise RuntimeError("Failed to fetch spot metadata from Hyperliquid: spot_meta is empty")

        if not isinstance(spot_meta, dict):
            raise RuntimeError(
                f"Invalid spot metadata format: expected dict, got {type(spot_meta).__name__}"
            )

        # Check for universe data
        universe = spot_meta.get("universe")
        if universe is None:
            raise RuntimeError(
                "Spot metadata is malformed: missing 'universe' field. "
                f"Available fields: {list(spot_meta.keys())}"
            )

        if not isinstance(universe, list):
            raise RuntimeError(
                f"Spot metadata is malformed: 'universe' should be a list, got {type(universe).__name__}"
            )

        # Log spot metadata structure for debugging
        self.logger.debug(f"Spot metadata structure: {list(spot_meta.keys())}")
        self.logger.debug(f"Spot metadata universe length: {len(universe)}")

        # Log number of spot markets loaded
        num_spot_markets = len(universe)
        self.logger.info(f"Loaded {num_spot_markets} spot markets from Hyperliquid")

        if num_spot_markets == 0:
            self.logger.warning(
                "No spot markets found in metadata - spot trading may not be available"
            )

        # Log sample of available spot markets for debugging
        if num_spot_markets > 0:
            sample_markets = [market.get("name", "unknown") for market in universe[:5]]
            self.logger.debug(f"Sample spot markets: {sample_markets}")

        self.exchange = Exchange(
            account_address=config.account_address,
            wallet=account,
            base_url=config.base_url,
            spot_meta=spot_meta,  # type: ignore[arg-type]  # Pass spot metadata
        )

        self._asset_metadata_cache: dict[str, Any] = {}

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

            # Handle transfer action
            if action.action_type == "transfer":
                result = self._submit_transfer(action)
                direction = "TO SPOT" if action.market_type == "spot" else "TO PERP"
                self.logger.info(f"Transfer executed: {action.size} {action.coin} [{direction}]")
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
                f"Order executed: {action.action_type.upper()} {action.size} {action.coin} "
                f"[{action.market_type.upper()} MARKET], order_id={order_id}"
            )

            return ExecutionResult(action=action, success=True, order_id=order_id)

        except Exception as e:
            error_msg = str(e)
            self.logger.error(
                f"Failed to execute {action.action_type} {action.coin}: {error_msg}",
                exc_info=True,
            )
            return ExecutionResult(action=action, success=False, error=error_msg)

    def _get_asset_metadata(self, coin: str) -> Any:
        """Get asset metadata including szDecimals.

        Args:
            coin: Asset symbol (e.g., 'BTC', 'ETH')

        Returns:
            Asset metadata dictionary

        Raises:
            ValueError: If asset not found
        """
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
        """Round size to conform to asset's szDecimals requirement.

        Args:
            size: Raw size value
            coin: Asset symbol
            market_type: "spot" or "perp"

        Returns:
            Rounded size that conforms to exchange requirements
        """
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
        """Fetch reference price for notional enforcement.

        Args:
            coin: Base asset symbol
            market_type: "spot" or "perp"
            market_name: Resolved market identifier (used for spot markets)

        Returns:
            Decimal price in USDC terms

        Raises:
            ValueError: If the price cannot be determined
        """

        try:
            if market_type == "spot":
                identifier_candidates: set[str] = {market_name.upper()}
                spot_info = None

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

                if spot_info:
                    identifier_candidates.add(spot_info.market_name.upper())

                    if spot_info.native_symbol:
                        identifier_candidates.add(spot_info.native_symbol.upper())

                    for alias in spot_info.aliases:
                        if alias:
                            identifier_candidates.add(alias.upper())

                _, spot_ctxs = self.info.spot_meta_and_asset_ctxs()
                ctx_lookup = {
                    ctx_coin.upper(): ctx
                    for ctx in spot_ctxs
                    if (ctx_coin := ctx.get("coin")) and isinstance(ctx_coin, str)
                }

                for identifier in identifier_candidates:
                    ctx = ctx_lookup.get(identifier)
                    if not ctx:
                        continue

                    price_str = ctx.get("markPx") or ctx.get("midPx")
                    if price_str is None:
                        continue

                    price = Decimal(price_str)
                    if price <= 0:
                        continue

                    return price

                self.logger.warning(
                    "Spot reference price lookup failed for %s (%s). Candidates: %s."
                    " Available spot context keys: %s",
                    coin,
                    market_name,
                    sorted(identifier_candidates),
                    sorted(ctx_lookup.keys())[:10],
                )

                raise ValueError(f"Spot reference price not found for market {market_name}")

            meta, perp_ctxs = self.info.meta_and_asset_ctxs()
            universe = meta.get("universe", [])
            for asset, ctx in zip(universe, perp_ctxs, strict=False):
                if asset.get("name") == coin:
                    price_str = ctx.get("markPx") or ctx.get("midPx")
                    if price_str is None:
                        break
                    price = Decimal(price_str)
                    if price <= 0:
                        break
                    return price

            raise ValueError(f"Perp reference price not found for coin {coin}")

        except Exception as exc:
            raise ValueError(
                f"Unable to determine reference price for {coin} ({market_type})"
            ) from exc

    def _ensure_min_notional(
        self, size: float, reference_price: Decimal, coin: str, market_type: str
    ) -> float:
        """Ensure order notional meets exchange minimum requirements.

        Args:
            size: Current order size after rounding
            reference_price: Price estimate in USDC terms
            coin: Base asset symbol
            market_type: "spot" or "perp"

        Returns:
            Adjusted size respecting minimum notional

        Raises:
            ValueError: If a valid adjustment cannot be made
        """

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
        """Get market name using the centralized registry.

        Args:
            coin: Base coin symbol (e.g., 'ETH', 'BTC')
            market_type: 'spot' or 'perp'

        Returns:
            Market identifier for Hyperliquid SDK

        Raises:
            ValueError: If market not found in registry
        """
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
        """Validate action parameters before submission.

        Args:
            action: Trade action to validate

        Returns:
            True if action is valid, False otherwise
        """
        # Check action type
        if action.action_type not in ["buy", "sell", "hold", "close", "transfer"]:
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

        # For transfer actions, size must be specified and positive
        if action.action_type == "transfer" and (action.size is None or action.size <= 0):
            self.logger.error(f"Invalid size for transfer: {action.size}")
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

        # Format market name based on market type
        # SPOT: "ETH/USDC", PERP: "ETH"
        market_name = self._get_market_name(
            action.coin,
            action.market_type,
            identity=getattr(action, "asset_identity", None),
            native_symbol=getattr(action, "native_symbol", None),
        )

        self.logger.debug(
            f"Submitting {action.market_type.upper()} {action.action_type} order for '{market_name}'"
        )

        # Handle close action
        if action.action_type == "close":
            # Close position by selling (for long) or buying (for short)
            # For simplicity, we'll use market order to close
            # Size should be the position size (caller should provide this)
            if action.size is None:
                raise ValueError("Size must be specified for close action")

            # Round size to conform to exchange requirements
            rounded_size = self._round_size(action.size, action.coin, action.market_type)

            # Submit market order to close
            if action.market_type == "spot":
                self.logger.info(
                    "Spot CLOSE order -> market=%s, is_buy=%s, size=%s",
                    market_name,
                    is_buy,
                    rounded_size,
                )

            response = self.exchange.market_open(
                name=market_name,
                is_buy=is_buy,
                sz=rounded_size,
                px=None,  # Market order
            )

            if action.market_type == "spot":
                self.logger.info("Spot CLOSE order response: %s", response)

            return response

        # Handle buy/sell actions
        if action.size is None:
            raise ValueError(f"Size must be specified for {action.action_type} action")

        # Round size to conform to exchange requirements
        rounded_size = self._round_size(action.size, action.coin, action.market_type)

        if action.action_type in ["buy", "sell"]:
            # Determine reference price for notional calculation
            if action.price is not None:
                reference_price = Decimal(str(action.price))
            else:
                reference_price = self._get_reference_price(
                    action.coin, action.market_type, market_name
                )

            rounded_size = self._ensure_min_notional(
                rounded_size,
                reference_price,
                action.coin,
                action.market_type,
            )

        # Market order (price is None)
        if action.price is None:
            if action.market_type == "spot":
                self.logger.info(
                    "Spot %s market order -> market=%s, is_buy=%s, size=%s",
                    action.action_type.upper(),
                    market_name,
                    is_buy,
                    rounded_size,
                )

            response = self.exchange.market_open(
                name=market_name,
                is_buy=is_buy,
                sz=rounded_size,
                px=None,
            )

            if action.market_type == "spot":
                self.logger.info(
                    "Spot %s market order response: %s", action.action_type.upper(), response
                )

            return response

        # Limit order
        if action.market_type == "spot":
            self.logger.info(
                "Spot %s limit order -> market=%s, is_buy=%s, size=%s, limit_px=%s",
                action.action_type.upper(),
                market_name,
                is_buy,
                rounded_size,
                action.price,
            )

        response = self.exchange.order(
            name=market_name,
            is_buy=is_buy,
            sz=rounded_size,
            limit_px=action.price,
            order_type={"limit": {"tif": "Gtc"}},  # Good-til-cancel
        )

        if action.market_type == "spot":
            self.logger.info(
                "Spot %s limit order response: %s", action.action_type.upper(), response
            )

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

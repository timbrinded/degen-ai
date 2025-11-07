"""Position monitoring and account state retrieval."""

import logging
import time
from dataclasses import dataclass, field
from typing import Literal

from hyperliquid.info import Info

from hyperliquid_agent.asset_identity import AssetIdentity
from hyperliquid_agent.config import HyperliquidConfig
from hyperliquid_agent.identity_registry import AssetIdentityRegistry
from hyperliquid_agent.price_service import AssetPriceService


def _safe_float(value: float | int | str | None) -> float:
    """Convert value to float, returning 0.0 on failure."""

    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


@dataclass
class Position:
    """Represents a trading position."""

    coin: str
    size: float
    entry_price: float
    current_price: float
    unrealized_pnl: float
    market_type: Literal["spot", "perp"]
    asset_identity: AssetIdentity | None = None
    native_symbol: str | None = None


@dataclass
class AccountState:
    """Current account state snapshot."""

    portfolio_value: float
    available_balance: float  # Perp margin balance (withdrawable)
    positions: list[Position]
    timestamp: float
    spot_balances: dict[str, float] = field(default_factory=dict)
    account_value: float = 0.0
    total_initial_margin: float = 0.0
    total_maintenance_margin: float = 0.0
    margin_fraction: float | None = None
    is_stale: bool = False
    assets: dict[str, AssetIdentity] = field(default_factory=dict)


class PositionMonitor:
    """Monitors positions and retrieves account state from Hyperliquid."""

    def __init__(
        self,
        config: HyperliquidConfig,
        *,
        identity_registry: AssetIdentityRegistry | None = None,
        price_service: AssetPriceService | None = None,
    ) -> None:
        """Initialize the position monitor.

        Args:
            config: HyperliquidConfig instance
        """
        self.info = Info(config.base_url, skip_ws=True)
        self.account_address = config.account_address
        self.last_valid_state: AccountState | None = None
        self.logger = logging.getLogger(__name__)

        # Cache for spot mid-prices used to mark spot balances to market
        self._spot_price_cache: dict[str, float] = {}
        self._spot_price_cache_ts: float = 0.0
        self._spot_price_cache_ttl: float = 30.0  # seconds
        self.identity_registry = identity_registry
        self.price_service = price_service

        if self.price_service is None and self.identity_registry is not None:
            self.price_service = AssetPriceService(self.info, self.identity_registry)

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
        margin_summary = raw_state.get("marginSummary", {}) or {}
        account_value = _safe_float(margin_summary.get("accountValue"))

        total_initial_margin = _safe_float(
            margin_summary.get("totalInitialMargin")
            or margin_summary.get("totalInitialMarginUsed")
            or margin_summary.get("initialMargin")
        )

        total_maintenance_margin = _safe_float(
            margin_summary.get("totalMaintenanceMargin") or margin_summary.get("maintenanceMargin")
        )

        margin_fraction_raw = margin_summary.get("marginFraction")
        margin_fraction: float | None
        if margin_fraction_raw is None:
            margin_fraction = None
        else:
            try:
                margin_fraction = float(margin_fraction_raw)
            except (TypeError, ValueError):
                margin_fraction = None

        # Extract withdrawable balance (available balance for perp)
        withdrawable = _safe_float(raw_state.get("withdrawable", 0.0))

        # Parse spot balances and attempt to value them in USD terms
        spot_balances: dict[str, float] = {}
        spot_value = 0.0
        pending_spot_positions: list[Position] = []
        balances = spot_state.get("balances", [])
        for balance in balances:
            coin = balance.get("coin", "")
            total = _safe_float(balance.get("total", 0.0))
            if total <= 0:
                continue

            spot_balances[coin] = total

            identity: AssetIdentity | None = None
            if self.identity_registry:
                identity = self.identity_registry.resolve(coin)
                if not identity and coin.startswith("U"):
                    identity = self.identity_registry.resolve(coin[1:])

            usd_value = _safe_float(
                balance.get("usdValue")
                or balance.get("usd_value")
                or balance.get("usd")
                or balance.get("notional")
                or 0.0
            )
            price: float | None = None

            if usd_value > 0:
                price = usd_value / total if total > 0 else None
            else:
                price = self._get_spot_price(coin, identity)
                if price is not None:
                    usd_value = price * total

            if coin.upper() == "USDC" and usd_value <= 0:
                # Treat USDC at par if price metadata unavailable
                usd_value = total
                price = 1.0

            if usd_value > 0:
                spot_value += usd_value
            else:
                self.logger.debug("Unable to value spot asset %s; assuming zero", coin)

            if coin.upper() != "USDC":
                pending_spot_positions.append(
                    Position(
                        coin=coin,
                        size=total,
                        entry_price=price or 0.0,
                        current_price=price or 0.0,
                        unrealized_pnl=0.0,
                        market_type="spot",
                        asset_identity=identity,
                        native_symbol=coin,
                    )
                )

        # Parse positions from assetPositions (perp positions)
        positions = []
        asset_positions = raw_state.get("assetPositions", [])

        for asset_pos in asset_positions:
            position_data = asset_pos.get("position", {})
            coin = position_data.get("coin", "")

            # Skip if no position size
            size_str = position_data.get("szi", "0")
            size = _safe_float(size_str)
            if size == 0:
                continue

            # Extract position details
            entry_price = _safe_float(position_data.get("entryPx", 0.0))

            # Get current price from position data or mark price
            mark_px = _safe_float(position_data.get("positionValue", 0.0))
            current_price = abs(mark_px / size) if size != 0 and mark_px != 0 else entry_price

            # Extract unrealized PnL
            unrealized_pnl = _safe_float(position_data.get("unrealizedPnl", 0.0))

            # Determine market type (perp is default for Hyperliquid positions)
            market_type: Literal["spot", "perp"] = "perp"

            identity = self.identity_registry.resolve(coin) if self.identity_registry else None

            positions.append(
                Position(
                    coin=coin,
                    size=abs(size),  # Use absolute value for size
                    entry_price=entry_price,
                    current_price=current_price,
                    unrealized_pnl=unrealized_pnl,
                    market_type=market_type,
                    asset_identity=identity,
                    native_symbol=coin,
                )
            )

        # Append marked-to-market spot positions (excluding cash equivalent)
        positions.extend(pending_spot_positions)

        # Total portfolio value includes perp account value + spot balances
        total_portfolio_value = account_value + spot_value

        assets_map: dict[str, AssetIdentity] = {}
        if self.identity_registry:
            for position in positions:
                if position.asset_identity:
                    assets_map[position.asset_identity.canonical_symbol] = position.asset_identity
            for coin in spot_balances:
                identity = self.identity_registry.resolve(coin)
                if identity:
                    assets_map[identity.canonical_symbol] = identity

        return AccountState(
            portfolio_value=total_portfolio_value,
            available_balance=withdrawable,
            positions=positions,
            timestamp=time.time(),
            spot_balances=spot_balances,
            account_value=account_value,
            total_initial_margin=total_initial_margin,
            total_maintenance_margin=total_maintenance_margin,
            margin_fraction=margin_fraction,
            is_stale=False,
            assets=assets_map,
        )

    def _refresh_spot_price_cache(self) -> None:
        """Refresh cached spot mid-prices from the exchange metadata."""

        try:
            meta_and_ctxs = self.info.spot_meta_and_asset_ctxs()
        except Exception as exc:  # pragma: no cover - network failures are non-deterministic
            self.logger.debug("Failed to refresh spot price cache: %s", exc, exc_info=True)
            self._spot_price_cache_ts = time.time()
            return

        if self.price_service is not None:
            # Dedicated price service owns the cache when available
            self._spot_price_cache_ts = time.time()
            return

        if not isinstance(meta_and_ctxs, list) or len(meta_and_ctxs) < 2:
            self._spot_price_cache_ts = time.time()
            return

        asset_ctxs = meta_and_ctxs[1]
        new_cache: dict[str, float] = {"USDC": 1.0}

        for ctx in asset_ctxs:
            coin = ctx.get("coin")
            if not coin:
                continue

            mid_px = _safe_float(ctx.get("midPx"))
            mark_px = _safe_float(ctx.get("markPx"))
            price = mid_px or mark_px
            if price <= 0:
                continue

            new_cache[coin] = price

            if self.identity_registry:
                identity = self.identity_registry.resolve_spot_symbol(
                    coin
                ) or self.identity_registry.resolve(coin)
                if identity:
                    new_cache[identity.canonical_symbol] = price
                    new_cache[identity.wallet_symbol] = price
                    for alias in identity.spot_aliases:
                        new_cache[alias] = price
                    # Include display symbol with default quote if missing slash
                    if identity.default_quote:
                        new_cache[f"{identity.canonical_symbol}/{identity.default_quote}"] = price

        self._spot_price_cache = new_cache
        self._spot_price_cache_ts = time.time()

    def _get_spot_price(self, coin: str, identity: AssetIdentity | None = None) -> float | None:
        """Return cached USD price for a spot asset when available."""

        if self.price_service is not None and identity is not None:
            return self.price_service.get_price(identity, "spot")

        now = time.time()
        if now - self._spot_price_cache_ts > self._spot_price_cache_ttl:
            self._refresh_spot_price_cache()

        normalized = coin.upper()
        candidate_keys = [coin, normalized]

        if identity:
            candidate_keys.append(identity.canonical_symbol)
            candidate_keys.append(identity.wallet_symbol)
            for alias in identity.spot_aliases:
                candidate_keys.append(alias)
            if identity.default_quote:
                candidate_keys.append(f"{identity.canonical_symbol}/{identity.default_quote}")
                candidate_keys.append(f"{identity.wallet_symbol}/{identity.default_quote}")

        if "/" not in normalized and normalized:
            candidate_keys.append(f"{normalized}/USDC")

        for key in candidate_keys:
            price = self._spot_price_cache.get(key)
            if price is not None:
                return price

        if normalized == "USDC":
            return 1.0

        return None

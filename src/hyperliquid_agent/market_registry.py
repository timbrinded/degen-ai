"""Centralized market registry for Hyperliquid spot and perpetual markets.

This module provides a unified interface for asset and market resolution across
different market types (spot vs perpetual). It follows the "Security Master" pattern
commonly used in professional trading systems.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

from hyperliquid.info import Info

logger = logging.getLogger(__name__)


@dataclass
class SpotMarketInfo:
    """Metadata for a specific spot market.

    Attributes:
        market_name: Preferred market identifier for API calls (e.g., "UETH/USDC")
        base_token_idx: Index of base token in spot metadata
        quote_token_idx: Index of quote token in spot metadata
        sz_decimals: Number of decimals for size precision
        px_decimals: Number of decimals for price precision
        native_symbol: Exchange-native identifier (e.g., "@1242")
        aliases: Alternate identifiers resolvable by the API client
        lot_size: Minimum order size increment (if available)
        min_order_size: Minimum order size (if available)
    """

    market_name: str
    base_token_idx: int
    quote_token_idx: int
    sz_decimals: int
    px_decimals: int
    native_symbol: str | None = None
    aliases: list[str] = field(default_factory=list)
    lot_size: Decimal | None = None
    min_order_size: Decimal | None = None


@dataclass
class PerpMarketInfo:
    """Metadata for perpetual market.

    Attributes:
        market_name: Market identifier for API calls (e.g., "ETH")
        asset_id: Internal asset ID
        sz_decimals: Number of decimals for size precision
        px_decimals: Number of decimals for price precision
        tick_size: Minimum price increment (if available)
        lot_size: Minimum order size increment (if available)
    """

    market_name: str
    asset_id: int
    sz_decimals: int
    px_decimals: int
    tick_size: Decimal | None = None
    lot_size: Decimal | None = None


@dataclass
class AssetMarketInfo:
    """Complete market information for a single asset.

    Provides unified access to both spot and perpetual market metadata for
    a given base asset (e.g., "ETH").

    Attributes:
        base_symbol: Canonical symbol (e.g., "ETH", "BTC")
        perp: Perpetual market info (None if not available)
        spot_markets: List of available spot markets (may have multiple quotes)
    """

    base_symbol: str
    perp: PerpMarketInfo | None = None
    spot_markets: list[SpotMarketInfo] = field(default_factory=list)

    @property
    def has_perp(self) -> bool:
        """Check if asset has perpetual market."""
        return self.perp is not None

    @property
    def has_spot(self) -> bool:
        """Check if asset has any spot markets."""
        return len(self.spot_markets) > 0


class MarketRegistry:
    """Centralized registry for all Hyperliquid markets.

    This registry hydrates market metadata on startup and provides O(1) lookups
    for symbol resolution, market name retrieval, and metadata access. It handles
    the complexities of Hyperliquid's different identifier schemes for spot and
    perpetual markets.

    Usage:
        registry = MarketRegistry(info)
        await registry.hydrate()

        # Get market name for trading
        market_name = registry.get_market_name("ETH", "perp")

        # Get full asset info
        asset_info = registry.get_asset_info("ETH")
    """

    def __init__(self, info: Info):
        """Initialize the market registry.

        Args:
            info: Hyperliquid Info API client
        """
        self._info = info
        self._assets: dict[str, AssetMarketInfo] = {}
        self._perp_by_name: dict[str, AssetMarketInfo] = {}
        self._spot_by_name: dict[str, AssetMarketInfo] = {}
        self._spot_market_by_identifier: dict[str, SpotMarketInfo] = {}
        self._ready = False
        self._logger = logging.getLogger(__name__)

    @property
    def is_ready(self) -> bool:
        """Check if registry has been hydrated."""
        return self._ready

    async def hydrate(self) -> None:
        """Load all market metadata from Hyperliquid.

        This method fetches perpetual and spot market data from the Hyperliquid API
        and builds unified asset mappings. It should be called during application
        startup before any trading operations.

        Raises:
            Exception: If metadata fetching fails
        """
        self._logger.info("Hydrating market registry...")

        try:
            # Load perpetual markets
            perp_count = await self._load_perp_markets()

            # Load spot markets
            spot_count = await self._load_spot_markets()

            # Mark as ready
            self._ready = True

            self._logger.info(
                f"Market registry hydrated successfully: "
                f"{len(self._assets)} unique assets, "
                f"{perp_count} perp markets, "
                f"{spot_count} spot markets"
            )

        except Exception as e:
            self._logger.error(f"Failed to hydrate market registry: {e}", exc_info=True)
            raise

    async def _load_perp_markets(self) -> int:
        """Load perpetual market metadata.

        Returns:
            Number of perpetual markets loaded
        """
        meta = await asyncio.to_thread(self._info.meta)
        universe = meta.get("universe", [])

        perp_count = 0
        for asset_data in universe:
            name = asset_data.get("name")
            if not name:
                continue

            # Normalize symbol to uppercase
            base_symbol = name.upper()

            # Create or get asset entry
            if base_symbol not in self._assets:
                self._assets[base_symbol] = AssetMarketInfo(base_symbol=base_symbol)

            asset_info = self._assets[base_symbol]

            # Add perpetual market info
            asset_id = asset_data.get("assetId", 0)
            sz_decimals = asset_data.get("szDecimals", 0)
            assert isinstance(asset_id, int), f"Expected int for assetId, got {type(asset_id)}"
            assert isinstance(sz_decimals, int), (
                f"Expected int for szDecimals, got {type(sz_decimals)}"
            )

            asset_info.perp = PerpMarketInfo(
                market_name=name,  # Keep original case for API calls
                asset_id=asset_id,
                sz_decimals=sz_decimals,
                px_decimals=8,  # Default for perps
            )

            # Add to reverse lookup
            self._perp_by_name[name] = asset_info
            self._perp_by_name[base_symbol] = asset_info  # Also allow uppercase lookup

            perp_count += 1

        self._logger.debug(f"Loaded {perp_count} perpetual markets")
        return perp_count

    async def _load_spot_markets(self) -> int:
        """Load spot market metadata.

        Returns:
            Number of spot markets loaded
        """
        spot_meta = await asyncio.to_thread(self._info.spot_meta)
        spot_universe = spot_meta.get("universe", [])
        tokens = spot_meta.get("tokens", [])

        spot_count = 0
        for spot_data in spot_universe:
            market_name = spot_data.get("name")
            if not market_name:
                continue

            # Get token indices
            token_pair = spot_data.get("tokens", [])
            if len(token_pair) != 2:
                self._logger.warning(f"Invalid token pair for spot market {market_name}")
                continue

            base_token_idx, quote_token_idx = token_pair

            # Validate token indices
            if base_token_idx >= len(tokens):
                self._logger.warning(f"Invalid base token index for {market_name}")
                continue

            if quote_token_idx >= len(tokens):
                self._logger.warning(f"Invalid quote token index for {market_name}")
                continue

            base_token = tokens[base_token_idx]
            quote_token = tokens[quote_token_idx]

            raw_base_symbol = base_token.get("name", "")
            raw_quote_symbol = quote_token.get("name", "")

            if not raw_base_symbol:
                self._logger.warning(f"No base symbol found for spot market {market_name}")
                continue

            if not raw_quote_symbol:
                self._logger.warning(f"No quote symbol found for spot market {market_name}")
                continue

            # Normalize base symbol to align spot and perp metadata (e.g., UETH -> ETH)
            normalized_base_symbol = self._normalize_symbol(raw_base_symbol)

            if normalized_base_symbol not in self._assets:
                self._assets[normalized_base_symbol] = AssetMarketInfo(
                    base_symbol=normalized_base_symbol
                )

            asset_info = self._assets[normalized_base_symbol]

            # Add spot market info
            sz_decimals_spot = spot_data.get("szDecimals", 0)
            assert isinstance(sz_decimals_spot, int), (
                f"Expected int for szDecimals, got {type(sz_decimals_spot)}"
            )

            px_decimals_spot = spot_data.get("pxDecimals", 8) or 8
            if not isinstance(px_decimals_spot, int):
                self._logger.debug(
                    "pxDecimals missing or invalid for %s, defaulting to 8", market_name
                )
                px_decimals_spot = 8

            alias_market_name = f"{raw_base_symbol.upper()}/{raw_quote_symbol.upper()}"
            unique_aliases = list(dict.fromkeys([alias_market_name, market_name]))

            spot_info = SpotMarketInfo(
                market_name=alias_market_name,
                base_token_idx=base_token_idx,
                quote_token_idx=quote_token_idx,
                sz_decimals=sz_decimals_spot,
                px_decimals=px_decimals_spot,
                native_symbol=market_name,
                aliases=unique_aliases,
            )

            asset_info.spot_markets.append(spot_info)

            # Add to reverse lookup
            lookup_identifiers = set(unique_aliases)
            if spot_info.native_symbol:
                lookup_identifiers.add(spot_info.native_symbol)

            for identifier in lookup_identifiers:
                if not identifier:
                    continue

                normalized_identifier = identifier.upper()

                # Preserve original casing for legacy lookups
                self._spot_by_name[identifier] = asset_info
                self._spot_market_by_identifier[identifier.upper()] = spot_info

                # Store normalized variant to allow case-insensitive matching
                self._spot_by_name[normalized_identifier] = asset_info
                self._spot_market_by_identifier[normalized_identifier] = spot_info

            spot_count += 1

        self._logger.debug(f"Loaded {spot_count} spot markets")
        return spot_count

    def get_asset_info(self, symbol: str) -> AssetMarketInfo | None:
        """Get complete market information for a symbol.

        Args:
            symbol: Asset symbol (e.g., "ETH", "BTC")

        Returns:
            AssetMarketInfo if found, None otherwise
        """
        if not self._ready:
            raise RuntimeError(
                "MarketRegistry not ready. Call await registry.hydrate() during startup."
            )

        # Normalize to uppercase
        normalized = self._normalize_symbol(symbol)
        return self._assets.get(normalized)

    def get_market_name(
        self, symbol: str, market_type: Literal["spot", "perp"], quote: str = "USDC"
    ) -> str:
        """Get the correct market identifier for order placement.

        This method handles the complexity of Hyperliquid's different naming schemes:
        - Perps: Direct symbol (e.g., "ETH")
        - Spot: Pair notation or index (e.g., "ETH/USDC" or "@123")

        Args:
            symbol: Asset symbol (e.g., "ETH", "BTC")
            market_type: "spot" or "perp"
            quote: Quote currency for spot markets (default: "USDC")

        Returns:
            Market identifier string for API calls

        Raises:
            RuntimeError: If registry not hydrated
            ValueError: If asset or market type not available
        """
        self._logger.debug(
            f"MarketRegistry.get_market_name called: symbol='{symbol}', "
            f"market_type='{market_type}', quote='{quote}'"
        )

        if not self._ready:
            raise RuntimeError(
                "MarketRegistry not ready. Call await registry.hydrate() during startup."
            )

        # Normalize symbol
        normalized = self._normalize_symbol(symbol)
        self._logger.debug(f"Normalized symbol '{symbol}' -> '{normalized}'")

        asset = self._assets.get(normalized)
        if not asset:
            self._logger.debug(
                f"Asset '{symbol}' (normalized: '{normalized}') not found in registry. "
                f"Available assets: {list(self._assets.keys())[:10]}"
            )
            raise ValueError(f"Unknown asset: {symbol}")

        self._logger.debug(
            f"Asset '{normalized}' found: has_perp={asset.has_perp}, "
            f"has_spot={asset.has_spot}, spot_markets={len(asset.spot_markets)}"
        )

        if market_type == "perp":
            if not asset.perp:
                self._logger.debug(f"Asset '{symbol}' does not have perpetual market")
                raise ValueError(f"{symbol} not available on perpetual market")

            market_name = asset.perp.market_name
            self._logger.debug(f"Returning perp market name: '{market_name}'")
            return market_name

        # Spot market: find best match based on quote currency
        if not asset.spot_markets:
            self._logger.debug(f"Asset '{symbol}' does not have any spot markets")
            raise ValueError(f"{symbol} not available on spot market")

        self._logger.debug(
            f"Searching for spot market with quote '{quote}' among "
            f"{[s.market_name for s in asset.spot_markets]}"
        )

        # Prefer requested quote currency
        quote_upper = quote.upper()
        for spot in asset.spot_markets:
            if quote_upper in spot.market_name.upper():
                self._logger.debug(
                    f"Found matching spot market: '{spot.market_name}' (contains quote '{quote}')"
                )
                return spot.market_name

        # Fallback to first available spot market
        fallback_market = asset.spot_markets[0].market_name
        self._logger.debug(
            f"Quote '{quote}' not found for {symbol}, using fallback: '{fallback_market}'"
        )
        return fallback_market

    def get_spot_market_info(
        self,
        symbol: str,
        quote: str = "USDC",
        market_identifier: str | None = None,
    ) -> SpotMarketInfo:
        """Retrieve detailed spot metadata for a symbol.

        Args:
            symbol: Asset symbol (e.g., "ETH").
            quote: Desired quote currency for spot markets.
            market_identifier: Optional market identifier (alias or native symbol).

        Returns:
            SpotMarketInfo describing the resolved market.

        Raises:
            RuntimeError: If the registry has not been hydrated.
            ValueError: If the requested spot market is unavailable.
        """

        if not self._ready:
            raise RuntimeError(
                "MarketRegistry not ready. Call await registry.hydrate() during startup."
            )

        normalized_symbol = self._normalize_symbol(symbol)
        asset = self._assets.get(normalized_symbol)

        if not asset or not asset.spot_markets:
            raise ValueError(f"{symbol} not available on spot market")

        # 1) Direct lookup by provided identifier (alias or native)
        if market_identifier:
            lookup_key = market_identifier.upper()
            spot_info = self._spot_market_by_identifier.get(lookup_key)
            if spot_info and spot_info in asset.spot_markets:
                return spot_info

        quote_upper = quote.upper()

        # 2) Prefer markets whose aliases explicitly include the desired quote
        for spot in asset.spot_markets:
            identifiers = [spot.market_name, *(spot.aliases or [])]
            for identifier in identifiers:
                if not identifier or "/" not in identifier:
                    continue

                try:
                    _, identifier_quote = identifier.rsplit("/", 1)
                except ValueError:
                    continue

                if identifier_quote.upper() == quote_upper:
                    return spot

        # 3) Fallback to the first available market
        self._logger.debug(
            "Quote '%s' not explicitly found for %s; falling back to first spot market '%s'",
            quote,
            symbol,
            asset.spot_markets[0].market_name,
        )

        return asset.spot_markets[0]

    def resolve_symbol(self, raw_symbol: str) -> tuple[str, Literal["spot", "perp"]] | None:
        """Resolve ambiguous input to (base_symbol, market_type).

        Handles various input formats:
        - "ETH" -> could be perp or spot (defaults to perp if available)
        - "ETH/USDC" -> spot market
        - "@123" -> spot market by index

        Args:
            raw_symbol: Raw symbol string from user input or LLM

        Returns:
            Tuple of (base_symbol, market_type) if resolved, None otherwise
        """
        if not self._ready:
            raise RuntimeError(
                "MarketRegistry not ready. Call await registry.hydrate() during startup."
            )

        # Check if it's a spot market name (contains "/" or starts with "@")
        if "/" in raw_symbol or raw_symbol.startswith("@"):
            asset = self._spot_by_name.get(raw_symbol)
            if asset:
                return (asset.base_symbol, "spot")
            return None

        # Normalize and check if it's a known asset
        normalized = self._normalize_symbol(raw_symbol)
        asset = self._assets.get(normalized)

        if not asset:
            return None

        # Default to perp if available, otherwise spot
        if asset.has_perp:
            return (asset.base_symbol, "perp")
        elif asset.has_spot:
            return (asset.base_symbol, "spot")

        return None

    def _normalize_symbol(self, symbol: str) -> str:
        """Normalize symbol to canonical form.

        Args:
            symbol: Raw symbol string

        Returns:
            Normalized symbol (uppercase, stripped)
        """
        # Remove whitespace and convert to uppercase
        normalized = symbol.strip().upper()

        # Remove common prefixes that might cause issues
        # (e.g., "UETH" -> "ETH" if someone accidentally prefixes with U)
        if normalized.startswith("U") and len(normalized) > 1:
            # Check if removing U gives us a known symbol
            without_u = normalized[1:]
            if without_u in self._assets:
                self._logger.debug(f"Normalized '{symbol}' to '{without_u}' (removed U prefix)")
                return without_u

        return normalized

    async def refresh(self) -> None:
        """Refresh market metadata from Hyperliquid.

        This method reloads all market data and atomically swaps the internal
        dictionaries to avoid partial updates during concurrent access.
        """
        self._logger.info("Refreshing market registry...")

        # Build new dictionaries
        old_assets = self._assets
        old_perp = self._perp_by_name
        old_spot = self._spot_by_name
        old_spot_market_lookup = self._spot_market_by_identifier
        old_ready = self._ready

        try:
            # Reset state
            self._assets = {}
            self._perp_by_name = {}
            self._spot_by_name = {}
            self._spot_market_by_identifier = {}
            self._ready = False

            # Reload
            await self.hydrate()

            self._logger.info("Market registry refreshed successfully")

        except Exception as e:
            # Restore old state on failure
            self._logger.error(f"Failed to refresh registry, restoring old state: {e}")
            self._assets = old_assets
            self._perp_by_name = old_perp
            self._spot_by_name = old_spot
            self._spot_market_by_identifier = old_spot_market_lookup
            self._ready = old_ready
            raise

    def get_sz_decimals(self, symbol: str, market_type: Literal["spot", "perp"]) -> int:
        """Get size decimals for a specific market.

        Args:
            symbol: Asset symbol
            market_type: "spot" or "perp"

        Returns:
            Number of decimal places for size

        Raises:
            ValueError: If asset or market type not found
        """
        asset = self.get_asset_info(symbol)
        if not asset:
            raise ValueError(f"Unknown asset: {symbol}")

        if market_type == "perp":
            if not asset.perp:
                raise ValueError(f"{symbol} not available on perpetual market")
            return asset.perp.sz_decimals
        else:
            if not asset.spot_markets:
                raise ValueError(f"{symbol} not available on spot market")
            # Return decimals from first spot market (usually same across quotes)
            return asset.spot_markets[0].sz_decimals

"""Asset identity registry built from static configuration and exchange metadata."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from pathlib import Path

from hyperliquid.info import Info

from .asset_identity import AssetIdentity, MarketDescriptor

logger = logging.getLogger(__name__)


def default_assets_config_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "assets.json"


class AssetIdentityRegistry:
    """Provides canonical asset lookups across perp and spot venues."""

    def __init__(self, config_path: Path, info: Info | None = None) -> None:
        self._config_path = config_path
        self._info = info
        self._identities: dict[str, AssetIdentity] = {}
        self._lookup: dict[str, AssetIdentity] = {}
        self._spot_descriptors: dict[tuple[str, str], MarketDescriptor] = {}
        self._perp_descriptors: dict[str, MarketDescriptor] = {}
        self._spot_symbol_lookup: dict[str, AssetIdentity] = {}

    def load(self) -> None:
        """Load static config and hydrate exchange metadata if available."""

        raw_config = json.loads(self._config_path.read_text())

        identities: dict[str, AssetIdentity] = {}
        lookup: dict[str, AssetIdentity] = {}

        for entry in raw_config:
            perp_symbol = entry.get("perp")
            default_quote = entry.get("default_quote")
            identity = AssetIdentity(
                canonical_symbol=entry["canonical"].upper(),
                wallet_symbol=entry["wallet"].upper(),
                perp_symbol=(perp_symbol.upper() if perp_symbol else None),
                spot_aliases=tuple(alias.upper() for alias in entry.get("spot_aliases", [])),
                default_quote=(default_quote.upper() if default_quote else None),
            )

            identities[identity.canonical_symbol] = identity

            for alias in {
                identity.canonical_symbol,
                identity.wallet_symbol,
                *identity.spot_aliases,
            }:
                lookup[alias.upper()] = identity
            if identity.perp_symbol:
                lookup[identity.perp_symbol.upper()] = identity

        self._identities = identities
        self._lookup = lookup
        self._spot_symbol_lookup = {}

        if self._info:
            self._hydrate_market_metadata()

    def _hydrate_market_metadata(self) -> None:
        """Fetch Hyperliquid metadata and attach market descriptors."""

        assert self._info is not None

        spot_data = self._info.spot_meta()
        tokens = spot_data.get("tokens", [])
        universe = spot_data.get("universe", [])

        token_lookup = {token.get("index"): token for token in tokens if token.get("name")}

        for market in universe:
            tokens = market.get("tokens", [])
            if len(tokens) != 2:
                continue

            base_idx, quote_idx = tokens
            base_token = token_lookup.get(base_idx)
            quote_token = token_lookup.get(quote_idx)
            if not base_token or not quote_token:
                continue

            native_symbol = market.get("name")
            market_name = f"{base_token.get('name')}/{quote_token.get('name')}"

            identity = self.resolve(base_token.get("name", "")) if base_token else None
            if not identity:
                # Try matching wallet alias (U prefix) if present
                symbol = base_token.get("name", "")
                prefixed = f"U{symbol}" if symbol else ""
                identity = self.resolve(prefixed)

            if identity:
                sz_candidate = market.get("szDecimals")
                if isinstance(sz_candidate, str):
                    sz_candidate = int(sz_candidate) if sz_candidate.isdigit() else None
                if not isinstance(sz_candidate, int):
                    token_sz = base_token.get("szDecimals")
                    sz_candidate = token_sz if isinstance(token_sz, int) else None

                px_candidate = market.get("pxDecimals")
                if isinstance(px_candidate, str):
                    px_candidate = int(px_candidate) if px_candidate.isdigit() else None
                if not isinstance(px_candidate, int):
                    px_candidate = 8

                descriptor = MarketDescriptor(
                    market_type="spot",
                    native_symbol=native_symbol,
                    display_symbol=market_name,
                    quote_symbol=(quote_token.get("name") if quote_token else None),
                    sz_decimals=sz_candidate,
                    px_decimals=px_candidate,
                )
                key = (
                    identity.canonical_symbol,
                    descriptor.quote_symbol or identity.default_quote or "USDC",
                )
                self._spot_descriptors[key] = descriptor

                for alias in {
                    descriptor.native_symbol.upper() if descriptor.native_symbol else "",
                    descriptor.display_symbol.upper(),
                    identity.wallet_symbol.upper(),
                    *identity.spot_aliases,
                }:
                    if alias:
                        self._spot_symbol_lookup[alias] = identity

        perp_data = self._info.meta()
        for asset in perp_data.get("universe", []):
            symbol = asset.get("name", "").upper()
            identity = self.resolve(symbol)
            if not identity:
                continue

            descriptor = MarketDescriptor(
                market_type="perp",
                native_symbol=asset.get("name"),
                display_symbol=asset.get("name"),
                quote_symbol="USDC",
                sz_decimals=asset.get("szDecimals"),
                px_decimals=None,
            )
            self._perp_descriptors[identity.canonical_symbol] = descriptor

    def resolve(self, symbol: str | None) -> AssetIdentity | None:
        if not symbol:
            return None
        return self._lookup.get(symbol.upper())

    def get_spot_market(
        self, asset: AssetIdentity, quote: str | None = None
    ) -> MarketDescriptor | None:
        quote_symbol = (quote or asset.default_quote or "USDC").upper()
        return self._spot_descriptors.get((asset.canonical_symbol, quote_symbol))

    def get_perp_market(self, asset: AssetIdentity) -> MarketDescriptor | None:
        return self._perp_descriptors.get(asset.canonical_symbol)

    def identities(self) -> Iterable[AssetIdentity]:
        return self._identities.values()

    def resolve_spot_symbol(self, symbol: str | None) -> AssetIdentity | None:
        if not symbol:
            return None
        return self._spot_symbol_lookup.get(symbol.upper())

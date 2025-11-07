"""Core asset identity definitions for unifying perp and spot symbols."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Literal

MarketType = Literal["spot", "perp"]


@dataclass(frozen=True)
class MarketDescriptor:
    """Resolved market metadata for a specific asset/venue combination."""

    market_type: MarketType
    native_symbol: str
    display_symbol: str
    quote_symbol: str | None = None
    sz_decimals: int | None = None
    px_decimals: int | None = None


@dataclass(frozen=True)
class AssetIdentity:
    """Canonical view over an asset across perp/spot/wallet contexts."""

    canonical_symbol: str
    wallet_symbol: str
    perp_symbol: str | None = None
    spot_aliases: tuple[str, ...] = field(default_factory=tuple)
    default_quote: str | None = None

    def matches(self, symbol: str) -> bool:
        """Return True if *symbol* belongs to this asset in any venue."""

        norm = symbol.upper()
        if norm == self.canonical_symbol.upper():
            return True
        if self.perp_symbol and norm == self.perp_symbol.upper():
            return True
        if norm == self.wallet_symbol.upper():
            return True
        return any(norm == alias.upper() for alias in self.spot_aliases)

    @property
    def all_aliases(self) -> Iterable[str]:
        """Yield every known identifier for the asset."""

        if self.perp_symbol:
            yield self.perp_symbol
        yield self.wallet_symbol
        yield from self.spot_aliases

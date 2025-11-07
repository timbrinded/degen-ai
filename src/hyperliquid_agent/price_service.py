"""Asset price resolution shared across modules."""

from __future__ import annotations

import logging
import time
from typing import Literal

from hyperliquid.info import Info

from .asset_identity import AssetIdentity
from .identity_registry import AssetIdentityRegistry

logger = logging.getLogger(__name__)


def _safe_float(value):
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


class AssetPriceService:
    """Provides cached access to spot/perp prices using identity registry."""

    def __init__(
        self,
        info: Info,
        identity_registry: AssetIdentityRegistry,
        *,
        cache_ttl_seconds: float = 30.0,
    ) -> None:
        self.info = info
        self.identity_registry = identity_registry
        self.cache_ttl_seconds = cache_ttl_seconds
        self._spot_cache: dict[str, float] = {"USDC": 1.0}
        self._last_refresh = 0.0

    def get_price(
        self,
        asset: AssetIdentity,
        market_type: Literal["spot", "perp"] = "spot",
        *,
        quote: str | None = None,
    ) -> float | None:
        if market_type == "spot":
            return self._get_spot_price(asset, quote)
        if market_type == "perp":
            # Perp mark price not implemented yet
            return None
        raise ValueError(f"Unsupported market type: {market_type}")

    def get_spot_symbol_price(self, symbol: str) -> float | None:
        identity = self.identity_registry.resolve(symbol)
        return self._get_spot_price(identity, None) if identity else None

    def _get_spot_price(self, identity: AssetIdentity, quote: str | None) -> float | None:
        now = time.time()
        if now - self._last_refresh > self.cache_ttl_seconds:
            self._refresh_spot_cache()

        search_keys: list[str] = []
        if identity:
            search_keys.append(identity.canonical_symbol)
            search_keys.append(identity.wallet_symbol)
            search_keys.extend(identity.spot_aliases)
            if quote or identity.default_quote:
                q = (quote or identity.default_quote or "USDC").upper()
                search_keys.append(f"{identity.canonical_symbol}/{q}")
                search_keys.append(f"{identity.wallet_symbol}/{q}")

        for key in search_keys:
            price = self._spot_cache.get(key)
            if price is not None:
                return price

        # As fallback, allow raw canonical symbol without identity match
        return None

    def _refresh_spot_cache(self) -> None:
        try:
            meta_and_ctxs = self.info.spot_meta_and_asset_ctxs()
        except Exception as exc:  # pragma: no cover
            logger.debug("Failed to refresh spot price cache: %s", exc, exc_info=True)
            self._last_refresh = time.time()
            return

        if not isinstance(meta_and_ctxs, list) or len(meta_and_ctxs) < 2:
            self._last_refresh = time.time()
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

            identity = self.identity_registry.resolve_spot_symbol(
                coin
            ) or self.identity_registry.resolve(coin)
            if identity:
                for alias in identity.all_aliases:
                    new_cache[alias.upper()] = price
                if identity.default_quote:
                    q = identity.default_quote.upper()
                    new_cache[f"{identity.canonical_symbol}/{q}"] = price

        self._spot_cache = new_cache
        self._last_refresh = time.time()

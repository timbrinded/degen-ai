"""Exchange-level constraints such as minimum order notionals."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal

from hyperliquid_agent.config import RiskConfig


def _to_decimal(value: float | int | str) -> Decimal:
    """Convert primitive value to Decimal using string casting for precision."""

    return Decimal(str(value))


@dataclass(frozen=True)
class NotionalConstraints:
    """Encapsulates minimum notional rules for spot and perpetual markets."""

    perp_min_notional_usd: Decimal = Decimal("10")
    spot_min_notional_quote: Decimal = Decimal("10")
    spot_quote_overrides: Mapping[str, Decimal] = field(default_factory=dict)

    @classmethod
    def from_risk_config(cls, risk_config: RiskConfig | None) -> NotionalConstraints:
        if risk_config is None:
            return cls()

        overrides: dict[str, Decimal] = {
            quote.upper(): _to_decimal(amount)
            for quote, amount in (risk_config.spot_quote_notional_overrides or {}).items()
        }

        return cls(
            perp_min_notional_usd=_to_decimal(risk_config.perp_min_notional_usd),
            spot_min_notional_quote=_to_decimal(risk_config.spot_min_notional_quote),
            spot_quote_overrides=overrides,
        )

    @property
    def perp_minimum(self) -> Decimal:
        return self.perp_min_notional_usd

    def spot_minimum(self, quote_symbol: str | None) -> Decimal:
        if not quote_symbol:
            return self.spot_min_notional_quote
        return self.spot_quote_overrides.get(quote_symbol.upper(), self.spot_min_notional_quote)

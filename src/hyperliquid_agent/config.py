"""Configuration management for the trading agent."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


@dataclass
class RiskConfig:
    """Risk controls for capital allocation between perp and spot wallets."""

    enable_auto_transfers: bool = True
    target_initial_margin_ratio: float = 1.25
    min_perp_balance_usd: float = 1000.0
    target_spot_usdc_buffer_usd: float = 0.0
    perp_min_notional_usd: float = 10.0
    spot_min_notional_quote: float = 10.0
    spot_quote_notional_overrides: dict[str, float] = field(default_factory=dict)


@dataclass
class HyperliquidConfig:
    """Hyperliquid API configuration."""

    account_address: str
    secret_key: str
    base_url: str


@dataclass
class LLMConfig:
    """LLM provider configuration."""

    provider: Literal["openai", "anthropic"]
    model: str
    api_key: str
    temperature: float = 0.7
    max_tokens: int = 10000


@dataclass
class AgentConfig:
    """Trading agent configuration."""

    tick_interval_seconds: int = 60
    max_retries: int = 5
    retry_backoff_base: float = 2.0
    log_level: str = "INFO"
    prompt_template_path: str = "prompts/default.txt"


@dataclass
class HyperliquidProviderConfig:
    """Hyperliquid provider configuration for signal system."""

    max_retries: int = 3
    timeout_seconds: float = 10.0
    backoff_factor: float = 2.0
    initial_delay_seconds: float = 1.0


@dataclass
class OnChainConfig:
    """On-chain data provider configuration.

    Providers:
    - token_unlocks: Token unlock schedule data (requires API key)
    - nansen: On-chain analytics (requires API key)
    - dune: Blockchain query data (requires API key)
    - None: Disabled (no on-chain data collection)
    """

    enabled: bool = True
    provider: str | None = None  # e.g., "token_unlocks", "nansen", "dune"
    api_key: str | None = None
    cache_ttl_seconds: int = 3600

    def __post_init__(self):
        """Validate configuration."""
        if self.enabled and self.provider and not self.api_key:
            raise ValueError(
                f"On-chain provider '{self.provider}' is enabled but no API key provided. "
                f"Set api_key in config or disable the provider."
            )


@dataclass
class ExternalMarketConfig:
    """External market data provider configuration.

    Providers:
    - CoinGecko: Crypto price data (FREE tier available, API key optional for higher limits)
    - yfinance: Traditional market data via Yahoo Finance (FREE - no API key required)
    - TradingView: Advanced charting data (requires API key)
    """

    enabled: bool = True
    use_coingecko: bool = True
    coingecko_api_key: str | None = None
    use_yfinance: bool = True
    jblanked_api_key: str | None = None
    use_tradingview: bool = False
    cache_ttl_seconds: int = 900


@dataclass
class SentimentConfig:
    """Sentiment data provider configuration.

    Providers:
    - Fear & Greed Index: Alternative.me API (FREE - no API key required)
    - Social Sentiment: Twitter/X sentiment analysis (requires API key)
    """

    enabled: bool = True
    use_fear_greed_index: bool = True
    use_social_sentiment: bool = False
    cache_ttl_seconds: int = 1800


@dataclass
class ComputedConfig:
    """Computed signals configuration."""

    enabled: bool = True
    technical_lookback_hours: int = 168
    volatility_lookback_hours: int = 168
    correlation_lookback_days: int = 30
    cache_ttl_seconds: int = 300


@dataclass
class CacheConfig:
    """Cache layer configuration."""

    cleanup_interval_seconds: int = 3600
    vacuum_on_startup: bool = True
    max_size_mb: int = 100


@dataclass
class SignalConfig:
    """Signal system configuration."""

    timeout_seconds: float = 30.0
    caching_enabled: bool = True
    db_path: str = "state/signal_cache.db"
    hyperliquid: HyperliquidProviderConfig | None = None
    onchain: OnChainConfig | None = None
    external_market: ExternalMarketConfig | None = None
    sentiment: SentimentConfig | None = None
    computed: ComputedConfig | None = None
    cache: CacheConfig | None = None


@dataclass
class GovernanceConfig:
    """Governance system configuration."""

    governor: dict
    regime_detector: dict
    tripwire: dict
    fast_loop_interval_seconds: int = 10
    medium_loop_interval_minutes: int = 30
    slow_loop_interval_hours: int = 24
    emergency_reduction_pct: float = 100.0  # Percentage of positions to close in emergency


@dataclass
class ObservabilityConfig:
    """Observability and tracing configuration."""

    langsmith_api_key: str | None = None


@dataclass
class LangGraphConfig:
    """LangGraph runtime configuration."""

    enabled: bool = False
    checkpoint_backend: Literal["sqlite", "memory"] = "sqlite"
    storage_path: str = "state/langgraph/checkpoints.db"
    snapshot_dir: str = "state/snapshots"
    phase_tag: str = "langgraph_phase_1"


@dataclass
class Config:
    """Complete application configuration."""

    hyperliquid: HyperliquidConfig
    llm: LLMConfig
    agent: AgentConfig
    risk: RiskConfig = field(default_factory=RiskConfig)
    governance: GovernanceConfig | None = None
    signals: SignalConfig | None = None
    observability: ObservabilityConfig | None = None
    langgraph: LangGraphConfig | None = None


def load_config(config_path: str | Path = "config.toml") -> Config:
    """Load configuration from TOML file.

    Args:
        config_path: Path to the configuration file

    Returns:
        Parsed configuration object

    Raises:
        FileNotFoundError: If config file doesn't exist
        ValueError: If required fields are missing or invalid
    """
    import tomllib

    config_file = Path(config_path)
    if not config_file.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with open(config_file, "rb") as f:
        data = tomllib.load(f)

    # Validate required sections
    required_sections = ["hyperliquid", "llm", "agent"]
    for section in required_sections:
        if section not in data:
            raise ValueError(f"Missing required configuration section: [{section}]")

    # Parse Hyperliquid config
    hl_data = data["hyperliquid"]
    required_hl_fields = ["account_address", "secret_key", "base_url"]
    for required_field in required_hl_fields:
        if required_field not in hl_data:
            raise ValueError(f"Missing required field in [hyperliquid]: {required_field}")

    hyperliquid_config = HyperliquidConfig(
        account_address=hl_data["account_address"],
        secret_key=hl_data["secret_key"],
        base_url=hl_data["base_url"],
    )

    # Parse LLM config
    llm_data = data["llm"]
    required_llm_fields = ["provider", "model", "api_key"]
    for required_field in required_llm_fields:
        if required_field not in llm_data:
            raise ValueError(f"Missing required field in [llm]: {required_field}")

    if llm_data["provider"] not in ["openai", "anthropic"]:
        raise ValueError(
            f"Invalid LLM provider: {llm_data['provider']}. Must be 'openai' or 'anthropic'"
        )

    llm_config = LLMConfig(
        provider=llm_data["provider"],
        model=llm_data["model"],
        api_key=llm_data["api_key"],
        temperature=llm_data.get("temperature", 0.7),
        max_tokens=llm_data.get("max_tokens", 10000),
    )

    # Parse Agent config with defaults
    agent_data = data.get("agent", {})

    # Allow LOG_LEVEL environment variable to override config file
    log_level = os.environ.get("LOG_LEVEL", agent_data.get("log_level", "INFO")).upper()

    agent_config = AgentConfig(
        tick_interval_seconds=agent_data.get("tick_interval_seconds", 60),
        max_retries=agent_data.get("max_retries", 5),
        retry_backoff_base=agent_data.get("retry_backoff_base", 2.0),
        log_level=log_level,
        prompt_template_path=agent_data.get("prompt_template_path", "prompts/default.txt"),
    )

    # Parse risk controls (optional)
    risk_data = data.get("risk", {})
    overrides = risk_data.get("spot_quote_notional_overrides") or {}
    if overrides and not isinstance(overrides, dict):
        raise ValueError("[risk].spot_quote_notional_overrides must be a table of quote -> amount")

    risk_config = RiskConfig(
        enable_auto_transfers=bool(risk_data.get("enable_auto_transfers", True)),
        target_initial_margin_ratio=float(risk_data.get("target_initial_margin_ratio", 1.25)),
        min_perp_balance_usd=float(risk_data.get("min_perp_balance_usd", 1000.0)),
        target_spot_usdc_buffer_usd=float(risk_data.get("target_spot_usdc_buffer_usd", 0.0)),
        perp_min_notional_usd=float(risk_data.get("perp_min_notional_usd", 10.0)),
        spot_min_notional_quote=float(risk_data.get("spot_min_notional_quote", 10.0)),
        spot_quote_notional_overrides={k.upper(): float(v) for k, v in overrides.items()},
    )

    # Parse Governance config (optional)
    governance_config = None
    if "governance" in data:
        gov_data = data["governance"]

        # Store raw config dicts - will be converted to proper types in CLI
        governance_config = GovernanceConfig(
            governor=gov_data.get("governor", {}),
            regime_detector=gov_data.get("regime_detector", {}),
            tripwire=gov_data.get("tripwire", {}),
            fast_loop_interval_seconds=gov_data.get("fast_loop_interval_seconds", 10),
            medium_loop_interval_minutes=gov_data.get("medium_loop_interval_minutes", 30),
            slow_loop_interval_hours=gov_data.get("slow_loop_interval_hours", 24),
            emergency_reduction_pct=gov_data.get("emergency_reduction_pct", 100.0),
        )

    # Parse Signal config (optional)
    signal_config = None
    if "signals" in data:
        signals_data = data["signals"]

        # Parse Hyperliquid provider config
        hyperliquid_provider_config = None
        if "hyperliquid" in signals_data:
            hl_provider_data = signals_data["hyperliquid"]
            hyperliquid_provider_config = HyperliquidProviderConfig(
                max_retries=hl_provider_data.get("max_retries", 3),
                timeout_seconds=hl_provider_data.get("timeout_seconds", 10.0),
                backoff_factor=hl_provider_data.get("backoff_factor", 2.0),
                initial_delay_seconds=hl_provider_data.get("initial_delay_seconds", 1.0),
            )

        # Parse On-chain config
        onchain_config = None
        if "onchain" in signals_data:
            onchain_data = signals_data["onchain"]
            # Support API key from config or environment variable
            api_key = onchain_data.get("api_key") or os.environ.get("ONCHAIN_API_KEY")
            # Empty string should be treated as None
            if api_key == "":
                api_key = None

            # Get provider, treating empty string as None
            provider = onchain_data.get("provider")
            if provider == "":
                provider = None

            onchain_config = OnChainConfig(
                enabled=onchain_data.get("enabled", True),
                provider=provider,
                api_key=api_key,
                cache_ttl_seconds=onchain_data.get("cache_ttl_seconds", 3600),
            )

        # Parse External market config
        external_market_config = None
        if "external_market" in signals_data:
            ext_data = signals_data["external_market"]
            # Support API key from config or environment variable
            coingecko_api_key = ext_data.get("coingecko_api_key") or os.environ.get(
                "COINGECKO_API_KEY"
            )
            # Empty string should be treated as None
            if coingecko_api_key == "":
                coingecko_api_key = None

            jblanked_api_key = ext_data.get("jblanked_api_key") or os.environ.get(
                "JBLANKED_API_KEY"
            )
            # Empty string should be treated as None
            if jblanked_api_key == "":
                jblanked_api_key = None

            external_market_config = ExternalMarketConfig(
                enabled=ext_data.get("enabled", True),
                use_coingecko=ext_data.get("use_coingecko", True),
                coingecko_api_key=coingecko_api_key,
                use_yfinance=ext_data.get("use_yfinance", True),
                jblanked_api_key=jblanked_api_key,
                use_tradingview=ext_data.get("use_tradingview", False),
                cache_ttl_seconds=ext_data.get("cache_ttl_seconds", 900),
            )

        # Parse Sentiment config
        sentiment_config = None
        if "sentiment" in signals_data:
            sent_data = signals_data["sentiment"]
            sentiment_config = SentimentConfig(
                enabled=sent_data.get("enabled", True),
                use_fear_greed_index=sent_data.get("use_fear_greed_index", True),
                use_social_sentiment=sent_data.get("use_social_sentiment", False),
                cache_ttl_seconds=sent_data.get("cache_ttl_seconds", 1800),
            )

        # Parse Computed config
        computed_config = None
        if "computed" in signals_data:
            comp_data = signals_data["computed"]
            computed_config = ComputedConfig(
                enabled=comp_data.get("enabled", True),
                technical_lookback_hours=comp_data.get("technical_lookback_hours", 168),
                volatility_lookback_hours=comp_data.get("volatility_lookback_hours", 168),
                correlation_lookback_days=comp_data.get("correlation_lookback_days", 30),
                cache_ttl_seconds=comp_data.get("cache_ttl_seconds", 300),
            )

        # Parse Cache config
        cache_config = None
        if "cache" in signals_data:
            cache_data = signals_data["cache"]
            cache_config = CacheConfig(
                cleanup_interval_seconds=cache_data.get("cleanup_interval_seconds", 3600),
                vacuum_on_startup=cache_data.get("vacuum_on_startup", True),
                max_size_mb=cache_data.get("max_size_mb", 100),
            )

        signal_config = SignalConfig(
            timeout_seconds=signals_data.get("timeout_seconds", 30.0),
            caching_enabled=signals_data.get("caching_enabled", True),
            db_path=signals_data.get("db_path", "state/signal_cache.db"),
            hyperliquid=hyperliquid_provider_config,
            onchain=onchain_config,
            external_market=external_market_config,
            sentiment=sentiment_config,
            computed=computed_config,
            cache=cache_config,
        )

    observability_config = None
    if "observability" in data:
        obs_data = data["observability"] or {}
        langsmith_api_key = obs_data.get("langsmith_api_key")
        if isinstance(langsmith_api_key, str):
            langsmith_api_key = langsmith_api_key.strip() or None
        observability_config = ObservabilityConfig(langsmith_api_key=langsmith_api_key)
        if langsmith_api_key:
            os.environ["LANGSMITH_API_KEY"] = langsmith_api_key

    langgraph_config = None
    if "langgraph" in data:
        langgraph_data = data["langgraph"] or {}
        checkpoint_backend = langgraph_data.get("checkpoint_backend", "sqlite")
        if checkpoint_backend not in {"sqlite", "memory"}:
            raise ValueError(
                "[langgraph].checkpoint_backend must be 'sqlite' or 'memory' "
                f"(got {checkpoint_backend!r})"
            )

        langgraph_config = LangGraphConfig(
            enabled=bool(langgraph_data.get("enabled", False)),
            checkpoint_backend=checkpoint_backend,
            storage_path=langgraph_data.get("storage_path", "state/langgraph/checkpoints.db"),
            snapshot_dir=langgraph_data.get("snapshot_dir", "state/snapshots"),
            phase_tag=langgraph_data.get("phase_tag", "langgraph_phase_1"),
        )

    return Config(
        hyperliquid=hyperliquid_config,
        llm=llm_config,
        agent=agent_config,
        risk=risk_config,
        governance=governance_config,
        signals=signal_config,
        observability=observability_config,
        langgraph=langgraph_config,
    )

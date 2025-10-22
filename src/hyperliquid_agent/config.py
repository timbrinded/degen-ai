"""Configuration management for the trading agent."""

from dataclasses import dataclass
from typing import Literal


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
    max_tokens: int = 1000


@dataclass
class AgentConfig:
    """Trading agent configuration."""

    tick_interval_seconds: int = 60
    max_retries: int = 5
    retry_backoff_base: float = 2.0
    log_level: str = "INFO"
    prompt_template_path: str = "prompts/default.txt"


@dataclass
class Config:
    """Complete application configuration."""

    hyperliquid: HyperliquidConfig
    llm: LLMConfig
    agent: AgentConfig


def load_config(config_path: str = "config.toml") -> Config:
    """Load configuration from TOML file.

    Args:
        config_path: Path to the configuration file

    Returns:
        Parsed configuration object

    Raises:
        FileNotFoundError: If config file doesn't exist
        ValueError: If required fields are missing or invalid
    """
    import os
    import tomllib
    from pathlib import Path

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
    for field in required_hl_fields:
        if field not in hl_data:
            raise ValueError(f"Missing required field in [hyperliquid]: {field}")

    hyperliquid_config = HyperliquidConfig(
        account_address=hl_data["account_address"],
        secret_key=hl_data["secret_key"],
        base_url=hl_data["base_url"],
    )

    # Parse LLM config
    llm_data = data["llm"]
    required_llm_fields = ["provider", "model", "api_key"]
    for field in required_llm_fields:
        if field not in llm_data:
            raise ValueError(f"Missing required field in [llm]: {field}")

    if llm_data["provider"] not in ["openai", "anthropic"]:
        raise ValueError(
            f"Invalid LLM provider: {llm_data['provider']}. Must be 'openai' or 'anthropic'"
        )

    llm_config = LLMConfig(
        provider=llm_data["provider"],
        model=llm_data["model"],
        api_key=llm_data["api_key"],
        temperature=llm_data.get("temperature", 0.7),
        max_tokens=llm_data.get("max_tokens", 1000),
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

    return Config(hyperliquid=hyperliquid_config, llm=llm_config, agent=agent_config)

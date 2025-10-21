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
    """
    # TODO: Implement TOML parsing
    raise NotImplementedError("Configuration loading not yet implemented")

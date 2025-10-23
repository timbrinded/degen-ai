"""Unit tests for configuration module."""

import os
import tempfile

import pytest

from hyperliquid_agent.config import (
    load_config,
)


@pytest.fixture
def valid_config_toml():
    """Valid configuration TOML content."""
    return """
[hyperliquid]
account_address = "0x1234567890123456789012345678901234567890"
secret_key = "0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
base_url = "https://api.hyperliquid-testnet.xyz"

[llm]
provider = "openai"
model = "gpt-4"
api_key = "sk-test123"
temperature = 0.8
max_tokens = 1500

[agent]
tick_interval_seconds = 120
max_retries = 3
retry_backoff_base = 1.5
log_level = "DEBUG"
prompt_template_path = "prompts/custom.txt"
"""


@pytest.fixture
def minimal_config_toml():
    """Minimal configuration with only required fields."""
    return """
[hyperliquid]
account_address = "0x1234567890123456789012345678901234567890"
secret_key = "0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
base_url = "https://api.hyperliquid-testnet.xyz"

[llm]
provider = "anthropic"
model = "claude-3-opus-20240229"
api_key = "sk-ant-test123"

[agent]
"""


def test_load_valid_config(valid_config_toml):
    """Test loading a valid configuration file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write(valid_config_toml)
        config_path = f.name

    try:
        config = load_config(config_path)

        # Verify Hyperliquid config
        assert config.hyperliquid.account_address == "0x1234567890123456789012345678901234567890"
        assert (
            config.hyperliquid.secret_key
            == "0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
        )
        assert config.hyperliquid.base_url == "https://api.hyperliquid-testnet.xyz"

        # Verify LLM config
        assert config.llm.provider == "openai"
        assert config.llm.model == "gpt-4"
        assert config.llm.api_key == "sk-test123"
        assert config.llm.temperature == 0.8
        assert config.llm.max_tokens == 1500

        # Verify Agent config
        assert config.agent.tick_interval_seconds == 120
        assert config.agent.max_retries == 3
        assert config.agent.retry_backoff_base == 1.5
        assert config.agent.log_level == "DEBUG"
        assert config.agent.prompt_template_path == "prompts/custom.txt"
    finally:
        os.unlink(config_path)


def test_load_minimal_config_with_defaults(minimal_config_toml):
    """Test loading minimal config applies default values."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write(minimal_config_toml)
        config_path = f.name

    try:
        config = load_config(config_path)

        # Verify required fields are loaded
        assert config.hyperliquid.account_address == "0x1234567890123456789012345678901234567890"
        assert config.llm.provider == "anthropic"
        assert config.llm.model == "claude-3-opus-20240229"

        # Verify defaults are applied
        assert config.llm.temperature == 0.7
        assert config.llm.max_tokens == 10000
        assert config.agent.tick_interval_seconds == 60
        assert config.agent.max_retries == 5
        assert config.agent.retry_backoff_base == 2.0
        assert config.agent.log_level == "INFO"
        assert config.agent.prompt_template_path == "prompts/default.txt"
    finally:
        os.unlink(config_path)


def test_load_config_file_not_found():
    """Test loading non-existent config file raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError, match="Configuration file not found"):
        load_config("nonexistent_config.toml")


def test_load_config_missing_hyperliquid_section():
    """Test loading config without hyperliquid section raises ValueError."""
    config_content = """
[llm]
provider = "openai"
model = "gpt-4"
api_key = "sk-test"
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write(config_content)
        config_path = f.name

    try:
        with pytest.raises(ValueError, match="Missing required configuration section.*hyperliquid"):
            load_config(config_path)
    finally:
        os.unlink(config_path)


def test_load_config_missing_llm_section():
    """Test loading config without llm section raises ValueError."""
    config_content = """
[hyperliquid]
account_address = "0x1234567890123456789012345678901234567890"
secret_key = "0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
base_url = "https://api.hyperliquid-testnet.xyz"
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write(config_content)
        config_path = f.name

    try:
        with pytest.raises(ValueError, match="Missing required configuration section.*llm"):
            load_config(config_path)
    finally:
        os.unlink(config_path)


def test_load_config_missing_required_hyperliquid_field():
    """Test loading config with missing hyperliquid field raises ValueError."""
    config_content = """
[hyperliquid]
account_address = "0x1234567890123456789012345678901234567890"
base_url = "https://api.hyperliquid-testnet.xyz"

[llm]
provider = "openai"
model = "gpt-4"
api_key = "sk-test"

[agent]
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write(config_content)
        config_path = f.name

    try:
        with pytest.raises(ValueError, match="Missing required field in.*hyperliquid.*secret_key"):
            load_config(config_path)
    finally:
        os.unlink(config_path)


def test_load_config_missing_required_llm_field():
    """Test loading config with missing llm field raises ValueError."""
    config_content = """
[hyperliquid]
account_address = "0x1234567890123456789012345678901234567890"
secret_key = "0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
base_url = "https://api.hyperliquid-testnet.xyz"

[llm]
provider = "openai"
model = "gpt-4"

[agent]
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write(config_content)
        config_path = f.name

    try:
        with pytest.raises(ValueError, match="Missing required field in.*llm.*api_key"):
            load_config(config_path)
    finally:
        os.unlink(config_path)


def test_load_config_invalid_llm_provider():
    """Test loading config with invalid LLM provider raises ValueError."""
    config_content = """
[hyperliquid]
account_address = "0x1234567890123456789012345678901234567890"
secret_key = "0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
base_url = "https://api.hyperliquid-testnet.xyz"

[llm]
provider = "invalid_provider"
model = "gpt-4"
api_key = "sk-test"

[agent]
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write(config_content)
        config_path = f.name

    try:
        with pytest.raises(
            ValueError, match="Invalid LLM provider.*Must be 'openai' or 'anthropic'"
        ):
            load_config(config_path)
    finally:
        os.unlink(config_path)


def test_log_level_environment_variable_override(minimal_config_toml):
    """Test LOG_LEVEL environment variable overrides config file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write(minimal_config_toml)
        config_path = f.name

    try:
        # Set environment variable
        os.environ["LOG_LEVEL"] = "ERROR"
        config = load_config(config_path)
        assert config.agent.log_level == "ERROR"

        # Test lowercase is converted to uppercase
        os.environ["LOG_LEVEL"] = "warning"
        config = load_config(config_path)
        assert config.agent.log_level == "WARNING"
    finally:
        os.unlink(config_path)
        # Clean up environment variable
        if "LOG_LEVEL" in os.environ:
            del os.environ["LOG_LEVEL"]

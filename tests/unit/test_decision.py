"""Unit tests for DecisionEngine module."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from hyperliquid_agent.config import LLMConfig
from hyperliquid_agent.decision import (
    DecisionEngine,
    DecisionResult,
    PromptTemplate,
    TradeAction,
)
from hyperliquid_agent.monitor import AccountState, Position


@pytest.fixture
def llm_config_openai():
    """Create OpenAI LLM configuration."""
    return LLMConfig(
        provider="openai",
        model="gpt-4",
        api_key="sk-test123",
        temperature=0.7,
        max_tokens=10000,
    )


@pytest.fixture
def llm_config_anthropic():
    """Create Anthropic LLM configuration."""
    return LLMConfig(
        provider="anthropic",
        model="claude-3-opus-20240229",
        api_key="sk-ant-test123",
        temperature=0.7,
        max_tokens=10000,
    )


@pytest.fixture
def sample_prompt_template():
    """Create a temporary prompt template file."""
    template_content = """Portfolio Value: ${portfolio_value}
Available Balance: ${available_balance}
Timestamp: {timestamp}

Positions:
{positions}

Strategies:
{strategies}

Provide your decision in JSON format."""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write(template_content)
        return f.name


@pytest.fixture
def sample_account_state():
    """Create a sample account state."""
    return AccountState(
        portfolio_value=10000.0,
        available_balance=5000.0,
        positions=[
            Position(
                coin="BTC",
                size=0.5,
                entry_price=50000.0,
                current_price=51000.0,
                unrealized_pnl=500.0,
                market_type="perp",
            ),
            Position(
                coin="ETH",
                size=2.0,
                entry_price=3000.0,
                current_price=3100.0,
                unrealized_pnl=200.0,
                market_type="spot",
            ),
        ],
        timestamp=1234567890.0,
        is_stale=False,
    )


@pytest.fixture
def empty_account_state():
    """Create an account state with no positions."""
    return AccountState(
        portfolio_value=1000.0,
        available_balance=1000.0,
        positions=[],
        timestamp=1234567890.0,
        is_stale=False,
    )


def test_prompt_template_initialization(sample_prompt_template):
    """Test PromptTemplate initializes correctly."""
    template = PromptTemplate(sample_prompt_template, strategies_dir="nonexistent")

    assert template.template is not None
    assert len(template.template) > 0
    assert template.strategies == []


def test_prompt_template_file_not_found():
    """Test PromptTemplate raises error for missing file."""
    with pytest.raises(FileNotFoundError, match="Prompt template not found"):
        PromptTemplate("nonexistent_template.txt")


def test_prompt_template_format_with_positions(sample_prompt_template, sample_account_state):
    """Test prompt formatting with positions."""
    template = PromptTemplate(sample_prompt_template, strategies_dir="nonexistent")
    formatted = template.format(sample_account_state)

    assert "10000.0" in formatted
    assert "5000.0" in formatted
    assert "1234567890.0" in formatted
    assert "BTC" in formatted
    assert "ETH" in formatted
    assert "0.5000" in formatted
    assert "50000.00" in formatted


def test_prompt_template_format_empty_positions(sample_prompt_template, empty_account_state):
    """Test prompt formatting with no positions."""
    template = PromptTemplate(sample_prompt_template, strategies_dir="nonexistent")
    formatted = template.format(empty_account_state)

    assert "1000.0" in formatted
    assert "No open positions" in formatted


def test_prompt_template_format_positions_details(sample_prompt_template, sample_account_state):
    """Test position formatting includes all details."""
    template = PromptTemplate(sample_prompt_template, strategies_dir="nonexistent")
    formatted = template.format(sample_account_state)

    # Check BTC position details
    assert "BTC (perp)" in formatted
    assert "Size=0.5000" in formatted
    assert "Entry=$50000.00" in formatted
    assert "Current=$51000.00" in formatted
    assert "PnL=$500.00" in formatted

    # Check ETH position details
    assert "ETH (spot)" in formatted
    assert "Size=2.0000" in formatted


@patch("openai.OpenAI")
def test_decision_engine_init_openai(mock_openai_class, llm_config_openai, sample_prompt_template):
    """Test DecisionEngine initializes with OpenAI provider."""
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client

    template = PromptTemplate(sample_prompt_template, strategies_dir="nonexistent")
    engine = DecisionEngine(llm_config_openai, template)

    assert engine.llm_config == llm_config_openai
    assert engine.prompt_template == template
    assert engine.client == mock_client
    mock_openai_class.assert_called_once_with(api_key="sk-test123")


@patch("anthropic.Anthropic")
def test_decision_engine_init_anthropic(mock_anthropic_class, llm_config_anthropic, sample_prompt_template):
    """Test DecisionEngine initializes with Anthropic provider."""
    mock_client = MagicMock()
    mock_anthropic_class.return_value = mock_client

    template = PromptTemplate(sample_prompt_template, strategies_dir="nonexistent")
    engine = DecisionEngine(llm_config_anthropic, template)

    assert engine.llm_config == llm_config_anthropic
    assert engine.client == mock_client
    mock_anthropic_class.assert_called_once_with(api_key="sk-ant-test123")


def test_decision_engine_init_invalid_provider(sample_prompt_template):
    """Test DecisionEngine raises error for invalid provider."""
    invalid_config = LLMConfig(
        provider="invalid",
        model="test-model",
        api_key="test-key",
    )

    template = PromptTemplate(sample_prompt_template, strategies_dir="nonexistent")

    with pytest.raises(ValueError, match="Unsupported LLM provider: invalid"):
        DecisionEngine(invalid_config, template)


def test_parse_response_valid_json():
    """Test parsing valid JSON response."""
    response = json.dumps({
        "selected_strategy": "funding-harvest",
        "actions": [
            {
                "action_type": "buy",
                "coin": "BTC",
                "market_type": "perp",
                "size": 0.1,
                "price": 50000.0,
                "reasoning": "Good entry point"
            }
        ]
    })

    template = PromptTemplate(Path(__file__).parent.parent.parent / "prompts" / "default.txt", strategies_dir="nonexistent")
    engine = DecisionEngine(
        LLMConfig(provider="openai", model="gpt-4", api_key="test"),
        template
    )

    actions, strategy, allocation = engine._parse_response(response)

    assert len(actions) == 1
    assert strategy == "funding-harvest"
    assert allocation is None

    action = actions[0]
    assert action.action_type == "buy"
    assert action.coin == "BTC"
    assert action.market_type == "perp"
    assert action.size == 0.1
    assert action.price == 50000.0
    assert action.reasoning == "Good entry point"


def test_parse_response_with_markdown_code_block():
    """Test parsing JSON wrapped in markdown code blocks."""
    response = """```json
{
    "selected_strategy": "trend-following",
    "actions": [
        {
            "action_type": "sell",
            "coin": "ETH",
            "market_type": "spot",
            "size": 1.0,
            "reasoning": "Take profit"
        }
    ]
}
```"""

    template = PromptTemplate(Path(__file__).parent.parent.parent / "prompts" / "default.txt", strategies_dir="nonexistent")
    engine = DecisionEngine(
        LLMConfig(provider="openai", model="gpt-4", api_key="test"),
        template
    )

    actions, strategy, allocation = engine._parse_response(response)

    assert len(actions) == 1
    assert strategy == "trend-following"
    assert actions[0].action_type == "sell"
    assert actions[0].coin == "ETH"


def test_parse_response_with_target_allocation():
    """Test parsing response with target allocation."""
    response = json.dumps({
        "selected_strategy": "portfolio-rebalance",
        "target_allocation": {
            "BTC": 0.5,
            "ETH": 0.3,
            "SOL": 0.2
        },
        "actions": []
    })

    template = PromptTemplate(Path(__file__).parent.parent.parent / "prompts" / "default.txt", strategies_dir="nonexistent")
    engine = DecisionEngine(
        LLMConfig(provider="openai", model="gpt-4", api_key="test"),
        template
    )

    actions, strategy, allocation = engine._parse_response(response)

    assert len(actions) == 0
    assert strategy == "portfolio-rebalance"
    assert allocation is not None
    assert allocation["BTC"] == 0.5
    assert allocation["ETH"] == 0.3
    assert allocation["SOL"] == 0.2


def test_parse_response_hold_action():
    """Test parsing hold action."""
    response = json.dumps({
        "actions": [
            {
                "action_type": "hold",
                "coin": "BTC",
                "market_type": "perp",
                "reasoning": "Wait for better entry"
            }
        ]
    })

    template = PromptTemplate(Path(__file__).parent.parent.parent / "prompts" / "default.txt", strategies_dir="nonexistent")
    engine = DecisionEngine(
        LLMConfig(provider="openai", model="gpt-4", api_key="test"),
        template
    )

    actions, strategy, allocation = engine._parse_response(response)

    assert len(actions) == 1
    assert actions[0].action_type == "hold"
    assert actions[0].size is None
    assert actions[0].price is None


def test_parse_response_invalid_json():
    """Test parsing invalid JSON raises ValueError."""
    response = "This is not valid JSON"

    template = PromptTemplate(Path(__file__).parent.parent.parent / "prompts" / "default.txt", strategies_dir="nonexistent")
    engine = DecisionEngine(
        LLMConfig(provider="openai", model="gpt-4", api_key="test"),
        template
    )

    with pytest.raises(ValueError, match="No JSON object found in response"):
        engine._parse_response(response)


def test_parse_response_no_json_object():
    """Test parsing response without JSON object."""
    response = "Some text without any JSON"

    template = PromptTemplate(Path(__file__).parent.parent.parent / "prompts" / "default.txt", strategies_dir="nonexistent")
    engine = DecisionEngine(
        LLMConfig(provider="openai", model="gpt-4", api_key="test"),
        template
    )

    with pytest.raises(ValueError, match="No JSON object found in response"):
        engine._parse_response(response)


def test_parse_response_malformed_json():
    """Test parsing malformed JSON raises ValueError."""
    response = '{"actions": [{"action_type": "buy", "coin": "BTC"}]}'  # Valid JSON with closing brace

    template = PromptTemplate(Path(__file__).parent.parent.parent / "prompts" / "default.txt", strategies_dir="nonexistent")
    engine = DecisionEngine(
        LLMConfig(provider="openai", model="gpt-4", api_key="test"),
        template
    )

    # Test with actual malformed JSON that has closing brace but invalid structure
    malformed = '{"actions": [{"action_type": "buy", "coin": "BTC",}]}'  # Trailing comma
    with pytest.raises(ValueError, match="Invalid JSON in response"):
        engine._parse_response(malformed)


def test_parse_response_llm_error_state():
    """Test parsing response with LLM error state."""
    response = json.dumps({
        "error": True,
        "error_reason": "Insufficient data to make decision"
    })

    template = PromptTemplate(Path(__file__).parent.parent.parent / "prompts" / "default.txt", strategies_dir="nonexistent")
    engine = DecisionEngine(
        LLMConfig(provider="openai", model="gpt-4", api_key="test"),
        template
    )

    with pytest.raises(ValueError, match="LLM decision error: Insufficient data to make decision"):
        engine._parse_response(response)


def test_parse_response_invalid_action_type():
    """Test parsing skips actions with invalid action_type."""
    response = json.dumps({
        "actions": [
            {
                "action_type": "invalid_action",
                "coin": "BTC",
                "market_type": "perp"
            },
            {
                "action_type": "buy",
                "coin": "ETH",
                "market_type": "spot",
                "size": 1.0
            }
        ]
    })

    template = PromptTemplate(Path(__file__).parent.parent.parent / "prompts" / "default.txt", strategies_dir="nonexistent")
    engine = DecisionEngine(
        LLMConfig(provider="openai", model="gpt-4", api_key="test"),
        template
    )

    actions, _, _ = engine._parse_response(response)

    # Should skip invalid action and only return valid one
    assert len(actions) == 1
    assert actions[0].action_type == "buy"
    assert actions[0].coin == "ETH"


def test_parse_response_missing_coin():
    """Test parsing skips actions without coin."""
    response = json.dumps({
        "actions": [
            {
                "action_type": "buy",
                "market_type": "perp",
                "size": 0.1
            }
        ]
    })

    template = PromptTemplate(Path(__file__).parent.parent.parent / "prompts" / "default.txt", strategies_dir="nonexistent")
    engine = DecisionEngine(
        LLMConfig(provider="openai", model="gpt-4", api_key="test"),
        template
    )

    actions, _, _ = engine._parse_response(response)

    # Should skip action without coin
    assert len(actions) == 0


def test_parse_response_invalid_market_type():
    """Test parsing defaults invalid market_type to perp."""
    response = json.dumps({
        "actions": [
            {
                "action_type": "buy",
                "coin": "BTC",
                "market_type": "invalid_market",
                "size": 0.1
            }
        ]
    })

    template = PromptTemplate(Path(__file__).parent.parent.parent / "prompts" / "default.txt", strategies_dir="nonexistent")
    engine = DecisionEngine(
        LLMConfig(provider="openai", model="gpt-4", api_key="test"),
        template
    )

    actions, _, _ = engine._parse_response(response)

    assert len(actions) == 1
    assert actions[0].market_type == "perp"  # Should default to perp


def test_parse_response_actions_not_list():
    """Test parsing raises error when actions is not a list."""
    response = json.dumps({
        "actions": "not a list"
    })

    template = PromptTemplate(Path(__file__).parent.parent.parent / "prompts" / "default.txt", strategies_dir="nonexistent")
    engine = DecisionEngine(
        LLMConfig(provider="openai", model="gpt-4", api_key="test"),
        template
    )

    with pytest.raises(ValueError, match="'actions' field must be a list"):
        engine._parse_response(response)


@patch("openai.OpenAI")
def test_get_decision_success(mock_openai_class, llm_config_openai, sample_prompt_template, sample_account_state):
    """Test successful decision retrieval."""
    # Setup mock
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = json.dumps({
        "selected_strategy": "test-strategy",
        "actions": [
            {
                "action_type": "buy",
                "coin": "BTC",
                "market_type": "perp",
                "size": 0.1,
                "reasoning": "Test"
            }
        ]
    })
    mock_response.usage = MagicMock()
    mock_response.usage.prompt_tokens = 100
    mock_response.usage.completion_tokens = 50

    mock_client.chat.completions.create.return_value = mock_response
    mock_openai_class.return_value = mock_client

    template = PromptTemplate(sample_prompt_template, strategies_dir="nonexistent")
    engine = DecisionEngine(llm_config_openai, template)

    result = engine.get_decision(sample_account_state)

    assert result.success is True
    assert result.error is None
    assert len(result.actions) == 1
    assert result.selected_strategy == "test-strategy"
    assert result.input_tokens == 100
    assert result.output_tokens == 50


@patch("openai.OpenAI")
def test_get_decision_llm_failure(mock_openai_class, llm_config_openai, sample_prompt_template, sample_account_state):
    """Test decision retrieval handles LLM failures."""
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = Exception("API error")
    mock_openai_class.return_value = mock_client

    template = PromptTemplate(sample_prompt_template, strategies_dir="nonexistent")
    engine = DecisionEngine(llm_config_openai, template)

    result = engine.get_decision(sample_account_state)

    assert result.success is False
    assert result.error == "API error"
    assert len(result.actions) == 0
    assert result.raw_response == ""


@patch("openai.OpenAI")
def test_get_decision_parsing_failure(mock_openai_class, llm_config_openai, sample_prompt_template, sample_account_state):
    """Test decision retrieval handles parsing failures."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Invalid response without JSON"
    mock_response.usage = MagicMock()
    mock_response.usage.prompt_tokens = 100
    mock_response.usage.completion_tokens = 50

    mock_client.chat.completions.create.return_value = mock_response
    mock_openai_class.return_value = mock_client

    template = PromptTemplate(sample_prompt_template, strategies_dir="nonexistent")
    engine = DecisionEngine(llm_config_openai, template)

    result = engine.get_decision(sample_account_state)

    assert result.success is False
    assert "No JSON object found in response" in result.error
    assert len(result.actions) == 0

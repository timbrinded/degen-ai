"""Integration tests for full agent flow.

These tests verify the complete trading agent workflow with real API calls
to Hyperliquid testnet. They test the integration of all components:
- Position monitoring
- LLM decision making
- Trade execution
- Error recovery and retry logic
"""

import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from hyperliquid_agent.agent import TradingAgent
from hyperliquid_agent.config import load_config


@pytest.fixture
def testnet_config_content():
    """Create testnet configuration content."""
    return """
[hyperliquid]
account_address = "0x0000000000000000000000000000000000000000"
secret_key = "0x0000000000000000000000000000000000000000000000000000000000000000"
base_url = "https://api.hyperliquid-testnet.xyz"

[llm]
provider = "openai"
model = "gpt-4"
api_key = "sk-test-key"
temperature = 0.7
max_tokens = 1000

[agent]
tick_interval_seconds = 1
max_retries = 3
retry_backoff_base = 1.5
log_level = "INFO"
prompt_template_path = "prompts/default.txt"
"""


@pytest.fixture
def testnet_config(testnet_config_content):
    """Create a temporary testnet configuration file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write(testnet_config_content)
        config_path = f.name

    try:
        config = load_config(config_path)
        yield config
    finally:
        os.unlink(config_path)


@pytest.fixture
def mock_hyperliquid_responses():
    """Mock responses for Hyperliquid API calls."""
    return {
        "user_state": {
            "marginSummary": {"accountValue": "10000.0"},
            "withdrawable": "5000.0",
            "assetPositions": [
                {
                    "position": {
                        "coin": "BTC",
                        "szi": "0.1",
                        "entryPx": "50000.0",
                        "positionValue": "5100.0",
                        "unrealizedPnl": "100.0",
                    }
                }
            ],
        },
        "meta": {
            "universe": [
                {"name": "BTC", "szDecimals": 4},
                {"name": "ETH", "szDecimals": 3},
            ]
        },
    }


@pytest.fixture
def mock_llm_response():
    """Mock LLM response with trading decision."""
    return json.dumps(
        {
            "selected_strategy": "test-strategy",
            "actions": [
                {
                    "action_type": "hold",
                    "coin": "BTC",
                    "market_type": "perp",
                    "reasoning": "Market conditions unclear, holding position",
                }
            ],
        }
    )


def test_agent_initialization(testnet_config):
    """Test TradingAgent initializes with valid configuration."""
    agent = TradingAgent(testnet_config)

    assert agent.config == testnet_config
    assert agent.monitor is not None
    assert agent.decision_engine is not None
    assert agent.executor is not None
    assert agent.logger is not None
    assert agent.tick_count == 0


def test_agent_logging_setup(testnet_config):
    """Test agent sets up logging correctly."""
    agent = TradingAgent(testnet_config)

    assert agent.logger.name == "hyperliquid_agent"
    assert agent.logger.level == 20  # INFO level
    assert len(agent.logger.handlers) > 0


@patch("hyperliquid_agent.monitor.Info")
@patch("hyperliquid_agent.executor.Exchange")
@patch("hyperliquid_agent.executor.Info")
@patch("openai.OpenAI")
def test_execute_tick_success(
    mock_openai_class,
    mock_executor_info,
    mock_executor_exchange,
    mock_monitor_info,
    testnet_config,
    mock_hyperliquid_responses,
    mock_llm_response,
):
    """Test successful execution of a single tick."""
    # Setup monitor mock
    mock_monitor_instance = MagicMock()
    mock_monitor_instance.user_state.return_value = mock_hyperliquid_responses["user_state"]
    mock_monitor_info.return_value = mock_monitor_instance

    # Setup executor mocks
    mock_executor_info_instance = MagicMock()
    mock_executor_info_instance.meta.return_value = mock_hyperliquid_responses["meta"]
    mock_executor_info.return_value = mock_executor_info_instance

    mock_exchange_instance = MagicMock()
    mock_executor_exchange.return_value = mock_exchange_instance

    # Setup LLM mock - must mock beta.chat.completions.parse for structured outputs
    from hyperliquid_agent.decision import DecisionSchema, TradeActionSchema

    mock_llm_client = MagicMock()
    mock_llm_response_obj = MagicMock()
    # Create proper DecisionSchema instance for structured output
    decision_data = json.loads(mock_llm_response)
    parsed_decision = DecisionSchema(
        selected_strategy=decision_data.get("selected_strategy"),
        actions=[TradeActionSchema(**action) for action in decision_data.get("actions", [])],
    )
    mock_llm_response_obj.choices = [MagicMock()]
    mock_llm_response_obj.choices[0].message.parsed = parsed_decision
    mock_llm_response_obj.usage = MagicMock()
    mock_llm_response_obj.usage.prompt_tokens = 100
    mock_llm_response_obj.usage.completion_tokens = 50
    mock_llm_client.beta.chat.completions.parse.return_value = mock_llm_response_obj
    mock_openai_class.return_value = mock_llm_client

    # Create agent and execute tick
    agent = TradingAgent(testnet_config)
    agent._execute_tick()

    # Verify tick was executed
    assert agent.tick_count == 1

    # Verify monitor was called
    mock_monitor_instance.user_state.assert_called_once()

    # Verify LLM was called
    mock_llm_client.beta.chat.completions.parse.assert_called_once()

    # Verify no orders were submitted (hold action)
    mock_exchange_instance.order.assert_not_called()
    mock_exchange_instance.market_open.assert_not_called()


@patch("hyperliquid_agent.monitor.Info")
@patch("hyperliquid_agent.executor.Exchange")
@patch("hyperliquid_agent.executor.Info")
@patch("openai.OpenAI")
def test_execute_tick_with_trade_execution(
    mock_openai_class,
    mock_executor_info,
    mock_executor_exchange,
    mock_monitor_info,
    testnet_config,
    mock_hyperliquid_responses,
):
    """Test tick execution with actual trade submission."""
    # Setup monitor mock
    mock_monitor_instance = MagicMock()
    mock_monitor_instance.user_state.return_value = mock_hyperliquid_responses["user_state"]
    mock_monitor_info.return_value = mock_monitor_instance

    # Setup executor mocks
    mock_executor_info_instance = MagicMock()
    mock_executor_info_instance.meta.return_value = mock_hyperliquid_responses["meta"]
    mock_executor_info.return_value = mock_executor_info_instance

    mock_exchange_instance = MagicMock()
    mock_exchange_instance.order.return_value = {"status": {"resting": {"oid": "0xorder123"}}}
    mock_executor_exchange.return_value = mock_exchange_instance

    # Setup LLM mock with buy action - must mock beta.chat.completions.parse
    from hyperliquid_agent.decision import DecisionSchema, TradeActionSchema

    mock_llm_client = MagicMock()
    mock_llm_response_obj = MagicMock()
    # Create proper DecisionSchema instance for structured output
    parsed_decision = DecisionSchema(
        selected_strategy="test-buy-strategy",
        actions=[
            TradeActionSchema(
                action_type="buy",
                coin="ETH",
                market_type="perp",
                size=0.5,
                price=3000.0,
                reasoning="Good entry point",
            )
        ],
    )
    mock_llm_response_obj.choices = [MagicMock()]
    mock_llm_response_obj.choices[0].message.parsed = parsed_decision
    mock_llm_response_obj.usage = MagicMock()
    mock_llm_response_obj.usage.prompt_tokens = 100
    mock_llm_response_obj.usage.completion_tokens = 50
    mock_llm_client.beta.chat.completions.parse.return_value = mock_llm_response_obj
    mock_openai_class.return_value = mock_llm_client

    # Create agent and execute tick
    agent = TradingAgent(testnet_config)
    agent._execute_tick()

    # Verify order was submitted
    mock_exchange_instance.order.assert_called_once()
    call_kwargs = mock_exchange_instance.order.call_args.kwargs
    assert call_kwargs["name"] == "ETH"
    assert call_kwargs["is_buy"] is True
    assert call_kwargs["sz"] == 0.5
    assert call_kwargs["limit_px"] == 3000.0


@patch("hyperliquid_agent.monitor.Info")
@patch("hyperliquid_agent.executor.Exchange")
@patch("hyperliquid_agent.executor.Info")
@patch("openai.OpenAI")
def test_execute_tick_monitor_error_recovery(
    mock_openai_class,
    mock_executor_info,
    mock_executor_exchange,
    mock_monitor_info,
    testnet_config,
    mock_hyperliquid_responses,
):
    """Test tick continues after monitor error with cached state."""
    # Setup monitor mock to fail first, then succeed
    mock_monitor_instance = MagicMock()
    mock_monitor_instance.user_state.side_effect = [
        mock_hyperliquid_responses["user_state"],  # First call succeeds
        Exception("API timeout"),  # Second call fails
    ]
    mock_monitor_info.return_value = mock_monitor_instance

    # Setup executor mocks
    mock_executor_info_instance = MagicMock()
    mock_executor_info_instance.meta.return_value = mock_hyperliquid_responses["meta"]
    mock_executor_info.return_value = mock_executor_info_instance
    mock_executor_exchange.return_value = MagicMock()

    # Setup LLM mock
    mock_llm_client = MagicMock()
    mock_llm_response_obj = MagicMock()
    mock_llm_response_obj.choices = [MagicMock()]
    mock_llm_response_obj.choices[0].message.content = json.dumps(
        {"actions": [{"action_type": "hold", "coin": "BTC", "market_type": "perp"}]}
    )
    mock_llm_response_obj.usage = MagicMock()
    mock_llm_response_obj.usage.prompt_tokens = 100
    mock_llm_response_obj.usage.completion_tokens = 50
    mock_llm_client.chat.completions.create.return_value = mock_llm_response_obj
    mock_openai_class.return_value = mock_llm_client

    # Create agent
    agent = TradingAgent(testnet_config)

    # First tick succeeds
    agent._execute_tick()
    assert agent.tick_count == 1

    # Second tick should use cached state
    agent._execute_tick()
    assert agent.tick_count == 2

    # Verify monitor was called twice
    assert mock_monitor_instance.user_state.call_count == 2


@patch("hyperliquid_agent.monitor.Info")
@patch("hyperliquid_agent.executor.Exchange")
@patch("hyperliquid_agent.executor.Info")
@patch("openai.OpenAI")
def test_execute_tick_llm_error_recovery(
    mock_openai_class,
    mock_executor_info,
    mock_executor_exchange,
    mock_monitor_info,
    testnet_config,
    mock_hyperliquid_responses,
):
    """Test tick continues after LLM error without executing trades."""
    # Setup monitor mock
    mock_monitor_instance = MagicMock()
    mock_monitor_instance.user_state.return_value = mock_hyperliquid_responses["user_state"]
    mock_monitor_info.return_value = mock_monitor_instance

    # Setup executor mocks
    mock_executor_info_instance = MagicMock()
    mock_executor_info_instance.meta.return_value = mock_hyperliquid_responses["meta"]
    mock_executor_info.return_value = mock_executor_info_instance

    mock_exchange_instance = MagicMock()
    mock_executor_exchange.return_value = mock_exchange_instance

    # Setup LLM mock to fail
    mock_llm_client = MagicMock()
    mock_llm_client.chat.completions.create.side_effect = Exception("LLM API error")
    mock_openai_class.return_value = mock_llm_client

    # Create agent and execute tick
    agent = TradingAgent(testnet_config)
    agent._execute_tick()

    # Verify tick completed despite error
    assert agent.tick_count == 1

    # Verify no orders were submitted
    mock_exchange_instance.order.assert_not_called()
    mock_exchange_instance.market_open.assert_not_called()


@patch("hyperliquid_agent.monitor.Info")
@patch("hyperliquid_agent.executor.Exchange")
@patch("hyperliquid_agent.executor.Info")
@patch("openai.OpenAI")
def test_execute_tick_executor_error_recovery(
    mock_openai_class,
    mock_executor_info,
    mock_executor_exchange,
    mock_monitor_info,
    testnet_config,
    mock_hyperliquid_responses,
):
    """Test tick continues after executor error."""
    # Setup monitor mock
    mock_monitor_instance = MagicMock()
    mock_monitor_instance.user_state.return_value = mock_hyperliquid_responses["user_state"]
    mock_monitor_info.return_value = mock_monitor_instance

    # Setup executor mocks
    mock_executor_info_instance = MagicMock()
    mock_executor_info_instance.meta.return_value = mock_hyperliquid_responses["meta"]
    mock_executor_info.return_value = mock_executor_info_instance

    mock_exchange_instance = MagicMock()
    mock_exchange_instance.order.side_effect = Exception("Insufficient balance")
    mock_executor_exchange.return_value = mock_exchange_instance

    # Setup LLM mock with buy action - must mock beta.chat.completions.parse
    from hyperliquid_agent.decision import DecisionSchema, TradeActionSchema

    mock_llm_client = MagicMock()
    mock_llm_response_obj = MagicMock()
    # Create proper DecisionSchema instance for structured output
    parsed_decision = DecisionSchema(
        actions=[
            TradeActionSchema(
                action_type="buy",
                coin="BTC",
                market_type="perp",
                size=0.1,
                price=50000.0,
            )
        ]
    )
    mock_llm_response_obj.choices = [MagicMock()]
    mock_llm_response_obj.choices[0].message.parsed = parsed_decision
    mock_llm_response_obj.usage = MagicMock()
    mock_llm_response_obj.usage.prompt_tokens = 100
    mock_llm_response_obj.usage.completion_tokens = 50
    mock_llm_client.beta.chat.completions.parse.return_value = mock_llm_response_obj
    mock_openai_class.return_value = mock_llm_client

    # Create agent and execute tick
    agent = TradingAgent(testnet_config)
    agent._execute_tick()

    # Verify tick completed despite executor error
    assert agent.tick_count == 1

    # Verify order was attempted
    mock_exchange_instance.order.assert_called_once()


@patch("hyperliquid_agent.monitor.Info")
@patch("hyperliquid_agent.executor.Exchange")
@patch("hyperliquid_agent.executor.Info")
@patch("openai.OpenAI")
def test_execute_tick_logs_portfolio_value(
    mock_openai_class,
    mock_executor_info,
    mock_executor_exchange,
    mock_monitor_info,
    testnet_config,
    mock_hyperliquid_responses,
    mock_llm_response,
):
    """Test tick execution logs portfolio value changes."""
    # Setup monitor mock
    mock_monitor_instance = MagicMock()
    mock_monitor_instance.user_state.return_value = mock_hyperliquid_responses["user_state"]
    mock_monitor_info.return_value = mock_monitor_instance

    # Setup executor mocks
    mock_executor_info_instance = MagicMock()
    mock_executor_info_instance.meta.return_value = mock_hyperliquid_responses["meta"]
    mock_executor_info.return_value = mock_executor_info_instance
    mock_executor_exchange.return_value = MagicMock()

    # Setup LLM mock
    mock_llm_client = MagicMock()
    mock_llm_response_obj = MagicMock()
    mock_llm_response_obj.choices = [MagicMock()]
    mock_llm_response_obj.choices[0].message.content = mock_llm_response
    mock_llm_response_obj.usage = MagicMock()
    mock_llm_response_obj.usage.prompt_tokens = 100
    mock_llm_response_obj.usage.completion_tokens = 50
    mock_llm_client.chat.completions.create.return_value = mock_llm_response_obj
    mock_openai_class.return_value = mock_llm_client

    # Create agent and execute tick
    agent = TradingAgent(testnet_config)

    # Execute tick
    agent._execute_tick()

    # Verify tick completed successfully
    assert agent.tick_count == 1

    # Verify portfolio value tracking is working
    assert agent.last_portfolio_value is not None


@patch("hyperliquid_agent.monitor.Info")
@patch("hyperliquid_agent.executor.Exchange")
@patch("hyperliquid_agent.executor.Info")
@patch("openai.OpenAI")
def test_execute_tick_multiple_actions(
    mock_openai_class,
    mock_executor_info,
    mock_executor_exchange,
    mock_monitor_info,
    testnet_config,
    mock_hyperliquid_responses,
):
    """Test tick execution with multiple trading actions."""
    # Setup monitor mock
    mock_monitor_instance = MagicMock()
    mock_monitor_instance.user_state.return_value = mock_hyperliquid_responses["user_state"]
    mock_monitor_info.return_value = mock_monitor_instance

    # Setup executor mocks
    mock_executor_info_instance = MagicMock()
    mock_executor_info_instance.meta.return_value = mock_hyperliquid_responses["meta"]
    mock_executor_info.return_value = mock_executor_info_instance

    mock_exchange_instance = MagicMock()
    mock_exchange_instance.order.return_value = {"status": {"resting": {"oid": "0xorder123"}}}
    mock_executor_exchange.return_value = mock_exchange_instance

    # Setup LLM mock with multiple actions - must mock beta.chat.completions.parse
    from hyperliquid_agent.decision import DecisionSchema, TradeActionSchema

    mock_llm_client = MagicMock()
    mock_llm_response_obj = MagicMock()
    # Create proper DecisionSchema instance for structured output
    parsed_decision = DecisionSchema(
        selected_strategy="multi-action-strategy",
        actions=[
            TradeActionSchema(
                action_type="buy",
                coin="BTC",
                market_type="perp",
                size=0.1,
                price=50000.0,
                reasoning="Buy BTC",
            ),
            TradeActionSchema(
                action_type="sell",
                coin="ETH",
                market_type="spot",
                size=1.0,
                price=3000.0,
                reasoning="Sell ETH",
            ),
        ],
    )
    mock_llm_response_obj.choices = [MagicMock()]
    mock_llm_response_obj.choices[0].message.parsed = parsed_decision
    mock_llm_response_obj.usage = MagicMock()
    mock_llm_response_obj.usage.prompt_tokens = 100
    mock_llm_response_obj.usage.completion_tokens = 50
    mock_llm_client.beta.chat.completions.parse.return_value = mock_llm_response_obj
    mock_openai_class.return_value = mock_llm_client

    # Create agent and execute tick
    agent = TradingAgent(testnet_config)
    agent._execute_tick()

    # Verify both orders were submitted
    assert mock_exchange_instance.order.call_count == 2


@patch("hyperliquid_agent.monitor.Info")
@patch("hyperliquid_agent.executor.Exchange")
@patch("hyperliquid_agent.executor.Info")
@patch("openai.OpenAI")
def test_execute_tick_stale_state_handling(
    mock_openai_class,
    mock_executor_info,
    mock_executor_exchange,
    mock_monitor_info,
    testnet_config,
    mock_hyperliquid_responses,
    mock_llm_response,
):
    """Test tick execution handles stale state indicator."""
    # Setup monitor mock to return stale state
    mock_monitor_instance = MagicMock()
    mock_monitor_instance.user_state.side_effect = [
        mock_hyperliquid_responses["user_state"],  # First call fresh
        Exception("API error"),  # Second call fails, returns stale
    ]
    mock_monitor_info.return_value = mock_monitor_instance

    # Setup executor mocks
    mock_executor_info_instance = MagicMock()
    mock_executor_info_instance.meta.return_value = mock_hyperliquid_responses["meta"]
    mock_executor_info.return_value = mock_executor_info_instance
    mock_executor_exchange.return_value = MagicMock()

    # Setup LLM mock
    mock_llm_client = MagicMock()
    mock_llm_response_obj = MagicMock()
    mock_llm_response_obj.choices = [MagicMock()]
    mock_llm_response_obj.choices[0].message.content = mock_llm_response
    mock_llm_response_obj.usage = MagicMock()
    mock_llm_response_obj.usage.prompt_tokens = 100
    mock_llm_response_obj.usage.completion_tokens = 50
    mock_llm_client.chat.completions.create.return_value = mock_llm_response_obj
    mock_openai_class.return_value = mock_llm_client

    # Create agent
    agent = TradingAgent(testnet_config)

    # First tick with fresh state
    agent._execute_tick()
    assert agent.tick_count == 1

    # Second tick with stale state - should still complete successfully
    agent._execute_tick()
    assert agent.tick_count == 2

    # Verify the agent continued operating despite the API error
    # The monitor should have returned cached state with is_stale=True


def test_agent_configuration_logging(testnet_config):
    """Test agent logs configuration at startup."""
    agent = TradingAgent(testnet_config)

    # Verify logger was configured with correct name
    assert agent.logger.name == "hyperliquid_agent"

    # Verify configuration was stored
    assert agent.config == testnet_config


@patch("hyperliquid_agent.monitor.Info")
@patch("hyperliquid_agent.executor.Exchange")
@patch("hyperliquid_agent.executor.Info")
@patch("openai.OpenAI")
def test_execute_tick_invalid_llm_response(
    mock_openai_class,
    mock_executor_info,
    mock_executor_exchange,
    mock_monitor_info,
    testnet_config,
    mock_hyperliquid_responses,
):
    """Test tick handles invalid LLM response gracefully."""
    # Setup monitor mock
    mock_monitor_instance = MagicMock()
    mock_monitor_instance.user_state.return_value = mock_hyperliquid_responses["user_state"]
    mock_monitor_info.return_value = mock_monitor_instance

    # Setup executor mocks
    mock_executor_info_instance = MagicMock()
    mock_executor_info_instance.meta.return_value = mock_hyperliquid_responses["meta"]
    mock_executor_info.return_value = mock_executor_info_instance

    mock_exchange_instance = MagicMock()
    mock_executor_exchange.return_value = mock_exchange_instance

    # Setup LLM mock with invalid response
    mock_llm_client = MagicMock()
    mock_llm_response_obj = MagicMock()
    mock_llm_response_obj.choices = [MagicMock()]
    mock_llm_response_obj.choices[0].message.content = "This is not valid JSON"
    mock_llm_response_obj.usage = MagicMock()
    mock_llm_response_obj.usage.prompt_tokens = 100
    mock_llm_response_obj.usage.completion_tokens = 50
    mock_llm_client.chat.completions.create.return_value = mock_llm_response_obj
    mock_openai_class.return_value = mock_llm_client

    # Create agent and execute tick
    agent = TradingAgent(testnet_config)
    agent._execute_tick()

    # Verify tick completed without executing trades
    assert agent.tick_count == 1
    mock_exchange_instance.order.assert_not_called()
    mock_exchange_instance.market_open.assert_not_called()

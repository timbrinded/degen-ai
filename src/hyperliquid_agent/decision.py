"""Decision engine for generating trading decisions using LLM."""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import frontmatter

from hyperliquid_agent.config import LLMConfig
from hyperliquid_agent.monitor import AccountState, Position


@dataclass
class TradeAction:
    """Represents a single trading action."""

    action_type: Literal["buy", "sell", "hold", "close"]
    coin: str
    market_type: Literal["spot", "perp"]
    size: float | None = None
    price: float | None = None  # None for market orders
    reasoning: str = ""


@dataclass
class DecisionResult:
    """Result of a decision engine query."""

    actions: list[TradeAction]
    selected_strategy: str | None = None
    target_allocation: dict[str, float] | None = None  # Optional target allocation
    raw_response: str = ""
    success: bool = True
    error: str | None = None
    # Cost tracking
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


class PromptTemplate:
    """Manages prompt template and strategy loading."""

    def __init__(self, template_path: str, strategies_dir: str = "strategies") -> None:
        """Initialize the prompt template.

        Args:
            template_path: Path to the prompt template file
            strategies_dir: Directory containing strategy markdown files
        """
        template_file = Path(template_path)
        if not template_file.exists():
            raise FileNotFoundError(f"Prompt template not found: {template_path}")

        with open(template_file) as f:
            self.template = f.read()

        self.strategies_dir = strategies_dir
        self.strategies = self._load_strategies()

    def _load_strategies(self) -> list[dict]:
        """Load all active strategy markdown files.

        Returns:
            List of strategy dictionaries with metadata and content
        """
        strategies = []
        strategy_path = Path(self.strategies_dir)

        if not strategy_path.exists():
            return strategies

        for md_file in sorted(strategy_path.glob("*.md")):
            try:
                with open(md_file) as f:
                    post = frontmatter.load(f)
                    # Only include active or draft strategies
                    status = str(post.get("status", "")).lower()
                    if status in ["active", "draft"]:
                        strategies.append({"metadata": post.metadata, "content": post.content})
            except Exception:
                # Skip files that can't be parsed
                continue

        return strategies

    def format(self, account_state: AccountState) -> str:
        """Format account state and strategies into LLM prompt.

        Args:
            account_state: Current account state

        Returns:
            Formatted prompt string
        """
        return self.template.format(
            portfolio_value=account_state.portfolio_value,
            available_balance=account_state.available_balance,
            positions=self._format_positions(account_state.positions),
            timestamp=account_state.timestamp,
            strategies=self._format_strategies(),
        )

    def _format_positions(self, positions: list[Position]) -> str:
        """Format positions for prompt.

        Args:
            positions: List of current positions

        Returns:
            Formatted position string
        """
        if not positions:
            return "No open positions"

        lines: list[str] = []
        for pos in positions:
            lines.append(
                f"- {pos.coin} ({pos.market_type}): "
                f"Size={pos.size:.4f}, "
                f"Entry=${pos.entry_price:.2f}, "
                f"Current=${pos.current_price:.2f}, "
                f"PnL=${pos.unrealized_pnl:.2f}"
            )
        return "\n".join(lines)

    def _format_strategies(self) -> str:
        """Format loaded strategies for prompt.

        Returns:
            Formatted strategies string
        """
        if not self.strategies:
            return "No strategies available"

        formatted: list[str] = []
        for strategy in self.strategies:
            meta = strategy["metadata"]
            formatted.append(
                f"Strategy: {meta.get('title', 'Unknown')} (ID: {meta.get('id', 'unknown')})\n"
                f"Risk: {meta.get('risk_profile', 'N/A')} | "
                f"Markets: {', '.join(meta.get('markets', []))}\n"
                f"{strategy['content']}\n"
            )
        return "\n---\n".join(formatted)


class DecisionEngine:
    """Generates trading decisions using LLM."""

    def __init__(self, llm_config: LLMConfig, prompt_template: PromptTemplate) -> None:
        """Initialize the decision engine.

        Args:
            llm_config: LLM configuration
            prompt_template: Prompt template instance
        """
        self.llm_config = llm_config
        self.prompt_template = prompt_template
        self.client = self._init_llm_client()
        self.logger = logging.getLogger("hyperliquid_agent.decision")
        # Cost tracking
        self.total_cost_usd = 0.0
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_calls = 0

    def _init_llm_client(self):
        """Initialize LLM client based on provider.

        Returns:
            Initialized LLM client

        Raises:
            ValueError: If provider is not supported
        """
        if self.llm_config.provider == "openai":
            from openai import OpenAI

            return OpenAI(api_key=self.llm_config.api_key)
        elif self.llm_config.provider == "anthropic":
            from anthropic import Anthropic

            return Anthropic(api_key=self.llm_config.api_key)
        else:
            raise ValueError(f"Unsupported LLM provider: {self.llm_config.provider}")

    def get_decision(self, account_state: AccountState) -> DecisionResult:
        """Query LLM for trading decision.

        Args:
            account_state: Current account state

        Returns:
            Decision result with actions and/or target allocation
        """
        try:
            prompt = self.prompt_template.format(account_state)
            response, input_tokens, output_tokens, cost_usd = self._query_llm(prompt)
            actions, selected_strategy, target_allocation = self._parse_response(response)

            # Update running totals
            self.total_input_tokens += input_tokens
            self.total_output_tokens += output_tokens
            self.total_cost_usd += cost_usd
            self.total_calls += 1

            return DecisionResult(
                actions=actions,
                selected_strategy=selected_strategy,
                target_allocation=target_allocation,
                raw_response=response,
                success=True,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost_usd,
            )
        except Exception as e:
            return DecisionResult(
                actions=[],
                target_allocation=None,
                raw_response="",
                success=False,
                error=str(e),
            )

    def _calculate_cost(
        self, model: str, provider: str, input_tokens: int, output_tokens: int
    ) -> float:
        """Calculate cost in USD based on token usage.

        Args:
            model: Model name
            provider: Provider name (openai or anthropic)
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens

        Returns:
            Cost in USD
        """
        # Pricing as of 2025 (per million tokens)
        # OpenAI pricing
        openai_pricing = {
            "gpt-4o": {"input": 2.50, "output": 10.00},
            "gpt-4o-mini": {"input": 0.15, "output": 0.60},
            "gpt-4-turbo": {"input": 10.00, "output": 30.00},
            "gpt-5-mini-2025-08-07": {"input": 0.25, "output": 2.00},
            "gpt-4": {"input": 30.00, "output": 60.00},
            "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
            "o1": {"input": 15.00, "output": 60.00},
            "o1-mini": {"input": 3.00, "output": 12.00},
            "o3-mini": {"input": 1.10, "output": 4.40},
        }

        # Anthropic pricing
        anthropic_pricing = {
            "claude-3-5-sonnet-20241022": {"input": 3.00, "output": 15.00},
            "claude-3-5-haiku-20241022": {"input": 0.80, "output": 4.00},
            "claude-3-opus-20240229": {"input": 15.00, "output": 75.00},
            "claude-3-sonnet-20240229": {"input": 3.00, "output": 15.00},
            "claude-3-haiku-20240307": {"input": 0.25, "output": 1.25},
        }

        pricing = openai_pricing if provider == "openai" else anthropic_pricing

        # Find matching model (handle version suffixes)
        model_pricing = None
        for key in pricing:
            if model.startswith(key):
                model_pricing = pricing[key]
                break

        if not model_pricing:
            # Default to a reasonable estimate if model not found
            self.logger.warning(f"Unknown model pricing for {model}, using default estimate")
            model_pricing = {"input": 1.00, "output": 3.00}

        input_cost = (input_tokens / 1_000_000) * model_pricing["input"]
        output_cost = (output_tokens / 1_000_000) * model_pricing["output"]

        return input_cost + output_cost

    def _query_llm(self, prompt: str) -> tuple[str, int, int, float]:
        """Send prompt to LLM and get response with usage tracking.

        Args:
            prompt: Formatted prompt string

        Returns:
            Tuple of (response text, input tokens, output tokens, cost in USD)

        Raises:
            Exception: If LLM query fails
        """
        self.logger.debug(
            f"Making LLM call: provider={self.llm_config.provider}, "
            f"model={self.llm_config.model}, "
            f"max_tokens={self.llm_config.max_tokens}"
        )

        if self.llm_config.provider == "openai":
            from openai import OpenAI

            client: OpenAI = self.client  # type: ignore

            # GPT-5 models use the responses API
            if self.llm_config.model.startswith("gpt-5"):
                self.logger.debug("gpt-5 model selected, using responses api")
                response = client.responses.create(
                    model=self.llm_config.model,
                    input=prompt,
                    max_output_tokens=self.llm_config.max_tokens,
                )
                result = response.output_text or ""
                # GPT-5 API may have different usage tracking
                input_tokens = getattr(response, "input_tokens", 0)
                output_tokens = getattr(response, "output_tokens", 0)
            else:
                # GPT-4 and earlier models use completions API
                self.logger.debug("non gpt-5 model selected, using completions api")
                response = client.chat.completions.create(
                    model=self.llm_config.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=self.llm_config.temperature,
                    max_tokens=self.llm_config.max_tokens,
                )
                result = response.choices[0].message.content or ""
                input_tokens = response.usage.prompt_tokens if response.usage else 0
                output_tokens = response.usage.completion_tokens if response.usage else 0

            self.logger.debug(f"LLM response received: {len(result)} characters")

            # Check for empty response
            if not result or not result.strip():
                raise ValueError(
                    f"LLM returned empty response. Model: {self.llm_config.model}, "
                    f"Provider: {self.llm_config.provider}. This may indicate an API issue "
                    "or the model refusing to respond."
                )

            cost = self._calculate_cost(
                self.llm_config.model, self.llm_config.provider, input_tokens, output_tokens
            )
            return result, input_tokens, output_tokens, cost

        elif self.llm_config.provider == "anthropic":
            from anthropic import Anthropic
            from anthropic.types import TextBlock

            client: Anthropic = self.client  # type: ignore
            response = client.messages.create(
                model=self.llm_config.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.llm_config.temperature,
                max_tokens=self.llm_config.max_tokens,
            )

            # Extract usage information
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens

            # Extract text from the first text block
            result = ""
            for block in response.content:
                if isinstance(block, TextBlock):
                    result = block.text
                    self.logger.debug(f"LLM response received: {len(result)} characters")
                    break

            cost = self._calculate_cost(
                self.llm_config.model, self.llm_config.provider, input_tokens, output_tokens
            )
            return result, input_tokens, output_tokens, cost
        else:
            raise ValueError(f"Unsupported LLM provider: {self.llm_config.provider}")

    def _parse_response(
        self, response: str
    ) -> tuple[list[TradeAction], str | None, dict[str, float] | None]:
        """Parse LLM response into structured actions and/or target allocation.

        Args:
            response: Raw LLM response text

        Returns:
            Tuple of (list of TradeAction objects, selected strategy ID, target allocation dict)

        Raises:
            ValueError: If response cannot be parsed
        """
        # Try to extract JSON from the response
        # LLM might wrap JSON in markdown code blocks or add text around it
        response = response.strip()

        # Remove markdown code blocks if present
        if response.startswith("```"):
            lines = response.split("\n")
            # Remove first line (```json or ```)
            lines = lines[1:]
            # Remove last line if it's ```
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            response = "\n".join(lines)

        # Try to find JSON object in the response
        start_idx = response.find("{")
        end_idx = response.rfind("}") + 1

        if start_idx == -1 or end_idx == 0:
            raise ValueError("No JSON object found in response")

        json_str = response[start_idx:end_idx]

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in response: {e}") from e

        # Check if LLM returned an error state
        if data.get("error"):
            error_reason = data.get("error_reason", "LLM reported error without reason")
            raise ValueError(f"LLM decision error: {error_reason}")

        # Extract selected strategy
        selected_strategy = data.get("selected_strategy")

        # Extract target allocation if present
        target_allocation = None
        if "target_allocation" in data:
            target_alloc_data = data["target_allocation"]
            if isinstance(target_alloc_data, dict):
                # Validate and normalize allocation
                target_allocation = {str(k): float(v) for k, v in target_alloc_data.items()}

        # Parse actions
        actions = []
        actions_data = data.get("actions", [])

        if not isinstance(actions_data, list):
            raise ValueError("'actions' field must be a list")

        for action_data in actions_data:
            if not isinstance(action_data, dict):
                continue

            # Validate required fields
            action_type = action_data.get("action_type")
            if action_type not in ["buy", "sell", "hold", "close"]:
                continue

            coin = action_data.get("coin", "")
            if not coin:
                continue

            market_type = action_data.get("market_type", "perp")
            if market_type not in ["spot", "perp"]:
                market_type = "perp"

            # Extract optional fields
            size = action_data.get("size")
            if size is not None:
                size = float(size)

            price = action_data.get("price")
            if price is not None:
                price = float(price)

            reasoning = action_data.get("reasoning", "")

            actions.append(
                TradeAction(
                    action_type=action_type,
                    coin=coin,
                    market_type=market_type,
                    size=size,
                    price=price,
                    reasoning=reasoning,
                )
            )

        return actions, selected_strategy, target_allocation

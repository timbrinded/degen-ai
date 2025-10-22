"""Decision engine for generating trading decisions using LLM."""

import json
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
            response = self._query_llm(prompt)
            actions, selected_strategy, target_allocation = self._parse_response(response)
            return DecisionResult(
                actions=actions,
                selected_strategy=selected_strategy,
                target_allocation=target_allocation,
                raw_response=response,
                success=True,
            )
        except Exception as e:
            return DecisionResult(
                actions=[],
                target_allocation=None,
                raw_response="",
                success=False,
                error=str(e),
            )

    def _query_llm(self, prompt: str) -> str:
        """Send prompt to LLM and get response.

        Args:
            prompt: Formatted prompt string

        Returns:
            LLM response text

        Raises:
            Exception: If LLM query fails
        """
        if self.llm_config.provider == "openai":
            from openai import OpenAI

            client: OpenAI = self.client  # type: ignore
            response = client.chat.completions.create(
                model=self.llm_config.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.llm_config.temperature,
                max_tokens=self.llm_config.max_tokens,
            )
            return response.choices[0].message.content or ""
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
            # Extract text from the first text block
            for block in response.content:
                if isinstance(block, TextBlock):
                    return block.text
            return ""
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

        # Extract selected strategy
        selected_strategy = data.get("selected_strategy")

        # Extract target allocation if present
        target_allocation = None
        if "target_allocation" in data:
            target_alloc_data = data["target_allocation"]
            if isinstance(target_alloc_data, dict):
                # Validate and normalize allocation
                target_allocation = {
                    str(k): float(v) for k, v in target_alloc_data.items()
                }

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

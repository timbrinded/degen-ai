"""Decision engine for generating trading decisions using LLM."""

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import frontmatter
from pydantic import BaseModel, Field

from hyperliquid_agent.config import LLMConfig
from hyperliquid_agent.monitor import AccountState, Position

if TYPE_CHECKING:
    from hyperliquid_agent.governance.plan_card import StrategyPlanCard


# Pydantic models for structured outputs
class TradeActionSchema(BaseModel):
    """Schema for a single trading action using structured outputs."""

    action_type: Literal["buy", "sell", "hold", "close", "transfer"]
    coin: str
    market_type: Literal["spot", "perp"] = "perp"
    size: float | None = None
    price: float | None = None
    reasoning: str = ""


class DecisionSchema(BaseModel):
    """Schema for LLM trading decision using structured outputs."""

    actions: list[TradeActionSchema] = Field(default_factory=list)
    selected_strategy: str | None = None
    target_allocation: dict[str, float] | None = None
    error: bool = False
    error_reason: str | None = None


class GovernanceDecisionSchema(BaseModel):
    """Schema for governance-aware LLM decision using structured outputs."""

    maintain_plan: bool = True
    reasoning: str = ""
    micro_adjustments: list[TradeActionSchema] | None = None
    proposed_plan: dict | None = None  # Will be parsed separately


@dataclass
class TradeAction:
    """Represents a single trading action."""

    action_type: Literal["buy", "sell", "hold", "close", "transfer"]
    coin: str
    market_type: Literal["spot", "perp"]
    size: float | None = None
    price: float | None = None  # None for market orders
    reasoning: str = ""
    # For transfer actions: "spot" means transfer TO spot, "perp" means transfer TO perp


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


@dataclass
class GovernanceDecisionResult:
    """Result of a governance-aware decision engine query."""

    maintain_plan: bool
    proposed_plan: "StrategyPlanCard | None" = None  # type: ignore
    micro_adjustments: list[TradeAction] | None = None
    reasoning: str = ""
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
        """Load all strategy markdown files from the strategies directory.

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
                    # Include all strategies found in the directory
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
            # Use structured outputs for OpenAI, fallback to manual parsing for Anthropic
            schema = DecisionSchema if self.llm_config.provider == "openai" else None
            response, input_tokens, output_tokens, cost_usd = self._query_llm(prompt, schema=schema)
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

    def _query_llm(
        self, prompt: str, schema: type[BaseModel] | None = None
    ) -> tuple[str, int, int, float]:
        """Send prompt to LLM and get response with usage tracking.

        Args:
            prompt: Formatted prompt string
            schema: Optional Pydantic model for structured outputs (OpenAI only)

        Returns:
            Tuple of (response text, input tokens, output tokens, cost in USD)

        Raises:
            Exception: If LLM query fails
        """
        self.logger.debug(
            f"Making LLM call: provider={self.llm_config.provider}, "
            f"model={self.llm_config.model}, "
            f"max_tokens={self.llm_config.max_tokens}, "
            f"structured_output={schema is not None}"
        )

        if self.llm_config.provider == "openai":
            from openai import OpenAI

            client: OpenAI = self.client  # type: ignore

            # GPT-5 models use the responses API with structured outputs
            if self.llm_config.model.startswith("gpt-5"):
                self.logger.debug(
                    "gpt-5 model selected, using responses API with structured outputs"
                )

                if schema is not None:
                    # Use structured outputs with responses.parse()
                    response = client.responses.parse(
                        model=self.llm_config.model,
                        input=[{"role": "user", "content": prompt}],
                        max_output_tokens=self.llm_config.max_tokens,
                        text_format=schema,
                    )
                    # Convert parsed output back to JSON string for compatibility
                    result = (
                        response.output_parsed.model_dump_json() if response.output_parsed else ""
                    )
                else:
                    # Fallback to unstructured output
                    response = client.responses.create(
                        model=self.llm_config.model,
                        input=[{"role": "user", "content": prompt}],
                        max_output_tokens=self.llm_config.max_tokens,
                        text={"format": {"type": "text"}},
                    )
                    result = response.output_text or ""

                # Extract usage info
                input_tokens = getattr(response, "input_tokens", 0)
                output_tokens = getattr(response, "output_tokens", 0)
            else:
                # GPT-4 and earlier models use chat completions API
                self.logger.debug("non gpt-5 model selected, using chat completions API")

                if schema is not None:
                    # Use structured outputs with chat.completions.parse()
                    response = client.beta.chat.completions.parse(
                        model=self.llm_config.model,
                        messages=[{"role": "user", "content": prompt}],
                        temperature=self.llm_config.temperature,
                        max_tokens=self.llm_config.max_tokens,
                        response_format=schema,
                    )
                    # Convert parsed output back to JSON string for compatibility
                    parsed = response.choices[0].message.parsed
                    result = parsed.model_dump_json() if parsed else ""
                else:
                    # Fallback to unstructured output
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
            if action_type not in ["buy", "sell", "hold", "close", "transfer"]:
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

    def get_decision_with_governance(
        self,
        account_state: AccountState,
        active_plan: "StrategyPlanCard | None",
        current_regime: str,
        can_review: bool,
    ) -> GovernanceDecisionResult:
        """Query LLM for governance-aware trading decision.

        This method is used by the governed trading agent to query the LLM
        with governance context, including the active plan, regime, and
        review permissions.

        Args:
            account_state: Current account state
            active_plan: Currently active Strategy Plan Card (if any)
            current_regime: Current market regime classification
            can_review: Whether plan review is permitted by governor

        Returns:
            GovernanceDecisionResult with maintain_plan flag and optional proposed plan
        """
        try:
            prompt = self._format_governance_prompt(
                account_state, active_plan, current_regime, can_review
            )
            # Use structured outputs for OpenAI, fallback to manual parsing for Anthropic
            schema = GovernanceDecisionSchema if self.llm_config.provider == "openai" else None
            response, input_tokens, output_tokens, cost_usd = self._query_llm(prompt, schema=schema)
            maintain_plan, proposed_plan, micro_adjustments, reasoning = (
                self._parse_governance_response(response)
            )

            # Update running totals
            self.total_input_tokens += input_tokens
            self.total_output_tokens += output_tokens
            self.total_cost_usd += cost_usd
            self.total_calls += 1

            return GovernanceDecisionResult(
                maintain_plan=maintain_plan,
                proposed_plan=proposed_plan,
                micro_adjustments=micro_adjustments,
                reasoning=reasoning,
                raw_response=response,
                success=True,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost_usd,
            )
        except Exception as e:
            self.logger.error(f"Governance decision failed: {e}", exc_info=True)
            return GovernanceDecisionResult(
                maintain_plan=True,  # Default to maintaining plan on error
                raw_response="",
                success=False,
                error=str(e),
            )

    def _format_governance_prompt(
        self,
        account_state: AccountState,
        active_plan: "StrategyPlanCard | None",
        current_regime: str,
        can_review: bool,
    ) -> str:
        """Format governance-aware prompt for LLM.

        Args:
            account_state: Current account state
            active_plan: Currently active Strategy Plan Card (if any)
            current_regime: Current market regime classification
            can_review: Whether plan review is permitted

        Returns:
            Formatted prompt string
        """
        # Load governance prompt template
        governance_template_path = Path("prompts/governance.txt")
        if not governance_template_path.exists():
            raise FileNotFoundError(
                f"Governance prompt template not found: {governance_template_path}"
            )

        with open(governance_template_path) as f:
            template = f.read()

        # Format active plan summary
        active_plan_summary = self._format_active_plan(active_plan)

        # Format review status
        review_status = self._format_review_status(can_review, active_plan)

        # Format strategies with governance metadata
        strategies = self._format_strategies_with_governance()

        return template.format(
            portfolio_value=account_state.portfolio_value,
            available_balance=account_state.available_balance,
            positions=self.prompt_template._format_positions(account_state.positions),
            timestamp=account_state.timestamp,
            regime=current_regime,
            active_plan_summary=active_plan_summary,
            review_status=review_status,
            can_review=can_review,
            strategies=strategies,
        )

    def _format_active_plan(self, active_plan: "StrategyPlanCard | None") -> str:
        """Format active plan for prompt.

        Args:
            active_plan: Currently active Strategy Plan Card

        Returns:
            Formatted plan summary string
        """
        if active_plan is None:
            return "No active plan"

        # Calculate time since activation
        time_active = ""
        if active_plan.activated_at:
            elapsed = datetime.now() - active_plan.activated_at
            hours = elapsed.total_seconds() / 3600
            time_active = f" (active for {hours:.1f} hours)"

        # Format target allocations
        allocations = ", ".join(
            [f"{a.coin}: {a.target_pct:.1f}%" for a in active_plan.target_allocations]
        )

        return f"""
Strategy: {active_plan.strategy_name}{time_active}
Objective: {active_plan.objective}
Key Thesis: {active_plan.key_thesis}
Target Allocations: {allocations}
Expected Edge: {active_plan.expected_edge_bps:.0f} bps
Minimum Dwell: {active_plan.minimum_dwell_minutes} minutes
Compatible Regimes: {", ".join(active_plan.compatible_regimes)}
Avoid Regimes: {", ".join(active_plan.avoid_regimes)}
Status: {active_plan.status}
"""

    def _format_review_status(
        self, can_review: bool, active_plan: "StrategyPlanCard | None"
    ) -> str:
        """Format plan review status for prompt.

        Args:
            can_review: Whether plan review is permitted
            active_plan: Currently active Strategy Plan Card

        Returns:
            Formatted review status string
        """
        if can_review:
            return "✓ Plan review is PERMITTED - you may propose changes if warranted"
        else:
            reason = "No active plan" if active_plan is None else "Dwell time or cooldown not met"
            return f"✗ Plan review is BLOCKED - {reason}. You may only make micro-adjustments within allowed bands."

    def _format_strategies_with_governance(self) -> str:
        """Format loaded strategies with governance metadata for prompt.

        Returns:
            Formatted strategies string with governance fields
        """
        if not self.prompt_template.strategies:
            return "No strategies available"

        formatted: list[str] = []
        for strategy in self.prompt_template.strategies:
            meta = strategy["metadata"]

            # Extract governance metadata
            intended_horizon = meta.get("intended_horizon", "N/A")
            minimum_dwell = meta.get("minimum_dwell_minutes", "N/A")
            compatible_regimes = meta.get("compatible_regimes", [])
            avoid_regimes = meta.get("avoid_regimes", [])
            max_position_pct = meta.get("max_position_pct", "N/A")
            max_leverage = meta.get("max_leverage", "N/A")
            expected_switching_cost = meta.get("expected_switching_cost_bps", "N/A")

            formatted.append(
                f"Strategy: {meta.get('title', 'Unknown')} (ID: {meta.get('id', 'unknown')})\n"
                f"Risk: {meta.get('risk_profile', 'N/A')} | "
                f"Markets: {', '.join(meta.get('markets', []))}\n"
                f"Horizon: {intended_horizon} | "
                f"Min Dwell: {minimum_dwell} min | "
                f"Switching Cost: {expected_switching_cost} bps\n"
                f"Compatible Regimes: {', '.join(compatible_regimes) if compatible_regimes else 'Any'}\n"
                f"Avoid Regimes: {', '.join(avoid_regimes) if avoid_regimes else 'None'}\n"
                f"Max Position: {max_position_pct}% | Max Leverage: {max_leverage}x\n"
                f"{strategy['content']}\n"
            )
        return "\n---\n".join(formatted)

    def _parse_governance_response(
        self, response: str
    ) -> tuple[bool, "StrategyPlanCard | None", list[TradeAction] | None, str]:
        """Parse LLM governance response into structured format.

        Args:
            response: Raw LLM response text

        Returns:
            Tuple of (maintain_plan, proposed_plan, micro_adjustments, reasoning)

        Raises:
            ValueError: If response cannot be parsed
        """
        # Try to extract JSON from the response
        response = response.strip()

        # Remove markdown code blocks if present
        if response.startswith("```"):
            lines = response.split("\n")
            lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            response = "\n".join(lines)

        # Try to find JSON object in the response
        start_idx = response.find("{")
        end_idx = response.rfind("}") + 1

        if start_idx == -1 or end_idx == 0:
            raise ValueError("No JSON object found in governance response")

        json_str = response[start_idx:end_idx]

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in governance response: {e}") from e

        # Check maintain_plan flag
        maintain_plan = data.get("maintain_plan", True)

        # Extract reasoning
        reasoning = data.get("reasoning", "")

        # Parse micro adjustments if present
        micro_adjustments = None
        if "micro_adjustments" in data and isinstance(data["micro_adjustments"], list):
            micro_adjustments = []
            for action_data in data["micro_adjustments"]:
                if not isinstance(action_data, dict):
                    continue

                action_type = action_data.get("action_type")
                if action_type not in ["buy", "sell", "hold", "close", "transfer"]:
                    continue

                coin = action_data.get("coin", "")
                if not coin:
                    continue

                market_type = action_data.get("market_type", "perp")
                if market_type not in ["spot", "perp"]:
                    market_type = "perp"

                size = action_data.get("size")
                if size is not None:
                    size = float(size)

                price = action_data.get("price")
                if price is not None:
                    price = float(price)

                micro_adjustments.append(
                    TradeAction(
                        action_type=action_type,
                        coin=coin,
                        market_type=market_type,
                        size=size,
                        price=price,
                        reasoning=action_data.get("reasoning", ""),
                    )
                )

        # Parse proposed plan if present
        proposed_plan = None
        if not maintain_plan and "proposed_plan" in data:
            proposed_plan = self._parse_proposed_plan(data["proposed_plan"])

        return maintain_plan, proposed_plan, micro_adjustments, reasoning

    def _parse_proposed_plan(self, plan_data: dict) -> "StrategyPlanCard":
        """Parse proposed Strategy Plan Card from LLM response.

        Args:
            plan_data: Dictionary containing plan fields from LLM

        Returns:
            StrategyPlanCard instance

        Raises:
            ValueError: If required fields are missing or invalid
        """
        from hyperliquid_agent.governance.plan_card import (
            ChangeCostModel,
            ExitRules,
            RiskBudget,
            StrategyPlanCard,
            TargetAllocation,
        )

        # Generate plan ID
        plan_id = f"plan_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # Parse target allocations
        target_allocations = []
        for alloc_data in plan_data.get("target_allocations", []):
            target_allocations.append(
                TargetAllocation(
                    coin=alloc_data["coin"],
                    target_pct=float(alloc_data["target_pct"]),
                    market_type=alloc_data.get("market_type", "perp"),
                    leverage=float(alloc_data.get("leverage", 1.0)),
                )
            )

        # Parse risk budget
        risk_budget_data = plan_data.get("risk_budget", {})
        risk_budget = RiskBudget(
            max_position_pct=risk_budget_data.get("max_position_pct", {}),
            max_leverage=float(risk_budget_data.get("max_leverage", 2.0)),
            max_adverse_excursion_pct=float(
                risk_budget_data.get("max_adverse_excursion_pct", 10.0)
            ),
            plan_max_drawdown_pct=float(risk_budget_data.get("plan_max_drawdown_pct", 15.0)),
            per_trade_risk_pct=float(risk_budget_data.get("per_trade_risk_pct", 2.0)),
        )

        # Parse exit rules
        exit_rules_data = plan_data.get("exit_rules", {})
        exit_rules = ExitRules(
            profit_target_pct=exit_rules_data.get("profit_target_pct"),
            stop_loss_pct=exit_rules_data.get("stop_loss_pct"),
            time_based_review_hours=int(exit_rules_data.get("time_based_review_hours", 24)),
            invalidation_triggers=exit_rules_data.get("invalidation_triggers", []),
        )

        # Parse change cost
        change_cost_data = plan_data.get("change_cost", {})
        change_cost = ChangeCostModel(
            estimated_fees_bps=float(change_cost_data.get("estimated_fees_bps", 10.0)),
            estimated_slippage_bps=float(change_cost_data.get("estimated_slippage_bps", 5.0)),
            estimated_funding_change_bps=float(
                change_cost_data.get("estimated_funding_change_bps", 0.0)
            ),
            opportunity_cost_bps=float(change_cost_data.get("opportunity_cost_bps", 0.0)),
        )

        # Parse allowed leverage range
        leverage_range_data = plan_data.get("allowed_leverage_range", [1.0, 2.0])
        allowed_leverage_range = (float(leverage_range_data[0]), float(leverage_range_data[1]))

        # Create Strategy Plan Card
        return StrategyPlanCard(
            plan_id=plan_id,
            strategy_name=plan_data.get("strategy_name", "unknown"),
            strategy_version=plan_data.get("strategy_version", "1.0"),
            created_at=datetime.now(),
            objective=plan_data.get("objective", ""),
            target_holding_period_hours=int(plan_data.get("target_holding_period_hours", 24)),
            time_horizon=plan_data.get("time_horizon", "hours"),
            key_thesis=plan_data.get("key_thesis", ""),
            target_allocations=target_allocations,
            allowed_leverage_range=allowed_leverage_range,
            risk_budget=risk_budget,
            exit_rules=exit_rules,
            change_cost=change_cost,
            expected_edge_bps=float(plan_data.get("expected_edge_bps", 50.0)),
            kpis_to_track=plan_data.get("kpis_to_track", []),
            minimum_dwell_minutes=int(plan_data.get("minimum_dwell_minutes", 60)),
            compatible_regimes=plan_data.get("compatible_regimes", []),
            avoid_regimes=plan_data.get("avoid_regimes", []),
        )

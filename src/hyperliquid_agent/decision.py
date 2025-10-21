"""Decision engine for LLM-based trading decisions."""

from dataclasses import dataclass
from typing import Literal


@dataclass
class TradeAction:
    """Represents a single trading action."""

    action_type: Literal["buy", "sell", "hold", "close"]
    coin: str
    market_type: Literal["spot", "perp"]
    size: float | None = None
    price: float | None = None
    reasoning: str = ""


@dataclass
class DecisionResult:
    """Result of a decision engine query."""

    actions: list[TradeAction]
    raw_response: str
    success: bool
    error: str | None = None


class PromptTemplate:
    """Manages prompt templates for LLM queries."""

    def __init__(self, template_path: str) -> None:
        """Load prompt template from file.

        Args:
            template_path: Path to the template file
        """
        # TODO: Load template
        raise NotImplementedError("PromptTemplate not yet implemented")

    def format(self, account_state) -> str:
        """Format account state into LLM prompt.

        Args:
            account_state: AccountState instance

        Returns:
            Formatted prompt string
        """
        # TODO: Implement formatting
        raise NotImplementedError("Template formatting not yet implemented")


class DecisionEngine:
    """Generates trading decisions using LLM."""

    def __init__(self, llm_config, prompt_template: PromptTemplate) -> None:
        """Initialize the decision engine.

        Args:
            llm_config: LLMConfig instance
            prompt_template: PromptTemplate instance
        """
        # TODO: Initialize LLM client
        raise NotImplementedError("DecisionEngine not yet implemented")

    def get_decision(self, account_state) -> DecisionResult:
        """Query LLM for trading decision.

        Args:
            account_state: AccountState instance

        Returns:
            Decision result with actions
        """
        # TODO: Implement decision logic
        raise NotImplementedError("Decision logic not yet implemented")

"""Centralized LLM client utility for application-wide use.

This module provides a standardized interface for making LLM calls throughout
the application, ensuring consistent error handling, cost tracking, and provider
abstraction.
"""

import json
import logging
from dataclasses import dataclass
from typing import TypeVar

from pydantic import BaseModel

from hyperliquid_agent.config import LLMConfig

T = TypeVar("T", bound=BaseModel)


@dataclass
class LLMResponse:
    """Standardized LLM response with usage tracking."""

    content: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    model: str
    provider: str


class LLMClient:
    """Centralized LLM client with provider abstraction and cost tracking.

    This class provides a unified interface for making LLM calls regardless of
    the underlying provider (OpenAI, Anthropic). It handles:
    - Provider-specific API differences
    - Token usage tracking
    - Cost calculation
    - Error handling and logging
    - Response parsing

    Usage:
        config = LLMConfig(provider="openai", model="gpt-4o", api_key="...")
        client = LLMClient(config)
        response = client.query("What is the capital of France?")
        print(response.content)  # "Paris"
        print(response.cost_usd)  # 0.00123
    """

    def __init__(self, config: LLMConfig, logger: logging.Logger | None = None):
        """Initialize LLM client with configuration.

        Args:
            config: LLM configuration (provider, model, API key, etc.)
            logger: Optional logger for tracking calls and errors
        """
        self.config = config
        self.logger = logger or logging.getLogger(__name__)
        self._client = self._init_provider_client()

        # Cost tracking
        self.total_cost_usd = 0.0
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_calls = 0

    def _init_provider_client(self):
        """Initialize provider-specific client.

        Returns:
            Initialized provider client (OpenAI or Anthropic)

        Raises:
            ValueError: If provider is not supported
        """
        if self.config.provider == "openai":
            from openai import OpenAI

            return OpenAI(api_key=self.config.api_key)
        elif self.config.provider == "anthropic":
            from anthropic import Anthropic

            return Anthropic(api_key=self.config.api_key)
        else:
            raise ValueError(f"Unsupported LLM provider: {self.config.provider}")

    def query(
        self,
        prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
        schema: type[BaseModel] | None = None,
    ) -> LLMResponse:
        """Query LLM with prompt and return standardized response.

        Args:
            prompt: Text prompt to send to LLM
            temperature: Override config temperature (0.0-1.0)
            max_tokens: Override config max_tokens
            schema: Optional Pydantic model for structured outputs (OpenAI only)

        Returns:
            LLMResponse with content, token usage, and cost

        Raises:
            Exception: If LLM query fails
        """
        temp = temperature if temperature is not None else self.config.temperature
        max_tok = max_tokens if max_tokens is not None else self.config.max_tokens

        self.logger.debug(
            f"LLM query: provider={self.config.provider}, "
            f"model={self.config.model}, temperature={temp}, "
            f"structured_output={schema is not None}"
        )

        try:
            if self.config.provider == "openai":
                response = self._query_openai(prompt, temp, max_tok, schema=schema)
            elif self.config.provider == "anthropic":
                if schema is not None:
                    self.logger.warning(
                        "Structured outputs not supported for Anthropic, falling back to manual parsing"
                    )
                response = self._query_anthropic(prompt, temp, max_tok)
            else:
                raise ValueError(f"Unsupported provider: {self.config.provider}")

            # Update running totals
            self.total_input_tokens += response.input_tokens
            self.total_output_tokens += response.output_tokens
            self.total_cost_usd += response.cost_usd
            self.total_calls += 1

            self.logger.debug(
                f"LLM response: {len(response.content)} chars, cost=${response.cost_usd:.6f}"
            )

            return response

        except Exception as e:
            self.logger.error(
                f"LLM query failed: {e}\n"
                f"  Provider: {self.config.provider}\n"
                f"  Model: {self.config.model}\n"
                f"  Temperature: {temp}\n"
                f"  Max tokens: {max_tok}\n"
                f"  Schema: {schema.__name__ if schema else 'None'}\n"
                f"  Prompt length: {len(prompt)} chars",
                exc_info=True,
            )
            raise

    def _query_openai(
        self,
        prompt: str,
        temperature: float,
        max_tokens: int,
        schema: type[BaseModel] | None = None,
    ) -> LLMResponse:
        """Query OpenAI API with optional structured outputs.

        Args:
            prompt: Text prompt
            temperature: Temperature setting
            max_tokens: Maximum tokens in response
            schema: Optional Pydantic model for structured outputs

        Returns:
            LLMResponse with standardized fields
        """
        from openai import OpenAI

        client = self._client
        assert isinstance(client, OpenAI)

        # GPT-5 models use responses API
        if self.config.model.startswith("gpt-5"):
            if schema is not None:
                # Log the prompt for debugging
                self.logger.debug(
                    f"GPT-5 structured output request:\n"
                    f"  Model: {self.config.model}\n"
                    f"  Max tokens: {max_tokens}\n"
                    f"  Schema: {schema.__name__}\n"
                    f"  Prompt length: {len(prompt)} chars\n"
                    f"  Prompt preview: {prompt[:300]}..."
                )

                # Use structured outputs with responses.parse()
                response = client.responses.parse(
                    model=self.config.model,
                    input=[{"role": "user", "content": prompt}],
                    max_output_tokens=max_tokens,
                    text_format=schema,
                )

                # Log raw response details before parsing
                self.logger.debug(
                    f"GPT-5 raw response received:\n"
                    f"  Output parsed: {response.output_parsed is not None}\n"
                    f"  Input tokens: {getattr(response, 'input_tokens', 'N/A')}\n"
                    f"  Output tokens: {getattr(response, 'output_tokens', 'N/A')}"
                )

                # Convert parsed output to JSON string
                content = response.output_parsed.model_dump_json() if response.output_parsed else ""

                if not content:
                    self.logger.error("GPT-5 returned empty parsed output!")
                else:
                    self.logger.debug(
                        f"GPT-5 parsed response ({len(content)} chars): {content[:300]}..."
                    )
            else:
                # Fallback to unstructured text output
                response = client.responses.create(
                    model=self.config.model,
                    input=[{"role": "user", "content": prompt}],
                    max_output_tokens=max_tokens,
                    text={"format": {"type": "text"}},
                )
                content = response.output_text or ""

            input_tokens = getattr(response, "input_tokens", 0)
            output_tokens = getattr(response, "output_tokens", 0)
        else:
            # GPT-4 and earlier use chat completions API
            if schema is not None:
                # Use structured outputs with chat.completions.parse()
                response = client.beta.chat.completions.parse(
                    model=self.config.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=temperature,
                    max_tokens=max_tokens,
                    response_format=schema,
                )
                # Convert parsed output to JSON string
                parsed = response.choices[0].message.parsed
                content = parsed.model_dump_json() if parsed else ""
            else:
                # Fallback to unstructured text output
                response = client.chat.completions.create(
                    model=self.config.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                content = response.choices[0].message.content or ""

            input_tokens = response.usage.prompt_tokens if response.usage else 0
            output_tokens = response.usage.completion_tokens if response.usage else 0

        # Check for empty response
        if not content or not content.strip():
            raise ValueError(f"OpenAI returned empty response. Model: {self.config.model}")

        cost = self._calculate_cost(input_tokens, output_tokens)

        return LLMResponse(
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            model=self.config.model,
            provider="openai",
        )

    def _query_anthropic(self, prompt: str, temperature: float, max_tokens: int) -> LLMResponse:
        """Query Anthropic API.

        Args:
            prompt: Text prompt
            temperature: Temperature setting
            max_tokens: Maximum tokens in response

        Returns:
            LLMResponse with standardized fields
        """
        from anthropic import Anthropic
        from anthropic.types import TextBlock

        client = self._client
        assert isinstance(client, Anthropic)

        response = client.messages.create(
            model=self.config.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
        )

        # Extract text from response
        content = ""
        for block in response.content:
            if isinstance(block, TextBlock):
                content = block.text
                break

        if not content or not content.strip():
            raise ValueError(f"Anthropic returned empty response. Model: {self.config.model}")

        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        cost = self._calculate_cost(input_tokens, output_tokens)

        return LLMResponse(
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            model=self.config.model,
            provider="anthropic",
        )

    def _calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Calculate cost in USD based on token usage.

        Args:
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens

        Returns:
            Cost in USD
        """
        # Pricing as of January 2025 (per million tokens)
        openai_pricing = {
            "gpt-4o": {"input": 2.50, "output": 10.00},
            "gpt-4o-mini": {"input": 0.15, "output": 0.60},
            "gpt-4-turbo": {"input": 10.00, "output": 30.00},
            "gpt-5-mini-2025-08-07": {"input": 0.25, "output": 2.00},
            "gpt-5-2025-08-07": {"input": 2.50, "output": 10.00},
            "gpt-4": {"input": 30.00, "output": 60.00},
            "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
            "o1": {"input": 15.00, "output": 60.00},
            "o1-mini": {"input": 3.00, "output": 12.00},
            "o3-mini": {"input": 1.10, "output": 4.40},
        }

        anthropic_pricing = {
            "claude-3-5-sonnet-20241022": {"input": 3.00, "output": 15.00},
            "claude-3-5-haiku-20241022": {"input": 0.80, "output": 4.00},
            "claude-3-opus-20240229": {"input": 15.00, "output": 75.00},
            "claude-3-sonnet-20240229": {"input": 3.00, "output": 15.00},
            "claude-3-haiku-20240307": {"input": 0.25, "output": 1.25},
        }

        pricing = openai_pricing if self.config.provider == "openai" else anthropic_pricing

        # Find matching model (handle version suffixes)
        model_pricing = None
        for key in pricing:
            if self.config.model.startswith(key):
                model_pricing = pricing[key]
                break

        if not model_pricing:
            # Default estimate if model not found
            self.logger.warning(f"Unknown model pricing for {self.config.model}, using default")
            model_pricing = {"input": 1.00, "output": 3.00}

        input_cost = (input_tokens / 1_000_000) * model_pricing["input"]
        output_cost = (output_tokens / 1_000_000) * model_pricing["output"]

        return input_cost + output_cost

    def parse_json_response(self, response: LLMResponse) -> dict:
        """Parse JSON from LLM response content.

        Handles common LLM response formats:
        - Pure JSON
        - JSON wrapped in markdown code blocks
        - JSON with surrounding text

        Args:
            response: LLMResponse to parse

        Returns:
            Parsed JSON dictionary

        Raises:
            ValueError: If JSON cannot be parsed
        """
        content = response.content.strip()

        # Remove markdown code blocks if present
        if content.startswith("```"):
            lines = content.split("\n")
            lines = lines[1:]  # Remove ```json or ```
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            content = "\n".join(lines)

        # Find JSON object
        start_idx = content.find("{")
        end_idx = content.rfind("}") + 1

        if start_idx == -1 or end_idx == 0:
            raise ValueError("No JSON object found in LLM response")

        json_str = content[start_idx:end_idx]

        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in LLM response: {e}") from e

    def get_cost_summary(self) -> dict:
        """Get summary of LLM usage and costs.

        Returns:
            Dictionary with total tokens, calls, and cost
        """
        return {
            "total_calls": self.total_calls,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_cost_usd": self.total_cost_usd,
            "avg_cost_per_call": (
                self.total_cost_usd / self.total_calls if self.total_calls > 0 else 0.0
            ),
        }


def create_llm_client(
    config: LLMConfig,
    logger: logging.Logger | None = None,
) -> LLMClient:
    """Factory function to create LLM client from config.

    Args:
        config: LLM configuration
        logger: Optional logger

    Returns:
        Initialized LLMClient
    """
    return LLMClient(config=config, logger=logger)

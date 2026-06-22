"""Provider-neutral token usage and explicit cost estimation."""

from decimal import Decimal
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

TOKENS_PER_MILLION = Decimal(1_000_000)


class GenerationUsage(BaseModel):
    """Cumulative or per-request generation token counts."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def require_consistent_total(self) -> Self:
        if self.total_tokens < self.input_tokens + self.output_tokens:
            raise ValueError("total tokens cannot be less than input plus output tokens")
        return self

    def __add__(self, other: "GenerationUsage") -> "GenerationUsage":
        return GenerationUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
        )

    def __sub__(self, earlier: "GenerationUsage") -> "GenerationUsage":
        values = {
            "input_tokens": self.input_tokens - earlier.input_tokens,
            "output_tokens": self.output_tokens - earlier.output_tokens,
            "total_tokens": self.total_tokens - earlier.total_tokens,
        }
        if any(value < 0 for value in values.values()):
            raise ValueError("generation usage snapshots must be monotonic")
        return GenerationUsage(**values)


class TokenPricing(BaseModel):
    """Explicit USD rates per million input and output tokens."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    input_usd_per_million: Decimal = Field(ge=0)
    output_usd_per_million: Decimal = Field(ge=0)

    def estimate_cost(self, usage: GenerationUsage) -> Decimal:
        """Estimate generation cost from auditable rates and token counts."""
        input_cost = Decimal(usage.input_tokens) * self.input_usd_per_million
        output_cost = Decimal(usage.output_tokens) * self.output_usd_per_million
        return (input_cost + output_cost) / TOKENS_PER_MILLION

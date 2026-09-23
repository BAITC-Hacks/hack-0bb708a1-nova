"""Narrow, validated contracts at the LLM boundary."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

FieldName = Literal["city", "event_date", "event_type", "category", "budget_kzt", "duration_hours", "language"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Update(StrictModel):
    field: FieldName
    value: str | float | None
    evidence: str = Field(max_length=1000)


class Ambiguity(StrictModel):
    field: FieldName
    question: str = Field(min_length=1, max_length=300)


class TurnDecision(StrictModel):
    intent: Literal["request", "confirm", "question", "greeting", "reset", "off_topic", "nonsense", "abusive", "injection", "unsafe"]
    updates: list[Update] = Field(max_length=7)
    ambiguities: list[Ambiguity] = Field(max_length=7)
    reply: str = Field(max_length=600)


class WrittenCard(StrictModel):
    id: str
    explanation: str = Field(min_length=1, max_length=1000)
    description_quote: str = Field(min_length=1, max_length=300)


class WrittenCards(StrictModel):
    cards: list[WrittenCard] = Field(max_length=3)


class CardVerdict(StrictModel):
    id: str
    supported: bool


class VerifiedCards(StrictModel):
    cards: list[CardVerdict] = Field(max_length=3)

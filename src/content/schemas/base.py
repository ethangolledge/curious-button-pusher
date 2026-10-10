"""The base of every record: immutable, and strict about unknown fields."""

from pydantic import BaseModel, ConfigDict


class ImmutableModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

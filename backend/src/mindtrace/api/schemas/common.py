"""Shared response DTOs: pagination. See ``problem.py`` for the error envelope."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Page[Item](BaseModel):
    """``docs/api/08`` s1: opaque ``cursor`` + ``limit`` pagination envelope."""

    model_config = ConfigDict(extra="forbid")

    items: list[Item]
    next_cursor: str | None = None

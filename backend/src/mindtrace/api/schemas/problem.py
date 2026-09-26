"""RFC 9457 ``application/problem+json`` response DTO (``docs/api/08`` s1)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ProblemDetail(BaseModel):
    """One problem+json error body.

    ``errors`` is populated only for ``422`` request-validation failures;
    every other status omits it. Never carries a stack trace, decrypted
    prose, a SQL fragment, or any secret/key material (M6-API planning s10).
    """

    model_config = ConfigDict(extra="forbid")

    type: str = "about:blank"
    title: str
    status: int
    detail: str
    instance: str
    errors: list[dict[str, object]] | None = None

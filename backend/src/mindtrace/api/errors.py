"""Domain-error -> HTTP status mapping (``docs/api/08`` s1/s12).

The one place that translates a typed service/security error into a
``problem+json`` response. Never leaks a stack trace, a SQL fragment, a
password hash, a JWT/master secret, or ciphertext (M6-API planning s10) -
every branch below constructs its own short, generic ``detail`` string
rather than passing ``str(exc)`` through, except where the exception's own
message is already known to be safe (a domain-authored, no-secret message).
"""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from mindtrace.security.auth import InvalidCredentialsError, TokenError
from mindtrace.services.errors import (
    EmailAlreadyRegisteredError,
    IdempotencyKeyConflictError,
    InvalidChosenOptionError,
    InvalidStatusTransitionError,
    ResourceNotFoundError,
    SimulationInProgressError,
    SituationFrozenError,
)

_PROBLEM_MEDIA_TYPE = "application/problem+json"


def _problem(request: Request, *, status_code: int, title: str, detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        media_type=_PROBLEM_MEDIA_TYPE,
        content={
            "type": "about:blank",
            "title": title,
            "status": status_code,
            "detail": detail,
            "instance": str(request.url.path),
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register every typed-error -> problem+json handler on ``app``."""

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            media_type=_PROBLEM_MEDIA_TYPE,
            content={
                "type": "about:blank",
                "title": "Validation Error",
                "status": status.HTTP_422_UNPROCESSABLE_CONTENT,
                "detail": "The request did not satisfy the documented schema.",
                "instance": str(request.url.path),
                "errors": [
                    {"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]}
                    for e in exc.errors()
                ],
            },
        )

    @app.exception_handler(ResourceNotFoundError)
    async def _not_found(request: Request, _exc: ResourceNotFoundError) -> JSONResponse:
        # Deliberately generic detail - never confirms *what* was searched
        # for or *why* it was not found (ownership vs. non-existence must be
        # indistinguishable, docs/api/08 s1).
        return _problem(
            request,
            status_code=status.HTTP_404_NOT_FOUND,
            title="Not Found",
            detail="The requested resource does not exist.",
        )

    @app.exception_handler(EmailAlreadyRegisteredError)
    async def _email_taken(request: Request, _exc: EmailAlreadyRegisteredError) -> JSONResponse:
        return _problem(
            request,
            status_code=status.HTTP_409_CONFLICT,
            title="Conflict",
            detail="This email is already registered.",
        )

    @app.exception_handler(IdempotencyKeyConflictError)
    async def _idempotency_conflict(
        request: Request, _exc: IdempotencyKeyConflictError
    ) -> JSONResponse:
        return _problem(
            request,
            status_code=status.HTTP_409_CONFLICT,
            title="Idempotency Key Conflict",
            detail="This Idempotency-Key was already used with a different request body.",
        )

    @app.exception_handler(SituationFrozenError)
    async def _situation_frozen(request: Request, _exc: SituationFrozenError) -> JSONResponse:
        return _problem(
            request,
            status_code=status.HTTP_409_CONFLICT,
            title="Conflict",
            detail="This decision's situation is frozen and can no longer be changed.",
        )

    @app.exception_handler(InvalidStatusTransitionError)
    async def _invalid_transition(
        request: Request, _exc: InvalidStatusTransitionError
    ) -> JSONResponse:
        return _problem(
            request,
            status_code=status.HTTP_409_CONFLICT,
            title="Conflict",
            detail="The requested status is not reachable from the current state.",
        )

    @app.exception_handler(InvalidChosenOptionError)
    async def _invalid_option(request: Request, _exc: InvalidChosenOptionError) -> JSONResponse:
        return _problem(
            request,
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            title="Validation Error",
            detail="chosen_option does not name one of this decision's options.",
        )

    @app.exception_handler(SimulationInProgressError)
    async def _simulation_in_progress(
        request: Request, _exc: SimulationInProgressError
    ) -> JSONResponse:
        return _problem(
            request,
            status_code=status.HTTP_409_CONFLICT,
            title="Conflict",
            detail="A simulation for this Idempotency-Key is already in progress. Retry shortly.",
        )

    @app.exception_handler(InvalidCredentialsError)
    async def _invalid_credentials(request: Request, _exc: InvalidCredentialsError) -> JSONResponse:
        return _problem(
            request,
            status_code=status.HTTP_401_UNAUTHORIZED,
            title="Unauthorized",
            detail="Invalid credentials.",
        )

    @app.exception_handler(TokenError)
    async def _token_error(request: Request, _exc: TokenError) -> JSONResponse:
        return _problem(
            request,
            status_code=status.HTTP_401_UNAUTHORIZED,
            title="Unauthorized",
            detail="The access token is missing, malformed, or expired.",
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, _exc: Exception) -> JSONResponse:
        # Fail closed: no exception detail, no traceback, ever reaches the
        # client - only a generic 500 (M6-API planning s10).
        return _problem(
            request,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            title="Internal Server Error",
            detail="An unexpected error occurred.",
        )

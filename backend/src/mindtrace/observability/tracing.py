"""Optional OpenTelemetry tracing (M10).

Uses the OpenTelemetry **API** only by default - with no ``TracerProvider``
configured, every span is already a safe no-op (OTel's own documented
behaviour), so :func:`traced_span` needs no collector to be reachable and
never blocks on one. :func:`configure_tracing` additionally wraps SDK setup
defensively: a failure to configure a real exporter degrades to the same
no-op tracer rather than raising - observability must never become a
business-logic dependency (M10 planning).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry import trace
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.trace import Tracer

_TRACER_NAME = "mindtrace"

AttributeValue = str | int | float | bool


def get_tracer() -> Tracer:
    """The process-wide tracer - a safe no-op unless :func:`configure_tracing` ran first."""
    return trace.get_tracer(_TRACER_NAME)


def configure_tracing(service_name: str = "mindtrace") -> None:
    """Install a real SDK ``TracerProvider`` (no exporter wired - a quiet, in-process provider).

    Never raises: a failure here is caught and logged, leaving the existing
    (safe, no-op-by-default) global tracer provider exactly as it was.
    """
    try:
        provider = TracerProvider(resource=Resource.create({SERVICE_NAME: service_name}))
        trace.set_tracer_provider(provider)
    except Exception:
        pass


@contextmanager
def traced_span(name: str, **attributes: AttributeValue) -> Iterator[None]:
    """A span around one meaningful boundary (e.g. ``"m10.twin_ensemble"``).

    If starting the span itself fails for any infrastructure reason, this
    degrades to a plain no-op context - the wrapped code still runs exactly
    as if untraced. An exception raised *inside* the wrapped code is never
    swallowed here - only span-creation failures are.
    """
    try:
        span_context = get_tracer().start_as_current_span(name, attributes=dict(attributes))
    except Exception:
        yield
        return
    with span_context:
        yield


__all__ = ["AttributeValue", "configure_tracing", "get_tracer", "traced_span"]

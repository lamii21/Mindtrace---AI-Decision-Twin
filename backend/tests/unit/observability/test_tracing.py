"""Tests for the optional OpenTelemetry tracing wrapper (M10).

The core guarantee this module exists for: observability failures must
never become business failures (M10 planning). ``configure_tracing`` never
raises even if SDK setup fails; ``traced_span`` degrades to a plain no-op
if starting the span itself fails, while an exception raised by the
*wrapped* business code is never swallowed.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from mindtrace.observability.tracing import configure_tracing, get_tracer, traced_span


class TestConfigureTracing:
    def test_installs_a_provider_without_raising(self) -> None:
        configure_tracing()  # must not raise

    def test_degrades_silently_if_sdk_setup_fails(self) -> None:
        with patch(
            "mindtrace.observability.tracing.TracerProvider", side_effect=RuntimeError("boom")
        ):
            configure_tracing()  # must not raise even though the SDK call failed


class TestTracedSpan:
    def test_the_wrapped_code_runs_under_a_real_span(self) -> None:
        ran = False
        with traced_span("m10.test_span", decision_id="d1"):
            ran = True
        assert ran

    def test_degrades_to_a_plain_no_op_if_span_creation_itself_fails(self) -> None:
        """A tracer that cannot even start a span (e.g. an exporter-side failure) must
        never stop the wrapped business logic from running."""

        class _BrokenTracer:
            def start_as_current_span(self, *args: Any, **kwargs: Any) -> Any:
                raise RuntimeError("collector unreachable")

        ran = False
        with (
            patch("mindtrace.observability.tracing.get_tracer", return_value=_BrokenTracer()),
            traced_span("m10.test_span"),
        ):
            ran = True
        assert ran

    def test_never_swallows_an_exception_raised_by_the_wrapped_code(self) -> None:
        with (
            pytest.raises(ValueError, match="business logic failure"),
            traced_span("m10.test_span"),
        ):
            raise ValueError("business logic failure")

    def test_get_tracer_returns_a_usable_tracer(self) -> None:
        tracer = get_tracer()
        # Just confirm it exposes the expected span API without raising.
        with tracer.start_as_current_span("m10.test_span"):
            pass

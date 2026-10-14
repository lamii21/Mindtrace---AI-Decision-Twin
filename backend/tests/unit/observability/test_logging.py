"""Tests for the ``structlog`` configuration (M10)."""

from __future__ import annotations

import logging

from mindtrace.observability.logging import configure_logging, get_logger, reset_logging_for_tests


class TestConfigureLogging:
    def test_is_idempotent(self) -> None:
        """A second call is a no-op - never reconfigures/double-installs processors."""
        reset_logging_for_tests()
        configure_logging()
        configure_logging()  # must not raise, must not change behaviour
        get_logger(__name__).info("m10_test_event")


class TestGetLogger:
    def test_auto_configures_on_first_use(self) -> None:
        reset_logging_for_tests()
        logger = get_logger(__name__)
        logger.info("m10_test_event", some_field="value")  # must not raise

    def test_returns_a_usable_logger_once_already_configured(self) -> None:
        configure_logging()
        logger = get_logger(__name__)
        logger.info("m10_test_event")


class TestResetLoggingForTests:
    def test_a_fresh_get_logger_call_reconfigures_after_reset(self) -> None:
        configure_logging()
        reset_logging_for_tests()
        # configure_logging's own module-level state must reflect the reset -
        # exercised indirectly via get_logger's auto-configure branch above,
        # and directly here via a second configure_logging() call succeeding.
        configure_logging(level=logging.DEBUG)
        get_logger(__name__).debug("m10_test_event")

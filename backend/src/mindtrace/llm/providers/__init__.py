"""Concrete `LLMClient` implementations.

The only place `.importlinter`'s `provider-sdks-isolated` contract permits a
real provider SDK import. M5 ships only `fake.py` - a deterministic,
network-free client for tests and for running the extraction boundary
without a provider API key.
"""

from __future__ import annotations

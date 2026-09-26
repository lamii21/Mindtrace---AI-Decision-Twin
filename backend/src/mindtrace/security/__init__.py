"""Authentication and key-lifecycle boundary (layer 1).

``docs/architecture/01-repository-structure.md`` s3: authentication, per-user
ownership checks, per-user encryption key lifecycle, RLS policy definitions.
Depends only on ``domain``. Never imports ``mindtrace.db`` (mutually isolated
per ADR-009): ``keyring.py``'s ``KeyProvider`` implementations are purely
cryptographic and take already-fetched bytes, never a database session.
"""

from __future__ import annotations

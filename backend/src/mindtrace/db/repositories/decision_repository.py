"""Persistence for AG-5's ``Decision`` (pre-``simulate`` fields only).

``options`` is encrypted as one canonical-JSON blob, not per-key - the same
"opaque JSONB, read whole" treatment ADR-004 already applies to
``trait_snapshot``/``results``, extended to ciphertext (M6-Persistence
planning s3/s11).
"""

from __future__ import annotations

import json

from mindtrace.db.crypto import KeyProvider, decrypt_field, encrypt_field
from mindtrace.db.dek_resolution import current_key_version, resolve_dek
from mindtrace.db.models.decision import DecisionModel
from mindtrace.db.session import user_scoped_session
from mindtrace.db.types import unpack_envelope
from mindtrace.domain.decision_record import Decision, DecisionOption
from mindtrace.domain.enums import DecisionCategory, DecisionStatus
from mindtrace.domain.ids import DecisionId, UserId

_TABLE = "decision"


def create_decision(*, decision: Decision, key_provider: KeyProvider) -> None:
    """Insert one new decision, encrypting its prose/JSON fields."""
    with user_scoped_session(decision.user_id) as session:
        key_version = current_key_version(session, user_id=decision.user_id)
        dek = resolve_dek(
            session, user_id=decision.user_id, key_version=key_version, key_provider=key_provider
        )

        def encrypt(column: str, plaintext: str) -> bytes:
            return encrypt_field(
                plaintext,
                dek=dek,
                table=_TABLE,
                column=column,
                user_id=decision.user_id,
                row_id=decision.id,
                key_version=key_version,
            )

        options_json = json.dumps(
            [option.model_dump(mode="json") for option in decision.options],
            sort_keys=True,
            separators=(",", ":"),
        )
        reasoning_envelope = (
            encrypt("reasoning", decision.reasoning) if decision.reasoning else None
        )

        session.add(
            DecisionModel(
                id=decision.id,
                user_id=decision.user_id,
                title=encrypt("title", decision.title),
                category=decision.category.value,
                context=encrypt("context", decision.context),
                options=encrypt("options", options_json),
                chosen_option=decision.chosen_option,
                reasoning=reasoning_envelope,
                decided_at=decision.decided_at,
                status=decision.status.value,
                created_at=decision.created_at,
            )
        )


def get_decision(
    user_id: UserId, decision_id: DecisionId, *, key_provider: KeyProvider
) -> Decision | None:
    """Return one decision, decrypted, or ``None`` if it does not exist / is not visible (RLS)."""
    with user_scoped_session(user_id) as session:
        row = session.get(DecisionModel, decision_id)
        if row is None:
            return None

        def decrypt(column: str, envelope: bytes) -> str:
            _fmt, key_version, _nonce, _ct = unpack_envelope(envelope)
            dek = resolve_dek(
                session, user_id=user_id, key_version=key_version, key_provider=key_provider
            )
            return decrypt_field(
                envelope, dek=dek, table=_TABLE, column=column, user_id=user_id, row_id=row.id
            )

        options = tuple(
            DecisionOption.model_validate(item)
            for item in json.loads(decrypt("options", row.options))
        )
        reasoning = decrypt("reasoning", row.reasoning) if row.reasoning is not None else None

        return Decision(
            id=DecisionId(row.id),
            user_id=user_id,
            title=decrypt("title", row.title),
            category=DecisionCategory(row.category),
            context=decrypt("context", row.context),
            options=options,
            chosen_option=row.chosen_option,
            reasoning=reasoning,
            decided_at=row.decided_at,
            status=DecisionStatus(row.status),
            created_at=row.created_at,
        )

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from automotive_quality.infrastructure.database import models

IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$")


class AIOperationState(StrEnum):
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    AMBIGUOUS = "AMBIGUOUS"


class AIOperationConflict(RuntimeError):
    def __init__(self, code: str, operation_id: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.operation_id = operation_id


@dataclass(frozen=True)
class OperationClaim:
    operation_id: str
    owner_token: str | None
    state: AIOperationState
    response_payload: dict[str, Any] | None = None
    response_status: int | None = None

    @property
    def is_owner(self) -> bool:
        return self.owner_token is not None


def canonical_request_hash(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest()


class AIOperationStore:
    """Durable claims use independent short transactions on the business engine."""

    def __init__(self, session: Session) -> None:
        bind = session.get_bind()
        self.bind = getattr(bind, "engine", bind)

    def claim(
        self,
        *,
        principal_id: str,
        operation_type: str,
        target_resource: str,
        idempotency_key: str,
        request_hash: str,
    ) -> OperationClaim:
        if not IDEMPOTENCY_KEY_PATTERN.fullmatch(idempotency_key):
            raise ValueError(
                "Idempotency-Key must be 8-128 characters using letters, digits, '.', '_', ':', or '-'"
            )
        operation_id = f"AIOP-{uuid4().hex[:24].upper()}"
        owner_token = uuid4().hex
        try:
            with Session(self.bind) as claim_session:
                claim_session.add(models.AIOperation(
                    operation_id=operation_id,
                    principal_id=principal_id,
                    operation_type=operation_type,
                    target_resource=target_resource,
                    idempotency_key=idempotency_key,
                    request_hash=request_hash,
                    state=AIOperationState.RUNNING.value,
                    owner_token=owner_token,
                ))
                claim_session.commit()
            return OperationClaim(operation_id, owner_token, AIOperationState.RUNNING)
        except IntegrityError:
            pass

        with Session(self.bind) as lookup:
            operation = lookup.scalar(select(models.AIOperation).where(
                models.AIOperation.principal_id == principal_id,
                models.AIOperation.operation_type == operation_type,
                models.AIOperation.target_resource == target_resource,
                models.AIOperation.idempotency_key == idempotency_key,
            ))
            if operation is None:
                raise RuntimeError("AI operation claim could not be resolved after uniqueness conflict")
            if operation.request_hash != request_hash:
                raise AIOperationConflict(
                    "IDEMPOTENCY_KEY_CONFLICT",
                    operation.operation_id,
                    "Idempotency key was already used with different request content",
                )
            return OperationClaim(
                operation.operation_id,
                None,
                AIOperationState(operation.state),
                operation.response_payload,
                operation.response_status,
            )

    def succeed(
        self,
        claim: OperationClaim,
        response_payload: dict[str, Any],
        *,
        ai_run_id: str | None,
        response_status: int = 200,
    ) -> None:
        self._terminal_update(
            claim,
            AIOperationState.SUCCEEDED,
            response_payload=response_payload,
            response_status=response_status,
            ai_run_id=ai_run_id,
        )

    def fail(
        self,
        claim: OperationClaim,
        category: str,
        *,
        ambiguous: bool,
        ai_run_id: str | None = None,
    ) -> None:
        self._terminal_update(
            claim,
            AIOperationState.AMBIGUOUS if ambiguous else AIOperationState.FAILED,
            error_category=category,
            ai_run_id=ai_run_id,
        )

    def _terminal_update(self, claim: OperationClaim, state: AIOperationState, **values: object) -> None:
        if claim.owner_token is None:
            raise RuntimeError("Only the operation owner may transition state")
        now = datetime.now(timezone.utc)
        with Session(self.bind) as operation_session:
            changed = operation_session.execute(
                update(models.AIOperation)
                .where(
                    models.AIOperation.operation_id == claim.operation_id,
                    models.AIOperation.owner_token == claim.owner_token,
                    models.AIOperation.state == AIOperationState.RUNNING.value,
                )
                .values(state=state.value, updated_at=now, completed_at=now, **values)
            ).rowcount
            if changed != 1:
                operation_session.rollback()
                raise AIOperationConflict(
                    "OPERATION_OWNERSHIP_LOST",
                    claim.operation_id,
                    "AI operation ownership was lost before completion",
                )
            operation_session.commit()

    def status(self, operation_id: str, principal_id: str) -> models.AIOperation | None:
        with Session(self.bind) as operation_session:
            operation = operation_session.scalar(select(models.AIOperation).where(
                models.AIOperation.operation_id == operation_id,
                models.AIOperation.principal_id == principal_id,
            ))
            if operation is not None:
                operation_session.expunge(operation)
            return operation

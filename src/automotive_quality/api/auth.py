from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from automotive_quality.shared.config import Settings, get_settings
from automotive_quality.shared.security_logging import log_security_event


class AuthConfigurationError(RuntimeError):
    """Raised when bearer authentication cannot be configured safely."""


class CredentialConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key_id: str = Field(min_length=1, max_length=128)
    token_sha256: str
    enabled: bool = True
    expires_at: datetime | None = None

    @field_validator("token_sha256")
    @classmethod
    def validate_digest(cls, value: str) -> str:
        normalized = value.lower()
        if len(normalized) != 64:
            raise ValueError("credential digest must be a 64-character SHA-256 hex value")
        try:
            bytes.fromhex(normalized)
        except ValueError as exc:
            raise ValueError("credential digest must be hexadecimal") from exc
        return normalized


class PrincipalConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    principal_id: str = Field(min_length=1, max_length=128)
    category: str = Field(default="service", min_length=1, max_length=64)
    roles: frozenset[str] = Field(default_factory=frozenset)
    credentials: tuple[CredentialConfig, ...] = Field(min_length=1)

    @field_validator("roles")
    @classmethod
    def validate_roles(cls, value: frozenset[str]) -> frozenset[str]:
        if any(not role or len(role) > 64 for role in value):
            raise ValueError("roles must be non-empty strings no longer than 64 characters")
        return value

    @model_validator(mode="after")
    def validate_key_ids(self) -> PrincipalConfig:
        key_ids = [credential.key_id for credential in self.credentials]
        if len(key_ids) != len(set(key_ids)):
            raise ValueError("credential key IDs must be unique within a principal")
        return self


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    principal_id: str
    category: str
    roles: frozenset[str]
    key_id: str
    authentication_method: str = "bearer_sha256"


class BearerAuthenticator:
    def __init__(self, principals: tuple[PrincipalConfig, ...]) -> None:
        self._principals = principals

    @classmethod
    def from_settings(cls, settings: Settings) -> BearerAuthenticator:
        raw_config = settings.api_auth_principals_json
        if not raw_config:
            raise AuthConfigurationError("API bearer authentication is not configured")
        try:
            decoded = json.loads(raw_config)
            principals = tuple(PrincipalConfig.model_validate(item) for item in decoded)
        except (json.JSONDecodeError, TypeError, ValidationError):
            # Do not chain validation details: malformed operator input may
            # accidentally contain a raw credential and reach startup logs.
            raise AuthConfigurationError("API bearer authentication configuration is invalid") from None
        if not principals:
            raise AuthConfigurationError("API bearer authentication has no configured principals")
        principal_ids = [principal.principal_id for principal in principals]
        if len(principal_ids) != len(set(principal_ids)):
            raise AuthConfigurationError("API bearer authentication contains duplicate principal IDs")
        key_scopes = [
            (principal.principal_id, credential.key_id)
            for principal in principals
            for credential in principal.credentials
        ]
        if len(key_scopes) != len(set(key_scopes)):
            raise AuthConfigurationError("API bearer authentication contains duplicate credential identities")
        digests = [
            credential.token_sha256
            for principal in principals
            for credential in principal.credentials
        ]
        if len(digests) != len(set(digests)):
            raise AuthConfigurationError("API bearer authentication contains ambiguous credential digests")
        return cls(principals)

    def authenticate(self, token: str, *, now: datetime | None = None) -> AuthenticatedPrincipal | None:
        submitted_digest = hashlib.sha256(token.encode("utf-8")).digest()
        current_time = now or datetime.now(timezone.utc)
        match: AuthenticatedPrincipal | None = None
        for principal in self._principals:
            for credential in principal.credentials:
                configured_digest = bytes.fromhex(credential.token_sha256)
                digest_matches = hmac.compare_digest(submitted_digest, configured_digest)
                expires_at = credential.expires_at
                if expires_at is not None and expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)
                usable = credential.enabled and (expires_at is None or expires_at > current_time)
                if digest_matches and usable:
                    match = AuthenticatedPrincipal(
                        principal_id=principal.principal_id,
                        category=principal.category,
                        roles=principal.roles,
                        key_id=credential.key_id,
                    )
        return match


bearer_scheme = HTTPBearer(auto_error=False)


@lru_cache(maxsize=1)
def get_bearer_authenticator() -> BearerAuthenticator:
    return BearerAuthenticator.from_settings(get_settings())


def _authentication_failure() -> HTTPException:
    log_security_event("authentication_failure", reason="invalid_or_missing_credential")
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing bearer credential",
        headers={"WWW-Authenticate": "Bearer"},
    )


BearerCredentials = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)]


def authenticated_principal(credentials: BearerCredentials) -> AuthenticatedPrincipal:
    if (
        credentials is None
        or credentials.scheme.lower() != "bearer"
        or len(credentials.credentials) < 32
    ):
        raise _authentication_failure()
    try:
        authenticator = get_bearer_authenticator()
    except AuthConfigurationError as exc:
        log_security_event("authentication_unavailable", reason="invalid_configuration")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API authentication is unavailable",
        ) from exc
    principal = authenticator.authenticate(credentials.credentials)
    if principal is None:
        raise _authentication_failure()
    return principal

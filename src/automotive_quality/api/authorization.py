from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from typing import Annotated

from fastapi import Depends, HTTPException, status

from .auth import AuthenticatedPrincipal, authenticated_principal


class Permission(StrEnum):
    READ = "read"
    OPERATE_AI = "operate_ai"
    OPERATE_REQUIREMENTS = "operate_requirements"
    SUBMIT_TEST_RESULTS = "submit_test_results"
    REVIEW = "review"
    RETRY_EXTERNAL_SYNC = "retry_external_sync"


ROLE_PERMISSIONS: dict[str, frozenset[Permission]] = {
    "reader": frozenset({Permission.READ}),
    "operator": frozenset({
        Permission.READ,
        Permission.OPERATE_AI,
        Permission.OPERATE_REQUIREMENTS,
        Permission.SUBMIT_TEST_RESULTS,
        Permission.RETRY_EXTERNAL_SYNC,
    }),
    "reviewer": frozenset({Permission.READ, Permission.REVIEW}),
    "administrator": frozenset(Permission),
}

Authenticated = Annotated[AuthenticatedPrincipal, Depends(authenticated_principal)]


def require_permission(permission: Permission) -> Callable[[AuthenticatedPrincipal], AuthenticatedPrincipal]:
    def authorize(principal: Authenticated) -> AuthenticatedPrincipal:
        allowed = any(permission in ROLE_PERMISSIONS.get(role, frozenset()) for role in principal.roles)
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Authenticated principal is not authorized for this operation",
            )
        return principal

    authorize.required_permission = permission  # type: ignore[attr-defined]
    return authorize

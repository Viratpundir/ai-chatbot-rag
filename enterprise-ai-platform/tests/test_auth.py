from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.auth import RegisterRequest


@pytest.mark.parametrize("role", ["EMPLOYEE", "STUDENT"])
def test_registration_accepts_employee_and_student_roles(role: str) -> None:
    request = RegisterRequest(
        name="Test User",
        email="user@example.com",
        password="Strong!Password42",
        role=role,
    )

    assert request.role == role


def test_registration_rejects_privileged_roles() -> None:
    with pytest.raises(ValidationError):
        RegisterRequest(
            name="Test User",
            email="user@example.com",
            password="Strong!Password42",
            role="ADMIN",
        )

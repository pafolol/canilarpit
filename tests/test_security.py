import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.core.security import validate_authorized_party


def test_authorized_party_is_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "clerk_authorized_parties", ["https://canilarpit.com"])
    validate_authorized_party({"azp": "https://canilarpit.com"})
    with pytest.raises(HTTPException) as error:
        validate_authorized_party({"azp": "https://attacker.example"})
    assert error.value.status_code == 401

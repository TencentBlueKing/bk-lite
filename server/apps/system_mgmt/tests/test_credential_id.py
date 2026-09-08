import re

import pytest

from apps.system_mgmt.services.credential_service import build_credential_id


@pytest.mark.unit
def test_build_credential_id_uses_type_key_and_uuid4_hex():
    for type_key in ("sql", "ssh"):
        credential_id = build_credential_id(type_key)

        assert re.fullmatch(rf"crd-{type_key}-[0-9a-f]{{32}}", credential_id)


@pytest.mark.unit
def test_build_credential_id_returns_unique_ids():
    assert build_credential_id("sql") != build_credential_id("sql")

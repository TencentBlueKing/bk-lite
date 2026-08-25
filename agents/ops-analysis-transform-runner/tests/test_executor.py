import pytest

from app.capacity import CapacityError, OrgConcurrencyLimiter
from app.executor import TransformRuntimeError, execute_transform
from app.script_guard import ScriptValidationError, validate_script_ast


def test_validate_script_rejects_forbidden_import():
    with pytest.raises(ScriptValidationError) as exc:
        validate_script_ast("import os\ndef transform(rows, params):\n    return rows\n")
    assert exc.value.code == "script_import_not_allowed"


def test_execute_transform_happy_path():
    script = """
def transform(rows, params):
    return [{"v": row["n"] + 1} for row in rows]
"""
    assert execute_transform(script, [{"n": 1}, {"n": 2}], {}) == [{"v": 2}, {"v": 3}]


def test_execute_transform_allows_whitelisted_imports():
    script = """
import math
import json
from datetime import datetime
from collections import Counter

def transform(rows, params):
    return [{"n": math.floor(1.9), "c": Counter(["a"]).most_common(1)[0][0], "j": json.dumps({"ok": True})}]
"""
    out = execute_transform(script, [{"n": 1}], {})
    assert out[0]["n"] == 1
    assert out[0]["c"] == "a"
    assert '"ok"' in out[0]["j"]


def test_execute_transform_rejects_non_list_return():
    script = """
def transform(rows, params):
    return {"ok": True}
"""
    with pytest.raises(TransformRuntimeError) as exc:
        execute_transform(script, [{"n": 1}], {})
    assert exc.value.code == "transform_return_invalid"


def test_org_limiter_rejects_when_full():
    limiter = OrgConcurrencyLimiter(limit=1)
    with limiter.acquire("org-a"):
        with pytest.raises(CapacityError):
            with limiter.acquire("org-a", timeout=0):
                pass

# -*- coding: utf-8 -*-
"""catalog.py 单测"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.collect_fixtures.catalog import Spec, lookup, list_models, validate  # noqa: E402


def _make_spec(**overrides):
    defaults = dict(
        model_id="mysql",
        image="mysql:8.0",
        ports={"3306/tcp": 13306},
        env={"MYSQL_ROOT_PASSWORD": "rootpw"},
        wait_strategy={"type": "tcp", "port": 13306, "timeout": 60},
        init_script=None,
        entry_type="python",
        entry_module="plugins.inputs.mysql.mysql_info",
        entry_class="MysqlInfo",
        entry_method="list_all_resources",
        collector_kwargs={"host": "127.0.0.1", "port": 13306, "user": "root", "password": "rootpw"},
    )
    defaults.update(overrides)
    return Spec(**defaults)


def test_lookup_returns_spec():
    spec = lookup("mysql")
    assert spec.model_id == "mysql"
    assert spec.image == "mysql:8.0"


def test_lookup_unknown_raises_keyerror():
    with pytest.raises(KeyError):
        lookup("not_exists_xyz")


def test_list_models_returns_sorted_ids():
    models = list_models()
    assert isinstance(models, list)
    assert models == sorted(models)
    assert "mysql" in models


def test_validate_all_specs_have_required_fields():
    errors = validate()
    assert errors == [], f"validate 发现配置错误: {errors}"


def test_spec_dataclass_is_immutable():
    spec = _make_spec()
    with pytest.raises(Exception):
        spec.model_id = "other"  # frozen dataclass
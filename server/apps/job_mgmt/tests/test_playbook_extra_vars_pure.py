"""Playbook extra_vars 纯函数契约。"""

import pydantic.root_model  # noqa
import pytest

from apps.job_mgmt.services.playbook_execution import PlaybookExecution

pytestmark = pytest.mark.unit


def test_unbalanced_quotes_fallback_to_split():
    params_def = [{"name": "a"}, {"name": "b"}]

    result = PlaybookExecution._build_extra_vars("v1 'v2", params_def)

    assert result == {"a": "v1", "b": "'v2"}

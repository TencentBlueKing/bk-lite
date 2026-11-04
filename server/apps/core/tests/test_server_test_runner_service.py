"""默认门禁保留应用和内嵌工具测试，并隔离顶层模块命名空间。"""

import xml.etree.ElementTree as ET

import pytest

from apps.core.testing_runner import run_suites

pytestmark = pytest.mark.integration


@pytest.fixture
def isolated_suites(tmp_path, monkeypatch):
    monkeypatch.setenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    monkeypatch.delenv("DJANGO_SETTINGS_MODULE", raising=False)
    monkeypatch.delenv("PYTEST_ADDOPTS", raising=False)
    tools = tmp_path / "apps/opspilot/support-files/skill_packages/ppt-master/scripts"
    (tools / "tests").mkdir(parents=True)
    (tmp_path / "tests").mkdir()
    (tmp_path / "config.py").write_text("ORIGIN = 'server'\n")
    (tools / "config.py").write_text("ORIGIN = 'ppt'\n")
    (tmp_path / "conftest.py").write_text(
        "import config\nimport pytest\n@pytest.fixture(autouse=True)\ndef application_only():\n    assert config.ORIGIN == 'server'\n"
    )
    (tmp_path / "pytest.ini").write_text("[pytest]\naddopts = --ignore=apps/opspilot/support-files/skill_packages/ppt-master/scripts/tests\n")
    (tmp_path / "tests/test_application.py").write_text("import config\ndef test_origin():\n    assert config.ORIGIN == 'server'\n")
    (tools / "tests/test_embedded.py").write_text("import config\ndef test_origin():\n    assert config.ORIGIN == 'ppt'\n")
    return tmp_path, tools


def test_both_suites_use_their_own_config_modules(isolated_suites):
    root, _ = isolated_suites
    assert run_suites(root) == 0
    for suite in ("server", "ppt-skill"):
        report = ET.parse(root / "test-results" / f"{suite}.xml").getroot().find("testsuite")
        assert report.get("tests") == "1"
        assert report.get("skipped") == "0"


@pytest.mark.parametrize("suite", ["application", "embedded"])
def test_failure_in_either_suite_fails_the_gate(isolated_suites, suite):
    root, tools = isolated_suites
    test = root / "tests/test_application.py" if suite == "application" else tools / "tests/test_embedded.py"
    test.write_text("def test_failure():\n    assert False, 'gate must fail'\n")
    assert run_suites(root) != 0

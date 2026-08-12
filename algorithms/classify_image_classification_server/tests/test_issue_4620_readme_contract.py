"""Issue #4620：README 的可复制示例必须遵循真实预测 API 契约。"""

import ast
import json
import re
from pathlib import Path

from classify_image_classification_server.serving.schemas import PredictResponse


MODULE_ROOT = Path(__file__).parents[1]
README_PATH = MODULE_ROOT / "README.md"


def _readme() -> str:
    return README_PATH.read_text(encoding="utf-8")


def test_readme_json_request_uses_nested_predict_config():
    request_section = _readme().split("**请求格式**:", maxsplit=1)[1]
    json_example = re.search(
        r"```json\s*(.*?)\s*```", request_section, flags=re.DOTALL
    )

    assert json_example is not None
    payload = json.loads(json_example.group(1))
    assert set(payload) == {"images", "config"}
    assert payload["config"] == {"top_k": 5}


def test_readme_json_response_matches_public_response_schema():
    json_examples = re.findall(
        r"```json\s*(.*?)\s*```", _readme(), flags=re.DOTALL
    )

    response = json.loads(json_examples[1])
    PredictResponse.model_validate(response)


def test_readme_python_clients_use_nested_predict_config():
    python_examples = re.findall(
        r"```python\s*(.*?)\s*```", _readme(), flags=re.DOTALL
    )

    request_payloads = []
    for example in python_examples:
        tree = ast.parse(example)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr != "post":
                continue
            json_keyword = next(
                keyword for keyword in node.keywords if keyword.arg == "json"
            )
            request_payloads.append(json_keyword.value)

    assert len(request_payloads) == 2
    for payload in request_payloads:
        assert isinstance(payload, ast.Dict)
        top_level_keys = [ast.literal_eval(key) for key in payload.keys]
        assert top_level_keys == ["images", "config"]

        config = payload.values[1]
        assert isinstance(config, ast.Dict)
        assert [ast.literal_eval(key) for key in config.keys] == ["top_k"]


def test_readme_local_links_resolve_to_existing_files():
    local_links = re.findall(r"\[[^]]+\]\((?!https?://)([^)#]+)", _readme())

    for link in local_links:
        assert (MODULE_ROOT / link).exists(), f"README 链接不存在: {link}"

import ast
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace


class _Provider:
    def __init__(self, provider_id, name, team):
        self.id = provider_id
        self.name = name
        self.team = team
        self.saved_with = []

    def save(self, **kwargs):
        self.saved_with.append(kwargs)


class _Manager:
    def __init__(self, providers):
        self.providers = {provider.name: provider for provider in providers}
        self.lock_count = 0

    def select_for_update(self):
        self.lock_count += 1
        return self

    def get(self, *, name, is_build_in):
        assert is_build_in is True
        return self.providers[name]


class _Atomic:
    def __init__(self):
        self.entries = 0
        self.exits = 0

    @contextmanager
    def atomic(self):
        self.entries += 1
        try:
            yield
        finally:
            self.exits += 1


def _load_guest_provider_functions(namespace):
    source_path = Path(__file__).parents[1] / "nats_api.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    functions = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name in {"_grant_provider_team_access", "get_guest_provider"}
    ]
    assert {node.name for node in functions} == {"_grant_provider_team_access", "get_guest_provider"}
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(source_path), "exec"), namespace)


def test_get_guest_provider_uses_one_transaction_and_locks_every_row():
    llm = [_Provider(1, "GPT-4o", [3])]
    rerank = [_Provider(2, "bce-reranker-base_v1", [])]
    embeds = [
        _Provider(3, "bce-embedding-base_v1", []),
        _Provider(4, "FastEmbed(BAAI/bge-small-zh-v1.5)", []),
    ]
    ocrs = [
        _Provider(5, "PaddleOCR", []),
        _Provider(6, "AzureOCR", []),
        _Provider(7, "OlmOCR", []),
    ]
    managers = {
        "LLMModel": _Manager(llm),
        "RerankProvider": _Manager(rerank),
        "EmbedProvider": _Manager(embeds),
        "OCRProvider": _Manager(ocrs),
    }
    transaction = _Atomic()
    namespace = {
        "nats_client": SimpleNamespace(register=lambda function: function),
        "transaction": transaction,
        **{name: SimpleNamespace(objects=manager) for name, manager in managers.items()},
    }
    _load_guest_provider_functions(namespace)

    result = namespace["get_guest_provider"](group_id=7)

    assert result["result"] is True
    assert transaction.entries == transaction.exits == 1
    assert managers["LLMModel"].lock_count == 1
    assert managers["RerankProvider"].lock_count == 1
    assert managers["EmbedProvider"].lock_count == 2
    assert managers["OCRProvider"].lock_count == 3
    for provider in rerank + embeds + ocrs:
        assert provider.team == [7]
        assert provider.saved_with == [{"update_fields": ["team"]}]
    assert llm[0].team == [3, 7]
    assert llm[0].saved_with == [{"update_fields": ["team"]}]

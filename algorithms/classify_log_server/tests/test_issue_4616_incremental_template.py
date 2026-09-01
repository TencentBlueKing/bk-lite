"""Issue #4616：Spell 同簇模板更新应保持语义且不保留全部 token 历史。"""

from collections import Counter, defaultdict
import importlib.util
from pathlib import Path
import random
import sys
import types

import pytest


def _load_spell_model():
    """直接加载被测模块，避免 training 包导入无关特征工程全栈。"""
    root_name = "issue_4616_training"
    training = types.ModuleType(root_name)
    training.__path__ = []
    models = types.ModuleType(f"{root_name}.models")
    models.__path__ = []
    base = types.ModuleType(f"{root_name}.models.base")
    evaluation_contract = types.ModuleType(f"{root_name}.evaluation_contract")
    evaluation_contract.require_unsupervised_evaluation = lambda ground_truth: None

    class BaseLogClusterModel:
        def __init__(self, config=None):
            self.config = config or {}
            self.templates = None
            self.is_trained = False

        def _check_fitted(self):
            if not self.is_trained:
                raise RuntimeError("模型未训练")

    class ModelRegistry:
        @staticmethod
        def register(_name):
            return lambda model_class: model_class

    base.BaseLogClusterModel = BaseLogClusterModel
    base.ModelRegistry = ModelRegistry
    mlflow = types.ModuleType("mlflow")
    mlflow.active_run = lambda: None
    loguru = types.ModuleType("loguru")
    loguru.logger = types.SimpleNamespace(
        debug=lambda *args, **kwargs: None,
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
        error=lambda *args, **kwargs: None,
    )
    temporary_modules = {
        root_name: training,
        f"{root_name}.models": models,
        f"{root_name}.models.base": base,
        f"{root_name}.evaluation_contract": evaluation_contract,
        "mlflow": mlflow,
        "loguru": loguru,
    }
    previous_modules = {name: sys.modules.get(name) for name in temporary_modules}
    sys.modules.update(temporary_modules)

    module_name = f"{root_name}.models.spell_model"
    module_path = (
        Path(__file__).parent.parent
        / "classify_log_server"
        / "training"
        / "models"
        / "spell_model.py"
    )
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    try:
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(module_name, None)
        for name, previous in previous_modules.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous
    return module.SpellModel


SpellModel = _load_spell_model()


def _load_with_legacy_reader(artifact):
    """Run the pre-schema-version load flow against a current artifact."""
    import joblib

    model_data = joblib.load(artifact)
    instance = SpellModel(**model_data.get("config", {}))
    instance.templates = model_data["templates"]
    instance.clusters = model_data.get("clusters", [])
    instance.tau = model_data["tau"]
    instance.use_position_weight = model_data.get("use_position_weight", True)
    instance.position_weight_config = model_data.get("position_weight_config", instance.position_weight_config)
    instance.merge_threshold = model_data.get("merge_threshold", 0.85)
    instance.diversity_threshold = model_data.get("diversity_threshold", 3)
    instance.min_cluster_size = model_data.get("min_cluster_size", 5)
    instance.is_trained = model_data["is_trained"]
    instance.token_index = defaultdict(set)
    for cluster in instance.clusters:
        for token in cluster["template"]:
            if token != "<*>":
                instance.token_index[token].add(cluster["id"])
    return instance, model_data


def _legacy_update_template(model, logs):
    """保留变更前实现，作为语义等价 oracle。"""
    if not logs:
        return []
    if len(logs) == 1:
        return logs[0]

    template = logs[0]
    for log in logs[1:]:
        template = model._compute_lcs(template, log)

    template = []
    for position in range(max(map(len, logs))):
        counts = Counter(log[position] for log in logs if position < len(log))
        token, _count = counts.most_common(1)[0]
        template.append("<*>" if len(counts) >= model.diversity_threshold else token)
    return template


def test_single_cluster_template_update_has_linear_lcs_calls(monkeypatch):
    model = SpellModel(
        tau=0.3,
        merge_threshold=0,
        use_cache=False,
        enable_explain=False,
    )
    lcs_calls = 0
    compute_lcs = model._compute_lcs

    def counted_compute_lcs(sequence, template):
        nonlocal lcs_calls
        lcs_calls += 1
        return compute_lcs(sequence, template)

    monkeypatch.setattr(model, "_compute_lcs", counted_compute_lcs)
    logs = [f"service request id{index} completed successfully" for index in range(200)]

    model.fit(logs, verbose=False, log_to_mlflow=False)

    assert len(model.clusters) == 1
    assert lcs_calls < len(logs) * 2


@pytest.mark.parametrize(
    "logs",
    [
        [["A", "x", "A"], ["A", "y", "A"], ["A", "z", "A"]],
        [["A", "B"], ["A", "B", "C"], ["A", "D"]],
        [["A", "B"], ["A", "C"], ["A", "C"], ["A", "B"]],
    ],
)
def test_incremental_template_matches_existing_majority_semantics(logs):
    model = SpellModel(diversity_threshold=3)
    cluster = model._new_cluster(cluster_id=0, log_id=0, tokens=logs[0])

    for log_id, tokens in enumerate(logs[1:], start=1):
        model._append_to_cluster(cluster, log_id=log_id, tokens=tokens)

    assert cluster["template"] == _legacy_update_template(model, logs)


def test_incremental_template_matches_legacy_for_threshold_one_and_shorter_log():
    logs = [["A", "B"], ["A"]]
    model = SpellModel(diversity_threshold=1)
    cluster = model._new_cluster(cluster_id=0, log_id=0, tokens=logs[0])

    model._append_to_cluster(cluster, log_id=1, tokens=logs[1])

    assert cluster["template"] == _legacy_update_template(model, logs)


def test_incremental_template_matches_seeded_legacy_oracle():
    rng = random.Random(4616)
    vocabulary = ["A", "B", "C", "A"]

    for _case in range(500):
        threshold = rng.randint(1, 4)
        logs = [
            [rng.choice(vocabulary) for _token in range(rng.randint(1, 7))]
            for _log in range(rng.randint(1, 12))
        ]
        model = SpellModel(diversity_threshold=threshold)
        cluster = model._new_cluster(cluster_id=0, log_id=0, tokens=logs[0])
        assert cluster["template"] == _legacy_update_template(model, logs[:1])

        for log_id, tokens in enumerate(logs[1:], start=1):
            model._append_to_cluster(cluster, log_id=log_id, tokens=tokens)
            assert cluster["template"] == _legacy_update_template(model, logs[: log_id + 1])


def test_fit_keeps_cluster_assignment_and_template_oracle():
    token_logs = [
        ["event", "A", "A", "done"],
        ["event", "A", "B", "done"],
        ["event", "A", "C", "done"],
        ["event", "B", "A", "done"],
    ]
    model = SpellModel(
        tau=0.2,
        merge_threshold=0,
        diversity_threshold=3,
        use_position_weight=False,
        enable_explain=False,
    )

    model.fit(
        [" ".join(tokens) for tokens in token_logs],
        verbose=False,
        log_to_mlflow=False,
    )

    assert len(model.clusters) == 1
    assert model.clusters[0]["log_ids"] == [0, 1, 2, 3]
    assert model.clusters[0]["template"] == _legacy_update_template(model, token_logs)


def test_new_cluster_state_does_not_retain_all_token_sequences():
    model = SpellModel(tau=0.3, merge_threshold=0, enable_explain=False)
    logs = [f"service request id{index} completed successfully" for index in range(50)]

    model.fit(logs, verbose=False, log_to_mlflow=False)

    cluster = model.clusters[0]
    assert [len(log) for log in cluster["logs"]] == [5] * len(logs)
    assert all(isinstance(log, range) for log in cluster["logs"])
    assert cluster["log_length_total"] == sum(len(log.split()) for log in logs)
    assert len(cluster["position_counts"]) == len(logs[0].split())
    assert cluster["position_counts"][2] is None
    assert all(
        state is None or len(state["counts"]) < model.diversity_threshold
        for state in cluster["position_counts"]
    )


def test_legacy_cluster_state_is_migrated_without_changing_template():
    model = SpellModel(diversity_threshold=3)
    legacy_logs = [["A", "x"], ["A", "y"], ["A", "z"]]
    cluster = {
        "id": 0,
        "template": ["A", "<*>"],
        "logs": legacy_logs,
        "log_ids": [0, 1, 2],
    }

    model._ensure_cluster_state(cluster)

    assert cluster["template"] == ["A", "<*>"]
    assert [len(log) for log in cluster["logs"]] == [2, 2, 2]
    assert cluster["position_counts"][1] is None
    assert cluster["log_length_total"] == 6


def test_load_migrates_legacy_model_artifact(tmp_path):
    import joblib

    artifact = tmp_path / "legacy-spell.joblib"
    joblib.dump(
        {
            "config": {},
            "templates": ["A <*>"],
            "clusters": [
                {
                    "id": 0,
                    "template": ["A", "<*>"],
                    "logs": [["A", "x"], ["A", "y"], ["A", "z"]],
                    "log_ids": [0, 1, 2],
                }
            ],
            "tau": 0.5,
            "is_trained": True,
        },
        artifact,
    )

    model = SpellModel.load(artifact)

    assert model.templates == ["A <*>"]
    assert model.clusters[0]["template"] == ["A", "<*>"]
    assert [len(log) for log in model.clusters[0]["logs"]] == [2, 2, 2]
    assert model.clusters[0]["log_length_total"] == 6


def test_current_artifact_round_trip_preserves_legacy_length_slot(tmp_path):
    model = SpellModel(tau=0.3, merge_threshold=0, enable_explain=False)
    logs = [f"service request id{index} completed successfully" for index in range(10)]
    model.fit(logs, verbose=False, log_to_mlflow=False)
    artifact = tmp_path / "current-spell.joblib"

    model.save(artifact)
    loaded = SpellModel.load(artifact)
    summary = loaded.get_cluster_summary(0)

    assert loaded.predict(["service request next completed successfully"]) == [0]
    assert summary["avg_log_length"] == 5
    assert [len(log) for log in loaded.clusters[0]["logs"]] == [5] * len(logs)
    # 回滚到旧读取器时可由长度哨兵精确恢复平均长度，但不保留任何 token。
    assert sum(map(len, loaded.clusters[0]["logs"])) == 50
    assert all(isinstance(log, range) for log in loaded.clusters[0]["logs"])


def test_current_artifact_remains_readable_by_legacy_inference_flow(tmp_path):
    model = SpellModel(tau=0.3, merge_threshold=0, enable_explain=False)
    logs = [f"service request id{index} completed successfully" for index in range(10)]
    model.fit(logs, verbose=False, log_to_mlflow=False)
    artifact = tmp_path / "current-spell.joblib"
    model.save(artifact)

    loaded, model_data = _load_with_legacy_reader(artifact)

    assert model_data["artifact_schema_version"] == 2
    assert loaded.predict(["service request next completed successfully"]) == [0]
    legacy_logs = loaded.clusters[0]["logs"]
    assert sum(map(len, legacy_logs)) / len(legacy_logs) == 5
    assert all(isinstance(log, range) for log in legacy_logs)


def test_merged_cluster_state_matches_original_concatenation_order():
    model = SpellModel(diversity_threshold=4)
    target_logs = [["A", "x"], ["A", "y"]]
    source_logs = [["A", "y"], ["A", "x", "tail"]]
    target = model._new_cluster(cluster_id=0, log_id=0, tokens=target_logs[0])
    source = model._new_cluster(cluster_id=1, log_id=2, tokens=source_logs[0])
    model._append_to_cluster(target, log_id=1, tokens=target_logs[1])
    model._append_to_cluster(source, log_id=3, tokens=source_logs[1])

    model._merge_cluster_state(target, source)

    assert target["template"] == _legacy_update_template(model, target_logs + source_logs)
    assert target["log_ids"] == [0, 1, 2, 3]
    assert target["log_length_total"] == sum(
        len(tokens) for tokens in target_logs + source_logs
    )


def test_merged_cluster_state_matches_legacy_at_threshold_one():
    model = SpellModel(diversity_threshold=1)
    target_logs = [["A", "B", "tail"]]
    source_logs = [["A"]]
    target = model._new_cluster(cluster_id=0, log_id=0, tokens=target_logs[0])
    source = model._new_cluster(cluster_id=1, log_id=1, tokens=source_logs[0])

    model._merge_cluster_state(target, source)

    assert target["template"] == _legacy_update_template(model, target_logs + source_logs)

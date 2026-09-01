from unittest.mock import patch

import pytest
from classify_log_server.training.config.schema import SUPPORTED_METRICS
from classify_log_server.training.data_loader import LogDataLoader
from classify_log_server.training.evaluation_contract import (
    EVALUATION_CONTRACT_VERSION,
    SupervisedEvaluationUnsupported,
)
from classify_log_server.training.models.spell_model import SpellModel
from classify_log_server.training.trainer import UniversalTrainer

EXPECTED_UNSUPERVISED_METRICS = {
    "num_templates",
    "coverage_rate",
    "template_diversity",
    "template_quality_score",
}


def _fitted_model():
    model = SpellModel(tau=0.5)
    model.fit(
        [
            "database connection failed host alpha",
            "database connection failed host beta",
            "user login succeeded account alice",
            "user login succeeded account bob",
        ],
        verbose=False,
        log_to_mlflow=False,
    )
    return model


def test_supported_hyperopt_metrics_are_explicitly_unsupervised():
    assert set(SUPPORTED_METRICS) == EXPECTED_UNSUPERVISED_METRICS
    assert not {
        "grouping_accuracy",
        "parsing_accuracy",
        "precision",
        "recall",
        "f1_score",
    } & set(SUPPORTED_METRICS)


def test_explicit_ground_truth_fails_fast_instead_of_returning_id_sensitive_score():
    model = _fitted_model()

    with pytest.raises(
        SupervisedEvaluationUnsupported,
        match="当前正式训练契约仅支持无监督评估",
    ) as exc_info:
        model.evaluate(
            [
                "database connection failed host gamma",
                "user login succeeded account carol",
            ],
            ground_truth=[7, 3],
            verbose=False,
        )
    assert exc_info.value.code == "supervised_evaluation_unsupported"


def test_unsupervised_evaluation_never_exports_supervised_metric_names():
    model = _fitted_model()

    metrics = model.evaluate(
        [
            "database connection failed host gamma",
            "user login succeeded account carol",
        ],
        verbose=False,
    )

    assert EXPECTED_UNSUPERVISED_METRICS <= set(metrics)
    assert not {
        "grouping_accuracy",
        "parsing_accuracy",
        "precision",
        "recall",
        "f1_score",
        "_ground_truth",
    } & set(metrics)


def test_trainer_logs_evaluation_contract_version():
    trainer = object.__new__(UniversalTrainer)
    trainer.config = type(
        "Config",
        (),
        {"to_dict": lambda self: {"model": {"type": "Spell"}}},
    )()

    with patch(
        "classify_log_server.training.trainer.MLFlowUtils.log_params_batch"
    ) as log_params:
        trainer._log_config()

    logged = log_params.call_args.args[0]
    assert logged["evaluation_contract_version"] == EVALUATION_CONTRACT_VERSION


def test_legacy_ground_truth_loader_warns_that_trainer_does_not_consume_labels(
    tmp_path,
):
    labels = tmp_path / "labels.txt"
    labels.write_text("0\n1\n", encoding="utf-8")

    with pytest.warns(
        FutureWarning,
        match="不属于当前正式 Trainer 契约",
    ):
        assert LogDataLoader().load_ground_truth(str(labels)) == [0, 1]

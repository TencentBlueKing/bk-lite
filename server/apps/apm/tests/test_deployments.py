from datetime import UTC, datetime, timedelta

from apps.apm.services.contracts import InferredDeploymentRelease
from apps.apm.services.deployments import annotate_inferred_deployment_status


def test_annotate_marks_version_regression_as_rollback():
    observed_at = datetime(2026, 8, 24, 12, tzinfo=UTC)
    releases = [
        InferredDeploymentRelease("shop", "checkout", "production", "1.0.0", observed_at - timedelta(days=2), observed_at - timedelta(hours=1)),
        InferredDeploymentRelease("shop", "checkout", "production", "0.9.0", observed_at - timedelta(hours=1), observed_at),
    ]
    annotated = annotate_inferred_deployment_status(releases, observed_at=observed_at)
    statuses = {item.version: status for item, status in annotated}
    assert statuses["1.0.0"] == "success"
    assert statuses["0.9.0"] == "rollback"

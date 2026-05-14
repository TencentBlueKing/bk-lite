from apps.core.logger import mlops_logger as logger
from apps.core.utils.viewset_utils import AuthViewSet
from apps.mlops.constants import TrainJobStatus, MLflowRunStatus
from apps.mlops.utils.group_scope import assert_dataset_version_scope
from apps.mlops.utils.webhook_client import (
    WebhookClient,
    WebhookConnectionError,
    WebhookError,
    WebhookTimeoutError,
)
from django.db import transaction
from rest_framework import serializers, status
from rest_framework.response import Response


class TeamModelViewSet(AuthViewSet):
    """``AuthViewSet`` with ``team`` ownership for root MLOps resources.

    Subclasses must define ``queryset`` on a model that exposes a
    ``team`` JSONField directly.
    """

    ORGANIZATION_FIELD = "team"
    MLFLOW_PREFIX = ""

    def cleanup_serving_runtime(self, serving):
        """Delete a serving runtime and return an error response on failure."""
        container_id = f"{self.MLFLOW_PREFIX}_Serving_{serving.id}"

        try:
            WebhookClient.remove(container_id)
            logger.info(
                f"删除 serving 容器成功: container_id={container_id}, serving_id={serving.id}"
            )
        except (WebhookConnectionError, WebhookTimeoutError) as e:
            logger.error(
                f"删除 serving 容器失败，已阻止数据库记录删除: container_id={container_id}, "
                f"serving_id={serving.id}, error={str(e)}",
                exc_info=True,
            )
            return Response(
                {"error": f"删除服务失败：容器清理失败，{str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        except WebhookError as e:
            if "not found" in str(e).lower() or "does not exist" in str(e).lower():
                logger.warning(
                    f"删除 serving 时容器已不存在，继续删除记录: container_id={container_id}, "
                    f"serving_id={serving.id}"
                )
            else:
                logger.error(
                    f"删除 serving 容器失败，已阻止数据库记录删除: container_id={container_id}, "
                    f"serving_id={serving.id}, error={str(e)}",
                    exc_info=True,
                )
                return Response(
                    {"error": f"删除服务失败：容器清理失败，{str(e)}"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

        return None

    def destroy_serving_with_runtime_cleanup(self, request, *args, **kwargs):
        """Delete serving runtime first, then remove the DB record."""
        instance = self.get_object()
        cleanup_error = self.cleanup_serving_runtime(instance)
        if cleanup_error is not None:
            return cleanup_error

        return super().destroy(request, *args, **kwargs)

    def destroy_train_job_with_runtime_cleanup(self, request, *args, **kwargs):
        """Delete all related serving runtimes first, then remove the train job."""
        train_job = self.get_object()
        related_servings = list(train_job.servings.all())

        for serving in related_servings:
            cleanup_error = self.cleanup_serving_runtime(serving)
            if cleanup_error is not None:
                logger.error(
                    f"删除训练任务前清理关联 serving 失败，已阻止数据库记录删除: "
                    f"train_job_id={train_job.id}, serving_id={serving.id}"
                )
                return cleanup_error

        logger.info(
            f"删除训练任务前已完成关联 serving runtime 清理: "
            f"train_job_id={train_job.id}, serving_count={len(related_servings)}"
        )

        return super().destroy(request, *args, **kwargs)

    # ---- run delete eligibility helpers (shared across all TrainJob viewsets) ----

    def claim_train_job_running(self, train_job):
        """Atomically claim a TrainJob as running.

        Returns the previous status when the claim succeeds, or ``None`` if the
        TrainJob is already running.
        """
        with transaction.atomic():
            locked_train_job = train_job.__class__.objects.select_for_update().get(pk=train_job.pk)
            if locked_train_job.status == TrainJobStatus.RUNNING:
                return None

            previous_status = locked_train_job.status
            locked_train_job.status = TrainJobStatus.RUNNING
            locked_train_job.save(update_fields=["status"])

        train_job.status = TrainJobStatus.RUNNING
        return previous_status

    def ensure_train_job_dataset_scope(self, request, train_job):
        """Block dirty TrainJob records whose dataset_version no longer matches
        the current team / persisted team binding.
        """
        try:
            assert_dataset_version_scope(train_job.dataset_version, train_job.team, request)
        except serializers.ValidationError as exc:
            detail = getattr(exc, "detail", None)
            if isinstance(detail, dict):
                errors = []
                for value in detail.values():
                    if isinstance(value, (list, tuple)):
                        errors.extend(str(item) for item in value)
                    else:
                        errors.append(str(value))
                message = "；".join(errors) if errors else "训练任务关联的数据集版本无权访问"
            else:
                message = "训练任务关联的数据集版本无权访问"
            return Response({"error": message}, status=status.HTTP_400_BAD_REQUEST)
        return None

    @staticmethod
    def restore_train_job_status(train_job, previous_status):
        """Restore a TrainJob status after webhook launch failure."""
        updated = train_job.__class__.objects.filter(pk=train_job.pk, status=TrainJobStatus.RUNNING).update(status=previous_status)
        if updated:
            train_job.status = previous_status

    @staticmethod
    def annotate_run_delete_eligibility(run_datas, train_job_status):
        """Annotate each run dict with ``is_latest_run``, ``can_delete_run``,
        ``delete_block_reason``.

        ``run_datas`` is the *full* list ordered by start_time DESC (as
        returned by ``get_experiment_runs``).  The first element is the
        latest run.

        Rules
        -----
        1. TrainJob.status != running  → all runs deletable.
        2. TrainJob.status == running AND latest run.status == RUNNING
           → latest run NOT deletable; other RUNNING runs are deletable
             (they are stale/orphaned); non-RUNNING runs are deletable.
        3. TrainJob.status == running AND latest run.status != RUNNING
           → inconsistent state – fail closed: RUNNING rows blocked,
             non-RUNNING rows deletable.
        """
        if not run_datas:
            return run_datas

        latest_run_id = run_datas[0].get("run_id")
        ambiguous_latest = not latest_run_id or sum(1 for run in run_datas if run.get("run_id") == latest_run_id) != 1

        for run in run_datas:
            is_latest = bool(latest_run_id) and run["run_id"] == latest_run_id
            if ambiguous_latest:
                run["is_latest_run"] = False
                if train_job_status == TrainJobStatus.RUNNING and run["status"] == MLflowRunStatus.RUNNING:
                    run["can_delete_run"] = False
                    run["delete_block_reason"] = "ambiguous_latest_run"
                else:
                    run["can_delete_run"] = True
                    run["delete_block_reason"] = None
                continue
            run["is_latest_run"] = is_latest

            if train_job_status != TrainJobStatus.RUNNING:
                # Rule 1
                run["can_delete_run"] = True
                run["delete_block_reason"] = None
            else:
                latest_status = run_datas[0]["status"]
                if latest_status == MLflowRunStatus.RUNNING:
                    # Rule 2
                    if is_latest:
                        run["can_delete_run"] = False
                        run["delete_block_reason"] = "active_latest_run"
                    else:
                        run["can_delete_run"] = True
                        run["delete_block_reason"] = None
                else:
                    # Rule 3 – inconsistent state
                    if run["status"] == MLflowRunStatus.RUNNING:
                        run["can_delete_run"] = False
                        run["delete_block_reason"] = "inconsistent_state"
                    else:
                        run["can_delete_run"] = True
                        run["delete_block_reason"] = None

        return run_datas

    def check_run_delete_eligibility(self, run_id, train_job):
        """Re-check eligibility for a single run right before deletion.

        Returns ``(allowed: bool, reason: str | None)``.
        """
        from apps.mlops.utils import mlflow_service

        experiment_name = mlflow_service.build_experiment_name(
            prefix=self.MLFLOW_PREFIX,
            algorithm=train_job.algorithm,
            train_job_id=train_job.id,
        )
        experiment = mlflow_service.get_experiment_by_name(experiment_name)
        experiment_id = getattr(experiment, "experiment_id", None) if experiment else None
        if not experiment_id:
            return False, "run_not_found"

        runs = mlflow_service.get_experiment_runs(str(experiment_id))
        if runs.empty:
            return False, "run_not_found"

        run_ids = list(runs["run_id"])
        if run_id not in run_ids:
            return False, "run_not_found"

        # Build lightweight dicts for the eligibility logic
        run_datas = []
        for _, row in runs.iterrows():
            run_status = row.get("status", MLflowRunStatus.UNKNOWN)
            run_datas.append(
                {
                    "run_id": str(row["run_id"]),
                    "status": str(run_status),
                }
            )

        self.annotate_run_delete_eligibility(run_datas, train_job.status)

        for rd in run_datas:
            if rd["run_id"] == run_id:
                if rd["can_delete_run"]:
                    return True, None
                return False, rd["delete_block_reason"]

        return False, "run_not_found"

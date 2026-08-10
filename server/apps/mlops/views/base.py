import pandas as pd
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.response import Response

from apps.core.logger import mlops_logger as logger
from apps.core.utils.viewset_utils import AuthViewSet
from apps.mlops.constants import MLflowRunStatus, TrainJobStatus
from apps.mlops.utils import mlflow_service
from apps.mlops.utils.group_scope import assert_dataset_version_scope
from apps.mlops.utils.i18n import mlops_message
from apps.mlops.utils.webhook_client import WebhookClient, WebhookConnectionError, WebhookError, WebhookTimeoutError


class TeamModelViewSet(AuthViewSet):
    """``AuthViewSet`` with ``team`` ownership for root MLOps resources.

    Subclasses must define ``queryset`` on a model that exposes a
    ``team`` JSONField directly.
    """

    ORGANIZATION_FIELD = "team"
    MLFLOW_PREFIX = ""

    def get_authorized_object(self):
        queryset = self.filter_queryset(self.get_queryset())
        request = getattr(self, "request", None)

        if request is not None and not getattr(getattr(request, "user", None), "is_superuser", False):
            self._validate_current_team_permission(request)
            _, _, _, query = self.filter_by_group(queryset, request, request.user)
            queryset = queryset.filter(query)

        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        lookup_value = self.kwargs.get(lookup_url_kwarg)
        return get_object_or_404(queryset, **{self.lookup_field: lookup_value})

    def get_authorized_object_or_none(self):
        try:
            return self.get_authorized_object()
        except Http404:
            return None

    def get_object(self):
        return self.get_authorized_object()

    @staticmethod
    def parse_run_list_pagination(request):
        """解析运行列表的旧分页契约；参数非法时返回 ``None``。"""
        raw_page_size = request.GET.get("page_size")
        try:
            page = int(request.GET.get("page", 1))
        except (TypeError, ValueError):
            return None

        if raw_page_size is None or raw_page_size in {"0", "-1"}:
            return page, None, False

        try:
            page_size = int(raw_page_size)
        except (TypeError, ValueError):
            return None

        if page < 1 or page_size < 1:
            return None

        return page, page_size, True

    def get_train_job_runs(self, train_job):
        from apps.mlops.utils import mlflow_service

        experiment_name = mlflow_service.build_experiment_name(
            prefix=self.MLFLOW_PREFIX,
            algorithm=train_job.algorithm,
            train_job_id=train_job.id,
        )
        experiment = mlflow_service.get_experiment_by_name(experiment_name)
        experiment_id = getattr(experiment, "experiment_id", None) if experiment else None
        if not experiment_id:
            return None

        return mlflow_service.get_experiment_runs(str(experiment_id))

    @staticmethod
    def has_run_in_runs_frame(runs, run_id):
        if runs is None or runs.empty:
            return False

        return str(run_id) in {str(value) for value in runs["run_id"]}

    def train_job_has_run(self, train_job, run_id):
        runs = self.get_train_job_runs(train_job)
        return self.has_run_in_runs_frame(runs, run_id)

    def run_not_found_response(self, run_id):
        return Response(
            {
                "error": mlops_message(self.request, "error.training_run_not_found"),
                "code": "run_not_found",
                "run_id": run_id,
            },
            status=status.HTTP_404_NOT_FOUND,
        )

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
                {"error": mlops_message(self.request, "error.serving_runtime_cleanup_failed", detail=str(e))},
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
                    {"error": mlops_message(self.request, "error.serving_runtime_cleanup_failed", detail=str(e))},
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
        runs = self.get_train_job_runs(train_job)
        if runs is None or runs.empty:
            return False, "run_not_found"

        if not self.has_run_in_runs_frame(runs, run_id):
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


class BaseTrainJobViewSet(TeamModelViewSet):
    """六类训练作业共享的运行记录动作实现。

    具体算法 ViewSet 继续声明 ``@action`` 与 ``@HasPermission``，从而保留
    既有路由和权限名；这里只集中不含算法差异的业务实现。
    """

    def delete_run(self, request, pk=None, run_id=None):
        """软删除指定 MLflow run。"""
        try:
            train_job = self.get_object()

            allowed, reason = self.check_run_delete_eligibility(run_id, train_job)
            if not allowed:
                return Response(
                    {
                        "error": mlops_message(
                            request,
                            "error.training_run_not_found" if reason == "run_not_found" else "error.training_run_cannot_delete",
                        ),
                        "code": reason,
                        "run_id": run_id,
                    },
                    status=(status.HTTP_404_NOT_FOUND if reason == "run_not_found" else status.HTTP_400_BAD_REQUEST),
                )

            mlflow_service.delete_run(run_id)

            return Response(
                {
                    "result": True,
                    "run_id": run_id,
                    "train_job_id": train_job.id,
                    "deleted": True,
                    "deletion_type": "mlflow_soft_delete",
                }
            )
        except Exception as e:
            logger.error(f"删除 run 失败: {str(e)}", exc_info=True)
            return Response(
                {
                    "result": False,
                    "message": mlops_message(request, "error.run_delete_failed", detail=str(e)),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def get_metric_data(self, request, pk=None, run_id: str = "", metric_name: str = ""):
        """获取指定 run 的指标历史。"""
        try:
            train_job = self.get_authorized_object_or_none()
            if train_job is None:
                return self.run_not_found_response(run_id)
            if not self.train_job_has_run(train_job, run_id):
                return self.run_not_found_response(run_id)

            metric_data = mlflow_service.get_metric_history(run_id, metric_name)
            if not metric_data:
                return Response(
                    {
                        "run_id": run_id,
                        "metric_name": metric_name,
                        "total_points": 0,
                        "metric_history": [],
                    }
                )

            return Response(
                {
                    "run_id": run_id,
                    "metric_name": metric_name,
                    "total_points": len(metric_data),
                    "metric_history": metric_data,
                }
            )
        except Exception as e:
            logger.error(f"获取指标历史数据失败: {str(e)}", exc_info=True)
            return Response(
                {
                    "error": mlops_message(
                        request,
                        "error.metric_history_fetch_failed",
                        detail=str(e),
                    )
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def get_run_params(self, request, pk=None, run_id: str = ""):
        """获取指定 run 的训练参数与运行元信息。"""
        try:
            train_job = self.get_authorized_object_or_none()
            if train_job is None:
                return self.run_not_found_response(run_id)
            if not self.train_job_has_run(train_job, run_id):
                return self.run_not_found_response(run_id)

            run = mlflow_service.get_run_info(run_id)
            params = mlflow_service.get_run_params(run_id)
            run_name = run.data.tags.get("mlflow.runName", run_id)
            run_status = run.info.status
            start_time = run.info.start_time
            end_time = run.info.end_time

            return Response(
                {
                    "run_id": run_id,
                    "run_name": run_name,
                    "status": run_status,
                    "start_time": pd.Timestamp(start_time, unit="ms").isoformat() if start_time else None,
                    "end_time": pd.Timestamp(end_time, unit="ms").isoformat() if end_time else None,
                    "params": params,
                }
            )
        except Exception as e:
            logger.error(f"获取运行参数失败: {str(e)}", exc_info=True)
            return Response(
                {
                    "error": mlops_message(
                        request,
                        "error.run_params_fetch_failed",
                        detail=str(e),
                    )
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

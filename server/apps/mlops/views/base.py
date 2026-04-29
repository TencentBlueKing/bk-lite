from apps.core.utils.viewset_utils import AuthViewSet
from apps.mlops.constants import TrainJobStatus, MLflowRunStatus
from apps.core.logger import mlops_logger as logger


class TeamModelViewSet(AuthViewSet):
    """``AuthViewSet`` with ``team`` ownership for root MLOps resources.

    Subclasses must define ``queryset`` on a model that exposes a
    ``team`` JSONField directly.
    """

    ORGANIZATION_FIELD = "team"
    MLFLOW_PREFIX = ""

    # ---- run delete eligibility helpers (shared across all TrainJob viewsets) ----

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

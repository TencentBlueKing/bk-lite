try:
    from apps.cmdb.enterprise.models import *  # noqa
except ModuleNotFoundError as exc:
    if exc.name not in {"apps.cmdb.enterprise", "apps.cmdb.enterprise.models"}:
        raise

    import hashlib
    import secrets
    from hmac import compare_digest

    from django.db import models, transaction
    from django.utils import timezone

    from apps.core.models.maintainer_info import MaintainerInfo
    from apps.core.models.time_info import TimeInfo

    class CustomReportingTask(TimeInfo, MaintainerInfo):
        name = models.CharField(max_length=128, db_index=True, verbose_name="任务名称")
        team = models.JSONField(default=list, verbose_name="关联组织")
        config = models.JSONField(default=dict, verbose_name="任务配置")
        is_enabled = models.BooleanField(default=True, db_index=True, verbose_name="启用状态")
        last_reported_at = models.DateTimeField(
            null=True,
            blank=True,
            db_index=True,
            verbose_name="最近上报时间",
        )

        class Meta:
            db_table = "cmdb_custom_reporting_task"
            verbose_name = "自定义报表任务"
            verbose_name_plural = verbose_name
            ordering = ["-created_at"]
            indexes = [
                models.Index(fields=["name"], name="idx_custom_report_task_name"),
                models.Index(fields=["is_enabled"], name="idx_custom_report_task_enabled"),
            ]

        def __str__(self):
            return f"CustomReportingTask({self.id}:{self.name})"

        def sync_scopes(self):
            CustomReportingTaskScope.objects.filter(task=self).delete()
            scopes = [
                CustomReportingTaskScope(task=self, team_id=team_id, name=self.name)
                for team_id in (self.team or [])
            ]
            if scopes:
                CustomReportingTaskScope.objects.bulk_create(scopes)

        def save(self, *args, **kwargs):
            sync_scopes = kwargs.pop("sync_scopes", True)
            with transaction.atomic():
                super().save(*args, **kwargs)
                if sync_scopes:
                    self.sync_scopes()


    class CustomReportingTaskScope(models.Model):
        task = models.ForeignKey(
            CustomReportingTask,
            on_delete=models.CASCADE,
            related_name="scopes",
            verbose_name="所属任务",
        )
        team_id = models.BigIntegerField(db_index=True, verbose_name="组织ID")
        name = models.CharField(max_length=128, verbose_name="任务名称")

        class Meta:
            db_table = "cmdb_custom_reporting_task_scope"
            verbose_name = "自定义报表任务组织映射"
            verbose_name_plural = verbose_name
            unique_together = (("team_id", "name"),)
            indexes = [
                models.Index(fields=["task", "team_id"], name="idx_cr_task_scope_task_team"),
            ]

        def __str__(self):
            return f"CustomReportingTaskScope(task={self.task_id}, team={self.team_id}, name={self.name})"


    class CustomReportingCredential(TimeInfo, MaintainerInfo):
        task = models.ForeignKey(
            CustomReportingTask,
            on_delete=models.CASCADE,
            related_name="credentials",
            verbose_name="所属任务",
        )
        name = models.CharField(max_length=128, verbose_name="凭据名称")
        credential_type = models.CharField(max_length=64, verbose_name="凭据类型")
        credential_data = models.JSONField(default=dict, verbose_name="凭据内容")
        is_enabled = models.BooleanField(default=True, verbose_name="启用状态")
        last_used_at = models.DateTimeField(null=True, blank=True, verbose_name="最近使用时间")

        class Meta:
            db_table = "cmdb_custom_reporting_credential"
            verbose_name = "自定义报表凭据"
            verbose_name_plural = verbose_name
            ordering = ["-created_at"]
            constraints = [
                models.UniqueConstraint(fields=["task"], name="uniq_cr_credential_task"),
            ]

        def __str__(self):
            return f"CustomReportingCredential({self.id}:{self.name})"

        def _sanitize_credential_data(self):
            credential_data = dict(self.credential_data or {})
            raw_token = credential_data.pop("token", None)
            if raw_token:
                credential_data["token_hash"] = hashlib.sha256(str(raw_token).encode("utf-8")).hexdigest()
                credential_data["token_masked"] = True
            self.credential_data = credential_data

        def save(self, *args, **kwargs):
            self._sanitize_credential_data()
            super().save(*args, **kwargs)

        def issue_token(self, token: str | None = None):
            raw_token = token or secrets.token_urlsafe(32)
            credential_data = dict(self.credential_data or {})
            credential_data["token"] = raw_token
            credential_data["issued_at"] = timezone.now().isoformat()
            credential_data["token_revoked"] = False
            credential_data.pop("revoked_at", None)
            self.is_enabled = True
            self.credential_data = credential_data
            self.save()
            return raw_token

        def rotate_token(self, token: str | None = None):
            raw_token = self.issue_token(token=token)
            credential_data = dict(self.credential_data or {})
            credential_data["rotated_at"] = timezone.now().isoformat()
            self.credential_data = credential_data
            self.save()
            return raw_token

        def revoke_token(self):
            credential_data = dict(self.credential_data or {})
            credential_data.pop("token_hash", None)
            credential_data.pop("token_masked", None)
            credential_data["token_revoked"] = True
            credential_data["revoked_at"] = timezone.now().isoformat()
            self.is_enabled = False
            self.credential_data = credential_data
            self.save()

        def matches_token(self, raw_token: str | None):
            if not raw_token or not self.is_enabled:
                return False

            credential_data = dict(self.credential_data or {})
            token_hash = credential_data.get("token_hash")
            if not token_hash or credential_data.get("token_revoked") is True:
                return False

            expected_hash = hashlib.sha256(str(raw_token).encode("utf-8")).hexdigest()
            return compare_digest(str(token_hash), expected_hash)

        def mark_used(self):
            self.last_used_at = timezone.now()
            self.save(update_fields=["last_used_at", "updated_at"])


    class CustomReportingBatch(TimeInfo):
        STATUS_PENDING = "pending"
        STATUS_RUNNING = "running"
        STATUS_SUCCESS = "success"
        STATUS_FAILED = "failed"
        STATUS_CHOICES = (
            (STATUS_PENDING, "待处理"),
            (STATUS_RUNNING, "执行中"),
            (STATUS_SUCCESS, "成功"),
            (STATUS_FAILED, "失败"),
        )

        task = models.ForeignKey(
            CustomReportingTask,
            on_delete=models.CASCADE,
            related_name="batches",
            verbose_name="所属任务",
        )
        status = models.CharField(
            max_length=32,
            choices=STATUS_CHOICES,
            default=STATUS_PENDING,
            db_index=True,
            verbose_name="批次状态",
        )
        summary = models.JSONField(default=dict, verbose_name="批次摘要")

        class Meta:
            db_table = "cmdb_custom_reporting_batch"
            verbose_name = "自定义报表批次"
            verbose_name_plural = verbose_name
            ordering = ["-created_at"]
            indexes = [
                models.Index(fields=["task", "status"], name="idx_custom_report_batch_status"),
            ]

        def __str__(self):
            return f"CustomReportingBatch({self.id}:{self.status})"


    class CustomReportingPendingRelation(TimeInfo):
        task = models.ForeignKey(
            CustomReportingTask,
            on_delete=models.CASCADE,
            related_name="pending_relations",
            verbose_name="所属任务",
        )
        source_model_id = models.CharField(max_length=64, verbose_name="源模型ID")
        target_model_id = models.CharField(max_length=64, verbose_name="目标模型ID")
        relation_payload = models.JSONField(default=dict, verbose_name="关系载荷")

        class Meta:
            db_table = "cmdb_custom_reporting_pending_relation"
            verbose_name = "自定义报表待处理关系"
            verbose_name_plural = verbose_name
            ordering = ["-created_at"]
            indexes = [
                models.Index(
                    fields=["task", "source_model_id", "target_model_id"],
                    name="idx_cr_pending_rel",
                ),
            ]

        def __str__(self):
            return (
                f"CustomReportingPendingRelation("
                f"{self.id}:{self.source_model_id}->{self.target_model_id})"
            )


    class CustomReportingCleanupReview(TimeInfo, MaintainerInfo):
        STATUS_PENDING = "pending"
        STATUS_APPROVED = "approved"
        STATUS_REJECTED = "rejected"
        STATUS_CHOICES = (
            (STATUS_PENDING, "待审核"),
            (STATUS_APPROVED, "已通过"),
            (STATUS_REJECTED, "已驳回"),
        )

        batch = models.ForeignKey(
            CustomReportingBatch,
            on_delete=models.CASCADE,
            related_name="cleanup_reviews",
            verbose_name="所属批次",
        )
        status = models.CharField(
            max_length=32,
            choices=STATUS_CHOICES,
            default=STATUS_PENDING,
            db_index=True,
            verbose_name="审核状态",
        )
        review_payload = models.JSONField(default=dict, verbose_name="审核内容")
        reviewed_by = models.CharField(max_length=32, blank=True, default="", verbose_name="审核人")
        reviewed_at = models.DateTimeField(null=True, blank=True, verbose_name="审核时间")

        class Meta:
            db_table = "cmdb_custom_reporting_cleanup_review"
            verbose_name = "自定义报表清理审核"
            verbose_name_plural = verbose_name
            ordering = ["-created_at"]
            indexes = [
                models.Index(fields=["batch", "status"], name="idx_cr_review_status"),
            ]

        def __str__(self):
            return f"CustomReportingCleanupReview({self.id}:batch={self.batch_id})"

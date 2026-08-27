from django.db import models

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo

TYPE_SCOPED_COLLECT_TYPE_NAMES = frozenset({"syslog", "snmp_trap"})


class LogExtractor(TimeInfo, MaintainerInfo):
    class ExtractorType(models.TextChoices):
        COPY = "copy", "Copy"
        SPLIT = "split", "Split"
        KV = "kv", "Key Value"
        REGEX = "regex", "Regex"
        REGEX_REPLACE = "regex_replace", "Regex Replace"
        JSON = "json", "JSON"

    name = models.CharField(max_length=200)
    collect_instance = models.ForeignKey("log.CollectInstance", null=True, blank=True, on_delete=models.CASCADE, related_name="log_extractors")
    collect_type = models.ForeignKey("log.CollectType", null=True, blank=True, on_delete=models.CASCADE, related_name="type_log_extractors")
    condition = models.JSONField(default=dict)
    extractor_type = models.CharField(max_length=20, choices=ExtractorType.choices)
    source_field = models.CharField(max_length=500, default="message")
    target_field = models.CharField(max_length=500, null=True, blank=True)
    delete_source = models.BooleanField(default=False)
    config = models.JSONField(default=dict)
    sort_order = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ("collect_instance_id", "collect_type_id", "sort_order", "id")
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(collect_instance__isnull=False, collect_type__isnull=True)
                    | models.Q(collect_instance__isnull=True, collect_type__isnull=False)
                ),
                name="log_extractor_scope_xor",
            ),
            models.UniqueConstraint(
                fields=("collect_instance", "name"), condition=models.Q(collect_instance__isnull=False), name="log_extractor_instance_name_uniq"
            ),
            models.UniqueConstraint(
                fields=("collect_instance", "sort_order"),
                condition=models.Q(collect_instance__isnull=False),
                name="log_extractor_instance_order_uniq",
            ),
            models.UniqueConstraint(
                fields=("collect_instance", "name"),
                name="log_extractor_instance_name_portable_uniq",
            ),
            models.UniqueConstraint(
                fields=("collect_instance", "sort_order"),
                name="log_extractor_instance_order_portable_uniq",
            ),
            models.UniqueConstraint(
                fields=("collect_type", "name"),
                condition=models.Q(collect_instance__isnull=True, collect_type__isnull=False),
                name="log_extractor_type_name_uniq",
            ),
            models.UniqueConstraint(
                fields=("collect_type", "sort_order"),
                condition=models.Q(collect_instance__isnull=True, collect_type__isnull=False),
                name="log_extractor_type_order_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=("collect_instance", "sort_order", "id"), name="log_extractor_order_idx"),
            models.Index(fields=("collect_type", "sort_order", "id"), name="log_extractor_type_order_idx"),
        ]


class SystemVectorConfigState(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        GENERATING = "generating", "Generating"
        PUBLISHED = "published", "Published"
        FAILED = "failed", "Failed"

    scope = models.CharField(max_length=20, primary_key=True, default="global", editable=False)
    desired_generation = models.PositiveBigIntegerField(default=0)
    published_generation = models.PositiveBigIntegerField(default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    published_content = models.TextField(blank=True, default="")
    published_checksum = models.CharField(max_length=71, blank=True, default="")
    last_error = models.CharField(max_length=500, blank=True, default="")
    last_published_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)


class SystemVectorToken(models.Model):
    scope = models.CharField(max_length=20, primary_key=True, default="global", editable=False)
    token_digest = models.CharField(max_length=256)
    rotated_at = models.DateTimeField(auto_now=True)

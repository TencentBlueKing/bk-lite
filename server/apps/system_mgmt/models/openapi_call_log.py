from django.db import models

from apps.core.models.time_info import TimeInfo


class OpenAPICallLog(TimeInfo):
    CREDENTIAL_API_TOKEN = "api_token"
    CREDENTIAL_SYSTEM_TOKEN = "system_token"
    CREDENTIAL_CHOICES = [
        ("", ""),
        (CREDENTIAL_API_TOKEN, "API Token"),
        (CREDENTIAL_SYSTEM_TOKEN, "System Token"),
    ]

    API_KIND_INTERNAL = "internal"
    API_KIND_EXTERNAL = "external"
    API_KIND_CHOICES = [
        ("", ""),
        (API_KIND_INTERNAL, "Internal"),
        (API_KIND_EXTERNAL, "External"),
    ]

    source_ip = models.GenericIPAddressField("Source IP")
    username = models.CharField("Username", max_length=100, db_index=True, blank=True, default="")
    credential_type = models.CharField(
        "Credential Type",
        max_length=16,
        choices=CREDENTIAL_CHOICES,
        blank=True,
        default="",
    )
    token_id = models.PositiveIntegerField("Token ID", null=True, blank=True)
    token_name = models.CharField("Token Name", max_length=128, blank=True, default="")
    system_id = models.CharField("System ID", max_length=32, blank=True, default="")
    team_id = models.PositiveIntegerField("Team ID", null=True, blank=True)
    api_kind = models.CharField(
        "API Kind",
        max_length=16,
        choices=API_KIND_CHOICES,
        blank=True,
        default="",
    )
    method = models.CharField("Method", max_length=10, blank=True, default="")
    path = models.CharField("Path", max_length=512, blank=True, default="")
    http_status = models.PositiveSmallIntegerField("HTTP Status")
    error_code = models.CharField("Error Code", max_length=32, blank=True, default="")

    class Meta:
        verbose_name = "OpenAPI Call Log"
        verbose_name_plural = "OpenAPI Call Logs"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["username", "-created_at"]),
            models.Index(fields=["credential_type", "token_id", "-created_at"]),
        ]
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(credential_type="system_token") & ~models.Q(system_id="")
                )
                | (~models.Q(credential_type="system_token") & models.Q(system_id="")),
                name="openapi_call_system_id_ck",
            ),
        ]

    def __str__(self):
        return f"{self.username} {self.method} {self.path} {self.http_status}"

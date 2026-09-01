from django.db import transaction
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from apps.alerts.constants.constants import DEFAULT_GROUP_ID, SNMP_TRAP_SOURCE_ID
from apps.alerts.models.alert_source import AlertSource
from apps.alerts.utils.util import encode_team_secret
from apps.core.logger import alert_logger as logger


class AlertSourceCredentialService:
    """Own organization scope, atomic mutation, and controlled credential delivery."""

    @staticmethod
    def _team_ids(user):
        team_ids = set()
        for item in getattr(user, "group_list", []) or []:
            value = item.get("id") if isinstance(item, dict) else item
            try:
                team_ids.add(str(int(value)))
            except (TypeError, ValueError):
                continue
        return team_ids

    @classmethod
    def ensure_team_access(cls, user, team_id):
        team_id = str(team_id)
        if getattr(user, "is_superuser", False):
            return team_id
        if team_id not in cls._team_ids(user):
            raise PermissionDenied("无权管理该组织的告警源密钥")
        return team_id

    @classmethod
    def list_metadata(cls, user, source):
        allowed_team_ids = None if getattr(user, "is_superuser", False) else cls._team_ids(user)
        team_names = {
            str(item.get("id")): item.get("name", "")
            for item in (getattr(user, "group_list", []) or [])
            if isinstance(item, dict) and item.get("id") is not None
        }
        result = []
        for team_id in sorted((source.team_secrets or {}), key=str):
            team_id = str(team_id)
            if allowed_team_ids is not None and team_id not in allowed_team_ids:
                continue
            result.append(
                {
                    "team_id": team_id,
                    "team_name": team_names.get(team_id, ""),
                    "has_secret": True,
                }
            )
        return result

    @classmethod
    def reveal(cls, user, source, team_id):
        team_id = cls.ensure_team_access(user, team_id)
        secret = (source.team_secrets or {}).get(team_id)
        if not secret:
            raise NotFound("该组织尚未配置密钥")
        cls._audit("revealed", user, source.source_id, team_id)
        return {"team_id": team_id, "secret": secret}

    @classmethod
    def deployment_credential(cls, user, source, team_id):
        team_id = cls.ensure_team_access(user, team_id)
        if source.source_id == SNMP_TRAP_SOURCE_ID:
            if team_id != str(DEFAULT_GROUP_ID):
                raise PermissionDenied("SNMP Trap 仅支持默认组织")
            cls._audit("material_revealed", user, source.source_id, team_id)
            return source.secret
        return cls.reveal(user, source, team_id)["secret"]

    @classmethod
    def add(cls, user, source_id, team_id):
        return cls._mutate(user, source_id, team_id, "added")

    @classmethod
    def regenerate(cls, user, source_id, team_id):
        return cls._mutate(user, source_id, team_id, "regenerated")

    @classmethod
    def remove(cls, user, source_id, team_id):
        return cls._mutate(user, source_id, team_id, "removed")

    @classmethod
    def _mutate(cls, user, source_id, team_id, action):
        team_id = cls.ensure_team_access(user, team_id)
        with transaction.atomic():
            try:
                source = AlertSource.objects.select_for_update().get(pk=source_id)
            except AlertSource.DoesNotExist as error:
                raise NotFound("告警源不存在") from error

            if source.source_id == SNMP_TRAP_SOURCE_ID:
                raise ValidationError({"detail": "SNMP Trap 不支持组织密钥"})

            team_secrets = dict(source.team_secrets or {})
            if action == "added":
                if team_id in team_secrets:
                    raise ValidationError({"detail": f"组织 {team_id} 已存在密钥"})
                secret = encode_team_secret(source.secret, team_id)
                team_secrets[team_id] = secret
            elif action == "regenerated":
                if team_id not in team_secrets:
                    raise NotFound("该组织尚未配置密钥")
                secret = encode_team_secret(source.secret, team_id)
                team_secrets[team_id] = secret
            elif action == "removed":
                if team_id not in team_secrets:
                    raise NotFound("该组织尚未配置密钥")
                del team_secrets[team_id]
                secret = None
            else:
                raise ValueError(f"Unsupported team secret action: {action}")

            source.team_secrets = team_secrets
            source.save(update_fields=["team_secrets", "updated_at"])

        cls._audit(action, user, source.source_id, team_id)
        result = {"team_id": team_id}
        if secret:
            result["secret"] = secret
        return result

    @staticmethod
    def _audit(action, user, source_id, team_id):
        logger.info(
            "event=alert_source_team_secret_%s actor=%s source_id=%s team_id=%s",
            action,
            getattr(user, "username", ""),
            source_id,
            team_id,
        )

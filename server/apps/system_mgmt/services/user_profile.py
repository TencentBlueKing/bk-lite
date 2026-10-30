"""用户标准档案与自定义字段的读取、校验和同步写入。"""

from datetime import datetime, time

from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from apps.system_mgmt.models.user import EmploymentStatus, User
from apps.system_mgmt.models.user_field import UserFieldDefinition, UserFieldType, UserFieldValue
from apps.system_mgmt.models.user_sync_source import UserSyncSource

PROFILE_KEYS = frozenset(
    {
        "username",
        "display_name",
        "email",
        "phone",
        "manager",
        "employment_status",
        "job_title",
        "job_level",
        "employee_no",
        "account_expires_at",
        "disabled",
    }
)
TEXT_PROFILE_FIELDS = ("job_title", "job_level", "employee_no")
_UNSET = object()
_EMPLOYMENT_ALIASES = {
    "unspecified": EmploymentStatus.UNSPECIFIED,
    "未设置": EmploymentStatus.UNSPECIFIED,
    "employed": EmploymentStatus.EMPLOYED,
    "在职": EmploymentStatus.EMPLOYED,
    "resigned": EmploymentStatus.RESIGNED,
    "离职": EmploymentStatus.RESIGNED,
}
_PERMANENT_EXPIRY = {"permanent", "never", "永久", "永久有效"}
_DISABLED_TRUE = {"true", "1", "yes", "disabled", "禁用"}
_DISABLED_FALSE = {"false", "0", "no", "enabled", "启用"}


class ProfileInputError(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


def parse_disabled(raw):
    """返回 True、False 或 _UNSET。空值和无法识别的值都不覆盖。"""
    text = str(raw or "").strip()
    if not text:
        return _UNSET
    folded = text.casefold()
    if folded in _DISABLED_TRUE or text in _DISABLED_TRUE:
        return True
    if folded in _DISABLED_FALSE or text in _DISABLED_FALSE:
        return False
    return _UNSET


def parse_employment_status(raw):
    text = str(raw or "").strip()
    if not text:
        return None
    alias = _EMPLOYMENT_ALIASES.get(text) or _EMPLOYMENT_ALIASES.get(text.casefold())
    return alias


def parse_account_expiry(raw):
    """返回到期时间、None（永久）或 _UNSET（无法识别）。空值视为未提供。"""
    text = str(raw or "").strip()
    if not text:
        return _UNSET
    if text.casefold() in _PERMANENT_EXPIRY or text in _PERMANENT_EXPIRY:
        return None
    parsed = parse_datetime(text)
    if parsed is None and len(text) >= 10:
        parsed_date = parse_date(text[:10])
        if parsed_date is not None and text[:10] == parsed_date.isoformat():
            parsed = datetime.combine(parsed_date, time.min)
    if parsed is None:
        return _UNSET
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def _clip(field_name, value):
    max_length = User._meta.get_field(field_name).max_length
    text = str(value or "")
    if max_length and len(text) > max_length:
        return text[:max_length]
    return text


def extract_mapped_profile(raw_user, field_mapping):
    """只读取映射里出现的档案。空文本、无法识别的状态和到期时间不进入更新。"""
    mapping = field_mapping or {}
    profile = {
        "texts": {},
        "employment_status": None,
        "account_expires_at": _UNSET,
        "manager_username": None,
        "disabled": _UNSET,
        "custom_fields": {},
    }
    for field_name in TEXT_PROFILE_FIELDS:
        if field_name not in mapping:
            continue
        raw = raw_user.get(mapping.get(field_name))
        text = _clip(field_name, str(raw or "").strip())
        if text:
            profile["texts"][field_name] = text
    if "employment_status" in mapping:
        parsed = parse_employment_status(raw_user.get(mapping.get("employment_status")))
        if parsed:
            profile["employment_status"] = parsed
    if "account_expires_at" in mapping:
        parsed_expiry = parse_account_expiry(raw_user.get(mapping.get("account_expires_at")))
        if parsed_expiry is not _UNSET:
            profile["account_expires_at"] = parsed_expiry
    if "manager" in mapping:
        manager_name = str(raw_user.get(mapping.get("manager")) or "").strip()
        if manager_name:
            profile["manager_username"] = manager_name
    if "disabled" in mapping and str(mapping.get("disabled") or "").strip():
        parsed_disabled = parse_disabled(raw_user.get(mapping.get("disabled")))
        if parsed_disabled is not _UNSET:
            profile["disabled"] = parsed_disabled
    for key, source_key in mapping.items():
        if key in PROFILE_KEYS or not source_key:
            continue
        raw = raw_user.get(source_key)
        text = "" if raw is None else str(raw).strip()
        if text:
            profile["custom_fields"][key] = text
    return profile


def _aware(value):
    if value is None:
        return None
    if timezone.is_naive(value):
        return timezone.make_aware(value, timezone.get_current_timezone())
    return value


def manager_chain_reaches(manager, subject_id, subject_username, subject_domain):
    if manager is None:
        return False
    if subject_username and manager.username == subject_username and manager.domain == subject_domain:
        return True
    seen = set()
    current_id = manager.id
    while current_id:
        if subject_id and current_id == subject_id:
            return True
        if current_id in seen:
            return False
        seen.add(current_id)
        current_id = User.objects.filter(id=current_id).values_list("manager_id", flat=True).first()
    return False


def lookup_manager(username, domain):
    if not username:
        return None
    return User.objects.filter(username=username, domain=domain).only("id", "username", "domain", "manager_id").first()


def apply_mapped_profile(user, profile):
    """把同步映射应用到用户。匹配不到或成环的上级保持原值。返回是否改了用户列。"""
    changed = False
    for field_name, value in profile["texts"].items():
        if getattr(user, field_name) != value:
            setattr(user, field_name, value)
            changed = True
    if profile["employment_status"] and user.employment_status != profile["employment_status"]:
        user.employment_status = profile["employment_status"]
        changed = True
    if profile["account_expires_at"] is not _UNSET:
        if _aware(user.account_expires_at) != _aware(profile["account_expires_at"]):
            user.account_expires_at = profile["account_expires_at"]
            changed = True
    if profile["manager_username"]:
        manager = lookup_manager(profile["manager_username"], user.domain)
        if manager is not None and not manager_chain_reaches(manager, user.pk, user.username, user.domain):
            if user.manager_id != manager.id:
                user.manager = manager
                changed = True
    mapped_disabled = profile.get("disabled", _UNSET)
    if mapped_disabled is not _UNSET and user.disabled != mapped_disabled:
        user.disabled = mapped_disabled
        changed = True
    return changed


def profile_create_kwargs(profile, username, domain):
    attrs = dict(profile["texts"])
    if profile["employment_status"]:
        attrs["employment_status"] = profile["employment_status"]
    if profile["account_expires_at"] is not _UNSET:
        attrs["account_expires_at"] = profile["account_expires_at"]
    if profile["manager_username"]:
        manager = lookup_manager(profile["manager_username"], domain)
        subject = User(username=username, domain=domain)
        if manager is not None and not manager_chain_reaches(manager, None, subject.username, subject.domain):
            attrs["manager"] = manager
    mapped_disabled = profile.get("disabled", _UNSET)
    if mapped_disabled is not _UNSET:
        attrs["disabled"] = mapped_disabled
    return attrs


def coerce_custom_value(field_type, raw):
    text = "" if raw is None else str(raw).strip()
    if not text:
        return None
    if field_type == UserFieldType.TEXT:
        return text[:255]
    if field_type == UserFieldType.NUMBER:
        try:
            number = float(text) if "." in text else int(text)
        except ValueError:
            return None
        return str(number)
    if field_type == UserFieldType.DATE:
        parsed = parse_date(text[:10]) if len(text) >= 10 else None
        if parsed is None or text[:10] != parsed.isoformat():
            parsed_dt = parse_datetime(text)
            parsed = parsed_dt.date() if parsed_dt is not None else parse_date(text)
        if parsed is None:
            return None
        return parsed.isoformat()
    return None


def write_mapped_custom_fields(user, custom_fields):
    """停用、无法解析或不存在的字段跳过。返回是否写过值。"""
    if not custom_fields:
        return False
    definitions = {item.key: item for item in UserFieldDefinition.objects.filter(key__in=list(custom_fields), is_enabled=True)}
    changed = False
    for key, raw in custom_fields.items():
        definition = definitions.get(key)
        if definition is None:
            continue
        value = coerce_custom_value(definition.field_type, raw)
        if value is None:
            continue
        current = UserFieldValue.objects.filter(user=user, field=definition).first()
        if current is None:
            UserFieldValue.objects.create(user=user, field=definition, value=value)
            changed = True
        elif current.value != value:
            current.value = value
            current.save(update_fields=["value"])
            changed = True
    return changed


def _require_employment(raw):
    parsed = parse_employment_status(raw)
    if parsed is None:
        raise ProfileInputError("invalid employment status")
    return parsed


def form_profile_fields(params, user):
    """管理员保存。空值会清空本地档案；自指或成环的上级拒绝这次保存。"""
    fields = {}
    for field_name in TEXT_PROFILE_FIELDS:
        if field_name in params:
            fields[field_name] = _clip(field_name, str(params.get(field_name) or "").strip())
    if "employment_status" in params:
        fields["employment_status"] = _require_employment(params.get("employment_status") or EmploymentStatus.UNSPECIFIED)
    if "account_expires_at" in params:
        raw_expiry = params.get("account_expires_at")
        if raw_expiry in (None, ""):
            fields["account_expires_at"] = None
        else:
            parsed_expiry = parse_account_expiry(raw_expiry)
            if parsed_expiry is _UNSET:
                raise ProfileInputError("invalid account expiry")
            fields["account_expires_at"] = parsed_expiry
    if "manager_username" in params:
        manager_name = str(params.get("manager_username") or "").strip()
        if not manager_name:
            fields["manager_id"] = None
        else:
            manager = lookup_manager(manager_name, getattr(user, "domain", None) or "domain.com")
            if manager is None:
                raise ProfileInputError("manager not found")
            if manager_chain_reaches(manager, getattr(user, "pk", None), getattr(user, "username", ""), getattr(user, "domain", "") or "domain.com"):
                raise ProfileInputError("manager cycle")
            fields["manager_id"] = manager.id
    return fields


def form_custom_values(user, raw_fields):
    """返回要写入的 {definition: value}。停用字段若提交了不同的值则拒绝。"""
    if not isinstance(raw_fields, dict):
        raise ProfileInputError("invalid custom fields")
    definitions = {item.key: item for item in UserFieldDefinition.objects.filter(key__in=list(raw_fields))}
    existing = {}
    if getattr(user, "pk", None):
        existing = {item.field_id: item.value for item in UserFieldValue.objects.filter(user=user, field__key__in=list(raw_fields))}
    writes = {}
    for key, raw in raw_fields.items():
        definition = definitions.get(key)
        if definition is None:
            raise ProfileInputError("unknown custom field")
        value = coerce_custom_value(definition.field_type, raw)
        if value is None and str(raw or "").strip():
            raise ProfileInputError("invalid custom field value")
        stored = existing.get(definition.id, "")
        if not definition.is_enabled:
            if (value or "") != (stored or ""):
                raise ProfileInputError("custom field disabled")
            continue
        if value is None:
            value = ""
        if value != (stored or ""):
            writes[definition] = value
    return writes


def save_custom_values(user, writes):
    for definition, value in writes.items():
        current = UserFieldValue.objects.filter(user=user, field=definition).first()
        if current is None:
            if value == "":
                continue
            UserFieldValue.objects.create(user=user, field=definition, value=value)
        else:
            current.value = value
            current.save(update_fields=["value"])


def custom_field_details(user):
    definitions = list(UserFieldDefinition.objects.all())
    values = {item.field_id: item.value for item in UserFieldValue.objects.filter(user=user)}
    rows = []
    for definition in definitions:
        value = values.get(definition.id, "")
        if not definition.is_enabled and not value:
            continue
        rows.append(
            {
                "key": definition.key,
                "name": definition.name,
                "field_type": definition.field_type,
                "description": definition.description,
                "is_enabled": definition.is_enabled,
                "value": value,
            }
        )
    return rows


def field_mapping_targets(key):
    """返回第一个把该字段映射到非空外部名的同步源。调用方只判断有没有映射。"""
    for source in UserSyncSource.objects.filter(field_mapping__has_key=key).order_by("id").only("id", "field_mapping").iterator(chunk_size=1):
        mapping = source.field_mapping or {}
        if str(mapping.get(key) or "").strip():
            return [source.id]
    return []

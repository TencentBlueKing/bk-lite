import json

from apps.system_mgmt.models import User

DEFAULT_OTP_RECOMMENDED_APPS = "Microsoft Authenticator,FreeOTP,Google Authenticator"
BUILTIN_ADMIN_USERNAME = "admin"
BUILTIN_ADMIN_DOMAIN = "domain.com"


def default_otp_whitelist_value():
    admin_id = User.objects.filter(username=BUILTIN_ADMIN_USERNAME, domain=BUILTIN_ADMIN_DOMAIN).values_list("id", flat=True).first()
    return json.dumps([admin_id] if admin_id is not None else [])


def parse_otp_recommended_apps(raw_value):
    return [item.strip() for item in str(raw_value or "").split(",") if item.strip()]


def parse_otp_whitelist_ids(raw_value):
    if raw_value in (None, ""):
        return set()
    try:
        parsed = json.loads(raw_value) if isinstance(raw_value, str) else raw_value
    except (TypeError, ValueError, json.JSONDecodeError):
        return set()
    if not isinstance(parsed, list):
        return set()
    user_ids = set()
    for item in parsed:
        if isinstance(item, bool):
            continue
        try:
            user_ids.add(int(item))
        except (TypeError, ValueError):
            continue
    return user_ids

# flake8: noqa
from .common import *  # noqa: F401,F403
from .common import _build_jwt_payload, _get_pwd_policy_settings, _verify_token


@nats_client.register
def login(username, password):
    user = User.objects.filter(username=username, domain="domain.com").first()
    if not user:
        return {"result": False, "message": "Username or password is incorrect"}

    # 初始化语言加载器，使用用户的locale
    loader = LanguageLoader(app="system_mgmt", default_lang=user.locale or "en")

    # 检查账号是否被锁定
    now = timezone.now()
    if user.account_locked_until and user.account_locked_until > now:
        # 计算剩余锁定时间（分钟）
        remaining_minutes = int((user.account_locked_until - now).total_seconds() / 60) + 1
        msg = loader.get(
            "login.account_locked",
            "Account is locked. Please try again after {minutes} minutes.",
        ).format(minutes=remaining_minutes)
        return {"result": False, "message": msg}

    # 使用 check_password 验证密码是否匹配
    if not check_password(password, user.password):
        # 密码错误，递增错误次数
        user.password_error_count += 1

        # 批量读取密码策略（单次 DB 查询 + 缓存，避免每次失败登录多次打 DB）
        pwd_policy = _get_pwd_policy_settings()
        max_retry_count = pwd_policy["pwd_set_max_retry_count"]
        lock_duration_seconds = pwd_policy["pwd_set_lock_duration"]

        # 如果错误次数达到或超过最大重试次数，锁定账号
        if user.password_error_count >= max_retry_count:
            user.account_locked_until = now + timedelta(seconds=lock_duration_seconds)
            user.save()
            lock_duration_minutes = int(lock_duration_seconds / 60) + 1
            return {
                "result": False,
                "message": loader.get(
                    "login.account_locked_too_many_attempts",
                    "Account locked due to too many failed attempts. Please try again after {minutes} minutes.",
                ).format(minutes=lock_duration_minutes),
            }

        user.save()
        remaining_attempts = max_retry_count - user.password_error_count
        return {
            "result": False,
            "message": loader.get(
                "login.incorrect_password_with_attempts",
                "Username or password is incorrect. {attempts} attempts remaining.",
            ).format(attempts=remaining_attempts),
        }

    # 密码正确，重置错误次数和锁定状态
    user.password_error_count = 0
    user.account_locked_until = None
    user.save()

    is_admin_account = user.username == "admin"

    # 检查密码过期
    password_expiry_reminder = ""
    if user.password_last_modified:
        # 批量读取密码策略（与密码错误路径共用同一缓存，无额外 DB 开销）
        pwd_policy = _get_pwd_policy_settings()
        validity_period_days = pwd_policy["pwd_set_validity_period"]

        # validity_period_days <= 0 表示永不过期，跳过过期检查
        if validity_period_days > 0:
            reminder_days = pwd_policy["pwd_set_expiry_reminder_days"]

            password_expire_date = user.password_last_modified + timedelta(days=validity_period_days)
            days_until_expire = (password_expire_date - now).days

            # 密码已过期，阻止登录
            if days_until_expire <= 0:
                if is_admin_account:
                    if not user.temporary_pwd:
                        user.temporary_pwd = True
                        user.save()
                else:
                    return {
                        "result": False,
                        "message": loader.get(
                            "login.password_expired_contact_admin",
                            "Your password has expired. Please contact the administrator to reset your password.",
                        ),
                    }

            # 密码快过期，生成提醒消息
            if days_until_expire <= reminder_days:
                password_expiry_reminder = loader.get(
                    "login.password_expiring_soon",
                    "Your password will expire in {days} day(s). Please change it soon.",
                ).format(days=days_until_expire)

    result = get_user_login_token(user, username, skip_token_for_otp=True)
    if result.get("result"):
        # Add password_expiry_reminder to response
        result["data"]["password_expiry_reminder"] = password_expiry_reminder
    return result


@nats_client.register
def reset_pwd(username, domain, password, caller_token=""):
    """
    重置用户密码（NATS接口）

    会进行密码复杂度校验，以及调用方身份校验——caller_token 必须是有效的
    JWT 会话 token，且 token 所属用户必须与 username 一致（自助改密），
    以阻止任意内网服务通过 NATS 总线篡改他人密码。
    """
    # 调用方身份校验：验证 caller_token 有效，且属于请求的同一用户
    if not caller_token:
        return {"result": False, "message": "caller_token is required"}
    try:
        caller = _verify_token(caller_token)
    except Exception:
        return {"result": False, "message": "Unauthorized: invalid token"}
    caller_domain = getattr(caller, "domain", "") or "domain.com"
    target_domain = domain or "domain.com"
    if caller.username != username or caller_domain != target_domain:
        return {"result": False, "message": "Unauthorized: caller does not match target user"}

    filter_kwargs = {"username": username}
    if domain:
        filter_kwargs["domain"] = domain
    user = User.objects.filter(**filter_kwargs).first()
    if not user:
        return {"result": False, "message": "Username not exists"}

    # 守卫:外部同步用户 + password 字段是 sentinel 标记 → 拒绝本地重置
    # sentinel 由 PasswordInitService 在 mode=none 时写入,格式 "!UNSET_PASSWORD:..."
    # (非合法 hash 格式 → Django check_password 永远 False,用户本地无法登录)
    if user.password.startswith("!UNSET_PASSWORD:"):
        loader = LanguageLoader(app="system_mgmt", default_lang=user.locale or "en")
        msg = loader.get(
            "login.external_sync_no_password",
            "外部同步用户未设置本地密码,无法在此修改",
        )
        return {"result": False, "message": msg}

    # 校验密码复杂度
    is_valid, error_message = PasswordValidator.validate_password(password)
    if not is_valid:
        return {"result": False, "message": error_message}

    user.password = make_password(password)
    user.temporary_pwd = False
    user.save()
    return {"result": True}


@nats_client.register
def bk_lite_user_login(username, domain):
    user = User.objects.filter(username=username, domain=domain).first()
    if not user:
        return {"result": False, "message": "Username or password is incorrect"}
    return get_user_login_token(user, username)


def get_user_login_token(user, username, skip_token_for_otp=False):
    """
    Get login token for user.

    Args:
        user: User object
        username: Username string
        skip_token_for_otp: If True and OTP is enabled, return challenge_id instead of token

    Returns:
        Dict with login result and data
    """
    if user.disabled:
        return {"result": False, "message": "User is disabled"}

    # Check if OTP is enabled globally
    enable_otp_setting = SystemSettings.objects.filter(key="enable_otp").first()
    enable_otp = enable_otp_setting and enable_otp_setting.value == "1"

    # Check if user has OTP configured (has otp_secret)
    user_has_otp = user.otp_secret is not None and user.otp_secret != ""

    # If OTP is enabled and we should use two-phase authentication
    if skip_token_for_otp and enable_otp:
        # Generate QR code for first-time OTP binding if user hasn't configured OTP yet
        qr_code_base64 = None
        if not user_has_otp:
            # Generate new OTP secret and QR code
            user.otp_secret = pyotp.random_base32()
            user.save()
            totp = pyotp.TOTP(user.otp_secret)
            provisioning_uri = totp.provisioning_uri(name=username, issuer_name="WeopsX")

            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(provisioning_uri)
            qr.make(fit=True)

            img = qr.make_image(fill_color="black", back_color="white")
            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            qr_code_base64 = base64.b64encode(buffer.getvalue()).decode()

        challenge_id = create_challenge(user.id, username)
        response_data = {
            "require_otp": True,
            "challenge_id": challenge_id,
            "username": username,
            "display_name": user.display_name,
            "id": user.id,
            "user_id": user.user_id,
            "domain": user.domain,
            "locale": user.locale,
            "timezone": user.timezone,
            "temporary_pwd": user.temporary_pwd,
        }

        # Include QR code for first-time binding
        if qr_code_base64:
            response_data["qr_code"] = qr_code_base64
            response_data["need_binding"] = True  # Flag to indicate first-time binding

        return {
            "result": True,
            "data": response_data,
        }

    # Normal flow (OTP disabled): issue JWT token
    secret_key = os.getenv("SECRET_KEY")
    algorithm = os.getenv("JWT_ALGORITHM", "HS256")
    user_obj = _build_jwt_payload(user.id)
    token = jwt.encode(payload=user_obj, key=secret_key, algorithm=algorithm)
    user.last_login = timezone.now()
    user.save()

    return {
        "result": True,
        "data": {
            "token": token,
            "username": username,
            "display_name": user.display_name,
            "id": user.id,
            "user_id": user.user_id,
            "domain": user.domain,
            "locale": user.locale,
            "timezone": user.timezone,
            "temporary_pwd": user.temporary_pwd,
            "enable_otp": enable_otp,
            "qrcode": user.otp_secret is None or user.otp_secret == "",
        },
    }

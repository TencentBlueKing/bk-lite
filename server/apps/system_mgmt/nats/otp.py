# flake8: noqa
from .common import *  # noqa: F401,F403
from .common import _build_jwt_payload, _get_pwd_policy_settings


@nats_client.register
def generate_qr_code_by_user_id(user_id):
    """
    Generate OTP QR code for a user by user_id.

    This is the secure version that requires authentication.
    The user_id comes from the authenticated session.
    """
    user = User.objects.filter(id=user_id).first()
    if not user:
        return {"result": False, "message": "User not found"}

    user.otp_secret = pyotp.random_base32()
    user.save()
    totp = pyotp.TOTP(user.otp_secret)
    # 创建用于Authenticator应用的配置URL
    provisioning_uri = totp.provisioning_uri(name=user.username, issuer_name="WeopsX")

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

    return {"result": True, "data": {"qr_code": qr_code_base64}}


@nats_client.register
def verify_otp_code(username, otp_code, client_ip=""):
    """
    Verify OTP code for a user by username.

    Requires client_ip for rate limiting. Falls back to empty string when not
    provided (legacy callers), but rate limiting is still applied per IP+username.
    """
    # Check rate limit before any DB lookup
    is_limited, remaining = check_rate_limit(client_ip, username)
    if is_limited:
        return {"result": False, "message": "Too many failed attempts. Please try again later."}

    user = User.objects.filter(username=username).first()
    if not user:
        return {"result": False, "message": "User not found"}

    if not user.otp_secret:
        return {"result": False, "message": "OTP not configured for this user"}

    totp = pyotp.TOTP(user.otp_secret)
    if totp.verify(otp_code):
        reset_rate_limit(client_ip, username)
        return {"result": True, "message": "Verification successful"}

    record_failed_attempt(client_ip, username)
    return {"result": False, "message": "Invalid OTP code"}


@nats_client.register
def verify_otp_code_by_user_id(user_id, otp_code):
    """
    Verify OTP code for a user by user_id.

    This is the secure version that requires authentication.
    The user_id comes from the authenticated session.
    """
    user = User.objects.filter(id=user_id).first()
    if not user:
        return {"result": False, "message": "User not found"}

    if not user.otp_secret:
        return {"result": False, "message": "OTP not configured for this user"}

    totp = pyotp.TOTP(user.otp_secret)
    if totp.verify(otp_code):
        return {"result": True, "message": "Verification successful"}
    return {"result": False, "message": "Invalid OTP code"}


@nats_client.register
def verify_otp_login(challenge_id, otp_code, client_ip=""):
    """
    Verify OTP code with challenge_id and issue JWT token.

    This is the second phase of two-factor authentication.
    The challenge_id was obtained from the first phase (password verification).

    Args:
        challenge_id: The challenge ID from password verification
        otp_code: The OTP code from user's authenticator app
        client_ip: Client IP for rate limiting

    Returns:
        Dict with login result and JWT token if successful
    """
    # Verify challenge exists and is valid
    challenge_data = verify_challenge(challenge_id)
    if not challenge_data:
        return {"result": False, "message": "Invalid or expired challenge. Please login again."}

    username = challenge_data.get("username")
    user_id = challenge_data.get("user_id")

    # Check rate limit
    is_limited, remaining = check_rate_limit(client_ip, username)
    if is_limited:
        return {"result": False, "message": "Too many failed attempts. Please try again later."}

    # Get user
    user = User.objects.filter(id=user_id).first()
    if not user:
        return {"result": False, "message": "User not found"}

    if not user.otp_secret:
        return {"result": False, "message": "OTP not configured for this user"}

    # Verify OTP code
    totp = pyotp.TOTP(user.otp_secret)
    if not totp.verify(otp_code):
        record_failed_attempt(client_ip, username)
        return {"result": False, "message": "Invalid OTP code"}

    # OTP verified successfully
    # Invalidate challenge (one-time use)
    invalidate_challenge(challenge_id)

    # Reset rate limit
    reset_rate_limit(client_ip, username)

    # Issue JWT token
    secret_key = os.getenv("SECRET_KEY")
    algorithm = os.getenv("JWT_ALGORITHM", "HS256")
    user_obj = _build_jwt_payload(user.id)
    token = jwt.encode(payload=user_obj, key=secret_key, algorithm=algorithm)

    user.last_login = timezone.now()
    user.save()

    # Check password expiry reminder (expired users already blocked in login phase)
    password_expiry_reminder = ""
    if user.password_last_modified:
        # Initialize language loader for user's locale
        loader = LanguageLoader(app="system_mgmt", default_lang=user.locale or "en")

        # 批量读取密码策略（单次 DB 查询 + 缓存，复用与 login() 相同的缓存键）
        pwd_policy = _get_pwd_policy_settings()
        validity_period_days = pwd_policy["pwd_set_validity_period"]

        # validity_period_days <= 0 表示永不过期，跳过过期检查
        if validity_period_days > 0:
            reminder_days = pwd_policy["pwd_set_expiry_reminder_days"]

            now = timezone.now()
            password_expire_date = user.password_last_modified + timedelta(days=validity_period_days)
            days_until_expire = (password_expire_date - now).days

            if 0 < days_until_expire <= reminder_days:
                password_expiry_reminder = loader.get(
                    "login.password_expiring_soon",
                    "Your password will expire in {days} day(s). Please change it soon.",
                ).format(days=days_until_expire)

    return {
        "result": True,
        "data": {
            "token": token,
            "username": username,
            "display_name": user.display_name,
            "id": user.id,
            "domain": user.domain,
            "locale": user.locale,
            "timezone": user.timezone,
            "temporary_pwd": user.temporary_pwd,
            "password_expiry_reminder": password_expiry_reminder,
        },
    }

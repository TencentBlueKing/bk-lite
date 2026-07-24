import secrets

from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction

from apps.log.models import SystemVectorToken

_DUMMY_TOKEN_DIGEST = make_password(secrets.token_urlsafe(48))


def authenticate_system_vector_token(authorization: str | None) -> bool:
    if not authorization:
        return False
    scheme, separator, token = authorization.partition(" ")
    if not separator or scheme.lower() != "bearer" or not token or token != token.strip():
        return False
    stored = SystemVectorToken.objects.filter(scope="global").only("token_digest").first()
    matches = check_password(token, stored.token_digest if stored else _DUMMY_TOKEN_DIGEST)
    return bool(stored and matches)


def rotate_system_vector_token() -> str:
    plaintext = secrets.token_urlsafe(48)
    digest = make_password(plaintext)
    with transaction.atomic():
        SystemVectorToken.objects.update_or_create(scope="global", defaults={"token_digest": digest})
    return plaintext

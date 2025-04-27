import os

from loguru import logger

from src.core.web.crypto import PasswordCrypto


def test_decrypt():
    crypto = PasswordCrypto(os.getenv("SECRET_KEY"))
    rs = crypto.encrypt(os.getenv("ADMIN_PASSWORD"))
    logger.info(rs)
    result = crypto.decrypt(rs)
    logger.info(result)

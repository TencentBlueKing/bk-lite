import requests

from apps.core.logger import logger


def get_bk_user_info(bk_token, app_id, app_token, bk_url):
    params = {"bk_app_code": app_id, "bk_app_secret": app_token, "bk_token": bk_token}
    url = f"{bk_url.rstrip('/')}/api/c/compapi/v2/bk_login/get_user/"
    try:
        res = requests.get(url, params=params, timeout=5).json()
    except Exception:
        logger.exception("Abnormal error in verify_bk_token...")
        return False, None

    if not res.get("result"):
        logger.exception("验证失败:{}".format(res.get("message")))
        return False, None
    bk_username = res.get("data").get("bk_username")
    user_detail_url = f"{bk_url.rstrip('/')}/api/c/compapi/v2/usermanage/retrieve_user/"
    detail_params = dict(params, **{"id": bk_username, "fields": "username,domain,display_name,email,language,time_zone"})
    try:
        res = requests.get(user_detail_url, params=detail_params, timeout=5).json()
    except Exception:
        logger.exception("Abnormal error in get_user_info...:")
        return False, None
    if not res.get("result"):
        logger.exception("验证失败:{}".format(res.get("message")))
        return False, {}
    return True, res["data"]

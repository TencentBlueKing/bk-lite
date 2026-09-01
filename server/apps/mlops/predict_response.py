from rest_framework import status

PREDICT_INPUT_ERROR_STATUSES = frozenset(
    {
        status.HTTP_400_BAD_REQUEST,
        status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        status.HTTP_422_UNPROCESSABLE_ENTITY,
    }
)


def map_predict_upstream_status(status_code: int) -> int:
    """保留算法侧已登记的输入错误，其余上游异常继续收敛为 500。"""
    if status_code in PREDICT_INPUT_ERROR_STATUSES:
        return status_code
    return status.HTTP_500_INTERNAL_SERVER_ERROR

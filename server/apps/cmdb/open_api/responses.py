from django.http import JsonResponse


def open_api_success(data=None, *, status_code=200):
    return JsonResponse(
        {"result": True, "data": data if data is not None else {}, "message": "", "code": "ok"},
        status=status_code,
    )


def open_api_error(error):
    return JsonResponse(
        {"result": False, "data": error.data, "message": error.message, "code": error.code},
        status=error.status_code,
    )

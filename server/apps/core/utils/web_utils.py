import io

from django.http import FileResponse, JsonResponse
from rest_framework import status


class WebUtils:
    @staticmethod
    def response_success(response_data={}, message=""):
        return JsonResponse({"data": response_data, "result": True, "message": message}, status=status.HTTP_200_OK)

    @staticmethod
    def response_error(response_data={}, error_message="", status_code=status.HTTP_400_BAD_REQUEST):
        # 兼容 response_error("文案", status_code=404)：首位是 str 时视为 message，而不是 data。
        if isinstance(response_data, str) and not error_message:
            error_message = response_data
            response_data = {}
        return JsonResponse({"data": response_data, "result": False, "message": error_message}, status=status_code)

    @staticmethod
    def response_401(message):
        return JsonResponse({"result": False, "message": message}, status=status.HTTP_401_UNAUTHORIZED)

    @staticmethod
    def response_403(message):
        return JsonResponse({"result": False, "message": message}, status=status.HTTP_403_FORBIDDEN)

    @staticmethod
    def response_file(file, filename):
        if isinstance(file, bytes):
            file = io.BytesIO(file)
        response = FileResponse(file, content_type="application/octet-stream")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

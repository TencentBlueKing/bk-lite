from django.utils.deprecation import MiddlewareMixin

from apps.core.services.gm_transport import (
    API_PREFIX,
    TransportFailure,
    error_response,
    install_plaintext,
    is_public_path,
    log_client_failure,
    log_unexpected,
    open_request,
    seal_response,
    unexpected_response,
)


class GmTransportMiddleware(MiddlewareMixin):
    """带 X-Gm-Transport: 1 时解开信封，并加密响应。不读开关。"""

    def process_request(self, request):
        if not request.path.startswith(f"{API_PREFIX}/"):
            return None
        if is_public_path(request.path):
            return None
        if request.META.get("HTTP_X_GM_TRANSPORT") != "1":
            return None
        try:
            opened = open_request(request)
        except Exception as exc:
            log_unexpected(request, exc, "open_request")
            return unexpected_response(request)
        if isinstance(opened, TransportFailure):
            log_client_failure(request, opened)
            return error_response(request, opened.code, opened.status)
        try:
            install_plaintext(request, opened)
        except Exception as exc:
            log_unexpected(request, exc, "install_plaintext")
            return unexpected_response(request)
        return None

    def process_response(self, request, response):
        try:
            return seal_response(request, response)
        except Exception as exc:
            log_unexpected(request, exc, "seal_response")
            return unexpected_response(request)

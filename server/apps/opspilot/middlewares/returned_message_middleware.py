# -*- coding: utf-8 -*-
"""把 OpsPilot 已收录的接口错误句换成当前页面语言。"""

from apps.opspilot.utils.returned_messages import translate_response_body


class ReturnedMessageLocaleMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        translate_response_body(response, request)
        return response

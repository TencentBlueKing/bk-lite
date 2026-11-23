class ExampleChannelSendAdapter:
    """模板类示例。具名参数，不向外部投递。"""

    @classmethod
    def send(cls, config, phone, template_params):
        if not isinstance(template_params, dict) or not str(template_params.get("code") or "").strip():
            return {"status": "rejected", "request_id": "", "reason": "缺少参数 code"}
        if not str(phone or "").strip():
            return {"status": "rejected", "request_id": "", "reason": "缺少电话"}
        return {"status": "rejected", "request_id": "", "reason": "示例包不向外部投递"}


# 正文类写法。不要和上面的模板类同时启用。
# 把 manifest 的 delivery 改成 "body"，并删掉 parameter_mode。
# 收件地址放在 config 里，例如 webhook_url。send 收不到接收人和 template_params。
#
# class ExampleBodySendAdapter:
#     @classmethod
#     def send(cls, config, title, content):
#         if not isinstance(title, str) or not isinstance(content, str) or not content.strip():
#             return {"status": "rejected", "request_id": "", "reason": "缺少正文"}
#         return {"status": "rejected", "request_id": "", "reason": "示例包不向外部投递"}

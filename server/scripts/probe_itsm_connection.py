#!/usr/bin/env python
"""使用已保存的团队配置进行真实、只读的 ITSM 连接测试。

在 server 目录运行：python scripts/probe_itsm_connection.py --team-id 1
复用页面测试客户端；不创建工单、不更改配置、不关闭 TLS/SSRF 校验。
仅输出请求地址、HTTP 状态和受控诊断，不输出令牌、证书或响应正文。
退出码：0 连接测试成功；1 调用失败；2 无法读取配置或执行测试。
"""

import argparse
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import requests
from dotenv import load_dotenv


def probe(instance):
    from apps.alerts.itsm.client import ItsmClient
    from apps.alerts.itsm.config import ItsmError

    connection = instance.connection_config()
    report = {
        "team_id": instance.team_id,
        "integration_id": instance.pk,
        "authentication": "Bearer (saved credential)",
        "certificate": "saved CA PEM" if connection.get("ca_pem") else "default trust store",
        "tls_verification": True,
        "method": "GET",
        "request_url": None,
        "http_status": None,
        "is_404": None,
        "success": False,
    }
    real_send = requests.Session.send

    def observe_send(session, request, **kwargs):
        # 只观察真实 HTTP 调用；不替换响应、不修改认证、证书或目标。
        report["request_url"] = request.url
        response = real_send(session, request, **kwargs)
        report["http_status"] = response.status_code
        report["is_404"] = response.status_code == 404
        return response

    try:
        with patch.object(requests.Session, "send", observe_send):
            ItsmClient(connection, allow_disabled=True).test_connection()
    except ItsmError as exc:
        report["diagnosis"] = str(exc)  # 客户端定义的受控文案，无远端正文。
        report["outcome"] = exc.outcome
    else:
        report["success"] = True
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--team-id", required=True, type=int)
    args = parser.parse_args()
    server_dir = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(server_dir))
    load_dotenv(server_dir / ".env")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")
    try:
        import django

        django.setup()
        from apps.alerts.models.itsm import AlertItsmIntegration

        instance = AlertItsmIntegration.objects.filter(team_id=args.team_id).first()
        if instance is None:
            print(json.dumps({"success": False, "diagnosis": "该团队没有已保存的 ITSM 集成"}, ensure_ascii=False))
            return 2
        report = probe(instance)
    except Exception as exc:
        # 数据库/初始化异常可能携带连接秘密，仅报告异常类型。
        print(json.dumps({"success": False, "error_type": type(exc).__name__, "diagnosis": "无法读取配置或完成探测"}, ensure_ascii=False))
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["success"] else 1


if __name__ == "__main__":
    sys.exit(main())

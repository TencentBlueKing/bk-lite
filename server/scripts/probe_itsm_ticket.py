#!/usr/bin/env python
"""使用已保存的团队集成创建一张真实工单并查询详情。

在 server 目录运行：
python scripts/probe_itsm_ticket.py --team-id 1
默认流程 20261012164700000901，只提交标题。
输出工单 ID、单号、状态和 end_at 是否为空。不打印令牌、证书或响应正文。
退出码：0 建单并查到详情；1 调用失败；2 无法读取配置。
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import requests
from dotenv import load_dotenv

WORKFLOW = "20261012164700000901"


def probe(instance, workflow_key, title):
    from apps.alerts.itsm.client import ItsmClient
    from apps.alerts.itsm.config import ItsmError

    report = {
        "team_id": instance.team_id,
        "workflow_key": workflow_key,
        "success": False,
        "ticket_id": None,
        "ticket_number": None,
        "ticket_status": None,
        "end_at_empty": None,
    }
    client = ItsmClient(instance.connection_config())
    observed = {"http_status": None, "code": None}
    real_send = requests.Session.send

    def observe_send(session, request, **kwargs):
        response = real_send(session, request, **kwargs)
        observed["http_status"] = response.status_code
        try:
            payload = json.loads(response.content)
        except (ValueError, TypeError):
            payload = None
        if isinstance(payload, dict):
            observed["code"] = payload.get("code")
            text = payload.get("message") or payload.get("msg") or payload.get("detail")
            if isinstance(text, str) and len(text) <= 200 and "token" not in text.lower() and "bearer" not in text.lower():
                observed["message"] = text
        return response

    try:
        with patch.object(requests.Session, "send", observe_send):
            ticket_id = client.create(workflow_key, {"ticket__title": title})
            detail = client.detail(ticket_id)
    except ItsmError as exc:
        report["diagnosis"] = str(exc)
        report["outcome"] = exc.outcome
        report["http_status"] = observed["http_status"]
        report["code"] = observed["code"]
        if observed.get("message"):
            report["message"] = observed["message"]
        return report
    report.update(
        {
            "success": True,
            "ticket_id": detail["ticket_id"],
            "ticket_number": detail["ticket_number"],
            "ticket_status": detail["ticket_status"],
            "status_label": detail["status_label"],
            "end_at_empty": not detail["is_closed"],
        }
    )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--team-id", type=int)
    parser.add_argument("--workflow-key", default=WORKFLOW)
    args = parser.parse_args()
    server_dir = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(server_dir))
    load_dotenv(server_dir / ".env")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")
    try:
        import django

        django.setup()
        from apps.alerts.models.itsm import AlertItsmIntegration

        queryset = AlertItsmIntegration.objects.filter(enabled=True)
        if args.team_id is not None:
            queryset = queryset.filter(team_id=args.team_id)
        instances = list(queryset.order_by("team_id"))
        if len(instances) != 1:
            print(
                json.dumps(
                    {
                        "success": False,
                        "diagnosis": "需要唯一已启用的 ITSM 集成",
                        "team_ids": [item.team_id for item in instances],
                    },
                    ensure_ascii=False,
                )
            )
            return 2
        title = "告警中心真实建单验证 " + datetime.now().strftime("%Y-%m-%d %H:%M")
        report = probe(instances[0], args.workflow_key, title)
    except Exception as exc:
        print(json.dumps({"success": False, "error_type": type(exc).__name__, "diagnosis": "无法读取配置或完成建单"}, ensure_ascii=False))
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["success"] else 1


if __name__ == "__main__":
    sys.exit(main())

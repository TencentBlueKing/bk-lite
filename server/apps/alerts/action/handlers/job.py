import logging
from django.conf import settings
from apps.rpc.job_mgmt import JobMgmt
from apps.alerts.action.handlers.base import ActionHandler
from apps.alerts.action.payload import build_match_payload, resolve_field
from apps.alerts.action.resolver import resolve_params
from apps.alerts.action.target_resolver import resolve_node_target
from apps.alerts.action.exceptions import ConfigError

logger = logging.getLogger(__name__)


class JobActionHandler(ActionHandler):
    action_type = "job"

    def execute(self, rule, alert, execution):
        cfg = rule.action_config or {}
        try:
            script = JobMgmt().get_script(cfg.get("script_id"))
            if not script:
                return self._config_error(execution, "作业不存在")

            payload = build_match_payload(alert)
            binding = cfg.get("target_binding", {})
            host_value = resolve_field(payload, binding.get("host_field", "labels.ip"))
            target = resolve_node_target(host_value, rule.team)

            params = resolve_params(payload, cfg.get("param_bindings", []), script.get("params", []))

            data = {
                "name": f"告警动作-{rule.name}-{alert.alert_id}",
                "target_source": "node_mgmt",
                "target_list": [target],
                "script_type": script["script_type"],
                "script_content": script["content"],
                "params": params,
                "timeout": cfg.get("timeout") or script.get("timeout", 600),
                "team": list(rule.team or []),
                "callback_url": self._callback_url(),
            }
            resp = JobMgmt().job_script_execute(data) or {}
            if not resp.get("result"):
                execution.status = "failed"
                execution.result = {"message": resp.get("message", "作业触发失败")}
                execution.save()
                return
            task_id = resp["data"]["task_id"]
            execution.job_task_id = task_id
            execution.job_detail_url = self._job_url(task_id)
            execution.status = "running"
            execution.save()
        except ConfigError as e:
            self._config_error(execution, str(e))
        except Exception as e:
            logger.exception("[ActionEngine] job handler 异常")
            execution.status = "failed"
            execution.result = {"message": str(e)}
            execution.save()

    def _config_error(self, execution, msg):
        execution.status = "config_error"
        execution.result = {"message": msg}
        execution.save()

    def _callback_url(self):
        base = getattr(settings, "SELF_BASE_URL", "").rstrip("/")
        return f"{base}/api/v1/alerts/api/action_callback/" if base else "/api/v1/alerts/api/action_callback/"

    def _job_url(self, task_id):
        base = getattr(settings, "WEB_BASE_URL", "").rstrip("/")
        return f"{base}/job/execution/{task_id}" if base else f"/job/execution/{task_id}"

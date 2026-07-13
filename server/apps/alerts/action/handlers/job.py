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
            # mode: from_alert(默认，保留旧行为) | fixed（用规则内写死的 ip，不读 alert）
            mode = (binding.get("mode") or "from_alert").strip().lower()
            resolved_source_ip: str = ""
            if mode == "fixed":
                fixed_ip = (binding.get("ip") or "").strip()
                if not fixed_ip:
                    # ConfigError 会被下方 except ConfigError 捕获并写 status=config_error
                    raise ConfigError("target_binding.mode='fixed' 时必须填写 ip")
                target = resolve_node_target(fixed_ip, rule.team)
                resolved_source_ip = fixed_ip
            else:
                # mode 缺失或显式 from_alert：维持旧行为。
                # 目标主机字段默认从告警 labels 里取：前端只写裸字段名(默认 ip_addr)，
                # 这里补上 labels. 前缀；若已写成带点的完整路径(如 enrichment.x)则按原样解析。
                host_field = (binding.get("host_field") or "ip_addr").strip()
                lookup_key = host_field if "." in host_field else f"labels.{host_field}"
                host_value = resolve_field(payload, lookup_key)
                target = resolve_node_target(host_value, rule.team)
                resolved_source_ip = str(host_value) if host_value else ""

            # 记录本次执行实际命中的主机 IP，便于前端"动作记录"展示与排错。
            # 注意：成功后会再覆盖（extras），失败/异常时只有 result 字段被改写为 message。
            execution.result = {
                "target_ip": str(target.get("ip") or resolved_source_ip or ""),
                "mode": mode,
            }

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
                # 失败时也要保留 target_ip / mode，便于前端"动作记录"展示当时试图触发哪个主机。
                execution.result = {
                    **execution.result,
                    "message": resp.get("message", "作业触发失败"),
                }
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
        """构造作业平台完成后的回调 URL；空时返回 None，不传 callback 字段。

        SELF_BASE_URL 必须是对 job_mgmt 网络可达的入口；不允许默认到 localhost，
        因为 job_mgmt 的 SSRFValidator 会拦截 loopback。
        """
        base = (getattr(settings, "SELF_BASE_URL", "") or "").rstrip("/")
        if not base:
            logger.warning(
                "[ActionEngine] SELF_BASE_URL 未设置 — 告警触发作业后将无法回调，"
                "ActionExecution.status 会停在 running 而不会自动变为 success/failed。"
                "请在 .env 里显式配置，比如 SELF_BASE_URL=http://10.0.0.1:8011"
            )
            return None
        return f"{base}/api/v1/alerts/api/action_callback/"

    def _job_url(self, task_id):
        """前端"查看作业"链接：task_id 走 query 参数（前端路由 /job/execution/job-record）。"""
        base = (getattr(settings, "WEB_BASE_URL", "") or "").rstrip("/")
        return f"{base}/job/execution/job-record?id={task_id}" if base else f"/job/execution/job-record?id={task_id}"

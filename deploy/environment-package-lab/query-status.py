import django,json
from pathlib import Path
from django.core.serializers.json import DjangoJSONEncoder
django.setup()
from apps.log.models.policy import Alert,Event,AlertSnapshot
from apps.apm.models import ApmAlert,ApmEvent,ApmAlertOutbox
r={'log_alerts':list(Alert.objects.filter(policy__name='C/D 日志错误验证').values('id','status','notice','source_id','value')),'log_events':list(Event.objects.filter(policy__name='C/D 日志错误验证').values('id','alert_id','action','notified','notice_retry_count','notice_result')),'apm_alerts':list(ApmAlert.objects.filter(service_namespace='cd-query-validation').values('id','service_name','status','current_value')),'apm_events':list(ApmEvent.objects.filter(alert__service_namespace='cd-query-validation').values('id','alert_id','action','value')),'outbox':list(ApmAlertOutbox.objects.filter(event__alert__service_namespace='cd-query-validation').values('event_id','delivery_status','attempts','last_error_code','last_error_message'))}
print(json.dumps(r,cls=DjangoJSONEncoder,ensure_ascii=False,indent=2))
Path('/test/evidence/query-alert-20261115/latest-status.json').write_text(json.dumps(r,cls=DjangoJSONEncoder,ensure_ascii=False,indent=2))

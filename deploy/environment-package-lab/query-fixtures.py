"""Declarative owned query/alert fixtures; never manufacture telemetry or alerts."""
import django,json,sys
from pathlib import Path
from django.utils import timezone
from query_run import enable_log_policy_for_run
django.setup()
from apps.node_mgmt.models import CloudRegion
from apps.system_mgmt.models.channel import Channel
from apps.log.models.log_group import LogGroup,LogGroupOrganization
from apps.log.models.policy import Policy,PolicyOrganization
from apps.log.utils.log_group import LogGroupQueryBuilder
from apps.apm.models import ApmApplication,ApmApplicationOrganization,ApmService,ApmPolicy,ApmPolicyOrganization,ApmPolicyNotificationTarget
from django_celery_beat.models import PeriodicTask,IntervalSchedule
assert CloudRegion.objects.get(pk=2).name=='Auto Executor validation 20261114'
out=Path('/test/evidence/query-alert-20261115');out.mkdir(exist_ok=True)
app,_=ApmApplication.objects.get_or_create(application_id='cd-query-validation',defaults={'name':'C/D 查询告警验证','description':'isolated C/D real telemetry'})
ApmApplicationOrganization.objects.get_or_create(application=app,organization=1)
rule={'mode':'OR','conditions':[{'field':'node_ip','op':'==','value':ip} for ip in ['192.168.122.4','192.168.122.209']]};LogGroupQueryBuilder.validate_rule(rule)
group,_=LogGroup.objects.update_or_create(id='cd-query-validation',defaults={'name':'C/D 实际日志','rule':rule,'description':'Only new isolated C/D VM data','created_by':'env-ui-admin'})
LogGroupOrganization.objects.get_or_create(log_group=group,organization=1)
channel,_=Channel.objects.update_or_create(name='C/D 隔离告警回执',defaults={'channel_type':'nats','team':[1],'description':'Local sink only; no external messages','config':{'namespace':'envquery','method_name':'receive_alert_events','timeout':5},'created_by':'env-ui-admin'})
if '--policies' in sys.argv:
 policy,_=enable_log_policy_for_run(Policy, {'alert_type':'aggregate','alert_name':'${node_ip} C/D日志错误','alert_level':'error','alert_condition':{'query':'verification:="CD-QUERY" AND level:="error"','group_by':['node_ip'],'rule':{'mode':'and','conditions':[{'func':'count','field':'_msg','op':'>','value':0}]}},'log_groups':[group.pk],'schedule':{'type':'min','value':1},'period':{'type':'min','value':1},'notice':True,'notice_type':'nats','notice_type_id':channel.pk,'notice_users':[],'enable':True,'created_by':'env-ui-admin'}, timezone.now())
 PolicyOrganization.objects.get_or_create(policy=policy,organization=1)
 interval,_=IntervalSchedule.objects.get_or_create(every=30,period='seconds')
 PeriodicTask.objects.update_or_create(name='log_policy_task_'+str(policy.pk),defaults={'task':'apps.log.tasks.policy.scan_log_policy_task','args':json.dumps([policy.pk]),'interval':interval,'crontab':None,'enabled':True})
 services=list(ApmService.objects.filter(application=app));assert len(services)==2,'Wait for real telemetry discovery'
 ids=[]
 for service in services:
  p,_=ApmPolicy.objects.update_or_create(name='C/D 延迟验证 '+service.name,defaults={'service':service,'environment':'isolated','metric_type':'p95','metric_window':1,'evaluation_interval':1,'aggregation':'max','thresholds':[{'severity':'error','comparator':'gt','value':'100'}],'trigger_after':1,'recover_after':1,'is_enabled':True})
  ApmPolicyOrganization.objects.get_or_create(policy=p,organization=1)
  ApmPolicyNotificationTarget.objects.update_or_create(policy=p,channel_id=channel.pk,defaults={'channel_name':channel.name,'channel_type':'nats','delivery_mode':'alert_event_copy','recipient_mode':'none','recipients':[]});ids.append(str(p.pk))
 (out/'policy-ids.json').write_text(json.dumps({'log_policy':policy.pk,'apm_policies':ids,'channel_id':channel.pk},indent=2))
print('__QUERY_FIXTURES_RECONCILED__')

if '--disable' in sys.argv:
 owned=Policy.objects.filter(name='C/D 日志错误验证');ids=list(owned.values_list('pk',flat=True));owned.update(enable=False)
 PeriodicTask.objects.filter(name__in=['log_policy_task_'+str(x) for x in ids]).update(enabled=False)
 ApmPolicy.objects.filter(service__application=app,name__startswith='C/D 延迟验证 ').update(is_enabled=False)
 print('__OWNED_TEST_POLICIES_DISABLED__')

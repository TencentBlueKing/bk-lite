"""Read back actual Victoria storage and Ansible terminal results, fail closed."""
import json,time,sys
from pathlib import Path
import requests,django
django.setup()
from apps.node_mgmt.models import Node
from apps.rpc.ansible import AnsibleExecutor
out=Path('/test/evidence/business-20261115');phase=sys.argv[1];assert phase in ['after','repeat','recovery','persisted']
source='after' if phase=='persisted' else phase
injected=json.loads((out/(source+'-injected.json')).read_text());results=[]
for item in injected:
 marker=item['marker'];trace=item['trace_id'];deadline=time.monotonic()+60;logs=[];traces=None
 while time.monotonic()<deadline:
  r=requests.post('http://env-business-20261115-logs:9428/select/logsql/query',data={'query':'_msg:="'+marker+'"','limit':10},timeout=5);r.raise_for_status();logs=[json.loads(s) for s in r.text.splitlines() if s.strip()]
  r=requests.get('http://env-business-20261115-traces:10428/select/jaeger/api/traces/'+trace,timeout=5)
  if r.status_code==200:traces=r.json()
  if logs and traces and traces.get('data'):break
  time.sleep(2)
 entry={'ip':item['ip'],'marker':marker,'trace_id':trace,'logs':logs,'traces':traces};results.append(entry)
 (out/(phase+'-storage.json')).write_text(json.dumps(results,indent=2))
 assert logs and any(x.get('_msg')==marker for x in logs),('log-not-persisted',item['ip'])
 assert all(x['node_ip']==item['ip'] for x in logs),('wrong-log-node',item['ip'])
 assert traces and traces.get('data'),('trace-not-persisted',item['ip'])
 assert marker in json.dumps(traces) and trace in json.dumps(traces),('trace-mismatch',item['ip'])
 assert traces['data'][0]['traceID']==trace and traces['data'][0]['spans'][0]['spanID']=='1234567890abcdef'
 assert any(t['key']=='bk.cloud_region.id' and t['value']=='2' for p in traces['data'][0]['processes'].values() for t in p['tags'])
 print('STORAGE_OK',item['ip'],trace,flush=True)
if phase=='persisted':print('__PERSISTENT_STORAGE_READBACK_OK__');sys.exit(0)
nodes=list(Node.objects.filter(cloud_region_id=2));jobs=[]
for n in nodes:
 for number in range(2):
  task='business-'+phase+'-'+n.id[:8]+'-'+str(int(time.time()))+'-'+str(number)
  ex=AnsibleExecutor(n.id)
  accepted=ex.adhoc(inventory_content='[targets]\nlocalhost ansible_connection=local ansible_python_interpreter=/usr/bin/python3\n',hosts='targets',module='ansible.builtin.command',module_args='/bin/hostname',task_id=task,timeout=30)
  jobs.append({'node_id':n.id,'ip':n.ip,'expected_hostname':next(x['hostname'] for x in injected if x['ip']==n.ip),'task_id':task,'accepted':accepted})
  print('JOB_SUBMITTED',n.ip,task,flush=True)
deadline=time.monotonic()+90
while time.monotonic()<deadline:
 for job in jobs:
  if job.get('result',{}).get('status') not in ['success','failed','cancelled']:
   job['result']=AnsibleExecutor(job['node_id']).task_query(job['task_id'])
 if all(j.get('result',{}).get('status') in ['success','failed','cancelled'] for j in jobs):break
 time.sleep(2)
(out/(phase+'-ansible.json')).write_text(json.dumps(jobs,indent=2))
for j in jobs:
 r=j['result'];assert r.get('status')=='success',('ansible-not-success',j['ip'],r)
 assert r['result']['owner_id'].startswith(j['node_id']+'-'),('wrong-owner',j['ip'])
 hosts=r['result']['result'];assert hosts and all(h['exit_code']==0 and h['stdout'].strip()==j['expected_hostname'] for h in hosts),('wrong-execution-node',j['ip'],r)
 print('ANSIBLE_OK',j['ip'],j['task_id'],flush=True)
print('__BUSINESS_STORAGE_AND_ANSIBLE_VERIFIED__')

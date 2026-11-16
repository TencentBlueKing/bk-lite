"""Bounded outage test of the new isolated system APM consumer only."""
import subprocess,json,time
from pathlib import Path
root=Path('/opt/bklite-environment-test-20261113');out=root/'evidence/business-20261115';api='env-install-ca-api-20261113';target='env-business-20261115-apm'
def state():
 r=subprocess.run(['docker','exec',api,'python','/test/runtime/business/stream_state.py'],capture_output=True,text=True,check=True)
 return json.loads(next(line for line in r.stdout.splitlines() if line.startswith('{')))
before=state();assert before['pending']==0 and before['ack_pending']==0,before
try:
 subprocess.run(['docker','stop',target],check=True,stdout=subprocess.DEVNULL)
 subprocess.run(['python3',str(root/'runtime/business/inject.py'),'recovery'],check=True,stdout=subprocess.DEVNULL)
 deadline=time.monotonic()+30
 while time.monotonic()<deadline:
  paused=state()
  if paused['pending']>=2:break
  time.sleep(1)
 assert paused['storage']=='file' and paused['pending']>=2,paused
finally:
 subprocess.run(['docker','start',target],check=True,stdout=subprocess.DEVNULL)
r=subprocess.run(['docker','exec',api,'python','/test/runtime/business/verify.py','recovery'],capture_output=True,text=True,check=True)
assert '__BUSINESS_STORAGE_AND_ANSIBLE_VERIFIED__' in r.stdout
for _ in range(10):
 after=state()
 if after['pending']==0 and after['ack_pending']==0:break
 time.sleep(1)
assert after['pending']==0 and after['ack_pending']==0,after
(out/'trace-consumer-recovery.json').write_text(json.dumps({'before':before,'consumer_stopped':paused,'recovered':after},indent=2));print('__TRACE_FILE_QUEUE_RECOVERY_AND_BUSINESS_VERIFIED__')

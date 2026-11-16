"""Synthetic clients of the unchanged VM Logstash/OTLP listeners; not config fixes."""
import concurrent.futures,json,subprocess,sys,time
from pathlib import Path
phase=sys.argv[1];assert phase in ['before','after','repeat','recovery']
root=Path('/opt/bklite-environment-test-20261113');out=root/'evidence/business-20261115';out.mkdir(exist_ok=True)
run_id='BUSINESS-'+phase+'-'+str(int(time.time()))
script=r'''
import socket,struct,json,urllib.request,time,hashlib
marker=RUN_ID+'-'+socket.gethostname();result={'marker':marker,'hostname':socket.gethostname()}
payload=json.dumps({'message':marker,'verification':RUN_ID}).encode()
try:
 with socket.create_connection(('127.0.0.1',15044),timeout=8) as s:
  s.sendall(b'2W'+struct.pack('!I',1)+b'2J'+struct.pack('!II',1,len(payload))+payload)
  result['log_ack']=s.recv(6).hex()
except Exception as e:result['log_error']=type(e).__name__
now=time.time_ns();trace=hashlib.sha256(marker.encode()).hexdigest()[:32];result['trace_id']=trace
body={'resourceSpans':[{'resource':{'attributes':[{'key':'service.name','value':{'stringValue':marker}}]},'scopeSpans':[{'scope':{'name':'environment-package-e2e'},'spans':[{'traceId':trace,'spanId':'1234567890abcdef','name':marker,'kind':1,'startTimeUnixNano':str(now),'endTimeUnixNano':str(now+1000000),'status':{'code':1}}]}]}]}
try:
 r=urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:4318/v1/traces',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'}),timeout=10)
 result['otlp_status']=r.status;result['otlp_response']=r.read().decode()
except Exception as e:result['otlp_error']=type(e).__name__
print(json.dumps(result))
'''
def inject(ip):
 r=subprocess.run(['ssh','-T','root@'+ip,'python3 -'],input='RUN_ID='+repr(run_id)+'\n'+script,text=True,capture_output=True,timeout=30,check=True)
 data=json.loads(r.stdout);data['ip']=ip;return data
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(inject,['192.168.122.4','192.168.122.209']))
(out/(phase+'-injected.json')).write_text(json.dumps(results,indent=2));print(json.dumps(results));print('__TELEMETRY_INJECTED__')

"""Send real C/D traffic to their default listeners, with application identity."""
import subprocess,json,sys,time,concurrent.futures
from pathlib import Path
phase=sys.argv[1];assert phase in ['baseline','alarm','recovery']
runid='CD-QUERY-'+phase+'-'+str(int(time.time()));out=Path('/opt/bklite-environment-test-20261113/evidence/query-alert-20261115');out.mkdir(exist_ok=True)
script=r'''
import socket,struct,json,time,hashlib,urllib.request
host=socket.gethostname();service='cd-c' if host=='env-auto-c-20261114' else 'cd-d';assert host in ['env-auto-c-20261114','env-auto-d-20261114']
marker=RUNID+'-'+host
payload=json.dumps({'message':marker,'verification':'CD-QUERY','level':'error' if PHASE=='alarm' else 'info'}).encode()
with socket.create_connection(('127.0.0.1',15044),timeout=10) as s:
 s.sendall(b'2W'+struct.pack('!I',1)+b'2J'+struct.pack('!II',1,len(payload))+payload);ack=s.recv(6).hex();assert ack=='324100000001'
def attr(k,v):return {'key':k,'value':{'stringValue':v}}
attrs=[attr('service.namespace','cd-query-validation'),attr('service.name',service),attr('service.instance.id',host),attr('deployment.environment','isolated'),attr('service.version','1.0'),attr('telemetry.sdk.language','python')]
spans=[];ids=[];now=time.time_ns()
for i in range(20):
 trace=hashlib.sha256((marker+str(i)).encode()).hexdigest()[:32];ids.append(trace)
 spans.append({'traceId':trace,'spanId':'1234567890abcdef','name':'GET /cd-validation','kind':2,'startTimeUnixNano':str(now+i),'endTimeUnixNano':str(now+i+(500000000 if PHASE=='alarm' else 1000000)),'status':{'code':2 if PHASE=='alarm' else 1},'attributes':[attr('http.method','GET'),attr('http.route','/cd-validation'),{'key':'http.status_code','value':{'intValue':500 if PHASE=='alarm' else 200}},attr('test.marker',marker)]})
data={'resourceSpans':[{'resource':{'attributes':attrs},'scopeSpans':[{'scope':{'name':'cd-query-validation'},'spans':spans}]}]}
r=urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:4318/v1/traces',data=json.dumps(data).encode(),headers={'Content-Type':'application/json'}),timeout=10);assert r.status==200
print(json.dumps({'host':host,'service':service,'marker':marker,'trace_ids':ids,'log_ack':ack,'otlp_status':r.status,'otlp_response':r.read().decode()}))
'''
def inject(ip):
 r=subprocess.run(['ssh','-T','root@'+ip,'python3 -'],input='RUNID='+repr(runid)+'\nPHASE='+repr(phase)+'\n'+script,text=True,capture_output=True,check=True,timeout=40)
 d=json.loads(r.stdout);d['ip']=ip;return d
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(inject,['192.168.122.4','192.168.122.209']))
(out/(phase+'-traffic.json')).write_text(json.dumps(results,indent=2));print(json.dumps([{'ip':x['ip'],'marker':x['marker'],'trace_count':len(x['trace_ids'])} for x in results]));print('__CD_QUERY_TRAFFIC_INJECTED__')

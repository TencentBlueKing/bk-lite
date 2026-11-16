"""Enable only the isolated log/APM query and alert runtime, with DB backup."""
from pathlib import Path
import subprocess,json,hashlib,secrets,time,os
root=Path('/opt/bklite-environment-test-20261113');image=os.environ.get('ENV_QUERY_SERVER_IMAGE', 'bklite/server:env-business-20261115');network='env-install-net-20261113'
def run(*args,**kwargs):return subprocess.run(args,check=True,capture_output=True,text=True,**kwargs).stdout
# Resolve before mutations; the immutable ID also detects rebuilt tags.
image=json.loads(run('docker','image','inspect',image))[0]['Id']
assert json.loads(run('docker','inspect','env-install-ca-api-20261113'))[0]['NetworkSettings']['Networks'].get(network)
private=root/'config/query-minio.json'
if not private.exists():
 private.write_text(json.dumps({'user':'isolatedqueryminio','password':secrets.token_urlsafe(32)}));private.chmod(0o600)
credentials=json.loads(private.read_text())
if credentials['user']=='envqueryminio':
 credentials['user']='isolatedqueryminio';private.write_text(json.dumps(credentials));private.chmod(0o600)
minio_env={**os.environ,'MINIO_ROOT_USER':credentials['user'],'MINIO_ROOT_PASSWORD':credentials['password']}
# This image supplies *_FILE defaults; clear them when using environment credentials.
minio_name='env-query-minio-20261115'
found=subprocess.run(['docker','inspect',minio_name],capture_output=True,text=True)
if found.returncode==0:
 item=json.loads(found.stdout)[0]
 assert network in item['NetworkSettings']['Networks']
 if not item['State']['Running']:
  run('docker','rename',minio_name,minio_name+'-failed-'+item['Id'][:8])
  found=None
if found is None or found.returncode:
 file_options=[]
 for key in ['MINIO_ACCESS_KEY_FILE','MINIO_SECRET_KEY_FILE','MINIO_ROOT_USER_FILE','MINIO_ROOT_PASSWORD_FILE','MINIO_KMS_SECRET_KEY_FILE','MINIO_CONFIG_ENV_FILE']:
  file_options.extend(['-e',key+'='])
 run('docker','run','-d','--pull=never','--name',minio_name,'--network',network,'--memory','512m','--cpus','1','-e','MINIO_ROOT_USER','-e','MINIO_ROOT_PASSWORD',*file_options,'-v',minio_name+':/data','--entrypoint','sh','bk-lite.tencentcloudcr.com/bklite/weopsx/minio/minio:RELEASE.2024-05-01T01-11-10Z-cpuv1','-c','unset MINIO_ACCESS_KEY_FILE MINIO_SECRET_KEY_FILE MINIO_ROOT_USER_FILE MINIO_ROOT_PASSWORD_FILE MINIO_KMS_SECRET_KEY_FILE MINIO_CONFIG_ENV_FILE; exec minio server /data',env=minio_env)
for attempt in range(15):
 check=subprocess.run(['docker','exec',minio_name,'curl','-fsS','http://127.0.0.1:9000/minio/health/ready'],capture_output=True)
 if check.returncode==0:break
 time.sleep(2)
else:raise RuntimeError('Isolated MinIO readiness failed; deployment stopped')
base=(root/'config/ui-server.env').read_text().splitlines()
overrides={'INSTALL_APPS':'node_mgmt,system_mgmt,monitor,log,apm','DJANGO_SETTINGS_MODULE':'query_settings','VICTORIALOGS_HOST':'http://env-business-20261115-logs:9428','VICTORIATRACES_HOST':'http://env-business-20261115-traces:10428','APM_SYSTEM_COLLECTOR_HEALTH_ENDPOINT':'http://env-business-20261115-apm:13133','ENABLE_CELERY':'true'}
overrides.update({'MINIO_ENDPOINT':'env-query-minio-20261115:9000','MINIO_USE_HTTPS':'0','MINIO_ACCESS_KEY':credentials['user'],'MINIO_SECRET_KEY':credentials['password']})
content='\n'.join(x for x in base if x.split('=',1)[0] not in overrides)+'\n'+'\n'.join(k+'='+v for k,v in overrides.items())+'\n'
env={**os.environ,**overrides}
options=[value for key in overrides for value in ('-e',key)]
backup=root/'query-backup-20261115';backup.mkdir(exist_ok=True,mode=0o700)
if not (backup/'database.dump').exists():
 with (backup/'database.dump').open('wb') as f:
  subprocess.run(['docker','exec','env-install-pg-20261113','sh','-c','pg_dump -Fc -U "$POSTGRES_USER" "$POSTGRES_DB"'],stdout=f,check=True)
 (backup/'database.dump').chmod(0o600)
common=['--network',network,'--memory','2g','--env-file',str(root/'config/ui-server.env'),*options,'-v',str(root)+':/test','-w','/apps']
run('docker','run','--rm',*common,'--entrypoint','python',image,'manage.py','check',env=env)
result=run('docker','run','--rm',*common,'--entrypoint','python',image,'manage.py','migrate','--noinput',env=env)
(root/'evidence/query-migrations-20261115.log').write_text(result)
spec=hashlib.sha256((content+image).encode()).hexdigest()
for name,alias,entry,args in [
 ('env-install-ca-api-20261113','env-install-ca-api','uvicorn',['asgi:application','--workers','1','--host','0.0.0.0','--port','8000','--no-access-log']),
 ('env-install-worker-20261113',None,'celery',['-A','apps.core.celery','worker','-l','WARNING','--pool=threads','--concurrency=2']),
 ('env-install-rpc-20261113',None,'python',['manage.py','nats_listener']),
 ('env-query-notice-20261115',None,'python',['/test/runtime/business/query-notice-sink.py']),
 ('env-query-beat-20261115',None,'celery',['-A','apps.core.celery','beat','-l','WARNING','--pidfile=/tmp/query-beat.pid','--schedule=/tmp/query-beat-schedule']),
]:
 found=subprocess.run(['docker','inspect',name],capture_output=True,text=True)
 if found.returncode==0:
  item=json.loads(found.stdout)[0]
  if (item['Config'].get('Labels') or {}).get('query-spec')==spec:
   assert item['State']['Running'],name+' stopped';continue
  assert network in item['NetworkSettings']['Networks'],name
  run('docker','stop',name);run('docker','rename',name,name+'-pre-query-'+item['Id'][:8])
 extra=['--network-alias',alias] if alias else []
 run('docker','run','-d','--name',name,'--label','query-spec='+spec,*common,*extra,'--entrypoint',entry,image,*args,env=env)
run('docker','exec','env-install-nginx-20261113','nginx','-s','reload')
print('__ISOLATED_QUERY_AND_ALERT_RUNTIME_DEPLOYED__')

"""Idempotent business dependency fixture for the explicitly isolated wx-test lab.

No VM files are edited. Broker permissions, cloud-region env and downstream
services are reconciled as deployment dependencies. Never use on production.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path('/opt/bklite-environment-test-20261113')
NETWORK = 'env-install-net-20261113'
API = 'env-install-ca-api-20261113'
PREFIX = 'env-business-20261115'


def run(*args, **kwargs):
    return subprocess.run(args, check=True, capture_output=True, text=True, **kwargs).stdout


def executor_permissions(existing, nodes):
    import copy
    permissions = copy.deepcopy(existing)
    pub = permissions['publish']['allow']
    sub = permissions['subscribe']['allow']
    pub += ['vector', 'apm.traces.2', '$JS.API.STREAM.NAMES', 'bk.ans_exec.tasks.>']
    for node in nodes:
        pub += [f'ansible_executor.callback.retry.{node}', f'bk.ans_exec.{node}.tasks.>']
        sub += [f'{s}.{node}' for s in ['ansible.adhoc', 'ansible.playbook', 'ansible.task.query']]
        # Current and per-node namespace defaults, including durable callback retry.
        streams = [f'bk.ans_exec.tasks.{node}', f'bk.ans_exec.{node}.tasks.{node}']
        for raw in streams:
            stream = raw.replace('.', '_').upper()
            for stream in [stream, stream+'_CALLBACK_RETRY']:
                pub += [f'$JS.API.STREAM.{op}.{stream}' for op in ['INFO', 'CREATE', 'UPDATE']]
                pub += [f'$JS.API.CONSUMER.{op}.{stream}' for op in ['LIST', 'NAMES', 'CREATE']]
                pub += [f'$JS.API.CONSUMER.{op}.{stream}.>' for op in ['CREATE', 'DURABLE.CREATE', 'INFO', 'DELETE', 'MSG.NEXT']]
                pub += [f'$JS.ACK.{stream}.>']
    permissions['publish']['allow'] = sorted(set(pub))
    permissions['subscribe']['allow'] = sorted(set(sub))
    return permissions


def write_private(path, content):
    path.write_text(content)
    path.chmod(0o600)


def main():
    assert ROOT.is_dir() and json.loads(run('docker','inspect',API))[0]['NetworkSettings']['Networks'].get(NETWORK)
    for image, expected in json.loads((Path(__file__).parent/'images.json').read_text()).items():
        assert json.loads(run('docker','image','inspect',image))[0]['Id']==expected,'Image drift: '+image
    nodes = json.loads(run('docker', 'exec', API, 'python', '-c',
        'import django,json;django.setup();from apps.node_mgmt.models import Node,CloudRegion;'
        'assert CloudRegion.objects.get(pk=2).name=="Auto Executor validation 20261114";'
        'print(json.dumps(list(Node.objects.filter(cloud_region_id=2).values_list("id",flat=True))))'))
    assert len(nodes) == 2
    cfg = ROOT/'config/nats.conf'; before=cfg.read_text(); data=json.loads(before)
    account = next(u for u in data['authorization']['users'] if u['user']=='test-auto-region-executor')
    previous_permissions = {'account': account['user'], 'permissions': account['permissions']}
    account['permissions'] = executor_permissions(account['permissions'], nodes)
    if '--apply' not in sys.argv:
        print(json.dumps({'region':2,'nodes':nodes,'broker_permissions_changed':json.loads(before)!=data,'services':['logs','traces','vector','apm'],'mode':'plan'}));return
    backup=ROOT/'config/nats.permissions-pre-business-20261115.json'
    if not backup.exists():write_private(backup,json.dumps(previous_permissions))
    if json.loads(before) != data:
        write_private(cfg,json.dumps(data));run('docker','kill','--signal=HUP','env-install-nats-20261113')
    # Use existing private broker administrative identity only within new isolated
    # server-side consumers; never distribute it to VM nodes.
    admin=next(u for u in data['authorization']['users'] if u['user']=='test-admin')
    private=ROOT/'business-20261115';private.mkdir(exist_ok=True,mode=0o755);private.chmod(0o755)
    ca=private/'ca.crt';ca.write_bytes((ROOT/'certs/ca.crt').read_bytes());ca.chmod(0o644)
    env={
        'VECTOR_NATS_SERVERS':'tls://env-install-nats:4222','NATS_ADMIN_USERNAME':admin['user'],'NATS_ADMIN_PASSWORD':admin['password'],
        'VECTOR_NATS_TLS_ENABLED':'true','VECTOR_NATS_TLS_CA_FILE':'/test/certs/ca.crt',
        'VECTOR_VICTORIA_LOGS_URL':'http://'+PREFIX+'-logs:9428',
        'APM_NATS_URL':'tls://'+admin['user']+':'+admin['password']+'@env-install-nats:4222',
        'APM_NATS_STREAM':'ENV_AUTO_APM_2','APM_NATS_CONSUMER':'ENV_AUTO_APM_SYSTEM_2',
        'APM_NATS_CREDENTIALS_FILE':'','APM_NATS_CA_FILE':'/test/certs/ca.crt','APM_NATS_CERT_FILE':'','APM_NATS_KEY_FILE':'','APM_NATS_TLS_SERVER_NAME':'env-install-nats',
        'APM_NATS_MAX_ACK_PENDING':'32','APM_COLLECTOR_MEMORY_LIMIT_MIB':'192','APM_COLLECTOR_MEMORY_SPIKE_MIB':'48',
        'APM_VICTORIATRACES_OTLP_ENDPOINT':'http://'+PREFIX+'-traces:10428/insert/opentelemetry/v1/traces',
    }
    (private/'system.yaml').write_bytes((Path(__file__).parent/'system.yaml').read_bytes())
    run('docker','exec',API,'python','/test/runtime/business/region.py')
    run('docker','compose','-f',str(Path(__file__).parent/'compose.yaml'),'up','-d','--pull','never',env={**os.environ,**env})
    print('__BUSINESS_DEPENDENCIES_RECONCILED__')

if __name__ == '__main__':
    assert all(arg in ['--plan','--apply'] for arg in sys.argv[1:])
    main()

"""Run in the isolated API, not startup.sh; no per-node configuration edits."""
import asyncio
import json
from pathlib import Path
import django
django.setup()
from apps.node_mgmt.models import CloudRegion,SidecarEnv
from apps.core.utils.crypto.aes_crypto import AESCryptor
from nats_client.clients import get_nc_client
from nats.js.errors import NotFoundError
from nats.js.api import ConsumerConfig,AckPolicy,StorageType
from apps.log.services.log_extractor.compiler import compile_system_vector_config
root=Path('/test');assert CloudRegion.objects.get(pk=2).name=='Auto Executor validation 20261114'
credentials=json.loads((root/'config/auto-executor-runtime.json').read_text())
for key,value,kind in [('NATS_USERNAME',credentials['user'],'string'),('NATS_PASSWORD',credentials['password'],'secret')]:
 item=SidecarEnv.objects.get(cloud_region_id=2,key=key)
 current=AESCryptor().decode(item.value) if item.type=='secret' else item.value
 if current!=value:
  item.value=AESCryptor().encode(value) if kind=='secret' else value;item.type=kind;item.save()
(root/'business-20261115/vector.yaml').write_text(compile_system_vector_config([]))
async def main():
 nc=await get_nc_client();js=nc.jetstream();name='ENV_AUTO_APM_2'
 try:
  info=await js.stream_info(name);assert info.config.subjects==['apm.traces.2'] and info.config.storage==StorageType.FILE
 except NotFoundError:
  await js.add_stream(name=name,subjects=['apm.traces.2'],storage=StorageType.FILE,max_bytes=67108864,max_age=86400,max_msg_size=8388608)
 durable='ENV_AUTO_APM_SYSTEM_2'
 try:
  info=await js.consumer_info(name,durable);assert info.config.filter_subject in ['apm.traces.2','apm.traces.>']
  if info.config.filter_subject!='apm.traces.>':
   info.config.filter_subject='apm.traces.>';await js.add_consumer(name,info.config)
 except NotFoundError:
  await js.add_consumer(name,ConsumerConfig(durable_name=durable,filter_subject='apm.traces.>',ack_policy=AckPolicy.EXPLICIT,ack_wait=60,max_ack_pending=32,max_deliver=8))
 await nc.close()
asyncio.run(main());print('__REGION_AND_DURABLE_STREAM_READY__')
# Reconcile only generated defaults in this lab region. Refuse custom drift.
from django.db import transaction
from apps.node_mgmt.models import Collector,CollectorConfiguration
from apps.node_mgmt.services.sidecar import Sidecar
from apps.core.utils.safe_template import build_sandboxed_env
source=json.loads((root/'runtime/business/Ansible-Executor.json').read_text())
new=next(c for c in source if c['id']=='ansibleexecutor_linux')['default_config']
old=new['nats'].replace('bk.ans_exec.${node.id}', 'bk.ans_exec')
with transaction.atomic():
 collector=Collector.objects.get(pk='ansibleexecutor_linux')
 if collector.default_config!=new:collector.default_config=new;collector.save()
 for cfg in CollectorConfiguration.objects.filter(cloud_region_id=2,collector=collector):
  assert cfg.is_pre and cfg.nodes.count()==1,'Refuse custom or shared configuration'
  node=cfg.nodes.get();assert node.cloud_region_id==2
  variables=Sidecar.get_cloud_region_envconfig(node)
  target=build_sandboxed_env().from_string(new['nats']).render(variables)
  previous=build_sandboxed_env().from_string(old).render(variables)
  assert cfg.config_template in [previous,target],'Default has custom drift'
  if cfg.config_template!=target:cfg.config_template=target;cfg.save()
print('__NODE_SCOPED_ANSIBLE_DEFAULTS_RECONCILED__')

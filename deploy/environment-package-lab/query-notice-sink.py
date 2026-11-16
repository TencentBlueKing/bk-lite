"""Local notification receiver: records real requests and acknowledges delivery."""
import asyncio,json,datetime
from pathlib import Path
import django
django.setup()
from nats_client.clients import get_nc_client
out=Path('/test/evidence/query-alert-20261115');out.mkdir(exist_ok=True)
async def main():
 nc=await get_nc_client()
 async def receive(msg):
  data=json.loads(msg.data)
  data.get('kwargs',{}).pop('internal_auth',None)
  record={'received_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'subject':msg.subject,'request':data}
  with (out/'notification-receipts.jsonl').open('a') as f:f.write(json.dumps(record,ensure_ascii=False)+'\n')
  await msg.respond(json.dumps({'success':True,'result':{'result':True,'message':'isolated notification stored'}}).encode())
 await nc.subscribe('envquery.receive_alert_events',cb=receive);await nc.flush();print('__ISOLATED_NOTICE_SINK_READY__',flush=True)
 await asyncio.Future()
asyncio.run(main())

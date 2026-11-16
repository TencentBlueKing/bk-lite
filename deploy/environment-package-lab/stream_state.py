import asyncio,json,django
django.setup()
from nats_client.clients import get_nc_client
async def main():
 nc=await get_nc_client();js=nc.jetstream();s=await js.stream_info('ENV_AUTO_APM_2');c=await js.consumer_info('ENV_AUTO_APM_2','ENV_AUTO_APM_SYSTEM_2')
 print(json.dumps({'storage':s.config.storage,'messages':s.state.messages,'last_seq':s.state.last_seq,'pending':c.num_pending,'ack_pending':c.num_ack_pending}));await nc.close()
asyncio.run(main())

import os

from api import api, enterprise_api
from core.collection.application import initialize_collection_application
from core.collection.host_remote.runtime import register_host_remote_runtime
from core.config import YamlConfig
from core.infra.nats import initialize_nats
from core.infra.redis_client import register_redis_lifecycle
from core.infra.snmp_engine_pool import register_snmp_engine_lifecycle
from dotenv import load_dotenv
from sanic import Sanic

load_dotenv(".env")

yml_config = YamlConfig(path="./config.yml")
app = Sanic("Stargazer", config=yml_config)
app.blueprint(api)
if enterprise_api:
    app.blueprint(enterprise_api)

nats_instance_id = os.getenv("NATS_INSTANCE_ID", "default")
service_name = f"{nats_instance_id}_stargazer"
nats = initialize_nats(app, service_name=service_name)

register_redis_lifecycle(app)
register_snmp_engine_lifecycle(app)
initialize_collection_application(app)
register_host_remote_runtime(app)

# 导入 nats_server 模块，确保处理器被注册
from service import nats_server as _nats_server  # noqa: E402,F401


@app.before_server_start
async def show_banner(app, loop):
    with open("./asserts/banner.txt") as f:
        print(f.read())


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8083, workers=int(os.getenv("SANIC_WORKERS", "4")))

from sanic import Sanic
from api import api
from core.config import YamlConfig
from dotenv import load_dotenv
from core.nats import initialize_nats

load_dotenv()

yml_config = YamlConfig(path="./config.yml")
app = Sanic("Stargazer", config=yml_config)
app.blueprint(api)

# 初始化 NATS
nats = initialize_nats(app, service_name="stargazer")

# 导入 nats_server 模块，确保处理器被注册
from service import nats_server


@app.before_server_start
async def show_banner(app, loop):
    with open(f"./asserts/banner.txt") as f:
        print(f.read())


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8083, workers=1)

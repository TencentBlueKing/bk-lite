from sanic import Sanic
from sanic.response import text

app = Sanic("Metis")

@app.before_server_start
async def show_banner(app, loop):
    with open(f"./asserts/banner.txt") as f:
        print(f.read())


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=18083, workers=1)

"""Django 与 worker 启动器共用的环境文件读取方式。"""

from dotenv import find_dotenv, load_dotenv


def load_runtime_environment():
    path = find_dotenv(usecwd=True)
    if path:
        load_dotenv(path, override=False)

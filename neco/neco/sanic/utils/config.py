from sanic.config import Config
import yaml


class YamlConfig(Config):
    def __init__(self, *args, path: str, **kwargs):
        super().__init__(*args, **kwargs)

        with open(path, "r", encoding="utf-8") as f:
            self.update(yaml.load(f, Loader=yaml.SafeLoader))

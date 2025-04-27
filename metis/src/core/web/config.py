from sanic.config import Config
import yaml


class YamlConfig(Config):
    def __init__(self, *args, path: str, **kwargs):
        super().__init__(*args, **kwargs)

        with open(path, "r") as f:
            self.apply(yaml.load(f, Loader=yaml.SafeLoader))

    def apply(self, config):
        self.update(config)

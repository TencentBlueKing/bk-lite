from .client import test_esb_connection


class BlueKingBaseConnectionAdapter:
    @classmethod
    def test_connection(cls, config: dict, provider_key: str, capability_key: str, **kwargs):
        return test_esb_connection(config)

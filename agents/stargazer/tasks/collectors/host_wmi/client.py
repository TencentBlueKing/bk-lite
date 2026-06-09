from .errors import WmiError


class WmiClient:
    def __init__(self, host: str, username: str, password: str, namespace: str = "root\\cimv2", timeout: int = 60):
        self.host = host
        self.username = username
        self.password = password
        self.namespace = namespace
        self.timeout = timeout

    def connect(self):
        raise WmiError("WMI client dependency is not configured", "unknown")

    def close(self):
        return None

    def query_class(self, class_name: str):
        return self.query(f"SELECT * FROM {class_name}")

    def query(self, query: str):
        raise WmiError("WMI client dependency is not configured", "unknown")

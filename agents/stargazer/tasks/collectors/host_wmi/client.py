from .errors import WmiError


class WmiClient:
    def __init__(self, host: str, username: str, password: str, namespace: str = "root\\cimv2", timeout: int = 60):
        self.host = host
        self.username = username
        self.password = password
        self.namespace = namespace
        self.timeout = timeout
        self._dcom = None
        self._services = None

    def _load_impacket(self):
        from impacket.dcerpc.v5.dcom import wmi
        from impacket.dcerpc.v5.dcomrt import DCOMConnection
        from impacket.dcerpc.v5.dtypes import NULL

        return DCOMConnection, wmi, NULL

    def _split_username(self) -> tuple[str, str]:
        username = str(self.username or "")
        if "\\" in username:
            domain, user = username.split("\\", 1)
            return domain, user
        if "@" in username:
            user, domain = username.split("@", 1)
            return domain, user
        return "", username

    @staticmethod
    def _normalize_rows(raw_rows):
        rows = []
        for raw_row in raw_rows:
            row = {}
            for key, value in raw_row.items():
                if isinstance(value, dict) and "value" in value:
                    row[key] = value.get("value")
                else:
                    row[key] = value
            rows.append(row)
        return rows

    def connect(self):
        try:
            DCOMConnection, wmi, NULL = self._load_impacket()
        except ImportError as error:
            raise WmiError("impacket is required for Windows WMI collection", "unknown") from error

        domain, user = self._split_username()
        try:
            self._dcom = DCOMConnection(
                self.host,
                user,
                self.password,
                domain,
                "",
                "",
                oxidResolver=True,
            )
            interface = self._dcom.CoCreateInstanceEx(
                wmi.CLSID_WbemLevel1Login,
                wmi.IID_IWbemLevel1Login,
            )
            login = wmi.IWbemLevel1Login(interface)
            self._services = login.NTLMLogin(f"//./{self.namespace}", NULL, NULL)
            login.RemRelease()
        except Exception as error:
            self.close()
            raise WmiError(f"failed to connect to WMI: {error}", "unknown") from error

    def close(self):
        services = self._services
        self._services = None
        if services and hasattr(services, "RemRelease"):
            try:
                services.RemRelease()
            except Exception:
                pass

        dcom = self._dcom
        self._dcom = None
        if dcom and hasattr(dcom, "disconnect"):
            try:
                dcom.disconnect()
            except Exception:
                pass

    def query_class(self, class_name: str):
        return self.query(f"SELECT * FROM {class_name}")

    def query(self, query: str):
        if self._services is None:
            raise WmiError("WMI query called before connection is ready", "unknown")

        try:
            enumerator = self._services.ExecQuery(query)
            raw_rows = []
            while True:
                try:
                    item = enumerator.Next(0xFFFFFFFF, 1)[0]
                    raw_rows.append(item.getProperties())
                    item.RemRelease()
                except Exception as error:
                    if "S_FALSE" in str(error):
                        break
                    raise
            return self._normalize_rows(raw_rows)
        except Exception as error:
            raise WmiError(f"WMI query failed: {error}", "query_failed") from error
        finally:
            if "enumerator" in locals() and hasattr(enumerator, "RemRelease"):
                try:
                    enumerator.RemRelease()
                except Exception:
                    pass

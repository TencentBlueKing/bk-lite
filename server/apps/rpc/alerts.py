# -- coding: utf-8 --
import os

from apps.rpc.base import AppClient, BaseOperationAnaRpc


class AlertOperationAnaRpc(BaseOperationAnaRpc):
    def __init__(self, *args, **kwargs):
        is_local_client = kwargs.pop("is_local_client", False)
        is_local_client = os.getenv("IS_LOCAL_RPC", "0") == "1" or is_local_client
        if is_local_client:
            self.client = AppClient("apps.alerts.nats.nats")
            return
        super().__init__(*args, **kwargs)

    def get_alert_trend_data(self, *args, **kwargs):
        return_data = self.client.run("get_alert_trend_data", *args, **kwargs)
        return return_data

    def list_alerts(self, query_data: dict, **kwargs):
        return self.client.run("list_alerts", query_data=query_data, **kwargs)

    def get_alert_detail(self, alert_id: str, **kwargs):
        return self.client.run("get_alert_detail", alert_id=alert_id, **kwargs)

    def list_alert_events(self, alert_id: str, query_data: dict, **kwargs):
        return self.client.run("list_alert_events", alert_id=alert_id, query_data=query_data, **kwargs)

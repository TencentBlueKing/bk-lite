"""在现有 SNMP 采集与认证链路上输出指定对象的系统配置。"""
from plugins.inputs.network.snmp_facts import SnmpFacts


class SnmpInventory(SnmpFacts):
    model_id = "network"

    async def list_all_resources(self):
        result = await super().list_all_resources()
        if result.get("success"):
            result["result"] = {self.model_id: result["result"].get("network_system", [])}
        return result

"""OpsPilot 发布时，把 workflow 里的 nats 触发节点同步为 system_mgmt 的 NATS 通道。

设计要点：
- 通道由 OpsPilot 托管，通道名为 ``{bot.name} - {节点label}``，config 里带 source="opspilot"
  以及 bot_id/node_id，供告警中心通过统一通道触发 workflow。
- 仅在发布（上线）时同步；同步为对账式（增/改/删），删除已移除节点对应的旧通道。
- 通过 RPC 调 system_mgmt，不直接 import Channel 模型（两者可能分进程部署）。
"""
from apps.core.logger import opspilot_logger as logger
from apps.opspilot.models import BotWorkFlow
from apps.rpc.system_mgmt import SystemMgmt


def extract_nats_nodes(flow_json):
    """从 flow_json 中提取 type=='nats' 的触发节点，返回 [{"node_id", "name"}]。"""
    nodes = []
    if not isinstance(flow_json, dict):
        return nodes
    for node in flow_json.get("nodes", []) or []:
        if not isinstance(node, dict) or node.get("type") != "nats":
            continue
        node_id = node.get("id")
        if not node_id:
            continue
        label = (node.get("data") or {}).get("label") or node_id
        nodes.append({"node_id": str(node_id), "name": str(label)})
    return nodes


def sync_opspilot_nats_channels_for_bot(bot):
    """发布时同步 bot 下 nats 触发节点对应的通道（对账：增/改/删）。失败不阻断发布。"""
    try:
        workflow = BotWorkFlow.objects.filter(bot_id=bot.id).order_by("-id").first()
        flow_json = workflow.flow_json if workflow else None
        nats_nodes = extract_nats_nodes(flow_json)
        result = SystemMgmt().sync_opspilot_nats_channels(
            bot_id=bot.id,
            bot_name=bot.name,
            team=bot.team or [],
            nodes=nats_nodes,
        )
        logger.info(f"[NatsChannelSync] bot={bot.id} 同步通道结果: {result}")
        return result
    except Exception as e:  # noqa: BLE001
        logger.error(f"[NatsChannelSync] bot={bot.id} 同步 NATS 通道失败: {e}", exc_info=True)
        return {"result": False, "message": str(e)}


def cleanup_opspilot_nats_channels_for_bot(bot_id):
    """bot 删除时清理其名下所有 OpsPilot 托管的 NATS 通道。失败不阻断删除。"""
    try:
        result = SystemMgmt().delete_opspilot_nats_channels(bot_id=bot_id)
        logger.info(f"[NatsChannelSync] bot={bot_id} 清理通道结果: {result}")
        return result
    except Exception as e:  # noqa: BLE001
        logger.error(f"[NatsChannelSync] bot={bot_id} 清理 NATS 通道失败: {e}", exc_info=True)
        return {"result": False, "message": str(e)}

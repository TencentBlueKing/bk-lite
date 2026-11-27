# -- coding: utf-8 --
"""云事件接入说明。

指南页读接入说明接口。字段映射按平台事件字段列出云上取值。
示例是云厂商原始 JSON，并带上这条报文实际入库的字段。
"""

import json
from datetime import datetime
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from apps.alerts.common.source_adapter.cloud_catalog import catalog_text, parse_body

_PLACEHOLDER_HOST = "{url}"
_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}
_SHANGHAI = ZoneInfo("Asia/Shanghai")
_FIRING_AT = datetime(2026, 11, 26, 17, 0, tzinfo=_SHANGHAI)
_RECOVERY_AT = datetime(2026, 11, 26, 17, 10, tzinfo=_SHANGHAI)
_FIRING_ISO = "2026-11-26T09:00:00Z"
_RECOVERY_ISO = "2026-11-26T09:10:00Z"
_FIRING_NAIVE = "2026-11-26 17:00:00"
_RECOVERY_NAIVE = "2026-11-26 17:10:00"
_FIRING_MS = int(_FIRING_AT.timestamp() * 1000)

_ALIYUN_ACCOUNT = "1234567890980000"
_ALIYUN_INSTANCE = "i-bp1gp1t77800001"
_ALIYUN_EVENT = "e-bp1c86ziq4q00001"
_DISK_ID = "d-bp15esw9c01fh0001"
_PARENT_INSTANCE = "i-bp1iwarx7zt1e0001"
_TENCENT_SESSION = "sess-cvm-0001"
_TENCENT_INSTANCE = "ins-0a1b2c3d"
_TENCENT_APP = "1250000000"


def webhook_path(source_id):
    return f"/api/v1/alerts/api/source/{source_id}/webhook/"


def stored_webhook_url(source_id):
    return f"{_PLACEHOLDER_HOST}{webhook_path(source_id)}"


def _public_origin(value):
    text = str(value or "").strip().rstrip("/")
    if not text or text == "{url}":
        return ""
    parsed = urlparse(text if "://" in text else f"http://{text}")
    host = (parsed.hostname or "").lower()
    if host in _LOOPBACK_HOSTS:
        return ""
    return text


def callback_origin(base_url):
    """云上要访问的平台地址。127 和 localhost 不能写进指南。"""
    from django.conf import settings

    requested = _public_origin(base_url)
    if requested:
        return requested
    configured = _public_origin(getattr(settings, "WEB_BASE_URL", ""))
    if configured:
        return configured
    return "{url}"


def cloud_operator_guide(vendor):
    if vendor == "aliyun":
        return _aliyun_guide()
    return _tencent_guide()


def cloud_request_examples(source_id, webhook_url, credential, query_url=None):
    if source_id == "aliyun_eventbridge":
        return _aliyun_examples(webhook_url, credential)
    if source_id == "tencent_eventbus":
        return _tencent_examples(webhook_url, credential, query_url)
    return {"CURL": "", "Python": "", "items": []}


def _row(field, source, detail):
    return {"field": field, "from": source, "detail": detail}


def _section(title, *paragraphs):
    return {"title": title, "paragraphs": list(paragraphs)}


def _aliyun_guide():
    return {
        "description": ("阿里云 EventBridge 把 ECS 原始 JSON 推到本地址。" "平台按下面的事件字段映射写入事件，云上不要改成 title、description 这套字段名。"),
        "field_mapping_note": "下表每一行是事件上的一个字段，右边是它从云上报文的哪里来。报文里多出来的字段留在原始数据 original，不单独成列。",
        "sections": [
            _section(
                "回调收什么",
                "地址已经选中集成源「阿里云 EventBridge」。请求体是云上的原始 JSON，一个对象是一条事件，对象数组里每个对象是一条事件。",
                "不要包 source_id，也不要包 events。包成通用 REST 报文时，平台认不出阿里云事件，回执 400。",
                "多个云账号可以共用这一条地址和同一枚组织密钥。账号留在报文的 aliyunaccountid，平台把它写进内容和 labels.account。",
            ),
            _section(
                "阿里云控制台怎么填",
                "在该账号的默认事件总线新建规则。投递目标选 HTTP，方法 POST。地址填本页回调地址。请求头增加一行，名称 SECRET，值是本页所选组织揭示出来的组织密钥。不要填告警源上的源级总密钥，那种密钥回执 403。",
                (
                    "事件模式只订下面目录里的类型，并且订带 CloudMonitor 的过程态，"
                    "例如 ecs:CloudMonitor:Instance[SystemFailure.Reboot:Executing]。"
                    "同一件事不要再订不带 CloudMonitor 的原生事件 ecs:Instance:SystemFailure.Reboot，否则一次重启会推两条。"
                ),
                "过程态要把该类型实际有的阶段订全。Executing 是发生。Executed、Avoided、Canceled 是恢复。Failed 仍记为发生，但挂到同一条未关闭告警上，不新开、不再通知。Scheduled 和 Inquiring 记为无状态，不建告警。",
                (
                    "另外只订四条没有过程态的原生事件：ecs:Instance:StateChange、"
                    "ecs:Instance:PreemptibleInstanceInterruption、ecs:Instance:LiveMigrationAcrossDDH、"
                    "ecs:Disk:OverduePaymentRelease。它们只进事件列表。"
                ),
                "不要订 ActionTrail 和 Config。目录外的 ECS 事件回执 200，但不入库。",
            ),
            _section(
                "告警什么时候出现",
                "事件先入库。只有动作是 created，并且还没有同一 external_id 的未关闭告警时，才新建告警。后面再到的发生，包括 Failed，挂到这条告警上。恢复把这条告警关掉。恢复先到、之后又来一条发生，仍会新建告警。",
                "无状态的 record 不建告警。还要另建一条即时策略，匹配条件选集成源「阿里云 EventBridge」，运算符用 any_of。没有这条策略时，事件列表有数据，不会发通知。窗口策略能匹配上，但要等窗口结束。",
            ),
            _section(
                "回执怎么看",
                "200：已接收。重复投递、目录外跳过，也是 200。403：没带组织密钥，或带了源级总密钥。400：空包、不是 JSON、数组里有非对象，或认不出是阿里云事件。500：平台内部失败，并且一条都没入库。",
                "日志只记集成源、事件类型和处理结果，不记报文和密钥。",
            ),
        ],
        "steps": [
            "默认事件总线，HTTP POST，请求头 SECRET 填所选组织的组织密钥。",
            "只订目录中的 CloudMonitor 过程态，不要再订同名原生事件。",
            "另订 StateChange、PreemptibleInstanceInterruption、LiveMigrationAcrossDDH、OverduePaymentRelease。",
            "不要订 ActionTrail 和 Config。",
            "再建即时策略，匹配集成源「阿里云 EventBridge」。",
        ],
        "key_reminders": [
            "产生和恢复必须是同一个 data.eventId。外层 id 是投递 ID，每次都变，不能用来关联。",
            "磁盘事件的 resource_id 是 data.diskId。关联 CMDB 时用 data.ecsInstanceId 去对模型 aliyun_ecs。",
            "标题和级别不读报文，按目录生成。级别 0 严重、1 错误、2 警告、3 提醒。",
        ],
        "field_mapping": _aliyun_mapping(),
        "catalog_text": catalog_text("aliyun"),
    }


def _aliyun_mapping():
    return [
        _row("title", "目录中文名 + 空格 + resource_id", "不读报文里的标题。系统错误重启写成「因系统错误实例重启 i-bp1...」。"),
        _row("description", "aliyunaccountid，aliyunregionid，再加发生、恢复或无状态", "Failed 时内容末尾再加「失败」。认不出的阶段把原文也写进内容，动作仍是无状态。"),
        _row("level", "目录里的级别，不读报文", "实例故障、系统错误、磁盘损坏和磁盘严重变慢是 0。系统维护进行中是 2。计划、问询、状态变化、抢占释放、热迁移、欠费释放是 3。Failed 保持该类型自己的级别。"),
        _row("item", "type 方括号里的事件名，去掉阶段", "ecs:CloudMonitor:Instance[SystemFailure.Reboot:Executing] 的指标名是 SystemFailure.Reboot。"),
        _row("start_time", "time", "ISO8601 按报文里的时区换成毫秒。缺时间则用接收时间，并走现有的分钟级去重。"),
        _row("end_time", "不取", "云上没有单独的结束时间。"),
        _row("labels", "aliyunaccountid", '写成 {"account": "账号"}。没有账号就不写 labels。'),
        _row("rule_id", "不取", "阿里云这条链路没有策略名。"),
        _row("external_id", 'aliyunaccountid + ":" + data.eventId', "产生和恢复必须相同。没有 eventId 时退回 resource_id:事件名。不要用外层 id。"),
        _row("push_source_id", "不改", "保持平台默认值。云账号不写在这个字段。"),
        _row("resource_id", "实例用 data.instanceId，没有则用 data.resourceId；磁盘用 data.diskId", "标题里的资源 ID 和这个字段是同一个值。"),
        _row("resource_name", "实例用 data.instanceName 或 data.ecsInstanceName；磁盘用 data.diskName", "报文没带名称就留空。私网 IP、公网 IP 只留在 original。"),
        _row("resource_type", "由事件种类决定", "实例是 aliyun_ecs。磁盘是 aliyun_disk。这是资源种类，不是 CMDB 模型 ID。"),
        _row("value", "不取", "云事件没有指标数值。"),
        _row(
            "action",
            "type 里的阶段，没有则看 data.eventStatus",
            "Executing 是 created。Executed、Avoided、Canceled 是 recovery。Failed 是 created。Scheduled、Inquiring 和无状态原生事件是 record。",
        ),
        _row("service", "不取", "云上没有对应字段。"),
        _row("tags", "不取", "云上没有对应字段。"),
        _row("location", "aliyunregionid", "和内容里的地域是同一个值。"),
        _row("assignee", "不取", "云上没有责任人。"),
        _row(
            "cmdb_id",
            "按组织查询 CMDB，报文里没有这个字段",
            "实例用 resource_id 对模型 aliyun_ecs。磁盘用 data.ecsInstanceId 对 aliyun_ecs，resource_id 仍是磁盘 ID。组织内恰好一台才写入，否则留空，事件照常入库。",
        ),
    ]


def _tencent_guide():
    return {
        "description": ("腾讯云事件总线把 CVM 原始 JSON 推到本地址。" "监控告警模板和 CloudEvent 都收。平台按下面的事件字段映射写入事件。"),
        "field_mapping_note": "下表每一行是事件上的一个字段。监控模板和 CloudEvent 取值不同的，写在同一行里。报文里多出来的字段留在原始数据 original。",
        "sections": [
            _section(
                "回调收什么",
                "地址已经选中集成源「腾讯云事件总线」。请求体是腾讯云原始 JSON。一个对象是一条事件，对象数组里每个对象是一条事件。不要包 source_id 和 events。",
                "两种正文都能认。监控告警模板要有 alarmType=event。CloudEvent 要有 specversion 和 type。两种都不是的包回执 400，DDoS 高防属于这一类，云上会重试，不要打到这条地址。",
                (
                    "目前只收 CVM。监控模板看 conditions.productName，必须是 cvm，实例 ID 在 alarmObjInfo.dimensions.unInstanceId。"
                    "CloudEvent 的 type 里要有 cvm，实例 ID 用 subject，不用 dimensions。其它产品回执 200，但不入库。"
                ),
            ),
            _section(
                "腾讯云控制台怎么填",
                "在事件总线新建规则，目标选接口回调，不要选短信或电话。事件总线默认每天触达 10000 次，那是腾讯云侧限额。",
                "能加请求头时，地址填本页回调地址，请求头 SECRET 填所选组织的组织密钥。不能加请求头时，改用本页带密钥的回调地址，查询参数名是 secret，值仍是同一枚组织密钥，并且不要再加 SECRET 头。两种方式只选一种。",
                "不要填源级总密钥。源级总密钥回执 403。多个云账号可以共用这一条地址。账号有 appId、ownerUin 或 uin 才写入；官方监控模板示例里经常没有这几个字段，这时 external_id 以冒号开头。",
            ),
            _section(
                "状态、时间和告警",
                "alarmStatus 或 status 为 1、未恢复，动作是 created。为 0、恢复，动作是 recovery。其它值，包括「无状态」，动作是 record，不建告警。官方页面展示过状态 1；把 0 当成恢复，是按恢复报文应关闭告警做的约定。",
                "监控模板的 firstOccurTime 没有时区，按东八区换成毫秒。CloudEvent 的 time 已经是毫秒，不再加时区。恢复报文的时间要晚于发生，否则关不掉已经打开的告警。",
                "业务 ID 用 sessionId，监控模板在最外层，CloudEvent 在最外层或 data.sessionId。不要用 CloudEvent 的 id，那是投递 ID。产生和恢复的 sessionId 必须相同。",
                "只有 created 且还没有同一 external_id 的未关闭告警时才新建告警。随后的发生挂到这条告警上。恢复关闭它。恢复先到，之后的发生仍会新建。另建即时策略，匹配集成源「腾讯云事件总线」，运算符用 any_of。没有策略就只有事件，不会通知。",
            ),
            _section(
                "回执怎么看",
                "200：已接收、重复投递，或不是 CVM 被跳过。403：密钥不对。400：不是监控模板也不是 CloudEvent。500：平台内部失败，并且一条都没入库。",
                "日志只记集成源、事件类型和处理结果，不记报文和密钥。",
            ),
        ],
        "steps": [
            "事件总线规则的目标选接口回调，不要选短信或电话。",
            "能加请求头就加 SECRET；不能加就用查询参数 secret。两种只选一种。",
            "规则只匹配 CVM。实例字段是 unInstanceId，CloudEvent 用 subject。",
            "不要把 DDoS 高防或其它产品打到这条地址。",
            "再建即时策略，匹配集成源「腾讯云事件总线」。",
        ],
        "key_reminders": [
            "产生和恢复必须是同一个 sessionId。",
            "guest_reboot 以及名称里带 reboot、failure、crash、panic、hang 的 CVM 事件，级别是 0。其它已接收的 CVM 事件级别是 2。无状态固定是 3。",
            "标题用目录中文名。guest_reboot 写成「客户机重启」。目录里没有的 CVM 事件，标题用事件名本身。",
        ],
        "field_mapping": _tencent_mapping(),
        "catalog_text": catalog_text("tencent"),
    }


def _tencent_mapping():
    return [
        _row("title", "目录中文名 + 空格 + resource_id", "guest_reboot 写成「客户机重启 ins-...」。不读 eventShowName。"),
        _row("description", "账号，地域，再加发生、恢复或无状态", "账号来自 appId、ownerUin 或 uin。模板没有这些字段时，内容里就没有账号。未知状态的原文会附加在内容里。"),
        _row("level", "按事件名，不读报文里的级别", "名称含 reboot、failure、crash、panic、hang 为 0 严重。其它 CVM 事件为 2 警告。record 固定为 3 提醒。"),
        _row("item", "监控模板 conditions.eventName；CloudEvent 取 type 最后一段", "产品必须是 cvm。指标名是事件名，不是中文展示名。"),
        _row("start_time", "监控模板 firstOccurTime；CloudEvent 的 time", "firstOccurTime 形如 2026-11-26 17:00:00，没有时区，按东八区。time 已是毫秒。缺时间用接收时间。"),
        _row("end_time", "不取", "recoverTime 不写入结束时间，只留在 original。"),
        _row("labels", "appId、ownerUin 或 uin", '写成 {"account": "账号"}。监控模板公开示例经常没有，这时不写 labels。'),
        _row("rule_id", "监控模板 alarmPolicyInfo.policyName；CloudEvent 的 ruleName 或 data.ruleName", "没有策略名就留空。"),
        _row("external_id", '账号 + ":" + sessionId', "监控模板的 sessionId 在最外层。CloudEvent 在最外层或 data.sessionId。没有账号时以冒号开头。不要用 CloudEvent 的 id。"),
        _row("push_source_id", "不改", "保持平台默认值。"),
        _row("resource_id", "监控模板 dimensions.unInstanceId；CloudEvent 的 subject", "两种报文不要混用字段。CloudEvent 不读 dimensions。"),
        _row("resource_name", "不取", "这两类报文没有稳定的实例名称。"),
        _row("resource_type", "固定 qcloud_cvm", "只表示 CVM 这一种资源。没有单独的 CBS 磁盘模型。"),
        _row("value", "不取", "云事件没有指标数值。"),
        _row("action", "alarmStatus 或 status", "1 和「未恢复」是 created。0 和「恢复」是 recovery。其它是 record。CloudEvent 先看最外层 status，没有再看 data.status。"),
        _row("service", "不取", "云上没有对应字段。"),
        _row("tags", "不取", "云上没有对应字段。"),
        _row("location", "监控模板 alarmObjInfo.region；CloudEvent 的 region 或 data.region", "和内容里的地域是同一个值。"),
        _row("assignee", "不取", "云上没有责任人。"),
        _row("cmdb_id", "按组织查询 CMDB，报文里没有这个字段", "用 resource_id 对模型 qcloud_cvm。组织内恰好一台才写入，否则留空，事件照常入库。"),
    ]


def _aliyun_envelope(event_type, data, when, delivery_id):
    return {
        "id": delivery_id,
        "source": "acs.ecs",
        "specversion": "1.0",
        "subject": f"acs.ecs:cn-hangzhou:{_ALIYUN_ACCOUNT}:215672",
        "time": when,
        "type": event_type,
        "aliyunaccountid": _ALIYUN_ACCOUNT,
        "aliyunpublishtime": when,
        "aliyuneventbusname": "default",
        "aliyunregionid": "cn-hangzhou",
        "aliyunpublishaddr": "172.25.0.10",
        "data": data,
    }


def _instance_data(status, event_type, when):
    data = {
        "eventId": _ALIYUN_EVENT,
        "eventStatus": status,
        "eventType": event_type,
        "executeStartTime": _FIRING_ISO,
        "instanceId": _ALIYUN_INSTANCE,
        "instanceName": "web-a",
        "privateIpAddress": ["10.11.0.8"],
        "publicIpAddress": ["47.98.0.8"],
    }
    if status != "Executing":
        data["executeFinishTime"] = when
    return data


ALIYUN_FIRING_BODY = _aliyun_envelope(
    "ecs:CloudMonitor:Instance[SystemFailure.Reboot:Executing]",
    _instance_data("Executing", "SystemFailure.Reboot", _FIRING_ISO),
    _FIRING_ISO,
    "delivery-reboot-executing",
)
ALIYUN_RECOVERY_BODY = _aliyun_envelope(
    "ecs:CloudMonitor:Instance[SystemFailure.Reboot:Executed]",
    _instance_data("Executed", "SystemFailure.Reboot", _RECOVERY_ISO),
    _RECOVERY_ISO,
    "delivery-reboot-executed",
)
ALIYUN_FAILED_BODY = _aliyun_envelope(
    "ecs:CloudMonitor:Instance[SystemFailure.Reboot:Failed]",
    _instance_data("Failed", "SystemFailure.Reboot", _RECOVERY_ISO),
    _RECOVERY_ISO,
    "delivery-reboot-failed",
)
ALIYUN_DISK_BODY = _aliyun_envelope(
    "ecs:CloudMonitor:Disk[ErrorDetected:Executing]",
    {
        "device": "/dev/xvdf",
        "diskId": _DISK_ID,
        "diskName": "data-disk",
        "ecsInstanceId": _PARENT_INSTANCE,
        "ecsInstanceName": "web-a",
        "eventId": "e-disk-0001",
        "eventStatus": "Executing",
        "eventType": "ErrorDetected",
    },
    _FIRING_ISO,
    "delivery-disk-executing",
)
ALIYUN_STATE_BODY = _aliyun_envelope(
    "ecs:Instance:StateChange",
    {
        "eventId": "e-state-0001",
        "resourceId": _ALIYUN_INSTANCE,
        "instanceName": "web-a",
        "state": "Running",
    },
    "2026-11-26T09:20:00Z",
    "delivery-state-change",
)

TENCENT_FIRING_BODY = {
    "sessionId": _TENCENT_SESSION,
    "alarmStatus": "1",
    "alarmType": "event",
    "alarmObjInfo": {
        "region": "ap-guangzhou",
        "namespace": "qce/cvm",
        "appId": _TENCENT_APP,
        "uin": "100001234567",
        "dimensions": {"unInstanceId": _TENCENT_INSTANCE},
    },
    "alarmPolicyInfo": {
        "policyId": "policy-cvm-reboot",
        "policyName": "cvm-guest-reboot",
        "conditions": {
            "productName": "cvm",
            "productShowName": "云服务器",
            "eventName": "guest_reboot",
            "eventShowName": "客户机重启",
        },
    },
    "firstOccurTime": _FIRING_NAIVE,
    "durationTime": 0,
    "recoverTime": "0",
}
TENCENT_RECOVERY_BODY = {
    "sessionId": _TENCENT_SESSION,
    "alarmStatus": "0",
    "alarmType": "event",
    "alarmObjInfo": {
        "region": "ap-guangzhou",
        "namespace": "qce/cvm",
        "appId": _TENCENT_APP,
        "uin": "100001234567",
        "dimensions": {"unInstanceId": _TENCENT_INSTANCE},
    },
    "alarmPolicyInfo": {
        "policyId": "policy-cvm-reboot",
        "policyName": "cvm-guest-reboot",
        "conditions": {
            "productName": "cvm",
            "productShowName": "云服务器",
            "eventName": "guest_reboot",
            "eventShowName": "客户机重启",
        },
    },
    "firstOccurTime": _RECOVERY_NAIVE,
    "durationTime": 600,
    "recoverTime": _RECOVERY_NAIVE,
}
TENCENT_CLOUDEVENT_BODY = {
    "specversion": "1.0",
    "id": "ce-delivery-0001",
    "type": "cvm:ErrorEvent:guest_reboot",
    "source": "cvm.cloud.tencent",
    "subject": _TENCENT_INSTANCE,
    "time": _FIRING_MS,
    "region": "ap-guangzhou",
    "ruleName": "cvm-guest-reboot",
    "data": {
        "appId": _TENCENT_APP,
        "sessionId": _TENCENT_SESSION,
        "status": "1",
    },
}


def _aliyun_examples(webhook_url, credential):
    items = [
        _item(
            "发生：系统错误导致实例重启",
            "订的是 CloudMonitor 过程态，阶段 Executing。data.eventId 才是业务 ID，外层 id 每次投递都变。私网 IP 和公网 IP 只留在 original。",
            "aliyun",
            ALIYUN_FIRING_BODY,
            webhook_url,
            credential,
            ("同一 external_id 已有未关闭告警时，这条挂上去，不新开告警。",),
        ),
        _item(
            "恢复：同一次重启执行完成",
            "type 末尾和 data.eventStatus 改为 Executed。eventId、账号、实例 ID 保持不变。时间晚于发生。",
            "aliyun",
            ALIYUN_RECOVERY_BODY,
            webhook_url,
            credential,
            ("external_id 必须和发生那条相同，平台才关得掉那条告警。",),
        ),
        _item(
            "失败：同一次重启没有成功",
            "阶段是 Failed。动作仍是发生，级别仍按系统错误记为严重。它挂到未关闭告警上，内容里多一个「失败」。",
            "aliyun",
            ALIYUN_FAILED_BODY,
            webhook_url,
            credential,
        ),
        _item(
            "磁盘损坏开始",
            "资源 ID 用 data.diskId，名称用 data.diskName。关联 CMDB 不用磁盘 ID，用 data.ecsInstanceId 去对云主机。",
            "aliyun",
            ALIYUN_DISK_BODY,
            webhook_url,
            credential,
            ("cmdb 查询模型是 aliyun_ecs，查询值是 data.ecsInstanceId，不是 diskId。",),
        ),
        _item(
            "无状态：实例生命周期变化",
            "这是没有 CloudMonitor 过程态的原生事件。动作是 record，级别是提醒，不建告警。另外三条无状态事件用各自的 type，字段位置相同。",
            "aliyun",
            ALIYUN_STATE_BODY,
            webhook_url,
            credential,
        ),
    ]
    return _packed(webhook_url, credential, ALIYUN_FIRING_BODY, items, "恢复把阶段改成 Executed，eventId 保持不变。")


def _tencent_examples(webhook_url, credential, query_url):
    items = [
        _item(
            "发生：监控告警模板，客户机重启",
            "alarmType 必须是 event，productName 必须是 cvm，实例在 dimensions.unInstanceId。alarmStatus 为 1。firstOccurTime 没有时区，按东八区。eventShowName 不参与标题。",
            "tencent",
            TENCENT_FIRING_BODY,
            webhook_url,
            credential,
            ("本例带了 appId，所以账号会写入。官方模板如果没有 appId、uin、ownerUin，external_id 会以冒号开头。",),
        ),
        _item(
            "恢复：同一 sessionId，alarmStatus 改为 0",
            "sessionId、实例 ID、appId 保持不变。firstOccurTime 要晚于发生，这里是 10 分钟后。",
            "tencent",
            TENCENT_RECOVERY_BODY,
            webhook_url,
            credential,
        ),
        _item(
            "发生：CloudEvent",
            "specversion 和 type 用来识别这种正文。实例 ID 只读 subject，不读 dimensions。状态在 data.status。sessionId 在 data 里。time 已经是毫秒。投递 ID 是外层 id，不参与 external_id。",
            "tencent",
            TENCENT_CLOUDEVENT_BODY,
            webhook_url,
            credential,
        ),
    ]
    if query_url:
        items.append(
            _item(
                "控制台不能加请求头",
                "地址使用查询参数 secret，值是同一枚组织密钥。这条请求不要再带 SECRET 头。正文和上面的发生报文相同。",
                "tencent",
                TENCENT_FIRING_BODY,
                query_url,
                credential,
                header=False,
            )
        )
    note = "恢复把 alarmStatus 改为 0，sessionId 保持不变。产品必须是 cvm。"
    return _packed(webhook_url, credential, TENCENT_FIRING_BODY, items, note, query_url)


def _packed(webhook_url, credential, firing, items, note, query_url=None):
    return {
        "CURL": "\n\n".join(item["curl"] for item in items),
        "Python": _python(webhook_url, credential, firing, note, query_url),
        "items": items,
    }


def _item(title, explain, vendor, body, url, credential, notes=(), header=True):
    return {
        "title": title,
        "explain": explain,
        "lands": _lands(vendor, body, notes),
        "curl": _curl(url, credential, body, title, header=header),
    }


def _lands(vendor, body, notes):
    parsed = parse_body(vendor, body)
    event = parsed.get("event") or {}
    lines = []
    for key in (
        "title",
        "description",
        "level",
        "item",
        "action",
        "external_id",
        "resource_id",
        "resource_name",
        "resource_type",
        "location",
        "start_time",
        "labels",
        "rule_id",
    ):
        value = event.get(key)
        if value in (None, "", [], {}):
            continue
        if isinstance(value, (dict, list)):
            shown = json.dumps(value, ensure_ascii=False)
        else:
            shown = str(value)
        lines.append(f"{key} = {shown}")
    lines.extend(notes)
    return lines


def _curl(url, credential, body, comment, header=True):
    payload = json.dumps(body, ensure_ascii=False, indent=2)
    lines = [f"# {comment}", f"curl --location --request POST '{url}' \\"]
    if header:
        lines.append(f"  --header 'SECRET: {credential}' \\")
    lines.append("  --header 'Content-Type: application/json' \\")
    lines.append(f"  --data-raw '{payload}'")
    return "\n".join(lines)


def _python(url, credential, body, note, query_url=None):
    payload = json.dumps(body, ensure_ascii=False, indent=4)
    secret = json.dumps(credential, ensure_ascii=False)
    lines = [
        "import json",
        "import requests",
        "",
        f"url = {json.dumps(url, ensure_ascii=False)}",
        f"headers = {{'SECRET': {secret}, 'Content-Type': 'application/json'}}",
        f"body = {payload}",
        f"# {note}",
        "response = requests.post(url, headers=headers, data=json.dumps(body, ensure_ascii=False))",
        "print(response.status_code, response.text)",
    ]
    if query_url:
        lines.append(f"# 不能加请求头时改用 {query_url} ，并且不要再带 SECRET 头。")
    return "\n".join(lines)

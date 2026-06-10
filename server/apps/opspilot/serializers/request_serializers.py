"""请求体校验序列化器。

集中存放仅用于校验入站请求体的 DRF 序列化器，避免视图/动作直接对
``request.data`` 做原始字典访问（KeyError -> 500）。这些序列化器只负责
输入校验，不参与响应输出，因此不会改变任何前端读取的响应结构。

字段的可选/必填与默认值严格对齐前端实际发送的载荷：
- 前端始终发送的字段在缺失时返回干净的 400（required）。
- 前端可能省略的字段保持可选并提供与原视图一致的默认值。
"""

from rest_framework import serializers


class BatchTrainRequestSerializer(serializers.Serializer):
    """knowledge_document 的 batch_train 动作请求体。

    前端（web knowledge.ts batchTrainDocuments）发送：
        {knowledge_document_ids: number[], delete_qa_pairs: boolean}

    - knowledge_document_ids: 原视图通过 ``pop(..., [])`` 容忍缺失，故保持可选，默认空列表。
      同时兼容原视图“非 list 自动包装为单元素 list”的行为。
    - delete_qa_pairs: 原视图为 ``kwargs["delete_qa_pairs"]`` 原始访问（缺失会 500）。
      前端始终发送布尔值；此处保持可选并默认 True 以避免 KeyError 且不改变成功路径行为。
    """

    knowledge_document_ids = serializers.ListField(child=serializers.IntegerField(), required=False, default=list)
    delete_qa_pairs = serializers.BooleanField(required=False, default=True)

    def to_internal_value(self, data):
        # 兼容原视图：knowledge_document_ids 传入非 list（如单个 id）时包装为 list
        if isinstance(data, dict):
            raw = data.get("knowledge_document_ids", None)
            if raw is not None and not isinstance(raw, (list, tuple)):
                data = dict(data)
                data["knowledge_document_ids"] = [raw]
        return super().to_internal_value(data)


class DeleteChunksRequestSerializer(serializers.Serializer):
    """knowledge_document 的 delete_chunks 动作请求体。

    前端（web knowledge.ts deleteChunks）发送：
        {knowledge_base_id: number, ids: string[], delete_all: boolean}

    - ids: 原视图为 ``params["ids"]`` 原始访问（缺失会 500）。前端始终发送，
      标记为 required 以返回干净的 400。
    - knowledge_base_id: 原视图通过 ``get(..., 0)`` 容忍缺失，保持可选，默认 0。
    - delete_all: 原视图通过 ``get(..., False)`` 容忍缺失，保持可选，默认 False。
    """

    ids = serializers.ListField(child=serializers.CharField(), allow_empty=True)
    knowledge_base_id = serializers.IntegerField(required=False, default=0)
    delete_all = serializers.BooleanField(required=False, default=False)


class SubmitApprovalRequestSerializer(serializers.Serializer):
    """bot_mgmt submit_approval 请求体。

    前端（ApprovalCard）发送：
        {execution_id, node_id, tool_call_id, decision, reason?}

    - execution_id / node_id / tool_call_id / decision: 原视图要求全部非空（all([...])），
      标记为 required + 非空。decision 限定为 approve / reject。
    - reason: 前端可选发送，保持可选，默认空字符串（与原 ``get("reason", "")`` 一致）。
    """

    execution_id = serializers.CharField(allow_blank=False)
    node_id = serializers.CharField(allow_blank=False)
    tool_call_id = serializers.CharField(allow_blank=False)
    decision = serializers.ChoiceField(choices=("approve", "reject"))
    reason = serializers.CharField(required=False, allow_blank=True, default="")


class SubmitChoiceRequestSerializer(serializers.Serializer):
    """bot_mgmt submit_choice 请求体。

    前端（UserChoiceCard）发送：
        {execution_id, node_id, choice_id, selected}

    - execution_id / node_id / choice_id: 原视图要求全部非空，标记为 required + 非空。
    - selected: 原视图要求为非空 list，标记为 required + allow_empty=False。
    """

    execution_id = serializers.CharField(allow_blank=False)
    node_id = serializers.CharField(allow_blank=False)
    choice_id = serializers.CharField(allow_blank=False)
    selected = serializers.ListField(allow_empty=False)


class InterruptChatFlowRequestSerializer(serializers.Serializer):
    """bot_mgmt interrupt_chat_flow_execution 请求体。

    - execution_id: 原视图要求非空，标记为 required + 非空。
    - reason: 原视图通过 ``get("reason", "user_manual")`` 容忍缺失，保持可选并使用同一默认值。
    """

    execution_id = serializers.CharField(allow_blank=False)
    reason = serializers.CharField(required=False, allow_blank=True, default="user_manual")

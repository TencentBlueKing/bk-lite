from django.db.models import Min
from django_filters import filters
from django_filters.rest_framework import FilterSet
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.opspilot.models import ChatApplication, WorkFlowConversationHistory
from apps.opspilot.models.bot_mgmt import BotWorkFlow
from apps.opspilot.models.model_provider_mgmt import LLMSkill
from apps.opspilot.serializers.chat_application_serializer import ChatApplicationSerializer


class ChatApplicationFilter(FilterSet):
    """聊天应用过滤器"""

    app_name = filters.CharFilter(field_name="app_name", lookup_expr="icontains")
    app_type = filters.ChoiceFilter(field_name="app_type", choices=ChatApplication.APP_TYPE_CHOICES)
    bot = filters.NumberFilter(field_name="bot_id")
    app_tags = filters.CharFilter(method="filter_app_tags")

    class Meta:
        model = ChatApplication
        fields = ["app_name", "app_type", "bot", "app_tags"]

    def filter_app_tags(self, queryset, name, value):
        """
        过滤包含指定标签的应用
        支持单个标签匹配（app_tags字段为JSON数组）
        """
        if value:
            return queryset.filter(app_tags__contains=[value])
        return queryset


class ChatApplicationViewSet(viewsets.ReadOnlyModelViewSet):
    """
    聊天应用视图集

    只提供查询功能,不支持创建、修改和删除
    应用由 BotWorkFlow 保存时自动同步生成
    """

    serializer_class = ChatApplicationSerializer
    queryset = ChatApplication.objects.select_related("bot").all()
    permission_key = "chat_application"
    filterset_class = ChatApplicationFilter
    ordering_fields = ["id", "app_name", "app_type"]
    search_fields = ["app_name", "app_description"]

    def get_queryset(self):
        """根据用户团队过滤应用"""
        queryset = super().get_queryset()

        # 如果不是超级用户，只返回用户所属团队的应用
        if not self.request.user.is_superuser:
            current_team = self.request.COOKIES.get("current_team")
            if current_team:
                queryset = queryset.filter(bot__team__contains=[int(current_team)])

        return queryset

    @action(detail=False, methods=["get"])
    def web_chat_sessions(self, request):
        """
        获取用户的 web_chat 会话列表

        根据当前用户的 username@domain 构造 user_id，
        筛选 entry_type 为 web_chat 且 session_id 不为空的对话历史，
        按 session_id 分组并取每组第一条记录的内容作为标题

        Query Parameters:
            bot_id (int, optional): 机器人ID，用于过滤特定机器人的会话

        返回格式: [{"session_id": "xxx", "title": "xxx"}]
        """
        # 拼接 user_id
        username = request.user.username
        domain = getattr(request.user, "domain", "")
        user_id = f"{username}@{domain}" if domain else username

        # 构建查询条件
        filter_kwargs = {
            "user_id": user_id,
            "entry_type": "web_chat",
            "conversation_role": "user",  # 只取用户输入作为标题
        }

        # 如果提供了 bot_id 参数，添加过滤条件
        bot_id = request.query_params.get("bot_id")
        if bot_id:
            filter_kwargs["bot_id"] = bot_id

        # 查询符合条件的对话历史，按 session_id 分组取最早的一条
        sessions = (
            WorkFlowConversationHistory.objects.filter(**filter_kwargs)
            .exclude(session_id="")  # 过滤 session_id 为空
            .values("session_id")  # 按 session_id 分组
            .annotate(first_time=Min("conversation_time"))  # 获取每组最早时间
            .order_by("-first_time")  # 按时间倒序
        )

        # 获取每个 session_id 的第一条记录内容作为标题
        result = []
        for session in sessions:
            session_id = session["session_id"]

            # 构建查询第一条记录的条件
            first_record_kwargs = {
                "user_id": user_id,
                "entry_type": "web_chat",
                "session_id": session_id,
                "conversation_role": "user",
            }
            if bot_id:
                first_record_kwargs["bot_id"] = bot_id

            first_record = WorkFlowConversationHistory.objects.filter(**first_record_kwargs).order_by("conversation_time").first()

            if first_record:
                # 取对话内容的前50个字符作为标题
                title = first_record.conversation_content[:50]
                if len(first_record.conversation_content) > 50:
                    title += "..."

                result.append({"session_id": session_id, "title": title})

        return Response(result)

    @action(detail=False, methods=["get"])
    def session_messages(self, request):
        """
        获取指定会话的全部对话内容

        Query Parameters:
            session_id (str, required): 会话ID

        返回格式: [
            {
                "id": 1,
                "bot_id": 1,
                "node_id": "web-chat-123",
                "user_id": "user@domain",
                "conversation_role": "user",
                "conversation_content": "内容",
                "conversation_time": "2025-12-04T10:00:00Z",
                "entry_type": "web_chat",
                "session_id": "session-123"
            }
        ]
        """
        session_id = request.query_params.get("session_id")

        if not session_id:
            return Response({"error": "session_id 参数是必填的"}, status=400)

        # 拼接 user_id
        username = request.user.username
        domain = getattr(request.user, "domain", "")
        user_id = f"{username}@{domain}" if domain else username

        # 查询该会话的所有对话记录
        messages = (
            WorkFlowConversationHistory.objects.filter(user_id=user_id, session_id=session_id, entry_type="web_chat")
            .order_by("conversation_time")
            .values(
                "id", "bot_id", "node_id", "user_id", "conversation_role", "conversation_content", "conversation_time", "entry_type", "session_id"
            )
        )

        return Response(list(messages))

    @action(detail=False, methods=["get"])
    def skill_guide(self, request):
        """
        获取工作流中第一个 LLM 节点对应的技能引导信息

        根据 bot_id 和 node_id，查找从该节点出发最短路径上第一个包含 LLM 模型的节点，
        然后返回该 LLM 节点关联的 LLMSkill 的 guide 字段

        Query Parameters:
            bot_id (int, required): 机器人ID
            node_id (str, required): 起始节点ID

        返回格式: {"guide": "技能引导内容"}
        """
        bot_id = request.query_params.get("bot_id")
        node_id = request.query_params.get("node_id")

        if not bot_id:
            return Response({"error": "bot_id 参数是必填的"}, status=400)
        if not node_id:
            return Response({"error": "node_id 参数是必填的"}, status=400)

        try:
            # 获取工作流数据
            workflow = BotWorkFlow.objects.filter(bot_id=bot_id).first()
            if not workflow:
                return Response({"error": "未找到对应的工作流"}, status=404)

            flow_json = workflow.flow_json
            if not flow_json:
                return Response({"error": "工作流数据为空"}, status=404)

            # 解析节点和边
            nodes = {node["id"]: node for node in flow_json.get("nodes", [])}
            edges = flow_json.get("edges", [])

            # 构建邻接表（图结构）
            graph = {}
            for edge in edges:
                source = edge.get("source")
                target = edge.get("target")
                if source not in graph:
                    graph[source] = []
                graph[source].append(target)

            # BFS 查找最短路径上第一个 LLM 节点
            from collections import deque

            queue = deque([node_id])
            visited = {node_id}

            llm_skill_id = None

            while queue:
                current_node_id = queue.popleft()

                # 检查当前节点是否有 LLM 模型配置
                current_node = nodes.get(current_node_id)
                if current_node:
                    node_data = current_node.get("data", {})
                    node_config = node_data.get("config", {})

                    # 检查是否有 skill_id（LLM 节点特征）
                    skill_id = node_config.get("agent")
                    if skill_id:
                        llm_skill_id = skill_id
                        break

                # 继续遍历下一层节点
                if current_node_id in graph:
                    for next_node_id in graph[current_node_id]:
                        if next_node_id not in visited:
                            visited.add(next_node_id)
                            queue.append(next_node_id)

            # 如果没找到 LLM 节点
            if not llm_skill_id:
                return Response({"guide": ""})

            # 查找对应的 LLMSkill
            llm_skill = LLMSkill.objects.filter(id=llm_skill_id).first()
            if not llm_skill:
                return Response({"guide": ""})

            return Response({"guide": llm_skill.guide or ""})

        except Exception as e:
            return Response({"error": f"查询失败: {str(e)}"}, status=500)

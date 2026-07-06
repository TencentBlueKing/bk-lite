import json

from django.db.models import Min, Q
from django_filters import filters
from django_filters.rest_framework import FilterSet
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from apps.core.decorators.api_permission import HasPermission
from apps.core.logger import opspilot_logger as logger
from apps.opspilot.models import ChatApplication, WorkFlowConversationHistory
from apps.opspilot.models.bot_mgmt import BotWebChatSession, BotWorkFlow
from apps.opspilot.models.model_provider_mgmt import LLMSkill
from apps.opspilot.serializers.chat_application_serializer import ChatApplicationSerializer
from apps.opspilot.utils.team_permission_mixin import TeamPermissionMixin


def _current_user_candidates(request):
    """构造当前 web 用户的身份候选集（username + username@domain）。

    参与者授权同时兼容两种 NATS 调用方约定的 user_id 格式。
    """
    user = request.user
    username = getattr(user, "username", "") or ""
    domain = getattr(user, "domain", "") or ""
    candidates = {username}
    if domain:
        candidates.add(f"{username}@{domain}")
    return candidates


def _filter_sessions_by_user(session_qs, request):
    """对 BotWebChatSession queryset 应用参与者授权过滤。

    匹配规则：当前用户在 participants 中（username 或 username@domain 任一命中即视为干系人）。
    """
    candidates = _current_user_candidates(request)
    user_filter = Q()
    for cand in candidates:
        user_filter |= Q(participants__contains=cand)
    return session_qs.filter(user_filter)


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


class ChatApplicationViewSet(TeamPermissionMixin, viewsets.ReadOnlyModelViewSet):
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

        # 验证 current_team 权限
        current_team = self._validate_current_team_permission(self.request)

        # 如果不是超级用户，只返回用户所属团队的应用
        if not self.request.user.is_superuser:
            # 检查用户是否属于 OpsPilotGuest 顶级组，若有则同时纳入该组的数据
            guest_group_ids = {
                int(group["id"])
                for group in getattr(self.request.user, "group_list", [])
                if isinstance(group, dict) and group.get("name") == "OpsPilotGuest" and group.get("id") is not None
            }
            team_filter = Q(bot__team__contains=[current_team])
            for gid in guest_group_ids:
                team_filter |= Q(bot__team__contains=[gid])
            queryset = queryset.filter(team_filter)

        return queryset

    @HasPermission("bot_list-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("bot_list-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @action(detail=False, methods=["get"])
    @HasPermission("bot_list-View")
    def web_chat_sessions(self, request):
        """
        获取用户的 web_chat 会话列表

        根据当前用户的 username@domain 构造 user_id，
        筛选 entry_type 为 web_chat 且 session_id 不为空的对话历史，
        按 session_id 分组并取每组第一条记录的内容作为标题

        Query Parameters:
            bot_id (int, optional): 机器人ID，用于过滤特定机器人的会话

        返回格式: [{"session_id": "xxx", "title": "xxx", "bot_id": ..., "source": "..."}]
        """
        # 拼接 user_id
        username = request.user.username
        domain = getattr(request.user, "domain", "")
        user_id = f"{username}@{domain}" if domain else username

        entry_type = request.GET.get("entry_type", "web_chat")
        node_id = request.GET.get("node_id")
        # 构建查询条件
        filter_kwargs = {
            "user_id": user_id,
            "entry_type": entry_type,
            "conversation_role": "user",  # 只取用户输入作为标题
            "node_id": node_id,
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

        result = []
        seen_session_ids = set()
        for session in sessions:
            session_id = session["session_id"]

            # 复用外层的查询条件，添加 session_id
            first_record = WorkFlowConversationHistory.objects.filter(**filter_kwargs, session_id=session_id).order_by("conversation_time").first()

            if first_record:
                # 取对话内容的前50个字符作为标题
                title = first_record.conversation_content[:50]
                if len(first_record.conversation_content) > 50:
                    title += "..."

                result.append(
                    {
                        "session_id": session_id,
                        "title": title,
                        "bot_id": first_record.bot_id,
                        "source": entry_type,
                    }
                )
                seen_session_ids.add(session_id)

        # 附加：当前用户作为干系人的 BotWebChatSession 会话（NATS 触发场景）
        session_qs = BotWebChatSession.objects.filter(is_active=True)
        if bot_id:
            session_qs = session_qs.filter(bot_id=bot_id)
        if node_id:
            session_qs = session_qs.filter(node_id=node_id)
        session_qs = _filter_sessions_by_user(session_qs, request).order_by("-created_at")

        for sess in session_qs:
            if sess.session_id in seen_session_ids:
                continue
            result.append(
                {
                    "session_id": sess.session_id,
                    "title": sess.title,
                    "bot_id": sess.bot_id,
                    "source": sess.source,
                    "created_at": sess.created_at.isoformat() if sess.created_at else None,
                }
            )

        return Response(result)

    @action(detail=False, methods=["get"])
    @HasPermission("bot_list-View")
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
            return Response({"result": False, "message": "session_id 参数是必填的"}, status=400)

        # 优先查 BotWebChatSession（覆盖 NATS / 暴露场景）：做参与者授权
        web_session = BotWebChatSession.objects.filter(session_id=session_id).first()
        if web_session is not None:
            if not web_session.is_participant(request.user):
                raise PermissionDenied("当前用户不在该会话的干系人列表中")
            messages = (
                WorkFlowConversationHistory.objects.filter(session_id=session_id)
                .order_by("conversation_time")
                .values(
                    "id",
                    "bot_id",
                    "node_id",
                    "user_id",
                    "conversation_role",
                    "conversation_content",
                    "conversation_time",
                    "entry_type",
                    "session_id",
                )
            )
            return_data = []
            for i in messages:
                obj = dict(i, **{})
                try:
                    obj["conversation_content"] = json.loads(i["conversation_content"])
                except Exception:
                    pass
                return_data.append(obj)
            return Response(return_data)

        # 兼容旧路径：owner == {username}@{domain} 的 web_chat / mobile 会话
        username = request.user.username
        domain = getattr(request.user, "domain", "")
        user_id = f"{username}@{domain}" if domain else username

        # 查询该会话的所有对话记录
        messages = (
            WorkFlowConversationHistory.objects.filter(
                user_id=user_id,
                session_id=session_id,
                entry_type__in=["web_chat", "mobile"],
            )
            .order_by("conversation_time")
            .values(
                "id",
                "bot_id",
                "node_id",
                "user_id",
                "conversation_role",
                "conversation_content",
                "conversation_time",
                "entry_type",
                "session_id",
            )
        )
        return_data = []
        for i in messages:
            obj = dict(i, **{})
            try:
                obj["conversation_content"] = json.loads(i["conversation_content"])
            except Exception:
                pass
            return_data.append(obj)
        return Response(return_data)

    @action(detail=False, methods=["get"])
    @HasPermission("bot_list-View")
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
            return Response({"result": False, "message": "bot_id 参数是必填的"}, status=400)
        if not node_id:
            return Response({"result": False, "message": "node_id 参数是必填的"}, status=400)

        try:
            # 获取工作流数据
            workflow = BotWorkFlow.objects.filter(bot_id=bot_id).first()
            if not workflow:
                return Response({"result": False, "message": "未找到对应的工作流"}, status=404)

            flow_json = workflow.flow_json
            if not flow_json:
                return Response({"result": False, "message": "工作流数据为空"}, status=404)

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
            logger.exception("skill_guide query failed: bot_id=%s, node_id=%s", bot_id, node_id)
            return Response({"result": False, "message": f"查询失败: {str(e)}"}, status=500)

    @action(detail=False, methods=["POST"])
    @HasPermission("bot_list-View")
    def delete_session_history(self, request):
        """
        删除指定会话的对话历史

        Query Parameters:
            node_id (str, required): 节点ID
            session_id (str, required): 会话ID

        仅删除当前用户的会话历史记录
        """
        node_id = request.data.get("node_id")
        session_id = request.data.get("session_id")

        if not node_id:
            return Response({"result": False, "message": "node_id 参数是必填的"}, status=400)
        if not session_id:
            return Response({"result": False, "message": "session_id 参数是必填的"}, status=400)

        # 优先按 BotWebChatSession 做参与者授权（NAT / 暴露场景）
        web_session = BotWebChatSession.objects.filter(session_id=session_id).first()
        if web_session is not None:
            if not web_session.is_participant(request.user):
                raise PermissionDenied("当前用户不在该会话的干系人列表中")
            deleted_count, _ = WorkFlowConversationHistory.objects.filter(session_id=session_id).delete()
            web_session.is_active = False
            web_session.save(update_fields=["is_active", "updated_at"])
            logger.info(f"Soft-deleted BotWebChatSession {session_id} by user={request.user.username}, " f"history deleted count={deleted_count}")
            return Response({"result": True})

        # 旧路径：owner == {username}@{domain} 的 web_chat / mobile 会话
        username = request.user.username
        domain = getattr(request.user, "domain", "")
        user_id = f"{username}@{domain}" if domain else username

        deleted_count, _ = WorkFlowConversationHistory.objects.filter(user_id=user_id, node_id=node_id, session_id=session_id).delete()

        logger.info(f"Deleted {deleted_count} conversation history records for user={user_id}, node_id={node_id}, session_id={session_id}")

        return Response({"result": True})

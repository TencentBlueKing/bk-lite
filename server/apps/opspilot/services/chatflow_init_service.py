import json
from pathlib import Path

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.models import Bot, BotWorkFlow, LLMSkill, SkillTools


class ChatFlowInitService:
    """ChatFlow 初始化服务

    从 chatflow_data 目录读取配置，初始化内置的 ChatFlow Bot。
    每个 chatflow 包含：
    - check.txt: 巡检 prompt（用于创建主 LLMSkill）
    - format.txt: 格式化 prompt（用于创建格式化 LLMSkill）
    - workflow.json: chatflow 工作流配置
    """

    CHATFLOW_DATA_DIR = Path(__file__).parent.parent / "management" / "chatflow_data"
    DEFAULT_CREATED_BY = "admin"
    DEFAULT_DOMAIN = "domain.com"
    DEFAULT_TEAM = [1]

    # LLMSkill 默认配置（公共部分）
    DEFAULT_SKILL_CONFIG = {
        "enable_conversation_history": False,
        "conversation_window_size": 10,
        "enable_rag": False,
        "enable_rag_knowledge_source": False,
        "rag_score_threshold_map": {},
        "temperature": 0.7,
        "enable_rag_strict_mode": False,
        "is_template": False,
        "enable_km_route": False,
        "enable_suggest": False,
        "enable_query_rewrite": False,
        "show_think": False,
        "team": [1],
        "created_by": "admin",
        "domain": "domain.com",
    }

    def __init__(self):
        pass

    def _build_tools_list(self, tool_names: list) -> list:
        """根据工具名称列表构建 tools JSON

        Args:
            tool_names: 工具名称列表，如 ["postgres", "kubernetes"]

        Returns:
            tools JSON 列表，包含 id, name, icon, kwargs
        """
        if not tool_names:
            return []

        tools_list = []
        for tool_name in tool_names:
            skill_tool = SkillTools.objects.filter(name=tool_name).first()
            if not skill_tool:
                logger.warning(f"SkillTools 不存在: {tool_name}")
                continue

            # 构建 kwargs 列表
            kwargs = []
            for key, param_info in skill_tool.params.items():
                kwargs.append(
                    {
                        "key": key,
                        "type": param_info.get("type", "text"),
                        "value": param_info.get("default", ""),
                        "isRequired": param_info.get("required", False),
                        "description": param_info.get("description", ""),
                    }
                )

            tools_list.append(
                {
                    "id": skill_tool.id,
                    "name": skill_tool.name,
                    "icon": skill_tool.icon or "gongjuji",
                    "kwargs": kwargs,
                }
            )

        return tools_list

    def init(self):
        """初始化所有配置的 chatflow"""
        config_path = self.CHATFLOW_DATA_DIR / "config.json"

        if not config_path.exists():
            logger.warning(f"ChatFlow 配置文件不存在: {config_path}")
            return

        with open(config_path, "r", encoding="utf-8") as f:
            chatflow_configs = json.load(f)

        for config in chatflow_configs:
            try:
                self._init_single_chatflow(config)
            except Exception as e:
                logger.exception(f"初始化 ChatFlow [{config.get('id')}] 失败: {e}")

    def _init_single_chatflow(self, config: dict):
        """初始化单个 chatflow

        Args:
            config: chatflow 配置，包含 id, name, format_skill_name, description, tools, check_skill_type, format_skill_type
        """
        chatflow_id = config["id"]
        chatflow_name = config["name"]
        format_skill_name = config["format_skill_name"]
        description = config.get("description", "")
        tool_names = config.get("tools", [])
        check_skill_type = config.get("check_skill_type", 1)
        format_skill_type = config.get("format_skill_type", 2)

        chatflow_dir = self.CHATFLOW_DATA_DIR / chatflow_id

        if not chatflow_dir.exists():
            logger.warning(f"ChatFlow 目录不存在: {chatflow_dir}")
            return

        # 读取 prompt 文件
        check_prompt = self._read_file(chatflow_dir / "check.txt")
        format_prompt = self._read_file(chatflow_dir / "format.txt")
        workflow_json = self._read_json(chatflow_dir / "workflow.json")

        if not check_prompt or not format_prompt or not workflow_json:
            logger.warning(f"ChatFlow [{chatflow_id}] 配置文件不完整，跳过")
            return

        # 构建 tools 列表
        tools_list = self._build_tools_list(tool_names)

        # 创建或更新主 LLMSkill（巡检）
        main_skill = LLMSkill.objects.filter(
            name=chatflow_name,
            created_by=self.DEFAULT_CREATED_BY,
            domain=self.DEFAULT_DOMAIN,
        ).first()
        if main_skill:
            # 已存在，更新但不修改 team 和 tools
            main_skill.skill_prompt = check_prompt
            main_skill.introduction = description
            main_skill.save()
        else:
            # 新建，设置完整参数
            main_skill = LLMSkill.objects.create(
                name=chatflow_name,
                skill_prompt=check_prompt,
                introduction=description,
                skill_type=check_skill_type,
                tools=tools_list,
                **self.DEFAULT_SKILL_CONFIG,
            )
        logger.info(f"创建/更新 LLMSkill: {chatflow_name} (ID: {main_skill.id})")

        # 创建或更新格式化 LLMSkill
        format_skill = LLMSkill.objects.filter(
            name=format_skill_name,
            created_by=self.DEFAULT_CREATED_BY,
            domain=self.DEFAULT_DOMAIN,
        ).first()
        if format_skill:
            # 已存在，更新但不修改 team
            format_skill.skill_prompt = format_prompt
            format_skill.introduction = f"{chatflow_name} 数据格式化"
            format_skill.save()
        else:
            # 新建，设置完整参数
            format_skill = LLMSkill.objects.create(
                name=format_skill_name,
                skill_prompt=format_prompt,
                introduction=f"{chatflow_name} 数据格式化",
                skill_type=format_skill_type,
                tools=[],
                **self.DEFAULT_SKILL_CONFIG,
            )
        logger.info(f"创建/更新 LLMSkill: {format_skill_name} (ID: {format_skill.id})")

        # 更新 workflow.json 中的 agent ID
        updated_workflow = self._update_workflow_agent_ids(
            workflow_json,
            chatflow_name,
            main_skill.id,
            format_skill_name,
            format_skill.id,
        )

        # 创建或更新 Bot
        bot = Bot.objects.filter(
            name=chatflow_name,
            created_by=self.DEFAULT_CREATED_BY,
            domain=self.DEFAULT_DOMAIN,
        ).first()
        if bot:
            # 已存在，更新但不修改 team
            bot.introduction = description
            bot.online = False
            bot.save()
        else:
            # 新建，设置 team
            bot = Bot.objects.create(
                name=chatflow_name,
                created_by=self.DEFAULT_CREATED_BY,
                domain=self.DEFAULT_DOMAIN,
                introduction=description,
                online=False,
                team=self.DEFAULT_TEAM,
            )
        logger.info(f"创建/更新 Bot: {chatflow_name} (ID: {bot.id})")

        # 创建或更新 BotWorkFlow
        BotWorkFlow.objects.update_or_create(
            bot=bot,
            defaults={
                "flow_json": updated_workflow,
                "web_json": updated_workflow,
            },
        )
        logger.info(f"创建/更新 BotWorkFlow for Bot: {chatflow_name}")

    def _read_file(self, path: Path) -> str | None:
        """读取文本文件"""
        if not path.exists():
            logger.warning(f"文件不存在: {path}")
            return None

        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def _read_json(self, path: Path) -> dict | None:
        """读取 JSON 文件"""
        if not path.exists():
            logger.warning(f"文件不存在: {path}")
            return None

        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _update_workflow_agent_ids(
        self,
        workflow: dict,
        main_skill_name: str,
        main_skill_id: int,
        format_skill_name: str,
        format_skill_id: int,
    ) -> dict:
        """更新 workflow 中的 agent ID

        遍历 workflow 的所有节点，根据 agentName 匹配并更新 agent ID。

        Args:
            workflow: workflow 配置
            main_skill_name: 主技能名称
            main_skill_id: 主技能 ID
            format_skill_name: 格式化技能名称
            format_skill_id: 格式化技能 ID

        Returns:
            更新后的 workflow 配置
        """
        nodes = workflow.get("nodes", [])

        for node in nodes:
            if node.get("type") != "agents":
                continue

            config = node.get("data", {}).get("config", {})
            agent_name = config.get("agentName", "")

            if agent_name == main_skill_name:
                config["agent"] = main_skill_id
                logger.debug(f"更新节点 {node['id']} 的 agent ID 为 {main_skill_id}")
            elif agent_name == format_skill_name:
                config["agent"] = format_skill_id
                logger.debug(f"更新节点 {node['id']} 的 agent ID 为 {format_skill_id}")

        return workflow

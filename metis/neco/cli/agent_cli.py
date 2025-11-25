"""
Agent CLI

通过 YAML 配置文件执行各种类型的 Agent（ReAct、Deep、Supervisor、Chatbot）。
支持参数透传，配置文件中的所有参数直接传递给对应的 Agent Request 对象。

使用方法（推荐使用 uvx）:
    # 使用 uvx（推荐，无需安装）
    uvx --from . neco-agent run --config=agents.yml --agent=research_agent --message="帮我搜索 Python 最佳实践"
    uvx --from . neco-agent run_all --config=agents.yml --message="帮我搜索 Python 最佳实践"
    uvx --from . neco-agent validate --config=agents.yml
    uvx --from . neco-agent list --config=agents.yml
    
    # 或使用 uv run（需要项目环境）
    uv run python -m neco.cli.agent_cli run --config=agents.yml --agent=research_agent --message="..."
    
    # 或安装后直接使用命令
    uv pip install -e .
    neco-agent run --config=agents.yml --agent=research_agent --message="..."
"""

import asyncio
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import fire
import yaml
from loguru import logger

from neco.llm.agent.chatbot_workflow import ChatBotWorkflowGraph, ChatBotWorkflowRequest
from neco.llm.agent.deep_agent import DeepAgentGraph, DeepAgentRequest
from neco.llm.agent.react_agent import ReActAgentGraph, ReActAgentRequest
from neco.llm.agent.supervisor_multi_agent import (
    AgentConfig,
    SupervisorMultiAgentGraph,
    SupervisorMultiAgentRequest,
)
from neco.llm.chain.entity import ToolsServer


class AgentCLI:
    """Agent CLI 主类"""

    # 支持的 Agent 类型
    SUPPORTED_AGENT_TYPES = ["react", "deep", "supervisor", "chatbot"]

    # 支持的 Backend
    SUPPORTED_BACKENDS = ["local"]

    @staticmethod
    def _substitute_env_vars(value: Any) -> Any:
        """
        递归替换配置中的环境变量

        支持格式：${VAR_NAME} 或 ${VAR_NAME:default_value}

        Args:
            value: 配置值（可能是 str、dict、list 等）

        Returns:
            替换后的值
        """
        if isinstance(value, str):
            # 匹配 ${VAR_NAME} 或 ${VAR_NAME:default}
            pattern = r'\$\{([^}:]+)(?::([^}]*))?\}'

            def replacer(match):
                var_name = match.group(1)
                default_value = match.group(
                    2) if match.group(2) is not None else ""
                env_value = os.environ.get(var_name, default_value)

                if not env_value and not default_value:
                    logger.warning(f"环境变量 ${{{var_name}}} 未设置且无默认值")

                return env_value

            return re.sub(pattern, replacer, value)

        elif isinstance(value, dict):
            return {k: AgentCLI._substitute_env_vars(v) for k, v in value.items()}

        elif isinstance(value, list):
            return [AgentCLI._substitute_env_vars(item) for item in value]

        else:
            return value

    @staticmethod
    def _load_config(config_path: str) -> Dict[str, Any]:
        """
        加载并解析 YAML 配置文件，支持环境变量替换

        支持的环境变量格式：
        - ${VAR_NAME} - 使用环境变量，未设置时为空字符串
        - ${VAR_NAME:default} - 使用环境变量，未设置时使用默认值

        Args:
            config_path: 配置文件路径

        Returns:
            解析后的配置字典（已替换环境变量）

        Raises:
            FileNotFoundError: 配置文件不存在
            yaml.YAMLError: YAML 格式错误
        """
        config_file = Path(config_path)

        if not config_file.exists():
            raise FileNotFoundError(f"配置文件不存在: {config_path}")

        try:
            with config_file.open("r", encoding="utf-8") as f:
                config = yaml.safe_load(f)

            # 递归替换环境变量
            config = AgentCLI._substitute_env_vars(config)

            logger.info(f"成功加载配置文件: {config_path}")
            return config
        except yaml.YAMLError as e:
            logger.error(f"YAML 解析错误: {e}")
            raise

    @staticmethod
    def _validate_config(config: Dict[str, Any]) -> bool:
        """
        验证配置文件的合法性

        Args:
            config: 配置字典

        Returns:
            验证是否通过
        """
        logger.info("开始验证配置文件...")

        # 检查必需字段
        if "agents" not in config:
            logger.error("配置缺少 'agents' 字段")
            return False

        if not isinstance(config["agents"], list):
            logger.error("'agents' 必须是列表类型")
            return False

        if len(config["agents"]) == 0:
            logger.error("'agents' 列表不能为空")
            return False

        # 检查 backend
        backend = config.get("backend", "local")
        if backend not in AgentCLI.SUPPORTED_BACKENDS:
            logger.error(
                f"不支持的 backend: {backend}，支持的类型: {AgentCLI.SUPPORTED_BACKENDS}")
            return False

        # 检查每个 Agent 配置
        agent_names = set()
        for idx, agent_config in enumerate(config["agents"]):
            if not AgentCLI._validate_agent_config(agent_config, idx):
                return False

            # 检查 Agent 名称唯一性
            agent_name = agent_config.get("name")
            if agent_name in agent_names:
                logger.error(f"Agent 名称重复: {agent_name}")
                return False
            agent_names.add(agent_name)

        logger.info("✅ 配置文件验证通过")
        return True

    @staticmethod
    def _validate_agent_config(agent_config: Dict[str, Any], idx: int) -> bool:
        """验证单个 Agent 配置"""
        # 检查必需字段
        if "name" not in agent_config:
            logger.error(f"Agent[{idx}] 缺少 'name' 字段")
            return False

        if "type" not in agent_config:
            logger.error(f"Agent[{idx}] 缺少 'type' 字段")
            return False

        agent_type = agent_config["type"]
        if agent_type not in AgentCLI.SUPPORTED_AGENT_TYPES:
            logger.error(
                f"Agent[{idx}] 不支持的类型: {agent_type}，"
                f"支持的类型: {AgentCLI.SUPPORTED_AGENT_TYPES}"
            )
            return False

        # Supervisor 类型需要 sub_agents
        if agent_type == "supervisor":
            if "sub_agents" not in agent_config:
                logger.error(f"Supervisor Agent[{idx}] 缺少 'sub_agents' 字段")
                return False

            if not isinstance(agent_config["sub_agents"], list):
                logger.error(f"Supervisor Agent[{idx}] 'sub_agents' 必须是列表类型")
                return False

            if len(agent_config["sub_agents"]) == 0:
                logger.error(f"Supervisor Agent[{idx}] 'sub_agents' 不能为空")
                return False

        return True

    @staticmethod
    def _build_tools_servers(tools_config: List[Dict[str, Any]]) -> List[ToolsServer]:
        """
        从配置构建 ToolsServer 列表

        Args:
            tools_config: 工具配置列表

        Returns:
            ToolsServer 对象列表
        """
        if not tools_config:
            return []

        tools_servers = []
        for tool in tools_config:
            tools_server = ToolsServer(**tool)
            tools_servers.append(tools_server)

        return tools_servers

    @staticmethod
    def _build_agent_config_list(sub_agents_config: List[Dict[str, Any]]) -> List[AgentConfig]:
        """
        从配置构建 AgentConfig 列表（用于 Supervisor）

        Args:
            sub_agents_config: 子 Agent 配置列表

        Returns:
            AgentConfig 对象列表
        """
        if not sub_agents_config:
            return []

        agent_configs = []
        for sub_config in sub_agents_config:
            # 提取 tools_servers
            tools_servers = AgentCLI._build_tools_servers(
                sub_config.pop("tools_servers", [])
            )

            # 直接透传所有参数
            agent_cfg = AgentConfig(
                tools_servers=tools_servers,
                **sub_config
            )
            agent_configs.append(agent_cfg)

        return agent_configs

    @staticmethod
    def _build_request(
        config: Dict[str, Any],
        agent_config: Dict[str, Any],
        user_message: str
    ) -> Any:
        """
        通用的请求构建方法，支持参数透传

        参数合并优先级：
        1. agent_config 中的显式配置（优先级最高）
        2. global 中的配置（作为默认值）
        3. user_message（运行时参数）

        Args:
            config: 全局配置
            agent_config: Agent 配置
            user_message: 用户消息

        Returns:
            对应类型的 Request 对象
        """
        agent_type = agent_config["type"]
        global_config = config.get("global", {})

        # 复制 agent_config，避免修改原始配置
        params = agent_config.copy()

        # 移除元数据字段
        params.pop("name", None)
        params.pop("type", None)
        params.pop("description", None)

        # 处理 tools_servers
        tools_config = params.pop("tools_servers", None)
        if tools_config is not None:
            params["tools_servers"] = AgentCLI._build_tools_servers(
                tools_config)

        # 合并 global 配置（agent_config 中未指定的才使用 global）
        for key, value in global_config.items():
            if key not in params:
                params[key] = value

        # 设置 user_message
        params["user_message"] = user_message

        # 根据 Agent 类型构建对应的 Request
        if agent_type == "react":
            return ReActAgentRequest(**params)
        elif agent_type == "deep":
            return DeepAgentRequest(**params)
        elif agent_type == "chatbot":
            return ChatBotWorkflowRequest(**params)
        elif agent_type == "supervisor":
            # Supervisor 特殊处理：构建 sub_agents
            sub_agents_config = params.pop("sub_agents", [])
            params["agents"] = AgentCLI._build_agent_config_list(
                sub_agents_config)
            return SupervisorMultiAgentRequest(**params)
        else:
            raise ValueError(f"不支持的 Agent 类型: {agent_type}")

    async def _execute_agent(self, agent_type: str, request: Any) -> None:
        """
        执行 Agent（流式输出）

        Args:
            agent_type: Agent 类型
            request: Agent 请求对象
        """
        # 根据类型选择对应的 Graph
        graph_cls = {
            "react": ReActAgentGraph,
            "deep": DeepAgentGraph,
            "chatbot": ChatBotWorkflowGraph,
            "supervisor": SupervisorMultiAgentGraph,
        }.get(agent_type)

        if not graph_cls:
            logger.error(f"不支持的 Agent 类型: {agent_type}")
            return

        graph = graph_cls()

        logger.info("开始流式执行...")
        message_stream = await graph.stream(request)

        async for chunk in message_stream:
            content = await graph.filter_messages(chunk)
            if content:
                print(content, end="", flush=True)

        print("\n")

    def run(
        self,
        config: str,
        agent: str,
        message: str,
    ) -> None:
        """
        执行指定的 Agent（流式输出）

        Args:
            config: 配置文件路径
            agent: Agent 名称
            message: 用户消息
        """
        logger.info("=" * 80)
        logger.info(f"🚀 Agent CLI - 执行 Agent")
        logger.info("=" * 80)
        logger.info(f"配置文件: {config}")
        logger.info(f"Agent 名称: {agent}")
        logger.info(f"用户消息: {message}")
        logger.info("=" * 80)

        # 加载配置
        try:
            config_data = self._load_config(config)
        except Exception as e:
            logger.error(f"加载配置失败: {e}")
            return

        # 验证配置
        if not self._validate_config(config_data):
            return

        # 查找 Agent 配置
        agent_config = None
        for cfg in config_data["agents"]:
            if cfg["name"] == agent:
                agent_config = cfg
                break

        if not agent_config:
            logger.error(f"未找到 Agent: {agent}")
            logger.info(
                f"可用的 Agent: {[a['name'] for a in config_data['agents']]}")
            return

        agent_type = agent_config["type"]
        logger.info(f"Agent 类型: {agent_type}")

        # 构建请求（参数透传）
        try:
            request = self._build_request(config_data, agent_config, message)
        except Exception as e:
            logger.error(f"构建请求失败: {e}")
            return

        # 执行 Agent
        asyncio.run(self._execute_agent(agent_type, request))

    def run_all(
        self,
        config: str,
        message: str,
        continue_on_error: bool = True,
    ) -> None:
        """
        执行配置文件中的所有 Agent（流式输出）

        Args:
            config: 配置文件路径
            message: 用户消息
            continue_on_error: 遇到错误时是否继续执行其他 Agent
        """
        logger.info("=" * 80)
        logger.info(f"🚀 Agent CLI - 执行所有 Agent")
        logger.info("=" * 80)
        logger.info(f"配置文件: {config}")
        logger.info(f"用户消息: {message}")
        logger.info(f"遇错继续: {continue_on_error}")
        logger.info("=" * 80)

        # 加载配置
        try:
            config_data = self._load_config(config)
        except Exception as e:
            logger.error(f"加载配置失败: {e}")
            return

        # 验证配置
        if not self._validate_config(config_data):
            return

        agents = config_data.get("agents", [])
        total_agents = len(agents)
        success_count = 0
        failed_agents = []

        logger.info(f"共有 {total_agents} 个 Agent 待执行\n")

        # 遍历执行所有 Agent
        for idx, agent_config in enumerate(agents, 1):
            agent_name = agent_config["name"]
            agent_type = agent_config["type"]

            print("\n" + "=" * 80)
            print(f"[{idx}/{total_agents}] 执行 Agent: {agent_name} ({agent_type})")
            print("=" * 80)

            try:
                # 构建请求（参数透传）
                request = self._build_request(
                    config_data, agent_config, message)

                # 执行 Agent
                asyncio.run(self._execute_agent(agent_type, request))

                logger.info(f"✅ Agent [{agent_name}] 执行完成")
                success_count += 1

            except Exception as e:
                logger.error(f"❌ Agent [{agent_name}] 执行失败: {e}")
                failed_agents.append(agent_name)

                if not continue_on_error:
                    logger.error("遇到错误，停止执行后续 Agent")
                    break

        # 输出总结
        print("\n" + "=" * 80)
        print("📊 执行总结")
        print("=" * 80)

        executed_count = success_count + len(failed_agents)
        print(f"总计: {total_agents} 个 Agent")
        print(f"已执行: {executed_count} 个")
        print(f"成功: {success_count} 个")
        print(f"失败: {len(failed_agents)} 个")

        if failed_agents:
            print("\n失败的 Agent:")
            for name in failed_agents:
                print(f"  - {name}")

        print("=" * 80)

    def validate(self, config: str) -> bool:
        """
        验证配置文件

        Args:
            config: 配置文件路径

        Returns:
            验证是否通过
        """
        logger.info("=" * 80)
        logger.info("🔍 Agent CLI - 验证配置文件")
        logger.info("=" * 80)

        try:
            config_data = self._load_config(config)
            return self._validate_config(config_data)
        except Exception as e:
            logger.error(f"验证失败: {e}")
            return False

    def list(self, config: str) -> None:
        """
        列出配置文件中的所有 Agent

        Args:
            config: 配置文件路径
        """
        logger.info("=" * 80)
        logger.info("📋 Agent CLI - 列出所有 Agent")
        logger.info("=" * 80)

        try:
            config_data = self._load_config(config)
        except Exception as e:
            logger.error(f"加载配置失败: {e}")
            return

        if not self._validate_config(config_data):
            return

        agents = config_data.get("agents", [])

        print(f"\n配置文件: {config}")
        print(f"Backend: {config_data.get('backend', 'local')}")
        print(f"Agent 数量: {len(agents)}\n")

        for idx, agent_config in enumerate(agents, 1):
            print(f"{idx}. {agent_config['name']}")
            print(f"   类型: {agent_config['type']}")
            print(f"   描述: {agent_config.get('description', 'N/A')}")
            print(
                f"   工具: {[t['name'] for t in agent_config.get('tools', [])]}")

            if agent_config["type"] == "supervisor":
                sub_agents = agent_config.get("sub_agents", [])
                print(f"   子 Agent 数量: {len(sub_agents)}")
                for sub in sub_agents:
                    print(
                        f"     - {sub['name']}: {sub.get('description', 'N/A')}")

            print()


def main():
    """主函数"""
    fire.Fire(AgentCLI)


if __name__ == "__main__":
    main()

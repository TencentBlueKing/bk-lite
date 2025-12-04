import json
from typing import Type, TypeVar

import json_repair
from langchain_core.messages import HumanMessage
from langchain_core.output_parsers import PydanticOutputParser
from openai import OpenAI
from pydantic import BaseModel
from loguru import logger

T = TypeVar('T', bound=BaseModel)


class StructuredOutputParser:
    """结构化输出解析器 - 统一使用聊天模式"""

    # 需要禁用thinking模式的模型列表（可以是模型名称的部分匹配）
    THINKING_DISABLED_MODELS = [
        "Qwen",  # Qwen系列模型
    ]

    def __init__(self, llm):
        """
        初始化结构化输出解析器

        Args:
            llm: LangChain LLM实例
        """
        self.llm = llm
        self._independent_llm = None  # 独立的 LLM 实例，不会被 LangGraph 捕获
        
        # 根据配置决定是否禁用thinking模式
        self._configure_thinking_mode()

    def _configure_thinking_mode(self):
        """根据模型配置决定是否禁用thinking模式"""
        model_name = getattr(self.llm, 'model_name', '') or getattr(self.llm, 'model', '')
        
        # 检查当前模型是否在需要禁用thinking的列表中
        should_disable = any(
            disabled_model.lower() in str(model_name).lower() 
            for disabled_model in self.THINKING_DISABLED_MODELS
        )
        
        if should_disable:
            if not hasattr(self.llm, 'extra_body') or self.llm.extra_body is None:
                self.llm.extra_body = {}
            self.llm.extra_body["enable_thinking"] = False

    def _get_openai_client(self):
        """创建一个原生 OpenAI 客户端，完全绕过 LangChain/LangGraph"""
        if self._independent_llm is None:
            # 从 ChatOpenAI 实例获取配置参数
            # openai_api_key 是 SecretStr 类型，需要调用 get_secret_value()
            secret_key = self.llm.openai_api_key
            api_key = secret_key.get_secret_value() if secret_key else None
            base_url = self.llm.openai_api_base
            
            if not api_key:
                raise ValueError("无法从 ChatOpenAI 实例中获取 API key")
            
            # 创建原生 OpenAI 客户端，完全绕过 LangChain，设置合理的超时时间
            kwargs = {
                'api_key': api_key,
                'timeout': 60.0  # 设置60秒超时
            }
            if base_url:
                kwargs['base_url'] = base_url
            
            self._independent_llm = OpenAI(**kwargs)
        
        return self._independent_llm

    async def parse_with_structured_output(self, user_message: str, pydantic_class: Type[T]) -> T:
        """
        使用独立LLM客户端进行结构化输出解析，避免LangGraph消息泄露

        Args:
            user_message: 用户消息内容
            pydantic_class: 目标Pydantic模型类

        Returns:
            T: 解析后的Pydantic模型实例

        Raises:
            ValueError: 解析失败时抛出
        """
        response_text = ""
        try:
            # 创建 PydanticOutputParser
            output_parser = PydanticOutputParser(pydantic_object=pydantic_class)
            
            # 获取格式化指令
            format_instructions = output_parser.get_format_instructions()

            # 构建消息内容
            full_message = f"{user_message}\n\n请按照以下格式要求输出结果：\n{format_instructions}"
            
            # 使用原生 OpenAI SDK，完全绕过 LangChain/LangGraph
            client = self._get_openai_client()
            model_name = getattr(self.llm, 'model_name', None) or getattr(self.llm, 'model', 'gpt-3.5-turbo')
            temperature = getattr(self.llm, 'temperature', 0.7)
            
            # 准备调用参数
            call_kwargs = {
                'model': model_name,
                'messages': [{'role': 'user', 'content': full_message}],
                'temperature': temperature,
            }
            
            # 添加 extra_body 如果存在
            if hasattr(self.llm, 'extra_body') and self.llm.extra_body:
                call_kwargs['extra_body'] = self.llm.extra_body
            
            # 直接调用 OpenAI API，不经过 LangChain
            raw_response = client.chat.completions.create(**call_kwargs)
            response_text = raw_response.choices[0].message.content

            # 使用 PydanticOutputParser 解析响应
            result = output_parser.parse(response_text)
            return result

        except Exception as e:
            logger.warning(f"结构化输出解析失败: {str(e)[:100]}...")
            # 如果 PydanticOutputParser 解析失败，尝试使用 json_repair 作为后备方案
            try:
                if response_text and response_text.strip():
                    data = json_repair.loads(response_text)
                    result = pydantic_class.model_validate(data)
                    return result
                else:
                    # 如果没有响应内容，返回默认实例
                    logger.warning(f"响应内容为空，返回默认的 {pydantic_class.__name__} 实例")
                    return pydantic_class()
            except Exception as fallback_error:
                logger.warning(f"后备解析方案失败，返回默认实例")
                # 如果所有解析都失败，返回模型的默认实例
                try:
                    return pydantic_class()
                except Exception:
                    raise ValueError(f"解析结构化输出失败: {e}")

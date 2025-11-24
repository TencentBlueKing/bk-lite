"""
GraphitiCore OpenAI客户端补丁

解决GraphitiCore使用Azure OpenAI特有的responses.parse API的兼容性问题。
复用项目现有的结构化输出解析机制，提供更好的兼容性和降级支持。
"""

import json
from neco.llm.common.structured_output_parser import StructuredOutputParser
from openai.types.chat import ChatCompletionMessageParam
from pydantic import BaseModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from loguru import logger


class MockResponse:
    """模拟responses.parse的返回结果"""

    def __init__(self, content: str):
        self.output_text = content
        self.refusal = None


class SimplePrompt:
    """简单的prompt包装器，兼容LangChain接口"""

    def __init__(self, messages):
        self.messages = messages

    async def aformat_messages(self, **kwargs):
        """格式化消息"""
        return self.messages


async def patched_create_structured_completion(
    self,
    model: str,
    messages: list[ChatCompletionMessageParam],
    temperature: float | None,
    max_tokens: int,
    response_model: type[BaseModel],
    reasoning: str | None = None,
    verbosity: str | None = None,
):
    """
    替换GraphitiCore的_create_structured_completion方法

    完全使用项目现有的structured_output_parser进行解析，提供完整的降级支持
    """
    logger.debug(f"使用补丁版本的_create_structured_completion，模型: {model}")

    # 创建LangChain兼容的LLM实例
    # 确保base_url是字符串类型
    base_url = str(self.client.base_url) if self.client.base_url else None
    api_key = str(self.client.api_key) if self.client.api_key else None

    llm = ChatOpenAI(
        model=model,
        openai_api_key=api_key,
        openai_api_base=base_url,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=60*5  # 5分钟超时
    )

    # 转换OpenAI消息格式为LangChain消息格式
    langchain_messages = []
    for msg in messages:
        if msg['role'] == 'system':
            langchain_messages.append(SystemMessage(content=msg['content']))
        elif msg['role'] == 'user':
            langchain_messages.append(HumanMessage(content=msg['content']))
        elif msg['role'] == 'assistant':
            # 如果需要支持assistant消息，可以添加AIMessage
            from langchain_core.messages import AIMessage
            langchain_messages.append(AIMessage(content=msg['content']))

    # 使用项目现有的结构化输出解析器
    # 它已经包含了完整的降级机制：GPT原生 -> schema增强 -> 基础schema
    parser = StructuredOutputParser(llm)

    # 将所有消息组合成一个用户消息
    combined_message = ""
    for msg in langchain_messages:
        if hasattr(msg, 'content'):
            if isinstance(msg, SystemMessage):
                combined_message += f"系统消息: {msg.content}\n\n"
            elif isinstance(msg, HumanMessage):
                combined_message += f"用户消息: {msg.content}\n\n"
            else:  # AIMessage or other
                combined_message += f"助手消息: {msg.content}\n\n"

    try:
        logger.info(
            f"开始使用structured_output_parser解析，目标模型: {response_model.__name__}")

        # 使用解析器进行结构化输出，它会自动处理所有降级逻辑
        result = await parser.parse_with_structured_output(
            user_message=combined_message.strip(),
            pydantic_class=response_model
        )

        # 将结果序列化为JSON字符串，兼容不同Pydantic版本
        # 将结果序列化为JSON字符串，兼容不同Pydantic版本
        try:
            # Pydantic v2 方式，支持ensure_ascii参数
            result_json = result.model_dump_json(ensure_ascii=False)
        except TypeError:
            # Pydantic v1 或不支持ensure_ascii参数的版本
            result_json = result.model_dump_json()
        except AttributeError:
            # 降级到dict方式
            result_dict = result.model_dump() if hasattr(
                result, 'model_dump') else result.dict()
            result_json = json.dumps(
                result_dict, ensure_ascii=False, indent=None, separators=(',', ':'))

        logger.info(f"结构化输出成功: {result_json[:200]}...")

        # 返回模拟的responses.parse格式
        return MockResponse(result_json)

    except Exception as e:
        logger.error(f"structured_output_parser解析失败: {e}")
        logger.error(f"错误类型: {type(e).__name__}")
        import traceback
        logger.error(f"错误堆栈: {traceback.format_exc()}")

        # 如果structured_output_parser也失败了，尝试构建合理的默认值
        try:
            logger.info(f"尝试创建{response_model.__name__}的默认实例")

            # 获取模型的字段信息
            model_fields = response_model.model_fields if hasattr(
                response_model, 'model_fields') else {}
            logger.info(f"模型字段: {list(model_fields.keys())}")

            # 构建默认值字典
            default_values = {}
            for field_name, field_info in model_fields.items():
                # 根据字段类型提供合理的默认值
                if hasattr(field_info, 'annotation'):
                    field_type = field_info.annotation
                    if hasattr(field_type, '__origin__') and field_type.__origin__ is list:
                        default_values[field_name] = []
                    elif field_type == str:
                        default_values[field_name] = ""
                    elif field_type == int:
                        default_values[field_name] = 0
                    elif field_type == float:
                        default_values[field_name] = 0.0
                    elif field_type == bool:
                        default_values[field_name] = False
                    else:
                        # 对于复杂类型，尝试创建空值
                        default_values[field_name] = [] if 'list' in str(
                            field_type).lower() else {}

            logger.info(f"构建的默认值: {default_values}")

            # 尝试创建实例
            empty_result = response_model(**default_values)

            # 序列化，兼容不同版本
            try:
                content = empty_result.model_dump_json(ensure_ascii=False)
            except TypeError:
                content = empty_result.model_dump_json()

            logger.warning(f"使用默认值作为降级方案: {content}")
            return MockResponse(content)

        except Exception as final_e:
            logger.error(f"创建默认实例失败: {final_e}")
            # 最终降级：返回符合基本结构的JSON
            try:
                # 尝试构建一个最小的合法JSON结构
                if 'ExtractedEntities' in response_model.__name__:
                    # 针对GraphitiCore的ExtractedEntities模型
                    fallback_json = '{"extracted_entities": []}'
                else:
                    fallback_json = '{}'

                logger.warning(f"使用硬编码降级方案: {fallback_json}")
                return MockResponse(fallback_json)
            except Exception:
                logger.error("所有降级方案都失败，返回空对象")
                return MockResponse('{}')


def apply_openai_client_patch():
    """
    应用OpenAI客户端补丁

    将GraphitiCore的OpenAIClient._create_structured_completion方法
    替换为兼容标准OpenAI API的版本
    """
    try:
        from graphiti_core.llm_client.openai_client import OpenAIClient

        # 保存原始方法（如果需要恢复的话）
        if not hasattr(OpenAIClient, '_original_create_structured_completion'):
            OpenAIClient._original_create_structured_completion = OpenAIClient._create_structured_completion

        # 应用补丁
        OpenAIClient._create_structured_completion = patched_create_structured_completion

        logger.info("成功应用GraphitiCore OpenAI客户端兼容性补丁")

    except ImportError as e:
        logger.error(f"无法导入GraphitiCore模块: {e}")
        raise
    except Exception as e:
        logger.error(f"应用OpenAI客户端补丁失败: {e}")
        raise


def remove_openai_client_patch():
    """
    移除OpenAI客户端补丁，恢复原始方法
    """
    try:
        from graphiti_core.llm_client.openai_client import OpenAIClient

        if hasattr(OpenAIClient, '_original_create_structured_completion'):
            OpenAIClient._create_structured_completion = OpenAIClient._original_create_structured_completion
            delattr(OpenAIClient, '_original_create_structured_completion')
            logger.info("成功移除GraphitiCore OpenAI客户端补丁")
        else:
            logger.warning("未找到原始方法，无法移除补丁")

    except ImportError as e:
        logger.error(f"无法导入GraphitiCore模块: {e}")
        raise
    except Exception as e:
        logger.error(f"移除OpenAI客户端补丁失败: {e}")
        raise

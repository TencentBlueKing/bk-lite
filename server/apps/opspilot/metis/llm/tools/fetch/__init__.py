"""Fetch工具模块

这个模块提供了完整的Web内容获取和HTTP请求工具集，用于Agent与外部API和网页进行交互。
工具按功能分类到不同的子模块中：

- http: HTTP请求工具（GET、POST、PUT、DELETE、PATCH）
- fetch: 高级内容获取工具（HTML、JSON、纯文本、Markdown）
- formatter: 内容格式化工具（HTML转文本、HTML转Markdown、JSON解析）
- utils: 通用辅助函数

**主要特性：**
- 支持所有标准HTTP方法（GET、POST、PUT、DELETE、PATCH）
- 自动处理各种内容格式（HTML、JSON、文本、Markdown）
- 支持自定义请求头和参数
- 支持大内容分段获取
- 智能内容提取和清理
- 完整的错误处理

**使用场景：**
- 调用外部REST API
- 获取网页内容和数据
- 下载和解析JSON数据
- 提取网页文本内容
- 转换网页为Markdown
- 与第三方服务集成

**工具分类：**

1. HTTP请求工具（http.py）：
   - http_get: 发送GET请求
   - http_post: 发送POST请求
   - http_put: 发送PUT请求
   - http_delete: 发送DELETE请求
   - http_patch: 发送PATCH请求

2. 高级Fetch工具（fetch.py）：
   - fetch_html: 获取HTML内容
   - fetch_txt: 获取纯文本内容
   - fetch_markdown: 获取Markdown格式内容
   - fetch_json: 获取和解析JSON数据

3. 格式化工具（formatter.py）：
   - html_to_text: HTML转纯文本
   - html_to_markdown: HTML转Markdown
   - parse_json: 解析JSON
   - extract_main_content: 提取主要内容
"""

# 工具集构造参数元数据
from apps.opspilot.metis.llm.tools.fetch.utils import (
    prepare_fetch_config,
    validate_url,
    prepare_headers,
    truncate_content,
    format_response_info,
)
from apps.opspilot.metis.llm.tools.fetch.formatter import (
    html_to_text,
    html_to_markdown,
    parse_json,
    format_json,
    extract_main_content,
    clean_whitespace,
)
from apps.opspilot.metis.llm.tools.fetch.fetch import (
    fetch_html,
    fetch_txt,
    fetch_markdown,
    fetch_json,
)
from apps.opspilot.metis.llm.tools.fetch.http import (
    http_get,
    http_post,
    http_put,
    http_delete,
    http_patch,
)
CONSTRUCTOR_PARAMS = [
    {
        "name": "default_timeout",
        "type": "integer",
        "required": False,
        "description": "HTTP请求默认超时时间（秒），默认30秒"
    },
    {
        "name": "default_limit",
        "type": "integer",
        "required": False,
        "description": "默认内容长度限制，默认5000字符，0表示不限制"
    },
    {
        "name": "user_agent",
        "type": "string",
        "required": False,
        "description": "默认User-Agent字符串"
    },
    {
        "name": "verify_ssl",
        "type": "boolean",
        "required": False,
        "description": "是否验证SSL证书，默认True"
    }
]

# 导入所有工具函数


__all__ = [
    # HTTP请求工具
    "http_get",
    "http_post",
    "http_put",
    "http_delete",
    "http_patch",

    # 高级Fetch工具
    "fetch_html",
    "fetch_txt",
    "fetch_markdown",
    "fetch_json",

    # 格式化工具
    "html_to_text",
    "html_to_markdown",
    "parse_json",
    "format_json",
    "extract_main_content",
    "clean_whitespace",

    # 辅助函数
    "prepare_fetch_config",
    "validate_url",
    "prepare_headers",
    "truncate_content",
    "format_response_info",
]

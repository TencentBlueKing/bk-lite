"""浏览器操作工具模块

这个模块提供了基于AI的浏览器自动化工具，使用Browser-Use实现智能网页交互。
工具可以理解自然语言任务描述，自动执行复杂的网页操作。

**主要特性：**
- AI驱动的智能网页操作
- 处理动态加载的JavaScript内容
- 支持点击、填表、滚动等交互
- 智能信息提取和识别
- 自动处理常见网页元素

**使用场景：**
- 自动化网页测试和数据采集
- 与需要交互的网站进行操作
- 从动态网页提取结构化数据
- 执行复杂的网页自动化流程

**依赖要求：**
- browser-use: AI浏览器自动化框架
- playwright: 浏览器驱动（browser-use的依赖）

**工具列表：**
- browse_website: 访问网站并执行任务
- extract_webpage_info: 从网页中提取特定信息
"""

# 导入所有工具函数，保持向后兼容性
from apps.opspilot.metis.llm.tools.browser_use.browser_tool import browse_website, extract_webpage_info

# 工具集构造参数元数据
# Browser-Use 工具不需要特殊的构造参数
CONSTRUCTOR_PARAMS = []

__all__ = [
    # 浏览器操作工具
    "browse_website",
    "extract_webpage_info",
]

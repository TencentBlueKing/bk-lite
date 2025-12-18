"""内容格式化工具"""
import json
import re
from typing import Dict, Any
from bs4 import BeautifulSoup
from markdownify import markdownify as md


def html_to_text(html: str) -> str:
    """
    将HTML转换为纯文本

    Args:
        html: HTML字符串

    Returns:
        str: 纯文本内容
    """
    try:
        soup = BeautifulSoup(html, 'html.parser')

        # 移除script和style标签
        for script in soup(['script', 'style']):
            script.decompose()

        # 获取文本
        text = soup.get_text()

        # 清理空白
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip()
                  for line in lines for phrase in line.split("  "))
        text = '\n'.join(chunk for chunk in chunks if chunk)

        return text
    except Exception as e:
        # 如果BeautifulSoup解析失败，使用简单的正则清理
        return _simple_html_clean(html)


def html_to_markdown(html: str) -> str:
    """
    将HTML转换为Markdown格式

    Args:
        html: HTML字符串

    Returns:
        str: Markdown格式文本
    """
    try:
        soup = BeautifulSoup(html, 'html.parser')

        # 移除script和style标签
        for script in soup(['script', 'style']):
            script.decompose()

        # 转换为Markdown
        markdown = md(str(soup), heading_style="ATX")

        # 清理多余的空行
        markdown = re.sub(r'\n{3,}', '\n\n', markdown)

        return markdown.strip()
    except Exception as e:
        # 如果转换失败，返回纯文本
        return html_to_text(html)


def _simple_html_clean(html: str) -> str:
    """
    简单的HTML清理（备用方法）

    Args:
        html: HTML字符串

    Returns:
        str: 清理后的文本
    """
    # 移除script和style标签及其内容
    html = re.sub(r'<script[^>]*>.*?</script>', '',
                  html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<style[^>]*>.*?</style>', '', html,
                  flags=re.DOTALL | re.IGNORECASE)

    # 移除HTML注释
    html = re.sub(r'<!--.*?-->', '', html, flags=re.DOTALL)

    # 移除所有HTML标签
    html = re.sub(r'<[^>]+>', '', html)

    # 转换HTML实体
    html = html.replace('&nbsp;', ' ')
    html = html.replace('&lt;', '<')
    html = html.replace('&gt;', '>')
    html = html.replace('&amp;', '&')
    html = html.replace('&quot;', '"')
    html = html.replace('&#39;', "'")

    # 清理多余空白
    html = re.sub(r'\n\s*\n', '\n\n', html)
    html = re.sub(r' +', ' ', html)

    return html.strip()


def parse_json(content: str) -> Dict[str, Any]:
    """
    解析JSON内容

    Args:
        content: JSON字符串

    Returns:
        dict: 解析后的JSON对象

    Raises:
        json.JSONDecodeError: JSON格式无效时抛出
    """
    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        raise json.JSONDecodeError(
            f"JSON解析失败: {str(e)}",
            e.doc,
            e.pos
        )


def format_json(obj: Any, indent: int = 2) -> str:
    """
    格式化JSON对象为字符串

    Args:
        obj: 任意可序列化的Python对象
        indent: 缩进空格数

    Returns:
        str: 格式化的JSON字符串
    """
    return json.dumps(obj, indent=indent, ensure_ascii=False)


def extract_main_content(html: str) -> str:
    """
    从HTML中提取主要内容

    尝试移除导航、侧边栏、页脚等非主要内容

    Args:
        html: HTML字符串

    Returns:
        str: 主要内容的HTML
    """
    try:
        soup = BeautifulSoup(html, 'html.parser')

        # 移除常见的非内容元素
        for element in soup(['script', 'style', 'nav', 'header', 'footer', 'aside']):
            element.decompose()

        # 移除常见的非内容class
        for class_name in ['nav', 'navbar', 'sidebar', 'footer', 'header', 'menu', 'advertisement', 'ad']:
            for element in soup.find_all(class_=re.compile(class_name, re.I)):
                element.decompose()

        # 尝试找到主要内容区域
        main_content = (
            soup.find('main') or
            soup.find('article') or
            soup.find('div', class_=re.compile(r'content|main', re.I)) or
            soup.find('body') or
            soup
        )

        return str(main_content)
    except Exception:
        return html


def clean_whitespace(text: str) -> str:
    """
    清理文本中的多余空白

    Args:
        text: 文本字符串

    Returns:
        str: 清理后的文本
    """
    # 移除行首行尾空白
    lines = [line.strip() for line in text.split('\n')]

    # 移除空行（保留一个）
    cleaned_lines = []
    prev_empty = False
    for line in lines:
        if line:
            cleaned_lines.append(line)
            prev_empty = False
        elif not prev_empty:
            cleaned_lines.append('')
            prev_empty = True

    return '\n'.join(cleaned_lines).strip()

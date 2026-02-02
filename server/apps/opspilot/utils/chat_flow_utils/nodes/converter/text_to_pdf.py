"""
文本转PDF节点 - 将上一个节点的消息转换为PDF文件流
"""

import io
import os
from typing import Any, Dict

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.utils.chat_flow_utils.engine.core.base_executor import BaseNodeExecutor


class TextToPdfNode(BaseNodeExecutor):
    """文本转PDF节点

    功能：
    - 将上一个节点的 last_message 转换为 PDF
    - PDF 以字节流（BytesIO）形式存储在节点变量中
    - 支持自定义配置（页面大小、字体、边距等）
    """

    def __init__(self, variable_manager):
        super().__init__(variable_manager)
        self.chinese_font_name = self._register_fonts()

    def _register_fonts(self) -> str:
        """
        注册中文字体（如果可用）

        Returns:
            可用的中文字体名称，如果注册失败返回 'Helvetica'
        """
        # 定义字体候选列表（优先级从高到低）
        font_candidates = [
            # Windows 常用字体
            ("微软雅黑", "C:/Windows/Fonts/msyh.ttf"),
            ("微软雅黑", "C:/Windows/Fonts/msyh.ttc"),
            ("黑体", "C:/Windows/Fonts/simhei.ttf"),
            ("宋体", "C:/Windows/Fonts/simsun.ttc"),
            # Linux 中文字体
            ("Noto Sans CJK SC", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
            ("WenQuanYi Micro Hei", "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"),
            # macOS 常用字体
            ("PingFang SC", "/System/Library/Fonts/PingFang.ttc"),
            ("Heiti SC", "/System/Library/Fonts/Heiti.ttc"),
            ("Heiti SC", "/System/Library/Fonts/STHeiti Light.ttc"),
            ("Heiti SC", "/System/Library/Fonts/STHeiti Medium.ttc"),
            # Linux 默认字体（作为降级方案）
            ("DejaVuSans", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            ("LiberationSans", "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
            ("FreeSans", "/usr/share/fonts/truetype/freefont/FreeSans.ttf"),
        ]

        # 尝试注册字体
        for font_name, font_path in font_candidates:
            try:
                if os.path.exists(font_path):
                    pdfmetrics.registerFont(TTFont(font_name, font_path))
                    logger.info(f"成功注册字体: {font_name} ({font_path})")
                    return font_name
            except Exception:
                continue

        # 最后降级到reportlab内置字体
        logger.warning("未找到可用字体，使用reportlab内置字体Helvetica")
        return "Helvetica"

    def _create_pdf_stream(
        self,
        content: str,
        title: str = "Document",
        page_size: tuple = A4,
        font_name: str = None,
        font_size: int = 12,
    ) -> io.BytesIO:
        """创建 PDF 文件流

        Args:
            content: 要转换的文本内容
            title: PDF 文档标题
            page_size: 页面大小，默认 A4
            font_name: 字体名称，None 时使用已注册的中文字体
            font_size: 字体大小

        Returns:
            包含 PDF 内容的 BytesIO 对象
        """
        # 如果未指定字体，使用已注册的中文字体
        if font_name is None:
            font_name = self.chinese_font_name
        # 创建内存字节流
        pdf_buffer = io.BytesIO()

        # 创建 PDF 文档对象
        doc = SimpleDocTemplate(
            pdf_buffer,
            pagesize=page_size,
            rightMargin=2 * cm,
            leftMargin=2 * cm,
            topMargin=2 * cm,
            bottomMargin=2 * cm,
            title=title,
        )

        # 准备文档内容
        story = []

        # 获取样式
        styles = getSampleStyleSheet()

        # 创建自定义段落样式
        custom_style = ParagraphStyle(
            "CustomStyle",
            parent=styles["Normal"],
            fontName=font_name,
            fontSize=font_size,
            leading=font_size * 1.5,  # 行高
            textColor=colors.black,
            alignment=0,  # 左对齐
            spaceAfter=12,
        )

        # 添加标题
        title_style = ParagraphStyle(
            "TitleStyle",
            parent=styles["Heading1"],
            fontName=font_name,
            fontSize=font_size + 6,
            leading=(font_size + 6) * 1.5,
            textColor=colors.HexColor("#333333"),
            alignment=1,  # 居中对齐
            spaceAfter=20,
        )

        story.append(Paragraph(title, title_style))
        story.append(Spacer(1, 0.5 * cm))

        # 处理内容：将文本按段落分割
        paragraphs = content.split("\n")
        for para_text in paragraphs:
            if para_text.strip():
                # 转义 HTML 特殊字符
                para_text = para_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                para = Paragraph(para_text, custom_style)
                story.append(para)
            else:
                # 空行添加间距
                story.append(Spacer(1, 0.3 * cm))

        # 构建 PDF
        doc.build(story)

        # 将指针重置到开头
        pdf_buffer.seek(0)

        return pdf_buffer

    def execute(self, node_id: str, node_config: Dict[str, Any], input_data: Dict[str, Any]) -> Dict[str, Any]:
        """执行文本转PDF节点

        节点配置示例：
        {
            "config": {
                "inputParams": "last_message",
                "outputParams": "last_message",
                "pdfConfig": {
                    "title": "文档标题",
                    "fontSize": 12,
                    "fontName": "Helvetica"
                }
            }
        }

        Args:
            node_id: 节点ID
            node_config: 节点配置
            input_data: 输入数据

        Returns:
            执行结果，包含 PDF 元数据和变量引用
        """
        config = node_config["data"].get("config", {})
        input_key = config.get("inputParams", "last_message")
        output_key = config.get("outputParams", "last_message")

        # 获取输入文本
        input_text = input_data.get(input_key, "")

        if not input_text:
            logger.warning(f"文本转PDF节点 {node_id}: 输入文本为空")
            return {output_key: "输入文本为空，无法生成PDF"}

        try:
            # 获取 PDF 配置
            pdf_config = config.get("pdfConfig", {})
            title = pdf_config.get("title", "Document")
            font_size = pdf_config.get("fontSize", 12)
            # 如果用户指定了字体，使用指定的字体，否则使用None让_create_pdf_stream使用已注册的中文字体
            font_name = pdf_config.get("fontName")

            logger.info(f"文本转PDF节点 {node_id}: 开始生成PDF，标题={title}, 字体大小={font_size}, 字体={font_name or self.chinese_font_name}")

            # 生成 PDF 流
            pdf_stream = self._create_pdf_stream(content=input_text, title=title, font_name=font_name, font_size=font_size)

            # 获取 PDF 大小（字节数）
            pdf_size = pdf_stream.getbuffer().nbytes

            # 将 PDF 流存储到变量管理器（使用output_key作为变量名）
            self.variable_manager.set_variable(output_key, pdf_stream)

            logger.info(f"文本转PDF节点 {node_id}: PDF生成成功，大小={pdf_size} bytes，存储在变量 '{output_key}'")

            # 返回结果
            return {
                output_key: pdf_stream,
                "pdf_metadata": {
                    "title": title,
                    "size_bytes": pdf_size,
                    "variable_name": output_key,
                    "content_length": len(input_text),
                },
            }

        except Exception as e:
            logger.exception(f"文本转PDF节点 {node_id}: PDF生成失败: {str(e)}")
            return {output_key: f"PDF生成失败: {str(e)}"}

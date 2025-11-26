import base64
import re
import tempfile
from io import BytesIO
from typing import List

import fitz
import pandas as pd
from langchain_core.documents import Document
from tabula.io import read_pdf
from tqdm import tqdm
from loguru import logger

from neco.ocr.base_ocr import BaseOCR


class PDFLoader:

    def __init__(self, file_path, ocr: BaseOCR, load_mode: str = 'full'):
        """
        初始化PDF加载器

        Args:
            file_path: PDF文件路径
            ocr: OCR处理器
            mode: 模式，可选值为'full'(整个文档作为一个Document)或'page'(每页一个Document)
        """
        self.file_path = file_path
        self.ocr = ocr
        self.load_mode = load_mode

    def remove_unicode_chars(self, text):
        return re.sub(r'\\u[fF]{1}[0-9a-fA-F]{3}', '', text)

    def _get_table_areas(self, pdf):
        """获取所有页面的表格区域"""
        table_areas = []
        for page in tqdm(pdf, desc=f"检测PDF表格区域[{self.file_path}]"):
            # 使用 fitz 的表格检测功能
            tables = page.find_tables()
            if tables and tables.tables:
                for table in tables.tables:
                    # 保存表格的边界框
                    table_areas.append((page.number, table.bbox))
        return table_areas

    def _is_in_table_area(self, page_num, bbox, table_areas):
        """检查文本块是否在任何表格区域内"""
        try:
            x0, y0, x1, y1 = bbox
            for page_number, table_bbox in table_areas:
                if page_num == page_number:
                    tx0, ty0, tx1, ty1 = table_bbox
                    # 检查重叠
                    if x0 < tx1 and x1 > tx0 and y0 < ty1 and y1 > ty0:
                        return True
            return False
        except Exception as e:
            return False

    def _extract_page_text(self, page, table_areas):
        """提取页面文本，跳过表格区域"""
        try:
            page_dict = page.get_text("dict")
            text_blocks = [
                span["text"].strip()
                for block in page_dict["blocks"]
                if block["type"] == 0 and not self._is_in_table_area(page.number, block["bbox"], table_areas)
                for line in block["lines"]
                for span in line["spans"]
                if span["text"].strip()
            ]

            if text_blocks:
                return " ".join(self.remove_unicode_chars(text) for text in text_blocks).strip()
            return ""
        except Exception as e:
            logger.error(f"提取页面文本失败: {e}")
            return ""

    def _parse_images(self, pdf):
        """解析PDF中的图片内容"""
        docs = []
        if not self.ocr:
            logger.info(f"[{self.file_path}]未配置OCR,跳过图片解析")
            return docs

        for page_number in tqdm(range(1, len(pdf) + 1), desc=f"解析PDF图片[{self.file_path}]"):
            page = pdf[page_number - 1]
            for image_number, image in enumerate(page.get_images(), start=1):
                try:
                    xref_value = image[0]
                    base_image = pdf.extract_image(xref_value)
                    image_bytes = base_image["image"]

                    image_base64 = base64.b64encode(
                        image_bytes).decode('utf-8')

                    with tempfile.NamedTemporaryFile(delete=True, suffix=".png") as tmp_file:
                        tmp_file.write(image_bytes)
                        predict_result = self.ocr.predict(tmp_file.name)
                        metadata = {
                            "format": "image", "page": page_number, "image_base64": image_base64}
                        docs.append(
                            Document(predict_result, metadata=metadata))
                except Exception as e:
                    logger.error(f"解析图片失败: {e}")

        return docs

    def _parse_tables(self):
        """解析PDF中的表格"""
        docs = []
        try:
            with BytesIO(open(self.file_path, 'rb').read()) as pdf_file:
                tables = read_pdf(pdf_file, pages='all')
                page_numbers = read_pdf(
                    pdf_file, pages='all', output_format='json')

                for i, (table, page_info) in enumerate(zip(tables, page_numbers)):
                    page_num = page_info.get('page_number', i + 1)
                    table_docs = Document(
                        pd.DataFrame(table).to_markdown(index=False),
                        metadata={"format": "table", "page": page_num}
                    )
                    docs.append(table_docs)
        except Exception as e:
            logger.error(f"解析PDF表格失败: {e}", exc_info=True)

        return docs

    def load(self) -> List[Document]:
        logger.info(f"解析PDF文件：{self.file_path}, 模式: {self.load_mode}")
        docs = []

        with fitz.open(self.file_path) as pdf:
            # 解析图片内容
            docs.extend(self._parse_images(pdf))

            # 获取所有表格区域
            table_areas = self._get_table_areas(pdf)

            # 解析文本，根据模式处理
            try:
                if self.load_mode == 'full':
                    # 整个文档作为一个Document
                    full_text = ""
                    for page in tqdm(pdf, desc=f"解析PDF文本[{self.file_path}]"):
                        page_text = self._extract_page_text(page, table_areas)
                        if page_text:
                            full_text += page_text + " "

                    if full_text.strip():
                        docs.append(Document(full_text.strip()))

                elif self.load_mode == 'page':
                    # 每页一个Document
                    for page_number, page in enumerate(tqdm(pdf, desc=f"按页解析PDF文本[{self.file_path}]"), 1):
                        page_text = self._extract_page_text(page, table_areas)
                        if page_text:
                            docs.append(Document(
                                page_text,
                                metadata={"format": "text",
                                          "page": page_number}
                            ))
            except Exception as e:
                logger.error(f"解析PDF文本失败: {e}", exc_info=True)

            # 解析表格
            docs.extend(self._parse_tables())

            logger.info(f'成功解析PDF文件：{self.file_path}，共提取 {len(docs)} 个文档片段')
            return docs

import re
import tempfile
from io import BytesIO
from typing import List

import fitz
import pandas as pd
from langchain_core.documents import Document
from tabula.io import read_pdf
from tqdm import tqdm
from src.ocr.base_ocr import BaseOCR
from loguru import logger


class PDFLoader:

    def __init__(self, file_path, ocr: BaseOCR, mode: str = 'full'):
        self.file_path = file_path
        self.ocr = ocr
        self.mode = mode

    def remove_unicode_chars(self, text):
        return re.sub(r'\\u[fF]{1}[0-9a-fA-F]{3}', '', text)

    def _get_table_areas(self, pdf):
        """获取所有页面的表格区域"""
        table_areas = []
        for page in pdf:
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

    def load(self) -> List[Document]:
        logger.info(f"解析PDF文件：{self.file_path}")

        docs = []

        with fitz.open(self.file_path) as pdf:
            if self.ocr:
                for page_number in tqdm(range(1, len(pdf) + 1), desc=f"解析PDF图片[{self.file_path}]"):
                    page = pdf[page_number - 1]
                    for image_number, image in enumerate(page.get_images(), start=1):
                        try:
                            xref_value = image[0]
                            base_image = pdf.extract_image(xref_value)
                            image_bytes = base_image["image"]
                            with tempfile.NamedTemporaryFile(delete=True, suffix=".png") as tmp_file:
                                tmp_file.write(image_bytes)
                                predict_result = self.ocr.predict(
                                    tmp_file.name)
                                docs.append(
                                    Document(predict_result, metadata={"format": "image"}))
                        except Exception as e:
                            logger.error(f"解析图片失败: {e}")
                            continue

            # 首先获取所有表格区域
            table_areas = self._get_table_areas(pdf)

            # 解析文本，跳过表格区域
            full_text = ""
            try:
                for page in tqdm(pdf, desc=f"解析PDF文本[{self.file_path}]"):
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
                        full_text += " ".join(
                            self.remove_unicode_chars(text) for text in text_blocks
                        ) + " "
            except Exception as e:
                logger.error(f"解析PDF文本失败: {e}", exc_info=True)

            if full_text:
                docs.append(Document(full_text.strip()))

            # 使用上下文管理器处理临时文件
            try:
                with BytesIO(open(self.file_path, 'rb').read()) as pdf_file:
                    tables = read_pdf(pdf_file, pages='all')
                    table_docs = [
                        Document(
                            pd.DataFrame(table).to_markdown(index=False),
                            metadata={"format": "table"}
                        )
                        for table in tqdm(tables, desc=f"解析PDF表格[{self.file_path}]")
                    ]
                    docs.extend(table_docs)
            except Exception as e:
                logger.error(f"解析PDF表格失败: {e}", exc_info=True)

            logger.info(f'成功解析PDF文件：{self.file_path}，共提取 {len(docs)} 个文档片段')

            return docs

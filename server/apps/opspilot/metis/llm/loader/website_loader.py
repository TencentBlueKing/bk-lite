import base64
import copy
import os
import tempfile
from typing import List, Optional
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from langchain_community.document_loaders import RecursiveUrlLoader
from langchain_community.document_transformers import BeautifulSoupTransformer
from langchain_core.documents import Document
from loguru import logger


class WebSiteLoader:
    def __init__(self, url, max_depth, ocr):
        """
        Args:
            url: 起始URL
            max_depth: 最大爬取深度
            ocr: OCR客户端实例（如OlmOcr）
        """
        self.url = url
        self.max_depth = max_depth
        self.ocr = ocr

    def load(self) -> List[Document]:
        logger.info(f"加载网站: [{self.url}], 最大深度: [{self.max_depth}], OCR: [{self.ocr is not None}]")

        # 加载网页文本内容
        loader = RecursiveUrlLoader(self.url, max_depth=self.max_depth)
        web_docs = loader.load()

        transformer = BeautifulSoupTransformer()
        text_docs = transformer.transform_documents(copy.deepcopy(web_docs))

        logger.info(f"网站文本加载完成, 文档数量: {len(text_docs)}")

        # 如果启用OCR，提取并识别图片
        image_docs = []
        if self.ocr is not None:
            image_docs = self._extract_images_from_pages(web_docs)
            logger.info(f"图片提取完成, 图片数量: {len(image_docs)}")

        # 合并文本文档和图片文档
        all_docs = text_docs + image_docs

        logger.info(f"网站加载完成, 总文档数量: {len(all_docs)} (文本: {len(text_docs)}, 图片: {len(image_docs)})")

        return all_docs

    def _extract_images_from_pages(self, web_docs: List[Document]) -> List[Document]:
        """从网页文档中提取图片并使用OCR识别

        Args:
            web_docs: 原始HTML文档列表

        Returns:
            图片文档列表
        """
        image_docs = []

        for doc in web_docs:
            page_url = doc.metadata.get("source", self.url)
            html_content = doc.page_content

            # 解析HTML，提取图片
            try:
                soup = BeautifulSoup(html_content, "html.parser")
                img_tags = soup.find_all("img")

                logger.debug(f"页面 [{page_url}] 发现 {len(img_tags)} 个图片标签")

                for idx, img_tag in enumerate(img_tags, 1):
                    img_doc = self._process_image_tag(img_tag, page_url, idx)
                    if img_doc:
                        image_docs.append(img_doc)

            except Exception as e:
                logger.error(f"处理页面 [{page_url}] 的图片时出错: {e}")

        return image_docs

    def _process_image_tag(self, img_tag, page_url: str, img_index: int) -> Optional[Document]:
        """处理单个图片标签，下载图片并使用OCR识别

        Args:
            img_tag: BeautifulSoup的img标签对象
            page_url: 图片所在页面的URL
            img_index: 图片在页面中的索引

        Returns:
            图片Document对象，失败返回None
        """
        temp_img_path = None
        try:
            # 获取图片URL
            img_src = img_tag.get("src")
            if not img_src:
                return None

            # 处理相对URL
            img_url = urljoin(page_url, img_src)

            # 过滤掉data URL和无效URL
            if img_url.startswith("data:") or not self._is_valid_image_url(img_url):
                logger.debug(f"跳过无效图片URL: {img_url[:100]}")
                return None

            # 下载图片
            image_data = self._download_image(img_url)
            if not image_data:
                return None

            # 转换为base64
            image_base64 = base64.b64encode(image_data).decode("utf-8")

            # 获取图片描述信息
            img_alt = img_tag.get("alt", "")
            img_title = img_tag.get("title", "")

            # 使用OCR识别图片
            if hasattr(self.ocr, "predict_from_base64"):
                # 如果OCR支持从base64直接识别，避免创建临时文件
                logger.info(f"开始处理图片 [{img_index}]: 使用 predict_from_base64 方法")
                ocr_result = self.ocr.predict_from_base64(image_base64)
            else:
                # 降级方案：保存到临时文件并使用OCR识别
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_img:
                    temp_img.write(image_data)
                    temp_img.flush()
                    temp_img_path = temp_img.name

                logger.info(f"开始处理图片 [{img_index}]: {temp_img_path}")
                ocr_result = self.ocr.predict(temp_img_path)

            # 准备文档内容
            page_content = f"图片来源: {page_url}\n"
            if img_alt:
                page_content += f"图片描述(alt): {img_alt}\n"
            if img_title:
                page_content += f"图片标题(title): {img_title}\n"
            page_content += f"图片OCR识别内容:\n{ocr_result}"

            # 创建图片Document
            img_doc = Document(page_content, metadata={"format": "image", "page": img_index, "image_base64": image_base64})

            logger.debug(f"图片OCR识别成功 [{img_index}]: {img_url}, 大小: {len(image_data)} bytes")
            return img_doc

        except Exception as e:
            logger.error(f"处理图片标签时出错: {e}")
            return None
        finally:
            # 清理临时文件
            if temp_img_path:
                try:
                    os.unlink(temp_img_path)
                except Exception as cleanup_error:
                    logger.warning(f"清理临时文件失败 {temp_img_path}: {cleanup_error}")

    @staticmethod
    def _is_valid_image_url(url: str) -> bool:
        """检查是否为有效的图片URL"""
        try:
            parsed = urlparse(url)
            # 检查是否有scheme和netloc
            if not parsed.scheme or not parsed.netloc:
                return False
            return True
        except Exception:
            return False

    @staticmethod
    def _download_image(img_url: str, timeout: int = 10, max_size: int = 10 * 1024 * 1024) -> Optional[bytes]:
        """下载图片

        Args:
            img_url: 图片URL
            timeout: 超时时间（秒）
            max_size: 最大文件大小（字节），默认10MB

        Returns:
            图片二进制数据，失败返回None
        """
        try:
            with httpx.Client(timeout=timeout, follow_redirects=True) as client:
                response = client.get(img_url)

                if response.status_code != 200:
                    logger.warning(f"下载图片失败 [{img_url}], 状态码: {response.status_code}")
                    return None

                # 检查内容类型
                content_type = response.headers.get("content-type", "")
                if not content_type.startswith("image/"):
                    logger.warning(f"URL不是图片类型 [{img_url}], content-type: {content_type}")
                    return None

                # 检查文件大小
                content = response.content
                if len(content) > max_size:
                    logger.warning(f"图片过大 [{img_url}], 大小: {len(content)} bytes, 超过限制: {max_size} bytes")
                    return None

                return content

        except httpx.TimeoutException:
            logger.warning(f"下载图片超时 [{img_url}]")
            return None
        except Exception as e:
            logger.error(f"下载图片异常 [{img_url}]: {e}")
            return None

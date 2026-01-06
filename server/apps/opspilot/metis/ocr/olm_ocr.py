import base64
import io
import logging

from openai import OpenAI
from PIL import Image

logger = logging.getLogger(__name__)


class OlmOcr:
    def __init__(self, base_url: str, api_key: str, model="olmOCR-7B-0225-preview"):
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.model = model

    @staticmethod
    def _compress_image_from_bytes(image_data: bytes, max_size_kb: int = 600) -> bytes:
        """从字节数据压缩图片到指定大小以下

        Args:
            image_data: 图片字节数据
            max_size_kb: 最大文件大小（KB）

        Returns:
            压缩后的图片字节数据
        """
        data_size = len(image_data)
        logger.info(f"原始图片大小: {data_size / 1024:.2f} KB")

        # 如果文件小于限制，直接返回原始数据
        if data_size <= max_size_kb * 1024:
            logger.info("图片大小在限制范围内，无需压缩")
            return image_data

        # 使用 Pillow 压缩图片
        img = Image.open(io.BytesIO(image_data))
        img_format = img.format or "JPEG"

        # 如果是 PNG 且有透明通道，转换为 RGBA，否则转换为 RGB
        if img.mode in ("RGBA", "LA", "P"):
            if img_format.upper() == "PNG":
                pass  # 保持 PNG 格式
            else:
                # 转换为 RGB（移除透明通道）
                background = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode == "P":
                    img = img.convert("RGBA")
                background.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
                img = background
                img_format = "JPEG"
        elif img.mode != "RGB":
            img = img.convert("RGB")
            img_format = "JPEG"

        # 尝试不同的压缩参数
        quality = 85
        scale = 1.0

        while quality >= 20 or scale > 0.3:
            # 缩放图片
            if scale < 1.0:
                new_size = (int(img.width * scale), int(img.height * scale))
                resized_img = img.resize(new_size, Image.Resampling.LANCZOS)
            else:
                resized_img = img

            # 保存到内存
            buffer = io.BytesIO()
            if img_format.upper() == "PNG":
                resized_img.save(buffer, format="PNG", optimize=True)
            else:
                resized_img.save(buffer, format="JPEG", quality=quality, optimize=True)

            compressed_size = buffer.tell()

            # 检查压缩后的大小
            if compressed_size <= max_size_kb * 1024:
                logger.debug(f"压缩成功 - 质量: {quality}, 缩放: {scale:.2f}, " f"压缩后大小: {compressed_size / 1024:.2f} KB")
                return buffer.getvalue()

            # 调整压缩参数
            if quality > 20:
                quality -= 5
            else:
                scale -= 0.1

        # 如果还是太大，返回最后一次压缩的结果
        logger.warning(f"图片压缩到最低参数仍超过限制，当前大小: {compressed_size / 1024:.2f} KB")
        return buffer.getvalue()

    def predict_from_base64(self, image_base64: str) -> str:
        """从base64编码的图片进行OCR识别

        Args:
            image_base64: base64编码的图片字符串

        Returns:
            OCR识别结果文本
        """
        logger.info(f"开始处理base64图片，编码长度: {len(image_base64)}")

        # 解码base64得到图片字节数据
        image_data = base64.b64decode(image_base64)

        # 压缩图片（如需要）
        compressed_image = self._compress_image_from_bytes(image_data)
        compressed_base64 = base64.b64encode(compressed_image).decode("utf-8")

        logger.info(f"压缩后 base64 编码长度: {len(compressed_base64)}")

        # 调用OCR识别
        return self._perform_ocr(compressed_base64)

    def predict(self, file_path: str) -> str:
        """从文件路径进行OCR识别

        Args:
            file_path: 图片文件路径

        Returns:
            OCR识别结果文本
        """
        logger.info(f"开始处理图片: {file_path}")

        # 读取文件并压缩
        with open(file_path, "rb") as f:
            image_data = f.read()

        compressed_image = self._compress_image_from_bytes(image_data)
        base64_image = base64.b64encode(compressed_image).decode("utf-8")

        logger.info(f"图片 base64 编码长度: {len(base64_image)}")

        # 调用OCR识别
        return self._perform_ocr(base64_image)

    def _perform_ocr(self, base64_image: str) -> str:
        """执行OCR识别的核心逻辑

        Args:
            base64_image: base64编码的图片字符串

        Returns:
            OCR识别结果文本
        """
        try:
            logger.info(f"准备发送请求 - model: {self.model}, base_url: {self.client.base_url}")

            # 使用 OpenAI SDK 发送请求
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": """总结这张图片信息密度最高的摘要，并原样输出图片中的所有文字内容，要求符合以下条件：

第一部分 - 精准命中 RAG 系统检索需求的摘要：
输出内容应具备高度概括性，适合被知识检索系统高效匹配。
输出结构要求：
总结性摘要：提供图片核心信息的高度概括性总结，限制在一两句话内。
分项摘要：仅总结每个分项的主要用途或功能，不列出具体细则或冗长描述。
注意事项：
不直接复述图片中的具体内容。
避免列出图片中的细节，仅提供用途概括。
输出需简洁清晰，不冗长。

第二部分 - 图片正文内容识别要求：
1. 保持原文的段落结构和排版
2. 如果有表格,转换为 Markdown 表格格式
3. 如果有数学公式,使用 LaTeX 语法,行内公式用 \\( \\),独立公式用 \\[ \\]
4. 如果有手写文字,尽可能准确识别
5. 忽略页眉页脚,但保留脚注和参考文献
6. 如果图片方向不正确,请按正确方向识别
7. 不要编造内容,只返回图片中真实存在的文本
8. 按照自然阅读顺序返回所有文本内容

输出格式：
摘要：
总结性摘要：<核心总结>
分项摘要：
1)：<用途概括>
2)：<用途概括>
3)：<用途概括> （依此类推）

图片正文：
<按照上述要求识别的所有文字内容>

确保严格遵守以上要求，直接返回识别结果，不需要额外说明。
""",
                            },
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}},
                        ],
                    }
                ],
                temperature=0.01,
            )

            logger.info("请求成功，开始解析响应")

            # 提取文本内容
            if response.choices and len(response.choices) > 0:
                content = response.choices[0].message.content
                logger.info(f"识别成功，内容长度: {len(content) if content else 0}")
                return content
            else:
                logger.warning("响应中没有 choices 或 choices 为空")
                return "无法识别文本"

        except Exception as e:
            logger.error(f"请求失败: {type(e).__name__}: {str(e)}", exc_info=True)
            return f"请求失败: {str(e)}"

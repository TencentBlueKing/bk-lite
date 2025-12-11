import base64
import logging
from openai import OpenAI

logger = logging.getLogger(__name__)


class OlmOcr:
    def __init__(self, base_url: str, api_key: str, model="olmOCR-7B-0225-preview"):
        logger.info(f"初始化 OlmOcr - base_url: {base_url}, model: {model}")
        logger.info(
            f"API Key 长度: {len(api_key)}, 前缀: {api_key[:10]}... 后缀: ...{api_key[-4:]}")

        self.client = OpenAI(
            base_url=base_url,
            api_key=api_key
        )
        self.model = model

    def predict(self, file_path: str) -> str:
        logger.info(f"开始处理图片: {file_path}")

        # 读取图片并转换为base64编码
        with open(file_path, "rb") as image_file:
            base64_image = base64.b64encode(image_file.read()).decode('utf-8')

        logger.info(f"图片 base64 编码长度: {len(base64_image)}")

        try:
            logger.info(
                f"准备发送请求 - model: {self.model}, base_url: {self.client.base_url}")

            # 使用 OpenAI SDK 发送请求
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "Extract all text from this image."
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
                temperature=0.01
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

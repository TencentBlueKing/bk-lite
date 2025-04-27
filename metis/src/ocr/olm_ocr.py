import base64
import requests
import json

from loguru import logger


class OlmOcr:
    def __init__(self, base_url: str, api_key: str, model="olmOCR-7B-0225-preview"):
        self.base_url = base_url
        self.api_key = api_key
        self.model = model

    def predict(self, file_path: str) -> str:
        logger.info(f'使用olmOCR识别文件: {file_path}')
        # 读取图片并转换为base64编码
        with open(file_path, "rb") as image_file:
            base64_image = base64.b64encode(image_file.read()).decode('utf-8')

        # 构建请求体
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": """
                                Below is the image of one page of a PDF document,Just return the plain text representation of this document as if you were reading it naturally.
                                Turn equations into a LaTeX representation, and tables into markdown format. Remove the headers and footers, but keep references and footnotes.
                                Read any natural handwriting.
                                If there is no text at all that you think you should read, you can output empty string.
                                Do not hallucinate.
                            """
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
            "temperature": 0.01,
            "max_tokens": 8000
        }

        # 发送请求
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            data=json.dumps(payload)
        )

        # 解析响应
        if response.status_code == 200:
            result = response.json()
            # 提取文本内容
            if "choices" in result and len(result["choices"]) > 0:
                return result["choices"][0]["message"]["content"]
            else:
                return "无法识别文本"
        else:
            return f"请求失败，状态码: {response.status_code}, 响应: {response.text}"

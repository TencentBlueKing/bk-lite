import base64
import requests
import json


class OlmOcr:
    def __init__(self, base_url: str, api_key: str, model="olmOCR-7B-0225-preview"):
        self.base_url = base_url
        self.api_key = api_key
        self.model = model

    def predict(self, file_path: str) -> str:
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
                               你是一个具备OCR能力的智能体，阅读方式和人类一样。你可以从图片中提取文本信息。
                               下面是一张的图片，要求：
                                    1. 一步一步的思考
                                    2. 只需返回该文档的纯文本表示，就像您自然阅读一样
                                    3. 当识别出公式的时候，将公式转换为 LaTeX 格式，将表格转换为 Markdown 格式
                                    4. 不要产生幻觉
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

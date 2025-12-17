from typing import Any, Dict, List, Tuple, Union


class HistoryService:
    """处理对话历史和消息格式化的服务"""

    @classmethod
    def process_user_message_and_images(cls, user_message: Union[str, List[Dict[str, Any]]]) -> Tuple[str, List[str]]:
        """
        处理用户消息和图片数据

        Args:
            user_message: 用户消息，可能是字符串或包含文本和图片的列表

        Returns:
            处理后的文本消息和图片URL列表
        """
        image_data = []
        text_message = user_message

        if isinstance(user_message, list):
            for item in user_message:
                if item["type"] == "image_url":
                    image_url = item.get("image_url", item.get("url"))
                    if isinstance(image_url, dict):
                        image_url = image_url.get("url")
                    if image_url:
                        image_data.append(image_url)
                else:
                    text_message = item.get("message", item.get("text", ""))

        return text_message, image_data

    @staticmethod
    def process_chat_history(chat_history: List[Dict[str, Any]], window_size: int, image_data) -> List[Dict[str, Any]]:
        """
        处理聊天历史，处理窗口大小和图片数据

        Args:
            chat_history: 原始聊天历史
            window_size: 对话窗口大小

        Returns:
            处理后的聊天历史
        """
        num = window_size * -1
        processed_history = []
        role_map = {"assistant": "bot"}
        for user_msg in chat_history[num:]:
            message = user_msg.get("message", user_msg.get("text", ""))
            if user_msg["event"] == "user" and isinstance(message, list):
                image_list = []
                msg = ""
                for item in user_msg["message"]:
                    if item["type"] == "image_url":
                        image_url = item.get("image_url", item.get("url"))
                        if isinstance(image_url, dict):
                            image_url = image_url.get("url")
                        if image_url:
                            image_list.append(image_url)
                    else:
                        msg = item.get("text", "") or item.get("message", "")
                processed_history.append({"event": "user", "message": msg, "image_data": image_list})
            else:
                txt = user_msg.get("message", user_msg.get("text", ""))
                if isinstance(txt, list):
                    txt = "\n".join([i.get("message", i.get("text")) for i in txt])
                processed_history.append(
                    {
                        "event": role_map.get(user_msg["event"], user_msg["event"]),
                        "message": txt,
                    }
                )
        if image_data:
            processed_history.append(
                {
                    "event": "user",
                    "message": "",
                    "image_data": image_data,
                }
            )
        return processed_history


# 创建服务实例
history_service = HistoryService()

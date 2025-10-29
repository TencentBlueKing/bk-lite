import os


class WebConstants:
    """Web相关常量"""

    # WEB URL
    URL = os.getenv("WEB_URL", "http://localhost:8000")


import os
import tempfile
import warnings

# MarkItDown 在包导入阶段会加载音频 converter；Wiki 不支持音频资料,
# 这里仅忽略未使用音频能力导致的 ffmpeg 环境提示。
with warnings.catch_warnings():
    warnings.filterwarnings(
        "ignore",
        message="Couldn't find ffmpeg or avconv.*",
        category=RuntimeWarning,
    )
    from markitdown import MarkItDown

SUPPORTED_FILE_EXTENSIONS = (
    ".pdf",
    ".docx",
    ".pptx",
    ".xlsx",
    ".xls",
    ".msg",
    ".html",
    ".htm",
    ".txt",
    ".md",
    ".markdown",
    ".csv",
    ".json",
    ".xml",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".bmp",
    ".tiff",
    ".tif",
    ".webp",
    ".zip",
    ".epub",
)


class MarkItDownParser:
    """Default Wiki parser backed by Microsoft MarkItDown."""

    def parse_file(self, data: bytes, filename: str, *, vision_client=None, vision_model=None) -> str:
        if not data:
            return ""
        suffix = os.path.splitext(filename or "")[1] or ".bin"
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(data)
                tmp_path = tmp.name
            return self._convert(tmp_path, vision_client=vision_client, vision_model=vision_model)
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def parse_text(self, text: str, *, filename: str = "raw.txt") -> str:
        if not (text or "").strip():
            return ""
        return self.parse_file((text or "").encode("utf-8"), filename, vision_client=None)

    def parse_url(self, url: str, *, vision_client=None, vision_model=None) -> str:
        if not (url or "").strip():
            return ""
        return self._convert(url, vision_client=vision_client, vision_model=vision_model)

    def _convert(self, source, *, vision_client=None, vision_model=None) -> str:
        kwargs = {}
        if vision_client is not None and vision_model:
            kwargs["llm_client"] = vision_client
            kwargs["llm_model"] = vision_model
        result = MarkItDown(**kwargs).convert(source)
        return (getattr(result, "text_content", "") or "").strip()

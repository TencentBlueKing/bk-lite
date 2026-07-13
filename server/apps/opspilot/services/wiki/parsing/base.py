from typing import Protocol


class DocumentParser(Protocol):
    """Parse Wiki materials into markdown."""

    def parse_file(self, data: bytes, filename: str, *, vision_client=None, vision_model=None) -> str:
        """Parse uploaded file bytes into markdown."""
        ...

    def parse_text(self, text: str, *, filename: str = "raw.txt") -> str:
        """Parse raw text into markdown."""
        ...

    def parse_url(self, url: str, *, vision_client=None, vision_model=None) -> str:
        """Parse a URL into markdown."""
        ...

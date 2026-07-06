from apps.opspilot.services.wiki.parsing.markitdown_parser import MarkItDownParser


def get_parser():
    """Return the configured Wiki material parser."""
    return MarkItDownParser()

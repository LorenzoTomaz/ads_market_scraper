from urllib.parse import unquote_plus
from html import unescape


def decode_text(text: str) -> str:
    """Decodes a text with surrogate pairs

    Args:
        text (str): the text to decode

    Returns:
        str: the decoded text
    """
    return (
        unescape(unquote_plus(text)).encode("utf-16", "surrogatepass").decode("utf-16")
    )

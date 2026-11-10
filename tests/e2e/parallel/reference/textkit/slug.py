import re
import unicodedata


def slugify(text, sep="-", max_len=None):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", sep, text).strip(sep) if sep else re.sub(r"[^a-z0-9]+", "", text)
    if max_len is not None:
        slug = slug[:max_len].rstrip(sep) if sep else slug[:max_len]
    return slug

import math
import re


def stats(text):
    words = sum(1 for t in text.split() if any(c.isalnum() for c in t))
    sentences = len(re.findall(r"[.!?]+(?=\s|$)", text))
    if words and not sentences:
        sentences = 1
    return {"words": words, "sentences": sentences, "reading_minutes": math.ceil(words / 200)}

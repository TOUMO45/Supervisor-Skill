import re

HEADING = re.compile(r"^(#{1,6})[ \t]+(.*?)[ \t]*#*[ \t]*$")


def toc(markdown):
    out, used, fence = [], set(), None
    for line in markdown.splitlines():
        stripped = line.strip()
        marker = stripped[:3]
        if fence:
            if stripped.startswith(fence):
                fence = None
            continue
        if marker in ("```", "~~~"):
            fence = marker
            continue
        m = HEADING.match(line)
        if not m or len(m.group(1)) < 2:
            continue
        level, text = len(m.group(1)), m.group(2).rstrip("#").strip()
        base = re.sub(r"[^a-z0-9 _-]", "", text.lower()).replace(" ", "-")
        anchor, n = base, 0
        while anchor in used:
            n += 1
            anchor = f"{base}-{n}"
        used.add(anchor)
        out.append("  " * (level - 2) + f"- [{text}](#{anchor})")
    return "\n".join(out) + "\n" if out else ""

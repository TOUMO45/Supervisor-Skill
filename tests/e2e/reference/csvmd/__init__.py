import csv, io, math

def escape(t): return t.replace("|", "\\|").replace("\r\n", "<br>").replace("\n", "<br>")

def is_num(t):
    try: return math.isfinite(float(t))
    except ValueError: return False

def convert(text, align="auto", max_width=None):
    if text.startswith("\ufeff"): text = text[1:]
    rows = list(csv.reader(io.StringIO(text, newline="")))
    if not rows: return ""
    n = max(len(r) for r in rows)
    rows = [r + [""] * (n - len(r)) for r in rows]
    def cell(c):
        if max_width and len(c) > max_width: c = c[: max_width - 1] + "…"
        return escape(c)
    seps = []
    for i in range(n):
        vals = [r[i].strip() for r in rows[1:] if r[i].strip()]
        if align == "none": seps.append("---")
        elif align == "left": seps.append(":---")
        else: seps.append("---:" if vals and all(is_num(v) for v in vals) else ":---")
    line = lambda cs: "| " + " | ".join(cs) + " |"
    out = [line([cell(c) for c in rows[0]]), line(seps)] + [line([cell(c) for c in r]) for r in rows[1:]]
    return "\n".join(out) + "\n"

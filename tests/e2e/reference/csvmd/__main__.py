import argparse, sys
from csvmd import convert
p = argparse.ArgumentParser(prog="csvmd")
p.add_argument("file", nargs="?", default="-")
p.add_argument("--align", choices=["auto", "left", "none"], default="auto")
p.add_argument("--max-width", type=int)
a = p.parse_args()
if a.max_width is not None and a.max_width < 2: p.error("--max-width must be >= 2")
try:
    text = sys.stdin.read() if a.file == "-" else open(a.file, encoding="utf-8", newline="").read()
except OSError as e:
    print(f"csvmd: cannot read {a.file}: {e.strerror}", file=sys.stderr); sys.exit(2)
sys.stdout.write(convert(text, a.align, a.max_width))

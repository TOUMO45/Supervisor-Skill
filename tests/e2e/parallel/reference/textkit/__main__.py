import argparse
import sys

from . import slugify, stats, toc


def read(path):
    if path in (None, "-"):
        return sys.stdin.read()
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError as exc:
        print(f"textkit: cannot read {path}: {exc.strerror}", file=sys.stderr)
        sys.exit(2)


p = argparse.ArgumentParser(prog="textkit")
sub = p.add_subparsers(dest="cmd", required=True)
s = sub.add_parser("slug"); s.add_argument("--sep", default="-"); s.add_argument("--max-len", type=int); s.add_argument("text", nargs="+")
sub.add_parser("toc").add_argument("file", nargs="?")
sub.add_parser("stats").add_argument("file", nargs="?")
a = p.parse_args()
if a.cmd == "slug":
    print("\n".join(slugify(t, a.sep, a.max_len) for t in a.text))
elif a.cmd == "toc":
    sys.stdout.write(toc(read(a.file)))
else:
    r = stats(read(a.file))
    print(f"words={r['words']} sentences={r['sentences']} reading_minutes={r['reading_minutes']}")

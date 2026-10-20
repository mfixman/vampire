import argparse
import hashlib
import os
from pathlib import Path
import re

def split_key(problem):
    # Match Connections split scheme 5; variants of ABC123 stay together.
    name = Path(problem).stem
    match = re.match(r"[A-Z]{3}\d{3}", name)
    if match:
        return match.group()

    return name.split("__", 1)[0]

def part(problem, count):
    digest = hashlib.md5(split_key(problem).encode("utf-8"), usedforsecurity = False).digest()
    return int.from_bytes(digest, "big") % count

def split_problems(root, count, output):
    root = root.expanduser().resolve()
    source = root / "Problems" if (root / "Problems").is_dir() else root
    problems = sorted(path for path in source.rglob("*.p") if path.is_file())
    if not problems:
        raise ValueError(f"no .p problem files found under {source}")

    groups = [[] for _ in range(count)]
    for problem in problems:
        if "\n" in str(problem) or "\r" in str(problem):
            raise ValueError(f"problem path cannot contain a newline: {problem!r}")

        groups[part(problem, count)].append(str(problem))

    output.mkdir(parents = True, exist_ok = False)
    width = max(2, len(str(count - 1)))
    for index, group in enumerate(groups):
        path = output / f"part-{index:0{width}d}.txt"
        path.write_text("".join(name + "\n" for name in group), encoding = "utf-8")
        print(f"{path}: {len(group)} problems")

    print(f"Total: {len(problems)} problems; Connections split scheme 5")

def main():
    parser = argparse.ArgumentParser(
        description = "Split TPTP problem paths using Connections' MD5 prefix rule."
    )
    parser.add_argument(
        "root",
        nargs = "?",
        default = os.environ.get("TPTP"),
        type = Path,
        help = "TPTP root or problem directory (default: $TPTP)",
    )
    parser.add_argument("--split", type = int, default = 10, help = "number of parts (default: 10)")
    parser.add_argument("--output", type = Path, default = Path("TPTP_split"))
    args = parser.parse_args()
    if args.root is None:
        parser.error("provide the TPTP directory or set $TPTP")

    if args.split < 1:
        parser.error("--split must be at least 1")

    try:
        split_problems(args.root, args.split, args.output)
    except (OSError, ValueError) as error:
        parser.exit(1, f"Error: {error}\n")

if __name__ == "__main__":
    main()

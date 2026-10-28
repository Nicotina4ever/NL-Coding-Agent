"""CI helper: write SHA256SUMS for report files only (never data/runtime/models)."""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    root = Path(args[0] if args else "reports")
    if not root.is_dir():
        print("No report directory: " + str(root))
        return 1
    files = sorted(path for path in root.rglob("*") if path.is_file()
                   and path.name != "SHA256SUMS")
    lines = []
    for path in files:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(digest + "  " + path.relative_to(root).as_posix())
    (root / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Wrote " + str(len(lines)) + " checksum(s) to " + str(root / "SHA256SUMS"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

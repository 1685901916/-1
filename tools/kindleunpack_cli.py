from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    repo_root = Path(__file__).resolve().parents[1]
    kindleunpack_root = repo_root / ".tools" / "KindleUnpack"
    if not kindleunpack_root.exists():
        print(f"KindleUnpack repo not found: {kindleunpack_root}", file=sys.stderr)
        return 2

    sys.path.insert(0, str(kindleunpack_root))
    from lib.kindleunpack import main as kindleunpack_main

    return int(kindleunpack_main(sys.argv))


if __name__ == "__main__":
    raise SystemExit(main())

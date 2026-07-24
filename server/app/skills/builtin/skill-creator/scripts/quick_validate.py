from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: quick_validate.py <skill-directory>")
        return 2
    root = Path(__file__).resolve().parents[5]
    sys.path.insert(0, str(root))
    from app.skills.loader import read_skill_package
    try:
        manifest, _, digest, _ = read_skill_package(Path(sys.argv[1]))
    except Exception as exc:
        print(f"invalid: {exc}")
        return 1
    print(f"valid: {manifest.name} sha256:{digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

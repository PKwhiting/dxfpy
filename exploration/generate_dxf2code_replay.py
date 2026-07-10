from __future__ import annotations

import sys

from dxfpy.addons.dxf2code import document_to_code_file


def main() -> int:
    if len(sys.argv) != 4:
        raise SystemExit(
            "usage: generate_dxf2code_replay.py <source.dxf> <script.py> <output.dxf>"
        )
    document_to_code_file(sys.argv[1], sys.argv[2], sys.argv[3])
    print(sys.argv[2])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

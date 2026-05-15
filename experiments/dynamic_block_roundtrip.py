from __future__ import annotations

import argparse
from pathlib import Path

import ezdxf


def default_output_path(source: Path) -> Path:
    return source.with_name(f"{source.stem}_roundtrip_ezdxf.dxf")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Roundtrip a DXF through ezdxf readfile/saveas."
    )
    parser.add_argument("source", type=Path, help="Source DXF path")
    parser.add_argument(
        "output",
        type=Path,
        nargs="?",
        help="Output DXF path, defaults to <source>_roundtrip_ezdxf.dxf",
    )
    args = parser.parse_args()

    source = args.source.expanduser().resolve()
    output = (
        args.output.expanduser().resolve()
        if args.output is not None
        else default_output_path(source)
    )

    doc = ezdxf.readfile(source)
    doc.saveas(output)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

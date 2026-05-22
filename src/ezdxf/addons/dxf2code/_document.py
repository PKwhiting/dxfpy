from __future__ import annotations

import sys
from pathlib import Path

import ezdxf

from ._capture import capture_document_codegen_inputs
from ._emit import render_document_codegen_script


def write_document_code(
    source: str | Path,
    script_path: str | Path,
    out_path: str | Path,
) -> None:
    source = Path(source)
    script_path = Path(script_path)
    out_path = Path(out_path)

    doc = ezdxf.readfile(source)
    captured = capture_document_codegen_inputs(doc, source)
    script_text = render_document_codegen_script(captured, out_path)
    script_path.write_text(script_text, encoding="utf-8")


def main() -> int:
    if len(sys.argv) != 4:
        raise SystemExit(
            "usage: generate_dxf2code_replay.py <source.dxf> <script.py> <output.dxf>"
        )

    write_document_code(sys.argv[1], sys.argv[2], sys.argv[3])
    print(Path(sys.argv[2]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

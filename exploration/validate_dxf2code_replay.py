"""Generate a dxf2code replay, execute it, and print replay fidelity checks."""

from __future__ import annotations

import argparse
import runpy

import dxfpy
from dxfpy._fidelity_compare import compare_replay_documents, format_replay_comparison
from dxfpy.addons.dxf2code import document_to_code_file


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate, execute, and compare a dxf2code full-document replay."
    )
    parser.add_argument("source", help="source DXF path")
    parser.add_argument("script", help="generated Python replay script path")
    parser.add_argument("output", help="generated replay DXF path")
    parser.add_argument(
        "--strict-layout-order",
        action="store_true",
        help="treat layout tab order differences as failures",
    )
    parser.add_argument(
        "--sample-limit",
        type=int,
        default=10,
        help="maximum number of sample rows per issue type",
    )
    args = parser.parse_args(argv)

    print(f"Generating replay script: {args.script}")
    document_to_code_file(args.source, args.script, args.output)

    print(f"Executing replay script: {args.script}")
    runpy.run_path(args.script, run_name="__main__")

    print(f"Reading source DXF: {args.source}")
    source_doc = dxfpy.readfile(args.source)
    print(f"Reading replay DXF: {args.output}")
    replay_doc = dxfpy.readfile(args.output)

    comparison = compare_replay_documents(source_doc, replay_doc)
    print(format_replay_comparison(comparison, sample_limit=args.sample_limit))
    return 1 if comparison.has_issues(
        include_layout_order=args.strict_layout_order
    ) else 0


if __name__ == "__main__":
    raise SystemExit(main())

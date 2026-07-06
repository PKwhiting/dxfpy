from __future__ import annotations

import argparse

import ezdxf
from ezdxf._fidelity_compare import compare_replay_documents, format_replay_comparison


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare a source DXF against a dxf2code replay DXF."
    )
    parser.add_argument("source", help="source DXF path")
    parser.add_argument("replay", help="replay DXF path")
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

    source_doc = ezdxf.readfile(args.source)
    replay_doc = ezdxf.readfile(args.replay)
    comparison = compare_replay_documents(source_doc, replay_doc)
    print(format_replay_comparison(comparison, sample_limit=args.sample_limit))
    return 1 if comparison.has_issues(
        include_layout_order=args.strict_layout_order
    ) else 0


if __name__ == "__main__":
    raise SystemExit(main())

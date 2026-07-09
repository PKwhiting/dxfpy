# Copyright (c) 2026, Manfred Moitzi
# License: MIT License
from __future__ import annotations

import argparse
from pathlib import Path

import ezdxf
from ezdxf.document import Drawing
from ezdxf.dynamic_blocks import (
    DynamicBlockReference,
    DynamicBlockVisibilityError,
)

# ------------------------------------------------------------------------------
# This example shows how to inspect dynamic block INSERT entities and how to
# change the visibility state of an existing dynamic block reference.
#
# Usage:
#   python change_dynamic_block_visibility.py input.dxf
#   python change_dynamic_block_visibility.py input.dxf \
#       --state "State Name" --output output.dxf
#
# The input DXF must already contain AutoCAD-compatible dynamic blocks. ezdxf can
# change visibility states of existing dynamic block references, but does not
# create complete dynamic block definitions from scratch.
# ------------------------------------------------------------------------------


def iter_dynamic_block_references(doc: Drawing) -> tuple[DynamicBlockReference, ...]:
    """Return dynamic block references from modelspace."""
    references: list[DynamicBlockReference] = []
    for insert in doc.modelspace().query("INSERT"):
        reference = DynamicBlockReference(insert)
        if reference.is_dynamic:
            references.append(reference)
    return tuple(references)


def print_visibility_states(references: tuple[DynamicBlockReference, ...]) -> None:
    """Print visibility metadata for dynamic block references."""
    for reference in references:
        print_reference_header(reference)
        if reference.has_visibility:
            print(f"  current visibility: {reference.visibility_state!r}")
            print(f"  available states: {', '.join(reference.visibility_state_names)}")
        else:
            print("  no visibility states")


def print_reference_header(reference: DynamicBlockReference) -> None:
    """Print identifying information for a dynamic block reference."""
    insert = reference.insert
    print(f"INSERT #{insert.dxf.handle}:")
    print(f"  definition: {reference.definition_name!r}")
    print(f"  active reference: {reference.reference_name!r}")


def change_first_reference_state(
    references: tuple[DynamicBlockReference, ...], state: str
) -> bool:
    """Set `state` on the first compatible dynamic block reference."""
    for reference in references:
        if state not in reference.visibility_state_names:
            continue
        try:
            set_reference_state(reference, state)
        except DynamicBlockVisibilityError as error:
            print(f"skipped INSERT #{reference.insert.dxf.handle}: {error}")
        else:
            return True
    return False


def set_reference_state(reference: DynamicBlockReference, state: str) -> None:
    """Set the visibility state and print the changed INSERT handle."""
    reference.set_visibility_state(state)
    print(f"changed INSERT #{reference.insert.dxf.handle} to {state!r}")


def run(input_file: Path, output_file: Path | None, state: str | None) -> None:
    """Load, inspect, optionally modify, and save the DXF document."""
    doc = ezdxf.readfile(input_file)
    references = iter_dynamic_block_references(doc)
    print_visibility_states(references)
    if state is None:
        return
    if not change_first_reference_state(references, state):
        raise DynamicBlockVisibilityError(
            f"no editable dynamic block reference supports visibility state: {state!r}"
        )
    if output_file is None:
        raise ValueError("output file required when changing a visibility state")
    doc.saveas(output_file)
    print(f"saved: {output_file}")


def main() -> None:
    """Run the command line interface."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "input",
        type=Path,
        help="DXF file containing dynamic blocks",
    )
    parser.add_argument(
        "--state",
        help="visibility state to set on the first compatible dynamic block reference",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="DXF file to write after changing state",
    )
    args = parser.parse_args()
    if args.state is not None and args.output is None:
        parser.error("--output is required when --state is used")
    run(args.input, args.output, args.state)


if __name__ == "__main__":
    main()

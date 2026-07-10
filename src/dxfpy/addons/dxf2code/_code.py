from __future__ import annotations

from typing import Iterable


def black(code: str, line_length=88, fast: bool = True) -> str:
    """Returns the source `code` as a single string formatted by `Black`_.

    Requires the installed `Black`_ formatter::

        pip3 install black

    Args:
        code: source code
        line_length: max. source code line length
        fast: ``True`` for fast mode, ``False`` to check that the reformatted
            code is valid

    Raises:
        ImportError: Black is not available

    .. _black: https://pypi.org/project/black/

    """

    import black

    mode = black.FileMode()
    mode.line_length = line_length
    return black.format_file_contents(code, fast=fast, mode=mode)


class Code:
    """Source code container."""

    def __init__(self) -> None:
        self.code: list[str] = []
        self.imports: set[str] = set()
        self.layers: set[str] = set()
        self.styles: set[str] = set()
        self.linetypes: set[str] = set()
        self.dimstyles: set[str] = set()
        self.blocks: set[str] = set()

    def code_str(self, indent: int = 0) -> str:
        lead_str = " " * indent
        return "\n".join(lead_str + line for line in self.code)

    def black_code_str(self, line_length=88) -> str:
        return black(self.code_str(), line_length)

    def __str__(self) -> str:
        return self.code_str()

    def import_str(self, indent: int = 0) -> str:
        lead_str = " " * indent
        return "\n".join(lead_str + line for line in self.imports)

    def add_import(self, statement: str) -> None:
        self.imports.add(statement)

    def add_line(self, code: str, indent: int = 0) -> None:
        self.code.append(" " * indent + code)

    def add_lines(self, code: Iterable[str], indent: int = 0) -> None:
        for line in code:
            self.add_line(line, indent=indent)

    def merge(self, code: Code, indent: int = 0) -> None:
        self.imports.update(code.imports)
        self.layers.update(code.layers)
        self.linetypes.update(code.linetypes)
        self.styles.update(code.styles)
        self.dimstyles.update(code.dimstyles)
        self.blocks.update(code.blocks)
        self.add_lines(code.code, indent=indent)

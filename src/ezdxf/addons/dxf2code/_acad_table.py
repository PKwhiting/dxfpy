from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Sequence

if TYPE_CHECKING:
    from ezdxf.entities import DXFEntity
    from ezdxf.entities.acad_table import AcadTableCell, AcadTableLinkedCellContent
    from ezdxf.entities.dxfobj import Field


_ACAD_TABLE_TEXT_CONTENT_TYPE = 1
_ACAD_TABLE_FIELD_CONTENT_TYPE = 2
_ACAD_TABLE_BLOCK_CONTENT_TYPE = 4


@dataclass(frozen=True)
class _AcadTableReplayProfile:
    reasons: tuple[str, ...] = ()

    @property
    def is_semantic_safe(self) -> bool:
        """Returns ``True`` if high-level ACAD_TABLE replay is safe."""
        return not self.reasons

    def comment_text(self) -> str:
        """Returns a compact reason list for generated-code comments."""
        return ", ".join(self.reasons)


class _AcadTableReplayClassifier:
    def profile(self, entity: DXFEntity) -> _AcadTableReplayProfile:
        """Classify an ACAD_TABLE for high-level dxf2code replay."""
        data = getattr(entity, "data", None)
        if data is None:
            return _AcadTableReplayProfile(("missing-table-data",))
        reasons: list[str] = []
        for cell in data.cells:
            self._append_cell_reasons(entity, cell, reasons)
        return _AcadTableReplayProfile(tuple(dict.fromkeys(reasons)))

    def _append_cell_reasons(
        self, entity: DXFEntity, cell: AcadTableCell, reasons: list[str]
    ) -> None:
        """Append unsupported replay reasons for one semantic cell."""
        if self._has_merged_shape(cell):
            reasons.append("merged-cells")
        if cell.rotation != 0.0:
            reasons.append("rotated-cells")
        self._append_field_reasons(entity, cell, reasons)
        self._append_linked_content_reasons(entity, cell, reasons)

    @staticmethod
    def _has_merged_shape(cell: AcadTableCell) -> bool:
        """Returns ``True`` if a cell carries merge/span shape markers."""
        if cell.merged_value != 0 or cell.virtual_edge_flag != 0:
            return True
        return cell.border_width not in (0, 1) or cell.border_height not in (0, 1)

    def _append_field_reasons(
        self, entity: DXFEntity, cell: AcadTableCell, reasons: list[str]
    ) -> None:
        """Append unsupported FIELD graph reasons for one cell."""
        if cell.field_handle is None:
            return
        primary = self._primary_field(entity, cell)
        if primary is None or not self._field_tree_is_supported(primary):
            reasons.append("unsupported-field-tree")

    @staticmethod
    def _primary_field(entity: DXFEntity, cell: AcadTableCell) -> Field | None:
        """Returns the primary FIELD for one cell if it can be resolved."""
        get_primary = getattr(entity, "get_cell_primary_field", None)
        if not callable(get_primary):
            return None
        return get_primary(cell.row, cell.col)

    def _field_tree_is_supported(self, field: Field) -> bool:
        """Returns ``True`` if dxf2code can reconstruct the FIELD tree."""
        children = tuple(field.get_child_fields())
        if not children:
            return True
        if field.evaluator_id != "AcExpr" or not field.field_code.startswith(
            "\\AcExpr "
        ):
            return False
        return all(self._field_tree_is_supported(child) for child in children)

    def _append_linked_content_reasons(
        self, entity: DXFEntity, cell: AcadTableCell, reasons: list[str]
    ) -> None:
        """Append unsupported linked TABLECONTENT reasons for one cell."""
        contents = self._linked_cell_contents(entity, cell)
        if not contents:
            return
        if not self._linked_content_shape_is_supported(cell, contents):
            reasons.append("unsupported-linked-contents")
        if self._has_unmirrored_field_content(cell, contents):
            reasons.append("unmirrored-linked-field")

    def _linked_cell_contents(
        self, entity: DXFEntity, cell: AcadTableCell
    ) -> tuple[AcadTableLinkedCellContent, ...]:
        """Returns linked TABLECONTENT entries for one semantic cell."""
        contents = tuple(getattr(cell, "linked_cell_contents", ()) or ())
        if contents:
            return contents
        return self._load_linked_cell_contents(entity, cell)

    @staticmethod
    def _load_linked_cell_contents(
        entity: DXFEntity, cell: AcadTableCell
    ) -> tuple[AcadTableLinkedCellContent, ...]:
        """Load linked TABLECONTENT entries through the table API."""
        get_linked_cell = getattr(entity, "get_linked_cell", None)
        if not callable(get_linked_cell):
            return ()
        try:
            linked_cell = get_linked_cell(cell.row, cell.col)
        except (AttributeError, IndexError):
            return ()
        return tuple(getattr(linked_cell, "contents", ()) or ())

    @staticmethod
    def _linked_content_shape_is_supported(
        cell: AcadTableCell, contents: Sequence[AcadTableLinkedCellContent]
    ) -> bool:
        """Returns ``True`` if linked content matches a replayed shape."""
        content_types = tuple(content.content_type for content in contents)
        if cell.is_block_cell:
            return _block_content_shape_is_supported(content_types)
        return content_types in (
            (_ACAD_TABLE_TEXT_CONTENT_TYPE,),
            (_ACAD_TABLE_FIELD_CONTENT_TYPE,),
        )

    @staticmethod
    def _has_unmirrored_field_content(
        cell: AcadTableCell, contents: Sequence[AcadTableLinkedCellContent]
    ) -> bool:
        """Returns ``True`` for linked FIELD content without shell mirror state."""
        has_field_content = any(
            content.content_type == _ACAD_TABLE_FIELD_CONTENT_TYPE
            for content in contents
        )
        return has_field_content and cell.field_handle is None


def _block_content_shape_is_supported(content_types: tuple[int, ...]) -> bool:
    """Returns ``True`` if block-cell linked content can be regenerated."""
    if content_types == (_ACAD_TABLE_BLOCK_CONTENT_TYPE,):
        return True
    return len(content_types) == 2 and set(content_types) == {
        _ACAD_TABLE_TEXT_CONTENT_TYPE,
        _ACAD_TABLE_BLOCK_CONTENT_TYPE,
    }

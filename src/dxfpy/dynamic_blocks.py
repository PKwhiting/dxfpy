from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from dxfpy import dynblkhelper
from dxfpy.dynblkhelper import (
    DynamicBlockPointParameter,
    DynamicBlockPropertyColumn,
    DynamicBlockPropertyRow,
    DynamicBlockPropertiesTable,
)
from dxfpy.entities import DXFEntity, DXFGraphic, Insert
from dxfpy.layouts import BaseLayout, BlockLayout
from dxfpy.lldxf import const
from dxfpy.math import UVec

if TYPE_CHECKING:
    from dxfpy.document import Drawing

__all__ = [
    "DynamicBlockError",
    "NotDynamicBlockReferenceError",
    "DynamicBlockVisibilityError",
    "UnknownVisibilityStateError",
    "UnsupportedDynamicBlockReferenceError",
    "DynamicBlockDefinition",
    "DynamicBlockPointParameter",
    "DynamicBlockPropertyColumn",
    "DynamicBlockPropertyRow",
    "DynamicBlockPropertiesTable",
    "DynamicBlockReference",
]


class DynamicBlockError(const.DXFValueError):
    """Base exception for dynamic block facade errors."""


class NotDynamicBlockReferenceError(DynamicBlockError):
    """Raised when an operation requires a dynamic block reference."""


class DynamicBlockVisibilityError(DynamicBlockError):
    """Raised when a visibility operation cannot be completed."""


class UnknownVisibilityStateError(DynamicBlockVisibilityError):
    """Raised when a requested visibility state does not exist."""


class UnsupportedDynamicBlockReferenceError(DynamicBlockVisibilityError):
    """Raised when a dynamic block reference shape is not safely editable."""


class DynamicBlockDefinition:
    """High-level facade for inspecting dynamic block definitions."""

    def __init__(self, block: BlockLayout) -> None:
        """Initialize the facade.

        :param block: Dynamic block definition to inspect.
        """
        self._block = block

    @classmethod
    def find(cls, document: Drawing, name: str) -> DynamicBlockDefinition | None:
        """Find a dynamic definition by block or recorded true name.

        :param document: Document containing the definition.
        :param name: Block-table or recorded true name.
        :return: Matching definition facade or ``None``.
        """
        direct = document.blocks.get(name)
        if direct is not None and cls._is_dynamic(direct):
            return cls(direct)
        normalized = name.casefold()
        for block in document.blocks:
            if cls._matches_true_name(block, normalized):
                return cls(block)
        return None

    @property
    def block(self) -> BlockLayout:
        """Return the wrapped block definition."""
        return self._block

    @property
    def document(self) -> Drawing:
        """Return the owning document.

        :raises DXFStructureError: If the definition is not document-bound.
        """
        document = self._block.doc
        if document is None:
            raise const.DXFStructureError("dynamic block requires a document")
        return document

    @property
    def name(self) -> str:
        """Return the block-table name."""
        return self._block.name

    @property
    def true_name(self) -> str:
        """Return the recorded dynamic block name."""
        return dynblkhelper.get_dynamic_block_true_name(self._block)

    @property
    def has_visibility(self) -> bool:
        """Return ``True`` if visibility states are available."""
        return bool(self.visibility_state_names)

    @property
    def visibility_state_names(self) -> tuple[str, ...]:
        """Return all available visibility-state names."""
        return dynblkhelper.get_dynamic_block_visibility_states(self._block)

    @property
    def property_table(self) -> DynamicBlockPropertiesTable | None:
        """Return the dynamic property table when present."""
        return dynblkhelper.get_dynamic_block_properties_table(self._block)

    @property
    def has_property_table(self) -> bool:
        """Return ``True`` if a dynamic property table is available."""
        return self.property_table is not None

    def visible_entities(self, state: str) -> tuple[DXFEntity, ...]:
        """Return entities visible in one state.

        :param state: Visibility-state name.
        :raises UnknownVisibilityStateError: If ``state`` is unknown.
        """
        self._validate_visibility_state(state)
        return dynblkhelper.get_dynamic_block_visibility_entities(
            self._block, state
        )

    def point_parameters(
        self, state: str
    ) -> tuple[DynamicBlockPointParameter, ...]:
        """Return point parameters referenced by one state.

        :param state: Visibility-state name.
        :raises UnknownVisibilityStateError: If ``state`` is unknown.
        """
        self._validate_visibility_state(state)
        return dynblkhelper.get_dynamic_block_point_parameters(
            self._block, state
        )

    def copy_visible_entities(
        self,
        state: str,
        target: BaseLayout,
        *,
        predicate: Callable[[DXFGraphic], bool] | None = None,
    ) -> tuple[DXFGraphic, ...]:
        """Copy visible graphics into a same-document layout.

        :param state: Visibility-state name.
        :param target: Layout receiving copied graphics.
        :param predicate: Optional source-entity filter.
        :return: Copied graphics in visibility-record order.
        """
        self._validate_target(target)
        self._validate_materializable_state(state)
        copied: list[DXFGraphic] = []
        for entity in self.visible_entities(state):
            if not self._should_copy(entity, predicate):
                continue
            duplicate = entity.copy_to_layout(target)
            duplicate.dxf.invisible = 0
            copied.append(duplicate)
        return tuple(copied)

    def materialize_visibility_state(
        self,
        state: str,
        target: BaseLayout,
        insertion: UVec,
        *,
        predicate: Callable[[DXFGraphic], bool] | None = None,
    ) -> Insert:
        """Insert a static anonymous block for one visibility state.

        :param state: Visibility-state name.
        :param target: Layout receiving the block reference.
        :param insertion: Block-reference insertion point.
        :param predicate: Optional source-entity filter.
        :return: Inserted static block reference.
        """
        self._validate_visibility_state(state)
        self._validate_target(target)
        block = self.document.blocks.new_anonymous_block(
            type_char="U", base_point=self._block.base_point
        )
        try:
            self.copy_visible_entities(state, block, predicate=predicate)
            return target.add_blockref(block.name, insertion)
        except Exception:
            self.document.blocks.delete_block(block.name, safe=False)
            raise

    def _validate_visibility_state(self, state: str) -> None:
        """Require a known visibility state."""
        if state not in self.visibility_state_names:
            raise UnknownVisibilityStateError(
                f"unknown dynamic block visibility state: {state!r}"
            )

    def _validate_target(self, target: BaseLayout) -> None:
        """Require a target in the definition's document."""
        if target.doc is not self.document:
            raise const.DXFStructureError(
                "dynamic block target requires the source document"
            )

    def _validate_materializable_state(self, state: str) -> None:
        """Reject visibility paths that require nested-block evaluation."""
        self._validate_visibility_state(state)
        handles = dynblkhelper.get_dynamic_block_visibility_state_handles(
            self._block, state
        )
        for handle in handles:
            path = dynblkhelper.get_dynamic_block_entity_rep_index_path(
                self._block, handle
            )
            if len(path) > 1:
                raise DynamicBlockVisibilityError(
                    "nested visibility paths cannot be materialized"
                )

    @staticmethod
    def _should_copy(
        entity: DXFEntity,
        predicate: Callable[[DXFGraphic], bool] | None,
    ) -> bool:
        """Return whether one source entity should be copied."""
        return (
            isinstance(entity, DXFGraphic)
            and entity.is_alive
            and (predicate is None or predicate(entity))
        )

    @staticmethod
    def _is_dynamic(block: BlockLayout) -> bool:
        """Return whether a block is a dynamic definition."""
        return dynblkhelper.is_dynamic_block_definition(block.block_record)

    @classmethod
    def _matches_true_name(cls, block: BlockLayout, name: str) -> bool:
        """Return whether a dynamic definition has a true-name match."""
        return cls._is_dynamic(block) and (
            dynblkhelper.get_dynamic_block_true_name(block).casefold() == name
        )


class DynamicBlockReference:
    """High-level facade for dynamic block INSERT entities.

    The facade exposes common dynamic block reference operations without requiring
    callers to manipulate anonymous blocks, extension dictionaries, or cached
    visibility-state records directly.
    """

    def __init__(self, insert: Insert) -> None:
        """Initialize the facade for an INSERT entity.

        Args:
            insert: INSERT entity to inspect or edit.

        Raises:
            DXFTypeError: `insert` is not an INSERT entity.
        """
        if not isinstance(insert, Insert):
            raise const.DXFTypeError(f"INSERT entity required, got {str(insert)}")
        self._insert = insert

    @property
    def insert(self) -> Insert:
        """Return the wrapped INSERT entity."""
        return self._insert

    @property
    def is_dynamic(self) -> bool:
        """Return ``True`` if the INSERT references a dynamic block."""
        return self.definition is not None

    @property
    def definition(self) -> BlockLayout | None:
        """Return the dynamic block definition or ``None``."""
        return dynblkhelper.get_dynamic_block_definition(self._insert)

    @property
    def reference(self) -> BlockLayout | None:
        """Return the active block representation or ``None``."""
        if not self.is_dynamic:
            return None
        return dynblkhelper.get_dynamic_block_reference(self._insert)

    @property
    def definition_name(self) -> str | None:
        """Return the dynamic block definition name or ``None``."""
        definition = self.definition
        return definition.name if definition is not None else None

    @property
    def reference_name(self) -> str | None:
        """Return the active block representation name or ``None``."""
        reference = self.reference
        return reference.name if reference is not None else None

    @property
    def is_anonymous_reference(self) -> bool:
        """Return ``True`` if the INSERT uses an anonymous representation."""
        definition = self.definition
        reference = self.reference
        return definition is not None and reference is not None and definition is not reference

    @property
    def has_visibility(self) -> bool:
        """Return ``True`` if the dynamic block has visibility states."""
        return bool(self.visibility_state_names)

    @property
    def visibility_state_names(self) -> tuple[str, ...]:
        """Return all available visibility state names."""
        return dynblkhelper.get_dynamic_block_visibility_states(self._insert)

    @property
    def visibility_state(self) -> str | None:
        """Return the current visibility state name or ``None``."""
        state = dynblkhelper.get_dynamic_block_visibility_state(self._insert)
        return state or None

    @property
    def property_table(self) -> DynamicBlockPropertiesTable | None:
        """Return the dynamic block property table or ``None``."""
        if not self.is_dynamic:
            return None
        return dynblkhelper.get_dynamic_block_properties_table(self._insert)

    @property
    def has_property_table(self) -> bool:
        """Return ``True`` if the dynamic block has a property table."""
        return self.property_table is not None

    def visible_entities(self, state: str | None = None) -> tuple[DXFEntity, ...]:
        """Return entities visible for a visibility state.

        Args:
            state: Optional state name. The current state is used if omitted.

        Raises:
            UnknownVisibilityStateError: `state` is not a known visibility state.
        """
        if state is not None:
            self._validate_visibility_state(state)
        return dynblkhelper.get_dynamic_block_visibility_entities(
            self._insert, state or ""
        )

    def set_visibility_state(self, state: str) -> None:
        """Set the current visibility state of the dynamic block reference.

        Args:
            state: Name of the visibility state to activate.

        Raises:
            NotDynamicBlockReferenceError: the INSERT is not dynamic.
            DynamicBlockVisibilityError: the block has no visibility states.
            UnknownVisibilityStateError: `state` is not a known visibility state.
            UnsupportedDynamicBlockReferenceError: the reference cannot be edited safely.
        """
        definition = self._require_dynamic_definition()
        self._require_visibility_support()
        self._validate_visibility_state(state)
        self._require_editable_reference(definition)
        dynblkhelper.set_dynamic_block_visibility_state(
            self._insert, definition, state=state
        )

    def _require_dynamic_definition(self) -> BlockLayout:
        definition = self.definition
        if definition is None:
            raise NotDynamicBlockReferenceError("INSERT does not reference a dynamic block")
        return definition

    def _require_visibility_support(self) -> None:
        if not self.visibility_state_names:
            raise DynamicBlockVisibilityError("dynamic block has no visibility states")

    def _validate_visibility_state(self, state: str) -> None:
        names = self.visibility_state_names
        if state not in names:
            raise UnknownVisibilityStateError(
                f"unknown dynamic block visibility state: {state!r}"
            )

    def _require_editable_reference(self, definition: BlockLayout) -> None:
        reference = self.reference
        if reference is None:
            raise UnsupportedDynamicBlockReferenceError(
                "dynamic block representation is not resolvable"
            )
        if reference is definition:
            raise UnsupportedDynamicBlockReferenceError(
                "direct dynamic block references are not safely editable"
            )
        self._require_unshared_reference(reference)

    def _require_unshared_reference(self, reference: BlockLayout) -> None:
        handles = self._live_reference_handles(reference)
        if len(handles) > 1:
            raise UnsupportedDynamicBlockReferenceError(
                "shared anonymous dynamic block references are not safely editable"
            )

    def _live_reference_handles(self, reference: BlockLayout) -> tuple[str, ...]:
        doc = self._insert.doc
        if doc is None:
            return ()
        handles: list[str] = []
        for handle in reference.block_record.blkref_handles:
            entity = doc.entitydb.get(handle)
            if isinstance(entity, Insert) and entity.is_alive and entity.dxf.handle:
                handles.append(entity.dxf.handle)
        return tuple(handles)

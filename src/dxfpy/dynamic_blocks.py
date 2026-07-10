from __future__ import annotations

from typing import TYPE_CHECKING

from dxfpy import dynblkhelper
from dxfpy.dynblkhelper import DynamicBlockPropertiesTable
from dxfpy.entities import DXFEntity, Insert
from dxfpy.lldxf import const

if TYPE_CHECKING:
    from dxfpy.layouts import BlockLayout

__all__ = [
    "DynamicBlockError",
    "NotDynamicBlockReferenceError",
    "DynamicBlockVisibilityError",
    "UnknownVisibilityStateError",
    "UnsupportedDynamicBlockReferenceError",
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

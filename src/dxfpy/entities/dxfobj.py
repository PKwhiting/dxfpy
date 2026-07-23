# Copyright (c) 2019-2024 Manfred Moitzi
# License: MIT License
from __future__ import annotations
from typing import TYPE_CHECKING, Iterable, Union, Any, Optional, Sequence
from typing_extensions import Self, TypeGuard
import logging
import array
import re
from dxfpy.lldxf import validator
from dxfpy.lldxf.const import (
    DXF2000,
    DXFStructureError,
    DXFTypeError,
    DXFVersionError,
    SUBCLASS_MARKER,
)
from dxfpy.lldxf.tags import Tags
from dxfpy.lldxf.types import dxftag, DXFTag, DXFBinaryTag
from dxfpy.lldxf.attributes import (
    DXFAttr,
    DXFAttributes,
    DefSubclass,
    RETURN_DEFAULT,
    group_code_mapping,
)
from dxfpy.tools import take2
from .dxfentity import DXFEntity, base_class, SubclassProcessor, DXFTagStorage
from .factory import register_entity
from .copy import CopyStrategy, default_copy

if TYPE_CHECKING:
    from dxfpy.audit import Auditor
    from dxfpy.document import Drawing
    from dxfpy.entities import DXFNamespace
    from dxfpy.lldxf.tagwriter import AbstractTagWriter
    from dxfpy import xref

__all__ = [
    "DXFObject",
    "Placeholder",
    "XRecord",
    "VBAProject",
    "SortEntsTable",
    "Field",
    "is_dxf_object",
]
logger = logging.getLogger("dxfpy")
FIELD_CODE_CHUNK_SIZE = 250
FIELD_INDEX_PATTERN = re.compile(r"%<\\_FldIdx (-?\d+)>%")


class DXFObject(DXFEntity):
    """Non-graphical entities stored in the OBJECTS section."""

    MIN_DXF_VERSION_FOR_EXPORT = DXF2000


@register_entity
class Placeholder(DXFObject):
    DXFTYPE = "ACDBPLACEHOLDER"


acdb_xrecord = DefSubclass(
    "AcDbXrecord",
    {
        # 0 = not applicable
        # 1 = keep existing
        # 2 = use clone
        # 3 = <xref>$0$<name>
        # 4 = $0$<name>
        # 5 = Unmangle name
        "cloning": DXFAttr(
            280,
            default=1,
            validator=validator.is_in_integer_range(0, 6),
            fixer=RETURN_DEFAULT,
        ),
    },
)


def totags(tags: Iterable) -> Iterable[DXFTag]:
    for tag in tags:
        if isinstance(tag, DXFTag):
            yield tag
        else:
            yield dxftag(tag[0], tag[1])


@register_entity
class XRecord(DXFObject):
    """DXF XRECORD entity"""

    DXFTYPE = "XRECORD"
    DXFATTRIBS = DXFAttributes(base_class, acdb_xrecord)

    def __init__(self):
        super().__init__()
        self.tags = Tags()

    def copy_data(self, entity: Self, copy_strategy=default_copy) -> None:
        assert isinstance(entity, XRecord)
        entity.tags = Tags(self.tags)

    def load_dxf_attribs(
        self, processor: Optional[SubclassProcessor] = None
    ) -> DXFNamespace:
        dxf = super().load_dxf_attribs(processor)
        if processor:
            try:
                tags = processor.subclasses[1]
            except IndexError:
                raise DXFStructureError(
                    f"Missing subclass AcDbXrecord in XRecord (#{dxf.handle})"
                )
            start_index = 1
            if len(tags) > 1:
                # First tag is group code 280, but not for DXF R13/R14.
                # SUT: doc may be None, but then doc also can not
                # be R13/R14 - dxfpy does not create R13/R14
                if self.doc is None or self.doc.dxfversion >= DXF2000:
                    code, value = tags[1]
                    if code == 280:
                        dxf.cloning = value
                        start_index = 2
                    else:  # just log recoverable error
                        logger.info(
                            f"XRecord (#{dxf.handle}): expected group code 280 "
                            f"as first tag in AcDbXrecord"
                        )
            self.tags = Tags(tags[start_index:])
        return dxf

    def export_entity(self, tagwriter: AbstractTagWriter) -> None:
        super().export_entity(tagwriter)
        tagwriter.write_tag2(SUBCLASS_MARKER, acdb_xrecord.name)
        tagwriter.write_tag2(280, self.dxf.cloning)
        tagwriter.write_tags(Tags(totags(self.tags)))

    def reset(self, tags: Iterable[Union[DXFTag, tuple[int, Any]]]) -> None:
        """Reset DXF tags."""
        self.tags.clear()
        self.tags.extend(totags(tags))

    def extend(self, tags: Iterable[Union[DXFTag, tuple[int, Any]]]) -> None:
        """Extend DXF tags."""
        self.tags.extend(totags(tags))

    def clear(self) -> None:
        """Remove all DXF tags."""
        self.tags.clear()


acdb_vba_project = DefSubclass(
    "AcDbVbaProject",
    {
        # 90: Number of bytes of binary chunk data (contained in the group code
        #   310 records that follow)
        # 310: DXF: Binary object data (multiple entries containing VBA project
        #   data)
    },
)


@register_entity
class VBAProject(DXFObject):
    """DXF VBA_PROJECT entity"""

    DXFTYPE = "VBA_PROJECT"
    DXFATTRIBS = DXFAttributes(base_class, acdb_vba_project)

    def __init__(self):
        super().__init__()
        self.data = b""

    def copy_data(self, entity: Self, copy_strategy=default_copy) -> None:
        assert isinstance(entity, VBAProject)
        entity.data = entity.data

    def load_dxf_attribs(
        self, processor: Optional[SubclassProcessor] = None
    ) -> DXFNamespace:
        dxf = super().load_dxf_attribs(processor)
        if processor:
            self.load_byte_data(processor.subclasses[1])
        return dxf

    def load_byte_data(self, tags: Tags) -> None:
        byte_array = array.array("B")
        # Translation from String to binary data happens in tag_compiler():
        for byte_data in (tag.value for tag in tags if tag.code == 310):
            byte_array.extend(byte_data)
        self.data = byte_array.tobytes()

    def export_entity(self, tagwriter: AbstractTagWriter) -> None:
        super().export_entity(tagwriter)
        tagwriter.write_tag2(SUBCLASS_MARKER, acdb_vba_project.name)
        tagwriter.write_tag2(90, len(self.data))
        self.export_data(tagwriter)

    def export_data(self, tagwriter: AbstractTagWriter):
        data = self.data
        while data:
            tagwriter.write_tag(DXFBinaryTag(310, data[:127]))
            data = data[127:]

    def clear(self) -> None:
        self.data = b""


acdb_sort_ents_table = DefSubclass(
    "AcDbSortentsTable",
    {
        # Soft-pointer ID/handle to owner (currently only the *MODEL_SPACE or
        # *PAPER_SPACE blocks) in dxfpy the block_record handle for a layout is
        # also called layout_key:
        "block_record_handle": DXFAttr(330),
        # 331: Soft-pointer ID/handle to an entity (zero or more entries may exist)
        #   5: Sort handle (zero or more entries may exist)
    },
)
acdb_sort_ents_table_group_codes = group_code_mapping(acdb_sort_ents_table)


@register_entity
class SortEntsTable(DXFObject):
    """DXF SORTENTSTABLE entity - sort entities table"""

    # should work with AC1015/R2000 but causes problems with TrueView/AutoCAD
    # LT 2019: "expected was-a-zombie-flag"
    # No problems with AC1018/R2004 and later
    #
    # If the header variable $SORTENTS Regen flag (bit-code value 16) is set,
    # AutoCAD regenerates entities in ascending handle order.
    #
    # When the DRAWORDER command is used, a SORTENTSTABLE object is attached to
    # the *Model_Space or *Paper_Space block's extension dictionary under the
    # name ACAD_SORTENTS. The SORTENTSTABLE object related to this dictionary
    # associates a different handle with each entity, which redefines the order
    # in which the entities are regenerated.
    #
    # $SORTENTS (280): Controls the object sorting methods (bitcode):
    # 0 = Disables SORTENTS
    # 1 = Sorts for object selection
    # 2 = Sorts for object snap
    # 4 = Sorts for redraws; obsolete
    # 8 = Sorts for MSLIDE command slide creation; obsolete
    # 16 = Sorts for REGEN commands
    # 32 = Sorts for plotting
    # 64 = Sorts for PostScript output; obsolete

    DXFTYPE = "SORTENTSTABLE"
    DXFATTRIBS = DXFAttributes(base_class, acdb_sort_ents_table)

    def __init__(self) -> None:
        super().__init__()
        self.table: dict[str, str] = dict()

    def copy_data(self, entity: Self, copy_strategy=default_copy) -> None:
        assert isinstance(entity, SortEntsTable)
        entity.table = dict(entity.table)

    def load_dxf_attribs(
        self, processor: Optional[SubclassProcessor] = None
    ) -> DXFNamespace:
        dxf = super().load_dxf_attribs(processor)
        if processor:
            tags = processor.fast_load_dxfattribs(
                dxf, acdb_sort_ents_table_group_codes, 1, log=False
            )
            self.load_table(tags)
        return dxf

    def load_table(self, tags: Tags) -> None:
        for handle, sort_handle in take2(tags):
            if handle.code != 331:
                raise DXFStructureError(
                    f"Invalid handle code {handle.code}, expected 331"
                )
            if sort_handle.code != 5:
                raise DXFStructureError(
                    f"Invalid sort handle code {handle.code}, expected 5"
                )
            self.table[handle.value] = sort_handle.value

    def export_entity(self, tagwriter: AbstractTagWriter) -> None:
        super().export_entity(tagwriter)
        tagwriter.write_tag2(SUBCLASS_MARKER, acdb_sort_ents_table.name)
        tagwriter.write_tag2(330, self.dxf.block_record_handle)
        self.export_table(tagwriter)

    def export_table(self, tagwriter: AbstractTagWriter):
        for handle, sort_handle in self.table.items():
            tagwriter.write_tag2(331, handle)
            tagwriter.write_tag2(5, sort_handle)

    def __len__(self) -> int:
        return len(self.table)

    def __iter__(self) -> Iterable:
        """Yields all redraw associations as (object_handle, sort_handle)
        tuples.

        """
        return iter(self.table.items())

    def append(self, handle: str, sort_handle: str) -> None:
        """Append redraw association (handle, sort_handle).

        Args:
            handle: DXF entity handle (uppercase hex value without leading '0x')
            sort_handle: sort handle (uppercase hex value without leading '0x')

        """
        self.table[handle] = sort_handle

    def clear(self):
        """Remove all handles from redraw order table."""
        self.table = dict()

    def set_handles(self, handles: Iterable[tuple[str, str]]) -> None:
        """Set all redraw associations from iterable `handles`, after removing
        all existing associations.

        Args:
            handles: iterable yielding (object_handle, sort_handle) tuples

        """
        # The sort_handle doesn't have to be unique, same or all handles can
        # share the same sort_handle and sort_handles can use existing handles
        # too.
        #
        # The '0' handle can be used, but this sort_handle will be drawn as
        # latest (on top of all other entities) and not as first as expected.
        # Invalid entity handles will be ignored by AutoCAD.
        self.table = dict(handles)

    def remove_invalid_handles(self) -> None:
        """Remove all handles which do not exist in the drawing database."""
        if self.doc is None:
            return
        entitydb = self.doc.entitydb
        self.table = {
            handle: sort_handle
            for handle, sort_handle in self.table.items()
            if handle in entitydb
        }

    def remove_handle(self, handle: str) -> None:
        """Remove handle of DXF entity from redraw order table.

        Args:
            handle: DXF entity handle (uppercase hex value without leading '0x')

        """
        try:
            del self.table[handle]
        except KeyError:
            pass


acdb_field = DefSubclass(
    "AcDbField",
    {
        "evaluator_id": DXFAttr(1),
        "field_code": DXFAttr(2),
        # Overflow of field code string
        "field_code_overflow": DXFAttr(3),
        # Number of child fields
        "n_child_fields": DXFAttr(90),
        # 360:  Child field ID (AcDbHardOwnershipId); repeats for number of children
        #  97:  Number of object IDs used in the field code
        # 331:  Object ID used in the field code (AcDbSoftPointerId); repeats for
        #       the number of object IDs used in the field code
        #  93:  Number of the data set in the field
        #   6:  Key string for the field data; a key-field pair is repeated for the
        #       number of data sets in the field
        #   7:  Key string for the evaluated cache; this key is hard-coded
        #       as ACFD_FIELD_VALUE
        #  90:  Data type of field value
        #  91:  Long value (if data type of field value is long)
        # 140:  Double value (if data type of field value is double)
        # 330:  ID value, AcDbSoftPointerId (if data type of field value is ID)
        #  92:  Binary data buffer size (if data type of field value is binary)
        # 310:  Binary data (if data type of field value is binary)
        # 301:  Format string
        #   9:  Overflow of Format string
        #  98:  Length of format string
    },
)


@register_entity
class Field(DXFObject):
    """DXF FIELD entity"""

    DXFTYPE = "FIELD"
    DXFATTRIBS = DXFAttributes(base_class, acdb_field)

    def __init__(self) -> None:
        super().__init__()
        self.tags = Tags()
        self._pending_copy_children: Optional[list[Field]] = None
        self._copy_field_list_member = False
        self._copy_has_owner_reactor = False
        self._copy_source_owner: Optional[str] = None
        self._restore_owner_reactor_on_reparent = False

    def copy_data(
        self, entity: Self, copy_strategy: CopyStrategy = default_copy
    ) -> None:
        """Copy this FIELD and its complete hard-owned child tree."""
        assert isinstance(entity, Field)
        children = self._validate_copyable_tree(set())
        entity.tags = Tags(self.tags)
        entity._pending_copy_children = [
            copy_strategy.copy(child) for child in children
        ]
        entity._replace_child_handle_tags(["0"] * len(children))
        entity._copy_field_list_member = self._is_field_list_member()
        (
            entity._copy_source_owner,
            entity._copy_has_owner_reactor,
        ) = self._owner_reactor_copy_state()
        entity._restore_owner_reactor_on_reparent = (
            self._restore_owner_reactor_on_reparent
        )

    def post_bind_hook(self) -> None:
        """Bind copied children and restore same-document FIELD metadata."""
        if self._pending_copy_children is None:
            return
        self._bind_pending_copy_children()
        self._restore_copied_owner_reactor()
        self._restore_copied_field_list_membership()
        self._clear_pending_copy_state()

    def pre_bind_hook(
        self, doc: Drawing, visited: Optional[set[int]] = None
    ) -> None:
        """Validate pending copies before document binding starts."""
        if visited is None:
            visited = set()
        super().pre_bind_hook(doc, visited)
        children = self._pending_copy_children
        if children is None:
            return
        child_tag_count = sum(1 for tag in self.tags if tag.code == 360)
        if child_tag_count != len(children):
            raise DXFStructureError("FIELD child handle count mismatch")
        if self._copy_field_list_member:
            doc.objects.get_field_list()
        for child in children:
            child.pre_bind_hook(doc, visited)

    def _validate_copyable_tree(self, seen: set[int]) -> list[Field]:
        """Validate a FIELD copy graph and return its direct children."""
        if not self.is_alive:
            raise DXFStructureError("destroyed FIELD entity")
        self._mark_unique_field(self, seen)
        children = self._copyable_direct_children()
        for child in children:
            child._validate_copyable_tree(seen)
        return children

    def _validate_replacement_tree(
        self, doc: Drawing, reusable_handles: set[str]
    ) -> set[str]:
        """Validate a replacement tree while allowing reused old descendants."""
        if self._pending_copy_children is not None or (
            self.dxf.handle is None and not self.child_handles
        ):
            self._validate_copyable_tree(set())
            return self._field_tree_handles()
        stack = [self]
        seen: set[int] = set()
        handles: set[str] = set()
        while stack:
            parent = stack.pop()
            if parent is not self or parent.dxf.handle is not None:
                self._validate_bound_field(doc, parent)
            if parent.dxf.handle is not None:
                handles.add(parent.dxf.handle)
            self._mark_unique_field(parent, seen)
            children: list[Field] = []
            for handle in parent.child_handles:
                child = doc.entitydb.get(handle)
                if not isinstance(child, Field) or not child.is_alive:
                    raise DXFStructureError("invalid child FIELD reference")
                if (
                    child.dxf.get("owner")
                    not in (None, "0", parent.dxf.handle)
                    and handle not in reusable_handles
                ):
                    raise DXFStructureError("child FIELD has an invalid owner")
                children.append(child)
            stack.extend(reversed(children))
        return handles

    def _copyable_direct_children(self) -> list[Field]:
        """Return owned children from a bound or pending FIELD copy."""
        if self._pending_copy_children is not None:
            return list(self._pending_copy_children)
        doc = self.doc
        if doc is None or self.dxf.handle is None:
            if self.child_handles:
                raise DXFStructureError("virtual FIELD root cannot have children")
            return []
        self._validate_bound_field(doc, self)
        return self._require_owned_children(doc, self)

    def _is_field_list_member(self) -> bool:
        """Return whether this FIELD copy should retain FIELDLIST membership."""
        if self._pending_copy_children is not None:
            return self._copy_field_list_member
        doc = self.doc
        handle = self.dxf.handle
        if doc is None or handle is None:
            return False
        field_list = doc.objects.get_field_list()
        return field_list is not None and handle in field_list.handles

    def _owner_reactor_copy_state(self) -> tuple[Optional[str], bool]:
        """Return the source owner and whether it is also a reactor."""
        if self._pending_copy_children is not None:
            return self._copy_source_owner, self._copy_has_owner_reactor
        owner = self.dxf.get("owner")
        return owner, owner not in (None, "0") and owner in self.get_reactors()

    def _bind_pending_copy_children(self) -> None:
        """Bind pending child copies and replace their placeholder handles."""
        from . import factory

        doc = self.doc
        parent_handle = self.dxf.handle
        assert doc is not None and parent_handle is not None
        children = self._pending_copy_children or []
        self._replace_child_handle_tags(["0"] * len(children))
        handles: list[str] = []
        for child in children:
            child.dxf.owner = parent_handle
            factory.bind(child, doc)
            doc.objects.add_object(child)
            child_handle = child.dxf.handle
            assert child_handle is not None
            handles.append(child_handle)
        self._replace_child_handle_tags(handles)

    def _replace_child_handle_tags(self, handles: Sequence[str]) -> None:
        """Replace hard-owned child handles without changing tag order."""
        indices = [
            index for index, tag in enumerate(self.tags) if tag.code == 360
        ]
        if len(indices) != len(handles):
            raise DXFStructureError("FIELD child handle count mismatch")
        for index, handle in zip(indices, handles):
            self.tags[index] = dxftag(360, handle)

    def _restore_copied_owner_reactor(self) -> None:
        """Map a copied owner reactor to this FIELD's new owner."""
        reactors = self.get_reactors()
        source_owner = self._copy_source_owner
        if source_owner is not None and source_owner in reactors:
            reactors.remove(source_owner)
        owner = self.dxf.get("owner")
        if self._copy_has_owner_reactor and owner not in (None, "0"):
            reactors.append(owner)
        if reactors or self.reactors is not None:
            self.set_reactors(reactors)

    def _restore_copied_field_list_membership(self) -> None:
        """Register this copied FIELD when its source was registered."""
        if not self._copy_field_list_member or self.doc is None:
            return
        field_list = self.doc.objects.setup_field_list()
        handle = self.dxf.handle
        if handle is not None and handle not in field_list.handles:
            field_list.handles.append(handle)

    def _clear_pending_copy_state(self) -> None:
        """Discard transient state after a copied FIELD has been bound."""
        self._pending_copy_children = None
        self._copy_field_list_member = False
        self._copy_has_owner_reactor = False
        self._copy_source_owner = None

    def register_resources(self, registry: xref.Registry) -> None:
        """Register resources referenced by this complete FIELD tree."""
        with self._resource_registration_scope():
            registry.require_field_support()
            self._register_base_resources(registry)
            self._register_custom_property(registry)
            self._register_child_resources(registry, {id(self)})

    def get_handle_mapping(self, clone: Self) -> dict[str, str]:
        """Return mappings for this FIELD and all hard-owned child copies."""
        assert isinstance(clone, Field)
        mapping = super().get_handle_mapping(clone)
        source_children = self.get_child_fields()
        clone_children = clone.get_child_fields()
        if len(source_children) != len(clone_children):
            raise DXFStructureError("FIELD child copy count mismatch")
        for source_child, clone_child in zip(source_children, clone_children):
            mapping.update(source_child.get_handle_mapping(clone_child))
        return mapping

    def _register_child_resources(
        self, registry: xref.Registry, seen: set[int]
    ) -> None:
        """Register child resources without registering child objects."""
        for child in self.get_child_fields():
            marker = id(child)
            if marker in seen:
                continue
            seen.add(marker)
            DXFEntity.register_resources(child, registry)
            child._register_custom_property(registry)
            child._register_child_resources(registry, seen)

    def _register_custom_property(self, registry: xref.Registry) -> None:
        """Register a custom drawing property referenced by this FIELD."""
        name = self._custom_property_name()
        if name:
            registry.add_custom_var(name)

    def _custom_property_name(self) -> Optional[str]:
        """Return the referenced custom drawing-property name if present."""
        if self.evaluator_id != "AcVar":
            return None
        name = self._structured_variable_name()
        if name is None:
            name = self._field_code_variable_name()
        prefix = "CustomDP."
        return name[len(prefix) :] if name and name.startswith(prefix) else None

    def _structured_variable_name(self) -> Optional[str]:
        """Read the variable name from the structured FIELD value data."""
        variable_data = False
        for tag in self.tags:
            if tag.code == 6 and tag.value == "Variable":
                variable_data = True
                continue
            if variable_data and tag.code == 1:
                return str(tag.value)
            if variable_data and tag.code == 304:
                return None
        return None

    def _field_code_variable_name(self) -> Optional[str]:
        """Read a variable name from a minimal or legacy FIELD code."""
        prefix = r"\AcVar "
        field_code = self.field_code
        if not field_code.startswith(prefix):
            return None
        name = field_code[len(prefix) :]
        format_marker = r' \f "'
        if format_marker in name:
            name = name.partition(format_marker)[0]
        return name

    def map_resources(self, clone: Self, mapping: xref.ResourceMapper) -> None:
        """Map FIELD soft pointers and recursively map copied children."""
        assert isinstance(clone, Field)
        super().map_resources(clone, mapping)
        self._map_soft_pointer_tags(clone, mapping)
        source_children = self.get_child_fields()
        clone_children = clone.get_child_fields()
        if len(source_children) != len(clone_children):
            raise DXFStructureError("FIELD child copy count mismatch")
        for source_child, clone_child in zip(source_children, clone_children):
            source_child.map_resources(clone_child, mapping)

    def _map_soft_pointer_tags(
        self, clone: Field, mapping: xref.ResourceMapper
    ) -> None:
        """Map payload pointers without changing hard-owned child handles."""
        if len(self.tags) != len(clone.tags):
            raise DXFStructureError("FIELD copy tag count mismatch")
        for index, source_tag in enumerate(self.tags):
            if source_tag.code not in (330, 331):
                continue
            if clone.tags[index].code != source_tag.code:
                raise DXFStructureError("FIELD copy tag structure mismatch")
            clone.tags[index] = dxftag(
                source_tag.code, mapping.get_handle(str(source_tag.value))
            )

    def _requires_binding_to(self, doc: Drawing) -> bool:
        """Validate document membership and return whether binding is required."""
        if self.doc not in (None, doc):
            raise DXFStructureError("field belongs to a different DXF document")
        handle = self.dxf.handle
        if handle is None:
            self.pre_bind_hook(doc)
            return True
        if self.doc is not doc or doc.entitydb.get(handle) is not self:
            raise DXFStructureError("invalid FIELD database entry")
        if self.dxf.get("owner") not in (None, "0") or self.get_reactors():
            raise DXFStructureError("FIELD root is already owned")
        return False

    def _bind_to_owner(self, doc: Drawing, owner_handle: str) -> None:
        """Bind this virtual FIELD with its final owner already assigned."""
        from . import factory

        previous_owner = self.dxf.get("owner")
        self.dxf.owner = owner_handle
        try:
            factory.bind(self, doc)
        except Exception:
            self.dxf.owner = previous_owner
            raise
        doc.objects.add_object(self)

    @property
    def evaluator_id(self) -> str:
        return self.dxf.get("evaluator_id", "")

    @property
    def field_code(self) -> str:
        if self.tags:
            return self._collect_field_code(self.tags)
        return self.dxf.get("field_code", "") + self.dxf.get(
            "field_code_overflow", ""
        )

    @property
    def is_text_wrapper(self) -> bool:
        return self.evaluator_id == "_text"

    @property
    def child_handles(self) -> list[str]:
        return [tag.value for tag in self.tags if tag.code == 360]

    @property
    def object_handles(self) -> list[str]:
        return [tag.value for tag in self.tags if tag.code == 331]

    def get_child_fields(self) -> list[Field]:
        if self._pending_copy_children is not None:
            return list(self._pending_copy_children)
        if self.doc is None:
            return []
        result: list[Field] = []
        for handle in self.child_handles:
            field = self.doc.entitydb.get(handle)
            if isinstance(field, Field) and field.is_alive:
                result.append(field)
        return result

    def get_field_tree(self) -> list[Field]:
        result: list[Field] = []
        stack = [self]
        seen: set[int] = set()
        while stack:
            field = stack.pop()
            marker = id(field)
            if marker in seen:
                continue
            seen.add(marker)
            result.append(field)
            stack.extend(reversed(field.get_child_fields()))
        return result

    @classmethod
    def _bind_field_roots(
        cls,
        doc: Drawing,
        child_fields: Sequence[Field],
        reusable_root_handles: Optional[set[str]] = None,
    ) -> list[Field]:
        """Validate and bind direct child FIELD roots to `doc`."""
        from . import factory

        fields = cls._validate_field_roots(
            doc, child_fields, reusable_root_handles
        )
        for field in fields:
            if field.doc is None:
                factory.bind(field, doc)
                doc.objects.add_object(field)
        return fields

    @classmethod
    def _validate_field_roots(
        cls,
        doc: Drawing,
        child_fields: Sequence[Field],
        reusable_root_handles: Optional[set[str]] = None,
    ) -> list[Field]:
        """Validate detached direct roots and their complete FIELD trees."""
        fields = list(child_fields)
        if not fields:
            raise DXFStructureError("linked child FIELDs required")
        for field in fields:
            if not isinstance(field, cls):
                raise DXFTypeError(
                    f"invalid FIELD reference: {type(field).__name__}"
                )
            if not field.is_alive:
                raise DXFStructureError("destroyed FIELD entity")
            if field.doc is not None and field.doc is not doc:
                raise DXFStructureError("field belongs to a different DXF document")
        seen: set[int] = set()
        reusable_handles = reusable_root_handles or set()
        for field in fields:
            cls._validate_available_root(field, reusable_handles)
            cls._validate_field_subtree(doc, field, seen)
        return fields

    @staticmethod
    def _validate_available_root(
        field: Field, reusable_root_handles: set[str]
    ) -> None:
        """Require a detached root or a reusable descendant of this host."""
        handle = field.dxf.handle
        if field.doc is None and handle is not None:
            raise DXFStructureError("virtual FIELD root cannot have a handle")
        owner = field.dxf.get("owner")
        if owner not in (None, "0") and handle not in reusable_root_handles:
            raise DXFStructureError("FIELD root is already owned")
        if field.get_reactors():
            raise DXFStructureError("FIELD root already has reactors")

    @classmethod
    def _validate_field_subtree(
        cls, doc: Drawing, root: Field, seen: set[int]
    ) -> None:
        """Validate ownership, document membership, and graph uniqueness."""
        if root.doc is None:
            root.pre_bind_hook(doc)
            root._validate_copyable_tree(seen)
            return
        stack = [root]
        while stack:
            parent = stack.pop()
            cls._validate_bound_field(doc, parent)
            cls._mark_unique_field(parent, seen)
            children = cls._require_owned_children(doc, parent)
            stack.extend(reversed(children))

    @staticmethod
    def _validate_bound_field(doc: Drawing, field: Field) -> None:
        """Require a live FIELD registered by handle in `doc`."""
        handle = field.dxf.handle
        if (
            not field.is_alive
            or field.doc is not doc
            or handle is None
            or doc.entitydb.get(handle) is not field
        ):
            raise DXFStructureError("invalid FIELD tree member")

    @staticmethod
    def _mark_unique_field(field: Field, seen: set[int]) -> None:
        """Reject duplicate roots, shared descendants, and cycles."""
        marker = id(field)
        if marker in seen:
            raise DXFStructureError("FIELD tree contains a duplicate or cycle")
        seen.add(marker)

    @classmethod
    def _require_owned_children(cls, doc: Drawing, parent: Field) -> list[Field]:
        """Resolve children and require exact hard-ownership links."""
        children: list[Field] = []
        for handle in parent.child_handles:
            child = doc.entitydb.get(handle)
            if not isinstance(child, cls) or not child.is_alive:
                raise DXFStructureError("invalid child FIELD reference")
            if child.dxf.get("owner") != parent.dxf.handle:
                raise DXFStructureError("child FIELD has an invalid owner")
            children.append(child)
        return children

    @staticmethod
    def _validate_text_wrapper_code(field_code: str, child_count: int) -> None:
        """Require valid references to every direct child FIELD."""
        if not isinstance(field_code, str):
            raise DXFTypeError("FIELD wrapper code must be a string")
        matches = list(FIELD_INDEX_PATTERN.finditer(field_code))
        if field_code.count(r"\_FldIdx") != len(matches):
            raise DXFStructureError("malformed FIELD wrapper child reference")
        indices = {int(match.group(1)) for match in matches}
        if any(index < 0 or index >= child_count for index in indices):
            raise DXFStructureError("FIELD wrapper child index out of range")
        if indices != set(range(child_count)):
            raise DXFStructureError("FIELD wrapper must reference every child")

    def _update_child_owners(self) -> None:
        """Set each linked child FIELD owner to its parent FIELD handle."""
        for parent in self.get_field_tree():
            for child in parent.get_child_fields():
                child._reparent_to(parent.dxf.handle)

    def _reparent_to(self, owner_handle: Optional[str]) -> None:
        """Set a new owner and preserve an existing owner-reactor relation."""
        previous_owner = self.dxf.get("owner")
        reactors = self.get_reactors()
        if previous_owner in reactors:
            reactors.remove(previous_owner)
            self._restore_owner_reactor_on_reparent = True
        if self._restore_owner_reactor_on_reparent and owner_handle is not None:
            reactors.append(owner_handle)
            self._restore_owner_reactor_on_reparent = False
        if reactors or self.reactors is not None:
            self.set_reactors(reactors)
        self.dxf.owner = owner_handle

    def _detach_from_owner(self) -> None:
        """Detach this FIELD while remembering an owner-reactor relation."""
        self._reparent_to(None)
        self.dxf.owner = "0"

    def _field_tree_handles(self) -> set[str]:
        """Returns handles of all live ``FIELD`` objects in this tree."""
        return self._handles(self.get_field_tree())

    def _reusable_field_handles(self) -> set[str]:
        """Return this validated tree's handles for same-key replacement."""
        doc = self.doc
        if doc is None:
            raise DXFStructureError("valid DXF document required")
        self._validate_field_subtree(doc, self, set())
        return self._field_tree_handles()

    def _delete_field_tree(
        self,
        *,
        exclude_handles: Optional[Iterable[str]] = None,
        validate_field_list: bool = True,
    ) -> None:
        """Delete this ``FIELD`` and all child ``FIELD`` objects.

        Args:
            exclude_handles: Handles in this tree to preserve.

        Side Effects:
            Removes deleted field handles from the root ``ACAD_FIELDLIST``.

        """
        doc = self.doc
        if doc is None:
            return
        if validate_field_list:
            doc.objects.get_field_list()
        protected_handles = (
            set(exclude_handles) if exclude_handles is not None else set()
        )
        fields = self._deletable_field_tree(protected_handles)
        self._release_protected_children(fields, protected_handles)
        try:
            try:
                self._discard_field_list_handles(doc, self._handles(fields))
            except DXFStructureError:
                if validate_field_list:
                    raise
        finally:
            for field in reversed(fields):
                if field.is_alive and field.doc is doc:
                    doc.objects.delete_entity(field)

    @staticmethod
    def _release_protected_children(
        fields: Iterable[Field], protected_handles: set[str]
    ) -> None:
        """Detach protected child roots before their old parents are destroyed."""
        if not protected_handles:
            return
        for field in fields:
            for child in field._live_owned_children():
                if child.dxf.handle in protected_handles:
                    child._detach_from_owner()

    def _register_field_tree(self) -> None:
        """Register this ``FIELD`` tree in the root ``ACAD_FIELDLIST``."""
        doc = self.doc
        if doc is None:
            raise DXFStructureError("valid DXF document required")
        self._preflight_field_list_registration(doc)
        field_list = doc.objects.setup_field_list()
        handles = list(field_list.handles)
        known_handles = set(handles)
        for field in self.get_field_tree():
            handle = field.dxf.handle
            if handle is None:
                continue
            if handle not in known_handles:
                handles.append(handle)
                known_handles.add(handle)
        field_list.handles = handles

    @staticmethod
    def _preflight_field_list_registration(doc: Drawing) -> None:
        """Validate document support and an existing FIELDLIST object."""
        if doc.dxfversion < DXF2000:
            raise DXFVersionError("FIELD resources require DXF R2000 or later")
        doc.objects.get_field_list()

    def _deletable_field_tree(self, exclude_handles: set[str]) -> list[Field]:
        """Returns live tree fields not protected by `exclude_handles`."""
        return [
            field
            for field in self._owned_field_tree()
            if field.dxf.handle not in exclude_handles
        ]

    def _owned_field_tree(self) -> list[Field]:
        """Return only FIELDs connected by verified ownership links."""
        result: list[Field] = []
        stack = [self]
        seen: set[int] = set()
        while stack:
            field = stack.pop()
            marker = id(field)
            if marker in seen:
                continue
            seen.add(marker)
            result.append(field)
            stack.extend(reversed(field._live_owned_children()))
        return result

    def _live_owned_children(self) -> list[Field]:
        """Resolve live children whose owner is this FIELD."""
        doc = self.doc
        handle = self.dxf.handle
        if doc is None or handle is None:
            return []
        children: list[Field] = []
        for child_handle in self.child_handles:
            child = doc.entitydb.get(child_handle)
            if (
                isinstance(child, Field)
                and child.is_alive
                and child.dxf.get("owner") == handle
            ):
                children.append(child)
        return children

    def _discard_replaced_children(self, replacement_tags: Tags) -> None:
        """Delete owned children omitted by a replacement FIELD payload."""
        replacement_handles = [
            str(tag.value) for tag in replacement_tags if tag.code == 360
        ]
        pending_children = self._pending_copy_children
        if pending_children is not None:
            if (
                set(replacement_handles) == {"0"}
                and len(replacement_handles) == len(pending_children)
            ):
                return
            for child in pending_children:
                child.destroy()
            self._pending_copy_children = []
            return
        doc = self.doc
        if doc is None:
            return
        protected_handles = set(replacement_handles)
        delete_roots = [
            child
            for child in self._live_owned_children()
            if child.dxf.handle not in protected_handles
        ]
        if not delete_roots:
            return
        doc.objects.get_field_list()
        promoted_fields: dict[str, Field] = {}
        for root in delete_roots:
            subtree = root._owned_field_tree()
            promoted_fields.update(
                {
                    field.dxf.handle: field
                    for field in subtree
                    if field.dxf.handle in protected_handles
                }
            )
            self._release_protected_children(subtree, protected_handles)
        for root in delete_roots:
            if root.is_alive:
                doc.objects.delete_entity(root)
        parent_handle = self.dxf.handle
        for field in promoted_fields.values():
            if field.is_alive:
                field._reparent_to(parent_handle)

    @staticmethod
    def _handles(fields: Iterable[Field]) -> set[str]:
        """Returns valid handles of `fields`."""
        handles: set[str] = set()
        for field in fields:
            handle = field.dxf.handle
            if handle is not None:
                handles.add(handle)
        return handles

    @staticmethod
    def _discard_field_list_handles(doc: Drawing, handles: Iterable[str]) -> None:
        """Remove `handles` from the root ``ACAD_FIELDLIST`` if present."""
        remove_handles = set(handles)
        if len(remove_handles) == 0:
            return
        field_list = doc.objects.get_field_list()
        if field_list is None:
            return
        field_list.handles = [
            handle for handle in field_list.handles if handle not in remove_handles
        ]

    @staticmethod
    def _field_text_checksum(text: str) -> float:
        return float(sum((index + 1) * ord(char) for index, char in enumerate(text)))

    @staticmethod
    def _field_code_tags(field_code: str) -> list[tuple[int, str]]:
        """Split a FIELD code into its primary and continuation tags."""
        chunks = [
            field_code[index : index + FIELD_CODE_CHUNK_SIZE]
            for index in range(0, len(field_code), FIELD_CODE_CHUNK_SIZE)
        ] or [""]
        return [(2, chunks[0]), *((3, chunk) for chunk in chunks[1:])]

    def set_text_wrapper(
        self,
        child_field: Union[Field, str],
        *,
        text: str = "",
        wrapper_flags: int = 13,
        include_checksum: bool = True,
    ) -> None:
        """Configure this FIELD as a single-child text wrapper."""
        self.set_text_wrapper_fields(
            [child_field],
            field_code="%<\\_FldIdx 0>%",
            text=text,
            wrapper_flags=wrapper_flags,
            include_checksum=include_checksum,
        )

    def set_text_wrapper_fields(
        self,
        child_fields: Sequence[Union[Field, str]],
        *,
        field_code: str,
        text: str = "",
        wrapper_flags: int = 13,
        include_checksum: bool = True,
    ) -> None:
        """Configure this FIELD as a text wrapper for multiple child FIELDs.

        Args:
            child_fields: Ordered child FIELD entities or handles.
            field_code: Wrapper text containing ``%<\\_FldIdx n>%`` references.
            text: Visible host-entity text used for the wrapper checksum.
            wrapper_flags: Raw wrapper flags stored in group code 94.
            include_checksum: Include the observed field-text checksum payload.
        """
        child_handles = self._require_field_handles(child_fields)
        self._validate_text_wrapper_code(field_code, len(child_handles))
        checksum = self._field_text_checksum(text)
        tags = [
            (1, "_text"),
            *self._field_code_tags(field_code),
            (90, len(child_handles)),
            *((360, handle) for handle in child_handles),
            (97, 0),
            (91, 63),
            (92, 0),
            (94, wrapper_flags),
            (95, 2),
            (96, 0),
            (300, ""),
        ]
        if include_checksum:
            tags.extend(
                [
                    (93, 1),
                    (6, "ACFD_FIELDTEXT_CHECKSUM"),
                    (93, 2),
                    (90, 2),
                    (140, checksum),
                    (94, 0),
                    (300, ""),
                    (302, ""),
                    (304, "ACVALUE_END"),
                ]
            )
        else:
            tags.append((93, 0))
        tags.extend(
            [
                (7, "ACFD_FIELD_VALUE"),
                (93, 3),
                (90, 0),
                (94, 0),
                (300, ""),
                (302, ""),
                (304, "ACVALUE_END"),
                (301, ""),
                (98, 0),
            ]
        )
        self.reset(tags)

    @classmethod
    def _require_field_handles(
        cls, child_fields: Sequence[Union[Field, str]],
    ) -> list[str]:
        """Return handles for independent FIELD roots without graph overlap."""
        handles: list[str] = []
        seen_fields: set[int] = set()
        seen_handles: set[str] = set()
        for child in child_fields:
            if isinstance(child, Field):
                if child.doc is not None and child.dxf.handle is not None:
                    cls._validate_field_subtree(child.doc, child, set())
                elif child.child_handles:
                    raise DXFStructureError("virtual FIELD root cannot have children")
                for field in child.get_field_tree():
                    marker = id(field)
                    handle = field.dxf.handle
                    if marker in seen_fields or (
                        handle is not None and handle in seen_handles
                    ):
                        raise DXFStructureError(
                            "FIELD tree contains a duplicate or overlap"
                        )
                    seen_fields.add(marker)
                    if handle is not None:
                        seen_handles.add(handle)
                handles.append(child.dxf.handle)
            elif isinstance(child, str):
                if child in seen_handles:
                    raise DXFStructureError(
                        "FIELD tree contains a duplicate or overlap"
                    )
                seen_handles.add(child)
                handles.append(child)
            else:
                raise DXFTypeError(
                    f"invalid FIELD reference: {type(child).__name__}"
                )
        if not handles or any(not handle for handle in handles):
            raise DXFStructureError("linked child FIELDs require valid handles")
        return handles

    def _set_acvar_payload(
        self,
        variable_name: str,
        *,
        field_format: str = "",
        value: str = "",
        display: str = "",
    ) -> None:
        """Build an ``AcVar``-style field payload."""
        field_code = f"\\AcVar {variable_name}"
        if field_format:
            field_code += f' \\f "{field_format}"'

        value_dtype = 4
        self.reset(
            [
                (1, "AcVar"),
                *self._field_code_tags(field_code),
                (90, 0),
                (97, 0),
                (91, 63),
                (92, 0),
                (94, 59),
                (95, 2),
                (96, 0),
                (300, ""),
                (93, 1),
                (6, "Variable"),
                (93, 2),
                (90, 4),
                (1, variable_name),
                (94, 0),
                (300, ""),
                (302, ""),
                (304, "ACVALUE_END"),
                (7, "ACFD_FIELD_VALUE"),
                (93, 4),
                (90, value_dtype),
                (1, value),
                (94, 0),
                (300, ""),
                (302, ""),
                (304, "ACVALUE_END"),
                (301, display),
                (98, len(display)),
            ]
        )

    def set_acvar(self, name: str, *, value: str = "", display: str = "") -> None:
        """Build a simple ``AcVar`` field payload."""
        self._set_acvar_payload(name, value=value, display=display)

    def set_dwgprops(
        self,
        name: str,
        *,
        field_format: str = "",
        value: str = "",
        display: str = "",
    ) -> None:
        """Build a drawing-properties field payload using the observed
        ``AcVar CustomDP.<Name>`` pattern.
        """
        self._set_acvar_payload(
            f"CustomDP.{name}",
            field_format=field_format,
            value=value,
            display=display,
        )

    def set_acexpr(
        self,
        expression: str,
        child_fields: Sequence[Union[Field, str]],
        *,
        field_format: str = "%lu2",
        value: Any = None,
        display: str = "",
        include_eval_option: bool = True,
    ) -> None:
        handles = self._require_field_handles(child_fields)

        field_code = f"\\AcExpr {expression}"
        if field_format:
            field_code += f' \\f "{field_format}"'

        tags: list[tuple[int, Any]] = [
            (1, "AcExpr"),
            *self._field_code_tags(field_code),
            (90, len(handles)),
            *[(360, handle) for handle in handles],
            (97, 0),
            (91, 0 if include_eval_option else 63),
            (92, 0),
            (94, 59),
            (95, 2),
            (96, 0),
            (300, ""),
        ]
        if include_eval_option:
            tags.extend(
                [
                    (93, 1),
                    (6, "ACAD_ROUNDTRIP_2008_FIELD_EVALOPTION"),
                    (93, 2),
                    (90, 1),
                    (91, 63),
                    (94, 0),
                    (300, ""),
                    (302, ""),
                    (304, "ACVALUE_END"),
                ]
            )
        else:
            tags.append((93, 0))

        if value is not None or display:
            tags.extend(self._field_value_tags(value, display, field_format))
        self.reset(tags)

    @classmethod
    def _build_virtual_acexpr(
        cls,
        expression: str,
        child_fields: Sequence[Field],
        *,
        field_format: str = "%lu2",
        value: Any = None,
        display: str = "",
        include_eval_option: bool = True,
    ) -> Field:
        """Build a detached expression FIELD with detached child FIELDs.

        :param expression: Native expression containing child-index references.
        :param child_fields: Detached child FIELD roots.
        :param field_format: Native expression field format.
        :param value: Optional cached numeric value.
        :param display: Optional cached display text.
        :param include_eval_option: Include standard FIELD evaluation metadata.
        :return: Detached expression FIELD tree.
        """
        children = list(child_fields)
        if not children:
            raise DXFStructureError("expression requires child FIELDs")
        placeholders = [format(index, "X") for index in range(len(children))]
        expression_field = cls()
        expression_field.set_acexpr(
            expression,
            placeholders,
            field_format=field_format,
            value=value,
            display=display,
            include_eval_option=include_eval_option,
        )
        expression_field._pending_copy_children = children
        expression_field._validate_copyable_tree(set())
        return expression_field

    @staticmethod
    def build_acexpr(
        doc,
        expression: str,
        child_fields: Sequence[Field],
        *,
        field_format: str = "%lu2",
        value: Any = None,
        display: str = "",
        include_eval_option: bool = True,
    ) -> Field:
        children = list(child_fields)
        for child in children:
            if not isinstance(child, Field):
                dxftype = (
                    child.dxftype()
                    if isinstance(child, DXFEntity)
                    else type(child).__name__
                )
                raise DXFTypeError(f"invalid DXF type: {dxftype}")
            if child.doc is not None and child.doc is not doc:
                raise DXFStructureError("field belongs to a different DXF document")
        expr_children: list[Field] = []
        for child in children:
            child_copy = doc.objects.add_field(owner="0")
            child_copy.reset(child.tags)
            if child_copy.evaluator_id == "AcObjProp":
                child_copy.normalize_acobjprop_cache()
            expr_children.append(child_copy)

        expr = doc.objects.add_field(owner="0")
        expr.set_acexpr(
            expression,
            expr_children,
            field_format=field_format,
            value=value,
            display=display,
            include_eval_option=include_eval_option,
        )
        for child_copy in expr_children:
            child_copy.dxf.owner = expr.dxf.handle
        return expr

    def set_acobjprop(
        self,
        target: Union[DXFEntity, str],
        property_name: str,
        *,
        field_format: str = "%lu2",
        value: Any = None,
        display: str = "",
    ) -> None:
        """Build a simple ``AcObjProp`` field payload.

        Args:
            target: referenced DXF entity or handle string
            property_name: AutoCAD object property name, e.g. ``"Length"``
            field_format: field formatting code
            value: optional evaluated property value
            display: optional visible display text

        """
        if isinstance(target, str):
            handle = target
        else:
            handle = target.dxf.handle
        if not handle:
            raise DXFStructureError("AcObjProp target requires a valid handle")

        field_code = f"\\AcObjProp Object(%<\\_ObjIdx 0>%).{property_name}"
        if field_format:
            field_code += f' \\f "{field_format}"'

        tags: list[tuple[int, Any]] = [
            (1, "AcObjProp"),
            *self._field_code_tags(field_code),
            (90, 0),
            (97, 1),
            (331, handle),
            (91, 63),
            (92, 0),
            (94, 59),
            (95, 2),
            (96, 0),
            (300, ""),
            (93, 2),
            (6, "ObjectPropertyId"),
            (93, 2),
            (90, 64),
            (330, handle),
            (94, 0),
            (300, ""),
            (302, ""),
            (304, "ACVALUE_END"),
            (6, "ObjectPropertyName"),
            (93, 2),
            (90, 4),
            (1, property_name),
            (94, 0),
            (300, ""),
            (302, ""),
            (304, "ACVALUE_END"),
        ]

        if value is not None or display:
            tags.extend(self._field_value_tags(value, display, field_format))

        self.reset(tags)

    @staticmethod
    def _field_value_tags(value: Any, display: str, field_format: str) -> list[tuple[int, Any]]:
        if value is None:
            dtype = 4
            value_tag = (1, "")
        elif isinstance(value, bool):
            dtype = 1
            value_tag = (91, int(value))
        elif isinstance(value, int):
            dtype = 1
            value_tag = (91, value)
        elif isinstance(value, float):
            dtype = 2
            value_tag = (140, value)
        else:
            dtype = 4
            value_tag = (1, str(value))

        return [
            (7, "ACFD_FIELD_VALUE"),
            (93, 4),
            (90, dtype),
            value_tag,
            (94, 0),
            (300, field_format),
            (302, display),
            (304, "ACVALUE_END"),
            (301, display),
            (98, len(display)),
        ]

    def normalize_acobjprop_cache(self) -> None:
        in_field_value = False
        top_level_flags_done = False
        for index, tag in enumerate(self.tags):
            if not top_level_flags_done and tag.code == 94:
                self.tags[index] = dxftag(94, 27)
                top_level_flags_done = True
                continue
            if tag.code == 7 and tag.value == "ACFD_FIELD_VALUE":
                in_field_value = True
                continue
            if in_field_value:
                if tag.code == 93:
                    self.tags[index] = dxftag(93, 0)
                elif tag.code == 302:
                    self.tags[index] = dxftag(302, "")
                elif tag.code == 301:
                    self.tags[index] = dxftag(301, "")
                elif tag.code == 98:
                    break
        self._sync_dxf_attribs()

    def load_dxf_attribs(
        self, processor: Optional[SubclassProcessor] = None
    ) -> DXFNamespace:
        dxf = super().load_dxf_attribs(processor)
        self.dxf = dxf
        if processor:
            try:
                tags = processor.subclasses[1]
            except IndexError:
                raise DXFStructureError(
                    f"Missing subclass AcDbField in FIELD(#{dxf.handle})"
                )
            self.reset(tags)
        return dxf

    @staticmethod
    def _collect_field_code(tags: Tags) -> str:
        parts: list[str] = []
        has_primary_tag = False
        for tag in tags:
            if tag.code not in (2, 3):
                if parts:
                    break
                continue
            parts.append(str(tag.value))
            has_primary_tag |= tag.code == 2
        if has_primary_tag:
            return "".join(parts)
        return ""

    def _sync_dxf_attribs(self) -> None:
        for attrib_name in (
            "evaluator_id",
            "field_code",
            "field_code_overflow",
            "n_child_fields",
        ):
            self.dxf.discard(attrib_name)

        for tag in self.tags:
            if tag.code == 1 and not self.dxf.hasattr("evaluator_id"):
                self.dxf.evaluator_id = tag.value
            elif tag.code == 2 and not self.dxf.hasattr("field_code"):
                self.dxf.field_code = tag.value
            elif tag.code == 3 and not self.dxf.hasattr("field_code_overflow"):
                self.dxf.field_code_overflow = tag.value
            elif tag.code == 90 and not self.dxf.hasattr("n_child_fields"):
                self.dxf.n_child_fields = tag.value

    def export_entity(self, tagwriter: AbstractTagWriter) -> None:
        super().export_entity(tagwriter)
        tagwriter.write_tag2(SUBCLASS_MARKER, acdb_field.name)
        if self.tags:
            tagwriter.write_tags(Tags(totags(self.tags)))
        else:
            self.dxf.export_dxf_attribs(
                tagwriter,
                [
                    "evaluator_id",
                    "field_code",
                    "field_code_overflow",
                    "n_child_fields",
                ],
            )

    def reset(self, tags: Iterable[Union[DXFTag, tuple[int, Any]]]) -> None:
        replacement_tags = Tags(totags(tags))
        if len(replacement_tags) and replacement_tags[0] == (
            SUBCLASS_MARKER,
            acdb_field.name,
        ):
            del replacement_tags[0]
        self._discard_replaced_children(replacement_tags)
        self.tags = replacement_tags
        self._sync_dxf_attribs()

    def extend(self, tags: Iterable[Union[DXFTag, tuple[int, Any]]]) -> None:
        self.tags.extend(totags(tags))
        self._sync_dxf_attribs()

    def clear(self) -> None:
        self.reset(())

    def destroy(self) -> None:
        """Destroy this FIELD and every verified hard-owned child FIELD."""
        if not self.is_alive:
            return
        pending_children = self._pending_copy_children or []
        self._pending_copy_children = None
        for child in pending_children:
            child.destroy()

        doc = self.doc
        handle = self.dxf.handle
        if doc is not None and handle is not None:
            children = self._live_owned_children()
            try:
                self._discard_field_list_handles(doc, [handle])
            except DXFStructureError:
                pass
            for child in children:
                if child.is_alive:
                    doc.objects.delete_entity(child)
        self._clear_pending_copy_state()
        super().destroy()


def is_dxf_object(entity: DXFEntity) -> TypeGuard[DXFObject]:
    """Returns ``True`` if the `entity` is a DXF object from the OBJECTS section,
    otherwise the entity is a table or class entry or a graphic entity which can
    not reside in the OBJECTS section.
    """
    if isinstance(entity, DXFObject):
        return True
    if isinstance(entity, DXFTagStorage) and not entity.is_graphic_entity:
        return True
    return False

# Copyright (c) 2019-2024 Manfred Moitzi
# License: MIT License
from __future__ import annotations
from typing import TYPE_CHECKING, Iterable, Union, Any, Optional, Sequence
from typing_extensions import Self, TypeGuard
import logging
import array
from dxfpy.lldxf import validator
from dxfpy.lldxf.const import DXF2000, DXFStructureError, DXFTypeError, SUBCLASS_MARKER
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
from .copy import default_copy

if TYPE_CHECKING:
    from dxfpy.audit import Auditor
    from dxfpy.document import Drawing
    from dxfpy.entities import DXFNamespace
    from dxfpy.lldxf.tagwriter import AbstractTagWriter

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

    def copy_data(self, entity: Self, copy_strategy=default_copy) -> None:
        assert isinstance(entity, Field)
        entity.tags = Tags(self.tags)

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

    def _field_tree_handles(self) -> set[str]:
        """Returns handles of all live ``FIELD`` objects in this tree."""
        return self._handles(self.get_field_tree())

    def _delete_field_tree(
        self, *, exclude_handles: Optional[Iterable[str]] = None
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
        protected_handles = (
            set(exclude_handles) if exclude_handles is not None else set()
        )
        fields = self._deletable_field_tree(protected_handles)
        self._discard_field_list_handles(doc, self._handles(fields))
        for field in reversed(fields):
            if field.is_alive and field.doc is doc:
                doc.objects.delete_entity(field)

    def _register_field_tree(self) -> None:
        """Register this ``FIELD`` tree in the root ``ACAD_FIELDLIST``."""
        doc = self.doc
        if doc is None:
            raise DXFStructureError("valid DXF document required")
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

    def _deletable_field_tree(self, exclude_handles: set[str]) -> list[Field]:
        """Returns live tree fields not protected by `exclude_handles`."""
        return [
            field
            for field in self.get_field_tree()
            if field.dxf.handle not in exclude_handles
        ]

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

    def set_text_wrapper(
        self,
        child_field: Union[Field, str],
        *,
        text: str = "",
        wrapper_flags: int = 13,
        include_checksum: bool = True,
    ) -> None:
        if isinstance(child_field, Field):
            child_handle = child_field.dxf.handle
        else:
            child_handle = child_field
        if not child_handle:
            raise DXFStructureError("linked child FIELD requires a valid handle")
        checksum = self._field_text_checksum(text)
        tags = [
            (1, "_text"),
            (2, "%<\\_FldIdx 0>%"),
            (90, 1),
            (360, child_handle),
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
                (2, field_code),
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
        handles: list[str] = []
        for child in child_fields:
            if isinstance(child, Field):
                handle = child.dxf.handle
            else:
                handle = str(child)
            if not handle:
                raise DXFStructureError("AcExpr child FIELD requires a valid handle")
            handles.append(handle)

        field_code = f"\\AcExpr {expression}"
        if field_format:
            field_code += f' \\f "{field_format}"'

        tags: list[tuple[int, Any]] = [
            (1, "AcExpr"),
            (2, field_code),
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
        expr_children: list[Field] = []
        for child in child_fields:
            if not isinstance(child, Field):
                dxftype = (
                    child.dxftype()
                    if isinstance(child, DXFEntity)
                    else type(child).__name__
                )
                raise DXFTypeError(f"invalid DXF type: {dxftype}")
            if child.doc is not None and child.doc is not doc:
                raise DXFStructureError("field belongs to a different DXF document")
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
            (2, field_code),
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
        for index, tag in enumerate(tags):
            if tag.code == 2:
                parts = [tag.value]
                index += 1
                while index < len(tags) and tags[index].code == 3:
                    parts.append(tags[index].value)
                    index += 1
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
        self.tags = Tags(totags(tags))
        if len(self.tags) and self.tags[0] == (SUBCLASS_MARKER, acdb_field.name):
            del self.tags[0]
        self._sync_dxf_attribs()

    def extend(self, tags: Iterable[Union[DXFTag, tuple[int, Any]]]) -> None:
        self.tags.extend(totags(tags))
        self._sync_dxf_attribs()

    def clear(self) -> None:
        self.tags.clear()
        self._sync_dxf_attribs()


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

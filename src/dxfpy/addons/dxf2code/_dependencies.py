from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Protocol, cast

from dxfpy.document import Drawing
from dxfpy.entities import DXFEntity, is_graphic_entity
from dxfpy.entities.acad_table import (
    AcadTable,
    AcadTableBlockContent,
    TableContent,
    TableStyle,
)
from dxfpy.entities.attrib import BaseAttrib
from dxfpy.entities.blockrecord import BlockRecord
from dxfpy.entities.dimstyle import (
    DIM_ARROW_HEAD_ATTRIBS,
    DIM_LINETYPE_ATTRIBS,
    DIM_TEXT_STYLE_ATTR,
    DimStyle,
)
from dxfpy.entities.layer import Layer
from dxfpy.entities.ltype import Linetype
from dxfpy.entities.mline import MLineStyle
from dxfpy.lldxf import const, validator
from dxfpy.render.arrows import ARROWS
from dxfpy.sections.blocks import is_anonymous_block

from ._api import block_to_code, entities_to_code, table_entries_to_code
from ._code import Code

__all__ = [
    "entities_to_code_with_dependencies",
    "namespace_resource_names",
]

_STANDARD_RESOURCE_NAMES = {
    "layers": frozenset({"0", "defpoints"}),
    "linetypes": frozenset({"byblock", "bylayer", "continuous"}),
    "styles": frozenset({"standard"}),
    "dimstyles": frozenset({"standard"}),
}
_TARGET_DOCUMENT_VARIABLE = "_dxfpy_target_document"
_TARGET_LAYOUT_VARIABLE = "_dxfpy_target_layout"
_MAX_RESOURCE_NAME_LENGTH = 255
_HEADER_NAME_REFERENCES = {
    "$CLAYER": "layers",
    "$CELTYPE": "linetypes",
    "$TEXTSTYLE": "styles",
    "$DIMSTYLE": "dimstyles",
    "$DIMBLK": "blocks",
    "$DIMBLK1": "blocks",
    "$DIMBLK2": "blocks",
    "$DIMLDRBLK": "blocks",
}
_TABLE_ATTRIBUTE_BY_DXFTYPE = {
    "LAYER": "layers",
    "LTYPE": "linetypes",
    "STYLE": "styles",
    "DIMSTYLE": "dimstyles",
}


class _NamedDxfTable(Protocol):
    """Named DXF table lookup behavior."""

    def get(self, name: str) -> DXFEntity | None:
        """Return the named table entry when present."""


class _MutableNamedDxfTable(_NamedDxfTable, Protocol):
    """Named DXF table behavior required for resource namespacing."""

    def __iter__(self) -> Iterable[DXFEntity]:
        """Iterate over table entries."""

    def replace(self, name: str, entry: DXFEntity) -> None:
        """Replace the entry indexed by `name`."""


def namespace_resource_names(
    document: Drawing,
    namespace: str,
    *,
    protected_names: Mapping[str, Iterable[str]] | None = None,
) -> None:
    """Namespace collision-prone resources and their direct references.

    Standard DXF resources retain their names. Additional names can be protected
    per table by the `protected_names` mapping. The source `document` is modified
    in place.

    :param document: Source drawing to namespace.
    :param namespace: Prefix for deterministic replacement names.
    :param protected_names: Additional names to preserve by table attribute.
    """
    _ResourceNameNamespacer(document, namespace, protected_names).namespace()


def entities_to_code_with_dependencies(
    document: Drawing,
    entities: Iterable[DXFEntity],
    *,
    layout: str = "layout",
    drawing: str = "doc",
    ignore: Iterable[str] | None = None,
) -> Code:
    """Generate entity source preceded by its transitive DXF dependencies.

    The `layout` and `drawing` arguments must be Python expressions available
    when the generated source is executed.

    :param document: Drawing that owns the source entities and resources.
    :param entities: Source entities to translate.
    :param layout: Target layout variable used by generated entity source.
    :param drawing: Target drawing variable used by dependency source.
    :param ignore: DXF entity types to omit.
    :return: Source code with resources, nested blocks, and entities in order.
    """
    _require_expression("layout", layout)
    _require_expression("drawing", drawing)
    ignored = {dxftype.upper() for dxftype in ignore or ()}
    selected = tuple(entity for entity in entities if entity.dxftype() not in ignored)
    entity_code = entities_to_code(
        selected,
        layout=_TARGET_LAYOUT_VARIABLE,
        drawing=_TARGET_DOCUMENT_VARIABLE,
    )
    dependencies = _CodeDependencyResolver(document, _TARGET_DOCUMENT_VARIABLE).resolve(
        selected, entity_code.entity_handles
    )
    result = Code()
    result.add_line(f"{_TARGET_DOCUMENT_VARIABLE} = ({drawing})")
    result.add_line(f"{_TARGET_LAYOUT_VARIABLE} = ({layout})")
    result.merge(dependencies)
    result.merge(entity_code)
    return result


def _require_expression(argument: str, value: str) -> None:
    """Require a valid Python expression for generated assignment source."""
    if not isinstance(value, str):
        raise TypeError(f"{argument} must be a str")
    if not value.strip():
        raise ValueError(f"{argument} must be a Python expression")
    try:
        compile(
            f"_dxfpy_expression_value = ({value})",
            "<dxf2code-expression>",
            "exec",
        )
    except SyntaxError as exc:
        raise ValueError(f"{argument} must be a Python expression") from exc


class _ResourceNameNamespacer:
    """Apply deterministic names to source-document resources."""

    def __init__(
        self,
        document: Drawing,
        namespace: str,
        protected_names: Mapping[str, Iterable[str]] | None,
    ) -> None:
        """Initialize resource mappings for `document`."""
        if not isinstance(namespace, str):
            raise TypeError("namespace must be a str")
        if not namespace:
            raise ValueError("namespace cannot be empty")
        if not validator.is_valid_table_name(namespace):
            raise ValueError("namespace contains invalid DXF name characters")
        self._document = document
        self._namespace = namespace
        self._protected = self._protected_names(protected_names)
        self._tables = self._table_mappings()
        self._blocks = self._block_mapping()
        self._mleader_style_handles: dict[str, str] = {}
        self._table_style_handles: dict[str, str] = {}

    def namespace(self) -> None:
        """Rename resources and update their direct references."""
        self._mleader_style_handles = self._duplicate_mleader_styles()
        self._table_style_handles = self._duplicate_table_styles()
        self._update_entity_references()
        self._update_layer_references()
        self._update_dimstyle_references()
        self._update_table_style_references()
        self._update_header_references()
        self._rename_tables()
        self._rename_blocks()

    @staticmethod
    def _protected_names(
        additions: Mapping[str, Iterable[str]] | None,
    ) -> dict[str, frozenset[str]]:
        """Return normalized standard and caller-protected names."""
        protected = dict(_STANDARD_RESOURCE_NAMES)
        for attribute, names in (additions or {}).items():
            if attribute not in protected:
                raise ValueError(f"unsupported resource table: {attribute}")
            protected[attribute] = protected[attribute] | frozenset(
                name.lower() for name in names
            )
        return protected

    def _table_mappings(self) -> dict[str, dict[str, str]]:
        """Return deterministic mappings for collision-prone named tables."""
        mappings: dict[str, dict[str, str]] = {}
        for attribute, protected in self._protected.items():
            table = cast(_MutableNamedDxfTable, getattr(self._document, attribute))
            mappings[attribute] = self._table_mapping(table, attribute, protected)
        return mappings

    def _table_mapping(
        self,
        table: _MutableNamedDxfTable,
        attribute: str,
        protected: frozenset[str],
    ) -> dict[str, str]:
        """Return one deterministic table-name mapping."""
        mapping: dict[str, str] = {}
        occupied = {
            entry.dxf.name.lower()
            for entry in table
            if isinstance(entry.dxf.get("name"), str)
        }
        for index, entry in enumerate(table):
            name = entry.dxf.get("name")
            if not isinstance(name, str) or name.lower() in protected:
                continue
            base_name = f"{self._namespace}_{attribute}_{index}"
            mapping[name.lower()] = self._available_name(base_name, occupied)
        return mapping

    def _block_mapping(self) -> dict[str, str]:
        """Return deterministic mappings for non-layout block definitions."""
        blocks = list(self._document.blocks)
        occupied = {block.name.lower() for block in blocks}
        mapping: dict[str, str] = {}
        for index, block in enumerate(blocks):
            if block.is_any_layout:
                continue
            if self._is_managed_arrow_block(block.name):
                continue
            prefix = block.name[:2] if is_anonymous_block(block.name) else ""
            base_name = f"{prefix}{self._namespace}_blocks_{index}"
            mapping[block.name.lower()] = self._available_name(base_name, occupied)
        return mapping

    @staticmethod
    def _is_managed_arrow_block(name: str) -> bool:
        """Return whether `name` identifies a managed arrow definition."""
        if ARROWS.is_dxfpy_arrow(name):
            return True
        return name.startswith("_") and ARROWS.is_acad_arrow(ARROWS.arrow_name(name))

    def _duplicate_mleader_styles(self) -> dict[str, str]:
        """Duplicate MLEADERSTYLE objects under isolated names."""
        handles: dict[str, str] = {}
        styles = list(self._document.mleader_styles)
        occupied = {name.lower() for name, _ in styles}
        for index, (name, style) in enumerate(styles):
            base_name = f"{self._namespace}_mleader_styles_{index}"
            isolated_name = self._available_name(base_name, occupied)
            duplicate = self._document.mleader_styles.duplicate_entry(
                name, isolated_name
            )
            handles[style.dxf.handle] = duplicate.dxf.handle
        return handles

    def _duplicate_table_styles(self) -> dict[str, str]:
        """Duplicate TABLESTYLE objects under isolated names."""
        handles: dict[str, str] = {}
        styles = list(self._document.table_styles)
        occupied = {name.lower() for name, _ in styles}
        for index, (name, style) in enumerate(styles):
            base_name = f"{self._namespace}_table_styles_{index}"
            isolated_name = self._available_name(base_name, occupied)
            duplicate = self._document.table_styles.duplicate_entry(name, isolated_name)
            handles[style.dxf.handle] = duplicate.dxf.handle
        return handles

    @staticmethod
    def _available_name(base_name: str, occupied: set[str]) -> str:
        """Return and reserve a case-insensitively unique resource name."""
        suffix_index = 0
        candidate = base_name[:_MAX_RESOURCE_NAME_LENGTH]
        while candidate.lower() in occupied:
            suffix_index += 1
            suffix = f"_{suffix_index}"
            prefix = base_name[: _MAX_RESOURCE_NAME_LENGTH - len(suffix)]
            candidate = f"{prefix}{suffix}"
        occupied.add(candidate.lower())
        return candidate

    def _update_entity_references(self) -> None:
        """Update names and handles stored directly by entities."""
        attributes = {
            "layer": self._tables["layers"],
            "linetype": self._tables["linetypes"],
            "style": self._tables["styles"],
            "dimstyle": self._tables["dimstyles"],
        }
        for entity in self._document.entitydb.values():
            if not entity.is_alive:
                continue
            for attribute, mapping in attributes.items():
                self._replace_dxf_name(entity, attribute, mapping)
            if entity.dxftype() == "INSERT":
                self._replace_dxf_name(entity, "name", self._blocks)
            if entity.dxf.is_supported("geometry"):
                self._replace_dxf_name(entity, "geometry", self._blocks)
            if entity.dxftype() == "MULTILEADER":
                self._replace_dxf_handle(
                    entity, "style_handle", self._mleader_style_handles
                )
            if isinstance(entity, (AcadTable, AcadTableBlockContent)):
                self._replace_dxf_handle(
                    entity, "table_style_id", self._table_style_handles
                )
                self._update_acad_table_references(entity)
            if isinstance(entity, TableContent):
                handle = entity.table_style_handle
                if handle in self._table_style_handles:
                    entity.table_style_handle = self._table_style_handles[handle]
            if isinstance(entity, BaseAttrib) and entity.has_embedded_mtext_entity:
                self._update_embedded_mtext_references(entity)
            if isinstance(entity, MLineStyle):
                self._update_mline_style_references(entity)

    def _update_embedded_mtext_references(self, entity: BaseAttrib) -> None:
        """Update resources stored by an embedded ATTRIB/ATTDEF MTEXT entity."""
        mtext = entity.virtual_mtext_entity()
        self._replace_dxf_name(mtext, "style", self._tables["styles"])
        self._replace_dxf_name(mtext, "layer", self._tables["layers"])
        self._replace_dxf_name(mtext, "linetype", self._tables["linetypes"])
        entity.set_mtext(mtext, graphic_properties=False)

    def _update_mline_style_references(self, style: MLineStyle) -> None:
        """Update linetype names stored by MLINESTYLE elements."""
        mapping = self._tables["linetypes"]
        style.elements.elements = [
            element._replace(linetype=self._replacement_name(element.linetype, mapping))
            for element in style.elements
        ]

    def _update_layer_references(self) -> None:
        """Update linetype names selected by layer table entries."""
        for layer in self._document.layers:
            self._replace_dxf_name(layer, "linetype", self._tables["linetypes"])

    def _update_dimstyle_references(self) -> None:
        """Update resources selected by dimension-style table entries."""
        for dimstyle in self._document.dimstyles:
            self._replace_dxf_name(
                dimstyle, DIM_TEXT_STYLE_ATTR, self._tables["styles"]
            )
            for attribute in DIM_LINETYPE_ATTRIBS:
                self._replace_dxf_name(dimstyle, attribute, self._tables["linetypes"])
            for attribute in DIM_ARROW_HEAD_ATTRIBS:
                self._replace_dxf_name(dimstyle, attribute, self._blocks)

    def _update_acad_table_references(
        self, table: AcadTable | AcadTableBlockContent
    ) -> None:
        """Update names stored in semantic ACAD_TABLE cell data."""
        if table.data is None:
            return
        for cell in table.data.cells:
            if cell.text_style:
                cell.text_style = self._replacement_name(
                    cell.text_style, self._tables["styles"]
                )
            if cell.wrapper_block_name:
                cell.wrapper_block_name = self._replacement_name(
                    cell.wrapper_block_name, self._blocks
                )

    def _update_table_style_references(self) -> None:
        """Update text-style names stored by TABLESTYLE objects."""
        for _, table_style in self._document.table_styles:
            if not isinstance(table_style, TableStyle) or table_style.data is None:
                continue
            for cell_style in table_style.data.cell_styles:
                cell_style.text_style = self._replacement_name(
                    cell_style.text_style, self._tables["styles"]
                )

    def _update_header_references(self) -> None:
        """Update current resource names and MLEADERSTYLE handle in HEADER."""
        header = self._document.header
        mappings = {**self._tables, "blocks": self._blocks}
        for variable, attribute in _HEADER_NAME_REFERENCES.items():
            value = header.get(variable)
            if isinstance(value, str):
                header[variable] = self._replacement_name(value, mappings[attribute])
        style_handle = header.get("$CMLSTYLE")
        if style_handle in self._mleader_style_handles:
            header["$CMLSTYLE"] = self._mleader_style_handles[style_handle]

    @staticmethod
    def _replacement_name(name: str, mapping: Mapping[str, str]) -> str:
        """Return the case-insensitive replacement for `name` when present."""
        return mapping.get(name.lower(), name)

    @staticmethod
    def _replace_dxf_name(
        entity: DXFEntity, attribute: str, mapping: Mapping[str, str]
    ) -> None:
        """Replace one case-insensitive DXF name reference when mapped."""
        if not entity.dxf.is_supported(attribute):
            return
        value = entity.dxf.get(attribute)
        replacement = mapping.get(value.lower()) if isinstance(value, str) else None
        if replacement is not None:
            entity.dxf.set(attribute, replacement)

    @staticmethod
    def _replace_dxf_handle(
        entity: DXFEntity, attribute: str, mapping: Mapping[str, str]
    ) -> None:
        """Replace one DXF handle reference when mapped."""
        if not entity.dxf.is_supported(attribute):
            return
        replacement = mapping.get(entity.dxf.get(attribute))
        if replacement is not None:
            entity.dxf.set(attribute, replacement)

    def _rename_tables(self) -> None:
        """Apply mapped names to source table indexes and entries."""
        for attribute, mapping in self._tables.items():
            table = cast(_MutableNamedDxfTable, getattr(self._document, attribute))
            for old_key, new_name in mapping.items():
                entry = table.get(old_key)
                if not isinstance(entry, DXFEntity):
                    continue
                if isinstance(entry, Layer):
                    entry.rename(new_name)
                else:
                    entry.dxf.name = new_name
                    table.replace(old_key, entry)

    def _rename_blocks(self) -> None:
        """Apply mapped names to source block records."""
        for old_key, new_name in self._blocks.items():
            self._document.blocks.rename_block(old_key, new_name)


class _CodeDependencyResolver:
    """Build dependency-ordered DXF table and block source."""

    def __init__(self, document: Drawing, drawing: str) -> None:
        """Initialize a resolver for one source document."""
        self._document = document
        self._drawing = drawing
        self._result = Code()
        self._seen_tables: set[tuple[str, str]] = set()
        self._seen_shx_styles: set[str] = set()
        self._seen_blocks: set[str] = set()
        self._seen_objects: set[str] = set()
        self._registered_entities: set[int] = set()
        self._scope_handles: set[str] = set()

    def resolve(
        self, entities: Iterable[DXFEntity], entity_handles: Iterable[str]
    ) -> Code:
        """Return transitive dependencies for generated entity source."""
        self._register_scope_resources(tuple(entities), entity_handles)
        return self._result

    def _register_scope_resources(
        self, entities: tuple[DXFEntity, ...], entity_handles: Iterable[str]
    ) -> None:
        """Register resources while enforcing one generated handle-map scope."""
        previous_handles = self._scope_handles
        self._scope_handles = set(entity_handles)
        try:
            self._validate_field_references(entities)
            for entity in entities:
                self._register_entity(entity)
        finally:
            self._scope_handles = previous_handles

    def _validate_field_references(self, entities: Iterable[DXFEntity]) -> None:
        """Reject FIELD object pointers that cannot use this scope's entity map."""
        seen: set[int] = set()
        for entity in entities:
            for host in (entity, *getattr(entity, "attribs", ())):
                for field in self._hosted_fields(host):
                    for nested in field.get_field_tree():
                        marker = id(nested)
                        if marker in seen:
                            continue
                        seen.add(marker)
                        self._validate_field_object_handles(nested.object_handles)

    @staticmethod
    def _hosted_fields(entity: DXFEntity) -> Iterable[DXFEntity]:
        """Yield FIELD roots hosted by one supported entity."""
        has_field_dict = getattr(entity, "has_field_dict", None)
        get_field_dict = getattr(entity, "get_field_dict", None)
        if callable(has_field_dict) and callable(get_field_dict) and has_field_dict():
            yield from (field for _, field in get_field_dict().items())
        if isinstance(entity, (AcadTable, AcadTableBlockContent)) and entity.data:
            for cell in entity.data.cells:
                field = entity.get_cell_field(cell.row, cell.col)
                if field is not None:
                    yield field

    def _validate_field_object_handles(self, handles: Iterable[str]) -> None:
        """Require FIELD object-property targets in the current generated scope."""
        for handle in handles:
            if handle not in self._scope_handles:
                raise const.DXFStructureError(
                    "FIELD object-property reference crosses a generated entity scope: "
                    f"#{handle}"
                )

    def _register_entity(self, entity: DXFEntity) -> None:
        """Register one entity's resource graph exactly once."""
        marker = id(entity)
        if marker in self._registered_entities:
            return
        self._registered_entities.add(marker)
        entity.register_resources(self)
        if isinstance(entity, (AcadTable, AcadTableBlockContent)):
            self._register_acad_table_resources(entity)
        elif isinstance(entity, TableStyle):
            self._register_table_style_resources(entity)

    def _register_acad_table_resources(
        self, table: AcadTable | AcadTableBlockContent
    ) -> None:
        """Register semantic ACAD_TABLE resources absent from its base protocol."""
        style = getattr(table, "get_table_style", lambda: None)()
        if isinstance(style, DXFEntity):
            self._emit_named_object(style)
        if table.data is None:
            return
        for cell in table.data.cells:
            if cell.text_style:
                self.add_text_style(cell.text_style)
            self.add_handle(cell.block_record_handle)

    def _register_table_style_resources(self, style: TableStyle) -> None:
        """Register text styles selected by TABLESTYLE cell-style buckets."""
        if style.data is None:
            return
        for cell_style in style.data.cell_styles:
            if cell_style.text_style:
                self.add_text_style(cell_style.text_style)

    def add_entity(self, entity: DXFEntity, block_key: str = "0") -> None:
        """Register a resource entity requested by an entity protocol."""
        table_attribute = _TABLE_ATTRIBUTE_BY_DXFTYPE.get(entity.dxftype())
        name = entity.dxf.get("name")
        if table_attribute and isinstance(name, str) and name:
            self._emit_table_entry(table_attribute, name)
        elif entity.dxftype() == "STYLE" and getattr(entity, "is_shape_file", False):
            self._emit_shx_style(entity)
        elif isinstance(entity, BlockRecord):
            self.add_block_name(entity.dxf.name)
        elif entity.dxftype() in {"MLEADERSTYLE", "TABLESTYLE"}:
            self._emit_named_object(entity)
        else:
            self._register_entity(entity)

    def add_block(self, block_record: BlockRecord) -> None:
        """Register one block definition requested by an entity protocol."""
        self.add_block_name(block_record.dxf.name)

    def add_handle(self, handle: str | None) -> None:
        """Register a handle-based resource requested by an entity protocol."""
        if not handle or handle == "0":
            return
        entity = self._document.entitydb.get(handle)
        if entity is None:
            raise const.DXFStructureError(f"missing handle dependency: #{handle}")
        if is_graphic_entity(entity):
            if str(handle) not in self._scope_handles:
                raise const.DXFStructureError(
                    f"graphic handle dependency crosses a generated entity scope: #{handle}"
                )
            return
        self.add_entity(entity)

    def add_layer(self, name: str) -> None:
        """Register a layer table dependency."""
        self._emit_table_entry("layers", name)

    def add_linetype(self, name: str) -> None:
        """Register a linetype table dependency."""
        self._emit_table_entry("linetypes", name)

    def add_text_style(self, name: str) -> None:
        """Register a text-style table dependency."""
        self._emit_table_entry("styles", name)

    def add_dim_style(self, name: str) -> None:
        """Register a dimension-style table dependency."""
        self._emit_table_entry("dimstyles", name)

    def add_block_name(self, name: str) -> None:
        """Register a block-definition dependency."""
        if name:
            self._emit_block(name)

    def add_appid(self, name: str) -> None:
        """Accept an APPID dependency created by generated XDATA APIs."""

    def add_custom_var(self, name: str) -> None:
        """Accept a custom property emitted with generated FIELD source."""

    def require_field_support(self) -> None:
        """Confirm that generated source supports FIELD recreation."""

    def _emit_table_entry(self, table_attribute: str, name: str) -> None:
        """Emit one table entry after recursively emitting its dependencies."""
        key = (table_attribute, name)
        if key in self._seen_tables:
            return
        self._seen_tables.add(key)
        table = cast(_NamedDxfTable, getattr(self._document, table_attribute))
        try:
            entry = table.get(name)
        except const.DXFTableEntryError as exc:
            raise const.DXFStructureError(
                f"missing {table_attribute} dependency: {name}"
            ) from exc
        if not isinstance(entry, DXFEntity):
            raise const.DXFStructureError(
                f"invalid {table_attribute} dependency: {name}"
            )
        self._validate_nested_table_resources(entry)
        self._register_entity(entry)
        source = table_entries_to_code([entry], drawing=self._drawing)
        self._result.imports.update(source.imports)
        self._result.add_line(f"if {name!r} not in {self._drawing}.{table_attribute}:")
        self._result.add_lines(source.code, indent=4)
        source_handle = entry.dxf.get("handle")
        if source_handle:
            self._emit_existing_resource_handle_mapping(
                str(source_handle),
                f"{self._drawing}.{table_attribute}.get({name!r})",
            )

    def _emit_existing_resource_handle_mapping(
        self, source_handle: str, target_expression: str
    ) -> None:
        """Register a source handle even when the target resource already exists."""
        self._result.add_import(
            "from dxfpy.dynblkhelper import register_source_handle_mapping"
        )
        self._result.add_line(
            f"register_source_handle_mapping({source_handle!r}, {target_expression})"
        )

    def _validate_nested_table_resources(self, entry: DXFEntity) -> None:
        """Fail fast for nested resources whose protocols skip missing entries."""
        if isinstance(entry, DimStyle):
            self._validate_dimstyle_resources(entry)
        elif isinstance(entry, Linetype):
            self._validate_linetype_style(entry)

    def _validate_dimstyle_resources(self, dimstyle: DimStyle) -> None:
        """Require every named table resource selected by a DIMSTYLE."""
        self._require_dxf_table_name(dimstyle, DIM_TEXT_STYLE_ATTR, "styles")
        for attribute in DIM_LINETYPE_ATTRIBS:
            self._require_dxf_table_name(dimstyle, attribute, "linetypes")

    def _require_dxf_table_name(
        self, entity: DXFEntity, attribute: str, table_attribute: str
    ) -> None:
        """Require a named table entry selected by one DXF attribute."""
        name = entity.dxf.get(attribute)
        if not isinstance(name, str) or not name:
            return
        table = cast(_NamedDxfTable, getattr(self._document, table_attribute))
        try:
            resource = table.get(name)
        except const.DXFTableEntryError as exc:
            raise const.DXFStructureError(
                f"missing {table_attribute} dependency: {name}"
            ) from exc
        if not isinstance(resource, DXFEntity):
            raise const.DXFStructureError(
                f"missing {table_attribute} dependency: {name}"
            )

    def _validate_linetype_style(self, linetype: Linetype) -> None:
        """Require a valid STYLE referenced by a complex linetype."""
        handle = linetype.pattern_tags.get_style_handle()
        if not handle or handle == "0":
            return
        style = self._document.entitydb.get(handle)
        if style is None or style.dxftype() != "STYLE":
            raise const.DXFStructureError(
                f"missing styles dependency for linetype {linetype.dxf.name}: #{handle}"
            )

    def _emit_shx_style(self, style: DXFEntity) -> None:
        """Emit one unnamed SHX shape STYLE dependency."""
        font = style.dxf.get("font", "")
        key = font.lower()
        if not font or key in self._seen_shx_styles:
            return
        self._seen_shx_styles.add(key)
        source = table_entries_to_code([style], drawing=self._drawing)
        self._result.imports.update(source.imports)
        self._result.add_lines(source.code)
        source_handle = style.dxf.get("handle")
        if source_handle:
            self._emit_existing_resource_handle_mapping(
                str(source_handle),
                f"{self._drawing}.styles.get_shx({font!r})",
            )

    def _emit_named_object(self, entity: DXFEntity) -> None:
        """Emit one supported named-object resource and its dependencies."""
        handle = entity.dxf.get("handle")
        key = str(handle) if handle else f"id:{id(entity)}"
        if key in self._seen_objects:
            return
        self._seen_objects.add(key)
        self._register_entity(entity)
        source = table_entries_to_code([entity], drawing=self._drawing)
        self._result.imports.update(source.imports)
        self._result.add_lines(source.code)

    def _emit_block(self, name: str) -> None:
        """Emit one block after recursively emitting all dependencies."""
        if name in self._seen_blocks:
            return
        self._seen_blocks.add(name)
        block = self._document.blocks.get(name)
        if block is None:
            if self._is_managed_arrow_name(name):
                return
            raise const.DXFStructureError(f"missing blocks dependency: {name}")
        self._emit_dynamic_base_block(block)
        source = block_to_code(block, drawing=self._drawing)
        self._register_scope_resources(tuple(block), source.entity_handles)
        if block.block is not None:
            self._register_entity(block.block)
            layer = block.block.dxf.get("layer")
            if isinstance(layer, str) and layer:
                self.add_layer(layer)
        for dependency in sorted(source.blocks):
            if dependency != name:
                self._emit_block(dependency)
        self._result.imports.update(source.imports)
        self._result.add_line(f"if {name!r} not in {self._drawing}.blocks:")
        self._result.add_lines(source.code, indent=4)

    def _emit_dynamic_base_block(self, block) -> None:
        """Emit the base definition required by a dynamic representation block."""
        from dxfpy.dynblkhelper import get_dynamic_block_record_handle

        handle = get_dynamic_block_record_handle(block.block_record)
        if not handle:
            return
        record = self._document.entitydb.get(handle)
        if not isinstance(record, BlockRecord):
            raise const.DXFStructureError(
                f"missing dynamic base block dependency: #{handle}"
            )
        if record.dxf.name != block.name:
            self._emit_block(record.dxf.name)

    @staticmethod
    def _is_managed_arrow_name(name: str) -> bool:
        """Return whether a missing block name denotes a built-in arrow."""
        arrow_name = ARROWS.arrow_name(name)
        return arrow_name in ARROWS or ARROWS.is_acad_arrow(arrow_name)

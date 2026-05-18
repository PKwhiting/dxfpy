# Copyright (c) 2019-2024, Manfred Moitzi
# License: MIT License
from __future__ import annotations
from typing import TYPE_CHECKING, Any, Iterable, Mapping, Optional
import json

from ezdxf.sections.tables import TABLENAMES
from ezdxf.lldxf import const
from ezdxf.lldxf.tags import Tags
from ezdxf.entities import BoundaryPathType, EdgeType, Dictionary, XRecord
from ezdxf.render.arrows import ARROWS
import numpy as np

if TYPE_CHECKING:
    from ezdxf.lldxf.types import DXFTag
    from ezdxf.entities import (
        Insert,
        MText,
        MultiLeader,
        LWPolyline,
        Polyline,
        Spline,
        Leader,
        Dimension,
        Image,
        Mesh,
        Hatch,
        MPolygon,
        Wipeout,
    )
    from ezdxf.entities import DXFEntity, Linetype
    from ezdxf.entities.polygon import DXFPolygon
    from ezdxf.layouts import BlockLayout

__all__ = [
    "entities_to_code",
    "block_to_code",
    "table_entries_to_code",
    "black",
]


def black(code: str, line_length=88, fast: bool = True) -> str:
    """Returns the source `code` as a single string formatted by `Black`_

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


def entities_to_code(
    entities: Iterable[DXFEntity],
    layout: str = "layout",
    ignore: Optional[Iterable[str]] = None,
) -> Code:
    """
    Translates DXF entities into Python source code to recreate this entities
    by ezdxf.

    Args:
        entities: iterable of DXFEntity
        layout: variable name of the layout (model space or block) as string
        ignore: iterable of entities types to ignore as strings
            like ``['IMAGE', 'DIMENSION']``

    Returns:
        :class:`Code`

    """
    code = _SourceCodeGenerator(layout=layout)
    code.translate_entities(entities, ignore=ignore)
    return code.code


def block_to_code(
    block: BlockLayout,
    drawing: str = "doc",
    ignore: Optional[Iterable[str]] = None,
) -> Code:
    """
    Translates a BLOCK into Python source code to recreate the BLOCK by ezdxf.

    Args:
        block: block definition layout
        drawing: variable name of the drawing as string
        ignore: iterable of entities types to ignore as strings
            like ['IMAGE', 'DIMENSION']

    Returns:
        :class:`Code`

    """
    assert block.block is not None
    dxfattribs = _purge_handles(block.block.dxfattribs())
    block_name = dxfattribs.pop("name")
    base_point = dxfattribs.pop("base_point")
    code = _SourceCodeGenerator(layout="b")
    prolog = f'b = {drawing}.blocks.new("{block_name}", base_point={base_point}, dxfattribs={{'
    code.add_source_code_line(prolog)
    code.add_source_code_lines(_fmt_mapping(dxfattribs, indent=4))
    code.add_source_code_line("    }")
    code.add_source_code_line(")")
    code.translate_entities(block, ignore=ignore)
    code._register_block_handle(block)
    code._emit_dynamic_block_metadata(block)
    return code.code


def table_entries_to_code(
    entities: Iterable[DXFEntity], drawing="doc"
) -> Code:
    code = _SourceCodeGenerator(doc=drawing)
    code.translate_entities(entities)
    return code.code


class Code:
    """Source code container."""

    def __init__(self) -> None:
        self.code: list[str] = []
        # global imports -> indentation level 0:
        self.imports: set[str] = set()
        # layer names as string:
        self.layers: set[str] = set()
        # text style name as string, requires a TABLE entry:
        self.styles: set[str] = set()
        # line type names as string, requires a TABLE entry:
        self.linetypes: set[str] = set()
        # dimension style names as string, requires a TABLE entry:
        self.dimstyles: set[str] = set()
        # block names as string, requires a BLOCK definition:
        self.blocks: set[str] = set()

    def code_str(self, indent: int = 0) -> str:
        """Returns the source code as a single string.

        Args:
            indent: source code indentation count by spaces

        """
        lead_str = " " * indent
        return "\n".join(lead_str + line for line in self.code)

    def black_code_str(self, line_length=88) -> str:
        """Returns the source code as a single string formatted by `Black`_

        Args:
            line_length: max. source code line length

        Raises:
            ImportError: Black is not available

        """
        return black(self.code_str(), line_length)

    def __str__(self) -> str:
        """Returns the source code as a single string."""

        return self.code_str()

    def import_str(self, indent: int = 0) -> str:
        """Returns required imports as a single string.

        Args:
            indent: source code indentation count by spaces

        """
        lead_str = " " * indent
        return "\n".join(lead_str + line for line in self.imports)

    def add_import(self, statement: str) -> None:
        """Add import statement, identical import statements are merged
        together.
        """
        self.imports.add(statement)

    def add_line(self, code: str, indent: int = 0) -> None:
        """Add a single source code line without line ending ``\\n``."""
        self.code.append(" " * indent + code)

    def add_lines(self, code: Iterable[str], indent: int = 0) -> None:
        """Add multiple source code lines without line ending ``\\n``."""
        for line in code:
            self.add_line(line, indent=indent)

    def merge(self, code: Code, indent: int = 0) -> None:
        """Add another :class:`Code` object."""
        # merge used resources
        self.imports.update(code.imports)
        self.layers.update(code.layers)
        self.linetypes.update(code.linetypes)
        self.styles.update(code.styles)
        self.dimstyles.update(code.dimstyles)
        self.blocks.update(code.blocks)

        # append source code lines
        self.add_lines(code.code, indent=indent)


_PURGE_DXF_ATTRIBUTES = {
    "handle",
    "owner",
    "paperspace",
    "material_handle",
    "visualstyle_handle",
    "plotstyle_handle",
}


def _purge_handles(attribs: dict) -> dict:
    """Purge handles from DXF attributes which will be invalid in a new
    document, or which will be set automatically by adding an entity to a
    layout (paperspace).

    Args:
        attribs: entity DXF attributes dictionary

    """
    return {k: v for k, v in attribs.items() if k not in _PURGE_DXF_ATTRIBUTES}


def _fmt_mapping(mapping: Mapping, indent: int = 0) -> Iterable[str]:
    # key is always a string
    fmt = " " * indent + "'{}': {},"
    for k, v in mapping.items():
        assert isinstance(k, str)
        if isinstance(v, str):
            v = json.dumps(v)  # for correct escaping of quotes
        else:
            v = str(v)  # format uses repr() for Vec3s
        yield fmt.format(k, v)


def _fmt_list(l: Iterable, indent: int = 0) -> Iterable[str]:
    def cleanup(values: Iterable) -> Iterable:
        for value in values:
            if isinstance(value, np.float64):
                yield float(value)
            else:
                yield value

    fmt = " " * indent + "{},"
    for v in l:
        if not isinstance(v, (float, int, str)):
            v = tuple(cleanup(v))
        yield fmt.format(str(v))


def _fmt_api_call(
    func_call: str, args: Iterable[str], dxfattribs: dict
) -> list[str]:
    attributes = dict(dxfattribs)
    args = list(args) if args else []

    def fmt_keywords() -> Iterable[str]:
        for arg in args:
            if arg not in attributes:
                continue
            value = attributes.pop(arg)
            if isinstance(value, str):
                valuestr = json.dumps(value)  # quoted string!
            else:
                valuestr = str(value)
            yield "    {}={},".format(arg, valuestr)

    s = [func_call]
    s.extend(fmt_keywords())
    s.append("    dxfattribs={")
    s.extend(_fmt_mapping(attributes, indent=8))
    s.extend(
        [
            "    },",
            ")",
        ]
    )
    return s


def _fmt_dxf_tags(tags: Iterable[DXFTag], indent: int = 0):
    fmt = " " * indent + "dxftag({}, {}),"
    for code, value in tags:
        assert isinstance(code, int)
        if isinstance(value, str):
            value = json.dumps(value)  # for correct escaping of quotes
        else:
            value = str(value)  # format uses repr() for Vec3s
        yield fmt.format(code, value)


class _SourceCodeGenerator:
    """
    The :class:`_SourceCodeGenerator` translates DXF entities into Python source
    code for creating the same DXF entity in another model space or block
    definition.

    :ivar code: list of source code lines without line endings
    :ivar required_imports: list of import source code lines, which are required
        to create executable Python code.

    """

    def __init__(self, layout: str = "layout", doc: str = "doc"):
        self.doc = doc
        self.layout = layout
        self.code = Code()
        self._deferred_code: list[str] = []
        self._translated_handles: set[str] = set()
        self._emitted_handles: set[str] = set()

    def translate_entity(self, entity: DXFEntity) -> None:
        """Translates one DXF entity into Python source code. The generated
        source code is appended to the attribute `source_code`.

        Args:
            entity: DXFEntity object

        """
        dxftype = entity.dxftype()
        try:
            entity_translator = getattr(self, "_" + dxftype.lower())
        except AttributeError:
            self.add_source_code_line(f'# unsupported DXF entity "{dxftype}"')
        else:
            supported = entity_translator(entity)
            if supported is not False and dxftype not in TABLENAMES and dxftype != "MLEADERSTYLE":
                self._register_entity_handle(entity)
                self._schedule_hosted_fields(entity)

    def translate_entities(
        self,
        entities: Iterable[DXFEntity],
        ignore: Optional[Iterable[str]] = None,
    ) -> None:
        """Translates multiple DXF entities into Python source code. The
        generated source code is appended to the attribute `source_code`.

        Args:
            entities: iterable of DXFEntity
            ignore: iterable of entities types to ignore as strings
                like ['IMAGE', 'DIMENSION']

        """
        ignore = set(ignore) if ignore else set()
        entities = list(entities)
        self._translated_handles = self._collect_translated_handles(entities)
        self.add_source_code_line("_entity_map = {}")

        for entity in entities:
            if entity.dxftype() not in ignore:
                self.translate_entity(entity)
        if self._deferred_code:
            self.add_source_code_line("# recreate hosted FIELD objects")
            self.add_source_code_lines(self._deferred_code)

    def add_used_resources(self, dxfattribs: Mapping) -> None:
        """Register used resources like layers, line types, text styles and
        dimension styles.

        Args:
            dxfattribs: DXF attributes dictionary

        """
        if "layer" in dxfattribs:
            self.code.layers.add(dxfattribs["layer"])
        if "linetype" in dxfattribs:
            self.code.linetypes.add(dxfattribs["linetype"])
        if "style" in dxfattribs:
            self.code.styles.add(dxfattribs["style"])
        if "dimstyle" in dxfattribs:
            self.code.dimstyles.add(dxfattribs["dimstyle"])

    def add_import_statement(self, statement: str) -> None:
        self.code.add_import(statement)

    def add_source_code_line(self, code: str) -> None:
        self.code.add_line(code)

    def add_source_code_lines(self, code: Iterable[str]) -> None:
        assert not isinstance(code, str)
        self.code.add_lines(code)

    def add_deferred_source_code_line(self, code: str) -> None:
        self._deferred_code.append(code)

    def add_deferred_source_code_lines(self, code: Iterable[str]) -> None:
        assert not isinstance(code, str)
        self._deferred_code.extend(code)

    def add_list_source_code(
        self,
        values: Iterable,
        prolog: str = "[",
        epilog: str = "]",
        indent: int = 0,
    ) -> None:
        fmt_str = " " * indent + "{}"
        self.add_source_code_line(fmt_str.format(prolog))
        self.add_source_code_lines(_fmt_list(values, indent=4 + indent))
        self.add_source_code_line(fmt_str.format(epilog))

    def add_dict_source_code(
        self,
        mapping: Mapping,
        prolog: str = "{",
        epilog: str = "}",
        indent: int = 0,
    ) -> None:
        fmt_str = " " * indent + "{}"
        self.add_source_code_line(fmt_str.format(prolog))
        self.add_source_code_lines(_fmt_mapping(mapping, indent=4 + indent))
        self.add_source_code_line(fmt_str.format(epilog))

    def add_tags_source_code(
        self, tags: Tags, prolog="tags = Tags(", epilog=")", indent=4
    ):
        fmt_str = " " * indent + "{}"
        self.add_source_code_line(fmt_str.format(prolog))
        self.add_source_code_lines(_fmt_dxf_tags(tags, indent=4 + indent))
        self.add_source_code_line(fmt_str.format(epilog))

    @staticmethod
    def _collect_translated_handles(entities: Iterable[DXFEntity]) -> set[str]:
        handles: set[str] = set()
        for entity in entities:
            handle = entity.dxf.get("handle")
            if handle:
                handles.add(handle)
            for attrib in getattr(entity, "attribs", []):
                attrib_handle = attrib.dxf.get("handle")
                if attrib_handle:
                    handles.add(attrib_handle)
        return handles

    def _register_entity_handle(self, entity: DXFEntity, var_name: str = "e") -> None:
        handle = entity.dxf.get("handle")
        if handle:
            self._emitted_handles.add(handle)
            self.add_source_code_line(
                f'_entity_map[{json.dumps(handle)}] = {var_name}'
            )

    def _register_block_handle(self, block) -> None:
        if block.block is not None:
            self._register_entity_handle(block.block, var_name="b.block")
        self._register_entity_handle(block.block_record, var_name="b.block_record")

    @staticmethod
    def _read_field_value(field, marker_code: int, marker_value: str) -> Any:
        tags = list(field.tags)
        for index, tag in enumerate(tags):
            if tag.code != marker_code or tag.value != marker_value:
                continue
            for value_tag in tags[index + 1 :]:
                if value_tag.code in (1, 91, 140, 330):
                    return value_tag.value
                if value_tag.code == 304 and value_tag.value == "ACVALUE_END":
                    break
        return None

    def _dwgprops_name(self, field) -> Optional[str]:
        if field.evaluator_id != "AcVar":
            return None
        variable_name = self._read_field_value(field, 6, "Variable")
        if isinstance(variable_name, str) and variable_name.startswith("CustomDP."):
            return variable_name[len("CustomDP.") :]
        return None

    @staticmethod
    def _field_display_text(field) -> str:
        for tag in reversed(field.tags):
            if tag.code == 301:
                return str(tag.value)
        return ""

    @staticmethod
    def _attdef_rep_index(entity) -> Optional[int]:
        try:
            return int(entity.get_xdata("AcDbBlockRepETag").get_first_value(1071, -1))
        except const.DXFValueError:
            return None

    @staticmethod
    def _entity_rep_etag_info(entity) -> Optional[tuple[int, str]]:
        try:
            tags = list(entity.get_xdata("AcDbBlockRepETag"))
        except const.DXFValueError:
            return None
        rep_index = next((int(tag.value) for tag in tags if tag.code == 1071), -1)
        rep_handle = next((str(tag.value) for tag in tags if tag.code == 1005), "")
        if rep_index < 0:
            return None
        return rep_index, rep_handle

    @staticmethod
    def _attdef_has_context_record(entity) -> bool:
        if not entity.has_extension_dict:
            return False
        root = entity.get_extension_dict().dictionary
        mgr = root.get("AcDbContextDataManager")
        if not isinstance(mgr, Dictionary):
            return False
        scales = mgr.get("ACDB_ANNOTATIONSCALES")
        return isinstance(scales, Dictionary) and "*A1" in scales

    @staticmethod
    def _field_has_eval_option(field) -> bool:
        return any(
            tag.code == 6 and tag.value == "ACAD_ROUNDTRIP_2008_FIELD_EVALOPTION"
            for tag in field.tags
        )

    def _field_format(self, field) -> str:
        tags = list(field.tags)
        for index, tag in enumerate(tags):
            if tag.code != 7 or tag.value != "ACFD_FIELD_VALUE":
                continue
            for value_tag in tags[index + 1 :]:
                if value_tag.code == 300:
                    return str(value_tag.value)
                if value_tag.code == 304 and value_tag.value == "ACVALUE_END":
                    break
        return ""

    def _acexpr_expression(self, field) -> Optional[str]:
        code = field.field_code
        prefix = "\\AcExpr "
        if not code.startswith(prefix):
            return None
        expression = code[len(prefix) :]
        field_format = self._field_format(field)
        if field_format:
            suffix = f' \\f "{field_format}"'
            if expression.endswith(suffix):
                expression = expression[: -len(suffix)]
        return expression

    def _uses_field_list(self, wrapper, child) -> bool:
        doc = wrapper.doc
        if doc is None:
            return False
        field_list = doc.objects.get_field_list()
        if field_list is None:
            return False
        handles = set(field_list.handles)
        return any(field.dxf.handle in handles for field in wrapper.get_field_tree())

    def _format_field_tag_value(self, code: int, value: Any) -> Optional[str]:
        if code in (330, 331):
            if not isinstance(value, str) or value not in self._translated_handles:
                return None
            return f'_entity_map[{json.dumps(value)}].dxf.handle'
        if isinstance(value, str):
            return json.dumps(value)
        return str(value)

    def _field_reset_source(
        self, field, child_handle_expr: Optional[dict[str, str]] = None
    ) -> Optional[list[str]]:
        lines: list[str] = []
        for code, value in field.tags:
            if (
                code == 360
                and child_handle_expr is not None
                and isinstance(value, str)
                and value in child_handle_expr
            ):
                value_str = child_handle_expr[value]
            else:
                value_str = self._format_field_tag_value(code, value)
            if value_str is None:
                return None
            lines.append(f"    ({code}, {value_str}),")
        return lines

    def _emit_text_wrapper_construction(
        self, wrapper, wrapper_var: str, host_var: str
    ) -> Optional[list[str]]:
        if not wrapper.is_text_wrapper:
            return None
        child_fields = wrapper.get_child_fields()
        if not child_fields:
            return None
        child_vars: list[str] = []
        child_handle_expr: dict[str, str] = {}
        for index, child in enumerate(child_fields):
            child_var = f"{wrapper_var}_{index}"
            if not self._emit_field_construction(
                child, child_var, host_var, bind_leaf_to_doc=True
            ):
                return None
            child_vars.append(child_var)
            if child.dxf.handle:
                child_handle_expr[child.dxf.handle] = f"{child_var}.dxf.handle"
        wrapper_reset_source = self._field_reset_source(wrapper, child_handle_expr)
        if wrapper_reset_source is None:
            return None
        self.add_deferred_source_code_line(f"{wrapper_var} = Field()")
        self.add_deferred_source_code_line(f"{wrapper_var}.reset([")
        self.add_deferred_source_code_lines(wrapper_reset_source)
        self.add_deferred_source_code_line("])" )
        return child_vars

    def _emit_field_custom_var_setup(self, field, field_var: str, host_var: str) -> None:
        dwgprops_name = self._dwgprops_name(field)
        if dwgprops_name is None:
            return
        dwgprops_value = self._read_field_value(field, 7, "ACFD_FIELD_VALUE")
        if dwgprops_value is None:
            dwgprops_value = ""
        elif not isinstance(dwgprops_value, str):
            dwgprops_value = str(dwgprops_value)
        self.add_deferred_source_code_line(f"_custom_vars = {host_var}.doc.header.custom_vars")
        self.add_deferred_source_code_line(
            f"if _custom_vars.has_tag({json.dumps(dwgprops_name)}):"
        )
        self.add_deferred_source_code_line(
            f"    _custom_vars.replace({json.dumps(dwgprops_name)}, {json.dumps(dwgprops_value)})"
        )
        self.add_deferred_source_code_line("else:")
        self.add_deferred_source_code_line(
            f"    _custom_vars.append({json.dumps(dwgprops_name)}, {json.dumps(dwgprops_value)})"
        )

    def _emit_field_construction(
        self,
        field,
        field_var: str,
        host_var: str,
        *,
        bind_leaf_to_doc: bool = False,
    ) -> bool:
        self.add_import_statement("from ezdxf.entities.dxfobj import Field")
        child_fields = field.get_child_fields()
        if len(child_fields):
            if field.evaluator_id != "AcExpr":
                return False
            expression = self._acexpr_expression(field)
            if expression is None:
                return False
            child_vars: list[str] = []
            for index, child in enumerate(child_fields):
                child_var = f"{field_var}_{index}"
                if not self._emit_field_construction(child, child_var, host_var):
                    return False
                child_vars.append(child_var)
            self.add_deferred_source_code_line(f"{field_var} = Field.build_acexpr(")
            self.add_deferred_source_code_line(f"    {host_var}.doc,")
            self.add_deferred_source_code_line(f"    {json.dumps(expression)},")
            self.add_deferred_source_code_line(
                f"    [{', '.join(child_vars)}],"
            )
            self.add_deferred_source_code_line(
                f"    field_format={json.dumps(self._field_format(field) or '%lu2')},"
            )
            self.add_deferred_source_code_line(
                f"    value={self._format_python_value(self._read_field_value(field, 7, 'ACFD_FIELD_VALUE'))},"
            )
            self.add_deferred_source_code_line(
                f"    display={json.dumps(self._field_display_text(field))},"
            )
            self.add_deferred_source_code_line(
                f"    include_eval_option={self._field_has_eval_option(field)},"
            )
            self.add_deferred_source_code_line(")")
            return True

        field_reset_source = self._field_reset_source(field)
        if field_reset_source is None:
            return False
        if bind_leaf_to_doc:
            self.add_deferred_source_code_line(
                f"{field_var} = {host_var}.doc.objects.add_field(owner='0')"
            )
        else:
            self.add_deferred_source_code_line(f"{field_var} = Field()")
        self.add_deferred_source_code_line(f"{field_var}.reset([")
        self.add_deferred_source_code_lines(field_reset_source)
        self.add_deferred_source_code_line("])"
        )
        self._emit_field_custom_var_setup(field, field_var, host_var)
        return True

    @staticmethod
    def _dynamic_block_guid(block_record) -> str:
        try:
            return str(block_record.get_xdata("AcDbDynamicBlockGUID").get_first_value(1000, ""))
        except const.DXFValueError:
            return ""

    @staticmethod
    def _dynamic_block_true_name(block_record) -> str:
        try:
            return str(block_record.get_xdata("AcDbDynamicBlockTrueName").get_first_value(1000, ""))
        except const.DXFValueError:
            try:
                return str(block_record.get_xdata("AcDbDynamicBlockTrueName2").get_first_value(1000, ""))
            except const.DXFValueError:
                return block_record.dxf.name

    @staticmethod
    def _block_rep_index(block_record) -> Optional[int]:
        try:
            return int(block_record.get_xdata("AcDbBlockRepETag").get_first_value(1071, -1))
        except const.DXFValueError:
            return None

    def _emit_block_rep_etag_preservation(self, block) -> None:
        rep_index = self._block_rep_index(block.block_record)
        if rep_index is not None:
            self.add_source_code_line(
                f'b.block_record.set_xdata("AcDbBlockRepETag", [(1070, 1), (1071, {rep_index})])'
            )
        for entity in block:
            handle = entity.dxf.get("handle")
            if not handle or handle not in self._emitted_handles:
                continue
            info = self._entity_rep_etag_info(entity)
            if info is None:
                continue
            rep_index, rep_handle = info
            rep_handle_expr = (
                f'_entity_map[{json.dumps(handle)}].dxf.handle'
                if rep_handle == handle
                else json.dumps(rep_handle)
            )
            self.add_source_code_line(
                f'_entity_map[{json.dumps(handle)}].set_xdata("AcDbBlockRepETag", [(1070, 1), (1071, {rep_index}), (1005, {rep_handle_expr})])'
            )

    def _emit_dynamic_block_metadata(self, block) -> None:
        from ezdxf.dynblkhelper import (
            get_dynamic_block_base_point_parameter,
            get_dynamic_block_linear_parameters,
            get_dynamic_block_lookup_actions,
            get_dynamic_block_lookup_parameters,
            get_dynamic_block_properties_table,
            get_dynamic_block_record_handle,
            get_dynamic_block_stretch_actions,
            get_dynamic_block_visibility_parameter,
            is_dynamic_block_definition,
        )

        block_record = block.block_record
        if is_dynamic_block_definition(block_record):
            base_point_parameter = get_dynamic_block_base_point_parameter(block)
            linear_parameters = get_dynamic_block_linear_parameters(block)
            lookup_parameters = get_dynamic_block_lookup_parameters(block)
            lookup_actions = get_dynamic_block_lookup_actions(block)
            parameter = get_dynamic_block_visibility_parameter(block)
            properties_table = get_dynamic_block_properties_table(block)
            stretch_actions = get_dynamic_block_stretch_actions(block)
            if parameter is not None:
                self.add_import_statement(
                    "from ezdxf.dynblkhelper import DynamicBlockVisibilityParameter, DynamicBlockVisibilityState, set_dynamic_block_visibility_parameter"
                )
                self.add_source_code_line("_dyn_states = (")
                for state in parameter.states:
                    handles = ", ".join(
                        f'_entity_map[{json.dumps(handle)}].dxf.handle'
                        for handle in state.entity_handles
                    )
                    if len(state.entity_handles) == 1:
                        handles += ","
                    self.add_source_code_line(
                        f"    DynamicBlockVisibilityState({json.dumps(state.name)}, ({handles})),"
                    )
                self.add_source_code_line(")")
                self.add_source_code_line(
                    "_dyn_param = DynamicBlockVisibilityParameter("
                )
                self.add_source_code_line("    handle='',")
                self.add_source_code_line(
                    f"    label={json.dumps(parameter.label)},"
                )
                self.add_source_code_line(
                    f"    parameter_name={json.dumps(parameter.parameter_name)},"
                )
                self.add_source_code_line(
                    f"    location={self._format_python_value(parameter.location)},"
                )
                self.add_source_code_line("    states=_dyn_states,")
                handles = ", ".join(
                    f'_entity_map[{json.dumps(handle)}].dxf.handle'
                    for handle in parameter.all_entity_handles
                )
                if len(parameter.all_entity_handles) == 1:
                    handles += ","
                self.add_source_code_line(
                    f"    all_entity_handles=({handles}),"
                )
                self.add_source_code_line(")")
                self.add_source_code_line(
                    f"set_dynamic_block_visibility_parameter(b, _dyn_param, guid={json.dumps(self._dynamic_block_guid(block_record))}, true_name={json.dumps(self._dynamic_block_true_name(block_record))})"
                )
            if properties_table is not None:
                self.add_import_statement(
                    "from ezdxf.dynblkhelper import DynamicBlockPropertiesTable, DynamicBlockPropertyColumn, DynamicBlockPropertyRow, set_dynamic_block_properties_table"
                )
                self.add_source_code_line("_dyn_property_columns = (")
                for column in properties_table.columns:
                    if column.source_dxftype == "ATTDEF" and column.source_handle in self._translated_handles:
                        source_handle = f'_entity_map[{json.dumps(column.source_handle)}].dxf.handle'
                    else:
                        source_handle = json.dumps("")
                    self.add_source_code_line(
                        f"    DynamicBlockPropertyColumn({source_handle}, {json.dumps(column.source_dxftype)}, {json.dumps(column.name)}, {json.dumps(column.display_name)}),"
                    )
                self.add_source_code_line(")")
                self.add_source_code_line("_dyn_property_rows = (")
                for row in properties_table.rows:
                    self.add_source_code_line(
                        f"    DynamicBlockPropertyRow({row.index}, {self._format_python_value(row.values)}),"
                    )
                self.add_source_code_line(")")
                self.add_source_code_line("_dyn_props = DynamicBlockPropertiesTable(")
                self.add_source_code_line("    handle='',")
                self.add_source_code_line(
                    f"    label={json.dumps(properties_table.label)},"
                )
                self.add_source_code_line(
                    f"    table_name={json.dumps(properties_table.table_name)},"
                )
                self.add_source_code_line(
                    f"    description={json.dumps(properties_table.description)},"
                )
                self.add_source_code_line(
                    f"    location={self._format_python_value(properties_table.location)},"
                )
                self.add_source_code_line(
                    f"    grip_location={self._format_python_value(properties_table.grip_location)},"
                )
                self.add_source_code_line("    columns=_dyn_property_columns,")
                self.add_source_code_line("    rows=_dyn_property_rows,")
                self.add_source_code_line(")")
                self.add_source_code_line("_dyn_props = set_dynamic_block_properties_table(b, _dyn_props)")
            if base_point_parameter is not None:
                self.add_import_statement(
                    "from ezdxf.dynblkhelper import DynamicBlockBasePointParameter, set_dynamic_block_base_point_parameter"
                )
                self.add_source_code_line("_dyn_basepoint = DynamicBlockBasePointParameter(")
                self.add_source_code_line("    handle='',")
                self.add_source_code_line(
                    f"    label={json.dumps(base_point_parameter.label)},"
                )
                self.add_source_code_line(
                    f"    location={self._format_python_value(base_point_parameter.location)},"
                )
                self.add_source_code_line(
                    f"    base_point={self._format_python_value(base_point_parameter.base_point)},"
                )
                self.add_source_code_line(
                    f"    second_point={self._format_python_value(base_point_parameter.second_point)},"
                )
                self.add_source_code_line(
                    f"    expr_id={self._format_python_value(base_point_parameter.expr_id)},"
                )
                self.add_source_code_line(")")
                self.add_source_code_line(
                    "set_dynamic_block_base_point_parameter(b, _dyn_basepoint)"
                )
            if properties_table is not None and linear_parameters:
                self.add_import_statement(
                    "from ezdxf.dynblkhelper import DynamicBlockLinearParameter, DynamicBlockStretchAction, DynamicBlockStretchActionTarget, set_dynamic_block_linear_parameter"
                )
                if len(linear_parameters) != len(stretch_actions):
                    self.add_source_code_line(
                        "# unsupported dynamic block linear metadata: parameter/action count mismatch"
                    )
                    return
                if len(linear_parameters) > 1:
                    self.add_source_code_line(
                        "# unsupported dynamic block linear metadata: multiple linear parameters"
                    )
                    return
                for index, linear in enumerate(linear_parameters):
                    action = stretch_actions[index]
                    linear_var = f"_dyn_linear_{index}"
                    action_var = f"_dyn_stretch_{index}"
                    self.add_source_code_line(f"{linear_var} = DynamicBlockLinearParameter(")
                    self.add_source_code_line("    handle='',")
                    self.add_source_code_line(
                        f"    label={json.dumps(linear.label)},"
                    )
                    self.add_source_code_line(
                        f"    parameter_name={json.dumps(linear.parameter_name)},"
                    )
                    self.add_source_code_line(
                        f"    description={json.dumps(linear.description)},"
                    )
                    self.add_source_code_line(
                        f"    base_point={self._format_python_value(linear.base_point)},"
                    )
                    self.add_source_code_line(
                        f"    end_point={self._format_python_value(linear.end_point)},"
                    )
                    self.add_source_code_line(
                        f"    distance={self._format_python_value(linear.distance)},"
                    )
                    self.add_source_code_line(
                        f"    expr_id={self._format_python_value(linear.expr_id)},"
                    )
                    self.add_source_code_line(
                        f"    base_grip_label={json.dumps(linear.base_grip_label)},"
                    )
                    self.add_source_code_line(
                        f"    end_grip_label={json.dumps(linear.end_grip_label)},"
                    )
                    self.add_source_code_line(
                        f"    base_grip_location={self._format_python_value(linear.base_grip_location)},"
                    )
                    self.add_source_code_line(
                        f"    end_grip_location={self._format_python_value(linear.end_grip_location)},"
                    )
                    self.add_source_code_line(")")
                    self.add_source_code_line(f"{action_var} = DynamicBlockStretchAction(")
                    self.add_source_code_line("    handle='',")
                    self.add_source_code_line(
                        f"    label={json.dumps(action.label)},"
                    )
                    self.add_source_code_line(
                        f"    action_location={self._format_python_value(action.action_location)},"
                    )
                    self.add_source_code_line(
                        f"    x_expr_id={self._format_python_value(action.x_expr_id)},"
                    )
                    self.add_source_code_line(
                        f"    x_name={json.dumps(action.x_name)},"
                    )
                    self.add_source_code_line(
                        f"    y_expr_id={self._format_python_value(action.y_expr_id)},"
                    )
                    self.add_source_code_line(
                        f"    y_name={json.dumps(action.y_name)},"
                    )
                    self.add_source_code_line(
                        f"    selection_window={self._format_python_value(action.selection_window)},"
                    )
                    if base_point_parameter is not None:
                        translated_deps = [
                            f'_entity_map[{json.dumps(handle)}].dxf.handle'
                            for handle in action.dependency_handles
                            if handle in self._translated_handles
                        ]
                        deps = ", ".join(translated_deps)
                        if len(translated_deps) == 1:
                            deps += ","
                        self.add_source_code_line(
                            f"    dependency_handles=({deps}),"
                        )
                        target_vars = []
                        for t_index, target in enumerate(action.targets):
                            if target.entity_handle not in self._translated_handles:
                                continue
                            target_var = f"{action_var}_target_{t_index}"
                            target_vars.append(target_var)
                            self.add_source_code_line(
                                f"    # {target_var} created below"
                            )
                        self.add_source_code_line("    targets=(),")
                    else:
                        self.add_source_code_line("    dependency_handles=(),")
                        self.add_source_code_line("    targets=(),")
                    self.add_source_code_line(")")
                    if base_point_parameter is not None:
                        target_vars = []
                        for t_index, target in enumerate(action.targets):
                            if target.entity_handle not in self._translated_handles:
                                continue
                            target_var = f"{action_var}_target_{t_index}"
                            target_vars.append(target_var)
                            self.add_source_code_line(
                                f"{target_var} = DynamicBlockStretchActionTarget(_entity_map[{json.dumps(target.entity_handle)}].dxf.handle, {self._format_python_value(target.mode)}, {self._format_python_value(target.components)})"
                            )
                        joined_targets = ", ".join(target_vars)
                        if len(target_vars) == 1:
                            joined_targets += ","
                        deps_expr = f"({deps})" if translated_deps else "()"
                        self.add_source_code_line(
                            f"{action_var} = DynamicBlockStretchAction(handle='', label={json.dumps(action.label)}, action_location={self._format_python_value(action.action_location)}, x_expr_id={self._format_python_value(action.x_expr_id)}, x_name={json.dumps(action.x_name)}, y_expr_id={self._format_python_value(action.y_expr_id)}, y_name={json.dumps(action.y_name)}, selection_window={self._format_python_value(action.selection_window)}, dependency_handles={deps_expr}, targets=({joined_targets}))"
                        )
                    self.add_source_code_line(
                        f"set_dynamic_block_linear_parameter(b, {linear_var}, {action_var})"
                    )
            if properties_table is not None and lookup_parameters:
                self.add_import_statement(
                    "from ezdxf.dynblkhelper import DynamicBlockLookupParameter, DynamicBlockLookupAction, DynamicBlockLookupActionBinding, set_dynamic_block_lookup_parameter"
                )
                if len(lookup_parameters) != 1 or len(lookup_actions) != 2:
                    self.add_source_code_line(
                        "# unsupported dynamic block lookup metadata"
                    )
                    return
                lookup = lookup_parameters[0]
                action_vars: list[str] = []
                for index, action in enumerate(lookup_actions):
                    bindings_var = f"_dyn_lookup_bindings_{index}"
                    action_var = f"_dyn_lookup_action_{index}"
                    action_vars.append(action_var)
                    self.add_source_code_line(f"{bindings_var} = (")
                    for binding in action.bindings:
                        self.add_source_code_line(
                            "    DynamicBlockLookupActionBinding("
                        )
                        self.add_source_code_line(
                            f"        group_label={json.dumps(binding.group_label)},"
                        )
                        self.add_source_code_line(
                            f"        expr_id={self._format_python_value(binding.expr_id)},"
                        )
                        self.add_source_code_line(
                            f"        value_code={self._format_python_value(binding.value_code)},"
                        )
                        self.add_source_code_line(
                            f"        value_type={self._format_python_value(binding.value_type)},"
                        )
                        self.add_source_code_line(
                            f"        flag282={self._format_python_value(binding.flag282)},"
                        )
                        self.add_source_code_line(
                            f"        display_name={json.dumps(binding.display_name)},"
                        )
                        self.add_source_code_line(
                            f"        flag281={self._format_python_value(binding.flag281)},"
                        )
                        self.add_source_code_line(
                            f"        property_name={json.dumps(binding.property_name)},"
                        )
                        self.add_source_code_line("    ),")
                    self.add_source_code_line(")")
                    self.add_source_code_line(f"{action_var} = DynamicBlockLookupAction(")
                    self.add_source_code_line("    handle='',")
                    self.add_source_code_line(
                        f"    label={json.dumps(action.label)},"
                    )
                    self.add_source_code_line(
                        f"    action_location={self._format_python_value(action.action_location)},"
                    )
                    self.add_source_code_line(
                        f"    expr_id={self._format_python_value(action.expr_id)},"
                    )
                    self.add_source_code_line(
                        f"    row_count={self._format_python_value(action.row_count)},"
                    )
                    self.add_source_code_line(
                        f"    column_count={self._format_python_value(action.column_count)},"
                    )
                    self.add_source_code_line(
                        f"    entries={self._format_python_value(action.entries)},"
                    )
                    self.add_source_code_line(
                        f"    bindings={bindings_var},"
                    )
                    self.add_source_code_line(
                        f"    enabled={self._format_python_value(action.enabled)},"
                    )
                    self.add_source_code_line(")")
                self.add_source_code_line("_dyn_lookup = DynamicBlockLookupParameter(")
                self.add_source_code_line("    handle='',")
                self.add_source_code_line(
                    f"    label={json.dumps(lookup.label)},"
                )
                self.add_source_code_line(
                    f"    parameter_name={json.dumps(lookup.parameter_name)},"
                )
                self.add_source_code_line(
                    f"    description={json.dumps(lookup.description)},"
                )
                self.add_source_code_line(
                    f"    location={self._format_python_value(lookup.location)},"
                )
                self.add_source_code_line(
                    f"    expr_id={self._format_python_value(lookup.expr_id)},"
                )
                self.add_source_code_line(
                    f"    action_expr_id={self._format_python_value(lookup.action_expr_id)},"
                )
                self.add_source_code_line(
                    f"    grip_label={json.dumps(lookup.grip_label)},"
                )
                self.add_source_code_line(")")
                joined_action_vars = ", ".join(action_vars)
                if len(action_vars) == 1:
                    joined_action_vars += ","
                self.add_source_code_line(
                    f"set_dynamic_block_lookup_parameter(b, _dyn_lookup, ({joined_action_vars}))"
                )
            if (
                parameter is None
                and properties_table is None
                and base_point_parameter is None
                and not linear_parameters
                and not lookup_parameters
            ):
                self.add_import_statement(
                    "from ezdxf.dynblkhelper import set_dynamic_block_definition_metadata"
                )
                rep_index = self._block_rep_index(block_record)
                if rep_index is None:
                    rep_index = len(block)
                self.add_source_code_line(
                    f"set_dynamic_block_definition_metadata(b, guid={json.dumps(self._dynamic_block_guid(block_record))}, true_name={json.dumps(self._dynamic_block_true_name(block_record))}, rep_index={rep_index}, annotative={block_record.has_xdata('AcadAnnotative')})"
                )
            self._emit_block_rep_etag_preservation(block)
            return

        base_handle = get_dynamic_block_record_handle(block_record)
        if not base_handle:
            return
        base_block = block.doc.blocks.get(block.doc.entitydb.get(base_handle).dxf.name)
        if base_block is None:
            return
        self.add_import_statement(
            "from ezdxf.dynblkhelper import set_dynamic_block_reference"
        )
        self.add_source_code_line(
            f"set_dynamic_block_reference(b, {self.doc}.blocks.get({json.dumps(base_block.name)}), clone_property_attdefs=False, normalize_entities=True)"
        )
        if any(child.dxftype() == "ATTDEF" and child.get_reactors() for child in block):
            self.add_import_statement(
                "from ezdxf.dynblkhelper import get_dynamic_block_properties_table"
            )
            self.add_source_code_line(
                f"_base = {self.doc}.blocks.get({json.dumps(base_block.name)})"
            )
            self.add_source_code_line("_props = get_dynamic_block_properties_table(_base)")
            self.add_source_code_line("if _props is not None:")
            self.add_source_code_line(
                "    for _attdef in (entity for entity in b if entity.dxftype() == 'ATTDEF'):"
            )
            self.add_source_code_line(
                "        _attdef.set_reactors([_props.handle])"
            )
        self._emit_block_rep_etag_preservation(block)

    def _schedule_dynamic_block_insert_state(self, entity: Insert) -> None:
        from ezdxf.dynblkhelper import (
            get_dynamic_block_definition,
            get_dynamic_block_visibility_parameter,
            get_dynamic_block_visibility_state,
        )

        base_block = get_dynamic_block_definition(entity)
        if base_block is None:
            return
        parameter = get_dynamic_block_visibility_parameter(entity)
        handle = entity.dxf.get("handle")
        if not handle:
            return
        cache_records = self._dynamic_insert_cache_records(entity)
        appdata_records = self._dynamic_insert_appdata_records(entity)
        if parameter is None:
            if entity.has_extension_dict:
                self.add_import_statement(
                    "from ezdxf.dynblkhelper import set_dynamic_block_insert_cache"
                )
                self.add_deferred_source_code_line(
                    f"set_dynamic_block_insert_cache(_entity_map[{json.dumps(handle)}], {self.doc}.blocks.get({json.dumps(base_block.name)}), location={self._format_python_value(tuple(entity.dxf.insert))}, update_cache={not bool(cache_records)})"
                )
                self._emit_dynamic_insert_cache_records(cache_records, handle, base_block.name)
                self._emit_dynamic_insert_appdata_records(appdata_records, handle, base_block.name)
            return
        state = get_dynamic_block_visibility_state(entity)
        if not state:
            return
        self.add_import_statement(
            "from ezdxf.dynblkhelper import set_dynamic_block_visibility_state"
        )
        self.add_deferred_source_code_line(
            f"set_dynamic_block_visibility_state(_entity_map[{json.dumps(handle)}], {self.doc}.blocks.get({json.dumps(base_block.name)}), state={json.dumps(state)}, location={self._format_python_value(parameter.location)}, update_cache={not bool(cache_records)})"
        )
        self._emit_dynamic_insert_cache_records(cache_records, handle, base_block.name)
        self._emit_dynamic_insert_appdata_records(appdata_records, handle, base_block.name)

    @staticmethod
    def _dynamic_insert_cache_records(
        entity: Insert,
    ) -> list[tuple[str, tuple[tuple[int, Any], ...]]]:
        if not entity.has_extension_dict:
            return []
        rep = entity.get_extension_dict().dictionary.get("AcDbBlockRepresentation")
        if not isinstance(rep, Dictionary):
            return []
        cache = rep.get("AppDataCache")
        if not isinstance(cache, Dictionary):
            return []
        enhanced = cache.get("ACAD_ENHANCEDBLOCKDATA")
        if not isinstance(enhanced, Dictionary):
            return []
        records: list[tuple[str, tuple[tuple[int, Any], ...]]] = []
        for key, value in enhanced.items():
            if isinstance(value, XRecord):
                records.append((str(key), tuple((tag.code, tag.value) for tag in value.tags)))
        return records

    @staticmethod
    def _dynamic_insert_appdata_records(
        entity: Insert,
    ) -> list[tuple[str, tuple[tuple[int, Any], ...]]]:
        if not entity.has_extension_dict:
            return []
        rep = entity.get_extension_dict().dictionary.get("AcDbBlockRepresentation")
        if not isinstance(rep, Dictionary):
            return []
        cache = rep.get("AppDataCache")
        if not isinstance(cache, Dictionary):
            return []
        records: list[tuple[str, tuple[tuple[int, Any], ...]]] = []
        for key, value in cache.items():
            if isinstance(value, XRecord):
                records.append((str(key), tuple((tag.code, tag.value) for tag in value.tags)))
        return records

    def _emit_dynamic_insert_cache_records(
        self,
        records: list[tuple[str, tuple[tuple[int, Any], ...]]],
        handle: str,
        base_block_name: str,
    ) -> None:
        if not records:
            return
        self.add_import_statement(
            "from ezdxf.dynblkhelper import set_dynamic_block_insert_cache_record"
        )
        self.add_deferred_source_code_line(
            f"_base = {self.doc}.blocks.get({json.dumps(base_block_name)})"
        )
        for key, tags in records:
            self.add_deferred_source_code_line(
                f"set_dynamic_block_insert_cache_record(_entity_map[{json.dumps(handle)}], {json.dumps(key)}, {self._format_python_value(tags)}, _base)"
            )

    def _emit_dynamic_insert_appdata_records(
        self,
        records: list[tuple[str, tuple[tuple[int, Any], ...]]],
        handle: str,
        base_block_name: str,
    ) -> None:
        if not records:
            return
        self.add_import_statement(
            "from ezdxf.dynblkhelper import set_dynamic_block_insert_appdata_record"
        )
        self.add_deferred_source_code_line(
            f"_base = {self.doc}.blocks.get({json.dumps(base_block_name)})"
        )
        for key, tags in records:
            self.add_deferred_source_code_line(
                f"set_dynamic_block_insert_appdata_record(_entity_map[{json.dumps(handle)}], {json.dumps(key)}, {self._format_python_value(tags)}, _base)"
            )

    def _format_python_value(self, value: Any) -> str:
        if isinstance(value, str):
            return json.dumps(value)
        if isinstance(value, (list, tuple)):
            items = ", ".join(self._format_python_value(item) for item in value)
            opener, closer = ("[", "]") if isinstance(value, list) else ("(", ")")
            if len(value) == 1 and isinstance(value, tuple):
                items += ","
            return f"{opener}{items}{closer}"
        if type(value).__name__ == "Vec3":
            self.add_import_statement("from ezdxf.math import Vec3")
            return repr(value)
        return repr(value)

    @staticmethod
    def _named_object_resource_name(entity, collection_name: str, handle: str) -> Optional[str]:
        doc = entity.doc
        if doc is None:
            return None
        collection = getattr(doc, collection_name, None)
        if collection is None:
            return None
        for name, resource in collection:
            if resource.dxf.handle == handle:
                return name
        return None

    @staticmethod
    def _resource_name_by_handle(entity, handle: Optional[str]) -> Optional[str]:
        if not handle:
            return None
        doc = entity.doc
        if doc is None:
            return None
        resource = doc.entitydb.get(handle)
        if resource is None:
            return None
        return resource.dxf.get("name")

    @staticmethod
    def _block_name_by_handle(entity, handle: Optional[str]) -> Optional[str]:
        return _SourceCodeGenerator._resource_name_by_handle(entity, handle)

    def _block_record_handle_expr(self, block_name: str) -> str:
        arrow_name = ARROWS.arrow_name(block_name)
        if arrow_name in ARROWS:
            self.add_import_statement("from ezdxf.render.arrows import ARROWS")
            return f"ARROWS.arrow_handle({self.doc}.blocks, {json.dumps(arrow_name)})"
        self.code.blocks.add(block_name)
        return f"{self.doc}.blocks.get({json.dumps(block_name)}).block_record_handle"

    def _set_block_record_handle_if_exists(
        self, owner: str, attrib_name: str, block_name: str
    ) -> None:
        arrow_name = ARROWS.arrow_name(block_name)
        if arrow_name in ARROWS:
            self.add_source_code_line(
                f"{owner}.dxf.{attrib_name} = {self._block_record_handle_expr(block_name)}"
            )
            return
        self.code.blocks.add(block_name)
        self.add_source_code_line(
            f'if {json.dumps(block_name)} in {self.doc}.blocks:'
        )
        self.add_source_code_line(
            f'    {owner}.dxf.{attrib_name} = {self.doc}.blocks.get({json.dumps(block_name)}).block_record_handle'
        )
        self.add_source_code_line("else:")
        self.add_source_code_line(f'    {owner}.dxf.discard({json.dumps(attrib_name)})')

    def _set_multileader_resource_handles(
        self,
        entity,
        *,
        style_name: str,
        leader_linetype_name: Optional[str],
        text_style_name: str,
        mtext_style_name: Optional[str] = None,
    ) -> None:
        self.add_source_code_line(
            f'e.dxf.style_handle = {self.doc}.mleader_styles.get({json.dumps(style_name)}).dxf.handle'
        )
        if leader_linetype_name is not None:
            self.add_source_code_line(
                f'e.dxf.leader_linetype_handle = {self.doc}.linetypes.get({json.dumps(leader_linetype_name)}).dxf.handle'
            )
        self.add_source_code_line(
            f'e.dxf.text_style_handle = {self.doc}.styles.get({json.dumps(text_style_name)}).dxf.handle'
        )
        if mtext_style_name is not None:
            self.add_source_code_line(
                f'mtext.style_handle = {self.doc}.styles.get({json.dumps(mtext_style_name)}).dxf.handle'
            )

    def _setup_multileader_style(self, entity, style_name: str) -> None:
        doc = entity.doc
        if doc is None:
            return
        style = doc.mleader_styles.get(style_name)
        if style is None:
            return

        dxfattribs = _purge_handles(style.dxfattribs())
        dxfattribs.pop("name", None)
        for name in (
            "leader_linetype_handle",
            "arrow_head_handle",
            "text_style_handle",
            "block_record_handle",
        ):
            dxfattribs.pop(name, None)
        style_text_style_name = self._resource_name_by_handle(
            entity, style.dxf.get("text_style_handle")
        )
        style_linetype_name = self._resource_name_by_handle(
            entity, style.dxf.get("leader_linetype_handle")
        )
        style_arrow_block_name = self._block_name_by_handle(
            entity, style.dxf.get("arrow_head_handle")
        )
        style_block_record_name = self._block_name_by_handle(
            entity, style.dxf.get("block_record_handle")
        )

        if style_name == "Standard":
            self.add_source_code_line(
                f'mlstyle = {self.doc}.mleader_styles.get({json.dumps(style_name)})'
            )
        else:
            self.add_source_code_line(
                f'if {json.dumps(style_name)} in {self.doc}.mleader_styles:'
            )
            self.add_source_code_line(
                f'    mlstyle = {self.doc}.mleader_styles.get({json.dumps(style_name)})'
            )
            self.add_source_code_line("else:")
            self.add_source_code_line(
                f'    mlstyle = {self.doc}.mleader_styles.duplicate_entry("Standard", {json.dumps(style_name)})'
            )

        for name, value in dxfattribs.items():
            self.add_source_code_line(
                f"mlstyle.dxf.{name} = {self._format_python_value(value)}"
            )

        if style_text_style_name is not None:
            self.code.styles.add(style_text_style_name)
            self.add_source_code_line(
                f'mlstyle.dxf.text_style_handle = {self.doc}.styles.get({json.dumps(style_text_style_name)}).dxf.handle'
            )
        if style_linetype_name is not None:
            self.code.linetypes.add(style_linetype_name)
            self.add_source_code_line(
                f'mlstyle.dxf.leader_linetype_handle = {self.doc}.linetypes.get({json.dumps(style_linetype_name)}).dxf.handle'
            )
        if style_arrow_block_name is not None:
            self.add_source_code_line(
                f"mlstyle.dxf.arrow_head_handle = {self._block_record_handle_expr(style_arrow_block_name)}"
            )
        else:
            self.add_source_code_line('mlstyle.dxf.discard("arrow_head_handle")')
        if style_block_record_name is not None:
            self._set_block_record_handle_if_exists(
                "mlstyle", "block_record_handle", style_block_record_name
            )
        else:
            self.add_source_code_line('mlstyle.dxf.discard("block_record_handle")')

    def _multileader_supported(self, entity: "MultiLeader") -> tuple[bool, dict[str, Any]]:
        context = entity.context
        doc = entity.doc
        if doc is None:
            return False, {}
        has_mtext_content = entity.has_mtext_content and context.mtext is not None
        has_block_content = context.block is not None
        if not has_mtext_content and not has_block_content:
            return False, {}
        style_name = self._named_object_resource_name(
            entity, "mleader_styles", entity.dxf.style_handle
        )
        leader_linetype_name = self._resource_name_by_handle(
            entity, entity.dxf.leader_linetype_handle
        )
        text_style_name = self._resource_name_by_handle(
            entity, entity.dxf.text_style_handle
        )
        style = doc.mleader_styles.get(style_name) if style_name is not None else None
        if style is None:
            return False, {}
        style_arrow_handle = style.dxf.get("arrow_head_handle")
        style_block_handle = style.dxf.get("block_record_handle")
        if style_arrow_handle is not None and self._block_name_by_handle(entity, style_arrow_handle) is None:
            return False, {}
        if style_block_handle is not None and self._block_name_by_handle(entity, style_block_handle) is None:
            return False, {}
        entity_arrow_block_name = self._block_name_by_handle(
            entity, entity.dxf.get("arrow_head_handle")
        )
        if entity.dxf.get("arrow_head_handle") is not None and entity_arrow_block_name is None:
            return False, {}
        multi_arrow_block_names: list[tuple[int, str]] = []
        for arrow_head in entity.arrow_heads:
            block_name = self._block_name_by_handle(entity, arrow_head.handle)
            if block_name is None:
                return False, {}
            multi_arrow_block_names.append((arrow_head.index, block_name))
        if not all((style_name, text_style_name)):
            return False, {}

        resources: dict[str, Any] = {
            "style_name": style_name,
            "leader_linetype_name": leader_linetype_name,
            "text_style_name": text_style_name,
            "entity_arrow_block_name": entity_arrow_block_name,
            "multi_arrow_block_names": multi_arrow_block_names,
        }
        if has_mtext_content:
            mtext_style_name = self._resource_name_by_handle(
                entity, context.mtext.style_handle
            )
            if not mtext_style_name:
                return False, {}
            resources["content_type"] = "mtext"
            resources["mtext_style_name"] = mtext_style_name
            return True, resources

        block_name = self._block_name_by_handle(
            entity, entity.dxf.get("block_record_handle")
        )
        context_block_name = self._block_name_by_handle(
            entity, context.block.block_record_handle
        )
        if not block_name or not context_block_name:
            return False, {}
        resources["content_type"] = "block"
        resources["block_name"] = block_name
        resources["context_block_name"] = context_block_name
        return True, resources

    def _schedule_hosted_fields(self, entity: DXFEntity) -> None:
        has_field_dict = getattr(entity, "has_field_dict", None)
        get_field_dict = getattr(entity, "get_field_dict", None)
        set_field = getattr(entity, "set_field", None)
        if not callable(has_field_dict) or not callable(get_field_dict) or not callable(set_field):
            return
        if not has_field_dict():
            return
        handle = entity.dxf.get("handle")
        if not handle:
            self.add_deferred_source_code_line(
                f'# unsupported hosted FIELD on {entity.dxftype()}: missing handle'
            )
            return
        for key, wrapper in get_field_dict().items():
            if getattr(wrapper, "dxftype", lambda: "")() != "FIELD":
                self.add_deferred_source_code_line(
                    f'# unsupported hosted FIELD on {entity.dxftype()} key {json.dumps(key)}'
                )
                continue
            child_fields = wrapper.get_child_fields() if wrapper.is_text_wrapper else []
            if not wrapper.is_text_wrapper or not child_fields:
                self.add_deferred_source_code_line(
                    f'# unsupported hosted FIELD on {entity.dxftype()} key {json.dumps(key)}'
                )
                continue
            child = child_fields[0]
            self.add_deferred_source_code_line(
                f'_host = _entity_map[{json.dumps(handle)}]'
            )
            register_field_list = self._uses_field_list(wrapper, child)
            child_vars = self._emit_text_wrapper_construction(wrapper, "_wrapper", "_host")
            if child_vars is None:
                self.add_deferred_source_code_line(
                    f'# unsupported hosted FIELD on {entity.dxftype()} key {json.dumps(key)}'
                )
                continue
            self.add_deferred_source_code_line(
                f"_host.set_field(_wrapper, key={json.dumps(key)})"
            )
            for child_var in child_vars:
                self.add_deferred_source_code_line(
                    f"{child_var}.dxf.owner = _wrapper.dxf.handle"
                )
            self.add_deferred_source_code_line(
                "_wrapper.set_reactors([_host.get_field_dict().dxf.handle])"
            )
            if register_field_list:
                self.add_deferred_source_code_line("_field_list = _host.doc.objects.setup_field_list()")
                self.add_deferred_source_code_line("_handles = list(_field_list.handles)")
                self.add_deferred_source_code_line(
                    "for _handle in (linked.dxf.handle for linked in _wrapper.get_field_tree()):"
                )
                self.add_deferred_source_code_line(
                    "    if _handle and _handle not in _handles:"
                )
                self.add_deferred_source_code_line("        _handles.append(_handle)")
                self.add_deferred_source_code_line("_field_list.handles = _handles")

    def generic_api_call(
        self, dxftype: str, dxfattribs: dict, prefix: str = "e = "
    ) -> Iterable[str]:
        """Returns the source code strings to create a DXF entity by a generic
        `new_entity()` call.

        Args:
            dxftype: DXF entity type as string, like 'LINE'
            dxfattribs: DXF attributes dictionary
            prefix: prefix string like variable assignment 'e = '

        """
        dxfattribs = _purge_handles(dxfattribs)
        self.add_used_resources(dxfattribs)
        s = [
            f"{prefix}{self.layout}.new_entity(",
            f"    '{dxftype}',",
            "    dxfattribs={",
        ]
        s.extend(_fmt_mapping(dxfattribs, indent=8))
        s.extend(
            [
                "    },",
                ")",
            ]
        )
        return s

    def api_call(
        self,
        api_call: str,
        args: Iterable[str],
        dxfattribs: dict,
        prefix: str = "e = ",
    ) -> Iterable[str]:
        """Returns the source code strings to create a DXF entity by the
        specialised API call.

        Args:
            api_call: API function call like 'add_line('
            args: DXF attributes to pass as arguments
            dxfattribs: DXF attributes dictionary
            prefix: prefix string like variable assignment 'e = '

        """
        dxfattribs = _purge_handles(dxfattribs)
        func_call = f"{prefix}{self.layout}.{api_call}"
        return _fmt_api_call(func_call, args, dxfattribs)

    def new_table_entry(self, dxftype: str, dxfattribs: dict) -> Iterable[str]:
        """Returns the source code strings to create a new table entity by
        ezdxf.

        Args:
            dxftype: table entry type as string, like 'LAYER'
            dxfattribs: DXF attributes dictionary

        """
        table = f"{self.doc}.{TABLENAMES[dxftype]}"
        dxfattribs = _purge_handles(dxfattribs)
        name = dxfattribs.pop("name")
        s = [
            f"if '{name}' not in {table}:",
            f"    t = {table}.new(",
            f"        '{name}',",
            "        dxfattribs={",
        ]
        s.extend(_fmt_mapping(dxfattribs, indent=12))
        s.extend(
            [
                "        },",
                "    )",
            ]
        )
        return s

    # simple graphical types

    def _line(self, entity: DXFEntity) -> None:
        self.add_source_code_lines(
            self.api_call("add_line(", ["start", "end"], entity.dxfattribs())
        )

    def _point(self, entity: DXFEntity) -> None:
        self.add_source_code_lines(
            self.api_call("add_point(", ["location"], entity.dxfattribs())
        )

    def _circle(self, entity: DXFEntity) -> None:
        self.add_source_code_lines(
            self.api_call(
                "add_circle(", ["center", "radius"], entity.dxfattribs()
            )
        )

    def _arc(self, entity: DXFEntity) -> None:
        self.add_source_code_lines(
            self.api_call(
                "add_arc(",
                ["center", "radius", "start_angle", "end_angle"],
                entity.dxfattribs(),
            )
        )

    def _text(self, entity: DXFEntity) -> None:
        self.add_source_code_lines(
            self.api_call("add_text(", ["text"], entity.dxfattribs())
        )

    def _solid(self, entity: DXFEntity) -> None:
        self.add_source_code_lines(
            self.generic_api_call("SOLID", entity.dxfattribs())
        )

    def _trace(self, entity: DXFEntity) -> None:
        self.add_source_code_lines(
            self.generic_api_call("TRACE", entity.dxfattribs())
        )

    def _3dface(self, entity: DXFEntity) -> None:
        self.add_source_code_lines(
            self.generic_api_call("3DFACE", entity.dxfattribs())
        )

    def _shape(self, entity: DXFEntity) -> None:
        self.add_source_code_lines(
            self.api_call(
                "add_shape(", ["name", "insert", "size"], entity.dxfattribs()
            )
        )

    def _attrib(self, entity: DXFEntity) -> None:
        self.add_source_code_lines(
            self.api_call(
                "add_attrib(", ["tag", "text", "insert"], entity.dxfattribs()
            )
        )
        if entity.has_extension_dict:
            self.add_source_code_line(
                "if not a.has_extension_dict: a.new_extension_dict()"
            )

    def _attdef(self, entity: DXFEntity) -> None:
        self.add_source_code_lines(
            self.generic_api_call("ATTDEF", entity.dxfattribs())
        )
        rep_index = self._attdef_rep_index(entity)
        if rep_index is not None:
            self.add_import_statement(
                "from ezdxf.dynblkhelper import setup_dynamic_block_property_attdef_support"
            )
            self.add_source_code_line(
                f"setup_dynamic_block_property_attdef_support(e, {rep_index}, annotative={entity.has_xdata('AcadAnnotative')}, create_context_record={self._attdef_has_context_record(entity)})"
            )

    def _mleaderstyle(self, entity: DXFEntity) -> None:
        self._setup_multileader_style(entity, entity.dxf.name)

    def _ellipse(self, entity: DXFEntity) -> None:
        self.add_source_code_lines(
            self.api_call(
                "add_ellipse(",
                ["center", "major_axis", "ratio", "start_param", "end_param"],
                entity.dxfattribs(),
            )
        )

    def _viewport(self, entity: DXFEntity) -> None:
        self.add_source_code_lines(
            self.generic_api_call("VIEWPORT", entity.dxfattribs())
        )
        self.add_source_code_line(
            '# Set valid handles or remove attributes ending with "_handle", '
            "otherwise the DXF file is invalid for AutoCAD"
        )

    # complex graphical types

    def _insert(self, entity: Insert) -> None:
        self.code.blocks.add(entity.dxf.name)
        self.add_source_code_lines(
            self.api_call(
                "add_blockref(", ["name", "insert"], entity.dxfattribs()
            )
        )
        self._schedule_dynamic_block_insert_state(entity)
        if entity.has_extension_dict:
            xdict = entity.get_extension_dict().dictionary
            if "AcDbContextDataManager" in xdict:
                self.add_source_code_line(
                    "_xdict = e.get_extension_dict() if e.has_extension_dict else e.new_extension_dict()"
                )
                self.add_source_code_line(
                    "_ctx = _xdict.dictionary.get('AcDbContextDataManager')"
                )
                self.add_source_code_line(
                    "if _ctx is None: _ctx = _xdict.dictionary.add_new_dict('AcDbContextDataManager')"
                )
                self.add_source_code_line(
                    "_scales = _ctx.get('ACDB_ANNOTATIONSCALES')"
                )
                self.add_source_code_line(
                    "if _scales is None: _scales = _ctx.add_new_dict('ACDB_ANNOTATIONSCALES')"
                )
        if len(entity.attribs):
            for attrib in entity.attribs:
                dxfattribs = _purge_handles(attrib.dxfattribs())
                dxfattribs[
                    "layer"
                ] = entity.dxf.layer  # set ATTRIB layer to same as INSERT
                self.add_used_resources(dxfattribs)
                self.add_source_code_lines(
                    _fmt_api_call(
                        "a = e.add_attrib(",
                        ["tag", "text", "insert"],
                        dxfattribs,
                    )
                )
                if attrib.has_extension_dict:
                    self.add_source_code_line(
                        "if not a.has_extension_dict: a.new_extension_dict()"
                    )
                self._register_entity_handle(attrib, var_name="a")
                self._schedule_hosted_fields(attrib)

    def _mtext(self, entity: MText) -> None:
        self.add_source_code_lines(
            self.generic_api_call("MTEXT", entity.dxfattribs())
        )
        # MTEXT content 'text' is not a single DXF tag and therefore not a DXF
        # attribute
        self.add_source_code_line("e.text = {}".format(json.dumps(entity.text)))
        if entity.has_extension_dict:
            self.add_source_code_line(
                "if not e.has_extension_dict: e.new_extension_dict()"
            )
        if entity.has_extension_dict and "AcDbContextDataManager" in entity.get_extension_dict().dictionary:
            self.add_source_code_line(
                "_xdict = e.get_extension_dict() if e.has_extension_dict else e.new_extension_dict()"
            )
            self.add_source_code_line(
                "_ctx = _xdict.dictionary.get('AcDbContextDataManager')"
            )
            self.add_source_code_line(
                "if _ctx is None: _ctx = _xdict.dictionary.add_new_dict('AcDbContextDataManager')"
            )
            self.add_source_code_line(
                "_scales = _ctx.get('ACDB_ANNOTATIONSCALES')"
            )
            self.add_source_code_line(
                "if _scales is None: _scales = _ctx.add_new_dict('ACDB_ANNOTATIONSCALES')"
            )
        if entity.has_extension_dict and "ACAD_FIELD" in entity.get_extension_dict().dictionary:
            field_dict = entity.get_extension_dict().dictionary.get("ACAD_FIELD")
            is_empty_field_dict = hasattr(field_dict, "items") and len(list(field_dict.items())) == 0
            if is_empty_field_dict:
                self.add_source_code_line(
                    "_xdict = e.get_extension_dict() if e.has_extension_dict else e.new_extension_dict()"
                )
                self.add_source_code_line(
                    "if 'ACAD_FIELD' not in _xdict.dictionary: _xdict.dictionary.add_new_dict('ACAD_FIELD', hard_owned=True)"
                )

    def _acad_table(self, entity: DXFEntity) -> None:
        data = getattr(entity, "data", None)
        if data is None:
            self.add_source_code_line('# unsupported DXF entity "ACAD_TABLE"')
            return

        style = getattr(entity, "get_table_style", lambda: None)()
        style_name = style.dxf.name if style is not None else "Standard"
        if style_name != "Standard":
            self.add_source_code_line(
                f"# ACAD_TABLE requires TABLESTYLE {json.dumps(style_name)} in target doc"
            )

        dxfattribs = _purge_handles(entity.dxfattribs())
        insert = dxfattribs.pop("insert", (0, 0, 0))
        for key in (
            "geometry",
            "version",
            "table_style_id",
            "block_record_handle",
            "horizontal_direction",
            "table_value",
            "n_rows",
            "n_cols",
            "override_flag",
            "border_color_override_flag",
            "border_lineweight_override_flag",
            "border_visibility_override_flag",
        ):
            dxfattribs.pop(key, None)
        self.add_used_resources(dxfattribs)

        content: list[list[str]] = []
        for row in data.rows():
            content.append([
                (
                    self._field_display_text(entity.get_cell_primary_field(cell.row, cell.col))
                    if cell.is_text_cell and cell.field_handle is not None and entity.get_cell_primary_field(cell.row, cell.col) is not None
                    else cell.text if cell.is_text_cell else ""
                )
                for cell in row
            ])

        self.add_source_code_line(f"e = {self.layout}.add_table(")
        self.add_source_code_line(f"    {self._format_python_value(insert)},")
        self.add_source_code_line(f"    {self._format_python_value(content)},")
        if style_name != "Standard":
            self.add_source_code_line(f"    style_name={json.dumps(style_name)},")
        self.add_source_code_line(
            f"    row_heights={self._format_python_value(data.row_heights)},"
        )
        self.add_source_code_line(
            f"    col_widths={self._format_python_value(data.col_widths)},"
        )
        self.add_source_code_line("    dxfattribs={")
        self.add_source_code_lines(_fmt_mapping(dxfattribs, indent=8))
        self.add_source_code_line("    },")
        self.add_source_code_line(")")

        self._emit_acad_table_mutations(entity)
        self._schedule_acad_table_fields(entity)

    def _schedule_acad_table_fields(self, entity: DXFEntity) -> None:
        data = getattr(entity, "data", None)
        handle = entity.dxf.get("handle")
        if data is None or not handle:
            return
        for cell in data.cells:
            if cell.field_handle is None:
                continue
            wrapper = getattr(entity, "get_cell_field", lambda *_: None)(cell.row, cell.col)
            primary = getattr(entity, "get_cell_primary_field", lambda *_: None)(cell.row, cell.col)
            if (
                getattr(wrapper, "dxftype", lambda: "")() != "FIELD"
                or primary is None
            ):
                self.add_deferred_source_code_line(
                    f"# unsupported ACAD_TABLE field cell at ({cell.row}, {cell.col})"
                )
                continue
            self.add_deferred_source_code_line(
                f'_host = _entity_map[{json.dumps(handle)}]'
            )
            if not self._emit_field_construction(primary, "_field", "_host"):
                self.add_deferred_source_code_line(
                    f"# unsupported ACAD_TABLE field cell at ({cell.row}, {cell.col})"
                )
                continue
            self.add_deferred_source_code_line("_host.set_cell_linked_field(")
            self.add_deferred_source_code_line(f"    {cell.row},")
            self.add_deferred_source_code_line(f"    {cell.col},")
            self.add_deferred_source_code_line("    _field,")
            self.add_deferred_source_code_line(
                f"    text={json.dumps(self._field_display_text(primary))},"
            )
            self.add_deferred_source_code_line(
                f"    register_field_list={self._uses_field_list(wrapper, primary)},"
            )
            self.add_deferred_source_code_line(")")

    def _emit_acad_table_mutations(self, entity: DXFEntity) -> None:
        data = getattr(entity, "data", None)
        if data is None:
            return

        inferred_title = 0 if data.n_rows >= 3 else 1
        inferred_header = 0 if data.n_rows >= 2 else 1
        if (data.suppress_title or 0) != inferred_title:
            self.add_source_code_line(
                f"e.set_title_suppressed({bool(data.suppress_title)})"
            )
        if (data.suppress_column_header or 0) != inferred_header:
            self.add_source_code_line(
                f"e.set_column_header_suppressed({bool(data.suppress_column_header)})"
            )

        for cell in data.cells:
            row = cell.row
            col = cell.col
            if cell.is_block_cell:
                block_name = getattr(entity, "get_cell_block_name", lambda *_: "")(row, col)
                if not block_name:
                    self.add_source_code_line(
                        f"# unsupported ACAD_TABLE block cell at ({row}, {col})"
                    )
                    continue
                self.code.blocks.add(block_name)
                alignment = cell.alignment if cell.alignment is not None else 1
                self.add_source_code_line(
                    f"e.set_cell_block({row}, {col}, {json.dumps(block_name)}, block_scale={cell.block_scale}, alignment={alignment})"
                )
                continue

            if cell.text_height is not None:
                self.add_source_code_line(
                    f"e.set_cell_text_height({row}, {col}, {cell.text_height})"
                )
            if cell.alignment is not None:
                self.add_source_code_line(
                    f"e.set_cell_alignment({row}, {col}, {cell.alignment})"
                )
            if cell.text_style is not None:
                self.code.styles.add(cell.text_style)
                self.add_source_code_line(
                    f"e.set_cell_text_style({row}, {col}, {json.dumps(cell.text_style)})"
                )
            if cell.fill_enabled == 1:
                self.add_source_code_line(f"e.clear_cell_fill({row}, {col})")
            elif cell.fill_color is not None:
                if cell.fill_true_color is not None:
                    self.add_source_code_line(
                        f"e.set_cell_fill_color({row}, {col}, {cell.fill_color}, {cell.fill_true_color})"
                    )
                else:
                    self.add_source_code_line(
                        f"e.set_cell_fill_color({row}, {col}, {cell.fill_color})"
                    )

    def _multileader(self, entity: "MultiLeader") -> None:
        supported, resources = self._multileader_supported(entity)
        if not supported:
            self.add_source_code_line('# unsupported DXF entity "MULTILEADER"')
            return False

        self.add_import_statement(
            "from ezdxf.entities.mleader import ArrowHeadData, AttribData, BlockData, LeaderData, LeaderLine, MTextData"
        )
        dxfattribs = entity.dxfattribs()
        for key in (
            "style_handle",
            "leader_linetype_handle",
            "text_style_handle",
            "arrow_head_handle",
            "block_record_handle",
        ):
            dxfattribs.pop(key, None)
        self.add_used_resources(dxfattribs)
        if resources["leader_linetype_name"] is not None:
            self.code.linetypes.add(resources["leader_linetype_name"])
        self.code.styles.add(resources["text_style_name"])
        if resources["content_type"] == "mtext":
            self.code.styles.add(resources["mtext_style_name"])
        else:
            self.code.blocks.add(resources["block_name"])
            self.code.blocks.add(resources["context_block_name"])
        self._setup_multileader_style(entity, resources["style_name"])
        self.add_source_code_lines(self.generic_api_call("MULTILEADER", dxfattribs))
        if entity.has_extension_dict:
            self.add_source_code_line(
                "if not e.has_extension_dict: e.new_extension_dict()"
            )
        self.add_source_code_line("ctx = e.context")
        for name in (
            "scale",
            "base_point",
            "char_height",
            "arrow_head_size",
            "landing_gap_size",
            "left_attachment",
            "right_attachment",
            "text_align_type",
            "attachment_type",
            "plane_origin",
            "plane_x_axis",
            "plane_y_axis",
            "plane_normal_reversed",
            "top_attachment",
            "bottom_attachment",
        ):
            self.add_source_code_line(
                f"ctx.{name} = {self._format_python_value(getattr(entity.context, name))}"
            )
        if resources["content_type"] == "mtext":
            self.add_source_code_line("mtext = MTextData()")
            for name in (
                "default_content",
                "extrusion",
                "insert",
                "text_direction",
                "rotation",
                "width",
                "defined_height",
                "line_spacing_factor",
                "line_spacing_style",
                "color",
                "alignment",
                "flow_direction",
                "bg_color",
                "bg_scale_factor",
                "bg_transparency",
                "use_window_bg_color",
                "has_bg_fill",
                "column_type",
                "use_auto_height",
                "column_width",
                "column_gutter_width",
                "column_flow_reversed",
                "column_sizes",
                "use_word_break",
            ):
                self.add_source_code_line(
                    f"mtext.{name} = {self._format_python_value(getattr(entity.context.mtext, name))}"
                )
            self._set_multileader_resource_handles(
                entity,
                style_name=resources["style_name"],
                leader_linetype_name=resources["leader_linetype_name"],
                text_style_name=resources["text_style_name"],
                mtext_style_name=resources["mtext_style_name"],
            )
            self.add_source_code_line("ctx.mtext = mtext")
            self.add_source_code_line("ctx.block = None")
        else:
            self.add_source_code_line(
                f'_block = {self.doc}.blocks.get({json.dumps(resources["block_name"])})'
            )
            self.add_source_code_line(
                f'_ctx_block = {self.doc}.blocks.get({json.dumps(resources["context_block_name"])})'
            )
            self.add_source_code_line("block = BlockData()")
            for name in (
                "extrusion",
                "insert",
                "scale",
                "rotation",
                "color",
            ):
                self.add_source_code_line(
                    f"block.{name} = {self._format_python_value(getattr(entity.context.block, name))}"
                )
            self.add_source_code_line(
                f"block._matrix = {self._format_python_value(entity.context.block._matrix)}"
            )
            self._set_multileader_resource_handles(
                entity,
                style_name=resources["style_name"],
                leader_linetype_name=resources["leader_linetype_name"],
                text_style_name=resources["text_style_name"],
            )
            self.add_source_code_line("e.dxf.block_record_handle = _block.block_record_handle")
            self.add_source_code_line("block.block_record_handle = _ctx_block.block_record_handle")
            self.add_source_code_line("ctx.block = block")
            self.add_source_code_line("ctx.mtext = None")
            self.add_source_code_line("e.block_attribs = []")
            self.add_source_code_line("_block_attdefs = list(_block.attdefs())")
            for attrib in entity.block_attribs:
                self.add_source_code_line(
                    "e.block_attribs.append(AttribData("
                    f"handle=_block_attdefs[{attrib.index}].dxf.handle, "
                    f"index={attrib.index}, width={attrib.width}, text={json.dumps(attrib.text)}"
                    "))"
                )
        if resources["entity_arrow_block_name"] is not None:
            self.add_source_code_line(
                f"e.dxf.arrow_head_handle = {self._block_record_handle_expr(resources['entity_arrow_block_name'])}"
            )
        if resources["multi_arrow_block_names"]:
            self.add_source_code_line("e.arrow_heads = []")
            for index, block_name in resources["multi_arrow_block_names"]:
                self.add_source_code_line(
                    "e.arrow_heads.append(ArrowHeadData("
                    f"{index}, {self._block_record_handle_expr(block_name)}"
                    "))"
                )
        self.add_source_code_line("ctx.leaders.clear()")
        for leader in entity.context.leaders:
            self.add_source_code_line("leader = LeaderData()")
            for name in (
                "has_last_leader_line",
                "has_dogleg_vector",
                "last_leader_point",
                "dogleg_vector",
                "dogleg_length",
                "index",
                "attachment_direction",
                "breaks",
            ):
                self.add_source_code_line(
                    f"leader.{name} = {self._format_python_value(getattr(leader, name))}"
                )
            self.add_source_code_line("leader.lines.clear()")
            for line in leader.lines:
                self.add_source_code_line("line = LeaderLine()")
                for name in ("vertices", "breaks", "index", "color"):
                    self.add_source_code_line(
                        f"line.{name} = {self._format_python_value(getattr(line, name))}"
                    )
                self.add_source_code_line("leader.lines.append(line)")
            self.add_source_code_line("ctx.leaders.append(leader)")
        self.add_source_code_line("e.update_proxy_graphic()")
        return True

    def _lwpolyline(self, entity: LWPolyline) -> None:
        self.add_source_code_lines(
            self.generic_api_call("LWPOLYLINE", entity.dxfattribs())
        )
        # lwpolyline points are not DXF attributes
        self.add_list_source_code(
            entity.get_points(), prolog="e.set_points([", epilog="])"
        )

    def _spline(self, entity: Spline) -> None:
        self.add_source_code_lines(
            self.api_call("add_spline(", ["degree"], entity.dxfattribs())
        )
        # spline points, knots and weights are not DXF attributes
        if len(entity.fit_points):
            self.add_list_source_code(
                entity.fit_points, prolog="e.fit_points = [", epilog="]"
            )

        if len(entity.control_points):
            self.add_list_source_code(
                entity.control_points, prolog="e.control_points = [", epilog="]"
            )

        if len(entity.knots):
            self.add_list_source_code(
                entity.knots, prolog="e.knots = [", epilog="]"
            )

        if len(entity.weights):
            self.add_list_source_code(
                entity.weights, prolog="e.weights = [", epilog="]"
            )

    def _polyline(self, entity: Polyline) -> None:
        self.add_source_code_lines(
            self.generic_api_call("POLYLINE", entity.dxfattribs())
        )
        # polyline vertices are separate DXF entities and therefore not DXF attributes
        for v in entity.vertices:
            attribs = _purge_handles(v.dxfattribs())
            location = attribs.pop("location")
            if "layer" in attribs:
                del attribs[
                    "layer"
                ]  # layer is automatically set to the POLYLINE layer

            # each VERTEX can have different DXF attributes: bulge, start_width, end_width ...
            self.add_source_code_line(
                f"e.append_vertex({str(location)}, dxfattribs={attribs})"
            )

    def _leader(self, entity: Leader):
        self.add_source_code_line(
            "# Dimension style attribute overriding is not supported!"
        )
        self.add_source_code_lines(
            self.generic_api_call("LEADER", entity.dxfattribs())
        )
        self.add_list_source_code(
            entity.vertices, prolog="e.set_vertices([", epilog="])"
        )

    def _dimension(self, entity: Dimension):
        self.add_import_statement(
            "from ezdxf.dimstyleoverride import DimStyleOverride"
        )
        self.add_source_code_line(
            "# Dimension style attribute overriding is not supported!"
        )
        self.add_source_code_lines(
            self.generic_api_call("DIMENSION", entity.dxfattribs())
        )
        self.add_source_code_lines(
            [
                "# You have to create the required graphical representation for ",
                "# the DIMENSION entity as anonymous block, otherwise the DXF file",
                "# is invalid for AutoCAD (but not for BricsCAD):",
                "# DimStyleOverride(e).render()",
                "",
            ]
        )

    def _image(self, entity: Image):
        self.add_source_code_line(
            "# Image requires IMAGEDEF and IMAGEDEFREACTOR objects in the "
            "OBJECTS section!"
        )
        self.add_source_code_lines(
            self.generic_api_call("IMAGE", entity.dxfattribs())
        )
        if len(entity.boundary_path):
            self.add_list_source_code(
                (v for v in entity.boundary_path),  # just x, y axis
                prolog="e.set_boundary_path([",
                epilog="])",
            )
        self.add_source_code_line(
            "# Set valid image_def_handle and image_def_reactor_handle, "
            "otherwise the DXF file is invalid for AutoCAD"
        )

    def _wipeout(self, entity: Wipeout):
        self.add_source_code_lines(
            self.generic_api_call("WIPEOUT", entity.dxfattribs())
        )
        if len(entity.boundary_path):
            self.add_list_source_code(
                (v for v in entity.boundary_path),  # just x, y axis
                prolog="e.set_boundary_path([",
                epilog="])",
            )

    def _mesh(self, entity: Mesh):
        self.add_source_code_lines(
            self.api_call("add_mesh(", [], entity.dxfattribs())
        )
        if len(entity.vertices):
            self.add_list_source_code(
                entity.vertices, prolog="e.vertices = [", epilog="]"
            )
        if len(entity.edges):
            # array.array -> tuple
            self.add_list_source_code(
                (tuple(e) for e in entity.edges),
                prolog="e.edges = [",
                epilog="]",
            )
        if len(entity.faces):
            # array.array -> tuple
            self.add_list_source_code(
                (tuple(f) for f in entity.faces),
                prolog="e.faces = [",
                epilog="]",
            )
        if len(entity.creases):
            self.add_list_source_code(
                entity.creases, prolog="e.creases = [", epilog="]"
            )

    def _hatch(self, entity: Hatch):
        dxfattribs = entity.dxfattribs()
        dxfattribs["associative"] = 0  # associative hatch not supported
        self.add_source_code_lines(
            self.api_call("add_hatch(", ["color"], dxfattribs)
        )
        self._polygon(entity)

    def _mpolygon(self, entity: MPolygon):
        dxfattribs = entity.dxfattribs()
        self.add_source_code_lines(
            self.api_call("add_mpolygon(", ["color"], dxfattribs)
        )
        if entity.dxf.solid_fill:
            self.add_source_code_line(
                f"e.set_solid_fill(color={entity.dxf.fill_color})\n"
            )
        self._polygon(entity)

    def _polygon(self, entity: DXFPolygon):
        add_line = self.add_source_code_line
        if len(entity.seeds):
            add_line(f"e.set_seed_points({entity.seeds})")
        if entity.pattern:
            self.add_list_source_code(
                map(str, entity.pattern.lines),
                prolog="e.set_pattern_definition([",
                epilog="])",
            )
            self.add_source_code_line("e.dxf.solid_fill = 0")
        arg = "    {}={},"

        if entity.gradient is not None:
            g = entity.gradient
            self.add_import_statement("from ezdxf.colors import RGB")
            add_line("e.set_gradient(")
            add_line(arg.format("color1", str(g.color1)))
            add_line(arg.format("color2", str(g.color2)))
            add_line(arg.format("rotation", g.rotation))
            add_line(arg.format("centered", g.centered))
            add_line(arg.format("one_color", g.one_color))
            add_line(arg.format("name", json.dumps(g.name)))
            add_line(")")
        for count, path in enumerate(entity.paths, start=1):
            if path.type == BoundaryPathType.POLYLINE:
                add_line("# {}. polyline path".format(count))
                self.add_list_source_code(
                    path.vertices,
                    prolog="e.paths.add_polyline_path([",
                    epilog="    ],",
                )
                add_line(arg.format("is_closed", str(path.is_closed)))
                add_line(arg.format("flags", str(path.path_type_flags)))
                add_line(")")
            else:  # EdgePath
                add_line(
                    f"# {count}. edge path: associative hatch not supported"
                )
                add_line(
                    f"ep = e.paths.add_edge_path(flags={path.path_type_flags})"
                )
                for edge in path.edges:
                    if edge.type == EdgeType.LINE:
                        add_line(f"ep.add_line({edge.start}, {str(edge.end)})")
                    elif edge.type == EdgeType.ARC:
                        # Start- and end angles are always stored in ccw
                        # orientation:
                        add_line("ep.add_arc(")
                        add_line(arg.format("center", str(edge.center)))
                        add_line(arg.format("radius", edge.radius))
                        add_line(arg.format("start_angle", edge.start_angle))
                        add_line(arg.format("end_angle", edge.end_angle))
                        add_line(arg.format("ccw", edge.ccw))
                        add_line(")")
                    elif edge.type == EdgeType.ELLIPSE:
                        # Start- and end params are always stored in ccw
                        # orientation:
                        add_line("ep.add_ellipse(")
                        add_line(arg.format("center", str(edge.center)))
                        add_line(arg.format("major_axis", str(edge.major_axis)))
                        add_line(arg.format("ratio", edge.ratio))
                        add_line(arg.format("start_angle", edge.start_angle))
                        add_line(arg.format("end_angle", edge.end_angle))
                        add_line(arg.format("ccw", edge.ccw))
                        add_line(")")
                    elif edge.type == EdgeType.SPLINE:
                        add_line("ep.add_spline(")
                        if edge.fit_points:
                            add_line(
                                arg.format(
                                    "fit_points",
                                    str([fp for fp in edge.fit_points]),
                                )
                            )
                        if edge.control_points:
                            add_line(
                                arg.format(
                                    "control_points",
                                    str([cp for cp in edge.control_points]),
                                )
                            )
                        if edge.knot_values:
                            add_line(
                                arg.format("knot_values", str(edge.knot_values))
                            )
                        if edge.weights:
                            add_line(arg.format("weights", str(edge.weights)))
                        add_line(arg.format("degree", edge.degree))
                        add_line(arg.format("periodic", edge.periodic))
                        if edge.start_tangent is not None:
                            add_line(
                                arg.format(
                                    "start_tangent", str(edge.start_tangent)
                                )
                            )
                        if edge.end_tangent is not None:
                            add_line(
                                arg.format("end_tangent", str(edge.end_tangent))
                            )
                        add_line(")")

    # simple table entries
    def _layer(self, layer: DXFEntity):
        self.add_source_code_lines(
            self.new_table_entry("LAYER", layer.dxfattribs())
        )

    def _ltype(self, ltype: Linetype):
        self.add_import_statement("from ezdxf.lldxf.tags import Tags")
        self.add_import_statement("from ezdxf.lldxf.types import dxftag")
        self.add_import_statement(
            "from ezdxf.entities.ltype import LinetypePattern"
        )
        self.add_source_code_lines(
            self.new_table_entry("LTYPE", ltype.dxfattribs())
        )
        self.add_tags_source_code(
            ltype.pattern_tags.tags,
            prolog="tags = Tags([",
            epilog="])",
            indent=4,
        )
        self.add_source_code_line("    t.pattern_tags = LinetypePattern(tags)")

    def _style(self, style: DXFEntity):
        self.add_source_code_lines(
            self.new_table_entry("STYLE", style.dxfattribs())
        )

    def _dimstyle(self, dimstyle: DXFEntity):
        self.add_source_code_lines(
            self.new_table_entry("DIMSTYLE", dimstyle.dxfattribs())
        )

    def _appid(self, appid: DXFEntity):
        self.add_source_code_lines(
            self.new_table_entry("APPID", appid.dxfattribs())
        )

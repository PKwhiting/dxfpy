# Copyright (c) 2026, Manfred Moitzi
# License: MIT License
from __future__ import annotations

import ast
import re
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, DecimalException, InvalidOperation
import math
from typing import TYPE_CHECKING, Protocol, TypeAlias

from dxfpy.lldxf import const

from .dxfentity import DXFEntity
from .dxfobj import Field

if TYPE_CHECKING:
    from dxfpy.document import Drawing

__all__ = [
    "DrawingProperty",
    "DrawingVariable",
    "ObjectProperty",
    "drawing_property",
    "drawing_variable",
    "object_property",
]

FieldScalar: TypeAlias = str | int | float | Decimal


@dataclass(frozen=True)
class DrawingProperty:
    """Reference a custom drawing property by name."""

    name: str
    value: FieldScalar | None = None
    display: str | None = None
    field_format: str = ""


@dataclass(frozen=True)
class DrawingVariable:
    """Reference a drawing variable such as ``CTab``."""

    name: str
    value: FieldScalar | None = None
    display: str | None = None


@dataclass(frozen=True)
class ObjectProperty:
    """Reference a property of a bound DXF entity."""

    target: DXFEntity
    property_name: str
    field_format: str = "%lu2"
    value: FieldScalar | None = None
    display: str | None = None


FieldTemplateValue: TypeAlias = (
    FieldScalar | DrawingProperty | DrawingVariable | ObjectProperty
)


def drawing_property(
    name: str,
    *,
    value: FieldScalar | None = None,
    display: str | None = None,
    field_format: str = "",
) -> DrawingProperty:
    """Create a custom drawing-property field source.

    :param name: Custom drawing property name.
    :param value: Optional property value to set.
    :param display: Optional cached display value.
    :param field_format: Native field-format string.
    :return: Immutable drawing-property source.
    """
    return DrawingProperty(name, value, display, field_format)


def drawing_variable(
    name: str,
    *,
    value: FieldScalar | None = None,
    display: str | None = None,
) -> DrawingVariable:
    """Create a drawing-variable field source.

    :param name: Drawing variable name, such as ``CTab``.
    :param value: Optional cached field value.
    :param display: Optional cached display value.
    :return: Immutable drawing-variable source.
    """
    return DrawingVariable(name, value, display)


def object_property(
    target: DXFEntity,
    property_name: str,
    *,
    field_format: str = "%lu2",
    value: FieldScalar | None = None,
    display: str | None = None,
) -> ObjectProperty:
    """Create an object-property field source.

    :param target: Bound target DXF entity.
    :param property_name: Object property name, such as ``Length``.
    :param field_format: Native field-format string.
    :param value: Optional cached property value.
    :param display: Optional cached display value.
    :return: Immutable object-property source.
    """
    return ObjectProperty(target, property_name, field_format, value, display)


class _FieldTemplateHost(Protocol):
    doc: Drawing | None

    def dxftype(self) -> str: ...

    def set_linked_fields(
        self,
        child_fields: Sequence[Field],
        key: str = "TEXT",
        *,
        field_code: str,
        text: str | None = None,
        register_field_list: bool = False,
    ) -> Field: ...

    def _infer_object_property_value(
        self, target: DXFEntity, property_name: str
    ) -> object | None: ...

    def _format_object_property_value(
        self, value: object, field_format: str
    ) -> str: ...


@dataclass(frozen=True)
class _Expression:
    source: str
    node: ast.expr
    names: tuple[str, ...]
    key: str

    @classmethod
    def parse(cls, source: str) -> _Expression:
        """Parse and validate one arithmetic field expression."""
        try:
            node = ast.parse(source, mode="eval").body
            names = _ExpressionValidator().validate(node)
        except SyntaxError as error:
            raise const.DXFValueError(
                f"invalid field expression: {source!r}"
            ) from error
        except RecursionError as error:
            raise const.DXFValueError("field expression is too complex") from error
        return cls(source, node, names, ast.dump(node, include_attributes=False))

    @property
    def is_direct_reference(self) -> bool:
        """Return ``True`` for an expression containing only one name."""
        return isinstance(self.node, ast.Name)

    def field_code(self) -> str:
        """Compile this expression to native FIELD child references."""
        indices = {name: index for index, name in enumerate(self.names)}
        try:
            return _ExpressionCompiler(indices).compile(self.node)
        except RecursionError as error:
            raise const.DXFValueError("field expression is too complex") from error

    def evaluate(self, sources: Mapping[str, _ResolvedSource]) -> Decimal:
        """Evaluate cached arithmetic without executing arbitrary code."""
        try:
            return _ExpressionEvaluator(sources).evaluate(self.node)
        except (DecimalException, RecursionError) as error:
            raise const.DXFValueError(
                "field expression is outside the supported numeric range"
            ) from error


class _ExpressionValidator:
    _OPERATORS = (ast.Add, ast.Sub, ast.Mult, ast.Div)
    _UNARY_OPERATORS = (ast.UAdd, ast.USub)

    def __init__(self) -> None:
        self._names: list[str] = []

    def validate(self, node: ast.expr) -> tuple[str, ...]:
        """Validate `node` and return names in first-use order."""
        self._visit(node)
        if not self._names:
            raise const.DXFValueError("field expression requires a named value")
        return tuple(self._names)

    def _visit(self, node: ast.expr) -> None:
        if isinstance(node, ast.Name):
            self._append_name(node.id)
        elif isinstance(node, ast.Constant):
            self._validate_constant(node.value)
        elif isinstance(node, ast.BinOp) and isinstance(node.op, self._OPERATORS):
            self._visit(node.left)
            self._visit(node.right)
        elif isinstance(node, ast.UnaryOp) and isinstance(
            node.op, self._UNARY_OPERATORS
        ):
            self._visit(node.operand)
        else:
            raise const.DXFValueError(
                f"unsupported field expression element: {type(node).__name__}"
            )

    def _append_name(self, name: str) -> None:
        if name not in self._names:
            self._names.append(name)

    @staticmethod
    def _validate_constant(value: object) -> None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise const.DXFValueError("field expressions require numeric literals")
        if not Decimal(str(value)).is_finite():
            raise const.DXFValueError("field expression literals must be finite")


class _ExpressionCompiler:
    def __init__(self, indices: Mapping[str, int]) -> None:
        self._indices = indices

    def compile(self, node: ast.expr) -> str:
        """Compile a validated expression node to native FIELD syntax."""
        if isinstance(node, ast.Name):
            return f"%<\\_FldIdx {self._indices[node.id]}>%"
        if isinstance(node, ast.Constant):
            return str(node.value)
        if isinstance(node, ast.UnaryOp):
            return f"({self._unary_symbol(node.op)}{self.compile(node.operand)})"
        if isinstance(node, ast.BinOp):
            left = self.compile(node.left)
            right = self.compile(node.right)
            return f"({left}{self._binary_symbol(node.op)}{right})"
        raise AssertionError("expression was not validated")

    @staticmethod
    def _binary_symbol(operator: ast.operator) -> str:
        return {
            ast.Add: "+",
            ast.Sub: "-",
            ast.Mult: "*",
            ast.Div: "/",
        }[type(operator)]

    @staticmethod
    def _unary_symbol(operator: ast.unaryop) -> str:
        return {ast.UAdd: "+", ast.USub: "-"}[type(operator)]


class _ExpressionEvaluator:
    def __init__(self, sources: Mapping[str, _ResolvedSource]) -> None:
        self._sources = sources

    def evaluate(self, node: ast.expr) -> Decimal:
        """Evaluate a validated expression node as a decimal number."""
        if isinstance(node, ast.Name):
            return self._source_value(node.id)
        if isinstance(node, ast.Constant):
            return Decimal(str(node.value))
        if isinstance(node, ast.UnaryOp):
            value = self.evaluate(node.operand)
            return value if isinstance(node.op, ast.UAdd) else -value
        if isinstance(node, ast.BinOp):
            return self._evaluate_binary(node)
        raise AssertionError("expression was not validated")

    def _source_value(self, name: str) -> Decimal:
        value = self._sources[name].numeric_value
        if value is None:
            raise const.DXFValueError(
                f"field value {name!r} is not numeric"
            )
        return value

    def _evaluate_binary(self, node: ast.BinOp) -> Decimal:
        left = self.evaluate(node.left)
        right = self.evaluate(node.right)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if right == 0:
            raise const.DXFValueError("field expression divides by zero")
        return left / right


class _ResolvedSource(ABC):
    @property
    @abstractmethod
    def display(self) -> str:
        """Return the cached display value."""

    @property
    @abstractmethod
    def numeric_value(self) -> Decimal | None:
        """Return the numeric value used by calculations."""

    @abstractmethod
    def new_field(self) -> Field:
        """Create a detached FIELD object."""


@dataclass(frozen=True)
class _DrawingPropertySource(_ResolvedSource):
    name: str
    value: FieldScalar
    cached_display: str
    field_format: str

    @property
    def display(self) -> str:
        return self.cached_display

    @property
    def numeric_value(self) -> Decimal | None:
        return _as_decimal(self.value)

    def new_field(self) -> Field:
        field = Field()
        field.set_dwgprops(
            self.name,
            field_format=self.field_format,
            value=str(self.value),
            display=self.cached_display,
        )
        return field


@dataclass(frozen=True)
class _DrawingVariableSource(_ResolvedSource):
    name: str
    value: FieldScalar | None
    cached_display: str

    @property
    def display(self) -> str:
        return self.cached_display

    @property
    def numeric_value(self) -> Decimal | None:
        return _as_decimal(self.value)

    def new_field(self) -> Field:
        field = Field()
        field.set_acvar(
            self.name,
            value="" if self.value is None else str(self.value),
            display=self.cached_display,
        )
        return field


@dataclass(frozen=True)
class _ObjectPropertySource(_ResolvedSource):
    target: DXFEntity
    property_name: str
    field_format: str
    value: FieldScalar | None
    cached_display: str
    normalize_cache: bool

    @property
    def display(self) -> str:
        return self.cached_display

    @property
    def numeric_value(self) -> Decimal | None:
        return _as_decimal(self.value)

    def new_field(self) -> Field:
        field = Field()
        field.set_acobjprop(
            self.target,
            self.property_name,
            field_format=self.field_format,
            value=self.value,
            display=self.cached_display,
        )
        if self.normalize_cache:
            field.normalize_acobjprop_cache()
        return field


class _SourceResolver:
    def __init__(
        self,
        host: _FieldTemplateHost,
        values: Mapping[str, FieldTemplateValue],
    ) -> None:
        self._host = host
        doc = host.doc
        if doc is None:
            raise const.DXFStructureError("valid DXF document required")
        self._doc = doc
        self._normalize_object_cache = host.dxftype() == "MULTILEADER"
        self._values = dict(values)
        self._sources: dict[str, _ResolvedSource] = {}
        self._updates: dict[str, str] = {}

    def resolve(self, name: str) -> _ResolvedSource:
        """Resolve one template name to a reusable field source."""
        source = self._sources.get(name)
        if source is None:
            source = self._resolve_new_source(name)
            self._sources[name] = source
        return source

    @property
    def property_updates(self) -> tuple[tuple[str, str], ...]:
        """Return validated custom-property updates."""
        return tuple(self._updates.items())

    def validate_all_values_used(self) -> None:
        """Reject supplied values not referenced by the template."""
        unused = set(self._values).difference(self._sources)
        if unused:
            names = ", ".join(sorted(unused))
            raise const.DXFValueError(f"unused field values: {names}")

    def _resolve_new_source(self, name: str) -> _ResolvedSource:
        if name not in self._values:
            return self._existing_property(name)
        value = self._values[name]
        if isinstance(value, DrawingProperty):
            return self._drawing_property(value)
        if isinstance(value, DrawingVariable):
            return self._drawing_variable(value)
        if isinstance(value, ObjectProperty):
            return self._object_property(value)
        return self._drawing_property(DrawingProperty(name, _scalar(value)))

    def _existing_property(self, name: str) -> _ResolvedSource:
        self._require_drawing_property_version()
        custom_vars = self._doc.header.custom_vars
        if not custom_vars.has_tag(name):
            raise const.DXFValueError(f"missing field value: {name}")
        value = custom_vars.get(name)
        assert value is not None
        scalar = _scalar(value)
        return _DrawingPropertySource(name, scalar, value, "")

    def _drawing_property(
        self, source: DrawingProperty
    ) -> _DrawingPropertySource:
        self._require_drawing_property_version()
        name = _require_name(source.name, "drawing property")
        field_format = _dxf_string(source.field_format, "field format")
        value = source.value
        if value is None:
            return self._existing_property_with_name(
                name, source, field_format
            )
        value = _scalar(value)
        self._record_update(name, str(value))
        display = _display_text(source.display, value)
        return _DrawingPropertySource(name, value, display, field_format)

    def _existing_property_with_name(
        self, name: str, source: DrawingProperty, field_format: str
    ) -> _DrawingPropertySource:
        custom_vars = self._doc.header.custom_vars
        if not custom_vars.has_tag(name):
            raise const.DXFValueError(f"missing drawing property: {name}")
        value = custom_vars.get(name)
        assert value is not None
        scalar = _scalar(value)
        display = _display_text(source.display, scalar)
        return _DrawingPropertySource(name, scalar, display, field_format)

    def _drawing_variable(
        self, source: DrawingVariable
    ) -> _DrawingVariableSource:
        name = _require_name(source.name, "drawing variable")
        value = None if source.value is None else _scalar(source.value)
        display = _display_text(source.display, value)
        return _DrawingVariableSource(name, value, display)

    def _object_property(self, source: ObjectProperty) -> _ObjectPropertySource:
        target = source.target
        self._validate_target(target)
        name = _require_name(source.property_name, "object property")
        field_format = _dxf_string(source.field_format, "field format")
        value: object | None = source.value
        if value is None:
            value = self._host._infer_object_property_value(target, name)
        scalar = None if value is None else _scalar(value)
        display = self._object_display(source, scalar, field_format)
        return _ObjectPropertySource(
            target,
            name,
            field_format,
            scalar,
            display,
            self._normalize_object_cache,
        )

    def _object_display(
        self,
        source: ObjectProperty,
        value: FieldScalar | None,
        field_format: str,
    ) -> str:
        if source.display is not None:
            return _dxf_string(source.display, "field display")
        if value is None:
            return ""
        return _dxf_string(
            self._host._format_object_property_value(value, field_format),
            "field display",
        )

    def _require_drawing_property_version(self) -> None:
        if self._doc.dxfversion < const.DXF2004:
            raise const.DXFVersionError(
                "drawing-property fields require DXF R2004 or later"
            )

    def _validate_target(self, target: DXFEntity) -> None:
        handle = target.dxf.handle
        if (
            target.doc is not self._doc
            or handle is None
            or self._doc.entitydb.get(handle) is not target
        ):
            raise const.DXFStructureError(
                "object property target requires a bound entity in this document"
            )

    def _record_update(self, name: str, value: str) -> None:
        previous = self._updates.get(name)
        if previous is not None and previous != value:
            raise const.DXFValueError(
                f"conflicting drawing property values: {name}"
            )
        self._updates[name] = value


@dataclass(frozen=True)
class _ParsedTemplate:
    segments: tuple[str | _Expression, ...]


class _FieldTemplateParser:
    _EXPRESSION = re.compile(r"{{(.*?)}}", re.DOTALL)

    def parse(self, template: str) -> _ParsedTemplate:
        """Parse a user-facing FIELD template."""
        if not isinstance(template, str):
            raise const.DXFTypeError("FIELD template must be a string")
        _dxf_string(template, "FIELD template")
        segments: list[str | _Expression] = []
        cursor = 0
        for match in self._EXPRESSION.finditer(template):
            self._append_text(segments, template[cursor : match.start()])
            segments.append(self._parse_expression(match.group(1)))
            cursor = match.end()
        self._append_text(segments, template[cursor:])
        if not any(isinstance(item, _Expression) for item in segments):
            raise const.DXFValueError("FIELD template requires {{name}}")
        return _ParsedTemplate(tuple(segments))

    @staticmethod
    def _append_text(segments: list[str | _Expression], text: str) -> None:
        if "{{" in text or "}}" in text:
            raise const.DXFValueError("malformed FIELD template braces")
        if text:
            segments.append(text)

    @staticmethod
    def _parse_expression(source: str) -> _Expression:
        source = source.strip()
        if not source:
            raise const.DXFValueError("empty FIELD template expression")
        return _Expression.parse(source)


@dataclass(frozen=True)
class _CompiledTemplate:
    field_code: str
    text: str
    child_fields: tuple[Field, ...]
    property_updates: tuple[tuple[str, str], ...]


class _FieldTemplateCompiler:
    def __init__(
        self,
        host: _FieldTemplateHost,
        values: Mapping[str, FieldTemplateValue],
    ) -> None:
        self._resolver = _SourceResolver(host, values)
        self._include_eval_option = host.dxftype() != "MULTILEADER"

    def compile(self, template: str) -> _CompiledTemplate:
        """Compile a FIELD template without mutating a document."""
        parsed = _FieldTemplateParser().parse(template)
        code: list[str] = []
        text: list[str] = []
        fields: list[Field] = []
        indices: dict[str, int] = {}
        displays: dict[str, str] = {}
        for segment in parsed.segments:
            if isinstance(segment, str):
                code.append(segment)
                text.append(segment)
                continue
            index, display = self._compile_expression(
                segment, fields, indices, displays
            )
            code.append(f"%<\\_FldIdx {index}>%")
            text.append(display)
        self._resolver.validate_all_values_used()
        return _CompiledTemplate(
            "".join(code),
            "".join(text),
            tuple(fields),
            self._resolver.property_updates,
        )

    def _compile_expression(
        self,
        expression: _Expression,
        fields: list[Field],
        indices: dict[str, int],
        displays: dict[str, str],
    ) -> tuple[int, str]:
        if expression.key not in indices:
            field, display = self._new_expression_field(expression)
            indices[expression.key] = len(fields)
            displays[expression.key] = display
            fields.append(field)
        return indices[expression.key], displays[expression.key]

    def _new_expression_field(self, expression: _Expression) -> tuple[Field, str]:
        sources = {name: self._resolver.resolve(name) for name in expression.names}
        if expression.is_direct_reference:
            source = sources[expression.names[0]]
            return source.new_field(), source.display
        value = expression.evaluate(sources)
        cached_value = _finite_float(value)
        display = _decimal_text(value)
        children = [sources[name].new_field() for name in expression.names]
        field = Field._build_virtual_acexpr(
            expression.field_code(),
            children,
            value=cached_value,
            display=display,
            include_eval_option=self._include_eval_option,
        )
        return field, display


def attach_field_template(
    host: _FieldTemplateHost,
    template: str,
    *,
    key: str,
    values: Mapping[str, FieldTemplateValue] | None,
    register_field_list: bool,
) -> Field:
    """Compile and attach a user-facing FIELD template to `host`.

    :param host: Text-like entity that owns the resulting FIELD tree.
    :param template: User-facing template containing ``{{...}}`` expressions.
    :param key: Nested ``ACAD_FIELD`` dictionary key.
    :param values: Named template sources and drawing-property values.
    :param register_field_list: Register the complete tree globally.
    :return: Attached text-wrapper FIELD.
    """
    if host.doc is None:
        raise const.DXFStructureError("valid DXF document required")
    doc = host.doc
    key = _require_name(key, "FIELD dictionary key")
    if doc.dxfversion < const.DXF2000:
        raise const.DXFVersionError(
            "FIELD templates require DXF R2000 or later"
        )
    supplied_values = _require_values(values)
    compiled = _FieldTemplateCompiler(host, supplied_values).compile(template)
    wrapper = host.set_linked_fields(
        compiled.child_fields,
        key=key,
        field_code=compiled.field_code,
        text=compiled.text,
        register_field_list=register_field_list,
    )
    custom_vars = doc.header.custom_vars
    for name, value in compiled.property_updates:
        custom_vars.set(name, value)
    return wrapper


def _require_values(
    values: Mapping[str, FieldTemplateValue] | None,
) -> Mapping[str, FieldTemplateValue]:
    if values is None:
        return {}
    if not isinstance(values, Mapping):
        raise const.DXFTypeError("FIELD template values must be a mapping")
    if any(not isinstance(name, str) for name in values):
        raise const.DXFTypeError("FIELD template value names must be strings")
    return values


def _require_name(name: str, label: str) -> str:
    if not isinstance(name, str) or not name.strip():
        raise const.DXFValueError(f"{label} name cannot be empty")
    return _dxf_string(name, f"{label} name")


def _scalar(value: object) -> FieldScalar:
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise const.DXFTypeError(
            f"unsupported FIELD template value: {type(value).__name__}"
        )
    if isinstance(value, float) and not Decimal(str(value)).is_finite():
        raise const.DXFValueError("FIELD template value must be finite")
    if isinstance(value, Decimal) and not value.is_finite():
        raise const.DXFValueError("FIELD template value must be finite")
    if isinstance(value, str):
        return _dxf_string(value, "FIELD template value")
    return value


def _as_decimal(value: FieldScalar | None) -> Decimal | None:
    if value is None:
        return None
    try:
        number = Decimal(str(value).strip())
    except InvalidOperation:
        return None
    return number if number.is_finite() else None


def _decimal_text(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _finite_float(value: Decimal) -> float:
    try:
        result = float(value)
    except (OverflowError, ValueError) as error:
        raise const.DXFValueError(
            "field expression is outside the supported numeric range"
        ) from error
    if not math.isfinite(result) or (result == 0.0 and value != 0):
        raise const.DXFValueError(
            "field expression is outside the supported numeric range"
        )
    return result


def _display_text(display: str | None, value: FieldScalar | None) -> str:
    if display is not None:
        return _dxf_string(display, "field display")
    return "" if value is None else str(value)


def _dxf_string(value: str, label: str) -> str:
    if "\r" in value or "\n" in value:
        raise const.DXFValueError(f"{label} cannot contain line breaks")
    return value

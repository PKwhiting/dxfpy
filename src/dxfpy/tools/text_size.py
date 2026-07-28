# Copyright (c) 2021-2026, Manfred Moitzi
# License: MIT License
from __future__ import annotations
import math
from typing import Sequence, Optional, cast
from dataclasses import dataclass

from dxfpy.math import Matrix44, Vec2
from dxfpy.entities import Text, MText, get_font_name
from dxfpy.entities.copy import CopySettings, CopyStrategy
from dxfpy.fonts import fonts
from dxfpy.lldxf import const
from dxfpy.tools import text_layout as tl
from dxfpy.tools.text import MTextContext, MTextParser, TokenType
from dxfpy.render.abstract_mtext_renderer import (
    AbstractMTextRenderer,
    MIN_MTEXT_COLUMN_WIDTH,
)
from dxfpy.tools.text import estimate_mtext_extents, valid_text_height

__all__ = [
    "text_size",
    "mtext_size",
    "TextSize",
    "MTextSize",
    "MTextSingleLineFitOptions",
    "MTextSingleLineMeasurement",
    "MTextSingleLineFitter",
    "WordSizeDetector",
    # estimate_mtext_extents() belongs also to the topic of this module, users
    # may look here first
    "estimate_mtext_extents",
]


@dataclass(frozen=True)
class TextSize:
    width: float
    # The text entity has a fixed font:
    cap_height: float  # height of "X" without descender
    total_height: float  # including the descender


@dataclass(frozen=True)
class MTextSize:
    total_width: float
    total_height: float
    column_width: float
    gutter_width: float
    column_heights: Sequence[float]

    # Storing additional font metrics like "cap_height" makes no sense, because
    # the font metrics can be variable by using inline codes to vary the text
    # height or the width factor or even changing the used font at all.
    @property
    def column_count(self) -> int:
        return len(self.column_heights)


@dataclass(frozen=True)
class MTextSingleLineFitOptions:
    """Configuration for shrinking MTEXT to one rendered line.

    The defaults are starting values that should be calibrated against the
    fonts and content used by an application.
    """

    maximum_iterations: int = 24
    minimum_character_height: float = 0.01
    character_height_tolerance_factor: float = 0.02

    def __post_init__(self) -> None:
        """Validate and normalize fitting options."""
        self._validate_iteration_count()
        minimum = self._finite_number(
            "minimum_character_height", self.minimum_character_height
        )
        tolerance = self._finite_number(
            "character_height_tolerance_factor",
            self.character_height_tolerance_factor,
        )
        if minimum <= 0.0:
            raise ValueError("minimum_character_height must be greater than zero")
        if tolerance < 0.0:
            raise ValueError(
                "character_height_tolerance_factor cannot be negative"
            )
        object.__setattr__(self, "minimum_character_height", minimum)
        object.__setattr__(
            self, "character_height_tolerance_factor", tolerance
        )

    def _validate_iteration_count(self) -> None:
        """Require a positive integer binary-search iteration count."""
        if type(self.maximum_iterations) is not int:
            raise TypeError("maximum_iterations must be an int")
        if self.maximum_iterations <= 0:
            raise ValueError("maximum_iterations must be greater than zero")

    @staticmethod
    def _finite_number(name: str, value: object) -> float:
        """Return `value` as a finite float."""
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"{name} must be a number")
        number = float(value)
        if not math.isfinite(number):
            raise ValueError(f"{name} must be finite")
        return number


@dataclass(frozen=True)
class MTextSingleLineMeasurement:
    """Rendered line and width measurements for one MTEXT character height."""

    character_height: float
    line_count: int
    content_width: float
    available_width: float
    tolerance: float

    @property
    def fits(self) -> bool:
        """Return whether the measured content fits one rendered line."""
        if self.line_count == 0:
            return True
        return self.line_count == 1 and (
            self.content_width <= self.available_width + self.tolerance
        )


class MTextSingleLineFitter:
    """Shrink MTEXT character height until visible content fits one line."""

    def __init__(
        self, options: Optional[MTextSingleLineFitOptions] = None
    ) -> None:
        """Initialize the fitter.

        :param options: Validated fitting options or starting defaults.
        """
        if options is not None and not isinstance(
            options, MTextSingleLineFitOptions
        ):
            raise TypeError("MTextSingleLineFitOptions required")
        self.options = (
            options if options is not None else MTextSingleLineFitOptions()
        )

    def fit(self, entity: MText) -> float:
        """Shrink `entity` in place and return its final character height.

        The method never enlarges text. Unbounded or already fitting MTEXT is
        unchanged. Content that cannot become one line, such as text with an
        explicit line break, stops at the configured minimum character height.

        :param entity: MTEXT entity to fit.
        :return: Final character height.
        """
        self._require_mtext(entity)
        original = self._measurement_height(entity, None)
        if not self._has_bounded_width(entity):
            return original
        detector = MTextSizeDetector()
        if self._measure(entity, original, detector).fits:
            return original
        final = self._largest_fitting_height(entity, original, detector)
        entity.dxf.char_height = final
        return final

    def measure(
        self, entity: MText, character_height: Optional[float] = None
    ) -> MTextSingleLineMeasurement:
        """Measure line count and width acceptance at one character height.

        :param entity: MTEXT entity to inspect without modifying it.
        :param character_height: Optional candidate height; the current height
            is used when omitted.
        :return: Structured fit measurement.
        """
        self._require_mtext(entity)
        height = self._measurement_height(entity, character_height)
        if not self._has_bounded_width(entity):
            return self._unbounded_measurement(entity, height)
        return self._measure(entity, height, MTextSizeDetector())

    def _unbounded_measurement(
        self, entity: MText, character_height: float
    ) -> MTextSingleLineMeasurement:
        """Return explicit unrestricted-width measurement semantics."""
        return MTextSingleLineMeasurement(
            character_height=character_height,
            line_count=self._logical_line_count(entity),
            content_width=0.0,
            available_width=math.inf,
            tolerance=(
                character_height
                * self.options.character_height_tolerance_factor
            ),
        )

    def _measure(
        self,
        entity: MText,
        character_height: float,
        detector: MTextSizeDetector,
    ) -> MTextSingleLineMeasurement:
        """Return one measurement using the operation-scoped detector."""
        widths = self._rendered_line_widths(entity, character_height, detector)
        content_width, available_width = max(
            widths,
            key=lambda pair: pair[0] - pair[1],
            default=(0.0, self._column_width(entity)),
        )
        return MTextSingleLineMeasurement(
            character_height=character_height,
            line_count=len(widths),
            content_width=content_width,
            available_width=available_width,
            tolerance=(
                character_height
                * self.options.character_height_tolerance_factor
            ),
        )

    def _largest_fitting_height(
        self, entity: MText, original: float, detector: MTextSizeDetector
    ) -> float:
        """Return the largest fitting height no greater than `original`."""
        lower = min(original, self.options.minimum_character_height)
        if not self._measure(entity, lower, detector).fits:
            return lower
        upper = original
        for _ in range(self.options.maximum_iterations):
            midpoint = (lower + upper) / 2.0
            if self._measure(entity, midpoint, detector).fits:
                lower = midpoint
            else:
                upper = midpoint
        return lower

    def _rendered_line_widths(
        self,
        entity: MText,
        character_height: float,
        detector: MTextSizeDetector,
    ) -> list[tuple[float, float]]:
        """Return paired content and available widths for rendered lines."""
        layout = detector.measure(
            self._measurement_copy(entity, character_height)
        )
        widths: list[tuple[float, float]] = []
        rendered_blank_lines = 0
        for column in layout:
            for paragraph in column:
                if isinstance(paragraph, tl.EmptyParagraph):
                    widths.append((0.0, paragraph.total_width))
                    rendered_blank_lines += 1
                else:
                    lines = list(paragraph)
                    if lines:
                        widths.extend(
                            (line.total_width, line.line_width)
                            for line in lines
                        )
        missing = self._logical_blank_line_count(entity) - rendered_blank_lines
        widths.extend(
            [(0.0, self._column_width(entity))] * max(missing, 0)
        )
        return widths

    @classmethod
    def _logical_line_count(cls, entity: MText) -> int:
        """Return the visible line count encoded across all MTEXT columns."""
        return len(cls._paragraph_distribution_states(entity))

    @classmethod
    def _logical_blank_line_count(cls, entity: MText) -> int:
        """Return blank lines omitted by normal line distribution."""
        return cls._paragraph_distribution_states(entity).count(False)

    @staticmethod
    def _paragraph_distribution_states(entity: MText) -> list[bool]:
        """Return whether each encoded paragraph creates a rendered line."""
        content = entity.all_columns_raw_content()
        if not content:
            return []
        states: list[bool] = []
        has_rendered_content = False
        for token in MTextParser(content):
            if token.type in (TokenType.NEW_PARAGRAPH, TokenType.NEW_COLUMN):
                states.append(has_rendered_content)
                has_rendered_content = False
            elif token.type in (TokenType.WORD, TokenType.STACK):
                has_rendered_content = True
        states.append(has_rendered_content)
        return states

    @staticmethod
    def _measurement_copy(entity: MText, character_height: float) -> MText:
        """Return a detached visible-text copy for measurement."""
        candidate = cast(MText, entity.copy(_MEASUREMENT_COPY_STRATEGY))
        candidate.text = entity.text
        candidate.dxf.char_height = character_height
        candidate.dxf.width = MTextSingleLineFitter._column_width(entity)
        return candidate

    @staticmethod
    def _measurement_height(
        entity: MText, character_height: Optional[float]
    ) -> float:
        """Return a valid explicit or current character height."""
        height = (
            MTextSingleLineFitter._character_height(entity)
            if character_height is None
            else MTextSingleLineFitOptions._finite_number(
                "character_height", character_height
            )
        )
        if not math.isfinite(height) or height <= 0.0:
            raise const.DXFValueError("character height must be finite and positive")
        return height

    @staticmethod
    def _column_width(entity: MText) -> float:
        """Return a valid non-negative wrapping width."""
        columns = entity.columns
        source_width = columns.width if columns else entity.dxf.get("width", 0.0)
        width = float(source_width or 0.0)
        if not math.isfinite(width) or width < 0.0:
            raise const.DXFValueError(
                "MTEXT column width must be finite and non-negative"
            )
        if columns and width < MIN_MTEXT_COLUMN_WIDTH:
            raise const.DXFValueError(
                "MTEXT column configuration width is too small to render"
            )
        return width

    @classmethod
    def _has_bounded_width(cls, entity: MText) -> bool:
        """Return whether the renderer treats the column width as bounded."""
        return cls._column_width(entity) >= MIN_MTEXT_COLUMN_WIDTH

    @staticmethod
    def _character_height(entity: MText) -> float:
        """Return the current character height."""
        return float(entity.dxf.get_default("char_height"))

    @staticmethod
    def _require_mtext(entity: MText) -> None:
        """Require an MTEXT entity."""
        if not isinstance(entity, MText):
            raise const.DXFTypeError("MTEXT entity required")


_MEASUREMENT_COPY_STRATEGY = CopyStrategy(
    CopySettings(
        copy_extension_dict=False,
        copy_xdata=False,
        copy_appdata=False,
        copy_proxy_graphic=False,
        set_source_of_copy=False,
    )
)


def text_size(text: Text) -> TextSize:
    """Returns the measured text width, the font cap-height and the font
    total-height for a :class:`~dxfpy.entities.Text` entity.
    This function uses the optional `Matplotlib` package if available to measure
    the final rendering width and font-height for the :class:`Text` entity as
    close as possible. This function does not measure the real char height!
    Without access to the `Matplotlib` package the
    :class:`~dxfpy.tools.fonts.MonospaceFont` is used and the measurements are
    very inaccurate.

    See the :mod:`~dxfpy.addons.text2path` add-on for more tools to work
    with the text path objects created by the `Matplotlib` package.

    """
    width_factor: float = text.dxf.get_default("width")
    text_width: float = 0.0
    cap_height: float = valid_text_height(text.dxf.get_default("height"))
    font: fonts.AbstractFont = fonts.MonospaceFont(cap_height, width_factor)
    if text.doc is not None:
        font_name = get_font_name(text)
        font = fonts.make_font(font_name, cap_height, width_factor)

    total_height = font.measurements.total_height
    content = text.plain_text()
    if content:
        text_width = font.text_width(content)
    return TextSize(text_width, cap_height, total_height)


def mtext_size(
    mtext: MText, tool: Optional[MTextSizeDetector] = None
) -> MTextSize:
    """Returns the total-width, -height and columns information for a
    :class:`~dxfpy.entities.MText` entity.

    This function uses the optional `Matplotlib` package if available to do
    font measurements and the internal text layout engine to determine the final
    rendering size for the :class:`MText` entity as close as possible.
    Without access to the `Matplotlib` package the :class:`~dxfpy.tools.fonts.MonospaceFont`
    is used and the measurements are very inaccurate.

    Attention: The required full layout calculation is slow!

    The first call to this function with `Matplotlib` support is very slow,
    because `Matplotlib` lookup all available fonts on the system. To speedup
    the calculation and accepting inaccurate results you can disable the
    `Matplotlib` support manually::

        dxfpy.option.use_matplotlib = False

    """
    tool = tool or MTextSizeDetector()
    column_heights: list[float] = [0.0]
    gutter_width = 0.0
    column_width = 0.0
    if mtext.text:
        columns: list[tl.Column] = list(tool.measure(mtext))
        if len(columns):
            first_column = columns[0]
            # same values for all columns
            column_width = first_column.total_width
            gutter_width = first_column.gutter
            column_heights = [column.total_height for column in columns]

    count = len(column_heights)
    return MTextSize(
        total_width=column_width * count + gutter_width * (count - 1),
        total_height=max(column_heights),
        column_width=column_width,
        gutter_width=gutter_width,
        column_heights=tuple(column_heights),
    )


class MTextSizeDetector(AbstractMTextRenderer):
    def __init__(self):
        super().__init__()
        self.do_nothing = tl.DoNothingRenderer()
        self.renderer = self.do_nothing

    def reset(self):
        pass

    def word(self, text: str, ctx: MTextContext) -> tl.ContentCell:
        return tl.Text(
            # The first call to get_font() is very slow!
            width=self.get_font(ctx).text_width(text),
            height=ctx.cap_height,
            valign=tl.CellAlignment(ctx.align),
            renderer=self.renderer,
        )

    def fraction(self, data: tuple, ctx: MTextContext) -> tl.ContentCell:
        upr, lwr, type_ = data
        if type_:
            return tl.Fraction(
                top=self.word(upr, ctx),
                bottom=self.word(lwr, ctx),
                stacking=self.get_stacking(type_),
                renderer=self.renderer,
            )
        else:
            return self.word(upr, ctx)

    def get_font_face(self, mtext: MText) -> fonts.FontFace:
        return fonts.get_entity_font_face(mtext)

    def make_bg_renderer(self, mtext: MText) -> tl.ContentRenderer:
        return self.do_nothing

    def measure(self, mtext: MText) -> tl.Layout:
        self.reset()
        layout = self.layout_engine(mtext)
        layout.place()
        return layout


class WordSizeCollector(tl.DoNothingRenderer):
    """Collects word sizes as tuples of the lower left corner and the upper
    right corner as Vec2 objects, ignores lines.
    """

    def __init__(self) -> None:
        self.word_boxes: list[tuple[Vec2, Vec2]] = []

    def render(
        self,
        left: float,
        bottom: float,
        right: float,
        top: float,
        m: Optional[Matrix44] = None,
    ) -> None:
        self.word_boxes.append((Vec2(left, bottom), Vec2(right, top)))


class WordSizeDetector(MTextSizeDetector):
    def reset(self):
        self.renderer = WordSizeCollector()

    def measure(self, mtext: MText) -> tl.Layout:
        layout = super().measure(mtext)
        layout.render()
        return layout

    def word_boxes(self) -> list[tuple[Vec2, Vec2]]:
        return self.renderer.word_boxes

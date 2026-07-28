#  Copyright (c) 2021-2025, Manfred Moitzi
#  License: MIT License
import math

import pytest

import dxfpy
from dxfpy.entities import MText, Text
from dxfpy.entities.mtext import MTextColumns
from dxfpy.layouts import VirtualLayout
from dxfpy.tools.text_size import (
    MTextSingleLineFitOptions,
    MTextSingleLineFitter,
    text_size,
    mtext_size,
    estimate_mtext_extents,
)
from dxfpy.fields import drawing_property
from dxfpy.tools.text import (
    set_estimation_safety_factor,
    reset_estimation_safety_factor,
)
from dxfpy.tools.text_layout import leading


@pytest.fixture
def msp():
    yield VirtualLayout()


H3W1 = {"height": 3.0, "width": 1.0}
H2W2 = {"height": 2.0, "width": 2.0}


def test_text_size_of_an_empty_string(msp):
    """The text_size() function does not measure the actual height of a char,
    it always returns the font measurement cap-height for text height and
    cap-height + descender for the total text height.
    """
    text = msp.add_text("", dxfattribs=H3W1)
    size = text_size(text)
    assert size.width == 0.0
    assert size.cap_height == 3.0
    assert size.total_height > 3.3  # assuming the descender factor is > 0.1


def test_text_size_for_height_0():
    text = Text()
    # hack
    text.dxf.__dict__["height"] = 0
    text.dxf.width = 1
    text.dxf.text = "Test"
    size = text_size(text)
    # a text height of 0 should default to 2.5
    assert size.width == 10.0
    assert size.cap_height == 2.5
    assert size.total_height >= 2.5


def test_text_width_of_a_single_char(msp):
    """The "MonospaceFont" font has a char width of cap-height x width factor."""
    text = msp.add_text("X", dxfattribs=H3W1)
    size = text_size(text)
    assert size.width == 3.0, "char width should be equal to cap height"


@pytest.mark.parametrize("s", ["ABC", ".,!", "   "])
def test_text_width_of_a_string(msp, s):
    text = msp.add_text(s, dxfattribs=H3W1)
    size = text_size(text)
    assert size.width == len(s) * size.cap_height


@pytest.mark.parametrize("s", ["ABC", ".,!", "   "])
def test_text_width_of_a_string_for_width_factor_2(msp, s):
    text = msp.add_text(s, dxfattribs=H2W2)
    size = text_size(text)
    assert size.width == len(s) * size.cap_height * 2.0


@pytest.mark.parametrize(
    "s",
    [
        "ABC\n",  # remove line ending
        "ABC\r",  # remove line ending
        "AB^I",  # parse caret notation "^I" -> "\t" (tabulator)
        "AB%%d",  # parse special chars "%%d" -> "°"
    ],
)
def test_measurement_of_plain_text(msp, s):
    text = msp.add_text(s, dxfattribs=H3W1)
    size = text_size(text)
    assert size.width == 3.0 * size.cap_height


def test_support_for_text_size():
    test_string = "TestString"
    doc = dxfpy.new()
    doc.styles.add("OpenSans", font="OpenSans-Regular.ttf")
    text = doc.modelspace().add_text(
        test_string,
        dxfattribs={
            "style": "OpenSans",
            "height": 2.0,
        },
    )
    length = len(test_string)
    size = text_size(text)
    # Do not check exact measurements!
    assert length * 1.0 < size.width < length * 2.0
    assert 1.95 < size.cap_height < 2.05
    assert size.total_height > size.cap_height


def test_mtext_size_of_an_empty_string(msp):
    mtext = msp.add_mtext("", dxfattribs={"char_height": 1.0})
    size = mtext_size(mtext)
    assert size.total_width == 0.0
    assert size.total_height == 0.0
    assert size.column_width == 0.0
    assert size.gutter_width == 0.0
    assert size.column_count == 1
    assert size.column_heights == (0.0,)


def test_mtext_size_for_height_0():
    text = MText()
    # hack
    text.dxf.__dict__["char_height"] = 0
    text.dxf.text = "Test"
    text.dxf.width = 20  # reference column width
    size = mtext_size(text)
    # a char height of 0 should default to 2.5
    assert size.total_height >= 2.5
    assert size.total_width >= 10.0


def test_mtext_size_of_a_single_char(msp):
    set_estimation_safety_factor(1.0)
    # Matplotlib support disabled and using MonospaceFont()
    mtext = msp.add_mtext("X", dxfattribs={"char_height": 2.0})
    size = mtext_size(mtext)
    assert size.total_height == 2.0
    assert size.total_width == pytest.approx(1.8794373744139317)
    assert size.column_width == pytest.approx(1.8794373744139317)
    assert size.gutter_width == 0.0
    assert size.column_count == 1
    reset_estimation_safety_factor()


def test_mtext_size_of_a_string(msp):
    set_estimation_safety_factor(1.0)
    # Matplotlib support disabled and using MonospaceFont()
    mtext = msp.add_mtext("XXX", dxfattribs={"char_height": 2.0})
    size = mtext_size(mtext)
    assert size.total_height == 2.0
    assert size.total_width == pytest.approx(5.6383121232417945)
    assert size.column_width == size.total_width
    assert size.gutter_width == 0.0
    assert size.column_count == 1
    reset_estimation_safety_factor()


def test_estimate_mtext_extents(msp):
    set_estimation_safety_factor(1.0)
    # Matplotlib support disabled and using MonospaceFont()
    mtext = msp.add_mtext(
        "XXXXXXXXXXXX\nYYYY\nZ",  # 5 lines!
        dxfattribs={
            "char_height": 2.0,
            "width": 8.0,
        },
    )
    width, height = estimate_mtext_extents(mtext)
    assert height == pytest.approx(15.336)  # 5 lines!
    assert width == 8.0
    reset_estimation_safety_factor()


@pytest.mark.parametrize(
    "cap_height, expected", [(2.0, 6.703281982585398), (3.0, 10.054922973878098)]
)
def test_mtext_size_of_2_lines(cap_height, expected, msp):
    set_estimation_safety_factor(1.0)
    # Matplotlib support disabled and using MonospaceFont()
    mtext = msp.add_mtext(
        "XXX\nYYYY",
        dxfattribs={
            "char_height": cap_height,
            "line_spacing_factor": 1.0,
        },
    )
    size = mtext_size(mtext)
    expected_total_height = leading(cap_height, line_spacing=1.0) + cap_height
    assert size.total_height == pytest.approx(expected_total_height)
    assert size.total_width == pytest.approx(expected), "expected width of 2nd line"
    assert size.column_width == size.total_width
    reset_estimation_safety_factor()


def test_single_line_fitter_starting_defaults_are_explicit():
    options = MTextSingleLineFitOptions()

    assert options.maximum_iterations == 24
    assert options.minimum_character_height == 0.01
    assert options.character_height_tolerance_factor == 0.02


def test_single_line_fitter_reports_why_wrapped_text_is_rejected():
    entity = _mtext(
        "A LONG EQUIPMENT DESCRIPTION THAT MUST FIT", width=2.0
    )
    fitter = MTextSingleLineFitter()

    before = fitter.measure(entity)
    final_height = fitter.fit(entity)
    after = fitter.measure(entity)

    assert before.fits is False
    assert before.line_count > 1
    assert final_height < 0.5
    assert after.fits is True
    assert after.character_height == final_height


def test_single_line_fitter_handles_unbreakable_overflow():
    entity = _mtext("UNBREAKABLEEQUIPMENTDESCRIPTION", width=1.0)
    fitter = MTextSingleLineFitter()

    before = fitter.measure(entity)
    fitter.fit(entity)
    after = fitter.measure(entity)

    assert before.fits is False
    assert before.content_width > before.available_width + before.tolerance
    assert after.fits is True


def test_single_line_fitter_keeps_text_that_already_fits():
    entity = _mtext(r"NORMAL {\H2x;TALL} NORMAL", width=100.0)

    final_height = MTextSingleLineFitter().fit(entity)

    assert final_height == 0.5
    assert entity.dxf.char_height == 0.5


def test_single_line_fitter_keeps_unbounded_text():
    entity = _mtext(r"NORMAL {\H2x;TALL} NORMAL", width=0.0)
    fitter = MTextSingleLineFitter()

    final_height = fitter.fit(entity)
    measurement = fitter.measure(entity)

    assert final_height == 0.5
    assert entity.dxf.char_height == 0.5
    assert measurement.line_count == 1
    assert measurement.content_width == 0.0
    assert measurement.available_width == math.inf
    assert measurement.fits is True


def test_single_line_fitter_rejects_unbounded_explicit_break():
    entity = _mtext(r"FIRST\PSECOND", width=0.0)

    measurement = MTextSingleLineFitter().measure(entity)

    assert measurement.line_count == 2
    assert measurement.fits is False


def test_single_line_fitter_treats_renderer_cutoff_as_unbounded():
    entity = _mtext("UNBOUNDED TEXT", width=0.0000005)

    final_height = MTextSingleLineFitter().fit(entity)
    measurement = MTextSingleLineFitter().measure(entity)

    assert final_height == 0.5
    assert measurement.available_width == math.inf


@pytest.mark.parametrize("content", ["\N{NO-BREAK SPACE}", "\N{EM SPACE}"])
def test_single_line_fitter_counts_rendered_unicode_whitespace_once(content):
    entity = _mtext(content, width=2.0)
    fitter = MTextSingleLineFitter()

    final_height = fitter.fit(entity)
    measurement = fitter.measure(entity)

    assert final_height == 0.5
    assert measurement.line_count == 1
    assert measurement.fits is True


def test_single_line_fitter_preserves_blank_after_zero_width_glyph():
    entity = _mtext("\N{ZERO WIDTH SPACE}\\P", width=2.0)
    fitter = MTextSingleLineFitter()

    final_height = fitter.fit(entity)
    measurement = fitter.measure(entity)

    assert final_height == 0.01
    assert measurement.line_count == 2
    assert measurement.fits is False


@pytest.mark.parametrize("content", [r"\\P", r"\\~"])
def test_single_line_fitter_preserves_escaped_literal_commands(content):
    entity = _mtext(content, width=2.0)
    fitter = MTextSingleLineFitter()

    final_height = fitter.fit(entity)
    measurement = fitter.measure(entity)

    assert final_height == 0.5
    assert measurement.line_count == 1
    assert measurement.fits is True


def test_single_line_fitter_uses_floor_for_explicit_line_break():
    entity = _mtext(r"FIRST\PSECOND", width=2.0)
    fitter = MTextSingleLineFitter()

    final_height = fitter.fit(entity)

    assert final_height == 0.01
    assert fitter.measure(entity).fits is False


def test_single_line_fitter_applies_custom_starting_options():
    entity = _mtext(r"FIRST\PSECOND", width=2.0)
    fitter = MTextSingleLineFitter(
        MTextSingleLineFitOptions(
            maximum_iterations=8,
            minimum_character_height=0.05,
            character_height_tolerance_factor=0.1,
        )
    )

    final_height = fitter.fit(entity)
    measurement = fitter.measure(entity)

    assert final_height == 0.05
    assert measurement.tolerance == pytest.approx(0.005)


def test_single_line_fitter_preserves_hosted_field_tree(monkeypatch):
    doc = dxfpy.new("R2018")
    entity = doc.modelspace().add_mtext(
        "----", dxfattribs={"char_height": 0.5, "width": 2.0}
    )
    field = entity.set_field(
        "{{description}}",
        values={
            "description": drawing_property(
                "Description",
                value="A LONG EQUIPMENT DESCRIPTION",
                display="A LONG EQUIPMENT DESCRIPTION",
            )
        },
    )
    field_tree = tuple(field.get_field_tree())
    entitydb_handles = tuple(doc.entitydb)
    field_list = doc.objects.get_field_list()
    assert field_list is not None
    field_list_handles = tuple(field_list.handles)

    def reject_field_copy(*_args, **_kwargs):
        raise AssertionError("measurement must not copy hosted FIELD trees")

    monkeypatch.setattr(type(field), "copy_data", reject_field_copy)

    MTextSingleLineFitter().fit(entity)

    assert entity.get_field() is field
    assert field.is_alive
    assert tuple(field.get_field_tree()) == field_tree
    assert tuple(doc.entitydb) == entitydb_handles
    assert tuple(field_list.handles) == field_list_handles
    assert entity.dxf.char_height < 0.5


@pytest.mark.parametrize(
    ("content", "width", "expected"),
    [
        ("A LONG EQUIPMENT DESCRIPTION THAT MUST FIT", 2.0, 0.06455656409263613),
        ("UNBREAKABLEEQUIPMENTDESCRIPTION", 1.0, 0.04042657256126404),
        (r"FIRST\PSECOND", 2.0, 0.01),
        (r"NORMAL {\H2x;TALL} NORMAL", 2.0, 0.11479316949844359),
        (r"NORMAL {\H0.8;TALL} NORMAL", 2.0, 0.01),
    ],
)
def test_single_line_fitter_matches_compatibility_baselines(
    content, width, expected
):
    entity = _mtext(content, width=width)
    raw_content = entity.text

    final_height = MTextSingleLineFitter().fit(entity)

    assert final_height == pytest.approx(expected, rel=1e-10)
    assert entity.text == raw_content


@pytest.mark.parametrize(
    "content",
    [
        r"\PFIRST",
        r"FIRST\P\PSECOND",
        r" \PFIRST",
        r"FIRST\P ",
        r"FIRST\P",
        r"FIRST\P\~",
    ],
)
def test_single_line_fitter_handles_blank_paragraphs(content):
    entity = _mtext(content, width=2.0)
    fitter = MTextSingleLineFitter()

    final_height = fitter.fit(entity)
    measurement = fitter.measure(entity)

    assert final_height == 0.01
    assert measurement.line_count >= 2
    assert measurement.fits is False


def test_single_line_fitter_counts_trailing_blank_after_wrapped_text():
    entity = _mtext(r"LONG EQUIPMENT DESCRIPTION THAT WRAPS\P", width=2.0)
    fitter = MTextSingleLineFitter()

    final_height = fitter.fit(entity)
    measurement = fitter.measure(entity)

    assert final_height == 0.01
    assert measurement.line_count >= 2
    assert measurement.fits is False


def test_single_line_fitter_counts_linked_column_trailing_blank():
    doc = dxfpy.new("R2013")
    entity = doc.modelspace().add_mtext(
        "", dxfattribs={"char_height": 0.5, "width": 2.0}
    )
    columns = MTextColumns()
    columns.count = 2
    columns.width = 2.0
    columns.gutter_width = 0.25
    columns.defined_height = 10.0
    entity.setup_columns(columns, linked=True)
    columns.linked_columns[0].text = r"FIRST\P"
    fitter = MTextSingleLineFitter()

    final_height = fitter.fit(entity)
    measurement = fitter.measure(entity)

    assert final_height == 0.01
    assert measurement.line_count == 2
    assert measurement.fits is False


def test_single_line_fitter_joins_linked_column_content_before_counting():
    doc = dxfpy.new("R2013")
    entity = doc.modelspace().add_mtext(
        r"FIRST\P", dxfattribs={"char_height": 0.5, "width": 2.0}
    )
    columns = MTextColumns()
    columns.count = 2
    columns.width = 2.0
    columns.gutter_width = 0.25
    columns.defined_height = 10.0
    entity.setup_columns(columns, linked=True)
    columns.linked_columns[0].text = "SECOND"

    measurement = MTextSingleLineFitter().measure(entity)

    assert measurement.line_count == 2


def test_single_line_fitter_ignores_blank_linked_storage_fragment():
    doc = dxfpy.new("R2013")
    entity = doc.modelspace().add_mtext(
        "FIRST", dxfattribs={"char_height": 0.5, "width": 2.0}
    )
    columns = MTextColumns()
    columns.count = 2
    columns.width = 2.0
    columns.gutter_width = 0.25
    columns.defined_height = 10.0
    entity.setup_columns(columns, linked=True)
    columns.linked_columns[0].text = " "

    measurement = MTextSingleLineFitter().measure(entity)

    assert measurement.line_count == 1
    assert measurement.fits is True


def test_single_line_fitter_uses_column_configuration_width():
    doc = dxfpy.new("R2018")
    entity = doc.modelspace().add_mtext(
        "A LONG EQUIPMENT DESCRIPTION THAT MUST FIT",
        dxfattribs={"char_height": 0.5, "width": 2.0},
    )
    columns = MTextColumns()
    columns.count = 1
    columns.width = 2.0
    columns.defined_height = 10.0
    entity.setup_columns(columns)
    entity.dxf.width = 0.0

    final_height = MTextSingleLineFitter().fit(entity)

    assert final_height < 0.5


@pytest.mark.parametrize("column_width", [math.inf, 0.0, 0.0000005])
def test_single_line_fitter_rejects_invalid_column_configuration_width(
    column_width,
):
    doc = dxfpy.new("R2018")
    entity = doc.modelspace().add_mtext(
        "TEXT", dxfattribs={"char_height": 0.5, "width": 2.0}
    )
    columns = MTextColumns()
    columns.count = 1
    columns.width = 2.0
    columns.defined_height = 10.0
    entity.setup_columns(columns)
    columns.width = column_width

    with pytest.raises(dxfpy.DXFValueError):
        MTextSingleLineFitter().measure(entity)


def test_single_line_fitter_skips_undistributed_overflow_paragraph():
    doc = dxfpy.new("R2018")
    entity = doc.modelspace().add_mtext(
        r"FIRST\PSECOND",
        dxfattribs={"char_height": 0.5, "width": 2.0},
    )
    columns = MTextColumns()
    columns.count = 2
    columns.width = 2.0
    columns.gutter_width = 0.25
    columns.defined_height = 0.5
    entity.setup_columns(columns)

    measurement = MTextSingleLineFitter().measure(entity)

    assert measurement.line_count == 2


def test_single_line_fitter_uses_render_only_copy_for_linked_columns():
    doc = dxfpy.new("R2013")
    entity = doc.modelspace().add_mtext(
        "LINKED COLUMN TEXT",
        dxfattribs={"char_height": 0.5, "width": 2.0},
    )
    columns = MTextColumns()
    columns.count = 2
    columns.width = 2.0
    columns.gutter_width = 0.25
    columns.defined_height = 10.0
    entity.setup_columns(columns, linked=True)
    linked_column = columns.linked_columns[0]

    class UncopyableExtensionDictionary:
        is_alive = True

        def copy(self, _copy_strategy):
            raise AssertionError("linked extension data must not be copied")

    linked_column.extension_dict = UncopyableExtensionDictionary()  # type: ignore[assignment]

    measurement = MTextSingleLineFitter().measure(entity)

    assert measurement.line_count >= 1
    assert columns.linked_columns[0] is linked_column


def test_single_line_measurement_reports_worst_paired_overflow_widths():
    fitter = MTextSingleLineFitter()
    entity = _mtext(
        r"\pxi2,l0,r0;AAAA\P\pxi0,l0,r0;BBBBBB", width=5.0
    )

    measurement = fitter.measure(entity)
    indented_line = fitter.measure(
        _mtext(r"\pxi2,l0,r0;AAAA", width=5.0)
    )
    wider_line = fitter.measure(_mtext("BBBBBB", width=5.0))

    assert measurement.line_count == 2
    assert measurement.content_width == indented_line.content_width
    assert measurement.available_width == indented_line.available_width
    assert wider_line.content_width > measurement.content_width
    assert wider_line.available_width > measurement.available_width


@pytest.mark.parametrize(
    "options",
    [
        {"maximum_iterations": 0},
        {"minimum_character_height": 0.0},
        {"character_height_tolerance_factor": -0.01},
    ],
)
def test_single_line_fitter_rejects_invalid_options(options):
    with pytest.raises(ValueError):
        MTextSingleLineFitOptions(**options)


def test_single_line_fitter_requires_typed_options_and_measurement_height():
    entity = _mtext("TEXT", width=2.0)
    with pytest.raises(TypeError):
        MTextSingleLineFitter(False)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        MTextSingleLineFitter().measure(entity, True)  # type: ignore[arg-type]


@pytest.mark.parametrize("width", [math.nan, math.inf, -math.inf, -1.0])
def test_single_line_fitter_rejects_invalid_column_width(width):
    entity = _mtext("TEXT", width=width)
    fitter = MTextSingleLineFitter()

    with pytest.raises(dxfpy.DXFValueError):
        fitter.measure(entity)
    with pytest.raises(dxfpy.DXFValueError):
        fitter.fit(entity)


def _mtext(content: str, *, width: float) -> MText:
    doc = dxfpy.new("R2018")
    return doc.modelspace().add_mtext(
        content,
        dxfattribs={"char_height": 0.5, "width": width},
    )


if __name__ == "__main__":
    pytest.main([__file__])

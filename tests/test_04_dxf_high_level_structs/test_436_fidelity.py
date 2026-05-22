from io import StringIO

import ezdxf
from ezdxf.dynblkhelper import (
    restore_dictionary_key_order,
    snapshot_object_handle_order,
    snapshot_raw_extension_subtree,
)
from ezdxf.fidelity import finalize_document_fidelity, prepare_document_fidelity
from ezdxf.lldxf.tagwriter import TagWriter
from ezdxf.lldxf.types import is_pointer_code
from ezdxf.sections.classes import snapshot_raw_classes
from ezdxf.sections.header import snapshot_raw_header_vars


def _normalize_handle_refs_in_text(text: str) -> str:
    lines = text.replace("\r\n", "\n").split("\n")
    normalized: list[str] = []
    index = 0
    while index < len(lines):
        code_line = lines[index]
        normalized.append(code_line)
        if index + 1 >= len(lines):
            break
        value_line = lines[index + 1]
        try:
            code = int(code_line.strip())
        except ValueError:
            normalized.append(value_line)
            index += 2
            continue
        if code in (5, 105, 1005) or is_pointer_code(code):
            normalized.append("<REF>")
        else:
            normalized.append(value_line)
        index += 2
    return "\n".join(normalized)


def _export_text(entity, dxfversion: str) -> str:
    stream = StringIO()
    entity.export_dxf(TagWriter(stream, dxfversion=dxfversion))
    return stream.getvalue()


def test_prepare_document_fidelity_restores_rootdict_entries_and_order():
    source_doc = ezdxf.new("R2018")
    source_doc.rootdict.get_required_dict("ZZZ_CUSTOM")
    source_doc.rootdict.get_required_dict("AAA_CUSTOM")
    restore_dictionary_key_order(
        source_doc.rootdict,
        ("AAA_CUSTOM", "ZZZ_CUSTOM", *tuple(source_doc.rootdict.keys())),
    )
    source_order = tuple(source_doc.rootdict.keys())

    target_doc = ezdxf.new("R2018")
    prepare_document_fidelity(source_doc, target_doc)

    assert tuple(target_doc.rootdict.keys()) == source_order
    assert target_doc.rootdict.get("AAA_CUSTOM").dxftype() == "DICTIONARY"
    assert target_doc.rootdict.get("ZZZ_CUSTOM").dxftype() == "DICTIONARY"


def test_prepare_document_fidelity_restores_layer_extension_subtrees_with_external_handle_remap():
    source_doc = ezdxf.new("R2018")
    ref_layer = source_doc.layers.new("U-MISC")
    annotated_layer = source_doc.layers.new("U-MISC @ 1")
    material = source_doc.materials.get("Global")
    assert source_doc.entitydb.reset_handle(ref_layer, "1A2C") is True
    assert source_doc.entitydb.reset_handle(material, "1A2D") is True
    xdict = annotated_layer.new_extension_dict().dictionary
    xrecord = xdict.add_xrecord("ASDK_XREC_ANNO_SCALE_INFO")
    xrecord.set_reactors([xdict.dxf.handle])
    xrecord.reset(
        [
            (70, 1),
            (340, material.dxf.handle),
            (340, ref_layer.dxf.handle),
            (70, -1),
        ]
    )

    target_doc = ezdxf.new("R2018")
    target_doc.layers.new("U-MISC")
    target_doc.layers.new("U-MISC @ 1")
    prepare_document_fidelity(source_doc, target_doc)

    replayed_layer = target_doc.layers.get("U-MISC @ 1")
    replayed_ref = target_doc.layers.get("U-MISC")
    replayed_material = target_doc.materials.get("Global")
    snapshot = snapshot_raw_extension_subtree(replayed_layer)

    assert replayed_ref is not None
    assert replayed_material is not None
    assert [value for code, value in snapshot[1] if code == 340] == [
        replayed_material.dxf.handle,
        replayed_ref.dxf.handle,
    ]


def test_prepare_document_fidelity_restores_mleader_style_extension_subtrees():
    source_doc = ezdxf.new("R2018")
    source_layer = source_doc.layers.new("MLEADER_LAYER")
    style = source_doc.mleader_styles.new("TEST_STYLE")
    xdict = style.new_extension_dict().dictionary
    xrecord = xdict.add_xrecord("MLEADER_EXT")
    xrecord.set_reactors([xdict.dxf.handle])
    xrecord.reset([(340, source_layer.dxf.handle)])

    target_doc = ezdxf.new("R2018")
    target_doc.layers.new("MLEADER_LAYER")
    prepare_document_fidelity(source_doc, target_doc)

    replayed_style = target_doc.mleader_styles.get("TEST_STYLE")
    replayed_layer = target_doc.layers.get("MLEADER_LAYER")
    snapshot = snapshot_raw_extension_subtree(replayed_style)

    assert replayed_style is not None
    assert replayed_layer is not None
    assert [value for code, value in snapshot[1] if code == 340] == [
        replayed_layer.dxf.handle
    ]


def test_prepare_document_fidelity_restores_table_style_extension_subtrees():
    source_doc = ezdxf.new("R2018")
    source_layer = source_doc.layers.new("TABLE_LAYER")
    style = source_doc.table_styles.duplicate_entry("Standard", "TEST_TABLE_STYLE")
    xdict = style.new_extension_dict().dictionary
    xrecord = xdict.add_xrecord("TABLESTYLE_EXT")
    xrecord.set_reactors([xdict.dxf.handle])
    xrecord.reset([(340, source_layer.dxf.handle)])

    target_doc = ezdxf.new("R2018")
    target_doc.layers.new("TABLE_LAYER")
    prepare_document_fidelity(source_doc, target_doc)

    replayed_style = target_doc.table_styles.get("TEST_TABLE_STYLE")
    replayed_layer = target_doc.layers.get("TABLE_LAYER")
    snapshot = snapshot_raw_extension_subtree(replayed_style)

    assert replayed_style is not None
    assert replayed_layer is not None
    assert [value for code, value in snapshot[1] if code == 340] == [
        replayed_layer.dxf.handle
    ]


def test_finalize_document_fidelity_restores_dimstyle_raw_export():
    source_doc = ezdxf.new("R2010")
    source_doc.styles.new("DIM_TXT", dxfattribs={"font": "txt"})
    ltype = source_doc.linetypes.new("DIM_LT", dxfattribs={"description": "DIM_LT"})
    ltype.setup_pattern([0.2, 0.1, -0.1])
    arrow = source_doc.blocks.new("DIM_ARROW")
    arrow.add_line((0, 0), (1, 0))
    dimstyle = source_doc.dimstyles.new("TEST_DIMSTYLE")
    dimstyle.dxf.dimtxsty = "DIM_TXT"
    dimstyle.dxf.dimblk = "DIM_ARROW"
    dimstyle.dxf.dimldrblk = "DIM_ARROW"
    dimstyle.dxf.dimltype = "DIM_LT"
    dimstyle.dxf.dimltex1 = "DIM_LT"
    dimstyle.dxf.dimltex2 = "DIM_LT"
    dimstyle.set_xdata("ACAD_DSTYLE_DIMBREAK", [(1070, 391), (1040, 0.125)])

    target_doc = ezdxf.new("R2010")
    target_doc.styles.new("DIM_TXT", dxfattribs={"font": "txt"})
    target_ltype = target_doc.linetypes.new(
        "DIM_LT", dxfattribs={"description": "DIM_LT"}
    )
    target_ltype.setup_pattern([0.2, 0.1, -0.1])
    target_arrow = target_doc.blocks.new("DIM_ARROW")
    target_arrow.add_line((0, 0), (1, 0))
    prepare_document_fidelity(source_doc, target_doc)
    target_doc.dimstyles.new("TEST_DIMSTYLE")

    finalize_document_fidelity(source_doc, target_doc)
    replayed = target_doc.dimstyles.get("TEST_DIMSTYLE")

    assert replayed is not None
    assert _normalize_handle_refs_in_text(
        _export_text(replayed, target_doc.dxfversion)
    ) == _normalize_handle_refs_in_text(_export_text(dimstyle, source_doc.dxfversion))


def test_finalize_document_fidelity_copies_header_state_and_custom_vars():
    source_doc = ezdxf.new("R2010")
    source_doc.encoding = "cp1252"
    source_doc.header["$LASTSAVEDBY"] = "fidelity"
    source_doc.header["$LTSCALE"] = 2.5
    source_doc.header.custom_vars.append("CustomTag", "CustomValue")

    target_doc = ezdxf.new("R2010")
    prepare_document_fidelity(source_doc, target_doc)
    finalize_document_fidelity(source_doc, target_doc)

    assert target_doc.encoding == "cp1252"
    assert target_doc.header["$LASTSAVEDBY"] == "fidelity"
    assert target_doc.header["$LTSCALE"] == 2.5
    assert list(target_doc.header.custom_vars) == [("CustomTag", "CustomValue")]


def test_finalize_document_fidelity_restores_raw_header_overrides(tmp_path):
    source_doc = ezdxf.new("R2010")
    source_doc.header["$PEXTMIN"] = (1.0, 2.0, 3.0)
    source_doc.header["$PEXTMAX"] = (4.0, 5.0, 6.0)
    filename = tmp_path / "source_header_overrides.dxf"
    source_doc.saveas(filename)
    raw_snapshot = dict(snapshot_raw_header_vars(str(filename), ("$PEXTMIN", "$PEXTMAX")))

    target_doc = ezdxf.new("R2010")
    prepare_document_fidelity(source_doc, target_doc)
    finalize_document_fidelity(source_doc, target_doc)

    stream = StringIO()
    target_doc.header.export_dxf(TagWriter(stream))
    text = stream.getvalue()

    for name, body in raw_snapshot.items():
        assert f"{name}\n{body}" in text


def test_finalize_document_fidelity_restores_raw_classes():
    source_doc = ezdxf.new("R2010")
    source_doc.classes.add_class("WIPEOUT")
    source_doc.classes.add_class("MULTILEADER")
    snapshot = snapshot_raw_classes(source_doc.classes)

    target_doc = ezdxf.new("R2010")
    prepare_document_fidelity(source_doc, target_doc)
    finalize_document_fidelity(source_doc, target_doc)

    stream = StringIO()
    target_doc.classes.export_dxf(TagWriter(stream))
    assert stream.getvalue() == (
        "  0\nSECTION\n  2\nCLASSES\n" + "".join(snapshot) + "  0\nENDSEC\n"
    )


def test_finalize_document_fidelity_reorders_objects_by_source_order():
    source_doc = ezdxf.new("R2018")
    source_doc.rootdict.get_required_dict("ZZZ_CUSTOM")
    source_order = snapshot_object_handle_order(source_doc)

    target_doc = ezdxf.new("R2018")
    prepare_document_fidelity(source_doc, target_doc)
    target_doc.objects._entity_space.entities = list(reversed(list(target_doc.objects)))
    pre_finalize_order = snapshot_object_handle_order(target_doc)

    finalize_document_fidelity(source_doc, target_doc)

    mapping = getattr(target_doc, "_raw_object_handle_mapping")
    expected = []
    seen: set[str] = set()
    for source_handle in source_order:
        target_handle = mapping.get(str(source_handle), str(source_handle))
        if target_doc.entitydb.get(target_handle) is None or target_handle in seen:
            continue
        expected.append(target_handle)
        seen.add(target_handle)
    for entity in target_doc.objects:
        handle = entity.dxf.handle
        if handle and handle not in seen:
            expected.append(handle)
            seen.add(handle)

    assert pre_finalize_order != tuple(expected)
    assert snapshot_object_handle_order(target_doc) == tuple(expected)


def test_finalize_document_fidelity_restores_rootdict_xrecord_handles_after_entity_creation():
    source_doc = ezdxf.new("R2010")
    line = source_doc.modelspace().add_line((0, 0), (1, 0))
    xrecord = source_doc.objects.add_xrecord(owner=source_doc.rootdict.dxf.handle)
    xrecord.set_reactors([source_doc.rootdict.dxf.handle])
    xrecord.tags.extend([(90, 1), (330, line.dxf.handle)])
    source_doc.rootdict.add("TEST_REFS", xrecord)

    target_doc = ezdxf.new("R2010")
    prepare_document_fidelity(source_doc, target_doc)
    target_line = target_doc.modelspace().add_line((0, 0), (1, 0))
    finalize_document_fidelity(source_doc, target_doc)

    restored = target_doc.rootdict.get("TEST_REFS")
    text = _export_text(restored, target_doc.dxfversion)

    assert f"330\n{target_line.dxf.handle}\n" in text

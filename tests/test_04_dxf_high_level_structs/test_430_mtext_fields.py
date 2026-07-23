# Copyright (c) 2026, Manfred Moitzi
# License: MIT License
import io
import dxfpy
import pytest
from dxfpy.entities.dxfobj import Field


def test_add_mtext_acvar_field_creates_object_backed_field():
    doc = dxfpy.new("R2007")
    msp = doc.modelspace()

    mtext = msp.add_mtext_acvar_field(
        "Author",
        text="----",
        dxfattribs={"insert": (0, 0, 0)},
        register_field_list=True,
    )

    assert mtext.text == "----"
    primary = mtext.get_primary_field()
    assert primary is not None
    assert primary.evaluator_id == "AcVar"
    assert primary.field_code == "\\AcVar Author"

    field_list = doc.objects.get_field_list()
    assert field_list is not None
    assert mtext.get_field().dxf.handle in field_list.handles
    assert primary.dxf.handle in field_list.handles


def test_add_mtext_acobjprop_length_field_creates_object_backed_field():
    doc = dxfpy.new("R2007")
    msp = doc.modelspace()
    line = msp.add_line((0, 0), (10, 0))

    mtext = msp.add_mtext_acobjprop_field(
        line,
        "Length",
        dxfattribs={"insert": (0, 0, 0)},
        register_field_list=True,
    )

    assert mtext.text == "10.0000"
    primary = mtext.get_primary_field()
    assert primary is not None
    assert primary.evaluator_id == "AcObjProp"
    assert primary.object_handles == [line.dxf.handle]
    assert "Length" in primary.field_code


def test_add_mtext_acobjprop_area_field_for_closed_lwpolyline():
    doc = dxfpy.new("R2007")
    msp = doc.modelspace()
    pline = msp.add_lwpolyline(
        [(0, 0), (10, 0), (10, 10), (0, 10)], close=True
    )

    mtext = msp.add_mtext_acobjprop_field(
        pline,
        "Area",
        dxfattribs={"insert": (0, 0, 0)},
        register_field_list=True,
    )

    assert mtext.text == "100.0000"
    primary = mtext.get_primary_field()
    assert primary is not None
    assert primary.evaluator_id == "AcObjProp"
    assert "Area" in primary.field_code


def test_add_mtext_dwgprops_field_creates_object_backed_field():
    doc = dxfpy.new("R2007")
    msp = doc.modelspace()

    mtext = msp.add_mtext_dwgprops_field(
        "ProjectCode",
        text="VALUE-123",
        dxfattribs={"insert": (0, 0, 0)},
        register_field_list=True,
    )

    assert mtext.text == "VALUE-123"
    primary = mtext.get_primary_field()
    assert primary is not None
    assert primary.evaluator_id == "AcVar"
    assert primary.field_code == "\\AcVar CustomDP.ProjectCode"
    assert doc.header.custom_vars.get("ProjectCode") == "VALUE-123"


def test_mtext_set_linked_fields_attaches_multiple_custom_properties():
    doc = dxfpy.new("R2007")
    mtext = doc.modelspace().add_mtext("---- / ----")
    first = Field()
    first.set_dwgprops("ProjectCode", display="----")
    second = Field()
    second.set_dwgprops("Revision", display="----")

    wrapper = mtext.set_linked_fields(
        [first, second],
        field_code="%<\\_FldIdx 0>% / %<\\_FldIdx 1>%",
        register_field_list=True,
    )

    field_dict = mtext.get_field_dict()
    assert wrapper.child_handles == [first.dxf.handle, second.dxf.handle]
    assert wrapper.dxf.owner == field_dict.dxf.handle
    assert wrapper.get_reactors() == [field_dict.dxf.handle]
    assert first.dxf.owner == wrapper.dxf.handle
    assert second.dxf.owner == wrapper.dxf.handle
    field_list = doc.objects.get_field_list()
    assert field_list is not None
    assert all(field.dxf.handle in field_list.handles for field in wrapper.get_field_tree())

    stream = io.StringIO()
    doc.write(stream)
    stream.seek(0)
    reloaded = dxfpy.read(stream)
    reloaded_wrapper = reloaded.modelspace()[0].get_field()
    assert reloaded_wrapper is not None
    assert len(reloaded_wrapper.get_child_fields()) == 2


def test_mtext_set_linked_fields_validates_before_binding_children():
    doc = dxfpy.new("R2007")
    foreign_doc = dxfpy.new("R2007")
    mtext = doc.modelspace().add_mtext("---- / ----")
    virtual = Field()
    foreign = foreign_doc.objects.add_field(owner="0")

    with pytest.raises(dxfpy.DXFStructureError):
        mtext.set_linked_fields(
            [virtual, foreign],
            field_code="%<\\_FldIdx 0>% / %<\\_FldIdx 1>%",
        )

    assert virtual.doc is None
    assert mtext.get_field() is None


def test_mtext_set_linked_fields_rejects_already_owned_root():
    doc = dxfpy.new("R2007")
    source = doc.modelspace().add_mtext("SOURCE")
    child, source_wrapper = source.new_dwgprops_field("ProjectCode")
    target = doc.modelspace().add_mtext("TARGET")

    with pytest.raises(dxfpy.DXFStructureError, match="already owned"):
        target.set_linked_fields([child], field_code="%<\\_FldIdx 0>%")

    assert source.get_field() is source_wrapper
    assert source.get_primary_field() is child
    assert child.is_alive
    assert target.get_field() is None


def test_mtext_set_linked_fields_reuses_current_child():
    doc = dxfpy.new("R2007")
    mtext = doc.modelspace().add_mtext("SOURCE")
    child, original_wrapper = mtext.new_dwgprops_field("ProjectCode")

    replacement = mtext.set_linked_fields(
        [child], field_code="%<\\_FldIdx 0>%"
    )

    assert original_wrapper.is_alive is False
    assert child.is_alive
    assert child.dxf.owner == replacement.dxf.handle
    assert mtext.get_field() is replacement


def test_mtext_set_linked_fields_reuses_current_direct_field():
    doc = dxfpy.new("R2007")
    mtext = doc.modelspace().add_mtext("SOURCE")
    field = doc.objects.add_field(owner="0")
    field.set_dwgprops("ProjectCode")
    mtext.set_field(field)

    wrapper = mtext.set_linked_field(field)

    assert field.is_alive
    assert field.dxf.owner == wrapper.dxf.handle
    assert mtext.get_field() is wrapper


def test_mtext_set_linked_fields_rejects_virtual_root_with_handle():
    doc = dxfpy.new("R2007")
    existing = doc.modelspace().add_line((0, 0), (1, 0))
    field = Field.new(handle=existing.dxf.handle, owner="0", dxfattribs={})
    field.set_dwgprops("ProjectCode")
    mtext = doc.modelspace().add_mtext("TARGET")

    with pytest.raises(dxfpy.DXFStructureError, match="cannot have a handle"):
        mtext.set_linked_fields([field], field_code="%<\\_FldIdx 0>%")

    assert doc.entitydb.get(existing.dxf.handle) is existing
    assert field.doc is None
    assert mtext.get_field() is None


def test_mtext_set_linked_fields_rejects_invalid_descendant_owner():
    doc = dxfpy.new("R2007")
    child = doc.objects.add_field(owner="0")
    child.set_dwgprops("ProjectCode")
    expression = doc.objects.add_field(owner="0")
    expression.set_acexpr("%<\\_FldIdx 0>% * 2", [child])
    mtext = doc.modelspace().add_mtext("TARGET")

    with pytest.raises(dxfpy.DXFStructureError, match="invalid owner"):
        mtext.set_linked_fields(
            [expression], field_code="%<\\_FldIdx 0>%"
        )

    assert expression.is_alive
    assert child.is_alive
    assert mtext.get_field() is None


def test_mtext_set_linked_fields_rejects_duplicate_virtual_roots():
    doc = dxfpy.new("R2007")
    field = Field()
    field.set_dwgprops("ProjectCode")
    mtext = doc.modelspace().add_mtext("TARGET")

    with pytest.raises(dxfpy.DXFStructureError, match="duplicate or cycle"):
        mtext.set_linked_fields(
            [field, field],
            field_code="%<\\_FldIdx 0>% / %<\\_FldIdx 1>%",
        )

    assert field.doc is None
    assert mtext.get_field() is None


def test_mtext_set_linked_fields_validates_code_before_binding():
    doc = dxfpy.new("R2007")
    field = Field()
    field.set_dwgprops("ProjectCode")
    mtext = doc.modelspace().add_mtext("TARGET")

    with pytest.raises(dxfpy.DXFStructureError, match="out of range"):
        mtext.set_linked_fields([field], field_code="%<\\_FldIdx 1>%")

    assert field.doc is None
    assert mtext.get_field() is None


def test_mtext_set_linked_fields_validates_field_list_before_binding():
    doc = dxfpy.new("R2007")
    invalid_field_list = doc.objects.add_xrecord()
    doc.rootdict.add("ACAD_FIELDLIST", invalid_field_list)
    field = Field()
    field.set_dwgprops("ProjectCode")
    mtext = doc.modelspace().add_mtext("TARGET")

    with pytest.raises(dxfpy.DXFStructureError, match="FIELDLIST"):
        mtext.set_linked_fields(
            [field],
            field_code="%<\\_FldIdx 0>%",
            register_field_list=True,
        )

    assert field.doc is None
    assert mtext.get_field() is None


def test_mtext_replacement_preflights_invalid_field_list():
    doc = dxfpy.new("R2007")
    mtext = doc.modelspace().add_mtext("SOURCE")
    child, original_wrapper = mtext.new_dwgprops_field("ProjectCode")
    invalid_field_list = doc.objects.add_xrecord()
    doc.rootdict.add("ACAD_FIELDLIST", invalid_field_list)
    replacement = Field()
    replacement.set_dwgprops("Revision")

    with pytest.raises(dxfpy.DXFStructureError, match="FIELDLIST"):
        mtext.set_linked_field(replacement)

    assert mtext.get_field() is original_wrapper
    assert original_wrapper.is_alive
    assert child.is_alive
    assert replacement.doc is None


def test_mtext_reuse_rejects_stale_existing_child_reference():
    doc = dxfpy.new("R2007")
    source = doc.modelspace().add_mtext("SOURCE")
    _, source_wrapper = source.new_dwgprops_field("ProjectCode")
    target = doc.modelspace().add_mtext("TARGET")
    target_child, target_wrapper = target.new_dwgprops_field("Revision")
    source_wrapper.set_text_wrapper_fields(
        [target_child], field_code="%<\\_FldIdx 0>%"
    )

    with pytest.raises(dxfpy.DXFStructureError, match="invalid owner"):
        source.set_linked_field(target_child)

    assert target.get_field() is target_wrapper
    assert target_child.dxf.owner == target_wrapper.dxf.handle


def test_mtext_copy_rejects_foreign_owned_child_before_layout_mutation():
    doc = dxfpy.new("R2007")
    source = doc.modelspace().add_mtext("SOURCE")
    _, source_wrapper = source.new_dwgprops_field("ProjectCode")
    other = doc.modelspace().add_mtext("OTHER")
    other_child, other_wrapper = other.new_dwgprops_field("Revision")
    source_wrapper.set_text_wrapper_fields(
        [other_child], field_code="%<\\_FldIdx 0>%"
    )
    target = doc.layout("Layout1")

    with pytest.raises(dxfpy.DXFStructureError, match="invalid owner"):
        source.copy_to_layout(target)

    assert len(target) == 0
    assert other.get_field() is other_wrapper
    assert other_child.is_alive


def test_mtext_set_field_binds_same_document_virtual_field_tree():
    doc = dxfpy.new("R2007")
    source = doc.modelspace().add_mtext("SOURCE")
    source_child, source_wrapper = source.new_dwgprops_field(
        "ProjectCode", register_field_list=True
    )
    target = doc.modelspace().add_mtext("TARGET")
    virtual_wrapper = source_wrapper.copy()

    target.set_field(virtual_wrapper)

    target_child = target.get_primary_field()
    assert target_child is not None
    assert target_child is not source_child
    assert target_child.dxf.handle != source_child.dxf.handle
    assert target_child.dxf.owner == virtual_wrapper.dxf.handle
    assert virtual_wrapper.dxf.owner == target.get_field_dict().dxf.handle
    assert virtual_wrapper.get_reactors() == [target.get_field_dict().dxf.handle]
    field_list = doc.objects.get_field_list()
    assert field_list is not None
    assert virtual_wrapper.dxf.handle in field_list.handles
    assert target_child.dxf.handle in field_list.handles


def test_mtext_set_field_rejects_foreign_field_before_replacement():
    doc = dxfpy.new("R2007")
    target = doc.modelspace().add_mtext("TARGET")
    target_child, target_wrapper = target.new_dwgprops_field(
        "ProjectCode", register_field_list=True
    )
    foreign_doc = dxfpy.new("R2007")
    foreign_field = foreign_doc.objects.add_field(owner="0")
    foreign_field.set_dwgprops("Revision")

    with pytest.raises(dxfpy.DXFStructureError, match="different DXF document"):
        target.set_field(foreign_field)

    assert target.get_field() is target_wrapper
    assert target.get_primary_field() is target_child
    assert target_wrapper.is_alive
    assert target_child.is_alive


def test_mtext_set_field_preflights_malformed_copy_before_replacement():
    doc = dxfpy.new("R2007")
    source = doc.modelspace().add_mtext("SOURCE")
    _, source_wrapper = source.new_dwgprops_field("ProjectCode")
    malformed = source_wrapper.copy()
    malformed.tags = type(malformed.tags)(
        tag for tag in malformed.tags if tag.code != 360
    )
    target = doc.modelspace().add_mtext("TARGET")
    target_child, target_wrapper = target.new_dwgprops_field(
        "Revision", register_field_list=True
    )

    with pytest.raises(dxfpy.DXFStructureError, match="child handle count"):
        target.set_field(malformed)

    assert target.get_field() is target_wrapper
    assert target.get_primary_field() is target_child
    assert target_wrapper.is_alive
    assert target_child.is_alive


def test_mtext_set_field_rejects_root_owned_by_another_host():
    doc = dxfpy.new("R2007")
    source = doc.modelspace().add_mtext("SOURCE")
    source_child, source_wrapper = source.new_dwgprops_field("ProjectCode")
    target = doc.modelspace().add_mtext("TARGET")

    with pytest.raises(dxfpy.DXFStructureError, match="already owned"):
        target.set_field(source_wrapper)

    assert source.get_field() is source_wrapper
    assert source.get_primary_field() is source_child
    assert target.get_field() is None
    assert source_wrapper.is_alive
    assert source_child.is_alive


def test_mtext_set_field_reparents_child_reused_by_bound_wrapper():
    doc = dxfpy.new("R2007")
    mtext = doc.modelspace().add_mtext("SOURCE")
    child, original_wrapper = mtext.new_dwgprops_field(
        "ProjectCode", register_field_list=True
    )
    replacement = doc.objects.add_field(owner="0")
    replacement.set_text_wrapper(child)

    mtext.set_field(replacement)

    assert original_wrapper.is_alive is False
    assert child.is_alive
    assert child.dxf.owner == replacement.dxf.handle
    assert mtext.get_primary_field() is child
    mtext.remove_field()
    assert child.is_alive is False


def test_mtext_set_field_preserves_child_reused_by_virtual_raw_wrapper():
    doc = dxfpy.new("R2007")
    mtext = doc.modelspace().add_mtext("SOURCE")
    child, original_wrapper = mtext.new_dwgprops_field(
        "ProjectCode", register_field_list=True
    )
    replacement = Field()
    replacement.set_text_wrapper(child)

    mtext.set_field(replacement)

    assert original_wrapper.is_alive is False
    assert child.is_alive
    assert replacement.get_child_fields() == [child]
    assert child.dxf.owner == replacement.dxf.handle
    assert mtext.get_primary_field() is child


def test_mtext_set_field_remaps_reused_wrapper_owner_reactor():
    doc = dxfpy.new("R2007")
    mtext = doc.modelspace().add_mtext("SOURCE")
    child, original_wrapper = mtext.new_dwgprops_field("ProjectCode")
    original_dictionary_handle = mtext.get_field_dict().dxf.handle
    replacement = doc.objects.add_field(owner="0")
    replacement.set_text_wrapper(original_wrapper)

    mtext.set_field(replacement)

    assert child.is_alive
    assert original_wrapper.dxf.owner == replacement.dxf.handle
    assert original_wrapper.get_reactors() == [replacement.dxf.handle]
    assert original_dictionary_handle not in original_wrapper.get_reactors()


def test_mtext_set_field_restores_detached_child_owner_reactor():
    doc = dxfpy.new("R2007")
    leaf = doc.objects.add_field(owner="0")
    leaf.set_dwgprops("ProjectCode")
    nested_wrapper = doc.objects.add_field(owner="0")
    nested_wrapper.set_text_wrapper(leaf)
    leaf.dxf.owner = nested_wrapper.dxf.handle
    original_wrapper = doc.objects.add_field(owner="0")
    original_wrapper.set_text_wrapper(nested_wrapper)
    nested_wrapper.dxf.owner = original_wrapper.dxf.handle
    nested_wrapper.set_reactors([original_wrapper.dxf.handle])
    mtext = doc.modelspace().add_mtext("SOURCE")
    mtext.set_field(original_wrapper)
    replacement = doc.objects.add_field(owner="0")
    replacement.set_text_wrapper(nested_wrapper)

    mtext.set_field(replacement)

    assert original_wrapper.is_alive is False
    assert nested_wrapper.is_alive
    assert nested_wrapper.dxf.owner == replacement.dxf.handle
    assert nested_wrapper.get_reactors() == [replacement.dxf.handle]


def test_mtext_remove_field_preflights_field_list_before_unlinking():
    doc = dxfpy.new("R2007")
    mtext = doc.modelspace().add_mtext("SOURCE")
    child, wrapper = mtext.new_dwgprops_field(
        "ProjectCode", register_field_list=True
    )
    invalid_field_list = doc.objects.add_xrecord()
    doc.rootdict.add("ACAD_FIELDLIST", invalid_field_list)

    with pytest.raises(dxfpy.DXFStructureError, match="FIELDLIST"):
        mtext.remove_field()

    assert mtext.get_field() is wrapper
    assert mtext.get_primary_field() is child
    assert wrapper.is_alive
    assert child.is_alive


def test_mtext_new_linked_field_rolls_back_on_invalid_field_list():
    doc = dxfpy.new("R2007")
    invalid_field_list = doc.objects.add_xrecord()
    doc.rootdict.add("ACAD_FIELDLIST", invalid_field_list)
    mtext = doc.modelspace().add_mtext("TARGET")

    with pytest.raises(dxfpy.DXFStructureError, match="FIELDLIST"):
        mtext.new_linked_field(register_field_list=True)

    assert not any(
        isinstance(entity, Field) for entity in doc.entitydb.values()
    )
    assert mtext.get_field() is None


def test_mtext_set_linked_fields_rejects_empty_children():
    doc = dxfpy.new("R2007")
    mtext = doc.modelspace().add_mtext("TEXT")

    with pytest.raises(dxfpy.DXFStructureError):
        mtext.set_linked_fields([], field_code="")

    assert mtext.get_field() is None


def test_add_mtext_acexpr_field_creates_nested_expression_field():
    doc = dxfpy.new("R2007")
    msp = doc.modelspace()
    line = msp.add_line((0, 0), (10, 0))
    circle = msp.add_circle((5, 0), radius=2.5)
    child1 = Field()
    child1.set_acobjprop(line, "Length", value=10.0, display="10.0000")
    child2 = Field()
    child2.set_acobjprop(circle, "Radius", value=2.5, display="2.5000")

    mtext = msp.add_mtext_acexpr_field(
        "(%<\\_FldIdx 0>%*%<\\_FldIdx 1>%)",
        [child1, child2],
        value=25.0,
        text="25.0000",
        dxfattribs={"insert": (0, 0, 0)},
        register_field_list=True,
    )

    assert mtext.text == "25.0000"
    primary = mtext.get_primary_field()
    assert primary is not None
    assert primary.evaluator_id == "AcExpr"
    assert primary.field_code == "\\AcExpr (%<\\_FldIdx 0>%*%<\\_FldIdx 1>%) \\f \"%lu2\""
    children = primary.get_child_fields()
    assert len(children) == 2
    assert children[0].field_code == "\\AcObjProp Object(%<\\_ObjIdx 0>%).Length \\f \"%lu2\""
    assert children[1].field_code == "\\AcObjProp Object(%<\\_ObjIdx 0>%).Radius \\f \"%lu2\""
    field_list = doc.objects.get_field_list()
    assert field_list is not None
    for field in mtext.get_field().get_field_tree():
        assert field.dxf.handle in field_list.handles


def test_writing_high_level_field_entities_exports_expected_markers():
    doc = dxfpy.new("R2007")
    msp = doc.modelspace()
    line = msp.add_line((0, 0), (10, 0))
    msp.add_mtext_acvar_field("Author", text="----", register_field_list=True)
    msp.add_mtext_acobjprop_field(line, "Length", register_field_list=True)

    stream = io.StringIO()
    doc.write(stream)
    data = stream.getvalue()
    assert "ACAD_FIELDLIST" in data
    assert "ACAD_FIELD" in data
    assert "\\AcVar Author" in data
    assert "AcObjProp" in data

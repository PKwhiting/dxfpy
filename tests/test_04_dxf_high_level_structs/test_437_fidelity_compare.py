import ezdxf
from ezdxf._fidelity_compare import (
    ReplayComparison,
    compare_replay_documents,
    format_replay_comparison,
)
from ezdxf.math import Vec2
from ezdxf.render.mleader import ConnectionSide


def test_compare_replay_documents_reports_replay_issues():
    source_doc = ezdxf.new("R2018")
    source_doc.layout("Layout1").dxf.page_setup_name = "Source Setup"
    source_table = source_doc.layout("Layout1").add_table((0, 0), [["A"]])
    source_table.dxf.override_flag = 0
    replay_doc = ezdxf.new("R2018")
    replay_doc.appids.new("TEST_APP")
    replay_doc.layout("Layout1").dxf.viewport_handle = "DEADCAFE"
    replay_table = replay_doc.layout("Layout1").add_table((0, 0), [["A"]])
    replay_table.dxf.override_flag = 1
    bad_table = replay_doc.blocks.new("BAD_TABLE_CONTAINER").add_table((0, 0), [["B"]])
    bad_table.dxf.geometry = "*T_MISSING"
    bad_table.dxf.block_record_handle = "DEADBEEF"

    paper_line = replay_doc.layout("Layout1").add_line((0, 0), (1, 0))
    paper_line.set_xdata("TEST_APP", [(1005, "DEADBEEF")])
    xdict = paper_line.new_extension_dict().dictionary
    xdict.dxf.owner = "BAD"

    boundary = replay_doc.modelspace().add_line((0, 0), (1, 0))
    hatch = replay_doc.modelspace().add_hatch(color=2)
    path = hatch.paths.add_polyline_path(
        [(0, 0), (1, 0), (1, 1), (0, 1)], is_closed=True
    )
    path.source_boundary_objects = [boundary.dxf.handle]
    hatch.dxf.associative = 1

    builder = replay_doc.modelspace().add_multileader_mtext("Standard")
    builder.set_content("note")
    builder.add_leader_line(ConnectionSide.left, [Vec2(-5, 0), Vec2(-2, 0)])
    builder.build(insert=Vec2(0, 0))
    mleader = next(iter(replay_doc.modelspace().query("MULTILEADER")))
    mleader.dxf.style_handle = "DEADBEEF"

    comparison = compare_replay_documents(source_doc, replay_doc)
    report = format_replay_comparison(comparison)

    assert comparison.has_issues() is True
    assert len(comparison.layout_metadata_diffs) == 1
    assert len(comparison.layout_entity_count_diffs) == 1
    assert len(comparison.replay_bad_layout_viewport_refs) == 1
    assert comparison.replay_bad_layout_viewport_refs[0].reason == "missing_viewport"
    assert len(comparison.acad_table_diffs) == 1
    assert comparison.acad_table_diffs[0].attrib == "override_flag"
    assert len(comparison.replay_bad_acad_table_btrs) == 1
    assert comparison.replay_bad_acad_table_btrs[0].reason == "missing_geometry_block"
    assert len(comparison.replay_invalid_mleader_style_refs) == 1
    assert len(comparison.replay_unresolved_xdata_handles) == 1
    assert len(comparison.replay_bad_extension_dict_owners) == 1
    assert len(comparison.replay_stale_hatch_associations) == 1
    assert "replay_bad_layout_viewport_ref_count=1" in report
    assert "acad_table_diff_count=1" in report
    assert "replay_bad_acad_table_btr_count=1" in report
    assert "replay_unresolved_xdata_handles=1" in report


def test_replay_comparison_can_ignore_layout_order():
    comparison = ReplayComparison(
        source_layout_names=("Layout1", "Model"),
        replay_layout_names=("Model", "Layout1"),
        missing_layout_names=(),
        extra_layout_names=(),
        source_active_layout="Layout1",
        replay_active_layout="Layout1",
        layout_metadata_diffs=(),
        layout_entity_count_diffs=(),
        replay_bad_layout_viewport_refs=(),
        source_mleader_count=0,
        replay_mleader_count=0,
        source_mleader_style_distribution=(),
        replay_mleader_style_distribution=(),
        source_invalid_mleader_style_refs=(),
        replay_invalid_mleader_style_refs=(),
        replay_unresolved_xdata_handles=(),
        replay_bad_extension_dict_owners=(),
        replay_stale_hatch_associations=(),
    )

    assert comparison.layout_names_match is False
    assert comparison.has_issues() is False
    assert comparison.has_issues(include_layout_order=True) is True

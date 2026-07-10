"""Internal source-vs-replay DXF document comparison helpers."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from dxfpy.lldxf import const

if TYPE_CHECKING:
    from dxfpy.document import Drawing


_LAYOUT_ATTRIB_SKIP = frozenset(
    {"handle", "owner", "block_record_handle", "viewport_handle"}
)
_ACAD_TABLE_ATTRIBS = (
    "geometry",
    "block_record_name",
    "table_style_name",
    "version",
    "override_flag",
    "n_rows",
    "n_cols",
)


@dataclass(frozen=True)
class LayoutMetadataDiff:
    layout: str
    attrib: str
    source: Any
    replay: Any


@dataclass(frozen=True)
class LayoutEntityCountDiff:
    layout: str
    source: tuple[tuple[str, int], ...]
    replay: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class LayoutBlockRecordNameDiff:
    layout: str
    source: str
    replay: str


@dataclass(frozen=True)
class BadLayoutViewportRef:
    layout: str
    viewport_handle: str
    expected_owner: str
    actual_owner: str
    reason: str


@dataclass(frozen=True)
class AcadTableDiff:
    layout: str
    table_index: int
    attrib: str
    source: Any
    replay: Any


@dataclass(frozen=True)
class AcadTableGeometryBlockDiff:
    geometry: str
    reason: str
    source_count: int
    replay_count: int
    first_diff_index: int = -1
    source_type: str = ""
    replay_type: str = ""


@dataclass(frozen=True)
class BadAcadTableBtr:
    container: str
    table_handle: str
    geometry: str
    block_record_handle: str
    reason: str


@dataclass(frozen=True)
class InvalidMLeaderStyleRef:
    entity_handle: str
    style_handle: str
    target_dxftype: str


@dataclass(frozen=True)
class UnresolvedXDataHandle:
    dxftype: str
    entity_handle: str
    appid: str
    handle: str


@dataclass(frozen=True)
class BadExtensionDictOwner:
    dxftype: str
    entity_handle: str
    extension_dict_handle: str
    owner_handle: str


@dataclass(frozen=True)
class StaleHatchAssociation:
    hatch_handle: str
    boundary_handle: str


@dataclass(frozen=True)
class ReplayComparison:
    source_layout_names: tuple[str, ...]
    replay_layout_names: tuple[str, ...]
    missing_layout_names: tuple[str, ...]
    extra_layout_names: tuple[str, ...]
    source_active_layout: str
    replay_active_layout: str
    layout_metadata_diffs: tuple[LayoutMetadataDiff, ...]
    layout_entity_count_diffs: tuple[LayoutEntityCountDiff, ...]
    layout_block_record_name_diffs: tuple[LayoutBlockRecordNameDiff, ...]
    replay_bad_layout_viewport_refs: tuple[BadLayoutViewportRef, ...]
    source_mleader_count: int
    replay_mleader_count: int
    source_mleader_style_distribution: tuple[tuple[str, int], ...]
    replay_mleader_style_distribution: tuple[tuple[str, int], ...]
    source_invalid_mleader_style_refs: tuple[InvalidMLeaderStyleRef, ...]
    replay_invalid_mleader_style_refs: tuple[InvalidMLeaderStyleRef, ...]
    replay_unresolved_xdata_handles: tuple[UnresolvedXDataHandle, ...]
    replay_bad_extension_dict_owners: tuple[BadExtensionDictOwner, ...]
    replay_stale_hatch_associations: tuple[StaleHatchAssociation, ...]
    acad_table_diffs: tuple[AcadTableDiff, ...] = ()
    acad_table_geometry_block_diffs: tuple[AcadTableGeometryBlockDiff, ...] = ()
    replay_bad_acad_table_btrs: tuple[BadAcadTableBtr, ...] = ()

    @property
    def layout_names_match(self) -> bool:
        return self.source_layout_names == self.replay_layout_names

    @property
    def active_layout_matches(self) -> bool:
        return self.source_active_layout == self.replay_active_layout

    @property
    def mleader_style_distribution_matches(self) -> bool:
        return (
            self.source_mleader_count == self.replay_mleader_count
            and self.source_mleader_style_distribution
            == self.replay_mleader_style_distribution
        )

    def has_issues(self, *, include_layout_order: bool = False) -> bool:
        if include_layout_order and not self.layout_names_match:
            return True
        return any(
            (
                self.missing_layout_names,
                self.extra_layout_names,
                not self.active_layout_matches,
                self.layout_metadata_diffs,
                self.layout_entity_count_diffs,
                self.layout_block_record_name_diffs,
                self.replay_bad_layout_viewport_refs,
                not self.mleader_style_distribution_matches,
                self.acad_table_diffs,
                self.acad_table_geometry_block_diffs,
                self.replay_bad_acad_table_btrs,
                self.source_invalid_mleader_style_refs,
                self.replay_invalid_mleader_style_refs,
                self.replay_unresolved_xdata_handles,
                self.replay_bad_extension_dict_owners,
                self.replay_stale_hatch_associations,
            )
        )


def compare_replay_documents(source_doc: Drawing, replay_doc: Drawing) -> ReplayComparison:
    source_layout_names = _layout_names(source_doc)
    replay_layout_names = _layout_names(replay_doc)
    source_mleader_stats = _mleader_stats(source_doc)
    replay_mleader_stats = _mleader_stats(replay_doc)
    return ReplayComparison(
        source_layout_names=source_layout_names,
        replay_layout_names=replay_layout_names,
        missing_layout_names=tuple(
            name for name in source_layout_names if name not in replay_layout_names
        ),
        extra_layout_names=tuple(
            name for name in replay_layout_names if name not in source_layout_names
        ),
        source_active_layout=_active_layout_name(source_doc),
        replay_active_layout=_active_layout_name(replay_doc),
        layout_metadata_diffs=_layout_metadata_diffs(source_doc, replay_doc),
        layout_entity_count_diffs=_layout_entity_count_diffs(source_doc, replay_doc),
        layout_block_record_name_diffs=_layout_block_record_name_diffs(
            source_doc, replay_doc
        ),
        replay_bad_layout_viewport_refs=_bad_layout_viewport_refs(replay_doc),
        source_mleader_count=source_mleader_stats[0],
        replay_mleader_count=replay_mleader_stats[0],
        source_mleader_style_distribution=source_mleader_stats[1],
        replay_mleader_style_distribution=replay_mleader_stats[1],
        acad_table_diffs=_acad_table_diffs(source_doc, replay_doc),
        acad_table_geometry_block_diffs=_acad_table_geometry_block_diffs(
            source_doc, replay_doc
        ),
        replay_bad_acad_table_btrs=_bad_acad_table_btrs(replay_doc),
        source_invalid_mleader_style_refs=source_mleader_stats[2],
        replay_invalid_mleader_style_refs=replay_mleader_stats[2],
        replay_unresolved_xdata_handles=_unresolved_xdata_handles(replay_doc),
        replay_bad_extension_dict_owners=_bad_extension_dict_owners(replay_doc),
        replay_stale_hatch_associations=_stale_hatch_associations(replay_doc),
    )


def format_replay_comparison(
    comparison: ReplayComparison, *, sample_limit: int = 10
) -> str:
    lines = [
        "Replay comparison:",
        f"  layout_names_match={comparison.layout_names_match}",
        f"  source_layouts={comparison.source_layout_names!r}",
        f"  replay_layouts={comparison.replay_layout_names!r}",
        f"  missing_layouts={comparison.missing_layout_names!r}",
        f"  extra_layouts={comparison.extra_layout_names!r}",
        f"  active_layout_matches={comparison.active_layout_matches}",
        f"  source_active_layout={comparison.source_active_layout!r}",
        f"  replay_active_layout={comparison.replay_active_layout!r}",
        f"  layout_metadata_diff_count={len(comparison.layout_metadata_diffs)}",
        f"  layout_entity_count_diff_count={len(comparison.layout_entity_count_diffs)}",
        "  layout_block_record_name_diff_count="
        f"{len(comparison.layout_block_record_name_diffs)}",
        "  replay_bad_layout_viewport_ref_count="
        f"{len(comparison.replay_bad_layout_viewport_refs)}",
        f"  source_mleader_count={comparison.source_mleader_count}",
        f"  replay_mleader_count={comparison.replay_mleader_count}",
        "  mleader_style_distribution_matches="
        f"{comparison.mleader_style_distribution_matches}",
        f"  acad_table_diff_count={len(comparison.acad_table_diffs)}",
        "  acad_table_geometry_block_diff_count="
        f"{len(comparison.acad_table_geometry_block_diffs)}",
        "  replay_bad_acad_table_btr_count="
        f"{len(comparison.replay_bad_acad_table_btrs)}",
        "  source_invalid_mleader_style_refs="
        f"{len(comparison.source_invalid_mleader_style_refs)}",
        "  replay_invalid_mleader_style_refs="
        f"{len(comparison.replay_invalid_mleader_style_refs)}",
        "  replay_unresolved_xdata_handles="
        f"{len(comparison.replay_unresolved_xdata_handles)}",
        "  replay_bad_extension_dict_owners="
        f"{len(comparison.replay_bad_extension_dict_owners)}",
        "  replay_stale_hatch_associations="
        f"{len(comparison.replay_stale_hatch_associations)}",
    ]
    _append_sample(
        lines, "layout_metadata_diffs", comparison.layout_metadata_diffs, sample_limit
    )
    _append_sample(
        lines,
        "layout_entity_count_diffs",
        comparison.layout_entity_count_diffs,
        sample_limit,
    )
    _append_sample(
        lines,
        "layout_block_record_name_diffs",
        comparison.layout_block_record_name_diffs,
        sample_limit,
    )
    _append_sample(
        lines,
        "replay_bad_layout_viewport_refs",
        comparison.replay_bad_layout_viewport_refs,
        sample_limit,
    )
    if not comparison.mleader_style_distribution_matches:
        lines.append(
            "  source_mleader_style_distribution="
            f"{comparison.source_mleader_style_distribution!r}"
        )
        lines.append(
            "  replay_mleader_style_distribution="
            f"{comparison.replay_mleader_style_distribution!r}"
        )
    _append_sample(lines, "acad_table_diffs", comparison.acad_table_diffs, sample_limit)
    _append_sample(
        lines,
        "acad_table_geometry_block_diffs",
        comparison.acad_table_geometry_block_diffs,
        sample_limit,
    )
    _append_sample(
        lines,
        "replay_bad_acad_table_btrs",
        comparison.replay_bad_acad_table_btrs,
        sample_limit,
    )
    _append_sample(
        lines,
        "source_invalid_mleader_style_refs",
        comparison.source_invalid_mleader_style_refs,
        sample_limit,
    )
    _append_sample(
        lines,
        "replay_invalid_mleader_style_refs",
        comparison.replay_invalid_mleader_style_refs,
        sample_limit,
    )
    _append_sample(
        lines,
        "replay_unresolved_xdata_handles",
        comparison.replay_unresolved_xdata_handles,
        sample_limit,
    )
    _append_sample(
        lines,
        "replay_bad_extension_dict_owners",
        comparison.replay_bad_extension_dict_owners,
        sample_limit,
    )
    _append_sample(
        lines,
        "replay_stale_hatch_associations",
        comparison.replay_stale_hatch_associations,
        sample_limit,
    )
    return "\n".join(lines)


def _append_sample(lines: list[str], name: str, values: tuple, limit: int) -> None:
    if not values:
        return
    lines.append(f"  {name}_sample={values[:limit]!r}")


def _normalize(value: Any) -> Any:
    if type(value).__name__ == "float64":
        return float(value)
    if type(value).__name__ in {"Vec2", "Vec3"}:
        return tuple(_normalize(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_normalize(item) for item in value)
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    if isinstance(value, dict):
        return {key: _normalize(item) for key, item in value.items()}
    return value


def _equivalent_values(source: Any, replay: Any) -> bool:
    if source == replay:
        return True
    if isinstance(source, tuple) and isinstance(replay, tuple):
        if len(source) == 2 and len(replay) == 3 and replay[2] == 0.0:
            return source == replay[:2]
        if len(source) == 3 and len(replay) == 2 and source[2] == 0.0:
            return source[:2] == replay
    return False


def _layout_names(doc: Drawing) -> tuple[str, ...]:
    return tuple(str(name) for name in doc.layouts.names())


def _active_layout_name(doc: Drawing) -> str:
    try:
        return str(doc.layouts.active_layout().name)
    except Exception:
        return ""


def _paper_layout_names(doc: Drawing) -> tuple[str, ...]:
    return tuple(
        name for name in _layout_names(doc) if name not in ("Model", "Model_Space")
    )


def _layout_dxfattribs(doc: Drawing, layout_name: str) -> dict[str, Any]:
    return {
        key: _normalize(value)
        for key, value in doc.layout(layout_name).dxf.all_existing_dxf_attribs().items()
        if key not in _LAYOUT_ATTRIB_SKIP
    }


def _layout_dxfattrib_value(doc: Drawing, layout_name: str, attrib: str) -> Any:
    layout = doc.layout(layout_name)
    try:
        return _normalize(layout.dxf.get_default(attrib))
    except const.DXFAttributeError:
        return _normalize(layout.dxf.get(attrib))


def _layout_metadata_diffs(
    source_doc: Drawing, replay_doc: Drawing
) -> tuple[LayoutMetadataDiff, ...]:
    diffs: list[LayoutMetadataDiff] = []
    replay_layouts = set(_layout_names(replay_doc))
    for layout_name in _paper_layout_names(source_doc):
        if layout_name not in replay_layouts:
            continue
        source_attribs = _layout_dxfattribs(source_doc, layout_name)
        replay_attribs = _layout_dxfattribs(replay_doc, layout_name)
        for attrib in sorted(set(source_attribs) | set(replay_attribs)):
            source_value = _layout_dxfattrib_value(source_doc, layout_name, attrib)
            replay_value = _layout_dxfattrib_value(replay_doc, layout_name, attrib)
            if not _equivalent_values(source_value, replay_value):
                diffs.append(
                    LayoutMetadataDiff(
                        layout_name,
                        attrib,
                        source_value,
                        replay_value,
                    )
                )
    return tuple(diffs)


def _layout_entity_count_diffs(
    source_doc: Drawing, replay_doc: Drawing
) -> tuple[LayoutEntityCountDiff, ...]:
    diffs: list[LayoutEntityCountDiff] = []
    replay_layouts = set(_layout_names(replay_doc))
    for layout_name in _paper_layout_names(source_doc):
        if layout_name not in replay_layouts:
            continue
        source_counts = _layout_type_counts(source_doc, layout_name)
        replay_counts = _layout_type_counts(replay_doc, layout_name)
        if source_counts != replay_counts:
            diffs.append(LayoutEntityCountDiff(layout_name, source_counts, replay_counts))
    return tuple(diffs)


def _layout_block_record_name_diffs(
    source_doc: Drawing, replay_doc: Drawing
) -> tuple[LayoutBlockRecordNameDiff, ...]:
    diffs: list[LayoutBlockRecordNameDiff] = []
    replay_layouts = set(_layout_names(replay_doc))
    for layout_name in _layout_names(source_doc):
        if layout_name not in replay_layouts:
            continue
        source_name = _layout_block_record_name(source_doc, layout_name)
        replay_name = _layout_block_record_name(replay_doc, layout_name)
        if source_name != replay_name:
            diffs.append(LayoutBlockRecordNameDiff(layout_name, source_name, replay_name))
    return tuple(diffs)


def _layout_block_record_name(doc: Drawing, layout_name: str) -> str:
    layout = doc.layout(layout_name)
    block_record = doc.entitydb.get(layout.block_record_handle)
    if block_record is None:
        return ""
    return str(block_record.dxf.get("name") or "")


def _layout_type_counts(doc: Drawing, layout_name: str) -> tuple[tuple[str, int], ...]:
    return tuple(
        sorted(Counter(entity.dxftype() for entity in doc.layout(layout_name)).items())
    )


def _bad_layout_viewport_refs(doc: Drawing) -> tuple[BadLayoutViewportRef, ...]:
    # AutoCAD dereferences LAYOUT.viewport_handle when activating a tab; stale
    # source handles can pass AUDIT but still crash during layout switching.
    bad: list[BadLayoutViewportRef] = []
    for layout_name in _paper_layout_names(doc):
        layout = doc.layout(layout_name)
        viewport_handle = str(layout.dxf.get("viewport_handle") or "")
        expected_owner = str(layout.block_record_handle or "")
        has_viewports = any(entity.dxftype() == "VIEWPORT" for entity in layout)
        reason = ""
        actual_owner = ""
        if not viewport_handle:
            if has_viewports:
                reason = "missing_viewport_handle"
        else:
            target = doc.entitydb.get(viewport_handle)
            if target is None:
                reason = "missing_viewport"
            elif not target.is_alive:
                reason = "erased_viewport"
            elif target.dxftype() != "VIEWPORT":
                reason = f"points_to_{target.dxftype()}"
                actual_owner = str(target.dxf.get("owner") or "")
            else:
                actual_owner = str(target.dxf.get("owner") or "")
                if actual_owner != expected_owner:
                    reason = "wrong_viewport_owner"
        if reason:
            bad.append(
                BadLayoutViewportRef(
                    layout_name,
                    viewport_handle,
                    expected_owner,
                    actual_owner,
                    reason,
                )
            )
    return tuple(bad)


def _acad_table_diffs(
    source_doc: Drawing, replay_doc: Drawing
) -> tuple[AcadTableDiff, ...]:
    diffs: list[AcadTableDiff] = []
    replay_layouts = set(_layout_names(replay_doc))
    for layout_name in _layout_names(source_doc):
        if layout_name not in replay_layouts:
            continue
        source_tables = _acad_tables(source_doc, layout_name)
        replay_tables = _acad_tables(replay_doc, layout_name)
        if len(source_tables) != len(replay_tables):
            diffs.append(
                AcadTableDiff(
                    layout_name,
                    -1,
                    "count",
                    len(source_tables),
                    len(replay_tables),
                )
            )
        for index, (source_table, replay_table) in enumerate(
            zip(source_tables, replay_tables)
        ):
            for attrib in _ACAD_TABLE_ATTRIBS:
                source_value = _acad_table_value(source_doc, source_table, attrib)
                replay_value = _acad_table_value(replay_doc, replay_table, attrib)
                if not _equivalent_values(source_value, replay_value):
                    diffs.append(
                        AcadTableDiff(
                            layout_name,
                            index,
                            attrib,
                            source_value,
                            replay_value,
                        )
                    )
    return tuple(diffs)


def _acad_table_geometry_block_diffs(
    source_doc: Drawing, replay_doc: Drawing
) -> tuple[AcadTableGeometryBlockDiff, ...]:
    diffs: list[AcadTableGeometryBlockDiff] = []
    source_names = _acad_table_geometry_names(source_doc)
    replay_names = _acad_table_geometry_names(replay_doc)
    for geometry_name in sorted(source_names - replay_names):
        source_signature = _block_signature(source_doc, geometry_name)
        diffs.append(
            AcadTableGeometryBlockDiff(
                geometry_name, "missing", len(source_signature), 0
            )
        )
    for geometry_name in sorted(replay_names - source_names):
        replay_signature = _block_signature(replay_doc, geometry_name)
        diffs.append(
            AcadTableGeometryBlockDiff(
                geometry_name, "extra", 0, len(replay_signature)
            )
        )
    for geometry_name in sorted(source_names & replay_names):
        source_signature = _block_signature(source_doc, geometry_name)
        replay_signature = _block_signature(replay_doc, geometry_name)
        if source_signature == replay_signature:
            continue
        first_diff = next(
            (
                index
                for index, (source, replay) in enumerate(
                    zip(source_signature, replay_signature)
                )
                if source != replay
            ),
            min(len(source_signature), len(replay_signature)),
        )
        source_type = (
            source_signature[first_diff][0]
            if first_diff < len(source_signature)
            else ""
        )
        replay_type = (
            replay_signature[first_diff][0]
            if first_diff < len(replay_signature)
            else ""
        )
        diffs.append(
            AcadTableGeometryBlockDiff(
                geometry_name,
                "content",
                len(source_signature),
                len(replay_signature),
                first_diff,
                source_type,
                replay_type,
            )
        )
    return tuple(diffs)


def _acad_table_geometry_names(doc: Drawing) -> set[str]:
    names: set[str] = set()
    for entity in doc.entitydb.values():
        if entity is None or not entity.is_alive or entity.dxftype() != "ACAD_TABLE":
            continue
        geometry_name = entity.dxf.get("geometry")
        if geometry_name and doc.blocks.get(str(geometry_name)) is not None:
            names.add(str(geometry_name))
    for block in doc.blocks:
        if not str(block.name).upper().startswith("*U"):
            continue
        for entity in block:
            if entity.dxftype() != "INSERT":
                continue
            geometry_name = str(entity.dxf.get("name") or "")
            if geometry_name.startswith("*T") and doc.blocks.get(geometry_name) is not None:
                names.add(geometry_name)
    return names


def _block_signature(doc: Drawing, block_name: str) -> tuple[tuple[str, Any], ...]:
    block = doc.blocks.get(block_name)
    if block is None:
        return ()
    return tuple(_entity_signature(entity) for entity in block)


def _entity_signature(entity) -> tuple[str, Any]:
    attribs = {
        key: _normalize(value)
        for key, value in entity.dxf.all_existing_dxf_attribs().items()
        if key not in {"handle", "owner"}
    }
    content = getattr(entity, "text", None)
    return entity.dxftype(), tuple(sorted(attribs.items())), content


def _acad_tables(doc: Drawing, layout_name: str) -> list:
    return [entity for entity in doc.layout(layout_name) if entity.dxftype() == "ACAD_TABLE"]


def _acad_table_value(doc: Drawing, table, attrib: str) -> Any:
    if attrib == "block_record_name":
        return _handle_resource_name(doc, table.dxf.get("block_record_handle", ""))
    if attrib == "table_style_name":
        return _handle_resource_name(doc, table.dxf.get("table_style_id", ""))
    try:
        return _normalize(table.dxf.get(attrib))
    except const.DXFAttributeError:
        return None


def _handle_resource_name(doc: Drawing, handle: str) -> str:
    if not handle:
        return ""
    entity = doc.entitydb.get(str(handle))
    if entity is None:
        return f"<missing:{handle}>"
    if entity.dxftype() == "TABLESTYLE":
        for name, style in doc.table_styles.object_dict.items():
            if style is entity:
                return str(name)
    if entity.dxf.hasattr("name"):
        return str(entity.dxf.name)
    return entity.dxftype()


def _bad_acad_table_btrs(doc: Drawing) -> tuple[BadAcadTableBtr, ...]:
    # AUDIT reports these as "AcDbTable BTR Id invalid" and erases the tables.
    block_record_names = _block_record_names(doc)
    bad: list[BadAcadTableBtr] = []
    for entity in doc.entitydb.values():
        if entity is None or not entity.is_alive or entity.dxftype() != "ACAD_TABLE":
            continue
        geometry_name = str(entity.dxf.get("geometry") or "")
        block_record_handle = str(entity.dxf.get("block_record_handle") or "")
        reason = ""
        if not geometry_name:
            reason = "missing_geometry"
        elif not block_record_handle:
            reason = "missing_block_record_handle"
        else:
            geometry_block = doc.blocks.get(geometry_name)
            target = doc.entitydb.get(block_record_handle)
            if geometry_block is None:
                reason = "missing_geometry_block"
            elif target is None:
                reason = "missing_block_record"
            elif target.dxftype() != "BLOCK_RECORD":
                reason = f"block_record_handle_points_to_{target.dxftype()}"
            elif geometry_block.block_record_handle != block_record_handle:
                reason = "geometry_block_record_mismatch"
        if reason:
            bad.append(
                BadAcadTableBtr(
                    block_record_names.get(str(entity.dxf.get("owner") or ""), ""),
                    str(entity.dxf.get("handle") or ""),
                    geometry_name,
                    block_record_handle,
                    reason,
                )
            )
    return tuple(bad)


def _block_record_names(doc: Drawing) -> dict[str, str]:
    names: dict[str, str] = {}
    for layout_name in _layout_names(doc):
        layout = doc.layout(layout_name)
        handle = layout.block_record_handle
        if handle:
            names[str(handle)] = layout_name
    for block in doc.blocks:
        if block.block_record_handle:
            names[str(block.block_record_handle)] = block.name
    return names


def _mleader_style_keys(doc: Drawing) -> dict[str, str]:
    return {
        str(style.dxf.handle): str(name)
        for name, style in doc.mleader_styles.object_dict.items()
        if style.dxf.handle
    }


def _mleader_style_handle(entity) -> str:
    try:
        return str(entity.dxf.get("style_handle") or "")
    except const.DXFAttributeError:
        pass
    xtags = getattr(entity, "xtags", None)
    if xtags is None:
        return ""
    try:
        tags = xtags.get_subclass("AcDbMLeader")
    except const.DXFKeyError:
        return ""
    start = 0
    for index, tag in enumerate(tags):
        if tag.code == 301:
            start = index + 1
            break
    for tag in tags[start:]:
        if tag.code == 340:
            return str(tag.value)
    return ""


def _mleader_stats(
    doc: Drawing,
) -> tuple[int, tuple[tuple[str, int], ...], tuple[InvalidMLeaderStyleRef, ...]]:
    handle_to_key = _mleader_style_keys(doc)
    invalid: list[InvalidMLeaderStyleRef] = []
    keys: Counter[str] = Counter()
    total = 0
    for entity in doc.entitydb.values():
        if entity.dxftype() != "MULTILEADER":
            continue
        total += 1
        style_handle = _mleader_style_handle(entity)
        target = doc.entitydb.get(style_handle) if style_handle else None
        if target is None or target.dxftype() != "MLEADERSTYLE":
            invalid.append(
                InvalidMLeaderStyleRef(
                    str(entity.dxf.get("handle", "")),
                    style_handle,
                    target.dxftype() if target is not None else "",
                )
            )
        keys[handle_to_key.get(style_handle, f"<invalid:{style_handle}>")] += 1
    return total, tuple(sorted(keys.items())), tuple(invalid)


def _unresolved_xdata_handles(doc: Drawing) -> tuple[UnresolvedXDataHandle, ...]:
    unresolved: list[UnresolvedXDataHandle] = []
    for entity in doc.entitydb.values():
        if not entity.xdata:
            continue
        for appid, tags in entity.xdata.data.items():
            for tag in tags:
                handle = str(tag.value)
                if (
                    tag.code == 1005
                    and handle != "0"
                    and doc.entitydb.get(handle) is None
                ):
                    unresolved.append(
                        UnresolvedXDataHandle(
                            entity.dxftype(),
                            str(entity.dxf.get("handle", "")),
                            str(appid),
                            handle,
                        )
                    )
    return tuple(unresolved)


def _bad_extension_dict_owners(doc: Drawing) -> tuple[BadExtensionDictOwner, ...]:
    bad: list[BadExtensionDictOwner] = []
    for entity in doc.entitydb.values():
        if not getattr(entity, "has_extension_dict", False):
            continue
        try:
            xdict = entity.get_extension_dict().dictionary
        except Exception:
            continue
        entity_handle = str(entity.dxf.get("handle", ""))
        owner_handle = str(xdict.dxf.get("owner", ""))
        if owner_handle != entity_handle:
            bad.append(
                BadExtensionDictOwner(
                    entity.dxftype(),
                    entity_handle,
                    str(xdict.dxf.get("handle", "")),
                    owner_handle,
                )
            )
    return tuple(bad)


def _stale_hatch_associations(doc: Drawing) -> tuple[StaleHatchAssociation, ...]:
    stale: list[StaleHatchAssociation] = []
    for entity in doc.entitydb.values():
        if entity.dxftype() != "HATCH" or not entity.dxf.get("associative", 0):
            continue
        hatch_handle = str(entity.dxf.get("handle", ""))
        for path in entity.paths:
            for boundary_handle in getattr(path, "source_boundary_objects", []):
                boundary_handle = str(boundary_handle)
                boundary = doc.entitydb.get(boundary_handle)
                reactors = (
                    list(boundary.reactors.reactors)
                    if boundary is not None and boundary.reactors
                    else []
                )
                if boundary is None or hatch_handle not in reactors:
                    stale.append(StaleHatchAssociation(hatch_handle, boundary_handle))
    return tuple(stale)

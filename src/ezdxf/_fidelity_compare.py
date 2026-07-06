"""Internal source-vs-replay DXF document comparison helpers."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ezdxf.lldxf import const

if TYPE_CHECKING:
    from ezdxf.document import Drawing


_LAYOUT_ATTRIB_SKIP = frozenset({"handle", "owner", "block_record_handle"})


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
    source_mleader_count: int
    replay_mleader_count: int
    source_mleader_style_distribution: tuple[tuple[str, int], ...]
    replay_mleader_style_distribution: tuple[tuple[str, int], ...]
    source_invalid_mleader_style_refs: tuple[InvalidMLeaderStyleRef, ...]
    replay_invalid_mleader_style_refs: tuple[InvalidMLeaderStyleRef, ...]
    replay_unresolved_xdata_handles: tuple[UnresolvedXDataHandle, ...]
    replay_bad_extension_dict_owners: tuple[BadExtensionDictOwner, ...]
    replay_stale_hatch_associations: tuple[StaleHatchAssociation, ...]

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
                not self.mleader_style_distribution_matches,
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
        source_mleader_count=source_mleader_stats[0],
        replay_mleader_count=replay_mleader_stats[0],
        source_mleader_style_distribution=source_mleader_stats[1],
        replay_mleader_style_distribution=replay_mleader_stats[1],
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
        f"  source_mleader_count={comparison.source_mleader_count}",
        f"  replay_mleader_count={comparison.replay_mleader_count}",
        "  mleader_style_distribution_matches="
        f"{comparison.mleader_style_distribution_matches}",
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
    if not comparison.mleader_style_distribution_matches:
        lines.append(
            "  source_mleader_style_distribution="
            f"{comparison.source_mleader_style_distribution!r}"
        )
        lines.append(
            "  replay_mleader_style_distribution="
            f"{comparison.replay_mleader_style_distribution!r}"
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


def _layout_type_counts(doc: Drawing, layout_name: str) -> tuple[tuple[str, int], ...]:
    return tuple(
        sorted(Counter(entity.dxftype() for entity in doc.layout(layout_name)).items())
    )


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

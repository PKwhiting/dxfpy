from __future__ import annotations

from typing import TYPE_CHECKING, Mapping, Sequence

from ezdxf.dynblkhelper import (
    _delete_graph_stack,
    _ensure_dynamic_block_extension_dict,
    _new_tag_storage_object,
    _raw_object_handle_mapping,
)
from ezdxf.entities import factory
from ezdxf.entities import DXFEntity
from ezdxf.entities.dxfentity import DXFTagStorage
from ezdxf.layouts.layouts import key as layout_key
from ezdxf.lldxf import const
from ezdxf.lldxf.extendedtags import ExtendedTags
from ezdxf.lldxf.tags import Tags
from ezdxf.lldxf.types import DXFTag, dxftag

from ._specs import OwnedObjectSpecData

if TYPE_CHECKING:
    from ezdxf.dynblkhelper import RawEntityExportSnapshot
    from ezdxf.entities.dxfobj import Field

_RAW_GRAPH_HANDLE_CODES = (330, 331, 332, 333, 340, 360, 1005)
_RAW_GRAPHIC_RESOURCE_CODES = (
    320,
    330,
    331,
    332,
    333,
    340,
    341,
    342,
    343,
    344,
    345,
    346,
    347,
    348,
    349,
    350,
    360,
    390,
    1005,
)
_BINARY_DATA_CODES = (310, 311, 312, 313, 314, 315, 316, 317, 318, 319)
_ACAD_TABLE_FIELD_CONTENT_TYPE = 2


class DocumentCodegenRuntime:
    def __init__(self, doc) -> None:
        self.doc = doc
        self.source_entity_map: dict[str, DXFEntity] = {}
        self.source_object_map: dict[str, DXFEntity] = {}
        self.dangling_handle_map: dict[str, str] = {}

    def register_entity_map(self, entity_map: dict[str, DXFEntity]) -> None:
        self.source_entity_map.update(entity_map)
        self._register_global_handles(entity_map)

    def register_object_map(self, object_map: Mapping[str, DXFEntity]) -> None:
        """Register source object handles mapped to replay objects.

        Args:
            object_map: Mapping of source handles to replayed DXF objects.

        """
        self.source_object_map.update(object_map)
        self._register_global_handles(object_map)

    def _register_global_handles(self, handle_map: Mapping[str, DXFEntity]) -> None:
        """Register source-to-target handles in the document global map."""
        global_mapping = _raw_object_handle_mapping(self.doc)
        for source_handle, entity in handle_map.items():
            target_handle = self._entity_handle(entity)
            if source_handle and target_handle:
                global_mapping[str(source_handle)] = str(target_handle)

    @staticmethod
    def _entity_handle(entity: DXFEntity) -> str | None:
        """Return an entity handle if `entity` exposes a DXF namespace."""
        dxf = getattr(entity, "dxf", None)
        if dxf is None:
            return None
        handle = dxf.get("handle")
        return str(handle) if handle else None

    def prepare_acad_table_geometry_restore(self, block_name: str) -> None:
        """Delete generated table geometry field trees before block restore.

        Args:
            block_name: Name of the table geometry block to restore.

        """
        block = self.doc.blocks.get(block_name)
        if block is None:
            return
        for entity in list(self.doc.entitydb.values()):
            if entity.dxftype() != "ACAD_TABLE":
                continue
            if entity.dxf.get("geometry") != block_name:
                continue
            destroy = getattr(entity, "_destroy_geometry_field_support", None)
            if callable(destroy):
                destroy(block)

    def register_acad_table_content_field_copy(
        self,
        table: DXFEntity,
        row: int,
        col: int,
        source_wrapper_handle: str,
        source_primary_handle: str,
    ) -> None:
        """Register source TABLECONTENT field-copy handles for a replayed cell.

        Args:
            table: Replayed ACAD_TABLE entity.
            row: Zero-based row index.
            col: Zero-based column index.
            source_wrapper_handle: Source wrapper FIELD handle.
            source_primary_handle: Source primary FIELD handle.

        """
        wrapper = self._acad_table_content_field_wrapper(table, row, col)
        if wrapper is None:
            return
        object_map: dict[str, DXFEntity] = {source_wrapper_handle: wrapper}
        primary = self._primary_field(wrapper)
        if source_primary_handle and primary is not None:
            object_map[source_primary_handle] = primary
        self.register_object_map(object_map)

    def restore_acad_table_field_handles(
        self, source_table_handle: str, cells: list[tuple[int, int, str]]
    ) -> None:
        """Restore ACAD_TABLE shell FIELD handles after geometry replay.

        Args:
            source_table_handle: Source ACAD_TABLE handle.
            cells: Tuples of row, column, and source wrapper FIELD handle.

        """
        table = self.source_entity_map.get(source_table_handle)
        if table is None:
            return
        for row, col, source_field_handle in cells:
            wrapper = self.source_object_map.get(source_field_handle)
            if wrapper is None or wrapper.dxftype() != "FIELD":
                continue
            self._restore_acad_table_cell_field(table, row, col, wrapper)

    def _restore_acad_table_cell_field(
        self, table: DXFEntity, row: int, col: int, wrapper: DXFEntity
    ) -> None:
        """Set one table cell to a replayed geometry wrapper FIELD."""
        try:
            cell = table.get_cell(row, col)
        except (AttributeError, IndexError):
            return
        cell.field_handle = wrapper.dxf.handle
        content_wrapper = self._acad_table_content_field_wrapper(table, row, col)
        self._sync_content_copy_children(content_wrapper, self._primary_field(wrapper))

    def _acad_table_content_field_wrapper(
        self, table: DXFEntity, row: int, col: int
    ) -> DXFEntity | None:
        """Return the linked TABLECONTENT field-copy wrapper for a cell."""
        get_linked_cell = getattr(table, "get_linked_cell", None)
        if not callable(get_linked_cell):
            return None
        try:
            linked_cell = get_linked_cell(row, col)
        except (AttributeError, IndexError):
            return None
        for content in linked_cell.contents:
            if getattr(content, "content_type", None) != _ACAD_TABLE_FIELD_CONTENT_TYPE:
                continue
            handle = getattr(content, "block_record_handle", None)
            if not handle:
                continue
            wrapper = self.doc.entitydb.get(handle)
            if wrapper is not None and wrapper.dxftype() == "FIELD":
                return wrapper
        return None

    @staticmethod
    def _primary_field(wrapper: DXFEntity | None) -> Field | None:
        """Return the primary field for a wrapper FIELD object."""
        if wrapper is None or wrapper.dxftype() != "FIELD":
            return None
        children = wrapper.get_child_fields()
        if wrapper.is_text_wrapper and children:
            return children[0]
        return wrapper

    def _sync_content_copy_children(
        self, content_wrapper: DXFEntity | None, geometry_primary: Field | None
    ) -> None:
        """Point TABLECONTENT AcExpr child handles at geometry children."""
        content_primary = self._primary_field(content_wrapper)
        if content_primary is None or geometry_primary is None:
            return
        if content_primary.evaluator_id != geometry_primary.evaluator_id:
            return
        geometry_children = geometry_primary.get_child_fields()
        content_child_count = self._field_child_handle_count(content_primary)
        if not geometry_children or len(geometry_children) != content_child_count:
            return
        handles = self._field_handles(geometry_children)
        if len(handles) != len(geometry_children):
            return
        self._replace_field_child_handles(content_primary, handles)

    @staticmethod
    def _field_child_handle_count(field: Field) -> int:
        """Return the number of child handle tags in a FIELD payload."""
        return sum(1 for tag in field.tags if tag.code == 360)

    @staticmethod
    def _field_handles(fields: Sequence[Field]) -> list[str]:
        """Return valid handles for FIELD children."""
        return [field.dxf.handle for field in fields if field.dxf.handle]

    @staticmethod
    def _replace_field_child_handles(field: Field, handles: list[str]) -> None:
        """Replace FIELD child handle tags with `handles` in order."""
        index = 0
        for tag_index, tag in enumerate(field.tags):
            if tag.code != 360:
                continue
            if index >= len(handles):
                break
            field.tags[tag_index] = dxftag(360, handles[index])
            index += 1

    def ensure_dynamic_block_extension_dict(self, block_record):
        return _ensure_dynamic_block_extension_dict(block_record)

    def delete_graph_stack(self, block_record) -> None:
        _delete_graph_stack(block_record)

    def add_raw_object(self, parent, key: str, dxftype: str, tags: list[tuple[int, object]]):
        raw = Tags([dxftag(0, dxftype), dxftag(330, parent.dxf.handle)])
        raw.extend(dxftag(code, value) for code, value in tags)
        obj = factory.load(ExtendedTags(raw), self.doc)
        factory.bind(obj, self.doc)
        self.doc.objects.add_object(obj)
        parent.add(key, obj)
        return obj

    @staticmethod
    def _map_raw_graph_value(
        value, entity_map: dict[str, DXFEntity], object_map: dict[str, DXFEntity]
    ):
        if isinstance(value, str):
            if value in object_map:
                return object_map[value].dxf.handle
            if value in entity_map:
                return entity_map[value].dxf.handle
        return value

    def new_raw_graph_object(self, dxftype: str, owner: str):
        if dxftype in ("XRECORD", "FIELD"):
            obj = factory.new(dxftype, dxfattribs={"owner": owner}, doc=self.doc)
            factory.bind(obj, self.doc)
            self.doc.objects.add_object(obj)
            return obj
        return _new_tag_storage_object(self.doc, dxftype, owner, [])

    def load_raw_graph_object(
        self,
        obj,
        owner: str,
        subclasses: list[list[tuple[int, object]]],
        xdata: list[list[tuple[int, object]]],
        entity_map: dict[str, DXFEntity],
        object_map: dict[str, DXFEntity],
    ):
        tags = [dxftag(0, obj.dxftype()), dxftag(5, obj.dxf.handle), dxftag(330, owner)]
        for subclass in subclasses:
            tags.extend(
                dxftag(
                    code,
                    self._map_raw_graph_value(value, entity_map, object_map)
                    if code in _RAW_GRAPH_HANDLE_CODES
                    else value,
                )
                for code, value in subclass
            )
        for xdata_tags in xdata:
            for code, value in xdata_tags:
                if isinstance(value, (tuple, list)):
                    tags.append(dxftag(code, value))
                else:
                    tags.append(DXFTag(code, value))
        xtags = ExtendedTags(tags)
        obj.load_tags(xtags, dxfversion=self.doc.dxfversion)
        if hasattr(obj, "store_tags"):
            obj.store_tags(xtags)
        return obj

    def set_raw_graph_reactors(
        self,
        obj,
        reactors: list[str],
        entity_map: dict[str, DXFEntity],
        object_map: dict[str, DXFEntity],
    ) -> None:
        mapped = [
            self._map_raw_graph_value(handle, entity_map, object_map)
            for handle in reactors
        ]
        mapped = [str(handle) for handle in mapped if handle]
        if mapped:
            obj.set_reactors(mapped)

    def refresh_entity_map_from_block(
        self,
        entity_map: dict[str, DXFEntity],
        block,
        entity_snapshots: Sequence[RawEntityExportSnapshot],
    ) -> None:
        for entity_snapshot, entity in zip(entity_snapshots, block):
            entity_text = (
                entity_snapshot.text
                if hasattr(entity_snapshot, "text")
                else entity_snapshot[0]
            )
            source_handle = ExtendedTags.from_text(entity_text).get_handle()
            if source_handle:
                entity_map[source_handle] = entity

    def mapped_handle(self, source_handle: str) -> str | None:
        if source_handle in self.source_entity_map:
            return self.source_entity_map[source_handle].dxf.handle
        if source_handle in self.source_object_map:
            return self.source_object_map[source_handle].dxf.handle
        global_mapping = getattr(self.doc, "_raw_object_handle_mapping", {})
        mapped = global_mapping.get(source_handle)
        if isinstance(mapped, str):
            return mapped
        return None

    @staticmethod
    def reorder_dictionary_entries(dictionary, ordered_keys: list[str]) -> None:
        data = dictionary._data
        if not data:
            return
        reordered = {}
        for key in ordered_keys:
            if key in data:
                reordered[key] = data[key]
        for key, value in data.items():
            if key not in reordered:
                reordered[key] = value
        dictionary._data = reordered

    def restore_layout_order(self, layout_order: list[str]) -> None:
        layouts = self.doc.layouts
        self.reorder_dictionary_entries(layouts._dxf_layouts, layout_order)
        ordered_layouts = {}
        for layout_name in layout_order:
            if layout_name in layouts:
                ordered_layouts[layout_key(layout_name)] = layouts.get(layout_name)
        for name_key, layout in layouts._layouts.items():
            if name_key not in ordered_layouts:
                ordered_layouts[name_key] = layout
        layouts._layouts = ordered_layouts

    def _register_field_tree_handles(self, objects: Sequence[DXFEntity]) -> None:
        handles = []
        for obj in objects:
            if obj.dxftype() == "FIELD" and obj.dxf.handle:
                handles.append(obj.dxf.handle)
        if not handles:
            return
        field_list = self.doc.objects.setup_field_list()
        existing = list(field_list.handles)
        for handle in handles:
            if handle not in existing:
                existing.append(handle)
        field_list.handles = existing

    def remap_root_xrecord_tags(self, tags: list[tuple[int, object]]) -> list[tuple[int, object]]:
        mapped = []
        for code, value in tags:
            if code == 330 and isinstance(value, str):
                if value in self.source_entity_map:
                    value = self.source_entity_map[value].dxf.handle
                elif value in self.source_object_map:
                    value = self.source_object_map[value].dxf.handle
            mapped.append((code, value))
        return mapped

    def register_recompose_table_styles(
        self, table_styles: list[tuple[str, str]]
    ) -> None:
        for source_handle, name in table_styles:
            style = self.doc.table_styles.get(name)
            if style is not None:
                self.source_entity_map[source_handle] = style

    def register_visualstyle_handles(
        self, visual_styles: list[tuple[str, str]]
    ) -> None:
        visualstyle_dict = self.doc.rootdict.get("ACAD_VISUALSTYLE")
        if visualstyle_dict is None:
            return
        for source_handle, key in visual_styles:
            style = visualstyle_dict.get(key)
            if style is not None:
                self.source_entity_map[source_handle] = style

    def remap_fieldlist_handles(
        self, handles: list[str], dangling: set[str]
    ) -> list[str]:
        mapped = []
        for handle in handles:
            if handle in self.source_object_map:
                target_handle = self._entity_handle(self.source_object_map[handle])
                mapped.append(target_handle if target_handle else handle)
            elif handle in self.source_entity_map:
                mapped.append(self.source_entity_map[handle].dxf.handle)
            elif handle in dangling:
                if handle not in self.dangling_handle_map:
                    new_handle = self.doc.entitydb.next_handle()
                    while (
                        new_handle in self.doc.entitydb
                        or new_handle in self.dangling_handle_map.values()
                    ):
                        new_handle = self.doc.entitydb.next_handle()
                    self.dangling_handle_map[handle] = new_handle
                mapped.append(self.dangling_handle_map[handle])
            else:
                mapped.append(handle)
        return mapped

    def remap_sortents_handles(
        self, handles: list[tuple[str, str]]
    ) -> list[tuple[str, str]]:
        mapped = []
        for handle, sort_handle in handles:
            if handle in self.source_entity_map:
                handle = self.source_entity_map[handle].dxf.handle
            if sort_handle in self.source_entity_map:
                sort_handle = self.source_entity_map[sort_handle].dxf.handle
            mapped.append((handle, sort_handle))
        return mapped

    def restore_mleader_style(
        self, name: str, xdata_tags: list[tuple[int, object]], source_reactors: list[str]
    ) -> None:
        style = self.doc.mleader_styles.get(name)
        if style is None:
            return
        if xdata_tags:
            style.set_xdata("ACAD_MLEADERVER", xdata_tags)
        reactors = []
        for handle in source_reactors:
            if handle == style.dxf.owner:
                reactors.append(style.dxf.owner)
            elif handle in self.source_entity_map:
                reactors.append(self.source_entity_map[handle].dxf.handle)
        if reactors:
            style.set_reactors(reactors)

    def restore_mleader_entity_styles(
        self, refs: list[tuple[str, str]]
    ) -> None:
        for source_handle, style_name in refs:
            entity = self.source_entity_map.get(source_handle)
            style = self.doc.mleader_styles.get(style_name)
            if entity is not None and style is not None:
                try:
                    entity.dxf.style_handle = style.dxf.handle
                except const.DXFAttributeError:
                    self._restore_raw_mleader_style_handle(entity, style.dxf.handle)

    @staticmethod
    def _restore_raw_mleader_style_handle(entity, style_handle: str) -> None:
        xtags = getattr(entity, "xtags", None)
        if xtags is None:
            return
        try:
            tags = xtags.get_subclass("AcDbMLeader")
        except const.DXFKeyError:
            return
        start = 0
        for index, tag in enumerate(tags):
            if tag.code == 301:  # END_CONTEXT_DATA, common tags follow.
                start = index + 1
                break
        for index in range(start, len(tags)):
            if tags[index].code == 340:
                tags[index] = dxftag(340, style_handle)
                return

    def rebuild_entity_xrecord_tree(
        self,
        host,
        dict_key: str,
        dict_order: list[str],
        root_handle: str,
        root_dxftype: str,
        root_subclasses: list[list[tuple[int, object]]],
        owned_specs: Sequence[OwnedObjectSpecData],
        entity_map: dict[str, DXFEntity],
    ) -> None:
        xdict = host.get_extension_dict() if host.has_extension_dict else host.new_extension_dict()
        if dict_key in xdict.dictionary:
            self.reorder_dictionary_entries(xdict.dictionary, dict_order)
            return
        object_map = {}
        root = self.new_raw_graph_object(root_dxftype, xdict.dictionary.dxf.handle)
        object_map[root_handle] = root
        self.source_object_map[root_handle] = root
        for spec in owned_specs:
            mapped_owner = self._map_raw_graph_value(spec["owner"], entity_map, object_map)
            object_map[spec["handle"]] = self.new_raw_graph_object(
                spec["dxftype"], mapped_owner
            )
            self.source_object_map[spec["handle"]] = object_map[spec["handle"]]
        self.load_raw_graph_object(
            root,
            xdict.dictionary.dxf.handle,
            root_subclasses,
            [],
            entity_map,
            object_map,
        )
        xdict.dictionary.add(dict_key, root)
        for spec in owned_specs:
            mapped_owner = self._map_raw_graph_value(spec["owner"], entity_map, object_map)
            self.load_raw_graph_object(
                object_map[spec["handle"]],
                mapped_owner,
                spec["subclasses"],
                [],
                entity_map,
                object_map,
            )
        self.reorder_dictionary_entries(xdict.dictionary, dict_order)
        self._register_field_tree_handles(list(object_map.values()))

    def swap_raw_graphic_entity(
        self,
        block,
        source_handle: str,
        source_owner: str,
        source_xdict_handle: str,
        source_resource_handles: list[tuple[str, str]],
        raw_tags: list[tuple[int, object]],
        source_xdata: list[list[tuple[int, object]]],
    ) -> None:
        old = self.source_entity_map[source_handle]
        xdict_handle = ""
        if source_xdict_handle and old.has_extension_dict:
            xdict_handle = old.get_extension_dict().dictionary.dxf.handle
        resource_handle_map = {}
        for source_value, attr_name in source_resource_handles:
            target_value = old.dxf.get(attr_name)
            if target_value:
                resource_handle_map[source_value] = target_value
        mapped = [dxftag(0, old.dxftype()), dxftag(5, old.dxf.handle), dxftag(330, old.dxf.owner)]
        for code, value in raw_tags:
            if code in _RAW_GRAPHIC_RESOURCE_CODES and isinstance(value, str):
                if value in resource_handle_map:
                    value = resource_handle_map[value]
                elif value == source_handle:
                    value = old.dxf.handle
                elif value == source_owner:
                    value = old.dxf.owner
                elif source_xdict_handle and value == source_xdict_handle and xdict_handle:
                    value = xdict_handle
            if code in _BINARY_DATA_CODES and isinstance(value, str):
                mapped.append(dxftag(code, bytes.fromhex(value)))
            elif code in _BINARY_DATA_CODES or isinstance(value, (tuple, list)):
                mapped.append(dxftag(code, value))
            else:
                mapped.append(DXFTag(code, value))
        new = DXFTagStorage.load(ExtendedTags(Tags(mapped)), self.doc)
        new.doc = self.doc
        new.appdata = old.appdata
        new.reactors = old.reactors
        new.xdata = None
        for xdata_tags in source_xdata:
            appid = next((value for code, value in xdata_tags if code == 1001), None)
            if not isinstance(appid, str):
                continue
            payload = []
            for code, value in xdata_tags:
                if code == 1001:
                    continue
                if code == 1005 and isinstance(value, str):
                    mapped_value = self.mapped_handle(value)
                    if mapped_value is not None:
                        value = mapped_value
                    elif value != "0" and self.doc.entitydb.get(value) is None:
                        value = "0"
                payload.append((code, value))
            new.set_xdata(appid, payload)
        if old.has_extension_dict:
            new.extension_dict = old.extension_dict
        index = block.block_record.entity_space.entities.index(old)
        block.block_record.entity_space.entities[index] = new
        self.doc.entitydb._database[old.dxf.handle] = new
        self.source_entity_map[source_handle] = new

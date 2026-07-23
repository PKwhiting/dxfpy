# Copyright (c) 2011-2022, Manfred Moitzi
# License: MIT License
from __future__ import annotations
from typing import TYPE_CHECKING, Iterator, Iterable, Union, cast, Optional, Sequence
from collections import Counter, OrderedDict
from io import StringIO
import logging

from dxfpy.lldxf.const import DXFStructureError, DXF2004, DXF2000, DXFKeyError
from dxfpy.lldxf.extendedtags import ExtendedTags
from dxfpy.entities.dxfclass import DXFClass
from dxfpy.entities.dxfentity import DXFEntity, DXFTagStorage
from dxfpy.entities import factory
from dxfpy.lldxf.tagwriter import TagWriter

if TYPE_CHECKING:
    from dxfpy.document import Drawing
    from dxfpy.lldxf.tagwriter import AbstractTagWriter

logger = logging.getLogger("dxfpy")

# name: cpp_class_name (2), app_name (3), flags(90), was_a_proxy (280),
# is_an_entity (281)
# Multiple entries for 'name' are possible and supported, ClassSection stores
# entries with key: (name, cpp_class_name).
# 0 <ctrl> CLASS
# 1 <str> MPOLYGON
# 2 <str> AcDbMPolygon
# 3 <str> "AcMPolygonObj15|Version(1.0.0.0) Product Desc: Object enabler for the AcDbMPolyg ... odesk.com"
# 90 <int> 3071, b101111111111
# 280 <int> 0
# 281 <int> 1
CLASS_DEFINITIONS = {
    "ACDBDICTIONARYWDFLT": [
        "AcDbDictionaryWithDefault",
        "ObjectDBX Classes",
        0,
        0,
        0,
    ],
    "SUN": ["AcDbSun", "SCENEOE", 1153, 0, 0],
    "DICTIONARYVAR": ["AcDbDictionaryVar", "ObjectDBX Classes", 0, 0, 0],
    "TABLESTYLE": ["AcDbTableStyle", "ObjectDBX Classes", 4095, 0, 0],
    "MATERIAL": ["AcDbMaterial", "ObjectDBX Classes", 1153, 0, 0],
    "VISUALSTYLE": ["AcDbVisualStyle", "ObjectDBX Classes", 4095, 0, 0],
    "SCALE": ["AcDbScale", "ObjectDBX Classes", 1153, 0, 0],
    "MLEADERSTYLE": ["AcDbMLeaderStyle", "ACDB_MLEADERSTYLE_CLASS", 4095, 0, 0],
    "MLEADER": ["AcDbMLeader", "ACDB_MLEADER_CLASS", 3071, 0, 1],
    "MULTILEADER": ["AcDbMLeader", "ACDB_MLEADER_CLASS", 1025, 0, 1],
    "MPOLYGON": ["AcDbMPolygon", "AcMPolygonObj15", 1025, 0, 1],
    "CELLSTYLEMAP": ["AcDbCellStyleMap", "ObjectDBX Classes", 1152, 0, 0],
    "EXACXREFPANELOBJECT": ["ExAcXREFPanelObject", "EXAC_ESW", 1025, 0, 0],
    "NPOCOLLECTION": [
        "AcDbImpNonPersistentObjectsCollection",
        "ObjectDBX Classes",
        1153,
        0,
        0,
    ],
    "LAYER_INDEX": ["AcDbLayerIndex", "ObjectDBX Classes", 0, 0, 0],
    "SPATIAL_INDEX": ["AcDbSpatialIndex", "ObjectDBX Classes", 0, 0, 0],
    "IDBUFFER": ["AcDbIdBuffer", "ObjectDBX Classes", 0, 0, 0],
    "DIMASSOC": ["AcDbDimAssoc", "AcDbDimAssoc", 0, 0, 0],
    "ACDBSECTIONVIEWSTYLE": [
        "AcDbSectionViewStyle",
        "ObjectDBX Classes",
        1025,
        0,
        0,
    ],
    "ACDBDETAILVIEWSTYLE": [
        "AcDbDetailViewStyle",
        "ObjectDBX Classes",
        1025,
        0,
        0,
    ],
    "IMAGEDEF": ["AcDbRasterImageDef", "ISM", 0, 0, 0],
    "RASTERVARIABLES": ["AcDbRasterVariables", "ISM", 0, 0, 0],
    "IMAGEDEF_REACTOR": ["AcDbRasterImageDefReactor", "ISM", 1, 0, 0],
    "IMAGE": ["AcDbRasterImage", "ISM", 2175, 0, 1],
    "PDFDEFINITION": ["AcDbPdfDefinition", "ObjectDBX Classes", 1153, 0, 0],
    "PDFUNDERLAY": ["AcDbPdfReference", "ObjectDBX Classes", 4095, 0, 1],
    "DWFDEFINITION": ["AcDbDwfDefinition", "ObjectDBX Classes", 1153, 0, 0],
    "DWFUNDERLAY": ["AcDbDwfReference", "ObjectDBX Classes", 1153, 0, 1],
    "DGNDEFINITION": ["AcDbDgnDefinition", "ObjectDBX Classes", 1153, 0, 0],
    "DGNUNDERLAY": ["AcDbDgnReference", "ObjectDBX Classes", 1153, 0, 1],
    "MENTALRAYRENDERSETTINGS": [
        "AcDbMentalRayRenderSettings",
        "SCENEOE",
        1024,
        0,
        0,
    ],
    "ACDBPLACEHOLDER": ["AcDbPlaceHolder", "ObjectDBX Classes", 0, 0, 0],
    "LAYOUT": ["AcDbLayout", "ObjectDBX Classes", 0, 0, 0],
    "SURFACE": ["AcDbSurface", "ObjectDBX Classes", 4095, 0, 1],
    "EXTRUDEDSURFACE": ["AcDbExtrudedSurface", "ObjectDBX Classes", 4095, 0, 1],
    "LOFTEDSURFACE": ["AcDbLoftedSurface", "ObjectDBX Classes", 0, 0, 1],
    "REVOLVEDSURFACE": ["AcDbRevolvedSurface", "ObjectDBX Classes", 0, 0, 1],
    "SWEPTSURFACE": ["AcDbSweptSurface", "ObjectDBX Classes", 0, 0, 1],
    "PLANESURFACE": ["AcDbPlaneSurface", "ObjectDBX Classes", 4095, 0, 1],
    "NURBSSURFACE": ["AcDbNurbSurface", "ObjectDBX Classes", 4095, 0, 1],
    "ACDBASSOCEXTRUDEDSURFACEACTIONBODY": [
        "AcDbAssocExtrudedSurfaceActionBody",
        "ObjectDBX Classes",
        1025,
        0,
        0,
    ],
    "ACDBASSOCLOFTEDSURFACEACTIONBODY": [
        "AcDbAssocLoftedSurfaceActionBody",
        "ObjectDBX Classes",
        1025,
        0,
        0,
    ],
    "ACDBASSOCREVOLVEDSURFACEACTIONBODY": [
        "AcDbAssocRevolvedSurfaceActionBody",
        "ObjectDBX Classes",
        1025,
        0,
        0,
    ],
    "ACDBASSOCSWEPTSURFACEACTIONBODY": [
        "AcDbAssocSweptSurfaceActionBody",
        "ObjectDBX Classes",
        1025,
        0,
        0,
    ],
    "HELIX": ["AcDbHelix", "ObjectDBX Classes", 4095, 0, 1],
    "WIPEOUT": [
        "AcDbWipeout",
        "WipeOut|Product Desc: Object Enabler for WipeOut entity | Company: Autodesk, Inc. | WEB Address: www.autodesk.com",
        2175,
        0,
        1,
    ],
    "WIPEOUTVARIABLES": ["AcDbWipeoutVariables", "WipeOut", 0, 0, 0],
    "FIELD": ["AcDbField", "ObjectDBX Classes", 1152, 0, 0],
    "FIELDLIST": ["AcDbFieldList", "ObjectDBX Classes", 1152, 0, 0],
    "DBCOLOR": ["AcDbColor", "ObjectDBX Classes", 0, 0, 0],
    "ACAD_EVALUATION_GRAPH": ["AcDbEvalGraph", "ObjectDBX Classes", 1153, 0, 0],
    "ACAECUSTOBJ": ["AcAeEditorObj", "AcAeEditorObj", 1024, 0, 0],
    "BLOCKBASEPOINTPARAMETER": ["AcDbBlockBasepointParameter", "ObjectDBX Classes", 1153, 0, 0],
    "BASEPOINTPARAMETERENTITY": [
        "AcDbBlockBasepointParameterEntity",
        "ObjectDBX Classes",
        1025,
        0,
        1,
    ],
    "BLOCKLINEARPARAMETER": ["AcDbBlockLinearParameter", "ObjectDBX Classes", 1153, 0, 0],
    "LINEARPARAMETERENTITY": [
        "AcDbBlockLinearParameterEntity",
        "ObjectDBX Classes",
        1025,
        0,
        1,
    ],
    "BLOCKLINEARGRIP": ["AcDbBlockLinearGrip", "ObjectDBX Classes", 1153, 0, 0],
    "LINEARGRIPENTITY": [
        "AcDbBlockLinearGripEntity",
        "ObjectDBX Classes",
        1025,
        0,
        1,
    ],
    "BLOCKLOOKUPPARAMETER": ["AcDbBlockLookupParameter", "ObjectDBX Classes", 1153, 0, 0],
    "BLOCKLOOKUPGRIP": ["AcDbBlockLookupGrip", "ObjectDBX Classes", 1153, 0, 0],
    "BLOCKGRIPLOCATIONCOMPONENT": ["AcDbBlockGripExpr", "ObjectDBX Classes", 1153, 0, 0],
    "LOOKUPGRIPENTITY": ["AcDbBlockLookupGripEntity", "ObjectDBX Classes", 1025, 0, 1],
    "ACAEEEMGROBJ": ["AcAeEEMgrObj", "AcAeEEMgrObj", 1024, 0, 0],
    "LOOKUPPARAMETERENTITY": ["AcDbBlockLookupParameterEntity", "ObjectDBX Classes", 1025, 0, 1],
    "ACDB_DYNAMICBLOCKPURGEPREVENTER_VERSION": ["AcDbDynamicBlockPurgePreventer", "ObjectDBX Classes", 1153, 0, 0],
    "BLOCKLOOKUPACTION": ["AcDbBlockLookupAction", "ObjectDBX Classes", 1153, 0, 0],
    "BLOCKFLIPACTION": ["AcDbBlockFlipAction", "ObjectDBX Classes", 1153, 0, 0],
    "BLOCKFLIPGRIP": ["AcDbBlockFlipGrip", "ObjectDBX Classes", 1153, 0, 0],
    "BLOCKFLIPPARAMETER": ["AcDbBlockFlipParameter", "ObjectDBX Classes", 1153, 0, 0],
    "BLOCKMOVEACTION": ["AcDbBlockMoveAction", "ObjectDBX Classes", 1153, 0, 0],
    "BLOCKPOINTPARAMETER": ["AcDbBlockPointParameter", "ObjectDBX Classes", 1153, 0, 0],
    "BLOCKXYGRIP": ["AcDbBlockXYGrip", "ObjectDBX Classes", 1153, 0, 0],
    "BLOCKSTRETCHACTION": ["AcDbBlockStretchAction", "ObjectDBX Classes", 1153, 0, 0],
    "STRETCHACTIONENTITY": [
        "AcDbBlockStretchActionEntity",
        "ObjectDBX Classes",
        1025,
        0,
        1,
    ],
    "LOOKUPACTIONENTITY": ["AcDbBlockLookupActionEntity", "ObjectDBX Classes", 1025, 0, 1],
    "BLOCKVISIBILITYPARAMETER": ["AcDbBlockVisibilityParameter", "ObjectDBX Classes", 1153, 0, 0],
    "BLOCKVISIBILITYGRIP": ["AcDbBlockVisibilityGrip", "ObjectDBX Classes", 1153, 0, 0],
    "VISIBILITYGRIPENTITY": ["AcDbBlockVisibilityGripEntity", "ObjectDBX Classes", 1025, 0, 1],
    "VISIBILITYPARAMETERENTITY": ["AcDbBlockVisibilityParameterEntity", "ObjectDBX Classes", 1025, 0, 1],
    "ACDB_BLOCKREPRESENTATION_DATA": ["AcDbBlockRepresentationData", "ObjectDBX Classes", 1153, 0, 0],
    "BLOCKPROPERTIESTABLE": ["AcDbBlockPropertiesTable", "ObjectDBX Classes", 1153, 0, 0],
    "BLOCKPROPERTIESTABLEGRIP": ["AcDbBlockPropertiesTableGrip", "ObjectDBX Classes", 1153, 0, 0],
    "BLOCKPROPERTIESTABLEGRIPENTITY": ["AcDbBlockPropertiesTableGripEntity", "ObjectDBX Classes", 1025, 0, 1],
    "BLOCKPROPERTIESTABLEENTITY": ["AcDbBlockPropertiesTableEntity", "ObjectDBX Classes", 1025, 0, 1],
    "ACDB_DYNAMICBLOCKPROXYNODE": ["AcDbDynamicBlockProxyNode", "ObjectDBX Classes", 1153, 0, 0],
    "ACDBASSOCNETWORK": ["AcDbAssocNetwork", "ObjectDBX Classes", 1025, 0, 0],
    "BLOCKUSERPARAMETER": ["AcDbBlockUserParameter", "ObjectDBX Classes", 1153, 0, 0],
    "ACDBASSOCVARIABLE": ["AcDbAssocVariable", "ObjectDBX Classes", 1025, 0, 0],
    "ACDB_MTEXTATTRIBUTEOBJECTCONTEXTDATA_CLASS": ["AcDbMTextAttributeObjectContextData", "ObjectDBX Classes", 1153, 0, 0],
    "GEODATA": ["AcDbGeoData", "ObjectDBX Classes", 4095, 0, 0],
    "SORTENTSTABLE": ["AcDbSortentsTable", "ObjectDBX Classes", 0, 0, 0],
    "ACAD_TABLE": ["AcDbTable", "ObjectDBX Classes", 1025, 0, 1],
    "TABLECONTENT": ["AcDbTableContent", "ObjectDBX Classes", 1152, 0, 0],
    "TABLEGEOMETRY": ["AcDbTableGeometry", "ObjectDBX Classes", 1152, 0, 0],
    "ARC_DIMENSION": ["AcDbArcDimension", "ObjectDBX Classes", 1025, 0, 1],
    "LARGE_RADIAL_DIMENSION": [
        "AcDbRadialDimensionLarge",
        "ObjectDBX Classes",
        1025,
        0,
        1,
    ],
}

REQ_R2000 = [
    "ACDBDICTIONARYWDFLT",
    "VISUALSTYLE",
    "MATERIAL",
    "SCALE",
    "TABLESTYLE",
    "MLEADERSTYLE",
    "DICTIONARYVAR",
    "CELLSTYLEMAP",
    "ACDBDETAILVIEWSTYLE",
    "ACDBSECTIONVIEWSTYLE",
    "RASTERVARIABLES",
]

REQ_R2004 = [
    "ACDBDICTIONARYWDFLT",
    "VISUALSTYLE",
    "MATERIAL",
    "SCALE",
    "TABLESTYLE",
    "MLEADERSTYLE",
    "DICTIONARYVAR",
    "CELLSTYLEMAP",
    "ACDBDETAILVIEWSTYLE",
    "ACDBSECTIONVIEWSTYLE",
    "RASTERVARIABLES",
]

REQUIRED_CLASSES = {
    DXF2000: REQ_R2000,
    DXF2004: REQ_R2004,
}


class ClassesSection:
    def __init__(
        self,
        doc: Optional[Drawing] = None,
        entities: Optional[Iterable[DXFEntity]] = None,
    ):
        # Multiple entries for 'name' possible -> key is (name, cpp_class_name)
        # DXFClasses are not stored in the entities database, because CLASS has
        # no handle.
        self.classes: dict[tuple[str, str], DXFClass] = OrderedDict()
        self.doc = doc
        self._raw_class_texts_override: Optional[tuple[str, ...]] = None
        if entities is not None:
            self.load(iter(entities))

    def __iter__(self) -> Iterator[DXFClass]:
        return (cls for cls in self.classes.values())

    def load(self, entities: Iterator[DXFEntity]) -> None:
        section_head = cast(DXFTagStorage, next(entities))

        if section_head.dxftype() != "SECTION" or section_head.base_class[1] != (
            2,
            "CLASSES",
        ):
            raise DXFStructureError("Critical structure error in CLASSES section.")

        for cls_entity in entities:
            if isinstance(cls_entity, DXFClass):
                self.register(cls_entity)
            else:
                logger.warning(
                    f"Ignored invalid DXF entity type '{cls_entity.dxftype()}'"
                    f" in section CLASSES."
                )

    def register(
        self, classes: Optional[Union[DXFClass, Iterable[DXFClass]]] = None
    ) -> None:
        if classes is None:
            return

        if isinstance(classes, DXFClass):
            classes = (classes,)

        for dxfclass in classes:
            key = dxfclass.key
            if key not in self.classes:
                self.classes[key] = dxfclass

    def add_class(self, name: str):
        """Register a known class by `name`."""
        if name not in CLASS_DEFINITIONS:
            return
        cls_data = CLASS_DEFINITIONS[name]
        cls = DXFClass.new(doc=self.doc)
        cpp, app, flags, proxy, entity = cls_data
        cls.update_dxf_attribs(
            {
                "name": name,
                "cpp_class_name": cpp,
                "app_name": app,
                "flags": flags,
                "was_a_proxy": proxy,
                "is_an_entity": entity,
            }
        )
        self.register(cls)

    def get(self, name: str) -> DXFClass:
        """Returns the first class matching `name`.

        Storage key is the ``(name, cpp_class_name)`` tuple, because there are
        some classes with the same :attr:`name` but different
        :attr:`cpp_class_names`.

        """
        for cls in self.classes.values():
            if cls.dxf.name == name:
                return cls
        raise DXFKeyError(name)

    def add_required_classes(self, dxfversion: str) -> None:
        """Add all required CLASS definitions for the specified DXF version."""
        names = REQUIRED_CLASSES.get(dxfversion, REQ_R2004)
        for name in names:
            self.add_class(name)

        if self.doc is None:  # testing environment SUT
            return

        dxf_types_in_use = self.doc.entitydb.dxf_types_in_use()
        if "SUN" in dxf_types_in_use:
            self.add_class("SUN")
        if "MENTALRAYRENDERSETTINGS" in dxf_types_in_use:
            self.add_class("MENTALRAYRENDERSETTINGS")
        if "IMAGE" in dxf_types_in_use:
            self.add_class("IMAGE")
            self.add_class("IMAGEDEF")
            self.add_class("IMAGEDEF_REACTOR")
        if "FIELD" in dxf_types_in_use:
            self.add_class("FIELD")
        if "FIELDLIST" in dxf_types_in_use:
            self.add_class("FIELDLIST")
        if {"MULTILEADER", "MLEADER"}.intersection(dxf_types_in_use):
            self.add_class("MULTILEADER")
        dynamic_visibility_types = {
            "ACAD_EVALUATION_GRAPH",
            "BLOCKBASEPOINTPARAMETER",
            "BLOCKLINEARPARAMETER",
            "BLOCKLINEARGRIP",
            "BLOCKVISIBILITYPARAMETER",
            "BLOCKVISIBILITYGRIP",
            "BLOCKSTRETCHACTION",
            "BLOCKGRIPLOCATIONCOMPONENT",
            "ACDB_DYNAMICBLOCKPURGEPREVENTER_VERSION",
            "ACDB_BLOCKREPRESENTATION_DATA",
        }
        if dynamic_visibility_types.intersection(dxf_types_in_use):
            for name in (
                "ACAD_EVALUATION_GRAPH",
                "ACAECUSTOBJ",
                "BLOCKBASEPOINTPARAMETER",
                "BASEPOINTPARAMETERENTITY",
                "BLOCKLINEARPARAMETER",
                "LINEARPARAMETERENTITY",
                "BLOCKLINEARGRIP",
                "LINEARGRIPENTITY",
                "BLOCKLOOKUPPARAMETER",
                "BLOCKLOOKUPGRIP",
                "BLOCKGRIPLOCATIONCOMPONENT",
                "LOOKUPGRIPENTITY",
                "ACAEEEMGROBJ",
                "LOOKUPPARAMETERENTITY",
                "ACDB_DYNAMICBLOCKPURGEPREVENTER_VERSION",
                "BLOCKLOOKUPACTION",
                "BLOCKSTRETCHACTION",
                "STRETCHACTIONENTITY",
                "LOOKUPACTIONENTITY",
                "BLOCKVISIBILITYPARAMETER",
                "BLOCKVISIBILITYGRIP",
                "VISIBILITYGRIPENTITY",
                "VISIBILITYPARAMETERENTITY",
                "ACDB_BLOCKREPRESENTATION_DATA",
                "BLOCKPROPERTIESTABLE",
                "BLOCKPROPERTIESTABLEGRIP",
                "BLOCKPROPERTIESTABLEGRIPENTITY",
                "BLOCKPROPERTIESTABLEENTITY",
                "ACDB_DYNAMICBLOCKPROXYNODE",
                "ACDBASSOCNETWORK",
                "BLOCKUSERPARAMETER",
                "ACDBASSOCVARIABLE",
                "ACDB_MTEXTATTRIBUTEOBJECTCONTEXTDATA_CLASS",
            ):
                self.add_class(name)
        if "PDFUNDERLAY" in dxf_types_in_use:
            self.add_class("PDFDEFINITION")
            self.add_class("PDFUNDERLAY")
        if "DWFUNDERLAY" in dxf_types_in_use:
            self.add_class("DWFDEFINITION")
            self.add_class("DWFUNDERLAY")
        if "DGNUNDERLAY" in dxf_types_in_use:
            self.add_class("DGNDEFINITION")
            self.add_class("DGNUNDERLAY")
        if "EXTRUDEDSURFACE" in dxf_types_in_use:
            self.add_class("EXTRUDEDSURFACE")
            self.add_class("ACDBASSOCEXTRUDEDSURFACEACTIONBODY")
        if "LOFTEDSURFACE" in dxf_types_in_use:
            self.add_class("LOFTEDSURFACE")
            self.add_class("ACDBASSOCLOFTEDSURFACEACTIONBODY")
        if "REVOLVEDSURFACE" in dxf_types_in_use:
            self.add_class("REVOLVEDSURFACE")
            self.add_class("ACDBASSOCREVOLVEDSURFACEACTIONBODY")
        if "SWEPTSURFACE" in dxf_types_in_use:
            self.add_class("SWEPTSURFACE")
            self.add_class("ACDBASSOCSWEPTSURFACEACTIONBODY")

        skip_implicit = {"LAYOUT", "ACDBPLACEHOLDER"}
        for dxftype in dxf_types_in_use:
            if dxftype in skip_implicit:
                continue
            self.add_class(dxftype)

    def export_dxf(self, tagwriter: AbstractTagWriter) -> None:
        """Export DXF tags. (internal API)"""
        tagwriter.write_str("  0\nSECTION\n  2\nCLASSES\n")
        if self._raw_class_texts_override is not None:
            for text in self._raw_class_texts_override:
                tagwriter.write_str(text)
        else:
            for dxfclass in self.classes.values():
                dxfclass.export_dxf(tagwriter)
        tagwriter.write_str("  0\nENDSEC\n")

    def update_instance_counters(self) -> None:
        """Update CLASS instance counter for all registered classes, requires
        DXF R2004+.
        """
        assert self.doc is not None
        if self.doc.dxfversion < DXF2004:
            return  # instance counter not supported
        counter: dict[str, int] = Counter()
        # count all entities in the entity database
        for entity in self.doc.entitydb.values():
            counter[entity.dxftype()] += 1

        for dxfclass in self.classes.values():
            dxfclass.dxf.instance_count = counter[dxfclass.dxf.name]


def snapshot_raw_classes(section: ClassesSection) -> tuple[str, ...]:
    texts: list[str] = []
    dxfversion = section.doc.dxfversion if section.doc is not None else DXF2004
    for dxfclass in section.classes.values():
        stream = StringIO()
        dxfclass.export_dxf(TagWriter(stream, dxfversion=dxfversion))
        texts.append(stream.getvalue())
    return tuple(texts)


def restore_raw_classes(section: ClassesSection, snapshot: Sequence[str]) -> None:
    classes: dict[tuple[str, str], DXFClass] = OrderedDict()
    for text in snapshot:
        entity = factory.load(ExtendedTags.from_text(text), section.doc)
        if isinstance(entity, DXFClass):
            classes[entity.key] = entity
    section.classes = classes
    section._raw_class_texts_override = tuple(snapshot)

.. _tut_fields:

Tutorial for Fields
===================

The field API can create and preserve object-backed AutoCAD-style field graphs
for several host entities. The generated DXF stores the field definition and a
cached display value; AutoCAD or another CAD application is still responsible for
evaluating fields after the drawing is opened.

Single-call field templates
---------------------------

The primary authoring API accepts readable ``{{name}}`` placeholders. Plain
values create or update custom drawing properties automatically, and field
trees are registered in ``ACAD_FIELDLIST`` by default:

.. code-block:: python

    import dxfpy

    doc = dxfpy.new("R2018")
    mtext = doc.modelspace().add_mtext("")
    mtext.set_field(
        "Client: {{ClientName}}",
        values={"ClientName": "Example Solar"},
    )

Drawing-property templates require DXF R2004 or later. Templates containing
only drawing-variable or object-property sources require DXF R2000 or later.
Use the MTEXT paragraph code ``\\P`` for line breaks; literal carriage-return
and newline characters are rejected because they cannot be stored safely in
ASCII DXF tags.

Arithmetic inside one placeholder creates a calculated field without exposing
native AutoCAD evaluator or child-index syntax:

.. code-block:: python

    mtext.set_field(
        "SYSTEM SIZE: {{ModuleCount * (ModuleWatts / 1000)}} kW",
        values={"ModuleCount": 20, "ModuleWatts": 410},
    )

Supported operators are ``+``, ``-``, ``*``, ``/``, unary ``+`` and ``-``,
parentheses, and numeric literals. Expressions are parsed by a restricted
validator and are never passed to Python ``eval()``.

Use public source helpers when a name refers to a drawing variable or an entity
property instead of a custom drawing property:

.. code-block:: python

    from dxfpy.fields import drawing_variable, object_property

    line = doc.modelspace().add_line((0, 0), (10, 0))
    width = doc.modelspace().add_line((0, 0), (0, 5))
    mtext.set_field(
        "SHEET {{sheet}} - AREA {{length * width}}",
        values={
            "sheet": drawing_variable("CTab", display="A1"),
            "length": object_property(line, "Length"),
            "width": object_property(width, "Length"),
        },
    )

Omit ``values`` to reference custom drawing properties already stored in
``doc.header.custom_vars``. Missing names, unused supplied values, malformed
expressions, non-numeric operands, and invalid object targets are rejected
before the hosted field is replaced.

Public source helpers
---------------------

.. module:: dxfpy.fields

.. autofunction:: drawing_property

.. autofunction:: drawing_variable

.. autofunction:: object_property

.. autoclass:: DrawingProperty

.. autoclass:: DrawingVariable

.. autoclass:: ObjectProperty

Supported field hosts
---------------------

- :class:`~ezdxf.entities.MText`
- :class:`~ezdxf.entities.Text`
- :class:`~ezdxf.entities.MultiLeader` with MTEXT content
- :class:`~ezdxf.entities.AttDef`
- :class:`~ezdxf.entities.Attrib`
- :class:`~ezdxf.entities.Insert` helper methods that create field-backed
  attached ``ATTRIB`` entities
- ``ACAD_TABLE`` text cells

Supported field families
------------------------

- ``AcVar``
- ``DWGPROPS`` via the observed ``AcVar CustomDP.<Name>`` pattern
- ``AcObjProp``
- ``AcExpr`` expressions composed from child fields
- linked ``_text`` wrapper fields used by text-like hosts

Support model
-------------

There are two different support layers:

- structural DXF support for object-backed ``FIELD`` and ``FIELDLIST`` objects
- selective high-level authoring support for specific field hosts and specific
  field/property cases

This means `ezdxf` can build and preserve object-backed field graphs in general,
but only a validated subset of field families and object-property cases are
exposed by the current convenience API.

`ezdxf` does not evaluate fields by itself. AutoCAD is still the authoritative
field evaluator in the current workflow.

Host / family matrix
--------------------

.. list-table::
    :header-rows: 1

    * - Host
      - ``AcVar``
      - ``DWGPROPS``
      - ``AcObjProp``
      - ``AcExpr``
      - Notes
    * - :class:`~ezdxf.entities.MText`
      - yes
      - yes
      - yes
      - yes
      - object-backed host with dedicated layout helpers
    * - :class:`~ezdxf.entities.Text`
      - yes
      - yes
      - yes
      - yes
      - also covers ``ATTRIB`` and ``ATTDEF`` entity-level helpers
    * - :class:`~ezdxf.entities.MultiLeader`
      - yes
      - yes
      - yes
      - yes
      - MTEXT-content leaders only
    * - :class:`~ezdxf.entities.AttDef`
      - yes
      - yes
      - yes
      - yes
      - stand-alone attribute definitions
    * - :class:`~ezdxf.entities.Attrib`
      - yes
      - yes
      - yes
      - yes
      - attached to ``INSERT`` entities
    * - :class:`~ezdxf.entities.Insert`
      - yes
      - yes
      - yes
      - no
      - convenience methods create attached field-backed ``ATTRIB`` entities
    * - ``ACAD_TABLE`` text cell
      - yes
      - yes
      - yes
      - yes
      - field is attached to the semantic cell and visible geometry MTEXT

Object-property support matrix
------------------------------

.. list-table::
    :header-rows: 1

    * - Entity
      - Supported properties
      - Notes
    * - ``LINE``
      - ``Length``
      - exact
    * - ``ARC``
      - ``Radius``, ``Length``, ``ArcLength``, ``Area``
      - exact
    * - ``CIRCLE``
      - ``Radius``, ``Diameter``, ``Circumference``, ``Area``
      - exact
    * - ``ELLIPSE``
      - ``MajorRadius``, ``MinorRadius``, ``Area``
      - exact for full ellipses and ellipse arcs
    * - ``SPLINE``
      - ``Area``
      - planar splines only; approximation-based
    * - ``POLYLINE``
      - ``Length``, ``Area``
      - 2D polylines with straight or circular-arc segments
    * - ``POLYLINE``
      - ``Length``
      - 3D polylines only
    * - ``LWPOLYLINE``
      - ``Length``, ``Area``
      - 2D polylines with straight or circular-arc segments
    * - ``HATCH``
      - ``Area``
      - polyline boundary paths, simple non-bulged hole loops, and single line/arc/ellipse/spline edge paths

Drawing property fields
-----------------------

DWGPROPS-backed fields are currently authored through the observed
``CustomDP.<Name>`` namespace and also populate the underlying drawing property
store via :attr:`doc.header.custom_vars`.

Example:

.. code-block:: python

    import ezdxf

    doc = ezdxf.new("R2018")
    msp = doc.modelspace()

    msp.add_mtext_dwgprops_field(
        "ProjectCode",
        text="VALUE-123",
        dxfattribs={"insert": (0, 0, 0)},
        register_field_list=True,
    )

Object property fields
----------------------

The current automatic inference support is intentionally small and explicit.

Supported inferred object-property cases:

- ``LINE.Length``
- ``POLYLINE.Length`` for 3D polylines
- ``ELLIPSE.MajorRadius``
- ``ELLIPSE.MinorRadius``
- ``ELLIPSE.Area``
- ``ARC.Radius``
- ``ARC.Length``
- ``ARC.ArcLength``
- ``ARC.Area``
- ``SPLINE.Area`` for planar splines
- ``HATCH.Area`` for polyline boundary paths, including simple hole loops, and for single edge paths made of line/arc, ellipse, or spline edges
- ``POLYLINE.Length`` for 2D polylines with straight or circular-arc segments
- ``POLYLINE.Area`` for 2D polylines with straight or circular-arc segments
- ``LWPOLYLINE.Length`` for 2D polylines with straight or circular-arc segments
- ``LWPOLYLINE.Area`` for 2D polylines with straight or circular-arc segments
- ``CIRCLE.Radius``
- ``CIRCLE.Diameter``
- ``CIRCLE.Circumference``
- ``CIRCLE.Area``

Example:

.. code-block:: python

    import ezdxf

    doc = ezdxf.new("R2018")
    msp = doc.modelspace()

    line = msp.add_line((0, 0), (10, 0))
    msp.add_mtext_acobjprop_field(
        line,
        "Length",
        dxfattribs={"insert": (0, 0, 0)},
        register_field_list=True,
    )

Expression fields
-----------------

``AcExpr`` fields combine child fields by using ``%<\\_FldIdx n>%`` placeholders
inside the expression string. The current helper copies the provided child field
objects into the document and links them to the expression field.

Example:

.. code-block:: python

    from ezdxf.entities import Field

    circle = msp.add_circle((0, 0), radius=3)
    line_field = Field()
    line_field.set_acobjprop(line, "Length", value=10.0, display="10.0000")
    circle_field = Field()
    circle_field.set_acobjprop(circle, "Radius", value=3.0, display="3.0000")

    msp.add_mtext_acexpr_field(
        "(%<\\_FldIdx 0>%+%<\\_FldIdx 1>%)",
        [line_field, circle_field],
        value=13.0,
        display="13.0000",
        dxfattribs={"insert": (0, 8, 0)},
        register_field_list=True,
    )

Table cell fields
-----------------

``ACAD_TABLE`` text cells support the same common field families. The field is
stored in the semantic table cell and synchronized to the generated table
geometry MTEXT so that CAD applications display the cached value immediately.

Example:

.. code-block:: python

    table = msp.add_table(
        (0, 0),
        [["FIELD", "VALUE"], ["Line Length", "10.0000"]],
        col_widths=[28.0, 28.0],
    )
    table.new_cell_acobjprop_field(
        1,
        1,
        line,
        "Length",
        value=10.0,
        display="10.0000",
        text="10.0000",
        register_field_list=True,
    )

Removing fields safely
----------------------

Use the host-level removal helpers to replace a field by static text. The
helpers remove the hosted ``FIELD`` tree and prune stale handles from the root
``ACAD_FIELDLIST``. ``ACAD_TABLE`` removal also updates linked ``TABLECONTENT``
roundtrip metadata.

If the optional ``text`` argument is omitted, the helper preserves the current
visible text where possible. This creates plain static content; `ezdxf` does not
evaluate the removed field.

Text-like hosts:

.. code-block:: python

    text = msp.add_text("----", dxfattribs={"insert": (0, 0, 0)})
    text.new_acvar_field("Author", text="----", register_field_list=True)

    # Replace the field by explicit static text:
    text.remove_field(text="Static Author")

    mtext = msp.add_mtext("Keep this text", dxfattribs={"insert": (0, 4, 0)})
    mtext.new_acvar_field("Author", text="Keep this text", register_field_list=True)

    # Remove the field and preserve the current visible text:
    mtext.remove_field()

``Text.remove_field()`` also applies to ``ATTRIB`` and ``ATTDEF`` entities.
``MultiLeader.remove_field()`` is available for MTEXT-content multileaders.

Table cells:

.. code-block:: python

    table.new_cell_acvar_field(1, 1, "Author", text="----", register_field_list=True)

    # Replace the table cell field by explicit static text:
    table.remove_cell_field(1, 1, text="Static value")

    table.new_cell_acvar_field(2, 1, "Author", text="Visible value", register_field_list=True)

    # Remove the table cell field and preserve the visible value:
    table.remove_cell_field(2, 1)

Reading fields
--------------

For text-like hosts use the host's ``get_field()`` method to access the wrapper
field and ``get_primary_field()`` to access the actual child field when the host
uses a ``_text`` wrapper. ``ACAD_TABLE`` exposes the same distinction through
:meth:`~ezdxf.entities.AcadTableBlockContent.get_cell_field` and
:meth:`~ezdxf.entities.AcadTableBlockContent.get_cell_primary_field`.

Example:

.. code-block:: python

    primary = mtext.get_primary_field()
    if primary is not None:
        print(primary.evaluator_id, primary.field_code)

    table_primary = table.get_cell_primary_field(1, 1)
    if table_primary is not None:
        print(table_primary.evaluator_id, table_primary.field_code)

Host-specific convenience methods
---------------------------------

Layout/modelspace level helpers:

- :meth:`~ezdxf.graphicsfactory.CreatorInterface.add_mtext_acvar_field`
- :meth:`~ezdxf.graphicsfactory.CreatorInterface.add_mtext_dwgprops_field`
- :meth:`~ezdxf.graphicsfactory.CreatorInterface.add_mtext_acobjprop_field`
- :meth:`~ezdxf.graphicsfactory.CreatorInterface.add_mtext_acexpr_field`
- :meth:`~ezdxf.graphicsfactory.CreatorInterface.add_text_acvar_field`
- :meth:`~ezdxf.graphicsfactory.CreatorInterface.add_text_dwgprops_field`
- :meth:`~ezdxf.graphicsfactory.CreatorInterface.add_text_acobjprop_field`
- :meth:`~ezdxf.graphicsfactory.CreatorInterface.add_text_acexpr_field`

Entity-level helpers:

- :meth:`~ezdxf.entities.MText.new_acvar_field`
- :meth:`~ezdxf.entities.MText.new_dwgprops_field`
- :meth:`~ezdxf.entities.MText.new_acobjprop_field`
- :meth:`~ezdxf.entities.MText.new_acexpr_field`
- :meth:`~ezdxf.entities.MText.remove_field`
- :meth:`~ezdxf.entities.Text.new_acvar_field`
- :meth:`~ezdxf.entities.Text.new_dwgprops_field`
- :meth:`~ezdxf.entities.Text.new_acobjprop_field`
- :meth:`~ezdxf.entities.Text.new_acexpr_field`
- :meth:`~ezdxf.entities.Text.remove_field`
- :meth:`~ezdxf.entities.MultiLeader.new_acvar_field`
- :meth:`~ezdxf.entities.MultiLeader.new_dwgprops_field`
- :meth:`~ezdxf.entities.MultiLeader.new_acobjprop_field`
- :meth:`~ezdxf.entities.MultiLeader.new_acexpr_field`
- :meth:`~ezdxf.entities.MultiLeader.remove_field`
- ``ACAD_TABLE`` cell helpers:
  :meth:`~ezdxf.entities.AcadTableBlockContent.new_cell_acvar_field`,
  :meth:`~ezdxf.entities.AcadTableBlockContent.new_cell_dwgprops_field`,
  :meth:`~ezdxf.entities.AcadTableBlockContent.new_cell_acobjprop_field`,
  :meth:`~ezdxf.entities.AcadTableBlockContent.new_cell_acexpr_field`,
  :meth:`~ezdxf.entities.AcadTableBlockContent.remove_cell_field`
- :class:`~ezdxf.entities.Insert` helpers:
  :meth:`~ezdxf.entities.Insert.add_attrib_acvar_field`,
  :meth:`~ezdxf.entities.Insert.add_attrib_dwgprops_field`,
  :meth:`~ezdxf.entities.Insert.add_attrib_acobjprop_field`

Builder-level helpers for MTEXT MULTILEADER content:

- :meth:`~ezdxf.render.MultiLeaderMTextBuilder.set_acvar_field`
- :meth:`~ezdxf.render.MultiLeaderMTextBuilder.set_dwgprops_field`
- :meth:`~ezdxf.render.MultiLeaderMTextBuilder.set_acobjprop_field`

Known gaps
----------

- ``MULTILEADER`` object-property child cache values still oscillate across
  repeated AutoCAD saves, even though the field graph survives.
- Raw multi-path bulged-hole ``HATCH.Area`` authoring is still not modeled.
- ``MPOLYGON.Area`` did not resolve in AutoCAD during probing.
- ``3DFACE`` and ``SOLID`` did not expose useful probed object-property cases.
- ``POLYLINE`` 3D ``Area`` did not resolve in AutoCAD during probing.
- ``SPLINE.Length`` and ``SPLINE.ArcLength`` did not resolve in AutoCAD during probing.
- Several intuitive names such as ``ARC.Diameter`` and ``ELLIPSE.Length`` are not supported by AutoCAD in the current probe set.

Example script
--------------

For a compact visual smoke test of the current SDK surface, see:

- ``examples/fields.py``

Notes
-----

- The examples write cached display values; open the DXF in a CAD application to
  evaluate or refresh the field results.
- Byte-level parity with UI-authored field graphs is still a work in progress.
- The automatic inference support is intentionally conservative and will expand
  only when backed by concrete experiments.

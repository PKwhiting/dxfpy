.. _dynamic_blocks:

.. module:: ezdxf.dynamic_blocks

Dynamic Blocks
==============

The :class:`DynamicBlockReference` facade provides read access to dynamic block
metadata and can change visibility states of existing dynamic block references.
It is intended for DXF files that already contain AutoCAD-compatible dynamic
blocks.

.. warning::

    Dynamic block support is intentionally limited. ezdxf does not create full
    dynamic block definitions from scratch and does not evaluate arbitrary
    dynamic block actions. The public facade currently focuses on inspecting
    existing dynamic block references and changing visibility states when the
    referenced anonymous block representation can be edited safely.

Visibility States
-----------------

Wrap an :class:`~ezdxf.entities.Insert` entity in :class:`DynamicBlockReference`
to inspect dynamic block metadata:

.. code-block:: Python

    import ezdxf
    from ezdxf.dynamic_blocks import DynamicBlockReference

    doc = ezdxf.readfile("dynamic-blocks.dxf")
    for insert in doc.modelspace().query("INSERT"):
        dynamic = DynamicBlockReference(insert)
        if dynamic.has_visibility:
            print(dynamic.definition_name, dynamic.visibility_state)
            print(dynamic.visibility_state_names)

Change the visibility state by name and save the document:

.. code-block:: Python

    dynamic.set_visibility_state("SquareVisibilityState")
    doc.saveas("dynamic-blocks-changed.dxf")

Changing a visibility state updates the active anonymous block representation
and the cached visibility-state data stored at the INSERT entity. The operation
raises :class:`UnsupportedDynamicBlockReferenceError` instead of modifying a
direct dynamic block reference or an anonymous block representation shared by
multiple live INSERT entities.

Definition Inspection
---------------------

Use :class:`DynamicBlockDefinition` to inspect a definition before creating an
INSERT. Definitions can be resolved by their block-table name or recorded
AutoCAD true name::

    definition = DynamicBlockDefinition.find(doc, "STRINGING")
    if definition is not None:
        print(definition.visibility_state_names)
        print(definition.point_parameters("STATE_A"))

The facade can copy visible graphics into another layout in the same document,
or materialize a visibility state as a static anonymous block reference. An
optional predicate can filter source graphics without embedding application
layer conventions in dxfpy. Arbitrary dynamic block actions and nested
visibility paths are not materialized.

DynamicBlockDefinition
----------------------

.. autoclass:: DynamicBlockDefinition

    .. automethod:: find
    .. autoproperty:: block
    .. autoproperty:: document
    .. autoproperty:: name
    .. autoproperty:: true_name
    .. autoproperty:: has_visibility
    .. autoproperty:: visibility_state_names
    .. autoproperty:: property_table
    .. autoproperty:: has_property_table
    .. automethod:: visible_entities
    .. automethod:: point_parameters
    .. automethod:: copy_visible_entities
    .. automethod:: materialize_visibility_state

.. seealso::

    example script: `change_dynamic_block_visibility.py`_ in the
    ``/examples/blocks`` folder

DynamicBlockReference
---------------------

.. autoclass:: DynamicBlockReference

    .. autoproperty:: insert

    .. autoproperty:: is_dynamic

    .. autoproperty:: definition

    .. autoproperty:: reference

    .. autoproperty:: definition_name

    .. autoproperty:: reference_name

    .. autoproperty:: is_anonymous_reference

    .. autoproperty:: has_visibility

    .. autoproperty:: visibility_state_names

    .. autoproperty:: visibility_state

    .. autoproperty:: property_table

    .. autoproperty:: has_property_table

    .. automethod:: visible_entities

    .. automethod:: set_visibility_state


Exceptions
----------

.. autoclass:: DynamicBlockError

.. autoclass:: NotDynamicBlockReferenceError

.. autoclass:: DynamicBlockVisibilityError

.. autoclass:: UnknownVisibilityStateError

.. autoclass:: UnsupportedDynamicBlockReferenceError

.. _change_dynamic_block_visibility.py: https://github.com/mozman/ezdxf/blob/master/examples/blocks/change_dynamic_block_visibility.py

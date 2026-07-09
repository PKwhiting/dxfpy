Field
=====

.. module:: ezdxf.entities
    :noindex:

The `FIELD` object stores AutoCAD field expressions and related cached values.

This object is most useful in combination with object-backed field graphs hosted
by supported host entities such as :class:`~ezdxf.entities.MText`,
:class:`~ezdxf.entities.Text`, and :class:`~ezdxf.entities.MultiLeader`.

The low-level `FIELD` object support is broader than the current high-level
authoring helpers. For the current validated host/entity/property matrix, see
the :ref:`field tutorial <tut_fields>`.

======================== =========================================================
Subclass of              :class:`ezdxf.entities.DXFObject`
DXF type                 ``'FIELD'``
Factory function         :meth:`ezdxf.sections.objects.ObjectsSection.add_field`
======================== =========================================================

.. warning::

    Do not instantiate object classes by yourself, always use the provided
    factory functions.

.. class:: Field

    The :class:`Field` class preserves the raw DXF payload tags of a field
    object and provides a few helpers for inspection and low-level authoring.

    .. autoattribute:: evaluator_id

    .. autoattribute:: field_code

    .. autoattribute:: is_text_wrapper

    .. autoattribute:: child_handles

    .. autoattribute:: object_handles

    .. automethod:: get_child_fields

    .. automethod:: get_field_tree

    .. automethod:: clear

    .. automethod:: reset

    .. automethod:: extend

    .. automethod:: set_text_wrapper

    .. automethod:: set_acvar

    .. automethod:: set_dwgprops

    .. automethod:: set_acobjprop

    .. automethod:: set_acexpr

    .. automethod:: build_acexpr

    .. automethod:: normalize_acobjprop_cache


FieldList
=========

======================== =============================================================
Subclass of              :class:`ezdxf.entities.DXFObject`
DXF type                 ``'FIELDLIST'``
Factory function         :meth:`ezdxf.sections.objects.ObjectsSection.setup_field_list`
======================== =============================================================

.. class:: FieldList

    The :class:`FieldList` object stores handles to field objects. In current
    AutoCAD-authored MTEXT field graphs this object appears to be repairable,
    while the host extension-dictionary link is critical.

    .. attribute:: dxf.flags

        Undocumented integer flag used by AutoCAD.

    .. attribute:: handles

        List of referenced field handles as uppercase hex strings.

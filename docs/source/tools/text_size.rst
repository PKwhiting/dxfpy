.. _Text Size Tools:

Text Size Tools
===============

.. module:: dxfpy.tools.text_size


.. class:: dxfpy.tools.text_size.TextSize

    A frozen dataclass as return type for the :func:`text_size` function.

    .. attribute:: width

        The text width in drawing units (float).

    .. attribute:: cap_height

        The font cap-height in drawing units (float).

    .. attribute:: total_height

        The font total-height = cap-height + descender-height in drawing units (float).

.. autofunction:: text_size


.. class:: dxfpy.tools.text_size.MTextSize

    A frozen dataclass as return type for the :func:`mtext_size` function.

    .. attribute:: total_width

        The total width in drawing units (float)

    .. attribute:: total_height

        The total height in drawing units (float), same as ``max(column_heights)``.

    .. attribute:: column_width

        The width of a single column in drawing units (float)

    .. attribute:: gutter_width

        The space between columns in drawing units (float)

    .. attribute:: column_heights

        A tuple of columns heights (float) in drawing units. Contains at least
        one column height and the column height is 0 for an empty column.

    .. attribute:: column_count

        The count of columns (int).

.. autofunction:: mtext_size

.. autofunction:: estimate_mtext_extents

Single-Line MTEXT Fitting
-------------------------

The :class:`~dxfpy.tools.text_size.MTextSingleLineFitter` shrinks the base
character height of bounded MTEXT until its rendered content fits one line. It
never enlarges text. Use :meth:`~dxfpy.tools.text_size.MTextSingleLineFitter.measure`
to inspect line count, content width, available width, and accepted tolerance
before or after fitting. For multiline content, the reported content and
available widths are a paired measurement from the line with the greatest
overflow rather than independent maxima from different lines.

Unbounded MTEXT is never resized. Its measurement reports logical paragraph
count with ``content_width=0.0`` and ``available_width=inf`` because wrapping
widths do not apply. Non-finite or negative MTEXT widths are rejected.

.. autoclass:: dxfpy.tools.text_size.MTextSingleLineFitOptions

    The option values are starting defaults rather than universal constants:

    - ``maximum_iterations=24`` provides deterministic binary-search precision
      over typical drawing-unit ranges.
    - ``minimum_character_height=0.01`` prevents fitting from approaching zero.
    - ``character_height_tolerance_factor=0.02`` allows overflow equal to 2%
      of the candidate character height for one unbreakable rendered line.

    Calibrate these defaults with representative fonts and real application
    content. Revisit the minimum when drawing units change, the tolerance when
    font or rendering engines change, and the iteration count when the height
    range or required precision changes. The tolerance is applied after text
    layout and does not prevent breakable content from wrapping onto multiple
    lines.

.. autoclass:: dxfpy.tools.text_size.MTextSingleLineMeasurement

    .. autoproperty:: fits

.. autoclass:: dxfpy.tools.text_size.MTextSingleLineFitter

    .. automethod:: fit

    .. automethod:: measure

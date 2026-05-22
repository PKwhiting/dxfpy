# Findings

## Summary

A DXF rebuilt through `ezdxf.addons.dxf2code` from generated Python source is
accepted by AutoCAD Core Console for the current supported field and
`MULTILEADER` surface. The only real structural defect uncovered during this
validation was an `INSERT` emitter bug that recreated attached `ATTRIB`
entities as standalone layout entities before also attaching them to the block
reference, which duplicated handles on export.

## Confirmed Changes

1. A dedicated round-trip validation sheet covering hosted fields, custom `MLEADERSTYLE`, MTEXT-content `MULTILEADER`, block-content `MULTILEADER`, and multi-arrow `MultiLeader.arrow_heads` can be generated entirely through `dxf2code` output.
2. AutoCAD rejected the first round-trip DXF because attached `ATTRIB` entities were emitted as separate layout entities and then reattached, creating duplicate handles.
3. Recreating attached attributes through `Insert.add_attrib(...)` instead of `layout.new_entity("ATTRIB", ...)` fixes the duplicate-handle export problem.
4. After that fix, AutoCAD Core Console opens and resaves the generated round-trip DXF successfully.
5. The remaining `before.dxf` -> `after.dxf` deltas are limited to expected AutoCAD canonicalization effects: timestamp and GUID churn, handle reseeding, binary/proxy cache rewrites, and the already-known `MULTILEADER` child-field cache flip for `AcObjProp` fields.

## Key Excerpts

AutoCAD rejection from the first validation run:

```text
Bad handle 4F: already in use on line 2870.
...
Invalid or incomplete DXF input -- drawing discarded.
```

The duplicated handle came from two emitted `ATTRIB` entities with the same
handle, one as a child of `INSERT` and one as a standalone layout entity.

After the emitter fix, Core Console produced both validation snapshots:

```text
Created snapshots:
- ...\validate-dxf2code-roundtrip-validation\before.dxf
- ...\validate-dxf2code-roundtrip-validation\after.dxf
```

The surviving `FIELD` delta for the `MULTILEADER` `AcObjProp` child matches the
already-known cache oscillation:

```text
94: 27 -> 59
93: 0 -> 4
302/301: blank -> 14.0000
```

## Interpretation

- `dxf2code` compatibility is now validated beyond unit tests: the generated Python source can rebuild a structurally valid DXF that AutoCAD accepts.
- The `INSERT`/`ATTRIB` bug was a real generator defect, not an AutoCAD-only cosmetic difference.
- The remaining AutoCAD save deltas do not currently indicate new unsupported field or `MULTILEADER` structures; they fit the existing canonicalization and cache-normalization model.

## Likely ezdxf Targets

- `src/ezdxf/addons/dxf2code/`
- `tests/test_08_addons/test_803*.py`
- `experiments/ezdxf-generated-fields/generate_dxf2code_roundtrip_validation.py`

## Artifacts

- `experiments/ezdxf-generated-fields/dxf2code_roundtrip_validation_source.dxf`
- `experiments/ezdxf-generated-fields/dxf2code_roundtrip_validation.dxf`
- `experiments/ezdxf-generated-fields/dxf2code_roundtrip_validation_generated.py`
- `experiments/ezdxf-generated-fields/validate-dxf2code-roundtrip-validation/`

## Non-Goals From This Experiment

- proving byte-level parity with AutoCAD-saved DXFs
- explaining the existing `MULTILEADER` `AcObjProp` cache oscillation
- validating unsupported deeper nested field trees

alias:: dynamic block replay, proxy insert replay, reverse handle remap

# Dynamic Block Replay Fidelity

- Context:
  - Oracle file for this investigation:
    - `experiments/dynamic-block-diffs/autocad_complex_replay_target_v1_edited.dxf`
  - Target behavior:
    - AutoCAD opens replayed DXF without proxying the modelspace insert or nested dynamic inserts.
    - AutoCAD `AUDIT` stays clean.

- Important lesson:
  - `AUDIT` clean does **not** mean the low-level object graph is semantically correct.
  - The replayed file can still open with proxied inserts if live handle references point to the wrong valid objects.

- Symptom that drove this work:
  - Focused dynamic block diffs were clean.
  - Structural validator was clean.
  - AutoCAD still proxied the insertion.

- Main discovery:
  - The decisive bug was **not** in the visible `INSERT` entity text.
  - The decisive bug was in **reverse references from objects outside the dynamic block family back into it**.
  - This included rootdict-owned objects like:
    - `ACDB_RECOMPOSE_DATA`
    - `ACAD_FIELDLIST`
    - custom `MLEADERSTYLE` reactors

- Why this was easy to miss:
  - Normalized block/entity diffs can look clean.
  - Extension subtrees on the nested inserts can also look clean.
  - The real failure can still live in late-restored `OBJECTS` entries that reference family entities.

- Root causes found:
  - Late-bound object graphs were restored too early, before final target handles existed.
  - `dynblkhelper._owner_from_raw_tags()` incorrectly treated the first `330` inside `{ACAD_REACTORS ...}` as the real owner handle.
    - That overwrote valid remaps with reactor handles.
  - Block-contained raw entity exports needed a second late restore pass after all block/entity handle mappings existed.
  - Rootdict-owned non-dictionary objects also needed a late restore pass after modelspace/block handles existed.
  - `MLEADERSTYLE` replay had to respect the object-dictionary key, not just `entity.dxf.name`, because those can diverge.
  - Layout/modelspace entities needed explicit source->target handle registration so late raw restores could remap reverse refs to them.

- Code areas changed:
  - `src/ezdxf/dynblkhelper.py`
    - `_owner_from_raw_tags()`
    - `restore_raw_entity_export()`
    - `restore_raw_dynamic_block_definition()`
    - `_restore_raw_block_entity_exports()`
  - `src/ezdxf/fidelity.py`
    - phase-1 orchestration module
    - late block-entity export restore
    - late rootdict object restore
    - layout/modelspace handle registration
    - late named-object raw restore
  - `src/ezdxf/addons/dxf2code.py`
    - `MLEADERSTYLE` emission must use the object-dictionary key when name/key diverge

- The practical fix pattern:
  - Create the target doc.
  - Create non-default resources.
  - Run `prepare_document_fidelity()`.
  - Create blocks.
  - Create modelspace entities.
  - Run `finalize_document_fidelity()`.
  - The finalize step is where reverse references become safe to restore.

- High-value diagnostics that worked:
  - Compare exact reverse references from external objects into the dynamic block family.
  - Do not stop at block-local diffs.
  - Inspect custom `MLEADERSTYLE` raw exports and rootdict-owned `XRECORD` payloads.
  - If AutoCAD proxies with clean `AUDIT`, suspect semantically wrong live handles rather than invalid handles.

- Representative bad pattern:
  - Replay object graph points to a live `LINE`, `ARC`, `BLOCKPOINTPARAMETER`, `BLOCKXYGRIP`, etc.
  - Oracle expects a `MULTILEADER`, `FIELD`, `MTEXT`, `INSERT`, or `BLOCK_RECORD` in the same slot.

- Representative good pattern after fix:
  - Exact external-reference signature for the dynamic family matches the oracle.
  - Reverse refs no longer have `extra` or `missing` semantic targets.

- Working generated files from this investigation:
  - `autocad_complex_replay_target_v1_edited_replayed_phase2_review_v18.dxf`
  - `autocad_complex_replay_target_v1_edited_replayed_phase2_review_v19.dxf`
  - Both opened correctly in AutoCAD and `AUDIT` was clean.

- Tests added/updated:
  - `tests/test_04_dxf_high_level_structs/test_435_dynblkhelper.py`
  - `tests/test_04_dxf_high_level_structs/test_436_fidelity.py`
  - `tests/test_08_addons/test_803_entities_to_code.py`

- Key takeaway:
  - For low-level DXF fidelity, the real oracle is the AutoCAD-opened result.
  - If the file proxies with clean `AUDIT`, keep looking for late semantic handle drift in `OBJECTS`, rootdict-owned objects, and named object collections.

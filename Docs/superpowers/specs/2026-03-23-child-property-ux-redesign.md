# Child Property UX Redesign

**Date:** 2026-03-23
**Status:** Approved

## Problem

The current implementation hides child property columns entirely, replacing them with a "First only / Distribute" mode toggle. This has two issues:
1. The user has no control over which child values are included.
2. If a property is incorrectly detected as a child (false positive), the user has no way to recover — the child values are inaccessible.

## Goal

Show child property columns alongside their parent columns. Allow the user to explicitly select child values, with availability gated on which parent values are checked. Omitting all child values for a given parent means the child property is excluded from the varcode for those permutations (letting pCon resolve the default).

## Removed Features

- "First only" mode
- "Distribute" mode
- `hierarchyModes` state
- `_buildHierarchyModeControl()` function
- `resolveChildValues()` function

## Design

### Section 1 — UI / Child Column Rendering

`renderDimensions()` no longer skips child columns. For each parent column that has a detected child, both columns are rendered in a `flex-col` wrapper — parent first, child directly beneath it.

**Child column header:**
- Property name (same as any other column)
- Small muted subtitle: `↳ {parent_property_name}`

**Child column body:**
- Values are grouped into sections, one per parent value, in the same order as the parent's value list.
- Each section has a small muted header row showing the parent value code.
- All checkboxes start unchecked and disabled (greyed out).
- Default state: no values selected.

**Interactivity:**
- When a parent value checkbox is toggled on, the corresponding child section's checkboxes become enabled and selectable.
- When a parent value checkbox is toggled off, the corresponding child section's checkboxes become disabled and unchecked.
- All/None buttons at the top of the child column operate only on currently-enabled values.

### Section 2 — Permutation Counting

The permutation count formula accounts for conditional child expansion:

```
total = (product of all standalone dimension counts)
        × Σ max(1, selected_child_count_for_parent_val)
          for each checked parent value
        (per child column)
```

- A parent value with 0 child values selected contributes 1 (one permutation, child prop omitted).
- A parent value with N child values selected contributes N (N permutations, each with a different child value).

**Example:** 2 standalone values × parent with A(2 children), B(1 child), C(0 children) = 2 × (2+1+1) = 8 permutations.

With no child selections at all: 2 × (1+1+1) = 6 — identical to if the child column didn't exist.

This formula is correct for one parent-child pair per column group. Multiple independent pairs are not currently supported (no known ranges require this).

### Section 3 — Data Model

**Frontend — child selections state:**

A new `getChildSelections()` function returns:
```json
{
  "Shell_Fabric_Colour": {
    "parent": "Shell_Fabric_Type",
    "resolution": {
      "1HA": ["1HA01", "1HA02"],
      "2AB": ["2AB01"],
      "3CD": []
    }
  }
}
```

This replaces the old `resolveChildValues()` output. It is stored on the queue item as `childResolutions`.

**Backend — `ChildResolution` Pydantic model (routes.py):**

```python
class ChildResolution(BaseModel):
    parent: str
    resolution: dict[str, list[str]]  # was dict[str, str]
```

**Backend — generate loop (routes.py):**

The old per-permutation single-value injection is replaced with an expansion loop:

```python
expanded = []
for perm in permutations:
    child_expansions = [{}]
    for child_prop, cr in item.child_resolutions.items():
        parent_val = perm["properties"].get(cr.parent, "")
        child_vals = cr.resolution.get(parent_val, [])
        if child_vals:
            new_expansions = []
            for existing in child_expansions:
                for cv in child_vals:
                    new_expansions.append({**existing, child_prop: cv})
            child_expansions = new_expansions
        # empty child_vals → child prop omitted for this permutation
    for expansion in child_expansions:
        expanded.append({
            "article": perm["article"],
            "properties": {**perm["properties"], **expansion}
        })
permutations = expanded
```

`generator.py` requires no changes.

## Files Changed

| File | Change |
|---|---|
| `static/snapper/snapper.js` | Remove `hierarchyModes`, `_buildHierarchyModeControl`, `resolveChildValues`; add `_buildChildColumn`, `getChildSelections`; update `renderDimensions`, `updatePermCount`, `addToQueueBtn` handler |
| `modules/snapper/routes.py` | Update `ChildResolution.resolution` type; replace generate injection loop with expansion loop |

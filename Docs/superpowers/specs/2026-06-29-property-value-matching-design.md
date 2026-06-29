# Property Value Matching ("Match to…") — Design

**Date:** 2026-06-29
**Module:** Snapper File Generator
**Status:** Approved, ready for implementation planning

## Problem

Two properties on the same article frequently share most or all of their values:
a sofa with a seat fabric and a back fabric (identical value sets), or a desk with
a worktop finish and an edgeband finish (edgeband = worktop finishes plus an extra
like plywood).

Today these render as independent checkbox columns, so selecting "all" on both
produces a full cartesian product (X × Y). To keep counts down, the QA team
currently does two separate generations (all-of-X × one-of-Y, then vice versa).
The efficient path is to let the user declare that Y should track X.

## Concept

Matching is the **inverse of the existing parent→child hierarchy**:

- Hierarchy **multiplies** — each parent value fans out into its child values.
- Matching **zips** — a column's value is slaved, in lockstep, to an earlier
  column's value.

Matching is keyed on **identical value codes** (confirmed: shared finishes use the
exact same value code in both properties). There is no fuzzy similarity detection —
the user explicitly declares the match; the system pairs values by exact code.

## Semantics

For a column **Y** matched to an earlier column **X**:

### Lockstep (shared values)
For every permutation, `Y = X`. Y contributes **nothing** to the cartesian product.
Only target values that also exist in Y's value set drive a tick; a selected X value
absent from Y's set leaves Y omitted for that permutation (pCon fills its default).

### Extras (Y-only values, e.g. plywood)
Each ticked extra value rides along the **first-selected X value** (the *anchor*).
Concretely: for each extra `e` and each base permutation where `X == anchor`, emit
one additional permutation with `Y = e`. Extras stay pinned to the anchor on the
X axis but still vary across any *other* free dimensions, and never blow up against
all of X.

### Worked example
worktop {oak, walnut, white} × edgeband {oak, walnut, white, **plywood**},
edgeband matched to worktop, anchor = first-selected worktop (oak):

| # | worktop | edgeband | source |
|---|---------|----------|--------|
| 1 | oak     | oak      | lockstep |
| 2 | walnut  | walnut   | lockstep |
| 3 | white   | white    | lockstep |
| 4 | oak     | plywood  | extra on anchor |

**4 permutations** instead of 12.

### Count formula
With `P` = the normal product of all free-dimension factors (including X), and
`Xfactor` = number of selected X values:

```
total = P                                    (lockstep: matched column drops out of the product)
      + Σ over matched columns: len(extras) × (P / Xfactor)   (extras on the anchor slice)
```

## UI (inline "Match to…")

On each eligible column, a **"Match to… ▾"** selector at the top, default
*"Not matched"*, listing only columns that appear **before** it and are eligible
(see Scope). When a target X is chosen, the column re-renders into two zones:

- **🔗 Matched** — values whose code matches a value in X. Shown auto-ticked and
  **locked/disabled**, driven live by X's current selection (same wiring and visual
  treatment as the existing child-section checkboxes).
- **Extra (independent)** — Y-only codes, shown as normal tickable checkboxes under
  an "Extra (independent)" subheader.

Caption under the header: `🔗 matched to {X} · extras pair with first-selected {X}`.

Changing X's ticks updates the matched zone reactively, mirroring
`_updateChildSections`.

## Data flow

### Client state
Per-group `matchConfig = { matchedProp: { matchTo, extras: [codes] } }`, persisted
in `groupStates` and carried into the queue item.

### Queue item → server
New field on the queue item:

```
match_resolutions: {
  matchedProp: {
    match_to:        str,        // the X property name
    matched_values:  [codes],    // intersection of selected-X-values and Y's value set
    extras:          [codes],    // Y-only values the user ticked
  }
}
```

The matched column is **excluded** from `selected_properties` (exactly like
hierarchy children are excluded).

### Server
A new `apply_matches(permutations, match_resolutions, selected_properties)` step in
`generator.py`, run **after** `compute_permutations` and
`expand_permutations_with_children`. Pure list-in / list-out, independently testable:

1. For each permutation, set `Y = perm[X]` when `perm[X]` is in `matched_values`;
   otherwise leave Y absent.
2. Compute `anchor = selected_properties[X][0]` (first selected, DOM order preserved).
3. For each extra `e` and each base permutation where `perm[X] == anchor`, append a
   copy with `Y = e`.

Wired into `routes.py` `generate_obx` alongside the existing child-resolution
expansion, with a matching Pydantic model (`MatchResolution`).

### Permutation counter (client)
Matched columns drop out of the product; each adds `len(extras) × (P / Xfactor)`
per the count formula above. Updated in `updatePermCount`.

## Scope (v1)

- Both X and Y must be **standalone** columns — neither is a hierarchy parent or
  child.
- Y cannot match a column that is itself matched (**no chains**).
- **Multiple columns may match the same X** (two edgebands → one worktop is fine).
  Preferring this over chains keeps the model flat and avoids transitive resolution.

These constraints cover the worktop/edgeband and seat/back-fabric cases without
entangling matching with hierarchy expansion. They can be lifted later if a real
range needs it.

## Files touched

- `static/snapper/snapper.js` — "Match to…" selector, matched/extra column
  rendering, reactive updates, `matchConfig` state, queue payload, counter.
- `modules/snapper/generator.py` — `apply_matches`.
- `modules/snapper/routes.py` — `MatchResolution` model, wiring into `generate_obx`.
- Tests for `apply_matches` (lockstep, extras-on-anchor, multi-match, absent-value
  omission, empty/edge cases).

## Out of scope

- Fuzzy / automatic similarity detection between columns.
- Value-by-value mapping when codes differ (not needed — codes are identical).
- Matching across hierarchy members; matching chains.

# Hierarchical Property Value Matching — Design Spec

**Date:** 2026-06-29
**Status:** Approved (brainstorm)
**Builds on:** `Docs/superpowers/specs/2026-06-29-property-value-matching-design.md` and its
plan `Docs/superpowers/plans/2026-06-29-property-value-matching.md` (the standalone-column
"Match to…" feature, already implemented).

## Problem

The first version of property value matching (the "Match to…" feature) only allows
**standalone** columns to participate — a column is eligible only if
`!is_child && !parentHasChild.has(name)`. This deliberately excluded any property in a
parent→child hierarchy.

The most common real QA case is exactly the excluded one: a product has two parallel fabric
hierarchies — e.g. `Shell_Fabric_Type → Shell_Fabric_Colour` and
`Seat_Fabric_Type → Seat_Fabric_Colour` — and the user wants the **seat fabric to be
identical to the shell fabric** (same type *and* same colour) in every generated
configuration. Today the fabric *type* is a parent, so it cannot be matched at all.

## Goal

Let the user match the two fabric **types** together and have their **colour children
auto-match**, producing identical fabrics in lockstep. Generalize the match mechanism so
**any** column (standalone, parent, or child) can be matched, while keeping the simple
"identical" workflow a single action.

Out of scope: extras for hierarchical matches, fuzzy/positional colour-code remapping,
multi-level chains, cross-article matching.

## Core model (unchanged semantics)

A match on column **Y** means: *"copy the value column **X** resolves to into Y, per
generated varcode."* This is a pure post-processing step (`apply_matches` in
`modules/snapper/routes.py`) that runs **after** `compute_permutations` and
`expand_permutations_with_children`. Because expansion has already happened, the target's
concrete value (including an expanded colour) is always present in the permutation when the
copy runs.

**Key consequence:** the backend `apply_matches` function needs **no change** for the
identical (no-extras) case. Its existing lockstep loop already does
`props[Y] = props[X]` for whatever `X` is — parent or child — as long as `match_to`
points at a column whose value is present in the permutation. The new behaviour is delivered
almost entirely on the frontend (eligibility, auto-pair, rendering, exclusions, payload),
plus a small **validity filter** described below.

## Design

### 1. Generalized eligibility (with cycle safety)

- **Any** column may be a match **source** (Y): standalone, parent, or child.
- A column's **target** (X) may be **any other column that is not itself currently
  matched**. This single rule replaces the old "earlier columns only" positional
  restriction *and* prevents all chains/cycles: to match `B→A`, `A` must be unmatched; but
  if `A→B` already exists then `A` is matched, so `B→A` is blocked. No separate
  cycle-detection needed.
- Parent→parent matches are only offered between parents that **each have a child**, so the
  colour pairing is well-defined.

### 2. Parent auto-pair

- Matching a parent `Y_parent → X_parent` **automatically creates** a second match for
  their children: `Y_child → X_child` (derived via the existing `parentHasChild` map).
  Example: `Seat_Fabric_Type → Shell_Fabric_Type` auto-adds
  `Seat_Fabric_Colour → Shell_Fabric_Colour`. One action ⇒ identical fabric.
- An **auto-paired child** renders as a **read-only** column showing
  `🔗 follows X_child (via X_parent)` — no value checkboxes, because it is fully determined
  by the target. The user cannot independently tick the seat colours while the parent match
  is active.
- Un-matching the parent removes the auto-paired child match as well.

### 3. Manual child matching

- A child whose parent is **not** itself matched may still be matched manually to another
  eligible (non-matched) column, using the same copy semantics.
- If a colour is matched **without** its corresponding type also being matched, the UI shows
  a **non-blocking warning**: the resulting varcode may be inconsistent (a colour without
  its governing type), which pCon can reject or reset on Update. Matching is still allowed —
  the user is trusted, just warned.

### 4. Validity filter (graceful handling of code mismatches)

When building the match payload, `matched_values` is computed as
`X's selected/expanded values ∩ Y's own value-code set`. `apply_matches` only copies a
target value that is in `matched_values`. Therefore, if the two properties happen to use
different colour codes for the same type, the non-shared codes are simply **omitted**
(pCon falls back to its default) instead of producing an invalid varcode. This also
guarantees every copied value has an entry in the article's `prop_val_to_class` map, so the
OBX builder can always assign a class to it.

### 5. Exclusions and the permutation counter

- A matched **parent** is excluded from the free dimensions (its checkboxes are not
  `.dim-check`), and its auto-paired colour **child** is excluded from child-expansion
  (skipped when building `child_resolutions`). Both are instead filled by the copy in
  `apply_matches`.
- Net effect on the counter: matched columns contribute no factors, so the permutation
  count equals the **target** side's type×colour product (e.g. Shell's) — the intuitive
  result for "make seat identical to shell."
- No extras are introduced for hierarchical matches. Standalone-column extras (from the
  original feature) are unchanged.

### 6. Data flow summary

1. Frontend: user matches `Seat_Type → Shell_Type`; UI auto-pairs `Seat_Colour →
   Shell_Colour`, marks both Seat columns as matched (excluded from free dims and from
   `child_resolutions`), and renders the read-only matched/auto-paired columns.
2. On *Add to Queue*: `match_resolutions` is built for both Seat columns with the validity
   filter; Shell columns travel normally in `selected_properties` / `child_resolutions`.
3. On *Generate*: `compute_permutations` (Shell type) → `expand_permutations_with_children`
   (Shell colour) → `apply_matches` copies Shell type→Seat type and Shell colour→Seat
   colour per permutation.

## Components touched

- `static/snapper/snapper.js` — **most of the work**: generalize `_matchableColumns` and
  the eligibility helpers; add "Match to…" selectors to parent and child columns; implement
  parent auto-pair (create/remove the child match); render auto-paired/manual matched child
  columns (read-only); exclude matched parents from free dims and matched children from
  `child_resolutions`; build `match_resolutions` for parent and child matches with the
  validity filter; the consistency warning; verify the counter excludes matched columns.
- `modules/snapper/routes.py` — `apply_matches` unchanged for the identical case; confirm a
  matched **child** target flows through correctly. (Only touch if a defect surfaces.)
- `tests/snapper/test_match_expansion.py` — add unit tests: child-target lockstep, a
  parent+child pair matched together, and the validity-filter omission case.
- `tests/test_routes.py` — extend/add an end-to-end generate test asserting both
  `Seat_Type = Shell_Type` and `Seat_Colour = Shell_Colour` (guarded to skip when the
  example range data is unavailable in the checkout, as the existing matching test is).

## Testing strategy

- **Backend (pytest):** pure-function unit tests for `apply_matches` covering a child
  target and a coordinated parent+child pair; an end-to-end `/api/snapper/generate` test
  for the lockstep type+colour result and for validity-filter omission.
- **Frontend:** no JS test harness exists; verify by running the app
  (`python main.py` → `localhost:8080/snapper/`) with a range that has two parallel fabric
  hierarchies, and inspect: parent selector appears, auto-pair locks the colour child,
  counter reflects the target-only product, and the generated OBX has identical fabrics.
  Report what was actually observed.

## Risks / notes

- Detection of the parent→child colour hierarchy already varies by range (see CLAUDE.md
  "Known limitations": some ranges, e.g. CLOUD, have mixed colour condition types that
  prevent automatic hierarchy detection, so colours render as standalone columns there). In
  such ranges the *standalone* matching already covers the colour, and the auto-pair simply
  doesn't apply — the generalized eligibility still lets the user match those columns
  directly. The feature degrades sensibly across the known structural styles.
- The frontend match UI is growing; keep the eligibility rules as the single source of
  truth for "what can match what," and fix the helper rather than call sites if a case slips
  through.

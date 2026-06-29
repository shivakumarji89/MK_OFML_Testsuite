# Hierarchical Property Value Matching Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a QA user match two parallel fabric hierarchies so one is identical to the other — match the fabric *types* and have their colour *children* auto-match in lockstep — by generalizing the existing "Match to…" feature to work on parent and child columns, not just standalone ones.

**Architecture:** The match mechanism is a pure post-step (`apply_matches` in `modules/snapper/routes.py`) that copies a target column's resolved value onto the matched column, running *after* permutation + colour expansion. Because the copy happens after expansion, it already works for child targets unchanged — so this feature is almost entirely a **frontend** change: generalize eligibility, add a "Match to…" selector to parent and child columns, auto-pair a parent's colour child when its type is matched, render matched parent/child columns, exclude matched columns from the permutation product, and build the `match_resolutions` payload with a value-validity filter. The backend gains only tests plus (if a defect surfaces) minor confirmation.

**Tech Stack:** Python 3 + FastAPI + Pydantic (backend), pytest (tests), vanilla JS + Tailwind CDN (frontend, no build step, no JS test harness).

**Spec:** `Docs/superpowers/specs/2026-06-29-hierarchical-property-matching-design.md`

**Builds on:** the standalone "Match to…" feature already implemented on branch `feat/property-value-matching` (`apply_matches`, `MatchResolution`, `matchConfig`, `_buildMatchedColumn`, `buildMatchResolutions`, etc.). This plan extends that code; it does not start from scratch.

---

## File Structure

- `modules/snapper/routes.py` — **mostly unchanged.** `apply_matches` already copies any `match_to` value (parent or child) present in a permutation. No production edit expected; touch only if a test reveals a defect.
- `tests/snapper/test_match_expansion.py` — **modify.** Add unit tests proving `apply_matches` handles a child target and a coordinated parent+child pair, and the validity-filter omission case.
- `tests/test_routes.py` — **modify.** Add one end-to-end generate test asserting `Seat_Type = Shell_Type` AND `Seat_Colour = Shell_Colour` (guarded to skip when the example range isn't in the local checkout, mirroring `test_generate_with_matching_locksteps_values`).
- `static/snapper/snapper.js` — **the bulk of the work.** Generalize eligibility; selectors on parent/child columns; parent auto-pair; matched parent/child rendering; exclude matched columns from `selected_properties` and `child_resolutions`; validity filter in `buildMatchResolutions`; consistency warning for manual child matches.
- `CLAUDE.md` — **modify.** Note hierarchical matching (auto-pair) under the Snapper "Matching" bullet.

> **Pattern note:** Keep the **eligibility helpers as the single source of truth** for "what can match what." If a case slips through (e.g. a parent offering an invalid target), fix the helper, not the call site.

---

## Chunk 1: Backend — characterization tests (no production change)

### Task 1: Prove `apply_matches` handles child + parent-pair targets

**Files:**
- Modify: `tests/snapper/test_match_expansion.py`

> `apply_matches` is generic: its lockstep loop does `props[Y] = props[X]` for whatever `X`
> resolves to in the permutation. These tests lock that behaviour for hierarchical shapes.
> They should PASS on first run (no production change) — they are characterization tests.

- [ ] **Step 1: Add the tests**

Append to `tests/snapper/test_match_expansion.py`:

```python
def test_child_target_lockstep_copies_colour():
    """A matched colour copies the (already-expanded) target colour per permutation."""
    perms = [
        {"article": "A1", "properties": {"Shell_Type": "1HA", "Shell_Colour": "1HA01"}},
        {"article": "A1", "properties": {"Shell_Type": "1HA", "Shell_Colour": "1HA02"}},
    ]
    match = {"Seat_Colour": {"match_to": "Shell_Colour",
                            "matched_values": ["1HA01", "1HA02"], "extras": []}}
    result = apply_matches(perms, match, {"Shell_Type": ["1HA"]})
    assert len(result) == 2
    assert all(p["properties"]["Seat_Colour"] == p["properties"]["Shell_Colour"]
               for p in result)


def test_parent_and_child_pair_lockstep_identical_fabric():
    """Matching type+colour together yields identical seat/shell fabric, no extras."""
    perms = [
        {"article": "A1", "properties": {"Shell_Type": "1HA", "Shell_Colour": "1HA01"}},
        {"article": "A1", "properties": {"Shell_Type": "1HA", "Shell_Colour": "1HA02"}},
        {"article": "A1", "properties": {"Shell_Type": "2AB", "Shell_Colour": "2AB01"}},
    ]
    match = {
        "Seat_Type":   {"match_to": "Shell_Type",
                        "matched_values": ["1HA", "2AB"], "extras": []},
        "Seat_Colour": {"match_to": "Shell_Colour",
                        "matched_values": ["1HA01", "1HA02", "2AB01"], "extras": []},
    }
    result = apply_matches(perms, match, {"Shell_Type": ["1HA", "2AB"]})
    assert len(result) == 3  # no extras -> count unchanged
    for p in result:
        assert p["properties"]["Seat_Type"] == p["properties"]["Shell_Type"]
        assert p["properties"]["Seat_Colour"] == p["properties"]["Shell_Colour"]


def test_validity_filter_omits_colour_not_in_target_set():
    """A target colour absent from the matched property's matched_values is left absent."""
    perms = [
        {"article": "A1", "properties": {"Shell_Type": "1HA", "Shell_Colour": "1HA01"}},
        {"article": "A1", "properties": {"Shell_Type": "1HA", "Shell_Colour": "1HA09"}},
    ]
    # Seat only carries 1HA01 (1HA09 does not exist as a seat colour)
    match = {"Seat_Colour": {"match_to": "Shell_Colour",
                            "matched_values": ["1HA01"], "extras": []}}
    result = apply_matches(perms, match, {"Shell_Type": ["1HA"]})
    by_shell = {p["properties"]["Shell_Colour"]: p["properties"] for p in result}
    assert by_shell["1HA01"]["Seat_Colour"] == "1HA01"
    assert "Seat_Colour" not in by_shell["1HA09"]  # omitted -> pCon default
```

- [ ] **Step 2: Run the tests**

Run: `python -m pytest tests/snapper/test_match_expansion.py -v`
Expected: PASS (all, including the 3 new ones). If any FAIL, `apply_matches` has a defect for hierarchical shapes — fix `apply_matches` minimally, then re-run.

- [ ] **Step 3: Commit**

```bash
git add tests/snapper/test_match_expansion.py
git commit -m "test: cover hierarchical (child + parent-pair) matching in apply_matches"
```

---

## Chunk 2: Frontend — generalized eligibility, parent auto-pair, rendering

> No JS test harness exists; verify by running the app (`python main.py` →
> `localhost:8080/snapper/`) with a range that has two parallel fabric hierarchies, and
> inspect behaviour. Apply `@superpowers:verification-before-completion`: state what you
> actually observed. Run `node --check static/snapper/snapper.js` after each task as a cheap
> syntax gate.

### Task 2: Generalize eligibility helpers

**Files:**
- Modify: `static/snapper/snapper.js` (the `// ── Property value matching` helper block added by the prior feature)

**Eligibility rules (v2):**
- Any column may be a **source** (Y): standalone, parent, or child.
- A **target** (X) may be any other column that is **not itself matched** (`!cfg[name]`) and
  is not the column itself. (This rule alone prevents chains/cycles: matching makes a column
  matched, so it can no longer be chosen as a target.)
- **Standalone** sources target other standalone columns.
- **Parent** sources (a column with a child) target other **parent** columns that also have a
  child (so the colour pairing is well-defined).
- **Child** sources target other **child** columns (manual matching — Chunk 3).
- The old "earlier columns only" positional restriction is **dropped**.

- [ ] **Step 1: Add a kind helper and an eligible-targets helper**

Replace the existing `_matchableColumns` / `_matchTargets` helpers with:

```javascript
function _colKind(col, parentHasChild) {
  if (col.is_child) return 'child';
  if (parentHasChild.has(col.name)) return 'parent';
  return 'standalone';
}

function _parentHasChildMap(group) {
  const m = new Map();
  for (const col of group.property_columns) {
    if (col.is_child) m.set(col.parent, col.name);
  }
  return m;
}

function _currentMatchConfig() {
  return (groupStates[currentGroupIndex] || {}).matchConfig || {};
}

function _matchTargets() {
  // Names currently used as a match target (so they don't also offer a source selector).
  const cfg = _currentMatchConfig();
  return new Set(Object.values(cfg).map(m => m.matchTo));
}

function _eligibleTargets(col, group, parentHasChild, cfg) {
  const kind = _colKind(col, parentHasChild);
  return group.property_columns.filter(c => {
    if (c.name === col.name) return false;   // not itself
    if (cfg[c.name]) return false;           // target must be unmatched (no chains)
    const cKind = _colKind(c, parentHasChild);
    if (kind === 'standalone') return cKind === 'standalone';
    if (kind === 'parent')     return cKind === 'parent';     // both have a child
    if (kind === 'child')      return cKind === 'child';
    return false;
  }).map(c => c.name);
}
```

- [ ] **Step 2: Point `_buildMatchSelector` at `_eligibleTargets`**

Replace the option-building inside `_buildMatchSelector` so it no longer uses index/`matchable`:

```javascript
function _buildMatchSelector(col, group, parentHasChild, cfg) {
  const options = _eligibleTargets(col, group, parentHasChild, cfg)
    .map(name => `<option value="${escapeHtml(name)}">${escapeHtml(name)}</option>`)
    .join('');
  const sel = document.createElement('div');
  sel.className = 'mb-2';
  sel.innerHTML = options
    ? `<label class="text-xs text-gray-500">Match to…
         <select class="match-select text-xs border rounded px-1 py-0.5 w-full mt-0.5"
                 data-prop="${escapeHtml(col.name)}">
           <option value="">Not matched</option>${options}
         </select></label>`
    : '';  // nothing eligible -> no selector
  const select = sel.querySelector('.match-select');
  if (select) {
    select.value = cfg[col.name]?.matchTo || '';
    select.addEventListener('change', () => onMatchTargetChange(col.name, select.value));
  }
  return sel;
}
```

- [ ] **Step 3: Syntax check**

Run: `node --check static/snapper/snapper.js`
Expected: `syntax OK` (prints nothing on success; exit 0). Note: callers still reference the old `_buildMatchSelector(col, group, matchable, targets, cfg)` signature — they are fixed in Task 4. The check only validates syntax, not call arity.

- [ ] **Step 4: Commit**

```bash
git add static/snapper/snapper.js
git commit -m "feat: generalize match eligibility to parent and child columns"
```

---

### Task 3: Parent auto-pair on match / unmatch

**Files:**
- Modify: `static/snapper/snapper.js` (`onMatchTargetChange`)

When a **parent** is matched to another parent, also create the child→child match; when the
parent is unmatched, remove the auto-paired child match.

- [ ] **Step 1: Rewrite `onMatchTargetChange`**

```javascript
function onMatchTargetChange(propName, targetName) {
  const group = currentSeed.groups[currentGroupIndex];
  const parentHasChild = _parentHasChildMap(group);
  const cfg = _currentMatchConfig();

  if (targetName) {
    cfg[propName] = { matchTo: targetName, extras: [] };
    // Auto-pair: if both source and target are parents with a child, match the children too.
    const srcChild = parentHasChild.get(propName);
    const tgtChild = parentHasChild.get(targetName);
    if (srcChild && tgtChild) {
      cfg[srcChild] = { matchTo: tgtChild, extras: [], auto: true };
    }
  } else {
    // Unmatch: drop this match and any child match auto-created for it.
    const srcChild = parentHasChild.get(propName);
    delete cfg[propName];
    if (srcChild && cfg[srcChild]?.auto) delete cfg[srcChild];
  }

  groupStates[currentGroupIndex].matchConfig = cfg;
  renderDimensions();
}
```

- [ ] **Step 2: Syntax check**

Run: `node --check static/snapper/snapper.js`
Expected: exit 0.

- [ ] **Step 3: Commit**

```bash
git add static/snapper/snapper.js
git commit -m "feat: auto-pair colour child when matching a fabric type parent"
```

---

### Task 4: Render matched parents and matched children; wire selectors into renderDimensions

**Files:**
- Modify: `static/snapper/snapper.js` (`renderDimensions` loop; `_buildMatchedColumn`; add `_buildMatchedChildColumn`)

- [ ] **Step 1: Give `_buildMatchedColumn` an `allowExtras` flag**

Standalone matches keep their extras zone; matched **parents** suppress it (hierarchical
matches are "identical", no extras — per spec). Change the signature and gate the extras
zone:

```javascript
function _buildMatchedColumn(col, group, matchCfg, allowExtras = true) {
  // ... unchanged setup (targetCodes, selectedTarget, extras, matchedVals) ...
  const extraVals = allowExtras ? col.values.filter(v => !targetCodes.has(v.code)) : [];
  // ... rest unchanged; the `${extraVals.length ? ...}` block now naturally hides
  //     the extras zone when allowExtras is false ...
}
```

- [ ] **Step 2: Add `_buildMatchedChildColumn` (read-only "follows" column)**

A matched child (auto-paired or manual) is fully determined by its target, so it shows no
value checkboxes — just the selector (to allow un-matching) and a follows note. If its own
parent is **not** matched, show a consistency warning.

```javascript
function _buildMatchedChildColumn(col, group, matchCfg, parentHasChild) {
  const el = document.createElement('div');
  el.className = 'bg-white rounded-lg shadow p-3 min-w-44 max-w-56 flex flex-col';
  el.dataset.propName = col.name;

  // Parent of this child, and whether that parent is itself matched (consistency check).
  const cfg = _currentMatchConfig();
  const parentMatched = col.parent && !!cfg[col.parent];
  const warn = !parentMatched
    ? `<div class="text-xs text-amber-600 mb-2">⚠ ${escapeHtml(col.parent || 'type')} is not
         matched — the varcode may be inconsistent.</div>`
    : '';

  el.innerHTML = `
    <div class="font-semibold text-sm text-gray-700 mb-0.5 border-b pb-1" title="${escapeHtml(col.name)}">${escapeHtml(col.name)}</div>
    <div class="mb-2">
      <label class="text-xs text-gray-500">Match to…
        <select class="match-select text-xs border rounded px-1 py-0.5 w-full mt-0.5" data-prop="${escapeHtml(col.name)}">
          <option value="">Not matched</option>
          <option value="${escapeHtml(matchCfg.matchTo)}" selected>${escapeHtml(matchCfg.matchTo)}</option>
        </select></label>
    </div>
    ${warn}
    <div class="text-xs text-gray-400">🔗 follows ${escapeHtml(matchCfg.matchTo)}${
      matchCfg.auto ? ` (via ${escapeHtml(col.parent)})` : ''}</div>`;

  el.querySelector('.match-select').addEventListener('change', (e) =>
    onMatchTargetChange(col.name, e.target.value));
  return el;
}
```

- [ ] **Step 3: Rewrite the `renderDimensions` column loop**

Replace the current standalone-only match integration with kind-aware handling. Inside
`renderDimensions`, replace the block that currently computes `matchable`/`targets`/`cfg` and
the `for (const col ...)` loop with:

```javascript
  const parentHasChild = _parentHasChildMap(group);
  const targets = _matchTargets();
  const cfg = _currentMatchConfig();

  for (const col of group.property_columns) {
    if (col.is_child) continue;  // children are rendered inside their parent's chain

    const kind = _colKind(col, parentHasChild);  // 'standalone' | 'parent'

    // Matched standalone or matched parent -> matched column (parent suppresses extras).
    if (cfg[col.name]) {
      dimensionColumns.appendChild(
        _buildMatchedColumn(col, group, cfg[col.name], kind === 'standalone'));
      continue;
    }

    const wrapper = document.createElement('div');
    wrapper.className = 'flex flex-col gap-1';

    // Offer a selector unless this column is itself a target of another match.
    if (!targets.has(col.name)) {
      wrapper.appendChild(_buildMatchSelector(col, group, parentHasChild, cfg));
    }

    wrapper.appendChild(
      _buildCheckboxColumn(col.name, col.values, col.seed_value, state.dimSelections, group.articles)
    );

    // Child chain: render each child as matched (read-only) or as a normal child column.
    let current = col.name;
    while (true) {
      const nextName = parentHasChild.get(current);
      if (!nextName) break;
      const nextCol = group.property_columns.find(c => c.name === nextName);
      if (!nextCol) break;
      if (cfg[nextName]) {
        wrapper.appendChild(_buildMatchedChildColumn(nextCol, group, cfg[nextName], parentHasChild));
      } else {
        wrapper.appendChild(_buildChildColumn(nextCol, group.articles));
      }
      current = nextName;
    }

    dimensionColumns.appendChild(wrapper);
  }
```

- [ ] **Step 4: Syntax check**

Run: `node --check static/snapper/snapper.js`
Expected: exit 0.

- [ ] **Step 5: Verify in the app**

Run `python main.py`, open `localhost:8080/snapper/`, upload a seed for a range with two
parallel fabric hierarchies (Shell + Seat). Confirm:
- The Seat fabric **type** column shows a "Match to…" selector listing the Shell type.
- Selecting it converts the Seat type to a matched column AND the Seat colour to a read-only
  "🔗 follows … (via …)" column.
- Setting the selector back to "Not matched" restores both Seat columns.
State what you observed.

- [ ] **Step 6: Commit**

```bash
git add static/snapper/snapper.js
git commit -m "feat: render matched parent and auto-paired child columns"
```

---

### Task 5: Exclude matched columns from the payload + validity filter

**Files:**
- Modify: `static/snapper/snapper.js` (`getChildSelections`, `buildMatchResolutions`)

Matched **parents** are already excluded from `selected_properties` (a matched column has no
`.dim-check`). Two gaps remain: matched **children** must be excluded from
`child_resolutions`, and `buildMatchResolutions` must (a) read a **child** target's selected
values from the colour checks, and (b) filter by the **source** column's codes (the validity
filter), not the target's.

- [ ] **Step 1: Skip matched children in `getChildSelections`**

In `getChildSelections`, skip any child that is currently matched:

```javascript
  const cfg = _currentMatchConfig();
  for (const col of group.property_columns) {
    if (!col.is_child) continue;
    if (cfg[col.name]) continue;   // matched child is filled by apply_matches, not expansion
    // ... unchanged resolution-building ...
  }
```

- [ ] **Step 2: Add a target-value helper and fix `buildMatchResolutions`**

```javascript
function _selectedTargetValues(targetName, group, parentSelections) {
  // A child target's selected values live in .child-check ticks; everything else in dims.
  const targetCol = group.property_columns.find(c => c.name === targetName);
  if (targetCol?.is_child) {
    const out = [];
    dimensionColumns
      .querySelectorAll(`.child-check[data-prop="${CSS.escape(targetName)}"]:checked`)
      .forEach(cb => out.push(cb.dataset.value));
    return out;
  }
  return parentSelections[targetName] || [];
}

function buildMatchResolutions(group, parentSelections) {
  const cfg = _currentMatchConfig();
  const out = {};
  for (const [matchedProp, m] of Object.entries(cfg)) {
    const sourceCol = group.property_columns.find(c => c.name === matchedProp);
    const sourceCodes = new Set((sourceCol?.values || []).map(v => v.code));  // validity filter
    const selectedX = _selectedTargetValues(m.matchTo, group, parentSelections);
    out[matchedProp] = {
      match_to: m.matchTo,
      matched_values: selectedX.filter(v => sourceCodes.has(v)),  // only values Y actually has
      extras: [...(m.extras || [])],
    };
  }
  return out;
}
```

> Why filter by `sourceCodes` (Y) rather than the target's codes: `apply_matches` copies the
> target value onto Y only if it is in `matched_values`. Restricting to values Y actually
> defines guarantees the copied value has a `prop_val_to_class` entry, so the OBX builder can
> assign a class — and silently omits colours Y lacks (pCon default), per the spec's validity
> filter.

- [ ] **Step 3: Syntax check**

Run: `node --check static/snapper/snapper.js`
Expected: exit 0.

- [ ] **Step 4: Verify counter + end-to-end in the app**

With Shell type (e.g. 2 types) and its colours selected, and Seat matched to Shell:
- The permutation counter equals the **Shell** type×colour product (Seat contributes
  nothing). Confirm the number matches Shell-only.
- Click **Add to Queue**, **Generate**, open the OBX: every article has
  `Seat_Type` equal to its `Shell_Type` and `Seat_Colour` equal to its `Shell_Colour`.
State what you observed (include the counter value and a sample varcode pair).

- [ ] **Step 5: Commit**

```bash
git add static/snapper/snapper.js
git commit -m "feat: exclude matched children and apply validity filter in match payload"
```

---

## Chunk 3: End-to-end test, manual child matching, docs

### Task 6: End-to-end generate test (type + colour lockstep)

**Files:**
- Modify: `tests/test_routes.py`

- [ ] **Step 1: Add the test**

Mirror `test_generate_with_matching_locksteps_values`, but match the *type* and rely on
auto-pair semantics by sending both resolutions explicitly (the server is UI-agnostic). Use
the CLOUD seed (Shell/Seat fabric type both `1HA`). Guard with a skip when the range data is
absent.

```python
def test_generate_with_hierarchical_matching_identical_fabric():
    parse = _upload_seed(CLOUD_SEED_XML)
    if parse.status_code != 200:
        pytest.skip(f"CLOUD range data unavailable in repo checkout (status {parse.status_code})")
    data = parse.json()
    group = data["groups"][0]
    art = group["articles"][0]
    col_names = {c["name"] for c in group["property_columns"]}
    assert {"Shell_Fabric_Type", "Seat_Fabric_Type"} <= col_names

    payload = {
        "manufacturer": data["manufacturer"],
        "series": data["series"],
        "filename": "match_hier.obx",
        "queue": [{
            "articles": [art],
            "selected_article_codes": [art["code"]],
            "selected_properties": {"Shell_Fabric_Type": ["1HA"]},
            "child_resolutions": {},  # Shell colour omitted for simplicity; type is enough here
            "match_resolutions": {
                "Seat_Fabric_Type": {
                    "match_to": "Shell_Fabric_Type",
                    "matched_values": ["1HA"], "extras": [],
                },
            },
            "filename": "match_hier.obx",
        }],
    }
    resp = client.post("/api/snapper/generate", json=payload)
    assert resp.status_code == 200
    body = resp.text
    assert "Shell_Fabric_Type=1HA" in body
    assert "Seat_Fabric_Type=1HA" in body
```

> If `1HA` is not valid in the live data, read the parse-seed `property_columns` values in a
> scratch run and substitute a real shared code. The assertion logic is unchanged.

- [ ] **Step 2: Run it**

Run: `python -m pytest tests/test_routes.py::test_generate_with_hierarchical_matching_identical_fabric -v`
Expected: PASS, or SKIP if CLOUD data isn't in the checkout.

- [ ] **Step 3: Commit**

```bash
git add tests/test_routes.py
git commit -m "test: end-to-end hierarchical (type) matching generate"
```

---

### Task 7: Manual child matching (selector on unmatched children)

**Files:**
- Modify: `static/snapper/snapper.js` (`_buildChildColumn`)

Allow a child whose parent is **not** matched to be matched manually to another eligible
child. The matched-child rendering (Task 4) and warning already handle the matched state;
this task only adds the *selector* to the unmatched child column.

- [ ] **Step 1: Prepend a selector inside `_buildChildColumn`**

At the end of `_buildChildColumn`, before `return el;`, insert a selector when eligible
(parent not matched, this child not a target of anyone):

```javascript
  const group = currentSeed.groups[currentGroupIndex];
  const parentHasChild = _parentHasChildMap(group);
  const cfg = _currentMatchConfig();
  const targets = _matchTargets();
  const parentMatched = col.parent && !!cfg[col.parent];
  if (!parentMatched && !targets.has(col.name)) {
    const selector = _buildMatchSelector(col, group, parentHasChild, cfg);
    if (selector.innerHTML) el.insertBefore(selector, el.firstChild.nextSibling);
  }
```

> `el.firstChild` is the column title; inserting after it keeps the selector under the header,
> consistent with parent/standalone columns. If `_eligibleTargets` returns nothing (no other
> free child), `_buildMatchSelector` yields an empty element and we skip it.

- [ ] **Step 2: Syntax check**

Run: `node --check static/snapper/snapper.js`
Expected: exit 0.

- [ ] **Step 3: Verify in the app**

With a range where a colour child is standalone-eligible (or two parallel children exist and
their parents are unmatched), confirm the unmatched child shows a "Match to…" selector; on
selecting a target, the child converts to the read-only matched-child view **with the amber
warning** that its type isn't matched. Then match the parent types and confirm the warning is
gone (parent-matched path). State what you observed.

- [ ] **Step 4: Commit**

```bash
git add static/snapper/snapper.js
git commit -m "feat: allow manual matching of child columns with consistency warning"
```

---

### Task 8: Final regression + docs

- [ ] **Step 1: Run the whole suite**

Run: `python -m pytest -q`
Expected: pre-existing environment-dependent failures only (the CLOUD parse-seed tests skip/fail when the SVN checkout lacks CLOUD); **no new failures** from this work. Confirm the match unit tests pass and the hierarchical e2e test passes or skips.

- [ ] **Step 2: Update `CLAUDE.md`**

Under the Snapper "Matching" bullet (added by the prior feature), append a sentence:

> Hierarchical fabrics: matching a fabric **type** to another type auto-matches their colour
> **children** in lockstep (one action ⇒ identical fabric); colours that don't exist on the
> matched side are omitted (pCon default).

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: document hierarchical fabric matching (auto-pair) in CLAUDE.md"
```

---

## Notes for the implementer

- **Backend is already generic.** Resist editing `apply_matches` — Chunk 1 proves it handles
  child and parent-pair targets. Only touch it if a Chunk 1 test fails.
- **Eligibility is the single source of truth.** All "what can match what" logic lives in
  `_colKind` / `_eligibleTargets`. Fix those, not the call sites.
- **DRY:** reuse `_buildMatchSelector` for standalone, parent, and child columns; reuse
  `_buildMatchedColumn` (with `allowExtras=false`) for parents.
- **YAGNI:** no extras for hierarchical matches, no positional colour remapping, no chains,
  no cross-article matching — all explicitly out of scope (see spec).
- **No JS tests exist here** — be honest in verification: run the app and report what you
  actually saw, per `@superpowers:verification-before-completion`.
```

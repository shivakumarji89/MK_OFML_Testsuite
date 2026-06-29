# Property Value Matching ("Match to…") Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a QA user declare that one property column should track an earlier column's value in lockstep (a "zip"), collapsing a cartesian product into matched pairs plus a small number of anchor-bound extras.

**Architecture:** Mirror the existing parent→child hierarchy machinery, but inverted. Server: a new pure `apply_matches` function in `modules/snapper/routes.py` runs after `compute_permutations` and `expand_permutations_with_children`, copying the target's value onto the matched property (lockstep) and appending extras bound to the first-selected target value (anchor). Client: an inline "Match to…" selector per eligible column in `static/snapper/snapper.js`, reusing the child-column rendering/reactivity patterns; matched columns are excluded from `selected_properties` and instead travel in a new `match_resolutions` payload field.

**Tech Stack:** Python 3 + FastAPI + Pydantic (backend), pytest (tests), vanilla JS + Tailwind CDN (frontend, no build step, no JS test harness).

**Spec:** `Docs/superpowers/specs/2026-06-29-property-value-matching-design.md`

---

## File Structure

- `modules/snapper/routes.py` — **modify.** Add pure function `apply_matches(...)` (next to `expand_permutations_with_children`), add `MatchResolution` Pydantic model, add `match_resolutions` field to `QueueItem`, wire `apply_matches` into `generate_obx`.
- `tests/snapper/test_match_expansion.py` — **create.** Unit tests for `apply_matches` (mirrors `test_generate_expansion.py`).
- `tests/test_routes.py` — **modify.** One end-to-end test driving `/api/snapper/generate` with `match_resolutions`.
- `static/snapper/snapper.js` — **modify.** Match-selector UI, matched/extra column rendering, reactive updates, `matchConfig` state, queue payload, permutation counter.

> **Pattern note:** The spec mentioned `generator.py` for `apply_matches`, but the established pattern places the permutation-expansion step (`expand_permutations_with_children`) in `routes.py`. Follow the established pattern and put `apply_matches` in `routes.py` beside it.

---

## Chunk 1: Backend — `apply_matches` + endpoint wiring

### Task 1: Pure `apply_matches` function (TDD)

**Files:**
- Modify: `modules/snapper/routes.py` (add function near `expand_permutations_with_children`, ~line 369)
- Test: `tests/snapper/test_match_expansion.py` (create)

**Contract:**

```python
def apply_matches(
    permutations: list[dict],
    match_resolutions: dict[str, dict],
    selected_properties: dict[str, list[str]],
) -> list[dict]:
    """
    Apply property-value matching (lockstep zip) to a list of permutations.

    Args:
        permutations: list of {article, properties} dicts. Matched properties are
            NOT present as free dimensions (the client excludes them from
            selected_properties), so they do not appear here yet.
        match_resolutions: {matched_prop: {
            "match_to": str,            # target (X) property name, appears earlier
            "matched_values": [codes],  # selected X values that also exist in Y's set
            "extras": [codes],          # Y-only values the user ticked
        }}
        selected_properties: {prop_name: [selected_values]} — used to find the
            anchor = first selected value of each target property.

    Returns:
        New list of {article, properties} dicts:
        - Lockstep: for each permutation, matched_prop = perm[match_to] when that
          value is in matched_values; otherwise matched_prop is left absent.
        - Extras: for each extra value e, for each lockstep permutation where
          perm[match_to] == anchor, append a copy with matched_prop = e.
        Extra sets are appended independently per matched column (no cross-product
        between different columns' extras).
    """
```

- [ ] **Step 1: Write failing tests**

Create `tests/snapper/test_match_expansion.py`:

```python
# tests/snapper/test_match_expansion.py
import pytest
from modules.snapper.routes import apply_matches


def test_no_matches_unchanged():
    perms = [{"article": "A1", "properties": {"Worktop": "oak", "Color": "red"}}]
    assert apply_matches(perms, {}, {"Worktop": ["oak"]}) == perms


def test_lockstep_copies_target_value():
    perms = [
        {"article": "A1", "properties": {"Worktop": "oak"}},
        {"article": "A1", "properties": {"Worktop": "walnut"}},
        {"article": "A1", "properties": {"Worktop": "white"}},
    ]
    match = {"Edge": {"match_to": "Worktop",
                      "matched_values": ["oak", "walnut", "white"],
                      "extras": []}}
    result = apply_matches(perms, match, {"Worktop": ["oak", "walnut", "white"]})
    assert len(result) == 3
    assert all(p["properties"]["Edge"] == p["properties"]["Worktop"] for p in result)


def test_extra_pairs_with_first_selected_anchor():
    """Worked example from the spec: 3 lockstep + 1 extra on anchor = 4."""
    perms = [
        {"article": "A1", "properties": {"Worktop": "oak"}},
        {"article": "A1", "properties": {"Worktop": "walnut"}},
        {"article": "A1", "properties": {"Worktop": "white"}},
    ]
    match = {"Edge": {"match_to": "Worktop",
                      "matched_values": ["oak", "walnut", "white"],
                      "extras": ["plywood"]}}
    result = apply_matches(perms, match, {"Worktop": ["oak", "walnut", "white"]})
    assert len(result) == 4
    pairs = {(p["properties"]["Worktop"], p["properties"]["Edge"]) for p in result}
    assert pairs == {("oak", "oak"), ("walnut", "walnut"),
                     ("white", "white"), ("oak", "plywood")}


def test_target_value_not_in_matched_values_omits_matched_prop():
    """A selected target value absent from Y's set leaves Y omitted (pCon default)."""
    perms = [
        {"article": "A1", "properties": {"Worktop": "oak"}},
        {"article": "A1", "properties": {"Worktop": "granite"}},  # no Edge equivalent
    ]
    match = {"Edge": {"match_to": "Worktop",
                      "matched_values": ["oak"], "extras": []}}
    result = apply_matches(perms, match, {"Worktop": ["oak", "granite"]})
    assert len(result) == 2
    by_wt = {p["properties"]["Worktop"]: p["properties"] for p in result}
    assert by_wt["oak"]["Edge"] == "oak"
    assert "Edge" not in by_wt["granite"]


def test_extras_vary_across_other_free_dimensions_on_anchor_slice():
    """Extras ride the anchor on X but still vary across other dimensions (Color)."""
    perms = [
        {"article": "A1", "properties": {"Worktop": "oak", "Color": "red"}},
        {"article": "A1", "properties": {"Worktop": "oak", "Color": "blue"}},
        {"article": "A1", "properties": {"Worktop": "walnut", "Color": "red"}},
        {"article": "A1", "properties": {"Worktop": "walnut", "Color": "blue"}},
    ]
    match = {"Edge": {"match_to": "Worktop",
                      "matched_values": ["oak", "walnut"], "extras": ["plywood"]}}
    result = apply_matches(perms, match,
                           {"Worktop": ["oak", "walnut"], "Color": ["red", "blue"]})
    # 4 lockstep + 2 extras (anchor=oak slice has 2 colors) = 6
    assert len(result) == 6
    extras = [p for p in result if p["properties"]["Edge"] == "plywood"]
    assert {p["properties"]["Color"] for p in extras} == {"red", "blue"}
    assert all(p["properties"]["Worktop"] == "oak" for p in extras)


def test_multiple_columns_match_same_target():
    """Two columns match Worktop; each locks, each contributes its own extras."""
    perms = [
        {"article": "A1", "properties": {"Worktop": "oak"}},
        {"article": "A1", "properties": {"Worktop": "walnut"}},
    ]
    match = {
        "Edge1": {"match_to": "Worktop", "matched_values": ["oak", "walnut"], "extras": ["ply1"]},
        "Edge2": {"match_to": "Worktop", "matched_values": ["oak", "walnut"], "extras": ["ply2"]},
    }
    result = apply_matches(perms, match, {"Worktop": ["oak", "walnut"]})
    # 2 lockstep + 1 extra(ply1 on anchor) + 1 extra(ply2 on anchor) = 4
    assert len(result) == 4
    # In ply1's extra row, Edge2 stays locked to anchor (oak), and vice versa
    ply1 = next(p for p in result if p["properties"]["Edge1"] == "ply1")
    assert ply1["properties"]["Edge2"] == "oak"
    ply2 = next(p for p in result if p["properties"]["Edge2"] == "ply2")
    assert ply2["properties"]["Edge1"] == "oak"


def test_no_anchor_when_target_not_selected_skips_extras():
    perms = [{"article": "A1", "properties": {"Worktop": "oak"}}]
    match = {"Edge": {"match_to": "Worktop", "matched_values": ["oak"], "extras": ["plywood"]}}
    result = apply_matches(perms, match, {})  # Worktop not in selected_properties
    assert len(result) == 1  # lockstep only, no extra (no anchor)
    assert result[0]["properties"]["Edge"] == "oak"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/snapper/test_match_expansion.py -v`
Expected: FAIL — `ImportError: cannot import name 'apply_matches'`.

- [ ] **Step 3: Implement `apply_matches`**

Add to `modules/snapper/routes.py` immediately after `expand_permutations_with_children`:

```python
def apply_matches(
    permutations: list[dict],
    match_resolutions: dict[str, dict],
    selected_properties: dict[str, list[str]],
) -> list[dict]:
    """See module docs / plan for the contract. Lockstep + anchor-bound extras."""
    if not match_resolutions:
        return permutations

    # 1. Lockstep: copy each target value onto its matched property.
    locked: list[dict] = []
    for perm in permutations:
        props = dict(perm["properties"])
        for matched_prop, mr in match_resolutions.items():
            target_val = props.get(mr["match_to"])
            if target_val is not None and target_val in mr["matched_values"]:
                props[matched_prop] = target_val
            # else: matched_prop left absent (pCon default)
        locked.append({"article": perm["article"], "properties": props})

    # 2. Extras: each rides the anchor (first selected target value) slice.
    extra_rows: list[dict] = []
    for matched_prop, mr in match_resolutions.items():
        selected = selected_properties.get(mr["match_to"], [])
        if not selected:
            continue  # no anchor available -> skip extras for this column
        anchor = selected[0]
        for extra_val in mr["extras"]:
            for base in locked:
                if base["properties"].get(mr["match_to"]) == anchor:
                    new_props = dict(base["properties"])
                    new_props[matched_prop] = extra_val
                    extra_rows.append({"article": base["article"], "properties": new_props})

    return locked + extra_rows
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/snapper/test_match_expansion.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add modules/snapper/routes.py tests/snapper/test_match_expansion.py
git commit -m "feat: add apply_matches permutation step for property value matching"
```

---

### Task 2: Pydantic model + wire into `generate_obx`

**Files:**
- Modify: `modules/snapper/routes.py` (`MatchResolution` model ~line 305, `QueueItem` ~line 310, `generate_obx` ~line 397)

- [ ] **Step 1: Add the `MatchResolution` model**

After the `ChildResolution` class (around line 308):

```python
class MatchResolution(BaseModel):
    match_to: str                    # target (X) property name, appears earlier
    matched_values: list[str] = []   # selected X values that also exist in Y's set
    extras: list[str] = []           # Y-only values the user ticked
```

- [ ] **Step 2: Add the field to `QueueItem`**

In `class QueueItem`, after `child_resolutions`:

```python
    match_resolutions: dict[str, MatchResolution] = {}
```

- [ ] **Step 3: Wire `apply_matches` into `generate_obx`**

In `generate_obx`, immediately after the existing
`permutations = expand_permutations_with_children(permutations, child_res_dicts)` line:

```python
        match_res_dicts = {
            name: {
                "match_to": mr.match_to,
                "matched_values": mr.matched_values,
                "extras": mr.extras,
            }
            for name, mr in item.match_resolutions.items()
        }
        permutations = apply_matches(permutations, match_res_dicts, item.selected_properties)
```

- [ ] **Step 4: Run the full snapper test suite to confirm no regressions**

Run: `python -m pytest tests/snapper tests/test_routes.py -v`
Expected: PASS (existing tests unaffected; default `match_resolutions={}` is a no-op).

- [ ] **Step 5: Commit**

```bash
git add modules/snapper/routes.py
git commit -m "feat: accept match_resolutions in generate endpoint"
```

---

### Task 3: End-to-end generate test with matching

**Files:**
- Modify: `tests/test_routes.py` (add one test using the existing `client` and `_upload_seed` helpers)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_routes.py`. It uploads the CLOUD seed (which has `Shell_Fabric_Type`/`Seat_Fabric_Type` both = `1HA`), matches `Seat_Fabric_Type` to `Shell_Fabric_Type`, and asserts the generated OBX contains lockstep varcodes. Use the parse-seed response to obtain real `articles` class maps and `seed_token`.

```python
def test_generate_with_matching_locksteps_values():
    parse = _upload_seed(CLOUD_SEED_XML)
    assert parse.status_code == 200
    data = parse.json()
    group = data["groups"][0]
    art = group["articles"][0]

    # Sanity: both fabric-type props exist as standalone columns
    col_names = {c["name"] for c in group["property_columns"]}
    assert {"Shell_Fabric_Type", "Seat_Fabric_Type"} <= col_names

    payload = {
        "manufacturer": data["manufacturer"],
        "series": data["series"],
        "filename": "match_test.obx",
        "queue": [{
            "articles": [art],
            "selected_article_codes": [art["code"]],
            # Shell is the free target dimension; Seat is matched (excluded here)
            "selected_properties": {"Shell_Fabric_Type": ["1HA"]},
            "child_resolutions": {},
            "match_resolutions": {
                "Seat_Fabric_Type": {
                    "match_to": "Shell_Fabric_Type",
                    "matched_values": ["1HA"],
                    "extras": [],
                }
            },
            "filename": "match_test.obx",
        }],
    }
    resp = client.post("/api/snapper/generate", json=payload)
    assert resp.status_code == 200
    body = resp.text
    # One permutation, Seat locked to Shell's 1HA
    assert "Shell_Fabric_Type=1HA" in body
    assert "Seat_Fabric_Type=1HA" in body
```

> If `1HA` is not a valid `Shell_Fabric_Type` value in the live repo data, read the parse-seed `property_columns` values in a quick scratch run and substitute a real shared code. The assertion logic stays the same.

- [ ] **Step 2: Run to verify it passes** (the backend is already implemented)

Run: `python -m pytest tests/test_routes.py::test_generate_with_matching_locksteps_values -v`
Expected: PASS. If it fails on data assumptions (not wiring), adjust the value codes per the note above.

- [ ] **Step 3: Commit**

```bash
git add tests/test_routes.py
git commit -m "test: end-to-end generate with property value matching"
```

---

## Chunk 2: Frontend — state, match selector, matched/extra rendering

> No JS test harness exists in this repo; frontend tasks are verified by running the app
> (`python main.py` → `localhost:8080/snapper/`) and inspecting behavior. The `@superpowers:verification-before-completion` discipline applies: state what you actually observed.

### Task 4: Add `matchConfig` to per-group state

**Files:**
- Modify: `static/snapper/snapper.js` (parse-seed init ~line 217, `_saveGroupState` ~line 269)

- [ ] **Step 1: Initialise `matchConfig` on parse**

In the parse-seed handler where `groupStates` is built:

```javascript
  groupStates = currentSeed.groups.map(() => ({
    articleSelections: null,
    dimSelections: {},
    matchConfig: {},   // { matchedProp: { matchTo, extras: [codes] } }
  }));
```

- [ ] **Step 2: Persist `matchConfig` in `_saveGroupState`**

`matchConfig` is mutated live on the active group's state object, so saving is just
ensuring it is carried (it already lives on `groupStates[currentGroupIndex]`). Add an
explicit refresh of `extras` from the DOM so ticks survive a tab switch:

```javascript
  // Refresh extras from any rendered match-extra checkboxes
  const cfg = state.matchConfig || {};
  for (const matchedProp of Object.keys(cfg)) {
    const ticked = [];
    dimensionColumns
      .querySelectorAll(`.match-extra-check[data-prop="${CSS.escape(matchedProp)}"]:checked`)
      .forEach(cb => ticked.push(cb.dataset.value));
    cfg[matchedProp].extras = ticked;
  }
  state.matchConfig = cfg;
```

- [ ] **Step 3: Verify** — reload `/snapper/`, parse a seed, switch tabs; confirm no console errors. (No visible change yet.)

- [ ] **Step 4: Commit**

```bash
git add static/snapper/snapper.js
git commit -m "feat: add matchConfig to snapper group state"
```

---

### Task 5: Eligibility helpers + "Match to…" selector

**Files:**
- Modify: `static/snapper/snapper.js` (`renderDimensions` ~line 286)

**Eligibility rules (v1 scope):** a column is *matchable* (can be a source Y or a target X)
only if it is standalone — `!is_child` and not a parent of any child. A column may be
matched to an earlier matchable column that is **not itself currently matched** (no chains).
A column that is currently a **target** of another match does not show its own selector
(prevents chains from the other direction).

- [ ] **Step 1: Add eligibility helpers** (near the top of the dimension-rendering section)

```javascript
function _matchableColumns(group, parentHasChild) {
  // Standalone columns only: not a child, not a parent.
  return group.property_columns.filter(
    c => !c.is_child && !parentHasChild.has(c.name)
  );
}

function _currentMatchConfig() {
  return (groupStates[currentGroupIndex] || {}).matchConfig || {};
}

function _matchTargets() {
  // Set of property names currently used as a match target (match_to).
  const cfg = _currentMatchConfig();
  return new Set(Object.values(cfg).map(m => m.matchTo));
}
```

- [ ] **Step 2: Render the selector inside each eligible standalone column**

In `renderDimensions`, the non-child branch currently builds the checkbox column. Wrap so
that for matchable columns a "Match to…" `<select>` is prepended, and matched columns route
to a new `_buildMatchedColumn` renderer. Replace the standalone build with:

```javascript
  const matchable = new Set(_matchableColumns(group, parentHasChild).map(c => c.name));
  const targets = _matchTargets();
  const cfg = _currentMatchConfig();

  group.property_columns.forEach((col, idx) => {
    if (col.is_child) return;
    // (existing parent-with-children handling continues to use the wrapper/while-loop)
  });
```

> Keep the existing parent→children `wrapper` + `while` traversal exactly as-is for parent
> columns. Only standalone matchable columns gain match behavior. Concretely: inside the
> existing loop, before building a standalone column, branch:
>
> ```javascript
> if (matchable.has(col.name) && cfg[col.name]) {
>   dimensionColumns.appendChild(_buildMatchedColumn(col, group, cfg[col.name]));
>   return; // continue forEach
> }
> // else build the normal checkbox column, and if it's matchable and NOT a target,
> // prepend a "Match to…" selector listing earlier matchable, non-target,
> // non-matched columns.
> ```

- [ ] **Step 3: Build the selector element** — add a helper that returns a `<select>`:

```javascript
function _buildMatchSelector(col, group, matchable, targets, cfg) {
  const colIndex = group.property_columns.findIndex(c => c.name === col.name);
  const options = group.property_columns
    .filter((c, i) =>
      i < colIndex &&            // earlier than this column
      matchable.has(c.name) &&   // standalone
      !cfg[c.name] &&            // target is not itself matched (no chains)
      c.name !== col.name)
    .map(c => `<option value="${escapeHtml(c.name)}">${escapeHtml(c.name)}</option>`)
    .join('');
  const sel = document.createElement('div');
  sel.className = 'mb-2';
  sel.innerHTML = options
    ? `<label class="text-xs text-gray-500">Match to…
         <select class="match-select text-xs border rounded px-1 py-0.5 w-full mt-0.5"
                 data-prop="${escapeHtml(col.name)}">
           <option value="">Not matched</option>${options}
         </select></label>`
    : '';  // nothing earlier to match to -> no selector
  const select = sel.querySelector('.match-select');
  if (select) {
    select.value = cfg[col.name]?.matchTo || '';
    select.addEventListener('change', () => onMatchTargetChange(col.name, select.value));
  }
  return sel;
}
```

Prepend `_buildMatchSelector(...)`'s element to a standalone matchable column that is not a
target (`!targets.has(col.name)`), before appending the checkbox column.

- [ ] **Step 4: Handle selector changes**

```javascript
function onMatchTargetChange(propName, targetName) {
  const cfg = _currentMatchConfig();
  if (targetName) cfg[propName] = { matchTo: targetName, extras: [] };
  else delete cfg[propName];
  groupStates[currentGroupIndex].matchConfig = cfg;
  renderDimensions();   // re-render: column converts to matched layout (or back)
}
```

- [ ] **Step 5: Verify** — parse a seed with two standalone finish columns; confirm the
later column shows "Match to…" with the earlier column as an option, and selecting it
re-renders without error. (Matched layout comes in Task 6.)

- [ ] **Step 6: Commit**

```bash
git add static/snapper/snapper.js
git commit -m "feat: add Match to selector to standalone snapper columns"
```

---

### Task 6: Render matched columns (matched zone + extras zone)

**Files:**
- Modify: `static/snapper/snapper.js` (add `_buildMatchedColumn` near `_buildChildColumn` ~line 479)

- [ ] **Step 1: Implement `_buildMatchedColumn`**

```javascript
function _buildMatchedColumn(col, group, matchCfg) {
  const targetCol = group.property_columns.find(c => c.name === matchCfg.matchTo);
  const targetCodes = new Set((targetCol?.values || []).map(v => v.code));
  // Currently-ticked target values drive which matched rows are checked.
  const selectedTarget = new Set(
    [...dimensionColumns.querySelectorAll(
      `.dim-check[data-prop="${CSS.escape(matchCfg.matchTo)}"]:checked`)]
      .map(cb => cb.dataset.value)
  );
  const extras = new Set(matchCfg.extras || []);

  const matchedVals = col.values.filter(v => targetCodes.has(v.code));
  const extraVals = col.values.filter(v => !targetCodes.has(v.code));

  const el = document.createElement('div');
  el.className = 'bg-white rounded-lg shadow p-3 min-w-44 max-w-56 flex flex-col';
  el.dataset.propName = col.name;

  const matchedRows = matchedVals.map(v => `
    <label class="flex items-center gap-1 text-xs text-gray-500 cursor-not-allowed">
      <input type="checkbox" class="match-locked-check" disabled
        data-prop="${escapeHtml(col.name)}" data-value="${escapeHtml(v.code)}"
        ${selectedTarget.has(v.code) ? 'checked' : ''}>
      <span class="text-blue-400">🔗</span>
      <span class="font-mono text-gray-500">${escapeHtml(v.code)}</span>
      ${v.label && v.label !== v.code ? `<span class="text-gray-300">·</span><span class="truncate">${escapeHtml(v.label)}</span>` : ''}
    </label>`).join('');

  const extraRows = extraVals.map(v => `
    <label class="flex items-center gap-1 text-xs text-gray-700 cursor-pointer">
      <input type="checkbox" class="match-extra-check"
        data-prop="${escapeHtml(col.name)}" data-value="${escapeHtml(v.code)}"
        ${extras.has(v.code) ? 'checked' : ''}>
      <span class="font-mono text-gray-500">${escapeHtml(v.code)}</span>
      ${v.label && v.label !== v.code ? `<span class="text-gray-300">·</span><span class="truncate">${escapeHtml(v.label)}</span>` : ''}
    </label>`).join('');

  el.innerHTML = `
    <div class="font-semibold text-sm text-gray-700 mb-0.5 border-b pb-1" title="${escapeHtml(col.name)}">${escapeHtml(col.name)}</div>
    <div class="mb-2">
      <label class="text-xs text-gray-500">Match to…
        <select class="match-select text-xs border rounded px-1 py-0.5 w-full mt-0.5" data-prop="${escapeHtml(col.name)}">
          <option value="">Not matched</option>
          <option value="${escapeHtml(matchCfg.matchTo)}" selected>${escapeHtml(matchCfg.matchTo)}</option>
        </select></label>
    </div>
    <div class="text-xs text-gray-400 mb-2">🔗 matched to ${escapeHtml(matchCfg.matchTo)} · extras pair with first-selected ${escapeHtml(matchCfg.matchTo)}</div>
    <div class="overflow-y-auto max-h-64">
      <div class="text-xs font-mono text-gray-300 px-1 pb-0.5 border-b border-gray-100 mb-0.5">Matched</div>
      <div class="pl-1 space-y-0.5 mb-2">${matchedRows || '<div class="text-xs text-gray-300 italic">none</div>'}</div>
      ${extraVals.length ? `
        <div class="text-xs font-mono text-gray-300 px-1 pb-0.5 border-b border-gray-100 mb-0.5">Extra (independent)</div>
        <div class="pl-1 space-y-0.5">${extraRows}</div>` : ''}
    </div>`;

  el.querySelector('.match-select').addEventListener('change', (e) =>
    onMatchTargetChange(col.name, e.target.value));
  el.querySelectorAll('.match-extra-check').forEach(cb =>
    cb.addEventListener('change', onMatchExtraChange));
  return el;
}

function onMatchExtraChange() {
  // Persist the ticked extras into matchConfig, then refresh the counter.
  const cfg = _currentMatchConfig();
  for (const matchedProp of Object.keys(cfg)) {
    const ticked = [];
    dimensionColumns
      .querySelectorAll(`.match-extra-check[data-prop="${CSS.escape(matchedProp)}"]:checked`)
      .forEach(cb => ticked.push(cb.dataset.value));
    cfg[matchedProp].extras = ticked;
  }
  updatePermCount();
}
```

- [ ] **Step 2: Verify** — match a later finish column to an earlier one; confirm the column
shows a "Matched" zone (locked, 🔗) reflecting the target's current ticks, and an "Extra
(independent)" zone with tickable leftover values. Toggle the target's ticks and confirm
(after Task 7) the matched zone updates.

- [ ] **Step 3: Commit**

```bash
git add static/snapper/snapper.js
git commit -m "feat: render matched columns with locked matched zone and extras"
```

---

## Chunk 3: Frontend — reactivity, counter, queue payload

### Task 7: Reactive matched-zone updates

**Files:**
- Modify: `static/snapper/snapper.js` (`onDimensionChange` ~line 409)

- [ ] **Step 1: Add `_updateMatchedColumns` and call it**

```javascript
function _updateMatchedColumns() {
  if (!currentSeed) return;
  const group = currentSeed.groups[currentGroupIndex];
  if (!group) return;
  const cfg = _currentMatchConfig();
  for (const [matchedProp, m] of Object.entries(cfg)) {
    const selectedTarget = new Set(
      [...dimensionColumns.querySelectorAll(
        `.dim-check[data-prop="${CSS.escape(m.matchTo)}"]:checked`)]
        .map(cb => cb.dataset.value)
    );
    dimensionColumns
      .querySelectorAll(`.match-locked-check[data-prop="${CSS.escape(matchedProp)}"]`)
      .forEach(cb => { cb.checked = selectedTarget.has(cb.dataset.value); });
  }
}
```

Add the call inside `onDimensionChange`:

```javascript
function onDimensionChange() {
  _updateChildSections();
  _updateMatchedColumns();   // <-- new
  _updateAllTierIndicators();
  updatePermCount();
}
```

- [ ] **Step 2: Verify** — with a match active, ticking/unticking the target column's values
flips the corresponding locked rows in the matched column live.

- [ ] **Step 3: Commit**

```bash
git add static/snapper/snapper.js
git commit -m "feat: reactively update matched columns when target changes"
```

---

### Task 8: Permutation counter accounts for matching

**Files:**
- Modify: `static/snapper/snapper.js` (`updatePermCount` ~line 673)

**Rule:** matched columns are already excluded from the product (their checkboxes are
`.match-locked-check` / `.match-extra-check`, not `.dim-check`, so the existing factor loop
never counts them). Add the extras contribution: for each matched column with `e` ticked
extras and a selected target factor `Xfactor > 0`, add `e × (P / Xfactor)` where `P` is the
product of all counted factors.

- [ ] **Step 1: After `P` (the existing `count`) is computed, add extras**

Just before assigning `currentPermCount`, insert:

```javascript
  // Extras from matched columns ride the anchor slice: e × (P / Xfactor).
  const cfg = _currentMatchConfig();
  let extrasTotal = 0;
  for (const [matchedProp, m] of Object.entries(cfg)) {
    const e = dimensionColumns.querySelectorAll(
      `.match-extra-check[data-prop="${CSS.escape(matchedProp)}"]:checked`).length;
    if (!e) continue;
    const xFactor = dimensionColumns.querySelectorAll(
      `.dim-check[data-prop="${CSS.escape(m.matchTo)}"]:checked`).length;
    if (xFactor > 0) extrasTotal += e * (count / xFactor);
  }
  const total = count + extrasTotal;
```

Then use `total` (not `count`) for `currentPermCount`, the displayed text, and the
warn/error thresholds. Keep the `addToQueueBtn` disable logic keyed on `total === 0`.

- [ ] **Step 2: Verify** — reproduce the spec worked example: worktop with 3 ticked,
edgeband matched with 1 extra ticked → counter reads **4**. Untick the extra → **3**.

- [ ] **Step 3: Commit**

```bash
git add static/snapper/snapper.js
git commit -m "feat: include matched-column extras in permutation count"
```

---

### Task 9: Carry matches into the queue payload + persistence

**Files:**
- Modify: `static/snapper/snapper.js` (`addToQueueBtn` handler ~line 764, `_doGenerate` ~line 960)

- [ ] **Step 1: Build `match_resolutions` when adding to queue**

In the `addToQueueBtn` click handler, before `queue.push`, build a helper and a value:

```javascript
function buildMatchResolutions(group, parentSelections) {
  const cfg = _currentMatchConfig();
  const out = {};
  for (const [matchedProp, m] of Object.entries(cfg)) {
    const targetCol = group.property_columns.find(c => c.name === m.matchTo);
    const targetCodes = new Set((targetCol?.values || []).map(v => v.code));
    const selectedX = parentSelections[m.matchTo] || [];
    out[matchedProp] = {
      match_to: m.matchTo,
      matched_values: selectedX.filter(v => targetCodes.has(v)),
      extras: [...(m.extras || [])],
    };
  }
  return out;
}
```

Then in the `queue.push({ ... })` object add:

```javascript
    matchResolutions: buildMatchResolutions(group, parentSelections),
```

> `parentSelections` already excludes matched columns (their checkboxes aren't `.dim-check`),
> so `selected_properties` sent to the server omits them automatically — no extra work needed.

- [ ] **Step 2: Send it in `_doGenerate`**

In the payload's `queue: items.map(e => ({ ... }))`, add:

```javascript
      match_resolutions: e.matchResolutions || {},
```

(The `|| {}` keeps old localStorage items — which lack the field — working.)

- [ ] **Step 3: Verify (end to end)** — with the dev server running, set up worktop (3) +
edgeband matched with plywood extra, Add to Queue (card shows 4 permutations), Generate, and
open the downloaded OBX. Confirm: 3 articles where edge varcode equals worktop varcode, and 1
article where worktop = first-selected and edge = plywood. Matches the spec table.

- [ ] **Step 4: Commit**

```bash
git add static/snapper/snapper.js
git commit -m "feat: send match_resolutions from snapper queue to generate endpoint"
```

---

### Task 10: Final regression + docs touch-up

- [ ] **Step 1: Run the whole suite**

Run: `python -m pytest -q`
Expected: all green.

- [ ] **Step 2: Update `CLAUDE.md` module/API notes**

In `CLAUDE.md`, under the `/api/snapper/generate` description, add `match_resolutions` to the
queue-item field list, and add a one-line "Matching" bullet under the Snapper "how it works"
section describing the "Match to…" feature (lockstep + anchor-bound extras).

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: document property value matching in CLAUDE.md"
```

---

## Notes for the implementer

- **DRY:** `apply_matches` deliberately parallels `expand_permutations_with_children` — same
  list-in/list-out shape, same placement, same test style. Don't invent a new abstraction.
- **YAGNI:** No fuzzy similarity detection, no value-by-value code mapping, no matching across
  hierarchy members, no chains. All explicitly out of scope (see spec).
- **Scope guard:** the eligibility helpers are the single source of truth for "what can match
  what." If a case slips through (e.g. a parent column offering a selector), fix the helper,
  not the call sites.
- **No JS tests exist here** — be honest in verification: run the app and report what you
  actually saw, per `@superpowers:verification-before-completion`.

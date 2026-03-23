# Child Property UX Redesign Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hidden "First only / Distribute" child property UI with visible grouped checkbox columns whose availability is gated on parent value selections.

**Architecture:** Two-file change. Backend: `routes.py` gets a revised `ChildResolution` model (multi-value list instead of single string) and an expansion loop replacing the old per-permutation injection. Frontend: `snapper.js` drops the three hierarchy helper functions and adds a new child column builder that renders values grouped by parent value, toggling enabled state as parent checkboxes change.

**Tech Stack:** Python / FastAPI (backend), vanilla JS / Tailwind CSS (frontend), pytest (backend unit tests)

**Spec:** `Docs/superpowers/specs/2026-03-23-child-property-ux-redesign.md`

---

## Chunk 1: Backend — ChildResolution model + expansion loop

### Task 1: Write a unit test for the new expansion logic

**Files:**
- Create: `tests/snapper/test_generate_expansion.py`

The expansion loop is pure logic that lives in the generate route. Extract it to a helper so it can be tested without FastAPI.

- [ ] **Step 1.1: Create test directory structure**

```bash
mkdir -p tests/snapper
touch tests/__init__.py tests/snapper/__init__.py
```

- [ ] **Step 1.2: Create the test file**

```python
# tests/snapper/test_generate_expansion.py
import pytest
from modules.snapper.routes import expand_permutations_with_children


def test_no_children_unchanged():
    perms = [{"article": "A1", "properties": {"Type": "10", "Finish": "R00"}}]
    result = expand_permutations_with_children(perms, {})
    assert result == perms


def test_child_omitted_when_no_selection():
    perms = [{"article": "A1", "properties": {"Fabric_Type": "1HA"}}]
    child_resolutions = {
        "Fabric_Colour": {"parent": "Fabric_Type", "resolution": {"1HA": []}}
    }
    result = expand_permutations_with_children(perms, child_resolutions)
    assert len(result) == 1
    assert "Fabric_Colour" not in result[0]["properties"]


def test_child_expands_when_selected():
    perms = [{"article": "A1", "properties": {"Fabric_Type": "1HA"}}]
    child_resolutions = {
        "Fabric_Colour": {"parent": "Fabric_Type", "resolution": {"1HA": ["1HA01", "1HA02"]}}
    }
    result = expand_permutations_with_children(perms, child_resolutions)
    assert len(result) == 2
    assert result[0]["properties"]["Fabric_Colour"] == "1HA01"
    assert result[1]["properties"]["Fabric_Colour"] == "1HA02"


def test_mixed_parent_values():
    """Parent A has 2 child values, parent B has 1, parent C has none."""
    perms = [
        {"article": "A1", "properties": {"Fabric_Type": "A"}},
        {"article": "A1", "properties": {"Fabric_Type": "B"}},
        {"article": "A1", "properties": {"Fabric_Type": "C"}},
    ]
    child_resolutions = {
        "Fabric_Colour": {
            "parent": "Fabric_Type",
            "resolution": {"A": ["A1", "A2"], "B": ["B1"], "C": []},
        }
    }
    result = expand_permutations_with_children(perms, child_resolutions)
    assert len(result) == 4  # 2 + 1 + 1
    colours = [p["properties"].get("Fabric_Colour") for p in result]
    assert colours.count("A1") == 1
    assert colours.count("A2") == 1
    assert colours.count("B1") == 1
    assert None in colours  # C perm has no Fabric_Colour


def test_parent_val_not_in_resolution_omits_child():
    """Parent value missing from resolution dict → child property omitted."""
    perms = [{"article": "A1", "properties": {"Fabric_Type": "UNKNOWN"}}]
    child_resolutions = {
        "Fabric_Colour": {"parent": "Fabric_Type", "resolution": {"1HA": ["1HA01"]}}
    }
    result = expand_permutations_with_children(perms, child_resolutions)
    assert len(result) == 1
    assert "Fabric_Colour" not in result[0]["properties"]


def test_standalone_props_preserved():
    perms = [{"article": "A1", "properties": {"Type": "10", "Fabric_Type": "1HA"}}]
    child_resolutions = {
        "Fabric_Colour": {"parent": "Fabric_Type", "resolution": {"1HA": ["1HA01"]}}
    }
    result = expand_permutations_with_children(perms, child_resolutions)
    assert result[0]["properties"]["Type"] == "10"
    assert result[0]["properties"]["Fabric_Type"] == "1HA"
    assert result[0]["properties"]["Fabric_Colour"] == "1HA01"
```

- [ ] **Step 1.3: Run tests — verify they fail with ImportError**

```bash
cd c:\Users\XMAMWU\Projects\MK_OFML_Testsuite
python -m pytest tests/snapper/test_generate_expansion.py -v
```

Expected: `ImportError: cannot import name 'expand_permutations_with_children'`

---

### Task 2: Extract expansion helper + update ChildResolution in routes.py

**Files:**
- Modify: `modules/snapper/routes.py`

- [ ] **Step 2.1: Update `ChildResolution` model**

Find this in `routes.py` (line 172):
```python
class ChildResolution(BaseModel):
    parent: str               # parent property name, e.g. "Shell_Fabric_Type"
    resolution: dict[str, str]  # {parent_value: child_value}, e.g. {"1HA": "1HA01"}
```

Replace with:
```python
class ChildResolution(BaseModel):
    parent: str                       # parent property name, e.g. "Shell_Fabric_Type"
    resolution: dict[str, list[str]]  # {parent_value: [child_values]}, empty list = omit child
```

- [ ] **Step 2.2: Add `expand_permutations_with_children` helper function**

Add this function above the `generate_obx` route (after the Pydantic models, around line 193):

```python
def expand_permutations_with_children(
    permutations: list[dict],
    child_resolutions: dict[str, dict],
) -> list[dict]:
    """
    Expand permutations to include child property values.

    For each base permutation (parent-only cartesian product):
    - Look up child values for the permutation's parent value.
    - If child values exist: expand into N copies (one per child value).
    - If child values are empty or parent value not in resolution: keep perm as-is,
      child property is simply absent from the varcode.

    Args:
        permutations: list of {article, properties} dicts (parent-only dimensions)
        child_resolutions: {child_prop_name: {"parent": str, "resolution": {parent_val: [child_vals]}}}
            Plain dicts — callers must convert Pydantic models before calling.

    Returns:
        Expanded list of {article, properties} dicts.
    """
    if not child_resolutions:
        return permutations

    expanded = []
    for perm in permutations:
        child_expansions: list[dict] = [{}]
        for child_prop, cr in child_resolutions.items():
            parent_val = perm["properties"].get(cr["parent"], "")
            child_vals = cr["resolution"].get(parent_val, [])
            if child_vals:
                new_expansions = []
                for existing in child_expansions:
                    for cv in child_vals:
                        new_expansions.append({**existing, child_prop: cv})
                child_expansions = new_expansions
            # else: child prop omitted for this permutation — child_expansions unchanged
        for extra in child_expansions:
            expanded.append({
                "article": perm["article"],
                "properties": {**perm["properties"], **extra},
            })
    return expanded
```

- [ ] **Step 2.3: Replace the old child injection loop in `generate_obx`**

Find these lines in the route (around lines 219–227):
```python
        permutations = compute_permutations([item.article], item.selected_properties)
        # Resolve child properties per-permutation based on that permutation's parent value.
        # This avoids a cartesian explosion (child × parent instead of paired assignment).
        for perm in permutations:
            for child_prop, cr in item.child_resolutions.items():
                parent_val = perm["properties"].get(cr.parent, "")
                child_val = cr.resolution.get(parent_val, "")
                if child_val:
                    perm["properties"][child_prop] = child_val
```

Replace with:
```python
        permutations = compute_permutations([item.article], item.selected_properties)
        # Convert Pydantic ChildResolution models to plain dicts for the helper
        child_res_dicts = {
            name: {"parent": cr.parent, "resolution": cr.resolution}
            for name, cr in item.child_resolutions.items()
        }
        permutations = expand_permutations_with_children(permutations, child_res_dicts)
```

- [ ] **Step 2.4: Run tests — all should pass**

```bash
python -m pytest tests/snapper/test_generate_expansion.py -v
```

Expected: 6 tests PASS

- [ ] **Step 2.5: Commit**

```bash
git add tests/__init__.py tests/snapper/__init__.py tests/snapper/test_generate_expansion.py modules/snapper/routes.py
git commit -m "feat: expand child property permutations with per-parent multi-value selection"
```

---

## Chunk 2: Frontend — child column UI and wiring

### Task 3: Remove old hierarchy code from snapper.js

**Files:**
- Modify: `static/snapper/snapper.js`

- [ ] **Step 3.1: Remove `hierarchyModes` state variable and its initialisation**

Remove from the state block (line 32):
```javascript
let hierarchyModes = {};
```

Remove from the parse-seed handler (lines 142–144):
```javascript
  hierarchyModes = {};
  for (const col of currentSeed.property_columns) {
    if (col.is_child) hierarchyModes[col.name] = 'first';
  }
```

- [ ] **Step 3.2: Remove `_buildHierarchyModeControl` function (lines 216–238)**

Delete the entire function:
```javascript
function _buildHierarchyModeControl(childPropName) {
  ...
}
```

- [ ] **Step 3.3: Remove `resolveChildValues` function (lines 277–294)**

Delete the entire function:
```javascript
function resolveChildValues(parentSelections) {
  ...
}
```

- [ ] **Step 3.4: Update `renderDimensions` — stop skipping child columns and remove mode control**

Find lines 172–181:
```javascript
  for (const col of currentSeed.property_columns) {
    if (col.is_child) continue;
    const wrapper = document.createElement('div');
    wrapper.className = 'flex flex-col gap-1';
    wrapper.appendChild(_buildCheckboxColumn(col.name, col.values, col.seed_value));
    const childName = parentHasChild.get(col.name);
    if (childName) wrapper.appendChild(_buildHierarchyModeControl(childName));
    dimensionColumns.appendChild(wrapper);
  }
```

Replace with:
```javascript
  for (const col of currentSeed.property_columns) {
    if (col.is_child) continue;
    const wrapper = document.createElement('div');
    wrapper.className = 'flex flex-col gap-1';
    wrapper.appendChild(_buildCheckboxColumn(col.name, col.values, col.seed_value));
    const childName = parentHasChild.get(col.name);
    if (childName) {
      const childCol = currentSeed.property_columns.find(c => c.name === childName);
      if (childCol) wrapper.appendChild(_buildChildColumn(childCol));
    }
    dimensionColumns.appendChild(wrapper);
  }
```

- [ ] **Step 3.5: Update `addToQueueBtn` handler — replace `childResolutions` and `count`**

Find in the handler (lines 324–326):
```javascript
    childResolutions: resolveChildValues(parentSelections),
    count: computePermCount(parentSelections),
```

Replace with:
```javascript
    childResolutions: getChildSelections(),
    count: currentPermCount,
```

Also add `let currentPermCount = 0;` to the state block at the top of the file alongside the other state variables (`currentSeed`, `queue`).

- [ ] **Step 3.6: Refresh the app and confirm no JS errors appear**

Open `http://localhost:8080/snapper/` and check the browser console. Upload a seed for a range **without** hierarchy (no parent-child pairs detected). Expected: no errors. Do NOT upload a hierarchy seed at this stage — `_buildChildColumn` does not exist yet and will throw `TypeError: _buildChildColumn is not a function`.

---

### Task 4: Add `_buildChildColumn` and `_updateChildSections`

**Files:**
- Modify: `static/snapper/snapper.js`

- [ ] **Step 4.1: Add `onDimensionChange` helper**

Add after the `_buildCheckboxColumn` function:

```javascript
function onDimensionChange() {
  _updateChildSections();
  updatePermCount();
}
```

- [ ] **Step 4.2: Update `_buildCheckboxColumn` to call `onDimensionChange` instead of `updatePermCount`**

In `_buildCheckboxColumn`, find:
```javascript
  col.querySelectorAll('.dim-check').forEach(cb => cb.addEventListener('change', updatePermCount));
```

Replace with:
```javascript
  col.querySelectorAll('.dim-check').forEach(cb => cb.addEventListener('change', onDimensionChange));
```

Also update the All/None buttons in `_buildCheckboxColumn`:
```javascript
  col.querySelector('.select-all-btn').addEventListener('click', () => {
    col.querySelectorAll('.dim-check').forEach(cb => { cb.checked = true; });
    onDimensionChange();
  });
  col.querySelector('.select-none-btn').addEventListener('click', () => {
    col.querySelectorAll('.dim-check').forEach(cb => { cb.checked = false; });
    onDimensionChange();
  });
```

- [ ] **Step 4.3: Add `_updateChildSections` function**

Add after `onDimensionChange`:

```javascript
function _updateChildSections() {
  if (!currentSeed) return;
  const sel = getParentSelections();

  for (const childCol of currentSeed.property_columns.filter(c => c.is_child)) {
    const checkedParentVals = new Set(sel[childCol.parent] || []);
    const colEl = dimensionColumns.querySelector(`[data-prop-name="${CSS.escape(childCol.name)}"]`);
    if (!colEl) continue;

    colEl.querySelectorAll('.child-section').forEach(section => {
      const pv = section.dataset.parentVal;
      const active = checkedParentVals.has(pv);
      section.querySelectorAll('.child-check').forEach(cb => {
        cb.disabled = !active;
        if (!active) cb.checked = false;
      });
      section.querySelectorAll('.child-label').forEach(lbl => {
        lbl.classList.toggle('text-gray-400', !active);
        lbl.classList.toggle('cursor-not-allowed', !active);
        lbl.classList.toggle('text-gray-700', active);
        lbl.classList.toggle('cursor-pointer', active);
      });
      // Dim the section header when inactive
      const header = section.querySelector('.section-header');
      if (header) {
        header.classList.toggle('text-gray-300', !active);
        header.classList.toggle('text-gray-500', active);
      }
    });
  }
}
```

- [ ] **Step 4.4: Add `_buildChildColumn` function**

Add after `_updateChildSections`:

```javascript
function _buildChildColumn(col) {
  // col = { name, values, is_child, parent, mapping }
  // Build a code→label lookup from the flat values list
  const labelOf = {};
  for (const v of col.values) labelOf[v.code] = v.label;

  const el = document.createElement('div');
  el.className = 'bg-white rounded-lg shadow p-3 min-w-44 max-w-56 flex flex-col';
  el.dataset.propName = col.name;

  // Build grouped sections HTML
  const sectionsHtml = Object.entries(col.mapping || {}).map(([parentVal, childCodes]) => {
    const childRows = childCodes.map(code => {
      const label = labelOf[code] || code;
      const hasLabel = label && label !== code;
      return `
        <label class="child-label flex items-center gap-1 text-xs text-gray-400 cursor-not-allowed">
          <input type="checkbox" class="child-check" data-prop="${escapeHtml(col.name)}"
            data-value="${escapeHtml(code)}" data-parent-val="${escapeHtml(parentVal)}" disabled>
          <span class="font-mono">${escapeHtml(code)}</span>
          ${hasLabel ? `<span class="text-gray-300">·</span><span class="truncate">${escapeHtml(label)}</span>` : ''}
        </label>`;
    }).join('');
    return `
      <div class="child-section mb-1" data-parent-val="${escapeHtml(parentVal)}">
        <div class="section-header text-xs font-mono text-gray-300 px-1 pb-0.5 border-b border-gray-100 mb-0.5">${escapeHtml(parentVal)}</div>
        <div class="pl-1 space-y-0.5">${childRows}</div>
      </div>`;
  }).join('');

  el.innerHTML = `
    <div class="font-semibold text-sm text-gray-700 mb-0.5 border-b pb-1" title="${escapeHtml(col.name)}">${escapeHtml(col.name)}</div>
    <div class="text-xs text-gray-400 mb-2">↳ ${escapeHtml(col.parent)}</div>
    <div class="flex gap-1 mb-2">
      <button class="text-xs text-blue-600 hover:underline select-all-btn">All</button>
      <span class="text-gray-300">|</span>
      <button class="text-xs text-blue-600 hover:underline select-none-btn">None</button>
    </div>
    <div class="overflow-y-auto max-h-64">${sectionsHtml}</div>`;

  el.querySelector('.select-all-btn').addEventListener('click', () => {
    el.querySelectorAll('.child-check:not(:disabled)').forEach(cb => { cb.checked = true; });
    onDimensionChange();
  });
  el.querySelector('.select-none-btn').addEventListener('click', () => {
    el.querySelectorAll('.child-check:not(:disabled)').forEach(cb => { cb.checked = false; });
    onDimensionChange();
  });
  el.querySelectorAll('.child-check').forEach(cb => cb.addEventListener('change', onDimensionChange));

  return el;
}
```

---

### Task 5: Add `getChildSelections` and update permutation counting

**Files:**
- Modify: `static/snapper/snapper.js`

- [ ] **Step 5.1: Add `getChildSelections` function**

Add after `getParentSelections`:

```javascript
function getChildSelections() {
  if (!currentSeed) return {};
  const result = {};
  for (const col of currentSeed.property_columns) {
    if (!col.is_child) continue;
    const resolution = {};
    for (const parentVal of Object.keys(col.mapping || {})) {
      const selected = [];
      dimensionColumns.querySelectorAll(
        `.child-check[data-prop="${CSS.escape(col.name)}"][data-parent-val="${CSS.escape(parentVal)}"]:checked`
      ).forEach(cb => selected.push(cb.dataset.value));
      resolution[parentVal] = selected;
    }
    result[col.name] = { parent: col.parent, resolution };
  }
  return result;
}
```

- [ ] **Step 5.2: Replace `computePermCount` and `updatePermCount` with new formulas**

Remove `computePermCount` entirely and replace `updatePermCount` with:

```javascript
function updatePermCount() {
  if (!currentSeed) { permCount.textContent = ''; return; }

  const sel = getParentSelections();
  const childSel = getChildSelections();

  // Which props are parents of a child?
  const parentProps = new Set(
    currentSeed.property_columns.filter(c => c.is_child).map(c => c.parent)
  );

  // Standalone dimensions: not a child and not a parent of a child
  const factors = [];
  for (const col of currentSeed.property_columns) {
    if (col.is_child || parentProps.has(col.name)) continue;
    const n = (sel[col.name] || []).length;
    if (n > 0) factors.push(n);
  }

  // Parent-child pair expansion: Σ max(1, child_count) per selected parent value
  for (const childCol of currentSeed.property_columns.filter(c => c.is_child)) {
    const parentVals = sel[childCol.parent] || [];
    if (parentVals.length === 0) continue;
    const resolution = childSel[childCol.name]?.resolution || {};
    let expansion = 0;
    for (const pv of parentVals) {
      expansion += Math.max(1, (resolution[pv] || []).length);
    }
    factors.push(expansion);
  }

  const count = factors.length ? factors.reduce((a, b) => a * b, 1) : 0;
  currentPermCount = count;  // stored for use by addToQueueBtn handler
  permCount.textContent = `${count.toLocaleString()} permutations`;
  permCount.className = 'text-sm font-medium ' + (
    count > ERROR_LIMIT ? 'text-red-600' :
    count > WARN_LIMIT  ? 'text-amber-600' : 'text-gray-700'
  );
  if (count > ERROR_LIMIT) permCount.textContent += ` ⚠ Consider splitting (max: ${ERROR_LIMIT})`;
  updateFilenamePreview();
}
```

- [ ] **Step 5.3: Commit**

```bash
git add static/snapper/snapper.js
git commit -m "feat: show child property column with grouped parent-gated values"
```

---

### Task 6: Manual integration test

- [ ] **Step 6.1: Start the server**

```bash
cd c:\Users\XMAMWU\Projects\MK_OFML_Testsuite
python main.py
```

- [ ] **Step 6.2: Upload a seed OBX for a range with a known parent-child pair**

Open `http://localhost:8080/snapper/`. Upload a seed for a range with hierarchy detection (e.g. `cosm`, `always`, or `ratio_rebuild`). Enter the repo path and click Parse Seed.

Expected: columns render, child column appears below its parent column with `↳ {parent_name}` subtitle. All child values are greyed out.

- [ ] **Step 6.3: Check a parent value — verify child section enables**

Tick one parent value (e.g. `1HA`). Expected: the `1HA` section in the child column becomes enabled (black text, clickable checkboxes). Other sections remain grey.

- [ ] **Step 6.4: Select some child values and verify permutation count**

Tick 2 child values under `1HA`. Expected: permutation count updates. With just parent `1HA` selected and 2 child values, count = 2 (or 2 × other standalone selections).

- [ ] **Step 6.5: Check a second parent value with no child values ticked — verify count**

Tick a second parent value (e.g. `2AB`) but leave its child values unchecked. Expected: count increases by 1 per additional parent (child omitted = 1 extra perm, not 0).

- [ ] **Step 6.6: Add to queue and generate — inspect OBX**

Add to queue and click Generate. Open the downloaded OBX in a text editor. Expected:
- Permutations with parent `1HA`: varcode includes `Fabric_Colour=...`
- Permutations with parent `2AB`: varcode does NOT include `Fabric_Colour`

- [ ] **Step 6.7: Test false-positive escape hatch**

If the range has a property incorrectly detected as a child, confirm that all its values are visible (grouped under their detected parent), and that ticking the parent value makes them selectable. The user can now use child values even in a false-positive case.

- [ ] **Step 6.8: Final commit**

```bash
git add static/snapper/snapper.js
git commit -m "feat: complete child property UX redesign — grouped gated columns, omit-if-empty varcode"
```

# Multi-Level Hierarchy Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the Snapper UI to render and correctly activate property chains deeper than one level (e.g. Group → Fabric → Finish).

**Architecture:** Two surgical changes to `snapper.js`. The backend already detects multi-level hierarchies correctly — `detect_hierarchy` returns `Group→Fabric` and `Fabric→Finish` as separate entries, and `property_columns` marks both `Fabric` and `Finish` as children with their respective parents. The gaps are purely in the frontend: (1) `renderDimensions` only appends one level of child columns to each wrapper, and (2) `_updateChildSections` builds its selection map from `dim-check` inputs only, missing child-check values that deeper columns need to activate their sections.

**Not affected by these changes:**
- `getChildSelections` (line 582) — already reads all `.child-check` by iterating `property_columns.is_child` columns; it does not depend on depth.
- `_updateAllTierIndicators` — already queries `[data-prop-name]` for every column including child columns; `_buildChildColumn` already sets `el.dataset.propName` so grandchild columns are found correctly.

**Tech Stack:** Vanilla JS frontend. No build step.

---

## Chunk 1: Render the full child chain

### Task 1: Follow `parentHasChild` to all depths in `renderDimensions`

**Files:**
- Modify: `static/snapper/snapper.js` (lines 305–318, `renderDimensions` loop)

- [ ] **Step 1: Understand current one-level loop**

  In `renderDimensions` (line 305), the outer loop skips `is_child` columns. For each root column it appends one direct child if found in `parentHasChild`. Since `Fabric` is `is_child`, the loop never reaches it, so `parentHasChild.get("Fabric") === "Finish"` is never consulted and `Finish` is silently dropped.

  The `parentHasChild` map (lines 300–303) is built by setting `parent → child` for every child column. For a linear chain `Group → Fabric → Finish`, this produces `{"Group": "Fabric", "Fabric": "Finish"}`. The map construction itself is correct and does **not** need changing — both entries are keyed by parent name and the while-chain traversal in Step 2 will follow them in sequence.

- [ ] **Step 2: Replace the one-shot child lookup with a while-chain**

  Replace lines 312–316:
  ```js
    const childName = parentHasChild.get(col.name);
    if (childName) {
      const childCol = group.property_columns.find(c => c.name === childName);
      if (childCol) wrapper.appendChild(_buildChildColumn(childCol, group.articles));
    }
  ```
  With:
  ```js
    // Follow the child chain to any depth (e.g. Group → Fabric → Finish → …).
    // parentHasChild maps each parent to its immediate child; the while-loop
    // traverses the full linear chain without needing to change the map itself.
    let current = col.name;
    while (true) {
      const nextName = parentHasChild.get(current);
      if (!nextName) break;
      const nextCol = group.property_columns.find(c => c.name === nextName);
      if (!nextCol) break;
      wrapper.appendChild(_buildChildColumn(nextCol, group.articles));
      current = nextName;
    }
  ```

- [ ] **Step 3: Verify rendering**

  Load a seed for an article with a 3-level chain — article `71AR` (or similar) which has Group → Fabric → Finish. If a suitable OBX isn't on hand, ask the team for one or temporarily modify the seed article in the URL to point at an article known to have this structure. Confirm:
  - Three adjacent columns appear in the wrapper: the parent checkbox column plus two child columns.
  - The `Finish` column header shows `↳ Fabric` (its immediate parent).
  - All `Finish` checkboxes start disabled (sections are not yet active).
  - Single-level hierarchies (ranges without a 3-level chain) still render identically to before.

- [ ] **Step 4: Commit**
  ```
  git add static/snapper/snapper.js
  git commit -m "feat: render full child chain in renderDimensions"
  ```

---

## Chunk 2: Activate grandchild sections correctly

### Task 2: Fix `_updateChildSections` to propagate selections through child-check columns

**Files:**
- Modify: `static/snapper/snapper.js` (lines 408–439, `_updateChildSections`)

- [ ] **Step 1: Understand the current bug**

  `_updateChildSections` builds `sel` once via `getParentSelections()`, which only reads `.dim-check:checked`. When processing the `Finish` column (child of `Fabric`), it looks up `sel["Fabric"]` — but `Fabric` values are `.child-check`, not `.dim-check`, so `sel["Fabric"]` is always `undefined` → `checkedParentVals` is always empty → all `Finish` sections stay disabled regardless of `Fabric` selections.

  The fix is to grow `sel` incrementally as the loop runs: after processing each child column, read the now-current checked child-checks for that column and store them into `sel`. The next column in the chain finds `sel[its parent]` already populated.

  **Important:** This relies on `property_columns` being in parent-before-child declaration order (Fabric before Finish). The OCD reader derives property order from the seed article's varcode, which pCon writes in OCD property declaration order — parents are always declared before the children that condition on them. This ordering is stable.

- [ ] **Step 2: Add the four-line `sel` update at the end of the for-loop body**

  After the existing `colEl.querySelectorAll('.child-section').forEach(...)` block (and before the closing `}` of the for-loop), add:
  ```js
      // Record checked values of this column so any deeper child can read them.
      const nowChecked = [];
      colEl.querySelectorAll('.child-check:checked').forEach(cb => nowChecked.push(cb.dataset.value));
      sel[childCol.name] = nowChecked;
  ```

  The full updated function for reference:
  ```js
  function _updateChildSections() {
    if (!currentSeed) return;
    const group = currentSeed.groups[currentGroupIndex];
    if (!group) return;

    // Start with top-level (dim-check) selections; grow the map as we process each
    // child column so that deeper columns find their parent's values already set.
    // Relies on property_columns being in parent-before-child order (OCD guarantee).
    const sel = getParentSelections();

    for (const childCol of group.property_columns.filter(c => c.is_child)) {
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
        const header = section.querySelector('.section-header');
        if (header) {
          header.classList.toggle('text-gray-300', !active);
          header.classList.toggle('text-gray-500', active);
        }
      });

      // Record checked values of this column so any deeper child can read them.
      const nowChecked = [];
      colEl.querySelectorAll('.child-check:checked').forEach(cb => nowChecked.push(cb.dataset.value));
      sel[childCol.name] = nowChecked;
    }
  }
  ```

- [ ] **Step 3: Verify activation**

  With the same 3-level seed:
  - Select a `Group` value in the checkbox column. The `Fabric` column's sections for that Group value become active; other Fabric sections stay disabled. All `Finish` sections remain disabled.
  - Check a `Fabric` value. The `Finish` column's sections for that Fabric value become active.
  - Uncheck the `Fabric` value. The corresponding `Finish` sections disable and uncheck automatically.
  - Uncheck the `Group` value. All `Fabric` sections disable and uncheck; all `Finish` sections also disable and uncheck (cascade works correctly).

- [ ] **Step 4: Verify permutation count**

  Select one Group value, two Fabric values under it, and several Finish values under each fabric. Confirm the permutation counter reflects the correct cartesian product (e.g. 1 Group × 2 Fabric × N Finish = 2N if Finish count is the same under each Fabric).

- [ ] **Step 5: Verify no regression on single-level ranges**

  Load a seed that only has a 2-level chain (e.g. a range with only Group → Fabric, no Finish). Confirm everything works identically to before: Fabric sections activate when Group values are checked.

- [ ] **Step 6: Commit**
  ```
  git add static/snapper/snapper.js
  git commit -m "feat: propagate child selections in _updateChildSections for multi-level chains"
  ```

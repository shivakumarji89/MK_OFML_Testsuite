# Snapper — pCon Dialogue Feature Design
**Date:** 2026-03-23
**Status:** Approved
**Extends:** `2026-03-22-ofml-testsuite-design.md`

---

## 1. Overview

This feature adds a two-stage "dialogue" between the Snapper Generator and pCon Planner, allowing the QA team to automatically clean pCon exports and remove configurations that pCon rejected as invalid.

**The problem:** When an OBX containing invalid configurations is imported into pCon and Updated, pCon cannot simply delete invalid items — it offers a migration instead. After rejecting the migration and re-exporting, valid items have been resolved (article number, price, description filled in) while invalid items remain untouched.

**The solution:** Inject a sentinel string (`__SNAPPER_RAW__`) into every article during Raw generation. After pCon Update, valid articles have their fields overwritten (sentinel gone); invalid articles remain untouched (sentinel still present). Re-importing the pCon export into the tool removes sentinel-bearing articles and produces a Clean OBX.

### End-to-end workflow

```
Seed OBX (from pCon)
    ↓ parse-seed
Dimension columns → select values → Add to Queue
    ↓ Generate (per item or batch)
Raw OBX  [fin_NOFIN_Low_tables_Raw.obx]  — contains __SNAPPER_RAW__ sentinel
    ↓ import into pCon → Update → reject migration → re-export
pCon OBX  [Project_2026-03-23_...obx]
    ↓ drop into queue card
Clean OBX  [fin_NOFIN_Low_tables_Clean.obx]  — sentinel articles removed
```

---

## 2. UI Layout

The page layout changes from a left-main / right-sidebar split to a full-width vertical flow:

```
[Header: title + repo path]
[Seed upload section — drag-and-drop hybrid]
[Dimension columns — full width, horizontally scrollable]
[Permutation count · Label input · + Add to Queue button]
[────────────────── Queue strip ───────────────────────────]
[Card 1]  [Card 2]  [Card 3]  …                [Generate All]
```

### Seed upload
The `<input type="file">` is replaced by a drag-and-drop zone that also opens the file picker on click. Same position in the page. Accepts `.obx` and `.xml`.

### Permutation / label row
Sits directly below the dimension columns:
- Left: permutation count (existing, colour-coded red/amber/grey)
- Centre: label text input — "Label (optional)" — user types their differentiator (e.g. `Low tables`)
- Right: `+ Add to Queue` button

### Queue strip
A horizontal strip of cards, scrollable if many items. `Generate All` button at the far right of the strip (or below it if the strip is full-width).

Each card is approximately 220px wide. Cards are colour-coded by state (see Section 4).

---

## 3. Filename Scheme

### Raw output (Stage 1)

```
[series]_[article]_[label]_Raw.obx      (with label)
[series]_[article]_Raw.obx              (without label)
```

- `series`: lowercased series code from parsed seed (e.g. `fin`)
- `article`: article code as-is from parsed seed (e.g. `NOFIN`)
- `label`: user input with spaces replaced by underscores, special characters stripped (e.g. `Low_tables`)
- `_Raw` is always appended — not editable

**Batch generate (Generate All):** produces a zip containing one OBX per queue item.
- Zip filename: `[series]_[article]_Raw.zip` (no label — the zip contains multiple labels)
- Each OBX inside: `[series]_[article]_[label]_Raw.obx`
- All generated cards turn orange.

**Individual generate:** produces a single OBX for that card only.

### Clean output (Stage 2)

```
[series]_[article]_[label]_Clean.obx
```

The label comes from the queue card the file was dropped onto — the tool already knows it. The user never has to type it again.

---

## 4. Queue Card States

Each queue item persists through three states, colour-coded:

### Red — not yet generated
- Shows: filename preview (`fin_NOFIN_Low_tables_Raw.obx`)
- Controls: `Generate` button, `✕` remove button

### Orange — Raw generated, awaiting pCon export
- Shows: filename (greyed), "Waiting for pCon export"
- Controls: drag-and-drop zone ("Drop pCon export here"), `Re-generate` button
- Drop zone accepts `.obx` and `.xml`

### Green — Cleaned
- Shows: clean filename (`fin_NOFIN_Low_tables_Clean.obx`), summary (`✓ 45 kept · 3 removed`)
- Controls: `Done` button (removes card from queue)

---

## 5. Queue Persistence

The queue is persisted to `localStorage` under the key `snapper_queue`. It is serialised to JSON on every state change (add, generate, import, remove).

On page load the queue is restored from localStorage, including orange cards with their drop zones. This means:
- The tool survives browser refresh, tab close, and server restart
- The team can generate a batch of Raw OBXs, close the tool, run pCon the next day, and come back to find all cards still orange and ready for import
- Future feature: the clean summary (`kept / removed` counts) can also be stored per card for later analysis

The queue is cleared only when the user explicitly removes cards (green "Done" or red "✕").

---

## 6. Sentinel Injection

**Sentinel value:** `__SNAPPER_RAW__`

**Injection point:** `<artNr type='final' default='1'>` on every `<bskArticle>` in the Raw OBX.

**Mechanism:** In `build_obx_from_seed` (`generator.py`), during the per-permutation string-substitution loop:
- If the seed template already contains `<artNr type="final"`, replace its text content with `__SNAPPER_RAW__`
- If it does not, insert `<artNr type="final" default="1">__SNAPPER_RAW__</artNr>` after the `<artNr type="base">` element

**After pCon Update:**
- Valid articles: pCon overwrites `artNr type='final'` with the resolved article number → sentinel gone
- Invalid articles: pCon leaves the element untouched → sentinel remains

---

## 7. Clean Endpoint

### `POST /api/snapper/clean-obx`

**Input:** multipart form
- `file`: the pCon-exported OBX file
- `label`: the queue item's label string (used to assemble the clean filename)

**Processing:**
1. Parse XML
2. Walk all `<bskArticle>` elements
3. Remove any where `<artNr type='final'>` text content equals `__SNAPPER_RAW__`
4. Re-serialise to XML string

**Response:** OBX file download
- `Content-Type: application/xml`
- `Content-Disposition: attachment; filename="[series]_[article]_[label]_Clean.obx"`
- `X-Kept-Count: 45` (response header)
- `X-Removed-Count: 3` (response header)

The JS reads these headers before triggering the blob download and displays the summary line on the queue card: `✓ 45 kept · 3 removed`.

---

## 8. Files Changed

| File | Change |
|------|--------|
| `static/snapper/index.html` | Full layout rewrite: vertical flow, drag-and-drop seed zone, permutation/label row, queue strip |
| `static/snapper/snapper.js` | Queue persistence (localStorage), card state machine, drag-and-drop for seed and per-card import, filename assembly, clean endpoint call |
| `modules/snapper/generator.py` | Sentinel injection in `build_obx_from_seed` |
| `modules/snapper/routes.py` | New `POST /api/snapper/clean-obx` endpoint |

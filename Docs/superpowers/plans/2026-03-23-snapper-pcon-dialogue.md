# Snapper pCon Dialogue — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two-stage pCon dialogue: Raw OBX generation with a sentinel marker, and Clean OBX generation by stripping sentinel-bearing articles from pCon exports.

**Architecture:** Backend gains a `SENTINEL` constant injected into every article's `<artNr type='final'>` during Raw generation, and a new `POST /api/snapper/clean-obx` endpoint. Frontend is restructured to a vertical-flow layout with a persistent, colour-coded queue strip at the bottom; queue state survives page refresh via localStorage.

**Tech Stack:** Python + FastAPI + xml.etree.ElementTree (backend); Vanilla JS + Tailwind CSS CDN (frontend); pytest (tests)

---

## Chunk 1: Backend

### Task 1: Sentinel injection in generator.py

**Files:**
- Modify: `modules/snapper/generator.py`
- Test: `tests/test_generator.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_generator.py`:

```python
from modules.snapper.generator import build_obx_from_seed, SENTINEL

_SEED_NO_FINAL = """<?xml version='1.0'?>
<cutBuffer>
  <state sessionId='s'/>
  <versionInfo vendorKey='EasternGraphics' appKey='EAI-Server' appVersion='4.18.3' bskXmlVersion='1.8.10'/>
  <items>
    <bskArticle basketId='bid-1' itemType='BasketArticle' updateState='UpToDate'>
      <manufacturer id='HM'/>
      <series id='TEST'/>
      <artNr type='base'>T01</artNr>
      <artNr type='ofmlvarcode'>TC.Prop=Val</artNr>
    </bskArticle>
  </items>
</cutBuffer>"""

_SEED_WITH_FINAL = """<?xml version='1.0'?>
<cutBuffer>
  <state sessionId='s'/>
  <versionInfo vendorKey='EasternGraphics' appKey='EAI-Server' appVersion='4.18.3' bskXmlVersion='1.8.10'/>
  <items>
    <bskArticle basketId='bid-1' itemType='BasketArticle' updateState='UpToDate'>
      <manufacturer id='HM'/>
      <series id='TEST'/>
      <artNr type='base'>T01</artNr>
      <artNr type='ofmlvarcode'>TC.Prop=Val</artNr>
      <artNr type='final' default='1'>OLD_CODE</artNr>
    </bskArticle>
  </items>
</cutBuffer>"""

def _artnrs(article_el):
    return {a.get("type"): (a.text or "") for a in article_el.findall("artNr")}


def test_sentinel_injected_when_no_final_element():
    result = build_obx_from_seed(_SEED_NO_FINAL, [{"article": "T01", "properties": {"Prop": "Val"}}], {"Prop": "TC"})
    root = ET.fromstring(result)
    for art in root.findall(".//bskArticle"):
        assert _artnrs(art).get("final") == SENTINEL


def test_sentinel_replaces_existing_final_element():
    result = build_obx_from_seed(_SEED_WITH_FINAL, [{"article": "T01", "properties": {"Prop": "Val"}}], {"Prop": "TC"})
    root = ET.fromstring(result)
    for art in root.findall(".//bskArticle"):
        assert _artnrs(art).get("final") == SENTINEL


def test_sentinel_present_on_every_permutation():
    perms = [
        {"article": "T01", "properties": {"Prop": "A"}},
        {"article": "T01", "properties": {"Prop": "B"}},
        {"article": "T01", "properties": {"Prop": "C"}},
    ]
    result = build_obx_from_seed(_SEED_NO_FINAL, perms, {"Prop": "TC"})
    root = ET.fromstring(result)
    articles = root.findall(".//bskArticle")
    assert len(articles) == 3
    for art in articles:
        assert _artnrs(art).get("final") == SENTINEL
```

- [ ] **Step 2: Run to confirm failure**

```
cd c:\Users\XMAMWU\Projects\MK_OFML_Testsuite
pytest tests/test_generator.py::test_sentinel_injected_when_no_final_element -v
```

Expected: `ImportError: cannot import name 'SENTINEL'`

- [ ] **Step 3: Add SENTINEL and inject it in build_obx_from_seed**

In `modules/snapper/generator.py`, add after the imports at the top:

```python
SENTINEL = "__SNAPPER_RAW__"
```

In `build_obx_from_seed`, immediately after the line `article_template = ET.tostring(seed_article, encoding="unicode")` (currently line 181), insert:

```python
    # Inject sentinel into <artNr type='final'> so pCon-updated valid articles
    # lose the sentinel while unresolved invalid articles keep it.
    _tmpl = ET.fromstring(article_template)
    _final = next((a for a in _tmpl.findall("artNr") if a.get("type") == "final"), None)
    if _final is None:
        _final = ET.SubElement(_tmpl, "artNr")
        _final.set("type", "final")
        _final.set("default", "1")
    _final.text = SENTINEL
    article_template = ET.tostring(_tmpl, encoding="unicode")
```

- [ ] **Step 4: Run all three new tests**

```
pytest tests/test_generator.py::test_sentinel_injected_when_no_final_element tests/test_generator.py::test_sentinel_replaces_existing_final_element tests/test_generator.py::test_sentinel_present_on_every_permutation -v
```

Expected: all PASS

- [ ] **Step 5: Run full suite to check for regressions**

```
pytest tests/ -v
```

Expected: all existing tests still pass

- [ ] **Step 6: Commit**

```bash
git add modules/snapper/generator.py tests/test_generator.py
git commit -m "feat: inject __SNAPPER_RAW__ sentinel into artNr type='final' during Raw generation"
```

---

### Task 2: POST /api/snapper/clean-obx endpoint

**Files:**
- Modify: `modules/snapper/routes.py`
- Test: `tests/test_routes.py`

- [ ] **Step 1: Write the failing tests**

Add to the top of `tests/test_routes.py`:

```python
import xml.etree.ElementTree as ET
from modules.snapper.generator import SENTINEL
```

Add the following test helpers and tests at the bottom of `tests/test_routes.py`:

```python
# ── /clean-obx tests ───────────────────────────────────────────────────────────

def _make_pcon_obx(articles: list[tuple[str, str | None]]) -> bytes:
    """Build a minimal pCon-style OBX. articles: [(base_artnr, final_artnr_or_None)]"""
    item_blocks = []
    for i, (base, final) in enumerate(articles):
        final_el = f'<artNr type="final">{final}</artNr>' if final is not None else ""
        item_blocks.append(
            f'<bskArticle basketId="bid-{i}" itemType="BasketArticle" updateState="UpToDate">'
            f'<manufacturer id="HM"/><series id="test"/>'
            f'<artNr type="base">{base}</artNr>{final_el}'
            f'</bskArticle>'
        )
    calc_entries = "".join(f'<itemCalculationChanges id="bid-{i}"/>' for i in range(len(articles)))
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<cutBuffer><state sessionId="t"/>'
        f'<items>{"".join(item_blocks)}</items>'
        f'<docCalculationChanges ppName="p">{calc_entries}</docCalculationChanges>'
        f'</cutBuffer>'
    ).encode()


def _clean(obx_bytes: bytes, label: str = "Low tables"):
    return client.post(
        "/api/snapper/clean-obx",
        data={"label": label},
        files={"file": ("pcon.obx", io.BytesIO(obx_bytes), "application/xml")},
    )


def test_clean_obx_returns_200():
    resp = _clean(_make_pcon_obx([("T01", "REAL")]))
    assert resp.status_code == 200


def test_clean_obx_removes_sentinel_articles():
    obx = _make_pcon_obx([("T01", "REAL"), ("T02", SENTINEL), ("T03", "REAL2")])
    resp = _clean(obx)
    root = ET.fromstring(resp.content)
    assert len(root.findall(".//bskArticle")) == 2


def test_clean_obx_kept_and_removed_headers():
    obx = _make_pcon_obx([("T01", "REAL"), ("T02", SENTINEL), ("T03", "REAL2")])
    resp = _clean(obx)
    assert resp.headers["X-Kept-Count"] == "2"
    assert resp.headers["X-Removed-Count"] == "1"


def test_clean_obx_filename_contains_label():
    resp = _clean(_make_pcon_obx([("T01", "REAL")]), label="Low tables")
    assert "Low_tables_Clean.obx" in resp.headers["Content-Disposition"]


def test_clean_obx_empty_label():
    resp = _clean(_make_pcon_obx([("T01", "REAL")]), label="")
    assert "Clean.obx" in resp.headers["Content-Disposition"]


def test_clean_obx_removes_doc_calc_entries():
    obx = _make_pcon_obx([("T01", "REAL"), ("T02", SENTINEL)])
    resp = _clean(obx)
    root = ET.fromstring(resp.content)
    doc_calc = root.find("docCalculationChanges")
    assert doc_calc is not None
    assert len(doc_calc.findall("itemCalculationChanges")) == 1


def test_clean_obx_all_valid():
    obx = _make_pcon_obx([("T01", "CODE1"), ("T02", "CODE2")])
    resp = _clean(obx)
    assert resp.headers["X-Kept-Count"] == "2"
    assert resp.headers["X-Removed-Count"] == "0"
```

- [ ] **Step 2: Run to confirm failure**

```
pytest tests/test_routes.py::test_clean_obx_returns_200 -v
```

Expected: FAIL with 404 (route does not exist)

- [ ] **Step 3: Add imports to routes.py**

At the top of `modules/snapper/routes.py`, add:

```python
import re
import xml.etree.ElementTree as ET
```

Change the generator import line to include `SENTINEL`:

```python
from .generator import compute_permutations, build_obx, build_obx_from_seed, SENTINEL
```

- [ ] **Step 4: Add the clean-obx endpoint to routes.py**

Append at the end of `modules/snapper/routes.py`:

```python
@router.post("/clean-obx")
async def clean_obx(
    file: UploadFile = File(...),
    label: str = Form(""),
):
    """
    Remove articles that still carry the __SNAPPER_RAW__ sentinel from a
    pCon-exported OBX. Returns the cleaned OBX with X-Kept-Count and
    X-Removed-Count response headers.
    """
    raw = await file.read()
    try:
        root = ET.parse(io.BytesIO(raw)).getroot()
    except ET.ParseError as e:
        raise HTTPException(status_code=400, detail=f"Could not parse OBX: {e}")

    # Read series and article before removing anything
    series = "unknown"
    article_code = "unknown"
    first_art = root.find(".//bskArticle")
    if first_art is not None:
        s_el = first_art.find("series")
        if s_el is not None:
            series = s_el.get("id", "unknown").lower()
        for a in first_art.findall("artNr"):
            if a.get("type") == "base":
                article_code = a.text or "unknown"
                break

    items_el = root.find(".//items")
    if items_el is None:
        raise HTTPException(status_code=400, detail="No <items> element found in OBX")

    removed_ids: set[str] = set()
    removed = 0
    for art in list(items_el.findall("bskArticle")):
        is_sentinel = any(
            a.get("type") == "final" and (a.text or "").strip() == SENTINEL
            for a in art.findall("artNr")
        )
        if is_sentinel:
            removed_ids.add(art.get("basketId", ""))
            items_el.remove(art)
            removed += 1

    kept = len(items_el.findall("bskArticle"))

    doc_calc = root.find("docCalculationChanges")
    if doc_calc is not None:
        for entry in list(doc_calc.findall("itemCalculationChanges")):
            if entry.get("id") in removed_ids:
                doc_calc.remove(entry)

    safe_label = re.sub(r"[^\w]", "_", label.strip().replace(" ", "_")) if label.strip() else ""
    parts = [p for p in [series, article_code, safe_label, "Clean"] if p]
    filename = "_".join(parts) + ".obx"

    xml_out = ET.tostring(root, encoding="unicode")

    return Response(
        content=xml_out,
        media_type="application/xml",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Kept-Count": str(kept),
            "X-Removed-Count": str(removed),
        },
    )
```

- [ ] **Step 5: Run all clean-obx tests**

```
pytest tests/test_routes.py -k "clean_obx" -v
```

Expected: all PASS

- [ ] **Step 6: Run full suite**

```
pytest tests/ -v
```

Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add modules/snapper/routes.py tests/test_routes.py
git commit -m "feat: add POST /api/snapper/clean-obx endpoint to strip sentinel articles"
```

---

## Chunk 2: Frontend

### Task 3: Rewrite index.html

**Files:**
- Modify: `static/snapper/index.html` (full rewrite)

- [ ] **Step 1: Replace index.html entirely**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Snapper Generator — OFML Testsuite</title>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-100 min-h-screen flex flex-col">

  <header class="bg-white shadow sticky top-0 z-10">
    <div class="max-w-full px-6 py-3 flex flex-wrap items-end gap-4">
      <a href="/" class="text-sm text-blue-600 hover:underline mr-2">← Home</a>
      <h1 class="text-lg font-bold text-gray-800 mr-4">Snapper File Generator</h1>
      <div>
        <label class="block text-xs text-gray-500 mb-1">Repository path</label>
        <input id="repoPath" type="text"
          class="border rounded px-2 py-1 text-sm w-96"
          placeholder="C:\path\to\_repository">
      </div>
    </div>
  </header>

  <main class="flex-1 overflow-y-auto p-4 flex flex-col gap-4">

    <!-- 1. Seed upload -->
    <div id="seedSection" class="bg-white rounded-lg shadow p-4">
      <h2 class="font-semibold text-gray-700 mb-3">Upload Seed OBX</h2>
      <div id="seedDropZone"
        class="border-2 border-dashed border-gray-300 rounded-lg p-6 text-center cursor-pointer hover:border-blue-400 hover:bg-blue-50 transition-colors">
        <input id="seedFile" type="file" accept=".obx,.xml" class="hidden">
        <p class="text-sm text-gray-500" id="seedDropLabel">
          Drag &amp; drop a seed OBX here, or <span class="text-blue-600 underline">click to browse</span>
        </p>
        <p class="text-xs text-gray-400 mt-1">Single configured product exported from pCon Planner</p>
      </div>
      <div class="flex items-center gap-3 mt-3 flex-wrap">
        <button id="parseSeedBtn"
          class="bg-blue-600 text-white px-4 py-1.5 rounded text-sm hover:bg-blue-700 disabled:opacity-50"
          disabled>Parse Seed</button>
        <div id="seedStatus" class="text-sm text-gray-500"></div>
      </div>
      <div id="seedInfo" class="hidden mt-3 p-3 bg-blue-50 rounded text-sm text-blue-800">
        <span id="seedInfoText"></span>
      </div>
    </div>

    <!-- 2. Dimension columns -->
    <div id="dimensionArea" class="hidden">
      <div id="dimensionColumns" class="flex gap-4 items-start overflow-x-auto pb-2"></div>
    </div>

    <!-- 3. Action row -->
    <div id="actionRow" class="hidden bg-white rounded-lg shadow px-4 py-3 flex items-center gap-4 flex-wrap">
      <div id="permCount" class="text-sm font-medium text-gray-700"></div>
      <div class="flex-1 min-w-48">
        <label class="block text-xs text-gray-500 mb-0.5">Label (optional)</label>
        <input id="articleLabel" type="text" placeholder="e.g. Low tables"
          class="border rounded px-2 py-1 text-sm w-full">
      </div>
      <div>
        <div id="filenamePreview" class="text-xs text-gray-400 font-mono mb-0.5"></div>
        <button id="addToQueueBtn"
          class="bg-green-600 text-white px-4 py-1.5 rounded text-sm hover:bg-green-700 disabled:opacity-50"
          disabled>+ Add to Queue</button>
      </div>
    </div>

    <!-- 4. Queue strip -->
    <div class="bg-white rounded-lg shadow p-4">
      <div class="flex justify-between items-center mb-3">
        <h2 class="font-semibold text-gray-700">Generation Queue</h2>
        <div class="flex items-center gap-2">
          <div id="generateStatus" class="text-xs text-gray-500 hidden"></div>
          <button id="generateAllBtn"
            class="bg-blue-700 text-white px-4 py-1.5 rounded text-sm hover:bg-blue-800 disabled:opacity-50"
            disabled>Generate All</button>
        </div>
      </div>
      <div id="queueStrip" class="flex gap-3 overflow-x-auto pb-2 min-h-24 items-start">
        <div id="emptyQueueMsg" class="text-gray-400 text-sm self-center">
          Parse a seed and add items to the queue to begin.
        </div>
      </div>
    </div>

  </main>

  <script src="/static/snapper/snapper.js"></script>
</body>
</html>
```

- [ ] **Step 2: Verify page loads**

Open `http://localhost:8080/snapper/` — no console errors, vertical layout visible.

> **Note:** Do NOT commit after this step. The page will be broken until Task 4 is complete (the existing snapper.js references DOM elements that no longer exist). Commit both files together at the end of Task 4.

---

### Task 4: Rewrite snapper.js

**Files:**
- Modify: `static/snapper/snapper.js` (full rewrite)

- [ ] **Step 1: Replace snapper.js entirely**

```javascript
// ── Constants ──────────────────────────────────────────────────────────────────
const WARN_LIMIT = 200;
const ERROR_LIMIT = 500;
const QUEUE_STORAGE_KEY = 'snapper_queue';

// ── HTML safety ────────────────────────────────────────────────────────────────
function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

// ── Filename assembly ──────────────────────────────────────────────────────────
function sanitizeLabel(raw) {
  return raw.trim().replace(/\s+/g, '_').replace(/[^\w]/g, '');
}

function assembleFilename(series, article, label, stage) {
  const parts = [series.toLowerCase(), article];
  const clean = sanitizeLabel(label);
  if (clean) parts.push(clean);
  parts.push(stage);
  return parts.join('_') + '.obx';
}

function assembleZipFilename(series, article) {
  return `${series.toLowerCase()}_${article}_Raw.zip`;
}

// ── State ──────────────────────────────────────────────────────────────────────
let currentSeed = null;
let hierarchyModes = {};
let queue = [];

// ── Queue persistence ──────────────────────────────────────────────────────────
function saveQueue() {
  localStorage.setItem(QUEUE_STORAGE_KEY, JSON.stringify(queue));
}

function loadQueue() {
  try {
    const saved = localStorage.getItem(QUEUE_STORAGE_KEY);
    if (saved) queue = JSON.parse(saved);
  } catch { queue = []; }
}

// ── DOM refs ───────────────────────────────────────────────────────────────────
const repoPathInput    = document.getElementById('repoPath');
const seedDropZone     = document.getElementById('seedDropZone');
const seedFileInput    = document.getElementById('seedFile');
const seedDropLabel    = document.getElementById('seedDropLabel');
const parseSeedBtn     = document.getElementById('parseSeedBtn');
const seedStatus       = document.getElementById('seedStatus');
const seedInfo         = document.getElementById('seedInfo');
const seedInfoText     = document.getElementById('seedInfoText');
const dimensionArea    = document.getElementById('dimensionArea');
const dimensionColumns = document.getElementById('dimensionColumns');
const actionRow        = document.getElementById('actionRow');
const permCount        = document.getElementById('permCount');
const articleLabel     = document.getElementById('articleLabel');
const filenamePreview  = document.getElementById('filenamePreview');
const addToQueueBtn    = document.getElementById('addToQueueBtn');
const queueStrip       = document.getElementById('queueStrip');
const emptyQueueMsg    = document.getElementById('emptyQueueMsg');
const generateAllBtn   = document.getElementById('generateAllBtn');
const generateStatus   = document.getElementById('generateStatus');

// ── Repo path persistence ──────────────────────────────────────────────────────
repoPathInput.value = localStorage.getItem('repoPath') || '';
repoPathInput.addEventListener('input', () => {
  localStorage.setItem('repoPath', repoPathInput.value.trim());
  updateParseSeedBtn();
});

// ── Seed drag-and-drop ─────────────────────────────────────────────────────────
seedDropZone.addEventListener('click', () => seedFileInput.click());

seedDropZone.addEventListener('dragover', (e) => {
  e.preventDefault();
  seedDropZone.classList.add('border-blue-500', 'bg-blue-50');
});
seedDropZone.addEventListener('dragleave', () => {
  seedDropZone.classList.remove('border-blue-500', 'bg-blue-50');
});
seedDropZone.addEventListener('drop', (e) => {
  e.preventDefault();
  seedDropZone.classList.remove('border-blue-500', 'bg-blue-50');
  const file = e.dataTransfer.files[0];
  if (file) {
    const dt = new DataTransfer();
    dt.items.add(file);
    seedFileInput.files = dt.files;
    onSeedFileSelected(file.name);
  }
});
seedFileInput.addEventListener('change', () => {
  if (seedFileInput.files[0]) onSeedFileSelected(seedFileInput.files[0].name);
});

function onSeedFileSelected(filename) {
  seedDropLabel.innerHTML =
    `<span class="font-medium text-gray-700">${escapeHtml(filename)}</span>`
    + ` — <span class="text-blue-600 underline">change file</span>`;
  updateParseSeedBtn();
}

function updateParseSeedBtn() {
  parseSeedBtn.disabled = !seedFileInput.files.length || !repoPathInput.value.trim();
}

// ── Parse Seed ─────────────────────────────────────────────────────────────────
parseSeedBtn.addEventListener('click', async () => {
  const file = seedFileInput.files[0];
  if (!file) return;
  const repo = repoPathInput.value.trim();
  if (!repo) { alert('Please enter the repository path first.'); return; }

  parseSeedBtn.disabled = true;
  seedStatus.textContent = 'Parsing…';

  const formData = new FormData();
  formData.append('file', file);
  formData.append('repo', repo);

  let response;
  try {
    response = await fetch('/api/snapper/parse-seed', { method: 'POST', body: formData });
  } catch (err) {
    seedStatus.textContent = `Network error: ${err.message}`;
    parseSeedBtn.disabled = false;
    return;
  }

  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: 'Unknown error' }));
    seedStatus.textContent = `Error: ${err.detail}`;
    parseSeedBtn.disabled = false;
    return;
  }

  currentSeed = await response.json();
  hierarchyModes = {};
  for (const col of currentSeed.property_columns) {
    if (col.is_child) hierarchyModes[col.name] = 'first';
  }

  seedStatus.textContent = '';
  parseSeedBtn.disabled = false;

  seedInfo.classList.remove('hidden');
  seedInfoText.textContent =
    `Article: ${currentSeed.article} · Manufacturer: ${currentSeed.manufacturer}`
    + ` · Series: ${currentSeed.series} · ${currentSeed.property_columns.length} properties`;

  dimensionArea.classList.remove('hidden');
  actionRow.classList.remove('hidden');
  renderDimensions();
  addToQueueBtn.disabled = false;
  updateFilenamePreview();
});

// ── Dimension columns ──────────────────────────────────────────────────────────
function renderDimensions() {
  dimensionColumns.innerHTML = '';
  if (!currentSeed) return;

  const parentHasChild = new Map();
  for (const col of currentSeed.property_columns) {
    if (col.is_child) parentHasChild.set(col.parent, col.name);
  }

  for (const col of currentSeed.property_columns) {
    if (col.is_child) continue;
    const wrapper = document.createElement('div');
    wrapper.className = 'flex flex-col gap-1';
    wrapper.appendChild(_buildCheckboxColumn(col.name, col.values, col.seed_value));
    const childName = parentHasChild.get(col.name);
    if (childName) wrapper.appendChild(_buildHierarchyModeControl(childName));
    dimensionColumns.appendChild(wrapper);
  }
  updatePermCount();
}

function _buildCheckboxColumn(propName, values, seedValue) {
  const col = document.createElement('div');
  col.className = 'bg-white rounded-lg shadow p-3 min-w-44 max-w-56 flex flex-col';
  col.dataset.propName = propName;
  col.innerHTML = `
    <div class="font-semibold text-sm text-gray-700 mb-2 border-b pb-1" title="${escapeHtml(propName)}">${escapeHtml(propName)}</div>
    <div class="flex gap-1 mb-2">
      <button class="text-xs text-blue-600 hover:underline select-all-btn">All</button>
      <span class="text-gray-300">|</span>
      <button class="text-xs text-blue-600 hover:underline select-none-btn">None</button>
    </div>
    <div class="overflow-y-auto max-h-64 space-y-1">
      ${values.map(v => `
        <label class="flex items-center gap-1 text-xs text-gray-700 cursor-pointer">
          <input type="checkbox" class="dim-check" data-prop="${escapeHtml(propName)}" data-value="${escapeHtml(v.code)}"
            ${v.code === seedValue ? 'checked' : ''}>
          <span class="font-mono text-gray-500">${escapeHtml(v.code)}</span>
          ${v.label && v.label !== v.code ? `<span class="text-gray-300">·</span><span class="truncate">${escapeHtml(v.label)}</span>` : ''}
        </label>`).join('')}
    </div>`;
  col.querySelector('.select-all-btn').addEventListener('click', () => {
    col.querySelectorAll('.dim-check').forEach(cb => { cb.checked = true; });
    updatePermCount();
  });
  col.querySelector('.select-none-btn').addEventListener('click', () => {
    col.querySelectorAll('.dim-check').forEach(cb => { cb.checked = false; });
    updatePermCount();
  });
  col.querySelectorAll('.dim-check').forEach(cb => cb.addEventListener('change', updatePermCount));
  return col;
}

function _buildHierarchyModeControl(childPropName) {
  const el = document.createElement('div');
  el.className = 'bg-amber-50 border border-amber-200 rounded p-2 text-xs text-amber-800';
  const mode = hierarchyModes[childPropName] || 'first';
  el.innerHTML = `
    <div class="font-semibold mb-1">${escapeHtml(childPropName)}</div>
    <div class="text-gray-500 mb-1">Colour assignment:</div>
    <div class="flex gap-1">
      <button class="mode-btn px-2 py-0.5 rounded text-xs border ${mode === 'first' ? 'bg-amber-600 text-white border-amber-600' : 'bg-white border-gray-300 text-gray-700'}"
        data-mode="first">First only</button>
      <button class="mode-btn px-2 py-0.5 rounded text-xs border ${mode === 'distribute' ? 'bg-amber-600 text-white border-amber-600' : 'bg-white border-gray-300 text-gray-700'}"
        data-mode="distribute">Distribute</button>
    </div>`;
  el.querySelectorAll('.mode-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      hierarchyModes[childPropName] = btn.dataset.mode;
      el.querySelectorAll('.mode-btn').forEach(b => {
        const active = b.dataset.mode === btn.dataset.mode;
        b.className = `mode-btn px-2 py-0.5 rounded text-xs border ${active ? 'bg-amber-600 text-white border-amber-600' : 'bg-white border-gray-300 text-gray-700'}`;
      });
    });
  });
  return el;
}

// ── Permutation counter ────────────────────────────────────────────────────────
function getParentSelections() {
  const sel = {};
  document.querySelectorAll('.dim-check:checked').forEach(cb => {
    if (!sel[cb.dataset.prop]) sel[cb.dataset.prop] = [];
    sel[cb.dataset.prop].push(cb.dataset.value);
  });
  return sel;
}

function computePermCount(sel) {
  const counts = Object.values(sel).map(v => v.length);
  return counts.length ? counts.reduce((a, b) => a * b, 1) : 0;
}

function updatePermCount() {
  const sel = getParentSelections();
  const count = computePermCount(sel);
  permCount.textContent = `${count.toLocaleString()} permutations`;
  permCount.className = 'text-sm font-medium ' + (
    count > ERROR_LIMIT ? 'text-red-600' :
    count > WARN_LIMIT  ? 'text-amber-600' : 'text-gray-700'
  );
  if (count > ERROR_LIMIT) permCount.textContent += ` ⚠ Consider splitting (max: ${ERROR_LIMIT})`;
  updateFilenamePreview();
}

function updateFilenamePreview() {
  if (!currentSeed) { filenamePreview.textContent = ''; return; }
  filenamePreview.textContent = assembleFilename(
    currentSeed.series, currentSeed.article, articleLabel.value, 'Raw'
  );
}
articleLabel.addEventListener('input', updateFilenamePreview);

// ── Child resolution + class maps ──────────────────────────────────────────────
function resolveChildValues(parentSelections) {
  if (!currentSeed) return {};
  const out = {};
  for (const childCol of currentSeed.property_columns.filter(c => c.is_child)) {
    const parentVals = parentSelections[childCol.parent] || [];
    const mode = hierarchyModes[childCol.name] || 'first';
    const resolution = {};
    for (const pv of parentVals) {
      const children = (childCol.mapping || {})[pv] || [];
      if (children.length === 0) continue;
      resolution[pv] = mode === 'first' ? children[0] : children[parentVals.indexOf(pv) % children.length];
    }
    if (Object.keys(resolution).length > 0) {
      out[childCol.name] = { parent: childCol.parent, resolution };
    }
  }
  return out;
}

function buildClassMaps() {
  if (!currentSeed) return { propertyToClass: {}, propValToClass: {} };
  const propertyToClass = {}, propValToClass = {};
  for (const col of currentSeed.property_columns) {
    propertyToClass[col.name] = col.article_class;
    for (const v of col.values) propValToClass[`${col.name}=${v.code}`] = col.article_class;
  }
  return { propertyToClass, propValToClass };
}

// ── Add to queue ───────────────────────────────────────────────────────────────
addToQueueBtn.addEventListener('click', () => {
  if (!currentSeed) return;
  const parentSelections = getParentSelections();
  const { propertyToClass, propValToClass } = buildClassMaps();
  const label = articleLabel.value.trim();

  queue.push({
    id: crypto.randomUUID(),
    state: 'red',
    label,
    filename: assembleFilename(currentSeed.series, currentSeed.article, label, 'Raw'),
    article: currentSeed.article,
    series: currentSeed.series,
    manufacturer: currentSeed.manufacturer,
    articleClass: currentSeed.property_columns[0]?.article_class || '',
    propertyToClass,
    propValToClass,
    selectedProperties: parentSelections,
    childResolutions: resolveChildValues(parentSelections),
    count: computePermCount(parentSelections),
    seedToken: currentSeed.seed_token ?? null,
    keptCount: null,
    removedCount: null,
  });

  articleLabel.value = '';
  updateFilenamePreview();
  saveQueue();
  renderQueue();
});

// ── Queue rendering ────────────────────────────────────────────────────────────
function renderQueue() {
  queueStrip.querySelectorAll('.queue-card').forEach(el => el.remove());
  if (queue.length === 0) {
    emptyQueueMsg.classList.remove('hidden');
    generateAllBtn.disabled = true;
    return;
  }
  emptyQueueMsg.classList.add('hidden');
  for (const item of queue) queueStrip.appendChild(buildCard(item));
  generateAllBtn.disabled = !queue.some(i => i.state === 'red');
}

function buildCard(item) {
  const card = document.createElement('div');
  card.className = 'queue-card rounded-lg p-3 w-56 flex-shrink-0 flex flex-col gap-2 border-2';
  card.dataset.id = item.id;

  if (item.state === 'red') {
    card.classList.add('border-red-400', 'bg-red-50');
    card.innerHTML = `
      <div class="text-xs font-mono text-gray-700 truncate" title="${escapeHtml(item.filename)}">${escapeHtml(item.filename)}</div>
      <div class="text-xs text-gray-500">${item.count.toLocaleString()} permutations</div>
      <div class="flex gap-1">
        <button class="generate-one-btn flex-1 bg-red-600 text-white px-2 py-1 rounded text-xs hover:bg-red-700">Generate</button>
        <button class="remove-btn text-red-400 hover:text-red-600 px-1">✕</button>
      </div>`;
    card.querySelector('.generate-one-btn').addEventListener('click', () => generateOne(item.id));
    card.querySelector('.remove-btn').addEventListener('click', () => removeItem(item.id));

  } else if (item.state === 'orange') {
    card.classList.add('border-amber-400', 'bg-amber-50');
    card.innerHTML = `
      <div class="text-xs font-mono text-gray-600 truncate" title="${escapeHtml(item.filename)}">${escapeHtml(item.filename)}</div>
      <div class="text-xs text-amber-700 font-medium">Waiting for pCon export</div>
      <div class="clean-drop-zone border-2 border-dashed border-amber-300 rounded p-3 text-center text-xs text-amber-600 cursor-pointer hover:bg-amber-100 transition-colors">
        Drop pCon export here<br>or click to browse
        <input type="file" accept=".obx,.xml" class="hidden clean-file-input">
      </div>
      <button class="regenerate-btn w-full text-xs text-gray-500 hover:text-gray-700 border rounded px-2 py-1">Re-generate</button>`;

    const dropZone = card.querySelector('.clean-drop-zone');
    const fileInput = card.querySelector('.clean-file-input');
    dropZone.addEventListener('click', () => fileInput.click());
    dropZone.addEventListener('dragover', (e) => { e.preventDefault(); dropZone.classList.add('bg-amber-200'); });
    dropZone.addEventListener('dragleave', () => dropZone.classList.remove('bg-amber-200'));
    dropZone.addEventListener('drop', (e) => {
      e.preventDefault();
      dropZone.classList.remove('bg-amber-200');
      if (e.dataTransfer.files[0]) cleanItem(item.id, e.dataTransfer.files[0]);
    });
    fileInput.addEventListener('change', () => {
      if (fileInput.files[0]) cleanItem(item.id, fileInput.files[0]);
    });
    card.querySelector('.regenerate-btn').addEventListener('click', () => revertToRed(item.id));

  } else if (item.state === 'green') {
    card.classList.add('border-green-400', 'bg-green-50');
    const cleanName = assembleFilename(item.series, item.article, item.label, 'Clean');
    card.innerHTML = `
      <div class="text-xs font-mono text-gray-700 truncate" title="${escapeHtml(cleanName)}">${escapeHtml(cleanName)}</div>
      <div class="text-xs text-green-700 font-medium">✓ ${item.keptCount} kept · ${item.removedCount} removed</div>
      <button class="done-btn w-full bg-green-600 text-white px-2 py-1 rounded text-xs hover:bg-green-700">Done</button>`;
    card.querySelector('.done-btn').addEventListener('click', () => removeItem(item.id));
  }

  return card;
}

function removeItem(id) {
  queue = queue.filter(i => i.id !== id);
  saveQueue();
  renderQueue();
}

function revertToRed(id) {
  const item = queue.find(i => i.id === id);
  if (!item) return;
  item.state = 'red';
  saveQueue();
  renderQueue();
}

// ── Generate (single) ──────────────────────────────────────────────────────────
async function generateOne(id) {
  const item = queue.find(i => i.id === id);
  if (!item || item.state !== 'red') return;
  const card = queueStrip.querySelector(`[data-id="${id}"]`);
  if (card) card.querySelector('.generate-one-btn').disabled = true;

  const ok = await _doGenerate([item], item.filename);
  if (ok) {
    item.state = 'orange';
    saveQueue();
  }
  renderQueue(); // Always re-render: restores button on failure, advances card on success
}

// ── Generate All ───────────────────────────────────────────────────────────────
generateAllBtn.addEventListener('click', async () => {
  const redItems = queue.filter(i => i.state === 'red');
  if (!redItems.length) return;

  generateAllBtn.disabled = true;
  generateStatus.classList.remove('hidden');
  generateStatus.textContent = 'Building…';

  const filename = redItems.length === 1
    ? redItems[0].filename
    : assembleZipFilename(redItems[0].series, redItems[0].article).replace('.zip', '.obx');

  const ok = await _doGenerate(redItems, filename);
  if (ok) {
    for (const item of redItems) item.state = 'orange';
    saveQueue();
    generateStatus.textContent = 'Downloaded.';
    setTimeout(() => generateStatus.classList.add('hidden'), 3000);
  }
  renderQueue();
});

// ── Shared generate logic ──────────────────────────────────────────────────────
async function _doGenerate(items, filename) {
  const payload = {
    manufacturer: items[0].manufacturer,
    series: items[0].series,
    filename,
    seed_token: items[0].seedToken ?? null,
    queue: items.map(e => ({
      article: e.article,
      article_class: e.articleClass,
      property_to_class: e.propertyToClass,
      prop_val_to_class: e.propValToClass,
      selected_properties: e.selectedProperties,
      child_resolutions: e.childResolutions || {},
    })),
  };

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 120000);
  let response;
  try {
    response = await fetch('/api/snapper/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
  } catch (err) {
    clearTimeout(timeoutId);
    _showGenerateStatus(err.name === 'AbortError' ? 'Timed out — try fewer permutations.' : `Network error: ${err.message}`);
    return false;
  }
  clearTimeout(timeoutId);

  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: 'Unknown error' }));
    _showGenerateStatus(`Error: ${err.detail}`);
    return false;
  }

  const contentType = response.headers.get('content-type') || '';
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = contentType.includes('zip')
    ? assembleZipFilename(items[0].series, items[0].article)
    : filename;
  a.click();
  URL.revokeObjectURL(url);
  return true;
}

function _showGenerateStatus(msg) {
  generateStatus.textContent = msg;
  generateStatus.classList.remove('hidden');
}

// ── Clean item ─────────────────────────────────────────────────────────────────
async function cleanItem(id, file) {
  const item = queue.find(i => i.id === id);
  if (!item) return;

  const card = queueStrip.querySelector(`[data-id="${id}"]`);
  const dropZone = card?.querySelector('.clean-drop-zone');
  if (dropZone) dropZone.textContent = 'Processing…';

  const formData = new FormData();
  formData.append('file', file);
  formData.append('label', item.label);

  let response;
  try {
    response = await fetch('/api/snapper/clean-obx', { method: 'POST', body: formData });
  } catch (err) {
    if (dropZone) dropZone.textContent = `Network error: ${err.message}`;
    return;
  }

  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: 'Unknown error' }));
    if (dropZone) dropZone.textContent = `Error: ${err.detail}`;
    return;
  }

  const kept = parseInt(response.headers.get('X-Kept-Count') || '0', 10);
  const removed = parseInt(response.headers.get('X-Removed-Count') || '0', 10);

  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = assembleFilename(item.series, item.article, item.label, 'Clean');
  a.click();
  URL.revokeObjectURL(url);

  item.state = 'green';
  item.keptCount = kept;
  item.removedCount = removed;
  saveQueue();
  renderQueue();
}

// ── Init ───────────────────────────────────────────────────────────────────────
loadQueue();
renderQueue();
```

- [ ] **Step 2: Verify full workflow manually**

With the server running (`python main.py`), test the following in order:

1. Open `http://localhost:8080/snapper/` — queue strip visible, empty state shown
2. Drag a seed OBX onto the drop zone — filename appears, Parse Seed button enables
3. Click Parse Seed — dimension columns appear, action row appears
4. Select some values, type `Low tables` in the label — filename preview shows `[series]_[article]_Low_tables_Raw.obx`
5. Click `+ Add to Queue` — a red card appears with correct filename
6. Refresh — red card still present (localStorage)
7. Click Generate on the card — OBX downloads with `_Raw` suffix, card turns orange
8. Parse a second seed (or re-parse the same one), type a different label (e.g. `High tables`), add to queue — two red cards visible. Click Generate All — a zip downloads, both cards turn orange
9. On an orange card, drag in any OBX file (can be any valid OBX for testing) — `_Clean.obx` downloads, card turns green with kept/removed counts
10. Click Done — card removed
11. Test failure recovery: when no seed is parsed, simulate a generate failure by temporarily breaking the repo path. Click Generate — card button re-enables after failure (does not stay permanently disabled)

- [ ] **Step 3: Run backend tests to confirm no regressions**

```
pytest tests/ -v
```

Expected: all pass

- [ ] **Step 4: Commit both HTML and JS together**

```bash
git add static/snapper/index.html static/snapper/snapper.js
git commit -m "feat: rewrite snapper UI with vertical layout, queue persistence, card state machine, drag-and-drop, and clean-obx integration"
```

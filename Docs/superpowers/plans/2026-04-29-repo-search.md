# Repo Search Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Repo Search module that lets QA users search for a string value across OCD CSV files in all ranges of a saved repository.

**Architecture:** Single FastAPI endpoint (`POST /api/search/run`) that walks the repo directory tree, opens selected CSV file types, and tests each cell against the query. Results are returned as a flat list grouped by manufacturer/range/file type. Frontend is vanilla JS + Tailwind, following the same patterns as the snapper module.

**Tech Stack:** Python 3.11, FastAPI, Pydantic, `csv` stdlib, vanilla JS, Tailwind CSS (CDN)

---

## Chunk 1: Backend — search module

### File map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `modules/search/__init__.py` | package marker |
| Create | `modules/search/routes.py` | scan logic + FastAPI router |
| Create | `tests/search/__init__.py` | test package marker |
| Create | `tests/search/test_routes.py` | unit + integration tests |

---

### Task 1: Create package stubs

**Files:**
- Create: `modules/search/__init__.py`
- Create: `tests/search/__init__.py`

- [ ] **Step 1: Create both empty `__init__.py` files**

```bash
touch modules/search/__init__.py tests/search/__init__.py
```

- [ ] **Step 2: Commit**

```bash
git add modules/search/__init__.py tests/search/__init__.py
git commit -m "feat: scaffold search module package"
```

---

### Task 2: Backend route — write failing tests first

**Files:**
- Create: `tests/search/test_routes.py`
- Create: `modules/search/routes.py` (stub — just enough to make tests importable)

- [ ] **Step 1: Create a stub `modules/search/routes.py`**

This stub is just enough so the test file can import without crashing. It does nothing yet.

```python
# modules/search/routes.py
from fastapi import APIRouter
router = APIRouter(prefix="/api/search", tags=["search"])
```

- [ ] **Step 2: Write the full test file**

`tests/search/test_routes.py`:

```python
import csv
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_range(tmp_path, mfr, range_name, file_data: dict[str, list[list[str]]]):
    """Create a minimal fake repo range with CSV files under ANY/1/db/."""
    db = tmp_path / mfr / range_name / "ANY" / "1" / "db"
    db.mkdir(parents=True)
    for fname, rows in file_data.items():
        with open(db / fname, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            for row in rows:
                writer.writerow(row)
    return db


def _search(tmp_path, file_types, query, match_mode="contains", case_sensitive=False):
    return client.post("/api/search/run", json={
        "repo": str(tmp_path),
        "file_types": file_types,
        "query": query,
        "match_mode": match_mode,
        "case_sensitive": case_sensitive,
    })


# ── Basic match modes ──────────────────────────────────────────────────────────

def test_contains_match(tmp_path):
    _make_range(tmp_path, "kno", "tulip", {
        "ocd_propvalue.csv": [
            ["TULIP_FABRIC", "H80040", "Cato Orange"],
            ["TULIP_FABRIC", "K12345", "Other Color"],
        ]
    })
    resp = _search(tmp_path, ["ocd_propvalue"], "H80040")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ranges_searched"] == 1
    assert len(data["results"]) == 1
    result = data["results"][0]
    assert result["manufacturer"] == "kno"
    assert result["range"] == "tulip"
    assert result["file_type"] == "ocd_propvalue"
    assert result["matches"][0]["row_number"] == 1
    assert result["matches"][0]["row"] == ["TULIP_FABRIC", "H80040", "Cato Orange"]


def test_contains_partial(tmp_path):
    _make_range(tmp_path, "kno", "tulip", {
        "ocd_propvalue.csv": [["FABRIC", "PREFIX_H80040_SUFFIX", "val"]]
    })
    resp = _search(tmp_path, ["ocd_propvalue"], "H80040")
    assert len(resp.json()["results"]) == 1


def test_equals_exact_only(tmp_path):
    _make_range(tmp_path, "kno", "tulip", {
        "ocd_propvalue.csv": [
            ["FABRIC", "H80040", "exact"],
            ["FABRIC", "H800400", "longer"],
            ["FABRIC", "0H80040", "prefixed"],
        ]
    })
    resp = _search(tmp_path, ["ocd_propvalue"], "H80040", match_mode="equals", case_sensitive=True)
    data = resp.json()
    assert len(data["results"][0]["matches"]) == 1
    assert data["results"][0]["matches"][0]["row"][1] == "H80040"


def test_starts_with(tmp_path):
    _make_range(tmp_path, "kno", "tulip", {
        "ocd_propvalue.csv": [
            ["FABRIC", "H80040-A", "starts"],
            ["FABRIC", "AH80040", "not starts"],
        ]
    })
    resp = _search(tmp_path, ["ocd_propvalue"], "H80040", match_mode="starts_with", case_sensitive=True)
    data = resp.json()
    assert len(data["results"][0]["matches"]) == 1
    assert data["results"][0]["matches"][0]["row"][1] == "H80040-A"


def test_ends_with(tmp_path):
    _make_range(tmp_path, "kno", "tulip", {
        "ocd_propvalue.csv": [
            ["FABRIC", "AH80040", "ends"],
            ["FABRIC", "H80040-X", "not ends"],
        ]
    })
    resp = _search(tmp_path, ["ocd_propvalue"], "H80040", match_mode="ends_with", case_sensitive=True)
    data = resp.json()
    assert len(data["results"][0]["matches"]) == 1
    assert data["results"][0]["matches"][0]["row"][1] == "AH80040"


# ── Case sensitivity ───────────────────────────────────────────────────────────

def test_case_insensitive_matches_lowercase(tmp_path):
    _make_range(tmp_path, "kno", "tulip", {
        "ocd_propvalue.csv": [["FABRIC", "h80040", "lower"]]
    })
    resp = _search(tmp_path, ["ocd_propvalue"], "H80040", case_sensitive=False)
    assert len(resp.json()["results"]) == 1


def test_case_sensitive_no_match(tmp_path):
    _make_range(tmp_path, "kno", "tulip", {
        "ocd_propvalue.csv": [["FABRIC", "h80040", "lower"]]
    })
    resp = _search(tmp_path, ["ocd_propvalue"], "H80040", case_sensitive=True)
    assert resp.json()["results"] == []


# ── Multiple ranges and file types ────────────────────────────────────────────

def test_no_match_range_excluded(tmp_path):
    _make_range(tmp_path, "hmx", "cosm", {
        "ocd_propvalue.csv": [["COSM_FABRIC", "X99999", "Some Color"]]
    })
    resp = _search(tmp_path, ["ocd_propvalue"], "H80040")
    data = resp.json()
    assert data["results"] == []
    assert data["ranges_searched"] == 1


def test_multiple_ranges_only_matching_returned(tmp_path):
    _make_range(tmp_path, "kno", "tulip", {
        "ocd_propvalue.csv": [["FABRIC", "H80040", "Orange"]]
    })
    _make_range(tmp_path, "kno", "saarinen", {
        "ocd_propvalue.csv": [["FABRIC", "X99999", "Other"]]
    })
    resp = _search(tmp_path, ["ocd_propvalue"], "H80040")
    data = resp.json()
    assert data["ranges_searched"] == 2
    assert len(data["results"]) == 1
    assert data["results"][0]["range"] == "tulip"


def test_multiple_file_types(tmp_path):
    _make_range(tmp_path, "kno", "tulip", {
        "ocd_propvalue.csv": [["FABRIC", "H80040", "Orange"]],
        "ocd_propvaluetext.csv": [["FABRIC", "H80040", "Cato Orange EN"]],
        "ocd_property.csv": [["FABRIC_TYPE", "label"]],
    })
    resp = _search(tmp_path, ["ocd_propvalue", "ocd_propvaluetext"], "H80040")
    data = resp.json()
    file_types = {r["file_type"] for r in data["results"]}
    assert file_types == {"ocd_propvalue", "ocd_propvaluetext"}


def test_missing_csv_file_skipped_gracefully(tmp_path):
    """Range without the requested file type should not cause an error."""
    _make_range(tmp_path, "kno", "tulip", {
        "ocd_propvalue.csv": [["FABRIC", "H80040", "Orange"]]
        # ocd_article.csv intentionally absent
    })
    resp = _search(tmp_path, ["ocd_article", "ocd_propvalue"], "H80040")
    assert resp.status_code == 200
    assert len(resp.json()["results"]) == 1


def test_row_number_is_one_based(tmp_path):
    _make_range(tmp_path, "kno", "tulip", {
        "ocd_propvalue.csv": [
            ["FABRIC", "NOMATCH", "x"],
            ["FABRIC", "H80040", "Orange"],
        ]
    })
    resp = _search(tmp_path, ["ocd_propvalue"], "H80040")
    assert resp.json()["results"][0]["matches"][0]["row_number"] == 2


def test_duration_ms_present(tmp_path):
    _make_range(tmp_path, "kno", "tulip", {
        "ocd_propvalue.csv": [["FABRIC", "H80040", "Orange"]]
    })
    resp = _search(tmp_path, ["ocd_propvalue"], "H80040")
    assert resp.json()["duration_ms"] >= 0


# ── Validation errors ──────────────────────────────────────────────────────────

def test_invalid_repo_path_returns_400():
    resp = client.post("/api/search/run", json={
        "repo": "C:\\nonexistent\\path\\that\\does\\not\\exist",
        "file_types": ["ocd_propvalue"],
        "query": "H80040",
        "match_mode": "contains",
        "case_sensitive": False,
    })
    assert resp.status_code == 400


def test_empty_query_returns_400(tmp_path):
    resp = client.post("/api/search/run", json={
        "repo": str(tmp_path),
        "file_types": ["ocd_propvalue"],
        "query": "",
        "match_mode": "contains",
        "case_sensitive": False,
    })
    assert resp.status_code == 400


def test_invalid_file_type_returns_400(tmp_path):
    resp = client.post("/api/search/run", json={
        "repo": str(tmp_path),
        "file_types": ["ocd_nonexistent"],
        "query": "H80040",
        "match_mode": "contains",
        "case_sensitive": False,
    })
    assert resp.status_code == 400


def test_invalid_match_mode_returns_400(tmp_path):
    resp = client.post("/api/search/run", json={
        "repo": str(tmp_path),
        "file_types": ["ocd_propvalue"],
        "query": "H80040",
        "match_mode": "fuzzy",
        "case_sensitive": False,
    })
    assert resp.status_code == 400
```

- [ ] **Step 3: Run tests — verify they all fail (route not yet implemented)**

```bash
pytest tests/search/test_routes.py -v
```

Expected: most tests FAIL with 404 or 422 since the endpoint doesn't exist yet.

---

### Task 3: Implement the search endpoint

**Files:**
- Modify: `modules/search/routes.py`

- [ ] **Step 1: Replace the stub with the full implementation**

```python
# modules/search/routes.py
import csv
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/search", tags=["search"])

SEARCHABLE_FILES = {
    "ocd_article",
    "ocd_artlongtext",
    "ocd_artshorttext",
    "ocd_property",
    "ocd_propertytext",
    "ocd_propvalue",
    "ocd_propvaluetext",
}

VALID_MATCH_MODES = {"contains", "equals", "starts_with", "ends_with"}


class SearchRequest(BaseModel):
    repo: str
    file_types: list[str]
    query: str
    match_mode: str  # contains | equals | starts_with | ends_with
    case_sensitive: bool = False


def _cell_matches(cell: str, query: str, match_mode: str, case_sensitive: bool) -> bool:
    if not case_sensitive:
        cell = cell.lower()
        query = query.lower()
    if match_mode == "contains":
        return query in cell
    if match_mode == "equals":
        return cell == query
    if match_mode == "starts_with":
        return cell.startswith(query)
    if match_mode == "ends_with":
        return cell.endswith(query)
    return False


def _scan_repo(
    repo: str,
    file_types: list[str],
    query: str,
    match_mode: str,
    case_sensitive: bool,
) -> tuple[list[dict], int]:
    repo_path = Path(repo)
    results: list[dict] = []
    ranges_searched = 0

    for mfr_dir in sorted(repo_path.iterdir()):
        if not mfr_dir.is_dir():
            continue
        for range_dir in sorted(mfr_dir.iterdir()):
            if not range_dir.is_dir():
                continue
            db_path = range_dir / "ANY" / "1" / "db"
            if not db_path.is_dir():
                continue
            ranges_searched += 1
            for file_type in file_types:
                csv_path = db_path / f"{file_type}.csv"
                if not csv_path.exists():
                    continue
                matches: list[dict] = []
                try:
                    with open(csv_path, encoding="utf-8", errors="replace", newline="") as f:
                        for row_idx, row in enumerate(csv.reader(f), start=1):
                            if any(
                                _cell_matches(cell, query, match_mode, case_sensitive)
                                for cell in row
                            ):
                                matches.append({"row_number": row_idx, "row": row})
                except OSError:
                    continue
                if matches:
                    results.append({
                        "manufacturer": mfr_dir.name,
                        "range": range_dir.name,
                        "file_type": file_type,
                        "matches": matches,
                    })

    return results, ranges_searched


@router.post("/run")
def run_search(req: SearchRequest):
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="Query must not be empty")
    if not req.file_types:
        raise HTTPException(status_code=400, detail="At least one file type must be selected")
    if req.match_mode not in VALID_MATCH_MODES:
        raise HTTPException(status_code=400, detail=f"Invalid match_mode: {req.match_mode!r}")
    invalid = set(req.file_types) - SEARCHABLE_FILES
    if invalid:
        raise HTTPException(status_code=400, detail=f"Invalid file types: {sorted(invalid)}")
    if not Path(req.repo).is_dir():
        raise HTTPException(status_code=400, detail=f"Repo path not found: {req.repo}")

    start = time.monotonic()
    results, ranges_searched = _scan_repo(
        req.repo, req.file_types, req.query, req.match_mode, req.case_sensitive
    )
    duration_ms = int((time.monotonic() - start) * 1000)

    return {"results": results, "ranges_searched": ranges_searched, "duration_ms": duration_ms}
```

- [ ] **Step 2: Register the router in `main.py`**

Add these two lines to `main.py` (alongside the existing snapper wiring):

```python
# At top — new import:
from modules.search.routes import router as search_router

# After app.include_router(snapper_router):
app.include_router(search_router)

# New page route (after /snapper/):
@app.get("/search/")
def search_page():
    return FileResponse("static/search/index.html")
```

- [ ] **Step 3: Run all search tests — verify they pass**

```bash
pytest tests/search/test_routes.py -v
```

Expected: all tests PASS.

- [ ] **Step 4: Commit**

```bash
git add modules/search/ tests/search/ main.py
git commit -m "feat: add repo search backend endpoint"
```

---

## Chunk 2: Frontend + dashboard card

### File map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `static/search/index.html` | search page shell + controls |
| Create | `static/search/search.js` | repo picker, form logic, results rendering |
| Modify | `static/index.html` | add dashboard card |

---

### Task 4: Search page HTML

**Files:**
- Create: `static/search/index.html`

- [ ] **Step 1: Create `static/search/index.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Repo Search — OFML Testsuite</title>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-100 min-h-screen">

  <header class="bg-white shadow">
    <div id="headerRow" class="max-w-7xl mx-auto px-6 py-4 flex items-center gap-4">
      <a href="/" class="text-gray-400 hover:text-gray-600 flex-shrink-0" title="Home">
        <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
          <path stroke-linecap="round" stroke-linejoin="round" d="M2.25 12L11.204 3.045a1.125 1.125 0 0 1 1.591 0L21.75 12M4.5 9.75v10.125c0 .621.504 1.125 1.125 1.125H9.75v-4.875c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21h4.125c.621 0 1.125-.504 1.125-1.125V9.75M8.25 21h8.25" />
        </svg>
      </a>
      <div>
        <h1 class="text-2xl font-bold text-gray-800">Repo Search</h1>
        <p class="text-sm text-gray-500">Find a value across all ranges in a repository</p>
      </div>
    </div>
  </header>

  <main class="max-w-7xl mx-auto px-6 py-8 space-y-6">

    <!-- Controls card -->
    <div class="bg-white rounded-xl shadow p-6 space-y-5">

      <!-- Row 1: Repo + Query -->
      <div class="flex flex-wrap gap-4 items-end">
        <div class="flex flex-col gap-1 min-w-48">
          <label class="text-xs font-medium text-gray-500 uppercase tracking-wide">Repository</label>
          <select id="repoSelect"
            class="border rounded px-3 py-2 text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-400">
            <option value="">— select repo —</option>
          </select>
          <p id="noReposMsg" class="text-xs text-amber-600 hidden">
            No repos saved. Add one in <button id="openSettingsLink" class="underline">Settings</button>.
          </p>
        </div>

        <div class="flex flex-col gap-1 flex-1 min-w-48">
          <label class="text-xs font-medium text-gray-500 uppercase tracking-wide">Search</label>
          <input id="queryInput" type="text" placeholder="e.g. H80040"
            class="border rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400">
        </div>

        <div class="flex flex-col gap-1">
          <label class="text-xs font-medium text-gray-500 uppercase tracking-wide">Match</label>
          <select id="matchMode"
            class="border rounded px-3 py-2 text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-400">
            <option value="contains">Contains</option>
            <option value="equals">Equals</option>
            <option value="starts_with">Starts with</option>
            <option value="ends_with">Ends with</option>
          </select>
        </div>

        <div class="flex items-center gap-2 pb-2">
          <input id="caseSensitive" type="checkbox" class="rounded">
          <label for="caseSensitive" class="text-sm text-gray-600">Case sensitive</label>
        </div>
      </div>

      <!-- Row 2: File types -->
      <div>
        <p class="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">File types</p>
        <div id="fileTypeChecks" class="flex flex-wrap gap-3">
          <!-- populated by JS -->
        </div>
      </div>

      <!-- Row 3: Search button -->
      <div class="flex items-center gap-4">
        <button id="searchBtn"
          class="px-5 py-2 rounded bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed"
          disabled>
          Search
        </button>
        <span id="statusMsg" class="text-sm text-gray-500"></span>
      </div>
    </div>

    <!-- Results -->
    <div id="results"></div>

  </main>

  <script src="/static/settings.js"></script>
  <script src="/static/search/search.js"></script>
  <script>
    initSettingsGear(document.getElementById('headerRow'));
    populateRepos();
  </script>
</body>
</html>
```

---

### Task 5: Search page JavaScript

**Files:**
- Create: `static/search/search.js`

- [ ] **Step 1: Create `static/search/search.js`**

```javascript
// ── Constants ─────────────────────────────────────────────────────────────────
const FILE_TYPES = [
  'ocd_article',
  'ocd_artlongtext',
  'ocd_artshorttext',
  'ocd_property',
  'ocd_propertytext',
  'ocd_propvalue',
  'ocd_propvaluetext',
];

// ── Element refs ──────────────────────────────────────────────────────────────
const repoSelect    = document.getElementById('repoSelect');
const noReposMsg    = document.getElementById('noReposMsg');
const openSettingsLink = document.getElementById('openSettingsLink');
const queryInput    = document.getElementById('queryInput');
const matchMode     = document.getElementById('matchMode');
const caseSensitive = document.getElementById('caseSensitive');
const fileTypeChecks = document.getElementById('fileTypeChecks');
const searchBtn     = document.getElementById('searchBtn');
const statusMsg     = document.getElementById('statusMsg');
const resultsEl     = document.getElementById('results');

// ── File type checkboxes ──────────────────────────────────────────────────────
FILE_TYPES.forEach(ft => {
  const label = document.createElement('label');
  label.className = 'flex items-center gap-1.5 text-sm text-gray-700 cursor-pointer';
  label.innerHTML = `
    <input type="checkbox" class="ft-check rounded" value="${ft}" checked>
    <span class="font-mono text-xs">${ft.replace('ocd_', '')}</span>`;
  fileTypeChecks.appendChild(label);
});

// ── Repo picker ───────────────────────────────────────────────────────────────
function populateRepos() {
  const repos = Settings.getSavedRepos();
  const current = repoSelect.value;
  repoSelect.innerHTML = '<option value="">— select repo —</option>';
  repos.forEach(r => {
    const opt = document.createElement('option');
    opt.value = r.path;
    opt.textContent = r.name;
    if (r.path === current) opt.selected = true;
    repoSelect.appendChild(opt);
  });
  noReposMsg.classList.toggle('hidden', repos.length > 0);
  repoSelect.classList.toggle('hidden', repos.length === 0);
  updateSearchBtn();
}

document.addEventListener('settings:savedReposChanged', populateRepos);
openSettingsLink.addEventListener('click', () =>
  document.getElementById('settingsGearBtn')?.click()
);

// ── Enable / disable search button ────────────────────────────────────────────
function updateSearchBtn() {
  const hasRepo  = repoSelect.value !== '';
  const hasQuery = queryInput.value.trim() !== '';
  const hasType  = [...document.querySelectorAll('.ft-check')].some(c => c.checked);
  searchBtn.disabled = !(hasRepo && hasQuery && hasType);
}

repoSelect.addEventListener('change', updateSearchBtn);
queryInput.addEventListener('input', updateSearchBtn);
fileTypeChecks.addEventListener('change', updateSearchBtn);

// ── Search ────────────────────────────────────────────────────────────────────
searchBtn.addEventListener('click', runSearch);
queryInput.addEventListener('keydown', e => { if (e.key === 'Enter') runSearch(); });

async function runSearch() {
  const repo = repoSelect.value;
  const query = queryInput.value.trim();
  const mode  = matchMode.value;
  const cs    = caseSensitive.checked;
  const types = [...document.querySelectorAll('.ft-check')]
    .filter(c => c.checked).map(c => c.value);

  if (!repo || !query || !types.length) return;

  searchBtn.disabled = true;
  statusMsg.textContent = 'Searching…';
  resultsEl.innerHTML = '';

  let data;
  try {
    const resp = await fetch('/api/search/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        repo, query, match_mode: mode, case_sensitive: cs, file_types: types,
      }),
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: resp.statusText }));
      throw new Error(err.detail || resp.statusText);
    }
    data = await resp.json();
  } catch (err) {
    statusMsg.textContent = '';
    resultsEl.innerHTML = `<p class="text-red-600 text-sm">${_esc(err.message)}</p>`;
    searchBtn.disabled = false;
    return;
  }

  searchBtn.disabled = false;
  renderResults(data, query);
}

// ── Results rendering ─────────────────────────────────────────────────────────
function renderResults(data, query) {
  const { results, ranges_searched, duration_ms } = data;
  const matchCount = results.reduce((n, r) => n + r.matches.length, 0);

  // Group by manufacturer+range
  const grouped = {};
  for (const r of results) {
    const key = `${r.manufacturer}/${r.range}`;
    if (!grouped[key]) grouped[key] = { manufacturer: r.manufacturer, range: r.range, files: [] };
    grouped[key].files.push({ file_type: r.file_type, matches: r.matches });
  }

  const rangeCount = Object.keys(grouped).length;

  let html = `<p class="text-sm text-gray-500 mb-4">`;
  if (matchCount === 0) {
    html += `No matches found — searched ${ranges_searched} range${ranges_searched !== 1 ? 's' : ''} in ${duration_ms}ms.`;
  } else {
    html += `Found <strong>${matchCount}</strong> match${matchCount !== 1 ? 'es' : ''} across <strong>${rangeCount}</strong> range${rangeCount !== 1 ? 's' : ''} (searched ${ranges_searched} in ${duration_ms}ms).`;
  }
  html += `</p>`;

  for (const [key, group] of Object.entries(grouped)) {
    html += `
      <details open class="bg-white rounded-xl shadow mb-3">
        <summary class="px-5 py-3 font-semibold text-gray-700 cursor-pointer select-none
                        flex items-center justify-between hover:bg-gray-50 rounded-xl">
          <span class="font-mono text-sm">${_esc(group.manufacturer)} / ${_esc(group.range)}</span>
          <span class="text-xs text-gray-400 font-normal">
            ${group.files.reduce((n, f) => n + f.matches.length, 0)} match${group.files.reduce((n, f) => n + f.matches.length, 0) !== 1 ? 'es' : ''}
          </span>
        </summary>
        <div class="px-5 pb-4 space-y-4">
          ${group.files.map(f => renderFileBlock(f)).join('')}
        </div>
      </details>`;
  }

  statusMsg.textContent = '';
  resultsEl.innerHTML = html;
}

function renderFileBlock({ file_type, matches }) {
  const rows = matches.map(m => {
    const cells = m.row.map(c => `<td class="px-3 py-1 text-xs font-mono whitespace-nowrap max-w-xs truncate" title="${_esc(c)}">${_esc(c)}</td>`).join('');
    return `<tr class="border-t border-gray-100 hover:bg-gray-50">
      <td class="px-3 py-1 text-xs text-gray-400 tabular-nums">${m.row_number}</td>
      ${cells}
    </tr>`;
  }).join('');

  return `
    <div>
      <p class="text-xs font-semibold text-gray-500 uppercase tracking-wide mt-3 mb-1 font-mono">
        ${_esc(file_type)}.csv
        <span class="font-normal normal-case text-gray-400">(${matches.length} row${matches.length !== 1 ? 's' : ''})</span>
      </p>
      <div class="overflow-x-auto rounded border border-gray-200">
        <table class="min-w-full">
          <tbody>${rows}</tbody>
        </table>
      </div>
    </div>`;
}

// _esc is provided globally by settings.js (loaded before this script)
```

---

### Task 6: Add dashboard card + final wiring check

**Files:**
- Modify: `static/index.html`

- [ ] **Step 1: Add the Repo Search card to the dashboard grid in `static/index.html`**

After the existing Snapper card `<a>` block, add:

```html
      <a href="/search/"
         class="block bg-white rounded-xl shadow p-6 hover:shadow-md transition">
        <h2 class="text-lg font-semibold text-gray-800 mb-2">Repo Search</h2>
        <p class="text-sm text-gray-500">
          Search for a value across all ranges in a repository.
          Find which ranges reference a finish code, property value, or article.
        </p>
      </a>
```

- [ ] **Step 2: Verify `main.py` has all three registrations**

Confirm `main.py` now contains:
```python
from modules.search.routes import router as search_router
app.include_router(search_router)

@app.get("/search/")
def search_page():
    return FileResponse("static/search/index.html")
```

- [ ] **Step 3: Run the full test suite**

```bash
pytest tests/ -v --ignore=tests/test_reader.py --ignore=tests/test_routes.py --ignore=tests/test_raw_seed_generator.py
```

(The ignored files hit the real SVN repos on disk and may not be available in all environments.)

Expected: all search tests PASS, no regressions in other unit tests.

- [ ] **Step 4: Manual smoke test**

Start the server:
```bash
python main.py
```

1. Open `http://localhost:8090/` — confirm the "Repo Search" card appears.
2. Open `http://localhost:8090/search/` — confirm controls render correctly.
3. Select a saved repo, enter a query (e.g. `H80040`), pick `ocd_propvalue`, click Search.
4. Confirm results render with range names and matching rows.
5. Test all four match modes and the case sensitivity toggle.

- [ ] **Step 5: Commit**

```bash
git add static/search/ static/index.html
git commit -m "feat: add repo search frontend and dashboard card"
```

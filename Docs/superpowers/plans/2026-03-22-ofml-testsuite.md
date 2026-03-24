# OFML Testsuite Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local web application for QA teams to generate pCon snapper files (OBX format) covering all meaningful product permutations for a given OFML range.

**Architecture:** Python FastAPI backend (stateless, serves static files + JSON API). Vanilla HTML/JS frontend with Tailwind CSS from CDN. Each QA module is a separate page linked from a dashboard home. No database — all session state in browser.

**Tech Stack:** Python 3.14, FastAPI, uvicorn, pytest. Frontend: HTML5 + vanilla JS + Tailwind CSS CDN.

**Read before starting:** `CLAUDE.md` and `docs/superpowers/specs/2026-03-22-ofml-testsuite-design.md`

**OFML repo for testing:** `C:\HermanMillerOFMLSVN\Staging\HermanMiller\_repository`
Test range: `hmx/cosm` — OCD files at `{repo}/hmx/cosm/ANY/1/db/`

---

## Chunk 1: Project Scaffold + Home Dashboard

### Task 1: Project setup

**Files:**
- Create: `requirements.txt`
- Create: `main.py`
- Create: `modules/__init__.py`
- Create: `modules/snapper/__init__.py`
- Create: `static/index.html`

- [ ] **Step 1: Create requirements.txt**

```
fastapi==0.115.0
uvicorn[standard]==0.32.0
pytest==8.3.0
httpx==0.28.0
```

- [ ] **Step 2: Install dependencies**

```bash
cd c:/Users/XMAMWU/Projects/MK_OFML_Testsuite
pip install -r requirements.txt
```

Expected: packages install without errors.

- [ ] **Step 3: Create main.py**

```python
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import uvicorn

app = FastAPI(title="OFML Testsuite")
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def home():
    return FileResponse("static/index.html")

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8080, reload=True)
```

- [ ] **Step 4: Create folder structure**

```bash
mkdir -p modules/snapper
mkdir -p static/snapper
mkdir -p tests
touch modules/__init__.py
touch modules/snapper/__init__.py
touch tests/__init__.py
```

- [ ] **Step 5: Create static/index.html**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>OFML Testsuite</title>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-100 min-h-screen">
  <header class="bg-white shadow">
    <div class="max-w-7xl mx-auto px-6 py-4">
      <h1 class="text-2xl font-bold text-gray-800">OFML Testsuite</h1>
      <p class="text-sm text-gray-500">MillerKnoll QA Tools</p>
    </div>
  </header>
  <main class="max-w-7xl mx-auto px-6 py-10">
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
      <a href="/static/snapper/index.html"
         class="block bg-white rounded-xl shadow p-6 hover:shadow-md transition">
        <h2 class="text-lg font-semibold text-gray-800 mb-2">Snapper File Generator</h2>
        <p class="text-sm text-gray-500">
          Generate OBX snapper files covering all product permutations for a range.
          Import into pCon Planner, run Update, export for QA comparison.
        </p>
      </a>
    </div>
  </main>
</body>
</html>
```

- [ ] **Step 6: Verify app starts**

```bash
python main.py
```

Open `http://localhost:8080` in browser. Expected: home page with "Snapper File Generator" card.

- [ ] **Step 7: Commit**

```bash
git init
git add requirements.txt main.py modules/ static/index.html tests/
git commit -m "feat: project scaffold with home dashboard"
```

---

## Chunk 2: OCD Data Reader

This module reads the OCD CSV files for a selected range and returns structured data to the API layer.

### Task 2: Range discovery

**Files:**
- Create: `modules/snapper/reader.py`
- Create: `tests/test_reader.py`

The reader must find all valid ranges in a repository. A range is valid if its `ANY/1/db/` subfolder contains `ocd_article.csv`.

- [ ] **Step 1: Write failing test for range discovery**

Create `tests/test_reader.py`:

```python
import pytest
from modules.snapper.reader import discover_ranges

REPO_ROOT = r"C:\HermanMillerOFMLSVN\Staging\HermanMiller\_repository"

def test_discover_ranges_finds_cosm():
    ranges = discover_ranges(REPO_ROOT)
    # ranges is a list of dicts: {manufacturer, range, path}
    range_ids = [(r["manufacturer"], r["range"]) for r in ranges]
    assert ("hmx", "cosm") in range_ids

def test_discover_ranges_only_returns_valid():
    ranges = discover_ranges(REPO_ROOT)
    for r in ranges:
        assert "manufacturer" in r
        assert "range" in r
        assert "db_path" in r
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_reader.py::test_discover_ranges_finds_cosm -v
```

Expected: ImportError or AttributeError (function not defined yet).

- [ ] **Step 3: Implement discover_ranges in reader.py**

Create `modules/snapper/reader.py`:

```python
import os
from pathlib import Path

def discover_ranges(repo_root: str) -> list[dict]:
    """
    Scan repo_root for valid OFML ranges.
    A range is valid if {manufacturer}/{range}/ANY/1/db/ocd_article.csv exists.
    Returns list of {manufacturer, range, db_path}.
    """
    results = []
    repo = Path(repo_root)
    if not repo.exists():
        return results
    for mfr_dir in sorted(repo.iterdir()):
        if not mfr_dir.is_dir():
            continue
        for range_dir in sorted(mfr_dir.iterdir()):
            if not range_dir.is_dir():
                continue
            db_path = range_dir / "ANY" / "1" / "db"
            if (db_path / "ocd_article.csv").exists():
                results.append({
                    "manufacturer": mfr_dir.name,
                    "range": range_dir.name,
                    "db_path": str(db_path),
                })
    return results
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_reader.py -v
```

Expected: both tests PASS.

- [ ] **Step 5: Commit**

```bash
git add modules/snapper/reader.py tests/test_reader.py
git commit -m "feat: range discovery from OFML repository"
```

---

### Task 3: OCD file parser

This is the core data reader. It reads four CSV files and returns a structured representation of a range's articles, properties, and values.

**Files:**
- Modify: `modules/snapper/reader.py`
- Modify: `tests/test_reader.py`

**CSV file schemas (semicolon-delimited, no header row):**

`ocd_article.csv`: `BaseCode ; Type ; MfrCode ; SeriesCode ; ...`
→ We want rows where col[1] == 'C' (configurable articles only)

`ocd_artbase.csv`: `BaseCode ; ArticleClass ; PropertyName ; DefaultValue`
→ We want to build a map: BaseCode → ArticleClass (take first row per BaseCode)

`ocd_property.csv`: `ArticleClass ; PropertyName ; SortOrder ; PropertyClassId ; RelationId ; ...`
→ We want all rows, grouped by ArticleClass

`ocd_propertyvalue.csv`: `ArticleClass ; PropertyName ; SortOrder ; ValueId ; RelationId ; DefaultFlag ; ... ; Value`
→ Value is always the LAST column. RelationId is col[4]. DefaultFlag is col[5].

- [ ] **Step 1: Write failing tests for OCD parsing**

Add to `tests/test_reader.py`:

```python
from modules.snapper.reader import load_range_data

def test_load_range_data_returns_articles():
    data = load_range_data(r"C:\HermanMillerOFMLSVN\Staging\HermanMiller\_repository\hmx\cosm\ANY\1\db")
    assert len(data["articles"]) > 0
    article = data["articles"][0]
    assert "code" in article
    assert "article_class" in article
    assert "manufacturer_code" in article
    assert "series_code" in article

def test_load_range_data_returns_properties():
    data = load_range_data(r"C:\HermanMillerOFMLSVN\Staging\HermanMiller\_repository\hmx\cosm\ANY\1\db")
    assert len(data["properties"]) > 0
    prop = data["properties"][0]
    assert "article_class" in prop
    assert "name" in prop
    assert "sort_order" in prop
    assert "relation_id" in prop

def test_load_range_data_returns_values():
    data = load_range_data(r"C:\HermanMillerOFMLSVN\Staging\HermanMiller\_repository\hmx\cosm\ANY\1\db")
    assert len(data["values"]) > 0
    val = data["values"][0]
    assert "article_class" in val
    assert "property_name" in val
    assert "value" in val
    assert "relation_id" in val
    assert "is_default" in val

def test_cosm_has_arms_property():
    data = load_range_data(r"C:\HermanMillerOFMLSVN\Staging\HermanMiller\_repository\hmx\cosm\ANY\1\db")
    prop_names = [p["name"] for p in data["properties"]]
    assert "Arms" in prop_names

def test_cosm_arms_has_multiple_values():
    data = load_range_data(r"C:\HermanMillerOFMLSVN\Staging\HermanMiller\_repository\hmx\cosm\ANY\1\db")
    arms_values = [v["value"] for v in data["values"] if v["property_name"] == "Arms"]
    assert len(arms_values) >= 3  # N, P, J, H
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_reader.py::test_load_range_data_returns_articles -v
```

Expected: ImportError (function not defined).

- [ ] **Step 3: Implement load_range_data**

Add to `modules/snapper/reader.py`:

```python
def _read_csv(path: str) -> list[list[str]]:
    """Read a semicolon-delimited CSV, skipping comment lines (starting with #)."""
    rows = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            rows.append(line.split(";"))
    return rows


def load_range_data(db_path: str) -> dict:
    """
    Load OCD data for a range from its db/ folder.
    Returns {articles, properties, values, relations}.

    articles: list of {code, article_class, manufacturer_code, series_code}
    properties: list of {article_class, name, sort_order, relation_id}
    values: list of {article_class, property_name, sort_order, value_id,
                     relation_id, is_default, value}
    relations: dict of {relation_id: full_expression_string}
    """
    db = Path(db_path)

    # --- ocd_article.csv: configurable articles only ---
    article_rows = _read_csv(str(db / "ocd_article.csv"))
    # col[1] == 'C' means configurable
    configurable = {row[0]: row for row in article_rows if len(row) > 3 and row[1].strip() == "C"}

    # --- ocd_artbase.csv: map article code → article class ---
    artbase_rows = _read_csv(str(db / "ocd_artbase.csv"))
    code_to_class = {}
    for row in artbase_rows:
        if len(row) < 2:
            continue
        code = row[0].strip()
        if code not in code_to_class:
            code_to_class[code] = row[1].strip()

    articles = []
    for code, row in configurable.items():
        articles.append({
            "code": code.strip(),
            "article_class": code_to_class.get(code.strip(), ""),
            "manufacturer_code": row[2].strip() if len(row) > 2 else "",
            "series_code": row[3].strip() if len(row) > 3 else "",
        })

    # --- ocd_property.csv ---
    prop_rows = _read_csv(str(db / "ocd_property.csv"))
    properties = []
    for row in prop_rows:
        if len(row) < 5:
            continue
        properties.append({
            "article_class": row[0].strip(),
            "name": row[1].strip(),
            "sort_order": int(row[2].strip()) if row[2].strip().isdigit() else 0,
            "relation_id": row[4].strip(),
        })

    # --- ocd_propertyvalue.csv ---
    # Value is always the LAST column (column index -1)
    value_rows = _read_csv(str(db / "ocd_propertyvalue.csv"))
    values = []
    for row in value_rows:
        if len(row) < 6:
            continue
        values.append({
            "article_class": row[0].strip(),
            "property_name": row[1].strip(),
            "sort_order": int(row[2].strip()) if row[2].strip().isdigit() else 0,
            "value_id": row[3].strip(),
            "relation_id": row[4].strip(),
            "is_default": row[5].strip() == "1",
            "value": row[-1].strip(),
        })

    # --- ocd_relation.csv: build full expression per relation_id ---
    relation_path = db / "ocd_relation.csv"
    relations: dict[str, str] = {}
    if relation_path.exists():
        rel_rows = _read_csv(str(relation_path))
        for row in rel_rows:
            if len(row) < 3:
                continue
            rel_id = row[0].strip()
            expression_part = row[2].strip().strip('"')
            if rel_id not in relations:
                relations[rel_id] = expression_part
            else:
                relations[rel_id] += " " + expression_part

    return {
        "articles": articles,
        "properties": properties,
        "values": values,
        "relations": relations,
    }
```

- [ ] **Step 4: Run all reader tests**

```bash
pytest tests/test_reader.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add modules/snapper/reader.py tests/test_reader.py
git commit -m "feat: OCD CSV parser for articles, properties, values, relations"
```

---

## Chunk 3: API Routes

Wire the reader into FastAPI endpoints so the frontend can call them.

### Task 4: Snapper API routes

**Files:**
- Create: `modules/snapper/routes.py`
- Modify: `main.py`
- Create: `tests/test_routes.py`

- [ ] **Step 1: Write failing tests for API**

Create `tests/test_routes.py`:

```python
import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

REPO_ROOT = r"C:\HermanMillerOFMLSVN\Staging\HermanMiller\_repository"


def test_list_ranges():
    response = client.get(f"/api/snapper/ranges?repo={REPO_ROOT}")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert any(r["manufacturer"] == "hmx" and r["range"] == "cosm" for r in data)


def test_load_range():
    response = client.get(
        f"/api/snapper/range?repo={REPO_ROOT}&manufacturer=hmx&range=cosm"
    )
    assert response.status_code == 200
    data = response.json()
    assert "articles" in data
    assert "properties" in data
    assert "values" in data
    assert len(data["articles"]) > 0


def test_load_range_invalid_returns_404():
    response = client.get(
        f"/api/snapper/range?repo={REPO_ROOT}&manufacturer=hmx&range=doesnotexist"
    )
    assert response.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_routes.py -v
```

Expected: all fail (routes not registered).

- [ ] **Step 3: Create modules/snapper/routes.py**

```python
from fastapi import APIRouter, HTTPException, Query
from .reader import discover_ranges, load_range_data
from pathlib import Path

router = APIRouter(prefix="/api/snapper", tags=["snapper"])


@router.get("/ranges")
def list_ranges(repo: str = Query(..., description="Path to OFML repository root")):
    """List all valid ranges found in the repository."""
    return discover_ranges(repo)


@router.get("/range")
def get_range(
    repo: str = Query(...),
    manufacturer: str = Query(...),
    range: str = Query(...),
):
    """Load OCD data for a specific range."""
    db_path = Path(repo) / manufacturer / range / "ANY" / "1" / "db"
    if not db_path.exists():
        raise HTTPException(status_code=404, detail=f"Range not found: {db_path}")
    return load_range_data(str(db_path))
```

- [ ] **Step 4: Register router in main.py**

Add to `main.py` (after imports, before `if __name__ == "__main__"`):

```python
from modules.snapper.routes import router as snapper_router
app.include_router(snapper_router)
```

- [ ] **Step 5: Run all tests**

```bash
pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add modules/snapper/routes.py main.py tests/test_routes.py
git commit -m "feat: snapper API routes for range discovery and OCD data loading"
```

---

## Chunk 4: Permutation Engine + OBX Generator

### Task 5: Permutation engine

Computes the cartesian product of selected dimensions. Hierarchy handling (fabric type/colour) is a separate concern and handled later — the permutation engine itself only receives dimensions that have already been resolved. For now, every property dimension is included as-is.

**Files:**
- Create: `modules/snapper/generator.py`
- Create: `tests/test_generator.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_generator.py`:

```python
import pytest
from modules.snapper.generator import compute_permutations, build_varcode, build_obx

def test_compute_permutations_single_dimension():
    dimensions = {"Arms": ["N", "P", "J"]}
    articles = ["FLC142"]
    result = compute_permutations(articles, dimensions)
    assert len(result) == 3
    assert {"article": "FLC142", "properties": {"Arms": "N"}} in result

def test_compute_permutations_two_dimensions():
    dimensions = {"Arms": ["N", "P"], "Back_Height": ["4", "5"]}
    articles = ["FLC142"]
    result = compute_permutations(articles, dimensions)
    assert len(result) == 4  # 2 * 2

def test_compute_permutations_two_articles():
    dimensions = {"Arms": ["N", "P"]}
    articles = ["FLC142", "FLC143"]
    result = compute_permutations(articles, dimensions)
    assert len(result) == 4  # 2 articles * 2 values

def test_compute_permutations_empty_dimensions():
    # No properties selected — one entry per article with empty props
    dimensions = {}
    articles = ["FLC142"]
    result = compute_permutations(articles, dimensions)
    assert len(result) == 1
    assert result[0] == {"article": "FLC142", "properties": {}}

def test_build_varcode():
    article_class = "COSM_NORMAL"
    properties = {"Arms": "N", "Back_Height": "4"}
    varcode = build_varcode(article_class, properties)
    parts = varcode.split(";")
    assert "COSM_NORMAL.Arms=N" in parts
    assert "COSM_NORMAL.Back_Height=4" in parts

def test_build_varcode_empty_properties():
    varcode = build_varcode("COSM_NORMAL", {})
    assert varcode == ""
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_generator.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement compute_permutations and build_varcode**

Create `modules/snapper/generator.py`:

```python
import itertools
import uuid
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom.minidom import parseString


def compute_permutations(
    articles: list[str],
    dimensions: dict[str, list[str]],
) -> list[dict]:
    """
    Compute cartesian product of articles × all selected property values.

    Args:
        articles: list of base article codes to include
        dimensions: {property_name: [selected_values]}
            Property values that are hierarchy children (e.g. fabric colours)
            should already be resolved and either excluded or pre-assigned
            before calling this function.

    Returns:
        list of {article: str, properties: {prop_name: value}}
    """
    if not articles:
        return []

    if not dimensions:
        return [{"article": a, "properties": {}} for a in articles]

    prop_names = list(dimensions.keys())
    value_lists = [dimensions[p] for p in prop_names]

    results = []
    for article in articles:
        for combo in itertools.product(*value_lists):
            results.append({
                "article": article,
                "properties": dict(zip(prop_names, combo)),
            })
    return results


def build_varcode(article_class: str, properties: dict[str, str]) -> str:
    """
    Build an OFML varcode string from an article class and property assignments.
    Format: ArticleClass.Prop1=Val1;ArticleClass.Prop2=Val2
    Returns empty string if no properties.
    """
    if not properties:
        return ""
    parts = [f"{article_class}.{k}={v}" for k, v in properties.items()]
    return ";".join(parts)
```

- [ ] **Step 4: Run permutation tests**

```bash
pytest tests/test_generator.py -k "permutation or varcode" -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add modules/snapper/generator.py tests/test_generator.py
git commit -m "feat: permutation engine and varcode builder"
```

---

### Task 6: OBX generator

Builds the OBX XML document from a list of permutations.

**⚠️ Empirical validation required:** The minimum OBX entry structure must be tested against a real pCon installation before this is considered done. See Section 10 of the design spec for what to test.

**Files:**
- Modify: `modules/snapper/generator.py`
- Modify: `tests/test_generator.py`

- [ ] **Step 1: Write failing test for OBX generation**

Add to `tests/test_generator.py`:

```python
import xml.etree.ElementTree as ET
from modules.snapper.generator import build_obx

def test_build_obx_returns_valid_xml():
    permutations = [
        {"article": "FLC142", "properties": {"Arms": "N", "Back_Height": "4"}},
        {"article": "FLC142", "properties": {"Arms": "P", "Back_Height": "4"}},
    ]
    article_class_map = {"FLC142": "COSM_NORMAL"}
    manufacturer_code = "HM"
    series_code = "COSM"

    xml_str = build_obx(permutations, article_class_map, manufacturer_code, series_code)

    root = ET.fromstring(xml_str)
    assert root.tag == "cutBuffer"
    items = root.find("items")
    assert items is not None
    articles = items.findall("bskArticle")
    assert len(articles) == 2

def test_build_obx_contains_varcode():
    permutations = [{"article": "FLC142", "properties": {"Arms": "N"}}]
    article_class_map = {"FLC142": "COSM_NORMAL"}
    xml_str = build_obx(permutations, article_class_map, "HM", "COSM")

    root = ET.fromstring(xml_str)
    article = root.find(".//bskArticle")
    artnrs = {a.get("type"): a.text for a in article.findall("artNr")}
    assert "base" in artnrs
    assert artnrs["base"] == "FLC142"
    assert "ofmlvarcode" in artnrs
    assert "COSM_NORMAL.Arms=N" in artnrs["ofmlvarcode"]

def test_build_obx_empty_properties():
    # Articles with no selected properties should still get base artNr, no varcode
    permutations = [{"article": "FLC142", "properties": {}}]
    article_class_map = {"FLC142": "COSM_NORMAL"}
    xml_str = build_obx(permutations, article_class_map, "HM", "COSM")
    root = ET.fromstring(xml_str)
    article = root.find(".//bskArticle")
    artnrs = {a.get("type"): a.text for a in article.findall("artNr")}
    assert "base" in artnrs
    assert "ofmlvarcode" not in artnrs
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_generator.py::test_build_obx_returns_valid_xml -v
```

Expected: ImportError (build_obx not defined yet).

- [ ] **Step 3: Implement build_obx**

Add to `modules/snapper/generator.py`:

```python
def build_obx(
    permutations: list[dict],
    article_class_map: dict[str, str],
    manufacturer_code: str,
    series_code: str,
) -> str:
    """
    Build an OBX XML document from a list of permutations.

    Args:
        permutations: output of compute_permutations (list of {article, properties})
        article_class_map: {article_code: article_class} — from OCD artbase data
        manufacturer_code: e.g. "HM" — from ocd_article.csv col[2]
        series_code: e.g. "COSM" — from ocd_article.csv col[3]

    Returns:
        Pretty-printed XML string.

    NOTE: The minimum required XML structure must be verified empirically against
    a real pCon installation. See design spec Section 10. If pCon's Update step
    fails to resolve entries, try:
    - Adding updateState='Outdated' (forces re-resolution)
    - Adding empty <features/> element
    - Adding <description type='short'><text lang='en'/></description> stub
    """
    session_id = str(uuid.uuid4())

    root = Element("cutBuffer")
    state = SubElement(root, "state", sessionId=session_id)
    SubElement(root, "versionInfo",
               vendorKey="EasternGraphics",
               appKey="EAI-Server",
               appVersion="4.18.3",
               bskXmlVersion="1.8.10")

    items = SubElement(root, "items")

    for perm in permutations:
        article_code = perm["article"]
        properties = perm["properties"]
        article_class = article_class_map.get(article_code, "")

        basket_article = SubElement(items, "bskArticle",
                                    basketId=str(uuid.uuid4()),
                                    itemType="BasketAggregate",
                                    updateState="UpToDate")

        mfr_el = SubElement(basket_article, "manufacturer", id=manufacturer_code)
        series_el = SubElement(basket_article, "series", id=series_code)

        base_artnr = SubElement(basket_article, "artNr", type="base")
        base_artnr.text = article_code

        if properties and article_class:
            varcode = build_varcode(article_class, properties)
            if varcode:
                varcode_el = SubElement(basket_article, "artNr", type="ofmlvarcode")
                varcode_el.text = varcode

    xml_bytes = tostring(root, encoding="unicode")
    return parseString(xml_bytes).toprettyxml(indent="  ")
```

- [ ] **Step 4: Run all generator tests**

```bash
pytest tests/test_generator.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add modules/snapper/generator.py tests/test_generator.py
git commit -m "feat: OBX XML generator from permutations"
```

---

### Task 7: Generator API route + download

Expose an endpoint that accepts a generation spec and returns an OBX file as a download.

**Files:**
- Modify: `modules/snapper/routes.py`
- Modify: `tests/test_routes.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_routes.py`:

```python
def test_generate_obx_download():
    payload = {
        "repo": REPO_ROOT,
        "manufacturer": "hmx",
        "range": "cosm",
        "selected_articles": ["FLC142", "FLC143"],
        "selected_properties": {
            "Arms": ["N", "P"],
            "Back_Height": ["4", "5"]
        },
        "filename": "test_cosm.obx"
    }
    response = client.post("/api/snapper/generate", json=payload)
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/xml"
    # 2 articles * 2 Arms * 2 Back_Height = 8 permutations
    content = response.text
    assert content.count("<bskArticle") == 8
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_routes.py::test_generate_obx_download -v
```

Expected: 404 or 422 (route not defined).

- [ ] **Step 3: Add generate endpoint to routes.py**

Add to `modules/snapper/routes.py`:

```python
from fastapi.responses import Response
from pydantic import BaseModel
from .generator import compute_permutations, build_obx


class GenerateRequest(BaseModel):
    repo: str
    manufacturer: str
    range: str
    selected_articles: list[str]
    selected_properties: dict[str, list[str]]  # {prop_name: [selected_values]}
    filename: str = "snapper.obx"


@router.post("/generate")
def generate_obx(req: GenerateRequest):
    """Generate a single OBX file from a generation spec."""
    db_path = Path(req.repo) / req.manufacturer / req.range / "ANY" / "1" / "db"
    if not db_path.exists():
        raise HTTPException(status_code=404, detail="Range not found")

    range_data = load_range_data(str(db_path))

    # Build article_class_map from loaded data
    article_class_map = {a["code"]: a["article_class"] for a in range_data["articles"]}

    # Get manufacturer/series from first article
    mfr_code = range_data["articles"][0]["manufacturer_code"] if range_data["articles"] else req.manufacturer
    series_code = range_data["articles"][0]["series_code"] if range_data["articles"] else req.range.upper()

    permutations = compute_permutations(req.selected_articles, req.selected_properties)
    xml_content = build_obx(permutations, article_class_map, mfr_code, series_code)

    return Response(
        content=xml_content,
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{req.filename}"'}
    )
```

- [ ] **Step 4: Run all tests**

```bash
pytest tests/ -v
```

Expected: all PASS.

- [ ] **Step 5: Manual smoke test**
Start the server (`python main.py`) and use curl or a REST client to hit the generate endpoint with a small selection. Save the result as a `.obx` file and import it into pCon Planner. Run Update. Document what happens — does pCon accept the minimal format? See design spec Section 10 for what to check.

- [ ] **Step 6: Commit**

```bash
git add modules/snapper/routes.py tests/test_routes.py
git commit -m "feat: OBX generate endpoint with download response"
```

---

## Chunk 5: Frontend — Snapper Generator Page

### Task 8: Dimension columns UI

**Files:**
- Create: `static/snapper/index.html`
- Create: `static/snapper/snapper.js`

This task produces a working end-to-end UI: select a repo + range, see dimension columns with checkboxes, see live permutation count.

- [ ] **Step 1: Create static/snapper/index.html**

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

  <!-- Header bar -->
  <header class="bg-white shadow sticky top-0 z-10">
    <div class="max-w-full px-6 py-3 flex flex-wrap items-end gap-4">
      <a href="/" class="text-sm text-blue-600 hover:underline mr-2">← Home</a>
      <h1 class="text-lg font-bold text-gray-800 mr-4">Snapper File Generator</h1>

      <div class="flex items-end gap-3 flex-wrap">
        <div>
          <label class="block text-xs text-gray-500 mb-1">Repository path</label>
          <input id="repoPath" type="text"
            class="border rounded px-2 py-1 text-sm w-80"
            placeholder="C:\path\to\_repository">
        </div>
        <div>
          <label class="block text-xs text-gray-500 mb-1">Manufacturer</label>
          <select id="mfrSelect" class="border rounded px-2 py-1 text-sm" disabled>
            <option value="">—</option>
          </select>
        </div>
        <div>
          <label class="block text-xs text-gray-500 mb-1">Range</label>
          <select id="rangeSelect" class="border rounded px-2 py-1 text-sm" disabled>
            <option value="">—</option>
          </select>
        </div>
        <button id="loadBtn"
          class="bg-blue-600 text-white px-4 py-1 rounded text-sm hover:bg-blue-700 disabled:opacity-50"
          disabled>
          Load
        </button>
      </div>
    </div>
  </header>

  <!-- Main area -->
  <main class="flex flex-1 overflow-hidden">

    <!-- Dimension columns panel -->
    <section class="flex-1 overflow-x-auto p-4">
      <div id="dimensionArea" class="hidden">
        <div id="dimensionColumns" class="flex gap-4 items-start"></div>
        <div id="permCount" class="mt-4 text-sm font-medium text-gray-700"></div>
      </div>
      <div id="emptyState" class="text-gray-400 text-sm mt-8 ml-2">
        Select a repository and range to begin.
      </div>
    </section>

    <!-- Queue panel -->
    <aside class="w-72 bg-white border-l shadow-inner p-4 flex flex-col">
      <h2 class="font-semibold text-gray-700 mb-3">Generation Queue</h2>

      <div class="mb-3">
        <input id="genName" type="text" placeholder="Generation name"
          class="border rounded px-2 py-1 text-sm w-full mb-2">
        <button id="addToQueueBtn"
          class="w-full bg-green-600 text-white px-3 py-1 rounded text-sm hover:bg-green-700 disabled:opacity-50"
          disabled>
          Add to Queue
        </button>
      </div>

      <div id="queueList" class="flex-1 overflow-y-auto space-y-2"></div>

      <button id="generateAllBtn"
        class="mt-4 w-full bg-blue-700 text-white px-3 py-2 rounded text-sm hover:bg-blue-800 disabled:opacity-50"
        disabled>
        Generate All
      </button>
    </aside>
  </main>

  <script src="/static/snapper/snapper.js"></script>
</body>
</html>
```

- [ ] **Step 2: Create static/snapper/snapper.js**

```javascript
// ── State ──────────────────────────────────────────────────────────────────
const WARN_LIMIT = 200;
const ERROR_LIMIT = 500;
let rangeData = null;  // {articles, properties, values}
let queue = [];        // [{name, selectedArticles, selectedProperties, count}]

// ── DOM refs ───────────────────────────────────────────────────────────────
const repoPath = document.getElementById('repoPath');
const mfrSelect = document.getElementById('mfrSelect');
const rangeSelect = document.getElementById('rangeSelect');
const loadBtn = document.getElementById('loadBtn');
const dimensionArea = document.getElementById('dimensionArea');
const dimensionColumns = document.getElementById('dimensionColumns');
const emptyState = document.getElementById('emptyState');
const permCount = document.getElementById('permCount');
const genName = document.getElementById('genName');
const addToQueueBtn = document.getElementById('addToQueueBtn');
const queueList = document.getElementById('queueList');
const generateAllBtn = document.getElementById('generateAllBtn');

// ── Persist repo path ──────────────────────────────────────────────────────
repoPath.value = localStorage.getItem('repoPath') || '';

repoPath.addEventListener('change', async () => {
  localStorage.setItem('repoPath', repoPath.value.trim());
  await loadRanges();
});

// ── Load ranges from API ───────────────────────────────────────────────────
async function loadRanges() {
  const repo = repoPath.value.trim();
  if (!repo) return;
  const res = await fetch(`/api/snapper/ranges?repo=${encodeURIComponent(repo)}`);
  if (!res.ok) return;
  const ranges = await res.json();

  // Populate manufacturer dropdown
  const mfrs = [...new Set(ranges.map(r => r.manufacturer))].sort();
  mfrSelect.innerHTML = '<option value="">—</option>' +
    mfrs.map(m => `<option value="${m}">${m}</option>`).join('');
  mfrSelect.disabled = false;

  mfrSelect.addEventListener('change', () => {
    const selectedMfr = mfrSelect.value;
    const filtered = ranges.filter(r => r.manufacturer === selectedMfr);
    rangeSelect.innerHTML = '<option value="">—</option>' +
      filtered.map(r => `<option value="${r.range}">${r.range}</option>`).join('');
    rangeSelect.disabled = false;
    rangeSelect.addEventListener('change', () => {
      loadBtn.disabled = !rangeSelect.value;
    });
  });
}

if (repoPath.value) loadRanges();

// ── Load range data ────────────────────────────────────────────────────────
loadBtn.addEventListener('click', async () => {
  const repo = repoPath.value.trim();
  const mfr = mfrSelect.value;
  const range = rangeSelect.value;
  const res = await fetch(
    `/api/snapper/range?repo=${encodeURIComponent(repo)}&manufacturer=${mfr}&range=${range}`
  );
  if (!res.ok) { alert('Failed to load range'); return; }
  rangeData = await res.json();
  renderDimensions();
  emptyState.classList.add('hidden');
  dimensionArea.classList.remove('hidden');
  addToQueueBtn.disabled = false;
});

// ── Render dimension columns ───────────────────────────────────────────────
function renderDimensions() {
  dimensionColumns.innerHTML = '';

  // Articles column
  const articleCodes = rangeData.articles.map(a => a.code);
  dimensionColumns.appendChild(renderColumn('Articles', articleCodes, 'article'));

  // Property columns — one per unique property name
  const propMap = {};
  for (const v of rangeData.values) {
    if (!propMap[v.property_name]) propMap[v.property_name] = [];
    if (!propMap[v.property_name].includes(v.value)) {
      propMap[v.property_name].push(v.value);
    }
  }

  // Sort by sort_order from properties list
  const propOrder = {};
  for (const p of rangeData.properties) {
    if (!propOrder[p.name]) propOrder[p.name] = p.sort_order;
  }
  const sortedProps = Object.keys(propMap).sort(
    (a, b) => (propOrder[a] || 999) - (propOrder[b] || 999)
  );

  for (const propName of sortedProps) {
    dimensionColumns.appendChild(renderColumn(propName, propMap[propName], `prop_${propName}`));
  }

  updatePermCount();
}

function renderColumn(label, values, key) {
  const col = document.createElement('div');
  col.className = 'bg-white rounded-lg shadow p-3 min-w-36 max-w-48 flex flex-col';
  col.innerHTML = `
    <div class="font-semibold text-sm text-gray-700 mb-2 border-b pb-1">${label}</div>
    <div class="flex gap-1 mb-2">
      <button class="text-xs text-blue-600 hover:underline select-all-btn">All</button>
      <span class="text-gray-300">|</span>
      <button class="text-xs text-blue-600 hover:underline select-none-btn">None</button>
    </div>
    <div class="overflow-y-auto max-h-64 space-y-1">
      ${values.map(v => `
        <label class="flex items-center gap-1 text-xs text-gray-700 cursor-pointer">
          <input type="checkbox" class="dim-check" data-key="${key}" data-value="${v}" checked>
          <span>${v}</span>
        </label>
      `).join('')}
    </div>
  `;
  col.querySelector('.select-all-btn').addEventListener('click', () => {
    col.querySelectorAll('.dim-check').forEach(cb => cb.checked = true);
    updatePermCount();
  });
  col.querySelector('.select-none-btn').addEventListener('click', () => {
    col.querySelectorAll('.dim-check').forEach(cb => cb.checked = false);
    updatePermCount();
  });
  col.querySelectorAll('.dim-check').forEach(cb =>
    cb.addEventListener('change', updatePermCount)
  );
  return col;
}

// ── Permutation count ──────────────────────────────────────────────────────
function getSelections() {
  const articles = [];
  const properties = {};

  document.querySelectorAll('.dim-check:checked').forEach(cb => {
    const key = cb.dataset.key;
    const val = cb.dataset.value;
    if (key === 'article') {
      articles.push(val);
    } else {
      const propName = key.replace(/^prop_/, '');
      if (!properties[propName]) properties[propName] = [];
      properties[propName].push(val);
    }
  });
  return { articles, properties };
}

function countPermutations(articles, properties) {
  if (articles.length === 0) return 0;
  const propCounts = Object.values(properties).map(v => v.length);
  const propProduct = propCounts.reduce((a, b) => a * b, 1);
  return articles.length * propProduct;
}

function updatePermCount() {
  const { articles, properties } = getSelections();
  const count = countPermutations(articles, properties);
  permCount.textContent = `${count.toLocaleString()} permutations`;
  permCount.className = 'mt-4 text-sm font-medium ' + (
    count > ERROR_LIMIT ? 'text-red-600' :
    count > WARN_LIMIT  ? 'text-amber-600' :
                          'text-gray-700'
  );
  if (count > ERROR_LIMIT) {
    permCount.textContent += ` ⚠ Consider splitting into multiple files (suggested max: ${ERROR_LIMIT})`;
  }
}

// ── Queue ──────────────────────────────────────────────────────────────────
addToQueueBtn.addEventListener('click', () => {
  const name = genName.value.trim() || `Generation ${queue.length + 1}`;
  const { articles, properties } = getSelections();
  const count = countPermutations(articles, properties);
  queue.push({
    name,
    selectedArticles: articles,
    selectedProperties: properties,
    count,
    repo: repoPath.value.trim(),
    manufacturer: mfrSelect.value,
    range: rangeSelect.value,
  });
  genName.value = '';
  renderQueue();
});

function renderQueue() {
  queueList.innerHTML = '';
  for (let i = 0; i < queue.length; i++) {
    const entry = queue[i];
    const card = document.createElement('div');
    card.className = 'bg-gray-50 border rounded p-2 text-xs';
    card.innerHTML = `
      <div class="flex justify-between items-start">
        <span class="font-semibold text-gray-800">${entry.name}</span>
        <button class="text-red-500 hover:text-red-700 ml-2" data-idx="${i}">✕</button>
      </div>
      <div class="text-gray-500 mt-1">${entry.count.toLocaleString()} permutations</div>
      <div class="text-gray-400">${entry.selectedArticles.length} articles · ${Object.keys(entry.selectedProperties).length} props</div>
    `;
    card.querySelector('button').addEventListener('click', (e) => {
      queue.splice(parseInt(e.target.dataset.idx), 1);
      renderQueue();
    });
    queueList.appendChild(card);
  }
  generateAllBtn.disabled = queue.length === 0;
}

// ── Generate all ───────────────────────────────────────────────────────────
generateAllBtn.addEventListener('click', async () => {
  generateAllBtn.disabled = true;
  generateAllBtn.textContent = 'Generating…';

  for (const entry of queue) {
    const payload = {
      repo: entry.repo,
      manufacturer: entry.manufacturer,
      range: entry.range,
      selected_articles: entry.selectedArticles,
      selected_properties: entry.selectedProperties,
      filename: `${entry.name.replace(/\s+/g, '_')}.obx`,
    };
    const res = await fetch('/api/snapper/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      alert(`Failed to generate: ${entry.name}`);
      continue;
    }
    // Trigger browser download
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = payload.filename;
    a.click();
    URL.revokeObjectURL(url);
  }

  generateAllBtn.disabled = false;
  generateAllBtn.textContent = 'Generate All';
});
```

- [ ] **Step 3: Manual end-to-end test**

Start the server:
```bash
python main.py
```

1. Open `http://localhost:8080/static/snapper/index.html`
2. Enter the repo path: `C:\HermanMillerOFMLSVN\Staging\HermanMiller\_repository`
3. Select `hmx` → `cosm` → Load
4. Verify dimension columns appear (Articles, Arms, Back_Height, etc.)
5. Deselect most values, leave 2 articles and 2 values per property
6. Verify permutation count updates correctly
7. Add to queue, hit Generate All
8. Verify `.obx` file downloads
9. Import into pCon Planner → run Update → check results

- [ ] **Step 4: Commit**

```bash
git add static/snapper/
git commit -m "feat: snapper generator frontend with dimensions, queue, and download"
```

---

## Chunk 6: Property Hierarchy Detection (Future — Complex)

**⚠️ This chunk is explicitly marked for a future implementation session.** The algorithm is complex and must be implemented carefully with full context from the design spec. Do NOT attempt to implement it without reading Section 5 of the design spec thoroughly.

**Prerequisite:** Chunks 1–5 must be complete and the basic OBX generation must be validated against pCon before starting this chunk.

### Task 9: fabric_colour_tbl.csv parser

**Files:**
- Create: `modules/snapper/hierarchy.py`
- Create: `tests/test_hierarchy.py`

**What it does:** When `fabric_colour_tbl.csv` exists in `db/`, parse it to build a type→colours map. This is the explicit hierarchy source used in ranges like Pullman and Always.

**File format:** `RowNum ; CATEGORY ; ValueCode` (no header)
- `CATEGORY` is either `COL_FABRIC_TYPE` or `COL_FABRIC_COLOUR`
- A `COL_FABRIC_TYPE` row marks the start of a new type group
- All subsequent `COL_FABRIC_COLOUR` rows until the next `COL_FABRIC_TYPE` belong to that type

- [ ] **Step 1: Write test using Pullman data**

Create `tests/test_hierarchy.py`:

```python
import pytest
from modules.snapper.hierarchy import parse_fabric_colour_table

PULLMAN_DB = r"C:\HermanMillerOFMLSVN\Staging\HermanMiller\_repository\hmx\pullman\ANY\1\db"

def test_parse_fabric_colour_table_returns_dict():
    result = parse_fabric_colour_table(PULLMAN_DB + r"\fabric_colour_tbl.csv")
    assert isinstance(result, dict)
    assert len(result) > 0

def test_each_type_has_colours():
    result = parse_fabric_colour_table(PULLMAN_DB + r"\fabric_colour_tbl.csv")
    for type_code, colours in result.items():
        assert isinstance(colours, list)
        assert len(colours) > 0

def test_returns_none_when_file_missing():
    from modules.snapper.hierarchy import parse_fabric_colour_table
    result = parse_fabric_colour_table("/nonexistent/fabric_colour_tbl.csv")
    assert result is None
```

- [ ] **Step 2–5:** Implement, test, commit (follow same TDD pattern as previous tasks).

---

### Task 10: Relation expression parser

**Files:**
- Modify: `modules/snapper/hierarchy.py`
- Modify: `tests/test_hierarchy.py`

**What it does:** Parse a relation expression string and determine if it is a single-property dependency condition. This is the building block for the fallback hierarchy detection algorithm.

**Target patterns to match:**
- `(SPECIFIED PropertyName) AND (PropertyName IN ('value'))`
- `SPECIFIED PropertyName AND PropertyName IN ('value')`
- With or without outer parentheses, with optional whitespace

**Returns:** `(property_name, value)` tuple if matched, `None` otherwise.

**Must return None for:**
- `$ BAN IN (...)` — article-level restriction
- `* comment text` — developer comment
- `(SPECIFIED A) AND (A IN ('x', 'y'))` — multiple values in IN clause
- `(SPECIFIED A) AND (A IN ('x')) AND (SPECIFIED B) AND ...` — multi-property

- [ ] **Step 1: Write tests**

Add to `tests/test_hierarchy.py`:

```python
from modules.snapper.hierarchy import parse_single_property_condition

def test_parses_standard_form():
    expr = "(SPECIFIED Seat_Fabric_Type) AND (Seat_Fabric_Type IN ('1HA'))"
    result = parse_single_property_condition(expr)
    assert result == ("Seat_Fabric_Type", "1HA")

def test_parses_without_parentheses():
    expr = "SPECIFIED Seat_Fabric_Type AND Seat_Fabric_Type IN ('221')"
    result = parse_single_property_condition(expr)
    assert result == ("Seat_Fabric_Type", "221")

def test_rejects_article_restriction():
    assert parse_single_property_condition("$ BAN IN ('NOCLE100')") is None

def test_rejects_comment():
    assert parse_single_property_condition("* not valid at article X") is None

def test_rejects_multiple_values_in_in_clause():
    expr = "(SPECIFIED Arms) AND (Arms IN ('H', 'J'))"
    assert parse_single_property_condition(expr) is None

def test_rejects_empty():
    assert parse_single_property_condition("") is None

def test_rejects_complex_multi_property():
    expr = "(SPECIFIED A) AND (A IN ('x')) AND (SPECIFIED B) AND (B IN ('y'))"
    assert parse_single_property_condition(expr) is None
```

- [ ] **Step 2–5:** Implement using `re` module, test, commit.

**Suggested implementation sketch:**

```python
import re

_PATTERN = re.compile(
    r"^\(?\s*SPECIFIED\s+(\w+)\s*\)?\s+AND\s+\(?\s*\1\s+IN\s+\(\s*'([^']+)'\s*\)\s*\)?$",
    re.IGNORECASE
)

def parse_single_property_condition(expression: str):
    expr = expression.strip()
    if not expr or expr.startswith("*") or expr.startswith("$"):
        return None
    m = _PATTERN.match(expr)
    if m:
        return (m.group(1), m.group(2))
    return None
```

---

### Task 11: Hierarchy detection algorithm

**Files:**
- Modify: `modules/snapper/hierarchy.py`
- Modify: `tests/test_hierarchy.py`

**Read Section 5 of the design spec in full before implementing this task.**

**What it does:** Given the full range data (from `load_range_data`), detect all parent→child property pairs where every value of the child property is conditioned on exactly one value of the same parent property.

**Algorithm (from design spec Section 5):**

```
FOR each property P in the range:
    values_of_P = all values of P
    IF all values have relation_ids AND
       all those relations parse as single-property conditions AND
       all those conditions reference the same parent property:
        register P as child of that parent property
        build mapping: {parent_value: [child_values]}
```

- [ ] **Step 1: Write test using Cloud data (no fabric_colour_tbl.csv)**

Add to `tests/test_hierarchy.py`:

```python
from modules.snapper.hierarchy import detect_hierarchies
from modules.snapper.reader import load_range_data

CLOUD_DB = r"C:\HermanMillerOFMLSVN\Staging\HermanMiller\_repository\hmx\cloud\ANY\1\db"

def test_detect_hierarchies_finds_fabric_colour_pair():
    data = load_range_data(CLOUD_DB)
    hierarchies = detect_hierarchies(data)
    # hierarchies is a list of {parent: str, child: str, mapping: {parent_val: [child_vals]}}
    pairs = [(h["parent"], h["child"]) for h in hierarchies]
    assert ("Seat_Fabric_Type", "Seat_Fabric_Colour") in pairs

def test_hierarchy_mapping_not_empty():
    data = load_range_data(CLOUD_DB)
    hierarchies = detect_hierarchies(data)
    for h in hierarchies:
        assert len(h["mapping"]) > 0
        for parent_val, child_vals in h["mapping"].items():
            assert len(child_vals) > 0
```

- [ ] **Step 2–5:** Implement, test, commit.

---

### Task 12: Hierarchy API endpoint + UI integration

**Files:**
- Modify: `modules/snapper/routes.py` — add `/api/snapper/hierarchies` endpoint
- Modify: `static/snapper/snapper.js` — show detected hierarchies, link columns, colour mode selector

**What the endpoint returns:**
```json
[
  {
    "parent": "Seat_Fabric_Type",
    "child": "Seat_Fabric_Colour",
    "mapping": {
      "1HA": ["Z301", "Z302", "Z303"],
      "221": ["Z304", "Z305"]
    }
  }
]
```

**UI changes:**
- After loading a range, call the hierarchy endpoint
- Show a collapsible "Detected relationships" section above the dimension columns
- Each relationship shows `ParentProperty → ChildProperty` with a remove button
- Child property columns are hidden from the main dimension columns
- Parent columns get a colour mode toggle: "First only" / "Distribute"
- Update permutation count to exclude hierarchy children from cartesian product

**Colour assignment in generator.py:**
- Add a `fabric_assignments` parameter to `compute_permutations`
- After computing the cartesian product, for each permutation, resolve each hierarchy child value based on the chosen mode
- See design spec Section 7 (Permutation engine) for the distribute counter logic

This task requires coordinated changes across the API, generator, and frontend. Plan it as a single unit with integration testing at the end.

---

## Appendix: Quick Reference

### Running tests
```bash
pytest tests/ -v                          # all tests
pytest tests/test_reader.py -v            # reader only
pytest tests/ -k "not hierarchy" -v       # skip hierarchy tests
```

### Starting the server
```bash
python main.py
# Open: http://localhost:8080
```

### Key file locations
- Design spec: `docs/superpowers/specs/2026-03-22-ofml-testsuite-design.md`
- OCD test data: `C:\HermanMillerOFMLSVN\Staging\HermanMiller\_repository\hmx\cosm\ANY\1\db\`
- Cloud (no fabric table): `...\hmx\cloud\ANY\1\db\`
- Pullman (has fabric table): `...\hmx\pullman\ANY\1\db\`

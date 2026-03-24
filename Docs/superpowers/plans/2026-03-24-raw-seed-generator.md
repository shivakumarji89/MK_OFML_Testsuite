# Raw Seed Generator Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Generate Seed" button to the Snapper page that lets users pick a repo range and instantly download a blank-template OBX — ready to import into pCon and update to populate default configurations.

**Architecture:** A pure backend function `build_raw_seed_obx` builds the OBX XML from OCD article data. Two new FastAPI routes expose range discovery (`GET /ranges`) and file generation (`POST /generate-raw-seed`). A modal overlay in the frontend handles range selection and file download without leaving the page.

**Tech Stack:** Python/FastAPI backend, vanilla JS + Tailwind CSS frontend, pytest for backend tests.

---

## Background: Raw Seed OBX Format

A raw seed is a valid pCon OBX file where each `<bskArticle>` has only the minimum fields needed for pCon to identify and resolve the product. pCon fills in prices, descriptions, and the default varcode when the user runs **Update** after importing.

The minimum required fields (confirmed by user testing against a real pCon installation):
- `<manufacturer id='HM'/>` — manufacturer code from `ocd_article.csv` col[2]
- `<series id='AERON'/>` — series code from `ocd_article.csv` col[3]
- `<artNr type='base'>AER1A13</artNr>` — the base article code
- `<pdInfo ... manufacturerId='HM' seriesId='AERON' progId='@hmx_aeron' ...>` — pCon catalog pointer
- All other fields (prices, descriptions, varcodes) are empty / zero

**`progId` derivation:** Read from `{range_dir}/ANY/1/oam/oam_article2ofml.csv`. Column[2] of the first data row contains the OFML instance path, e.g. `::hmx::aeron::W_AERON`. Strip the last `::` segment (the class name), join the rest with `_`, and prefix `@` → `@hmx_aeron`. This is confirmed against `aeron`, `cosm`, and `ratio_rebuild` — the OAM namespace always matches the folder structure. A `read_prog_id(range_dir)` helper in `reader.py` handles this, with a `@{mfr_folder}_{range_folder}` fallback if the OAM file is absent.

---

## File Map

| File | Change | Responsibility |
|---|---|---|
| `modules/snapper/reader.py` | Modify | Add `read_prog_id()` helper |
| `modules/snapper/generator.py` | Modify | Add `build_raw_seed_obx()` pure function |
| `modules/snapper/routes.py` | Modify | Add `GET /ranges` and `POST /generate-raw-seed` routes |
| `static/snapper/index.html` | Modify | Add "Generate Seed" button + modal overlay HTML |
| `static/snapper/snapper.js` | Modify | Add modal open/close, range fetch, and download JS |
| `tests/test_raw_seed_generator.py` | Create | Unit tests for `build_raw_seed_obx` |
| `tests/test_routes.py` | Modify | Integration tests for the two new routes |

---

## Chunk 1: Backend — read_prog_id + build_raw_seed_obx

### Task 1: read_prog_id helper (TDD)

**Files:**
- Modify: `modules/snapper/reader.py`
- Modify: `tests/test_reader.py`

- [ ] **Step 1: Add the failing test to test_reader.py**

```python
import pytest
from pathlib import Path
from modules.snapper.reader import read_prog_id


def test_read_prog_id_from_oam(tmp_path):
    oam_dir = tmp_path / "hmx" / "aeron" / "ANY" / "1" / "oam"
    oam_dir.mkdir(parents=True)
    (oam_dir / "oam_article2ofml.csv").write_text(
        "AER1A13;::ofml::oi::OiOdbPlElement;::hmx::aeron::W_AERON;\n",
        encoding="utf-8",
    )
    assert read_prog_id(str(tmp_path / "hmx" / "aeron")) == "@hmx_aeron"


def test_read_prog_id_multi_segment_range(tmp_path):
    oam_dir = tmp_path / "hmx" / "ratio_rebuild" / "ANY" / "1" / "oam"
    oam_dir.mkdir(parents=True)
    (oam_dir / "oam_article2ofml.csv").write_text(
        "AZAUS_NEW;::ofml::oi::OiOdbPlElement;::hmx::ratio_rebuild::W_UMBILICAL;\n",
        encoding="utf-8",
    )
    assert read_prog_id(str(tmp_path / "hmx" / "ratio_rebuild")) == "@hmx_ratio_rebuild"


def test_read_prog_id_skips_comment_lines(tmp_path):
    oam_dir = tmp_path / "hmx" / "cosm" / "ANY" / "1" / "oam"
    oam_dir.mkdir(parents=True)
    (oam_dir / "oam_article2ofml.csv").write_text(
        "# comment\nFLC142;::ofml::oi::OiOdbPlElement;::hmx::cosm::W_Work_Chair;\n",
        encoding="utf-8",
    )
    assert read_prog_id(str(tmp_path / "hmx" / "cosm")) == "@hmx_cosm"


def test_read_prog_id_fallback_when_oam_missing(tmp_path):
    # No OAM directory at all → returns None, caller uses folder-name fallback
    assert read_prog_id(str(tmp_path / "hmx" / "aeron")) is None
```

- [ ] **Step 2: Run tests, confirm they fail**

```
pytest tests/test_reader.py -v -k "prog_id"
```

Expected: FAIL — `read_prog_id` not defined.

- [ ] **Step 3: Implement read_prog_id in reader.py**

Append to the end of `modules/snapper/reader.py`:

```python
def read_prog_id(range_dir: str) -> str | None:
    """
    Derive the pCon progId for a range from oam_article2ofml.csv.

    Reads the OFML instance path from column[2] of the first data row, e.g.:
      "::hmx::aeron::W_AERON"  →  "@hmx_aeron"
      "::hmx::ratio_rebuild::W_X"  →  "@hmx_ratio_rebuild"

    The last '::' segment is the class name and is dropped; the rest form the
    namespace joined with '_'.

    Returns None if the OAM file is missing or cannot be parsed.
    """
    oam_path = Path(range_dir) / "ANY" / "1" / "oam" / "oam_article2ofml.csv"
    if not oam_path.exists():
        return None
    try:
        with oam_path.open(encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split(";")
                if len(parts) < 3:
                    continue
                instance_path = parts[2].strip()
                segments = [s for s in instance_path.split("::") if s]
                if len(segments) >= 2:
                    return "@" + "_".join(segments[:-1])
    except OSError:
        pass
    return None
```

- [ ] **Step 4: Run tests, confirm they pass**

```
pytest tests/test_reader.py -v -k "prog_id"
```

Expected: all 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add modules/snapper/reader.py tests/test_reader.py
git commit -m "feat: add read_prog_id helper to extract progId from OAM"
```

---

### Task 2: build_raw_seed_obx unit tests (write first)

**Files:**
- Create: `tests/test_raw_seed_generator.py`

- [ ] **Step 1: Create the test file**

```python
import xml.etree.ElementTree as ET
import pytest
from modules.snapper.generator import build_raw_seed_obx


ARTICLES = [
    {"code": "AER1A13", "manufacturer_code": "HM", "series_code": "AERON"},
    {"code": "AER1B23", "manufacturer_code": "HM", "series_code": "AERON"},
]


def test_produces_one_article_per_input():
    xml = build_raw_seed_obx(ARTICLES, prog_id="@hmx_aeron", mfr_folder="hmx")
    root = ET.fromstring(xml)
    articles = root.findall(".//bskArticle")
    assert len(articles) == 2


def test_article_has_correct_manufacturer_and_series():
    xml = build_raw_seed_obx(ARTICLES[:1], prog_id="@hmx_aeron", mfr_folder="hmx")
    art = ET.fromstring(xml).find(".//bskArticle")
    assert art.find("manufacturer").get("id") == "HM"
    assert art.find("series").get("id") == "AERON"


def test_article_base_artnr_is_set():
    xml = build_raw_seed_obx(ARTICLES[:1], prog_id="@hmx_aeron", mfr_folder="hmx")
    art = ET.fromstring(xml).find(".//bskArticle")
    base = next(e for e in art.findall("artNr") if e.get("type") == "base")
    assert base.text == "AER1A13"


def test_varcode_fields_are_empty():
    xml = build_raw_seed_obx(ARTICLES[:1], prog_id="@hmx_aeron", mfr_folder="hmx")
    art = ET.fromstring(xml).find(".//bskArticle")
    for t in ("final", "varcode", "ofmlvarcode"):
        el = next((e for e in art.findall("artNr") if e.get("type") == t), None)
        assert el is not None, f"Missing artNr type='{t}'"
        assert not (el.text or "").strip(), f"artNr type='{t}' should be empty"


def test_pd_info_prog_id():
    xml = build_raw_seed_obx(ARTICLES[:1], prog_id="@hmx_aeron", mfr_folder="hmx")
    art = ET.fromstring(xml).find(".//bskArticle")
    pd = art.find("pdInfo")
    assert pd.get("progId") == "@hmx_aeron"
    assert pd.get("manufacturerId") == "HM"
    assert pd.get("seriesId") == "AERON"


def test_all_prices_are_zero():
    xml = build_raw_seed_obx(ARTICLES[:1], prog_id="@hmx_aeron", mfr_folder="hmx")
    art = ET.fromstring(xml).find(".//bskArticle")
    for price in art.findall("itemPrice"):
        assert price.get("value") == "0"


def test_doc_calc_entry_matches_basket_id():
    xml = build_raw_seed_obx(ARTICLES[:1], prog_id="@hmx_aeron", mfr_folder="hmx")
    root = ET.fromstring(xml)
    bid = root.find(".//bskArticle").get("basketId")
    calc = root.find("docCalculationChanges")
    assert calc is not None
    entry = calc.find("itemCalculationChanges")
    assert entry.get("id") == bid


def test_catalogue_id_uses_mfr_folder():
    xml = build_raw_seed_obx(ARTICLES[:1], prog_id="@hmx_aeron", mfr_folder="hmx")
    art = ET.fromstring(xml).find(".//bskArticle")
    cat = art.find("catalogInfo")
    assert cat.get("id") == "@hmx_catalogue"
    assert cat.get("artNr") == "AER1A13"
    assert cat.get("varCode") == ""


def test_empty_articles_list():
    xml = build_raw_seed_obx([], prog_id="@hmx_aeron", mfr_folder="hmx")
    root = ET.fromstring(xml)
    assert root.findall(".//bskArticle") == []
```

- [ ] **Step 2: Run tests, confirm they all fail**

```
cd c:\Users\XMAMWU\Projects\MK_OFML_Testsuite
pytest tests/test_raw_seed_generator.py -v
```

Expected: `ImportError` or `NameError` — `build_raw_seed_obx` does not exist yet.

---

### Task 2: Implement build_raw_seed_obx

**Files:**
- Modify: `modules/snapper/generator.py`

- [ ] **Step 1: Add the import and function**

At the top of `generator.py`, add to the existing imports:

```python
from datetime import date
```

At the bottom of `generator.py`, append:

```python
def build_raw_seed_obx(
    articles: list[dict],
    prog_id: str,
    mfr_folder: str,
) -> str:
    """
    Build a 'raw seed' OBX with one bskArticle per article.
    Only manufacturer ID, series ID, and base article code are filled in.
    Everything else is blank/zero — pCon fills in defaults on Update.

    Args:
        articles: list of {code, manufacturer_code, series_code} dicts
        prog_id: pCon catalog identifier, e.g. "@hmx_aeron" — from read_prog_id()
        mfr_folder: repository manufacturer folder name, e.g. "hmx" — for catalogue_id
    """
    today = date.today().isoformat()
    session_id = str(uuid.uuid4())
    catalogue_id = f"@{mfr_folder}_catalogue"

    root = Element("cutBuffer")
    SubElement(root, "state", sessionId=session_id)
    SubElement(root, "versionInfo",
               vendorKey="EasternGraphics",
               appKey="EAI-Server",
               appVersion="4.18.3",
               bskXmlVersion="1.8.10")

    items = SubElement(root, "items")
    basket_ids: list[str] = []

    for art in articles:
        article_code = art["code"]
        mfr_code = art["manufacturer_code"]
        series_code = art["series_code"]

        bid = str(uuid.uuid4())
        basket_ids.append(bid)

        bsk = SubElement(items, "bskArticle",
                         basketId=bid,
                         itemType="BasketAggregate",
                         updateState="UpToDate")

        SubElement(bsk, "manufacturer", id=mfr_code)
        SubElement(bsk, "series", id=series_code)

        base_nr = SubElement(bsk, "artNr", type="base")
        base_nr.text = article_code
        SubElement(bsk, "artNr", type="final", default="1")
        SubElement(bsk, "artNr", type="varcode")
        SubElement(bsk, "artNr", type="ofmlvarcode")

        short_desc = SubElement(bsk, "description", type="short", default="0")
        SubElement(short_desc, "text", lang="en")
        long_desc = SubElement(bsk, "description", type="long", default="1")
        SubElement(long_desc, "text", lang="en")
        feat_desc = SubElement(bsk, "description", type="features", default="0")
        SubElement(feat_desc, "text", lang="en")

        SubElement(bsk, "features")

        SubElement(bsk, "itemPrice", type="purchase", currency="EUR", value="0")
        SubElement(bsk, "itemPrice", type="sale", pd="1", currency="EUR", value="0")
        SubElement(bsk, "itemPrice", type="sale", currency="EUR", value="0")
        SubElement(bsk, "itemPriceComponents", type="purchase")
        SubElement(bsk, "itemPriceComponents", type="sale")
        SubElement(bsk, "priceComponents")
        SubElement(bsk, "taxInfos")

        pd_info = SubElement(bsk, "pdInfo",
                             pdbType="ocd",
                             pkgName="::ofml::oi",
                             manufacturerId=mfr_code,
                             seriesId=series_code,
                             progId=prog_id,
                             region="EURO",
                             salesOnly="false",
                             aggrSalesOnly="false")
        SubElement(pd_info, "ocd", orderUnit="C62")

        SubElement(bsk, "packInfos")
        SubElement(bsk, "priceDate", value=today)
        SubElement(bsk, "artCalc")

        add1 = SubElement(bsk, "addStateCode", type="OiOdbPlElement")
        add1.text = ""
        add2 = SubElement(bsk, "addStateCode", type="ChildProps", aggr="1")
        add2.text = ""

        pvc1 = SubElement(bsk, "propVarCode")
        pvc1.text = ""
        pvc2 = SubElement(bsk, "propVarCode", aggr="1")
        pvc2.text = ""

        SubElement(bsk, "catalogInfo",
                   id=catalogue_id,
                   version="",
                   artNr=article_code,
                   varCode="")

    doc_calc = SubElement(root, "docCalculationChanges", ppName="STDB2B_WBK")
    for bid in basket_ids:
        SubElement(doc_calc, "itemCalculationChanges", id=bid)

    xml_bytes = tostring(root, encoding="unicode")
    return parseString(xml_bytes).toprettyxml(indent="  ")
```

- [ ] **Step 2: Run tests, confirm they pass**

```
pytest tests/test_raw_seed_generator.py -v
```

Expected: all 9 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add modules/snapper/generator.py tests/test_raw_seed_generator.py
git commit -m "feat: add build_raw_seed_obx to generate blank-template OBX from article list"
```

---

## Chunk 2: Backend — New Routes

### Task 3: New route tests

**Files:**
- Modify: `tests/test_routes.py`

- [ ] **Step 1: Add tests for GET /ranges and POST /generate-raw-seed**

Append to the end of `tests/test_routes.py`:

```python
# ── Raw seed routes ─────────────────────────────────────────────────────────────

def _make_mock_repo(tmp_path, mfr="hmx", range_name="aeron", series_code="AERON", mfr_code="HM"):
    """Create a minimal mock repo with one configurable article."""
    db_dir = tmp_path / mfr / range_name / "ANY" / "1" / "db"
    db_dir.mkdir(parents=True)
    (db_dir / "ocd_article.csv").write_text(
        f"AER1A13;C;{mfr_code};{series_code}\nAER1B23;C;{mfr_code};{series_code}\n",
        encoding="utf-8",
    )
    (db_dir / "ocd_artbase.csv").write_text(
        f"AER1A13;{series_code}_NORMAL\nAER1B23;{series_code}_NORMAL\n",
        encoding="utf-8",
    )
    (db_dir / "ocd_property.csv").write_text("", encoding="utf-8")
    (db_dir / "ocd_propertyvalue.csv").write_text("", encoding="utf-8")
    return tmp_path


def test_get_ranges_returns_list(tmp_path):
    _make_mock_repo(tmp_path)
    response = client.get(f"/api/snapper/ranges?repo={tmp_path}")
    assert response.status_code == 200
    data = response.json()
    assert len(data["ranges"]) == 1
    assert data["ranges"][0]["manufacturer"] == "hmx"
    assert data["ranges"][0]["range"] == "aeron"
    assert "db_path" not in data["ranges"][0]  # db_path is internal, not exposed


def test_get_ranges_empty_for_missing_repo(tmp_path):
    response = client.get(f"/api/snapper/ranges?repo={tmp_path / 'nonexistent'}")
    assert response.status_code == 200
    assert response.json()["ranges"] == []


def test_generate_raw_seed_returns_obx(tmp_path):
    _make_mock_repo(tmp_path)
    response = client.post("/api/snapper/generate-raw-seed", json={
        "repo": str(tmp_path),
        "manufacturer": "hmx",
        "range": "aeron",
    })
    assert response.status_code == 200
    assert "xml" in response.headers["content-type"]
    root = ET.fromstring(response.content)
    articles = root.findall(".//bskArticle")
    assert len(articles) == 2
    # Each article has a base artNr
    for art in articles:
        base = next(e for e in art.findall("artNr") if e.get("type") == "base")
        assert base.text in ("AER1A13", "AER1B23")


def test_generate_raw_seed_content_disposition(tmp_path):
    _make_mock_repo(tmp_path)
    response = client.post("/api/snapper/generate-raw-seed", json={
        "repo": str(tmp_path),
        "manufacturer": "hmx",
        "range": "aeron",
    })
    assert response.status_code == 200
    disposition = response.headers.get("content-disposition", "")
    assert "raw_seed_aeron.obx" in disposition


def test_generate_raw_seed_404_for_unknown_range(tmp_path):
    _make_mock_repo(tmp_path)
    response = client.post("/api/snapper/generate-raw-seed", json={
        "repo": str(tmp_path),
        "manufacturer": "hmx",
        "range": "nonexistent",
    })
    assert response.status_code == 404
```

- [ ] **Step 2: Run new tests, confirm they fail**

```
pytest tests/test_routes.py::test_get_ranges_returns_list tests/test_routes.py::test_generate_raw_seed_returns_obx -v
```

Expected: FAIL — routes don't exist yet.

---

### Task 4: Implement the two new routes

**Files:**
- Modify: `modules/snapper/routes.py`

- [ ] **Step 1: Update imports**

In `routes.py`, update the reader import line:

```python
from .reader import discover_ranges, load_range_data, _read_csv, read_prog_id
```

Update the generator import line:

```python
from .generator import compute_permutations, build_obx, build_obx_from_seed, build_obx_from_multi_seed, build_raw_seed_obx, SENTINEL
```

- [ ] **Step 2: Add the GET /ranges route**

Add after the `_build_short_id_relations` helper (before the `/parse-seed` endpoint):

```python
# ── /ranges endpoint ──────────────────────────────────────────────────────────

@router.get("/ranges")
def get_ranges(repo: str):
    """Return the list of valid ranges found in the given repo path."""
    ranges = discover_ranges(repo)
    # Strip db_path — it's an internal server-side detail
    return {
        "ranges": [{"manufacturer": r["manufacturer"], "range": r["range"]} for r in ranges]
    }
```

- [ ] **Step 3: Add the POST /generate-raw-seed route**

Add a Pydantic model and route. Place after the `get_ranges` route:

```python
# ── /generate-raw-seed endpoint ───────────────────────────────────────────────

class RawSeedRequest(BaseModel):
    repo: str
    manufacturer: str
    range: str


@router.post("/generate-raw-seed")
def generate_raw_seed(req: RawSeedRequest):
    """
    Generate a raw seed OBX for the given range.
    The OBX contains one bskArticle per configurable article with blank
    configuration — pCon populates defaults when the user runs Update.
    """
    ranges = discover_ranges(req.repo)
    matched = next(
        (r for r in ranges
         if r["manufacturer"] == req.manufacturer and r["range"] == req.range),
        None,
    )
    if matched is None:
        raise HTTPException(
            status_code=404,
            detail=f"Range '{req.range}' not found for manufacturer '{req.manufacturer}' in '{req.repo}'",
        )

    try:
        range_data = load_range_data(matched["db_path"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load range data: {e}")

    articles = range_data["articles"]
    if not articles:
        raise HTTPException(status_code=400, detail="No configurable articles found in this range")

    # db_path is "{range_dir}/ANY/1/db" — go up 3 levels to get range_dir
    range_dir = str(Path(matched["db_path"]).parent.parent.parent)
    prog_id = read_prog_id(range_dir) or f"@{req.manufacturer}_{req.range}"

    xml_content = build_raw_seed_obx(
        articles=articles,
        prog_id=prog_id,
        mfr_folder=req.manufacturer,
    )

    filename = f"raw_seed_{req.range}.obx"
    return Response(
        content=xml_content,
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
```

- [ ] **Step 4: Run all new route tests**

```
pytest tests/test_routes.py -v -k "raw_seed or ranges"
```

Expected: all 5 new tests PASS.

- [ ] **Step 5: Run full test suite to check for regressions**

```
pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add modules/snapper/routes.py tests/test_routes.py
git commit -m "feat: add GET /ranges and POST /generate-raw-seed endpoints"
```

---

## Chunk 3: Frontend

### Task 5: Add modal HTML and Generate Seed button to index.html

**Files:**
- Modify: `static/snapper/index.html`

Frontend changes have no automated tests — verify manually by running the app and checking the UI.

- [ ] **Step 1: Add the Generate Seed button next to the section heading**

In `index.html`, replace:

```html
      <h2 class="font-semibold text-gray-700 mb-3">Upload Seed OBX</h2>
```

With:

```html
      <div class="flex items-center justify-between mb-3">
        <h2 class="font-semibold text-gray-700">Upload Seed OBX</h2>
        <button id="generateSeedBtn"
          class="text-sm text-blue-600 border border-blue-300 rounded px-3 py-1 hover:bg-blue-50 transition-colors">
          Generate Seed…
        </button>
      </div>
```

- [ ] **Step 2: Add the modal overlay HTML**

Insert the modal directly before the closing `</body>` tag (before `<script src="/static/snapper/snapper.js"></script>`):

```html
  <!-- Raw Seed Generator modal -->
  <div id="rawSeedModal"
    class="fixed inset-0 bg-black bg-opacity-40 z-50 hidden flex items-center justify-center">
    <div class="bg-white rounded-lg shadow-xl p-6 w-96 max-w-full mx-4">
      <h2 class="font-semibold text-gray-800 mb-2">Generate Raw Seed</h2>
      <p class="text-sm text-gray-500 mb-4">
        Select a product range. The generated OBX contains all base articles with blank
        configurations. Import into pCon and run <strong>Update</strong> to populate defaults,
        then use it as your seed above.
      </p>
      <div class="mb-4">
        <label class="block text-xs text-gray-500 mb-1">Product range</label>
        <select id="rawSeedRangeSelect" class="border rounded px-2 py-1.5 text-sm w-full">
          <option value="">Loading…</option>
        </select>
      </div>
      <div id="rawSeedError" class="text-sm text-red-600 mb-3 hidden"></div>
      <div class="flex justify-end gap-2">
        <button id="rawSeedCancelBtn"
          class="px-3 py-1.5 rounded text-sm border border-gray-300 hover:bg-gray-50">
          Cancel
        </button>
        <button id="rawSeedGenerateBtn"
          class="px-4 py-1.5 rounded text-sm bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50"
          disabled>
          Generate &amp; Download
        </button>
      </div>
    </div>
  </div>
```

---

### Task 6: Add Generate Seed JS to snapper.js

**Files:**
- Modify: `static/snapper/snapper.js`

- [ ] **Step 1: Add DOM refs and event listeners**

Append to the end of `snapper.js`:

```javascript
// ── Raw Seed Generator ─────────────────────────────────────────────────────────
const rawSeedModal  = document.getElementById('rawSeedModal');
const rawSeedSelect = document.getElementById('rawSeedRangeSelect');
const rawSeedError  = document.getElementById('rawSeedError');
const rawSeedGenBtn = document.getElementById('rawSeedGenerateBtn');

document.getElementById('generateSeedBtn').addEventListener('click', openRawSeedModal);
document.getElementById('rawSeedCancelBtn').addEventListener('click', closeRawSeedModal);
// Click outside the card to dismiss
rawSeedModal.addEventListener('click', (e) => { if (e.target === rawSeedModal) closeRawSeedModal(); });
rawSeedSelect.addEventListener('change', () => {
  rawSeedGenBtn.disabled = !rawSeedSelect.value;
});
rawSeedGenBtn.addEventListener('click', downloadRawSeed);

async function openRawSeedModal() {
  const repo = repoPathInput.value.trim();
  if (!repo) {
    alert('Please enter the repository path first.');
    return;
  }

  // Reset state
  rawSeedSelect.innerHTML = '<option value="">Loading ranges…</option>';
  rawSeedGenBtn.disabled = true;
  rawSeedError.classList.add('hidden');
  rawSeedModal.classList.remove('hidden');

  try {
    const resp = await fetch(`/api/snapper/ranges?repo=${encodeURIComponent(repo)}`);
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.detail || resp.statusText);
    }
    const { ranges } = await resp.json();
    _populateRangeSelect(ranges);
  } catch (err) {
    rawSeedSelect.innerHTML = '<option value="">Failed to load ranges</option>';
    _showRawSeedError(`Could not load ranges: ${err.message}`);
  }
}

function _populateRangeSelect(ranges) {
  if (!ranges.length) {
    rawSeedSelect.innerHTML = '<option value="">No ranges found in this repository</option>';
    return;
  }
  // Group by manufacturer using optgroup
  const byMfr = {};
  for (const r of ranges) {
    (byMfr[r.manufacturer] ??= []).push(r);
  }
  rawSeedSelect.innerHTML = '<option value="">Select a range…</option>';
  for (const [mfr, rlist] of Object.entries(byMfr)) {
    const grp = document.createElement('optgroup');
    grp.label = mfr;
    for (const r of rlist) {
      const opt = document.createElement('option');
      opt.value = JSON.stringify({ manufacturer: r.manufacturer, range: r.range });
      opt.textContent = r.range;
      grp.appendChild(opt);
    }
    rawSeedSelect.appendChild(grp);
  }
}

async function downloadRawSeed() {
  const repo = repoPathInput.value.trim();
  const selection = rawSeedSelect.value;
  if (!selection) return;

  const { manufacturer, range } = JSON.parse(selection);

  rawSeedGenBtn.disabled = true;
  rawSeedGenBtn.textContent = 'Generating…';
  rawSeedError.classList.add('hidden');

  try {
    const resp = await fetch('/api/snapper/generate-raw-seed', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ repo, manufacturer, range }),
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.detail || resp.statusText);
    }
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `raw_seed_${range}.obx`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    closeRawSeedModal();
  } catch (err) {
    _showRawSeedError(`Generation failed: ${err.message}`);
  } finally {
    rawSeedGenBtn.disabled = false;
    rawSeedGenBtn.textContent = 'Generate \u0026 Download';
  }
}

function closeRawSeedModal() {
  rawSeedModal.classList.add('hidden');
}

function _showRawSeedError(msg) {
  rawSeedError.textContent = msg;
  rawSeedError.classList.remove('hidden');
}
```

- [ ] **Step 2: Manual smoke test**

1. Run `python main.py`
2. Open `http://localhost:8080/snapper/`
3. Enter the repository path in the header field
4. Click **Generate Seed…** — modal should open and load the range dropdown
5. Select a range, click **Generate & Download** — OBX file should download
6. Verify OBX opens correctly in a text editor: should have one `<bskArticle>` per article with empty varcodes and zero prices
7. Click outside the modal or Cancel — modal should close

- [ ] **Step 3: Commit**

```bash
git add static/snapper/index.html static/snapper/snapper.js
git commit -m "feat: add Generate Seed modal for raw OBX generation from repo range"
```

---

## Chunk 4: Final validation

- [ ] **Run full test suite**

```
pytest tests/ -v
```

Expected: all tests PASS, no regressions.

- [ ] **End-to-end check with real repo**

1. Open the Snapper page, enter the real repo path
2. Click **Generate Seed…**, pick `hmx / cloud`
3. Verify the download contains one article per row in `ocd_article.csv` (configurable only)
4. Import the OBX into pCon, run Update, confirm it resolves correctly
5. Upload the updated file as a seed — confirm it parses normally

- [ ] **Final commit if any tweaks made during E2E**

```bash
git add -p
git commit -m "fix: address issues found during E2E raw seed testing"
```

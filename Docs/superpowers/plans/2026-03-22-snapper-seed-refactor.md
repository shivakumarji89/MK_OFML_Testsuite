# Snapper Seed-Based Refactor Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the Snapper Generator from range-browser mode to seed-OBX mode: user uploads a pCon-exported OBX, the system extracts the article's properties and correct class prefixes from the varcode, looks up valid values from OCD, detects parent-child hierarchies (fabric type → colour), and presents a per-article configuration UI with a queue system.

**Architecture:** seed_parser.py extracts article/property/class data from an uploaded OBX. hierarchy.py detects parent-child property pairs from OCD relation data, scoped only to the seed's properties. Routes.py provides /parse-seed (POST multipart) and /generate (POST JSON). Frontend: seed upload → property columns → queue → generate. Hierarchy pairs shown as linked columns with First/Distribute colour mode. Per-article configuration — one article at a time, add to queue, repeat.

**Tech Stack:** Python 3.x, FastAPI, uvicorn, pytest, xml.etree.ElementTree (stdlib). Frontend: HTML5 + vanilla JS + Tailwind CSS CDN.

**Read before starting:** `CLAUDE.md` and `docs/superpowers/specs/2026-03-22-ofml-testsuite-design.md`

**OFML repo for testing:** `C:\HermanMillerOFMLSVN\Staging\HermanMiller\_repository`
Test range: `hmx/cloud` — OCD files at `{repo}/hmx/cloud/ANY/1/db/`

---

## Key architectural note: Relation ID lookup chain

Before implementing, understand this data model detail — it affects hierarchy.py significantly:

`ocd_propertyvalue.csv` stores a **short** integer relation ID in column 4 (e.g. `22205`). `ocd_relation.csv` uses **18-character zero-padded** IDs as keys (e.g. `000000000000570841`). These do not match directly.

The bridge is `ocd_relationobj.csv`: column 0 = short ID, column 2 = long ID. To resolve a value's condition expression:

```
value.relation_id (short, e.g. "22205")
  → ocd_relationobj: row where col[0] == "22205" → col[2] = "000000000000570841"
  → ocd_relation: rows where col[0] == "000000000000570841" → concatenated expression
```

`reader.py`'s existing `load_range_data` returns `relations` keyed by long IDs, but `values[i]['relation_id']` is the short ID. They cannot be used together directly. The `/parse-seed` route must build a `{short_id: expression}` map itself by joining `ocd_relationobj` and `ocd_relation`. This pre-built map is then passed to `detect_hierarchy`.

---

## Chunk 1: Backend — seed_parser.py + tests

### Task 1: Implement `modules/snapper/seed_parser.py`

**File:** `C:\Users\XMAMWU\Projects\MK_OFML_Testsuite\modules\snapper\seed_parser.py`

**Purpose:** Parse an OBX XML string (the content of a pCon-exported file) and return structured seed data.

**What to parse:**
- `<manufacturer id='...'>` → `manufacturer`
- `<series id='...'>` → `series`
- `<artNr type='base'>...</artNr>` → `article`
- `<artNr type='ofmlvarcode'>...</artNr>` → parse varcode segments

Varcode format: `ArticleClass.PropName=Value;ArticleClass2.PropName2=Value2;...`
Each semicolon-separated segment is split on `.` (first dot only) to get `article_class` and the remainder split on `=` to get `name` and `seed_value`.

Only parse the **first** `<bskArticle>` element — a seed file should contain one item.

- [ ] **Step 1: Create `modules/snapper/seed_parser.py`**

```python
import xml.etree.ElementTree as ET


class SeedParseError(ValueError):
    """Raised when the OBX XML is malformed or missing required fields."""
    pass


def parse_seed(xml_string: str) -> dict:
    """
    Parse a pCon OBX XML string and extract seed data from the first bskArticle.

    Args:
        xml_string: Full content of an OBX file as a string.

    Returns:
        {
            "article": str,           # base article code, e.g. "NOCLE4"
            "manufacturer": str,      # e.g. "HM"
            "series": str,            # e.g. "CLOUD"
            "properties": [
                {
                    "name": str,          # property name, e.g. "Type"
                    "article_class": str, # e.g. "CLOUD_ATTR_ARM_CHAIR"
                    "seed_value": str,    # the value from the seed OBX
                },
                ...
            ]
        }

    Raises:
        SeedParseError: if the XML cannot be parsed, no bskArticle is found,
                        or required fields (manufacturer, series, base artNr,
                        ofmlvarcode artNr) are missing.
    """
    try:
        root = ET.fromstring(xml_string)
    except ET.ParseError as e:
        raise SeedParseError(f"Invalid XML: {e}") from e

    article_el = root.find(".//bskArticle")
    if article_el is None:
        raise SeedParseError("No <bskArticle> element found in OBX")

    mfr_el = article_el.find("manufacturer")
    if mfr_el is None or not mfr_el.get("id"):
        raise SeedParseError("Missing <manufacturer id='...'> in bskArticle")
    manufacturer = mfr_el.get("id")

    series_el = article_el.find("series")
    if series_el is None or not series_el.get("id"):
        raise SeedParseError("Missing <series id='...'> in bskArticle")
    series = series_el.get("id")

    article_code = None
    varcode_str = None
    for artnr in article_el.findall("artNr"):
        t = artnr.get("type", "")
        if t == "base":
            article_code = (artnr.text or "").strip()
        elif t == "ofmlvarcode":
            varcode_str = (artnr.text or "").strip()

    if not article_code:
        raise SeedParseError("Missing <artNr type='base'> in bskArticle")
    if not varcode_str:
        raise SeedParseError("Missing <artNr type='ofmlvarcode'> in bskArticle")

    properties = _parse_varcode(varcode_str)

    return {
        "article": article_code,
        "manufacturer": manufacturer,
        "series": series,
        "properties": properties,
    }


def _parse_varcode(varcode_str: str) -> list[dict]:
    """
    Parse an OFML varcode string into a list of property dicts.

    Example input: "CLOUD_ATTR_ARM_CHAIR.Type=10;CLOUD_OPT.Base_Finish=R00"
    Example output:
        [
            {"name": "Type", "article_class": "CLOUD_ATTR_ARM_CHAIR", "seed_value": "10"},
            {"name": "Base_Finish", "article_class": "CLOUD_OPT", "seed_value": "R00"},
        ]

    Segments that do not contain '.' or '=' are skipped silently.
    """
    properties = []
    for segment in varcode_str.split(";"):
        segment = segment.strip()
        if not segment:
            continue
        dot_idx = segment.find(".")
        if dot_idx == -1:
            continue
        article_class = segment[:dot_idx]
        remainder = segment[dot_idx + 1:]
        eq_idx = remainder.find("=")
        if eq_idx == -1:
            continue
        prop_name = remainder[:eq_idx]
        seed_value = remainder[eq_idx + 1:]
        if article_class and prop_name:
            properties.append({
                "name": prop_name,
                "article_class": article_class,
                "seed_value": seed_value,
            })
    return properties
```

- [ ] **Step 2: Verify the file is importable**

```bash
cd C:\Users\XMAMWU\Projects\MK_OFML_Testsuite
python -c "from modules.snapper.seed_parser import parse_seed, SeedParseError; print('OK')"
```

Expected output: `OK`

---

### Task 2: Write `tests/test_seed_parser.py`

**File:** `C:\Users\XMAMWU\Projects\MK_OFML_Testsuite\tests\test_seed_parser.py`

**Approach:** TDD — write the tests first (they will fail on import if seed_parser.py doesn't exist yet), then implement Task 1. All fixtures are inline XML strings — no file I/O.

- [ ] **Step 3: Create `tests/test_seed_parser.py`**

```python
import pytest
from modules.snapper.seed_parser import parse_seed, SeedParseError

# ── Fixtures ──────────────────────────────────────────────────────────────────

CLOUD_SEED_XML = """<?xml version='1.0'?>
<cutBuffer>
  <state sessionId='169f45a8-041c-437f-b009-5600cecc5ca9'/>
  <versionInfo vendorKey='EasternGraphics' appKey='EAI-Server' appVersion='4.18.3' bskXmlVersion='1.8.10'/>
  <items>
    <bskArticle basketId='a1bab025-ebec-4652-841d-83918768adfc' itemType='BasketArticle' updateState='UpToDate'>
      <manufacturer id='HM'/>
      <series id='CLOUD'/>
      <artNr type='base'>NOCLE4</artNr>
      <artNr type='ofmlvarcode'>CLOUD_ATTR_ARM_CHAIR.Type=10;CLOUD_OPT.Base_Finish=R00;CLOUD_OPT.Shell_Fabric_Type=1HA;CLOUD_OPT.Shell_Fabric_Colour=1HA02;CLOUD_OPT.Seat_Fabric_Type=1HA;CLOUD_OPT.Seat_Fabric_Colour=1HA01</artNr>
    </bskArticle>
  </items>
</cutBuffer>"""

MINIMAL_SEED_XML = """<cutBuffer>
  <items>
    <bskArticle>
      <manufacturer id='HM'/>
      <series id='COSM'/>
      <artNr type='base'>FLC142</artNr>
      <artNr type='ofmlvarcode'>COSM_NORMAL.Arms=N;COSM_NORMAL.Back_Height=4</artNr>
    </bskArticle>
  </items>
</cutBuffer>"""

MULTI_ARTICLE_XML = """<cutBuffer>
  <items>
    <bskArticle>
      <manufacturer id='HM'/>
      <series id='CLOUD'/>
      <artNr type='base'>NOCLE4</artNr>
      <artNr type='ofmlvarcode'>CLOUD_OPT.Base_Finish=R00</artNr>
    </bskArticle>
    <bskArticle>
      <manufacturer id='HM'/>
      <series id='CLOUD'/>
      <artNr type='base'>NOCLE5</artNr>
      <artNr type='ofmlvarcode'>CLOUD_OPT.Base_Finish=SL</artNr>
    </bskArticle>
  </items>
</cutBuffer>"""


# ── Happy path tests ──────────────────────────────────────────────────────────

def test_parse_seed_returns_article_code():
    result = parse_seed(CLOUD_SEED_XML)
    assert result["article"] == "NOCLE4"


def test_parse_seed_returns_manufacturer():
    result = parse_seed(CLOUD_SEED_XML)
    assert result["manufacturer"] == "HM"


def test_parse_seed_returns_series():
    result = parse_seed(CLOUD_SEED_XML)
    assert result["series"] == "CLOUD"


def test_parse_seed_returns_properties_list():
    result = parse_seed(CLOUD_SEED_XML)
    assert isinstance(result["properties"], list)
    assert len(result["properties"]) == 6


def test_parse_seed_first_property_type():
    result = parse_seed(CLOUD_SEED_XML)
    first = result["properties"][0]
    assert first["name"] == "Type"
    assert first["article_class"] == "CLOUD_ATTR_ARM_CHAIR"
    assert first["seed_value"] == "10"


def test_parse_seed_second_property_base_finish():
    result = parse_seed(CLOUD_SEED_XML)
    second = result["properties"][1]
    assert second["name"] == "Base_Finish"
    assert second["article_class"] == "CLOUD_OPT"
    assert second["seed_value"] == "R00"


def test_parse_seed_fabric_type_and_colour():
    result = parse_seed(CLOUD_SEED_XML)
    props_by_name = {p["name"]: p for p in result["properties"]}
    assert "Shell_Fabric_Type" in props_by_name
    assert props_by_name["Shell_Fabric_Type"]["seed_value"] == "1HA"
    assert "Shell_Fabric_Colour" in props_by_name
    assert props_by_name["Shell_Fabric_Colour"]["seed_value"] == "1HA02"


def test_parse_seed_uses_first_article_only():
    """When multiple bskArticle elements are present, only the first is used."""
    result = parse_seed(MULTI_ARTICLE_XML)
    assert result["article"] == "NOCLE4"
    assert len(result["properties"]) == 1
    assert result["properties"][0]["seed_value"] == "R00"


def test_parse_seed_minimal_xml():
    result = parse_seed(MINIMAL_SEED_XML)
    assert result["article"] == "FLC142"
    assert result["series"] == "COSM"
    assert len(result["properties"]) == 2
    assert result["properties"][0]["name"] == "Arms"
    assert result["properties"][1]["name"] == "Back_Height"


# ── Error cases ───────────────────────────────────────────────────────────────

def test_parse_seed_invalid_xml_raises():
    with pytest.raises(SeedParseError, match="Invalid XML"):
        parse_seed("not xml at all <<<")


def test_parse_seed_no_bsk_article_raises():
    xml = "<cutBuffer><items></items></cutBuffer>"
    with pytest.raises(SeedParseError, match="No <bskArticle>"):
        parse_seed(xml)


def test_parse_seed_missing_manufacturer_raises():
    xml = """<cutBuffer><items><bskArticle>
      <series id='CLOUD'/>
      <artNr type='base'>NOCLE4</artNr>
      <artNr type='ofmlvarcode'>CLOUD_OPT.Base_Finish=R00</artNr>
    </bskArticle></items></cutBuffer>"""
    with pytest.raises(SeedParseError, match="manufacturer"):
        parse_seed(xml)


def test_parse_seed_missing_series_raises():
    xml = """<cutBuffer><items><bskArticle>
      <manufacturer id='HM'/>
      <artNr type='base'>NOCLE4</artNr>
      <artNr type='ofmlvarcode'>CLOUD_OPT.Base_Finish=R00</artNr>
    </bskArticle></items></cutBuffer>"""
    with pytest.raises(SeedParseError, match="series"):
        parse_seed(xml)


def test_parse_seed_missing_base_artnr_raises():
    xml = """<cutBuffer><items><bskArticle>
      <manufacturer id='HM'/>
      <series id='CLOUD'/>
      <artNr type='ofmlvarcode'>CLOUD_OPT.Base_Finish=R00</artNr>
    </bskArticle></items></cutBuffer>"""
    with pytest.raises(SeedParseError, match="base"):
        parse_seed(xml)


def test_parse_seed_missing_varcode_raises():
    xml = """<cutBuffer><items><bskArticle>
      <manufacturer id='HM'/>
      <series id='CLOUD'/>
      <artNr type='base'>NOCLE4</artNr>
    </bskArticle></items></cutBuffer>"""
    with pytest.raises(SeedParseError, match="ofmlvarcode"):
        parse_seed(xml)


# ── Varcode parsing edge cases ─────────────────────────────────────────────────

def test_parse_seed_skips_malformed_varcode_segments():
    """Segments without '.' or '=' are silently skipped."""
    xml = """<cutBuffer><items><bskArticle>
      <manufacturer id='HM'/>
      <series id='CLOUD'/>
      <artNr type='base'>NOCLE4</artNr>
      <artNr type='ofmlvarcode'>CLOUD_OPT.Base_Finish=R00;MALFORMED;ALSO_BAD</artNr>
    </bskArticle></items></cutBuffer>"""
    result = parse_seed(xml)
    assert len(result["properties"]) == 1
    assert result["properties"][0]["name"] == "Base_Finish"
```

- [ ] **Step 4: Run failing tests to confirm they are set up correctly**

Before implementing seed_parser.py, run to confirm tests exist:
```bash
cd C:\Users\XMAMWU\Projects\MK_OFML_Testsuite
python -m pytest tests/test_seed_parser.py -v 2>&1 | head -30
```

Expected: tests either fail with ImportError (if seed_parser.py does not exist yet) or pass after implementation.

- [ ] **Step 5: Run tests after implementing seed_parser.py**

```bash
cd C:\Users\XMAMWU\Projects\MK_OFML_Testsuite
python -m pytest tests/test_seed_parser.py -v
```

Expected: all 18 tests pass.

---

## Chunk 2: Backend — hierarchy.py + tests

### Task 3: Implement `modules/snapper/hierarchy.py`

**File:** `C:\Users\XMAMWU\Projects\MK_OFML_Testsuite\modules\snapper\hierarchy.py`

**Purpose:** Given a list of property names (from the seed), the full `values` list from `load_range_data`, and a `{short_rel_id: expression}` mapping, detect which property pairs form parent-child hierarchies.

**Critical design note:** The `relations` dict returned by `load_range_data` uses 18-character zero-padded long IDs as keys (e.g. `"000000000000570841"`). The `values` list has `relation_id` as the short integer string (e.g. `"22205"`). These do not match. The caller (the `/parse-seed` route) must build a `{short_id: expression}` dict by joining `ocd_relationobj.csv` (short→long bridge) with `ocd_relation.csv` (long→expression). This pre-resolved dict is passed in as `relations` to `detect_hierarchy`.

**Detection algorithm** (scoped to seed's property names only):

1. Filter `values` to only those where `property_name` is in `property_names`.
2. For each property name in `property_names`:
   a. Collect all its values from filtered list.
   b. If zero values: skip.
   c. For each value, if `relation_id` is empty or `"0"`: that value is unconditioned.
   d. Build `conditions = {value_code: expression}` for each value that has a non-zero relation_id. Look up expression from `relations[relation_id]`.
   e. If `len(conditions) != len(all_values_for_prop)`: not all values are conditioned → not a child → skip.
   f. Parse each expression with `_parse_single_property_condition`. If any returns `None`: not hierarchical → skip.
   g. Collect all parent names. If exactly one unique parent name and that parent is also in `property_names`: register hierarchy.
3. Return list of `{parent, child, mapping}` dicts.

**`_parse_single_property_condition(expression)` rules:**
- Strip leading/trailing whitespace.
- Return `None` if starts with `$` or `*` (article-level or comment).
- Match pattern: `(SPECIFIED PropName) AND (PropName IN ('val'))` or without outer parens.
- The `IN (...)` clause must contain exactly **one** value (no comma inside).
- Returns `(parent_prop_name, parent_value)` tuple or `None`.

- [ ] **Step 6: Create `modules/snapper/hierarchy.py`**

```python
import re


# Matches: (SPECIFIED PropName) AND (PropName IN ('val'))
# Also handles without outer parens: SPECIFIED PropName AND PropName IN ('val')
_CONDITION_PATTERN = re.compile(
    r"^\(?SPECIFIED\s+(\w+)\)?\s+AND\s+\(?\1\s+IN\s+\('([^']+)'\)\)?$",
    re.IGNORECASE,
)


def detect_hierarchy(
    property_names: list[str],
    values: list[dict],
    relations: dict[str, str],
) -> list[dict]:
    """
    Detect parent-child property pairs among a set of property names.

    Args:
        property_names: Names of properties to consider (from the seed).
            Only these properties are examined as potential children or parents.
        values: Full list of value dicts from load_range_data (all properties in range).
            Each dict has keys: property_name, value, relation_id, article_class, ...
        relations: {short_relation_id: expression_string}
            NOTE: This must use SHORT relation IDs (matching values[i]['relation_id']),
            NOT the long zero-padded IDs from ocd_relation.csv.
            The caller (/parse-seed route) builds this by joining ocd_relationobj.csv
            (short→long bridge) with ocd_relation.csv (long→expression).

    Returns:
        List of hierarchy dicts:
        [
            {
                "parent": "Shell_Fabric_Type",
                "child": "Shell_Fabric_Colour",
                "mapping": {
                    "1HA": ["1HA01", "1HA02", "1HA03"],
                    "2AB": ["2AB01", "2AB02"],
                }
            },
            ...
        ]
        Properties that are not hierarchically linked appear in neither list.
        A property can only be a child (not simultaneously a parent and a child
        in the same returned hierarchy, though multi-level hierarchies are not
        currently supported).
    """
    prop_name_set = set(property_names)

    # Group values by property_name (only for seed properties)
    prop_values: dict[str, list[dict]] = {}
    for v in values:
        pname = v["property_name"]
        if pname in prop_name_set:
            prop_values.setdefault(pname, []).append(v)

    hierarchies = []

    for prop_name in property_names:
        all_vals = prop_values.get(prop_name, [])
        if not all_vals:
            continue

        # Build conditions map: value_code -> expression (only for values with a relation)
        conditions: dict[str, str] = {}
        for v in all_vals:
            rel_id = v.get("relation_id", "")
            if rel_id and rel_id != "0":
                expr = relations.get(rel_id)
                if expr is not None:
                    conditions[v["value"]] = expr

        # All values must be conditioned for this property to be a child
        if len(conditions) != len(all_vals):
            continue

        # Parse each condition — all must reference the same single parent property
        parent_refs: set[str] = set()
        parent_value_map: dict[str, list[str]] = {}
        valid = True

        for value_code, expression in conditions.items():
            parsed = _parse_single_property_condition(expression)
            if parsed is None:
                valid = False
                break
            parent_name, parent_val = parsed
            parent_refs.add(parent_name)
            parent_value_map.setdefault(parent_val, []).append(value_code)

        if not valid:
            continue
        if len(parent_refs) != 1:
            continue

        parent_property = next(iter(parent_refs))

        # Parent must also be in the seed's property set
        if parent_property not in prop_name_set:
            continue

        hierarchies.append({
            "parent": parent_property,
            "child": prop_name,
            "mapping": parent_value_map,
        })

    return hierarchies


def _parse_single_property_condition(expression: str) -> tuple[str, str] | None:
    """
    Parse a condition expression that references exactly one property and one value.

    Accepted forms:
        (SPECIFIED PropName) AND (PropName IN ('val'))
        SPECIFIED PropName AND PropName IN ('val')

    Returns:
        (parent_property_name, parent_value) if the expression matches exactly.
    Returns None for:
        - Article-level conditions (starting with '$')
        - Comment lines (starting with '*')
        - Expressions referencing multiple properties or multiple IN values
        - Any expression that does not match the expected pattern
    """
    expr = expression.strip()

    if not expr:
        return None
    if expr.startswith("$") or expr.startswith("*"):
        return None

    m = _CONDITION_PATTERN.match(expr)
    if m:
        return (m.group(1), m.group(2))

    return None
```

- [ ] **Step 7: Verify the file is importable**

```bash
cd C:\Users\XMAMWU\Projects\MK_OFML_Testsuite
python -c "from modules.snapper.hierarchy import detect_hierarchy; print('OK')"
```

Expected: `OK`

---

### Task 4: Write `tests/test_hierarchy.py`

**File:** `C:\Users\XMAMWU\Projects\MK_OFML_Testsuite\tests\test_hierarchy.py`

All fixtures use inline dicts — no file I/O. The `relations` dict passed to `detect_hierarchy` uses short string IDs as keys (matching `value['relation_id']`), since the caller resolves the short-to-long mapping before calling this function.

- [ ] **Step 8: Create `tests/test_hierarchy.py`**

```python
import pytest
from modules.snapper.hierarchy import detect_hierarchy, _parse_single_property_condition


# ── Inline fixture data ────────────────────────────────────────────────────────

def _make_value(prop_name, value_code, relation_id="0", article_class="CLOUD_OPT"):
    return {
        "article_class": article_class,
        "property_name": prop_name,
        "value": value_code,
        "relation_id": relation_id,
        "sort_order": 1,
        "is_default": False,
        "label": value_code,
    }


# Shell_Fabric_Type: two values, no conditions (always available)
FABRIC_TYPE_VALUES = [
    _make_value("Shell_Fabric_Type", "1HA", relation_id="0"),
    _make_value("Shell_Fabric_Type", "2AB", relation_id="0"),
]

# Shell_Fabric_Colour: four values, each conditioned on one Shell_Fabric_Type value
FABRIC_COLOUR_VALUES = [
    _make_value("Shell_Fabric_Colour", "1HA01", relation_id="101"),
    _make_value("Shell_Fabric_Colour", "1HA02", relation_id="102"),
    _make_value("Shell_Fabric_Colour", "2AB01", relation_id="201"),
    _make_value("Shell_Fabric_Colour", "2AB02", relation_id="202"),
]

# Pre-resolved relations: short_id -> expression (as the /parse-seed route would build)
FABRIC_RELATIONS = {
    "101": "(SPECIFIED Shell_Fabric_Type) AND (Shell_Fabric_Type IN ('1HA'))",
    "102": "(SPECIFIED Shell_Fabric_Type) AND (Shell_Fabric_Type IN ('1HA'))",
    "201": "(SPECIFIED Shell_Fabric_Type) AND (Shell_Fabric_Type IN ('2AB'))",
    "202": "(SPECIFIED Shell_Fabric_Type) AND (Shell_Fabric_Type IN ('2AB'))",
}

ALL_VALUES = FABRIC_TYPE_VALUES + FABRIC_COLOUR_VALUES


# ── detect_hierarchy tests ────────────────────────────────────────────────────

def test_detect_hierarchy_returns_list():
    result = detect_hierarchy(
        ["Shell_Fabric_Type", "Shell_Fabric_Colour"],
        ALL_VALUES,
        FABRIC_RELATIONS,
    )
    assert isinstance(result, list)


def test_detect_hierarchy_finds_fabric_pair():
    result = detect_hierarchy(
        ["Shell_Fabric_Type", "Shell_Fabric_Colour"],
        ALL_VALUES,
        FABRIC_RELATIONS,
    )
    assert len(result) == 1
    h = result[0]
    assert h["parent"] == "Shell_Fabric_Type"
    assert h["child"] == "Shell_Fabric_Colour"


def test_detect_hierarchy_mapping_has_correct_children():
    result = detect_hierarchy(
        ["Shell_Fabric_Type", "Shell_Fabric_Colour"],
        ALL_VALUES,
        FABRIC_RELATIONS,
    )
    mapping = result[0]["mapping"]
    assert set(mapping["1HA"]) == {"1HA01", "1HA02"}
    assert set(mapping["2AB"]) == {"2AB01", "2AB02"}


def test_detect_hierarchy_parent_not_in_seed_returns_empty():
    """If parent property is not in property_names, no hierarchy is returned."""
    result = detect_hierarchy(
        ["Shell_Fabric_Colour"],  # parent (Shell_Fabric_Type) excluded
        ALL_VALUES,
        FABRIC_RELATIONS,
    )
    assert result == []


def test_detect_hierarchy_no_conditions_returns_empty():
    """Properties with no relation_ids are never children."""
    values = [
        _make_value("Arms", "N", relation_id="0"),
        _make_value("Arms", "P", relation_id="0"),
        _make_value("Back_Height", "4", relation_id="0"),
        _make_value("Back_Height", "5", relation_id="0"),
    ]
    result = detect_hierarchy(["Arms", "Back_Height"], values, {})
    assert result == []


def test_detect_hierarchy_partial_conditions_not_child():
    """If only some values of a property are conditioned, it's not a child."""
    values = FABRIC_TYPE_VALUES + [
        _make_value("Shell_Fabric_Colour", "1HA01", relation_id="101"),
        _make_value("Shell_Fabric_Colour", "1HA02", relation_id="0"),  # no condition!
    ]
    relations = {"101": "(SPECIFIED Shell_Fabric_Type) AND (Shell_Fabric_Type IN ('1HA'))"}
    result = detect_hierarchy(
        ["Shell_Fabric_Type", "Shell_Fabric_Colour"],
        values,
        relations,
    )
    assert result == []


def test_detect_hierarchy_complex_condition_not_child():
    """Values with complex (non-parseable) conditions are not treated as children."""
    values = FABRIC_TYPE_VALUES + [
        _make_value("SomeChildProp", "val1", relation_id="901"),
        _make_value("SomeChildProp", "val2", relation_id="902"),
    ]
    relations = {
        "901": "$ BAN NOT IN ('NOCLE100')",  # article-level
        "902": "(SPECIFIED Shell_Fabric_Type) AND (Shell_Fabric_Type IN ('1HA'))",
    }
    result = detect_hierarchy(
        ["Shell_Fabric_Type", "SomeChildProp"],
        values,
        relations,
    )
    assert result == []


def test_detect_hierarchy_multiple_parent_refs_not_child():
    """If values reference different parent properties, it's not hierarchical."""
    values = [
        _make_value("PropA", "a1", relation_id="0"),
        _make_value("PropA", "a2", relation_id="0"),
        _make_value("PropB", "b1", relation_id="0"),
        _make_value("PropB", "b2", relation_id="0"),
        _make_value("ChildMaybe", "c1", relation_id="901"),
        _make_value("ChildMaybe", "c2", relation_id="902"),
    ]
    relations = {
        "901": "(SPECIFIED PropA) AND (PropA IN ('a1'))",
        "902": "(SPECIFIED PropB) AND (PropB IN ('b1'))",  # different parent!
    }
    result = detect_hierarchy(
        ["PropA", "PropB", "ChildMaybe"],
        values,
        relations,
    )
    assert result == []


def test_detect_hierarchy_empty_property_names():
    result = detect_hierarchy([], ALL_VALUES, FABRIC_RELATIONS)
    assert result == []


def test_detect_hierarchy_two_independent_hierarchies():
    """Two separate parent-child pairs are detected independently."""
    seat_colour_values = [
        _make_value("Seat_Fabric_Colour", "1HA01", relation_id="301"),
        _make_value("Seat_Fabric_Colour", "2AB01", relation_id="302"),
    ]
    seat_relations = {
        "301": "(SPECIFIED Seat_Fabric_Type) AND (Seat_Fabric_Type IN ('1HA'))",
        "302": "(SPECIFIED Seat_Fabric_Type) AND (Seat_Fabric_Type IN ('2AB'))",
    }
    seat_type_values = [
        _make_value("Seat_Fabric_Type", "1HA", relation_id="0"),
        _make_value("Seat_Fabric_Type", "2AB", relation_id="0"),
    ]
    all_vals = ALL_VALUES + seat_type_values + seat_colour_values
    all_relations = {**FABRIC_RELATIONS, **seat_relations}
    prop_names = [
        "Shell_Fabric_Type", "Shell_Fabric_Colour",
        "Seat_Fabric_Type", "Seat_Fabric_Colour",
    ]
    result = detect_hierarchy(prop_names, all_vals, all_relations)
    parents = {h["parent"] for h in result}
    children = {h["child"] for h in result}
    assert "Shell_Fabric_Type" in parents
    assert "Shell_Fabric_Colour" in children
    assert "Seat_Fabric_Type" in parents
    assert "Seat_Fabric_Colour" in children
    assert len(result) == 2


# ── _parse_single_property_condition tests ────────────────────────────────────

def test_parse_condition_standard_form():
    expr = "(SPECIFIED Shell_Fabric_Type) AND (Shell_Fabric_Type IN ('1HA'))"
    result = _parse_single_property_condition(expr)
    assert result == ("Shell_Fabric_Type", "1HA")


def test_parse_condition_without_outer_parens():
    expr = "SPECIFIED Shell_Fabric_Type AND Shell_Fabric_Type IN ('1HA')"
    result = _parse_single_property_condition(expr)
    assert result == ("Shell_Fabric_Type", "1HA")


def test_parse_condition_article_level_returns_none():
    expr = "$ BAN NOT IN ('NOCLE100', 'NOCLE200')"
    assert _parse_single_property_condition(expr) is None


def test_parse_condition_comment_returns_none():
    expr = "* not valid at article NOCLE100"
    assert _parse_single_property_condition(expr) is None


def test_parse_condition_multiple_in_values_returns_none():
    expr = "(SPECIFIED Shell_Fabric_Type) AND (Shell_Fabric_Type IN ('1HA', '2AB'))"
    assert _parse_single_property_condition(expr) is None


def test_parse_condition_empty_returns_none():
    assert _parse_single_property_condition("") is None


def test_parse_condition_complex_expression_returns_none():
    expr = "(SPECIFIED PropA) AND (PropA IN ('x')) OR (PropB IN ('y'))"
    assert _parse_single_property_condition(expr) is None


def test_parse_condition_case_insensitive():
    expr = "(specified Shell_Fabric_Type) and (Shell_Fabric_Type in ('1HA'))"
    result = _parse_single_property_condition(expr)
    assert result == ("Shell_Fabric_Type", "1HA")
```

- [ ] **Step 9: Run tests**

```bash
cd C:\Users\XMAMWU\Projects\MK_OFML_Testsuite
python -m pytest tests/test_hierarchy.py -v
```

Expected: all 20 tests pass.

---

## Chunk 3: Backend — routes.py rewrite + test_routes.py update

### Task 5 + 6: Rewrite `modules/snapper/routes.py`

**File:** `C:\Users\XMAMWU\Projects\MK_OFML_Testsuite\modules\snapper\routes.py`

**Endpoints to add:**
- `POST /api/snapper/parse-seed` — multipart form with `file` + `repo` field
- `POST /api/snapper/generate` — JSON body with queue

**Endpoints to remove:**
- `GET /api/snapper/ranges`
- `GET /api/snapper/range`

**`/parse-seed` logic:**
1. Read uploaded OBX file as string.
2. Call `parse_seed(xml_string)` → get `{article, manufacturer, series, properties}`.
3. Discover `db_path`: call `discover_ranges(repo)`, find a range where `range_info['range'].lower() == seed_data['series'].lower()`. If not found, raise 404.
4. Call `load_range_data(db_path)` → get `{articles, properties, values, relations}`.
5. Build `short_to_long` map from `ocd_relationobj.csv` in `db_path`: `{col[0].strip(): col[2].strip()}`.
6. Build `short_id_relations` dict: for each value in `load_range_data`'s `relations` dict (keyed by long ID), invert through `short_to_long`. Also, scan `ocd_relation.csv` directly to build `{long_id: concatenated_expression}` then combine with the inversion. Implementation detail: just re-read `ocd_relationobj.csv` and `ocd_relation.csv` directly in the route (simpler than using `load_range_data`'s return).
7. Call `detect_hierarchy(seed_prop_names, range_values, short_id_relations)`.
8. For each property in seed: look up valid values from `range_data['values']` filtered to that property name.
9. Build response `property_columns` list.

**`property_columns` structure for each seed property:**
```python
{
    "name": prop["name"],
    "article_class": prop["article_class"],  # from seed
    "seed_value": prop["seed_value"],
    "values": [{"code": v["value"], "label": v["label"]} for v in matching_values],
    "is_child": bool,   # True if this prop appears as child in any hierarchy
    "parent": str|None, # parent prop name if is_child else None
    "mapping": dict|None # {parent_val: [child_vals]} if is_child else None
}
```

**`/generate` logic:**
1. For each `QueueItem` in `queue`:
   a. Build `article_class_map = {item.article: item.property_to_class.get("_article_class", "")}`. The frontend passes `article_class` from the seed's artbase data. Use `prop_val_to_class` from `item.prop_val_to_class` (string keys `"PropName=Value"` → convert to tuple keys `{(PropName, Value): class}`).
   b. Call `compute_permutations([item.article], item.selected_properties)`.
   c. Call `build_obx(permutations, article_class_map, manufacturer, series, property_to_class, prop_val_to_class)`.
2. If queue has one item: return XML directly.
3. If queue has multiple items: zip all OBX files and return as `application/zip`.

**Helper: build short_id_relations**

This helper function should be defined in routes.py (private, not exported):

```python
def _build_short_id_relations(db_path: str) -> dict[str, str]:
    """
    Build {short_relation_id: concatenated_expression} by joining
    ocd_relationobj.csv (short→long bridge) with ocd_relation.csv (long→expression).
    """
    from pathlib import Path
    from .reader import _read_csv

    db = Path(db_path)

    # Build long_id → concatenated expression from ocd_relation.csv
    long_to_expr: dict[str, str] = {}
    rel_path = db / "ocd_relation.csv"
    if rel_path.exists():
        for row in _read_csv(str(rel_path)):
            if len(row) < 3:
                continue
            long_id = row[0].strip()
            part = row[2].strip().strip('"')
            if long_id not in long_to_expr:
                long_to_expr[long_id] = part
            else:
                long_to_expr[long_id] += " " + part

    # Build short_id → expression via ocd_relationobj.csv
    short_to_expr: dict[str, str] = {}
    obj_path = db / "ocd_relationobj.csv"
    if obj_path.exists():
        for row in _read_csv(str(obj_path)):
            if len(row) < 3:
                continue
            short_id = row[0].strip()
            long_id = row[2].strip()
            expr = long_to_expr.get(long_id)
            if expr is not None and short_id not in short_to_expr:
                short_to_expr[short_id] = expr

    return short_to_expr
```

- [ ] **Step 10: Write the new `modules/snapper/routes.py`**

```python
import io
import zipfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from .reader import discover_ranges, load_range_data, _read_csv
from .generator import compute_permutations, build_obx
from .seed_parser import parse_seed, SeedParseError
from .hierarchy import detect_hierarchy

router = APIRouter(prefix="/api/snapper", tags=["snapper"])


# ── Helper ────────────────────────────────────────────────────────────────────

def _build_short_id_relations(db_path: str) -> dict[str, str]:
    """
    Build {short_relation_id: concatenated_expression} by joining
    ocd_relationobj.csv (short→long bridge) with ocd_relation.csv (long→expression).
    """
    db = Path(db_path)

    # Build long_id → concatenated expression
    long_to_expr: dict[str, str] = {}
    rel_path = db / "ocd_relation.csv"
    if rel_path.exists():
        for row in _read_csv(str(rel_path)):
            if len(row) < 3:
                continue
            long_id = row[0].strip()
            part = row[2].strip().strip('"')
            if long_id not in long_to_expr:
                long_to_expr[long_id] = part
            else:
                long_to_expr[long_id] += " " + part

    # Build short_id → expression via ocd_relationobj.csv
    short_to_expr: dict[str, str] = {}
    obj_path = db / "ocd_relationobj.csv"
    if obj_path.exists():
        for row in _read_csv(str(obj_path)):
            if len(row) < 3:
                continue
            short_id = row[0].strip()
            long_id = row[2].strip()
            expr = long_to_expr.get(long_id)
            if expr is not None and short_id not in short_to_expr:
                short_to_expr[short_id] = expr

    return short_to_expr


# ── /parse-seed endpoint ──────────────────────────────────────────────────────

@router.post("/parse-seed")
async def parse_seed_endpoint(
    file: UploadFile = File(...),
    repo: str = Form(...),
):
    """
    Parse an uploaded OBX seed file and return property columns with valid values
    and detected hierarchy information.
    """
    raw = await file.read()
    try:
        xml_string = raw.decode("utf-8", errors="replace")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not decode file: {e}")

    try:
        seed = parse_seed(xml_string)
    except SeedParseError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # Discover db_path by matching series code (case-insensitive) against known ranges
    ranges = discover_ranges(repo)
    matched = next(
        (r for r in ranges if r["range"].lower() == seed["series"].lower()),
        None,
    )
    if matched is None:
        raise HTTPException(
            status_code=404,
            detail=f"No range found matching series '{seed['series']}' in repo '{repo}'"
        )
    db_path = matched["db_path"]

    # Load OCD data for the range
    try:
        range_data = load_range_data(db_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load range data: {e}")

    # Build short_id → expression map for hierarchy detection
    short_id_relations = _build_short_id_relations(db_path)

    # Detect hierarchies scoped to seed properties only
    seed_prop_names = [p["name"] for p in seed["properties"]]
    hierarchies = detect_hierarchy(seed_prop_names, range_data["values"], short_id_relations)

    # Build lookup: child_prop_name → hierarchy dict
    child_map = {h["child"]: h for h in hierarchies}

    # Build values lookup: property_name → list of {code, label}
    values_by_prop: dict[str, list[dict]] = {}
    seen: dict[str, set] = {}
    for v in range_data["values"]:
        pname = v["property_name"]
        code = v["value"]
        if not code:
            continue
        if pname not in values_by_prop:
            values_by_prop[pname] = []
            seen[pname] = set()
        if code not in seen[pname]:
            seen[pname].add(code)
            values_by_prop[pname].append({"code": code, "label": v.get("label", code)})

    # Build property_columns
    property_columns = []
    for prop in seed["properties"]:
        pname = prop["name"]
        h = child_map.get(pname)
        is_child = h is not None
        property_columns.append({
            "name": pname,
            "article_class": prop["article_class"],
            "seed_value": prop["seed_value"],
            "values": values_by_prop.get(pname, []),
            "is_child": is_child,
            "parent": h["parent"] if is_child else None,
            "mapping": h["mapping"] if is_child else None,
        })

    return {
        "article": seed["article"],
        "manufacturer": seed["manufacturer"],
        "series": seed["series"],
        "repo": repo,
        "db_path": db_path,
        "property_columns": property_columns,
    }


# ── /generate endpoint ────────────────────────────────────────────────────────

class QueueItem(BaseModel):
    article: str
    article_class: str                      # Primary class for this article (from seed artbase)
    property_to_class: dict[str, str]       # {prop_name: article_class} — from seed varcode
    prop_val_to_class: dict[str, str]       # {"PropName=Value": article_class} — string keys
    selected_properties: dict[str, list[str]]  # {prop_name: [values]} — hierarchy resolved by frontend


class GenerateRequest(BaseModel):
    manufacturer: str
    series: str
    queue: list[QueueItem]
    filename: str = "snapper.obx"


@router.post("/generate")
def generate_obx(req: GenerateRequest):
    """
    Generate OBX file(s) from a queue of article configurations.
    Single-item queue returns XML directly; multi-item returns a zip.
    """
    if not req.queue:
        raise HTTPException(status_code=400, detail="Queue is empty")

    obx_files: list[tuple[str, str]] = []  # (filename, xml_content)

    for item in req.queue:
        # Build article_class_map: {article_code: article_class}
        article_class_map = {item.article: item.article_class}

        # Convert prop_val_to_class from string keys to tuple keys
        pvtc: dict[tuple, str] = {}
        for key_str, cls in item.prop_val_to_class.items():
            eq_idx = key_str.find("=")
            if eq_idx != -1:
                prop_name = key_str[:eq_idx]
                val = key_str[eq_idx + 1:]
                pvtc[(prop_name, val)] = cls

        permutations = compute_permutations([item.article], item.selected_properties)
        xml_content = build_obx(
            permutations,
            article_class_map,
            req.manufacturer,
            req.series,
            item.property_to_class,
            pvtc,
        )
        safe_name = item.article.replace("/", "_").replace("\\", "_")
        obx_files.append((f"{safe_name}.obx", xml_content))

    if len(obx_files) == 1:
        filename, xml_content = obx_files[0]
        return Response(
            content=xml_content,
            media_type="application/xml",
            headers={"Content-Disposition": f'attachment; filename="{req.filename}"'},
        )

    # Multiple files → zip
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname, content in obx_files:
            zf.writestr(fname, content)
    buf.seek(0)
    zip_filename = req.filename.replace(".obx", ".zip") if req.filename.endswith(".obx") else req.filename + ".zip"
    return Response(
        content=buf.read(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{zip_filename}"'},
    )
```

- [ ] **Step 11: Verify the app still starts**

```bash
cd C:\Users\XMAMWU\Projects\MK_OFML_Testsuite
python -c "from main import app; print('app loads OK')"
```

Expected: `app loads OK`

---

### Task 7: Update `tests/test_routes.py`

**File:** `C:\Users\XMAMWU\Projects\MK_OFML_Testsuite\tests\test_routes.py`

Replace all existing tests. The old `/ranges` and `/range` endpoints are gone. New tests cover `/parse-seed` and `/generate`. Integration tests hit the real repo.

- [ ] **Step 12: Rewrite `tests/test_routes.py`**

```python
import io
import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

REPO_ROOT = r"C:\HermanMillerOFMLSVN\Staging\HermanMiller\_repository"

# ── OBX fixture ───────────────────────────────────────────────────────────────

CLOUD_SEED_XML = b"""<?xml version='1.0'?>
<cutBuffer>
  <state sessionId='169f45a8-041c-437f-b009-5600cecc5ca9'/>
  <versionInfo vendorKey='EasternGraphics' appKey='EAI-Server' appVersion='4.18.3' bskXmlVersion='1.8.10'/>
  <items>
    <bskArticle basketId='a1bab025-ebec-4652-841d-83918768adfc' itemType='BasketArticle' updateState='UpToDate'>
      <manufacturer id='HM'/>
      <series id='CLOUD'/>
      <artNr type='base'>NOCLE4</artNr>
      <artNr type='ofmlvarcode'>CLOUD_ATTR_ARM_CHAIR.Type=10;CLOUD_OPT.Base_Finish=R00;CLOUD_OPT.Shell_Fabric_Type=1HA;CLOUD_OPT.Shell_Fabric_Colour=1HA02;CLOUD_OPT.Seat_Fabric_Type=1HA;CLOUD_OPT.Seat_Fabric_Colour=1HA01</artNr>
    </bskArticle>
  </items>
</cutBuffer>"""


def _upload_seed(xml_bytes=CLOUD_SEED_XML, repo=REPO_ROOT):
    return client.post(
        "/api/snapper/parse-seed",
        data={"repo": repo},
        files={"file": ("seed.obx", io.BytesIO(xml_bytes), "application/xml")},
    )


# ── /parse-seed integration tests ─────────────────────────────────────────────

def test_parse_seed_returns_200():
    response = _upload_seed()
    assert response.status_code == 200


def test_parse_seed_returns_article_code():
    data = _upload_seed().json()
    assert data["article"] == "NOCLE4"


def test_parse_seed_returns_series():
    data = _upload_seed().json()
    assert data["series"] == "CLOUD"


def test_parse_seed_returns_property_columns():
    data = _upload_seed().json()
    assert "property_columns" in data
    assert len(data["property_columns"]) == 6


def test_parse_seed_type_column_has_values():
    data = _upload_seed().json()
    cols = {c["name"]: c for c in data["property_columns"]}
    assert "Type" in cols
    type_col = cols["Type"]
    assert len(type_col["values"]) > 0
    assert type_col["article_class"] == "CLOUD_ATTR_ARM_CHAIR"
    assert type_col["is_child"] is False


def test_parse_seed_fabric_colour_is_child():
    data = _upload_seed().json()
    cols = {c["name"]: c for c in data["property_columns"]}
    colour_col = cols.get("Shell_Fabric_Colour")
    assert colour_col is not None
    assert colour_col["is_child"] is True
    assert colour_col["parent"] == "Shell_Fabric_Type"
    assert "mapping" in colour_col
    assert colour_col["mapping"] is not None


def test_parse_seed_fabric_type_is_not_child():
    data = _upload_seed().json()
    cols = {c["name"]: c for c in data["property_columns"]}
    type_col = cols.get("Shell_Fabric_Type")
    assert type_col is not None
    assert type_col["is_child"] is False
    assert type_col["parent"] is None


def test_parse_seed_invalid_repo_returns_404():
    response = _upload_seed(repo="/nonexistent/path")
    assert response.status_code == 404


def test_parse_seed_invalid_xml_returns_422():
    response = _upload_seed(xml_bytes=b"not xml at all <<<")
    assert response.status_code == 422


def test_parse_seed_missing_varcode_returns_422():
    xml = b"""<cutBuffer><items><bskArticle>
      <manufacturer id='HM'/><series id='CLOUD'/>
      <artNr type='base'>NOCLE4</artNr>
    </bskArticle></items></cutBuffer>"""
    response = _upload_seed(xml_bytes=xml)
    assert response.status_code == 422


# ── /generate integration tests ───────────────────────────────────────────────

def test_generate_single_article_returns_xml():
    payload = {
        "manufacturer": "HM",
        "series": "CLOUD",
        "queue": [
            {
                "article": "NOCLE4",
                "article_class": "CLOUD_OPT",
                "property_to_class": {
                    "Type": "CLOUD_ATTR_ARM_CHAIR",
                    "Base_Finish": "CLOUD_OPT",
                },
                "prop_val_to_class": {
                    "Type=10": "CLOUD_ATTR_ARM_CHAIR",
                    "Base_Finish=R00": "CLOUD_OPT",
                    "Base_Finish=SL": "CLOUD_OPT",
                },
                "selected_properties": {
                    "Type": ["10"],
                    "Base_Finish": ["R00", "SL"],
                },
            }
        ],
        "filename": "test_cloud.obx",
    }
    response = client.post("/api/snapper/generate", json=payload)
    assert response.status_code == 200
    assert "application/xml" in response.headers["content-type"]
    # 1 article * 1 Type * 2 Base_Finish = 2 permutations
    assert response.text.count("<bskArticle") == 2


def test_generate_obx_contains_correct_varcode():
    payload = {
        "manufacturer": "HM",
        "series": "CLOUD",
        "queue": [
            {
                "article": "NOCLE4",
                "article_class": "CLOUD_OPT",
                "property_to_class": {"Type": "CLOUD_ATTR_ARM_CHAIR"},
                "prop_val_to_class": {"Type=10": "CLOUD_ATTR_ARM_CHAIR"},
                "selected_properties": {"Type": ["10"]},
            }
        ],
        "filename": "test.obx",
    }
    response = client.post("/api/snapper/generate", json=payload)
    assert "CLOUD_ATTR_ARM_CHAIR.Type=10" in response.text


def test_generate_multiple_articles_returns_zip():
    payload = {
        "manufacturer": "HM",
        "series": "CLOUD",
        "queue": [
            {
                "article": "NOCLE4",
                "article_class": "CLOUD_OPT",
                "property_to_class": {"Base_Finish": "CLOUD_OPT"},
                "prop_val_to_class": {"Base_Finish=R00": "CLOUD_OPT"},
                "selected_properties": {"Base_Finish": ["R00"]},
            },
            {
                "article": "NOCLE5",
                "article_class": "CLOUD_OPT",
                "property_to_class": {"Base_Finish": "CLOUD_OPT"},
                "prop_val_to_class": {"Base_Finish=R00": "CLOUD_OPT"},
                "selected_properties": {"Base_Finish": ["R00"]},
            },
        ],
        "filename": "test.obx",
    }
    response = client.post("/api/snapper/generate", json=payload)
    assert response.status_code == 200
    assert "application/zip" in response.headers["content-type"]


def test_generate_empty_queue_returns_400():
    payload = {
        "manufacturer": "HM",
        "series": "CLOUD",
        "queue": [],
        "filename": "test.obx",
    }
    response = client.post("/api/snapper/generate", json=payload)
    assert response.status_code == 400
```

- [ ] **Step 13: Run the updated test suite**

```bash
cd C:\Users\XMAMWU\Projects\MK_OFML_Testsuite
python -m pytest tests/test_routes.py -v
```

Expected: all tests pass. The integration tests require the real repo at `C:\HermanMillerOFMLSVN\Staging\HermanMiller\_repository`.

- [ ] **Step 14: Run all backend tests together to confirm nothing regressed**

```bash
cd C:\Users\XMAMWU\Projects\MK_OFML_Testsuite
python -m pytest tests/ -v
```

Expected: all tests pass (test_generator.py and test_reader.py are unchanged and should still pass).

---

## Chunk 4: Frontend — full rewrite

### Task 8: Rewrite `static/snapper/index.html`

**File:** `C:\Users\XMAMWU\Projects\MK_OFML_Testsuite\static\snapper\index.html`

**Layout:**
- Header: title, back link, repo path input (localStorage-persisted)
- Main: left panel (seed upload + dimension columns) + right sidebar (queue)
- Left panel top: seed upload section (file input + "Parse Seed" button + parsed article info)
- Left panel bottom: scrollable dimension columns area + permutation counter
- Right sidebar: article name field + "Add to Queue" button + queue list + "Generate All" button

- [ ] **Step 15: Rewrite `static/snapper/index.html`**

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
      <div>
        <label class="block text-xs text-gray-500 mb-1">Repository path</label>
        <input id="repoPath" type="text"
          class="border rounded px-2 py-1 text-sm w-96"
          placeholder="C:\path\to\_repository">
      </div>
    </div>
  </header>

  <!-- Main area -->
  <main class="flex flex-1 overflow-hidden">

    <!-- Left panel: seed upload + dimension columns -->
    <section class="flex-1 overflow-x-auto p-4 flex flex-col gap-4">

      <!-- Seed upload section -->
      <div id="seedSection" class="bg-white rounded-lg shadow p-4">
        <h2 class="font-semibold text-gray-700 mb-3">Upload Seed OBX</h2>
        <div class="flex items-end gap-3 flex-wrap">
          <div>
            <label class="block text-xs text-gray-500 mb-1">Seed OBX file (single configured product from pCon)</label>
            <input id="seedFile" type="file" accept=".obx,.xml"
              class="border rounded px-2 py-1 text-sm">
          </div>
          <button id="parseSeedBtn"
            class="bg-blue-600 text-white px-4 py-1.5 rounded text-sm hover:bg-blue-700 disabled:opacity-50"
            disabled>
            Parse Seed
          </button>
          <div id="seedStatus" class="text-sm text-gray-500"></div>
        </div>

        <!-- Parsed article info (hidden until seed parsed) -->
        <div id="seedInfo" class="hidden mt-3 p-3 bg-blue-50 rounded text-sm text-blue-800">
          <span id="seedInfoText"></span>
        </div>
      </div>

      <!-- Dimension columns area (hidden until seed parsed) -->
      <div id="dimensionArea" class="hidden flex flex-col gap-2">
        <div id="dimensionColumns" class="flex gap-4 items-start"></div>
        <div id="permCount" class="text-sm font-medium text-gray-700"></div>
      </div>

      <!-- Empty state -->
      <div id="emptyState" class="text-gray-400 text-sm mt-4 ml-2">
        Upload a seed OBX file to begin. The seed should be a single product exported from pCon Planner.
      </div>

    </section>

    <!-- Right sidebar: queue -->
    <aside class="w-72 bg-white border-l shadow-inner p-4 flex flex-col">
      <h2 class="font-semibold text-gray-700 mb-3">Generation Queue</h2>

      <div class="mb-3">
        <label class="block text-xs text-gray-500 mb-1">Article label (optional)</label>
        <input id="articleLabel" type="text" placeholder="e.g. NOCLE4 arm chair"
          class="border rounded px-2 py-1 text-sm w-full mb-2">
        <button id="addToQueueBtn"
          class="w-full bg-green-600 text-white px-3 py-1.5 rounded text-sm hover:bg-green-700 disabled:opacity-50"
          disabled>
          Add to Queue
        </button>
      </div>

      <div id="queueList" class="flex-1 overflow-y-auto space-y-2"></div>

      <div class="mt-4 space-y-2">
        <button id="generateAllBtn"
          class="w-full bg-blue-700 text-white px-3 py-2 rounded text-sm hover:bg-blue-800 disabled:opacity-50"
          disabled>
          Generate All
        </button>
        <div id="generateStatus" class="text-xs text-gray-500 text-center hidden"></div>
      </div>
    </aside>
  </main>

  <script src="/static/snapper/snapper.js"></script>
</body>
</html>
```

---

### Task 9: Rewrite `static/snapper/snapper.js`

**File:** `C:\Users\XMAMWU\Projects\MK_OFML_Testsuite\static\snapper\snapper.js`

**State management:**
- `currentSeed` — the parsed `/parse-seed` response (null until a seed is uploaded)
- `hierarchyModes` — `{child_prop_name: "first"|"distribute"}` for each detected child prop
- `queue` — array of queue items, each containing all data needed to call `/generate`

**Workflow:**
1. User enters repo path (persisted to localStorage).
2. User selects a `.obx` file. "Parse Seed" button enables.
3. On "Parse Seed" click: POST to `/api/snapper/parse-seed`. On success: render dimension columns. Show article info. Enable "Add to Queue".
4. For each column: if `is_child` is false → render checkbox column. If `is_child` is true → do not render as its own column; instead render a mode toggle below the parent column.
5. "Add to Queue": compute resolved `selected_properties` (including child values resolved by mode), build queue item, push to queue, re-render queue list.
6. "Generate All": POST to `/api/snapper/generate` with all queue items. Handle single (XML download) or multiple (zip download).

**Hierarchy child resolution:**
- `"first"` mode: for each selected parent value, take `mapping[parent_val][0]`.
- `"distribute"` mode: across all selected parent values in order, cycle through child values: `mapping[parent_val][i % len(mapping[parent_val])]` where `i` is a per-parent counter that increments after each use.

**Permutation counting:** count = product of all selected non-child property value counts. Child props do not add dimensions (they're resolved 1-to-1 with parent values).

- [ ] **Step 16: Rewrite `static/snapper/snapper.js`**

```javascript
// ── Constants ──────────────────────────────────────────────────────────────────
const WARN_LIMIT = 200;
const ERROR_LIMIT = 500;

// ── State ──────────────────────────────────────────────────────────────────────
let currentSeed = null;    // Response from /parse-seed
let hierarchyModes = {};   // {child_prop_name: "first"|"distribute"}
let queue = [];            // [{label, article, articleClass, propertyToClass,
                           //   propValToClass, selectedProperties, count}]

// ── DOM refs ───────────────────────────────────────────────────────────────────
const repoPathInput = document.getElementById('repoPath');
const seedFileInput = document.getElementById('seedFile');
const parseSeedBtn = document.getElementById('parseSeedBtn');
const seedStatus = document.getElementById('seedStatus');
const seedInfo = document.getElementById('seedInfo');
const seedInfoText = document.getElementById('seedInfoText');
const dimensionArea = document.getElementById('dimensionArea');
const dimensionColumns = document.getElementById('dimensionColumns');
const emptyState = document.getElementById('emptyState');
const permCount = document.getElementById('permCount');
const articleLabel = document.getElementById('articleLabel');
const addToQueueBtn = document.getElementById('addToQueueBtn');
const queueList = document.getElementById('queueList');
const generateAllBtn = document.getElementById('generateAllBtn');
const generateStatus = document.getElementById('generateStatus');

// ── Persist repo path ──────────────────────────────────────────────────────────
repoPathInput.value = localStorage.getItem('repoPath') || '';
repoPathInput.addEventListener('input', () => {
  localStorage.setItem('repoPath', repoPathInput.value.trim());
});

// ── Seed file input ────────────────────────────────────────────────────────────
seedFileInput.addEventListener('change', () => {
  parseSeedBtn.disabled = !seedFileInput.files.length || !repoPathInput.value.trim();
});

repoPathInput.addEventListener('input', () => {
  parseSeedBtn.disabled = !seedFileInput.files.length || !repoPathInput.value.trim();
});

// ── Parse Seed ────────────────────────────────────────────────────────────────
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
  // Default mode for each child property: "first"
  for (const col of currentSeed.property_columns) {
    if (col.is_child) {
      hierarchyModes[col.name] = 'first';
    }
  }

  seedStatus.textContent = '';
  parseSeedBtn.disabled = false;

  // Show article info
  seedInfo.classList.remove('hidden');
  seedInfoText.textContent =
    `Article: ${currentSeed.article} · Manufacturer: ${currentSeed.manufacturer} · Series: ${currentSeed.series} · ${currentSeed.property_columns.length} properties`;

  // Show dimension columns
  emptyState.classList.add('hidden');
  dimensionArea.classList.remove('hidden');
  renderDimensions();
  addToQueueBtn.disabled = false;
});

// ── Render dimension columns ───────────────────────────────────────────────────
function renderDimensions() {
  dimensionColumns.innerHTML = '';
  if (!currentSeed) return;

  // Build a map of parent → child hierarchy info
  const childProps = new Map(); // child_name → {parent, mapping}
  const parentHasChild = new Map(); // parent_name → child_name
  for (const col of currentSeed.property_columns) {
    if (col.is_child) {
      childProps.set(col.name, { parent: col.parent, mapping: col.mapping });
      parentHasChild.set(col.parent, col.name);
    }
  }

  for (const col of currentSeed.property_columns) {
    if (col.is_child) continue; // Child props are rendered as a sub-control of parent

    const colEl = renderPropertyColumn(col, parentHasChild.get(col.name) || null, col.name);
    dimensionColumns.appendChild(colEl);
  }

  updatePermCount();
}

function renderPropertyColumn(col, childPropName, propName) {
  const wrapper = document.createElement('div');
  wrapper.className = 'flex flex-col gap-1';

  // Main checkbox column
  const colEl = _buildCheckboxColumn(propName, col.values, col.seed_value);
  wrapper.appendChild(colEl);

  // If this property has a child (colour), add mode toggle below
  if (childPropName) {
    const modeEl = _buildHierarchyModeControl(childPropName);
    wrapper.appendChild(modeEl);
  }

  return wrapper;
}

function _buildCheckboxColumn(propName, values, seedValue) {
  const col = document.createElement('div');
  col.className = 'bg-white rounded-lg shadow p-3 min-w-44 max-w-56 flex flex-col';
  col.dataset.propName = propName;

  col.innerHTML = `
    <div class="font-semibold text-sm text-gray-700 mb-2 border-b pb-1" title="${propName}">${propName}</div>
    <div class="flex gap-1 mb-2">
      <button class="text-xs text-blue-600 hover:underline select-all-btn">All</button>
      <span class="text-gray-300">|</span>
      <button class="text-xs text-blue-600 hover:underline select-none-btn">None</button>
    </div>
    <div class="overflow-y-auto max-h-64 space-y-1">
      ${values.map(v => `
        <label class="flex items-center gap-1 text-xs text-gray-700 cursor-pointer">
          <input type="checkbox" class="dim-check" data-prop="${propName}" data-value="${v.code}"
            ${v.code === seedValue ? 'checked' : ''}>
          <span class="font-mono text-gray-500">${v.code}</span>
          ${v.label && v.label !== v.code ? `<span class="text-gray-400">·</span><span class="truncate">${v.label}</span>` : ''}
        </label>
      `).join('')}
    </div>
  `;

  col.querySelector('.select-all-btn').addEventListener('click', () => {
    col.querySelectorAll('.dim-check').forEach(cb => { cb.checked = true; });
    updatePermCount();
  });
  col.querySelector('.select-none-btn').addEventListener('click', () => {
    col.querySelectorAll('.dim-check').forEach(cb => { cb.checked = false; });
    updatePermCount();
  });
  col.querySelectorAll('.dim-check').forEach(cb =>
    cb.addEventListener('change', updatePermCount)
  );
  return col;
}

function _buildHierarchyModeControl(childPropName) {
  const el = document.createElement('div');
  el.className = 'bg-amber-50 border border-amber-200 rounded p-2 text-xs text-amber-800';
  el.dataset.childProp = childPropName;

  const currentMode = hierarchyModes[childPropName] || 'first';
  el.innerHTML = `
    <div class="font-semibold mb-1">${childPropName}</div>
    <div class="text-gray-500 mb-1 text-xs">Colour assignment:</div>
    <div class="flex gap-1">
      <button class="mode-btn px-2 py-0.5 rounded text-xs border ${currentMode === 'first' ? 'bg-amber-600 text-white border-amber-600' : 'bg-white border-gray-300 text-gray-700'}"
        data-mode="first" data-child="${childPropName}">First only</button>
      <button class="mode-btn px-2 py-0.5 rounded text-xs border ${currentMode === 'distribute' ? 'bg-amber-600 text-white border-amber-600' : 'bg-white border-gray-300 text-gray-700'}"
        data-mode="distribute" data-child="${childPropName}">Distribute</button>
    </div>
  `;

  el.querySelectorAll('.mode-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      hierarchyModes[childPropName] = btn.dataset.mode;
      // Re-render just this control
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
  // Returns {propName: [selectedValues]} for non-child properties only
  const selections = {};
  document.querySelectorAll('.dim-check:checked').forEach(cb => {
    const prop = cb.dataset.prop;
    if (!selections[prop]) selections[prop] = [];
    selections[prop].push(cb.dataset.value);
  });
  return selections;
}

function computePermCount(parentSelections) {
  const counts = Object.values(parentSelections).map(v => v.length);
  if (counts.length === 0) return 0;
  return counts.reduce((a, b) => a * b, 1);
}

function updatePermCount() {
  const sel = getParentSelections();
  const count = computePermCount(sel);
  permCount.textContent = `${count.toLocaleString()} permutations`;
  permCount.className = 'text-sm font-medium ' + (
    count > ERROR_LIMIT ? 'text-red-600' :
    count > WARN_LIMIT  ? 'text-amber-600' :
                          'text-gray-700'
  );
  if (count > ERROR_LIMIT) {
    permCount.textContent += ` ⚠ Consider splitting (suggested max: ${ERROR_LIMIT})`;
  }
}

// ── Resolve child property values ──────────────────────────────────────────────
function resolveChildValues(parentSelections) {
  // For each child property, resolve which values to include based on mode
  // Returns: {child_prop_name: [resolved_values]} to merge into selectedProperties
  if (!currentSeed) return {};
  const childAssignments = {};

  const childCols = currentSeed.property_columns.filter(c => c.is_child);
  for (const childCol of childCols) {
    const parentVals = parentSelections[childCol.parent] || [];
    const mode = hierarchyModes[childCol.name] || 'first';
    const mapping = childCol.mapping || {};
    const resolved = [];

    if (mode === 'first') {
      for (const pv of parentVals) {
        const children = mapping[pv] || [];
        if (children.length > 0) resolved.push(children[0]);
      }
    } else {
      // distribute: cycle through children for each parent value
      const counters = {};
      for (const pv of parentVals) {
        const children = mapping[pv] || [];
        if (children.length === 0) continue;
        const n = counters[pv] || 0;
        resolved.push(children[n % children.length]);
        counters[pv] = n + 1;
      }
    }

    if (resolved.length > 0) {
      childAssignments[childCol.name] = resolved;
    }
  }
  return childAssignments;
}

// ── Build property_to_class and prop_val_to_class from seed ──────────────────
function buildClassMaps() {
  // property_to_class: {prop_name: article_class} — from seed
  // prop_val_to_class: {"PropName=Value": article_class} — for all values loaded
  if (!currentSeed) return { propertyToClass: {}, propValToClass: {} };

  const propertyToClass = {};
  const propValToClass = {};

  for (const col of currentSeed.property_columns) {
    propertyToClass[col.name] = col.article_class;
    for (const v of col.values) {
      propValToClass[`${col.name}=${v.code}`] = col.article_class;
    }
  }
  return { propertyToClass, propValToClass };
}

// ── Add to queue ──────────────────────────────────────────────────────────────
addToQueueBtn.addEventListener('click', () => {
  if (!currentSeed) return;

  const parentSelections = getParentSelections();
  const childResolved = resolveChildValues(parentSelections);
  const selectedProperties = { ...parentSelections, ...childResolved };

  const count = computePermCount(parentSelections);
  const label = articleLabel.value.trim() || currentSeed.article;
  const { propertyToClass, propValToClass } = buildClassMaps();

  queue.push({
    label,
    article: currentSeed.article,
    articleClass: currentSeed.property_columns[0]?.article_class || '',
    propertyToClass,
    propValToClass,
    selectedProperties,
    count,
    manufacturer: currentSeed.manufacturer,
    series: currentSeed.series,
  });

  articleLabel.value = '';
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
        <span class="font-semibold text-gray-800">${entry.label}</span>
        <button class="text-red-500 hover:text-red-700 ml-2 remove-btn" data-idx="${i}">✕</button>
      </div>
      <div class="text-gray-600 mt-0.5">Article: ${entry.article}</div>
      <div class="text-gray-500 mt-0.5">${entry.count.toLocaleString()} permutations · ${Object.keys(entry.selectedProperties).length} props</div>
    `;
    card.querySelector('.remove-btn').addEventListener('click', (e) => {
      queue.splice(parseInt(e.target.dataset.idx), 1);
      renderQueue();
    });
    queueList.appendChild(card);
  }
  generateAllBtn.disabled = queue.length === 0;
}

// ── Generate All ──────────────────────────────────────────────────────────────
generateAllBtn.addEventListener('click', async () => {
  if (queue.length === 0) return;

  generateAllBtn.disabled = true;
  generateAllBtn.textContent = 'Generating…';
  generateStatus.classList.remove('hidden');
  generateStatus.textContent = '';

  // All items must share the same manufacturer and series (they're per-article queues)
  // Use the first item's manufacturer/series (they should all match if from same range)
  const manufacturer = queue[0].manufacturer;
  const series = queue[0].series;

  const queuePayload = queue.map(entry => ({
    article: entry.article,
    article_class: entry.articleClass,
    property_to_class: entry.propertyToClass,
    prop_val_to_class: entry.propValToClass,
    selected_properties: entry.selectedProperties,
  }));

  const payload = {
    manufacturer,
    series,
    queue: queuePayload,
    filename: `snapper_${series}.obx`,
  };

  let response;
  try {
    response = await fetch('/api/snapper/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  } catch (err) {
    generateStatus.textContent = `Network error: ${err.message}`;
    generateAllBtn.disabled = false;
    generateAllBtn.textContent = 'Generate All';
    return;
  }

  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: 'Unknown error' }));
    generateStatus.textContent = `Error: ${err.detail}`;
    generateAllBtn.disabled = false;
    generateAllBtn.textContent = 'Generate All';
    return;
  }

  // Trigger download
  const contentType = response.headers.get('content-type') || '';
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = contentType.includes('zip')
    ? `snapper_${series}.zip`
    : `snapper_${series}.obx`;
  a.click();
  URL.revokeObjectURL(url);

  generateStatus.textContent = 'Downloaded.';
  generateAllBtn.disabled = false;
  generateAllBtn.textContent = 'Generate All';
});
```

- [ ] **Step 17: Smoke-test the UI manually**

```bash
cd C:\Users\XMAMWU\Projects\MK_OFML_Testsuite
python main.py
```

Then open `http://localhost:8080/snapper/` in a browser and:
1. Enter the repo path: `C:\HermanMillerOFMLSVN\Staging\HermanMiller\_repository`
2. Upload a real cloud OBX seed file (or create a minimal one with the XML from the test fixtures).
3. Click "Parse Seed". Verify article info appears and columns render.
4. Verify Shell_Fabric_Type shows as a normal column and Shell_Fabric_Colour appears as a mode toggle below it.
5. Select a subset of Type and Base_Finish values. Verify permutation count updates.
6. Click "Add to Queue". Verify the queue card appears.
7. Click "Generate All". Verify an OBX or zip file downloads.

---

## Final verification: full test suite

- [ ] **Step 18: Run the complete test suite**

```bash
cd C:\Users\XMAMWU\Projects\MK_OFML_Testsuite
python -m pytest tests/ -v --tb=short
```

Expected output:
```
tests/test_generator.py - all pass (unchanged)
tests/test_reader.py - all pass (unchanged)
tests/test_seed_parser.py - all 18 pass
tests/test_hierarchy.py - all 20 pass
tests/test_routes.py - all pass
```

---

## Implementation order and dependencies

```
Task 2 (test_seed_parser) → Task 1 (seed_parser.py)
Task 4 (test_hierarchy)   → Task 3 (hierarchy.py)
Task 1 + Task 3           → Task 5+6 (routes.py)
Task 5+6                  → Task 7 (test_routes.py)
Task 5+6                  → Task 8 (index.html) + Task 9 (snapper.js)
```

All backend work (Chunks 1–3) should be completed and passing before any frontend work begins. Frontend work (Chunk 4) can proceed independently once the API contract is stable.

---

## Key edge cases to handle during implementation

**seed_parser.py:**
- Empty varcode string → raise `SeedParseError`
- Varcode segments without `.` or `=` → silently skip (not an error)
- Multiple `<bskArticle>` elements → parse only the first

**hierarchy.py:**
- Property with zero values → skip
- Property where only some values have conditions → skip (not a child)
- Expression referencing a parent that is NOT in the seed's property list → skip
- Two properties both conditioned on the same parent → each registers as a separate child

**routes.py /parse-seed:**
- Series code matching is case-insensitive: `"CLOUD"` matches range folder `"cloud"`
- If `ocd_relationobj.csv` is missing from a range (unusual but possible) → `_build_short_id_relations` returns `{}` and hierarchy detection finds no pairs (safe fallback)
- Values with duplicate codes for the same property → deduplicate by code (use seen-set, same as current snapper.js pattern)

**snapper.js — hierarchy mode "distribute":**
- "Distribute" means: given parent values `[1HA, 2AB]` with children `[1HA01, 1HA02]` and `[2AB01]`, one permutation gets `1HA01`, the next gets `2AB01`. The counter increments per parent value, not globally. The prompt spec says: for each selected parent value, track `n` and assign `children[n % len(children)]`. This means within a single "Add to Queue" action, each parent value's counter starts at 0 and the list cycles if more permutations than children exist.

---

### Critical Files for Implementation

- `C:\Users\XMAMWU\Projects\MK_OFML_Testsuite\modules\snapper\routes.py` - Core logic to rewrite: two new endpoints, relation ID bridge via `_build_short_id_relations`, seed discovery, hierarchy wiring
- `C:\Users\XMAMWU\Projects\MK_OFML_Testsuite\modules\snapper\hierarchy.py` - New file: detect_hierarchy and _parse_single_property_condition; must handle the short-ID relation lookup correctly
- `C:\Users\XMAMWU\Projects\MK_OFML_Testsuite\modules\snapper\seed_parser.py` - New file: OBX XML parsing, varcode segmentation, SeedParseError
- `C:\Users\XMAMWU\Projects\MK_OFML_Testsuite\static\snapper\snapper.js` - Full rewrite: seed upload flow, hierarchy column rendering, mode toggle, queue with resolved child values
- `C:\Users\XMAMWU\Projects\MK_OFML_Testsuite\modules\snapper\reader.py` - Reference only (do not modify): `_read_csv` is imported by routes.py's `_build_short_id_relations` helper; `discover_ranges` and `load_range_data` are reused unchanged
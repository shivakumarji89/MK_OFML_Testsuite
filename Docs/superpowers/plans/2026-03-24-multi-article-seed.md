# Multi-Article Seed Support — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Parse all articles from a multi-article seed OBX, group them by property-name signature, and present each group as a tab with an article-selection column.

**Architecture:** `seed_parser.py` is extended to parse all bskArticle elements and extract short description labels. `routes.py` groups articles by property-name frozenset, stores per-article XML templates, and returns a `groups` array. A new `build_obx_from_multi_seed` function in `generator.py` generates one OBX across multiple articles with per-article class maps. The frontend tab strip replaces the seed-info bar; each tab owns independent dimension state and an article checkbox column.

**Tech Stack:** Python 3.11 · FastAPI · Pydantic · Vanilla JS · Tailwind CSS (CDN) · pytest

---

## Chunk 1: Backend — seed_parser.py + generator.py

### Task 1: Extend seed_parser to parse all articles and extract short descriptions

**Files:**
- Modify: `modules/snapper/seed_parser.py`
- Modify: `tests/test_seed_parser.py`

The function signature and return shape change. Callers (only `routes.py`) must be updated in Task 3.

- [ ] **Step 1: Update `test_parse_seed_uses_first_article_only` to reflect new multi-article behaviour**

Open `tests/test_seed_parser.py`. The existing test asserts only the first article is used — this is exactly the behaviour we are removing.

Verify that `MULTI_ARTICLE_XML` is already present in `tests/test_seed_parser.py` with exactly this content (it was added in an earlier version of the test file):

```python
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
```

If it is already present with this exact structure, do NOT add it again. If it is missing or has a different structure, add/replace it.

Then replace `test_parse_seed_uses_first_article_only` with tests for the new `articles` list return:

```python
# Replace the single test_parse_seed_uses_first_article_only test with these:

def test_parse_seed_returns_all_articles():
    """parse_seed returns all bskArticle elements."""
    result = parse_seed(MULTI_ARTICLE_XML)
    assert len(result["articles"]) == 2


def test_parse_seed_multi_article_codes():
    result = parse_seed(MULTI_ARTICLE_XML)
    codes = [a["article"] for a in result["articles"]]
    assert codes == ["NOCLE4", "NOCLE5"]


def test_parse_seed_multi_article_properties():
    """Each article carries its own properties list."""
    result = parse_seed(MULTI_ARTICLE_XML)
    first = result["articles"][0]
    assert len(first["properties"]) == 1
    assert first["properties"][0]["seed_value"] == "R00"
    second = result["articles"][1]
    assert second["properties"][0]["seed_value"] == "SL"
```

Also add a test for label extraction. Add this XML fixture near the top of the file:

```python
LABELLED_SEED_XML = """<cutBuffer>
  <items>
    <bskArticle>
      <manufacturer id='HM'/>
      <series id='HATCH'/>
      <artNr type='base'>NOHAN1</artNr>
      <artNr type='ofmlvarcode'>HATCH_OPT.Base_Finish=R00</artNr>
      <description type='short'>
        <text lang='de'>Hatch - Sitz</text>
        <text lang='en'>Hatch - Single seat</text>
      </description>
    </bskArticle>
    <bskArticle>
      <manufacturer id='HM'/>
      <series id='HATCH'/>
      <artNr type='base'>NOHAN2</artNr>
      <artNr type='ofmlvarcode'>HATCH_OPT.Base_Finish=SL</artNr>
      <description type='short'>
        <text lang='fr'>Hatch - Double</text>
      </description>
    </bskArticle>
    <bskArticle>
      <manufacturer id='HM'/>
      <series id='HATCH'/>
      <artNr type='base'>NOHAN3</artNr>
      <artNr type='ofmlvarcode'>HATCH_OPT.Base_Finish=SL</artNr>
    </bskArticle>
  </items>
</cutBuffer>"""
```

Add label tests:

```python
def test_parse_seed_label_english_preferred():
    result = parse_seed(LABELLED_SEED_XML)
    assert result["articles"][0]["label"] == "Hatch - Single seat"


def test_parse_seed_label_fallback_to_first_language():
    """No English text present — fall back to first available language."""
    result = parse_seed(LABELLED_SEED_XML)
    assert result["articles"][1]["label"] == "Hatch - Double"


def test_parse_seed_label_none_when_no_description():
    result = parse_seed(LABELLED_SEED_XML)
    assert result["articles"][2]["label"] is None
```

Also update the existing single-article tests so they read from `result["articles"][0]` instead of `result` directly:

```python
def test_parse_seed_returns_article_code():
    result = parse_seed(CLOUD_SEED_XML)
    assert result["articles"][0]["article"] == "NOCLE4"


def test_parse_seed_returns_manufacturer():
    result = parse_seed(CLOUD_SEED_XML)
    assert result["manufacturer"] == "HM"


def test_parse_seed_returns_series():
    result = parse_seed(CLOUD_SEED_XML)
    assert result["series"] == "CLOUD"


def test_parse_seed_returns_properties_list():
    result = parse_seed(CLOUD_SEED_XML)
    assert isinstance(result["articles"][0]["properties"], list)
    assert len(result["articles"][0]["properties"]) == 6


def test_parse_seed_first_property_type():
    result = parse_seed(CLOUD_SEED_XML)
    first = result["articles"][0]["properties"][0]
    assert first["name"] == "Type"
    assert first["article_class"] == "CLOUD_ATTR_ARM_CHAIR"
    assert first["seed_value"] == "10"


def test_parse_seed_second_property_base_finish():
    result = parse_seed(CLOUD_SEED_XML)
    second = result["articles"][0]["properties"][1]
    assert second["name"] == "Base_Finish"
    assert second["article_class"] == "CLOUD_OPT"
    assert second["seed_value"] == "R00"


def test_parse_seed_fabric_type_and_colour():
    result = parse_seed(CLOUD_SEED_XML)
    props_by_name = {p["name"]: p for p in result["articles"][0]["properties"]}
    assert "Shell_Fabric_Type" in props_by_name
    assert props_by_name["Shell_Fabric_Type"]["seed_value"] == "1HA"
    assert "Shell_Fabric_Colour" in props_by_name
    assert props_by_name["Shell_Fabric_Colour"]["seed_value"] == "1HA02"


def test_parse_seed_minimal_xml():
    result = parse_seed(MINIMAL_SEED_XML)
    assert result["articles"][0]["article"] == "FLC142"
    assert result["series"] == "COSM"
    assert len(result["articles"][0]["properties"]) == 2
    assert result["articles"][0]["properties"][0]["name"] == "Arms"
    assert result["articles"][0]["properties"][1]["name"] == "Back_Height"


def test_parse_seed_skips_malformed_varcode_segments():
    xml = """<cutBuffer><items><bskArticle>
      <manufacturer id='HM'/>
      <series id='CLOUD'/>
      <artNr type='base'>NOCLE4</artNr>
      <artNr type='ofmlvarcode'>CLOUD_OPT.Base_Finish=R00;MALFORMED;ALSO_BAD</artNr>
    </bskArticle></items></cutBuffer>"""
    result = parse_seed(xml)
    assert len(result["articles"][0]["properties"]) == 1
    assert result["articles"][0]["properties"][0]["name"] == "Base_Finish"
```

- [ ] **Step 2: Run tests — expect failures**

```
cd C:\Users\XMAMWU\Projects\MK_OFML_Testsuite
python -m pytest tests/test_seed_parser.py -v 2>&1 | head -60
```

Expected: multiple failures (`KeyError: 'articles'`, `AttributeError`, etc.)

- [ ] **Step 3: Implement the new `seed_parser.py`**

Replace the entire contents of `modules/snapper/seed_parser.py` with:

```python
import xml.etree.ElementTree as ET


class SeedParseError(ValueError):
    """Raised when the OBX XML is malformed or missing required fields."""
    pass


def parse_seed(xml_string: str) -> dict:
    """
    Parse a pCon OBX XML string and extract seed data from ALL bskArticle elements.

    Returns:
        {
            "manufacturer": str,
            "series": str,
            "articles": [
                {
                    "article": str,        # base article code
                    "label": str | None,   # short description (English preferred)
                    "properties": [
                        {"name": str, "article_class": str, "seed_value": str},
                        ...
                    ],
                    "article_xml": str,    # serialised bskArticle element (for seed templates)
                },
                ...
            ],
            "raw_xml": str,
        }

    Raises:
        SeedParseError: if the XML is malformed, no bskArticle found,
                        or required fields are missing in the first article.
    """
    try:
        root = ET.fromstring(xml_string)
    except ET.ParseError as e:
        raise SeedParseError(f"Invalid XML: {e}") from e

    article_elements = root.findall(".//bskArticle")
    if not article_elements:
        raise SeedParseError("No <bskArticle> element found in OBX")

    # manufacturer and series are read from the first article (shared across all)
    first = article_elements[0]
    mfr_el = first.find("manufacturer")
    if mfr_el is None or not mfr_el.get("id"):
        raise SeedParseError("Missing <manufacturer id='...'> in bskArticle")
    manufacturer = mfr_el.get("id")

    series_el = first.find("series")
    if series_el is None or not series_el.get("id"):
        raise SeedParseError("Missing <series id='...'> in bskArticle")
    series = series_el.get("id")

    articles = []
    for article_el in article_elements:
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
        label = _extract_short_description(article_el)
        article_xml = ET.tostring(article_el, encoding="unicode")

        articles.append({
            "article": article_code,
            "label": label,
            "properties": properties,
            "article_xml": article_xml,
        })

    return {
        "manufacturer": manufacturer,
        "series": series,
        "articles": articles,
        "raw_xml": xml_string,
    }


def _extract_short_description(article_el: ET.Element) -> str | None:
    """
    Extract the short description text from a bskArticle element.
    Prefers English; falls back to the first available language.
    Returns None if no short description element is present.
    """
    desc_el = next(
        (d for d in article_el.findall("description") if d.get("type") == "short"),
        None,
    )
    if desc_el is None:
        return None

    texts = desc_el.findall("text")
    if not texts:
        return None

    en_text = next((t for t in texts if t.get("lang") == "en"), None)
    if en_text is not None and en_text.text:
        return en_text.text.strip()

    first_text = next((t for t in texts if t.text), None)
    return first_text.text.strip() if first_text is not None else None


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

- [ ] **Step 4: Run seed_parser tests — expect all pass**

```
python -m pytest tests/test_seed_parser.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add modules/snapper/seed_parser.py tests/test_seed_parser.py
git commit -m "feat: parse all bskArticle elements with short description labels"
```

---

### Task 2: Add `build_obx_from_multi_seed` to generator.py

**Files:**
- Modify: `modules/snapper/generator.py`
- Modify: `tests/test_generator.py` (add new tests; existing tests untouched)

This new function handles generating one OBX across multiple articles, each with their own seed XML template and class maps.

- [ ] **Step 1: Write failing tests for `build_obx_from_multi_seed`**

Open `tests/test_generator.py`. Add at the end:

```python
from modules.snapper.generator import build_obx_from_multi_seed

# Minimal article XML templates for testing
_NOHAN1_XML = """<cutBuffer><items>
  <bskArticle basketId='aaa' itemType='BasketAggregate' updateState='UpToDate'>
    <manufacturer id='HM'/>
    <series id='HATCH'/>
    <artNr type='base'>NOHAN1</artNr>
    <artNr type='ofmlvarcode'>HATCH_ATTR_CHAIR.Type=20;HATCH_OPT.Base_Finish=R00</artNr>
    <artNr type='final' default='1'>NOHAN1_RESOLVED</artNr>
    <docCalculationChanges ppName='test'/>
  </bskArticle>
</items></cutBuffer>"""

_NOHAN2_XML = """<cutBuffer><items>
  <bskArticle basketId='bbb' itemType='BasketAggregate' updateState='UpToDate'>
    <manufacturer id='HM'/>
    <series id='HATCH'/>
    <artNr type='base'>NOHAN2</artNr>
    <artNr type='ofmlvarcode'>HATCH_ATTR_NEW.Type=20;HATCH_OPT.Base_Finish=R00</artNr>
    <artNr type='final' default='1'>NOHAN2_RESOLVED</artNr>
    <docCalculationChanges ppName='test'/>
  </bskArticle>
</items></cutBuffer>"""


def test_build_obx_from_multi_seed_single_article_two_perms():
    """Single article, two property permutations → two bskArticle elements."""
    perms = [
        {"article": "NOHAN1", "properties": {"Type": "20", "Base_Finish": "R00"}},
        {"article": "NOHAN1", "properties": {"Type": "20", "Base_Finish": "SL"}},
    ]
    article_seeds = {"NOHAN1": _NOHAN1_XML}
    article_class_maps = {
        "NOHAN1": {
            "property_to_class": {"Type": "HATCH_ATTR_CHAIR", "Base_Finish": "HATCH_OPT"},
            "prop_val_to_class": {},
        }
    }
    result = build_obx_from_multi_seed(article_seeds, perms, article_class_maps)
    assert result.count("<bskArticle") == 2


def test_build_obx_from_multi_seed_two_articles():
    """Two articles, one permutation each → two bskArticle elements."""
    perms = [
        {"article": "NOHAN1", "properties": {"Base_Finish": "R00"}},
        {"article": "NOHAN2", "properties": {"Base_Finish": "R00"}},
    ]
    article_seeds = {"NOHAN1": _NOHAN1_XML, "NOHAN2": _NOHAN2_XML}
    article_class_maps = {
        "NOHAN1": {
            "property_to_class": {"Base_Finish": "HATCH_OPT"},
            "prop_val_to_class": {},
        },
        "NOHAN2": {
            "property_to_class": {"Base_Finish": "HATCH_OPT"},
            "prop_val_to_class": {},
        },
    }
    result = build_obx_from_multi_seed(article_seeds, perms, article_class_maps)
    assert result.count("<bskArticle") == 2


def test_build_obx_from_multi_seed_uses_per_article_class():
    """Each article's varcode uses its own article class prefix."""
    perms = [
        {"article": "NOHAN1", "properties": {"Type": "20"}},
        {"article": "NOHAN2", "properties": {"Type": "20"}},
    ]
    article_seeds = {"NOHAN1": _NOHAN1_XML, "NOHAN2": _NOHAN2_XML}
    article_class_maps = {
        "NOHAN1": {
            "property_to_class": {"Type": "HATCH_ATTR_CHAIR"},
            "prop_val_to_class": {},
        },
        "NOHAN2": {
            "property_to_class": {"Type": "HATCH_ATTR_NEW"},
            "prop_val_to_class": {},
        },
    }
    result = build_obx_from_multi_seed(article_seeds, perms, article_class_maps)
    assert "HATCH_ATTR_CHAIR.Type=20" in result
    assert "HATCH_ATTR_NEW.Type=20" in result
```

- [ ] **Step 2: Run tests — expect ImportError / failure**

```
python -m pytest tests/test_generator.py -v -k "multi_seed" 2>&1 | head -30
```

Expected: ImportError (`cannot import name 'build_obx_from_multi_seed'`)

- [ ] **Step 3: Implement `build_obx_from_multi_seed` in generator.py**

Add at the end of `modules/snapper/generator.py`:

```python
def build_obx_from_multi_seed(
    article_seeds: dict[str, str],
    permutations: list[dict],
    article_class_maps: dict[str, dict],
) -> str:
    """
    Build one OBX from permutations across multiple articles, each with its own
    seed XML template and class maps.

    Args:
        article_seeds: {article_code: minimal_cutBuffer_xml_string}
            Each value is a full XML string containing exactly one bskArticle
            (the template for that article code).
        permutations: list of {article, properties} dicts (output of compute_permutations).
        article_class_maps: {article_code: {property_to_class, prop_val_to_class}}

    Returns:
        Pretty-printed OBX XML string with all permutations as bskArticle elements.
    """
    # Parse each article's seed XML and extract the bskArticle template element
    article_templates: dict[str, ET.Element] = {}
    article_old_varcodes: dict[str, str] = {}
    article_old_basket_ids: dict[str, str] = {}
    article_old_update_states: dict[str, str] = {}
    pp_name = ""
    version_str = ""

    for code, seed_xml in article_seeds.items():
        root = ET.fromstring(seed_xml)
        art = root.find(".//bskArticle")
        if art is None:
            continue
        article_templates[code] = art
        article_old_basket_ids[code] = art.get("basketId", "")
        article_old_update_states[code] = art.get("updateState", "UpToDate")

        old_varcode = ""
        for artnr in art.findall("artNr"):
            if artnr.get("type") == "ofmlvarcode":
                old_varcode = artnr.text or ""
                break
        article_old_varcodes[code] = old_varcode

        # pp_name: per-article minimal XMLs don't include docCalculationChanges,
        # so pp_name will be "" — this is acceptable; pCon still processes the OBX.
        if not version_str:
            ver_el = root.find("versionInfo")
            if ver_el is not None:
                version_str = ET.tostring(ver_el, encoding="unicode")

    # Build article string templates (with sentinel injected into final artNr)
    article_str_templates: dict[str, str] = {}
    for code, art_el in article_templates.items():
        tmpl = ET.fromstring(ET.tostring(art_el, encoding="unicode"))
        final = next((a for a in tmpl.findall("artNr") if a.get("type") == "final"), None)
        if final is None:
            final = ET.SubElement(tmpl, "artNr")
            final.set("type", "final")
            final.set("default", "1")
        final.text = SENTINEL
        article_str_templates[code] = ET.tostring(tmpl, encoding="unicode")

    article_blocks: list[str] = []
    basket_ids: list[str] = []

    for perm in permutations:
        code = perm["article"]
        tmpl_str = article_str_templates.get(code)
        if tmpl_str is None:
            continue

        maps = article_class_maps.get(code, {})
        ptc = maps.get("property_to_class", {})
        pvtc_raw = maps.get("prop_val_to_class", {})
        pvtc: dict[tuple, str] = {}
        for key_str, cls in pvtc_raw.items():
            eq = key_str.find("=")
            if eq != -1:
                pvtc[(key_str[:eq], key_str[eq + 1:])] = cls

        new_id = str(uuid.uuid4())
        basket_ids.append(new_id)

        varcode = build_varcode_multi(perm["properties"], ptc, pvtc)

        art = tmpl_str
        art = art.replace(
            f'basketId="{article_old_basket_ids[code]}"', f'basketId="{new_id}"', 1
        )
        art = art.replace(
            f'updateState="{article_old_update_states[code]}"',
            'updateState="Outdated"',
            1,
        )
        old_vc = article_old_varcodes.get(code, "")
        if old_vc:
            art = art.replace(f">{old_vc}</artNr>", f">{varcode}</artNr>", 1)

        desc_text = " | ".join(f"{k}={v}" for k, v in perm["properties"].items())
        if desc_text:
            new_long_desc = (
                f'<description type="long"><text lang="en">{desc_text}</text></description>'
            )
            new_art = re.sub(
                r'<description[^>]*\btype="long"[^>]*>.*?</description>',
                new_long_desc,
                art,
                count=1,
                flags=re.DOTALL,
            )
            art = new_art if new_art != art else art.replace(
                "</bskArticle>", f"{new_long_desc}</bskArticle>", 1
            )

        article_blocks.append(art)

    doc_calc_entries = "\n".join(
        f'    <itemCalculationChanges id="{bid}" />' for bid in basket_ids
    )
    doc_calc_open = (
        f'<docCalculationChanges ppName="{pp_name}">' if pp_name else "<docCalculationChanges>"
    )

    parts = [
        "<?xml version='1.0' encoding='UTF-8'?>",
        "<cutBuffer>",
        f'  <state sessionId="{uuid.uuid4()}" />',
        f"  {version_str}",
        "  <items>",
    ]
    for block in article_blocks:
        parts.append(f"    {block}")
    parts += [
        "  </items>",
        f"  {doc_calc_open}",
        doc_calc_entries,
        "  </docCalculationChanges>",
        "</cutBuffer>",
    ]

    return "\n".join(parts)
```

- [ ] **Step 4: Run generator tests — all pass**

```
python -m pytest tests/test_generator.py -v
```

Expected: all tests PASS including the three new `multi_seed` tests.

- [ ] **Step 5: Commit**

```bash
git add modules/snapper/generator.py tests/test_generator.py
git commit -m "feat: add build_obx_from_multi_seed for per-article class maps"
```

---

## Chunk 2: Backend — routes.py

### Task 3: Update `/parse-seed` to return groups

**Files:**
- Modify: `modules/snapper/routes.py`
- Modify: `tests/test_routes.py`

The response shape changes from flat fields to a `groups` array. The `/generate` endpoint also changes shape.

- [ ] **Step 1: Update `/parse-seed` integration tests**

In `tests/test_routes.py`, update the seed fixture to a multi-article HATCH seed that exercises grouping. Replace the file content with the following (keep all `/clean-obx` tests and the `_make_pcon_obx` / `_clean` helpers intact — only the parse-seed and generate tests change):

Add a second seed fixture for multi-article testing:

```python
# Add this fixture near CLOUD_SEED_XML:
HATCH_MULTI_SEED_XML = b"""<?xml version='1.0'?>
<cutBuffer>
  <state sessionId='test-session'/>
  <versionInfo vendorKey='EasternGraphics' appKey='EAI-Server' appVersion='4.18.3' bskXmlVersion='1.8.10'/>
  <items>
    <bskArticle basketId='aaa' itemType='BasketAggregate' updateState='UpToDate'>
      <manufacturer id='HM'/>
      <series id='HATCH'/>
      <artNr type='base'>NOHAN1</artNr>
      <artNr type='ofmlvarcode'>HATCH_ATTR_CHAIR.Type=20;HATCH_OPT.Base_Finish=R00</artNr>
      <description type='short'><text lang='en'>Hatch Single</text></description>
    </bskArticle>
    <bskArticle basketId='bbb' itemType='BasketAggregate' updateState='UpToDate'>
      <manufacturer id='HM'/>
      <series id='HATCH'/>
      <artNr type='base'>NOHAN2</artNr>
      <artNr type='ofmlvarcode'>HATCH_ATTR_NEW.Type=20;HATCH_OPT.Base_Finish=R00</artNr>
      <description type='short'><text lang='en'>Hatch Double</text></description>
    </bskArticle>
  </items>
</cutBuffer>"""
```

Replace the parse-seed integration tests:

```python
def test_parse_seed_returns_200():
    response = _upload_seed()
    assert response.status_code == 200


def test_parse_seed_returns_groups():
    data = _upload_seed().json()
    assert "groups" in data
    assert len(data["groups"]) >= 1


def test_parse_seed_group_has_required_fields():
    data = _upload_seed().json()
    group = data["groups"][0]
    assert "id" in group
    assert "articles" in group
    assert "property_columns" in group


def test_parse_seed_group_article_has_code_and_label():
    """seed_token lives on each article, not on the group."""
    data = _upload_seed().json()
    art = data["groups"][0]["articles"][0]
    assert "code" in art
    assert "label" in art
    assert "property_to_class" in art
    assert "prop_val_to_class" in art
    assert "seed_token" in art


def test_parse_seed_group_property_columns_populated():
    data = _upload_seed().json()
    cols = data["groups"][0]["property_columns"]
    assert len(cols) >= 1
    col = cols[0]
    assert "name" in col
    assert "values" in col
    assert "is_child" in col
    assert "parent" in col
    assert "mapping" in col


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
```

Replace the generate tests (keep `_doGenerate` helper and clean-obx tests unchanged):

```python
def _make_generate_payload(articles, selected_properties, seed_token=None):
    """Helper to build a /generate payload with the new multi-article shape."""
    return {
        "manufacturer": "HM",
        "series": "CLOUD",
        "filename": "test.obx",
        "seed_token": seed_token,
        "queue": [
            {
                "articles": articles,
                "selected_article_codes": [a["code"] for a in articles],
                "selected_properties": selected_properties,
                "child_resolutions": {},
                "filename": "test.obx",
            }
        ],
    }


def test_generate_single_article_returns_xml():
    articles = [
        {
            "code": "NOCLE4",
            "label": None,
            "property_to_class": {"Type": "CLOUD_ATTR_ARM_CHAIR", "Base_Finish": "CLOUD_OPT"},
            "prop_val_to_class": {
                "Type=10": "CLOUD_ATTR_ARM_CHAIR",
                "Base_Finish=R00": "CLOUD_OPT",
                "Base_Finish=SL": "CLOUD_OPT",
            },
            "seed_token": None,
        }
    ]
    payload = _make_generate_payload(
        articles,
        {"Type": ["10"], "Base_Finish": ["R00", "SL"]},
    )
    response = client.post("/api/snapper/generate", json=payload)
    assert response.status_code == 200
    assert "application/xml" in response.headers["content-type"]
    # 1 article * 1 Type * 2 Base_Finish = 2 permutations
    assert response.text.count("<bskArticle") == 2


def test_generate_obx_contains_correct_varcode():
    articles = [
        {
            "code": "NOCLE4",
            "label": None,
            "property_to_class": {"Type": "CLOUD_ATTR_ARM_CHAIR"},
            "prop_val_to_class": {"Type=10": "CLOUD_ATTR_ARM_CHAIR"},
            "seed_token": None,
        }
    ]
    payload = _make_generate_payload(articles, {"Type": ["10"]})
    response = client.post("/api/snapper/generate", json=payload)
    assert "CLOUD_ATTR_ARM_CHAIR.Type=10" in response.text


def test_generate_multiple_queue_items_returns_zip():
    """Two queue items → zip."""
    def _item(code):
        return {
            "articles": [
                {
                    "code": code,
                    "label": None,
                    "property_to_class": {"Base_Finish": "CLOUD_OPT"},
                    "prop_val_to_class": {"Base_Finish=R00": "CLOUD_OPT"},
                    "seed_token": None,
                }
            ],
            "selected_article_codes": [code],
            "selected_properties": {"Base_Finish": ["R00"]},
            "child_resolutions": {},
            "filename": f"{code}.obx",
        }

    payload = {
        "manufacturer": "HM",
        "series": "CLOUD",
        "filename": "test.obx",
        "queue": [_item("NOCLE4"), _item("NOCLE5")],
    }
    response = client.post("/api/snapper/generate", json=payload)
    assert response.status_code == 200
    assert "application/zip" in response.headers["content-type"]


def test_generate_empty_queue_returns_400():
    payload = {"manufacturer": "HM", "series": "CLOUD", "queue": [], "filename": "test.obx"}
    response = client.post("/api/snapper/generate", json=payload)
    assert response.status_code == 400
```

- [ ] **Step 2: Run route tests — expect failures**

```
python -m pytest tests/test_routes.py -v -k "parse_seed or generate" 2>&1 | head -60
```

Expected: failures on the parse-seed and generate tests (old response shape).

- [ ] **Step 3: Rewrite `/parse-seed` in routes.py**

In `modules/snapper/routes.py`, replace the `/parse-seed` endpoint body (the function `parse_seed_endpoint`) with the following.

**Important — keep these intact:**
- All existing imports at the top of the file
- The `_build_short_id_relations` helper function (existing, called by the new endpoint)
- The `expand_permutations_with_children` helper function (existing, called by the generate endpoint)
- The `_seed_store` dict and the `/clean-obx` endpoint
- Do NOT remove the old function body until Step 4 is also complete, since both endpoints change together

The grouping logic: group articles by `frozenset(prop["name"] for prop in article["properties"])`. Each group gets:
- `property_columns` from the first article in the group
- per-article `property_to_class` and `prop_val_to_class`
- a `seed_token` per article (minimal XML stored in `_seed_store`)

```python
@router.post("/parse-seed")
async def parse_seed_endpoint(
    file: UploadFile = File(...),
    repo: str = Form(...),
):
    raw = await file.read()
    try:
        xml_string = raw.decode("utf-8", errors="replace")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not decode file: {e}")

    try:
        seed = parse_seed(xml_string)
    except SeedParseError as e:
        raise HTTPException(status_code=422, detail=str(e))

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

    try:
        range_data = load_range_data(db_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load range data: {e}")

    short_id_relations = _build_short_id_relations(db_path)

    # Build values lookup: property_name -> list of {code, label}
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

    # Group articles by their property-name signature
    groups_map: dict[frozenset, list[dict]] = {}
    for article in seed["articles"]:
        sig = frozenset(p["name"] for p in article["properties"])
        groups_map.setdefault(sig, []).append(article)

    groups = []
    for group_idx, (sig, group_articles) in enumerate(groups_map.items()):
        # Build property_columns from the first article's property list
        first_article = group_articles[0]
        prop_names = [p["name"] for p in first_article["properties"]]

        hierarchies = detect_hierarchy(prop_names, range_data["values"], short_id_relations)
        already_child = {h["child"] for h in hierarchies}
        tbl_hierarchies = detect_hierarchy_from_tables(prop_names, range_data["values"], db_path)
        for h in tbl_hierarchies:
            if h["child"] not in already_child:
                hierarchies.append(h)
        child_map = {h["child"]: h for h in hierarchies}

        property_columns = []
        for prop in first_article["properties"]:
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

        # Build per-article info with class maps and individual seed tokens
        articles_out = []
        for article in group_articles:
            property_to_class: dict[str, str] = {}
            prop_val_to_class: dict[str, str] = {}
            for p in article["properties"]:
                property_to_class[p["name"]] = p["article_class"]
                for v in values_by_prop.get(p["name"], []):
                    prop_val_to_class[f"{p['name']}={v['code']}"] = p["article_class"]

            # Wrap the single article element in a minimal cutBuffer for use as a seed template
            article_seed_xml = (
                f"<?xml version='1.0' encoding='UTF-8'?>"
                f"<cutBuffer>"
                f"<versionInfo vendorKey='EasternGraphics' appKey='EAI-Server' "
                f"appVersion='4.18.3' bskXmlVersion='1.8.10'/>"
                f"<items>{article['article_xml']}</items>"
                f"</cutBuffer>"
            )
            article_token = str(uuid.uuid4())
            _seed_store[article_token] = article_seed_xml

            articles_out.append({
                "code": article["article"],
                "label": article["label"],
                "property_to_class": property_to_class,
                "prop_val_to_class": prop_val_to_class,
                "seed_token": article_token,
            })

        groups.append({
            "id": f"group-{group_idx}",
            "articles": articles_out,
            "property_columns": property_columns,
        })

    return {
        "manufacturer": seed["manufacturer"],
        "series": seed["series"],
        "repo": repo,
        "db_path": db_path,
        "groups": groups,
    }
```

- [ ] **Step 4: Update the `/generate` endpoint Pydantic models and logic**

In `modules/snapper/routes.py`, **delete** the existing `ChildResolution`, `QueueItem`, `GenerateRequest` Pydantic models AND the entire `generate_obx` function body. Replace all of them with the following. Do not leave any of the old model or function code in the file.

```python
class ArticleInfo(BaseModel):
    code: str
    label: str | None = None
    property_to_class: dict[str, str]
    prop_val_to_class: dict[str, str]
    seed_token: str | None = None


class ChildResolution(BaseModel):
    parent: str
    resolution: dict[str, list[str]]


class QueueItem(BaseModel):
    articles: list[ArticleInfo]
    selected_article_codes: list[str]
    selected_properties: dict[str, list[str]]
    child_resolutions: dict[str, ChildResolution] = {}
    filename: str = ""


class GenerateRequest(BaseModel):
    manufacturer: str
    series: str
    queue: list[QueueItem]
    filename: str = "snapper.obx"
    seed_token: str | None = None  # kept for backward compat; ignored (tokens are per-article)


@router.post("/generate")
def generate_obx(req: GenerateRequest):
    if not req.queue:
        raise HTTPException(status_code=400, detail="Queue is empty")

    obx_files: list[tuple[str, str]] = []

    for item in req.queue:
        # Filter to selected articles only
        selected_articles = [
            a for a in item.articles if a.code in item.selected_article_codes
        ]
        if not selected_articles:
            raise HTTPException(status_code=400, detail="No articles selected in queue item")

        selected_codes = [a.code for a in selected_articles]
        permutations = compute_permutations(selected_codes, item.selected_properties)

        child_res_dicts = {
            name: {"parent": cr.parent, "resolution": cr.resolution}
            for name, cr in item.child_resolutions.items()
        }
        permutations = expand_permutations_with_children(permutations, child_res_dicts)

        # Build per-article seed XMLs and class maps
        article_seeds: dict[str, str] = {}
        article_class_maps: dict[str, dict] = {}

        for art in selected_articles:
            seed_xml = _seed_store.get(art.seed_token) if art.seed_token else None
            if seed_xml:
                article_seeds[art.code] = seed_xml
            article_class_maps[art.code] = {
                "property_to_class": art.property_to_class,
                "prop_val_to_class": art.prop_val_to_class,
            }

        if article_seeds:
            # All selected articles have seed tokens (assigned during /parse-seed).
            # Use build_obx_from_multi_seed to generate one OBX across all of them.
            xml_content = build_obx_from_multi_seed(
                article_seeds, permutations, article_class_maps
            )
        else:
            # No seed templates — build generic OBX
            # Use the first article's class map (all should be identical for generic path)
            first_art = selected_articles[0]
            pvtc: dict[tuple, str] = {}
            for key_str, cls in first_art.prop_val_to_class.items():
                eq = key_str.find("=")
                if eq != -1:
                    pvtc[(key_str[:eq], key_str[eq + 1:])] = cls
            xml_content = build_obx(
                permutations,
                [a.code for a in selected_articles],
                req.manufacturer,
                req.series,
                first_art.property_to_class,
                pvtc,
            )

        entry_name = item.filename if item.filename else "snapper.obx"
        obx_files.append((entry_name, xml_content))

    if len(obx_files) == 1:
        filename, xml_content = obx_files[0]
        return Response(
            content=xml_content,
            media_type="application/xml",
            headers={"Content-Disposition": f'attachment; filename="{req.filename}"'},
        )

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

Also add `build_obx_from_multi_seed` to the generator import line at the top of `routes.py`:

```python
from .generator import compute_permutations, build_obx, build_obx_from_seed, build_obx_from_multi_seed, SENTINEL
```

Verify the hierarchy import already includes both functions (it should; no change needed):

```python
from .hierarchy import detect_hierarchy, detect_hierarchy_from_tables
```

- [ ] **Step 5: Run all backend tests**

```
python -m pytest tests/ -v --ignore=tests/snapper 2>&1 | tail -30
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add modules/snapper/routes.py modules/snapper/seed_parser.py tests/test_routes.py
git commit -m "feat: /parse-seed returns grouped articles; /generate accepts per-article class maps"
```

---

## Chunk 3: Frontend — index.html + snapper.js

### Task 4: Replace seed-info bar with tab strip and update state model

**Files:**
- Modify: `static/snapper/index.html`
- Modify: `static/snapper/snapper.js`

- [ ] **Step 1: Update index.html — replace seedInfo div with tabStrip**

In `static/snapper/index.html`, replace:

```html
      <div id="seedInfo" class="hidden mt-3 p-3 bg-blue-50 rounded text-sm text-blue-800">
        <span id="seedInfoText"></span>
      </div>
```

with:

```html
      <div id="tabStrip" class="hidden mt-3"></div>
```

- [ ] **Step 2: Update state variables in snapper.js**

At the top of `static/snapper/snapper.js`, replace:

```js
let currentSeed = null;
let currentPermCount = 0;
let queue = [];
```

with:

```js
let currentSeed = null;       // full parse-seed response: { manufacturer, series, groups, ... }
let currentGroupIndex = 0;    // index of the active tab
let groupStates = [];         // per-group UI state: [{ articleSelections, dimSelections }]
let currentPermCount = 0;
let queue = [];
```

- [ ] **Step 3: Update DOM refs — replace seedInfo with tabStrip**

In the DOM refs section, replace:

```js
const seedInfo         = document.getElementById('seedInfo');
const seedInfoText     = document.getElementById('seedInfoText');
```

with:

```js
const tabStrip         = document.getElementById('tabStrip');
```

- [ ] **Step 4: Update the parse-seed response handler**

**Note:** Steps 3 and 4 both touch the `parseSeedBtn` handler — apply them together in one edit session to avoid a transient `ReferenceError` on the removed `seedInfo` variable.

In the `parseSeedBtn` click handler, find and replace this exact block (lines 141–156 of the current file):

```js
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
```

Replace with:

```js
  seedStatus.textContent = '';
  parseSeedBtn.disabled = false;

  // Initialise per-group state
  groupStates = currentSeed.groups.map(() => ({
    articleSelections: null,   // null = all checked (default); set on first change
    dimSelections: {},         // { propName: [checkedValues] }
  }));
  currentGroupIndex = 0;

  tabStrip.classList.remove('hidden');
  dimensionArea.classList.remove('hidden');
  actionRow.classList.remove('hidden');

  renderTabStrip();
  renderDimensions();
  addToQueueBtn.disabled = false;
  updateFilenamePreview();
```

- [ ] **Step 5: Add `renderTabStrip` function**

Add after the DOM refs section:

```js
// ── Tab strip ─────────────────────────────────────────────────────────────────
function renderTabStrip() {
  tabStrip.innerHTML = '';
  if (!currentSeed) return;

  const nav = document.createElement('div');
  nav.className = 'flex gap-1 flex-wrap';

  currentSeed.groups.forEach((group, idx) => {
    const codes = group.articles.map(a => a.code);
    const label = codes.length === 1 ? codes[0] : codes.join(', ');

    const btn = document.createElement('button');
    btn.className = [
      'px-3 py-1.5 rounded text-sm font-medium border transition-colors',
      idx === currentGroupIndex
        ? 'bg-blue-600 text-white border-blue-600'
        : 'bg-white text-gray-600 border-gray-300 hover:border-blue-400 hover:text-blue-600',
    ].join(' ');
    btn.textContent = `${label} · ${group.property_columns.length} properties`;
    btn.addEventListener('click', () => switchTab(idx));
    nav.appendChild(btn);
  });

  tabStrip.appendChild(nav);
}

function switchTab(idx) {
  if (!currentSeed || idx === currentGroupIndex) return;
  _saveGroupState();
  currentGroupIndex = idx;
  renderTabStrip();
  renderDimensions();
  updateFilenamePreview();
}

function _saveGroupState() {
  if (!currentSeed || !groupStates[currentGroupIndex]) return;
  const state = groupStates[currentGroupIndex];

  // Save article selections
  state.articleSelections = _getArticleSelections();

  // Save dimension selections
  const dims = {};
  document.querySelectorAll('.dim-check:checked').forEach(cb => {
    if (!dims[cb.dataset.prop]) dims[cb.dataset.prop] = [];
    dims[cb.dataset.prop].push(cb.dataset.value);
  });
  state.dimSelections = dims;
}
```

- [ ] **Step 6: Update `renderDimensions` to support the article column and restore state**

Replace the existing `renderDimensions` function:

```js
function renderDimensions() {
  dimensionColumns.innerHTML = '';
  if (!currentSeed) return;

  const group = currentSeed.groups[currentGroupIndex];
  if (!group) return;

  const state = groupStates[currentGroupIndex] || {};

  // Article column — only shown for groups with 2+ articles
  if (group.articles.length > 1) {
    dimensionColumns.appendChild(_buildArticleColumn(group.articles, state.articleSelections));
  }

  const parentHasChild = new Map();
  for (const col of group.property_columns) {
    if (col.is_child) parentHasChild.set(col.parent, col.name);
  }

  for (const col of group.property_columns) {
    if (col.is_child) continue;
    const wrapper = document.createElement('div');
    wrapper.className = 'flex flex-col gap-1';
    wrapper.appendChild(
      _buildCheckboxColumn(col.name, col.values, col.seed_value, state.dimSelections)
    );
    const childName = parentHasChild.get(col.name);
    if (childName) {
      const childCol = group.property_columns.find(c => c.name === childName);
      if (childCol) wrapper.appendChild(_buildChildColumn(childCol));
    }
    dimensionColumns.appendChild(wrapper);
  }
  updatePermCount();
}
```

**Note:** Child column selections (`.child-check`) are not persisted across tab switches in this implementation — they reset to unchecked when switching back to a tab. This is an acceptable limitation for the initial release; only parent property (`.dim-check`) and article selections are saved.

```js```

- [ ] **Step 7: Add `_buildArticleColumn` function**

Add after `_buildChildColumn`:

```js
function _buildArticleColumn(articles, savedSelections) {
  const col = document.createElement('div');
  col.className = 'bg-white rounded-lg shadow p-3 min-w-44 max-w-56 flex flex-col';
  col.dataset.propName = '__article__';

  // All checked by default; restore saved state if present
  const checkedSet = savedSelections
    ? new Set(savedSelections)
    : new Set(articles.map(a => a.code));

  col.innerHTML = `
    <div class="font-semibold text-sm text-gray-700 mb-2 border-b pb-1">Article</div>
    <div class="flex gap-1 mb-2">
      <button class="text-xs text-blue-600 hover:underline select-all-btn">All</button>
      <span class="text-gray-300">|</span>
      <button class="text-xs text-blue-600 hover:underline select-none-btn">None</button>
    </div>
    <div class="overflow-y-auto max-h-64 space-y-1">
      ${articles.map(a => `
        <label class="flex items-center gap-1 text-xs text-gray-700 cursor-pointer">
          <input type="checkbox" class="article-check" data-code="${escapeHtml(a.code)}"
            ${checkedSet.has(a.code) ? 'checked' : ''}>
          <span class="font-mono text-gray-500">${escapeHtml(a.code)}</span>
          ${a.label ? `<span class="text-gray-300">·</span><span class="truncate">${escapeHtml(a.label)}</span>` : ''}
        </label>`).join('')}
    </div>`;

  col.querySelector('.select-all-btn').addEventListener('click', () => {
    col.querySelectorAll('.article-check').forEach(cb => { cb.checked = true; });
    onDimensionChange();
  });
  col.querySelector('.select-none-btn').addEventListener('click', () => {
    col.querySelectorAll('.article-check').forEach(cb => { cb.checked = false; });
    onDimensionChange();
  });
  col.querySelectorAll('.article-check').forEach(cb => cb.addEventListener('change', onDimensionChange));
  return col;
}

function _getArticleSelections() {
  const checked = [];
  document.querySelectorAll('.article-check:checked').forEach(cb => checked.push(cb.dataset.code));
  return checked.length > 0 ? checked : null;
}
```

- [ ] **Step 8: Update `_buildCheckboxColumn` to accept and restore saved selections**

Update the function signature and pre-check logic:

```js
function _buildCheckboxColumn(propName, values, seedValue, savedDimSelections) {
  const col = document.createElement('div');
  col.className = 'bg-white rounded-lg shadow p-3 min-w-44 max-w-56 flex flex-col';
  col.dataset.propName = propName;

  // Use saved selections if present; otherwise pre-check seed value
  const savedVals = savedDimSelections && savedDimSelections[propName];

  col.innerHTML = `
    <div class="font-semibold text-sm text-gray-700 mb-2 border-b pb-1" title="${escapeHtml(propName)}">${escapeHtml(propName)}</div>
    <div class="flex gap-1 mb-2">
      <button class="text-xs text-blue-600 hover:underline select-all-btn">All</button>
      <span class="text-gray-300">|</span>
      <button class="text-xs text-blue-600 hover:underline select-none-btn">None</button>
    </div>
    <div class="overflow-y-auto max-h-64 space-y-1">
      ${values.map(v => {
        const isChecked = savedVals
          ? savedVals.includes(v.code)
          : v.code === seedValue;
        return `
          <label class="flex items-center gap-1 text-xs text-gray-700 cursor-pointer">
            <input type="checkbox" class="dim-check" data-prop="${escapeHtml(propName)}" data-value="${escapeHtml(v.code)}"
              ${isChecked ? 'checked' : ''}>
            <span class="font-mono text-gray-500">${escapeHtml(v.code)}</span>
            ${v.label && v.label !== v.code ? `<span class="text-gray-300">·</span><span class="truncate">${escapeHtml(v.label)}</span>` : ''}
          </label>`;
      }).join('')}
    </div>`;

  col.querySelector('.select-all-btn').addEventListener('click', () => {
    col.querySelectorAll('.dim-check').forEach(cb => { cb.checked = true; });
    onDimensionChange();
  });
  col.querySelector('.select-none-btn').addEventListener('click', () => {
    col.querySelectorAll('.dim-check').forEach(cb => { cb.checked = false; });
    onDimensionChange();
  });
  col.querySelectorAll('.dim-check').forEach(cb => cb.addEventListener('change', onDimensionChange));
  return col;
}
```

- [ ] **Step 9: Update `updatePermCount` to include article dimension**

In `updatePermCount`, before computing `factors`, add the article count as a factor:

```js
function updatePermCount() {
  if (!currentSeed) { permCount.textContent = ''; return; }

  const group = currentSeed.groups[currentGroupIndex];
  if (!group) return;

  const sel = getParentSelections();
  const childSel = getChildSelections();

  const parentProps = new Set(
    group.property_columns.filter(c => c.is_child).map(c => c.parent)
  );

  const factors = [];

  // Article dimension (only relevant for multi-article groups)
  if (group.articles.length > 1) {
    const articleCount = document.querySelectorAll('.article-check:checked').length;
    if (articleCount > 0) factors.push(articleCount);
  }

  for (const col of group.property_columns) {
    if (col.is_child || parentProps.has(col.name)) continue;
    const n = (sel[col.name] || []).length;
    if (n > 0) factors.push(n);
  }

  for (const childCol of group.property_columns.filter(c => c.is_child)) {
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
  currentPermCount = count;
  permCount.textContent = `${count.toLocaleString()} permutations`;
  permCount.className = 'text-sm font-medium ' + (
    count > ERROR_LIMIT ? 'text-red-600' :
    count > WARN_LIMIT  ? 'text-amber-600' : 'text-gray-700'
  );
  if (count > ERROR_LIMIT) permCount.textContent += ` ⚠ Consider splitting (max: ${ERROR_LIMIT})`;

  // Disable Add to Queue if no articles selected in multi-article groups
  if (group.articles.length > 1) {
    const articleCount = document.querySelectorAll('.article-check:checked').length;
    addToQueueBtn.disabled = articleCount === 0 || count === 0;
  } else {
    addToQueueBtn.disabled = count === 0;
  }

  updateFilenamePreview();
}
```

- [ ] **Step 10: Update `getParentSelections` and `getChildSelections` to be group-aware**

`getParentSelections` and `getChildSelections` already work by querying the DOM — they need no change. The DOM always reflects the active group's columns. No change needed.

- [ ] **Step 11: Update `updateFilenamePreview` and `assembleFilename`**

`assembleFilename` currently takes `article` as a string. Update `updateFilenamePreview` to compute the right article token:

```js
function updateFilenamePreview() {
  if (!currentSeed) { filenamePreview.textContent = ''; return; }
  const group = currentSeed.groups[currentGroupIndex];
  if (!group) return;
  filenamePreview.textContent = assembleFilename(
    currentSeed.series, _resolveArticleToken(group), articleLabel.value, 'Raw'
  );
}

function _resolveArticleToken(group) {
  if (group.articles.length === 1) return group.articles[0].code;
  const checked = document.querySelectorAll('.article-check:checked');
  if (checked.length === 1) return checked[0].dataset.code;
  return 'multiple_articles';
}
```

- [ ] **Step 12: Update `buildClassMaps` to be group-aware**

Replace `buildClassMaps`:

```js
function buildClassMaps() {
  if (!currentSeed) return { propertyToClass: {}, propValToClass: {} };
  const group = currentSeed.groups[currentGroupIndex];
  if (!group) return { propertyToClass: {}, propValToClass: {} };
  // Use the first article's class maps for display purposes; per-article maps are
  // sent to the server via the articles array.
  const first = group.articles[0];
  return {
    propertyToClass: { ...first.property_to_class },
    propValToClass: { ...first.prop_val_to_class },
  };
}
```

- [ ] **Step 13: Update `addToQueueBtn` handler**

Replace the existing click handler:

```js
addToQueueBtn.addEventListener('click', () => {
  if (!currentSeed) return;
  const group = currentSeed.groups[currentGroupIndex];
  if (!group) return;

  const parentSelections = getParentSelections();
  const label = articleLabel.value.trim();

  // Determine selected articles
  let selectedArticles;
  if (group.articles.length === 1) {
    selectedArticles = group.articles;
  } else {
    const checkedCodes = new Set(
      [...document.querySelectorAll('.article-check:checked')].map(cb => cb.dataset.code)
    );
    selectedArticles = group.articles.filter(a => checkedCodes.has(a.code));
  }
  if (selectedArticles.length === 0) return;

  const articleToken = selectedArticles.length === 1
    ? selectedArticles[0].code
    : 'multiple_articles';

  const filename = assembleFilename(currentSeed.series, articleToken, label, 'Raw');

  queue.push({
    id: crypto.randomUUID(),
    state: 'red',
    label,
    filename,
    series: currentSeed.series,
    manufacturer: currentSeed.manufacturer,
    // New multi-article fields
    articles: selectedArticles.map(a => ({
      code: a.code,
      label: a.label,
      property_to_class: a.property_to_class,
      prop_val_to_class: a.prop_val_to_class,
      seed_token: a.seed_token,
    })),
    selectedArticleCodes: selectedArticles.map(a => a.code),
    selectedProperties: parentSelections,
    childResolutions: getChildSelections(),
    count: currentPermCount,
    keptCount: null,
    removedCount: null,
  });

  articleLabel.value = '';
  updateFilenamePreview();
  saveQueue();
  renderQueue();
});
```

- [ ] **Step 14: Update `_doGenerate` payload to use the new API shape**

In `_doGenerate`, replace the `const payload = { ... };` block (the whole object literal, ending before `const controller = new AbortController()`). The new payload removes the top-level `seed_token` field (tokens are now per-article in the `articles` array) and uses `articles` + `selected_article_codes` instead of a single article:

```js
  const payload = {
    manufacturer: items[0].manufacturer,
    series: items[0].series,
    filename,
    queue: items.map(e => ({
      articles: e.articles,
      selected_article_codes: e.selectedArticleCodes,
      selected_properties: e.selectedProperties,
      child_resolutions: e.childResolutions || {},
      filename: e.filename,
    })),
  };
  // continue with: const controller = new AbortController(); (unchanged)
```

- [ ] **Step 15: Update `buildCard` in queue rendering — `assembleFilename` for Clean card**

In the green card branch of `buildCard`, the Clean filename uses `item.article`. Update:

```js
  } else if (item.state === 'green') {
    card.classList.add('border-green-400', 'bg-green-50');
    const articleToken = item.selectedArticleCodes?.length === 1
      ? item.selectedArticleCodes[0]
      : 'multiple_articles';
    const cleanName = assembleFilename(item.series, articleToken, item.label, 'Clean');
    // ... rest unchanged
```

Also in the `cleanItem` function (around line 654 in snapper.js), find:

```js
  a.download = assembleFilename(item.series, item.article, item.label, 'Clean');
```

Replace with:

```js
  a.download = assembleFilename(
    item.series,
    item.selectedArticleCodes?.length === 1 ? item.selectedArticleCodes[0] : 'multiple_articles',
    item.label,
    'Clean'
  );
```

- [ ] **Step 16: Smoke test in the browser**

Start the server (`python main.py` in `C:\Users\XMAMWU\Projects\MK_OFML_Testsuite`) and open http://localhost:8080/snapper/.

Upload `C:\Users\XMAMWU\Downloads\Project_240326-072553.obx`.

Expected:
- Two tabs appear: one labelled `NOHAN1, NOHAN2 · 6 properties`, one labelled `NOHAN1 · 8 properties`
- First tab shows an Article column with `NOHAN1 · Hatch Single` and `NOHAN2 · Hatch Double`
- Permutation count multiplies article count × property combos
- Second tab shows no Article column; just property columns including extra fabric properties
- Filename preview uses `multiple_articles` when both articles are checked, article code when only one

- [ ] **Step 17: Commit**

```bash
git add static/snapper/index.html static/snapper/snapper.js
git commit -m "feat: multi-article tab strip with article column and per-article generation"
```

---

## Chunk 4: Integration wiring — fix generate for no-seed-token path and queue persistence

### Task 5: Fix queue persistence and `assembleZipFilename` for multi-article items

**Files:**
- Modify: `static/snapper/snapper.js`

Old queue items (loaded from localStorage) have `article` not `articles`. Need a migration shim so the old format still loads correctly.

- [ ] **Step 1: Add queue migration in `loadQueue`**

Replace `loadQueue`:

```js
function loadQueue() {
  try {
    const saved = localStorage.getItem(QUEUE_STORAGE_KEY);
    if (saved) {
      const raw = JSON.parse(saved);
      // Migrate old-format items (pre-multi-article) if needed
      queue = raw.map(item => {
        if (!item.articles && item.article) {
          return {
            ...item,
            articles: [{
              code: item.article,
              label: null,
              property_to_class: item.propertyToClass || {},
              prop_val_to_class: item.propValToClass || {},
              seed_token: item.seedToken || null,
            }],
            selectedArticleCodes: [item.article],
            selectedProperties: item.selectedProperties || {},
            childResolutions: item.childResolutions || {},
          };
        }
        return item;
      });
    }
  } catch { queue = []; }
}
```

- [ ] **Step 2: Update `assembleZipFilename` usage in Generate All**

In the `generateAllBtn` click handler, the zip filename uses `redItems[0].article`. Update:

```js
  const articleToken = redItems.length === 1 && redItems[0].selectedArticleCodes?.length === 1
    ? redItems[0].selectedArticleCodes[0]
    : 'multiple_articles';
  const filename = redItems.length === 1
    ? redItems[0].filename
    : assembleZipFilename(redItems[0].series, articleToken).replace('.zip', '.obx');
```

Also update the download filename in `_doGenerate`:
```js
  a.download = contentType.includes('zip')
    ? assembleZipFilename(
        items[0].series,
        items[0].selectedArticleCodes?.length === 1 ? items[0].selectedArticleCodes[0] : 'multiple_articles'
      )
    : filename;
```

- [ ] **Step 3: Run full backend test suite one more time**

```
python -m pytest tests/ -v 2>&1 | tail -20
```

Expected: all tests PASS.

- [ ] **Step 4: Final commit**

```bash
git add static/snapper/snapper.js
git commit -m "fix: queue migration shim and zip filename for multi-article items"
```

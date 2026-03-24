import pytest
import xml.etree.ElementTree as ET
from modules.snapper.generator import compute_permutations, build_varcode, build_obx
from modules.snapper.generator import build_obx_from_seed, SENTINEL


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


# ── Sentinel tests ─────────────────────────────────────────────────────────────

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
    """Single article, two property permutations -> two bskArticle elements."""
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
    """Two articles, one permutation each -> two bskArticle elements."""
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

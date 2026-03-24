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


# ── Multi-article tests ────────────────────────────────────────────────────────

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


# ── Label extraction tests ─────────────────────────────────────────────────────

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


# ── Happy path tests ──────────────────────────────────────────────────────────

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

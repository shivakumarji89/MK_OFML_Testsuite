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

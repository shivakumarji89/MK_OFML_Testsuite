import pytest
import xml.etree.ElementTree as ET
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

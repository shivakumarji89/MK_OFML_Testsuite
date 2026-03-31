import xml.etree.ElementTree as ET
from modules.sku_importer.obx_builder import build_import_obx


def test_build_import_obx_produces_xml():
    items = [
        {
            "article": "AER1B31",
            "manufacturer_code": "HM",
            "series_code": "AERON",
            "prog_id": "@hmx_aeron",
            "properties": {"Arm_Type": "LP", "Frame_Finish": "BK"},
            "property_to_class": {"Arm_Type": "AERON_NORM", "Frame_Finish": "AERON_NORM"},
        }
    ]
    xml_str = build_import_obx(items)
    root = ET.fromstring(xml_str)
    assert root.tag == "cutBuffer"


def test_build_import_obx_update_state_outdated():
    items = [
        {
            "article": "AER1B31",
            "manufacturer_code": "HM",
            "series_code": "AERON",
            "prog_id": "@hmx_aeron",
            "properties": {"Arm_Type": "LP"},
            "property_to_class": {"Arm_Type": "AERON_NORM"},
        }
    ]
    xml_str = build_import_obx(items)
    root = ET.fromstring(xml_str)
    article = root.find(".//bskArticle")
    assert article is not None
    assert article.get("updateState") == "Outdated"


def test_build_import_obx_has_pd_info():
    items = [
        {
            "article": "AER1B31",
            "manufacturer_code": "HM",
            "series_code": "AERON",
            "prog_id": "@hmx_aeron",
            "properties": {"Arm_Type": "LP"},
            "property_to_class": {"Arm_Type": "AERON_NORM"},
        }
    ]
    xml_str = build_import_obx(items)
    root = ET.fromstring(xml_str)
    pd_info = root.find(".//pdInfo")
    assert pd_info is not None
    assert pd_info.get("progId") == "@hmx_aeron"


def test_build_import_obx_varcode_uses_property_to_class():
    items = [
        {
            "article": "ART1",
            "manufacturer_code": "MFR",
            "series_code": "SER",
            "prog_id": "@mfr_range",
            "properties": {"Color": "BK"},
            "property_to_class": {"Color": "MY_CLASS"},
        }
    ]
    xml_str = build_import_obx(items)
    root = ET.fromstring(xml_str)
    varcodes = [a.text for a in root.findall(".//artNr") if a.get("type") == "ofmlvarcode"]
    assert any("MY_CLASS.Color=BK" in (v or "") for v in varcodes)

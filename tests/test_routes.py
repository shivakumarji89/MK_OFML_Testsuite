import io
import pytest
import xml.etree.ElementTree as ET
from fastapi.testclient import TestClient
from main import app
from modules.snapper.generator import SENTINEL

client = TestClient(app)

REPO_ROOT = r"C:\HermanMillerOFMLSVN\Staging\HermanMiller\_repository"

# ── OBX fixtures ───────────────────────────────────────────────────────────────

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


# ── /generate integration tests ───────────────────────────────────────────────

def _make_generate_payload(articles, selected_properties, seed_token=None):
    """Helper to build a /generate payload with the multi-article shape."""
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
    """Two queue items -> zip."""
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


# ── /clean-obx tests ───────────────────────────────────────────────────────────

def _make_pcon_obx(articles: list[tuple[str, str | None]]) -> bytes:
    """Build a minimal pCon-style OBX. articles: [(base_artnr, final_artnr_or_None)]"""
    item_blocks = []
    for i, (base, final) in enumerate(articles):
        final_el = f'<artNr type="final">{final}</artNr>' if final is not None else ""
        item_blocks.append(
            f'<bskArticle basketId="bid-{i}" itemType="BasketArticle" updateState="UpToDate">'
            f'<manufacturer id="HM"/><series id="test"/>'
            f'<artNr type="base">{base}</artNr>{final_el}'
            f'</bskArticle>'
        )
    calc_entries = "".join(f'<itemCalculationChanges id="bid-{i}"/>' for i in range(len(articles)))
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<cutBuffer><state sessionId="t"/>'
        f'<items>{"".join(item_blocks)}</items>'
        f'<docCalculationChanges ppName="p">{calc_entries}</docCalculationChanges>'
        f'</cutBuffer>'
    ).encode()


def _clean(obx_bytes: bytes, label: str = "Low tables"):
    return client.post(
        "/api/snapper/clean-obx",
        data={"label": label},
        files={"file": ("pcon.obx", io.BytesIO(obx_bytes), "application/xml")},
    )


def test_clean_obx_returns_200():
    resp = _clean(_make_pcon_obx([("T01", "REAL")]))
    assert resp.status_code == 200


def test_clean_obx_removes_sentinel_articles():
    obx = _make_pcon_obx([("T01", "REAL"), ("T02", SENTINEL), ("T03", "REAL2")])
    resp = _clean(obx)
    root = ET.fromstring(resp.content)
    assert len(root.findall(".//bskArticle")) == 2


def test_clean_obx_kept_and_removed_headers():
    obx = _make_pcon_obx([("T01", "REAL"), ("T02", SENTINEL), ("T03", "REAL2")])
    resp = _clean(obx)
    assert resp.headers["X-Kept-Count"] == "2"
    assert resp.headers["X-Removed-Count"] == "1"


def test_clean_obx_filename_contains_label():
    resp = _clean(_make_pcon_obx([("T01", "REAL")]), label="Low tables")
    assert "Low_tables_Clean.obx" in resp.headers["Content-Disposition"]


def test_clean_obx_empty_label():
    resp = _clean(_make_pcon_obx([("T01", "REAL")]), label="")
    assert "Clean.obx" in resp.headers["Content-Disposition"]


def test_clean_obx_removes_doc_calc_entries():
    obx = _make_pcon_obx([("T01", "REAL"), ("T02", SENTINEL)])
    resp = _clean(obx)
    root = ET.fromstring(resp.content)
    doc_calc = root.find("docCalculationChanges")
    assert doc_calc is not None
    assert len(doc_calc.findall("itemCalculationChanges")) == 1


def test_clean_obx_all_valid():
    obx = _make_pcon_obx([("T01", "CODE1"), ("T02", "CODE2")])
    resp = _clean(obx)
    assert resp.headers["X-Kept-Count"] == "2"
    assert resp.headers["X-Removed-Count"] == "0"

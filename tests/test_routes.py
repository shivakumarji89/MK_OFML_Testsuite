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


def test_parse_seed_columns_have_hierarchy_fields():
    """Each property column has the required hierarchy-related fields."""
    data = _upload_seed().json()
    for col in data["property_columns"]:
        assert "is_child" in col
        assert "parent" in col
        assert "mapping" in col


def test_parse_seed_non_child_columns_have_null_parent():
    """Columns that aren't children have null parent and mapping."""
    data = _upload_seed().json()
    non_children = [c for c in data["property_columns"] if not c["is_child"]]
    assert len(non_children) > 0
    for col in non_children:
        assert col["parent"] is None
        assert col["mapping"] is None


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

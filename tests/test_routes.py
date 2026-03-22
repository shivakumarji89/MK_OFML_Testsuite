import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

REPO_ROOT = r"C:\HermanMillerOFMLSVN\Staging\HermanMiller\_repository"


def test_list_ranges():
    response = client.get(f"/api/snapper/ranges?repo={REPO_ROOT}")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert any(r["manufacturer"] == "hmx" and r["range"] == "cosm" for r in data)


def test_load_range():
    response = client.get(
        f"/api/snapper/range?repo={REPO_ROOT}&manufacturer=hmx&range=cosm"
    )
    assert response.status_code == 200
    data = response.json()
    assert "articles" in data
    assert "properties" in data
    assert "values" in data
    assert len(data["articles"]) > 0


def test_load_range_invalid_returns_404():
    response = client.get(
        f"/api/snapper/range?repo={REPO_ROOT}&manufacturer=hmx&range=doesnotexist"
    )
    assert response.status_code == 404


def test_generate_obx_download():
    payload = {
        "repo": REPO_ROOT,
        "manufacturer": "hmx",
        "range": "cosm",
        "selected_articles": ["FLC142", "FLC143"],
        "selected_properties": {
            "Arms": ["N", "P"],
            "Back_Height": ["4", "5"]
        },
        "filename": "test_cosm.obx"
    }
    response = client.post("/api/snapper/generate", json=payload)
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/xml"
    # 2 articles * 2 Arms * 2 Back_Height = 8 permutations
    content = response.text
    assert content.count("<bskArticle") == 8

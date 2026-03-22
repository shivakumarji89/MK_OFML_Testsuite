import pytest
from modules.snapper.reader import discover_ranges

REPO_ROOT = r"C:\HermanMillerOFMLSVN\Staging\HermanMiller\_repository"


def test_discover_ranges_finds_cosm():
    ranges = discover_ranges(REPO_ROOT)
    # ranges is a list of dicts: {manufacturer, range, path}
    range_ids = [(r["manufacturer"], r["range"]) for r in ranges]
    assert ("hmx", "cosm") in range_ids


def test_discover_ranges_only_returns_valid():
    ranges = discover_ranges(REPO_ROOT)
    for r in ranges:
        assert "manufacturer" in r
        assert "range" in r
        assert "db_path" in r


from modules.snapper.reader import load_range_data


def test_load_range_data_returns_articles():
    data = load_range_data(r"C:\HermanMillerOFMLSVN\Staging\HermanMiller\_repository\hmx\cosm\ANY\1\db")
    assert len(data["articles"]) > 0
    article = data["articles"][0]
    assert "code" in article
    assert "article_class" in article
    assert "manufacturer_code" in article
    assert "series_code" in article


def test_load_range_data_returns_properties():
    data = load_range_data(r"C:\HermanMillerOFMLSVN\Staging\HermanMiller\_repository\hmx\cosm\ANY\1\db")
    assert len(data["properties"]) > 0
    prop = data["properties"][0]
    assert "article_class" in prop
    assert "name" in prop
    assert "sort_order" in prop
    assert "relation_id" in prop


def test_load_range_data_returns_values():
    data = load_range_data(r"C:\HermanMillerOFMLSVN\Staging\HermanMiller\_repository\hmx\cosm\ANY\1\db")
    assert len(data["values"]) > 0
    val = data["values"][0]
    assert "article_class" in val
    assert "property_name" in val
    assert "value" in val
    assert "relation_id" in val
    assert "is_default" in val


def test_cosm_has_arms_property():
    data = load_range_data(r"C:\HermanMillerOFMLSVN\Staging\HermanMiller\_repository\hmx\cosm\ANY\1\db")
    prop_names = [p["name"] for p in data["properties"]]
    assert "Arms" in prop_names


def test_cosm_arms_has_multiple_values():
    data = load_range_data(r"C:\HermanMillerOFMLSVN\Staging\HermanMiller\_repository\hmx\cosm\ANY\1\db")
    arms_values = [v["value"] for v in data["values"] if v["property_name"] == "Arms"]
    assert len(arms_values) >= 3  # N, P, J, H

# tests/snapper/test_generate_expansion.py
import pytest
from modules.snapper.routes import expand_permutations_with_children


def test_no_children_unchanged():
    perms = [{"article": "A1", "properties": {"Type": "10", "Finish": "R00"}}]
    result = expand_permutations_with_children(perms, {})
    assert result == perms


def test_child_omitted_when_no_selection():
    perms = [{"article": "A1", "properties": {"Fabric_Type": "1HA"}}]
    child_resolutions = {
        "Fabric_Colour": {"parent": "Fabric_Type", "resolution": {"1HA": []}}
    }
    result = expand_permutations_with_children(perms, child_resolutions)
    assert len(result) == 1
    assert "Fabric_Colour" not in result[0]["properties"]


def test_child_expands_when_selected():
    perms = [{"article": "A1", "properties": {"Fabric_Type": "1HA"}}]
    child_resolutions = {
        "Fabric_Colour": {"parent": "Fabric_Type", "resolution": {"1HA": ["1HA01", "1HA02"]}}
    }
    result = expand_permutations_with_children(perms, child_resolutions)
    assert len(result) == 2
    assert result[0]["properties"]["Fabric_Colour"] == "1HA01"
    assert result[1]["properties"]["Fabric_Colour"] == "1HA02"


def test_mixed_parent_values():
    """Parent A has 2 child values, parent B has 1, parent C has none."""
    perms = [
        {"article": "A1", "properties": {"Fabric_Type": "A"}},
        {"article": "A1", "properties": {"Fabric_Type": "B"}},
        {"article": "A1", "properties": {"Fabric_Type": "C"}},
    ]
    child_resolutions = {
        "Fabric_Colour": {
            "parent": "Fabric_Type",
            "resolution": {"A": ["A1", "A2"], "B": ["B1"], "C": []},
        }
    }
    result = expand_permutations_with_children(perms, child_resolutions)
    assert len(result) == 4  # 2 + 1 + 1
    colours = [p["properties"].get("Fabric_Colour") for p in result]
    assert colours.count("A1") == 1
    assert colours.count("A2") == 1
    assert colours.count("B1") == 1
    assert None in colours  # C perm has no Fabric_Colour


def test_parent_val_not_in_resolution_omits_child():
    """Parent value missing from resolution dict → child property omitted."""
    perms = [{"article": "A1", "properties": {"Fabric_Type": "UNKNOWN"}}]
    child_resolutions = {
        "Fabric_Colour": {"parent": "Fabric_Type", "resolution": {"1HA": ["1HA01"]}}
    }
    result = expand_permutations_with_children(perms, child_resolutions)
    assert len(result) == 1
    assert "Fabric_Colour" not in result[0]["properties"]


def test_standalone_props_preserved():
    perms = [{"article": "A1", "properties": {"Type": "10", "Fabric_Type": "1HA"}}]
    child_resolutions = {
        "Fabric_Colour": {"parent": "Fabric_Type", "resolution": {"1HA": ["1HA01"]}}
    }
    result = expand_permutations_with_children(perms, child_resolutions)
    assert result[0]["properties"]["Type"] == "10"
    assert result[0]["properties"]["Fabric_Type"] == "1HA"
    assert result[0]["properties"]["Fabric_Colour"] == "1HA01"

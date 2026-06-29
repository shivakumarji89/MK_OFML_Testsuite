# tests/snapper/test_match_expansion.py
import pytest
from modules.snapper.routes import apply_matches


def test_no_matches_unchanged():
    perms = [{"article": "A1", "properties": {"Worktop": "oak", "Color": "red"}}]
    assert apply_matches(perms, {}, {"Worktop": ["oak"]}) == perms


def test_lockstep_copies_target_value():
    perms = [
        {"article": "A1", "properties": {"Worktop": "oak"}},
        {"article": "A1", "properties": {"Worktop": "walnut"}},
        {"article": "A1", "properties": {"Worktop": "white"}},
    ]
    match = {"Edge": {"match_to": "Worktop",
                      "matched_values": ["oak", "walnut", "white"],
                      "extras": []}}
    result = apply_matches(perms, match, {"Worktop": ["oak", "walnut", "white"]})
    assert len(result) == 3
    assert all(p["properties"]["Edge"] == p["properties"]["Worktop"] for p in result)


def test_extra_pairs_with_first_selected_anchor():
    """Worked example from the spec: 3 lockstep + 1 extra on anchor = 4."""
    perms = [
        {"article": "A1", "properties": {"Worktop": "oak"}},
        {"article": "A1", "properties": {"Worktop": "walnut"}},
        {"article": "A1", "properties": {"Worktop": "white"}},
    ]
    match = {"Edge": {"match_to": "Worktop",
                      "matched_values": ["oak", "walnut", "white"],
                      "extras": ["plywood"]}}
    result = apply_matches(perms, match, {"Worktop": ["oak", "walnut", "white"]})
    assert len(result) == 4
    pairs = {(p["properties"]["Worktop"], p["properties"]["Edge"]) for p in result}
    assert pairs == {("oak", "oak"), ("walnut", "walnut"),
                     ("white", "white"), ("oak", "plywood")}


def test_target_value_not_in_matched_values_omits_matched_prop():
    """A selected target value absent from Y's set leaves Y omitted (pCon default)."""
    perms = [
        {"article": "A1", "properties": {"Worktop": "oak"}},
        {"article": "A1", "properties": {"Worktop": "granite"}},  # no Edge equivalent
    ]
    match = {"Edge": {"match_to": "Worktop",
                      "matched_values": ["oak"], "extras": []}}
    result = apply_matches(perms, match, {"Worktop": ["oak", "granite"]})
    assert len(result) == 2
    by_wt = {p["properties"]["Worktop"]: p["properties"] for p in result}
    assert by_wt["oak"]["Edge"] == "oak"
    assert "Edge" not in by_wt["granite"]


def test_extras_vary_across_other_free_dimensions_on_anchor_slice():
    """Extras ride the anchor on X but still vary across other dimensions (Color)."""
    perms = [
        {"article": "A1", "properties": {"Worktop": "oak", "Color": "red"}},
        {"article": "A1", "properties": {"Worktop": "oak", "Color": "blue"}},
        {"article": "A1", "properties": {"Worktop": "walnut", "Color": "red"}},
        {"article": "A1", "properties": {"Worktop": "walnut", "Color": "blue"}},
    ]
    match = {"Edge": {"match_to": "Worktop",
                      "matched_values": ["oak", "walnut"], "extras": ["plywood"]}}
    result = apply_matches(perms, match,
                           {"Worktop": ["oak", "walnut"], "Color": ["red", "blue"]})
    # 4 lockstep + 2 extras (anchor=oak slice has 2 colors) = 6
    assert len(result) == 6
    extras = [p for p in result if p["properties"]["Edge"] == "plywood"]
    assert {p["properties"]["Color"] for p in extras} == {"red", "blue"}
    assert all(p["properties"]["Worktop"] == "oak" for p in extras)


def test_multiple_columns_match_same_target():
    """Two columns match Worktop; each locks, each contributes its own extras."""
    perms = [
        {"article": "A1", "properties": {"Worktop": "oak"}},
        {"article": "A1", "properties": {"Worktop": "walnut"}},
    ]
    match = {
        "Edge1": {"match_to": "Worktop", "matched_values": ["oak", "walnut"], "extras": ["ply1"]},
        "Edge2": {"match_to": "Worktop", "matched_values": ["oak", "walnut"], "extras": ["ply2"]},
    }
    result = apply_matches(perms, match, {"Worktop": ["oak", "walnut"]})
    # 2 lockstep + 1 extra(ply1 on anchor) + 1 extra(ply2 on anchor) = 4
    assert len(result) == 4
    # In ply1's extra row, Edge2 stays locked to anchor (oak), and vice versa
    ply1 = next(p for p in result if p["properties"]["Edge1"] == "ply1")
    assert ply1["properties"]["Edge2"] == "oak"
    ply2 = next(p for p in result if p["properties"]["Edge2"] == "ply2")
    assert ply2["properties"]["Edge1"] == "oak"


def test_no_anchor_when_target_not_selected_skips_extras():
    perms = [{"article": "A1", "properties": {"Worktop": "oak"}}]
    match = {"Edge": {"match_to": "Worktop", "matched_values": ["oak"], "extras": ["plywood"]}}
    result = apply_matches(perms, match, {})  # Worktop not in selected_properties
    assert len(result) == 1  # lockstep only, no extra (no anchor)
    assert result[0]["properties"]["Edge"] == "oak"


def test_child_target_lockstep_copies_colour():
    """A matched colour copies the (already-expanded) target colour per permutation."""
    perms = [
        {"article": "A1", "properties": {"Shell_Type": "1HA", "Shell_Colour": "1HA01"}},
        {"article": "A1", "properties": {"Shell_Type": "1HA", "Shell_Colour": "1HA02"}},
    ]
    match = {"Seat_Colour": {"match_to": "Shell_Colour",
                            "matched_values": ["1HA01", "1HA02"], "extras": []}}
    result = apply_matches(perms, match, {"Shell_Type": ["1HA"]})
    assert len(result) == 2
    assert all(p["properties"]["Seat_Colour"] == p["properties"]["Shell_Colour"]
               for p in result)


def test_parent_and_child_pair_lockstep_identical_fabric():
    """Matching type+colour together yields identical seat/shell fabric, no extras."""
    perms = [
        {"article": "A1", "properties": {"Shell_Type": "1HA", "Shell_Colour": "1HA01"}},
        {"article": "A1", "properties": {"Shell_Type": "1HA", "Shell_Colour": "1HA02"}},
        {"article": "A1", "properties": {"Shell_Type": "2AB", "Shell_Colour": "2AB01"}},
    ]
    match = {
        "Seat_Type":   {"match_to": "Shell_Type",
                        "matched_values": ["1HA", "2AB"], "extras": []},
        "Seat_Colour": {"match_to": "Shell_Colour",
                        "matched_values": ["1HA01", "1HA02", "2AB01"], "extras": []},
    }
    result = apply_matches(perms, match, {"Shell_Type": ["1HA", "2AB"]})
    assert len(result) == 3  # no extras -> count unchanged
    for p in result:
        assert p["properties"]["Seat_Type"] == p["properties"]["Shell_Type"]
        assert p["properties"]["Seat_Colour"] == p["properties"]["Shell_Colour"]


def test_validity_filter_omits_colour_not_in_target_set():
    """A target colour absent from the matched property's matched_values is left absent."""
    perms = [
        {"article": "A1", "properties": {"Shell_Type": "1HA", "Shell_Colour": "1HA01"}},
        {"article": "A1", "properties": {"Shell_Type": "1HA", "Shell_Colour": "1HA09"}},
    ]
    # Seat only carries 1HA01 (1HA09 does not exist as a seat colour)
    match = {"Seat_Colour": {"match_to": "Shell_Colour",
                            "matched_values": ["1HA01"], "extras": []}}
    result = apply_matches(perms, match, {"Shell_Type": ["1HA"]})
    by_shell = {p["properties"]["Shell_Colour"]: p["properties"] for p in result}
    assert by_shell["1HA01"]["Seat_Colour"] == "1HA01"
    assert "Seat_Colour" not in by_shell["1HA09"]  # omitted -> pCon default

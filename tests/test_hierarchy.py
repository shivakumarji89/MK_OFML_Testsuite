import pytest
from modules.snapper.hierarchy import detect_hierarchy, _parse_single_property_condition


# ── Inline fixture data ────────────────────────────────────────────────────────

def _make_value(prop_name, value_code, relation_id="0", article_class="CLOUD_OPT"):
    return {
        "article_class": article_class,
        "property_name": prop_name,
        "value": value_code,
        "relation_id": relation_id,
        "sort_order": 1,
        "is_default": False,
        "label": value_code,
    }


# Shell_Fabric_Type: two values, no conditions (always available)
FABRIC_TYPE_VALUES = [
    _make_value("Shell_Fabric_Type", "1HA", relation_id="0"),
    _make_value("Shell_Fabric_Type", "2AB", relation_id="0"),
]

# Shell_Fabric_Colour: four values, each conditioned on one Shell_Fabric_Type value
FABRIC_COLOUR_VALUES = [
    _make_value("Shell_Fabric_Colour", "1HA01", relation_id="101"),
    _make_value("Shell_Fabric_Colour", "1HA02", relation_id="102"),
    _make_value("Shell_Fabric_Colour", "2AB01", relation_id="201"),
    _make_value("Shell_Fabric_Colour", "2AB02", relation_id="202"),
]

# Pre-resolved relations: short_id -> expression (as the /parse-seed route would build)
FABRIC_RELATIONS = {
    "101": "(SPECIFIED Shell_Fabric_Type) AND (Shell_Fabric_Type IN ('1HA'))",
    "102": "(SPECIFIED Shell_Fabric_Type) AND (Shell_Fabric_Type IN ('1HA'))",
    "201": "(SPECIFIED Shell_Fabric_Type) AND (Shell_Fabric_Type IN ('2AB'))",
    "202": "(SPECIFIED Shell_Fabric_Type) AND (Shell_Fabric_Type IN ('2AB'))",
}

ALL_VALUES = FABRIC_TYPE_VALUES + FABRIC_COLOUR_VALUES


# ── detect_hierarchy tests ────────────────────────────────────────────────────

def test_detect_hierarchy_returns_list():
    result = detect_hierarchy(
        ["Shell_Fabric_Type", "Shell_Fabric_Colour"],
        ALL_VALUES,
        FABRIC_RELATIONS,
    )
    assert isinstance(result, list)


def test_detect_hierarchy_finds_fabric_pair():
    result = detect_hierarchy(
        ["Shell_Fabric_Type", "Shell_Fabric_Colour"],
        ALL_VALUES,
        FABRIC_RELATIONS,
    )
    assert len(result) == 1
    h = result[0]
    assert h["parent"] == "Shell_Fabric_Type"
    assert h["child"] == "Shell_Fabric_Colour"


def test_detect_hierarchy_mapping_has_correct_children():
    result = detect_hierarchy(
        ["Shell_Fabric_Type", "Shell_Fabric_Colour"],
        ALL_VALUES,
        FABRIC_RELATIONS,
    )
    mapping = result[0]["mapping"]
    assert set(mapping["1HA"]) == {"1HA01", "1HA02"}
    assert set(mapping["2AB"]) == {"2AB01", "2AB02"}


def test_detect_hierarchy_parent_not_in_seed_returns_empty():
    """If parent property is not in property_names, no hierarchy is returned."""
    result = detect_hierarchy(
        ["Shell_Fabric_Colour"],  # parent (Shell_Fabric_Type) excluded
        ALL_VALUES,
        FABRIC_RELATIONS,
    )
    assert result == []


def test_detect_hierarchy_no_conditions_returns_empty():
    """Properties with no relation_ids are never children."""
    values = [
        _make_value("Arms", "N", relation_id="0"),
        _make_value("Arms", "P", relation_id="0"),
        _make_value("Back_Height", "4", relation_id="0"),
        _make_value("Back_Height", "5", relation_id="0"),
    ]
    result = detect_hierarchy(["Arms", "Back_Height"], values, {})
    assert result == []


def test_detect_hierarchy_partial_conditions_not_child():
    """Unconditioned values (relation_id=0) are skipped; conditioned values still form a hierarchy."""
    values = FABRIC_TYPE_VALUES + [
        _make_value("Shell_Fabric_Colour", "1HA01", relation_id="101"),
        _make_value("Shell_Fabric_Colour", "1HA02", relation_id="0"),  # no condition — skipped
    ]
    relations = {"101": "(SPECIFIED Shell_Fabric_Type) AND (Shell_Fabric_Type IN ('1HA'))"}
    result = detect_hierarchy(
        ["Shell_Fabric_Type", "Shell_Fabric_Colour"],
        values,
        relations,
    )
    # 1HA02 is skipped; 1HA01 is still detected as a child of Shell_Fabric_Type
    assert len(result) == 1
    assert result[0]["parent"] == "Shell_Fabric_Type"
    assert result[0]["child"] == "Shell_Fabric_Colour"
    assert result[0]["mapping"] == {"1HA": ["1HA01"]}


def test_detect_hierarchy_complex_condition_not_child():
    """Article-level ($-prefixed) conditions are skipped; other valid conditions still form a hierarchy."""
    values = FABRIC_TYPE_VALUES + [
        _make_value("SomeChildProp", "val1", relation_id="901"),
        _make_value("SomeChildProp", "val2", relation_id="902"),
    ]
    relations = {
        "901": "$ BAN NOT IN ('NOCLE100')",  # article-level — skipped
        "902": "(SPECIFIED Shell_Fabric_Type) AND (Shell_Fabric_Type IN ('1HA'))",
    }
    result = detect_hierarchy(
        ["Shell_Fabric_Type", "SomeChildProp"],
        values,
        relations,
    )
    # val1 is skipped ($-condition); val2 is detected as a child of Shell_Fabric_Type
    assert len(result) == 1
    assert result[0]["parent"] == "Shell_Fabric_Type"
    assert result[0]["child"] == "SomeChildProp"
    assert result[0]["mapping"] == {"1HA": ["val2"]}


def test_detect_hierarchy_multiple_parent_refs_not_child():
    """If values reference different parent properties, it's not hierarchical."""
    values = [
        _make_value("PropA", "a1", relation_id="0"),
        _make_value("PropA", "a2", relation_id="0"),
        _make_value("PropB", "b1", relation_id="0"),
        _make_value("PropB", "b2", relation_id="0"),
        _make_value("ChildMaybe", "c1", relation_id="901"),
        _make_value("ChildMaybe", "c2", relation_id="902"),
    ]
    relations = {
        "901": "(SPECIFIED PropA) AND (PropA IN ('a1'))",
        "902": "(SPECIFIED PropB) AND (PropB IN ('b1'))",  # different parent!
    }
    result = detect_hierarchy(
        ["PropA", "PropB", "ChildMaybe"],
        values,
        relations,
    )
    assert result == []


def test_detect_hierarchy_empty_property_names():
    result = detect_hierarchy([], ALL_VALUES, FABRIC_RELATIONS)
    assert result == []


def test_detect_hierarchy_two_independent_hierarchies():
    """Two separate parent-child pairs are detected independently."""
    seat_colour_values = [
        _make_value("Seat_Fabric_Colour", "1HA01", relation_id="301"),
        _make_value("Seat_Fabric_Colour", "2AB01", relation_id="302"),
    ]
    seat_relations = {
        "301": "(SPECIFIED Seat_Fabric_Type) AND (Seat_Fabric_Type IN ('1HA'))",
        "302": "(SPECIFIED Seat_Fabric_Type) AND (Seat_Fabric_Type IN ('2AB'))",
    }
    seat_type_values = [
        _make_value("Seat_Fabric_Type", "1HA", relation_id="0"),
        _make_value("Seat_Fabric_Type", "2AB", relation_id="0"),
    ]
    all_vals = ALL_VALUES + seat_type_values + seat_colour_values
    all_relations = {**FABRIC_RELATIONS, **seat_relations}
    prop_names = [
        "Shell_Fabric_Type", "Shell_Fabric_Colour",
        "Seat_Fabric_Type", "Seat_Fabric_Colour",
    ]
    result = detect_hierarchy(prop_names, all_vals, all_relations)
    parents = {h["parent"] for h in result}
    children = {h["child"] for h in result}
    assert "Shell_Fabric_Type" in parents
    assert "Shell_Fabric_Colour" in children
    assert "Seat_Fabric_Type" in parents
    assert "Seat_Fabric_Colour" in children
    assert len(result) == 2


# ── _parse_single_property_condition tests ────────────────────────────────────

def test_parse_condition_standard_form():
    expr = "(SPECIFIED Shell_Fabric_Type) AND (Shell_Fabric_Type IN ('1HA'))"
    result = _parse_single_property_condition(expr)
    assert result == ("Shell_Fabric_Type", "1HA")


def test_parse_condition_without_outer_parens():
    expr = "SPECIFIED Shell_Fabric_Type AND Shell_Fabric_Type IN ('1HA')"
    result = _parse_single_property_condition(expr)
    assert result == ("Shell_Fabric_Type", "1HA")


def test_parse_condition_article_level_returns_none():
    expr = "$ BAN NOT IN ('NOCLE100', 'NOCLE200')"
    assert _parse_single_property_condition(expr) is None


def test_parse_condition_comment_returns_none():
    expr = "* not valid at article NOCLE100"
    assert _parse_single_property_condition(expr) is None


def test_parse_condition_multiple_in_values_returns_none():
    expr = "(SPECIFIED Shell_Fabric_Type) AND (Shell_Fabric_Type IN ('1HA', '2AB'))"
    assert _parse_single_property_condition(expr) is None


def test_parse_condition_empty_returns_none():
    assert _parse_single_property_condition("") is None


def test_parse_condition_complex_expression_returns_none():
    expr = "(SPECIFIED PropA) AND (PropA IN ('x')) OR (PropB IN ('y'))"
    assert _parse_single_property_condition(expr) is None


def test_parse_condition_case_insensitive():
    expr = "(specified Shell_Fabric_Type) and (Shell_Fabric_Type in ('1HA'))"
    result = _parse_single_property_condition(expr)
    assert result == ("Shell_Fabric_Type", "1HA")

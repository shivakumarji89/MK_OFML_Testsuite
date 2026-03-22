import re


# Matches: (SPECIFIED PropName) AND (PropName IN ('val'))
# Also handles without outer parens: SPECIFIED PropName AND PropName IN ('val')
_CONDITION_PATTERN = re.compile(
    r"^\(?SPECIFIED\s+(\w+)\)?\s+AND\s+\(?\1\s+IN\s+\('([^']+)'\)\)?$",
    re.IGNORECASE,
)


def detect_hierarchy(
    property_names: list[str],
    values: list[dict],
    relations: dict[str, str],
) -> list[dict]:
    """
    Detect parent-child property pairs among a set of property names.

    Args:
        property_names: Names of properties to consider (from the seed).
            Only these properties are examined as potential children or parents.
        values: Full list of value dicts from load_range_data (all properties in range).
            Each dict has keys: property_name, value, relation_id, article_class, ...
        relations: {short_relation_id: expression_string}
            NOTE: This must use SHORT relation IDs (matching values[i]['relation_id']),
            NOT the long zero-padded IDs from ocd_relation.csv.
            The caller (/parse-seed route) builds this by joining ocd_relationobj.csv
            (short->long bridge) with ocd_relation.csv (long->expression).

    Returns:
        List of hierarchy dicts:
        [
            {
                "parent": "Shell_Fabric_Type",
                "child": "Shell_Fabric_Colour",
                "mapping": {
                    "1HA": ["1HA01", "1HA02", "1HA03"],
                    "2AB": ["2AB01", "2AB02"],
                }
            },
            ...
        ]
        Properties that are not hierarchically linked appear in neither list.
        A property can only be a child (not simultaneously a parent and a child
        in the same returned hierarchy, though multi-level hierarchies are not
        currently supported).
    """
    prop_name_set = set(property_names)

    # Group values by property_name (only for seed properties)
    prop_values: dict[str, list[dict]] = {}
    for v in values:
        pname = v["property_name"]
        if pname in prop_name_set:
            prop_values.setdefault(pname, []).append(v)

    hierarchies = []

    for prop_name in property_names:
        all_vals = prop_values.get(prop_name, [])
        if not all_vals:
            continue

        # Build conditions map: value_code -> expression (only for values with a relation)
        conditions: dict[str, str] = {}
        for v in all_vals:
            rel_id = v.get("relation_id", "")
            if rel_id and rel_id != "0":
                expr = relations.get(rel_id)
                if expr is not None:
                    conditions[v["value"]] = expr

        # All values must be conditioned for this property to be a child
        if len(conditions) != len(all_vals):
            continue

        # Parse each condition — all must reference the same single parent property
        parent_refs: set[str] = set()
        parent_value_map: dict[str, list[str]] = {}
        valid = True

        for value_code, expression in conditions.items():
            parsed = _parse_single_property_condition(expression)
            if parsed is None:
                valid = False
                break
            parent_name, parent_val = parsed
            parent_refs.add(parent_name)
            parent_value_map.setdefault(parent_val, []).append(value_code)

        if not valid:
            continue
        if len(parent_refs) != 1:
            continue

        parent_property = next(iter(parent_refs))

        # Parent must also be in the seed's property set
        if parent_property not in prop_name_set:
            continue

        hierarchies.append({
            "parent": parent_property,
            "child": prop_name,
            "mapping": parent_value_map,
        })

    return hierarchies


def _parse_single_property_condition(expression: str) -> tuple[str, str] | None:
    """
    Parse a condition expression that references exactly one property and one value.

    Accepted forms:
        (SPECIFIED PropName) AND (PropName IN ('val'))
        SPECIFIED PropName AND PropName IN ('val')

    Returns:
        (parent_property_name, parent_value) if the expression matches exactly.
    Returns None for:
        - Article-level conditions (starting with '$')
        - Comment lines (starting with '*')
        - Expressions referencing multiple properties or multiple IN values
        - Any expression that does not match the expected pattern
    """
    expr = expression.strip()

    if not expr:
        return None
    if expr.startswith("$") or expr.startswith("*"):
        return None

    m = _CONDITION_PATTERN.match(expr)
    if m:
        return (m.group(1), m.group(2))

    return None

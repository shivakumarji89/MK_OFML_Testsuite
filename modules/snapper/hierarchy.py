import re
from pathlib import Path


# Matches: (SPECIFIED PropName) AND (PropName IN ('val'))
# Also handles without outer parens: SPECIFIED PropName AND PropName IN ('val')
_CONDITION_PATTERN = re.compile(
    r"^\(?SPECIFIED\s+(\w+)\)?\s+AND\s+\(?\1\s+IN\s+\('([^']+)'\)\)?$",
    re.IGNORECASE,
)

# Matches simple equality: PropName = 'val'
# Used by some ranges (e.g. Fin) instead of the SPECIFIED...IN form.
_SIMPLE_EQUALITY_PATTERN = re.compile(
    r"^(\w+)\s*=\s*'([^']+)'$",
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

        # Build parent-child mapping from values that have a parseable parent-child condition.
        # Values with article-level conditions ($ prefix), no relation, or unrecognised
        # expressions are silently skipped — they won't appear in the mapping but that's
        # acceptable for the QA use case.
        parent_refs: set[str] = set()
        parent_value_map: dict[str, list[str]] = {}
        seen_children: dict[str, set[str]] = {}  # parent_val -> seen child codes

        for v in all_vals:
            rel_id = v.get("relation_id", "")
            if not rel_id or rel_id == "0":
                continue
            expr = relations.get(rel_id)
            if expr is None:
                continue
            parsed = _parse_single_property_condition(expr)
            if parsed is None:
                continue  # e.g. $-conditions, multi-value IN, etc.
            parent_name, parent_val = parsed
            parent_refs.add(parent_name)
            child_code = v["value"]
            if child_code not in seen_children.setdefault(parent_val, set()):
                seen_children[parent_val].add(child_code)
                parent_value_map.setdefault(parent_val, []).append(child_code)

        # Need at least some matched values, all referencing the same parent
        if not parent_refs or len(parent_refs) != 1:
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


def detect_hierarchy_from_tables(
    property_names: list[str],
    values: list[dict],
    db_path: str,
) -> list[dict]:
    """
    Detect parent-child property pairs from *_tbl.csv lookup tables in the db folder.

    Some ranges (e.g. Always) define valid fabric type→colour combinations via a
    custom table file rather than OCD relation expressions.  The table format is:
        seq ; CHILD_PROP_UPPERCASE ; child_value
    where seq is the sort_order of the parent property's value in ocd_propertyvalue.csv.

    The parent property is identified by sharing the same name prefix as the child
    (e.g. Chair_Fabric_Colour → prefix Chair_Fabric → parent Chair_Fabric_Type).
    """
    prop_name_set = set(property_names)
    prop_lower_map = {p.lower(): p for p in property_names}

    # Build {prop_name: {sort_order: value_code}} for resolving seq → parent value
    prop_seq_to_value: dict[str, dict[int, str]] = {}
    for v in values:
        pname = v["property_name"]
        seq = v["sort_order"]
        val = v["value"]
        if pname not in prop_seq_to_value:
            prop_seq_to_value[pname] = {}
        if seq not in prop_seq_to_value[pname]:
            prop_seq_to_value[pname][seq] = val

    hierarchies = []

    for tbl_path in sorted(Path(db_path).glob("*_tbl.csv")):
        tbl: dict[int, list[str]] = {}
        child_prop_upper: str | None = None

        for line in tbl_path.read_text(encoding="utf-8", errors="replace").splitlines():
            row = line.strip().split(";")
            if len(row) < 3:
                continue
            try:
                seq = int(row[0].strip())
            except ValueError:
                continue
            child_col = row[1].strip()
            child_val = row[2].strip()
            if not child_val:
                continue
            if child_prop_upper is None:
                child_prop_upper = child_col
            tbl.setdefault(seq, []).append(child_val)

        if not tbl or child_prop_upper is None:
            continue

        # Match child property name (case-insensitive)
        child_prop = prop_lower_map.get(child_prop_upper.lower())
        if child_prop is None:
            continue  # child property not in this seed

        # Find parent: same name prefix (everything before last underscore word)
        child_parts = child_prop.split("_")
        if len(child_parts) < 2:
            continue
        prefix_lower = "_".join(child_parts[:-1]).lower()  # e.g. "chair_fabric"

        parent_prop = next(
            (p for p in property_names
             if p != child_prop and p.lower().startswith(prefix_lower + "_")),
            None,
        )
        if parent_prop is None:
            continue

        # Map seq → parent value and build {parent_value: [child_values]}
        seq_to_value = prop_seq_to_value.get(parent_prop, {})
        mapping: dict[str, list[str]] = {}
        for seq, child_vals in tbl.items():
            parent_val = seq_to_value.get(seq)
            if parent_val:
                mapping[parent_val] = child_vals

        if mapping:
            hierarchies.append({
                "parent": parent_prop,
                "child": child_prop,
                "mapping": mapping,
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

    m = _SIMPLE_EQUALITY_PATTERN.match(expr)
    if m:
        return (m.group(1), m.group(2))

    return None

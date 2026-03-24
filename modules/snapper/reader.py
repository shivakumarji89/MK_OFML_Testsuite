import os
from pathlib import Path


def discover_ranges(repo_root: str) -> list[dict]:
    """
    Scan repo_root for valid OFML ranges.
    A range is valid if {manufacturer}/{range}/ANY/1/db/ocd_article.csv exists.
    Returns list of {manufacturer, range, db_path}.
    """
    results = []
    repo = Path(repo_root)
    if not repo.exists():
        return results
    for mfr_dir in sorted(repo.iterdir()):
        if not mfr_dir.is_dir():
            continue
        for range_dir in sorted(mfr_dir.iterdir()):
            if not range_dir.is_dir():
                continue
            db_path = range_dir / "ANY" / "1" / "db"
            if (db_path / "ocd_article.csv").exists():
                results.append({
                    "manufacturer": mfr_dir.name,
                    "range": range_dir.name,
                    "db_path": str(db_path),
                })
    return results


def _read_csv(path: str) -> list[list[str]]:
    """Read a semicolon-delimited CSV, skipping comment lines (starting with #)."""
    rows = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            rows.append(line.split(";"))
    return rows


def load_range_data(db_path: str) -> dict:
    """
    Load OCD data for a range from its db/ folder.
    Returns {articles, properties, values, relations}.

    articles: list of {code, article_class, manufacturer_code, series_code}
    properties: list of {article_class, name, sort_order, relation_id}
    values: list of {article_class, property_name, sort_order, value_id,
                     relation_id, is_default, value}
    relations: dict of {relation_id: full_expression_string}
    """
    db = Path(db_path)

    # --- ocd_article.csv: configurable articles only ---
    article_rows = _read_csv(str(db / "ocd_article.csv"))
    # col[1] == 'C' means configurable
    configurable = {row[0]: row for row in article_rows if len(row) > 3 and row[1].strip() == "C"}

    # --- ocd_artbase.csv: map article code → article class ---
    artbase_rows = _read_csv(str(db / "ocd_artbase.csv"))
    code_to_class = {}
    for row in artbase_rows:
        if len(row) < 2:
            continue
        code = row[0].strip()
        if code not in code_to_class:
            code_to_class[code] = row[1].strip()

    articles = []
    for code, row in configurable.items():
        articles.append({
            "code": code.strip(),
            "article_class": code_to_class.get(code.strip(), ""),
            "manufacturer_code": row[2].strip() if len(row) > 2 else "",
            "series_code": row[3].strip() if len(row) > 3 else "",
        })

    # --- ocd_property.csv ---
    prop_rows = _read_csv(str(db / "ocd_property.csv"))
    properties = []
    for row in prop_rows:
        if len(row) < 5:
            continue
        properties.append({
            "article_class": row[0].strip(),
            "name": row[1].strip(),
            "sort_order": int(row[2].strip()) if row[2].strip().isdigit() else 0,
            "relation_id": row[4].strip(),
        })

    # --- ocd_propvaluetext.csv: build value_id → English label map ---
    label_map: dict[str, str] = {}
    text_path = db / "ocd_propvaluetext.csv"
    if text_path.exists():
        for row in _read_csv(str(text_path)):
            if len(row) < 5:
                continue
            if row[1].strip().lower() != "en":
                continue
            value_id = row[0].strip()
            label = row[4].strip().strip('"')
            if value_id and value_id not in label_map:
                label_map[value_id] = label

    # --- ocd_propertyvalue.csv ---
    # The value code sits at col[8]; trailing semicolons produce empty columns
    # after it so row[-1] is unreliable — take the last non-empty column instead.
    value_rows = _read_csv(str(db / "ocd_propertyvalue.csv"))
    values = []
    for row in value_rows:
        if len(row) < 6:
            continue
        value_id = row[3].strip()
        value_code = next((c.strip() for c in reversed(row) if c.strip()), "")
        values.append({
            "article_class": row[0].strip(),
            "property_name": row[1].strip(),
            "sort_order": int(row[2].strip()) if row[2].strip().isdigit() else 0,
            "value_id": value_id,
            "relation_id": row[4].strip(),
            "is_default": row[5].strip() == "1",
            "value": value_code,
            "label": label_map.get(value_id, value_code),
        })

    # --- ocd_relation.csv: build full expression per relation_id ---
    relation_path = db / "ocd_relation.csv"
    relations: dict[str, str] = {}
    if relation_path.exists():
        rel_rows = _read_csv(str(relation_path))
        for row in rel_rows:
            if len(row) < 3:
                continue
            rel_id = row[0].strip()
            expression_part = row[2].strip().strip('"')
            if rel_id not in relations:
                relations[rel_id] = expression_part
            else:
                relations[rel_id] += " " + expression_part

    return {
        "articles": articles,
        "properties": properties,
        "values": values,
        "relations": relations,
    }


def read_prog_id(range_dir: str) -> str | None:
    """
    Derive the pCon progId for a range from oam_article2ofml.csv.

    Reads the OFML instance path from column[2] of the first data row, e.g.:
      "::hmx::aeron::W_AERON"  →  "@hmx_aeron"
      "::hmx::ratio_rebuild::W_X"  →  "@hmx_ratio_rebuild"

    The last '::' segment is the class name and is dropped; the rest form the
    namespace joined with '_'.

    Returns None if the OAM file is missing or cannot be parsed.
    """
    oam_path = Path(range_dir) / "ANY" / "1" / "oam" / "oam_article2ofml.csv"
    if not oam_path.exists():
        return None
    try:
        with oam_path.open(encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split(";")
                if len(parts) < 3:
                    continue
                instance_path = parts[2].strip()
                segments = [s for s in instance_path.split("::") if s]
                if len(segments) >= 2:
                    return "@" + "_".join(segments[:-1])
    except OSError:
        pass
    return None

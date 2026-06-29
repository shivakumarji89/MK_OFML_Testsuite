import io
import re
import uuid
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from .reader import discover_ranges, load_range_data, _read_csv, read_prog_id
from .generator import compute_permutations, build_obx, build_obx_from_seed, build_obx_from_multi_seed, build_raw_seed_obx, SENTINEL
from .seed_parser import parse_seed, SeedParseError
from .hierarchy import detect_hierarchy, detect_hierarchy_from_tables

router = APIRouter(prefix="/api/snapper", tags=["snapper"])

# In-memory store: seed_token -> raw XML string.  Cleared on server restart (fine for local use).
_seed_store: dict[str, str] = {}


# ── Helper ────────────────────────────────────────────────────────────────────

def _build_short_id_relations(db_path: str) -> dict[str, str]:
    """
    Build {short_relation_id: concatenated_expression} by joining
    ocd_relationobj.csv (short->long bridge) with ocd_relation.csv (long->expression).
    """
    db = Path(db_path)

    # Build long_id -> concatenated expression
    # Rows are multi-part: seq 1 is a "*" comment marker, seq 2 is blank, seq 3+ is the
    # actual condition expression.  Skip empty and "*"-prefixed parts.
    long_to_expr: dict[str, str] = {}
    rel_path = db / "ocd_relation.csv"
    if rel_path.exists():
        for row in _read_csv(str(rel_path)):
            if len(row) < 3:
                continue
            long_id = row[0].strip()
            part = row[2].strip().strip('"')
            if not part or part.startswith("*"):
                continue
            if long_id not in long_to_expr:
                long_to_expr[long_id] = part
            else:
                long_to_expr[long_id] += " " + part

    # Build short_id -> expression via ocd_relationobj.csv
    short_to_expr: dict[str, str] = {}
    obj_path = db / "ocd_relationobj.csv"
    if obj_path.exists():
        for row in _read_csv(str(obj_path)):
            if len(row) < 3:
                continue
            short_id = row[0].strip()
            long_id = row[2].strip()
            expr = long_to_expr.get(long_id)
            if expr is not None and short_id not in short_to_expr:
                short_to_expr[short_id] = expr

    return short_to_expr


# ── /ranges endpoint ──────────────────────────────────────────────────────────

@router.get("/ranges")
def get_ranges(repo: str):
    """Return the list of valid ranges found in the given repo path."""
    ranges = discover_ranges(repo)
    # Strip db_path — it's an internal server-side detail
    return {
        "ranges": [{"manufacturer": r["manufacturer"], "range": r["range"]} for r in ranges]
    }


# ── /generate-raw-seed endpoint ───────────────────────────────────────────────

class RawSeedRequest(BaseModel):
    repo: str
    manufacturer: str
    range: str


@router.post("/generate-raw-seed")
def generate_raw_seed(req: RawSeedRequest):
    """
    Generate a raw seed OBX for the given range.
    The OBX contains one bskArticle per configurable article with blank
    configuration — pCon populates defaults when the user runs Update.
    """
    ranges = discover_ranges(req.repo)
    matched = next(
        (r for r in ranges
         if r["manufacturer"] == req.manufacturer and r["range"] == req.range),
        None,
    )
    if matched is None:
        raise HTTPException(
            status_code=404,
            detail=f"Range '{req.range}' not found for manufacturer '{req.manufacturer}' in '{req.repo}'",
        )

    try:
        range_data = load_range_data(matched["db_path"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load range data: {e}")

    articles = range_data["articles"]
    if not articles:
        raise HTTPException(status_code=400, detail="No configurable articles found in this range")

    # db_path is "{range_dir}/ANY/1/db" — go up 3 levels to get range_dir
    range_dir = str(Path(matched["db_path"]).parent.parent.parent)
    prog_id = read_prog_id(range_dir) or f"@{req.manufacturer}_{req.range}"

    xml_content = build_raw_seed_obx(
        articles=articles,
        prog_id=prog_id,
        mfr_folder=req.manufacturer,
    )

    filename = f"raw_seed_{req.range}.obx"
    return Response(
        content=xml_content,
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── /parse-seed endpoint ──────────────────────────────────────────────────────

@router.post("/parse-seed")
async def parse_seed_endpoint(
    file: UploadFile = File(...),
    repo: str = Form(...),
):
    raw = await file.read()
    try:
        xml_string = raw.decode("utf-8", errors="replace")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not decode file: {e}")

    try:
        seed = parse_seed(xml_string)
    except SeedParseError as e:
        raise HTTPException(status_code=422, detail=str(e))

    ranges = discover_ranges(repo)
    seed_series = seed["series"]
    matched = next(
        (r for r in ranges if seed_series in r["series_codes"]),
        None,
    )
    if matched is None:
        raise HTTPException(
            status_code=404,
            detail=f"No range found matching series '{seed_series}' in repo '{repo}'"
        )
    db_path = matched["db_path"]

    try:
        range_data = load_range_data(db_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load range data: {e}")

    artbase_restrictions = range_data.get("artbase_restrictions", {})
    short_id_relations = _build_short_id_relations(db_path)

    # Build values lookup: property_name -> list of {code, label}
    # Also build per-class lookup: (article_class, property_name) -> [value_codes]
    values_by_prop: dict[str, list[dict]] = {}
    seen: dict[str, set] = {}
    class_prop_values: dict[tuple[str, str], list[str]] = {}
    seen_cpv: dict[tuple[str, str], set[str]] = {}
    for v in range_data["values"]:
        pname = v["property_name"]
        code = v["value"]
        if not code:
            continue
        if pname not in values_by_prop:
            values_by_prop[pname] = []
            seen[pname] = set()
        if code not in seen[pname]:
            seen[pname].add(code)
            values_by_prop[pname].append({"code": code, "label": v.get("label", code)})
        key = (v["article_class"], pname)
        if key not in class_prop_values:
            class_prop_values[key] = []
            seen_cpv[key] = set()
        if code not in seen_cpv[key]:
            seen_cpv[key].add(code)
            class_prop_values[key].append(code)

    # Group articles by their property-name signature
    groups_map: dict[frozenset, list[dict]] = {}
    for article in seed["articles"]:
        sig = frozenset(p["name"] for p in article["properties"])
        groups_map.setdefault(sig, []).append(article)

    groups = []
    for group_idx, (sig, group_articles) in enumerate(groups_map.items()):
        # Build property_columns from the first article's property list
        first_article = group_articles[0]
        prop_names = [p["name"] for p in first_article["properties"]]

        hierarchies = detect_hierarchy(prop_names, range_data["values"], short_id_relations)
        already_child = {h["child"] for h in hierarchies}
        tbl_hierarchies = detect_hierarchy_from_tables(prop_names, range_data["values"], db_path)
        for h in tbl_hierarchies:
            if h["child"] not in already_child:
                hierarchies.append(h)
        child_map = {h["child"]: h for h in hierarchies}

        property_columns = []
        for prop in first_article["properties"]:
            pname = prop["name"]
            h = child_map.get(pname)
            is_child = h is not None
            property_columns.append({
                "name": pname,
                "article_class": prop["article_class"],
                "seed_value": prop["seed_value"],
                "values": values_by_prop.get(pname, []),
                "is_child": is_child,
                "parent": h["parent"] if is_child else None,
                "mapping": h["mapping"] if is_child else None,
            })

        # Build per-article info with class maps and individual seed tokens
        articles_out = []
        for article in group_articles:
            property_to_class: dict[str, str] = {}
            prop_val_to_class: dict[str, str] = {}
            for p in article["properties"]:
                property_to_class[p["name"]] = p["article_class"]
                for v in values_by_prop.get(p["name"], []):
                    prop_val_to_class[f"{p['name']}={v['code']}"] = p["article_class"]

            # Build valid_values: class-filtered values, optionally narrowed by artbase restrictions.
            # If a property has values from multiple article classes in the OCD, only the values
            # belonging to this article's class are valid. Artbase restrictions narrow further.
            art_restrictions = artbase_restrictions.get(article["article"], {})
            valid_values: dict[str, list[str]] = {}
            for p in article["properties"]:
                class_vals = class_prop_values.get((p["article_class"], p["name"]), [])
                if not class_vals:
                    # No class data — leave out so frontend treats all values as valid
                    continue
                restriction = art_restrictions.get(p["name"])
                if restriction is not None:
                    restriction_set = set(restriction)
                    valid_values[p["name"]] = [c for c in class_vals if c in restriction_set]
                else:
                    valid_values[p["name"]] = class_vals

            # Wrap the single article element in a minimal cutBuffer for use as a seed template
            article_seed_xml = (
                f"<?xml version='1.0' encoding='UTF-8'?>"
                f"<cutBuffer>"
                f"<versionInfo vendorKey='EasternGraphics' appKey='EAI-Server' "
                f"appVersion='4.18.3' bskXmlVersion='1.8.10'/>"
                f"<items>{article['article_xml']}</items>"
                f"</cutBuffer>"
            )
            article_token = str(uuid.uuid4())
            _seed_store[article_token] = article_seed_xml

            articles_out.append({
                "code": article["article"],
                "label": article["label"],
                "property_to_class": property_to_class,
                "prop_val_to_class": prop_val_to_class,
                "seed_token": article_token,
                "valid_values": valid_values,
            })

        groups.append({
            "id": f"group-{group_idx}",
            "articles": articles_out,
            "property_columns": property_columns,
        })

    return {
        "manufacturer": seed["manufacturer"],
        "series": seed["series"],
        "repo": repo,
        "db_path": db_path,
        "groups": groups,
        "info_messages": seed.get("info_messages", []),
    }


# ── /generate endpoint ────────────────────────────────────────────────────────

class ArticleInfo(BaseModel):
    code: str
    label: str | None = None
    property_to_class: dict[str, str]
    prop_val_to_class: dict[str, str]
    seed_token: str | None = None


class ChildResolution(BaseModel):
    parent: str                       # parent property name, e.g. "Shell_Fabric_Type"
    resolution: dict[str, list[str]]  # {parent_value: [child_values]}, empty list = omit child


class QueueItem(BaseModel):
    articles: list[ArticleInfo]
    selected_article_codes: list[str]
    selected_properties: dict[str, list[str]]   # parent-only dimensions
    child_resolutions: dict[str, ChildResolution] = {}
    filename: str = ""


class GenerateRequest(BaseModel):
    manufacturer: str
    series: str
    queue: list[QueueItem]
    filename: str = "snapper.obx"
    seed_token: str | None = None  # kept for backward compat; ignored (tokens are per-article)


def expand_permutations_with_children(
    permutations: list[dict],
    child_resolutions: dict[str, dict],
) -> list[dict]:
    """
    Expand permutations to include child property values.

    For each base permutation (parent-only cartesian product):
    - Look up child values for the permutation's parent value.
    - If child values exist: expand into N copies (one per child value).
    - If child values are empty or parent value not in resolution: keep perm as-is,
      child property is simply absent from the varcode.

    Args:
        permutations: list of {article, properties} dicts (parent-only dimensions)
        child_resolutions: {child_prop_name: {"parent": str, "resolution": {parent_val: [child_vals]}}}
            Plain dicts — callers must convert Pydantic models before calling.

    Returns:
        Expanded list of {article, properties} dicts.
    """
    if not child_resolutions:
        return permutations

    expanded = []
    for perm in permutations:
        child_expansions: list[dict] = [{}]
        for child_prop, cr in child_resolutions.items():
            parent_val = perm["properties"].get(cr["parent"], "")
            child_vals = cr["resolution"].get(parent_val, [])
            if child_vals:
                new_expansions = []
                for existing in child_expansions:
                    for cv in child_vals:
                        new_expansions.append({**existing, child_prop: cv})
                child_expansions = new_expansions
            # else: child prop omitted for this permutation — child_expansions unchanged
        for extra in child_expansions:
            expanded.append({
                "article": perm["article"],
                "properties": {**perm["properties"], **extra},
            })
    return expanded


def apply_matches(
    permutations: list[dict],
    match_resolutions: dict[str, dict],
    selected_properties: dict[str, list[str]],
) -> list[dict]:
    """See module docs / plan for the contract. Lockstep + anchor-bound extras."""
    if not match_resolutions:
        return permutations

    # 1. Lockstep: copy each target value onto its matched property.
    locked: list[dict] = []
    for perm in permutations:
        props = dict(perm["properties"])
        for matched_prop, mr in match_resolutions.items():
            target_val = props.get(mr["match_to"])
            if target_val is not None and target_val in mr["matched_values"]:
                props[matched_prop] = target_val
            # else: matched_prop left absent (pCon default)
        locked.append({"article": perm["article"], "properties": props})

    # 2. Extras: each rides the anchor (first selected target value) slice.
    extra_rows: list[dict] = []
    for matched_prop, mr in match_resolutions.items():
        selected = selected_properties.get(mr["match_to"], [])
        if not selected:
            continue  # no anchor available -> skip extras for this column
        anchor = selected[0]
        for extra_val in mr["extras"]:
            for base in locked:
                if base["properties"].get(mr["match_to"]) == anchor:
                    new_props = dict(base["properties"])
                    new_props[matched_prop] = extra_val
                    extra_rows.append({"article": base["article"], "properties": new_props})

    return locked + extra_rows


@router.post("/generate")
def generate_obx(req: GenerateRequest):
    """
    Generate OBX file(s) from a queue of article configurations.
    Single-item queue returns XML directly; multi-item returns a zip.
    """
    if not req.queue:
        raise HTTPException(status_code=400, detail="Queue is empty")

    obx_files: list[tuple[str, str]] = []

    for item in req.queue:
        # Filter to selected articles only
        selected_articles = [
            a for a in item.articles if a.code in item.selected_article_codes
        ]
        if not selected_articles:
            raise HTTPException(status_code=400, detail="No articles selected in queue item")

        selected_codes = [a.code for a in selected_articles]
        permutations = compute_permutations(selected_codes, item.selected_properties)

        child_res_dicts = {
            name: {"parent": cr.parent, "resolution": cr.resolution}
            for name, cr in item.child_resolutions.items()
        }
        permutations = expand_permutations_with_children(permutations, child_res_dicts)

        # Build per-article seed XMLs and class maps
        article_seeds: dict[str, str] = {}
        article_class_maps: dict[str, dict] = {}

        for art in selected_articles:
            seed_xml = _seed_store.get(art.seed_token) if art.seed_token else None
            if seed_xml:
                article_seeds[art.code] = seed_xml
            article_class_maps[art.code] = {
                "property_to_class": art.property_to_class,
                "prop_val_to_class": art.prop_val_to_class,
            }

        if article_seeds:
            xml_content = build_obx_from_multi_seed(
                article_seeds, permutations, article_class_maps
            )
        else:
            # No seed templates — build generic OBX
            first_art = selected_articles[0]
            pvtc: dict[tuple, str] = {}
            for key_str, cls in first_art.prop_val_to_class.items():
                eq = key_str.find("=")
                if eq != -1:
                    pvtc[(key_str[:eq], key_str[eq + 1:])] = cls
            xml_content = build_obx(
                permutations,
                {a.code: "" for a in selected_articles},
                req.manufacturer,
                req.series,
                first_art.property_to_class,
                pvtc,
            )

        entry_name = item.filename if item.filename else "snapper.obx"
        obx_files.append((entry_name, xml_content))

    if len(obx_files) == 1:
        filename, xml_content = obx_files[0]
        return Response(
            content=xml_content,
            media_type="application/xml",
            headers={"Content-Disposition": f'attachment; filename="{req.filename}"'},
        )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname, content in obx_files:
            zf.writestr(fname, content)
    buf.seek(0)
    zip_filename = req.filename.replace(".obx", ".zip") if req.filename.endswith(".obx") else req.filename + ".zip"
    return Response(
        content=buf.read(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{zip_filename}"'},
    )


@router.post("/clean-obx")
async def clean_obx(
    file: UploadFile = File(...),
    label: str = Form(""),
):
    """
    Remove articles that still carry the __SNAPPER_RAW__ sentinel from a
    pCon-exported OBX. Returns the cleaned OBX with X-Kept-Count and
    X-Removed-Count response headers.
    """
    raw = await file.read()
    try:
        root = ET.parse(io.BytesIO(raw)).getroot()
    except ET.ParseError as e:
        raise HTTPException(status_code=400, detail=f"Could not parse OBX: {e}")

    # Read series and article before removing anything
    series = "unknown"
    article_code = "unknown"
    first_art = root.find(".//bskArticle")
    if first_art is not None:
        s_el = first_art.find("series")
        if s_el is not None:
            series = s_el.get("id", "unknown").lower()
        for a in first_art.findall("artNr"):
            if a.get("type") == "base":
                article_code = a.text or "unknown"
                break

    items_el = root.find(".//items")
    if items_el is None:
        raise HTTPException(status_code=400, detail="No <items> element found in OBX")

    removed_ids: set[str] = set()
    removed = 0
    for art in list(items_el.findall("bskArticle")):
        is_sentinel = any(
            a.get("type") == "final" and (a.text or "").strip() == SENTINEL
            for a in art.findall("artNr")
        )
        if is_sentinel:
            removed_ids.add(art.get("basketId", ""))
            items_el.remove(art)
            removed += 1

    kept = len(items_el.findall("bskArticle"))

    doc_calc = root.find("docCalculationChanges")
    if doc_calc is not None:
        for entry in list(doc_calc.findall("itemCalculationChanges")):
            if entry.get("id") in removed_ids:
                doc_calc.remove(entry)

    safe_label = re.sub(r"[^\w]", "_", label.strip().replace(" ", "_")) if label.strip() else ""
    parts = [p for p in [series, article_code, safe_label, "Clean"] if p]
    filename = "_".join(parts) + ".obx"

    xml_out = ET.tostring(root, encoding="unicode")

    return Response(
        content=xml_out,
        media_type="application/xml",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Kept-Count": str(kept),
            "X-Removed-Count": str(removed),
        },
    )

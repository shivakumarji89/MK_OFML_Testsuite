import io
import re
import uuid
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from .reader import discover_ranges, load_range_data, _read_csv
from .generator import compute_permutations, build_obx, build_obx_from_seed, SENTINEL
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


# ── /parse-seed endpoint ──────────────────────────────────────────────────────

@router.post("/parse-seed")
async def parse_seed_endpoint(
    file: UploadFile = File(...),
    repo: str = Form(...),
):
    """
    Parse an uploaded OBX seed file and return property columns with valid values
    and detected hierarchy information.
    """
    raw = await file.read()
    try:
        xml_string = raw.decode("utf-8", errors="replace")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not decode file: {e}")

    try:
        seed = parse_seed(xml_string)
    except SeedParseError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # Discover db_path by matching series code (case-insensitive) against known ranges
    ranges = discover_ranges(repo)
    matched = next(
        (r for r in ranges if r["range"].lower() == seed["series"].lower()),
        None,
    )
    if matched is None:
        raise HTTPException(
            status_code=404,
            detail=f"No range found matching series '{seed['series']}' in repo '{repo}'"
        )
    db_path = matched["db_path"]

    # Load OCD data for the range
    try:
        range_data = load_range_data(db_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load range data: {e}")

    # Build short_id -> expression map for hierarchy detection
    short_id_relations = _build_short_id_relations(db_path)

    # Detect hierarchies scoped to seed properties only
    seed_prop_names = [p["name"] for p in seed["properties"]]
    hierarchies = detect_hierarchy(seed_prop_names, range_data["values"], short_id_relations)

    # Also detect hierarchies from *_tbl.csv lookup tables (used by some ranges e.g. Always)
    # Table-based results take precedence if the same child property is detected by both methods.
    already_child = {h["child"] for h in hierarchies}
    tbl_hierarchies = detect_hierarchy_from_tables(seed_prop_names, range_data["values"], db_path)
    for h in tbl_hierarchies:
        if h["child"] not in already_child:
            hierarchies.append(h)

    # Build lookup: child_prop_name -> hierarchy dict
    child_map = {h["child"]: h for h in hierarchies}

    # Build values lookup: property_name -> list of {code, label}
    values_by_prop: dict[str, list[dict]] = {}
    seen: dict[str, set] = {}
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

    # Build property_columns
    property_columns = []
    for prop in seed["properties"]:
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

    seed_token = str(uuid.uuid4())
    _seed_store[seed_token] = seed["raw_xml"]

    return {
        "article": seed["article"],
        "manufacturer": seed["manufacturer"],
        "series": seed["series"],
        "repo": repo,
        "db_path": db_path,
        "property_columns": property_columns,
        "seed_token": seed_token,
    }


# ── /generate endpoint ────────────────────────────────────────────────────────

class ChildResolution(BaseModel):
    parent: str               # parent property name, e.g. "Shell_Fabric_Type"
    resolution: dict[str, str]  # {parent_value: child_value}, e.g. {"1HA": "1HA01"}


class QueueItem(BaseModel):
    article: str
    article_class: str
    property_to_class: dict[str, str]
    prop_val_to_class: dict[str, str]
    selected_properties: dict[str, list[str]]   # parent-only dimensions
    child_resolutions: dict[str, ChildResolution] = {}  # {child_prop: resolution}
    filename: str = ""  # desired filename for this item inside the zip


class GenerateRequest(BaseModel):
    manufacturer: str
    series: str
    queue: list[QueueItem]
    filename: str = "snapper.obx"
    seed_token: str | None = None


@router.post("/generate")
def generate_obx(req: GenerateRequest):
    """
    Generate OBX file(s) from a queue of article configurations.
    Single-item queue returns XML directly; multi-item returns a zip.
    """
    if not req.queue:
        raise HTTPException(status_code=400, detail="Queue is empty")

    obx_files: list[tuple[str, str]] = []  # (filename, xml_content)

    for item in req.queue:
        # Build article_class_map: {article_code: article_class}
        article_class_map = {item.article: item.article_class}

        # Convert prop_val_to_class from string keys to tuple keys
        pvtc: dict[tuple, str] = {}
        for key_str, cls in item.prop_val_to_class.items():
            eq_idx = key_str.find("=")
            if eq_idx != -1:
                prop_name = key_str[:eq_idx]
                val = key_str[eq_idx + 1:]
                pvtc[(prop_name, val)] = cls

        permutations = compute_permutations([item.article], item.selected_properties)
        # Resolve child properties per-permutation based on that permutation's parent value.
        # This avoids a cartesian explosion (child × parent instead of paired assignment).
        for perm in permutations:
            for child_prop, cr in item.child_resolutions.items():
                parent_val = perm["properties"].get(cr.parent, "")
                child_val = cr.resolution.get(parent_val, "")
                if child_val:
                    perm["properties"][child_prop] = child_val
        seed_xml = _seed_store.get(req.seed_token) if req.seed_token else None
        if seed_xml:
            xml_content = build_obx_from_seed(
                seed_xml,
                permutations,
                item.property_to_class,
                pvtc,
            )
        else:
            xml_content = build_obx(
                permutations,
                article_class_map,
                req.manufacturer,
                req.series,
                item.property_to_class,
                pvtc,
            )
        entry_name = item.filename if item.filename else f"{item.article.replace('/', '_').replace(chr(92), '_')}.obx"
        obx_files.append((entry_name, xml_content))

    if len(obx_files) == 1:
        filename, xml_content = obx_files[0]
        return Response(
            content=xml_content,
            media_type="application/xml",
            headers={"Content-Disposition": f'attachment; filename="{req.filename}"'},
        )

    # Multiple files -> zip
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

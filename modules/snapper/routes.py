from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from pathlib import Path

from .reader import discover_ranges, load_range_data
from .generator import compute_permutations, build_obx

router = APIRouter(prefix="/api/snapper", tags=["snapper"])


@router.get("/ranges")
def list_ranges(repo: str = Query(..., description="Path to OFML repository root")):
    """List all valid ranges found in the repository."""
    return discover_ranges(repo)


@router.get("/range")
def get_range(
    repo: str = Query(...),
    manufacturer: str = Query(...),
    range: str = Query(...),
):
    """Load OCD data for a specific range."""
    db_path = Path(repo) / manufacturer / range / "ANY" / "1" / "db"
    if not db_path.exists():
        raise HTTPException(status_code=404, detail=f"Range not found: {db_path}")
    return load_range_data(str(db_path))


class GenerateRequest(BaseModel):
    repo: str
    manufacturer: str
    range: str
    selected_articles: list[str]
    selected_properties: dict[str, list[str]]  # {prop_name: [selected_values]}
    filename: str = "snapper.obx"


@router.post("/generate")
def generate_obx(req: GenerateRequest):
    """Generate a single OBX file from a generation spec."""
    db_path = Path(req.repo) / req.manufacturer / req.range / "ANY" / "1" / "db"
    if not db_path.exists():
        raise HTTPException(status_code=404, detail="Range not found")

    range_data = load_range_data(str(db_path))

    # Build article_class_map from loaded data
    article_class_map = {a["code"]: a["article_class"] for a in range_data["articles"]}

    # Get manufacturer/series from first article
    mfr_code = range_data["articles"][0]["manufacturer_code"] if range_data["articles"] else req.manufacturer
    series_code = range_data["articles"][0]["series_code"] if range_data["articles"] else req.range.upper()

    permutations = compute_permutations(req.selected_articles, req.selected_properties)
    xml_content = build_obx(permutations, article_class_map, mfr_code, series_code)

    return Response(
        content=xml_content,
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{req.filename}"'}
    )

import csv
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/search", tags=["search"])

SEARCHABLE_FILES = {
    "ocd_article",
    "ocd_artlongtext",
    "ocd_artshorttext",
    "ocd_property",
    "ocd_propertytext",
    "ocd_propvalue",
    "ocd_propvaluetext",
}

VALID_MATCH_MODES = {"contains", "equals", "starts_with", "ends_with"}


class SearchRequest(BaseModel):
    repo: str
    file_types: list[str]
    query: str
    match_mode: str  # contains | equals | starts_with | ends_with
    case_sensitive: bool = False


def _cell_matches(cell: str, query: str, match_mode: str, case_sensitive: bool) -> bool:
    if not case_sensitive:
        cell = cell.lower()
        query = query.lower()
    if match_mode == "contains":
        return query in cell
    if match_mode == "equals":
        return cell == query
    if match_mode == "starts_with":
        return cell.startswith(query)
    if match_mode == "ends_with":
        return cell.endswith(query)
    return False


def _scan_repo(
    repo: str,
    file_types: list[str],
    query: str,
    match_mode: str,
    case_sensitive: bool,
) -> tuple[list[dict], int]:
    repo_path = Path(repo)
    results: list[dict] = []
    ranges_searched = 0

    for mfr_dir in sorted(repo_path.iterdir()):
        if not mfr_dir.is_dir():
            continue
        for range_dir in sorted(mfr_dir.iterdir()):
            if not range_dir.is_dir():
                continue
            db_path = range_dir / "ANY" / "1" / "db"
            if not db_path.is_dir():
                continue
            ranges_searched += 1
            for file_type in file_types:
                csv_path = db_path / f"{file_type}.csv"
                if not csv_path.exists():
                    continue
                matches: list[dict] = []
                try:
                    with open(csv_path, encoding="utf-8", errors="replace", newline="") as f:
                        for row_idx, row in enumerate(csv.reader(f), start=1):
                            if any(
                                _cell_matches(cell, query, match_mode, case_sensitive)
                                for cell in row
                            ):
                                matches.append({"row_number": row_idx, "row": row})
                except OSError:
                    continue
                if matches:
                    results.append({
                        "manufacturer": mfr_dir.name,
                        "range": range_dir.name,
                        "file_type": file_type,
                        "matches": matches,
                    })

    return results, ranges_searched


@router.post("/run")
def run_search(req: SearchRequest):
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="Query must not be empty")
    if not req.file_types:
        raise HTTPException(status_code=400, detail="At least one file type must be selected")
    if req.match_mode not in VALID_MATCH_MODES:
        raise HTTPException(status_code=400, detail=f"Invalid match_mode: {req.match_mode!r}")
    invalid = set(req.file_types) - SEARCHABLE_FILES
    if invalid:
        raise HTTPException(status_code=400, detail=f"Invalid file types: {sorted(invalid)}")
    if not Path(req.repo).is_dir():
        raise HTTPException(status_code=400, detail=f"Repo path not found: {req.repo}")

    start = time.monotonic()
    results, ranges_searched = _scan_repo(
        req.repo, req.file_types, req.query, req.match_mode, req.case_sensitive
    )
    duration_ms = int((time.monotonic() - start) * 1000)

    return {"results": results, "ranges_searched": ranges_searched, "duration_ms": duration_ms}

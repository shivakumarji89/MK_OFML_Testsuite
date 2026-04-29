import csv
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_range(tmp_path, mfr, range_name, file_data: dict[str, list[list[str]]]):
    """Create a minimal fake repo range with CSV files under ANY/1/db/."""
    db = tmp_path / mfr / range_name / "ANY" / "1" / "db"
    db.mkdir(parents=True)
    for fname, rows in file_data.items():
        with open(db / fname, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            for row in rows:
                writer.writerow(row)
    return db


def _search(tmp_path, file_types, query, match_mode="contains", case_sensitive=False):
    return client.post("/api/search/run", json={
        "repo": str(tmp_path),
        "file_types": file_types,
        "query": query,
        "match_mode": match_mode,
        "case_sensitive": case_sensitive,
    })


# ── Basic match modes ──────────────────────────────────────────────────────────

def test_contains_match(tmp_path):
    _make_range(tmp_path, "kno", "tulip", {
        "ocd_propvalue.csv": [
            ["TULIP_FABRIC", "H80040", "Cato Orange"],
            ["TULIP_FABRIC", "K12345", "Other Color"],
        ]
    })
    resp = _search(tmp_path, ["ocd_propvalue"], "H80040")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ranges_searched"] == 1
    assert len(data["results"]) == 1
    result = data["results"][0]
    assert result["manufacturer"] == "kno"
    assert result["range"] == "tulip"
    assert result["file_type"] == "ocd_propvalue"
    assert result["matches"][0]["row_number"] == 1
    assert result["matches"][0]["row"] == ["TULIP_FABRIC", "H80040", "Cato Orange"]


def test_contains_partial(tmp_path):
    _make_range(tmp_path, "kno", "tulip", {
        "ocd_propvalue.csv": [["FABRIC", "PREFIX_H80040_SUFFIX", "val"]]
    })
    resp = _search(tmp_path, ["ocd_propvalue"], "H80040")
    assert len(resp.json()["results"]) == 1


def test_equals_exact_only(tmp_path):
    _make_range(tmp_path, "kno", "tulip", {
        "ocd_propvalue.csv": [
            ["FABRIC", "H80040", "exact"],
            ["FABRIC", "H800400", "longer"],
            ["FABRIC", "0H80040", "prefixed"],
        ]
    })
    resp = _search(tmp_path, ["ocd_propvalue"], "H80040", match_mode="equals", case_sensitive=True)
    data = resp.json()
    assert len(data["results"][0]["matches"]) == 1
    assert data["results"][0]["matches"][0]["row"][1] == "H80040"


def test_starts_with(tmp_path):
    _make_range(tmp_path, "kno", "tulip", {
        "ocd_propvalue.csv": [
            ["FABRIC", "H80040-A", "starts"],
            ["FABRIC", "AH80040", "not starts"],
        ]
    })
    resp = _search(tmp_path, ["ocd_propvalue"], "H80040", match_mode="starts_with", case_sensitive=True)
    data = resp.json()
    assert len(data["results"][0]["matches"]) == 1
    assert data["results"][0]["matches"][0]["row"][1] == "H80040-A"


def test_ends_with(tmp_path):
    _make_range(tmp_path, "kno", "tulip", {
        "ocd_propvalue.csv": [
            ["FABRIC", "AH80040", "ends"],
            ["FABRIC", "H80040-X", "not ends"],
        ]
    })
    resp = _search(tmp_path, ["ocd_propvalue"], "H80040", match_mode="ends_with", case_sensitive=True)
    data = resp.json()
    assert len(data["results"][0]["matches"]) == 1
    assert data["results"][0]["matches"][0]["row"][1] == "AH80040"


# ── Case sensitivity ───────────────────────────────────────────────────────────

def test_case_insensitive_matches_lowercase(tmp_path):
    _make_range(tmp_path, "kno", "tulip", {
        "ocd_propvalue.csv": [["FABRIC", "h80040", "lower"]]
    })
    resp = _search(tmp_path, ["ocd_propvalue"], "H80040", case_sensitive=False)
    assert len(resp.json()["results"]) == 1


def test_case_sensitive_no_match(tmp_path):
    _make_range(tmp_path, "kno", "tulip", {
        "ocd_propvalue.csv": [["FABRIC", "h80040", "lower"]]
    })
    resp = _search(tmp_path, ["ocd_propvalue"], "H80040", case_sensitive=True)
    assert resp.json()["results"] == []


# ── Multiple ranges and file types ────────────────────────────────────────────

def test_no_match_range_excluded(tmp_path):
    _make_range(tmp_path, "hmx", "cosm", {
        "ocd_propvalue.csv": [["COSM_FABRIC", "X99999", "Some Color"]]
    })
    resp = _search(tmp_path, ["ocd_propvalue"], "H80040")
    data = resp.json()
    assert data["results"] == []
    assert data["ranges_searched"] == 1


def test_multiple_ranges_only_matching_returned(tmp_path):
    _make_range(tmp_path, "kno", "tulip", {
        "ocd_propvalue.csv": [["FABRIC", "H80040", "Orange"]]
    })
    _make_range(tmp_path, "kno", "saarinen", {
        "ocd_propvalue.csv": [["FABRIC", "X99999", "Other"]]
    })
    resp = _search(tmp_path, ["ocd_propvalue"], "H80040")
    data = resp.json()
    assert data["ranges_searched"] == 2
    assert len(data["results"]) == 1
    assert data["results"][0]["range"] == "tulip"


def test_multiple_file_types(tmp_path):
    _make_range(tmp_path, "kno", "tulip", {
        "ocd_propvalue.csv": [["FABRIC", "H80040", "Orange"]],
        "ocd_propvaluetext.csv": [["FABRIC", "H80040", "Cato Orange EN"]],
        "ocd_property.csv": [["FABRIC_TYPE", "label"]],
    })
    resp = _search(tmp_path, ["ocd_propvalue", "ocd_propvaluetext"], "H80040")
    data = resp.json()
    file_types = {r["file_type"] for r in data["results"]}
    assert file_types == {"ocd_propvalue", "ocd_propvaluetext"}


def test_missing_csv_file_skipped_gracefully(tmp_path):
    """Range without the requested file type should not cause an error."""
    _make_range(tmp_path, "kno", "tulip", {
        "ocd_propvalue.csv": [["FABRIC", "H80040", "Orange"]]
        # ocd_article.csv intentionally absent
    })
    resp = _search(tmp_path, ["ocd_article", "ocd_propvalue"], "H80040")
    assert resp.status_code == 200
    assert len(resp.json()["results"]) == 1


def test_row_number_is_one_based(tmp_path):
    _make_range(tmp_path, "kno", "tulip", {
        "ocd_propvalue.csv": [
            ["FABRIC", "NOMATCH", "x"],
            ["FABRIC", "H80040", "Orange"],
        ]
    })
    resp = _search(tmp_path, ["ocd_propvalue"], "H80040")
    assert resp.json()["results"][0]["matches"][0]["row_number"] == 2


def test_duration_ms_present(tmp_path):
    _make_range(tmp_path, "kno", "tulip", {
        "ocd_propvalue.csv": [["FABRIC", "H80040", "Orange"]]
    })
    resp = _search(tmp_path, ["ocd_propvalue"], "H80040")
    assert resp.json()["duration_ms"] >= 0


# ── Validation errors ──────────────────────────────────────────────────────────

def test_invalid_repo_path_returns_400():
    resp = client.post("/api/search/run", json={
        "repo": "C:\\nonexistent\\path\\that\\does\\not\\exist",
        "file_types": ["ocd_propvalue"],
        "query": "H80040",
        "match_mode": "contains",
        "case_sensitive": False,
    })
    assert resp.status_code == 400


def test_empty_query_returns_400(tmp_path):
    resp = client.post("/api/search/run", json={
        "repo": str(tmp_path),
        "file_types": ["ocd_propvalue"],
        "query": "",
        "match_mode": "contains",
        "case_sensitive": False,
    })
    assert resp.status_code == 400


def test_invalid_file_type_returns_400(tmp_path):
    resp = client.post("/api/search/run", json={
        "repo": str(tmp_path),
        "file_types": ["ocd_nonexistent"],
        "query": "H80040",
        "match_mode": "contains",
        "case_sensitive": False,
    })
    assert resp.status_code == 400


def test_invalid_match_mode_returns_400(tmp_path):
    resp = client.post("/api/search/run", json={
        "repo": str(tmp_path),
        "file_types": ["ocd_propvalue"],
        "query": "H80040",
        "match_mode": "fuzzy",
        "case_sensitive": False,
    })
    assert resp.status_code == 400

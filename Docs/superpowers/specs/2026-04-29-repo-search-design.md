# Repo Search — Design Spec

**Date:** 2026-04-29
**Status:** Approved

## Overview

A new module in the OFML Testsuite that lets QA users search for a string value across all ranges in a saved repository. The primary use case is identifying which ranges reference a specific finish code or property value (e.g. `H80040`) so that discontinued values can be found and removed.

## Problem

When a finish is discontinued, the team receives a request like "remove Cato Orange H80040 from all ranges." There is currently no way to know which ranges reference that value without manually checking each range's OCD CSVs. This module solves that.

## Module Structure

```
modules/search/
  __init__.py
  routes.py        — scan logic + FastAPI router
static/search/
  index.html       — search UI
  search.js        — all frontend logic
```

`main.py` — add router import and `/search/` page route.
`static/index.html` — add dashboard card.

## API

### `POST /api/search/run`

**Request body:**
```json
{
  "repo": "C:\\path\\to\\_repository",
  "file_types": ["ocd_propvalue", "ocd_propvaluetext"],
  "query": "H80040",
  "match_mode": "contains",
  "case_sensitive": false
}
```

`match_mode` values: `contains`, `equals`, `starts_with`, `ends_with`.
`file_types` is a subset of the seven searchable types (see below).

**Response:**
```json
{
  "results": [
    {
      "manufacturer": "kno",
      "range": "tulip",
      "file_type": "ocd_propvalue",
      "matches": [
        { "row_number": 42, "row": ["TULIP_FABRIC", "H80040", "Cato Orange"] }
      ]
    }
  ],
  "ranges_searched": 12,
  "duration_ms": 340
}
```

- Results ordered by manufacturer → range → file type.
- Ranges with zero matches are omitted.
- `row_number` is 1-based.

## Searchable File Types

The seven OCD CSV files that contain useful data to search by:

| UI label        | File name               |
|-----------------|-------------------------|
| article         | ocd_article.csv         |
| artlongtext     | ocd_artlongtext.csv     |
| artshorttext    | ocd_artshorttext.csv    |
| property        | ocd_property.csv        |
| propertytext    | ocd_propertytext.csv    |
| propvalue       | ocd_propvalue.csv       |
| propvaluetext   | ocd_propvaluetext.csv   |

## Backend Logic

1. Walk `{repo}/{manufacturer}/{range}/ANY/1/db/` paths (same traversal as `discover_ranges` in `reader.py`).
2. For each range, for each selected file type, open the CSV.
3. For each row, test every cell against the query using the chosen match mode and case flag.
4. Collect hits as `{ row_number, row }` and group by range + file type.
5. Return all groups with at least one match, plus `ranges_searched` and `duration_ms`.

No new dependencies — `pathlib`, `csv`, FastAPI only.

## Frontend UI

**Controls:**
- Repo dropdown — populated from `Settings.getSavedRepos()` (localStorage). Falls back to a message with a link to settings if no repos saved.
- Search input — plain text.
- Match mode dropdown — Contains / Equals / Starts with / Ends with.
- Case sensitive toggle — checkbox, default off.
- File type checkboxes — all seven, all checked by default.
- Search button — disabled until repo selected and query non-empty.

**Results:**
- Summary line: "Found X matches across Y ranges (searched Z ranges in 340ms)"
- One collapsible section per matching range, labelled `{manufacturer} / {range}`.
- Inside each section: one sub-table per matching file type, showing raw CSV cells.
- Zero-results state: "No matches found."

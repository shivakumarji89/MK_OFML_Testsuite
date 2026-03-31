# SKU Importer — Design Spec
_Date: 2026-03-31_

## Problem

Full product SKUs (e.g. `AER1B31DW ALP G1 G1 G1 BB BK 23103`) cannot be pasted directly into pCon — only the base article code is accepted. The remaining characters encode property selections that must be configured manually. This module reverse-engineers the OCD code scheme to decode a full SKU into its property values, then generates an OBX file that pCon can import and resolve via Update.

---

## Workflow

1. User pastes SKUs (one per line) or uploads a CSV — smart paste normalises Excel/CSV multi-column content automatically
2. User clicks **Decode** — backend identifies each article, detects code scheme style, decodes properties
3. A results table shows each SKU with its decoded properties and status (green / amber / red)
4. User clicks **Download OBX** — all successfully decoded SKUs are packaged into a single OBX

No editing step — the table is for QA transparency only.

---

## Module Structure

```
modules/sku_importer/
  __init__.py
  decoder.py        — article lookup, style detection, template decoding, relation inversion
  script_decoder.py — script-style: Code formula evaluator + brute-force enumeration + cache
  routes.py         — POST /api/sku-importer/decode, POST /api/sku-importer/generate

static/sku_importer/
  index.html
  sku_importer.js
```

**Reused from snapper:** `modules/snapper/reader.py` (OCD data loading), `modules/snapper/generator.py` (`build_obx`, `build_varcode_multi`), `static/settings.js` (saved repos).

---

## Article Identification

At request time, build an in-memory index by scanning all configured repos:

```
article_index: { article_code → { manufacturer, range, db_path, series_code, codescheme_template } }
```

`codescheme_template` is read from `ocd_codescheme.csv` — the second semicolon-delimited column. For ranges that store the codescheme ID in `ocd_article.csv` column 10 (all Knoll ranges), follow that ID to `ocd_codescheme.csv` to retrieve the template.

**Lookup:** longest-prefix match of the SKU against all known article codes.

**Conflict (same code in multiple ranges):** return all candidates to the frontend. The results table shows an amber "ambiguous" row with an inline range picker. The user selects a range; the frontend re-calls `/decode` for that SKU with the chosen range pinned.

**No match:** red error row — "unrecognised article code".

**Unsupported:** ranges whose codescheme template contains no `@` symbols and no leading article-code literals (currently `kno/matic` only) cannot be identified by prefix. These are flagged as unsupported in the error row.

---

## Code Scheme Style Detection

Inspect the `codescheme_template` string (second column of `ocd_codescheme.csv`):

| Template column | Style |
|---|---|
| No comma — single `Class:Property` reference | **Script** |
| Has commas — positional segment list | **Template** |

This rule is confirmed to be unambiguous across all 118 ranges with a codescheme in the HM and Knoll repos (22 script-style, 96 template-style).

---

## Template Decoding (96 ranges)

Split the template on `,` to get an ordered segment list. Walk segments left-to-right, consuming the SKU string:

- **`@`** — consume one character (matches the article code character at this position; skip)
- **Single literal** (e.g. `K`, `1`, ` `) — consume one character; verify it matches; error if not
- **`Class:Property`** — if the property name starts with `i` and has a relation, it is a computed intermediate (see below); otherwise try each known value for this property (longest-first) and consume the matching one

**Computed `i*` properties:** these are intermediate values not used directly in the varcode. Invert their relation:
- Load the relation expression from `ocd_relation.csv` for this property
- Parse `iXxx='val1' IF ActualProp='actual1'` patterns
- Build `{ computed_value → (actual_property_name, actual_value) }`
- Match the computed value in the SKU; record the actual property-value pair for the varcode

**Building the varcode:** for each decoded property, look up its article class from `ocd_property.csv`. Pre-set properties from `ocd_artbase.csv` (e.g. `Aeron_Type=B` for `AER1B31`) are appended. Use the existing `build_varcode_multi()`.

---

## Script Decoding (22 ranges)

The codescheme references a single computed `Code` property (type `R`). Its formula in `ocd_relation.csv` assembles the SKU from property values via string concatenation and `IF` conditions, e.g.:

```
Code = SUBSTR($BAN,0,3) IF Aeron_Type IN ('A','B','C'),
Code = Code + Assembly_Option + Aeron_Type + ... + ' ' + Back_Support + ' ' + Frame_Finish + ...
     IF Armpads = 'W' AND Aeron_Type IN ('A','B','C')
```

**Approach:** brute-force enumeration with caching.

1. Load all valid property values for the range from OCD data
2. Enumerate all valid combinations (respecting `ocd_artbase.csv` restrictions for the specific article)
3. For each combination, evaluate the formula using a lightweight evaluator that handles:
   - String concatenation: `A + B + ' ' + C`
   - `SUBSTR($BAN, n, m)` — substring of the base article number
   - Conditionals: `IF prop = 'val'` and `IF prop IN ('a','b')`
   - Multiple branches separated by `,`; last matching branch wins
4. Build reverse lookup: `{ full_code → property_values }`
5. Decode = exact lookup; not found = error row

**Cache:** result stored per `(db_path, article_code)` in process memory. First decode for a script-style range takes ~1–5 seconds; subsequent lookups are instant.

---

## OBX Generation

All successfully decoded SKUs (any number of ranges) are combined into a single OBX using the existing `build_obx()` from `generator.py`, with:
- `updateState="Outdated"` on every article — forces pCon to re-resolve on Update
- `pdInfo` populated using `read_prog_id()` per range

No seed template is required. `property_to_class` is derived entirely from `ocd_property.csv`.

---

## Frontend

Page at `/sku-importer/`.

**Input area**
- Textarea: paste SKUs (one per line)
- Smart paste handler: intercepts `paste` event, splits on newlines then tabs/commas, one value per line
- "Upload CSV" button alongside the textarea
- Repo selector: saved repos from `settings.js` (all repos searched by default)
- **Decode** button

**Results table** — columns: SKU | Status | Article | Range | Properties (collapsed, expandable on click)

Status badges:
- Green **Decoded** — ready for OBX
- Amber **Ambiguous** — inline dropdown of matching ranges; re-decodes on selection
- Red **Error** — reason shown inline (unrecognised, unsupported, decode failure)

**Actions bar**
- **Download OBX** button — enabled when ≥ 1 green row; labelled "Download OBX (N SKUs)"
- Count summary: "12 of 15 SKUs decoded"

---

## API

**POST `/api/sku-importer/decode`**
```json
Request:  { "skus": ["AER1B31DW ALP G1 G1 G1 BB BK 23103", ...], "repos": ["C:/..."], "pin": {"sku": "range_key"} }
Response: { "results": [ { "sku": "...", "status": "ok|ambiguous|error", "article": "...", "range": "...", "manufacturer": "...", "series": "...", "properties": {...}, "candidates": [...], "error": "..." } ] }
```

**POST `/api/sku-importer/generate`**
```json
Request:  { "items": [ { "sku": "...", "article": "...", "db_path": "...", "manufacturer_code": "...", "series_code": "...", "prog_id": "...", "properties": {...}, "property_to_class": {...} } ], "filename": "import.obx" }
Response: OBX file (application/xml)
```

---

## Known Limitations

- `kno/matic` (and any future range with no article-code prefix in the code): unsupported — flagged in the UI
- Computed `i*` property inversions assume simple if-else patterns; complex non-invertible transforms will cause a decode error for affected properties
- Script-style enumeration may be slow for ranges with very large combination spaces; a progress indicator should be shown
- Mixed-market SKUs (e.g. Saarinen with `iMarket='I'` suffix for UK): the market property is decoded and included in the varcode, but pCon may override it based on the active market configuration

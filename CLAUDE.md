# OFML Testsuite — Project Context

## What this project is

A local web application for QA verification of OFML data (Office Furniture Markup Language, used by pCon configurators). Built for the MillerKnoll QA team.

The app is a suite of QA modules, each on its own page, linked from a dashboard home. The first module is the **Snapper File Generator**.

### Snapper File Generator — how it works

1. Export a single configured product from pCon Planner as an OBX file (the **seed**).
2. Upload the seed at `/snapper/`. The backend parses the varcode to extract the article, series, and property names, then loads valid values from OCD.
3. Each property appears as a checkbox column. Parent-child property pairs (e.g. fabric type → fabric colour) are detected automatically — the colour column is replaced by a mode toggle ("First only" or "Distribute") below the parent.
4. Select values, optionally label the article, then click **Add to Queue**. Repeat for other articles in the same range.
5. Click **Generate All** to download a single OBX (one article) or a zip of OBX files (multiple articles). Import into pCon and run **Update** to resolve prices and descriptions.

**Matching ("Match to…"):** A property column can be set to track another eligible column in lockstep via its "Match to…" selector (standalone↔standalone, parent↔parent, child↔child; the target must itself be unmatched, which prevents chains). The matched column's value is copied from its target per permutation (the cartesian product collapses to matched pairs), and any matched-only "extra" values the user ticks are appended bound to the target's first-selected value (the anchor). Hierarchical fabrics: matching a fabric **type** to another type auto-matches their colour **children** in lockstep (one action ⇒ identical fabric); colours that don't exist on the matched side are omitted (pCon default).

## Key repositories

**HermanMiller OFML SVN root:**
`C:\HermanMillerOFMLSVN\Staging\HermanMiller\_repository`
Manufacturer folder: `hmx` — Example ranges: `cosm`, `cloud`, `pullman`, `always`, `ratio_rebuild`

**Knoll OFML SVN root:**
`C:\KnollOFMLSVN\Staging\_repository`
Manufacturer folder: `kno` — Example ranges: `saarinen`, and others

OCD source files for a range live at:
`{repo_root}/{manufacturer}/{range}/ANY/1/db/`

## Design spec

Full design: `Docs/superpowers/specs/2026-03-22-ofml-testsuite-design.md`

## Tech stack

- Python + FastAPI backend
- Vanilla HTML + JS frontend (no build step, no npm)
- Tailwind CSS from CDN
- Run: `python main.py` → open `localhost:8080`

## Key domain concepts

- **OBX file:** pCon's proprietary XML export format. Contains `<bskArticle>` entries, each representing a configured product.
- **ofmlvarcode:** The key field in an OBX entry. Format: `ArticleClass.PropertyName=Value;...`. Drives pCon's configuration resolution.
- **Snapper file:** A team term for an OBX file containing one entry per product configuration, used for QA comparison against PDM data.
- **Seed OBX:** A single-article OBX exported from pCon, used as input to the Snapper Generator to drive property discovery.
- **Update (pCon):** A pCon Planner function that re-resolves all configurations in an imported OBX and fills in prices, article codes, descriptions.
- **OCD article class:** Groups of articles sharing the same property set (e.g. `COSM_NORMAL`, `CLOUD_OPT`). The class name is used as the varcode prefix.
- **Hierarchy:** A parent-child property relationship where child values are conditioned on parent values (e.g. `Shell_Fabric_Colour` is conditioned on `Shell_Fabric_Type`). Detected automatically from `ocd_relation.csv` + `ocd_relationobj.csv`.

## Module structure

```
modules/snapper/
  seed_parser.py   — parses uploaded OBX seed file, extracts article/series/properties from varcode
  reader.py        — discovers ranges in the repo, loads OCD CSV data (articles, properties, values, relations)
  hierarchy.py     — detects parent-child property pairs from OCD relation expressions
  generator.py     — computes permutations, builds OBX XML with per-property article class prefixes
  routes.py        — FastAPI routes: POST /api/snapper/parse-seed, POST /api/snapper/generate
static/snapper/
  index.html       — seed upload UI, property columns, queue sidebar
  snapper.js       — all frontend logic: seed parsing, column rendering, hierarchy modes, queue, download
```

## API

**POST `/api/snapper/parse-seed`** — multipart: `file` (OBX) + `repo` (path string)
Returns: `{ article, manufacturer, series, repo, db_path, property_columns }`
Each column: `{ name, article_class, seed_value, values, is_child, parent, mapping }`

**POST `/api/snapper/generate`** — JSON: `{ manufacturer, series, queue, filename }`
Each queue item: `{ article, article_class, property_to_class, prop_val_to_class, selected_properties, child_resolutions, match_resolutions }`
- `match_resolutions`: `{ matched_prop: { match_to, matched_values, extras } }` — lockstep matching of a column to an earlier column (see "Matching" above).
Returns: XML (single item) or ZIP (multiple items)

## OFML documentation

Reference docs are in `Docs/`. The most relevant:
- `ocd_4.3_en.md` — OCD data model, property/value/relation tables
- `AN-2014-04_OCD_Features-EN.md` — OCD features and conditions

## OFML data variability

OFML product data is authored by different companies and teams, using different tools and conventions. This means the internal structure of OCD data can vary significantly between manufacturers, and even between ranges within the same manufacturer. There is no single "canonical" implementation — always investigate multiple ranges before drawing conclusions, and ground analysis in the official OFML documentation in `Docs/`.

Two known structural styles for code schemes (how a full SKU is constructed from property values):

- **HM style (e.g. Aeron):** `ocd_codescheme.csv` references a computed `Code` property (e.g. `AERON_OPTIONS:Code`). The full SKU formula lives in `ocd_relation.csv` as a mini-script: `Code = SUBSTR($BAN,0,3) + Assembly_Option + Aeron_Type + ...`. Properties are concatenated — some without spaces (positional), some with spaces as delimiters.
- **Knoll style (e.g. Saarinen):** `ocd_codescheme.csv` contains a positional template directly: `@,@,@,@,@,Structure_Table:iStrFinish,K,Market:iMarket, ,Upholstery_Tulip:Group, ,Upholstery_Tulip:iFinish`. `@` = individual characters from the base article code. `ArticleClass:Property` = property value at that position. Segments may reference intermediate computed properties (e.g. `iStrFinish`, `iMarket`) whose values are derived from another relation.

Other variations to be aware of:
- Multi-market ranges have additional market folders (e.g. `ALLEURO`, `ALLGBP`) alongside `ANY` — these may have separate pricing but typically share OCD structure.
- Some ranges have sub-range OAM namespaces that don't match the range folder name — the `read_prog_id` function handles this.

## Known limitations

- Hierarchy detection requires ALL values of a property to be conditioned on the same parent. In some ranges (e.g. CLOUD), fabric colour values have mixed condition types (`*`-prefixed or `$`-prefixed expressions), which prevents automatic detection. In that case the colour column renders as a normal checkbox column.
- Varcode prefix is the OCD article class name, read directly from the seed's varcode — no lookup needed.

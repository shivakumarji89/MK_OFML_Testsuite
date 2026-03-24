# OFML Testsuite — Design Spec
**Date:** 2026-03-22
**Status:** Approved
**First module:** Snapper File Generator

---

## 1. Project Overview

A local web application for QA verification of OFML data. The team creates OFML data manually from a PDM source of truth; this tool supports systematic QA by automating the creation of pCon "snapper" files (OBX format) and potentially other QA tasks in the future.

The app is structured as a **suite of modules**, each on its own page, linked from a dashboard home. The first module is the **Snapper File Generator**, which programmatically generates OBX files containing all meaningful product permutations for a given range — replacing the manual process of configuring each product in pCon Planner one by one.

**Workflow context:**
1. User generates an OBX file using this tool
2. User imports the OBX into pCon Planner
3. User runs pCon's "Update" function to resolve all configurations
4. User exports the resolved OBX
5. The exported OBX is compared against PDM data to verify article codes and prices

---

## 2. Architecture

### Option chosen: Separate pages per module, dashboard home

Each module is its own HTML page. A home screen (`index.html`) presents cards linking to each module. No single-page-app routing — navigation is standard page links.

**Rationale:** Cleanest isolation between modules. Simple to add new modules without touching existing ones. Acceptable UX trade-off since modules are independent workflows.

### Tech stack
- **Backend:** Python + FastAPI. Serves static HTML and exposes JSON API endpoints.
- **Frontend:** Vanilla HTML + JavaScript. Tailwind CSS loaded from CDN. No build step, no npm.
- **State:** All session state (queue, selections) lives in the browser (localStorage / in-memory JS). The backend is stateless.
- **Distribution:** QA team receives a folder. One-time setup: `pip install -r requirements.txt`. Run: `python main.py`. Open `localhost:8080` in browser.

### Folder structure
```
ofml_testsuite/
  main.py                        # FastAPI app entry point, mounts all module routers
  requirements.txt
  CLAUDE.md                      # Project context for AI-assisted development
  modules/
    snapper/
      routes.py                  # API endpoints for the snapper module
      reader.py                  # OCD file parsing logic
      generator.py               # OBX permutation + generation logic
      hierarchy.py               # Property dependency / fabric-type detection logic
  static/
    index.html                   # Home dashboard — module cards
    snapper/
      index.html                 # Snapper Generator page
      snapper.js                 # Frontend logic
```

---

## 3. OFML Repository Structure

The tool works against local OFML SVN repositories. The path to the repository root is configured by the user (saved in browser localStorage). The repository root may vary — the user provides the full path to it.

**Known repository:** `C:\HermanMillerOFMLSVN\Staging\HermanMiller\_repository`

Within a repository, structure is:
```
{repository_root}/
  {manufacturer}/              e.g. hmx
    {range}/                   e.g. cosm, cloud, pullman
      ANY/
        1/
          db/                  ← OCD source files live here
            ocd_article.csv
            ocd_artbase.csv
            ocd_property.csv
            ocd_propertyvalue.csv
            ocd_relation.csv
            ocd_relationobj.csv
            fabric_colour_tbl.csv   ← present only on some ranges
            ...
      1/                       ← GO + geometry files live here
        go_*.csv
        *.ofml
        ...
```

**Key assumption:** The market subfolder is always `ANY` and the version is always `1`. If this changes for specific ranges, the path resolution logic in `reader.py` will need to handle it.

---

## 4. OCD Data Model (reader.py)

### Files read and their schemas

**`ocd_article.csv`** — Base article codes for the range
Columns (semicolon-delimited, no header):
`BaseArticleCode ; Type ; ManufacturerCode ; SeriesCode ; ...`
- Column 0: base article code (e.g. `FLC142`)
- Column 1: article type — `C` = configurable (the ones we care about)
- Column 2: manufacturer code (e.g. `HM`) — used in OBX output
- Column 3: series code (e.g. `COSM`) — used in OBX output

**`ocd_artbase.csv`** — Maps article codes to their article class and default property values
Columns: `BaseArticleCode ; ArticleClass ; PropertyName ; DefaultValue`
- Used to determine the OCD article class for each base article (needed for varcode prefix)
- Each base article belongs to exactly one article class

**`ocd_property.csv`** — Properties available per article class
Columns: `ArticleClass ; PropertyName ; SortOrder ; PropertyClassId ; RelationId ; ...`
- Column 0: article class (e.g. `COSM_NORMAL`)
- Column 1: property name (e.g. `Arms`, `Back_Height`)
- Column 2: sort order (used for display ordering in UI)
- Column 4: relation ID — condition controlling when this property is visible (0 = always visible)

**`ocd_propertyvalue.csv`** — Valid values per property
Columns: `ArticleClass ; PropertyName ; SortOrder ; ValueId ; RelationId ; DefaultFlag ; ... ; Value`
- Column 0: article class
- Column 1: property name
- Column 2: sort order (used for ordering values in UI)
- Column 4: relation ID — condition controlling when this specific value is available
- Column 5: default flag (1 = this is the default value)
- Last column: the actual value code (e.g. `N`, `H`, `rilsanwh`)

**`ocd_relation.csv`** — Condition expressions
Columns: `RelationId ; LineNumber ; "ConditionExpression"`
- Multi-line relations are split across rows with the same RelationId
- Full condition is the concatenation of all lines for a given RelationId
- Expression examples:
  - `(SPECIFIED Seat_Fabric_Type) AND (Seat_Fabric_Type IN ('1HA'))` — value is available when another property has a specific value
  - `$ BAN IN ('NOCLE100', 'NOCLE200')` — article-level restriction
  - `* comment text` — developer comment, not a condition

**`ocd_relationobj.csv`** — Links relation IDs to property value IDs
Columns: `RelationId ; SeqNum ; LinkedRelationId ; RelationType ; C_or_P`
- Links a property value (identified by its ValueId) to a relation condition

---

## 5. Property Hierarchy Detection (hierarchy.py)

This is the most complex part of the data layer. Some property pairs have a parent-child dependency: every value of the child property is conditioned on a specific value of the parent property. The most common example is fabric type → fabric colour, but the same pattern applies to any hierarchical property (e.g. material type → finish options within that material).

If not handled, these pairs cause combinatorial explosion: 10 fabric types × 50 colours = 500 combinations instead of 10 meaningful ones.

### Detection strategy

**Primary: `fabric_colour_tbl.csv` (when present)**

Some ranges include an explicit mapping table. Format:
`RowNum ; CATEGORY ; ValueCode`

Where `CATEGORY` is either `COL_FABRIC_TYPE` or `COL_FABRIC_COLOUR`. A row with `COL_FABRIC_TYPE` marks the start of a new type group; all subsequent `COL_FABRIC_COLOUR` rows until the next `COL_FABRIC_TYPE` entry are the colours belonging to that type.

When this file exists in the `db/` folder, use it directly to build the type→colours map. The `ValueCode` values are property value codes matching the last column of `ocd_propertyvalue.csv`.

**Fallback: relation expression parsing (when no table present)**

Algorithm (implemented in `hierarchy.py`):

```
FOR each property P in the range:
    values = all values of P from ocd_propertyvalue.csv

    IF len(values) == 0: skip

    # Collect relation expressions for each value
    conditions = {}
    FOR each value V of P:
        IF V.relation_id is not empty:
            expression = concatenate all ocd_relation rows for V.relation_id
            conditions[V.value_code] = expression

    # Check if ALL values have conditions referencing the same single parent property
    IF len(conditions) != len(values): continue  # not all values conditioned → not hierarchical

    parent_refs = SET()
    parent_value_map = {}  # parent_value → [child_values]

    FOR each (value_code, expression) in conditions:
        parsed = parse_single_property_condition(expression)
        # parse_single_property_condition returns (parent_property_name, parent_value)
        # if expression matches: (SPECIFIED X) AND (X IN ('val'))
        # or: SPECIFIED X AND X IN ('val')
        # Returns None if expression is complex, multi-property, or article-level

        IF parsed is None: break  # complex condition → not hierarchical
        parent_name, parent_val = parsed
        parent_refs.add(parent_name)
        parent_value_map.setdefault(parent_val, []).append(value_code)

    IF len(parent_refs) == 1:  # all values reference the same parent property
        parent_property = parent_refs.pop()
        # Verify parent_property exists as a property in the same article class
        IF parent_property in properties_for_this_class:
            register_hierarchy(parent=parent_property, child=P, mapping=parent_value_map)
```

**`parse_single_property_condition(expression)`:**

Parses condition expressions of these forms (both with and without outer parentheses):
- `(SPECIFIED PropertyName) AND (PropertyName IN ('val1', 'val2'))`
- `SPECIFIED PropertyName AND PropertyName IN ('val1')`

Returns `(property_name, value)` if the expression references exactly one property and exactly one value in the IN clause. Returns `None` for:
- Article-level conditions (starting with `$`)
- Comment lines (starting with `*`)
- Expressions referencing multiple properties
- IN clauses with multiple values (these are conditional dependencies, not hierarchical)
- Any expression that doesn't match the expected pattern

**Manual override:**

After auto-detection, the UI displays a "Property relationships" section before the dimension columns. Each detected hierarchy is shown as `ParentProperty → ChildProperty`. The user can:
- Remove a detected relationship (treat both as independent dimensions)
- Manually add a relationship if auto-detection missed it

This is the safety valve for partially-authored ranges or unusual structures.

### Impact on UI and permutation engine

When a hierarchy is detected between properties A (parent) and B (child):
- A and B are **not** shown as separate dimension columns
- They are merged into one linked column showing only the parent values as checkboxes
- A colour mode selector appears below: **First only** or **Distribute**
  - **First only:** for each selected parent value, always use `child_values[0]` (the first colour/finish in the mapping)
  - **Distribute:** for each selected parent value, track how many permutations have already used it (counter `n`), and assign `child_values[n % len(child_values)]`
- The child dimension **does not participate** in the cartesian product — it is assigned after the product is computed

---

## 6. Snapper Generator: UI Design

### Page layout

**Header bar (top, full width):**
- App title / back-to-home link
- Repo path input (text field, persisted in localStorage)
- Manufacturer dropdown (populated after valid repo path)
- Range dropdown (populated after manufacturer selection)
- "Load range" button

**Main area (below header, full width):**
Three panels left to right:

**Panel 1 — Detected relationships (collapsible)**
Shows the output of hierarchy detection. Each row: `ParentProperty → ChildProperty [remove]`. A manual "Add relationship" control. Hidden by default once user has reviewed it.

**Panel 2 — Dimension columns (scrollable horizontally)**
One column per dimension, displayed side by side. Each column:
- Header: property name (or "Articles" for the article code dimension)
- Scrollable list of checkboxes, one per value, all checked by default
- For linked fabric/hierarchy columns: checkbox list shows only parent values, with colour mode toggle (First only / Distribute) below

Live permutation counter at the bottom of this panel:
- Shows: `X permutations across Y articles`
- Turns amber at >200, red at >500 with a warning message
- Suggested upper limit: 500 items per file (configurable)

**Panel 3 — Generation queue**
- Name field + "Add to queue" button
- Queue list: each entry is a card showing name, permutation count, summary of selections, remove button
- "Generate all" button at bottom: produces one OBX file per entry, downloads as a zip

---

## 7. OBX Generation Logic (generator.py)

### Minimal OBX entry

The generated OBX contains the minimum required for pCon to resolve the configuration via its Update function. The exact minimum is **to be verified empirically** — import a test file, run Update, and check what pCon accepts vs rejects.

Current working assumption (to be tested):

```xml
<?xml version='1.0'?>
<cutBuffer>
  <state sessionId='{uuid}'/>
  <versionInfo vendorKey='EasternGraphics' appKey='EAI-Server' appVersion='4.18.3' bskXmlVersion='1.8.10'/>
  <items>
    <bskArticle basketId='{uuid}' itemType='BasketAggregate' updateState='UpToDate'>
      <manufacturer id='{mfr_code}'/>
      <series id='{series_code}'/>
      <artNr type='base'>{base_article_code}</artNr>
      <artNr type='ofmlvarcode'>{varcode_string}</artNr>
    </bskArticle>
    <!-- one bskArticle per permutation -->
  </items>
</cutBuffer>
```

If pCon requires more fields (e.g. description, price stubs), they can be added as empty/placeholder elements. The `updateState='UpToDate'` value may need to be `'Outdated'` to force pCon to re-resolve — this is another thing to test.

**UUIDs:** Generate fresh `uuid4` for each `basketId`. The `sessionId` can be one shared UUID per file.

**`appVersion`:** Hardcode `4.18.3` initially (matches the example OBX). May need to be configurable if the team's pCon version differs.

### Varcode construction

Each base article maps to exactly one article class (from `ocd_artbase.csv`). The varcode for a permutation:

```
ArticleClass.Prop1=Val1;ArticleClass.Prop2=Val2;...
```

Example: article `FLC142` (class `COSM_NORMAL`), Arms=N, Back_Height=4:
```
COSM_NORMAL.Arms=N;COSM_NORMAL.Back_Height=4
```

Only properties selected by the user in the UI are included in the varcode. Properties not included are left for pCon to default.

**Note on MetaType prefix:** The article class name (e.g. `COSM_NORMAL`) is used as the varcode prefix. This assumption is based on observed OBX examples where prefixes like `Structure_Table`, `Table_Top`, `StructureSofa`, `Upholstery` match OCD article class names in the corresponding range. **Verify this against a cosm OBX if one exists, before full implementation.**

### Permutation engine

```
1. Get selected articles: [A1, A2, ...]
2. Get selected property dimensions: {Prop1: [v1, v2], Prop2: [v3, v4], ...}
   (hierarchy child properties are excluded here — handled separately)
3. Compute cartesian product of all dimensions including articles:
   product = cartesian([articles] + [prop_values for each prop])
4. For each combination in product:
   a. article = combination[0]
   b. prop_assignments = zip(prop_names, combination[1:])
   c. Resolve fabric/hierarchy assignments:
      FOR each (parent_prop, child_prop) in detected hierarchies:
          parent_val = prop_assignments[parent_prop]
          colours = hierarchy_map[parent_prop][parent_val]
          IF mode == 'first':
              child_val = colours[0]
          IF mode == 'distribute':
              n = usage_counter[(parent_prop, parent_val)]
              child_val = colours[n % len(colours)]
              usage_counter[(parent_prop, parent_val)] += 1
          prop_assignments[child_prop] = child_val
   d. Build varcode from all prop_assignments
   e. Emit bskArticle XML element
```

### Queue → files

Each queue entry stores the complete selection state (selected articles, selected property values per property, hierarchy modes). On "Generate all":
1. Backend receives all queue entries as a JSON array
2. For each entry, runs the permutation engine and builds an OBX XML document
3. All OBX files are zipped and returned as a single download

---

## 8. Home Dashboard (index.html)

Simple page with a grid of module cards. Initially one card: "Snapper File Generator". Each card has a title, short description, and a link to the module page.

Design intent: communicates "this is a QA suite" from day one, even with one module.

---

## 9. Future Modules

No specific modules are defined yet. To add a new module:
1. Create `modules/{name}/routes.py`, `reader.py`, `generator.py` as needed
2. Register the router in `main.py`
3. Add `static/{name}/index.html` and supporting JS
4. Add a card to `static/index.html`

No existing code needs to change.

---

## 10. Open Questions / Empirical Validation Needed

1. **Minimum OBX entry:** What is the minimum XML structure pCon will accept for the Update step? Test by generating a 3-item file and importing it. Try with just `<manufacturer>`, `<series>`, `<artNr type='base'>`, `<artNr type='ofmlvarcode'>`. If Update fails, try adding empty `<features/>`, `<description/>` stubs.

2. **`updateState` value:** Does `'UpToDate'` cause pCon to skip re-resolution? Try `'Outdated'` if Update doesn't modify the entries.

3. **Varcode prefix format:** Confirm the article class name is the correct prefix for the varcode. Find or create a cosm OBX to compare expected varcode format.

4. **`appVersion`:** Confirm whether pCon cares about the `appVersion` attribute in `<versionInfo>`. May need to match the installed pCon version.

5. **`ANY/1/db` path assumption:** Verify all target ranges use `ANY` as the market subfolder and `1` as the version. Flag any exceptions before implementing path resolution.

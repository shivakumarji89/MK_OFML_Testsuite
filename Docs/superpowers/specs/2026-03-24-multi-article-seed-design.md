# Multi-Article Seed Support — Design Spec

**Date:** 2026-03-24
**Feature:** Multi-article seed parsing with grouped tabs in the Snapper Generator

---

## Background

The Snapper Generator currently uses only the first `bskArticle` in an uploaded seed OBX. Many product ranges include multiple articles in a single export (e.g. NOHAN1 single-seat + NOHAN2 double-seat, plus a 2-fabric variant). This feature enables users to generate across multiple articles in a single session.

---

## Grouping Logic

After parsing all `bskArticle` elements from the seed, articles are grouped by their **frozenset of property names**. Two articles are in the same group if and only if they share exactly the same set of property names — values and article classes may differ.

Each group becomes one independent generation workspace (tab). Articles in the same group can be cross-generated together. Articles in different groups cannot.

---

## Backend Changes

### `seed_parser.py`

- Parse **all** `bskArticle` elements, not just the first.
- For each article extract:
  - `article` — base article code (e.g. `NOHAN1`)
  - `label` — short description text, English first, fallback to first available language
  - `manufacturer`, `series`
  - `properties` — list of `{ name, article_class, seed_value }`
- Return a list of article dicts (replacing the current single-article return).

### `routes.py` — `/parse-seed`

After parsing, group articles by `frozenset(prop["name"] for prop in article["properties"])`.

For each group:
- Build `property_columns` from the first article (OCD values are the same for all articles in the group).
- Build per-article class maps: `property_to_class` and `prop_val_to_class`.
- Store the first article's raw XML in `_seed_store` as the seed template for `build_obx_from_seed`.
- Assign a unique `seed_token` per group.

**Response shape changes** from a flat response to a `groups` array:

```json
{
  "manufacturer": "HM",
  "series": "HATCH",
  "repo": "...",
  "db_path": "...",
  "groups": [
    {
      "id": "group-0",
      "articles": [
        {
          "code": "NOHAN1",
          "label": "Hatch - Single seat",
          "property_to_class": { "Type": "HATCH_ATTR_CHAIR", ... },
          "prop_val_to_class": { "Type=20": "HATCH_ATTR_CHAIR", ... }
        },
        {
          "code": "NOHAN2",
          "label": "Hatch - Double seat",
          "property_to_class": { "Type": "HATCH_ATTR_NEW", ... },
          "prop_val_to_class": { "Type=20": "HATCH_ATTR_NEW", ... }
        }
      ],
      "property_columns": [ ... ],
      "seed_token": "abc123"
    },
    {
      "id": "group-1",
      "articles": [
        {
          "code": "NOHAN1",
          "label": "Hatch - Single seat (2 fabrics)",
          "property_to_class": { ... },
          "prop_val_to_class": { ... }
        }
      ],
      "property_columns": [ ... ],
      "seed_token": "def456"
    }
  ]
}
```

### `/generate` endpoint

`QueueItem` gains an `articles` field — a list of `{ code, property_to_class, prop_val_to_class }` — replacing the current single `article` + `article_class` + `property_to_class` + `prop_val_to_class` fields.

At generate time, for each queue item:
1. Compute the cartesian product across the selected article codes × selected property values.
2. For each permutation, look up the correct `property_to_class` / `prop_val_to_class` for that article.
3. Build the varcode using the per-article class map.

This ensures `HATCH_ATTR_CHAIR.Type=20` for NOHAN1 and `HATCH_ATTR_NEW.Type=20` for NOHAN2.

---

## Frontend Changes

### Tab strip

Replaces the blue `seedInfo` bar. One tab per group. Tab label = comma-separated article codes in the group (e.g. `NOHAN1, NOHAN2` or `NOHAN1`). The active tab is highlighted. Clicking a tab switches the active workspace.

Manufacturer and series remain in the page header (shared across all groups).

### Article column

In groups with 2 or more articles, a checkbox column named `Article` is prepended before the property columns. It follows the same visual pattern as other checkbox columns (All / None buttons, one checkbox per article). All articles are checked by default.

Each row renders as:
```
☑  NOHAN1  ·  Hatch - Single seat
☑  NOHAN2  ·  Hatch - Double seat
```

(Code in monospace, label alongside — same pattern as property value rows with labels.)

The article column participates in the cartesian product like any other dimension.

In single-article groups, no article column is shown (behaviour identical to today).

### Filename assembly

`assembleFilename(series, article, label, stage)` — `article` resolves to:
- The single article code if exactly one article checkbox is checked
- `multiple_articles` if two or more are checked
- Add to Queue button is disabled if zero articles are checked

### State management

- `currentSeed` holds the full parsed response (all groups).
- `currentGroupIndex` (integer) tracks the active tab.
- `groupStates[]` — one entry per group — stores the checkbox selection state for each tab so switching tabs preserves selections.

### Queue items

Each queued item stores:
- `groups_articles` — the selected articles array `[{ code, label, property_to_class, prop_val_to_class }]`
- `seed_token` — from the group
- `selectedProperties`, `childResolutions` — as today
- `filename`, `label`, `series`, `manufacturer` — as today

The single `article` / `articleClass` / `propertyToClass` / `propValToClass` fields are replaced by the above.

---

## Naming Rules

| Checked articles | Filename token |
|---|---|
| 1 article | that article's code |
| 2+ articles | `multiple_articles` |
| 0 articles | (button disabled) |

---

## Unchanged

- Property column rendering (checkbox columns, child hierarchy columns)
- Permutation counter logic
- Queue card rendering
- Clean OBX flow
- Generate endpoint ZIP/single logic

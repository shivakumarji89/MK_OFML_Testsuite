# Settings Panel — Saved Repositories

**Date:** 2026-03-24
**Status:** Approved

## Summary

A shared settings panel (gear icon → modal) that lets users save, name, rename, and delete repository paths. The panel is designed to grow — saved repos is the first section, with future preference sections (e.g. export paths) slotting in below.

---

## Data Model

Stored in `localStorage` under the key `ofml_settings`:

```json
{
  "savedRepos": [
    { "id": "abc123", "name": "Herman Miller", "path": "C:\\HermanMiller\\_repository" },
    { "id": "def456", "name": "Knoll", "path": "C:\\Knoll\\_repository" }
  ]
}
```

Each saved repo has a randomly generated `id` (used as a stable key for rename/delete), a display `name`, and a `path` string.

---

## Architecture

### `static/settings.js` — new shared module

Owns all settings state. Loaded on every page via a `<script>` tag.

**Exposes:**
- `Settings.getSavedRepos()` → array
- `Settings.addRepo(name, path)` → new entry
- `Settings.renameRepo(id, newName)`
- `Settings.deleteRepo(id)`
- `initSettingsGear(headerEl)` → injects the gear icon into the given header element and wires up the modal

**Events fired (on `document`):**
- `settings:savedReposChanged` — fired after any add/rename/delete so pages can update their UI without a reload

The modal is rendered into a `<div>` appended to `<body>` by `initSettingsGear`. Only one instance exists per page.

---

## Settings Modal

Opened by clicking the gear icon. Sections are separated by headings; future sections slot in below repos.

### Saved Repositories section

- Lists all saved repos as rows: **name** · truncated path · Rename button · Delete button
- **Rename:** clicking Rename replaces the name text inline with an `<input>` + Save/Cancel buttons. No nested modals.
- **Delete:** removes the entry immediately. No confirmation dialog — re-adding is cheap.
- **Add repository form** at the bottom of the section:
  - Name field (text input)
  - Path field (text input) — pre-filled with the current repo text input value when opened from the Snapper page
  - Add button — disabled until both fields are non-empty

---

## Snapper Page Changes

### Header

The repo area in the header gains a dropdown when one or more saved repos exist:

```
[Dropdown: Herman Miller ▼]  [text input: C:\path\_repository]  [⚙]
```

- Dropdown options: one entry per saved repo (by name) + `— Custom path —` at the bottom
- Selecting a saved repo fills the text input with that repo's path
- Editing the text input manually switches the dropdown to `— Custom path —`
- When no saved repos exist: dropdown is hidden; only the text input and gear icon are shown (no regression from current behaviour)
- Gear icon sits at the right edge of the header on all pages

### Event handling

`snapper.js` listens for `settings:savedReposChanged` and rebuilds the dropdown in place. No page reload needed.

---

## Files Changed

| File | Change |
|------|--------|
| `static/settings.js` | New — shared settings module |
| `static/snapper/index.html` | Add `<script src="/static/settings.js">`, call `initSettingsGear`, add repo dropdown markup |
| `static/snapper/snapper.js` | Add repo dropdown logic, listen for `settings:savedReposChanged` |

---

## Future Sections

The modal is built with named sections separated by `<hr>` + heading. Adding a new preference section means appending a new block inside the modal — no structural changes required.

Examples of likely future sections:
- Export path defaults
- Default manufacturer filter

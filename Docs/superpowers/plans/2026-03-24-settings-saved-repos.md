# Settings Panel — Saved Repositories Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a shared settings panel (gear icon → modal) that lets users save, name, rename, and delete repository paths, with a dropdown on the Snapper page to select from saved repos.

**Architecture:** A new `static/settings.js` shared module owns all settings state in `localStorage` and provides `initSettingsGear(headerEl, options)` which each page calls to inject the gear icon and modal. The Snapper page gains a repo dropdown that reflects saved repos and listens for `settings:savedReposChanged` to stay in sync.

**Tech Stack:** Vanilla JS, Tailwind CSS (CDN), localStorage — no build step, no framework.

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `static/settings.js` | Create | Settings data layer + gear icon + modal rendering + event wiring |
| `static/snapper/index.html` | Modify | Load settings.js, add gear anchor in header, add repo dropdown markup |
| `static/snapper/snapper.js` | Modify | Repo dropdown logic, sync with settings events |
| `static/index.html` | Modify | Load settings.js, add gear anchor in header |

---

## Chunk 1: Create `static/settings.js`

### Task 1: Data layer — read/write saved repos

**Files:**
- Create: `static/settings.js`

The Settings object reads and writes a single localStorage key `ofml_settings` containing `{ savedRepos: [{id, name, path}] }`. IDs are generated with `crypto.randomUUID()`.

- [ ] **Step 1: Create `static/settings.js` with the Settings object**

```js
// ── Settings storage key ────────────────────────────────────────────────────
const SETTINGS_KEY = 'ofml_settings';

// ── Settings data layer ─────────────────────────────────────────────────────
const Settings = {
  _load() {
    try {
      return JSON.parse(localStorage.getItem(SETTINGS_KEY)) || { savedRepos: [] };
    } catch { return { savedRepos: [] }; }
  },
  _save(data) {
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(data));
  },
  getSavedRepos() {
    return this._load().savedRepos;
  },
  addRepo(name, path) {
    const data = this._load();
    const entry = { id: crypto.randomUUID(), name: name.trim(), path: path.trim() };
    data.savedRepos.push(entry);
    this._save(data);
    return entry;
  },
  renameRepo(id, newName) {
    const data = this._load();
    const repo = data.savedRepos.find(r => r.id === id);
    if (repo) { repo.name = newName.trim(); this._save(data); }
  },
  deleteRepo(id) {
    const data = this._load();
    data.savedRepos = data.savedRepos.filter(r => r.id !== id);
    this._save(data);
  },
};
```

- [ ] **Step 2: Verify manually in browser console**

Open any page, open DevTools console, run:
```js
Settings.addRepo('Test', 'C:\\test');
console.log(Settings.getSavedRepos());  // [{id:..., name:'Test', path:'C:\\test'}]
Settings.deleteRepo(Settings.getSavedRepos()[0].id);
console.log(Settings.getSavedRepos());  // []
```

Expected: both assertions hold.

- [ ] **Step 3: Commit**

```bash
git add static/settings.js
git commit -m "feat: add settings data layer (savedRepos in localStorage)"
```

---

### Task 2: Modal HTML + gear icon injection

**Files:**
- Modify: `static/settings.js`

`initSettingsGear(headerEl, options)` appends the modal to `<body>` and a gear button to `headerEl`. The `options` object is optional and may contain `getCurrentPath: () => string` — used to pre-fill the path field when the modal opens on a page that has a repo input.

- [ ] **Step 1: Add `initSettingsGear` to `settings.js` — modal HTML + gear button**

Append to `static/settings.js`:

```js
// ── HTML safety ─────────────────────────────────────────────────────────────
function _esc(str) {
  return String(str)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

// ── Changed event ────────────────────────────────────────────────────────────
function _emitChanged() {
  document.dispatchEvent(new CustomEvent('settings:savedReposChanged'));
}

// ── Gear icon injection ─────────────────────────────────────────────────────
function initSettingsGear(headerEl, options = {}) {
  // ── Gear button ────────────────────────────────────────────────────────────
  const gearBtn = document.createElement('button');
  gearBtn.id = 'settingsGearBtn';
  gearBtn.title = 'Settings';
  gearBtn.className = 'ml-auto text-gray-400 hover:text-gray-600 flex-shrink-0';
  gearBtn.innerHTML = `
    <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
      <path stroke-linecap="round" stroke-linejoin="round"
        d="M10.343 3.94c.09-.542.56-.94 1.11-.94h1.093c.55 0 1.02.398 1.11.94l.149.894c.07.424.384.764.78.93.398.164.855.142 1.205-.108l.737-.527a1.125 1.125 0 0 1 1.45.12l.773.774c.39.389.44 1.002.12 1.45l-.527.737c-.25.35-.272.806-.107 1.204.165.397.505.71.93.78l.893.15c.543.09.94.559.94 1.109v1.094c0 .55-.397 1.02-.94 1.11l-.894.149c-.424.07-.764.383-.929.78-.165.398-.143.854.107 1.204l.527.738c.32.447.269 1.06-.12 1.45l-.774.773a1.125 1.125 0 0 1-1.449.12l-.738-.527c-.35-.25-.806-.272-1.203-.107-.398.165-.71.505-.781.929l-.149.894c-.09.542-.56.94-1.11.94h-1.094c-.55 0-1.019-.398-1.11-.94l-.148-.894c-.071-.424-.384-.764-.781-.93-.398-.164-.854-.142-1.204.108l-.738.527c-.447.32-1.06.269-1.45-.12l-.773-.774a1.125 1.125 0 0 1-.12-1.45l.527-.737c.25-.35.272-.806.108-1.204-.165-.397-.506-.71-.93-.78l-.894-.15c-.542-.09-.94-.56-.94-1.109v-1.094c0-.55.398-1.02.94-1.11l.894-.149c.424-.07.764-.384.93-.78.165-.398.143-.854-.108-1.204l-.526-.738a1.125 1.125 0 0 1 .12-1.45l.773-.773a1.125 1.125 0 0 1 1.45-.12l.737.527c.35.25.807.272 1.204.107.397-.165.71-.505.78-.929l.15-.894Z" />
      <path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z" />
    </svg>`;
  headerEl.appendChild(gearBtn);

  // ── Modal ──────────────────────────────────────────────────────────────────
  const modalWrapper = document.createElement('div');
  modalWrapper.id = 'settingsModal';
  modalWrapper.className = 'fixed inset-0 bg-black bg-opacity-40 z-50 hidden items-center justify-center';
  modalWrapper.innerHTML = `
    <div class="bg-white rounded-lg shadow-xl p-6 w-[480px] max-w-full mx-4 max-h-[80vh] overflow-y-auto">
      <div class="flex justify-between items-center mb-4">
        <h2 class="font-semibold text-gray-800 text-lg">Settings</h2>
        <button id="settingsModalClose" class="text-gray-400 hover:text-gray-600 text-2xl leading-none">&times;</button>
      </div>

      <h3 class="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">Saved Repositories</h3>
      <div id="settingsRepoList" class="space-y-2 mb-4 min-h-4"></div>

      <div class="border-t pt-4">
        <p class="text-xs text-gray-500 mb-2 font-medium">Add repository</p>
        <div class="flex gap-2 mb-2">
          <input id="settingsNewRepoName" type="text" placeholder="Name (e.g. Herman Miller)"
            class="border rounded px-2 py-1 text-sm flex-1">
        </div>
        <div class="flex gap-2">
          <input id="settingsNewRepoPath" type="text" placeholder="C:\\path\\to\\_repository"
            class="border rounded px-2 py-1 text-sm flex-1">
          <button id="settingsAddRepoBtn"
            class="px-3 py-1.5 rounded text-sm bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50"
            disabled>Add</button>
        </div>
      </div>
    </div>`;
  document.body.appendChild(modalWrapper);

  // ── Repo list renderer (stub — filled in Task 3) ───────────────────────────
  function _renderRepoList() {}

  // ── Open / close ───────────────────────────────────────────────────────────
  function openModal() {
    if (options.getCurrentPath) {
      const cur = options.getCurrentPath();
      if (cur) document.getElementById('settingsNewRepoPath').value = cur;
    }
    _renderRepoList();
    modalWrapper.classList.remove('hidden');
    modalWrapper.classList.add('flex');
  }
  function closeModal() {
    modalWrapper.classList.add('hidden');
    modalWrapper.classList.remove('flex');
    // reset add form
    document.getElementById('settingsNewRepoName').value = '';
    document.getElementById('settingsNewRepoPath').value = '';
    document.getElementById('settingsAddRepoBtn').disabled = true;
  }

  gearBtn.addEventListener('click', openModal);
  document.getElementById('settingsModalClose').addEventListener('click', closeModal);
  modalWrapper.addEventListener('click', (e) => { if (e.target === modalWrapper) closeModal(); });
}
```

- [ ] **Step 2: Add `id="settingsHeaderRow"` to the snapper page header div**

In `static/snapper/index.html`, the inner header div (line 12) is:
```html
    <div class="max-w-full px-6 py-3 flex flex-wrap items-end gap-4">
```

Replace it with:
```html
    <div id="settingsHeaderRow" class="max-w-full px-6 py-3 flex flex-wrap items-end gap-4">
```

- [ ] **Step 3: Load `settings.js` and add the init call to the snapper page**

In `static/snapper/index.html`, before the closing `</body>` tag (after the existing `<script src="/static/snapper/snapper.js"></script>`), add:
```html
<script src="/static/settings.js"></script>
<script>
  initSettingsGear(document.getElementById('settingsHeaderRow'));
</script>
```

- [ ] **Step 4: Verify gear icon renders and modal opens/closes**

Start the server (`python main.py`) and open `localhost:8080/snapper/`. Expected:
- Gear icon appears at the right of the header
- Clicking gear opens the modal with "Settings" title and "Saved Repositories" section
- Clicking × or clicking the backdrop closes the modal

- [ ] **Step 5: Commit**

```bash
git add static/settings.js static/snapper/index.html
git commit -m "feat: add settings gear icon and modal shell"
```

---

### Task 3: Modal interactions — add, rename, delete

**Files:**
- Modify: `static/settings.js`

Replace the `_renderRepoList` stub from Task 2 with the real implementation, and wire up the Add form. Both changes go inside `initSettingsGear`, after the `closeModal` function.

- [ ] **Step 1: Replace the `_renderRepoList` stub and wire the Add form**

In `static/settings.js`, inside `initSettingsGear`, replace:
```js
  // ── Repo list renderer (stub — filled in Task 3) ───────────────────────────
  function _renderRepoList() {}
```

With the full implementation plus Add-form wiring:

```js
  // ── Repo list renderer ─────────────────────────────────────────────────────
  function _renderRepoList() {
    const list = document.getElementById('settingsRepoList');
    const repos = Settings.getSavedRepos();
    if (!repos.length) {
      list.innerHTML = '<p class="text-sm text-gray-400">No saved repositories yet.</p>';
      return;
    }
    list.innerHTML = repos.map(r => `
      <div class="flex items-center gap-2 text-sm" data-id="${_esc(r.id)}">
        <span class="repo-name font-medium text-gray-700 w-36 truncate" title="${_esc(r.name)}">${_esc(r.name)}</span>
        <span class="text-gray-400 flex-1 truncate text-xs" title="${_esc(r.path)}">${_esc(r.path)}</span>
        <button class="rename-btn text-xs text-blue-500 hover:underline flex-shrink-0">Rename</button>
        <button class="delete-btn text-xs text-red-400 hover:underline flex-shrink-0">Delete</button>
      </div>`).join('');

    // wire rename buttons
    list.querySelectorAll('.rename-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const row = btn.closest('[data-id]');
        const id = row.dataset.id;
        const nameSpan = row.querySelector('.repo-name');
        const currentName = nameSpan.textContent;
        nameSpan.outerHTML = `
          <input class="rename-input border rounded px-1 py-0.5 text-sm w-36" value="${_esc(currentName)}">`;
        btn.textContent = 'Save';
        btn.classList.replace('text-blue-500', 'text-green-600');
        btn.onclick = () => {
          const input = row.querySelector('.rename-input');
          const newName = input.value.trim();
          if (!newName) return;
          Settings.renameRepo(id, newName);
          _emitChanged();
          _renderRepoList();
        };
        row.querySelector('.rename-input').addEventListener('keydown', (e) => {
          if (e.key === 'Escape') _renderRepoList();
        });
      });
    });

    // wire delete buttons
    list.querySelectorAll('.delete-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const id = btn.closest('[data-id]').dataset.id;
        Settings.deleteRepo(id);
        _emitChanged();
        _renderRepoList();
      });
    });
  }

  // ── Add form ───────────────────────────────────────────────────────────────
  const nameInput = document.getElementById('settingsNewRepoName');
  const pathInput = document.getElementById('settingsNewRepoPath');
  const addBtn    = document.getElementById('settingsAddRepoBtn');

  function _updateAddBtn() {
    addBtn.disabled = !nameInput.value.trim() || !pathInput.value.trim();
  }
  nameInput.addEventListener('input', _updateAddBtn);
  pathInput.addEventListener('input', _updateAddBtn);

  addBtn.addEventListener('click', () => {
    const name = nameInput.value.trim();
    const path = pathInput.value.trim();
    if (!name || !path) return;
    Settings.addRepo(name, path);
    _emitChanged();
    nameInput.value = '';
    pathInput.value = '';
    addBtn.disabled = true;
    _renderRepoList();
  });
```

- [ ] **Step 2: Verify add/rename/delete work**

Open `localhost:8080/snapper/`. Expected:
- Open settings modal → "No saved repositories yet."
- Fill in Name "Herman Miller" + a path → Add → row appears in list
- Add a second repo → two rows appear
- Click Rename on first row → name becomes an input, Save changes it
- Press Escape during rename → reverts without saving
- Click Delete → row disappears
- Refresh page → saved repos persist (localStorage)

- [ ] **Step 3: Commit**

```bash
git add static/settings.js
git commit -m "feat: add/rename/delete saved repos in settings modal"
```

---

## Chunk 2: Snapper page dropdown + home page gear

### Task 4: Repo dropdown on the Snapper page

**Files:**
- Modify: `static/snapper/index.html`
- Modify: `static/snapper/snapper.js`

The dropdown appears before the text input when saved repos exist. Selecting a saved repo fills the text input. Editing the text input directly switches the dropdown to "— Custom path —". When `settings:savedReposChanged` fires, the dropdown rebuilds.

- [ ] **Step 1: Add dropdown markup to `static/snapper/index.html`**

In the header, the repo section currently looks like:
```html
      <div>
        <label class="block text-xs text-gray-500 mb-1">Repository path</label>
        <input id="repoPath" type="text"
          class="border rounded px-2 py-1 text-sm w-96"
          placeholder="C:\path\to\_repository">
      </div>
```

Replace it with:
```html
      <div id="repoDropdownWrapper" class="hidden">
        <label class="block text-xs text-gray-500 mb-1">Saved repository</label>
        <select id="repoSelect" class="border rounded px-2 py-1 text-sm"></select>
      </div>
      <div>
        <label class="block text-xs text-gray-500 mb-1">Repository path</label>
        <input id="repoPath" type="text"
          class="border rounded px-2 py-1 text-sm w-96"
          placeholder="C:\path\to\_repository">
      </div>
```

- [ ] **Step 2: Update the `initSettingsGear` call in `static/snapper/index.html`**

The inline init script currently is:
```html
<script>
  initSettingsGear(document.getElementById('settingsHeaderRow'));
</script>
```

Update it to pass `getCurrentPath`:
```html
<script>
  initSettingsGear(
    document.getElementById('settingsHeaderRow'),
    { getCurrentPath: () => document.getElementById('repoPath').value.trim() }
  );
</script>
```

- [ ] **Step 3: Add repo dropdown logic to `static/snapper/snapper.js`**

In `snapper.js`, the existing repo persistence block (lines 90–95) is:
```js
repoPathInput.value = localStorage.getItem('repoPath') || '';
repoPathInput.addEventListener('input', () => {
  localStorage.setItem('repoPath', repoPathInput.value.trim());
  updateParseSeedBtn();
});
```

Replace that block with:

```js
// ── Repo path — init from localStorage (legacy key, still used for custom paths) ──
repoPathInput.value = localStorage.getItem('repoPath') || '';

// ── Repo dropdown ──────────────────────────────────────────────────────────
const repoDropdownWrapper = document.getElementById('repoDropdownWrapper');
const repoSelect          = document.getElementById('repoSelect');

function buildRepoDropdown() {
  const repos = Settings.getSavedRepos();
  if (!repos.length) {
    repoDropdownWrapper.classList.add('hidden');
    return;
  }
  repoDropdownWrapper.classList.remove('hidden');

  // Remember current selection or match against current path
  const currentPath = repoPathInput.value.trim();
  const matchedId = repos.find(r => r.path === currentPath)?.id || '__custom__';

  repoSelect.innerHTML =
    repos.map(r => `<option value="${r.id}">${r.name}</option>`).join('') +
    '<option value="__custom__">— Custom path —</option>';
  repoSelect.value = matchedId;
}

repoSelect.addEventListener('change', () => {
  const id = repoSelect.value;
  if (id === '__custom__') return;
  const repo = Settings.getSavedRepos().find(r => r.id === id);
  if (repo) {
    repoPathInput.value = repo.path;
    localStorage.setItem('repoPath', repo.path);
    updateParseSeedBtn();
  }
});

repoPathInput.addEventListener('input', () => {
  localStorage.setItem('repoPath', repoPathInput.value.trim());
  // snap dropdown to Custom if the typed path doesn't match any saved repo
  const repos = Settings.getSavedRepos();
  const match = repos.find(r => r.path === repoPathInput.value.trim());
  if (!match && repoSelect.value !== '__custom__') repoSelect.value = '__custom__';
  updateParseSeedBtn();
});

document.addEventListener('settings:savedReposChanged', buildRepoDropdown);

buildRepoDropdown();
```

- [ ] **Step 4: Verify dropdown behaviour**

Open `localhost:8080/snapper/`. Expected:
- With no saved repos: only the text input is visible (no dropdown)
- Open settings, add "Herman Miller" + a path → close modal → dropdown appears with "Herman Miller" selected, text input shows the path
- Add a second repo → dropdown gains the second option
- Select second repo in dropdown → text input updates to that path
- Edit the text input manually → dropdown switches to "— Custom path —"
- Delete all saved repos via settings → dropdown disappears
- Refresh page → saved repos and last-used path persist

- [ ] **Step 5: Commit**

```bash
git add static/snapper/index.html static/snapper/snapper.js
git commit -m "feat: add saved repo dropdown to snapper header"
```

---

### Task 5: Home page gear icon

**Files:**
- Modify: `static/index.html`

The home page header currently has no gear icon. Add `settings.js` and call `initSettingsGear` so users can manage saved repos from the home page too.

- [ ] **Step 1: Add `id` to the home page header div and load `settings.js`**

In `static/index.html`, the header inner div (line 12) is:
```html
    <div class="max-w-7xl mx-auto px-6 py-4">
      <h1 class="text-2xl font-bold text-gray-800">OFML Testsuite</h1>
      <p class="text-sm text-gray-500">MillerKnoll QA Tools</p>
    </div>
```

Replace it with (wrap the text in its own div so `flex` doesn't collapse the stacked title/subtitle):
```html
    <div id="homeHeaderRow" class="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-gray-800">OFML Testsuite</h1>
        <p class="text-sm text-gray-500">MillerKnoll QA Tools</p>
      </div>
    </div>
```

Before the closing `</body>`, add:
```html
  <script src="/static/settings.js"></script>
  <script>
    initSettingsGear(document.getElementById('homeHeaderRow'));
  </script>
```

- [ ] **Step 2: Verify gear on home page**

Open `localhost:8080`. Expected:
- Gear icon appears at the right of the home page header
- Modal opens, shows same saved repos as the snapper page
- Adding/renaming/deleting works identically

- [ ] **Step 3: Commit**

```bash
git add static/index.html
git commit -m "feat: add settings gear to home page"
```

---

## Done

All tasks complete. The feature is live at both `localhost:8080` and `localhost:8080/snapper/`.

**Smoke test checklist:**
- [ ] Home page: gear opens modal, repos can be added/renamed/deleted
- [ ] Snapper page: dropdown hidden with no saved repos, appears when repos are added via settings
- [ ] Selecting a saved repo fills the repo path text input
- [ ] Editing the path text input manually switches dropdown to "— Custom path —"
- [ ] Settings changes on one page are reflected immediately (no reload needed)
- [ ] Queue and parse-seed flow unaffected — existing behaviour unchanged

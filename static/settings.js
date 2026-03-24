// ── Settings storage key ────────────────────────────────────────────────────
const SETTINGS_KEY = 'ofml_settings';

// ── Settings data layer ─────────────────────────────────────────────────────
const Settings = {
  _load() {
    try {
      const parsed = JSON.parse(localStorage.getItem(SETTINGS_KEY));
      return (parsed && Array.isArray(parsed.savedRepos)) ? parsed : { savedRepos: [] };
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

  // ── Repo list renderer ─────────────────────────────────────────────────────
  function _renderRepoList() {
    const list = modalWrapper.querySelector('#settingsRepoList');
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
  const nameInput = modalWrapper.querySelector('#settingsNewRepoName');
  const pathInput = modalWrapper.querySelector('#settingsNewRepoPath');
  const addBtn    = modalWrapper.querySelector('#settingsAddRepoBtn');

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

  // ── Open / close ───────────────────────────────────────────────────────────
  function openModal() {
    if (options.getCurrentPath) {
      const cur = options.getCurrentPath();
      if (cur) modalWrapper.querySelector('#settingsNewRepoPath').value = cur;
    }
    _renderRepoList();
    modalWrapper.classList.remove('hidden');
    modalWrapper.classList.add('flex');
  }
  function closeModal() {
    modalWrapper.classList.add('hidden');
    modalWrapper.classList.remove('flex');
    // reset add form
    modalWrapper.querySelector('#settingsNewRepoName').value = '';
    modalWrapper.querySelector('#settingsNewRepoPath').value = '';
    modalWrapper.querySelector('#settingsAddRepoBtn').disabled = true;
  }

  gearBtn.addEventListener('click', openModal);
  modalWrapper.querySelector('#settingsModalClose').addEventListener('click', closeModal);
  modalWrapper.addEventListener('click', (e) => { if (e.target === modalWrapper) closeModal(); });
}

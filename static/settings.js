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

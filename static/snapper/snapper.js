// ── Constants ──────────────────────────────────────────────────────────────────
const WARN_LIMIT = 1500;
const ERROR_LIMIT = 5000;
const QUEUE_STORAGE_KEY = 'snapper_queue';

// ── HTML safety ────────────────────────────────────────────────────────────────
function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

// ── Filename assembly ──────────────────────────────────────────────────────────
function sanitizeLabel(raw) {
  return raw.trim().replace(/\s+/g, '_').replace(/[^\w]/g, '');
}

function assembleFilename(series, article, label, stage) {
  const parts = [series.toLowerCase(), article];
  const clean = sanitizeLabel(label);
  if (clean) parts.push(clean);
  parts.push(stage);
  return parts.join('_') + '.obx';
}

function assembleZipFilename(series, article) {
  return `${series.toLowerCase()}_${article}_Raw.zip`;
}

// ── State ──────────────────────────────────────────────────────────────────────
let currentSeed = null;       // full parse-seed response: { manufacturer, series, groups, ... }
let currentGroupIndex = 0;    // index of the active tab
let groupStates = [];         // per-group UI state: [{ articleSelections, dimSelections }]
let currentPermCount = 0;
let queue = [];

// ── Queue persistence ──────────────────────────────────────────────────────────
function saveQueue() {
  localStorage.setItem(QUEUE_STORAGE_KEY, JSON.stringify(queue));
}

function loadQueue() {
  try {
    const saved = localStorage.getItem(QUEUE_STORAGE_KEY);
    if (saved) {
      const raw = JSON.parse(saved);
      // Migrate old-format items (pre-multi-article) if needed
      queue = raw.map(item => {
        if (!item.articles && item.article) {
          return {
            ...item,
            articles: [{
              code: item.article,
              label: null,
              property_to_class: item.propertyToClass || {},
              prop_val_to_class: item.propValToClass || {},
              seed_token: item.seedToken || null,
            }],
            selectedArticleCodes: [item.article],
            selectedProperties: item.selectedProperties || {},
            childResolutions: item.childResolutions || {},
          };
        }
        return item;
      });
    }
  } catch { queue = []; }
}

// ── DOM refs ───────────────────────────────────────────────────────────────────
const repoPathInput    = document.getElementById('repoPath');
const seedDropZone     = document.getElementById('seedDropZone');
const seedFileInput    = document.getElementById('seedFile');
const seedDropLabel    = document.getElementById('seedDropLabel');
const parseSeedBtn     = document.getElementById('parseSeedBtn');
const seedStatus       = document.getElementById('seedStatus');
const tabStrip         = document.getElementById('tabStrip');
const dimensionArea    = document.getElementById('dimensionArea');
const dimensionColumns = document.getElementById('dimensionColumns');
const actionRow        = document.getElementById('actionRow');
const permCount        = document.getElementById('permCount');
const articleLabel     = document.getElementById('articleLabel');
const filenamePreview  = document.getElementById('filenamePreview');
const addToQueueBtn    = document.getElementById('addToQueueBtn');
const queueStrip       = document.getElementById('queueStrip');
const emptyQueueMsg    = document.getElementById('emptyQueueMsg');
const generateAllBtn   = document.getElementById('generateAllBtn');
const generateStatus   = document.getElementById('generateStatus');

// ── Repo path — init from localStorage ────────────────────────────────────
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

  // Match current path to a saved repo, or fall back to custom
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
  // Snap dropdown to Custom if the typed path doesn't match any saved repo
  const repos = Settings.getSavedRepos();
  const match = repos.find(r => r.path === repoPathInput.value.trim());
  if (!match && repoSelect.value !== '__custom__') repoSelect.value = '__custom__';
  updateParseSeedBtn();
});

document.addEventListener('settings:savedReposChanged', buildRepoDropdown);

buildRepoDropdown();

// ── Seed drag-and-drop ─────────────────────────────────────────────────────────
seedDropZone.addEventListener('click', () => seedFileInput.click());

seedDropZone.addEventListener('dragover', (e) => {
  e.preventDefault();
  seedDropZone.classList.add('border-blue-500', 'bg-blue-50');
});
seedDropZone.addEventListener('dragleave', () => {
  seedDropZone.classList.remove('border-blue-500', 'bg-blue-50');
});
seedDropZone.addEventListener('drop', (e) => {
  e.preventDefault();
  seedDropZone.classList.remove('border-blue-500', 'bg-blue-50');
  const file = e.dataTransfer.files[0];
  if (file) {
    const dt = new DataTransfer();
    dt.items.add(file);
    seedFileInput.files = dt.files;
    onSeedFileSelected(file.name);
  }
});
seedFileInput.addEventListener('change', () => {
  if (seedFileInput.files[0]) onSeedFileSelected(seedFileInput.files[0].name);
});

function onSeedFileSelected(filename) {
  seedDropLabel.innerHTML =
    `<span class="font-medium text-gray-700">${escapeHtml(filename)}</span>`
    + ` — <span class="text-blue-600 underline">change file</span>`;
  updateParseSeedBtn();
}

function updateParseSeedBtn() {
  parseSeedBtn.disabled = !seedFileInput.files.length || !repoPathInput.value.trim();
}

// ── Parse Seed ─────────────────────────────────────────────────────────────────
parseSeedBtn.addEventListener('click', async () => {
  const file = seedFileInput.files[0];
  if (!file) return;
  const repo = repoPathInput.value.trim();
  if (!repo) { alert('Please enter the repository path first.'); return; }

  parseSeedBtn.disabled = true;
  seedStatus.className = 'text-sm text-gray-500';
  seedStatus.textContent = 'Parsing…';

  const formData = new FormData();
  formData.append('file', file);
  formData.append('repo', repo);

  let response;
  try {
    response = await fetch('/api/snapper/parse-seed', { method: 'POST', body: formData });
  } catch (err) {
    seedStatus.textContent = `Network error: ${err.message}`;
    parseSeedBtn.disabled = false;
    return;
  }

  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: 'Unknown error' }));
    seedStatus.textContent = `Error: ${err.detail}`;
    parseSeedBtn.disabled = false;
    return;
  }

  currentSeed = await response.json();

  if (currentSeed.info_messages && currentSeed.info_messages.length) {
    seedStatus.textContent = currentSeed.info_messages.join(' | ');
    seedStatus.className = 'text-sm text-amber-600';
  } else {
    seedStatus.textContent = '';
  }
  parseSeedBtn.disabled = false;

  // Initialise per-group state
  groupStates = currentSeed.groups.map(() => ({
    articleSelections: null,   // null = all checked (default); set on first change
    dimSelections: {},         // { propName: [checkedValues] }
  }));
  currentGroupIndex = 0;

  tabStrip.classList.remove('hidden');
  dimensionArea.classList.remove('hidden');
  actionRow.classList.remove('hidden');

  renderTabStrip();
  renderDimensions();
  addToQueueBtn.disabled = false;
  updateFilenamePreview();
});

// ── Tab strip ─────────────────────────────────────────────────────────────────
function renderTabStrip() {
  tabStrip.innerHTML = '';
  if (!currentSeed) return;

  const nav = document.createElement('div');
  nav.className = 'flex gap-1 flex-wrap';

  currentSeed.groups.forEach((group, idx) => {
    const codes = group.articles.map(a => a.code);
    const label = codes.length === 1 ? codes[0] : codes.join(', ');

    const btn = document.createElement('button');
    btn.className = [
      'px-3 py-1.5 rounded text-sm font-medium border transition-colors',
      idx === currentGroupIndex
        ? 'bg-blue-600 text-white border-blue-600'
        : 'bg-white text-gray-600 border-gray-300 hover:border-blue-400 hover:text-blue-600',
    ].join(' ');
    btn.textContent = `${label} · ${group.property_columns.length} properties`;
    btn.addEventListener('click', () => switchTab(idx));
    nav.appendChild(btn);
  });

  tabStrip.appendChild(nav);
}

function switchTab(idx) {
  if (!currentSeed || idx === currentGroupIndex) return;
  _saveGroupState();
  currentGroupIndex = idx;
  renderTabStrip();
  renderDimensions();
  updateFilenamePreview();
}

function _saveGroupState() {
  if (!currentSeed || !groupStates[currentGroupIndex]) return;
  const state = groupStates[currentGroupIndex];

  // Save article selections
  state.articleSelections = _getArticleSelections();

  // Save dimension selections
  const dims = {};
  document.querySelectorAll('.dim-check:checked').forEach(cb => {
    if (!dims[cb.dataset.prop]) dims[cb.dataset.prop] = [];
    dims[cb.dataset.prop].push(cb.dataset.value);
  });
  state.dimSelections = dims;
}

// ── Dimension columns ──────────────────────────────────────────────────────────
function renderDimensions() {
  dimensionColumns.innerHTML = '';
  if (!currentSeed) return;

  const group = currentSeed.groups[currentGroupIndex];
  if (!group) return;

  const state = groupStates[currentGroupIndex] || {};

  // Article column — only shown for groups with 2+ articles
  if (group.articles.length > 1) {
    dimensionColumns.appendChild(_buildArticleColumn(group.articles, state.articleSelections));
  }

  const parentHasChild = new Map();
  for (const col of group.property_columns) {
    if (col.is_child) parentHasChild.set(col.parent, col.name);
  }

  for (const col of group.property_columns) {
    if (col.is_child) continue;
    const wrapper = document.createElement('div');
    wrapper.className = 'flex flex-col gap-1';
    wrapper.appendChild(
      _buildCheckboxColumn(col.name, col.values, col.seed_value, state.dimSelections)
    );
    const childName = parentHasChild.get(col.name);
    if (childName) {
      const childCol = group.property_columns.find(c => c.name === childName);
      if (childCol) wrapper.appendChild(_buildChildColumn(childCol));
    }
    dimensionColumns.appendChild(wrapper);
  }
  updatePermCount();
}

function _buildCheckboxColumn(propName, values, seedValue, savedDimSelections) {
  const col = document.createElement('div');
  col.className = 'bg-white rounded-lg shadow p-3 min-w-44 max-w-56 flex flex-col';
  col.dataset.propName = propName;

  // Use saved selections if present; otherwise pre-check seed value
  const savedVals = savedDimSelections && savedDimSelections[propName];

  col.innerHTML = `
    <div class="font-semibold text-sm text-gray-700 mb-2 border-b pb-1" title="${escapeHtml(propName)}">${escapeHtml(propName)}</div>
    <div class="flex gap-1 mb-2">
      <button class="text-xs text-blue-600 hover:underline select-all-btn">All</button>
      <span class="text-gray-300">|</span>
      <button class="text-xs text-blue-600 hover:underline select-none-btn">None</button>
    </div>
    <div class="overflow-y-auto max-h-64 space-y-1">
      ${values.map(v => {
        const isChecked = savedVals
          ? savedVals.includes(v.code)
          : v.code === seedValue;
        return `
          <label class="flex items-center gap-1 text-xs text-gray-700 cursor-pointer">
            <input type="checkbox" class="dim-check" data-prop="${escapeHtml(propName)}" data-value="${escapeHtml(v.code)}"
              ${isChecked ? 'checked' : ''}>
            <span class="font-mono text-gray-500">${escapeHtml(v.code)}</span>
            ${v.label && v.label !== v.code ? `<span class="text-gray-300">·</span><span class="truncate">${escapeHtml(v.label)}</span>` : ''}
          </label>`;
      }).join('')}
    </div>`;
  col.querySelector('.select-all-btn').addEventListener('click', () => {
    col.querySelectorAll('.dim-check').forEach(cb => { cb.checked = true; });
    onDimensionChange();
  });
  col.querySelector('.select-none-btn').addEventListener('click', () => {
    col.querySelectorAll('.dim-check').forEach(cb => { cb.checked = false; });
    onDimensionChange();
  });
  col.querySelectorAll('.dim-check').forEach(cb => cb.addEventListener('change', onDimensionChange));
  return col;
}

function onDimensionChange() {
  _updateChildSections();
  updatePermCount();
}

function _updateChildSections() {
  if (!currentSeed) return;
  const group = currentSeed.groups[currentGroupIndex];
  if (!group) return;
  const sel = getParentSelections();

  for (const childCol of group.property_columns.filter(c => c.is_child)) {
    const checkedParentVals = new Set(sel[childCol.parent] || []);
    const colEl = dimensionColumns.querySelector(`[data-prop-name="${CSS.escape(childCol.name)}"]`);
    if (!colEl) continue;

    colEl.querySelectorAll('.child-section').forEach(section => {
      const pv = section.dataset.parentVal;
      const active = checkedParentVals.has(pv);
      section.querySelectorAll('.child-check').forEach(cb => {
        cb.disabled = !active;
        if (!active) cb.checked = false;
      });
      section.querySelectorAll('.child-label').forEach(lbl => {
        lbl.classList.toggle('text-gray-400', !active);
        lbl.classList.toggle('cursor-not-allowed', !active);
        lbl.classList.toggle('text-gray-700', active);
        lbl.classList.toggle('cursor-pointer', active);
      });
      const header = section.querySelector('.section-header');
      if (header) {
        header.classList.toggle('text-gray-300', !active);
        header.classList.toggle('text-gray-500', active);
      }
    });
  }
}

function _buildChildColumn(col) {
  // col = { name, values, is_child, parent, mapping }
  // Build a code→label lookup from the flat values list
  const labelOf = {};
  for (const v of col.values) labelOf[v.code] = v.label;

  const el = document.createElement('div');
  el.className = 'bg-white rounded-lg shadow p-3 min-w-44 max-w-56 flex flex-col';
  el.dataset.propName = col.name;

  // Build grouped sections HTML
  const sectionsHtml = Object.entries(col.mapping || {}).map(([parentVal, childCodes]) => {
    const childRows = childCodes.map(code => {
      const label = labelOf[code] || code;
      const hasLabel = label && label !== code;
      return `
        <label class="child-label flex items-center gap-1 text-xs text-gray-400 cursor-not-allowed">
          <input type="checkbox" class="child-check" data-prop="${escapeHtml(col.name)}"
            data-value="${escapeHtml(code)}" data-parent-val="${escapeHtml(parentVal)}" disabled>
          <span class="font-mono">${escapeHtml(code)}</span>
          ${hasLabel ? `<span class="text-gray-300">·</span><span class="truncate">${escapeHtml(label)}</span>` : ''}
        </label>`;
    }).join('');
    return `
      <div class="child-section mb-1" data-parent-val="${escapeHtml(parentVal)}">
        <div class="section-header text-xs font-mono text-gray-300 px-1 pb-0.5 border-b border-gray-100 mb-0.5">${escapeHtml(parentVal)}</div>
        <div class="pl-1 space-y-0.5">${childRows}</div>
      </div>`;
  }).join('');

  el.innerHTML = `
    <div class="font-semibold text-sm text-gray-700 mb-0.5 border-b pb-1" title="${escapeHtml(col.name)}">${escapeHtml(col.name)}</div>
    <div class="text-xs text-gray-400 mb-2">↳ ${escapeHtml(col.parent)}</div>
    <div class="flex gap-1 mb-2">
      <button class="text-xs text-blue-600 hover:underline select-all-btn">All</button>
      <span class="text-gray-300">|</span>
      <button class="text-xs text-blue-600 hover:underline select-none-btn">None</button>
    </div>
    <div class="overflow-y-auto max-h-64">${sectionsHtml}</div>`;

  el.querySelector('.select-all-btn').addEventListener('click', () => {
    el.querySelectorAll('.child-check:not(:disabled)').forEach(cb => { cb.checked = true; });
    onDimensionChange();
  });
  el.querySelector('.select-none-btn').addEventListener('click', () => {
    el.querySelectorAll('.child-check:not(:disabled)').forEach(cb => { cb.checked = false; });
    onDimensionChange();
  });
  el.querySelectorAll('.child-check').forEach(cb => cb.addEventListener('change', onDimensionChange));

  return el;
}

function _buildArticleColumn(articles, savedSelections) {
  const col = document.createElement('div');
  col.className = 'bg-white rounded-lg shadow p-3 min-w-44 max-w-56 flex flex-col';
  col.dataset.propName = '__article__';

  // All checked by default; restore saved state if present
  const checkedSet = savedSelections
    ? new Set(savedSelections)
    : new Set(articles.map(a => a.code));

  col.innerHTML = `
    <div class="font-semibold text-sm text-gray-700 mb-2 border-b pb-1">Article</div>
    <div class="flex gap-1 mb-2">
      <button class="text-xs text-blue-600 hover:underline select-all-btn">All</button>
      <span class="text-gray-300">|</span>
      <button class="text-xs text-blue-600 hover:underline select-none-btn">None</button>
    </div>
    <div class="overflow-y-auto max-h-64 space-y-1">
      ${articles.map(a => `
        <label class="flex items-center gap-1 text-xs text-gray-700 cursor-pointer">
          <input type="checkbox" class="article-check" data-code="${escapeHtml(a.code)}"
            ${checkedSet.has(a.code) ? 'checked' : ''}>
          <span class="font-mono text-gray-500">${escapeHtml(a.code)}</span>
          ${a.label ? `<span class="text-gray-300">·</span><span class="truncate">${escapeHtml(a.label)}</span>` : ''}
        </label>`).join('')}
    </div>`;

  col.querySelector('.select-all-btn').addEventListener('click', () => {
    col.querySelectorAll('.article-check').forEach(cb => { cb.checked = true; });
    onDimensionChange();
  });
  col.querySelector('.select-none-btn').addEventListener('click', () => {
    col.querySelectorAll('.article-check').forEach(cb => { cb.checked = false; });
    onDimensionChange();
  });
  col.querySelectorAll('.article-check').forEach(cb => cb.addEventListener('change', onDimensionChange));
  return col;
}

function _getArticleSelections() {
  const checked = [];
  document.querySelectorAll('.article-check:checked').forEach(cb => checked.push(cb.dataset.code));
  return checked.length > 0 ? checked : null;
}

// ── Permutation counter ────────────────────────────────────────────────────────
function getParentSelections() {
  const sel = {};
  document.querySelectorAll('.dim-check:checked').forEach(cb => {
    if (!sel[cb.dataset.prop]) sel[cb.dataset.prop] = [];
    sel[cb.dataset.prop].push(cb.dataset.value);
  });
  return sel;
}

function getChildSelections() {
  if (!currentSeed) return {};
  const group = currentSeed.groups[currentGroupIndex];
  if (!group) return {};
  const result = {};
  for (const col of group.property_columns) {
    if (!col.is_child) continue;
    const resolution = {};
    for (const parentVal of Object.keys(col.mapping || {})) {
      const selected = [];
      dimensionColumns.querySelectorAll(
        `.child-check[data-prop="${CSS.escape(col.name)}"][data-parent-val="${CSS.escape(parentVal)}"]:checked`
      ).forEach(cb => selected.push(cb.dataset.value));
      resolution[parentVal] = selected;
    }
    result[col.name] = { parent: col.parent, resolution };
  }
  return result;
}

function updatePermCount() {
  if (!currentSeed) { permCount.textContent = ''; return; }

  const group = currentSeed.groups[currentGroupIndex];
  if (!group) return;

  const factors = [];

  // Article dimension (only relevant for multi-article groups)
  if (group.articles.length > 1) {
    const articleCount = document.querySelectorAll('.article-check:checked').length;
    if (articleCount > 0) factors.push(articleCount);
  }

  // Each property column contributes the count of its ticked checkboxes.
  // Child columns: count ticked child-check boxes (0 = no explicit selection → treated as ×1, i.e. default applies).
  // Parent columns: count ticked dim-check boxes.
  for (const col of group.property_columns) {
    let n;
    if (col.is_child) {
      n = dimensionColumns.querySelectorAll(
        `.child-check[data-prop="${CSS.escape(col.name)}"]:checked`
      ).length;
    } else {
      n = dimensionColumns.querySelectorAll(
        `.dim-check[data-prop="${CSS.escape(col.name)}"]:checked`
      ).length;
    }
    if (n > 0) factors.push(n);
  }

  const count = factors.length ? factors.reduce((a, b) => a * b, 1) : 0;
  currentPermCount = count;
  permCount.textContent = `${count.toLocaleString()} permutations`;
  permCount.className = 'text-sm font-medium ' + (
    count > ERROR_LIMIT ? 'text-red-600' :
    count > WARN_LIMIT  ? 'text-amber-600' : 'text-gray-700'
  );
  if (count > ERROR_LIMIT) permCount.textContent += ` ⚠ Consider splitting (max: ${ERROR_LIMIT.toLocaleString()})`;

  // Disable Add to Queue if no articles selected in multi-article groups
  if (group.articles.length > 1) {
    const articleCount = document.querySelectorAll('.article-check:checked').length;
    addToQueueBtn.disabled = articleCount === 0 || count === 0;
  } else {
    addToQueueBtn.disabled = count === 0;
  }

  updateFilenamePreview();
}

function updateFilenamePreview() {
  if (!currentSeed) { filenamePreview.textContent = ''; return; }
  const group = currentSeed.groups[currentGroupIndex];
  if (!group) return;
  filenamePreview.textContent = assembleFilename(
    currentSeed.series, _resolveArticleToken(group), articleLabel.value, 'Raw'
  );
}

function _resolveArticleToken(group) {
  if (group.articles.length === 1) return group.articles[0].code;
  const checked = document.querySelectorAll('.article-check:checked');
  if (checked.length === 1) return checked[0].dataset.code;
  return 'multiple_articles';
}

articleLabel.addEventListener('input', updateFilenamePreview);

// ── Class maps ─────────────────────────────────────────────────────────────────
function buildClassMaps() {
  if (!currentSeed) return { propertyToClass: {}, propValToClass: {} };
  const group = currentSeed.groups[currentGroupIndex];
  if (!group) return { propertyToClass: {}, propValToClass: {} };
  // Use the first article's class maps for display purposes; per-article maps are
  // sent to the server via the articles array.
  const first = group.articles[0];
  return {
    propertyToClass: { ...first.property_to_class },
    propValToClass: { ...first.prop_val_to_class },
  };
}

// ── Add to queue ───────────────────────────────────────────────────────────────
addToQueueBtn.addEventListener('click', () => {
  if (!currentSeed) return;
  const group = currentSeed.groups[currentGroupIndex];
  if (!group) return;

  const parentSelections = getParentSelections();
  const label = articleLabel.value.trim();

  // Determine selected articles
  let selectedArticles;
  if (group.articles.length === 1) {
    selectedArticles = group.articles;
  } else {
    const checkedCodes = new Set(
      [...document.querySelectorAll('.article-check:checked')].map(cb => cb.dataset.code)
    );
    selectedArticles = group.articles.filter(a => checkedCodes.has(a.code));
  }
  if (selectedArticles.length === 0) return;

  const articleToken = selectedArticles.length === 1
    ? selectedArticles[0].code
    : 'multiple_articles';

  const filename = assembleFilename(currentSeed.series, articleToken, label, 'Raw');

  queue.push({
    id: crypto.randomUUID(),
    state: 'red',
    label,
    filename,
    series: currentSeed.series,
    manufacturer: currentSeed.manufacturer,
    // Multi-article fields
    articles: selectedArticles.map(a => ({
      code: a.code,
      label: a.label,
      property_to_class: a.property_to_class,
      prop_val_to_class: a.prop_val_to_class,
      seed_token: a.seed_token,
    })),
    selectedArticleCodes: selectedArticles.map(a => a.code),
    selectedProperties: parentSelections,
    childResolutions: getChildSelections(),
    count: currentPermCount,
    keptCount: null,
    removedCount: null,
  });

  articleLabel.value = '';
  updateFilenamePreview();
  saveQueue();
  renderQueue();
});

// ── Queue rendering ────────────────────────────────────────────────────────────
function renderQueue() {
  queueStrip.querySelectorAll('.queue-card').forEach(el => el.remove());
  if (queue.length === 0) {
    emptyQueueMsg.classList.remove('hidden');
    generateAllBtn.disabled = true;
    return;
  }
  emptyQueueMsg.classList.add('hidden');
  for (const item of queue) queueStrip.appendChild(buildCard(item));
  generateAllBtn.disabled = !queue.some(i => i.state === 'red');
}

function buildCard(item) {
  const card = document.createElement('div');
  card.className = 'queue-card rounded-lg p-3 w-56 flex-shrink-0 flex flex-col gap-2 border-2 relative';
  card.dataset.id = item.id;

  // Always-present delete button in top-right corner
  const deleteBtn = document.createElement('button');
  deleteBtn.className = 'absolute top-1.5 right-1.5 text-gray-400 hover:text-red-500 text-xs w-5 h-5 flex items-center justify-center rounded hover:bg-red-50';
  deleteBtn.textContent = '✕';
  deleteBtn.title = 'Remove from queue';
  deleteBtn.addEventListener('click', () => removeItem(item.id));
  card.appendChild(deleteBtn);

  if (item.state === 'red') {
    card.classList.add('border-red-400', 'bg-red-50');
    const inner = document.createElement('div');
    inner.className = 'flex flex-col gap-2 pr-5';
    inner.innerHTML = `
      <div class="text-xs font-mono text-gray-700 truncate" title="${escapeHtml(item.filename)}">${escapeHtml(item.filename)}</div>
      <div class="text-xs text-gray-500">${item.count.toLocaleString()} permutations</div>
      <button class="generate-one-btn w-full bg-red-600 text-white px-2 py-1 rounded text-xs hover:bg-red-700">Generate</button>`;
    card.appendChild(inner);
    inner.querySelector('.generate-one-btn').addEventListener('click', () => generateOne(item.id));

  } else if (item.state === 'orange') {
    card.classList.add('border-amber-400', 'bg-amber-50');
    const inner = document.createElement('div');
    inner.className = 'flex flex-col gap-2 pr-5';
    inner.innerHTML = `
      <div class="text-xs font-mono text-gray-600 truncate" title="${escapeHtml(item.filename)}">${escapeHtml(item.filename)}</div>
      <div class="text-xs text-amber-700 font-medium">Waiting for pCon export</div>
      <div class="clean-drop-zone border-2 border-dashed border-amber-300 rounded p-3 text-center text-xs text-amber-600 cursor-pointer hover:bg-amber-100 transition-colors">
        Drop pCon export here<br>or click to browse
        <input type="file" accept=".obx,.xml" class="hidden clean-file-input">
      </div>
      <button class="regenerate-btn w-full text-xs text-gray-500 hover:text-gray-700 border rounded px-2 py-1">Re-generate</button>`;
    card.appendChild(inner);

    const dropZone = inner.querySelector('.clean-drop-zone');
    const fileInput = inner.querySelector('.clean-file-input');
    dropZone.addEventListener('click', () => fileInput.click());
    dropZone.addEventListener('dragover', (e) => { e.preventDefault(); dropZone.classList.add('bg-amber-200'); });
    dropZone.addEventListener('dragleave', () => dropZone.classList.remove('bg-amber-200'));
    dropZone.addEventListener('drop', (e) => {
      e.preventDefault();
      dropZone.classList.remove('bg-amber-200');
      if (e.dataTransfer.files[0]) cleanItem(item.id, e.dataTransfer.files[0]);
    });
    fileInput.addEventListener('change', () => {
      if (fileInput.files[0]) cleanItem(item.id, fileInput.files[0]);
    });
    inner.querySelector('.regenerate-btn').addEventListener('click', () => revertToRed(item.id));

  } else if (item.state === 'green') {
    card.classList.add('border-green-400', 'bg-green-50');
    const articleToken = item.selectedArticleCodes?.length === 1
      ? item.selectedArticleCodes[0]
      : 'multiple_articles';
    const cleanName = assembleFilename(item.series, articleToken, item.label, 'Clean');
    const inner = document.createElement('div');
    inner.className = 'flex flex-col gap-2 pr-5';
    inner.innerHTML = `
      <div class="text-xs font-mono text-gray-700 truncate" title="${escapeHtml(cleanName)}">${escapeHtml(cleanName)}</div>
      <div class="text-xs text-green-700 font-medium">✓ ${item.keptCount} kept · ${item.removedCount} removed</div>
      <button class="done-btn w-full bg-green-600 text-white px-2 py-1 rounded text-xs hover:bg-green-700">Done</button>`;
    card.appendChild(inner);
    inner.querySelector('.done-btn').addEventListener('click', () => removeItem(item.id));
  }

  return card;
}

function removeItem(id) {
  queue = queue.filter(i => i.id !== id);
  saveQueue();
  renderQueue();
}

function revertToRed(id) {
  const item = queue.find(i => i.id === id);
  if (!item) return;
  item.state = 'red';
  saveQueue();
  renderQueue();
}

// ── Generate (single) ──────────────────────────────────────────────────────────
async function generateOne(id) {
  const item = queue.find(i => i.id === id);
  if (!item || item.state !== 'red') return;
  const card = queueStrip.querySelector(`[data-id="${id}"]`);
  if (card) card.querySelector('.generate-one-btn').disabled = true;

  const ok = await _doGenerate([item], item.filename);
  if (ok) {
    item.state = 'orange';
    saveQueue();
  }
  renderQueue(); // Always re-render: restores button on failure, advances card on success
}

// ── Generate All ───────────────────────────────────────────────────────────────
generateAllBtn.addEventListener('click', async () => {
  const redItems = queue.filter(i => i.state === 'red');
  if (!redItems.length) return;

  generateAllBtn.disabled = true;
  generateStatus.classList.remove('hidden');
  generateStatus.textContent = 'Building…';

  const articleToken = redItems.length === 1 && redItems[0].selectedArticleCodes?.length === 1
    ? redItems[0].selectedArticleCodes[0]
    : 'multiple_articles';
  const filename = redItems.length === 1
    ? redItems[0].filename
    : assembleZipFilename(redItems[0].series, articleToken).replace('.zip', '.obx');

  const ok = await _doGenerate(redItems, filename);
  if (ok) {
    for (const item of redItems) item.state = 'orange';
    saveQueue();
    generateStatus.textContent = 'Downloaded.';
    setTimeout(() => generateStatus.classList.add('hidden'), 3000);
  }
  renderQueue();
});

// ── Shared generate logic ──────────────────────────────────────────────────────
async function _doGenerate(items, filename) {
  const payload = {
    manufacturer: items[0].manufacturer,
    series: items[0].series,
    filename,
    queue: items.map(e => ({
      articles: e.articles,
      selected_article_codes: e.selectedArticleCodes,
      selected_properties: e.selectedProperties,
      child_resolutions: e.childResolutions || {},
      filename: e.filename,
    })),
  };

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 120000);
  let response;
  try {
    response = await fetch('/api/snapper/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
  } catch (err) {
    clearTimeout(timeoutId);
    _showGenerateStatus(err.name === 'AbortError' ? 'Timed out — try fewer permutations.' : `Network error: ${err.message}`);
    return false;
  }
  clearTimeout(timeoutId);

  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: 'Unknown error' }));
    _showGenerateStatus(`Error: ${err.detail}`);
    return false;
  }

  const contentType = response.headers.get('content-type') || '';
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = contentType.includes('zip')
    ? assembleZipFilename(
        items[0].series,
        items[0].selectedArticleCodes?.length === 1 ? items[0].selectedArticleCodes[0] : 'multiple_articles'
      )
    : filename;
  a.click();
  URL.revokeObjectURL(url);
  return true;
}

function _showGenerateStatus(msg) {
  generateStatus.textContent = msg;
  generateStatus.classList.remove('hidden');
}

// ── Clean item ─────────────────────────────────────────────────────────────────
async function cleanItem(id, file) {
  const item = queue.find(i => i.id === id);
  if (!item) return;

  const card = queueStrip.querySelector(`[data-id="${id}"]`);
  const dropZone = card?.querySelector('.clean-drop-zone');
  if (dropZone) dropZone.textContent = 'Processing…';

  const formData = new FormData();
  formData.append('file', file);
  formData.append('label', item.label);

  let response;
  try {
    response = await fetch('/api/snapper/clean-obx', { method: 'POST', body: formData });
  } catch (err) {
    if (dropZone) dropZone.textContent = `Network error: ${err.message}`;
    return;
  }

  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: 'Unknown error' }));
    if (dropZone) dropZone.textContent = `Error: ${err.detail}`;
    return;
  }

  const kept = parseInt(response.headers.get('X-Kept-Count') || '0', 10);
  const removed = parseInt(response.headers.get('X-Removed-Count') || '0', 10);

  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = assembleFilename(
    item.series,
    item.selectedArticleCodes?.length === 1 ? item.selectedArticleCodes[0] : 'multiple_articles',
    item.label,
    'Clean'
  );
  a.click();
  URL.revokeObjectURL(url);

  item.state = 'green';
  item.keptCount = kept;
  item.removedCount = removed;
  saveQueue();
  renderQueue();
}

// ── Init ───────────────────────────────────────────────────────────────────────
loadQueue();
renderQueue();

// ── Raw Seed Generator ─────────────────────────────────────────────────────────
const rawSeedModal  = document.getElementById('rawSeedModal');
const rawSeedSelect = document.getElementById('rawSeedRangeSelect');
const rawSeedError  = document.getElementById('rawSeedError');
const rawSeedGenBtn = document.getElementById('rawSeedGenerateBtn');

document.getElementById('generateSeedBtn').addEventListener('click', openRawSeedModal);
document.getElementById('rawSeedCancelBtn').addEventListener('click', closeRawSeedModal);
// Click outside the card to dismiss
rawSeedModal.addEventListener('click', (e) => { if (e.target === rawSeedModal) closeRawSeedModal(); });
rawSeedSelect.addEventListener('change', () => {
  rawSeedGenBtn.disabled = !rawSeedSelect.value;
});
rawSeedGenBtn.addEventListener('click', downloadRawSeed);

async function openRawSeedModal() {
  const repo = repoPathInput.value.trim();
  if (!repo) {
    alert('Please enter the repository path first.');
    return;
  }

  // Reset state
  rawSeedSelect.innerHTML = '<option value="">Loading ranges…</option>';
  rawSeedGenBtn.disabled = true;
  rawSeedError.classList.add('hidden');
  rawSeedModal.classList.remove('hidden');

  try {
    const resp = await fetch(`/api/snapper/ranges?repo=${encodeURIComponent(repo)}`);
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.detail || resp.statusText);
    }
    const { ranges } = await resp.json();
    _populateRangeSelect(ranges);
  } catch (err) {
    rawSeedSelect.innerHTML = '<option value="">Failed to load ranges</option>';
    _showRawSeedError(`Could not load ranges: ${err.message}`);
  }
}

function _populateRangeSelect(ranges) {
  if (!ranges.length) {
    rawSeedSelect.innerHTML = '<option value="">No ranges found in this repository</option>';
    return;
  }
  // Group by manufacturer using optgroup
  const byMfr = {};
  for (const r of ranges) {
    (byMfr[r.manufacturer] ??= []).push(r);
  }
  rawSeedSelect.innerHTML = '<option value="">Select a range…</option>';
  for (const [mfr, rlist] of Object.entries(byMfr)) {
    const grp = document.createElement('optgroup');
    grp.label = mfr;
    for (const r of rlist) {
      const opt = document.createElement('option');
      opt.value = JSON.stringify({ manufacturer: r.manufacturer, range: r.range });
      opt.textContent = r.range;
      grp.appendChild(opt);
    }
    rawSeedSelect.appendChild(grp);
  }
}

async function downloadRawSeed() {
  const repo = repoPathInput.value.trim();
  const selection = rawSeedSelect.value;
  if (!selection) return;

  const { manufacturer, range } = JSON.parse(selection);

  rawSeedGenBtn.disabled = true;
  rawSeedGenBtn.textContent = 'Generating…';
  rawSeedError.classList.add('hidden');

  try {
    const resp = await fetch('/api/snapper/generate-raw-seed', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ repo, manufacturer, range }),
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.detail || resp.statusText);
    }
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `raw_seed_${range}.obx`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    closeRawSeedModal();
  } catch (err) {
    _showRawSeedError(`Generation failed: ${err.message}`);
  } finally {
    rawSeedGenBtn.disabled = false;
    rawSeedGenBtn.textContent = 'Generate \u0026 Download';
  }
}

function closeRawSeedModal() {
  rawSeedModal.classList.add('hidden');
}

function _showRawSeedError(msg) {
  rawSeedError.textContent = msg;
  rawSeedError.classList.remove('hidden');
}

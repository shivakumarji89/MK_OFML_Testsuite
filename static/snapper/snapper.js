// ── Constants ──────────────────────────────────────────────────────────────────
const WARN_LIMIT = 200;
const ERROR_LIMIT = 500;
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
let currentSeed = null;
let hierarchyModes = {};
let queue = [];

// ── Queue persistence ──────────────────────────────────────────────────────────
function saveQueue() {
  localStorage.setItem(QUEUE_STORAGE_KEY, JSON.stringify(queue));
}

function loadQueue() {
  try {
    const saved = localStorage.getItem(QUEUE_STORAGE_KEY);
    if (saved) queue = JSON.parse(saved);
  } catch { queue = []; }
}

// ── DOM refs ───────────────────────────────────────────────────────────────────
const repoPathInput    = document.getElementById('repoPath');
const seedDropZone     = document.getElementById('seedDropZone');
const seedFileInput    = document.getElementById('seedFile');
const seedDropLabel    = document.getElementById('seedDropLabel');
const parseSeedBtn     = document.getElementById('parseSeedBtn');
const seedStatus       = document.getElementById('seedStatus');
const seedInfo         = document.getElementById('seedInfo');
const seedInfoText     = document.getElementById('seedInfoText');
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

// ── Repo path persistence ──────────────────────────────────────────────────────
repoPathInput.value = localStorage.getItem('repoPath') || '';
repoPathInput.addEventListener('input', () => {
  localStorage.setItem('repoPath', repoPathInput.value.trim());
  updateParseSeedBtn();
});

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
  hierarchyModes = {};
  for (const col of currentSeed.property_columns) {
    if (col.is_child) hierarchyModes[col.name] = 'first';
  }

  seedStatus.textContent = '';
  parseSeedBtn.disabled = false;

  seedInfo.classList.remove('hidden');
  seedInfoText.textContent =
    `Article: ${currentSeed.article} · Manufacturer: ${currentSeed.manufacturer}`
    + ` · Series: ${currentSeed.series} · ${currentSeed.property_columns.length} properties`;

  dimensionArea.classList.remove('hidden');
  actionRow.classList.remove('hidden');
  renderDimensions();
  addToQueueBtn.disabled = false;
  updateFilenamePreview();
});

// ── Dimension columns ──────────────────────────────────────────────────────────
function renderDimensions() {
  dimensionColumns.innerHTML = '';
  if (!currentSeed) return;

  const parentHasChild = new Map();
  for (const col of currentSeed.property_columns) {
    if (col.is_child) parentHasChild.set(col.parent, col.name);
  }

  for (const col of currentSeed.property_columns) {
    if (col.is_child) continue;
    const wrapper = document.createElement('div');
    wrapper.className = 'flex flex-col gap-1';
    wrapper.appendChild(_buildCheckboxColumn(col.name, col.values, col.seed_value));
    const childName = parentHasChild.get(col.name);
    if (childName) wrapper.appendChild(_buildHierarchyModeControl(childName));
    dimensionColumns.appendChild(wrapper);
  }
  updatePermCount();
}

function _buildCheckboxColumn(propName, values, seedValue) {
  const col = document.createElement('div');
  col.className = 'bg-white rounded-lg shadow p-3 min-w-44 max-w-56 flex flex-col';
  col.dataset.propName = propName;
  col.innerHTML = `
    <div class="font-semibold text-sm text-gray-700 mb-2 border-b pb-1" title="${escapeHtml(propName)}">${escapeHtml(propName)}</div>
    <div class="flex gap-1 mb-2">
      <button class="text-xs text-blue-600 hover:underline select-all-btn">All</button>
      <span class="text-gray-300">|</span>
      <button class="text-xs text-blue-600 hover:underline select-none-btn">None</button>
    </div>
    <div class="overflow-y-auto max-h-64 space-y-1">
      ${values.map(v => `
        <label class="flex items-center gap-1 text-xs text-gray-700 cursor-pointer">
          <input type="checkbox" class="dim-check" data-prop="${escapeHtml(propName)}" data-value="${escapeHtml(v.code)}"
            ${v.code === seedValue ? 'checked' : ''}>
          <span class="font-mono text-gray-500">${escapeHtml(v.code)}</span>
          ${v.label && v.label !== v.code ? `<span class="text-gray-300">·</span><span class="truncate">${escapeHtml(v.label)}</span>` : ''}
        </label>`).join('')}
    </div>`;
  col.querySelector('.select-all-btn').addEventListener('click', () => {
    col.querySelectorAll('.dim-check').forEach(cb => { cb.checked = true; });
    updatePermCount();
  });
  col.querySelector('.select-none-btn').addEventListener('click', () => {
    col.querySelectorAll('.dim-check').forEach(cb => { cb.checked = false; });
    updatePermCount();
  });
  col.querySelectorAll('.dim-check').forEach(cb => cb.addEventListener('change', updatePermCount));
  return col;
}

function _buildHierarchyModeControl(childPropName) {
  const el = document.createElement('div');
  el.className = 'bg-amber-50 border border-amber-200 rounded p-2 text-xs text-amber-800';
  const mode = hierarchyModes[childPropName] || 'first';
  el.innerHTML = `
    <div class="font-semibold mb-1">${escapeHtml(childPropName)}</div>
    <div class="text-gray-500 mb-1">Colour assignment:</div>
    <div class="flex gap-1">
      <button class="mode-btn px-2 py-0.5 rounded text-xs border ${mode === 'first' ? 'bg-amber-600 text-white border-amber-600' : 'bg-white border-gray-300 text-gray-700'}"
        data-mode="first">First only</button>
      <button class="mode-btn px-2 py-0.5 rounded text-xs border ${mode === 'distribute' ? 'bg-amber-600 text-white border-amber-600' : 'bg-white border-gray-300 text-gray-700'}"
        data-mode="distribute">Distribute</button>
    </div>`;
  el.querySelectorAll('.mode-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      hierarchyModes[childPropName] = btn.dataset.mode;
      el.querySelectorAll('.mode-btn').forEach(b => {
        const active = b.dataset.mode === btn.dataset.mode;
        b.className = `mode-btn px-2 py-0.5 rounded text-xs border ${active ? 'bg-amber-600 text-white border-amber-600' : 'bg-white border-gray-300 text-gray-700'}`;
      });
    });
  });
  return el;
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

function computePermCount(sel) {
  const counts = Object.values(sel).map(v => v.length);
  return counts.length ? counts.reduce((a, b) => a * b, 1) : 0;
}

function updatePermCount() {
  const sel = getParentSelections();
  const count = computePermCount(sel);
  permCount.textContent = `${count.toLocaleString()} permutations`;
  permCount.className = 'text-sm font-medium ' + (
    count > ERROR_LIMIT ? 'text-red-600' :
    count > WARN_LIMIT  ? 'text-amber-600' : 'text-gray-700'
  );
  if (count > ERROR_LIMIT) permCount.textContent += ` ⚠ Consider splitting (max: ${ERROR_LIMIT})`;
  updateFilenamePreview();
}

function updateFilenamePreview() {
  if (!currentSeed) { filenamePreview.textContent = ''; return; }
  filenamePreview.textContent = assembleFilename(
    currentSeed.series, currentSeed.article, articleLabel.value, 'Raw'
  );
}
articleLabel.addEventListener('input', updateFilenamePreview);

// ── Child resolution + class maps ──────────────────────────────────────────────
function resolveChildValues(parentSelections) {
  if (!currentSeed) return {};
  const out = {};
  for (const childCol of currentSeed.property_columns.filter(c => c.is_child)) {
    const parentVals = parentSelections[childCol.parent] || [];
    const mode = hierarchyModes[childCol.name] || 'first';
    const resolution = {};
    for (const pv of parentVals) {
      const children = (childCol.mapping || {})[pv] || [];
      if (children.length === 0) continue;
      resolution[pv] = mode === 'first' ? children[0] : children[parentVals.indexOf(pv) % children.length];
    }
    if (Object.keys(resolution).length > 0) {
      out[childCol.name] = { parent: childCol.parent, resolution };
    }
  }
  return out;
}

function buildClassMaps() {
  if (!currentSeed) return { propertyToClass: {}, propValToClass: {} };
  const propertyToClass = {}, propValToClass = {};
  for (const col of currentSeed.property_columns) {
    propertyToClass[col.name] = col.article_class;
    for (const v of col.values) propValToClass[`${col.name}=${v.code}`] = col.article_class;
  }
  return { propertyToClass, propValToClass };
}

// ── Add to queue ───────────────────────────────────────────────────────────────
addToQueueBtn.addEventListener('click', () => {
  if (!currentSeed) return;
  const parentSelections = getParentSelections();
  const { propertyToClass, propValToClass } = buildClassMaps();
  const label = articleLabel.value.trim();

  queue.push({
    id: crypto.randomUUID(),
    state: 'red',
    label,
    filename: assembleFilename(currentSeed.series, currentSeed.article, label, 'Raw'),
    article: currentSeed.article,
    series: currentSeed.series,
    manufacturer: currentSeed.manufacturer,
    articleClass: currentSeed.property_columns[0]?.article_class || '',
    propertyToClass,
    propValToClass,
    selectedProperties: parentSelections,
    childResolutions: resolveChildValues(parentSelections),
    count: computePermCount(parentSelections),
    seedToken: currentSeed.seed_token ?? null,
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
  card.className = 'queue-card rounded-lg p-3 w-56 flex-shrink-0 flex flex-col gap-2 border-2';
  card.dataset.id = item.id;

  if (item.state === 'red') {
    card.classList.add('border-red-400', 'bg-red-50');
    card.innerHTML = `
      <div class="text-xs font-mono text-gray-700 truncate" title="${escapeHtml(item.filename)}">${escapeHtml(item.filename)}</div>
      <div class="text-xs text-gray-500">${item.count.toLocaleString()} permutations</div>
      <div class="flex gap-1">
        <button class="generate-one-btn flex-1 bg-red-600 text-white px-2 py-1 rounded text-xs hover:bg-red-700">Generate</button>
        <button class="remove-btn text-red-400 hover:text-red-600 px-1">✕</button>
      </div>`;
    card.querySelector('.generate-one-btn').addEventListener('click', () => generateOne(item.id));
    card.querySelector('.remove-btn').addEventListener('click', () => removeItem(item.id));

  } else if (item.state === 'orange') {
    card.classList.add('border-amber-400', 'bg-amber-50');
    card.innerHTML = `
      <div class="text-xs font-mono text-gray-600 truncate" title="${escapeHtml(item.filename)}">${escapeHtml(item.filename)}</div>
      <div class="text-xs text-amber-700 font-medium">Waiting for pCon export</div>
      <div class="clean-drop-zone border-2 border-dashed border-amber-300 rounded p-3 text-center text-xs text-amber-600 cursor-pointer hover:bg-amber-100 transition-colors">
        Drop pCon export here<br>or click to browse
        <input type="file" accept=".obx,.xml" class="hidden clean-file-input">
      </div>
      <button class="regenerate-btn w-full text-xs text-gray-500 hover:text-gray-700 border rounded px-2 py-1">Re-generate</button>`;

    const dropZone = card.querySelector('.clean-drop-zone');
    const fileInput = card.querySelector('.clean-file-input');
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
    card.querySelector('.regenerate-btn').addEventListener('click', () => revertToRed(item.id));

  } else if (item.state === 'green') {
    card.classList.add('border-green-400', 'bg-green-50');
    const cleanName = assembleFilename(item.series, item.article, item.label, 'Clean');
    card.innerHTML = `
      <div class="text-xs font-mono text-gray-700 truncate" title="${escapeHtml(cleanName)}">${escapeHtml(cleanName)}</div>
      <div class="text-xs text-green-700 font-medium">✓ ${item.keptCount} kept · ${item.removedCount} removed</div>
      <button class="done-btn w-full bg-green-600 text-white px-2 py-1 rounded text-xs hover:bg-green-700">Done</button>`;
    card.querySelector('.done-btn').addEventListener('click', () => removeItem(item.id));
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

  const filename = redItems.length === 1
    ? redItems[0].filename
    : assembleZipFilename(redItems[0].series, redItems[0].article).replace('.zip', '.obx');

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
    seed_token: items[0].seedToken ?? null,
    queue: items.map(e => ({
      article: e.article,
      article_class: e.articleClass,
      property_to_class: e.propertyToClass,
      prop_val_to_class: e.propValToClass,
      selected_properties: e.selectedProperties,
      child_resolutions: e.childResolutions || {},
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
    ? assembleZipFilename(items[0].series, items[0].article)
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
  a.download = assembleFilename(item.series, item.article, item.label, 'Clean');
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

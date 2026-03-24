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
let currentPermCount = 0;
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
    if (childName) {
      const childCol = currentSeed.property_columns.find(c => c.name === childName);
      if (childCol) wrapper.appendChild(_buildChildColumn(childCol));
    }
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
  const sel = getParentSelections();

  for (const childCol of currentSeed.property_columns.filter(c => c.is_child)) {
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
      // Dim the section header when inactive
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
  const result = {};
  for (const col of currentSeed.property_columns) {
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

  const sel = getParentSelections();
  const childSel = getChildSelections();

  // Which props are parents of a child?
  const parentProps = new Set(
    currentSeed.property_columns.filter(c => c.is_child).map(c => c.parent)
  );

  // Standalone dimensions: not a child and not a parent of a child
  const factors = [];
  for (const col of currentSeed.property_columns) {
    if (col.is_child || parentProps.has(col.name)) continue;
    const n = (sel[col.name] || []).length;
    if (n > 0) factors.push(n);
  }

  // Parent-child pair expansion: Σ max(1, child_count) per selected parent value
  for (const childCol of currentSeed.property_columns.filter(c => c.is_child)) {
    const parentVals = sel[childCol.parent] || [];
    if (parentVals.length === 0) continue;
    const resolution = childSel[childCol.name]?.resolution || {};
    let expansion = 0;
    for (const pv of parentVals) {
      expansion += Math.max(1, (resolution[pv] || []).length);
    }
    factors.push(expansion);
  }

  const count = factors.length ? factors.reduce((a, b) => a * b, 1) : 0;
  currentPermCount = count;  // stored for use by addToQueueBtn handler
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

// ── Class maps ─────────────────────────────────────────────────────────────────
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
    childResolutions: getChildSelections(),
    count: currentPermCount,
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

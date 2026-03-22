// ── Constants ──────────────────────────────────────────────────────────────────
const WARN_LIMIT = 200;
const ERROR_LIMIT = 500;

// ── HTML safety ────────────────────────────────────────────────────────────────
function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// ── State ──────────────────────────────────────────────────────────────────────
let currentSeed = null;    // Response from /parse-seed
let hierarchyModes = {};   // {child_prop_name: "first"|"distribute"}
let queue = [];            // [{label, article, articleClass, propertyToClass,
                           //   propValToClass, selectedProperties, count}]

// ── DOM refs ───────────────────────────────────────────────────────────────────
const repoPathInput = document.getElementById('repoPath');
const seedFileInput = document.getElementById('seedFile');
const parseSeedBtn = document.getElementById('parseSeedBtn');
const seedStatus = document.getElementById('seedStatus');
const seedInfo = document.getElementById('seedInfo');
const seedInfoText = document.getElementById('seedInfoText');
const dimensionArea = document.getElementById('dimensionArea');
const dimensionColumns = document.getElementById('dimensionColumns');
const emptyState = document.getElementById('emptyState');
const permCount = document.getElementById('permCount');
const articleLabel = document.getElementById('articleLabel');
const addToQueueBtn = document.getElementById('addToQueueBtn');
const queueList = document.getElementById('queueList');
const generateAllBtn = document.getElementById('generateAllBtn');
const generateStatus = document.getElementById('generateStatus');

// ── Persist repo path ──────────────────────────────────────────────────────────
repoPathInput.value = localStorage.getItem('repoPath') || '';
repoPathInput.addEventListener('input', () => {
  localStorage.setItem('repoPath', repoPathInput.value.trim());
});

// ── Seed file input ────────────────────────────────────────────────────────────
seedFileInput.addEventListener('change', () => {
  parseSeedBtn.disabled = !seedFileInput.files.length || !repoPathInput.value.trim();
});

repoPathInput.addEventListener('input', () => {
  parseSeedBtn.disabled = !seedFileInput.files.length || !repoPathInput.value.trim();
});

// ── Parse Seed ────────────────────────────────────────────────────────────────
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
  // Default mode for each child property: "first"
  for (const col of currentSeed.property_columns) {
    if (col.is_child) {
      hierarchyModes[col.name] = 'first';
    }
  }

  seedStatus.textContent = '';
  parseSeedBtn.disabled = false;

  // Show article info
  seedInfo.classList.remove('hidden');
  seedInfoText.textContent =
    `Article: ${currentSeed.article} · Manufacturer: ${currentSeed.manufacturer} · Series: ${currentSeed.series} · ${currentSeed.property_columns.length} properties`;

  // Show dimension columns
  emptyState.classList.add('hidden');
  dimensionArea.classList.remove('hidden');
  renderDimensions();
  addToQueueBtn.disabled = false;
});

// ── Render dimension columns ───────────────────────────────────────────────
function renderDimensions() {
  dimensionColumns.innerHTML = '';
  if (!currentSeed) return;

  // Build a map of parent → child hierarchy info
  const childProps = new Map(); // child_name → {parent, mapping}
  const parentHasChild = new Map(); // parent_name → child_name
  for (const col of currentSeed.property_columns) {
    if (col.is_child) {
      childProps.set(col.name, { parent: col.parent, mapping: col.mapping });
      parentHasChild.set(col.parent, col.name);
    }
  }

  for (const col of currentSeed.property_columns) {
    if (col.is_child) continue; // Child props are rendered as a sub-control of parent

    const colEl = renderPropertyColumn(col, parentHasChild.get(col.name) || null, col.name);
    dimensionColumns.appendChild(colEl);
  }

  updatePermCount();
}

function renderPropertyColumn(col, childPropName, propName) {
  const wrapper = document.createElement('div');
  wrapper.className = 'flex flex-col gap-1';

  // Main checkbox column
  const colEl = _buildCheckboxColumn(propName, col.values, col.seed_value);
  wrapper.appendChild(colEl);

  // If this property has a child (colour), add mode toggle below
  if (childPropName) {
    const modeEl = _buildHierarchyModeControl(childPropName);
    wrapper.appendChild(modeEl);
  }

  return wrapper;
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
        </label>
      `).join('')}
    </div>
  `;

  col.querySelector('.select-all-btn').addEventListener('click', () => {
    col.querySelectorAll('.dim-check').forEach(cb => { cb.checked = true; });
    updatePermCount();
  });
  col.querySelector('.select-none-btn').addEventListener('click', () => {
    col.querySelectorAll('.dim-check').forEach(cb => { cb.checked = false; });
    updatePermCount();
  });
  col.querySelectorAll('.dim-check').forEach(cb =>
    cb.addEventListener('change', updatePermCount)
  );
  return col;
}

function _buildHierarchyModeControl(childPropName) {
  const el = document.createElement('div');
  el.className = 'bg-amber-50 border border-amber-200 rounded p-2 text-xs text-amber-800';
  el.dataset.childProp = childPropName;

  const currentMode = hierarchyModes[childPropName] || 'first';
  el.innerHTML = `
    <div class="font-semibold mb-1">${escapeHtml(childPropName)}</div>
    <div class="text-gray-500 mb-1 text-xs">Colour assignment:</div>
    <div class="flex gap-1">
      <button class="mode-btn px-2 py-0.5 rounded text-xs border ${currentMode === 'first' ? 'bg-amber-600 text-white border-amber-600' : 'bg-white border-gray-300 text-gray-700'}"
        data-mode="first" data-child="${escapeHtml(childPropName)}">First only</button>
      <button class="mode-btn px-2 py-0.5 rounded text-xs border ${currentMode === 'distribute' ? 'bg-amber-600 text-white border-amber-600' : 'bg-white border-gray-300 text-gray-700'}"
        data-mode="distribute" data-child="${escapeHtml(childPropName)}">Distribute</button>
    </div>
  `;

  el.querySelectorAll('.mode-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      hierarchyModes[childPropName] = btn.dataset.mode;
      // Re-render just this control
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
  // Returns {propName: [selectedValues]} for non-child properties only
  const selections = {};
  document.querySelectorAll('.dim-check:checked').forEach(cb => {
    const prop = cb.dataset.prop;
    if (!selections[prop]) selections[prop] = [];
    selections[prop].push(cb.dataset.value);
  });
  return selections;
}

function computePermCount(parentSelections) {
  const counts = Object.values(parentSelections).map(v => v.length);
  if (counts.length === 0) return 0;
  return counts.reduce((a, b) => a * b, 1);
}

function updatePermCount() {
  const sel = getParentSelections();
  const count = computePermCount(sel);
  permCount.textContent = `${count.toLocaleString()} permutations`;
  permCount.className = 'text-sm font-medium ' + (
    count > ERROR_LIMIT ? 'text-red-600' :
    count > WARN_LIMIT  ? 'text-amber-600' :
                          'text-gray-700'
  );
  if (count > ERROR_LIMIT) {
    permCount.textContent += ` ⚠ Consider splitting (suggested max: ${ERROR_LIMIT})`;
  }
}

// ── Resolve child property values ──────────────────────────────────────────────
function resolveChildValues(parentSelections) {
  // For each child property, resolve which values to include based on mode
  // Returns: {child_prop_name: [resolved_values]} to merge into selectedProperties
  if (!currentSeed) return {};
  const childAssignments = {};

  const childCols = currentSeed.property_columns.filter(c => c.is_child);
  for (const childCol of childCols) {
    const parentVals = parentSelections[childCol.parent] || [];
    const mode = hierarchyModes[childCol.name] || 'first';
    const mapping = childCol.mapping || {};
    const resolved = [];

    if (mode === 'first') {
      for (const pv of parentVals) {
        const children = mapping[pv] || [];
        if (children.length > 0) resolved.push(children[0]);
      }
    } else {
      // distribute: cycle through children for each parent value
      const counters = {};
      for (const pv of parentVals) {
        const children = mapping[pv] || [];
        if (children.length === 0) continue;
        const n = counters[pv] || 0;
        resolved.push(children[n % children.length]);
        counters[pv] = n + 1;
      }
    }

    if (resolved.length > 0) {
      childAssignments[childCol.name] = resolved;
    }
  }
  return childAssignments;
}

// ── Build property_to_class and prop_val_to_class from seed ──────────────────
function buildClassMaps() {
  // property_to_class: {prop_name: article_class} — from seed
  // prop_val_to_class: {"PropName=Value": article_class} — for all values loaded
  if (!currentSeed) return { propertyToClass: {}, propValToClass: {} };

  const propertyToClass = {};
  const propValToClass = {};

  for (const col of currentSeed.property_columns) {
    propertyToClass[col.name] = col.article_class;
    for (const v of col.values) {
      propValToClass[`${col.name}=${v.code}`] = col.article_class;
    }
  }
  return { propertyToClass, propValToClass };
}

// ── Add to queue ──────────────────────────────────────────────────────────────
addToQueueBtn.addEventListener('click', () => {
  if (!currentSeed) return;

  const parentSelections = getParentSelections();
  const childResolved = resolveChildValues(parentSelections);
  const selectedProperties = { ...parentSelections, ...childResolved };

  const count = computePermCount(parentSelections);
  const label = articleLabel.value.trim() || currentSeed.article;
  const { propertyToClass, propValToClass } = buildClassMaps();

  queue.push({
    label,
    article: currentSeed.article,
    articleClass: currentSeed.property_columns[0]?.article_class || '',
    propertyToClass,
    propValToClass,
    selectedProperties,
    count,
    manufacturer: currentSeed.manufacturer,
    series: currentSeed.series,
  });

  articleLabel.value = '';
  renderQueue();
});

function renderQueue() {
  queueList.innerHTML = '';
  for (let i = 0; i < queue.length; i++) {
    const entry = queue[i];
    const card = document.createElement('div');
    card.className = 'bg-gray-50 border rounded p-2 text-xs';
    card.innerHTML = `
      <div class="flex justify-between items-start">
        <span class="font-semibold text-gray-800">${escapeHtml(entry.label)}</span>
        <button class="text-red-500 hover:text-red-700 ml-2 remove-btn" data-idx="${i}">✕</button>
      </div>
      <div class="text-gray-600 mt-0.5">Article: ${escapeHtml(entry.article)}</div>
      <div class="text-gray-500 mt-0.5">${entry.count.toLocaleString()} permutations · ${Object.keys(entry.selectedProperties).length} props</div>
    `;
    card.querySelector('.remove-btn').addEventListener('click', (e) => {
      queue.splice(parseInt(e.target.dataset.idx), 1);
      renderQueue();
    });
    queueList.appendChild(card);
  }
  generateAllBtn.disabled = queue.length === 0;
}

// ── Generate All ──────────────────────────────────────────────────────────
generateAllBtn.addEventListener('click', async () => {
  if (queue.length === 0) return;

  generateAllBtn.disabled = true;
  generateAllBtn.textContent = 'Generating…';
  generateStatus.classList.remove('hidden');
  generateStatus.textContent = '';

  // All items must share the same manufacturer and series (they're per-article queues)
  // Use the first item's manufacturer/series (they should all match if from same range)
  const manufacturer = queue[0].manufacturer;
  const series = queue[0].series;

  const queuePayload = queue.map(entry => ({
    article: entry.article,
    article_class: entry.articleClass,
    property_to_class: entry.propertyToClass,
    prop_val_to_class: entry.propValToClass,
    selected_properties: entry.selectedProperties,
  }));

  const payload = {
    manufacturer,
    series,
    queue: queuePayload,
    filename: `snapper_${series}.obx`,
  };

  let response;
  try {
    response = await fetch('/api/snapper/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  } catch (err) {
    generateStatus.textContent = `Network error: ${err.message}`;
    generateAllBtn.disabled = false;
    generateAllBtn.textContent = 'Generate All';
    return;
  }

  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: 'Unknown error' }));
    generateStatus.textContent = `Error: ${err.detail}`;
    generateAllBtn.disabled = false;
    generateAllBtn.textContent = 'Generate All';
    return;
  }

  // Trigger download
  const contentType = response.headers.get('content-type') || '';
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = contentType.includes('zip')
    ? `snapper_${series}.zip`
    : `snapper_${series}.obx`;
  a.click();
  URL.revokeObjectURL(url);

  generateStatus.textContent = 'Downloaded.';
  generateAllBtn.disabled = false;
  generateAllBtn.textContent = 'Generate All';
});

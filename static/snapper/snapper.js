// ── State ──────────────────────────────────────────────────────────────────
const WARN_LIMIT = 200;
const ERROR_LIMIT = 500;
let rangeData = null;  // {articles, properties, values}
let queue = [];        // [{name, selectedArticles, selectedProperties, count}]

// ── DOM refs ───────────────────────────────────────────────────────────────
const repoPath = document.getElementById('repoPath');
const mfrSelect = document.getElementById('mfrSelect');
const rangeSelect = document.getElementById('rangeSelect');
const loadBtn = document.getElementById('loadBtn');
const dimensionArea = document.getElementById('dimensionArea');
const dimensionColumns = document.getElementById('dimensionColumns');
const emptyState = document.getElementById('emptyState');
const permCount = document.getElementById('permCount');
const genName = document.getElementById('genName');
const addToQueueBtn = document.getElementById('addToQueueBtn');
const queueList = document.getElementById('queueList');
const generateAllBtn = document.getElementById('generateAllBtn');

// ── Persist repo path ──────────────────────────────────────────────────────
repoPath.value = localStorage.getItem('repoPath') || '';

repoPath.addEventListener('change', async () => {
  localStorage.setItem('repoPath', repoPath.value.trim());
  await loadRanges();
});

// ── Load ranges from API ───────────────────────────────────────────────────
async function loadRanges() {
  const repo = repoPath.value.trim();
  if (!repo) return;
  const res = await fetch(`/api/snapper/ranges?repo=${encodeURIComponent(repo)}`);
  if (!res.ok) return;
  const ranges = await res.json();

  // Populate manufacturer dropdown
  const mfrs = [...new Set(ranges.map(r => r.manufacturer))].sort();
  mfrSelect.innerHTML = '<option value="">—</option>' +
    mfrs.map(m => `<option value="${m}">${m}</option>`).join('');
  mfrSelect.disabled = false;

  mfrSelect.addEventListener('change', () => {
    const selectedMfr = mfrSelect.value;
    const filtered = ranges.filter(r => r.manufacturer === selectedMfr);
    rangeSelect.innerHTML = '<option value="">—</option>' +
      filtered.map(r => `<option value="${r.range}">${r.range}</option>`).join('');
    rangeSelect.disabled = false;
    rangeSelect.addEventListener('change', () => {
      loadBtn.disabled = !rangeSelect.value;
    });
  });
}

if (repoPath.value) loadRanges();

// ── Load range data ────────────────────────────────────────────────────────
loadBtn.addEventListener('click', async () => {
  const repo = repoPath.value.trim();
  const mfr = mfrSelect.value;
  const range = rangeSelect.value;
  const res = await fetch(
    `/api/snapper/range?repo=${encodeURIComponent(repo)}&manufacturer=${mfr}&range=${range}`
  );
  if (!res.ok) { alert('Failed to load range'); return; }
  rangeData = await res.json();
  renderDimensions();
  emptyState.classList.add('hidden');
  dimensionArea.classList.remove('hidden');
  addToQueueBtn.disabled = false;
});

// ── Render dimension columns ───────────────────────────────────────────────
function renderDimensions() {
  dimensionColumns.innerHTML = '';

  // Articles column
  const articleCodes = rangeData.articles.map(a => a.code);
  dimensionColumns.appendChild(renderColumn('Articles', articleCodes, 'article'));

  // Property columns — one per unique property name
  const propMap = {};
  for (const v of rangeData.values) {
    if (!propMap[v.property_name]) propMap[v.property_name] = [];
    if (!propMap[v.property_name].includes(v.value)) {
      propMap[v.property_name].push(v.value);
    }
  }

  // Sort by sort_order from properties list
  const propOrder = {};
  for (const p of rangeData.properties) {
    if (!propOrder[p.name]) propOrder[p.name] = p.sort_order;
  }
  const sortedProps = Object.keys(propMap).sort(
    (a, b) => (propOrder[a] || 999) - (propOrder[b] || 999)
  );

  for (const propName of sortedProps) {
    dimensionColumns.appendChild(renderColumn(propName, propMap[propName], `prop_${propName}`));
  }

  updatePermCount();
}

function renderColumn(label, values, key) {
  const col = document.createElement('div');
  col.className = 'bg-white rounded-lg shadow p-3 min-w-36 max-w-48 flex flex-col';
  col.innerHTML = `
    <div class="font-semibold text-sm text-gray-700 mb-2 border-b pb-1">${label}</div>
    <div class="flex gap-1 mb-2">
      <button class="text-xs text-blue-600 hover:underline select-all-btn">All</button>
      <span class="text-gray-300">|</span>
      <button class="text-xs text-blue-600 hover:underline select-none-btn">None</button>
    </div>
    <div class="overflow-y-auto max-h-64 space-y-1">
      ${values.map(v => `
        <label class="flex items-center gap-1 text-xs text-gray-700 cursor-pointer">
          <input type="checkbox" class="dim-check" data-key="${key}" data-value="${v}" checked>
          <span>${v}</span>
        </label>
      `).join('')}
    </div>
  `;
  col.querySelector('.select-all-btn').addEventListener('click', () => {
    col.querySelectorAll('.dim-check').forEach(cb => cb.checked = true);
    updatePermCount();
  });
  col.querySelector('.select-none-btn').addEventListener('click', () => {
    col.querySelectorAll('.dim-check').forEach(cb => cb.checked = false);
    updatePermCount();
  });
  col.querySelectorAll('.dim-check').forEach(cb =>
    cb.addEventListener('change', updatePermCount)
  );
  return col;
}

// ── Permutation count ──────────────────────────────────────────────────────
function getSelections() {
  const articles = [];
  const properties = {};

  document.querySelectorAll('.dim-check:checked').forEach(cb => {
    const key = cb.dataset.key;
    const val = cb.dataset.value;
    if (key === 'article') {
      articles.push(val);
    } else {
      const propName = key.replace(/^prop_/, '');
      if (!properties[propName]) properties[propName] = [];
      properties[propName].push(val);
    }
  });
  return { articles, properties };
}

function countPermutations(articles, properties) {
  if (articles.length === 0) return 0;
  const propCounts = Object.values(properties).map(v => v.length);
  const propProduct = propCounts.reduce((a, b) => a * b, 1);
  return articles.length * propProduct;
}

function updatePermCount() {
  const { articles, properties } = getSelections();
  const count = countPermutations(articles, properties);
  permCount.textContent = `${count.toLocaleString()} permutations`;
  permCount.className = 'mt-4 text-sm font-medium ' + (
    count > ERROR_LIMIT ? 'text-red-600' :
    count > WARN_LIMIT  ? 'text-amber-600' :
                          'text-gray-700'
  );
  if (count > ERROR_LIMIT) {
    permCount.textContent += ` ⚠ Consider splitting into multiple files (suggested max: ${ERROR_LIMIT})`;
  }
}

// ── Queue ──────────────────────────────────────────────────────────────────
addToQueueBtn.addEventListener('click', () => {
  const name = genName.value.trim() || `Generation ${queue.length + 1}`;
  const { articles, properties } = getSelections();
  const count = countPermutations(articles, properties);
  queue.push({
    name,
    selectedArticles: articles,
    selectedProperties: properties,
    count,
    repo: repoPath.value.trim(),
    manufacturer: mfrSelect.value,
    range: rangeSelect.value,
  });
  genName.value = '';
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
        <span class="font-semibold text-gray-800">${entry.name}</span>
        <button class="text-red-500 hover:text-red-700 ml-2" data-idx="${i}">✕</button>
      </div>
      <div class="text-gray-500 mt-1">${entry.count.toLocaleString()} permutations</div>
      <div class="text-gray-400">${entry.selectedArticles.length} articles · ${Object.keys(entry.selectedProperties).length} props</div>
    `;
    card.querySelector('button').addEventListener('click', (e) => {
      queue.splice(parseInt(e.target.dataset.idx), 1);
      renderQueue();
    });
    queueList.appendChild(card);
  }
  generateAllBtn.disabled = queue.length === 0;
}

// ── Generate all ───────────────────────────────────────────────────────────
generateAllBtn.addEventListener('click', async () => {
  generateAllBtn.disabled = true;
  generateAllBtn.textContent = 'Generating…';

  for (const entry of queue) {
    const payload = {
      repo: entry.repo,
      manufacturer: entry.manufacturer,
      range: entry.range,
      selected_articles: entry.selectedArticles,
      selected_properties: entry.selectedProperties,
      filename: `${entry.name.replace(/\s+/g, '_')}.obx`,
    };
    const res = await fetch('/api/snapper/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      alert(`Failed to generate: ${entry.name}`);
      continue;
    }
    // Trigger browser download
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = payload.filename;
    a.click();
    URL.revokeObjectURL(url);
  }

  generateAllBtn.disabled = false;
  generateAllBtn.textContent = 'Generate All';
});

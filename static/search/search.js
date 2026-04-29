// ── Constants ─────────────────────────────────────────────────────────────────
const FILE_TYPES = [
  'ocd_article',
  'ocd_artlongtext',
  'ocd_artshorttext',
  'ocd_property',
  'ocd_propertytext',
  'ocd_propvalue',
  'ocd_propvaluetext',
];

// ── Element refs ──────────────────────────────────────────────────────────────
const repoSelect    = document.getElementById('repoSelect');
const noReposMsg    = document.getElementById('noReposMsg');
const openSettingsLink = document.getElementById('openSettingsLink');
const queryInput    = document.getElementById('queryInput');
const matchMode     = document.getElementById('matchMode');
const caseSensitive = document.getElementById('caseSensitive');
const fileTypeChecks = document.getElementById('fileTypeChecks');
const searchBtn     = document.getElementById('searchBtn');
const statusMsg     = document.getElementById('statusMsg');
const resultsEl     = document.getElementById('results');

// ── File type checkboxes ──────────────────────────────────────────────────────
FILE_TYPES.forEach(ft => {
  const label = document.createElement('label');
  label.className = 'flex items-center gap-1.5 text-sm text-gray-700 cursor-pointer';
  label.innerHTML = `
    <input type="checkbox" class="ft-check rounded" value="${ft}" checked>
    <span class="font-mono text-xs">${ft.replace('ocd_', '')}</span>`;
  fileTypeChecks.appendChild(label);
});

// ── Repo picker ───────────────────────────────────────────────────────────────
function populateRepos() {
  const repos = Settings.getSavedRepos();
  const current = repoSelect.value;
  repoSelect.innerHTML = '<option value="">— select repo —</option>';
  repos.forEach(r => {
    const opt = document.createElement('option');
    opt.value = r.path;
    opt.textContent = r.name;
    if (r.path === current) opt.selected = true;
    repoSelect.appendChild(opt);
  });
  noReposMsg.classList.toggle('hidden', repos.length > 0);
  repoSelect.classList.toggle('hidden', repos.length === 0);
  updateSearchBtn();
}

document.addEventListener('settings:savedReposChanged', populateRepos);
openSettingsLink.addEventListener('click', () =>
  document.getElementById('settingsGearBtn')?.click()
);

// ── Enable / disable search button ────────────────────────────────────────────
function updateSearchBtn() {
  const hasRepo  = repoSelect.value !== '';
  const hasQuery = queryInput.value.trim() !== '';
  const hasType  = [...document.querySelectorAll('.ft-check')].some(c => c.checked);
  searchBtn.disabled = !(hasRepo && hasQuery && hasType);
}

repoSelect.addEventListener('change', updateSearchBtn);
queryInput.addEventListener('input', updateSearchBtn);
fileTypeChecks.addEventListener('change', updateSearchBtn);

// ── Search ────────────────────────────────────────────────────────────────────
searchBtn.addEventListener('click', runSearch);
queryInput.addEventListener('keydown', e => { if (e.key === 'Enter') runSearch(); });

async function runSearch() {
  const repo = repoSelect.value;
  const query = queryInput.value.trim();
  const mode  = matchMode.value;
  const cs    = caseSensitive.checked;
  const types = [...document.querySelectorAll('.ft-check')]
    .filter(c => c.checked).map(c => c.value);

  if (!repo || !query || !types.length) return;

  searchBtn.disabled = true;
  statusMsg.textContent = 'Searching…';
  resultsEl.innerHTML = '';

  let data;
  try {
    const resp = await fetch('/api/search/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        repo, query, match_mode: mode, case_sensitive: cs, file_types: types,
      }),
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: resp.statusText }));
      throw new Error(err.detail || resp.statusText);
    }
    data = await resp.json();
  } catch (err) {
    statusMsg.textContent = '';
    resultsEl.innerHTML = `<p class="text-red-600 text-sm">${_esc(err.message)}</p>`;
    searchBtn.disabled = false;
    return;
  }

  searchBtn.disabled = false;
  renderResults(data, query);
}

// ── Results rendering ─────────────────────────────────────────────────────────
function renderResults(data, query) {
  const { results, ranges_searched, duration_ms } = data;
  const matchCount = results.reduce((n, r) => n + r.matches.length, 0);

  // Group by manufacturer+range
  const grouped = {};
  for (const r of results) {
    const key = `${r.manufacturer}/${r.range}`;
    if (!grouped[key]) grouped[key] = { manufacturer: r.manufacturer, range: r.range, files: [] };
    grouped[key].files.push({ file_type: r.file_type, matches: r.matches });
  }

  const rangeCount = Object.keys(grouped).length;

  let html = `<p class="text-sm text-gray-500 mb-4">`;
  if (matchCount === 0) {
    html += `No matches found — searched ${ranges_searched} range${ranges_searched !== 1 ? 's' : ''} in ${duration_ms}ms.`;
  } else {
    html += `Found <strong>${matchCount}</strong> match${matchCount !== 1 ? 'es' : ''} across <strong>${rangeCount}</strong> range${rangeCount !== 1 ? 's' : ''} (searched ${ranges_searched} in ${duration_ms}ms).`;
  }
  html += `</p>`;

  for (const [key, group] of Object.entries(grouped)) {
    html += `
      <details open class="bg-white rounded-xl shadow mb-3">
        <summary class="px-5 py-3 font-semibold text-gray-700 cursor-pointer select-none
                        flex items-center justify-between hover:bg-gray-50 rounded-xl">
          <span class="font-mono text-sm">${_esc(group.manufacturer)} / ${_esc(group.range)}</span>
          <span class="text-xs text-gray-400 font-normal">
            ${group.files.reduce((n, f) => n + f.matches.length, 0)} match${group.files.reduce((n, f) => n + f.matches.length, 0) !== 1 ? 'es' : ''}
          </span>
        </summary>
        <div class="px-5 pb-4 space-y-4">
          ${group.files.map(f => renderFileBlock(f)).join('')}
        </div>
      </details>`;
  }

  statusMsg.textContent = '';
  resultsEl.innerHTML = html;
}

function renderFileBlock({ file_type, matches }) {
  const rows = matches.map(m => {
    const cells = m.row.map(c => `<td class="px-3 py-1 text-xs font-mono whitespace-nowrap max-w-xs truncate" title="${_esc(c)}">${_esc(c)}</td>`).join('');
    return `<tr class="border-t border-gray-100 hover:bg-gray-50">
      <td class="px-3 py-1 text-xs text-gray-400 tabular-nums">${m.row_number}</td>
      ${cells}
    </tr>`;
  }).join('');

  return `
    <div>
      <p class="text-xs font-semibold text-gray-500 uppercase tracking-wide mt-3 mb-1 font-mono">
        ${_esc(file_type)}.csv
        <span class="font-normal normal-case text-gray-400">(${matches.length} row${matches.length !== 1 ? 's' : ''})</span>
      </p>
      <div class="overflow-x-auto rounded border border-gray-200">
        <table class="min-w-full">
          <tbody>${rows}</tbody>
        </table>
      </div>
    </div>`;
}

// _esc is provided globally by settings.js (loaded before this script)

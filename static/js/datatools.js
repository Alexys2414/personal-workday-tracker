/* ============================================================
   Jornada — exportar (CSV / informe PDF) e importar (CSV)
   La importación es en dos pasos: el servidor valida todo el archivo
   y devuelve una vista previa; solo al confirmar se guarda, en una única
   escritura y tras crear una copia de seguridad.
   ============================================================ */
'use strict';

const importState = { file: null, preview: null, mode: 'skip', selected: new Set() };

/* ------------------------------------------------------------ exportar */

function prepareDataTab() {
  const { year, month } = state.cal || {};
  if (year) $('#exMonthName').textContent = `(${longDate(`${year}-${pad(month)}-01`, { month: 'long', year: 'numeric' })})`;
  const today = dateKey(nowMs());
  if (!$('#exFrom').value) $('#exFrom').value = `${today.slice(0, 8)}01`;
  if (!$('#exTo').value) $('#exTo').value = today;
  $('#exError').hidden = true;
}

function exportRange() {
  const scope = document.querySelector('input[name="exScope"]:checked').value;
  const today = state.today?.date || dateKey(nowMs());
  if (scope === 'all') return {};
  if (scope === 'week') {
    const monday = addDays(today, -weekdayOf(today));
    return { from: monday, to: addDays(monday, 6) };
  }
  if (scope === 'month') {
    const { year, month } = state.cal;
    const last = new Date(Date.UTC(year, month, 0)).getUTCDate();
    return { from: `${year}-${pad(month)}-01`, to: `${year}-${pad(month)}-${pad(last)}` };
  }
  const from = $('#exFrom').value, to = $('#exTo').value;
  if (!from || !to) throw new Error(t('data.range_missing'));
  if (to < from) throw new Error(t('data.range_order'));
  return { from, to };
}

const rangeQuery = (r) => new URLSearchParams(Object.entries(r).filter(([, v]) => v)).toString();

async function downloadCsv(button) {
  let range;
  try { range = exportRange(); } catch (e) { showError($('#exError'), e.message); return; }
  $('#exError').hidden = true;
  button.classList.add('is-saving');
  try {
    const res = await fetch(`/api/export.csv?${rangeQuery(range)}`);
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).error || `Error ${res.status}`);
    const blob = await res.blob();
    const name = /filename="([^"]+)"/.exec(res.headers.get('Content-Disposition') || '')?.[1] || 'jornada.csv';
    const url = URL.createObjectURL(blob);
    const a = Object.assign(document.createElement('a'), { href: url, download: name });
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  } catch (e) {
    showError($('#exError'), e.message);
  } finally {
    button.classList.remove('is-saving');
  }
}

function openReport() {
  let range;
  try { range = exportRange(); } catch (e) { showError($('#exError'), e.message); return; }
  $('#exError').hidden = true;
  window.open(`/report?${rangeQuery(range)}`, '_blank', 'noopener');
}

/* ------------------------------------------------------------ importar */

function toBase64(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = '';
  for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(binary);
}

function resetImport({ silent = true } = {}) {
  importState.file = null;
  importState.preview = null;
  importState.selected.clear();
  importState.mode = 'skip';
  $('#imPreview').hidden = true;
  $('#imFile').value = '';
  $('#imError').hidden = true;
  $('#imDrop').classList.remove('loading');
  if (!silent) toast(t('imp.cancelled'), 'info', 2600);
}

async function previewFile(file) {
  if (!file) return;
  resetImport();
  const drop = $('#imDrop');
  drop.classList.add('loading');
  drop.querySelector('strong').textContent = t('data.reading');
  try {
    importState.file = toBase64(await file.arrayBuffer());
    importState.preview = await api('/api/import/preview', { method: 'POST', body: { file: importState.file } });
    importState.mode = 'skip';
    setSegment($('#imDupSeg'), 'skip');
    renderImportPreview();
  } catch (e) {
    importState.file = null;
    showError($('#imError'), e.message);
  } finally {
    drop.classList.remove('loading');
    drop.querySelector('strong').textContent = t('data.choose');
  }
}

function importCount() {
  const rows = importState.preview?.rows || [];
  const fresh = rows.filter((r) => r.status === 'new').length;
  return fresh + (importState.mode === 'overwrite' ? importState.selected.size : 0);
}

function renderImportPreview() {
  const p = importState.preview;
  if (!p) return;
  const { new: fresh, dup, error } = p.counts;
  $('#imSummary').innerHTML = [
    ['new', 'i-plus', t('imp.summary_new', { n: fresh })],
    ['dup', 'i-rotate', t('imp.summary_dup', { n: dup })],
    ['err', 'i-alert', t('imp.summary_err', { n: error })],
  ].map(([k, ic, txt]) => `<span class="im-chip ${k}">${icon(ic)}${esc(txt)}</span>`).join('');
  $('#imDupMode').hidden = !dup;
  $('#imErrNote').hidden = !error;
  const overwrite = importState.mode === 'overwrite';
  $('#imAll').disabled = !overwrite || !dup;
  $('#imAll').checked = overwrite && dup > 0 && importState.selected.size === dup;

  $('#imRows').innerHTML = p.rows.map((r) => {
    const label = { new: t('imp.new'), dup: t('imp.dup'), error: t('imp.err') }[r.status];
    let check = '';
    if (r.status === 'dup') {
      check = `<input type="checkbox" data-date="${r.date}" ${importState.selected.has(r.date) ? 'checked' : ''} ${overwrite ? '' : 'disabled'} aria-label="${esc(t('imp.overwrite'))}">`;
    } else if (r.status === 'new') {
      check = `<span class="im-ok">${icon('i-check')}</span>`;
    }
    const detail = r.status === 'error'
      ? r.errors.map((m) => `<span class="im-err">${esc(m)}</span>`).join('')
      : `<span>${esc(t('imp.mode_profile', { mode: modeLabel(r.mode), profile: r.profile ? profileName(r.profile) : '—' }))}</span>
         <span class="muted">${r.clock_in ? `${r.clock_in.slice(0, 5)} – ${(r.clock_out || '…').slice(0, 5)}` : '—'}${r.clock_in ? ` · ${esc(t('imp.worked', { dur: human(r.worked_s) }))}` : ''}${r.has_notes ? ` ${icon('i-note')}` : ''}</span>`;
    return `<tr class="row-${r.status}">
      <td class="im-check">${check}</td>
      <td class="tabular">${esc(r.date || '—')}</td>
      <td><span class="im-badge ${r.status}">${esc(label)}</span></td>
      <td class="im-detail"><div>${detail}</div></td></tr>`;
  }).join('');

  const n = importCount();
  $('#imConfirm').textContent = n === 1 ? t('imp.confirm_one') : t('imp.confirm', { n });
  $('#imConfirm').disabled = n === 0;
  $('#imPreview').hidden = false;
}

async function confirmImport() {
  const p = importState.preview;
  if (!p) return;
  const overwrite = importState.mode === 'overwrite' ? [...importState.selected] : [];
  if (importCount() === 0) { toast(t('imp.nothing'), 'info'); return; }
  if (overwrite.length) {
    const ok = await confirmDialog({
      title: t('imp.ow_title'), text: t('imp.ow_text', { n: overwrite.length }), ok: t('imp.ow_ok'), danger: true,
    });
    if (!ok) return;
  }
  const btn = $('#imConfirm');
  btn.classList.add('is-saving');
  try {
    const res = await api('/api/import/commit', {
      method: 'POST', body: { file: importState.file, overwrite, fingerprint: p.fingerprint },
    });
    toast(t('imp.done', { n: res.imported, file: res.backup || '—' }), 'ok', 6000);
    resetImport();
    await refreshAll();
  } catch (e) {
    showError($('#imError'), e.message);
    if (e.status === 409) resetImport();
  } finally {
    btn.classList.remove('is-saving');
  }
}

/* ------------------------------------------------------------ eventos */

document.querySelectorAll('input[name="exScope"]').forEach((r) => r.addEventListener('change', () => {
  $('#exRange').hidden = document.querySelector('input[name="exScope"]:checked').value !== 'range';
  $('#exError').hidden = true;
}));
$('#exCsv').addEventListener('click', (e) => downloadCsv(e.currentTarget));
$('#exPdf').addEventListener('click', openReport);

$('#imFile').addEventListener('change', (e) => previewFile(e.target.files[0]));
const drop = $('#imDrop');
['dragenter', 'dragover'].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add('over'); }));
['dragleave', 'drop'].forEach((ev) => drop.addEventListener(ev, () => drop.classList.remove('over')));
drop.addEventListener('drop', (e) => { e.preventDefault(); previewFile(e.dataTransfer.files[0]); });

$('#imDupSeg').addEventListener('click', (e) => {
  const b = e.target.closest('button[data-value]');
  if (!b) return;
  importState.mode = b.dataset.value;
  if (importState.mode === 'skip') importState.selected.clear();
  renderImportPreview();
});
$('#imRows').addEventListener('change', (e) => {
  const box = e.target.closest('input[data-date]');
  if (!box) return;
  if (box.checked) importState.selected.add(box.dataset.date); else importState.selected.delete(box.dataset.date);
  renderImportPreview();
});
$('#imAll').addEventListener('change', (e) => {
  importState.selected.clear();
  if (e.target.checked) importState.preview.rows.filter((r) => r.status === 'dup').forEach((r) => importState.selected.add(r.date));
  renderImportPreview();
});
$('#imCancel').addEventListener('click', () => resetImport({ silent: false }));
$('#imConfirm').addEventListener('click', confirmImport);
$('#settingsDialog').addEventListener('close', () => resetImport());

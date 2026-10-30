/* ============================================================
   Jornada — festivos, vacaciones y ausencias (2.1)
   · Ajustes › Calendario: festivos (también recurrentes), rangos de
     vacaciones, importación JSON/CSV y cómo computa cada tipo de día.
   · Diálogo «Tipo de día» desde el detalle del calendario.
   · Tarjeta «Próximos días libres».
   Marcar un día con fichajes nunca los toca sin preguntar (diálogo de conflicto).
   ============================================================ */
'use strict';

const calTab = { data: null, editing: null, rangeTimer: null, plan: null, importText: null, importName: '', typesDraft: null };

const typeName = (type) => t(`dt.${type}`);
const typeIcon = (type) => icon(DAY_TYPE_ICONS[type] || 'i-tag');

function mdLabel(md) {
  return longDate(`2024-${md}`, { day: 'numeric', month: 'long' });
}

/* ------------------------------------------------------ conflictos */

/** Pregunta qué hacer con los días que ya tienen fichajes. Devuelve 'apply', 'keep' o 'cancel'. */
function conflictChoice(conflicts, type) {
  const dlg = $('#conflictDialog');
  $('#conflictText').textContent = t(conflicts.length === 1 ? 'cf.text_one' : 'cf.text', { n: conflicts.length, type: typeName(type) });
  $('#conflictList').innerHTML = conflicts.slice(0, 6).map((c) =>
    `<li>${icon('i-calendar')}<span>${esc(longDate(c.date, { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' }))}</span><em>${esc(t(STATUS_CHIP({ status: c.status, color: '' })[1]))}</em></li>`).join('')
    + (conflicts.length > 6 ? `<li class="muted">${esc(t('cf.more', { n: conflicts.length - 6 }))}</li>` : '');
  dlg.returnValue = '';
  dlg.showModal();
  return new Promise((resolve) => dlg.addEventListener('close', () => resolve(dlg.returnValue || 'cancel'), { once: true }));
}

/** Envía una marca; si choca con fichajes, pregunta y reenvía con la decisión. */
async function sendMarks(send, type) {
  try {
    return await send(undefined);
  } catch (e) {
    if (e.status !== 409 || e.data?.code !== 'cal.conflict') throw e;
    const choice = await conflictChoice(e.data.conflicts || [], type);
    if (choice === 'cancel') return null;
    return send(choice === 'apply');
  }
}

async function afterCalendarChange(message) {
  if (message) toast(message, 'ok');
  syncSend();
  await refreshAll();
  if (settingsDialog.open && settingsDialog.dataset.tab === 'calendar') await loadCalendarTab();
}

/* ---------------------------------------------------- Ajustes › Calendario */

async function loadCalendarTab() {
  try {
    calTab.data = (await api('/api/calendar')).calendar;
  } catch (e) {
    showError($('#csError'), e.message);
    return;
  }
  renderHolidays();
}

function prepareCalendarTab() {
  $('#csError').hidden = true;
  $('#rType').innerHTML = DAY_TYPES.filter((x) => x !== 'holiday')
    .map((x) => `<option value="${x}" ${x === 'vacation' ? 'selected' : ''}>${esc(typeName(x))}</option>`).join('')
    + `<option value="holiday">${esc(typeName('holiday'))}</option>`;
  resetHolidayForm();
  loadCalendarTab();
  previewRange();
}

function holidayItems() {
  const cal = calTab.data || { days: {}, recurring: {} };
  const today = dateKey(nowMs());
  const fixed = Object.entries(cal.days).filter(([, m]) => m.type === 'holiday')
    .map(([key, m]) => ({ key, recurring: false, label: m.label || '', past: key < today }));
  const recurring = Object.entries(cal.recurring).map(([key, m]) => ({ key, recurring: true, label: m.label || '' }));
  fixed.sort((a, b) => (a.past - b.past) || (a.past ? b.key.localeCompare(a.key) : a.key.localeCompare(b.key)));
  recurring.sort((a, b) => a.key.localeCompare(b.key));
  return [...recurring, ...fixed];
}

function renderHolidays() {
  const items = holidayItems();
  $('#hList').innerHTML = items.length ? items.map((h) => `
    <li class="${h.past ? 'past' : ''}" data-key="${h.key}" data-recurring="${h.recurring}">
      <span class="hol-icon">${icon(h.recurring ? 'i-rotate' : 'i-flag')}</span>
      <span class="hol-main"><strong>${esc(h.label || typeName('holiday'))}</strong>
        <small class="muted">${esc(h.recurring ? t('cs.every_year', { date: mdLabel(h.key) }) : longDate(h.key, { weekday: 'short', day: 'numeric', month: 'long', year: 'numeric' }))}</small></span>
      <button type="button" class="icon-btn small" data-hedit title="${esc(t('common.edit'))}" aria-label="${esc(t('common.edit'))}">${icon('i-edit')}</button>
      <button type="button" class="icon-btn small" data-hdel title="${esc(t('common.delete'))}" aria-label="${esc(t('common.delete'))}">${icon('i-trash')}</button>
    </li>`).join('') : `<li class="hol-empty muted small">${esc(t('cs.none'))}</li>`;
}

function resetHolidayForm() {
  calTab.editing = null;
  $('#hDate').value = '';
  $('#hLabel').value = '';
  $('#hRecurring').checked = false;
  $('#hAddText').textContent = t('cs.add');
}

async function saveHoliday() {
  const err = $('#csError');
  err.hidden = true;
  const value = $('#hDate').value;
  if (!value) { showError(err, t('cs.need_date')); return; }
  const recurring = $('#hRecurring').checked;
  const label = $('#hLabel').value.trim();
  const key = recurring ? value.slice(5) : value;
  const old = calTab.editing;
  try {
    let res;
    if (recurring) res = await api(`/api/calendar/recurring/${key}`, { method: 'PUT', body: { label } });
    else res = await sendMarks((apply) => api(`/api/calendar/days/${key}`, { method: 'PUT', body: { type: 'holiday', label, apply } }), 'holiday');
    if (res === null) return;
    // Editar fecha o recurrencia: se quita la entrada anterior (solo después de guardar la nueva).
    if (old && (old.key !== key || old.recurring !== recurring)) {
      await api(old.recurring ? `/api/calendar/recurring/${old.key}` : `/api/calendar/days/${old.key}`, { method: 'DELETE' }).catch(() => {});
    }
    resetHolidayForm();
    await afterCalendarChange(t(old ? 'cs.updated' : 'cs.added'));
  } catch (e) {
    showError(err, e.message);
  }
}

async function deleteHoliday(key, recurring) {
  const ok = await confirmDialog({
    title: t('cs.delete_title'),
    text: recurring ? t('cs.delete_recurring', { date: mdLabel(key) }) : t('cs.delete_text', { date: longDate(key) }),
    ok: t('common.delete'), danger: true,
  });
  if (!ok) return;
  try {
    await api(recurring ? `/api/calendar/recurring/${key}` : `/api/calendar/days/${key}`, { method: 'DELETE' });
    await afterCalendarChange(t('cs.deleted'));
  } catch (e) {
    showError($('#csError'), e.message);
  }
}

/* --- rangos (vacaciones, permisos…) --- */

function rangeBody() {
  return { from: $('#rFrom').value, to: $('#rTo').value, type: $('#rType').value, label: $('#rLabel').value.trim() };
}

function previewRange() {
  clearTimeout(calTab.rangeTimer);
  calTab.rangeTimer = setTimeout(async () => {
    const body = rangeBody();
    const box = $('#rPreview'), btn = $('#rApply');
    $('#rError').hidden = true;
    calTab.plan = null;
    btn.disabled = true;
    btn.textContent = t('cs.apply_n', { n: 0 });
    if (!body.from || !body.to) { box.innerHTML = `<span class="muted small">${esc(t('cs.range_pick'))}</span>`; return; }
    try {
      const plan = await api('/api/calendar/range/preview', { method: 'POST', body });
      if (JSON.stringify(rangeBody()) !== JSON.stringify(body)) return;   // respuesta antigua
      calTab.plan = { ...plan, body };
      const chips = [
        ['new', 'i-check', t(plan.count === 1 ? 'cs.will_one' : 'cs.will', { n: plan.count, type: typeName(body.type).toLowerCase() })],
        plan.skipped_nonworking ? ['dup', 'i-palm', t('cs.skip_nonworking', { n: plan.skipped_nonworking })] : null,
        plan.skipped_holiday.length ? ['dup', 'i-flag', t('cs.skip_holiday', { n: plan.skipped_holiday.length })] : null,
        plan.conflicts.length ? ['err', 'i-alert', t('cs.with_records', { n: plan.conflicts.length })] : null,
      ].filter(Boolean);
      box.innerHTML = chips.map(([k, ic, txt]) => `<span class="im-chip ${k}">${icon(ic)}${esc(txt)}</span>`).join('');
      btn.disabled = plan.count === 0;
      btn.textContent = t(plan.count === 1 ? 'cs.apply_one' : 'cs.apply_n', { n: plan.count });
    } catch (e) {
      box.innerHTML = '';
      showError($('#rError'), e.message);
    }
  }, 180);
}

async function applyRange() {
  const plan = calTab.plan;
  if (!plan?.count) return;
  const btn = $('#rApply');
  btn.classList.add('is-saving');
  try {
    const res = await sendMarks((apply) => api('/api/calendar/range', {
      method: 'POST', body: { ...plan.body, count: plan.count, apply },
    }), plan.body.type);
    if (res === null) return;
    $('#rFrom').value = '';
    $('#rTo').value = '';
    $('#rLabel').value = '';
    previewRange();
    await afterCalendarChange(t('cs.range_done', { n: res.marked }));
  } catch (e) {
    showError($('#rError'), e.message);
  } finally {
    btn.classList.remove('is-saving');
  }
}

/* --- importación --- */

async function previewHolidayImport(file) {
  const box = $('#hImportPreview');
  box.hidden = true;
  $('#csError').hidden = true;
  if (!file) return;
  if (file.size > 512 * 1024) { showError($('#csError'), t('cal.e.too_big')); return; }
  try {
    calTab.importText = await file.text();
    calTab.importName = file.name;
    const res = await api('/api/calendar/import/preview', { method: 'POST', body: { text: calTab.importText, filename: file.name } });
    const rows = res.items.slice(0, 8).map((it) => `<li>${icon(it.recurring ? 'i-rotate' : DAY_TYPE_ICONS[it.type])}
      <span>${esc(it.recurring ? t('cs.every_year', { date: mdLabel(it.key) }) : longDate(it.key, { day: 'numeric', month: 'short', year: 'numeric' }))}</span>
      <em>${esc(it.label || typeName(it.type))}</em></li>`).join('');
    const errs = res.errors.slice(0, 5).map((e) => `<li class="err">${icon('i-alert')}<span>${esc(t('cs.row', { n: e.row }))} · ${esc(e.value)}</span><em>${esc(e.message)}</em></li>`).join('');
    box.innerHTML = `<div class="im-summary">
        <span class="im-chip new">${icon('i-check')}${esc(t('cs.import_ok', { n: res.items.length }))}</span>
        ${res.errors.length ? `<span class="im-chip err">${icon('i-alert')}${esc(t('cs.import_err', { n: res.errors.length }))}</span>` : ''}</div>
      <ul class="mini-list">${rows}${res.items.length > 8 ? `<li class="muted">${esc(t('cf.more', { n: res.items.length - 8 }))}</li>` : ''}${errs}</ul>
      <div class="data-actions"><button type="button" class="ghost-btn small" data-import-cancel>${esc(t('imp.cancel'))}</button>
      <button type="button" class="primary-btn" data-import-go ${res.items.length ? '' : 'disabled'}>${esc(t('cs.import_go', { n: res.items.length }))}</button></div>`;
    box.hidden = false;
  } catch (e) {
    showError($('#csError'), e.message);
  } finally {
    $('#hImport').value = '';
  }
}

async function commitHolidayImport() {
  try {
    const res = await api('/api/calendar/import', { method: 'POST', body: { text: calTab.importText, filename: calTab.importName } });
    $('#hImportPreview').hidden = true;
    calTab.importText = null;
    await afterCalendarChange(t('cs.imported', { n: res.imported }));
  } catch (e) {
    showError($('#csError'), e.message);
  }
}

/* --- cómo computa cada tipo (se guarda con «Guardar ajustes») --- */

function fillDayTypes(s) {
  calTab.typesDraft = { ...s.day_types };
  $('#sDayTypes').innerHTML = DAY_TYPES.map((type) => `
    <div class="rule-row" data-type="${type}">
      <span class="rule-name">${typeIcon(type)}${esc(typeName(type))}</span>
      <div class="segmented" data-rule="${type}">
        <button type="button" data-value="none">${esc(t('rule.none'))}</button>
        <button type="button" data-value="target">${esc(t('rule.target'))}</button>
      </div>
    </div>`).join('');
  $('#sDayTypes').querySelectorAll('[data-rule]').forEach((seg) => setSegment(seg, calTab.typesDraft[seg.dataset.rule]));
}

function dayTypesDraft() {
  return calTab.typesDraft ? { ...calTab.typesDraft } : undefined;
}

/* ------------------------------------------------- diálogo «Tipo de día» */

const markDialog = $('#markDialog');
let marking = null;   // { date, current, recurring, registered }

async function openMark(date) {
  let c;
  try { c = await api(`/api/days/${date}`); } catch (e) { toast(e.message, 'err'); return; }
  marking = { date, current: c.day_recurring ? null : c.day_type, recurring: c.day_recurring, registered: c.registered && !!c.clock_in };
  $('#markSub').textContent = longDate(date, { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
  const chosen = c.day_type || 'holiday';
  $('#markTypes').innerHTML = DAY_TYPES.map((type) => `
    <button type="button" role="radio" class="type-btn" data-type="${type}" aria-checked="${type === chosen}">
      ${typeIcon(type)}<span>${esc(typeName(type))}</span></button>`).join('');
  $('#markTypes').dataset.value = chosen;
  $('#markLabel').value = c.day_label || '';
  $('#markRemove').hidden = !marking.current;
  $('#markError').hidden = true;
  updateMarkRule();
  if (!markDialog.open) markDialog.showModal();
}

function updateMarkRule() {
  const type = $('#markTypes').dataset.value;
  const mode = state.settings?.day_types?.[type] || 'none';
  let text = t(mode === 'none' ? 'mk.rule_none' : 'mk.rule_target', { type: typeName(type) });
  if (marking?.recurring) text += ' ' + t('mk.recurring_note');
  if (marking?.registered) text += ' ' + t('mk.has_records');
  $('#markRule').textContent = text;
}

async function saveMark(ev) {
  ev.preventDefault();
  if (!marking) return;
  const type = $('#markTypes').dataset.value;
  const label = $('#markLabel').value.trim();
  const btn = $('#markSave');
  btn.classList.add('is-saving');
  try {
    const res = await sendMarks((apply) => api(`/api/calendar/days/${marking.date}`, { method: 'PUT', body: { type, label, apply } }), type);
    if (res === null) return;
    closeDialog(markDialog);
    const date = marking.date;
    await afterCalendarChange(t('mk.saved', { type: typeName(type) }));
    flashDay(date);
  } catch (e) {
    showError($('#markError'), e.message);
  } finally {
    btn.classList.remove('is-saving');
  }
}

async function removeMark() {
  if (!marking?.current) return;
  try {
    await api(`/api/calendar/days/${marking.date}`, { method: 'DELETE' });
    closeDialog(markDialog);
    await afterCalendarChange(t('mk.removed'));
  } catch (e) {
    showError($('#markError'), e.message);
  }
}

/* --------------------------------------------- tarjeta «Próximos días libres» */

function renderUpcoming() {
  const list = $('#upList');
  const items = state.upcoming || [];
  const today = dateKey(nowMs());
  const html = items.length ? items.map((u) => {
    const days = Math.round((keyToDate(u.from) - keyToDate(today)) / 86400000);
    const when = days === 0 ? t('up.today') : days === 1 ? t('up.tomorrow') : t('up.in_days', { n: days });
    const range = u.from === u.to
      ? longDate(u.from, { weekday: 'short', day: 'numeric', month: 'short' })
      : `${longDate(u.from, { day: 'numeric', month: 'short' })} – ${longDate(u.to, { day: 'numeric', month: 'short' })}`;
    return `<li class="dt-${u.type}"><span class="up-icon">${typeIcon(u.type)}</span>
      <span class="up-main"><strong>${esc(u.label || typeName(u.type))}</strong><small class="muted">${esc(range)}${u.days > 1 ? ` · ${esc(t('up.n_days', { n: u.days }))}` : ''}</small></span>
      <span class="up-when ${days <= 7 ? 'soon' : ''}">${esc(when)}</span></li>`;
  }).join('') : `<li class="up-empty"><span class="muted small">${esc(t('up.empty'))}</span>
      <button type="button" class="ghost-btn small" data-up-add>${icon('i-plus')}${esc(t('up.add'))}</button></li>`;
  if (list.dataset.html !== html) { list.innerHTML = html; list.dataset.html = html; }
}

/* ------------------------------------------------------------ eventos */

$('#hAdd').addEventListener('click', saveHoliday);
$('#hLabel').addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); saveHoliday(); } });
$('#hList').addEventListener('click', (e) => {
  const row = e.target.closest('li[data-key]');
  if (!row) return;
  const recurring = row.dataset.recurring === 'true';
  if (e.target.closest('[data-hdel]')) deleteHoliday(row.dataset.key, recurring);
  if (e.target.closest('[data-hedit]')) {
    const item = holidayItems().find((h) => h.key === row.dataset.key && h.recurring === recurring);
    calTab.editing = item;
    $('#hDate').value = recurring ? `${dateKey(nowMs()).slice(0, 4)}-${item.key}` : item.key;
    $('#hLabel').value = item.label;
    $('#hRecurring').checked = recurring;
    $('#hAddText').textContent = t('cs.update');
    $('#hLabel').focus();
  }
});
['#rFrom', '#rTo', '#rType', '#rLabel'].forEach((sel) => $(sel).addEventListener('input', previewRange));
$('#rApply').addEventListener('click', applyRange);
$('#hImport').addEventListener('change', (e) => previewHolidayImport(e.target.files[0]));
$('#hImportPreview').addEventListener('click', (e) => {
  if (e.target.closest('[data-import-go]')) commitHolidayImport();
  if (e.target.closest('[data-import-cancel]')) { $('#hImportPreview').hidden = true; calTab.importText = null; }
});
$('#sDayTypes').addEventListener('click', (e) => {
  const b = e.target.closest('button[data-value]');
  const seg = b?.closest('[data-rule]');
  if (!seg) return;
  calTab.typesDraft[seg.dataset.rule] = b.dataset.value;
  setSegment(seg, b.dataset.value);
});

$('#markTypes').addEventListener('click', (e) => {
  const b = e.target.closest('[data-type]');
  if (!b) return;
  $('#markTypes').dataset.value = b.dataset.type;
  $('#markTypes').querySelectorAll('[data-type]').forEach((x) => x.setAttribute('aria-checked', String(x === b)));
  updateMarkRule();
});
$('#markForm').addEventListener('submit', saveMark);
$('#markRemove').addEventListener('click', removeMark);
$('#upManage').addEventListener('click', () => openSettings('calendar'));
$('#upList').addEventListener('click', (e) => { if (e.target.closest('[data-up-add]')) openSettings('calendar'); });

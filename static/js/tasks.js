/* ============================================================
   Jornada — tareas e imputación de horas (2.2)
   · Franja en el panel: tarea activa con su cronómetro, cambio en un clic.
   · Vista «Tareas»: tarjetas, día, semana y resumen para imputar.
   · Selector rápido (atajo configurable) y editor de tramos.
   El cronómetro se calcula con marcas de tiempo del servidor (como el fichaje):
   cerrar el navegador no lo altera. Nada sale del equipo.
   ============================================================ */
'use strict';

const TASK_COLORS = ['teal', 'blue', 'violet', 'coral', 'amber', 'green', 'pink', 'slate'];
const tk = {
  tasks: [], active: null, resume: null, projects: [], snapAt: 0, loaded: false,
  filter: 'open', search: '', tab: 'tasks', day: null, week: null, expanded: null,
  report: { from: null, to: null, group: 'day', format: 'hm', data: null },
  busy: false,
};

const taskById = (id) => tk.tasks.find((x) => x.id === id);
const taskName = (x) => (x ? (x.key ? `${x.key}${x.title ? ` · ${x.title}` : ''}` : x.title) : '—');
const taskLabel = (x) => (x?.key || x?.title || '—');
const numFmt = (opts) => new Intl.NumberFormat(currentLocale(), opts);

/** 5 h 30 min · 45 min · 2 h */
function hmin(sec) {
  const m = Math.round(Math.max(0, sec) / 60);
  const h = Math.floor(m / 60), r = m % 60;
  if (h && r) return `${h} h ${r} min`;
  return h ? `${h} h` : `${r} min`;
}
const decimalH = (sec) => `${numFmt({ minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(Math.round(sec / 36) / 100)} h`;
const fmtTime = (sec, format = tk.report.format) => (format === 'decimal' ? decimalH(sec) : hmin(sec));
const pct = (v) => `${numFmt({ maximumFractionDigits: 2 }).format(v)} %`;

/* ------------------------------------------------------------ datos */

function applyTasks(data) {
  tk.tasks = data.tasks;
  tk.active = data.active;
  tk.resume = data.resume_task_id;
  tk.projects = data.projects;
  tk.snapAt = data.server_ms;
  tk.loaded = true;
  renderStrip();
  if (tasksDialog.open) renderTasksTab();
}

async function loadTasks() {
  applyTasks(await api('/api/tasks'));
}

/** Segundos del tramo activo y total de su tarea, calculados en vivo desde las marcas. */
function activeLive() {
  if (!tk.active) return null;
  const now = nowMs();
  return {
    session: Math.max(0, (now - Date.parse(tk.active.start)) / 1000),
    total: tk.active.task_s + Math.max(0, (now - tk.snapAt) / 1000),
  };
}

function liveTotal(task) {
  if (tk.active && tk.active.task_id === task.id) return activeLive().total;
  return task.total_s;
}

/* ------------------------------------------------------------ acciones */

/** Pregunta con varias opciones. Devuelve el `value` del botón elegido o 'cancel'. */
function choiceDialog({ title, text, buttons }) {
  const dlg = $('#choiceDialog');
  $('#choiceTitle').textContent = title;
  $('#choiceText').textContent = text;
  $('#choiceButtons').innerHTML = `<button value="cancel" class="ghost-btn">${esc(t('common.cancel'))}</button><span class="spacer"></span>`
    + buttons.map(([value, label, primary]) => `<button value="${value}" class="${primary ? 'primary-btn' : 'ghost-btn'}">${esc(label)}</button>`).join('');
  dlg.returnValue = '';
  dlg.showModal();
  return new Promise((resolve) => dlg.addEventListener('close', () => resolve(dlg.returnValue || 'cancel'), { once: true }));
}

async function startTask(id, day) {
  if (tk.busy) return;
  tk.busy = true;
  const task = taskById(id);
  try {
    const res = await api(`/api/tasks/${id}/start`, {
      method: 'POST', body: { expect_active: tk.active?.entry_id ?? null, ...(day ? { day } : {}) },
    });
    applyTasks(res);
    toast(t('ts.now', { task: taskLabel(task) }), 'ok', 2600);
    syncSend('tasks');
    if (res.day_changed) await refreshAll();
  } catch (e) {
    tk.busy = false;
    if (e.status === 409 && e.data?.code === 'task.no_day') {
      const buttons = [['ignore', t('ts.only_task'), !e.data.can_start]];
      if (e.data.can_start) buttons.push(['start', t('ts.start_both'), true]);
      const choice = await choiceDialog({ title: t('ts.q_no_day_title'), text: t('ts.q_no_day'), buttons });
      if (choice !== 'cancel') return startTask(id, choice);
      return;
    }
    if (e.status === 409 && e.data?.code === 'task.on_break') {
      const choice = await choiceDialog({ title: t('ts.q_break_title'), text: t('ts.q_break'), buttons: [['end_break', t('ts.end_break_go'), true]] });
      if (choice !== 'cancel') return startTask(id, choice);
      return;
    }
    toast(e.message, e.status === 409 ? 'warn' : 'err');
    await loadTasks().catch(() => {});
  } finally {
    tk.busy = false;
  }
}

async function pauseTask() {
  if (!tk.active) return;
  try {
    applyTasks(await api('/api/tasks/pause', { method: 'POST', body: {} }));
    toast(t('ts.paused'), 'info', 2400);
    syncSend('tasks');
  } catch (e) { toast(e.message, 'err'); }
}

async function quickAdd(id, minutes, date = dateKey(nowMs())) {
  try {
    applyTasks(await api('/api/entries', { method: 'POST', body: { task_id: id, date, minutes } }));
    toast(t('ts.added', { dur: hmin(minutes * 60), task: taskLabel(taskById(id)) }), 'ok', 2600);
    syncSend('tasks');
    refreshTaskViews();
  } catch (e) { toast(e.message, 'err'); }
}

async function setTaskStatus(id, status) {
  try {
    applyTasks(await api(`/api/tasks/${id}`, { method: 'PUT', body: { status } }));
    toast(t(status === 'done' ? 'tk.completed' : 'tk.reopened'), 'ok', 2400);
    syncSend('tasks');
  } catch (e) { toast(e.message, 'err'); }
}

async function toggleFavorite(id) {
  const task = taskById(id);
  try { applyTasks(await api(`/api/tasks/${id}`, { method: 'PUT', body: { favorite: !task.favorite } })); } catch (e) { toast(e.message, 'err'); }
}

/* --------------------------------------------- franja del panel principal */

function recentTasks(n = 3) {
  return tk.tasks.filter((x) => x.status !== 'done' && !(tk.active && tk.active.task_id === x.id))
    .sort((a, b) => (b.favorite - a.favorite) || ((b.last_used ? Date.parse(b.last_used) : 0) - (a.last_used ? Date.parse(a.last_used) : 0)))
    .slice(0, n);
}

/** Imputado hoy (en vivo) frente al trabajo efectivo del fichaje. */
function todayImputed() {
  let sec = tk.tasks.reduce((sum, x) => sum + x.today_s, 0);
  if (tk.active) sec += Math.max(0, (nowMs() - tk.snapAt) / 1000);
  return sec;
}

function renderStrip() {
  const box = $('#taskStrip');
  if (!tk.loaded) return;
  const d = state.today;
  const chip = (x) => `<button type="button" class="ts-chip" data-start="${x.id}" title="${esc(t('ts.start_x', { task: taskName(x) }))}">
      <i class="tc-dot" data-color="${x.color}"></i><span>${esc(taskLabel(x))}</span>${icon('i-play')}</button>`;
  let html;
  if (tk.active) {
    const task = taskById(tk.active.task_id) || tk.active;
    const est = task.estimate_s;
    html = `<div class="ts-main">
        <span class="ts-pulse" data-color="${task.color}" aria-hidden="true"></span>
        <div class="ts-text"><span class="ts-label">${esc(t('ts.working_on'))}</span>
          <strong class="ts-name"><span class="ts-key">${esc(task.key || '')}</span>${task.key && task.title ? ' · ' : ''}${esc(task.title || '')}</strong></div>
        <span class="ts-timer tabular" data-ts="session">00:00:00</span>
      </div>
      <div class="ts-meta">
        ${est ? `<div class="ts-progress" title="${esc(t('ts.of_estimate'))}"><span data-ts="bar" data-color="${task.color}"></span></div>` : ''}
        <span class="small tabular" data-ts="total"></span>
        <span class="small muted tabular" data-ts="today"></span>
      </div>
      <div class="ts-actions">
        <button type="button" class="ghost-btn small" data-open-picker>${icon('i-switch')}<span>${esc(t('ts.switch'))}</span></button>
        <button type="button" class="ghost-btn small" data-pause>${icon('i-pause')}<span>${esc(t('ts.pause'))}</span></button>
        <button type="button" class="icon-btn small" data-open-tasks title="${esc(t('tk.open'))}" aria-label="${esc(t('tk.open'))}">${icon('i-ticket')}</button>
      </div>`;
  } else if (tk.resume && taskById(tk.resume)) {
    const task = taskById(tk.resume);
    const onBreak = d?.status === 'on_break';
    html = `<div class="ts-main"><span class="ts-icon">${icon(onBreak ? 'i-coffee' : 'i-rotate')}</span>
        <div class="ts-text"><span class="ts-label">${esc(t(onBreak ? 'ts.paused_for_break' : 'ts.back'))}</span>
        <strong class="ts-name">${esc(taskName(task))}</strong></div></div>
      <div class="ts-actions">
        ${onBreak ? '' : `<button type="button" class="primary-btn small" data-start="${task.id}">${icon('i-play')}<span>${esc(t('ts.continue'))}</span></button>`}
        <button type="button" class="ghost-btn small" data-open-picker>${icon('i-switch')}<span>${esc(t('ts.other'))}</span></button>
        <button type="button" class="icon-btn small" data-dismiss title="${esc(t('common.close'))}" aria-label="${esc(t('common.close'))}">${icon('i-x')}</button>
      </div>`;
  } else {
    const recent = recentTasks();
    html = `<div class="ts-main"><span class="ts-icon">${icon('i-ticket')}</span>
        <div class="ts-text"><span class="ts-label">${esc(t('ts.none'))}</span>
        <span class="small muted" data-ts="today"></span></div></div>
      <div class="ts-actions ts-recent">${recent.map(chip).join('')}
        <button type="button" class="ghost-btn small" data-open-picker>${icon('i-search')}<span>${esc(t(tk.tasks.length ? 'ts.pick' : 'ts.first'))}</span></button>
        <button type="button" class="icon-btn small" data-open-tasks title="${esc(t('tk.open'))}" aria-label="${esc(t('tk.open'))}">${icon('i-ticket')}</button></div>`;
  }
  const mode = tk.active ? 'active' : tk.resume ? 'resume' : 'idle';
  if (box.dataset.html !== html) { box.innerHTML = html; box.dataset.html = html; }
  box.dataset.mode = mode;
  renderTaskLive();
}

/** Llamada en cada tick: cronómetro de la tarea activa y reparto de hoy. */
function renderTaskLive() {
  if (!tk.loaded) return;
  const live = activeLive();
  const set = (sel, text) => { const el = $(sel); if (el && el.textContent !== text) el.textContent = text; };
  if (live) {
    const task = taskById(tk.active.task_id) || {};
    set('[data-ts="session"]', hms(live.session));
    set('[data-ts="total"]', task.estimate_s
      ? t('ts.total_est', { done: hmin(live.total), est: hmin(task.estimate_s) })
      : t('ts.total', { done: hmin(live.total) }));
    const bar = $('[data-ts="bar"]');
    if (bar && task.estimate_s) {
      bar.style.transform = `scaleX(${Math.min(1, live.total / task.estimate_s)})`;
      bar.classList.toggle('over', live.total > task.estimate_s);
    }
    const card = $(`.tk-card[data-id="${task.id}"] [data-live]`);
    if (card) card.textContent = hms(live.session);
  }
  const el = $('[data-ts="today"]');
  if (el && state.today) {
    const imputed = todayImputed();
    const worked = state.today.clock_in ? live_worked() : 0;
    const gap = worked - imputed;
    const text = !worked && !imputed ? '' : gap >= 60 ? t('ts.today_gap', { imp: hmin(imputed), gap: hmin(gap) })
      : gap <= -60 ? t('ts.today_over', { imp: hmin(imputed), over: hmin(-gap) }) : t('ts.today_ok', { imp: hmin(imputed) });
    if (el.textContent !== text) el.textContent = text;
  }
}

function live_worked() {
  try { return live().worked; } catch (e) { return state.today?.worked_s || 0; }
}

$('#taskStrip').addEventListener('click', async (e) => {
  const start = e.target.closest('[data-start]');
  if (start) return startTask(start.dataset.start);
  if (e.target.closest('[data-pause]')) return pauseTask();
  if (e.target.closest('[data-open-picker]')) return openPicker();
  if (e.target.closest('[data-open-tasks]')) return openTasks();
  if (e.target.closest('[data-dismiss]')) {
    tk.resume = null;
    renderStrip();
    api('/api/tasks/resume/dismiss', { method: 'POST', body: {} }).catch(() => {});
  }
});

/* ---------------------------------------------------- vista «Tareas» */

const tasksDialog = $('#tasksDialog');

async function openTasks(tab = tk.tab) {
  const today = dateKey(nowMs());
  tk.day = tk.day || today;
  tk.week = tk.week || today;
  if (!tk.report.from) { tk.report.from = addDays(today, -weekdayOf(today)); tk.report.to = today; }
  tk.report.format = state.settings?.tasks?.decimal ? 'decimal' : 'hm';
  if (!tasksDialog.open) tasksDialog.showModal();
  await loadTasks().catch((e) => toast(e.message, 'err'));
  selectTasksTab(tab);
}

function selectTasksTab(name) {
  tk.tab = name;
  const tabs = [...document.querySelectorAll('#tkTabs [role="tab"]')];
  tabs.forEach((b) => { const on = b.dataset.tab === name; b.setAttribute('aria-selected', String(on)); b.tabIndex = on ? 0 : -1; });
  document.querySelectorAll('#tasksDialog .tab-panel').forEach((p) => { p.hidden = p.dataset.panel !== name; });
  const active = tabs.find((b) => b.dataset.tab === name), ind = $('#tkTabs .tab-indicator');
  if (active && ind) { ind.style.width = `${active.offsetWidth}px`; ind.style.transform = `translateX(${active.offsetLeft}px)`; }
  renderTasksTab();
}

function renderTasksTab() {
  if (tk.tab === 'tasks') renderGrid();
  else if (tk.tab === 'day') loadDay();
  else if (tk.tab === 'week') loadWeek();
  else if (tk.tab === 'report') loadReport();
}

function refreshTaskViews() {
  if (tasksDialog.open && tk.tab !== 'tasks') renderTasksTab();
}

function statusLabel(s) { return t(`tk.s_${s}`); }

function progressHtml(x, total) {
  if (!x.estimate_s) return `<div class="tk-figs"><b class="tabular">${hmin(total)}</b><span class="muted">${esc(t('tk.no_estimate'))}</span></div>`;
  const over = total > x.estimate_s;
  const ratio = total / x.estimate_s;
  return `<div class="tk-bar ${over ? 'over' : ''}" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.round(ratio * 100)}"
      aria-label="${esc(t('tk.progress'))}"><span data-color="${x.color}" style="transform:scaleX(${Math.min(1, ratio)})"></span>${over ? `<i style="width:${Math.min(100, (ratio - 1) / ratio * 100)}%"></i>` : ''}</div>
    <div class="tk-figs"><b class="tabular">${hmin(total)}</b><span class="muted">/ ${hmin(x.estimate_s)}</span>
      <span class="tk-pct tabular ${over ? 'neg' : ''}">${pct(ratio * 100)}</span></div>
    <div class="tk-remain small ${over ? 'neg' : 'muted'}">${over ? esc(t('tk.over', { dur: hmin(total - x.estimate_s) })) : esc(t('tk.remaining', { dur: hmin(x.estimate_s - total) }))}</div>`;
}

function filteredTasks() {
  const q = tk.search.trim().toLowerCase();
  return tk.tasks.filter((x) => {
    if (tk.filter === 'open' && x.status === 'done') return false;
    if (tk.filter === 'fav' && !x.favorite) return false;
    if (tk.filter === 'done' && x.status !== 'done') return false;
    return !q || [x.key, x.title, x.project].some((v) => (v || '').toLowerCase().includes(q));
  });
}

function renderGrid() {
  const list = filteredTasks();
  if (!tk.tasks.length) {
    $('#tkGrid').innerHTML = `<div class="empty-state wide">${icon('i-ticket')}<span>${esc(t('tk.empty'))}</span>
      <button type="button" class="primary-btn" data-new>${icon('i-plus')}${esc(t('tk.new'))}</button></div>`;
    return;
  }
  if (!list.length) { $('#tkGrid').innerHTML = `<div class="empty-state wide">${icon('i-search')}<span>${esc(t('tk.no_match'))}</span></div>`; return; }
  $('#tkGrid').innerHTML = list.map((x) => {
    const isActive = tk.active?.task_id === x.id;
    const total = liveTotal(x);
    return `<article class="tk-card ${isActive ? 'active' : ''} ${x.status === 'done' ? 'done' : ''}" data-id="${x.id}">
      <header class="tk-head">
        <i class="tc-dot" data-color="${x.color}"></i>
        <span class="tk-key">${esc(x.key || t('tk.internal'))}</span>
        <span class="tk-status s-${x.status}">${esc(statusLabel(x.status))}</span>
        <span class="tk-tools">
          <button type="button" class="icon-btn small" data-sessions aria-expanded="${tk.expanded === x.id}" title="${esc(t('tk.sessions', { n: x.sessions }))}" aria-label="${esc(t('tk.sessions', { n: x.sessions }))}">${icon('i-list')}</button>
          ${x.status !== 'done' ? `<button type="button" class="icon-btn small" data-complete title="${esc(t('tk.complete'))}" aria-label="${esc(t('tk.complete'))}">${icon('i-check')}</button>` : ''}
          <button type="button" class="icon-btn small" data-edit-task title="${esc(t('common.edit'))}" aria-label="${esc(t('common.edit'))}">${icon('i-edit')}</button>
          <button type="button" class="icon-btn small tk-fav ${x.favorite ? 'on' : ''}" data-fav aria-pressed="${x.favorite}" title="${esc(t('tk.favorite'))}" aria-label="${esc(t('tk.favorite'))}">${icon('i-star')}</button>
        </span>
      </header>
      <h4 class="tk-title">${esc(x.title || x.key)}</h4>
      ${x.project ? `<span class="tk-project">${esc(x.project)}</span>` : ''}
      ${progressHtml(x, total)}
      <footer class="tk-foot">
        ${isActive
          ? `<button type="button" class="primary-btn small tk-running" data-pause>${icon('i-pause')}<span class="tabular" data-live>00:00:00</span></button>`
          : x.status === 'done'
            ? `<button type="button" class="ghost-btn small" data-reopen>${icon('i-rotate')}<span>${esc(t('tk.reopen'))}</span></button>`
            : `<button type="button" class="primary-btn small" data-start>${icon('i-play')}<span>${esc(t(tk.active ? 'ts.switch' : 'tk.start'))}</span></button>`}
        <span class="tk-quick" role="group" aria-label="${esc(t('tk.quick_add'))}">
          <button type="button" class="chip-btn" data-add="15" title="${esc(t('tk.add_today', { dur: '15 min' }))}">+15</button>
          <button type="button" class="chip-btn" data-add="30" title="${esc(t('tk.add_today', { dur: '30 min' }))}">+30</button>
          <button type="button" class="chip-btn" data-add="60" title="${esc(t('tk.add_today', { dur: '1 h' }))}">+1 h</button>
        </span>
      </footer>
      ${tk.expanded === x.id ? '<div class="tk-sessions" data-sessions-box><div class="skeleton" style="height:40px"></div></div>' : ''}
    </article>`;
  }).join('');
  if (tk.expanded) loadSessions(tk.expanded);
}

async function loadSessions(id) {
  const box = $(`.tk-card[data-id="${id}"] [data-sessions-box]`);
  if (!box) return;
  try {
    const { entries } = await api(`/api/tasks/${id}/entries`);
    box.innerHTML = entries.length ? `<ul class="entry-list compact">${entries.map(entryRow).join('')}</ul>`
      : `<p class="muted small">${esc(t('tk.no_sessions'))}</p>`;
  } catch (e) { box.textContent = e.message; }
}

function entryRow(v, { showTask = false } = {}) {
  const when = v.start ? `${v.local_start}–${v.active ? '…' : v.local_end}` : t('en.no_time');
  return `<li class="entry ${v.active ? 'is-active' : ''}" data-entry="${v.id}">
    <i class="tc-dot" data-color="${v.color}"></i>
    <span class="en-when tabular">${showTask ? '' : `<b>${esc(longDate(v.date, { day: 'numeric', month: 'short' }))}</b> `}${esc(when)}</span>
    ${showTask ? `<span class="en-task"><b>${esc(v.key || v.title)}</b>${v.key && v.title ? ` <span class="muted">${esc(v.title)}</span>` : ''}</span>` : `<span class="en-task muted">${esc(v.note || '')}</span>`}
    <span class="en-tags">${v.source === 'manual' ? `<span class="tag">${esc(t('en.manual'))}</span>` : ''}${v.booked ? `<span class="tag ok">${icon('i-check')}${esc(t('en.booked'))}</span>` : ''}${v.active ? `<span class="tag live">${esc(t('en.running'))}</span>` : ''}</span>
    <span class="en-dur tabular">${hmin(v.seconds)}</span>
    <button type="button" class="icon-btn small" data-edit-entry="${v.id}" title="${esc(t('common.edit'))}" aria-label="${esc(t('common.edit'))}">${icon('i-edit')}</button>
  </li>`;
}

$('#tkGrid').addEventListener('click', (e) => {
  if (e.target.closest('[data-new]')) return openTaskEditor();
  const editEntry = e.target.closest('[data-edit-entry]');
  if (editEntry) return openEntry({ id: editEntry.dataset.editEntry });
  const card = e.target.closest('.tk-card');
  if (!card) return;
  const id = card.dataset.id;
  if (e.target.closest('[data-start]')) startTask(id);
  else if (e.target.closest('[data-pause]')) pauseTask();
  else if (e.target.closest('[data-reopen]')) setTaskStatus(id, 'paused');
  else if (e.target.closest('[data-complete]')) completeTask(id);
  else if (e.target.closest('[data-fav]')) toggleFavorite(id);
  else if (e.target.closest('[data-edit-task]')) openTaskEditor(id);
  else if (e.target.closest('[data-add]')) quickAdd(id, Number(e.target.closest('[data-add]').dataset.add));
  else if (e.target.closest('[data-sessions]')) { tk.expanded = tk.expanded === id ? null : id; renderGrid(); }
});

async function completeTask(id) {
  const x = taskById(id);
  if (tk.active?.task_id === id) {
    const ok = await confirmDialog({ title: t('tk.complete_title'), text: t('tk.complete_running', { task: taskLabel(x) }), ok: t('tk.complete') });
    if (!ok) return;
  }
  setTaskStatus(id, 'done');
}

$('#tkSearch').addEventListener('input', (e) => { tk.search = e.target.value; renderGrid(); });
$('#tkFilter').addEventListener('click', (e) => { const b = e.target.closest('[data-value]'); if (b) { tk.filter = b.dataset.value; renderGrid(); } });
$('#tkNew').addEventListener('click', () => openTaskEditor());
$('#tkTabs').addEventListener('click', (e) => { const b = e.target.closest('[role="tab"]'); if (b) selectTasksTab(b.dataset.tab); });
$('#tkTabs').addEventListener('keydown', (e) => {
  if (!['ArrowLeft', 'ArrowRight'].includes(e.key)) return;
  const tabs = [...document.querySelectorAll('#tkTabs [role="tab"]')];
  const i = tabs.findIndex((b) => b.dataset.tab === tk.tab);
  const next = tabs[(i + (e.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length];
  e.preventDefault();
  selectTasksTab(next.dataset.tab);
  next.focus();
});
$('#tasksBtn').addEventListener('click', () => openTasks());

/* ------------------------------------------------------------ editor de tarea */

const taskDialog = $('#taskDialog');
let editingTask = null;

function openTaskEditor(id = null) {
  const x = id ? taskById(id) : null;
  editingTask = id;
  $('#taskDialogTitle').textContent = t(x ? 'tk.edit' : 'tk.new');
  $('#tfKey').value = x?.key || '';
  $('#tfTitle').value = x?.title || '';
  $('#tfProject').value = x?.project || '';
  $('#tfEstimate').value = x?.estimate_minutes ? minutesToHM(x.estimate_minutes) : '';
  $('#tfNotes').value = x?.notes || '';
  $('#tfFavorite').checked = !!x?.favorite;
  $('#tfProjects').innerHTML = tk.projects.map((p) => `<option value="${esc(p)}"></option>`).join('');
  const color = x?.color || TASK_COLORS[tk.tasks.length % TASK_COLORS.length];
  $('#tfColor').innerHTML = TASK_COLORS.map((c) => `<button type="button" role="radio" class="swatch" data-value="${c}" aria-checked="${c === color}" aria-label="${esc(t(`tc.${c}`))}" title="${esc(t(`tc.${c}`))}"><i class="tc-fill" data-color="${c}"></i></button>`).join('');
  $('#tfColor').dataset.value = color;
  setSegment($('#tfStatus'), x?.status || 'pending');
  $('#tfStatusWrap').hidden = !x;
  $('#tfDelete').hidden = !x;
  $('#tfError').hidden = true;
  taskDialog.showModal();
  (x ? $('#tfTitle') : $('#tfKey')).focus();
}

async function saveTask(ev) {
  ev.preventDefault();
  const est = $('#tfEstimate').value.trim();
  const minutes = est ? hmToMinutes(est) : null;
  if (est && minutes === null) { showError($('#tfError'), t('tk.estimate_fmt')); return; }
  const body = {
    key: $('#tfKey').value, title: $('#tfTitle').value, project: $('#tfProject').value,
    estimate_minutes: minutes, notes: $('#tfNotes').value, favorite: $('#tfFavorite').checked,
    color: $('#tfColor').dataset.value, ...(editingTask ? { status: $('#tfStatus').dataset.value } : {}),
  };
  try {
    const res = await api(editingTask ? `/api/tasks/${editingTask}` : '/api/tasks', { method: editingTask ? 'PUT' : 'POST', body });
    applyTasks(res);
    closeDialog(taskDialog);
    toast(t(editingTask ? 'tk.saved' : 'tk.created', { task: taskLabel(res.task) }), 'ok');
    syncSend('tasks');
    if (pickerDialog.open) renderPicker();
  } catch (e) { showError($('#tfError'), e.message); }
}

async function deleteTask() {
  const x = taskById(editingTask);
  const ok = await confirmDialog({
    title: t('tk.delete_title'),
    text: x.sessions ? t('tk.delete_with', { task: taskLabel(x), n: x.sessions }) : t('tk.delete_text', { task: taskLabel(x) }),
    ok: t('common.delete'), danger: true,
  });
  if (!ok) return;
  try {
    applyTasks(await api(`/api/tasks/${editingTask}`, { method: 'DELETE', body: { confirm: true } }));
    closeDialog(taskDialog);
    toast(t('tk.deleted'), 'ok');
    syncSend('tasks');
  } catch (e) { showError($('#tfError'), e.message); }
}

$('#taskForm').addEventListener('submit', saveTask);
$('#tfDelete').addEventListener('click', deleteTask);
$('#tfColor').addEventListener('click', (e) => {
  const b = e.target.closest('[data-value]');
  if (!b) return;
  $('#tfColor').dataset.value = b.dataset.value;
  $('#tfColor').querySelectorAll('[data-value]').forEach((s) => s.setAttribute('aria-checked', String(s === b)));
});
$('#tfStatus').addEventListener('click', (e) => { const b = e.target.closest('[data-value]'); if (b) setSegment($('#tfStatus'), b.dataset.value); });

/* ------------------------------------------------------------ selector rápido */

const pickerDialog = $('#pickerDialog');
let pickIndex = 0;

function openPicker() {
  if (!pickerDialog.open) pickerDialog.showModal();
  $('#pkSearch').value = '';
  pickIndex = 0;
  renderPicker();
  $('#pkSearch').focus();
  loadTasks().then(renderPicker).catch(() => {});
}

function pickerItems() {
  const q = $('#pkSearch').value.trim().toLowerCase();
  const open = tk.tasks.filter((x) => x.status !== 'done' || tk.active?.task_id === x.id);
  const match = (x) => !q || [x.key, x.title, x.project].some((v) => (v || '').toLowerCase().includes(q));
  const byRecent = (a, b) => (b.last_used ? Date.parse(b.last_used) : 0) - (a.last_used ? Date.parse(a.last_used) : 0);
  const list = open.filter(match).sort((a, b) => (tk.active?.task_id === b.id) - (tk.active?.task_id === a.id)
    || (b.favorite - a.favorite) || byRecent(a, b));
  const items = [];
  if (tk.active && !q) items.push({ kind: 'pause' });
  list.forEach((x) => items.push({ kind: 'task', task: x }));
  if (q && !list.length) items.push({ kind: 'create', q: $('#pkSearch').value.trim() });
  return items;
}

function renderPicker() {
  const items = pickerItems();
  pickIndex = Math.min(pickIndex, Math.max(0, items.length - 1));
  $('#pkList').innerHTML = items.map((it, i) => {
    const sel = i === pickIndex ? 'aria-selected="true" class="sel"' : 'aria-selected="false"';
    if (it.kind === 'pause') return `<li role="option" ${sel} data-i="${i}">${icon('i-pause')}<span class="pk-main"><strong>${esc(t('pk.pause'))}</strong></span><kbd>P</kbd></li>`;
    if (it.kind === 'create') return `<li role="option" ${sel} data-i="${i}">${icon('i-plus')}<span class="pk-main"><strong>${esc(t('pk.create', { q: it.q }))}</strong></span></li>`;
    const x = it.task, isActive = tk.active?.task_id === x.id;
    const total = liveTotal(x);
    return `<li role="option" ${sel} data-i="${i}" class="${i === pickIndex ? 'sel' : ''} ${isActive ? 'is-active' : ''}">
      <i class="tc-dot" data-color="${x.color}"></i>
      <span class="pk-main"><strong>${esc(x.key || x.title)}</strong>${x.key && x.title ? `<span class="muted">${esc(x.title)}</span>` : ''}</span>
      ${x.favorite ? `<span class="pk-fav">${icon('i-star')}</span>` : ''}
      <span class="pk-time tabular muted">${isActive ? esc(t('en.running')) : x.estimate_s ? `${hmin(total)} / ${hmin(x.estimate_s)}` : hmin(total)}</span></li>`;
  }).join('');
  $('#pkList').querySelector('.sel')?.scrollIntoView({ block: 'nearest' });
}

function choosePick(i = pickIndex) {
  const it = pickerItems()[i];
  if (!it) return;
  closeDialog(pickerDialog);
  if (it.kind === 'pause') pauseTask();
  else if (it.kind === 'create') {
    openTaskEditor();
    const looksKey = /^[A-Za-z][A-Za-z0-9_]*-\d+$/.test(it.q);
    $(looksKey ? '#tfKey' : '#tfTitle').value = it.q;
  } else if (tk.active?.task_id !== it.task.id) startTask(it.task.id);
}

$('#pkSearch').addEventListener('input', () => { pickIndex = 0; renderPicker(); });
$('#pkSearch').addEventListener('keydown', (e) => {
  const n = pickerItems().length;
  if (e.key === 'ArrowDown') { e.preventDefault(); pickIndex = (pickIndex + 1) % Math.max(1, n); renderPicker(); }
  else if (e.key === 'ArrowUp') { e.preventDefault(); pickIndex = (pickIndex - 1 + n) % Math.max(1, n); renderPicker(); }
  else if (e.key === 'Enter') { e.preventDefault(); choosePick(); }
  else if ((e.key === 'p' || e.key === 'P') && !e.target.value && tk.active) { e.preventDefault(); choosePick(0); }
});
$('#pkList').addEventListener('click', (e) => { const li = e.target.closest('[data-i]'); if (li) choosePick(Number(li.dataset.i)); });
$('#pkNew').addEventListener('click', () => { closeDialog(pickerDialog); openTaskEditor(); });
pickerDialog.addEventListener('click', (e) => { if (e.target === pickerDialog) closeDialog(pickerDialog); });

/* ------------------------------------------------------------ editor de tramos */

const entryDialog = $('#entryDialog');
let editingEntry = null;   // tramo existente, o null para uno manual nuevo

function taskOptions(selected, { includeDone = false } = {}) {
  return tk.tasks.filter((x) => includeDone || x.status !== 'done' || x.id === selected)
    .map((x) => `<option value="${x.id}" ${x.id === selected ? 'selected' : ''}>${esc(taskName(x))}</option>`).join('');
}

function setEntryKind(kind) {
  setSegment($('#efKind'), kind);
  $('#efDurationBox').hidden = kind !== 'duration';
  $('#efRangeBox').hidden = kind !== 'range';
  $('#efSplitAtWrap').hidden = kind !== 'range';
  $('#efSplitMinWrap').hidden = kind !== 'duration';
  updateSplitPreview();
}

async function openEntry({ id = null, date = null, task = null } = {}) {
  let v = null;
  if (id) {
    try { v = (await api(`/api/entries/${id}`)).entry; } catch (e) { toast(e.message, 'err'); return; }
  }
  if (!tk.tasks.length) { toast(t('en.need_task'), 'info'); openTaskEditor(); return; }
  editingEntry = v;
  $('#entryTitle').textContent = t(v ? (v.active ? 'en.edit_active' : 'en.edit') : 'en.add');
  $('#entrySub').textContent = v ? `${taskName(taskById(v.task_id))}` : t('en.add_sub');
  $('#efTask').innerHTML = taskOptions(v?.task_id || task || tk.active?.task_id || recentTasks(1)[0]?.id || tk.tasks[0].id, { includeDone: !!v });
  $('#efSplitTask').innerHTML = taskOptions(v?.task_id || '');
  $('#efDate').value = v?.date || date || tk.day || dateKey(nowMs());
  $('#efDate').max = dateKey(nowMs());
  $('#efStart').value = v?.local_start || '';
  $('#efEnd').value = v?.local_end || '';
  $('#efMinutes').value = v && !v.start ? minutesToHM(Math.round(v.seconds / 60)) : '';
  $('#efNote').value = v?.note || '';
  $('#efBooked').checked = !!v?.booked;
  $('#efBookedRow').hidden = !v || v.active;
  $('#efDelete').hidden = !v;
  $('#efSplit').hidden = !v || v.active;
  $('#efSplitAt').value = '';
  $('#efSplitFirst').value = '';
  $('#efSource').textContent = v ? t(v.source === 'manual' ? 'en.src_manual' : 'en.src_timer') : t('en.src_new');
  $('#efEnd').disabled = !!v?.active;
  $('#efDate').disabled = !!v?.active;
  $('#efKind').querySelector('[data-value="duration"]').disabled = !!v?.active;
  setEntryKind(v ? (v.start ? 'range' : 'duration') : 'duration');
  $('#efError').hidden = true;
  if (!entryDialog.open) entryDialog.showModal();
}

function updateSplitPreview() {
  const v = editingEntry;
  const out = $('#efSplitPreview');
  if (!v || $('#efSplit').hidden) { out.textContent = ''; return; }
  let first = null;
  if (v.start) {
    const at = $('#efSplitAt').value;
    if (at && v.local_start) {
      const toS = (hhmm) => { const [h, m] = hhmm.split(':').map(Number); return h * 3600 + m * 60; };
      let diff = toS(at) - toS(v.local_start);
      if (diff < 0) diff += 86400;
      first = diff;
    }
  } else {
    const m = hmToMinutes($('#efSplitFirst').value);
    first = m === null ? null : m * 60;
  }
  out.textContent = first === null ? t('en.split_hint')
    : first <= 0 || first >= v.seconds ? t('task.e.split_range')
      : t('en.split_preview', { a: hmin(first), b: hmin(v.seconds - first), total: hmin(v.seconds) });
}

async function saveEntry(ev) {
  ev.preventDefault();
  const kind = $('#efKind').dataset.value;
  const body = { task_id: $('#efTask').value, note: $('#efNote').value, date: $('#efDate').value };
  if (kind === 'duration') {
    const m = hmToMinutes($('#efMinutes').value);
    if (!m) { showError($('#efError'), t('en.duration_fmt')); return; }
    body.minutes = m;
  } else {
    body.start = $('#efStart').value;
    body.end = $('#efEnd').value;
    if (!body.start || (!body.end && !editingEntry?.active)) { showError($('#efError'), t('task.e.need_both')); return; }
    if (editingEntry?.active) { delete body.end; delete body.date; }
  }
  if (editingEntry) body.booked = $('#efBooked').checked;
  try {
    const res = editingEntry
      ? await api(`/api/entries/${editingEntry.id}`, { method: 'PUT', body })
      : await api('/api/entries', { method: 'POST', body });
    applyTasks(res);
    closeDialog(entryDialog);
    toast(t(editingEntry ? 'en.saved' : 'en.added'), 'ok');
    syncSend('tasks');
    refreshTaskViews();
  } catch (e) { showError($('#efError'), e.message); }
}

async function splitEntry() {
  const v = editingEntry;
  const body = { task_id: $('#efSplitTask').value };
  if (v.start) body.at = $('#efSplitAt').value;
  else body.first_minutes = hmToMinutes($('#efSplitFirst').value);
  if (!body.at && !body.first_minutes) { showError($('#efError'), t('en.split_hint')); return; }
  try {
    applyTasks(await api(`/api/entries/${v.id}/split`, { method: 'POST', body }));
    closeDialog(entryDialog);
    toast(t('en.split_done'), 'ok');
    syncSend('tasks');
    refreshTaskViews();
  } catch (e) { showError($('#efError'), e.message); }
}

async function deleteEntry() {
  const v = editingEntry;
  const ok = await confirmDialog({ title: t('en.delete_title'), text: t('en.delete_text', { dur: hmin(v.seconds), task: taskLabel(taskById(v.task_id)) }), ok: t('common.delete'), danger: true });
  if (!ok) return;
  try {
    applyTasks(await api(`/api/entries/${v.id}`, { method: 'DELETE', body: { confirm: true } }));
    closeDialog(entryDialog);
    toast(t('en.deleted'), 'ok');
    syncSend('tasks');
    refreshTaskViews();
  } catch (e) { showError($('#efError'), e.message); }
}

$('#entryForm').addEventListener('submit', saveEntry);
$('#efKind').addEventListener('click', (e) => { const b = e.target.closest('[data-value]'); if (b && !b.disabled) setEntryKind(b.dataset.value); });
$('#efQuick').addEventListener('click', (e) => { const b = e.target.closest('[data-min]'); if (b) $('#efMinutes').value = minutesToHM(Number(b.dataset.min)); });
$('#efSplitGo').addEventListener('click', splitEntry);
$('#efDelete').addEventListener('click', deleteEntry);
['#efSplitAt', '#efSplitFirst'].forEach((s) => $(s).addEventListener('input', updateSplitPreview));

/* ------------------------------------------------------------ vista diaria */

async function loadDay() {
  $('#tdDate').value = tk.day;
  $('#tdDate').max = dateKey(nowMs());
  $('#tdNext').disabled = tk.day >= dateKey(nowMs());
  let s;
  try { s = await api(`/api/tasks/day/${tk.day}`); } catch (e) { $('#tdBody').innerHTML = `<div class="form-error">${esc(e.message)}</div>`; return; }
  const tile = (label, value, cls = '', sub = '') => `<div class="avg-tile ${cls}"><span class="muted small">${esc(label)}</span><strong class="tabular">${value}</strong>${sub ? `<small class="muted">${esc(sub)}</small>` : ''}</div>`;
  const gapTile = s.over_s >= 60 ? tile(t('td.over'), `+${hmin(s.over_s)}`, 'neg')
    : tile(t('td.unassigned'), hmin(s.unassigned_s), s.unassigned_s >= 60 ? 'pend' : 'pos', s.unassigned_s < 60 && s.worked_s ? t('td.all_assigned') : '');
  const issues = s.issues.map((i) => {
    const e = s.entries.find((x) => x.id === i.entry_id);
    const what = e ? `${e.key || e.title} ${e.local_start || ''}–${e.local_end || '…'}` : '';
    return `<div class="alert warn">${icon('i-alert')}<span>${t(`td.i_${i.type}`, { dur: hmin(i.seconds || 0), what: esc(what) })}</span></div>`;
  }).join('');
  const canTrim = s.issues.some((i) => i.type === 'outside_work');
  $('#tdBody').innerHTML = `
    <div class="avg-grid four">${tile(t('td.worked'), s.worked_s ? hmin(s.worked_s) : '—')}${tile(t('td.imputed'), hmin(s.imputed_s))}${gapTile}
      ${tile(t('td.tasks_n'), String(s.tasks.length))}</div>
    ${issues ? `<div class="td-issues">${issues}${canTrim ? `<button type="button" class="ghost-btn small" data-trim>${icon('i-scissors')}${esc(t('td.trim'))}</button>` : ''}</div>` : ''}
    ${dayTimeline(s)}
    <div class="td-head"><h4>${esc(t('td.entries'))}</h4>
      <div class="td-add">${tk.tasks.length ? `<select id="tdQuickTask" aria-label="${esc(t('en.task'))}">${taskOptions(tk.active?.task_id || recentTasks(1)[0]?.id)}</select>
        <button type="button" class="chip-btn" data-qa="15">+15</button><button type="button" class="chip-btn" data-qa="30">+30</button><button type="button" class="chip-btn" data-qa="60">+1 h</button>` : ''}
        <button type="button" class="ghost-btn small" data-add-entry>${icon('i-plus')}${esc(t('en.add'))}</button></div></div>
    ${s.entries.length ? `<ul class="entry-list">${s.entries.map((v) => entryRow(v, { showTask: true })).join('')}</ul>`
      : `<div class="empty-state">${icon('i-clock')}<span>${esc(t('td.empty'))}</span></div>`}
    ${s.tasks.length ? `<div class="td-totals"><h4>${esc(t('td.by_task'))}</h4><ul class="share-list">${s.tasks.map((x) => shareRow(x.key || x.title, x.title && x.key ? x.title : '', x.seconds, s.imputed_s, x.color)).join('')}</ul></div>` : ''}`;
}

function shareRow(name, sub, sec, total, color = 'slate') {
  return `<li><i class="tc-dot" data-color="${color}"></i><span class="share-name"><b>${esc(name)}</b>${sub ? ` <span class="muted">${esc(sub)}</span>` : ''}</span>
    <span class="share-bar"><i data-color="${color}" style="transform:scaleX(${total ? Math.min(1, sec / total) : 0})"></i></span><b class="tabular">${hmin(sec)}</b></li>`;
}

/** Barra del día: trabajo efectivo según el fichaje (fondo) y tramos de tareas (color). */
function dayTimeline(s) {
  const spans = s.work_intervals.map(([a, b]) => [Date.parse(a), Date.parse(b)]);
  const items = s.entries.filter((v) => v.start).map((v) => [Date.parse(v.start), v.end ? Date.parse(v.end) : nowMs(), v.color, v]);
  const all = [...spans.flat(), ...items.flatMap((x) => [x[0], x[1]])];
  if (!all.length) return '';
  const lo = Math.min(...all), hi = Math.max(...all), span = Math.max(1, hi - lo);
  const pos = (a, b) => `left:${((a - lo) / span) * 100}%;width:${Math.max(0.4, ((b - a) / span) * 100)}%`;
  return `<div class="td-timeline" aria-hidden="true">
      <div class="tl-row work">${spans.map(([a, b]) => `<i style="${pos(a, b)}"></i>`).join('')}</div>
      <div class="tl-row tasks">${items.map(([a, b, c, v]) => `<i data-color="${c}" style="${pos(a, b)}" title="${esc(`${v.key || v.title} ${v.local_start}–${v.local_end || '…'}`)}"></i>`).join('')}</div>
      <div class="tl-scale small muted tabular"><span>${clock(lo)}</span><span>${esc(t('td.legend'))}</span><span>${clock(hi)}</span></div>
    </div>`;
}

async function trimDay() {
  const { plan } = await api(`/api/tasks/day/${tk.day}/trim`);
  if (!plan.length) { toast(t('td.nothing_to_trim'), 'info'); return; }
  const removed = plan.reduce((sum, p) => sum + p.before_s - p.after_s, 0);
  const ok = await confirmDialog({ title: t('td.trim_title'), text: t('td.trim_text', { n: plan.length, dur: hmin(removed) }), ok: t('td.trim_go') });
  if (!ok) return;
  try {
    await api(`/api/tasks/day/${tk.day}/trim`, { method: 'POST', body: { confirm: true, entry_ids: plan.map((p) => p.entry_id) } });
    toast(t('td.trimmed'), 'ok');
    await loadTasks();
    loadDay();
    syncSend('tasks');
  } catch (e) { toast(e.message, 'err'); }
}

$('#tdBody').addEventListener('click', (e) => {
  const ed = e.target.closest('[data-edit-entry]');
  if (ed) return openEntry({ id: ed.dataset.editEntry });
  if (e.target.closest('[data-add-entry]')) return openEntry({ date: tk.day });
  if (e.target.closest('[data-trim]')) return trimDay();
  const qa = e.target.closest('[data-qa]');
  if (qa) quickAdd($('#tdQuickTask').value, Number(qa.dataset.qa), tk.day);
});
$('#tdPrev').addEventListener('click', () => { tk.day = addDays(tk.day, -1); loadDay(); });
$('#tdNext').addEventListener('click', () => { tk.day = addDays(tk.day, 1); loadDay(); });
$('#tdToday').addEventListener('click', () => { tk.day = dateKey(nowMs()); loadDay(); });
$('#tdDate').addEventListener('change', (e) => { if (e.target.value) { tk.day = e.target.value; loadDay(); } });

/* ------------------------------------------------------------ vista semanal */

async function loadWeek() {
  let w;
  try { w = await api(`/api/tasks/week/${tk.week}`); } catch (e) { $('#twBody').innerHTML = `<div class="form-error">${esc(e.message)}</div>`; return; }
  $('#twRange').textContent = `${longDate(w.from, { day: 'numeric', month: 'short' })} – ${longDate(w.to, { day: 'numeric', month: 'short', year: 'numeric' })}`;
  const tile = (label, value, cls = '', sub = '') => `<div class="avg-tile ${cls}"><span class="muted small">${esc(label)}</span><strong class="tabular">${value}</strong>${sub ? `<small class="muted">${esc(sub)}</small>` : ''}</div>`;
  const goalTile = w.imputed_s >= w.goal_s ? tile(t('tw.goal_done'), `+${hmin(w.imputed_s - w.goal_s)}`, 'pos')
    : w.closed ? tile(t('tw.deficit'), `−${hmin(w.deficit_s)}`, 'neg') : tile(t('tw.pending'), hmin(w.remaining_s), 'pend', t('tw.not_deficit'));
  const diff = w.diff_worked_s;
  const maxS = Math.max(...w.days.map((d) => Math.max(d.imputed_s, d.worked_s)), 3600);
  const bars = w.days.map((d) => `<li class="${d.future ? 'future' : ''} ${d.today ? 'today' : ''}" title="${esc(`${weekdayName(d.weekday)}: ${t('td.imputed')} ${hmin(d.imputed_s)} · ${t('td.worked')} ${hmin(d.worked_s)}`)}">
      <span class="tw-val tabular">${d.imputed_s ? hmin(d.imputed_s) : ''}</span>
      <span class="wk-col"><i class="wk-target" style="height:${(d.worked_s / maxS) * 100}%"></i><i class="wk-done" style="height:${(d.imputed_s / maxS) * 100}%"></i></span>
      <span class="wk-day">${esc(t(`weekday.short.${d.weekday}`))}</span>${d.issues ? `<span class="tw-warn" title="${esc(t('tw.issues'))}">${icon('i-alert')}</span>` : ''}</li>`).join('');
  $('#twBody').innerHTML = `
    <div class="avg-grid four">${tile(t('tw.imputed'), hmin(w.imputed_s), '', t('tw.of_goal', { goal: hmin(w.goal_s) }))}${goalTile}
      ${tile(t('td.worked'), hmin(w.worked_s))}
      ${tile(t('tw.vs_worked'), Math.abs(diff) < 60 ? '0 min' : `${diff > 0 ? '+' : '−'}${hmin(Math.abs(diff))}`, Math.abs(diff) < 60 ? 'pos' : diff > 0 ? 'neg' : 'pend', t(diff > 0 ? 'tw.vs_over' : 'tw.vs_under'))}</div>
    <div class="tw-chart"><div class="legend chart-legend"><span><i class="lg done"></i>${esc(t('td.imputed'))}</span><span><i class="lg goal"></i>${esc(t('td.worked'))}</span></div>
      <ol class="wk-bars tw-bars">${bars}</ol></div>
    <div class="tw-split">
      <div><h4>${esc(t('tw.by_project'))}</h4>${w.projects.length ? `<ul class="share-list">${w.projects.map((p) => shareRow(p.project || t('tw.no_project'), '', p.seconds, w.imputed_s)).join('')}</ul>` : `<p class="muted small">—</p>`}</div>
      <div><h4>${esc(t('tw.by_ticket'))}</h4>${w.tickets.length ? `<ul class="share-list">${w.tickets.map((x) => shareRow(x.key || x.title, x.estimate_s ? t('tw.est', { pct: pct(x.pct), est: hmin(x.estimate_s) }) : '', x.seconds, w.imputed_s, x.color)).join('')}</ul>` : `<p class="muted small">—</p>`}</div>
    </div>
    <p class="muted small">${esc(t('tw.goal_note'))}</p>`;
}
$('#twPrev').addEventListener('click', () => { tk.week = addDays(tk.week, -7); loadWeek(); });
$('#twNext').addEventListener('click', () => { tk.week = addDays(tk.week, 7); loadWeek(); });
$('#twToday').addEventListener('click', () => { tk.week = dateKey(nowMs()); loadWeek(); });

/* ------------------------------------------------- resumen para imputación */

function reportQuery(extra = {}) {
  const r = tk.report;
  return new URLSearchParams(Object.entries({ from: r.from, to: r.to, group: r.group, ...extra }).filter(([, v]) => v)).toString();
}

async function loadReport() {
  $('#rpFrom').value = tk.report.from || '';
  $('#rpTo').value = tk.report.to || '';
  setSegment($('#rpGroup'), tk.report.group);
  setSegment($('#rpFormat'), tk.report.format);
  $('#rpDecimalLabel').textContent = decimalH(5400);
  const today = dateKey(nowMs()), monday = addDays(today, -weekdayOf(today));
  const ranges = [['rep.today', today, today], ['rep.yesterday', addDays(today, -1), addDays(today, -1)],
    ['rep.this_week', monday, today], ['rep.last_week', addDays(monday, -7), addDays(monday, -1)], ['rep.this_month', `${today.slice(0, 8)}01`, today]];
  $('#rpQuick').innerHTML = ranges.map(([k, a, b]) => `<button type="button" class="chip-btn ${tk.report.from === a && tk.report.to === b ? 'on' : ''}" data-from="${a}" data-to="${b}">${esc(t(k))}</button>`).join('');
  try { tk.report.data = await api(`/api/tasks/report?${reportQuery()}`); } catch (e) { $('#rpBody').innerHTML = `<div class="form-error">${esc(e.message)}</div>`; return; }
  renderReport();
}

const rowDate = (iso) => longDate(iso, { day: '2-digit', month: '2-digit', year: 'numeric' });

function renderReport() {
  const d = tk.report.data;
  const byDay = d.group === 'day';
  if (!d.rows.length) { $('#rpBody').innerHTML = `<div class="empty-state">${icon('i-list')}<span>${esc(t('rep.empty'))}</span></div>`; return; }
  const bookCell = (r) => `<button type="button" class="book-toggle ${r.booked}" data-book="${r.booked === 'all' ? 0 : 1}" aria-pressed="${r.booked === 'all'}"
      title="${esc(t(r.booked === 'all' ? 'rep.mark_pending' : 'rep.mark_booked'))}">${icon(r.booked === 'all' ? 'i-check-circle' : 'i-clock')}<span>${esc(t(`rep.booked_${r.booked}`))}</span></button>`;
  let lastDate = null;
  const rows = d.rows.map((r, i) => {
    const first = byDay && r.date !== lastDate;
    lastDate = r.date;
    return `<tr data-row="${i}" class="${first && i ? 'new-day' : ''} ${r.booked === 'all' ? 'is-booked' : ''}">
      ${byDay ? `<td class="tabular">${first ? esc(rowDate(r.date)) : ''}</td>` : ''}
      <td><b>${esc(r.key || '—')}</b>${r.manual ? ` <span class="tag">${esc(t('en.manual'))}</span>` : ''}</td>
      <td class="rp-title">${esc(r.title)}${r.project ? ` <span class="muted small">· ${esc(r.project)}</span>` : ''}</td>
      <td class="num tabular"><b>${fmtTime(r.seconds)}</b></td>
      <td>${bookCell(r)}</td>
      <td class="num"><button type="button" class="icon-btn small" data-copy="${i}" title="${esc(t('rep.copy_row'))}" aria-label="${esc(t('rep.copy_row'))}">${icon('i-copy')}</button></td></tr>`;
  }).join('');
  $('#rpBody').innerHTML = `
    <div class="rp-actions">
      <span class="small"><b class="tabular">${fmtTime(d.total_s)}</b> ${esc(t('rep.total'))}${d.pending_s && d.pending_s < d.total_s ? ` · <span class="pend">${esc(t('rep.pending_n', { dur: fmtTime(d.pending_s) }))}</span>` : ''}</span>
      <span class="spacer"></span>
      <button type="button" class="ghost-btn small" data-book-all="1">${icon('i-check-circle')}${esc(t('rep.all_booked'))}</button>
      <button type="button" class="ghost-btn small" data-book-all="0">${icon('i-clock')}${esc(t('rep.all_pending'))}</button>
      <button type="button" class="ghost-btn small" data-copy-all>${icon('i-copy')}${esc(t('rep.copy_all'))}</button>
      <button type="button" class="primary-btn small" data-csv>${icon('i-download')}CSV</button>
    </div>
    <div class="table-wrap"><table class="data-table rp-table">
      <thead><tr>${byDay ? `<th>${esc(t('rep.col_date'))}</th>` : ''}<th>${esc(t('rep.col_ticket'))}</th><th>${esc(t('rep.col_title'))}</th>
        <th class="num">${esc(t('rep.col_time'))}</th><th>${esc(t('rep.col_status'))}</th><th></th></tr></thead>
      <tbody>${rows}</tbody>
      <tfoot><tr>${byDay ? '<td></td>' : ''}<td colspan="2">${esc(t('rep.total'))}</td><td class="num tabular"><b>${fmtTime(d.total_s)}</b></td><td colspan="2"></td></tr></tfoot>
    </table></div>`;
}

function rowText(r) {
  return [r.date ? rowDate(r.date) : null, r.key || r.title, fmtTime(r.seconds)].filter((x) => x !== null).join('\t');
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
  } catch (e) {        // sin permiso de portapapeles: método clásico
    const area = Object.assign(document.createElement('textarea'), { value: text });
    area.style.cssText = 'position:fixed;opacity:0';
    document.body.append(area);
    area.select();
    document.execCommand('copy');
    area.remove();
  }
  toast(t('rep.copied'), 'ok', 1800);
}

async function setBooked(ids, booked) {
  try {
    await api('/api/entries/booked', { method: 'POST', body: { ids, booked } });
    await loadReport();
    loadTasks().catch(() => {});
  } catch (e) { toast(e.message, 'err'); }
}

$('#rpBody').addEventListener('click', (e) => {
  const d = tk.report.data;
  const copy = e.target.closest('[data-copy]');
  if (copy) return copyText(rowText(d.rows[Number(copy.dataset.copy)]));
  if (e.target.closest('[data-copy-all]')) {
    const head = [d.group === 'day' ? t('rep.col_date') : null, t('rep.col_ticket'), t('rep.col_time')].filter(Boolean).join('\t');
    return copyText([head, ...d.rows.map(rowText)].join('\n'));
  }
  const book = e.target.closest('[data-book]');
  if (book) return setBooked(d.rows[Number(book.closest('[data-row]').dataset.row)].entry_ids, book.dataset.book === '1');
  const all = e.target.closest('[data-book-all]');
  if (all) return setBooked(d.rows.flatMap((r) => r.entry_ids), all.dataset.bookAll === '1');
  if (e.target.closest('[data-csv]')) {
    const a = Object.assign(document.createElement('a'), { href: `/api/tasks/report.csv?${reportQuery({ format: tk.report.format })}` });
    document.body.append(a);
    a.click();
    a.remove();
  }
});
$('#rpQuick').addEventListener('click', (e) => {
  const b = e.target.closest('[data-from]');
  if (!b) return;
  tk.report.from = b.dataset.from;
  tk.report.to = b.dataset.to;
  loadReport();
});
['#rpFrom', '#rpTo'].forEach((s) => $(s).addEventListener('change', () => {
  tk.report.from = $('#rpFrom').value || null;
  tk.report.to = $('#rpTo').value || null;
  loadReport();
}));
$('#rpGroup').addEventListener('click', (e) => { const b = e.target.closest('[data-value]'); if (b) { tk.report.group = b.dataset.value; loadReport(); } });
$('#rpFormat').addEventListener('click', (e) => {
  const b = e.target.closest('[data-value]');
  if (!b) return;
  tk.report.format = b.dataset.value;
  renderReport();
  // Se recuerda la preferencia (horas y minutos o decimal).
  api('/api/settings', { method: 'PUT', body: { tasks: { decimal: tk.report.format === 'decimal' } } })
    .then((s) => { state.settings = s; }).catch(() => {});
});

/* ------------------------------------------------------------ integración */

// Los fichajes pausan la tarea en el servidor: aquí solo se avisa y se repinta.
window.addEventListener('jornada:clock', (e) => {
  const { action, res } = e.detail;
  if (res?.task_paused) {
    const x = taskById(res.task_paused);
    toast(t(action === 'stop' ? 'ts.closed_stop' : 'ts.paused_break', { task: taskLabel(x) }), 'info', 4200);
  }
  loadTasks().catch(() => {});
});

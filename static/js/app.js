/* ============================================================
   Jornada — frontend
   Los contadores se derivan de la foto que devuelve el servidor
   (marcas guardadas + hora del servidor) y del tiempo real transcurrido,
   nunca de un número que se incremente en memoria.
   Todos los textos salen de los diccionarios (i18n.js → t()).
   ============================================================ */
'use strict';

const TZ = 'Europe/Madrid';
const MODE_ICONS = { office: 'i-building', remote: 'i-home', off: 'i-palm' };
const PROFILE_KEYS = ['normal', 'friday', 'summer'];
const MAX_BREAK_NOTE = 200;

const $ = (sel, root = document) => root.querySelector(sel);
const icon = (id) => `<svg><use href="#${id}"/></svg>`;
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const weekdayName = (i) => t(`weekday.${i}`);
const modeLabel = (m) => t(`mode.${m}`);
const profileName = (p) => t(`profile.${p}`);

const state = {
  settings: null,
  today: null,      // jornada de hoy calculada por el servidor
  week: null,       // resumen semana actual
  month: null,      // resumen mes actual
  total: null,      // balance acumulado de todas las jornadas
  unclosed: [],
  snapAt: 0,        // instante (reloj del servidor) de la foto
  offset: 0,        // diferencia reloj servidor - reloj navegador
  cal: null,        // { year, month } visible en el calendario
  monthData: null,
  weekDate: null,
  weekData: null,
  selected: null,
  busy: false,
  heroKey: null,
  wasDone: null,
  offline: false,
};

/* ---------------------------------------------------------- utilidades */

const nowMs = () => Date.now() + state.offset;
const pad = (n) => String(n).padStart(2, '0');

function hms(sec, ceil = false) {
  let s = ceil ? Math.ceil(sec - 1e-6) : Math.floor(sec + 1e-6);
  s = Math.max(0, s);
  return `${pad(Math.floor(s / 3600))}:${pad(Math.floor((s % 3600) / 60))}:${pad(s % 60)}`;
}

function human(sec, ceil = false) {
  const s = Math.max(0, ceil ? Math.ceil(sec - 1e-6) : Math.floor(sec + 1e-6));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), r = s % 60;
  if (h) return m ? `${h} h ${m} min` : `${h} h`;
  if (m) return r && m < 10 ? `${m} min ${r} s` : `${m} min`;
  return `${r} s`;
}

/** Duración en el formato elegido en ajustes. */
function dur(sec, ceil = false) {
  if (state.settings?.duration_format === 'hm') {
    const total = Math.max(0, ceil ? Math.ceil(sec / 60 - 1e-9) : Math.floor(sec / 60 + 1e-9));
    const h = Math.floor(total / 60), m = total % 60;
    return h ? `${h} h ${pad(m)} min` : `${m} min`;
  }
  return hms(sec, ceil);
}

function signed(sec) {
  if (Math.abs(sec) < 1) return dur(0);
  return (sec > 0 ? '+' : '−') + dur(Math.abs(sec));
}

const shortDur = (sec) => {
  const m = Math.floor(Math.max(0, sec) / 60 + 1e-9);
  return `${Math.floor(m / 60)}:${pad(m % 60)}`;
};

const fmtCache = new Map();
function formatter(opts) {
  const h12 = state.settings?.time_format === '12h';
  const key = JSON.stringify(opts) + h12 + currentLocale();
  if (!fmtCache.has(key)) fmtCache.set(key, new Intl.DateTimeFormat(currentLocale(), { timeZone: TZ, hour12: h12, ...opts }));
  return fmtCache.get(key);
}

function clock(value, seconds = false) {
  if (value == null) return '—';
  return formatter({ hour: '2-digit', minute: '2-digit', ...(seconds ? { second: '2-digit' } : {}) }).format(new Date(value));
}

/** Hora grande con los segundos en pequeño. */
function bigClock(ms) {
  const parts = formatter({ hour: '2-digit', minute: '2-digit', second: '2-digit' }).formatToParts(new Date(ms));
  const get = (type) => parts.find((p) => p.type === type)?.value ?? '';
  const period = get('dayPeriod');
  return `${get('hour')}:${get('minute')}<small>:${get('second')}${period ? ' ' + esc(period) : ''}</small>`;
}

const keyFmt = new Intl.DateTimeFormat('en-CA', { timeZone: TZ, year: 'numeric', month: '2-digit', day: '2-digit' });
const dateKey = (ms) => keyFmt.format(new Date(ms));
const keyToDate = (key) => new Date(`${key}T12:00:00Z`);
const weekdayOf = (key) => (keyToDate(key).getUTCDay() + 6) % 7;
function addDays(key, n) {
  const d = keyToDate(key);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}
const longDate = (key, opts = { weekday: 'long', day: 'numeric', month: 'long' }) =>
  new Intl.DateTimeFormat(currentLocale(), { timeZone: 'UTC', ...opts }).format(keyToDate(key));

const refMinutes = (hhmm) => { const [h, m] = hhmm.split(':').map(Number); return h * 60 + m; };
function localSeconds(ms) {
  const p = new Intl.DateTimeFormat('en-GB', { timeZone: TZ, hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
    .formatToParts(new Date(ms));
  const g = (type) => Number(p.find((x) => x.type === type).value);
  return (g('hour') % 24) * 3600 + g('minute') * 60 + g('second');
}

/* --------------------------------------------------------------- API */

async function api(path, { method = 'GET', body } = {}) {
  let res;
  try {
    res = await fetch(path, {
      method,
      headers: body ? { 'Content-Type': 'application/json' } : {},
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch (e) {
    setOffline(true);
    throw new Error(t('toast.offline'));
  }
  setOffline(false);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(data.error || `Error ${res.status}`);
    err.status = res.status;
    throw err;
  }
  return data;
}

function setOffline(off) {
  if (state.offline === off) return;
  state.offline = off;
  renderBanner();
}

/* ------------------------------------------------------------ toasts */

function toast(msg, kind = 'ok', ms = 3600) {
  const ic = { ok: 'i-check-circle', err: 'i-alert', warn: 'i-alert', info: 'i-info', party: 'i-sparkles' }[kind] || 'i-info';
  const el = document.createElement('div');
  el.className = `toast ${kind === 'party' ? 'ok' : kind}`;
  el.setAttribute('role', kind === 'err' ? 'alert' : 'status');
  el.innerHTML = `${icon(ic)}<span>${esc(msg)}</span>`;
  $('#toasts').append(el);
  setTimeout(() => { el.classList.add('out'); setTimeout(() => el.remove(), 260); }, ms);
}

function confirmDialog({ title, text, ok = t('common.confirm'), danger = false }) {
  const dlg = $('#confirmDialog');
  $('#confirmTitle').textContent = title;
  $('#confirmText').textContent = text;
  $('#confirmOk').textContent = ok;
  $('#confirmOk').classList.toggle('danger', danger);
  $('#confirmIcon').classList.toggle('danger', danger);
  dlg.returnValue = '';
  dlg.showModal();
  return new Promise((resolve) => dlg.addEventListener('close', () => resolve(dlg.returnValue === 'ok'), { once: true }));
}

/* ------------------------------------------------------------- tema */

const media = matchMedia('(prefers-color-scheme: light)');
const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
function applyTheme(pref) {
  const resolved = pref === 'system' ? (media.matches ? 'light' : 'dark') : pref;
  document.documentElement.dataset.theme = resolved;
  try { localStorage.setItem('wt-theme', pref); } catch (e) { /* sin almacenamiento */ }
}
media.addEventListener('change', () => state.settings?.theme === 'system' && applyTheme('system'));

/* ------------------------------------------------------ carga de datos */

async function loadState() {
  const t0 = Date.now();
  const data = await api('/api/state');
  const t1 = Date.now();
  state.offset = data.server_ms - (t0 + t1) / 2;
  state.snapAt = data.server_ms;
  const formatChanged = state.settings && (state.settings.time_format !== data.settings.time_format);
  state.settings = data.settings;
  if (formatChanged) fmtCache.clear();
  state.today = data.today;
  state.week = data.week;
  state.month = data.month;
  state.total = data.total;
  state.unclosed = data.unclosed;
  // Versión: el proceso del servidor, los archivos en disco y esta página deben coincidir.
  const pageBuild = document.documentElement.dataset.build;
  state.update = data.build !== data.disk_build ? 'restart' : (pageBuild && pageBuild !== data.disk_build ? 'reload' : null);
  applyTheme(data.settings.theme);
  if (data.settings.language && data.settings.language !== currentLang()) await switchLanguage(data.settings.language, { save: false });
  renderStatic();
  tick();
}

async function loadMonth() {
  const { year, month } = state.cal;
  const data = await api(`/api/month/${year}-${pad(month)}`);
  // Al pasar meses rápido, una respuesta antigua no debe pintar el mes equivocado.
  if (state.cal.year !== year || state.cal.month !== month) return;
  state.monthData = data;
  renderCalendar();
  renderDetail();
}

async function loadWeek() {
  const day = state.weekDate;
  const data = await api(`/api/week/${day}`);
  if (state.weekDate !== day) return;
  state.weekData = data;
  renderWeek();
}

/** Recarga única: si se pide otra mientras hay una en curso, se repite al terminar
 *  (así, tras fichar, nunca se pinta una respuesta anterior al fichaje). */
let refreshing = null;
let refreshAgain = false;
function refreshAll() {
  if (state.closed) return Promise.resolve();
  if (refreshing) { refreshAgain = true; return refreshing; }
  refreshing = (async () => {
    do {
      refreshAgain = false;
      try {
        await loadState();
        await Promise.all([loadMonth(), loadWeek()]);
      } catch (e) {
        toast(e.message, 'err');
      }
    } while (refreshAgain && !state.closed);
  })().finally(() => { refreshing = null; });
  return refreshing;
}

/* ------------------------------------------------------- cálculo en vivo */

/** Instante en que el trabajo acumulado alcanza el objetivo. */
function completionInstant(day, endMs) {
  if (!day.clock_in || !day.target_s) return null;
  const goal = day.target_s * 1000;
  let acc = 0, cursor = Date.parse(day.clock_in);
  const breaks = day.breaks.map((b) => [Date.parse(b.start), b.end ? Date.parse(b.end) : endMs]).sort((a, b) => a[0] - b[0]);
  for (const [bs, be] of [...breaks, [endMs, endMs]]) {
    const segEnd = Math.min(bs, endMs);
    if (segEnd > cursor) {
      if (acc + (segEnd - cursor) >= goal) return cursor + (goal - acc);
      acc += segEnd - cursor;
    }
    cursor = Math.max(cursor, Math.min(be, endMs));
  }
  return null;
}

function live() {
  const d = state.today;
  const now = nowMs();
  const dt = Math.max(0, (now - state.snapAt) / 1000);
  let worked = d.worked_s, brk = d.break_s, cur = d.current_break_s;
  if (d.status === 'working') worked += dt;
  else if (d.status === 'on_break') { brk += dt; cur += dt; }

  const target = d.target_s;
  const remaining = Math.max(0, target - worked);
  const extra = Math.max(0, worked - target);
  const pendingBreak = target ? Math.max(0, d.min_break_s - brk) : 0;
  const optLeft = target ? Math.max(0, d.min_break_s + d.optional_break_s - brk) : 0;
  const inProgress = d.status === 'working' || d.status === 'on_break';

  let exit = null, exitMin = null, exitOpt = null;
  if (inProgress) {
    exitMin = Math.round((now + remaining * 1000) / 1000) * 1000;
    exit = exitMin + Math.ceil(pendingBreak) * 1000;
    exitOpt = exitMin + Math.ceil(optLeft) * 1000;
  } else if (d.status === 'not_started' && target) {
    exitMin = now + target * 1000;
    exit = exitMin + d.min_break_s * 1000;
    exitOpt = exitMin + (d.min_break_s + d.optional_break_s) * 1000;
  } else if (d.status === 'finished') {
    exit = Date.parse(d.clock_out);
  }
  const done = !!target && remaining === 0 && !!d.clock_in;
  const endMs = d.clock_out ? Date.parse(d.clock_out) : now;
  return {
    now, worked, brk, cur, target, remaining, extra, pendingBreak, optLeft, inProgress,
    exit, exitMin, exitOpt, done,
    completedAt: done ? completionInstant(d, endMs) : null,
    progress: target ? Math.min(1, worked / target) : (d.clock_in ? 1 : 0),
  };
}

function heroStatus(d, l) {
  switch (d.status) {
    case 'working': return l.done ? 'done' : 'working';
    case 'on_break': return 'on_break';
    case 'finished': return l.worked + 0.5 >= l.target ? 'finished' : 'finished_short';
    case 'not_started': return d.target_s ? 'idle' : 'off';
    default: return 'off';
  }
}

/* -------------------------------------------------------------- tick */

function tick() {
  const d = state.today;
  if (!d || state.closed) return;
  const now = nowMs();
  $('#liveClock').textContent = clock(now, true);

  if (dateKey(now) !== d.date) {   // cambio de día
    if (!state.rolling) { state.rolling = true; refreshAll().finally(() => { state.rolling = false; }); }
    return;
  }

  const l = live();
  const hs = heroStatus(d, l);
  $('#hero').dataset.status = hs;

  if (state.heroKey !== hs) {
    state.heroKey = hs;
    renderActions(hs);
  }

  // Aviso de jornada completada (solo al cruzar el umbral en vivo).
  if (d.status === 'working' && state.wasDone === false && l.done) celebrate();
  state.wasDone = d.status === 'working' ? l.done : null;

  renderStatusPill(d, hs);
  renderCountdown(d, l, hs);
  renderExit(d, l, hs);
  renderAlerts(d, l, hs);
  renderTiles(d, l);
  renderBreakMeter(d, l);
  renderDayline(d, l);
  renderStats(d, l);

  const exitEl = $('#tlExit');
  if (exitEl && !d.clock_out) exitEl.textContent = l.exit ? clock(l.exit) : '—';

  document.title =
    hs === 'working' ? `${hms(l.remaining, true)} · Jornada` :
    hs === 'done' ? `+${hms(l.extra)} · Jornada` :
    hs === 'on_break' ? `${t('tl.break')} ${hms(l.cur)} · Jornada` : 'Jornada';
}

function renderStatusPill(d, hs) {
  const cls = { working: 'working', done: 'done', on_break: 'on_break', finished: 'finished', finished_short: 'short' }[hs] || '';
  const key = { idle: 'status.idle', working: 'status.working', done: 'status.done', on_break: 'status.on_break',
    finished: 'status.finished', finished_short: 'status.finished_short' }[hs]
    || (d.status === 'off' ? 'status.off_day' : 'status.nonworking');
  $('#statusPill').className = `status-pill ${cls}`;
  $('#statusText').textContent = t(key);
}

function renderCountdown(d, l, hs) {
  const label = $('#countLabel'), value = $('#countdown'), sub = $('#progressText');
  const pct = Math.floor(l.progress * 100);
  let ring = l.progress;
  switch (hs) {
    case 'idle':
      label.textContent = t('count.target_today');
      value.textContent = hms(d.target_s);
      sub.textContent = t('count.not_clocked');
      break;
    case 'working':
      label.textContent = t('count.left');
      value.textContent = hms(l.remaining, true);
      sub.textContent = t('count.pct', { pct });
      break;
    case 'done':
      label.textContent = t('count.extra');
      value.textContent = '+' + hms(l.extra);
      sub.textContent = t('count.pct', { pct: 100 });
      break;
    case 'on_break':
      label.textContent = t(l.done ? 'count.extra_paused' : 'count.left_paused');
      value.textContent = l.done ? '+' + hms(l.extra) : hms(l.remaining, true);
      sub.textContent = t('count.pct', { pct });
      break;
    case 'finished':
    case 'finished_short': {
      const diff = l.worked - l.target;
      label.textContent = t(!l.target ? 'count.worked' : diff >= 1 ? 'count.extra' : diff <= -1 ? 'count.short' : 'count.exact');
      value.textContent = !l.target ? hms(l.worked) : (diff >= 1 ? '+' : diff <= -1 ? '−' : '') + hms(Math.abs(diff));
      sub.textContent = t('count.worked_value', { time: hms(l.worked) });
      break;
    }
    default:
      label.textContent = t('count.today');
      value.textContent = t(d.status === 'off' ? 'count.off' : 'count.rest');
      sub.textContent = t(d.status === 'off' ? 'count.off_sub' : 'count.nonworking_sub');
      ring = 0;
  }
  value.classList.toggle('long', value.textContent.length > 8);   // «+00:12:30» o «−00:12:30»
  $('#ringBar').style.strokeDasharray = `${Math.max(0, Math.min(1, ring)) * 1000} 1000`;
  renderTicks(hs === 'off' ? 0 : d.target_s);
}

/** Una marca por hora del objetivo: el anillo se lee como la esfera de un reloj. */
function renderTicks(targetS) {
  const hours = Math.round(targetS / 3600);
  const g = $('#ringTicks');
  if (Number(g.dataset.hours) === hours) return;
  g.dataset.hours = String(hours);
  if (hours < 2 || hours > 16) { g.innerHTML = ''; return; }
  const lines = [];
  for (let i = 1; i < hours; i++) {
    const a = (i / (targetS / 3600)) * 2 * Math.PI;
    const [x1, y1] = [110 + 88 * Math.cos(a), 110 + 88 * Math.sin(a)];
    const [x2, y2] = [110 + 104 * Math.cos(a), 110 + 104 * Math.sin(a)];
    lines.push(`<line x1="${x1.toFixed(2)}" y1="${y1.toFixed(2)}" x2="${x2.toFixed(2)}" y2="${y2.toFixed(2)}"/>`);
  }
  g.innerHTML = lines.join('');
}

function renderExit(d, l, hs) {
  const label = $('#exitLabel'), time = $('#exitTime'), note = $('#exitNote');
  const ref = d.ref_end ? t('exit.ref', { start: d.ref_start, end: d.ref_end }) : '';
  let html = '—', text = '';
  switch (hs) {
    case 'idle':
      label.textContent = t('exit.if_start');
      html = bigClock(l.exit);
      text = d.min_break_s ? t('exit.includes_min', { dur: human(d.min_break_s), ref }) : ref;
      break;
    case 'working':
      label.textContent = t('exit.leave_at');
      html = bigClock(l.exit);
      if (l.pendingBreak > 0) text = t('exit.pending_break', { dur: human(l.pendingBreak, true), time: clock(l.exitMin) });
      else if (l.optLeft > 0) text = t('exit.with_optional', { dur: human(l.optLeft, true), time: clock(l.exitOpt) });
      else text = refDiff(d, l.exit);
      break;
    case 'done':
      label.textContent = t('exit.completed_at');
      html = l.completedAt ? bigClock(l.completedAt) : '—';
      text = t('exit.extra_so_far', { dur: human(l.extra) });
      break;
    case 'on_break':
      label.textContent = t(l.done ? 'exit.already_done' : 'exit.will_leave');
      html = l.done ? (l.completedAt ? bigClock(l.completedAt) : '—') : bigClock(l.exit);
      if (l.done) text = t('exit.finish_any');
      else if (l.pendingBreak > 0) text = t('exit.if_back', { time: clock(l.exitMin) });
      else if (l.optLeft > 0) text = t('exit.opt_left', { dur: human(l.optLeft, true) });
      else text = t('exit.each_minute');
      break;
    case 'finished':
    case 'finished_short':
      label.textContent = t('exit.left_at');
      html = bigClock(Date.parse(d.clock_out));
      text = t('exit.worked_of', { worked: human(l.worked), target: human(l.target) });
      break;
    default:
      label.textContent = t('exit.no_day');
      html = '—';
      text = t('exit.work_anyway');
  }
  if (time.innerHTML !== html) time.innerHTML = html;
  if (note.innerHTML !== text) note.innerHTML = text;
}

function refDiff(d, exitMs) {
  if (!d.ref_end || !exitMs) return '';
  const diffMin = Math.round((refMinutes(d.ref_end) * 60 - localSeconds(exitMs)) / 60);
  if (diffMin > 0) return t('ref.before', { dur: human(diffMin * 60), time: d.ref_end });
  if (diffMin < 0) return t('ref.after', { dur: human(-diffMin * 60), time: d.ref_end });
  return t('ref.exact', { time: d.ref_end });
}

function renderAlerts(d, l, hs) {
  const items = [];
  if (hs === 'done') items.push(['celebrate', 'i-sparkles', t('alert.done')]);
  if (l.inProgress && l.pendingBreak > 0) {
    items.push(['warn', 'i-coffee', l.brk < 1
      ? t('alert.break_pending', { dur: human(d.min_break_s) })
      : t('alert.break_missing', { dur: human(l.pendingBreak, true), done: human(l.brk), min: human(d.min_break_s) })]);
  } else if (l.inProgress && d.min_break_s && l.brk > 0 && l.brk <= d.min_break_s + d.optional_break_s) {
    items.push(['ok', 'i-check-circle', t('alert.break_ok')]);
  }
  if (l.inProgress && l.target && l.brk > d.min_break_s + d.optional_break_s && d.min_break_s + d.optional_break_s > 0) {
    items.push(['warn', 'i-alert', t('alert.break_over', { dur: human(d.min_break_s + d.optional_break_s) })]);
  }
  if (hs.startsWith('finished') && d.flags.includes('break_short')) {
    items.push(['warn', 'i-alert', t('alert.break_short', { done: human(l.brk), min: human(d.min_break_s) })]);
  }
  if (hs === 'finished') items.push(['ok', 'i-check-circle', t('alert.closed')]);
  const html = items.map(([k, ic, msg]) => `<div class="alert ${k}">${icon(ic)}<span>${msg}</span></div>`).join('');
  const box = $('#heroAlerts');
  if (box.dataset.html !== html) { box.innerHTML = html; box.dataset.html = html; }

  const breakLive = $('#breakLive');
  breakLive.hidden = d.status !== 'on_break';
  if (!breakLive.hidden) $('#breakTimer').textContent = hms(l.cur);
}

function renderTiles(d, l) {
  $('#tWorked').textContent = dur(l.worked);
  $('#tWorkedSub').textContent = l.target ? t('sum.of_target', { dur: dur(l.target) }) : t('sum.no_target');

  const extra = l.extra > 0 && l.target;
  const deficit = d.status === 'finished' && l.remaining >= 1;
  $('#tRemainingLabel').textContent = t(extra ? 'sum.extra' : deficit ? 'sum.deficit' : 'sum.pending');
  $('#tRemaining').textContent = extra ? '+' + dur(l.extra) : deficit ? '−' + dur(l.remaining) : dur(l.remaining, true);
  $('#tRemainingCell').dataset.tone = extra ? 'gold' : deficit ? 'bad' : 'ink';
  $('#tRemainingSub').textContent = l.target ? t('sum.pct_day', { pct: Math.floor(l.progress * 100) }) : '—';

  $('#tBreak').textContent = dur(l.brk);
  const n = d.breaks.length;
  $('#tBreakSub').textContent = d.status === 'on_break'
    ? t('sum.in_progress', { time: hms(l.cur) })
    : n ? t(n === 1 ? 'sum.breaks_one' : 'sum.breaks_many', { n, min: human(d.min_break_s) })
      : (d.min_break_s ? t('sum.min_today', { min: human(d.min_break_s) }) : t('sum.no_min'));

  $('#tIn').textContent = d.clock_in ? clock(d.clock_in) : '—';
  let sub = t('sum.not_clocked');
  if (d.clock_in && d.ref_start) {
    const diff = Math.round((localSeconds(Date.parse(d.clock_in)) - refMinutes(d.ref_start) * 60) / 60);
    sub = diff === 0 ? t('sum.on_time', { time: d.ref_start })
      : t(diff < 0 ? 'sum.early' : 'sum.late', { dur: human(Math.abs(diff) * 60), time: d.ref_start });
  }
  $('#tInSub').textContent = sub;
}

function renderBreakMeter(d, l) {
  const min = d.min_break_s, opt = d.optional_break_s, total = min + opt;
  const bar = $('#breakMeterBar'), optBar = $('#breakMeterOpt');
  if (!total) {
    $('#breakMeterText').textContent = l.brk ? human(l.brk) : '—';
    bar.style.width = '0'; optBar.style.width = '0';
    $('#breakMeterNote').textContent = t('bm.none');
    return;
  }
  $('#breakMeterText').textContent = `${l.brk < 1 ? '0 min' : human(l.brk)} / ${human(min)}`;
  bar.style.width = `${(Math.min(l.brk, min) / total) * 100}%`;
  bar.classList.toggle('done', l.brk >= min);
  optBar.style.width = `${(Math.max(0, Math.min(l.brk - min, opt)) / total) * 100}%`;
  $('#breakMeterNote').textContent = l.brk < min
    ? (opt ? t('bm.missing_opt', { dur: human(min - l.brk, true), opt: human(opt) }) : t('bm.missing', { dur: human(min - l.brk, true) }))
    : l.brk <= total
      ? (opt ? t('bm.done_opt', { dur: human(total - l.brk, true) }) : t('bm.done'))
      : t('bm.over', { dur: human(l.brk - total) });
}

function renderDayline(d, l) {
  const box = $('#dayline');
  if (!d.clock_in) {
    box.innerHTML = '';
    $('#daylineScale')?.remove();
    return;
  }
  const start = Date.parse(d.clock_in);
  const end = d.clock_out ? Date.parse(d.clock_out) : l.now;
  const horizon = Math.max(end, l.exit || end);
  const span = Math.max(1, horizon - start);
  const pct = (a, b) => `left:${((a - start) / span) * 100}%;width:${(Math.max(0, b - a) / span) * 100}%`;
  const segs = [`<span class="w" style="${pct(start, end)}"></span>`];
  for (const b of d.breaks) {
    const bs = Date.parse(b.start), be = b.end ? Date.parse(b.end) : end;
    segs.push(`<span class="b" style="${pct(bs, Math.min(be, end))}"></span>`);
  }
  if (!d.clock_out && l.exit && l.exit > end) segs.push(`<span class="f" style="${pct(end, l.exit)}"></span>`);
  box.innerHTML = segs.join('');
  let scale = $('#daylineScale');
  if (!scale) {
    scale = document.createElement('div');
    scale.id = 'daylineScale';
    scale.className = 'dayline-scale';
    box.after(scale);
  }
  scale.innerHTML = `<span>${clock(start)}</span><span>${clock(horizon)}</span>`;
}

const STAT_PANELS = [
  { key: 'today', title: 'stats.today', scale: 3600 },
  { key: 'week', title: 'stats.week', scale: 2 * 3600 },
  { key: 'month', title: 'stats.month', scale: 5 * 3600 },
  { key: 'total', title: 'stats.total', scale: 10 * 3600 },
];

function buildStats() {
  const box = $('#stats');
  box.innerHTML = STAT_PANELS.map((p) => `
    <article class="stat-panel ${p.key === 'total' ? 'total' : ''}" data-panel="${p.key}">
      <h3 data-i18n="${p.title}">${t(p.title)}</h3>
      <span class="stat-balance tabular" data-f="balance">—</span>
      <div class="bal-bar" aria-hidden="true"><span data-f="bar"></span></div>
      <dl class="stat-rows" data-f="rows"></dl>
    </article>`).join('');
  box.dataset.built = '1';
  box.removeAttribute('aria-busy');
}

function setPanel(key, balance, rows, { pending = false } = {}) {
  const panel = $(`#stats [data-panel="${key}"]`);
  const def = STAT_PANELS.find((p) => p.key === key);
  const value = panel.querySelector('[data-f="balance"]');
  // Lo que falta de una jornada en curso es «pendiente», nunca un déficit con signo.
  const html = pending ? `${dur(Math.abs(balance), true)}<small>${t('stats.pending')}</small>` : signed(balance);
  if (value.innerHTML !== html) value.innerHTML = html;
  value.className = `stat-balance tabular ${pending ? 'pend' : balance >= 1 ? 'pos' : balance <= -1 ? 'neg' : 'zero'}`;
  // Barra divergente: el centro es 0; derecha = tiempo de más, izquierda = de menos.
  const half = pending ? 0 : Math.min(50, (Math.abs(balance) / def.scale) * 50);
  const bar = panel.querySelector('[data-f="bar"]');
  bar.className = balance >= 0 ? 'pos' : 'neg';
  bar.style.transform = `scaleX(${half / 50})`;
  const rowsHtml = rows.map(([k, v]) => `<dt>${t(k)}</dt><dd>${v}</dd>`).join('');
  const dl = panel.querySelector('[data-f="rows"]');
  if (dl.dataset.html !== rowsHtml) { dl.innerHTML = rowsHtml; dl.dataset.html = rowsHtml; }
}

function renderStats(d, l) {
  const w = state.week, m = state.month, all = state.total;
  if (!w || !m || !all) return;
  if (!$('#stats').dataset.built) buildStats();
  // Ajuste en vivo: lo que ha cambiado hoy desde la última foto del servidor.
  const dWorked = l.worked - d.worked_s;
  const dExtra = l.extra - d.extra_s;
  const pendingNow = l.inProgress ? l.remaining : 0;
  const wWorked = w.worked_s + dWorked, mWorked = m.worked_s + dWorked;
  const wBal = w.balance_s + dExtra, mBal = m.balance_s + dExtra, totalBal = all.balance_s + dExtra;
  const completed = m.completed_days + (l.done && !(d.worked_s >= d.target_s && d.target_s) ? 1 : 0);
  const pendRow = pendingNow > 0 ? [['stats.pending_today', `<span class="pend">${dur(pendingNow, true)}</span>`]] : [];

  // Hoy: en curso solo cuenta el extra; lo que falta es pendiente, no déficit.
  let todayBal = 0, todayPending = false;
  if (d.status === 'finished') todayBal = l.worked - l.target;
  else if (l.inProgress) { todayBal = l.extra > 0 ? l.extra : -l.remaining; todayPending = l.extra <= 0 && l.remaining > 0; }
  setPanel('today', todayBal, [
    ['stats.worked', dur(l.worked)],
    ['stats.target', l.target ? dur(l.target) : t('stats.no_target')],
    ['stats.break', dur(l.brk)],
  ], { pending: todayPending });

  setPanel('week', wBal, [['stats.worked', dur(wWorked)], ['stats.target', dur(w.target_s)], ...pendRow]);

  setPanel('month', mBal, [
    ['stats.worked', dur(mWorked)],
    ['stats.target', dur(m.target_s)],
    ['stats.completed', t('stats.completed_of', { n: completed, m: m.worked_days })],
    ['stats.avg', dur(m.worked_days ? mWorked / m.worked_days : 0)],
  ]);

  setPanel('total', totalBal, all.since ? [
    ['stats.days', String(all.worked_days)],
    ['stats.since', longDate(all.since, { day: 'numeric', month: 'short', year: 'numeric' })],
    ['stats.avg', dur(all.worked_days ? (all.worked_s + dWorked) / all.worked_days : 0)],
  ] : [['stats.days', t('stats.none_yet')]]);
}

/* ------------------------------------------- render al recibir datos */

function renderStatic() {
  const d = state.today;
  $('#todayLabel').textContent = longDate(d.date);
  const hasMode = d.status !== 'nonworking';
  $('#modeBadge').innerHTML = hasMode ? `${icon(MODE_ICONS[d.mode])}${modeLabel(d.mode)}` : `${icon('i-palm')}${t('mode.nonworking')}`;
  $('#modeBadge').nextElementSibling?.remove();
  if (d.profile && d.target_s) {
    $('#modeBadge').insertAdjacentHTML('afterend',
      `<span class="mode-badge">${icon(d.profile === 'summer' ? 'i-sun' : 'i-clock')}${profileName(d.profile)}</span>`);
  }
  $('#dayNoteBtn').classList.toggle('has-note', !!d.notes);
  renderTimeline(d);
  renderBanner();
  state.heroKey = null;   // fuerza a repintar los botones
}

function noteButton(target, note) {
  const label = t(note ? 'tl.note_edit' : 'tl.note_add');
  return `<button type="button" class="note-btn ${note ? 'has-note' : ''}" data-note="${target}" title="${esc(label)}" aria-label="${esc(label)}">${icon('i-note')}</button>`;
}

function renderTimeline(d) {
  const list = $('#timeline');
  if (!d.clock_in) {
    const html = `<li class="tl-empty">${esc(t('today.empty'))}</li>`;
    if (list.dataset.html !== html) { list.innerHTML = html; list.dataset.html = html; }
    return;
  }
  const items = [['in', 'i-login', t('tl.in'), clock(d.clock_in), d.ref_start ? t('tl.ref', { time: d.ref_start }) : '', '']];
  d.breaks.forEach((b, i) => {
    const sub = b.note ? `<span class="tl-note">${esc(b.note)}</span>` : (b.end ? human(b.duration_s) : t('tl.ongoing'));
    items.push(['br', 'i-coffee', d.breaks.length > 1 ? t('tl.break_n', { n: i + 1 }) : t('tl.break'),
      `${clock(b.start)} – ${b.end ? clock(b.end) : t('tl.now')}`, sub, noteButton(i, b.note)]);
  });
  items.push(d.clock_out
    ? ['out', 'i-stop', t('tl.out'), clock(d.clock_out), '', '']
    : ['', 'i-clock', t('tl.expected'), '<span id="tlExit">—</span>', d.ref_end ? t('tl.ref', { time: d.ref_end }) : '', '']);
  const html = items.map(([k, ic, title, time, sub, extra]) => `
    <li><span class="tl-icon ${k}">${icon(ic)}</span>
      <div class="tl-main"><span class="tl-title">${title}${extra}</span>${sub ? `<span class="tl-sub">${sub}</span>` : ''}</div>
      <span class="tl-time">${time}</span></li>`).join('')
    + (d.notes ? `<li class="tl-daynote"><span class="tl-icon note">${icon('i-note')}</span><button type="button" class="tl-daynote-text" data-note="day">${esc(d.notes)}</button></li>` : '');
  if (list.dataset.html !== html) { list.innerHTML = html; list.dataset.html = html; }
}

function renderBanner() {
  const b = $('#globalBanner');
  if (state.offline) {
    b.hidden = false;
    b.innerHTML = `${icon('i-alert')}<span>${esc(t('banner.offline'))}</span>`;
    return;
  }
  if (state.update) {
    b.hidden = false;
    b.innerHTML = state.update === 'restart'
      ? `${icon('i-info')}<span>${t('banner.restart')}</span>`
      : `${icon('i-info')}<span>${esc(t('banner.reload'))}</span><button class="ghost-btn small" data-reload>${icon('i-rotate')}${esc(t('banner.reload_btn'))}</button>`;
    return;
  }
  if (state.unclosed?.length) {
    const key = state.unclosed[0];
    b.hidden = false;
    b.innerHTML = `${icon('i-alert')}<span>${t('banner.unclosed', { date: esc(longDate(key)) })}</span>
      <button class="ghost-btn small" data-fix="${key}">${icon('i-edit')}${esc(t('banner.fix'))}</button>`;
    return;
  }
  b.hidden = true;
}

function renderActions(hs) {
  const btn = (action, cls, ic, key) =>
    `<button class="action-btn ${cls}" data-action="${action}">${icon(ic)}<span>${esc(t(key))}</span></button>`;
  const html = {
    idle: btn('start', 'primary go', 'i-play', 'action.start'),
    off: btn('start', 'primary go', 'i-play', 'action.start'),
    working: btn('break_start', 'primary pause', 'i-coffee', 'action.break_start') + btn('stop', 'secondary stop', 'i-stop', 'action.stop'),
    done: btn('stop', 'primary finish', 'i-stop', 'action.stop') + btn('break_start', 'secondary', 'i-coffee', 'action.break_start'),
    on_break: btn('break_end', 'primary resume', 'i-return', 'action.break_end') + btn('stop', 'secondary stop', 'i-stop', 'action.stop'),
    finished: btn('resume', 'secondary', 'i-rotate', 'action.resume'),
    finished_short: btn('resume', 'secondary', 'i-rotate', 'action.resume'),
  }[hs] || '';
  $('#actions').innerHTML = html;
}

/* ------------------------------------------------------------ fichaje */

async function doAction(action, button) {
  if (state.busy) return;     // evita dobles clics
  const d = state.today;
  state.busy = true;
  document.querySelectorAll('.action-btn').forEach((b) => { b.disabled = true; });
  button?.classList.add('busy');
  try {
    const res = await api('/api/clock', { method: 'POST', body: { action, expect: d.status } });
    const time = clock(nowMs());
    const msg = {
      start: t('toast.started', { time }),
      break_start: t('toast.break_started'),
      break_end: t('toast.break_ended'),
      stop: res.today.target_s ? t('toast.stopped_bal', { time, bal: signed(res.today.balance_s) }) : t('toast.stopped', { time }),
      resume: t('toast.resumed'),
    }[action];
    toast(msg, 'ok');
    if (action === 'start') askNotifications();
  } catch (e) {
    toast(e.message, e.status === 409 ? 'warn' : 'err', 5000);
  } finally {
    state.busy = false;
    await refreshAll();
  }
}

function askNotifications() {
  if ('Notification' in window && Notification.permission === 'default') Notification.requestPermission().catch(() => {});
}

function celebrate() {
  const key = `wt-celebrated-${state.today.date}`;
  try { if (localStorage.getItem(key)) return; localStorage.setItem(key, '1'); } catch (e) { /* sin almacenamiento */ }
  toast(t('alert.done'), 'party', 8000);
  confetti();
  if ('Notification' in window && Notification.permission === 'granted') {
    try { new Notification(t('notif.title'), { body: t('notif.body') }); } catch (e) { /* ignorar */ }
  }
}

/** Unos pocos papelitos que salen del anillo y caen: una vez al día, ~1,4 s. */
function confetti() {
  if (reducedMotion.matches) return;
  const hero = $('#hero');
  const ring = $('#hero .ring-wrap').getBoundingClientRect();
  const box = hero.getBoundingClientRect();
  const layer = document.createElement('div');
  layer.className = 'confetti';
  hero.append(layer);
  const colors = ['--gold-fill', '--work-fill', '--break-fill'].map((v) => getComputedStyle(hero).getPropertyValue(v));
  const cx = ring.left - box.left + ring.width / 2, cy = ring.top - box.top + ring.height / 2;
  for (let i = 0; i < 22; i++) {
    const piece = document.createElement('i');
    piece.style.left = `${cx}px`;
    piece.style.top = `${cy}px`;
    piece.style.background = colors[i % colors.length];
    layer.append(piece);
    const angle = (i / 22) * Math.PI * 2 + Math.random() * 0.3;
    const dist = 90 + Math.random() * 90;
    const dx = Math.cos(angle) * dist, dy = Math.sin(angle) * dist;
    const spin = (Math.random() - 0.5) * 720;
    piece.animate([
      { transform: 'translate(-50%, -50%) scale(0.6) rotate(0deg)', opacity: 1 },
      { transform: `translate(calc(-50% + ${dx}px), calc(-50% + ${dy}px)) rotate(${spin / 2}deg)`, opacity: 1, offset: 0.45 },
      { transform: `translate(calc(-50% + ${dx * 1.15}px), calc(-50% + ${dy + 120}px)) rotate(${spin}deg)`, opacity: 0 },
    ], { duration: 1400 + Math.random() * 300, easing: 'cubic-bezier(0.23, 1, 0.32, 1)', fill: 'forwards' });
  }
  setTimeout(() => layer.remove(), 1900);
}

/* -------------------------------------------------------- calendario */

const STATUS_CHIP = (c) => ({
  finished: c.color === 'green' ? ['green', 'chip.completed'] : ['red', 'chip.deficit'],
  working: c.color === 'green' ? ['green', 'chip.completed_live'] : ['yellow', 'chip.in_progress'],
  on_break: ['yellow', 'chip.on_break'],
  unclosed: ['yellow', 'chip.unclosed'],
  not_started: ['', 'chip.not_started'],
  none: ['', 'chip.none'],
  future: ['', 'chip.future'],
  nonworking: ['', 'chip.nonworking'],
  off: ['', 'chip.off'],
}[c.status] || ['', c.status]);

function renderCalendar() {
  if (!state.monthData) return;
  const { year, month } = state.cal;
  const first = `${year}-${pad(month)}-01`;
  $('#monthTitle').textContent = longDate(first, { month: 'long', year: 'numeric' });
  $('#calWeekdays').innerHTML = [0, 1, 2, 3, 4, 5, 6].map((i) => `<span>${t(`weekday.short.${i}`)}</span>`).join('');
  const todayKey = dateKey(nowMs());
  const lead = weekdayOf(first);
  const cells = [];
  for (let i = 0; i < lead; i++) cells.push('<span class="cal-day out"></span>');
  for (const c of state.monthData.days) {
    const n = Number(c.date.slice(8));
    const cls = ['cal-day', c.color !== 'gray' ? c.color : '',
      c.date === todayKey ? 'today' : '', c.date === state.selected ? 'selected' : '',
      !c.workday ? 'weekend' : ''].filter(Boolean).join(' ');
    const mark = (c.registered && c.mode === 'off' ? icon('i-palm')
      : (c.profile === 'summer' && c.target_s ? icon('i-sun') : '') + (c.mode === 'remote' && c.workday ? icon('i-home') : ''))
      + (c.has_notes ? icon('i-note') : '');
    const hours = c.clock_in ? shortDur(c.worked_s) : '';
    const pct = c.target_s ? Math.min(100, (c.worked_s / c.target_s) * 100) : (c.clock_in ? 100 : 0);
    const bal = c.status === 'finished' && Math.abs(c.balance_s) >= 60
      ? `<span class="bal">${c.balance_s > 0 ? '+' : '−'}${shortDur(Math.abs(c.balance_s))}</span>` : '';
    const title = `${longDate(c.date)}: ${t(STATUS_CHIP(c)[1])}${hours ? `, ${t('cal.worked', { hours })}` : ''}${c.has_notes ? `, ${t('cal.with_notes')}` : ''}`;
    cells.push(`<button class="${cls}" data-date="${c.date}" title="${esc(title)}" aria-label="${esc(title)}" aria-pressed="${c.date === state.selected}">
      <span class="n">${n}</span>${mark ? `<span class="mk">${mark}</span>` : ''}
      <span><span class="row"><span class="h">${hours}</span>${bal}</span>${c.clock_in ? `<span class="bar"><span style="width:${pct}%"></span></span>` : ''}</span></button>`);
  }
  $('#calGrid').innerHTML = cells.join('');
}

function selectDate(key) {
  state.selected = key;
  const [y, m] = key.split('-').map(Number);
  const weekChanged = !state.weekData || key < state.weekData.from || key > state.weekData.to;
  state.weekDate = key;
  if (state.cal.year !== y || state.cal.month !== m) {
    state.cal = { year: y, month: m };
    loadMonth().catch((e) => toast(e.message, 'err'));
  } else {
    renderCalendar();
    renderDetail();
  }
  if (weekChanged) loadWeek().catch((e) => toast(e.message, 'err'));
  else renderWeek();
}

function renderDetail() {
  const box = $('#dayDetail');
  const set = (html) => { if (box.dataset.html !== html) { box.innerHTML = html; box.dataset.html = html; } };
  const c = state.monthData?.days.find((d) => d.date === state.selected);
  if (!c) {
    set(`<div class="empty-state">${icon('i-calendar')}<span>${esc(t('detail.pick'))}</span></div>`);
    return;
  }
  const [chipCls, chipKey] = STATUS_CHIP(c);
  const head = `<div class="detail-head"><div><h3>${longDate(c.date, { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}</h3>
      <div class="chips"><span class="chip ${chipCls}">${esc(t(chipKey))}</span>${c.workday || c.registered ? `<span class="chip">${icon(MODE_ICONS[c.mode])}${esc(modeLabel(c.mode))}</span>` : ''}${profileChip(c)}</div></div></div>`;

  if (!c.registered) {
    const canAdd = c.status !== 'future';
    set(`${head}<div class="empty-state">${icon('i-calendar')}
      <span>${esc(t(c.status === 'future' ? 'detail.future' : 'detail.empty'))}</span>
      ${c.target_s ? `<span class="small">${esc(t('detail.planned', { dur: human(c.target_s) }))}</span>` : ''}
      <button class="primary-btn" data-edit="${c.date}">${icon(canAdd ? 'i-plus' : 'i-edit')}${esc(t(canAdd ? 'detail.register' : 'detail.plan'))}</button></div>`);
    return;
  }

  const n = c.breaks.length;
  const breaks = c.breaks.map((b, i) => `<dt class="small">· ${clock(b.start)} – ${b.end ? clock(b.end) : esc(t('tl.ongoing'))}${b.note ? `<span class="kv-note">${icon('i-note')}${esc(b.note)}</span>` : ''}</dt>
    <dd class="small">${human(b.duration_s)}${noteButton(`${i}`, b.note)}</dd>`).join('');
  set(`${head}
    <dl class="kv" data-date="${c.date}">
      <dt>${esc(t('detail.in'))}</dt><dd>${c.clock_in ? clock(c.clock_in) : '—'}</dd>
      <dt>${esc(t('detail.out'))}</dt><dd>${c.clock_out ? clock(c.clock_out) : c.clock_in ? (c.status === 'unclosed' ? `<span class="pend">${esc(t('detail.unclosed'))}</span>` : esc(t('detail.ongoing'))) : '—'}</dd>
      <dt>${esc(t('detail.breaks'))}</dt><dd>${n ? esc(t(n === 1 ? 'detail.breaks_one' : 'detail.breaks_many', { dur: human(c.break_s), n })) : '—'}</dd>
      ${breaks}
      <div class="divider"></div>
      <dt>${esc(t('detail.worked'))}</dt><dd>${dur(c.worked_s)}</dd>
      <dt>${esc(t('detail.required'))}</dt><dd>${dur(c.target_s)}${c.custom_targets ? ` <span class="muted small">${esc(t('detail.manual'))}</span>` : ''}</dd>
      <dt>${esc(balanceLabel(c))}</dt><dd>${balanceHtml(c)}</dd>
    </dl>
    ${c.notes
      ? `<button type="button" class="notes" data-note="day" data-date="${c.date}"><span class="notes-head">${icon('i-note')}${esc(t('detail.notes'))}</span>${esc(c.notes)}</button>`
      : ''}
    <div class="detail-actions">
      <button class="ghost-btn" data-edit="${c.date}">${icon('i-edit')}${esc(t('common.edit'))}</button>
      ${c.notes ? '' : `<button class="ghost-btn" data-note="day" data-date="${c.date}">${icon('i-note')}${esc(t('detail.add_note'))}</button>`}
      <button class="danger-btn" data-delete="${c.date}">${icon('i-trash')}${esc(t('common.delete'))}</button>
    </div>`);
}

function profileChip(c) {
  if (!c.profile || !(c.workday || c.profile_source === 'manual') || c.mode === 'off') return '';
  const ic = c.profile === 'summer' ? 'i-sun' : 'i-clock';
  return `<span class="chip">${icon(ic)}${esc(profileName(c.profile))}${c.profile_source === 'manual' ? esc(t('profile.manual_suffix')) : ''}</span>`;
}

function balanceLabel(c) {
  if (c.status === 'working' || c.status === 'on_break') return t(c.extra_s > 0 ? 'bal.extra' : 'bal.pending');
  if (c.status === 'finished') return t(c.balance_s >= 0 ? 'bal.extra' : 'bal.deficit');
  return t('bal.label');
}

function balanceHtml(c) {
  if (c.status === 'working' || c.status === 'on_break') {
    return c.extra_s > 0 ? `<span class="pos">+${dur(c.extra_s)}</span>` : `<span class="pend">${dur(c.pending_s, true)}</span>`;
  }
  if (c.status === 'finished') {
    const cls = c.balance_s >= 1 ? 'pos' : c.balance_s <= -1 ? 'neg' : '';
    return `<span class="${cls}">${signed(c.balance_s)}</span>`;
  }
  if (c.status === 'unclosed') return `<span class="pend">${esc(t('bal.no_out'))}</span>`;
  return '—';
}

function renderWeek() {
  const w = state.weekData;
  if (!w) return;
  $('#weekRange').textContent = `${longDate(w.from, { day: 'numeric', month: 'short' })} – ${longDate(w.to, { day: 'numeric', month: 'short', year: 'numeric' })}`;
  const todayKey = dateKey(nowMs());
  $('#weekBody').innerHTML = w.days.map((c) => {
    const pct = c.target_s ? Math.min(100, (c.worked_s / c.target_s) * 100) : (c.clock_in ? 100 : 0);
    const bar = c.clock_in ? `<div class="mini-bar"><span class="${c.color}" style="width:${pct}%"></span></div>` : '';
    return `<tr data-date="${c.date}" class="${c.date === todayKey ? 'is-today' : ''}">
      <td class="day-cell">${esc(weekdayName(c.weekday))}<span>${Number(c.date.slice(8))}</span>${c.has_notes ? `<i class="note-dot" title="${esc(t('cal.with_notes'))}"></i>` : ''}</td>
      <td class="hide-sm">${c.clock_in ? clock(c.clock_in) : '—'}</td>
      <td class="hide-sm">${c.clock_out ? clock(c.clock_out) : c.clock_in ? '<span class="pend">…</span>' : '—'}</td>
      <td class="hide-sm">${c.break_s ? human(c.break_s) : '—'}</td>
      <td>${c.clock_in ? dur(c.worked_s) : (c.status === 'off' ? `<span class="muted">${esc(t('mode.off'))}</span>` : '—')}${bar}</td>
      <td class="hide-xs">${c.target_s ? dur(c.target_s) : '—'}</td>
      <td class="num">${balanceHtml(c)}</td></tr>`;
  }).join('');
  const s = w.summary;
  const cls = s.balance_s >= 1 ? 'pos' : s.balance_s <= -1 ? 'neg' : '';
  $('#weekFoot').innerHTML = `<tr><td>${esc(t('week.total'))}</td><td class="hide-sm"></td><td class="hide-sm"></td><td class="hide-sm"></td>
    <td>${dur(s.worked_s)}</td><td class="hide-xs">${dur(s.target_s)}</td>
    <td class="num"><span class="${cls}">${signed(s.balance_s)}</span>${s.pending_s ? `<div class="small pend">${esc(t('week.pending', { dur: dur(s.pending_s, true) }))}</div>` : ''}</td></tr>`;
}

/* ----------------------------------------------------- editor de día */

const dayDialog = $('#dayDialog');
let editing = null;   // { date, isNew, registered, auto }

function setSegment(el, value) {
  el.querySelectorAll('button').forEach((b) => b.classList.toggle('active', b.dataset.value === value));
  el.dataset.value = value;
}

function setTime(input, full) {
  input.value = full ? full.slice(0, 5) : '';
  input.dataset.full = full || '';
}

/** Devuelve HH:MM:SS original si el usuario no cambió el minuto (no perder segundos). */
function getTime(input) {
  const v = input.value;
  if (!v) return '';
  return input.dataset.full && input.dataset.full.slice(0, 5) === v.slice(0, 5) ? input.dataset.full : v;
}

const toSec = (hhmmss) => {
  if (!hhmmss) return null;
  const [h, m, s = 0] = hhmmss.split(':').map(Number);
  return h * 3600 + m * 60 + s;
};
const minutesToHM = (m) => `${Math.floor(m / 60)}:${pad(m % 60)}`;
function hmToMinutes(text) {
  const m = /^\s*(\d{1,2})(?::(\d{2}))?\s*$/.exec(text || '');
  if (!m || Number(m[2] || 0) > 59) return null;
  return Number(m[1]) * 60 + Number(m[2] || 0);
}
const profileOptions = (selected) =>
  PROFILE_KEYS.map((k) => `<option value="${k}" ${k === selected ? 'selected' : ''}>${esc(profileName(k))}</option>`).join('');

function addBreakRow(start = '', end = '', note = '') {
  const row = document.createElement('div');
  row.className = 'break-row';
  row.innerHTML = `<input type="time" data-f="start" aria-label="${esc(t('ed.break_start'))}"><input type="time" data-f="end" aria-label="${esc(t('ed.break_end'))}">
    <span class="dur"></span><button type="button" class="icon-btn small" aria-label="${esc(t('ed.remove_break'))}">${icon('i-x')}</button>
    <label class="break-note">${icon('i-note')}<input type="text" data-f="note" maxlength="${MAX_BREAK_NOTE}" placeholder="${esc(t('ed.break_note'))}"></label>`;
  setTime(row.querySelector('[data-f="start"]'), start);
  setTime(row.querySelector('[data-f="end"]'), end);
  row.querySelector('[data-f="note"]').value = note || '';
  row.querySelector('button').addEventListener('click', () => { row.remove(); updatePreview(); });
  $('#fBreaks').append(row);
}

async function openEditor(date, isNew = false) {
  let c;
  try {
    c = await api(`/api/days/${date}`);
  } catch (e) {
    toast(e.message, 'err');
    return;
  }
  editing = { date, isNew, registered: c.registered, status: c.status, auto: c.auto };
  $('#dayDialogTitle').textContent = t(c.registered ? 'ed.edit' : 'ed.new');
  $('#dayDialogSub').textContent = longDate(date, { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
  $('#fDate').value = date;
  $('#fDate').disabled = !isNew;
  $('#fDate').max = dateKey(nowMs());
  setSegment($('#fMode'), c.mode);
  const autoKey = c.auto.profile_source === 'period' ? 'profile.auto_period' : 'profile.auto';
  $('#fProfile').innerHTML = `<option value="">${esc(t(autoKey, { name: profileName(c.auto.profile) }))}</option>`
    + profileOptions(c.profile_source === 'manual' ? c.profile : '');
  setTime($('#fIn'), c.local.clock_in);
  setTime($('#fOut'), c.local.clock_out);
  $('#fBreaks').innerHTML = '';
  c.local.breaks.forEach((b) => addBreakRow(b.start, b.end, b.note));
  $('#fTarget').value = minutesToHM(c.target_minutes);
  $('#fMinBreak').value = c.min_break_minutes;
  $('#fOptBreak').value = c.optional_break_minutes;
  $('#fNotes').value = c.notes || '';
  $('#fDelete').hidden = !c.registered;
  $('#fError').hidden = true;
  updatePreview();
  if (!dayDialog.open) dayDialog.showModal();
}

/** Al elegir otro perfil, el formulario adopta sus objetivos (se pueden retocar después). */
function applyProfileToForm() {
  const key = $('#fProfile').value;
  const src = key ? state.settings.profiles[key] : editing.auto;
  $('#fTarget').value = minutesToHM(src.target_minutes);
  $('#fMinBreak').value = src.min_break_minutes;
  $('#fOptBreak').value = src.optional_break_minutes;
  updatePreview();
}

function collectForm() {
  const target = hmToMinutes($('#fTarget').value);
  if (target === null) throw new Error(t('ed.target_fmt'));
  return {
    mode: $('#fMode').dataset.value,
    profile: $('#fProfile').value,
    clock_in: getTime($('#fIn')),
    clock_out: getTime($('#fOut')),
    breaks: [...$('#fBreaks').children].map((row) => ({
      start: getTime(row.querySelector('[data-f="start"]')),
      end: getTime(row.querySelector('[data-f="end"]')),
      note: row.querySelector('[data-f="note"]').value.trim(),
    })),
    target_minutes: target,
    min_break_minutes: Number($('#fMinBreak').value || 0),
    optional_break_minutes: Number($('#fOptBreak').value || 0),
    notes: $('#fNotes').value,
  };
}

function updatePreview() {
  if (!dayDialog.open && !editing) return;
  const box = $('#fPreview');
  const inS = toSec(getTime($('#fIn')));
  const isToday = $('#fDate').value === dateKey(nowMs());
  let outS = toSec(getTime($('#fOut')));
  if (outS === null && isToday && inS !== null) outS = localSeconds(nowMs());
  let brk = 0;
  for (const row of $('#fBreaks').children) {
    const s = toSec(getTime(row.querySelector('[data-f="start"]'))), e = toSec(getTime(row.querySelector('[data-f="end"]'))) ?? outS;
    const d = s !== null && e !== null && e > s ? e - s : 0;
    brk += d;
    row.querySelector('.dur').textContent = d ? human(d) : '';
  }
  const target = (hmToMinutes($('#fTarget').value) ?? 0) * 60;
  if (inS === null || outS === null || outS <= inS) {
    box.innerHTML = `<span>${esc(t(isToday ? 'ed.need_in' : 'ed.need_in_out'))}</span>`;
    return;
  }
  const worked = Math.max(0, outS - inS - brk);
  const diff = worked - target;
  const open = toSec(getTime($('#fOut'))) === null;
  box.innerHTML = `<span>${t(open ? 'ed.prev_worked_now' : 'ed.prev_worked', { dur: human(worked) })}</span>
    <span>${t('ed.prev_break', { dur: human(brk) })}</span>
    <span>${esc(t(diff >= 0 ? 'ed.prev_extra' : open ? 'ed.prev_pending' : 'ed.prev_deficit'))}: <b class="${diff >= 0 ? 'pos' : open ? 'pend' : 'neg'}">${human(Math.abs(diff))}</b></span>`;
}

function showError(el, message) {
  el.hidden = true;
  void el.offsetWidth;            // reinicia la animación de error
  el.textContent = message;
  el.hidden = false;
}

async function saveEditor(ev) {
  ev.preventDefault();
  const err = $('#fError');
  err.hidden = true;
  let body;
  try {
    body = collectForm();
  } catch (e) {
    showError(err, e.message); return;
  }
  const date = $('#fDate').value;
  if (!date) { showError(err, t('ed.need_date')); return; }
  const save = $('#fSave');
  save.classList.add('is-saving');
  try {
    await api(`/api/days/${date}`, { method: 'PUT', body });
    closeDialog(dayDialog);
    toast(t('toast.saved'), 'ok');
    state.selected = date;
    await refreshAll();
    selectDate(date);
    flashDay(date);
  } catch (e) {
    showError(err, e.message);
  } finally {
    save.classList.remove('is-saving');
  }
}

/** Confirma visualmente el guardado: un pulso en la celda del calendario. */
function flashDay(date) {
  requestAnimationFrame(() => {
    const cell = $(`.cal-day[data-date="${date}"]`);
    if (!cell) return;
    cell.classList.remove('saved');
    void cell.offsetWidth;
    cell.classList.add('saved');
  });
}

async function deleteDay(date) {
  const ok = await confirmDialog({
    title: t('ed.delete_title'),
    text: t('ed.delete_text', { date: longDate(date, { weekday: 'long', day: 'numeric', month: 'long' }) }),
    ok: t('common.delete'), danger: true,
  });
  if (!ok) return false;
  try {
    await api(`/api/days/${date}`, { method: 'DELETE' });
    toast(t('toast.deleted'), 'ok');
    await refreshAll();
    return true;
  } catch (e) {
    toast(e.message, 'err');
    return false;
  }
}

/* --------------------------------------------------- notas rápidas */

const noteDialog = $('#noteDialog');
let noting = null;   // { date, target }

function findDay(date) {
  if (state.today?.date === date) return state.today;
  return state.monthData?.days.find((d) => d.date === date) || state.weekData?.days.find((d) => d.date === date);
}

function openNote(date, target) {
  const day = findDay(date) || { notes: '', breaks: [] };
  const isDay = target === 'day';
  const brk = isDay ? null : day.breaks[Number(target)];
  noting = { date, target };
  $('#noteTitle').textContent = t(isDay ? 'note.day_title' : 'note.break_title');
  $('#noteSub').textContent = isDay
    ? longDate(date, { weekday: 'long', day: 'numeric', month: 'long' })
    : t('note.break_sub', { start: clock(brk.start), end: brk.end ? clock(brk.end) : t('tl.now') });
  const text = $('#noteText');
  text.maxLength = isDay ? 2000 : MAX_BREAK_NOTE;
  text.value = (isDay ? day.notes : brk?.note) || '';
  $('#noteDelete').hidden = !text.value;
  $('#noteError').hidden = true;
  $('#noteChips').innerHTML = ['note.s1', 'note.s2', 'note.s3', 'note.s4']
    .map((k) => `<button type="button" class="note-chip">${esc(t(k))}</button>`).join('');
  updateNoteCount();
  noteDialog.showModal();
  text.focus();
}

function updateNoteCount() {
  const text = $('#noteText');
  $('#noteCount').textContent = `${text.value.length}/${text.maxLength}`;
  $('#noteCount').classList.toggle('near', text.value.length > text.maxLength * 0.9);
}

async function saveNote(text) {
  if (!noting) return;
  const btn = $('#noteSave');
  btn.classList.add('is-saving');
  try {
    await api(`/api/days/${noting.date}/note`, { method: 'POST', body: { target: noting.target, text } });
    closeDialog(noteDialog);
    toast(t(text ? 'toast.note_saved' : 'toast.note_deleted'), 'ok');
    const date = noting.date;
    await refreshAll();
    flashDay(date);
  } catch (e) {
    showError($('#noteError'), e.message);
  } finally {
    btn.classList.remove('is-saving');
  }
}

/* ------------------------------------------------------------ ajustes */

const settingsDialog = $('#settingsDialog');

function addPeriodRow(start = '', end = '') {
  const box = $('#sPeriods');
  box.querySelector('.empty-periods')?.remove();
  const row = document.createElement('div');
  row.className = 'period-row';
  row.innerHTML = `<span>${esc(t('period.from'))}</span><input type="date" data-f="start" value="${start}" required>
    <span>${esc(t('period.to'))}</span><input type="date" data-f="end" value="${end}" required>
    <button type="button" class="icon-btn small" aria-label="${esc(t('period.remove'))}">${icon('i-x')}</button>`;
  row.querySelector('button').addEventListener('click', () => {
    row.remove();
    if (!box.children.length) box.innerHTML = `<span class="empty-periods">${esc(t('set.no_periods'))}</span>`;
  });
  box.append(row);
}

/** Pestañas de ajustes con indicador deslizante. */
function selectTab(name, { focus = false } = {}) {
  const tabs = [...document.querySelectorAll('#settingsTabs [role="tab"]')];
  tabs.forEach((tab) => {
    const on = tab.dataset.tab === name;
    tab.setAttribute('aria-selected', String(on));
    tab.tabIndex = on ? 0 : -1;
    if (on && focus) tab.focus();
  });
  document.querySelectorAll('#settingsDialog .tab-panel').forEach((p) => { p.hidden = p.dataset.panel !== name; });
  const active = tabs.find((tab) => tab.dataset.tab === name);
  const ind = $('#settingsTabs .tab-indicator');
  if (active && ind) {
    ind.style.width = `${active.offsetWidth}px`;
    ind.style.transform = `translateX(${active.offsetLeft}px)`;
  }
  settingsDialog.dataset.tab = name;
  $('#sSave').hidden = name === 'data';
  if (name === 'shortcuts' && window.renderShortcutSettings) renderShortcutSettings();
  if (name === 'data' && window.prepareDataTab) prepareDataTab();
}

function fillSettingsForm() {
  const s = state.settings;
  $('#sProfiles').innerHTML = PROFILE_KEYS.map((k) => {
    const p = s.profiles[k];
    return `<tr data-profile="${k}">
      <td>${esc(profileName(k))}</td>
      <td><input type="time" data-f="start" value="${p.start}" aria-label="${esc(t('th.ref_in'))}"></td>
      <td><input type="time" data-f="end" value="${p.end}" aria-label="${esc(t('th.ref_out'))}"></td>
      <td><input type="text" data-f="target" value="${minutesToHM(p.target_minutes)}" inputmode="numeric" aria-label="${esc(t('th.effective'))}"></td>
      <td><input type="number" data-f="min_break_minutes" value="${p.min_break_minutes}" min="0" max="600" aria-label="${esc(t('th.min'))}"></td>
      <td><input type="number" data-f="optional_break_minutes" value="${p.optional_break_minutes}" min="0" max="600" aria-label="${esc(t('th.opt'))}"></td></tr>`;
  }).join('');
  $('#sWeekdays').innerHTML = [0, 1, 2, 3, 4, 5, 6].map((i) => {
    const d = s.weekdays[i];
    return `<tr data-day="${i}" class="${d.workday ? '' : 'disabled'}">
      <td>${esc(weekdayName(i))}</td>
      <td><label class="switch"><input type="checkbox" data-f="workday" ${d.workday ? 'checked' : ''} aria-label="${esc(t('th.workday'))}"><span></span></label></td>
      <td><select data-f="profile" aria-label="${esc(t('th.profile'))}">${profileOptions(d.profile)}</select></td>
      <td><div class="segmented" data-f="mode">
        <button type="button" data-value="office">${icon('i-building')}${esc(t('mode.office'))}</button>
        <button type="button" data-value="remote">${icon('i-home')}${esc(t('mode.remote_short'))}</button></div></td></tr>`;
  }).join('');
  $('#sWeekdays').querySelectorAll('tr').forEach((tr) => {
    setSegment(tr.querySelector('[data-f="mode"]'), s.weekdays[tr.dataset.day].mode);
    tr.querySelector('[data-f="workday"]').addEventListener('change', (e) => tr.classList.toggle('disabled', !e.target.checked));
  });
  $('#sPeriods').innerHTML = '';
  if (s.summer.periods.length) s.summer.periods.forEach((p) => addPeriodRow(p.start, p.end));
  else $('#sPeriods').innerHTML = `<span class="empty-periods">${esc(t('set.no_periods'))}</span>`;
  $('#sSummerDays').innerHTML = [0, 1, 2, 3, 4, 5, 6].map((i) =>
    `<button type="button" data-day="${i}" class="${s.summer.weekdays.includes(i) ? 'active' : ''}" aria-pressed="${s.summer.weekdays.includes(i)}" aria-label="${esc(weekdayName(i))}">${esc(t(`weekday.short.${i}`))}</button>`).join('');
  setSegment($('#sTheme'), s.theme);
  setSegment($('#sTimeFormat'), s.time_format);
  setSegment($('#sDurFormat'), s.duration_format);
  setSegment($('#sLang'), s.language || currentLang());
}

function openSettings(tab = 'schedule') {
  fillSettingsForm();
  if (window.loadShortcutDraft) loadShortcutDraft();
  $('#sError').hidden = true;
  if (!settingsDialog.open) settingsDialog.showModal();
  requestAnimationFrame(() => selectTab(tab));
}

async function saveSettings(ev) {
  ev.preventDefault();
  const err = $('#sError');
  err.hidden = true;
  const profiles = {}, weekdays = {}, periods = [];
  try {
    $('#sProfiles').querySelectorAll('tr').forEach((tr) => {
      const f = (k) => tr.querySelector(`[data-f="${k}"]`);
      const target = hmToMinutes(f('target').value);
      if (target === null) throw new Error(t('set.target_fmt', { name: profileName(tr.dataset.profile) }));
      profiles[tr.dataset.profile] = {
        start: f('start').value,
        end: f('end').value,
        target_minutes: target,
        min_break_minutes: Number(f('min_break_minutes').value || 0),
        optional_break_minutes: Number(f('optional_break_minutes').value || 0),
      };
    });
    $('#sWeekdays').querySelectorAll('tr').forEach((tr) => {
      const f = (k) => tr.querySelector(`[data-f="${k}"]`);
      weekdays[tr.dataset.day] = { workday: f('workday').checked, profile: f('profile').value, mode: f('mode').dataset.value };
    });
    $('#sPeriods').querySelectorAll('.period-row').forEach((row, i) => {
      const start = row.querySelector('[data-f="start"]').value, end = row.querySelector('[data-f="end"]').value;
      if (!start || !end) throw new Error(t('set.period_missing', { n: i + 1 }));
      periods.push({ start, end });
    });
  } catch (e) {
    showError(err, e.message); return;
  }
  const summerDays = [...$('#sSummerDays').querySelectorAll('button.active')].map((b) => Number(b.dataset.day));
  const language = $('#sLang').dataset.value;
  const save = $('#sSave');
  save.classList.add('is-saving');
  try {
    await api('/api/settings', {
      method: 'PUT',
      body: {
        profiles,
        weekdays,
        summer: { periods, weekdays: summerDays },
        theme: $('#sTheme').dataset.value,
        time_format: $('#sTimeFormat').dataset.value,
        duration_format: $('#sDurFormat').dataset.value,
        language,
        shortcuts: window.shortcutDraft ? shortcutDraft() : undefined,
      },
    });
    fmtCache.clear();
    closeDialog(settingsDialog);
    if (language !== currentLang()) await switchLanguage(language, { save: false });
    toast(t('toast.settings_saved'), 'ok');
    await refreshAll();
  } catch (e) {
    showError(err, e.message);
  } finally {
    save.classList.remove('is-saving');
  }
}

/* ------------------------------------------------------------ idioma */

/** Cambia el idioma al instante: retraduce lo estático y repinta lo dinámico. */
async function switchLanguage(code, { save = true } = {}) {
  await loadLanguage(code);
  fmtCache.clear();
  $('#langCode').textContent = code.toUpperCase();
  if (state.settings) state.settings.language = code;
  if (save) {
    try { await api('/api/settings', { method: 'PUT', body: { language: code } }); } catch (e) { toast(e.message, 'err'); }
  }
  rerenderAll();
}

function rerenderAll() {
  if (!state.today) return;
  const stats = $('#stats');
  if (stats.dataset.built) stats.querySelectorAll('[data-f="rows"]').forEach((dl) => { dl.dataset.html = ''; });
  $('#heroAlerts').dataset.html = '';
  renderStatic();
  tick();
  renderCalendar();
  renderDetail();
  renderWeek();
  if (settingsDialog.open) { fillSettingsForm(); selectTab(settingsDialog.dataset.tab || 'schedule'); }
}

async function toggleLanguage() {
  const next = currentLang() === 'es' ? 'en' : 'es';
  try {
    await switchLanguage(next);
    toast(t('toast.lang'), 'info', 2200);
  } catch (e) {
    toast(e.message, 'err');
  }
}

/* ---------------------------------------------------------- cerrar */

async function quitApp() {
  const ok = await confirmDialog({ title: t('quit.title'), text: t('quit.text'), ok: t('quit.title') });
  if (!ok) return;
  try {
    await api('/api/shutdown', { method: 'POST', body: { confirm: true } });
  } catch (e) { /* si ya estaba cerrado, da igual */ }
  state.closed = true;
  $('#closedScreen').hidden = false;
  document.title = 'Jornada';
}

async function toggleTheme() {
  const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
  if (document.startViewTransition && !reducedMotion.matches) document.startViewTransition(() => applyTheme(next));
  else applyTheme(next);
  try {
    state.settings = await api('/api/settings', { method: 'PUT', body: { theme: next } });
  } catch (e) {
    toast(e.message, 'err');
  }
}

/** Lleva una sección a la vista y le da el foco (atajos «Abrir calendario/estadísticas»). */
function focusSection(id) {
  const el = document.getElementById(id);
  el.scrollIntoView({ behavior: reducedMotion.matches ? 'auto' : 'smooth', block: 'start' });
  el.focus({ preventScroll: true });
  el.classList.remove('flash');
  void el.offsetWidth;
  el.classList.add('flash');
}

/* ------------------------------------------------------------ eventos */

function bindEvents() {
  $('#actions').addEventListener('click', (e) => {
    const b = e.target.closest('[data-action]');
    if (b) doAction(b.dataset.action, b);
  });
  $('#editTodayBtn').addEventListener('click', () => state.today && openEditor(state.today.date));
  $('#dayNoteBtn').addEventListener('click', () => state.today && openNote(state.today.date, 'day'));
  $('#timeline').addEventListener('click', (e) => {
    const b = e.target.closest('[data-note]');
    if (b && state.today) openNote(state.today.date, b.dataset.note);
  });
  $('#addDayBtn').addEventListener('click', () => {
    const today = dateKey(nowMs());
    openEditor(state.selected && state.selected <= today ? state.selected : today, true);
  });
  $('#dataBtn').addEventListener('click', () => openSettings('data'));
  $('#themeBtn').addEventListener('click', toggleTheme);
  $('#langBtn').addEventListener('click', toggleLanguage);
  $('#settingsBtn').addEventListener('click', () => openSettings());
  $('#quitBtn').addEventListener('click', quitApp);
  $('#globalBanner').addEventListener('click', (e) => {
    const b = e.target.closest('[data-fix]');
    if (b) openEditor(b.dataset.fix);
    if (e.target.closest('[data-reload]')) location.reload();
  });

  $('#prevMonth').addEventListener('click', () => shiftMonth(-1));
  $('#nextMonth').addEventListener('click', () => shiftMonth(1));
  $('#calGrid').addEventListener('click', (e) => {
    const b = e.target.closest('[data-date]');
    if (b) selectDate(b.dataset.date);
  });
  $('#dayDetail').addEventListener('click', (e) => {
    const ed = e.target.closest('[data-edit]');
    if (ed) openEditor(ed.dataset.edit);
    const del = e.target.closest('[data-delete]');
    if (del) deleteDay(del.dataset.delete);
    const note = e.target.closest('[data-note]');
    if (note && state.selected) openNote(state.selected, note.dataset.note);
  });

  $('#prevWeek').addEventListener('click', () => { selectDate(addDays(state.weekDate, -7)); slideIn($('#weekBody'), -1); });
  $('#nextWeek').addEventListener('click', () => { selectDate(addDays(state.weekDate, 7)); slideIn($('#weekBody'), 1); });
  $('#thisWeek').addEventListener('click', () => selectDate(dateKey(nowMs())));
  $('#weekBody').addEventListener('click', (e) => {
    const tr = e.target.closest('[data-date]');
    if (tr) selectDate(tr.dataset.date);
  });

  // Diálogos
  document.querySelectorAll('dialog [data-close]').forEach((b) => b.addEventListener('click', () => closeDialog(b.closest('dialog'))));
  document.querySelectorAll('dialog').forEach((d) => d.addEventListener('click', (e) => { if (e.target === d) closeDialog(d, 'cancel'); }));
  document.querySelectorAll('.segmented').forEach((seg) => seg.addEventListener('click', (e) => {
    const b = e.target.closest('button[data-value]');
    if (b) { setSegment(seg, b.dataset.value); updatePreview(); }
  }));
  $('#sWeekdays').addEventListener('click', (e) => {
    const b = e.target.closest('.segmented button[data-value]');
    if (b) setSegment(b.parentElement, b.dataset.value);
  });

  $('#dayForm').addEventListener('submit', saveEditor);
  $('#dayForm').addEventListener('input', updatePreview);
  $('#fAddBreak').addEventListener('click', () => { addBreakRow(); updatePreview(); $('#fBreaks').lastElementChild.querySelector('input').focus(); });
  $('#fDate').addEventListener('change', (e) => { if (e.target.value) openEditor(e.target.value, true); });
  $('#fDelete').addEventListener('click', async () => {
    const date = editing?.date;
    if (date && await deleteDay(date)) closeDialog(dayDialog);
  });
  $('#fProfile').addEventListener('change', applyProfileToForm);

  $('#noteForm').addEventListener('submit', (e) => { e.preventDefault(); saveNote($('#noteText').value.trim()); });
  $('#noteDelete').addEventListener('click', () => saveNote(''));
  $('#noteText').addEventListener('input', updateNoteCount);
  $('#noteChips').addEventListener('click', (e) => {
    const chip = e.target.closest('.note-chip');
    if (!chip) return;
    const text = $('#noteText');
    text.value = chip.textContent;
    updateNoteCount();
    text.focus();
  });

  $('#settingsForm').addEventListener('submit', saveSettings);
  $('#settingsTabs').addEventListener('click', (e) => {
    const tab = e.target.closest('[role="tab"]');
    if (tab) selectTab(tab.dataset.tab);
  });
  $('#settingsTabs').addEventListener('keydown', (e) => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(e.key)) return;
    const tabs = [...document.querySelectorAll('#settingsTabs [role="tab"]')];
    const i = tabs.findIndex((tab) => tab.getAttribute('aria-selected') === 'true');
    const next = e.key === 'Home' ? 0 : e.key === 'End' ? tabs.length - 1 : (i + (e.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length;
    e.preventDefault();
    selectTab(tabs[next].dataset.tab, { focus: true });
  });
  $('#sAddPeriod').addEventListener('click', () => addPeriodRow());
  $('#sSummerDays').addEventListener('click', (e) => {
    const b = e.target.closest('button[data-day]');
    if (b) { b.classList.toggle('active'); b.setAttribute('aria-pressed', String(b.classList.contains('active'))); }
  });

  // Al volver a la pestaña o despertar el equipo, se resincroniza con el servidor.
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refreshAll(); });
  window.addEventListener('focus', () => refreshAll());
  window.addEventListener('resize', () => { if (settingsDialog.open) selectTab(settingsDialog.dataset.tab || 'schedule'); });
}

function shiftMonth(delta) {
  let { year, month } = state.cal;
  month += delta;
  if (month < 1) { month = 12; year--; }
  if (month > 12) { month = 1; year++; }
  state.cal = { year, month };
  loadMonth().then(() => slideIn($('#calGrid'), delta)).catch((e) => toast(e.message, 'err'));
}

/** Entrada direccional corta (el mes siguiente llega desde la derecha). */
function slideIn(el, direction) {
  if (reducedMotion.matches || !el.animate) return;
  el.animate([
    { opacity: 0, transform: `translateX(${direction > 0 ? 14 : -14}px)` },
    { opacity: 1, transform: 'none' },
  ], { duration: 240, easing: 'cubic-bezier(0.23, 1, 0.32, 1)' });
}

/** Cierre animado de los modales (la salida es más rápida que la entrada). */
function closeDialog(dlg, value) {
  if (!dlg.open || dlg.classList.contains('closing')) return;
  if (reducedMotion.matches) { dlg.close(value); return; }
  dlg.classList.add('closing');
  setTimeout(() => { dlg.classList.remove('closing'); dlg.close(value); }, 170);
}

/* -------------------------------------------------------------- inicio */

function renderSkeletons() {
  $('#calGrid').innerHTML = Array.from({ length: 35 }, () => '<span class="cal-day skeleton"></span>').join('');
  $('#stats').innerHTML = Array.from({ length: 4 }, () => '<div class="stat-panel skeleton" style="min-height:150px"></div>').join('');
  $('#weekBody').innerHTML = Array.from({ length: 4 }, () => '<tr><td colspan="7"><div class="skeleton" style="height:18px"></div></td></tr>').join('');
  $('#dayDetail').innerHTML = '<div class="skeleton" style="height:22px;width:60%"></div><div class="skeleton" style="height:140px;margin-top:18px"></div>';
}

async function init() {
  try {
    await loadState();
  } catch (e) {
    toast(e.message, 'err', 8000);
    setTimeout(init, 5000);
    return;
  }
  const today = state.today.date;
  state.selected = today;
  state.weekDate = today;
  state.cal = { year: Number(today.slice(0, 4)), month: Number(today.slice(5, 7)) };
  await Promise.all([loadMonth(), loadWeek()]).catch((e) => toast(e.message, 'err'));

  // Tick alineado al cambio de segundo (los fichajes se guardan en segundos exactos).
  // El siguiente se programa antes de pintar: un fallo en un fotograma se ve en la
  // consola, pero no detiene el reloj.
  const loop = () => { setTimeout(loop, 1005 - (nowMs() % 1000)); tick(); };
  loop();
  setInterval(() => { if (!document.hidden) refreshAll(); }, 60000);
  setInterval(() => { if (document.hidden && !state.closed) api('/api/ping').catch(() => {}); }, 300000);
}

bindEvents();
renderSkeletons();
window.addEventListener('scroll', () => $('.topbar').classList.toggle('scrolled', scrollY > 4), { passive: true });
init();

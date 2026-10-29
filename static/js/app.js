/* ============================================================
   Jornada — frontend
   Los contadores se derivan de la foto que devuelve el servidor
   (marcas guardadas + hora del servidor) y del tiempo real transcurrido,
   nunca de un número que se incremente en memoria.
   ============================================================ */
'use strict';

const TZ = 'Europe/Madrid';
const WEEKDAYS = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo'];
const MODE_INFO = {
  office: { label: 'Oficina', icon: 'i-building' },
  remote: { label: 'Teletrabajo', icon: 'i-home' },
  off: { label: 'Libre', icon: 'i-palm' },
};

const $ = (sel, root = document) => root.querySelector(sel);
const icon = (id) => `<svg><use href="#${id}"/></svg>`;
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

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
  let s = Math.max(0, ceil ? Math.ceil(sec - 1e-6) : Math.floor(sec + 1e-6));
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
  const key = JSON.stringify(opts) + h12;
  if (!fmtCache.has(key)) fmtCache.set(key, new Intl.DateTimeFormat('es-ES', { timeZone: TZ, hour12: h12, ...opts }));
  return fmtCache.get(key);
}

function clock(value, seconds = false) {
  if (value == null) return '—';
  const d = typeof value === 'number' ? new Date(value) : new Date(value);
  return formatter({ hour: '2-digit', minute: '2-digit', ...(seconds ? { second: '2-digit' } : {}) }).format(d);
}

/** Hora grande con los segundos en pequeño. */
function bigClock(ms) {
  const parts = formatter({ hour: '2-digit', minute: '2-digit', second: '2-digit' }).formatToParts(new Date(ms));
  const get = (t) => parts.find((p) => p.type === t)?.value ?? '';
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
  new Intl.DateTimeFormat('es-ES', { timeZone: 'UTC', ...opts }).format(keyToDate(key));

const refMinutes = (hhmm) => { const [h, m] = hhmm.split(':').map(Number); return h * 60 + m; };
function localSeconds(ms) {
  const p = new Intl.DateTimeFormat('en-GB', { timeZone: TZ, hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
    .formatToParts(new Date(ms));
  const g = (t) => Number(p.find((x) => x.type === t).value);
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
    throw new Error('No se puede contactar con el servidor. ¿Está en marcha app.py?');
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
  el.innerHTML = `${icon(ic)}<span>${esc(msg)}</span>`;
  $('#toasts').append(el);
  setTimeout(() => { el.classList.add('out'); setTimeout(() => el.remove(), 260); }, ms);
}

function confirmDialog({ title, text, ok = 'Confirmar', danger = false }) {
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
  applyTheme(data.settings.theme);
  renderStatic();
  tick();
}

async function loadMonth() {
  const { year, month } = state.cal;
  state.monthData = await api(`/api/month/${year}-${pad(month)}`);
  renderCalendar();
  renderDetail();
}

async function loadWeek() {
  state.weekData = await api(`/api/week/${state.weekDate}`);
  renderWeek();
}

async function refreshAll() {
  if (state.closed) return;
  try {
    await loadState();
    await Promise.all([loadMonth(), loadWeek()]);
  } catch (e) {
    toast(e.message, 'err');
  }
}

/* ------------------------------------------------------- cálculo en vivo */

/** Instante en que el trabajo acumulado alcanza el objetivo. */
function completionInstant(t, endMs) {
  if (!t.clock_in || !t.target_s) return null;
  const goal = t.target_s * 1000;
  let acc = 0, cursor = Date.parse(t.clock_in);
  const breaks = t.breaks.map((b) => [Date.parse(b.start), b.end ? Date.parse(b.end) : endMs]).sort((a, b) => a[0] - b[0]);
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
  const t = state.today;
  const now = nowMs();
  const dt = Math.max(0, (now - state.snapAt) / 1000);
  let worked = t.worked_s, brk = t.break_s, cur = t.current_break_s;
  if (t.status === 'working') worked += dt;
  else if (t.status === 'on_break') { brk += dt; cur += dt; }

  const target = t.target_s;
  const remaining = Math.max(0, target - worked);
  const extra = Math.max(0, worked - target);
  const pendingBreak = target ? Math.max(0, t.min_break_s - brk) : 0;
  const optLeft = target ? Math.max(0, t.min_break_s + t.optional_break_s - brk) : 0;
  const inProgress = t.status === 'working' || t.status === 'on_break';

  let exit = null, exitMin = null, exitOpt = null;
  if (inProgress) {
    exitMin = Math.round((now + remaining * 1000) / 1000) * 1000;
    exit = exitMin + Math.ceil(pendingBreak) * 1000;
    exitOpt = exitMin + Math.ceil(optLeft) * 1000;
  } else if (t.status === 'not_started' && target) {
    exitMin = now + target * 1000;
    exit = exitMin + t.min_break_s * 1000;
    exitOpt = exitMin + (t.min_break_s + t.optional_break_s) * 1000;
  } else if (t.status === 'finished') {
    exit = Date.parse(t.clock_out);
  }
  const done = !!target && remaining === 0 && !!t.clock_in;
  const endMs = t.clock_out ? Date.parse(t.clock_out) : now;
  return {
    now, worked, brk, cur, target, remaining, extra, pendingBreak, optLeft, inProgress,
    exit, exitMin, exitOpt, done,
    completedAt: done ? completionInstant(t, endMs) : null,
    progress: target ? Math.min(1, worked / target) : (t.clock_in ? 1 : 0),
  };
}

function heroStatus(t, l) {
  switch (t.status) {
    case 'working': return l.done ? 'done' : 'working';
    case 'on_break': return 'on_break';
    case 'finished': return l.worked + 0.5 >= l.target ? 'finished' : 'finished_short';
    case 'not_started': return t.target_s ? 'idle' : 'off';
    default: return 'off';
  }
}

/* -------------------------------------------------------------- tick */

function tick() {
  const t = state.today;
  if (!t || state.closed) return;
  const now = nowMs();
  $('#liveClock').textContent = clock(now, true);

  if (dateKey(now) !== t.date) {   // cambio de día
    if (!state.rolling) { state.rolling = true; refreshAll().finally(() => { state.rolling = false; }); }
    return;
  }

  const l = live();
  const hs = heroStatus(t, l);
  const hero = $('#hero');
  hero.dataset.status = hs;

  if (state.heroKey !== hs) {
    state.heroKey = hs;
    renderActions(hs);
  }

  // Aviso de jornada completada (solo al cruzar el umbral en vivo).
  if (t.status === 'working' && state.wasDone === false && l.done) celebrate();
  state.wasDone = t.status === 'working' ? l.done : null;

  renderStatusPill(t, hs);
  renderCountdown(t, l, hs);
  renderExit(t, l, hs);
  renderAlerts(t, l, hs);
  renderTiles(t, l);
  renderBreakMeter(t, l);
  renderDayline(t, l);
  renderStats(t, l);

  const exitEl = $('#tlExit');
  if (exitEl && !t.clock_out) exitEl.textContent = l.exit ? clock(l.exit) : '—';

  document.title =
    hs === 'working' ? `${hms(l.remaining, true)} · Jornada` :
    hs === 'done' ? `+${hms(l.extra)} · Jornada` :
    hs === 'on_break' ? `☕ ${hms(l.cur)} · Jornada` : 'Jornada';
}

function renderStatusPill(t, hs) {
  const [cls, text] = {
    idle: ['', 'Sin iniciar'],
    working: ['working', 'Trabajando'],
    done: ['done', 'Jornada completada'],
    on_break: ['on_break', 'Descansando'],
    finished: ['finished', 'Jornada finalizada'],
    finished_short: ['short', 'Finalizada con déficit'],
  }[hs] || ['', t.status === 'off' ? 'Día libre' : 'No laborable'];
  $('#statusPill').className = `status-pill ${cls}`;
  $('#statusText').textContent = text;
}

function renderCountdown(t, l, hs) {
  const label = $('#countLabel'), value = $('#countdown'), sub = $('#progressText');
  const pct = Math.floor(l.progress * 100);
  let ring = l.progress;
  switch (hs) {
    case 'idle':
      label.textContent = 'Objetivo de hoy';
      value.textContent = hms(t.target_s);
      sub.textContent = 'Aún no has fichado';
      break;
    case 'working':
      label.textContent = 'Te queda';
      value.textContent = hms(l.remaining, true);
      sub.textContent = `${pct} % completado`;
      break;
    case 'done':
      label.textContent = 'Tiempo extra';
      value.textContent = '+' + hms(l.extra);
      sub.textContent = '100 % completado';
      break;
    case 'on_break':
      label.textContent = l.done ? 'Tiempo extra · en pausa' : 'Te queda · en pausa';
      value.textContent = l.done ? '+' + hms(l.extra) : hms(l.remaining, true);
      sub.textContent = `${pct} % completado`;
      break;
    case 'finished':
    case 'finished_short': {
      const diff = l.worked - l.target;
      label.textContent = !l.target ? 'Trabajado' : diff >= 1 ? 'Tiempo extra' : diff <= -1 ? 'Te faltó' : 'Jornada exacta';
      value.textContent = !l.target ? hms(l.worked) : (diff >= 1 ? '+' : diff <= -1 ? '−' : '') + hms(Math.abs(diff));
      sub.textContent = `Trabajado ${hms(l.worked)}`;
      break;
    }
    default:
      label.textContent = 'Hoy';
      value.textContent = t.status === 'off' ? 'Libre' : 'Descanso';
      sub.textContent = t.status === 'off' ? 'Día marcado como libre' : 'Día no laborable';
      ring = 0;
  }
  $('#ringBar').style.strokeDasharray = `${Math.max(0, Math.min(1, ring)) * 1000} 1000`;
}

function renderExit(t, l, hs) {
  const label = $('#exitLabel'), time = $('#exitTime'), note = $('#exitNote');
  const ref = t.ref_end ? `Referencia ${t.ref_start}–${t.ref_end}` : '';
  let html = '—', text = '';
  switch (hs) {
    case 'idle':
      label.textContent = 'Si empiezas ahora, saldrías a las';
      html = bigClock(l.exit);
      text = t.min_break_s ? `Incluye ${human(t.min_break_s)} de descanso obligatorio · ${ref}` : ref;
      break;
    case 'working':
      label.textContent = 'Puedes salir a las';
      html = bigClock(l.exit);
      if (l.pendingBreak > 0) {
        text = `Incluye <b>${human(l.pendingBreak, true)}</b> de descanso obligatorio pendiente · sin él: <b>${clock(l.exitMin)}</b>`;
      } else if (l.optLeft > 0) {
        text = `Con el descanso opcional restante (${human(l.optLeft, true)}): <b>${clock(l.exitOpt)}</b>`;
      } else {
        text = refDiff(t, l.exit);
      }
      break;
    case 'done':
      label.textContent = 'Jornada completada a las';
      html = l.completedAt ? bigClock(l.completedAt) : '—';
      text = `Llevas <b>+${human(l.extra)}</b> de tiempo extra`;
      break;
    case 'on_break':
      label.textContent = l.done ? 'Jornada ya completada' : 'Saldrás a las';
      html = l.done ? (l.completedAt ? bigClock(l.completedAt) : '—') : bigClock(l.exit);
      if (l.done) text = 'Puedes finalizar la jornada cuando quieras';
      else if (l.pendingBreak > 0) text = `Si vuelves ahora: <b>${clock(l.exitMin)}</b> (sin completar el descanso mínimo)`;
      else if (l.optLeft > 0) text = `Te quedan <b>${human(l.optLeft, true)}</b> de descanso opcional sin retrasar tu salida habitual`;
      else text = 'Cada minuto más de descanso retrasa tu salida';
      break;
    case 'finished':
    case 'finished_short':
      label.textContent = 'Saliste a las';
      html = bigClock(Date.parse(t.clock_out));
      text = `Trabajado <b>${human(l.worked)}</b> de ${human(l.target)}`;
      break;
    default:
      label.textContent = 'Hoy no tienes jornada';
      html = '—';
      text = 'Si trabajas hoy, ficha igualmente: contará como tiempo extra.';
  }
  if (time.innerHTML !== html) time.innerHTML = html;
  if (note.innerHTML !== text) note.innerHTML = text;
}

function refDiff(t, exitMs) {
  if (!t.ref_end || !exitMs) return '';
  const diffMin = Math.round((refMinutes(t.ref_end) * 60 - localSeconds(exitMs)) / 60);
  if (diffMin > 0) return `${human(diffMin * 60)} antes de tu salida de referencia (${t.ref_end})`;
  if (diffMin < 0) return `${human(-diffMin * 60)} después de tu salida de referencia (${t.ref_end})`;
  return `Justo a tu hora de referencia (${t.ref_end})`;
}

function renderAlerts(t, l, hs) {
  const items = [];
  if (hs === 'done') items.push(['celebrate', 'i-sparkles', '¡Jornada completada! Ya puedes salir.']);
  if (l.inProgress && l.pendingBreak > 0) {
    items.push(['warn', 'i-coffee', l.brk < 1
      ? `Descanso obligatorio pendiente: <b>${human(t.min_break_s)}</b>`
      : `Te falta <b>${human(l.pendingBreak, true)}</b> de descanso obligatorio (llevas ${human(l.brk)} de ${human(t.min_break_s)})`]);
  } else if (l.inProgress && t.min_break_s && l.brk > 0 && l.brk <= t.min_break_s + t.optional_break_s) {
    items.push(['ok', 'i-check-circle', 'Descanso obligatorio completado']);
  }
  if (l.inProgress && l.target && l.brk > t.min_break_s + t.optional_break_s && t.min_break_s + t.optional_break_s > 0) {
    items.push(['warn', 'i-alert', `Has superado el descanso habitual (${human(t.min_break_s + t.optional_break_s)})`]);
  }
  if (hs.startsWith('finished') && t.flags.includes('break_short')) {
    items.push(['warn', 'i-alert', `No se completó el descanso mínimo (${human(l.brk)} de ${human(t.min_break_s)})`]);
  }
  if (hs === 'finished') items.push(['ok', 'i-check-circle', 'Jornada cerrada. ¡Buen trabajo!']);
  const html = items.map(([k, ic, msg]) => `<div class="alert ${k}">${icon(ic)}<span>${msg}</span></div>`).join('');
  const box = $('#heroAlerts');
  if (box.dataset.html !== html) { box.innerHTML = html; box.dataset.html = html; }

  const breakLive = $('#breakLive');
  breakLive.hidden = t.status !== 'on_break';
  if (!breakLive.hidden) $('#breakTimer').textContent = hms(l.cur);
}

function renderTiles(t, l) {
  $('#tWorked').textContent = dur(l.worked);
  $('#tWorkedSub').textContent = l.target ? `de ${dur(l.target)} objetivo` : 'Sin objetivo hoy';

  const extra = l.extra > 0 && l.target;
  const deficit = t.status === 'finished' && l.remaining >= 1;
  $('#tRemainingLabel').textContent = extra ? 'Tiempo extra' : deficit ? 'Déficit de hoy' : 'Pendiente';
  $('#tRemaining').textContent = extra ? '+' + dur(l.extra) : deficit ? '−' + dur(l.remaining) : dur(l.remaining, true);
  $('#tRemainingIcon').className = `tile-icon ${extra ? 'c-green' : deficit ? 'c-red' : 'c-blue'}`;
  $('#tRemainingSub').textContent = l.target ? `${Math.floor(l.progress * 100)} % de la jornada` : '—';

  $('#tBreak').textContent = dur(l.brk);
  $('#tBreakSub').textContent = t.status === 'on_break'
    ? `En curso: ${hms(l.cur)}`
    : `${t.breaks.length} ${t.breaks.length === 1 ? 'pausa' : 'pausas'} · mín. ${human(t.min_break_s)}`;

  $('#tIn').textContent = t.clock_in ? clock(t.clock_in) : '—';
  let sub = 'Sin fichar';
  if (t.clock_in && t.ref_start) {
    const diff = Math.round((localSeconds(Date.parse(t.clock_in)) - refMinutes(t.ref_start) * 60) / 60);
    sub = diff === 0 ? `Puntual (${t.ref_start})` : `${human(Math.abs(diff) * 60)} ${diff < 0 ? 'antes' : 'después'} de las ${t.ref_start}`;
  }
  $('#tInSub').textContent = sub;
}

function renderBreakMeter(t, l) {
  const min = t.min_break_s, opt = t.optional_break_s, total = min + opt;
  const bar = $('#breakMeterBar'), optBar = $('#breakMeterOpt');
  if (!total) {
    $('#breakMeterText').textContent = l.brk ? human(l.brk) : '—';
    bar.style.width = '0'; optBar.style.width = '0';
    $('#breakMeterNote').textContent = 'Hoy no hay descanso obligatorio.';
    return;
  }
  $('#breakMeterText').textContent = `${l.brk < 1 ? '0 min' : human(l.brk)} / ${human(min)}`;
  bar.style.width = `${(Math.min(l.brk, min) / total) * 100}%`;
  bar.classList.toggle('done', l.brk >= min);
  optBar.style.width = `${(Math.max(0, Math.min(l.brk - min, opt)) / total) * 100}%`;
  $('#breakMeterNote').textContent = l.brk < min
    ? `Faltan ${human(min - l.brk, true)} · opcional: ${human(opt)} más`
    : l.brk <= total
      ? `Completado · opcional restante: ${human(total - l.brk, true)}`
      : `Superado en ${human(l.brk - total)} el máximo habitual`;
}

function renderDayline(t, l) {
  const box = $('#dayline');
  const now = l.now;
  if (!t.clock_in) {
    box.innerHTML = '';
    $('#daylineScale')?.remove();
    return;
  }
  const start = Date.parse(t.clock_in);
  const end = t.clock_out ? Date.parse(t.clock_out) : now;
  const horizon = Math.max(end, l.exit || end);
  const span = Math.max(1, horizon - start);
  const pct = (a, b) => `left:${((a - start) / span) * 100}%;width:${(Math.max(0, b - a) / span) * 100}%`;
  const segs = [];
  segs.push(`<span class="w" style="${pct(start, end)}"></span>`);
  for (const b of t.breaks) {
    const bs = Date.parse(b.start), be = b.end ? Date.parse(b.end) : end;
    segs.push(`<span class="b" style="${pct(bs, Math.min(be, end))}"></span>`);
  }
  if (!t.clock_out && l.exit && l.exit > end) segs.push(`<span class="f" style="${pct(end, l.exit)}"></span>`);
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

function renderStats(t, l) {
  const w = state.week, m = state.month, all = state.total;
  if (!w || !m || !all) return;
  // Ajuste en vivo: lo que ha cambiado hoy desde la última foto del servidor.
  const dWorked = l.worked - t.worked_s;
  const dExtra = l.extra - t.extra_s;
  const pendingNow = l.inProgress ? l.remaining : 0;
  const wWorked = w.worked_s + dWorked, mWorked = m.worked_s + dWorked;
  const wBal = w.balance_s + dExtra, mBal = m.balance_s + dExtra, totalBal = all.balance_s + dExtra;
  const cls = (v) => (v >= 1 ? 'pos' : v <= -1 ? 'neg' : '');
  const bar = (a, b) => `<div class="bar"><span style="width:${b ? Math.min(100, (a / b) * 100) : 0}%"></span></div>`;
  const pendTxt = pendingNow > 0 ? `<span class="pend">${dur(pendingNow, true)} pendiente hoy</span>` : 'Solo cuenta jornadas cerradas';
  const completed = m.completed_days + (l.done && !(t.worked_s >= t.target_s && t.target_s) ? 1 : 0);
  const tiles = [
    ['Trabajado', 'Semana', dur(wWorked), `${Math.round(w.target_s ? (wWorked / w.target_s) * 100 : 0)} % del objetivo`, '', bar(wWorked, w.target_s)],
    ['Objetivo', 'Semana', dur(w.target_s), 'Según el horario de cada día', ''],
    ['Balance', 'Semana', signed(wBal), pendTxt, cls(wBal)],
    ['Promedio diario', 'Mes', dur(m.worked_days ? mWorked / m.worked_days : 0), `${m.worked_days} ${m.worked_days === 1 ? 'día fichado' : 'días fichados'}`, ''],
    ['Trabajado', 'Mes', dur(mWorked), `${Math.round(m.target_s ? (mWorked / m.target_s) * 100 : 0)} % del objetivo`, '', bar(mWorked, m.target_s)],
    ['Balance acumulado', 'Total', signed(totalBal),
      all.since ? `${all.worked_days} jornadas desde el ${longDate(all.since, { day: 'numeric', month: 'short', year: 'numeric' })}` : 'Sin jornadas todavía', cls(totalBal)],
    ['Balance', 'Mes', signed(mBal), pendTxt, cls(mBal)],
    ['Jornadas completadas', 'Mes', `${completed}`, `de ${m.worked_days} fichadas`, ''],
  ];
  const html = tiles.map(([label, scope, value, sub, c, extra = '']) =>
    `<div class="stat"><span class="stat-label">${label}<em>${scope}</em></span>
     <span class="stat-value ${c}">${value}</span><span class="stat-sub">${sub}</span>${extra}</div>`).join('');
  const box = $('#stats');
  if (box.dataset.html !== html) { box.innerHTML = html; box.dataset.html = html; }
}

/* ------------------------------------------- render al recibir datos */

function renderStatic() {
  const t = state.today;
  $('#todayLabel').textContent = longDate(t.date);
  const mode = t.status === 'nonworking' ? null : MODE_INFO[t.mode];
  const profile = t.profile && t.target_s ? ` · ${PROFILE_NAMES[t.profile]}` : '';
  $('#modeBadge').innerHTML = mode ? `${icon(mode.icon)}${mode.label}${profile}` : `${icon('i-palm')}No laborable`;
  renderTimeline(t);
  renderBanner();
  state.heroKey = null;   // fuerza a repintar los botones
}

function renderTimeline(t) {
  const items = [];
  if (!t.clock_in) {
    $('#timeline').innerHTML = `<li class="tl-empty">Pulsa «Iniciar jornada» para empezar a contar.</li>`;
    return;
  }
  items.push(['in', 'i-login', 'Entrada', clock(t.clock_in), t.ref_start ? `Referencia ${t.ref_start}` : '']);
  t.breaks.forEach((b, i) => {
    items.push(['br', 'i-coffee', `Descanso ${t.breaks.length > 1 ? i + 1 : ''}`.trim(),
      `${clock(b.start)} – ${b.end ? clock(b.end) : 'ahora'}`, b.end ? human(b.duration_s) : 'En curso']);
  });
  items.push(t.clock_out
    ? ['out', 'i-stop', 'Salida', clock(t.clock_out), '']
    : ['', 'i-clock', 'Salida prevista', `<span id="tlExit">—</span>`, t.ref_end ? `Referencia ${t.ref_end}` : '']);
  $('#timeline').innerHTML = items.map(([k, ic, title, time, sub]) => `
    <li><span class="tl-icon ${k}">${icon(ic)}</span>
      <div class="tl-main"><span class="tl-title">${title}</span>${sub ? `<span class="tl-sub">${sub}</span>` : ''}</div>
      <span class="tl-time">${time}</span></li>`).join('');
}

function renderBanner() {
  const b = $('#globalBanner');
  if (state.offline) {
    b.hidden = false;
    b.innerHTML = `${icon('i-alert')}<span>Sin conexión con el servidor. Los contadores siguen funcionando; los cambios se guardarán cuando vuelva.</span>`;
    return;
  }
  if (state.unclosed?.length) {
    const key = state.unclosed[0];
    b.hidden = false;
    b.innerHTML = `${icon('i-alert')}<span>La jornada del <b>${longDate(key)}</b> quedó sin hora de salida.</span>
      <button class="ghost-btn small" data-fix="${key}">${icon('i-edit')}Corregir</button>`;
    return;
  }
  b.hidden = true;
}

function renderActions(hs) {
  const btn = (action, cls, ic, label) =>
    `<button class="action-btn ${cls}" data-action="${action}">${icon(ic)}<span>${label}</span></button>`;
  const html = {
    idle: btn('start', 'primary go', 'i-play', 'Iniciar jornada'),
    off: btn('start', 'primary go', 'i-play', 'Iniciar jornada'),
    working: btn('break_start', 'primary pause', 'i-coffee', 'Iniciar descanso') + btn('stop', 'secondary stop', 'i-stop', 'Finalizar jornada'),
    done: btn('stop', 'primary finish', 'i-stop', 'Finalizar jornada') + btn('break_start', 'secondary', 'i-coffee', 'Iniciar descanso'),
    on_break: btn('break_end', 'primary resume', 'i-return', 'Terminar descanso') + btn('stop', 'secondary stop', 'i-stop', 'Finalizar jornada'),
    finished: btn('resume', 'secondary', 'i-rotate', 'Reanudar jornada'),
    finished_short: btn('resume', 'secondary', 'i-rotate', 'Reanudar jornada'),
  }[hs] || '';
  $('#actions').innerHTML = html;
}

/* ------------------------------------------------------------ fichaje */

async function doAction(action, button) {
  if (state.busy) return;     // evita dobles clics
  const t = state.today;
  state.busy = true;
  document.querySelectorAll('.action-btn').forEach((b) => { b.disabled = true; });
  button?.classList.add('busy');
  try {
    const res = await api('/api/clock', { method: 'POST', body: { action, expect: t.status } });
    const balance = res.today.target_s ? ` · balance ${signed(res.today.balance_s)}` : '';
    const msg = {
      start: `Jornada iniciada a las ${clock(nowMs())}`,
      break_start: 'Descanso iniciado. ¡Disfrútalo!',
      break_end: 'De vuelta al trabajo',
      stop: `Jornada finalizada a las ${clock(nowMs())}${balance}`,
      resume: 'Jornada reanudada',
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
  toast('¡Jornada completada! Ya puedes salir.', 'party', 8000);
  if ('Notification' in window && Notification.permission === 'granted') {
    try { new Notification('¡Jornada completada!', { body: 'Ya puedes salir. A partir de ahora cuenta como tiempo extra.' }); } catch (e) { /* ignorar */ }
  }
}

/* -------------------------------------------------------- calendario */

const STATUS_CHIP = (c) => ({
  finished: c.color === 'green' ? ['green', 'Completada'] : ['red', 'Déficit'],
  working: c.color === 'green' ? ['green', 'Completada · en curso'] : ['yellow', 'En curso'],
  on_break: ['yellow', 'En descanso'],
  unclosed: ['yellow', 'Sin hora de salida'],
  not_started: ['', 'Sin iniciar'],
  none: ['', 'Sin registro'],
  future: ['', 'Próximo'],
  nonworking: ['', 'No laborable'],
  off: ['', 'Libre'],
}[c.status] || ['', c.status]);

function renderCalendar() {
  const { year, month } = state.cal;
  const first = `${year}-${pad(month)}-01`;
  $('#monthTitle').textContent = longDate(first, { month: 'long', year: 'numeric' });
  const todayKey = dateKey(nowMs());
  const lead = weekdayOf(first);
  const cells = [];
  for (let i = 0; i < lead; i++) cells.push('<span class="cal-day out"></span>');
  for (const c of state.monthData.days) {
    const n = Number(c.date.slice(8));
    const cls = ['cal-day', c.color !== 'gray' ? c.color : '',
      c.date === todayKey ? 'today' : '', c.date === state.selected ? 'selected' : '',
      !c.workday ? 'weekend' : ''].filter(Boolean).join(' ');
    const mark = c.registered && c.mode === 'off' ? icon('i-palm')
      : (c.profile === 'summer' && c.target_s ? icon('i-sun') : '') + (c.mode === 'remote' && c.workday ? icon('i-home') : '');
    const hours = c.clock_in ? shortDur(c.worked_s) : '';
    const title = `${longDate(c.date)} · ${STATUS_CHIP(c)[1]}${hours ? ' · ' + hours : ''}`;
    cells.push(`<button class="${cls}" data-date="${c.date}" title="${esc(title)}">
      <span class="n">${n}</span>${mark ? `<span class="mk">${mark}</span>` : ''}<span class="h">${hours}</span></button>`);
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
  const c = state.monthData?.days.find((d) => d.date === state.selected);
  if (!c) {
    box.innerHTML = `<div class="empty-state">${icon('i-calendar')}<span>Selecciona un día del calendario</span></div>`;
    return;
  }
  const [chipCls, chipTxt] = STATUS_CHIP(c);
  const mode = MODE_INFO[c.mode];
  const head = `<div class="detail-head"><div><h3>${longDate(c.date, { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}</h3>
      <div class="chips"><span class="chip ${chipCls}">${chipTxt}</span>${c.workday || c.registered ? `<span class="chip">${icon(mode.icon)}${mode.label}</span>` : ''}${profileChip(c)}</div></div></div>`;

  if (!c.registered) {
    const canAdd = c.status !== 'future';
    box.innerHTML = `${head}<div class="empty-state">${icon('i-calendar')}
      <span>${c.status === 'future' ? 'Este día aún no ha llegado.' : 'No hay ningún registro este día.'}</span>
      ${c.target_s ? `<span class="small">Objetivo previsto: ${human(c.target_s)}</span>` : ''}
      <button class="primary-btn" data-edit="${c.date}">${icon(canAdd ? 'i-plus' : 'i-edit')}${canAdd ? 'Registrar jornada' : 'Planificar (libre, notas…)'}</button></div>`;
    return;
  }

  const breaks = c.breaks.map((b) => `<dt class="small">· ${clock(b.start)} – ${b.end ? clock(b.end) : 'en curso'}</dt><dd class="small">${human(b.duration_s)}</dd>`).join('');
  box.innerHTML = `${head}
    <dl class="kv">
      <dt>Entrada</dt><dd>${c.clock_in ? clock(c.clock_in) : '—'}</dd>
      <dt>Salida</dt><dd>${c.clock_out ? clock(c.clock_out) : c.clock_in ? (c.status === 'unclosed' ? '<span class="pend">Sin registrar</span>' : 'En curso') : '—'}</dd>
      <dt>Descansos</dt><dd>${c.breaks.length ? `${c.breaks.length} · ${human(c.break_s)}` : '—'}</dd>
      ${breaks}
      <div class="divider"></div>
      <dt>Trabajo efectivo</dt><dd>${dur(c.worked_s)}</dd>
      <dt>Horas exigidas</dt><dd>${dur(c.target_s)}${c.custom_targets ? ' <span class="muted small">(manual)</span>' : ''}</dd>
      <dt>${balanceLabel(c)}</dt><dd>${balanceHtml(c)}</dd>
    </dl>
    ${c.notes ? `<div class="notes">${esc(c.notes)}</div>` : ''}
    <div class="detail-actions">
      <button class="ghost-btn" data-edit="${c.date}">${icon('i-edit')}Editar</button>
      <button class="danger-btn" data-delete="${c.date}">${icon('i-trash')}Eliminar</button>
    </div>`;
}

function profileChip(c) {
  if (!c.profile || !(c.workday || c.profile_source === 'manual') || c.mode === 'off') return '';
  const ic = c.profile === 'summer' ? 'i-sun' : 'i-clock';
  return `<span class="chip">${icon(ic)}${PROFILE_NAMES[c.profile]}${c.profile_source === 'manual' ? ' · manual' : ''}</span>`;
}

function balanceLabel(c) {
  if (c.status === 'working' || c.status === 'on_break') return c.extra_s > 0 ? 'Tiempo extra' : 'Pendiente';
  if (c.status === 'finished') return c.balance_s >= 0 ? 'Tiempo extra' : 'Déficit';
  return 'Balance';
}

function balanceHtml(c) {
  if (c.status === 'working' || c.status === 'on_break') {
    return c.extra_s > 0 ? `<span class="pos">+${dur(c.extra_s)}</span>` : `<span class="pend">${dur(c.pending_s, true)}</span>`;
  }
  if (c.status === 'finished') {
    const cls = c.balance_s >= 1 ? 'pos' : c.balance_s <= -1 ? 'neg' : '';
    return `<span class="${cls}">${signed(c.balance_s)}</span>`;
  }
  if (c.status === 'unclosed') return '<span class="pend">Sin salida</span>';
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
      <td class="day-cell">${WEEKDAYS[c.weekday]}<span>${Number(c.date.slice(8))}</span></td>
      <td class="hide-sm">${c.clock_in ? clock(c.clock_in) : '—'}</td>
      <td class="hide-sm">${c.clock_out ? clock(c.clock_out) : c.clock_in ? '<span class="pend">…</span>' : '—'}</td>
      <td class="hide-sm">${c.break_s ? human(c.break_s) : '—'}</td>
      <td>${c.clock_in ? dur(c.worked_s) : (c.status === 'off' ? '<span class="muted">Libre</span>' : '—')}${bar}</td>
      <td class="hide-xs">${c.target_s ? dur(c.target_s) : '—'}</td>
      <td class="num">${balanceHtml(c)}</td></tr>`;
  }).join('');
  const s = w.summary;
  const cls = s.balance_s >= 1 ? 'pos' : s.balance_s <= -1 ? 'neg' : '';
  $('#weekFoot').innerHTML = `<tr><td>Total</td><td class="hide-sm"></td><td class="hide-sm"></td><td class="hide-sm"></td>
    <td>${dur(s.worked_s)}</td><td class="hide-xs">${dur(s.target_s)}</td>
    <td class="num"><span class="${cls}">${signed(s.balance_s)}</span>${s.pending_s ? `<div class="small pend">${dur(s.pending_s, true)} pendiente</div>` : ''}</td></tr>`;
}

/* ----------------------------------------------------- editor de día */

const dayDialog = $('#dayDialog');
let editing = null;   // { date, isNew, registered }

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

function addBreakRow(start = '', end = '') {
  const row = document.createElement('div');
  row.className = 'break-row';
  row.innerHTML = `<input type="time" aria-label="Inicio del descanso"><input type="time" aria-label="Fin del descanso">
    <span class="dur"></span><button type="button" class="icon-btn small" aria-label="Quitar descanso">${icon('i-x')}</button>`;
  const [a, b] = row.querySelectorAll('input');
  setTime(a, start);
  setTime(b, end);
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
  editing = { date, isNew, registered: c.registered, status: c.status };
  $('#dayDialogTitle').textContent = c.registered ? 'Editar jornada' : 'Registrar jornada';
  $('#dayDialogSub').textContent = longDate(date, { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
  $('#fDate').value = date;
  $('#fDate').disabled = !isNew;
  $('#fDate').max = dateKey(nowMs());
  setSegment($('#fMode'), c.mode);
  editing.auto = c.auto;
  const autoName = PROFILE_NAMES[c.auto.profile] + (c.auto.profile_source === 'period' ? ' (período de verano)' : '');
  $('#fProfile').innerHTML = `<option value="">Automático · ${autoName}</option>`
    + profileOptions(c.profile_source === 'manual' ? c.profile : '');
  setTime($('#fIn'), c.local.clock_in);
  setTime($('#fOut'), c.local.clock_out);
  $('#fBreaks').innerHTML = '';
  c.local.breaks.forEach((b) => addBreakRow(b.start, b.end));
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
  if (target === null) throw new Error('El objetivo efectivo debe tener formato H:MM (por ejemplo 8:30).');
  return {
    mode: $('#fMode').dataset.value,
    profile: $('#fProfile').value,
    clock_in: getTime($('#fIn')),
    clock_out: getTime($('#fOut')),
    breaks: [...$('#fBreaks').children].map((row) => {
      const [a, b] = row.querySelectorAll('input');
      return { start: getTime(a), end: getTime(b) };
    }),
    target_minutes: target,
    min_break_minutes: Number($('#fMinBreak').value || 0),
    optional_break_minutes: Number($('#fOptBreak').value || 0),
    notes: $('#fNotes').value,
  };
}

function updatePreview() {
  const box = $('#fPreview');
  const inS = toSec(getTime($('#fIn')));
  const isToday = $('#fDate').value === dateKey(nowMs());
  let outS = toSec(getTime($('#fOut')));
  if (outS === null && isToday && inS !== null) outS = localSeconds(nowMs());
  let brk = 0;
  for (const row of $('#fBreaks').children) {
    const [a, b] = row.querySelectorAll('input');
    const s = toSec(getTime(a)), e = toSec(getTime(b)) ?? outS;
    const d = s !== null && e !== null && e > s ? e - s : 0;
    brk += d;
    row.querySelector('.dur').textContent = d ? human(d) : '';
  }
  const target = (hmToMinutes($('#fTarget').value) ?? 0) * 60;
  if (inS === null || outS === null || outS <= inS) {
    box.innerHTML = `<span>Introduce entrada${isToday ? '' : ' y salida'} para ver el cálculo.</span>`;
    return;
  }
  const worked = Math.max(0, outS - inS - brk);
  const diff = worked - target;
  const open = toSec(getTime($('#fOut'))) === null;
  box.innerHTML = `<span>Trabajo efectivo${open ? ' (hasta ahora)' : ''}: <b>${human(worked)}</b></span>
    <span>Descanso: <b>${human(brk)}</b></span>
    <span>${diff >= 0 ? 'Extra' : open ? 'Pendiente' : 'Déficit'}: <b class="${diff >= 0 ? 'pos' : open ? 'pend' : 'neg'}">${human(Math.abs(diff))}</b></span>`;
}

async function saveEditor(ev) {
  ev.preventDefault();
  const err = $('#fError');
  err.hidden = true;
  let body;
  try {
    body = collectForm();
  } catch (e) {
    err.textContent = e.message; err.hidden = false; return;
  }
  const date = $('#fDate').value;
  if (!date) { err.textContent = 'Indica una fecha.'; err.hidden = false; return; }
  const save = $('#fSave');
  save.disabled = true;
  try {
    await api(`/api/days/${date}`, { method: 'PUT', body });
    dayDialog.close();
    toast('Jornada guardada', 'ok');
    state.selected = date;
    await refreshAll();
    selectDate(date);
  } catch (e) {
    err.textContent = e.message;
    err.hidden = false;
  } finally {
    save.disabled = false;
  }
}

async function deleteDay(date) {
  const ok = await confirmDialog({
    title: 'Eliminar registro',
    text: `Se borrarán todos los fichajes del ${longDate(date, { weekday: 'long', day: 'numeric', month: 'long' })}. Esta acción no se puede deshacer.`,
    ok: 'Eliminar', danger: true,
  });
  if (!ok) return false;
  try {
    await api(`/api/days/${date}`, { method: 'DELETE' });
    toast('Registro eliminado', 'ok');
    await refreshAll();
    return true;
  } catch (e) {
    toast(e.message, 'err');
    return false;
  }
}

/* ------------------------------------------------------------ ajustes */

const settingsDialog = $('#settingsDialog');

const PROFILE_KEYS = ['normal', 'friday', 'summer'];
const PROFILE_NAMES = { normal: 'Horario normal', friday: 'Viernes intensivo', summer: 'Intensivo de verano' };
const SHORT_DAYS = ['L', 'M', 'X', 'J', 'V', 'S', 'D'];
const profileOptions = (selected) =>
  PROFILE_KEYS.map((k) => `<option value="${k}" ${k === selected ? 'selected' : ''}>${PROFILE_NAMES[k]}</option>`).join('');

function addPeriodRow(start = '', end = '') {
  const box = $('#sPeriods');
  box.querySelector('.empty-periods')?.remove();
  const row = document.createElement('div');
  row.className = 'period-row';
  row.innerHTML = `<span>Desde</span><input type="date" data-f="start" value="${start}" required>
    <span>hasta</span><input type="date" data-f="end" value="${end}" required>
    <button type="button" class="icon-btn small" aria-label="Quitar período">${icon('i-x')}</button>`;
  row.querySelector('button').addEventListener('click', () => {
    row.remove();
    if (!box.children.length) box.innerHTML = '<span class="empty-periods">Sin períodos de verano configurados.</span>';
  });
  box.append(row);
}

function openSettings() {
  const s = state.settings;
  $('#sProfiles').innerHTML = PROFILE_KEYS.map((k) => {
    const p = s.profiles[k];
    return `<tr data-profile="${k}">
      <td>${PROFILE_NAMES[k]}</td>
      <td><input type="time" data-f="start" value="${p.start}"></td>
      <td><input type="time" data-f="end" value="${p.end}"></td>
      <td><input type="text" data-f="target" value="${minutesToHM(p.target_minutes)}" inputmode="numeric"></td>
      <td><input type="number" data-f="min_break_minutes" value="${p.min_break_minutes}" min="0" max="600"></td>
      <td><input type="number" data-f="optional_break_minutes" value="${p.optional_break_minutes}" min="0" max="600"></td></tr>`;
  }).join('');
  $('#sWeekdays').innerHTML = WEEKDAYS.map((name, i) => {
    const d = s.weekdays[i];
    return `<tr data-day="${i}" class="${d.workday ? '' : 'disabled'}">
      <td>${name}</td>
      <td><label class="switch"><input type="checkbox" data-f="workday" ${d.workday ? 'checked' : ''}><span></span></label></td>
      <td><select data-f="profile">${profileOptions(d.profile)}</select></td>
      <td><div class="segmented" data-f="mode">
        <button type="button" data-value="office">${icon('i-building')}Oficina</button>
        <button type="button" data-value="remote">${icon('i-home')}Tele</button></div></td></tr>`;
  }).join('');
  $('#sWeekdays').querySelectorAll('tr').forEach((tr) => {
    setSegment(tr.querySelector('[data-f="mode"]'), s.weekdays[tr.dataset.day].mode);
    tr.querySelector('[data-f="workday"]').addEventListener('change', (e) => tr.classList.toggle('disabled', !e.target.checked));
  });
  $('#sPeriods').innerHTML = '';
  if (s.summer.periods.length) s.summer.periods.forEach((p) => addPeriodRow(p.start, p.end));
  else $('#sPeriods').innerHTML = '<span class="empty-periods">Sin períodos de verano configurados.</span>';
  $('#sSummerDays').innerHTML = SHORT_DAYS.map((d, i) =>
    `<button type="button" data-day="${i}" class="${s.summer.weekdays.includes(i) ? 'active' : ''}" aria-label="${WEEKDAYS[i]}">${d}</button>`).join('');
  setSegment($('#sTheme'), s.theme);
  setSegment($('#sTimeFormat'), s.time_format);
  setSegment($('#sDurFormat'), s.duration_format);
  $('#sError').hidden = true;
  settingsDialog.showModal();
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
      if (target === null) throw new Error(`${PROFILE_NAMES[tr.dataset.profile]}: el tiempo efectivo debe tener formato H:MM.`);
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
      if (!start || !end) throw new Error(`Período ${i + 1}: indica la fecha de inicio y la de fin.`);
      periods.push({ start, end });
    });
  } catch (e) {
    err.textContent = e.message; err.hidden = false; return;
  }
  const summerDays = [...$('#sSummerDays').querySelectorAll('button.active')].map((b) => Number(b.dataset.day));
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
      },
    });
    fmtCache.clear();
    settingsDialog.close();
    toast('Ajustes guardados', 'ok');
    await refreshAll();
  } catch (e) {
    err.textContent = e.message; err.hidden = false;
  }
}

async function quitApp() {
  const ok = await confirmDialog({
    title: 'Cerrar Jornada',
    text: 'Se detendrá el servidor local. Todos los datos ya están guardados; los contadores se recalcularán al volver a abrirla.',
    ok: 'Cerrar Jornada',
  });
  if (!ok) return;
  try {
    await api('/api/shutdown', { method: 'POST', body: { confirm: true } });
  } catch (e) { /* si ya estaba cerrado, da igual */ }
  state.closed = true;
  $('#closedScreen').hidden = false;
  document.title = 'Jornada (cerrada)';
}

async function toggleTheme() {
  const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
  applyTheme(next);
  try {
    state.settings = await api('/api/settings', { method: 'PUT', body: { theme: next } });
  } catch (e) {
    toast(e.message, 'err');
  }
}

/* ------------------------------------------------------------ eventos */

function bindEvents() {
  $('#actions').addEventListener('click', (e) => {
    const b = e.target.closest('[data-action]');
    if (b) doAction(b.dataset.action, b);
  });
  $('#editTodayBtn').addEventListener('click', () => state.today && openEditor(state.today.date));
  $('#addDayBtn').addEventListener('click', () => {
    const today = dateKey(nowMs());
    openEditor(state.selected && state.selected <= today ? state.selected : today, true);
  });
  $('#themeBtn').addEventListener('click', toggleTheme);
  $('#settingsBtn').addEventListener('click', openSettings);
  $('#quitBtn').addEventListener('click', quitApp);
  $('#globalBanner').addEventListener('click', (e) => {
    const b = e.target.closest('[data-fix]');
    if (b) openEditor(b.dataset.fix);
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
  });

  $('#prevWeek').addEventListener('click', () => selectDate(addDays(state.weekDate, -7)));
  $('#nextWeek').addEventListener('click', () => selectDate(addDays(state.weekDate, 7)));
  $('#thisWeek').addEventListener('click', () => selectDate(dateKey(nowMs())));
  $('#weekBody').addEventListener('click', (e) => {
    const tr = e.target.closest('[data-date]');
    if (tr) selectDate(tr.dataset.date);
  });

  // Diálogos
  document.querySelectorAll('dialog [data-close]').forEach((b) => b.addEventListener('click', () => b.closest('dialog').close()));
  document.querySelectorAll('dialog').forEach((d) => d.addEventListener('click', (e) => { if (e.target === d) d.close('cancel'); }));
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
  $('#fAddBreak').addEventListener('click', () => { addBreakRow(); updatePreview(); });
  $('#fDate').addEventListener('change', (e) => { if (e.target.value) openEditor(e.target.value, true); });
  $('#fDelete').addEventListener('click', async () => {
    const date = editing?.date;
    if (date && await deleteDay(date)) dayDialog.close();
  });
  $('#settingsForm').addEventListener('submit', saveSettings);
  $('#sAddPeriod').addEventListener('click', () => addPeriodRow());
  $('#sSummerDays').addEventListener('click', (e) => {
    const b = e.target.closest('button[data-day]');
    if (b) b.classList.toggle('active');
  });
  $('#fProfile').addEventListener('change', applyProfileToForm);

  // Al volver a la pestaña o despertar el equipo, se resincroniza con el servidor.
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refreshAll(); });
  window.addEventListener('focus', () => { if (!state.closed) loadState().catch(() => {}); });
}

function shiftMonth(delta) {
  let { year, month } = state.cal;
  month += delta;
  if (month < 1) { month = 12; year--; }
  if (month > 12) { month = 1; year++; }
  state.cal = { year, month };
  loadMonth().catch((e) => toast(e.message, 'err'));
}

/* -------------------------------------------------------------- inicio */

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
  const loop = () => { tick(); setTimeout(loop, 1005 - (nowMs() % 1000)); };
  loop();
  setInterval(() => { if (!document.hidden) refreshAll(); }, 60000);
  setInterval(() => { if (document.hidden && !state.closed) api('/api/ping').catch(() => {}); }, 300000);
}

bindEvents();
init();

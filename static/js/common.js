/* ============================================================
   Jornada — utilidades compartidas
   Las usan el panel completo (app.js) y la vista compacta (compact.js):
   un único cálculo en vivo, un único formato de horas y una única API.
   ============================================================ */
'use strict';

const TZ = 'Europe/Madrid';
const MODE_ICONS = { office: 'i-building', remote: 'i-home', off: 'i-palm' };
const PROFILE_KEYS = ['normal', 'friday', 'summer'];
const DAY_TYPES = ['holiday', 'vacation', 'dayoff', 'permit', 'sick', 'custom'];
const DAY_TYPE_ICONS = { holiday: 'i-flag', vacation: 'i-suitcase', dayoff: 'i-palm', permit: 'i-badge', sick: 'i-heart', custom: 'i-tag' };
const MAX_BREAK_NOTE = 200;

const $ = (sel, root = document) => root.querySelector(sel);
const icon = (id) => `<svg><use href="#${id}"/></svg>`;
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const weekdayName = (i) => t(`weekday.${i}`);
const modeLabel = (m) => t(`mode.${m}`);
const profileName = (p) => t(`profile.${p}`);

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

/** Estado común. app.js lo amplía con lo propio del panel. */
const state = {
  settings: null,
  today: null,      // jornada de hoy calculada por el servidor
  snapAt: 0,        // instante (reloj del servidor) de la foto
  offset: 0,        // diferencia reloj servidor - reloj navegador
  offline: false,
};
/** Ganchos opcionales que cada página rellena (p. ej. el aviso de «sin conexión»). */
const hooks = { offline: null };

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
    hooks.offline?.(true);
    throw new Error(t('toast.offline'));
  }
  hooks.offline?.(false);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(data.error || `Error ${res.status}`);
    err.status = res.status;
    err.data = data;
    throw err;
  }
  return data;
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

/* ------------------------------------------- apariencia (2.1) */

/** Movimiento reducido: lo pide el sistema o el usuario en Ajustes. El sistema siempre manda. */
const motionReduced = () => reducedMotion.matches || state.settings?.motion === 'reduced';
const motionExpressive = () => !reducedMotion.matches && state.settings?.motion === 'expressive';

/** Acento, densidad y animaciones como atributos de <html>; se recuerdan para pintar sin parpadeo. */
function applyLook(s) {
  if (!s) return;
  const root = document.documentElement;
  root.dataset.accent = s.accent || 'teal';
  root.dataset.density = s.density || 'comfortable';
  root.dataset.motion = reducedMotion.matches ? 'reduced' : (s.motion || 'normal');
  try { localStorage.setItem('wt-look', JSON.stringify({ accent: s.accent, density: s.density, motion: s.motion })); } catch (e) { /* sin almacenamiento */ }
}
reducedMotion.addEventListener('change', () => applyLook(state.settings));

/* ------------------------------------- sincronización entre ventanas */

/** Avisa a las demás ventanas de Jornada (panel, vista compacta) de que algo cambió.
 *  BroadcastChannel cuando existe; si no, el evento «storage» de localStorage. */
const syncChannel = 'BroadcastChannel' in window ? new BroadcastChannel('jornada-sync') : null;
function syncSend(type = 'changed') {
  const msg = { type, at: Date.now() };
  if (syncChannel) syncChannel.postMessage(msg);
  else { try { localStorage.setItem('wt-sync', JSON.stringify(msg)); } catch (e) { /* sin almacenamiento */ } }
}
function onSync(handler) {
  if (syncChannel) syncChannel.addEventListener('message', (e) => handler(e.data || {}));
  window.addEventListener('storage', (e) => {
    if (e.key === 'wt-sync' && e.newValue) { try { handler(JSON.parse(e.newValue)); } catch (err) { /* ignorar */ } }
  });
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

/* ============================================================
   Jornada — avisos inteligentes (2.1)
   Se calculan en el navegador a partir del estado real de la jornada
   (el mismo cálculo en vivo que el contador). No hay ningún proceso de
   fondo: solo avisan mientras Jornada está abierta en alguna ventana.

   planAlerts() es una función pura (se prueba en tests/js/notify.html).
   Cada aviso se registra por día en localStorage («wt-alerts»), compartido
   por todas las ventanas: así no se repite al recargar ni con dos ventanas.
   ============================================================ */
'use strict';

/** Un aviso solo se muestra si su momento pasó hace menos de esto (s).
 *  Al abrir Jornada más tarde, los avisos ya vencidos se marcan sin mostrarse. */
const ALERT_WINDOW = 120;

/**
 * Decide qué avisos tocan ahora.
 * @param d   jornada de hoy (servidor)       @param l  cálculo en vivo (live())
 * @param cfg settings.notifications           @param fired { id: instante } ya avisados hoy
 * @returns {{fire: object[], mark: string[], rearm: string[]}}
 */
function planAlerts(d, l, cfg, fired) {
  const out = { fire: [], mark: [], rearm: [] };
  if (!d || !l || !cfg) return out;
  const working = d.status === 'working', onBreak = d.status === 'on_break';
  const inProgress = working || onBreak;
  const add = (id, ok, fresh, msg) => {
    if (!ok || fired[id]) return;
    if (fresh) out.fire.push({ id, ...msg }); else out.mark.push(id);
  };

  // Cuenta atrás: al cruzar cada umbral; si se cruzan varios a la vez, solo el más cercano.
  if (inProgress && l.target && !l.done) {
    const due = (cfg.leads || []).filter((m) => l.remaining <= m * 60 && !fired[`lead-${m}`]).sort((a, b) => a - b);
    due.forEach((m, i) => {
      const fresh = working && i === 0 && l.remaining > m * 60 - ALERT_WINDOW;
      add(`lead-${m}`, true, fresh, { kind: 'info', key: 'al.lead', params: { dur: m } });
    });
  }
  // Si se edita la jornada y vuelve a faltar más tiempo, el aviso se rearma.
  for (const m of cfg.leads || []) {
    if (fired[`lead-${m}`] && (!l.target || l.remaining > m * 60 + 60)) out.rearm.push(`lead-${m}`);
  }

  if (cfg.done) {
    const ok = inProgress && l.done && !!l.completedAt;
    add('done', ok, ok && l.now - l.completedAt < ALERT_WINDOW * 1000, { kind: 'party', key: 'al.done' });
    if (fired.done && !l.done) out.rearm.push('done');
  }

  const minB = d.min_break_s, total = d.min_break_s + d.optional_break_s;
  if (cfg.break_pending) {
    // Recordatorio único: llevas X horas trabajando y aún falta el descanso obligatorio.
    add('break_pending', working && l.pendingBreak > 0 && l.worked >= (cfg.break_pending_after || 300) * 60,
      true, { kind: 'warn', key: 'al.break_pending', params: { dur: Math.ceil(l.pendingBreak / 60) } });
  }
  if (cfg.break_min_done && minB) {
    add('break_min', onBreak && l.brk >= minB, l.brk - minB < ALERT_WINDOW, { kind: 'ok', key: 'al.break_min' });
  }
  if (cfg.break_over && total) {
    add('break_over', onBreak && l.brk > total, l.brk - total < ALERT_WINDOW,
      { kind: 'warn', key: 'al.break_over', params: { dur: Math.round(total / 60) } });
  }
  return out;
}

/* ---------------------------------------------------- registro por día */

const ALERT_KEY = 'wt-alerts';
let alertMemo = null;

function readFired(date) {
  try {
    const all = JSON.parse(localStorage.getItem(ALERT_KEY) || '{}');
    return all.date === date ? all.fired || {} : {};
  } catch (e) { return alertMemo?.date === date ? alertMemo.fired : {}; }
}

function writeFired(date, fired) {
  alertMemo = { date, fired };
  try { localStorage.setItem(ALERT_KEY, JSON.stringify(alertMemo)); } catch (e) { /* sin almacenamiento: solo en memoria */ }
}

/** Ejecuta `fn` en exclusiva entre ventanas (Web Locks si existe). */
function withAlertLock(fn) {
  if (navigator.locks?.request) return navigator.locks.request('jornada-alerts', async () => fn());
  return Promise.resolve(fn());
}

let alertBusy = false;
/** Se llama en cada tick. Barato: solo toca localStorage si hay algo que hacer. */
function checkAlerts(d, l) {
  const cfg = state.settings?.notifications;
  if (!cfg || !d || alertBusy) return;
  if (!cfg.in_app && !cfg.desktop && !cfg.sound) return;
  if (alertMemo?.date !== d.date) alertMemo = { date: d.date, fired: readFired(d.date) };
  const plan = planAlerts(d, l, cfg, alertMemo.fired);
  if (!plan.fire.length && !plan.mark.length && !plan.rearm.length) return;
  alertBusy = true;
  withAlertLock(() => {
    // Relee dentro del cerrojo: otra ventana puede haberlo avisado ya.
    const fired = readFired(d.date);
    const now = Date.now();
    const shown = plan.fire.filter((a) => !fired[a.id]);
    shown.forEach((a) => { fired[a.id] = now; });
    plan.mark.forEach((id) => { fired[id] = fired[id] || now; });
    plan.rearm.forEach((id) => { delete fired[id]; });
    writeFired(d.date, fired);
    shown.forEach((a) => deliverAlert(a, cfg));
  }).finally(() => { alertBusy = false; });
}

window.addEventListener('storage', (e) => { if (e.key === ALERT_KEY) alertMemo = null; });

/* ------------------------------------------------------------ entrega */

function deliverAlert(alert, cfg) {
  const text = t(alert.key, alert.params);
  if (cfg.in_app && typeof toast === 'function') toast(text, alert.kind, alert.kind === 'party' ? 8000 : 6000);
  if (cfg.desktop && 'Notification' in window && Notification.permission === 'granted') {
    try {
      new Notification('Jornada', { body: text, tag: `jornada-${alert.id}`, icon: '/static/img/jornada.png', silent: !cfg.sound });
    } catch (e) { /* algunos navegadores solo permiten notificaciones desde un service worker */ }
  }
  if (cfg.sound) chime(alert.kind);
}

/* Sonido discreto generado al vuelo (sin archivos). El navegador solo deja
   sonar audio tras una interacción: el contexto se prepara en el primer clic. */
let audioCtx = null;
function unlockAudio(force = false) {
  if (!force && !state.settings?.notifications?.sound) return;
  try {
    audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
    if (audioCtx.state === 'suspended') audioCtx.resume();
  } catch (e) { audioCtx = null; }
}
window.addEventListener('pointerdown', () => unlockAudio(), { passive: true });
window.addEventListener('keydown', () => unlockAudio(), { passive: true });

function chime(kind = 'info') {
  if (!audioCtx || audioCtx.state !== 'running') return;
  const notes = kind === 'party' ? [660, 880, 1320] : kind === 'warn' ? [520, 390] : [740, 990];
  const start = audioCtx.currentTime + 0.02;
  notes.forEach((freq, i) => {
    const osc = audioCtx.createOscillator(), gain = audioCtx.createGain();
    osc.type = 'sine';
    osc.frequency.value = freq;
    const at = start + i * 0.14;
    gain.gain.setValueAtTime(0.0001, at);
    gain.gain.exponentialRampToValueAtTime(0.08, at + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, at + 0.32);
    osc.connect(gain).connect(audioCtx.destination);
    osc.start(at);
    osc.stop(at + 0.35);
  });
}

/** Permiso de escritorio: solo se pide cuando el usuario activa la opción. */
async function requestDesktopPermission() {
  if (!('Notification' in window)) return 'unsupported';
  if (Notification.permission !== 'default') return Notification.permission;
  try { return await Notification.requestPermission(); } catch (e) { return 'denied'; }
}

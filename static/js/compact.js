/* ============================================================
   Jornada — vista compacta (2.1)
   Un widget con lo imprescindible: estado, cuenta atrás, salida,
   porcentaje y la acción principal. Comparte cálculo con el panel
   (common.js) y se sincroniza con él:
   · al fichar aquí se avisa a las demás ventanas (BroadcastChannel);
   · al recibir un aviso, o cada 30 s, se recarga la foto del servidor;
   · el contador se calcula en local cada segundo, sin pedir nada.
   El servidor rechaza una acción si el estado ya cambió en otra ventana
   (campo «expect»), así que nunca se duplica un fichaje.
   ============================================================ */
'use strict';

const inPip = new URLSearchParams(location.search).has('pip');
let busy = false;
let loading = null;

hooks.offline = (off) => {
  if (state.offline === off) return;
  state.offline = off;
  $('#cwOffline').hidden = !off;
  $('#widget').hidden = off;
};

async function load() {
  if (loading) return loading;
  loading = (async () => {
    const t0 = Date.now();
    const data = await api('/api/today');
    const t1 = Date.now();
    state.offset = data.server_ms - (t0 + t1) / 2;
    state.snapAt = data.server_ms;
    if (state.settings?.time_format !== data.settings.time_format) fmtCache.clear();
    state.settings = data.settings;
    state.today = data.today;
    state.task = data.task;
    applyTheme(data.settings.theme);
    applyLook(data.settings);
    if (data.settings.language !== currentLang()) await loadLanguage(data.settings.language);
    state.heroKey = null;
    tick();
  })().catch(() => {}).finally(() => { loading = null; });
  return loading;
}

const ACTION = {
  idle: ['start', 'go', 'i-play', 'action.start'],
  off: ['start', 'go', 'i-play', 'action.start'],
  working: ['break_start', 'pause', 'i-coffee', 'action.break_start'],
  done: ['stop', 'finish', 'i-stop', 'action.stop'],
  on_break: ['break_end', 'resume', 'i-return', 'action.break_end'],
  finished: ['resume', 'secondary', 'i-rotate', 'action.resume'],
  finished_short: ['resume', 'secondary', 'i-rotate', 'action.resume'],
};

function renderAction(hs) {
  const a = ACTION[hs];
  $('#cwAction').innerHTML = a
    ? `<button class="action-btn ${a[1] === 'secondary' ? 'secondary' : `primary ${a[1]}`}" data-action="${a[0]}">${icon(a[2])}<span>${esc(t(a[3]))}</span></button>`
    : '';
}

function tick() {
  const d = state.today;
  if (!d) return;
  const now = nowMs();
  if (dateKey(now) !== d.date) { load(); return; }
  const l = live();
  const hs = heroStatus(d, l);
  $('#widget').dataset.status = hs;
  if (state.heroKey !== hs) { state.heroKey = hs; renderAction(hs); }

  const pill = { working: 'working', done: 'done', on_break: 'on_break', finished: 'finished', finished_short: 'short' }[hs] || '';
  $('#cwPill').className = `status-pill ${pill}`;
  $('#cwStatus').textContent = t({ idle: 'status.idle', working: 'status.working', done: 'status.done', on_break: 'status.on_break',
    finished: 'status.finished', finished_short: 'status.finished_short' }[hs] || (d.day_type ? `dt.${d.day_type}` : 'status.nonworking'));

  let label = 'count.left', value = '--:--:--';
  if (hs === 'idle') { label = 'count.target_today'; value = hms(d.target_s); }
  else if (hs === 'working') value = hms(l.remaining, true);
  else if (hs === 'done') { label = 'count.extra'; value = '+' + hms(l.extra); }
  else if (hs === 'on_break') { label = l.done ? 'count.extra_paused' : 'count.left_paused'; value = l.done ? '+' + hms(l.extra) : hms(l.remaining, true); }
  else if (hs.startsWith('finished')) { label = 'count.worked'; value = hms(l.worked); }
  else { label = 'count.today'; value = d.day_type ? t(`dt.${d.day_type}`) : t('count.rest'); }
  $('#cwLabel').textContent = t(label);
  $('#cwCount').textContent = value;
  $('#cwCount').classList.toggle('long', value.length > 8);

  const pct = Math.floor(l.progress * 100);
  $('#cwPct').textContent = `${pct} %`;
  $('#cwFill').style.transform = `scaleX(${l.progress})`;
  $('#cwBar').setAttribute('aria-valuenow', String(pct));
  const exit = hs === 'done' ? l.completedAt : l.exit;
  $('#cwExitLabel').textContent = t(hs === 'done' ? 'exit.completed_at' : hs.startsWith('finished') ? 'exit.left_at' : 'cw.exit');
  $('#cwExit').textContent = exit ? clock(exit) : '—';

  // Tarea activa (2.2): solo informativa aquí; el cambio de tarea se hace en la aplicación completa.
  const box = $('#cwTask');
  box.hidden = !state.task;
  if (state.task) {
    const text = `${state.task.key || state.task.title} · ${hms(Math.max(0, (nowMs() - Date.parse(state.task.start)) / 1000))}`;
    const html = `<i class="tc-dot" data-color="${state.task.color}"></i><span class="tabular">${esc(text)}</span>`;
    if (box.innerHTML !== html) box.innerHTML = html;
  }

  document.title = hs === 'working' ? `${hms(l.remaining, true)} · Jornada` : hs === 'done' ? `+${hms(l.extra)} · Jornada` : 'Jornada';
  checkAlerts(d, l);
}

async function doAction(action, button) {
  if (busy || !state.today) return;
  busy = true;
  button.disabled = true;
  button.classList.add('busy');
  try {
    await api('/api/clock', { method: 'POST', body: { action, expect: state.today.status } });
    syncSend();
  } catch (e) {
    toast(e.message, e.status === 409 ? 'warn' : 'err', 4000);
  } finally {
    busy = false;
    await load();
  }
}

function openFull() {
  if (inPip || window.opener) {
    const main = window.open('/', 'jornada-main');
    main?.focus();
  } else {
    location.href = '/';
  }
}

async function pinWindow() {
  try {
    const pip = await documentPictureInPicture.requestWindow({ width: 360, height: 400 });
    const frame = pip.document.createElement('iframe');
    frame.src = '/compact?pip=1';
    frame.title = 'Jornada';
    frame.style.cssText = 'border:0;width:100%;height:100%;display:block';
    pip.document.body.style.margin = '0';
    pip.document.body.append(frame);
    if (window.opener) window.close();
  } catch (e) {
    toast(t('cm.pip_failed'), 'warn', 5000);
  }
}

$('#cwAction').addEventListener('click', (e) => {
  const b = e.target.closest('[data-action]');
  if (b) doAction(b.dataset.action, b);
});
$('#cwFull').addEventListener('click', openFull);
$('#cwPip').hidden = inPip || !('documentPictureInPicture' in window) || window !== window.top;
$('#cwPip').addEventListener('click', pinWindow);
onSync(() => load());
document.addEventListener('visibilitychange', () => { if (!document.hidden) load(); });
window.addEventListener('focus', () => load());
if (inPip) document.documentElement.classList.add('in-pip');

load().then(() => {
  const loop = () => { setTimeout(loop, 1005 - (nowMs() % 1000)); tick(); };
  loop();
  // Sincronización ligera: la foto del servidor cada 30 s (el contador es local).
  setInterval(() => { if (!document.hidden) load(); }, 30000);
});

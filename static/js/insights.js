/* ============================================================
   Jornada — objetivo semanal, simulador y estadísticas (2.1)
   Todo lo que se calcula aquí viene del servidor (insights.py), que usa
   las mismas reglas que el panel. Nada de este archivo guarda fichajes:
   simular y compensar son consultas de solo lectura.
   Los gráficos son SVG dibujado a mano: sin librerías.
   ============================================================ */
'use strict';

const hm = (sec) => shortDur(Math.abs(sec));                     // 8:30
const signedHm = (sec) => (Math.abs(sec) < 60 ? '0:00' : (sec > 0 ? '+' : '−') + hm(sec));
const toneOf = (sec) => (sec >= 60 ? 'pos' : sec <= -60 ? 'neg' : 'zero');

/* ===================================================== objetivo semanal */

const comp = { open: false, minutes: null, date: null, result: null, timer: null };

function renderWeekly() {
  const w = state.weekly;
  if (!w) return;
  $('#wkRange').textContent = `${longDate(w.from, { day: 'numeric', month: 'short' })} – ${longDate(w.to, { day: 'numeric', month: 'short' })}`;
  const today = dateKey(nowMs());
  const maxS = Math.max(...w.days.map((d) => Math.max(d.target_s, d.worked_s)), 3600);
  const bars = w.days.map((d) => {
    const cls = d.day_type && !d.worked_s ? 'rest' : d.status === 'finished' ? (d.worked_s + 0.5 >= d.target_s ? 'ok' : 'short')
      : (d.status === 'working' || d.status === 'on_break') ? 'live' : '';
    return `<li class="${cls} ${d.date === today ? 'today' : ''}" data-date="${d.date}" title="${esc(`${weekdayName(d.weekday)}: ${hm(d.worked_s)} / ${hm(d.target_s)}`)}">
      <span class="wk-col"><i class="wk-target" style="height:${(d.target_s / maxS) * 100}%"></i><i class="wk-done" data-day="${d.date}" style="height:${(d.worked_s / maxS) * 100}%"></i>
        ${d.day_type && !d.worked_s ? `<span class="wk-mark">${icon(DAY_TYPE_ICONS[d.day_type])}</span>` : ''}</span>
      <span class="wk-day">${esc(t(`weekday.short.${d.weekday}`))}</span></li>`;
  }).join('');
  $('#wkBody').innerHTML = `
    <div class="wk-top">
      <div class="wk-main">
        <span class="wk-big tabular"><span data-wk="worked">${hm(w.worked_s)}</span><small> / ${hm(w.goal_s)} h</small></span>
        <span class="muted small">${esc(t(w.mode === 'auto' ? 'wk.goal_auto' : 'wk.goal_custom'))}${w.excused_s ? ` · ${esc(t('wk.excused', { dur: hm(w.excused_s) }))}` : ''}</span>
      </div>
      <div class="wk-progress" role="progressbar" aria-label="${esc(t('wk.progress'))}" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.round(w.progress * 100)}">
        <span data-wk="bar" style="transform:scaleX(${w.progress})"></span>
      </div>
    </div>
    <dl class="wk-figures">
      <div><dt>${esc(t('wk.remaining'))}</dt><dd class="tabular" data-wk="remaining">${hm(w.remaining_s)}</dd></div>
      <div><dt>${esc(t('wk.extra'))}</dt><dd class="tabular pos" data-wk="extra">${w.extra_s ? '+' + hm(w.extra_s) : '0:00'}</dd></div>
      <div><dt title="${esc(t('wk.closed_hint'))}">${esc(t('wk.closed'))}</dt><dd class="tabular ${toneOf(w.closed_balance_s)}">${signedHm(w.closed_balance_s)}<small class="muted"> · ${esc(t('wk.closed_n', { n: w.closed_days }))}</small></dd></div>
    </dl>
    <ol class="wk-bars" aria-hidden="true">${bars}</ol>`;
  // Mientras se escribe en la compensación, la recarga periódica no la repinta (no se pierde el foco).
  if (!$('#wkComp').contains(document.activeElement)) renderCompensation();
}

/** Ajuste por segundo: lo trabajado hoy desde la última foto del servidor. */
function renderWeeklyLive(d, l) {
  const w = state.weekly;
  if (!w || !$('[data-wk="worked"]')) return;
  const worked = w.worked_s + (l.worked - d.worked_s);
  $('[data-wk="worked"]').textContent = hm(worked);
  $('[data-wk="remaining"]').textContent = hm(Math.max(0, w.goal_s - worked));
  const extra = Math.max(0, worked - w.goal_s);
  $('[data-wk="extra"]').textContent = extra ? '+' + hm(extra) : '0:00';
  const p = w.goal_s ? Math.min(1, worked / w.goal_s) : 0;
  $('[data-wk="bar"]').style.transform = `scaleX(${p})`;
  const todayBar = $(`.wk-done[data-day="${d.date}"]`);
  const maxS = Math.max(...w.days.map((x) => Math.max(x.target_s, x.date === d.date ? l.worked : x.worked_s)), 3600);
  if (todayBar) todayBar.style.height = `${(l.worked / maxS) * 100}%`;
  if (w.goal_s && worked >= w.goal_s && !state.weekCelebrated) {
    state.weekCelebrated = true;
    const key = `wt-week-${w.from}`;
    try {
      if (!localStorage.getItem(key) && worked - (l.worked - d.worked_s) < w.goal_s) {
        localStorage.setItem(key, '1');
        if (motionExpressive()) $('#weeklyCard').classList.add('celebrate');
      }
    } catch (e) { /* sin almacenamiento */ }
  }
}

/* --- compensación simulada (informativa) --- */

function renderCompensation() {
  const box = $('#wkComp');
  if (!state.settings?.weekly_goal?.compensation) { box.innerHTML = ''; return; }
  if (!comp.open) {
    const bal = state.weekly?.closed_balance_s || 0;
    box.innerHTML = `<button type="button" class="ghost-btn small" data-comp-open>${icon('i-scale')}${esc(t(bal >= 60 ? 'comp.cta_extra' : 'comp.cta', { dur: hm(bal) }))}</button>`;
    return;
  }
  const r = comp.result;
  const opts = (r?.choices || []).map((d) => `<option value="${d}" ${d === comp.date ? 'selected' : ''}>${esc(longDate(d, { weekday: 'long', day: 'numeric', month: 'short' }))}</option>`).join('');
  box.innerHTML = `
    <div class="comp-panel">
      <div class="comp-head"><strong>${esc(t('comp.title'))}</strong>
        <button type="button" class="icon-btn small" data-comp-close aria-label="${esc(t('common.close'))}">${icon('i-x')}</button></div>
      <div class="comp-inputs">
        <label class="field"><span>${esc(t('comp.minutes'))}</span><input type="number" min="0" max="600" step="5" id="compMinutes" value="${comp.minutes ?? ''}"></label>
        <label class="field"><span>${esc(t('comp.day'))}</span><select id="compDay">${opts}</select></label>
      </div>
      <div class="comp-out" aria-live="polite">${r?.data ? compText(r.data) : `<span class="muted small">${esc(r?.error || '…')}</span>`}</div>
      <p class="muted small">${esc(t('comp.note'))}</p>
    </div>`;
}

function compText(c) {
  const lines = [
    t('comp.exit', { day: longDate(c.date, { weekday: 'long' }), time: clock(c.exit), base: clock(c.base_exit) }),
    t('comp.worked', { dur: hm(c.worked_s), bal: signedHm(c.day_balance_s) }),
  ];
  if (c.same_week) lines.push(t('comp.week', { before: signedHm(c.week_closed_before_s), after: signedHm(c.week_closed_after_s) }));
  else lines.push(t('comp.next_week'));
  return lines.map((x, i) => `<p class="${i === 0 ? 'comp-lead' : 'small'}">${x}</p>`).join('');
}

async function runCompensation() {
  try {
    const data = await api('/api/compensation', { method: 'POST', body: { date: comp.date, minutes: comp.minutes } });
    comp.result = { ...comp.result, data };
    if (comp.minutes == null) comp.minutes = data.minutes;
    comp.date = data.date;
  } catch (e) {
    comp.result = { ...comp.result, data: null, error: e.message };
  }
  const focused = document.activeElement?.id;
  renderCompensation();
  if (focused) document.getElementById(focused)?.focus();
}

function workdayChoices() {
  const today = dateKey(nowMs());
  const out = [];
  for (let i = 0; i < 14 && out.length < 6; i++) {
    const key = addDays(today, i);
    const wd = state.settings.weekdays[weekdayOf(key)];
    if (wd.workday) out.push(key);
  }
  return out;
}

$('#wkComp').addEventListener('click', (e) => {
  if (e.target.closest('[data-comp-open]')) {
    comp.open = true;
    comp.minutes = null;
    comp.date = null;
    comp.result = { choices: workdayChoices() };
    renderCompensation();
    runCompensation();
  }
  if (e.target.closest('[data-comp-close]')) { comp.open = false; renderCompensation(); }
});
$('#wkComp').addEventListener('input', (e) => {
  if (e.target.id === 'compMinutes') comp.minutes = e.target.value === '' ? 0 : Number(e.target.value);
  if (e.target.id === 'compDay') comp.date = e.target.value;
  clearTimeout(comp.timer);
  comp.timer = setTimeout(runCompensation, 160);
});

/* ============================================================ simulador */

const simDialog = $('#simDialog');
const sim = { day: 'today', defaults: null, base: null, seq: 0, timer: null };

function simDate() {
  const today = dateKey(nowMs());
  return sim.day === 'tomorrow' ? addDays(today, 1) : today;
}

async function openSimulator(day = 'today') {
  sim.day = day;
  setSegment($('#simDay'), day);
  await resetSimulator();
  if (!simDialog.open) simDialog.showModal();
}

/** Carga los valores reales del día como punto de partida. */
async function resetSimulator() {
  let r;
  try { r = await api('/api/simulate', { method: 'POST', body: { date: simDate() } }); } catch (e) { toast(e.message, 'err'); return; }
  sim.defaults = r.defaults;
  $('#simIn').value = r.defaults.clock_in;
  $('#simTarget').value = minutesToHM(r.defaults.target_minutes);
  $('#simBreaks').value = r.defaults.breaks_minutes;
  $('#simBreaks').max = Math.max(180, r.defaults.breaks_minutes);
  $('#simExtra').value = 0;
  $('#simExit').value = '';
  $('#simOptional').checked = false;
  $('#simOptional').closest('label').hidden = !r.defaults.optional_break_minutes;
  $('#simOptionalText').textContent = t('sim.use_optional', { dur: r.defaults.optional_break_minutes });
  renderPresets();
  renderSim(r);
}

function simParams() {
  const target = hmToMinutes($('#simTarget').value);
  return {
    clock_in: $('#simIn').value || undefined,
    target_minutes: target ?? undefined,
    breaks_minutes: Number($('#simBreaks').value),
    extra_break_minutes: Number($('#simExtra').value),
    use_optional: $('#simOptional').checked,
    exit: $('#simExit').value || undefined,
  };
}

function updateSliderLabels() {
  $('#simBreaksVal').textContent = `${Number($('#simBreaks').value)} min`;
  $('#simExtraVal').textContent = `+${Number($('#simExtra').value)} min`;
}

/** Recalcula en cuanto cambia algo (el servidor responde en milisegundos; se descartan respuestas viejas). */
function scheduleSim() {
  updateSliderLabels();
  clearTimeout(sim.timer);
  sim.timer = setTimeout(async () => {
    const seq = ++sim.seq;
    try {
      const r = await api('/api/simulate', { method: 'POST', body: { date: simDate(), params: simParams() } });
      if (seq === sim.seq) renderSim(r);
    } catch (e) {
      if (seq !== sim.seq) return;
      $('#simResult').querySelector('.sim-error')?.remove();
      $('#simResult').insertAdjacentHTML('afterbegin', `<div class="form-error sim-error" role="alert">${esc(e.message)}</div>`);
    }
  }, 60);
}

function renderPresets() {
  const d = sim.defaults;
  const presets = [
    ['+20', 'sim.p_more_break', () => { $('#simExtra').value = 20; $('#simExit').value = ''; }],
    ['17', 'sim.p_exit_17', () => { $('#simExit').value = '17:00'; }],
    ['1830', 'sim.p_exit_1830', () => { $('#simExit').value = '18:30'; }],
  ];
  if (d.optional_break_minutes) presets.push(['opt', 'sim.p_optional', () => { $('#simOptional').checked = true; $('#simExit').value = ''; }]);
  if (sim.day === 'tomorrow') presets.push(['0745', 'sim.p_start_0745', () => { $('#simIn').value = '07:45'; $('#simExit').value = ''; }]);
  $('#simPresets').innerHTML = presets.map(([id, key]) => `<button type="button" class="chip-btn" data-preset="${id}">${esc(t(key))}</button>`).join('');
  sim.presets = Object.fromEntries(presets.map(([id, , fn]) => [id, fn]));
}

/** Barra de la jornada: trabajo, descanso y el desplazamiento de la salida. */
function simBar(s, startMs, spanMs) {
  const a = Date.parse(s.clock_in), b = Date.parse(s.exit);
  const pct = (x) => ((x - startMs) / spanMs) * 100;
  const brk = s.break_offset_s != null && s.break_s
    ? `<i class="b" style="left:${pct(a + s.break_offset_s * 1000)}%;width:${(s.break_s * 1000 / spanMs) * 100}%"></i>` : '';
  return `<span class="sim-bar"><i class="w" style="left:${pct(a)}%;width:${((b - a) / spanMs) * 100}%"></i>${brk}</span>`;
}

function renderSim(r) {
  const { base, sim: s, diff } = r;
  const start = Math.min(Date.parse(base.clock_in), Date.parse(s.clock_in));
  const end = Math.max(Date.parse(base.exit), Date.parse(s.exit));
  const span = Math.max(1, end - start);
  const diffCell = (sec, kind) => {
    if (Math.abs(sec) < 60) return `<span class="sim-diff zero">${esc(t('sim.same'))}</span>`;
    const later = kind === 'exit' ? sec > 0 : null;
    const tone = kind === 'balance' ? toneOf(sec) : kind === 'exit' ? (later ? 'later' : 'earlier') : 'neutral';
    return `<span class="sim-diff ${tone}">${signedHm(sec)}${kind === 'exit' ? ` <small>${esc(t(later ? 'sim.later' : 'sim.earlier'))}</small>` : ''}</span>`;
  };
  const row = (label, a, b, d) => `<tr><th scope="row">${esc(label)}</th><td class="tabular">${a}</td><td class="tabular strong">${b}</td><td>${d}</td></tr>`;
  const added = s.added_break_s >= 60 ? `<p class="muted small sim-note">${icon('i-info')}${esc(t('sim.added_break', { dur: human(s.added_break_s) }))}</p>` : '';
  const flags = s.flags.includes('break_long') ? `<p class="small sim-note warn">${icon('i-alert')}${esc(t('sim.break_long'))}</p>` : '';
  const verdict = Math.abs(s.balance_s) < 60 ? t('sim.v_exact', { time: clock(s.exit) })
    : s.balance_s > 0 ? t('sim.v_extra', { time: clock(s.exit), dur: human(s.balance_s) })
      : t('sim.v_short', { time: clock(s.exit), dur: human(-s.balance_s) });
  $('#simResult').innerHTML = `
    <div class="sim-hero">
      <span class="muted small">${esc(t(r.status === 'finished' ? 'sim.would_have' : 'sim.you_leave'))}</span>
      <span class="sim-exit tabular">${bigClock(Date.parse(s.exit))}</span>
      <span class="sim-verdict ${toneOf(s.balance_s)}">${verdict}</span>
    </div>
    <div class="sim-compare" aria-hidden="true">
      <div><span class="small muted">${esc(t('sim.current'))}</span>${simBar(base, start, span)}</div>
      <div><span class="small muted">${esc(t('sim.simulated'))}</span>${simBar(s, start, span)}</div>
      <div class="sim-scale small muted tabular"><span>${clock(start)}</span><span>${clock(end)}</span></div>
    </div>
    <table class="sim-table">
      <thead><tr><th></th><th>${esc(t('sim.current'))}</th><th>${esc(t('sim.simulated'))}</th><th>${esc(t('sim.difference'))}</th></tr></thead>
      <tbody>
        ${row(t('sim.r_exit'), clock(base.exit), clock(s.exit), diffCell(diff.exit_s, 'exit'))}
        ${row(t('sim.r_worked'), hm(base.worked_s), hm(s.worked_s), diffCell(diff.worked_s, 'neutral'))}
        ${row(t('sim.r_breaks'), hm(base.break_s), hm(s.break_s), diffCell(diff.break_s, 'neutral'))}
        ${row(t('sim.r_balance'), signedHm(base.balance_s), signedHm(s.balance_s), diffCell(diff.balance_s, 'balance'))}
      </tbody>
    </table>
    ${added}${flags}`;
  updateSliderLabels();
}

$('#simForm').addEventListener('input', scheduleSim);
$('#simForm').addEventListener('submit', (e) => e.preventDefault());
$('#simDay').addEventListener('click', (e) => {
  const b = e.target.closest('[data-value]');
  if (!b) return;
  sim.day = b.dataset.value;
  resetSimulator();
});
$('#simExitClear').addEventListener('click', () => { $('#simExit').value = ''; scheduleSim(); });
$('#simReset').addEventListener('click', resetSimulator);
$('#simPresets').addEventListener('click', (e) => {
  const b = e.target.closest('[data-preset]');
  if (!b) return;
  sim.presets[b.dataset.preset]();
  scheduleSim();
});
$('#simBtn').addEventListener('click', () => openSimulator());

/* ================================================= estadísticas avanzadas */

const statsDialog = $('#statsDialog');
const st = { month: null, scope: 'month', series: 'weekly', data: null, tables: new Set() };

async function openStats() {
  const today = dateKey(nowMs());
  st.month = st.month || today.slice(0, 7);
  if (!statsDialog.open) statsDialog.showModal();
  await loadStats();
}

async function loadStats() {
  const body = $('#stBody');
  body.setAttribute('aria-busy', 'true');
  try {
    st.data = await api(`/api/stats?month=${st.month}&scope=${st.scope}&weeks=12`);
  } catch (e) {
    body.innerHTML = `<div class="form-error" role="alert">${esc(e.message)}</div>`;
    return;
  }
  body.removeAttribute('aria-busy');
  $('#stSub').textContent = longDate(`${st.month}-01`, { month: 'long', year: 'numeric' });
  $('#stNext').disabled = st.month >= dateKey(nowMs()).slice(0, 7);
  renderStatsBody();
}

function panel(id, title, desc, chart, table, extra = '') {
  const open = st.tables.has(id);
  return `<section class="st-panel" data-panel="${id}" aria-labelledby="st-${id}">
    <header class="st-head"><div><h4 id="st-${id}">${esc(title)}</h4><p class="muted small">${esc(desc)}</p></div>
      <div class="st-tools">${extra}<button type="button" class="ghost-btn small" data-table="${id}" aria-expanded="${open}">${icon('i-layers')}${esc(t(open ? 'st.hide_data' : 'st.show_data'))}</button></div></header>
    <div class="st-chart" ${open ? 'hidden' : ''}>${chart}</div>
    <div class="table-wrap st-table" ${open ? '' : 'hidden'}>${table}</div>
  </section>`;
}

function renderStatsBody() {
  const d = st.data;
  const body = $('#stBody');
  if (!d.has_data) {
    body.innerHTML = `<div class="empty-state">${icon('i-chart')}<span>${esc(t('st.empty'))}</span></div>`;
    return;
  }
  body.innerHTML = [heatmapPanel(d), averagesPanel(d), balancePanel(d), weeklyPanel(d)].join('');
}

/* --- mapa de actividad --- */

const CAT_KEYS = ['complete', 'incomplete', 'progress', 'absence', 'nonworking', 'none'];

function heatmapPanel(d) {
  const first = d.heatmap[0];
  const lead = first.weekday;
  const maxW = Math.max(...d.heatmap.map((c) => c.worked_s), 8 * 3600);
  const cat = (c) => (c.category === 'absence_deficit' ? 'incomplete' : c.category === 'unclosed' ? 'incomplete' : c.category === 'off' ? 'absence' : c.category);
  const cells = Array.from({ length: lead }, () => '<span class="hm-cell out"></span>').concat(d.heatmap.map((c) => {
    const k = cat(c);
    const level = c.worked_s ? Math.min(4, 1 + Math.floor((c.worked_s / maxW) * 4)) : 0;
    const text = `${longDate(c.date, { weekday: 'long', day: 'numeric', month: 'long' })} · ${t(`hm.${k}`)}${c.worked_s ? ` · ${hm(c.worked_s)}` : ''}${c.label ? ` · ${c.label}` : ''}`;
    return `<span class="hm-cell ${k} l${level}" role="img" aria-label="${esc(text)}" data-tip="${esc(text)}">
      <b>${Number(c.date.slice(8))}</b>${k === 'absence' && c.day_type ? icon(DAY_TYPE_ICONS[c.day_type]) : ''}${k === 'incomplete' ? '<i class="hm-x"></i>' : ''}</span>`;
  })).join('');
  const legend = CAT_KEYS.map((k) => `<span><i class="hm-key ${k}"></i>${esc(t(`hm.${k}`))}</span>`).join('');
  const chart = `<div class="hm-week">${[0, 1, 2, 3, 4, 5, 6].map((i) => `<span>${esc(t(`weekday.short.${i}`))}</span>`).join('')}</div>
    <div class="hm-grid">${cells}</div><div class="legend hm-legend">${legend}</div>`;
  const table = `<table class="data-table"><thead><tr><th>${esc(t('th.day'))}</th><th>${esc(t('st.col_state'))}</th><th class="num">${esc(t('th.worked'))}</th><th class="num">${esc(t('th.target'))}</th></tr></thead><tbody>
    ${d.heatmap.filter((c) => c.category !== 'future').map((c) => `<tr><td>${esc(longDate(c.date, { weekday: 'short', day: 'numeric', month: 'short' }))}</td><td>${esc(t(`hm.${cat(c)}`))}${c.label ? ` · ${esc(c.label)}` : ''}</td>
      <td class="num">${c.worked_s ? hm(c.worked_s) : '—'}</td><td class="num">${c.target_s ? hm(c.target_s) : '—'}</td></tr>`).join('')}</tbody></table>`;
  return panel('heatmap', t('st.heatmap'), t('st.heatmap_desc'), chart, table);
}

/* --- promedios --- */

function averagesPanel(d) {
  const a = d.averages;
  const timeOf = (sec) => (sec == null ? '—' : `${pad(Math.floor(sec / 3600))}:${pad(Math.floor((sec % 3600) / 60))}`);
  const tile = (label, value, sub = '') => `<div class="avg-tile"><span class="muted small">${esc(label)}</span><strong class="tabular">${value}</strong>${sub ? `<small class="muted">${esc(sub)}</small>` : ''}</div>`;
  const list = (items) => items.length ? `<ol class="rank">${items.map((c) => `<li><span>${esc(longDate(c.date, { weekday: 'short', day: 'numeric', month: 'short' }))}</span>
      <span class="rank-bar"><i style="transform:scaleX(${Math.min(1, c.worked_s / Math.max(...[...a.most, ...a.least].map((x) => x.worked_s), 1))})"></i></span><b class="tabular">${hm(c.worked_s)}</b></li>`).join('')}</ol>` : `<p class="muted small">—</p>`;
  const scope = `<div class="segmented small-seg" data-scope>${['month', 'all'].map((s) => `<button type="button" data-value="${s}" class="${st.scope === s ? 'active' : ''}">${esc(t(`st.scope_${s}`))}</button>`).join('')}</div>`;
  const chart = `<div class="avg-grid">
      ${tile(t('st.avg_in'), timeOf(a.clock_in_s))}
      ${tile(t('st.avg_out'), timeOf(a.clock_out_s))}
      ${tile(t('st.avg_worked'), a.worked_s == null ? '—' : hm(a.worked_s))}
      ${tile(t('st.avg_break'), a.break_s == null ? '—' : hm(a.break_s))}
    </div>
    <p class="muted small">${esc(t('st.avg_basis', { n: a.days }))}${a.open_days ? ` ${esc(t('st.avg_open', { n: a.open_days }))}` : ''}</p>
    <div class="rank-grid"><div><h5>${esc(t('st.most'))}</h5>${list(a.most)}</div><div><h5>${esc(t('st.least'))}</h5>${list(a.least)}</div></div>`;
  const table = `<table class="data-table"><tbody>
    <tr><th scope="row">${esc(t('st.avg_in'))}</th><td class="num">${timeOf(a.clock_in_s)}</td></tr>
    <tr><th scope="row">${esc(t('st.avg_out'))}</th><td class="num">${timeOf(a.clock_out_s)}</td></tr>
    <tr><th scope="row">${esc(t('st.avg_worked'))}</th><td class="num">${a.worked_s == null ? '—' : hm(a.worked_s)}</td></tr>
    <tr><th scope="row">${esc(t('st.avg_break'))}</th><td class="num">${a.break_s == null ? '—' : hm(a.break_s)}</td></tr>
    <tr><th scope="row">${esc(t('st.avg_days'))}</th><td class="num">${a.days}</td></tr></tbody></table>`;
  return panel('averages', t('st.averages'), t('st.averages_desc'), chart, table, scope);
}

/* --- evolución del balance (línea) --- */

function niceStep(range) {
  const steps = [1800, 3600, 7200, 3 * 3600, 5 * 3600, 10 * 3600, 20 * 3600, 50 * 3600];
  return steps.find((s) => range / s <= 5) || 100 * 3600;
}

function balancePanel(d) {
  const series = st.series === 'monthly' ? d.monthly : d.weekly;
  const label = (p) => (p.from ? longDate(p.from, { day: 'numeric', month: 'short' }) : longDate(`${p.month}-01`, { month: 'short', year: '2-digit' }));
  const W = 520, H = 230, L = 52, R = 16, T = 18, B = 30;
  const vals = series.map((p) => p.cumulative_s);
  let lo = Math.min(0, ...vals), hi = Math.max(0, ...vals);
  if (hi - lo < 3600) { hi += 1800; lo -= 1800; }
  const step = niceStep(hi - lo);
  lo = Math.floor(lo / step) * step; hi = Math.ceil(hi / step) * step;
  const x = (i) => L + (i / Math.max(1, series.length - 1)) * (W - L - R);
  const y = (v) => T + ((hi - v) / (hi - lo)) * (H - T - B);
  const grid = [];
  for (let v = lo; v <= hi + 1; v += step) {
    grid.push(`<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" class="${v === 0 ? 'zero' : ''}"/><text x="${L - 8}" y="${y(v) + 4}" text-anchor="end">${signedHm(v)}</text>`);
  }
  const path = series.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p.cumulative_s).toFixed(1)}`).join('');
  const area = `${path}L${x(series.length - 1).toFixed(1)},${y(0)}L${x(0).toFixed(1)},${y(0)}Z`;
  const every = Math.ceil(series.length / 5);
  const xl = series.map((p, i) => (i % every === 0 || i === series.length - 1 ? `<text x="${x(i)}" y="${H - 8}" text-anchor="middle">${esc(label(p))}</text>` : '')).join('');
  const last = series[series.length - 1];
  const dots = series.map((p, i) => `<g class="pt" data-tip="${esc(`${label(p)} · ${t('st.period')} ${signedHm(p.balance_s)} · ${t('st.cumulative')} ${signedHm(p.cumulative_s)}`)}">
      <rect x="${x(i) - (W - L - R) / series.length / 2}" y="${T}" width="${(W - L - R) / series.length}" height="${H - T - B}" class="hit"/>
      <circle cx="${x(i)}" cy="${y(p.cumulative_s)}" r="${i === series.length - 1 ? 5 : 3.5}"/></g>`).join('');
  const chart = `<svg class="chart line-chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(t('st.balance_aria', { value: signedHm(last.cumulative_s) }))}">
      <g class="grid">${grid.join('')}</g><g class="axis">${xl}</g>
      <path class="area" d="${area}"/><path class="line" d="${path}"/>${dots}
      <text class="end-label" x="${x(series.length - 1) - 8}" y="${y(last.cumulative_s) - 10}" text-anchor="end">${signedHm(last.cumulative_s)}</text>
    </svg>`;
  const toggle = `<div class="segmented small-seg" data-series>${['weekly', 'monthly'].map((s) => `<button type="button" data-value="${s}" class="${st.series === s ? 'active' : ''}">${esc(t(`st.${s}`))}</button>`).join('')}</div>`;
  const table = `<table class="data-table"><thead><tr><th>${esc(t('st.period'))}</th><th class="num">${esc(t('th.worked'))}</th><th class="num">${esc(t('th.balance'))}</th><th class="num">${esc(t('st.cumulative'))}</th></tr></thead><tbody>
    ${series.map((p) => `<tr><td>${esc(label(p))}</td><td class="num">${hm(p.worked_s)}</td><td class="num ${toneOf(p.balance_s)}">${signedHm(p.balance_s)}</td><td class="num">${signedHm(p.cumulative_s)}</td></tr>`).join('')}</tbody></table>`;
  return panel('balance', t('st.balance'), t('st.balance_desc'), chart, table, toggle);
}

/* --- comparativa semanal (barras) --- */

function weeklyPanel(d) {
  const weeks = d.weekly.slice(-8);
  const W = 520, H = 240, L = 34, R = 6, T = 24, B = 30;
  const maxV = Math.max(...weeks.map((w) => Math.max(w.goal_s, w.worked_s)), 3600);
  const step = niceStep(maxV);
  const top = Math.ceil(maxV / step) * step;
  const y = (v) => T + (1 - v / top) * (H - T - B);
  const slot = (W - L - R) / weeks.length;
  const bw = Math.min(26, slot / 3);
  const grid = [];
  for (let v = 0; v <= top + 1; v += step) grid.push(`<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}"/><text x="${L - 6}" y="${y(v) + 4}" text-anchor="end">${Math.round(v / 3600)}</text>`);
  // Rectángulo con las esquinas superiores redondeadas, apoyado en la base.
  const bar = (x, v, cls) => {
    const h = Math.max(0, y(0) - y(v)), r = Math.min(4, h, bw / 2);
    if (h < 0.5) return '';
    return `<path class="${cls}" d="M${x},${y(0)}V${y(v) + r}Q${x},${y(v)} ${x + r},${y(v)}H${x + bw - r}Q${x + bw},${y(v)} ${x + bw},${y(v) + r}V${y(0)}Z"/>`;
  };
  const groups = weeks.map((w, i) => {
    const cx = L + slot * i + slot / 2;
    const tip = `${t('st.week_of', { date: longDate(w.from, { day: 'numeric', month: 'short' }) })} · ${t('st.goal')} ${hm(w.goal_s)} · ${t('st.done')} ${hm(w.worked_s)} · ${t('th.balance')} ${signedHm(w.balance_s)}`;
    return `<g class="wbar ${w.current ? 'current' : ''}" data-tip="${esc(tip)}">
      <rect class="hit" x="${cx - slot / 2}" y="${T}" width="${slot}" height="${H - T - B}"/>
      ${bar(cx - bw - 1, w.goal_s, 'goal')}${bar(cx + 1, w.worked_s, 'done')}
      <text class="bal ${toneOf(w.balance_s)}" x="${cx}" y="${Math.min(y(w.goal_s), y(w.worked_s)) - 6}" text-anchor="middle">${Math.abs(w.balance_s) >= 60 ? signedHm(w.balance_s) : ''}</text>
      <text class="xl" x="${cx}" y="${H - 10}" text-anchor="middle">${esc(longDate(w.from, { day: 'numeric', month: 'short' }))}</text></g>`;
  }).join('');
  const chart = `<div class="legend chart-legend"><span><i class="lg goal"></i>${esc(t('st.goal'))}</span><span><i class="lg done"></i>${esc(t('st.done'))}</span><span class="muted">${esc(t('st.bal_label'))}</span></div>
    <svg class="chart bar-chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(t('st.weekly_aria'))}">
      <g class="grid">${grid.join('')}</g><text class="unit" x="${L - 6}" y="12" text-anchor="end">h</text>${groups}
    </svg>`;
  const table = `<table class="data-table"><thead><tr><th>${esc(t('st.week'))}</th><th class="num">${esc(t('st.goal'))}</th><th class="num">${esc(t('st.done'))}</th><th class="num">${esc(t('th.balance'))}</th></tr></thead><tbody>
    ${weeks.map((w) => `<tr><td>${esc(longDate(w.from, { day: 'numeric', month: 'short', year: 'numeric' }))}${w.current ? ` <span class="muted small">(${esc(t('st.current_week'))})</span>` : ''}</td><td class="num">${hm(w.goal_s)}</td><td class="num">${hm(w.worked_s)}</td>
      <td class="num ${toneOf(w.balance_s)}">${signedHm(w.balance_s)}${w.pending_s ? ` <span class="pend small">${esc(t('st.pending_short'))}</span>` : ''}</td></tr>`).join('')}</tbody></table>`;
  return panel('weekly', t('st.weekly'), t('st.weekly_desc'), chart, table);
}

/* --- tooltip compartido (puntero y teclado) --- */

let tipEl = null;
function showTip(target, x, y) {
  if (!tipEl) {
    tipEl = document.createElement('div');
    tipEl.className = 'chart-tip';
    tipEl.setAttribute('role', 'tooltip');
    statsDialog.append(tipEl);
  }
  tipEl.textContent = target.dataset.tip;
  tipEl.hidden = false;
  const box = statsDialog.getBoundingClientRect();
  const w = tipEl.offsetWidth;
  tipEl.style.transform = `translate(${Math.max(8, Math.min(box.width - w - 8, x - box.left - w / 2))}px, ${y - box.top - tipEl.offsetHeight - 12}px)`;
}

$('#stBody').addEventListener('pointermove', (e) => {
  const target = e.target.closest('[data-tip]');
  if (target) showTip(target, e.clientX, e.clientY);
  else if (tipEl) tipEl.hidden = true;
});
$('#stBody').addEventListener('pointerleave', () => { if (tipEl) tipEl.hidden = true; });
$('#stBody').addEventListener('click', (e) => {
  const tb = e.target.closest('[data-table]');
  if (tb) {
    const id = tb.dataset.table;
    if (st.tables.has(id)) st.tables.delete(id); else st.tables.add(id);
    renderStatsBody();
    $(`[data-table="${id}"]`)?.focus();
    return;
  }
  const scope = e.target.closest('[data-scope] [data-value]');
  if (scope) { st.scope = scope.dataset.value; loadStats(); return; }
  const series = e.target.closest('[data-series] [data-value]');
  if (series) { st.series = series.dataset.value; renderStatsBody(); }
});
function shiftStatsMonth(delta) {
  let [y, m] = st.month.split('-').map(Number);
  m += delta;
  if (m < 1) { m = 12; y--; }
  if (m > 12) { m = 1; y++; }
  st.month = `${y}-${pad(m)}`;
  loadStats();
}
$('#stPrev').addEventListener('click', () => shiftStatsMonth(-1));
$('#stNext').addEventListener('click', () => shiftStatsMonth(1));
$('#advStatsBtn').addEventListener('click', openStats);

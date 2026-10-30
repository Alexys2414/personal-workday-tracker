/* ============================================================
   Jornada — atajos de teclado configurables
   Las teclas se identifican con KeyboardEvent.code (posición física),
   así que funcionan igual con cualquier distribución de teclado.
   Formato guardado: "Ctrl+Alt+Shift+Meta+<code>" (modificadores en ese orden).
   Solo actúan con la pestaña enfocada: no hay hooks globales del sistema.
   ============================================================ */
'use strict';

const SC_ACTIONS = ['start_day', 'break_start', 'break_end', 'stop_day', 'open_calendar',
  'open_stats', 'open_settings', 'toggle_theme', 'edit_today', 'open_simulator'];
const SC_MODIFIER_CODES = new Set(['ControlLeft', 'ControlRight', 'AltLeft', 'AltRight', 'ShiftLeft', 'ShiftRight',
  'MetaLeft', 'MetaRight', 'OSLeft', 'OSRight', 'CapsLock', 'Fn', 'AltGraph']);
const IS_MAC = /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent);

// Combinaciones que suelen pertenecer al navegador o al sistema: se avisa al asignarlas.
const SC_RESERVED = new Set([
  ...'TWNLRFGPSDHJKEOUQACVXZYB'.split('').map((k) => `Ctrl+Key${k}`),
  ...'NTRQWIJCKEMPBOHAZ'.split('').map((k) => `Ctrl+Shift+Key${k}`),
  ...'0123456789'.split('').map((d) => `Ctrl+Digit${d}`),
  'Ctrl+Tab', 'Ctrl+Shift+Tab', 'Ctrl+Equal', 'Ctrl+Minus', 'Ctrl+PageUp', 'Ctrl+PageDown', 'Ctrl+F4',
  'Ctrl+Shift+Delete', 'Ctrl+Space', 'Alt+Space', 'Alt+Tab', 'Alt+F4', 'Alt+ArrowLeft', 'Alt+ArrowRight',
  'Alt+Home', 'Alt+KeyD', 'Alt+KeyE', 'Alt+KeyF', 'Ctrl+Alt+KeyT', 'Ctrl+Alt+Delete', 'Ctrl+Alt+ArrowLeft',
  'Ctrl+Alt+ArrowRight', 'Ctrl+Alt+ArrowUp', 'Ctrl+Alt+ArrowDown', 'F1', 'F3', 'F5', 'F6', 'F7', 'F11', 'F12',
  'Ctrl+F5', 'Shift+F5', 'Escape',
]);

let scDraft = null;        // copia editable de los atajos mientras los ajustes están abiertos
let scListening = null;    // acción que espera una tecla
let scDefaults = null;

const SYMBOLS = {
  ArrowUp: '↑', ArrowDown: '↓', ArrowLeft: '←', ArrowRight: '→', Minus: '-', Equal: '=', BracketLeft: '[',
  BracketRight: ']', Semicolon: ';', Quote: "'", Backquote: '`', Backslash: '\\', Comma: ',', Period: '.',
  Slash: '/', IntlBackslash: '<', PageUp: 'PgUp', PageDown: 'PgDn', Home: 'Home', End: 'End', Insert: 'Ins',
  NumpadAdd: 'Num +', NumpadSubtract: 'Num -', NumpadMultiply: 'Num *', NumpadDivide: 'Num /',
  NumpadDecimal: 'Num .', NumpadEnter: 'Num ⏎',
};

function comboFromEvent(e) {
  if (SC_MODIFIER_CODES.has(e.code) || !e.code) return null;
  const mods = [];
  if (e.ctrlKey) mods.push('Ctrl');
  if (e.altKey) mods.push('Alt');
  if (e.shiftKey) mods.push('Shift');
  if (e.metaKey) mods.push('Meta');
  return [...mods, e.code].join('+');
}

function keyLabel(part) {
  if (part === 'Ctrl') return IS_MAC ? '⌃' : t('key.Ctrl');
  if (part === 'Alt') return IS_MAC ? '⌥' : t('key.Alt');
  if (part === 'Shift') return IS_MAC ? '⇧' : t('key.Shift');
  if (part === 'Meta') return IS_MAC ? '⌘' : t('key.Meta');
  if (/^Key[A-Z]$/.test(part)) return part.slice(3);
  if (/^Digit\d$/.test(part)) return part.slice(5);
  if (/^Numpad\d$/.test(part)) return `Num ${part.slice(6)}`;
  if (['Space', 'Enter', 'Backspace', 'Delete', 'Escape', 'Tab'].includes(part)) return t(`key.${part}`);
  return SYMBOLS[part] || part;
}

function keycaps(combo, cls = '') {
  if (!combo) return `<span class="sc-none">${esc(t('sc.none'))}</span>`;
  return `<span class="keys ${cls}">${combo.split('+').map((p) => `<kbd>${esc(keyLabel(p))}</kbd>`).join('<span class="plus">+</span>')}</span>`;
}

const scName = (action) => t(`sc.a.${action}`);
const scWarnings = (combo) => {
  if (!combo) return [];
  const out = [];
  if (SC_RESERVED.has(combo) || combo.startsWith('Meta+') || combo.includes('+Meta+')) out.push(t('sc.reserved'));
  if (!/^(Ctrl|Alt|Meta)\+/.test(combo) && !/^Shift\+F\d/.test(combo) && !/^F\d/.test(combo)) out.push(t('sc.no_modifier'));
  return out;
};

/* ------------------------------------------------------- editor en ajustes */

function loadShortcutDraft() {
  scDraft = { ...(state.settings?.shortcuts || {}) };
  scListening = null;
}

function shortcutDraft() {
  return scDraft ? { ...scDraft } : undefined;
}

function renderShortcutSettings() {
  if (!scDraft) loadShortcutDraft();
  $('#scList').innerHTML = SC_ACTIONS.map((action) => {
    const combo = scDraft[action];
    const warns = scWarnings(combo);
    return `<li class="sc-row ${scListening === action ? 'listening' : ''}" data-action="${action}">
      <span class="sc-name">${esc(scName(action))}</span>
      <span class="sc-keys" aria-live="polite">${scListening === action
        ? `<span class="listen-pill"><i></i>${esc(t('sc.listening'))}</span><span class="muted small">${esc(t('sc.listening_hint'))}</span>`
        : keycaps(combo)}</span>
      <span class="sc-btns">
        <button type="button" class="ghost-btn small" data-assign>${icon('i-keyboard')}${esc(t(combo ? 'sc.change' : 'sc.assign'))}</button>
        <button type="button" class="icon-btn small" data-clear ${combo ? '' : 'disabled'} title="${esc(t('sc.clear'))}" aria-label="${esc(t('sc.clear'))}">${icon('i-x')}</button>
      </span>
      ${warns.length ? `<span class="sc-warn">${icon('i-info')}${esc(warns.join(' '))}</span>` : ''}
      <span class="sc-error" hidden></span>
    </li>`;
  }).join('');
}

function startListening(action) {
  scListening = action;
  renderShortcutSettings();
  $(`#scList [data-action="${action}"] [data-assign]`)?.focus();
}

function stopListening() {
  scListening = null;
  renderShortcutSettings();
}

function rowError(action, message) {
  const row = $(`#scList [data-action="${action}"]`);
  const box = row?.querySelector('.sc-error');
  if (!box) return;
  box.textContent = message;
  box.hidden = false;
  row.classList.remove('shake');
  void row.offsetWidth;
  row.classList.add('shake');
}

function flashRow(action) {
  const row = $(`#scList [data-action="${action}"]`);
  if (!row) return;
  row.classList.remove('assigned');
  void row.offsetWidth;
  row.classList.add('assigned');
}

/** Captura de teclas mientras una acción espera su combinación. */
window.addEventListener('keydown', (e) => {
  if (!scListening) return;
  e.preventDefault();
  e.stopPropagation();
  const action = scListening;
  if (e.code === 'Escape' && !e.ctrlKey && !e.altKey && !e.shiftKey && !e.metaKey) { stopListening(); return; }
  const combo = comboFromEvent(e);
  const pill = $(`#scList [data-action="${action}"] .listen-pill`);
  if (!combo) {            // solo modificadores: vista previa de lo que se mantiene pulsado
    const mods = [e.ctrlKey && 'Ctrl', e.altKey && 'Alt', e.shiftKey && 'Shift', e.metaKey && 'Meta'].filter(Boolean);
    if (pill && mods.length) pill.innerHTML = `<i></i>${keycaps(mods.join('+') + '+…').replace('<kbd>…</kbd>', '<kbd class="ghost">…</kbd>')}`;
    return;
  }
  const owner = SC_ACTIONS.find((a) => a !== action && scDraft[a] === combo);
  scListening = null;
  if (owner) {
    renderShortcutSettings();
    rowError(action, t('sc.duplicate', { action: scName(owner) }));
    return;
  }
  scDraft[action] = combo;
  renderShortcutSettings();
  flashRow(action);
}, true);

window.addEventListener('keyup', (e) => {
  if (!scListening) return;
  const pill = $(`#scList [data-action="${scListening}"] .listen-pill`);
  if (pill && !e.ctrlKey && !e.altKey && !e.shiftKey && !e.metaKey) {
    pill.innerHTML = `<i></i>${esc(t('sc.listening'))}`;
  }
}, true);

$('#scList').addEventListener('click', (e) => {
  const row = e.target.closest('.sc-row');
  if (!row) return;
  if (e.target.closest('[data-assign]')) {
    if (scListening === row.dataset.action) stopListening();
    else startListening(row.dataset.action);
  } else if (e.target.closest('[data-clear]')) {
    scDraft[row.dataset.action] = null;
    scListening = null;
    renderShortcutSettings();
  }
});

$('#scRestore').addEventListener('click', () => {
  scDraft = { ...(scDefaults || {}) };
  scListening = null;
  renderShortcutSettings();
  SC_ACTIONS.forEach(flashRow);
  toast(t('sc.restored'), 'info', 3000);
});

// Esc mientras se escucha una tecla no debe cerrar los ajustes.
$('#settingsDialog').addEventListener('cancel', (e) => { if (scListening) e.preventDefault(); });
$('#settingsDialog').addEventListener('close', () => { scListening = null; scDraft = null; });

fetch('/api/shortcuts/defaults').then((r) => r.json()).then((d) => { scDefaults = d; }).catch(() => {});

/* ------------------------------------------------------- ejecución */

function isTyping(target) {
  if (!target || target === document.body) return false;
  const tag = target.tagName;
  return target.isContentEditable || tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT';
}

function shortcutHud(combo, label) {
  let hud = $('#scHud');
  if (!hud) {
    hud = document.createElement('div');
    hud.id = 'scHud';
    hud.className = 'sc-hud';
    hud.setAttribute('aria-hidden', 'true');
    document.body.append(hud);
  }
  hud.innerHTML = `${keycaps(combo)}<span>${esc(label)}</span>`;
  hud.classList.remove('show');
  void hud.offsetWidth;
  hud.classList.add('show');
  clearTimeout(shortcutHud.timer);
  shortcutHud.timer = setTimeout(() => hud.classList.remove('show'), 1100);
}

function runShortcut(action, combo) {
  const d = state.today;
  if (!d || state.closed) return;
  const hs = heroStatus(d, live());
  const fichaje = {
    start_day: [['idle', 'off'], 'start'],
    break_start: [['working', 'done'], 'break_start'],
    break_end: [['on_break'], 'break_end'],
    stop_day: [['working', 'done', 'on_break'], 'stop'],
  }[action];
  if (fichaje) {
    if (!fichaje[0].includes(hs) || state.busy) {
      toast(t('toast.unavailable', { action: scName(action) }), 'info', 2400);
      return;
    }
    shortcutHud(combo, scName(action));
    doAction(fichaje[1], $(`[data-action="${fichaje[1]}"]`));
    return;
  }
  shortcutHud(combo, scName(action));
  if (action === 'open_calendar') focusSection('historySection');
  else if (action === 'open_stats') focusSection('statsSection');
  else if (action === 'open_settings') openSettings();
  else if (action === 'toggle_theme') toggleTheme();
  else if (action === 'edit_today') openEditor(d.date);
  else if (action === 'open_simulator' && window.openSimulator) openSimulator();
}

window.addEventListener('keydown', (e) => {
  if (scListening || e.defaultPrevented || e.repeat || e.isComposing) return;
  if (isTyping(e.target) || document.querySelector('dialog[open]')) return;
  const combo = comboFromEvent(e);
  if (!combo) return;
  const shortcuts = state.settings?.shortcuts || {};
  const action = SC_ACTIONS.find((a) => shortcuts[a] === combo);
  if (!action) return;            // las combinaciones no asignadas siguen siendo del navegador
  e.preventDefault();
  runShortcut(action, combo);
});

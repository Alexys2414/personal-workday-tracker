/* ============================================================
   Jornada — traducciones (cliente)
   El diccionario activo llega incrustado en la página (#i18n-data),
   así que no hay parpadeo al cargar. Cambiar de idioma descarga el
   otro JSON de /static/i18n/ y retraduce sin recargar.
   ============================================================ */
'use strict';

const I18N = {
  dict: JSON.parse(document.getElementById('i18n-data').textContent),
  cache: {},
};
I18N.cache[I18N.dict._lang] = I18N.dict;

/** Traduce `key` sustituyendo {param}. Sin traducción, devuelve la clave. */
function t(key, params) {
  let text = I18N.dict[key];
  if (text === undefined) text = key;
  if (params) text = text.replace(/\{(\w+)\}/g, (m, k) => (params[k] !== undefined ? params[k] : m));
  return text;
}

const currentLang = () => I18N.dict._lang;
const currentLocale = () => I18N.dict._locale;

/** Retraduce los textos estáticos marcados con data-i18n*. */
function applyI18n(root = document) {
  root.querySelectorAll('[data-i18n]').forEach((el) => { el.textContent = t(el.dataset.i18n); });
  root.querySelectorAll('[data-i18n-html]').forEach((el) => { el.innerHTML = t(el.dataset.i18nHtml); });
  root.querySelectorAll('[data-i18n-title]').forEach((el) => { el.title = t(el.dataset.i18nTitle); });
  root.querySelectorAll('[data-i18n-aria]').forEach((el) => { el.setAttribute('aria-label', t(el.dataset.i18nAria)); });
  root.querySelectorAll('[data-i18n-placeholder]').forEach((el) => { el.placeholder = t(el.dataset.i18nPlaceholder); });
}

async function loadLanguage(code) {
  if (!I18N.cache[code]) {
    const res = await fetch(`/static/i18n/${code}.json`, { cache: 'no-cache' });
    if (!res.ok) throw new Error(`i18n ${code}`);
    I18N.cache[code] = await res.json();
  }
  I18N.dict = I18N.cache[code];
  document.documentElement.lang = code;
  applyI18n();
}

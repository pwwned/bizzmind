/* Inceptiq Analytics — i18n core (shared by every page).
   Language lives in the `lang` cookie (bg|en) so the server sees it too
   (error messages, AI output language, PDF labels). Dictionaries are
   registered per page via I18N.add(lang, {key: text}). Usage:
     t('key')                       -> string in the active language
     t('rows_cols', {n: 5, c: 3})   -> "{n}" placeholders substituted
     data-i18n="key"                -> textContent      (applyI18n)
     data-i18n-html="key"           -> innerHTML (trusted dictionary text)
     data-i18n-ph="key"             -> placeholder
     data-i18n-title="key"          -> title attribute
   Keys fall back to Bulgarian, then to the key itself — never blank. */
(function () {
  const dicts = { bg: {}, en: {} };
  function fromCookie() {
    const m = document.cookie.match(/(?:^|;\s*)lang=(bg|en)\b/);
    return m ? m[1] : null;
  }
  const LANG = fromCookie() || ((navigator.language || '').toLowerCase().startsWith('bg') ? 'bg' : 'en');
  if (!fromCookie()) document.cookie = `lang=${LANG};path=/;max-age=31536000;SameSite=Lax`;

  window.I18N = {
    lang: LANG,
    add(lang, dict) { Object.assign(dicts[lang] || (dicts[lang] = {}), dict); },
    set(lang) {
      if (lang !== 'bg' && lang !== 'en') return;
      document.cookie = `lang=${lang};path=/;max-age=31536000;SameSite=Lax`;
      location.reload();
    },
  };
  window.t = function (key, vars) {
    let s = dicts[LANG][key];
    if (s === undefined) s = dicts.bg[key];
    if (s === undefined) s = key;
    if (vars) s = s.replace(/\{(\w+)\}/g, (_, k) => (vars[k] === undefined || vars[k] === null ? '' : vars[k]));
    return s;
  };
  /* plural helper: t_n('table', n) -> looks up key, key_pl (bg/en both use one/many) */
  window.t_n = function (key, n, vars) {
    return t(n === 1 ? key : key + '_pl', Object.assign({ n }, vars || {}));
  };
  window.applyI18n = function (root) {
    root = root || document;
    document.documentElement.lang = LANG;
    root.querySelectorAll('[data-i18n]').forEach(e => { e.textContent = t(e.dataset.i18n); });
    root.querySelectorAll('[data-i18n-html]').forEach(e => { e.innerHTML = t(e.dataset.i18nHtml); });
    root.querySelectorAll('[data-i18n-ph]').forEach(e => { e.placeholder = t(e.dataset.i18nPh); });
    root.querySelectorAll('[data-i18n-title]').forEach(e => { e.title = t(e.dataset.i18nTitle); });
    root.querySelectorAll('[data-i18n-alt]').forEach(e => { e.alt = t(e.dataset.i18nAlt); });
    root.querySelectorAll('[data-i18n-content]').forEach(e => { e.content = t(e.dataset.i18nContent); });
    root.querySelectorAll('.langswitch').forEach(sw => {
      sw.innerHTML = ['bg', 'en'].map(l =>
        `<button type="button" data-lang="${l}" class="${l === LANG ? 'on' : ''}" aria-pressed="${l === LANG}">${l.toUpperCase()}</button>`).join('');
      sw.querySelectorAll('button').forEach(b => b.addEventListener('click', () => I18N.set(b.dataset.lang)));
    });
  };
  /* shared look for the BG|EN switch (pages may override) */
  const css = document.createElement('style');
  css.textContent = `
    .langswitch { display: inline-flex; border: 1px solid rgba(255,255,255,0.14); border-radius: 9px; overflow: hidden; font-size: 11px; font-weight: 800; letter-spacing: .04em; }
    .langswitch button { font-family: inherit; font-size: inherit; font-weight: inherit; padding: 5px 9px; border: none; cursor: pointer; background: none; color: rgba(255,255,255,0.55); }
    .langswitch button.on { background: linear-gradient(135deg, #0ADDF5, #069bb0); color: #04142c; }
    .langswitch button:not(.on):hover { color: #fff; }`;
  document.head.appendChild(css);
  document.addEventListener('DOMContentLoaded', () => applyI18n());
})();

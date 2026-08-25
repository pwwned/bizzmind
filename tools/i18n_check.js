// Проверка на преводите: всеки ключ, ползван в HTML/JS, трябва да е в BG и EN речника.
// Употреба: node tools/i18n_check.js   (exit 1 при липси)
const fs = require('fs'), path = require('path');
const root = path.join(__dirname, '..');
const dict = { bg: {}, en: {} };
global.I18N = { add: (l, d) => Object.assign(dict[l], d) };
for (const f of ['app.js', 'site.js']) eval(fs.readFileSync(path.join(root, 'static/i18n', f), 'utf8'));
let bad = 0;
for (const f of ['app.html', 'landing.html', 'login.html']) {
  const h = fs.readFileSync(path.join(root, 'static', f), 'utf8'); const used = new Set();
  for (const m of h.matchAll(/\bt(?:_n)?\(\s*'([^']+)'/g)) used.add(m[1]);
  for (const m of h.matchAll(/data-i18n(?:-\w+)?="([^"]+)"/g)) used.add(m[1]);
  for (const m of h.matchAll(/data-q="([^"]+)"/g)) used.add(m[1]);
  for (const k of used) for (const l of ['bg', 'en'])
    if (!(k in dict[l]) && !(h.includes(`t_n('${k}'`) && (k + '_pl') in dict[l])) { console.log(`${f}: липсва ${l}.${k}`); bad++; }
  const cyr = h.split('\n').map((l, i) => [i + 1, l]).filter(([, l]) => /[А-Яа-я]/.test(l) && !/data-i18n|^\s*(\/\/|\/\*|\*)/.test(l));
  for (const [n, l] of cyr) console.log(`${f}:${n}: твърд текст? ${l.trim().slice(0, 90)}`);
  console.log(`${f}: ${used.size} ключа`);
}
console.log(bad ? `❌ ${bad} липсващи` : '✅ речниците са пълни');
process.exit(bad ? 1 : 0);

'use strict';
// Pakiet 11 (A-INN-06): skróty klawiszowe poza edycją arkusza. Cmd+F na listach przenosi do wyszukiwarki listy (w arkuszu
// obsługuje go arkusz.js), Cmd+Enter otwiera kartę zaznaczonego albo wskazanego wiersza listy, Cmd+K otwiera pomoc
// z wyszukiwarką, „?” pokazuje listę skrótów. Na Windows zamiast Cmd działa Ctrl. Wyszukiwarka pomocy dochodzi też do panelu
// otwieranego przyciskiem Pomoc (otworzPomoc z app.js dostaje pole wyszukiwania).
(() => {

const SKROTY = [
  ['Wszędzie', [['?', 'ta lista skrótów'], ['Cmd+K', 'pomoc z wyszukiwarką'], ['Cmd+F', 'wyszukiwarka listy albo arkusza'],
    ['Esc', 'zamyka kartę, menu i pomoc']]],
  ['Listy', [['Cmd+Enter', 'karta zaznaczonego wiersza (albo wiersza pod kursorem)'], ['Shift+klik', 'zaznacza zakres wierszy'],
    ['Enter w wyszukiwarce', 'szuka od razu']]],
  ['Arkusz budżetu', [['strzałki, Tab', 'przesuwają zaznaczenie komórki'], ['Shift+strzałki', 'rozszerzają zaznaczenie'],
    ['cyfry albo Enter', 'edycja kwoty (Enter zapisuje, Esc anuluje)'], ['Cmd+Enter, Cmd+dwuklik', 'karta płatności komórki'],
    ['Cmd+C, Cmd+V', 'kopiuj i wklej, także blok z Excela'], ['Cmd+Z', 'cofnij ostatnią zmianę budżetu'], ['Cmd+A', 'zaznacz cały arkusz'],
    ['Delete', 'wyczyść komórkę'], ['Enter na przełączniku', 'przełącza Księgowane, W cash flow, Split']]],
];

Object.assign(POMOC, {
  skroty: { tytul: 'Skróty klawiszowe', krotko: 'Klawisz „?” pokazuje wszystkie skróty. Cmd+K otwiera pomoc z wyszukiwarką.',
    co: SKROTY.map(([g, l]) => `${g}: ${l.map(([k, o]) => `${k} (${o})`).join(', ')}`).join('. ') + '.',
    skad: 'Skróty jak w Budget Studio; na Windows zamiast Cmd działa Ctrl.',
    jak: 'Skróty nie działają, gdy piszesz w polu tekstowym (poza Esc).',
    zrob: 'Naciśnij „?” na dowolnym ekranie, żeby zobaczyć listę.' },
});

const wPolu = () => { const a = document.activeElement; return !!a && a !== document.body && a.matches('input, select, textarea, [contenteditable]'); };
const widoczne = el => !!el && el.offsetParent !== null;

function kartaSkrotow() {
  const k = $('#karta');
  k.innerHTML = `<button class="zamknij" aria-label="Zamknij">×</button><h2>Skróty klawiszowe</h2>
    ${SKROTY.map(([g, l]) => `<h3>${esc(g)}</h3><dl class="skroty">${l.map(([kl, o]) => `<dt>${kl.split(', ').map(x => `<kbd>${esc(x)}</kbd>`).join(' ')}</dt><dd>${esc(o)}</dd>`).join('')}</dl>`).join('')}
    <p class="szary">Na Windows zamiast Cmd naciśnij Ctrl.</p>`;
  k.hidden = false;
  $('.zamknij', k).onclick = () => { k.hidden = true; };
}

// Pomoc z wyszukiwarką: pole nad treścią filtruje sekcje po tekście (tytuł, opis, wszystkie akapity).
const otworzPomocBez = otworzPomoc;
window.otworzPomoc = klucz => {
  otworzPomocBez(klucz);
  const panel = $('#pomoc');
  if (panel.querySelector('.szukaj-pomocy')) return;
  const inp = Object.assign(document.createElement('input'), { type: 'search', className: 'szukaj-pomocy', placeholder: 'Szukaj w pomocy (Cmd+K)' });
  inp.setAttribute('aria-label', 'Szukaj w pomocy');
  panel.querySelector('h2').after(inp);
  inp.oninput = () => {
    const f = inp.value.trim().toLowerCase();
    panel.querySelectorAll('section').forEach(s => { s.hidden = !!f && !s.textContent.toLowerCase().includes(f); });
  };
  if (!klucz) inp.focus();
};

document.addEventListener('keydown', e => {
  if (e.defaultPrevented) return;   // arkusz.js obsłużył klawisz (edycja, Cmd+F w arkuszu)
  const mod = e.metaKey || e.ctrlKey, kl = e.key;
  const arkusz = typeof arkWidoczny === 'function' && arkWidoczny();
  if (mod && kl.toLowerCase() === 'k') { e.preventDefault(); otworzPomoc(null); return; }
  if (mod && kl.toLowerCase() === 'f' && !arkusz) {
    const pole = [...document.querySelectorAll('#widok input[type="search"], #widok input.szukaj')].find(widoczne);
    if (pole) { e.preventDefault(); pole.focus(); pole.select(); }
    return;
  }
  if (mod && kl === 'Enter' && !arkusz && !wPolu()) {
    const tr = [...document.querySelectorAll('#widok tbody tr.zaznaczony[data-i]')].find(widoczne)
      || [...document.querySelectorAll('#widok tbody tr[data-i]')].find(r => r.matches(':hover'));
    if (tr) { e.preventDefault(); tr.click(); }
    return;
  }
  if (kl === '?' && !mod && !wPolu()) { e.preventDefault(); kartaSkrotow(); }
});

})();

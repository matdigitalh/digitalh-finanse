'use strict';
// Pakiet 11 (A-BUD-07, A-BUD-14, B-INNE-02): rentowność budżetu jak w Budget Studio. Tabela przestawna płatności budżetu
// z Księgowane = tak: wiersze wg wybranych poziomów (folder, kategoria, arkusz, sekcja, przedmiot, kontrahent) z rozwijaniem,
// kolumny miesięcy, wartości: wynik, wpływy, obciążenia albo marża; pod spodem nasz wynik zarządczy (bank i dokumenty).
// Dane: GET /api/rentownosc/przestawna?rok=&poziomy=&os=&folder= (finanse/przestawna.py).
(() => {

(() => {
  const r = PODSTRONY.rentownosc;
  const i = r.findIndex(p => p.hash === '#/rentownosc');
  r.splice(i >= 0 ? i + 1 : r.length, 0, { nazwa: 'Rentowność budżetu', hash: '#/rentownosc/przestawna', ik: 'siatka' });
})();

Object.assign(POMOC, {
  przestawna: { tytul: 'Rentowność budżetu', krotko: 'Wynik z budżetu jak w Budget Studio: folder, klient, arkusz, kontrahent, miesiąc po miesiącu.',
    co: 'Tabela z planów i dokumentów w budżecie. Wybierasz, jak grupować wiersze (np. folder, potem kategoria, potem arkusz) i co pokazać w miesiącach: wynik, wpływy, obciążenia albo marżę. Na każdym poziomie widać wynik, a wynik folderu to suma jego arkuszy.',
    skad: 'Płatności budżetu z włączonym „Księgowane” (plany i dokumenty, kwoty netto). Bez arkusza Opłaty urzędowe i bez pozycji z wyłączonym „Księgowane” (np. kredyt, wypłata zysku).',
    jak: 'Wynik = wpływy minus obciążenia. Marża = wynik podzielony przez wpływy. Miesiąc wg budżetu to kolumna komórki w arkuszu; wg księgowania to miesiąc, do którego dokument trafia u biura. Pod tabelą nasz wynik zarządczy z banku i faktur, żeby porównać plan z wykonaniem.',
    zrob: 'Kliknij strzałkę przy wierszu, żeby go rozwinąć. Duża różnica między budżetem a wynikiem zarządczym to znak, że plany się rozjechały albo brakuje wydatków w budżecie.' },
});

const WARTOSCI = { wynik: 'Wynik', wplywy: 'Wpływy', obciazenia: 'Obciążenia', marza: 'Marża' };
const ROZWINIETE = {};   // klucz konfiguracji (poziomy, folder) → zbiór rozwiniętych ścieżek; żyje do przeładowania strony

function komorka(x, wart, razem = false) {
  if (!x) return `<td class="liczba-kol${razem ? ' razem' : ''}"></td>`;
  const v = wart === 'marza' ? x.marza : wart === 'obciazenia' ? -x.obciazenia : x[wart];
  if (v == null || (wart !== 'marza' && !v)) return `<td class="liczba-kol${razem ? ' razem' : ''}">${wart === 'marza' ? '' : '-'}</td>`;
  return `<td class="liczba-kol${razem ? ' razem' : ''}${v < 0 ? ' minus' : ''}">${wart === 'marza' ? procent(v) : tys(v)}</td>`;
}

const sumy = x => `<td class="liczba-kol sep">${tys(x.wplywy)}</td><td class="liczba-kol minus">${tys(-x.obciazenia)}</td>
  <td class="liczba-kol razem${x.wynik < 0 ? ' minus' : ''}">${tys(x.wynik) || '0'}</td><td class="liczba-kol">${procent(x.marza)}</td>`;

function cialo(d, wart, rozw) {
  const wiersze = [];
  const rysuj = (w, sciezka) => {
    const s = `${sciezka}/${w.klucz}`;
    const ma = w.dzieci.length > 0;
    const otwarty = rozw.has(s);
    const arkusz = d.poziomy[w.poziom] === 'arkusz';
    wiersze.push(`<tr class="poz-${w.poziom}${ma ? ' rozwijany' : ''}" data-s="${esc(s)}"><td class="nazwa-przest">
      ${ma ? `<button type="button" class="rozwin" aria-expanded="${otwarty}" aria-label="${otwarty ? 'Zwiń' : 'Rozwiń'}">${otwarty ? '▾' : '▸'}</button>` : '<span class="rozwin-pusty"></span>'}
      ${esc(w.nazwa)}${arkusz ? ` <a class="szary" href="#/budzet/arkusz?id=${encodeURIComponent(w.klucz)}" title="Otwórz arkusz">${ik('strzalkaP')}</a>` : ''}</td>
      ${d.miesiace.map(m => komorka(w.miesiace[m], wart)).join('')}${sumy(w)}</tr>`);
    if (ma && otwarty) w.dzieci.forEach(x => rysuj(x, s));
  };
  d.wiersze.forEach(w => rysuj(w, ''));
  return wiersze.join('') || `<tr><td colspan="${d.miesiace.length + 5}" class="pusto">Brak płatności z Księgowane w ${d.rok}.</td></tr>`;
}

function podepnijCialo(d, wart, rozw) {
  const t = $('#przestawna');
  if (!t) return;
  t.querySelectorAll('tbody tr.rozwijany').forEach(tr => tr.addEventListener('click', e => {
    if (e.target.closest('a')) return;
    const s = tr.dataset.s;
    rozw.has(s) ? rozw.delete(s) : rozw.add(s);
    t.querySelector('tbody').innerHTML = cialo(d, wart, rozw);
    podepnijCialo(d, wart, rozw);
  }));
}

WIDOKI['rentownosc/przestawna'] = async p => {
  const d = await api('rentownosc/przestawna', p);
  const wart = WARTOSCI[p.wartosc] ? p.wartosc : 'wynik';
  const konf = `${d.poziomy.join(',')}|${d.folder || ''}`;
  const rozw = ROZWINIETE[konf] ||= new Set();
  const wszystkie = [];
  const zbierz = (w, sciezka) => { const s = `${sciezka}/${w.klucz}`; if (w.dzieci.length) { wszystkie.push(s); w.dzieci.forEach(x => zbierz(x, s)); } };
  d.wiersze.forEach(w => zbierz(w, ''));
  const z = d.zarzadczy;
  const wierszZ = z ? `<tr class="zarzadczy"><td>Wynik zarządczy (bank i dokumenty)</td>${d.miesiace.map(m => m in z.wynik
      ? `<td class="liczba-kol${z.wynik[m] < 0 ? ' minus' : ''}${z.niepelne.includes(m) ? ' niepelny' : ''}">${tys(z.wynik[m]) || '0'}</td>` : '<td></td>').join('')}
      <td class="liczba-kol sep szary" title="obrót netto z faktur">${tys(z.razem_obrot)}</td><td></td><td class="liczba-kol razem${z.razem_wynik < 0 ? ' minus' : ''}">${tys(z.razem_wynik)}</td>
      <td class="liczba-kol">${z.razem_obrot > 0 ? procent(Math.round(1000 * z.razem_wynik / z.razem_obrot) / 10) : ''}</td></tr>
    <tr class="roznica"><td>Różnica wyniku: budżet minus zarządczy</td>${d.miesiace.map(m => {
      if (!(m in z.wynik)) return '<td></td>';
      const r = (d.razem.miesiace[m]?.wynik || 0) - z.wynik[m];
      return `<td class="liczba-kol${r < 0 ? ' minus' : ''}">${tys(r) || '0'}</td>`;
    }).join('')}<td></td><td></td><td class="liczba-kol razem">${tys(Object.keys(z.wynik).reduce((a, m) => a + (d.razem.miesiace[m]?.wynik || 0) - z.wynik[m], 0)) || '0'}</td><td></td></tr>` : '';
  setTimeout(() => {
    if (!$('#przestawna')) return;
    podepnijCialo(d, wart, rozw);
    const odswiez = () => { $('#przestawna tbody').innerHTML = cialo(d, wart, rozw); podepnijCialo(d, wart, rozw); };
    $('#przest-rozwin').onclick = () => { wszystkie.forEach(s => rozw.add(s)); odswiez(); };
    $('#przest-zwin').onclick = () => { rozw.clear(); odswiez(); };
    document.querySelectorAll('[data-poziom]').forEach(sel => sel.onchange = () => {
      const poz = [...document.querySelectorAll('[data-poziom]')].map(x => x.value).filter(Boolean);
      ustawParametry({ poziomy: poz.join(',') });
    });
    const f = $('#przest-folder');
    if (f) f.onclick = () => ustawParametry({ folder: '' });
  });
  const opcjePoz = (i, wybrany) => `<label>${i === 0 ? 'Grupuj wiersze wg' : 'potem wg'}<select data-poziom="${i}">${i ? '<option value="">(nic)</option>' : ''}
    ${Object.entries(d.nazwy_poziomow).map(([k, n]) => `<option value="${k}"${k === wybrany ? ' selected' : ''}>${esc(n)}</option>`).join('')}</select></label>`;
  return `<div class="naglowek-strony"><div><h1>Rentowność budżetu ${pytajnik('przestawna')}</h1>
      <div class="okruszki">Rentowność / ${d.rok} · płatności budżetu z „Księgowane”, kwoty netto w złotych</div></div></div>
    <div class="filtry">${filtr('rok', 'Rok', d.lata.map(r => [r, r]), d.rok)}
      ${[0, 1, 2, 3].map(i => opcjePoz(i, d.poziomy[i])).join('')}
      ${filtr('wartosc', 'W miesiącach', Object.entries(WARTOSCI), wart)}
      ${filtr('os', 'Miesiąc wg', [['budzet', 'budżetu (kolumna arkusza)'], ['ksiegowanie', 'księgowania']], d.os)}
      ${d.folder ? `<button type="button" class="pigulka przywroc" id="przest-folder" title="Pokaż wszystkie foldery">Folder: ${esc(d.folder)} ×</button>` : ''}
      <span class="prawo"><button type="button" class="przycisk" id="przest-rozwin">Rozwiń wszystko</button> <button type="button" class="przycisk" id="przest-zwin">Zwiń</button></span></div>
    <div class="tabela-ramka niska"><table class="miesiace przestawna" id="przestawna"><thead><tr><th>${d.poziomy.map(x => esc(d.nazwy_poziomow[x])).join(' / ')}</th>
      ${d.miesiace.map(m => `<th class="liczba-kol">${mies(m)}</th>`).join('')}
      <th class="liczba-kol sep">Wpływy</th><th class="liczba-kol">Obciążenia</th><th class="liczba-kol">Wynik</th><th class="liczba-kol">Marża</th></tr></thead>
      <tbody>${cialo(d, wart, rozw)}</tbody>
      <tfoot><tr class="razem-budzet"><td>Razem budżet</td>${d.miesiace.map(m => komorka(d.razem.miesiace[m], wart, true)).join('')}${sumy(d.razem)}</tr>${wierszZ}</tfoot></table></div>
    <p class="notka">W miesiącach: ${esc(WARTOSCI[wart].toLowerCase())}${wart === 'marza' ? ' (wynik do wpływów)' : ', w złotych bez groszy'}. Kolumny po prawej to cały rok. Wynik zarządczy liczony z banku i faktur (Rentowność, Wynik zarządczy); szare miesiące są jeszcze niepełne.</p>`;
};

})();

'use strict';
// Pakiet 6: kopia z Budget Studio (podgląd raportu kontroli sum przed zapisem, przyjęcie przy 0 różnic) i ekran
// „Zgodność z BS” (każdy nowy eksport BS kontra plany apki w okresie równoległym). Korzysta z funkcji z app.js i budzet.js.

(() => {
  const lista = PODSTRONY.budzet;
  const i = lista.findIndex(p => p.hash === '#/budzet/rozjazdy');
  lista.splice(i >= 0 ? i + 1 : lista.length, 0, { nazwa: 'Zgodność z BS i kopia', hash: '#/budzet/zgodnosc', ik: 'weryfikuj' });
})();

Object.assign(POMOC, {
  zgodnosc: { tytul: 'Kopia z BS i zgodność', krotko: 'Czy plany w apce zgadzają się z Budget Studio co do grosza.',
    co: 'Kontrola sum: arkusz, miesiąc, rodzaj, plan albo rzeczywista; liczba płatności, netto, VAT, brutto w BS i w apce. Do tego cash flow (brutto wg miesiąca dnia realnej płatności) i wynik (netto wg miesiąca księgowania) w każdym miesiącu.',
    skad: 'Strona BS: najnowszy eksport z folderu Dane. Strona apki: kopia z BS z Twoimi późniejszymi zmianami.',
    jak: 'Różnice szukamy też płatność po płatności (po ID z BS), stąd przyczyna przy każdej różnicy. Kopię da się przyjąć tylko przy 0 różnic.',
    zrob: 'Do 31.10: porządki w BS, podgląd kopii, przyjęcie. Od 1.11 wpisujesz plany w obu miejscach, a ten ekran pokazuje, gdzie się rozjechały.' },
});

const NAZWY_POL = { aktualna: 'aktualność', ksiegowanie: 'miesiąc księgowania', stawka: 'stawka VAT', komentarz: 'komentarz',
  wystawienie: 'dzień wystawienia', termin: 'dzień płatności', realny: 'dzień realnej płatności', metoda: 'metoda płatności',
  ksiegowane: 'Księgowane', w_cashflow: 'W cash flow', kontrahent: 'kontrahent' };
const GRUPY_ROWNOLEGLE = ['Plan w BS inny niż w apce', 'Wiersz jest tylko w BS', 'Wiersz jest tylko w apce'];

function naglowekKontroli(d) {
  const ok = d.roznic === 0;
  const czesci = [[d.roznic_komorek, 'komórek (arkusz, miesiąc, rodzaj, typ)'], [d.roznic_miesiecy, 'miesięcy (cash flow albo wynik)'],
    [d.roznic_platnosci, 'płatności']].filter(([n]) => n).map(([n, t]) => `${n} ${t}`);
  if (d.zla_liczba) czesci.push(`liczba płatności w pliku (${d.liczba_csv}) inna niż w imporcie (${d.liczba_bs})`);
  return `<div class="kafle"><div class="kafel${ok ? ' glowny' : ''}"><div class="tytul">Kontrola sum</div>
      <div class="wartosc ${ok ? 'plus' : 'minus'}">${ok ? '0 różnic' : `${d.roznic} ${d.roznic === 1 ? 'różnica' : 'różnic'}`}</div>
      <div class="dop">${ok ? 'co do grosza we wszystkich arkuszach i miesiącach' : esc(czesci.join(', '))}</div></div>
    <div class="kafel"><div class="tytul">Płatności</div><div class="wartosc">${d.liczba_apka}</div>
      <div class="dop">w apce; w BS ${d.liczba_bs}${d.liczba_csv != null ? `, w pliku ${d.liczba_csv}` : ''}${d.bez_danin ? '; bez VAT i podatku dochodowego (liczy je arkusz systemowy Opłaty urzędowe)' : ''}</div></div>
    <div class="kafel"><div class="tytul">Saldo razem (netto)</div><div class="wartosc">${zl(d.razem.apka.netto, false)}</div>
      <div class="dop">w BS ${zl(d.razem.bs.netto, false)}; VAT ${zl(d.razem.apka.vat, false)}, brutto ${zl(d.razem.apka.brutto, false)}</div></div></div>`;
}

function weryfikacja(w, p) {
  if (!w) return '';
  const wor = w.worek || {}, um = w.umowa || {};
  const inne = Object.entries(w.worek_inne || {}).map(([k, n]) => `${n}: ${esc(k)}`).join('; ');
  const nadp = Object.entries(w.nadpisania || {}).map(([k, n]) => `${esc(NAZWY_POL[k] || k)} ${n}`).join(', ');
  const jawne = Object.entries(w.jawne || {}).map(([k, n]) => `${n}: ${esc(k)}`).join('; ');
  return `<div class="karta-wyk"><h3>Co powstanie w apce</h3>
    <p class="notka">${p.arkuszy} arkuszy, ${p.wierszy} wierszy (${p.scalonych_umow} umów o pracę scalonych z trzech wierszy BS w jeden), ${p.komorek} komórek z kwotą,
      ${p.planow_z_komorek} planów liczonych z komórek, ${p.platnosci_jawnych} płatności przeniesionych wprost (rzeczywiste i plany, których reguła nie odtwarza).</p>
    <h3>Reguły apki sprawdzone na eksporcie BS</h3>
    <p class="notka">Worek, tydzień od ${w.tydzien === 1 ? 'wtorku' : w.tydzien === 0 ? 'poniedziałku' : `dnia ${w.tydzien}`}: ${wor.zgodne || 0} komórek zgodnych z regułą,
      ${wor.inne || 0} z podziałem przeniesionym wprost z BS${inne ? ` (${inne})` : ''}. Kwoty tygodni w kopii są zawsze z eksportu.</p>
    <p class="notka">Umowa o pracę z proporcji wiersza: ${um.zgodne || 0} komórek co do grosza${um.inne ? `, ${um.inne} z podziałem z BS (najwyżej ${w.umowa_maks_gr} gr różnicy)` : ''}.</p>
    <p class="notka">Plany różne od reguły wiersza, przeniesione jako ręczna zmiana planu: ${nadp || 'brak'}.</p>
    ${jawne ? `<p class="notka">Plany przeniesione wprost, bez komórki: ${jawne}.</p>` : ''}
    ${w.arkusze_rozszerzone ? `<p class="notka">Arkusze z zakresem poszerzonym do miesięcy płatności: ${w.arkusze_rozszerzone}.</p>` : ''}</div>`;
}

function tabeleKontroli(d) {
  const nazwa = aid => { const a = d.arkusze.find(x => x.arkusz === aid); return a ? `${a.folder} / ${a.nazwa}` : aid; };
  const przyczyny = xs => xs && xs.length ? `<ul class="szary">${xs.map(t => `<li>${esc(t)}</li>`).join('')}</ul>` : '';
  const komorki = d.komorki.length ? `<h2 class="sekcja">Różnice w komórkach <span class="szary">${d.komorki.length}</span></h2>
    <div class="tabela-ramka niska"><table><thead><tr><th>Arkusz</th><th>Miesiąc</th><th>Rodzaj</th><th>Typ</th><th class="liczba-kol">Liczba BS / apka</th>
      <th class="liczba-kol">Netto BS</th><th class="liczba-kol">Netto apka</th><th class="liczba-kol">VAT BS / apka</th><th class="liczba-kol">Brutto BS / apka</th><th>Przyczyna</th></tr></thead><tbody>
    ${d.komorki.map(x => `<tr><td>${esc(nazwa(x.arkusz))}</td><td>${x.miesiac ? mies(x.miesiac) : ''}</td><td>${x.rodzaj === 1 ? 'wpływ' : 'obciążenie'}</td><td>${esc(x.typ)}</td>
      <td class="liczba-kol">${x.bs.liczba} / ${x.apka.liczba}</td><td class="liczba-kol">${zl(x.bs.netto, false)}</td><td class="liczba-kol">${zl(x.apka.netto, false)}</td>
      <td class="liczba-kol">${zl(x.bs.vat, false)} / ${zl(x.apka.vat, false)}</td><td class="liczba-kol">${zl(x.bs.brutto, false)} / ${zl(x.apka.brutto, false)}</td>
      <td>${przyczyny(x.przyczyny)}</td></tr>`).join('')}</tbody></table></div>` : '';
  const miesiace = `<h2 class="sekcja">Cash flow i wynik w miesiącach</h2>
    <p class="notka">Cash flow: brutto płatności ${d.z_aktualnoscia ? 'aktualnych ' : ''}z „W cash flow” wg miesiąca dnia realnej płatności. Wynik: netto płatności ${d.z_aktualnoscia ? 'aktualnych ' : ''}z „Księgowane” wg miesiąca księgowania.
      ${d.z_aktualnoscia ? '' : 'Po kopii liczymy wszystkie płatności, bo BS sam przestawia plan na nieaktualny, gdy minie jego data.'}</p>
    <div class="tabela-ramka niska"><table><thead><tr><th>Miesiąc</th><th class="liczba-kol">Cash flow BS</th><th class="liczba-kol">Cash flow apka</th>
      <th class="liczba-kol">Wynik BS</th><th class="liczba-kol">Wynik apka</th><th>Zgodność</th></tr></thead><tbody>
    ${d.miesiace.map(x => `<tr><td>${mies(x.miesiac)}</td><td class="liczba-kol">${zl(x.cf_bs, false)}</td><td class="liczba-kol">${zl(x.cf_apka, false)}</td>
      <td class="liczba-kol">${zl(x.wynik_bs, false)}</td><td class="liczba-kol">${zl(x.wynik_apka, false)}</td>
      <td>${x.zgodny ? '<span class="chip plus">zgodny</span>' : `<span class="chip minus">różnica</span>${przyczyny(x.przyczyny)}`}</td></tr>`).join('')}</tbody></table></div>`;
  const arkusze = `<h2 class="sekcja">Arkusze <span class="szary">${d.arkusze.filter(a => !a.zgodny).length} z różnicą z ${d.arkusze.length}</span></h2>
    <div class="tabela-ramka niska"><table><thead><tr><th>Folder</th><th>Arkusz</th><th class="liczba-kol">Płatności BS / apka</th><th class="liczba-kol">Saldo netto BS</th>
      <th class="liczba-kol">Saldo netto apka</th><th class="liczba-kol">VAT BS / apka</th><th>Zgodność</th></tr></thead><tbody>
    ${d.arkusze.map(a => `<tr><td>${esc(a.folder)}</td><td>${a.arkusz ? `<a href="#/budzet/arkusz?id=${encodeURIComponent(a.arkusz)}">${esc(a.nazwa || a.arkusz)}</a>` : ''}</td>
      <td class="liczba-kol">${a.bs.liczba} / ${a.apka.liczba}</td><td class="liczba-kol">${zl(a.bs.netto, false)}</td><td class="liczba-kol">${zl(a.apka.netto, false)}</td>
      <td class="liczba-kol">${zl(a.bs.vat, false)} / ${zl(a.apka.vat, false)}</td><td>${a.zgodny ? '<span class="chip plus">zgodny</span>' : '<span class="chip minus">różnica</span>'}</td></tr>`).join('')}
    </tbody></table></div>`;
  const platnosci = d.platnosci.length ? `<h2 class="sekcja">Płatność po płatności <span class="szary">${d.platnosci_razem}${d.platnosci_razem > d.platnosci.length ? `, pokazane ${d.platnosci.length}` : ''}</span></h2>
    <div class="tabela-ramka niska"><table><thead><tr><th>ID w BS</th><th>ID w apce</th><th>Arkusz</th><th>Miesiąc</th><th>Typ</th><th class="liczba-kol">Brutto BS</th><th class="liczba-kol">Brutto apka</th><th>Przyczyna</th></tr></thead><tbody>
    ${d.platnosci.map(x => `<tr><td class="szary">${esc(x.bs_pid || '')}</td><td class="szary">${esc(x.apka_id || '')}</td><td>${esc(nazwa(x.arkusz))}</td><td>${x.miesiac ? mies(x.miesiac) : ''}</td>
      <td>${esc(x.typ)}</td><td class="liczba-kol">${x.bs ? zl(x.bs.brutto, false) : ''}</td><td class="liczba-kol">${x.apka ? zl(x.apka.brutto, false) : ''}</td><td>${esc(x.przyczyny.join(', '))}</td></tr>`).join('')}
    </tbody></table></div>` : '';
  return komorki + platnosci + miesiace + arkusze;
}

async function przyjmijKopie(sha) {
  const r = await fetch('/api/kopia-bs', { method: 'POST', headers: { 'X-Finanse': '1', 'Content-Type': 'application/json' },
    body: JSON.stringify({ eksport_sha256: sha }) });
  const w = await r.json().catch(() => ({}));
  if (!r.ok) return komunikat(w.blad || 'Nie udało się przyjąć kopii.', true);
  await sprawdzStan();
  location.hash = '#/budzet/zgodnosc';
  komunikat(`Kopia przyjęta (${w.plik}). Budżet pochodzi teraz z kopii; kolejne eksporty BS są tylko porównywane.`);
}

Object.assign(WIDOKI, {
  async 'budzet/zgodnosc'(p) {
    if (p.podglad === '1') {
      const d = await api('budzet/kopia');
      setTimeout(() => {
        const b = $('#przyjmij-kopie');
        if (b) b.onclick = () => { b.disabled = true; przyjmijKopie(d.eksport_sha256); };
      });
      return `<h1>Kopia z Budget Studio: podgląd ${pytajnik('zgodnosc')}</h1><div class="okruszki">Budżet / Zgodność z BS / podgląd przed zapisem</div>
        <p class="notka">Eksport ${esc(d.eksport)}. Nic nie zostało jeszcze zapisane. Po przyjęciu budżet w apce pochodzi z kopii, a kolejne eksporty BS są z nią tylko porównywane.
          ${d.zdarzen_przed ? `<b>Zmiany planów zapisane w apce przed kopią (${d.zdarzen_przed}) przestaną obowiązywać.</b>` : ''}</p>
        ${naglowekKontroli(d)}
        <div class="akcje"><button class="glowny" id="przyjmij-kopie" ${d.roznic === 0 ? '' : 'disabled'}>Przyjmij kopię</button>
          <a href="/api/eksport/kontrola-bs?podglad=1">Pobierz raport (Excel)</a> · <a href="#/budzet/zgodnosc">Wróć</a></div>
        ${d.roznic === 0 ? '' : '<p class="notka">Przyjęcie jest możliwe dopiero przy 0 różnic. Popraw w BS albo zgłoś przyczynę poniżej.</p>'}
        ${weryfikacja(d.weryfikacja, d.podsumowanie)}${tabeleKontroli(d)}`;
    }
    const [d, roz] = await Promise.all([api('budzet/zgodnosc'), api('budzet/rozjazdy')]);
    const k = d.kopia;
    setTimeout(() => {
      const c = $('#cofnij-kopie');
      if (c) c.onclick = () => { if (confirm('Cofnąć kopię? Budżet wróci do importu z eksportu BS, a zmiany zapisane po kopii zostaną w historii.')) zmiana('cofnij', { wpis: k.wpis }); };
      document.querySelectorAll('[data-idz]').forEach(b => { b.onclick = () => { location.hash = b.dataset.idz; }; });
      const i = $('#przelacz-import');
      if (i) i.onclick = () => zmiana('ustawienie', { klucz: 'import_bs', wartosc: d.import_bs ? 'nie' : 'tak' });
    });
    const rownolegle = roz.filter(x => GRUPY_ROWNOLEGLE.includes(x.rodzaj));
    const grupy = GRUPY_ROWNOLEGLE.map(g => [g, rownolegle.filter(x => x.rodzaj === g)]).filter(([, xs]) => xs.length);
    const rozHtml = grupy.map(([g, xs]) => `<h2 class="sekcja">${esc(g)} <span class="szary">${xs.length}</span></h2>
      <div class="tabela-ramka niska"><table><thead><tr><th>Arkusz</th><th>Kontrahent</th><th>Miesiąc</th><th class="liczba-kol">Różnica</th><th>Opis</th></tr></thead><tbody>
      ${xs.slice(0, 200).map(x => `<tr><td>${x.arkusz_id ? `<a href="#/budzet/arkusz?id=${encodeURIComponent(x.arkusz_id)}">${esc(x.arkusz || '')}</a>` : esc(x.arkusz || '')}</td>
        <td>${esc(x.kontrahent || '')}</td><td>${x.miesiac ? mies(x.miesiac) : ''}</td><td class="liczba-kol">${zl(x.kwota, false)}</td>
        <td class="szary">${esc(x.opis.replace(/(-?\d+) gr/g, (_, v) => zl(+v)))}</td></tr>`).join('')}</tbody></table></div>`).join('');
    const stan = k ? `<div class="karta-wyk"><h3>Kopia przyjęta</h3>
        <p class="notka">${esc(k.plik)} z eksportu ${esc(k.eksport || '')}, ${esc(new Date(k.czas).toLocaleString('pl-PL'))} (${esc(k.mac)}). Budżet w apce pochodzi z tej kopii i Twoich zmian po niej.</p>
        ${k.blad ? `<div class="komunikat blad"><span>${esc(k.blad)}</span></div>` : ''}
        <div class="akcje"><a href="#/budzet/zgodnosc?podglad=1">Zrób kopię ponownie (podgląd)</a><button id="cofnij-kopie">Cofnij kopię</button></div></div>`
      : `<div class="karta-wyk"><h3>Kopii jeszcze nie ma</h3>
        <p class="notka">Teraz budżet to import z najnowszego eksportu BS (odtwarzany przy każdym eksporcie). Po porządkach w BS zrób kopię: najpierw podgląd z raportem kontroli sum, potem przyjęcie.</p>
        <div class="akcje"><button class="glowny" data-idz="#/budzet/zgodnosc?podglad=1">Kopia z Budget Studio: podgląd</button></div></div>`;
    const imp = `<div class="karta-wyk"><h3>Import eksportów BS</h3>
        <p class="notka">Teraz: <b>${d.import_bs ? 'włączony' : 'wyłączony'}</b>. ${d.import_bs ? 'Apka czyta najnowszy eksport BS: bez kopii jako budżet, z kopią tylko do porównania.'
          : 'Apka nie czyta eksportów BS; budżet pochodzi z kopii i Twoich zmian.'}${!k && d.import_bs ? ' Bez kopii wyłączenie importu zostawi pusty budżet.' : ''}</p>
        <div class="akcje"><button id="przelacz-import">${d.import_bs ? 'Wyłącz import z BS' : 'Włącz import z BS'}</button></div></div>`;
    const raport = d.eksport ? `<h2 class="sekcja">Najnowszy eksport BS (${esc(d.eksport)}) kontra plany apki</h2>${naglowekKontroli(d)}
        <div class="akcje"><a href="/api/eksport/kontrola-bs">Pobierz raport (Excel)</a></div>
        ${k ? `${rozHtml || '<p class="notka">Plany w BS i w apce zgadzają się komórka po komórce.</p>'}` : '<p class="notka">Bez kopii apka pokazuje import tego eksportu, więc raport porównuje plik sam ze sobą.</p>'}
        ${tabeleKontroli(d)}` : `<div class="pusto">${d.import_bs ? 'Brak eksportu BS w folderze Dane.' : 'Import z BS wyłączony: nie ma czego porównywać.'}</div>`;
    return `<h1>Zgodność z Budget Studio ${pytajnik('zgodnosc')}</h1><div class="okruszki">Budżet / Kopia z BS i kontrola sum</div>${stan}${imp}${raport}`;
  },
});

// Ustawienia budżetu: karta kopii z BS i przełącznik importu eksportów BS (pełny ekran: Zgodność z BS i kopia).
(() => {
  const ustawienia = WIDOKI['budzet/ustawienia'];
  if (!ustawienia) return;
  WIDOKI['budzet/ustawienia'] = async p => {
    const [html, d] = await Promise.all([ustawienia(p), api('budzet/drzewo')]);
    const k = d.kopia_bs;
    setTimeout(() => {
      document.querySelectorAll('[data-idz]').forEach(b => { b.onclick = () => { location.hash = b.dataset.idz; }; });
      const i = $('#przelacz-import-ust');
      if (i) i.onclick = () => zmiana('ustawienie', { klucz: 'import_bs', wartosc: d.import_bs ? 'nie' : 'tak' });
    });
    return html + `<div class="karta-wyk"><h3>Kopia z Budget Studio</h3>
    <p class="notka">${k ? `Kopia przyjęta: ${esc(k.plik)} (eksport ${esc(k.eksport)}). Budżet pochodzi z kopii i Twoich zmian po niej.`
      : 'Kopii jeszcze nie ma: budżet to import z najnowszego eksportu BS. Kopia przenosi cały budżet z BS (2026 z historią) z kontrolą sum co do grosza.'}
      Import eksportów BS: <b>${d.import_bs ? 'włączony' : 'wyłączony'}</b>${d.import_bs ? (k ? ' (tylko do porównania z planami apki)' : '') : ''}.</p>
    <div class="akcje"><button class="${k ? '' : 'glowny'}" data-idz="#/budzet/zgodnosc?podglad=1">${k ? 'Zrób kopię ponownie (podgląd)' : 'Kopia z Budget Studio: podgląd'}</button>
      <button data-idz="#/budzet/zgodnosc">Zgodność z BS</button>
      <button id="przelacz-import-ust">${d.import_bs ? 'Wyłącz import z BS' : 'Włącz import z BS'}</button></div></div>`;
  };
})();

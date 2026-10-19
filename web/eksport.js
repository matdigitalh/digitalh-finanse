'use strict';
// Pakiet 10: eksport i import. Ekran Eksport (zakres i format jak w Budget Studio), przyciski Excel i CSV nad każdą
// listą (te same filtry, z którymi ekran pytał serwer), Historia importów z licznikami jak w BS, podsumowanie jednego
// importu, plik przeciągnięty do okna (podgląd, potem import). Korzysta z funkcji z app.js (api, tabela, stopka, filtr,
// esc, ik, komunikat, sprawdzStan, ...); app.js woła stąd zapamietajZapytanie() i poWidoku().

// ---------- Eksport listy z bieżącymi filtrami ----------
// Ekran pyta serwer przez api(); zapamiętujemy ścieżkę i parametry, a przycisk eksportu wysyła dokładnie te same.
let ZAPYTANIA = [];
function zapamietajZapytanie(sciezka, parametry) {
  ZAPYTANIA.push({ sciezka, parametry: { ...(parametry || {}) }, hash: location.hash });
  if (ZAPYTANIA.length > 60) ZAPYTANIA = ZAPYTANIA.slice(-30);
}

// Ekran → zapytanie, które eksportujemy (pierwsze z listy, o które ekran zapytał przy tym adresie).
// Listy z pakietu 7 pytają GET /api/lista/<ekran> (widoki, filtry dat i cech, sortowanie); stare ścieżki zostają jako zapas.
const EKSPORT_EKRANU = {
  'platnosci/plan': ['lista/platnosci', 'budzet/lista'],
  'platnosci/bank': ['lista/bank', 'operacje'],
  'platnosci/faktury': ['lista/faktury', 'faktury'],
  'platnosci/naleznosci': ['lista/naleznosci', 'naleznosci'],
  'platnosci/zakupy': ['lista/zakupy', 'zakupy'],
  'platnosci/do-polaczenia': ['lista/wplaty', 'wplaty'],
  'platnosci/do-weryfikacji': ['lista/do-weryfikacji', 'do-weryfikacji'],
  'platnosci/wyniki-biura': ['wyniki-biura'],
  budzet: ['klienci'],
  'budzet/klient': ['klienci/karta', 'klient'],   // pakiet 11: karta klienta pyta klienci/karta
  'budzet/wydatki': ['lista/wydatki', 'wydatki'],
  'budzet/nieprzypisane': ['nieprzypisane-grupy'],
  'budzet/konta': ['konta-reklamowe'],
  'budzet/rozjazdy': ['budzet/rozjazdy'],
  'budzet/arkusz': ['lista/platnosci', 'budzet/lista', 'cashflow/okresy', 'budzet/arkusz'],
  cashflow: ['cashflow/okresy'],
  rentownosc: ['wynik'],
  'rentownosc/klienci': ['obroty-klientow'],
  'rentownosc/koszty': ['koszty-kategorii'],
  'rentownosc/vat': ['vat'],
  'rentownosc/arkusze': ['rentownosc/arkusze'],
};

function adresEksportu(sciezka, parametry, format) {
  const p = Object.entries(parametry || {}).filter(([k, v]) => v !== '' && v != null && k !== 'strona' && k !== 'ile');
  return `/api/eksport/${sciezka}?${new URLSearchParams([...p, ['format', format]])}`;
}

function przyciskiEksportu(sciezka, parametry, opis = 'Pobierz') {
  return `<span class="szary">${esc(opis)}:</span>
    <a class="przycisk maly" href="${esc(adresEksportu(sciezka, parametry, 'xlsx'))}" download>${ik('plik')}Excel</a>
    <a class="przycisk maly" href="${esc(adresEksportu(sciezka, parametry, 'csv'))}" download>${ik('plik')}CSV</a>`;
}

// Wołane z pokaz() po narysowaniu ekranu: pasek „Pobierz: Excel, CSV” w nagłówku ekranu, gdy ekran jest listą.
function poWidoku(klucz) {
  const odKonca = ZAPYTANIA.filter(z => z.hash === location.hash).reverse();   // ostatnie zapytanie tego adresu wygrywa
  ZAPYTANIA = [];
  const z = (EKSPORT_EKRANU[klucz] || []).map(s => odKonca.find(x => x.sciezka === s)).find(Boolean);
  const widok = $('#widok');
  if (!z || widok.querySelector('.eksport-pasek')) return;
  const pasek = document.createElement('div');
  pasek.className = 'eksport-pasek';
  pasek.innerHTML = przyciskiEksportu(z.sciezka, z.parametry, ['budzet/lista', 'lista/platnosci'].includes(z.sciezka) ? 'Pobierz (układ Budget Studio)' : 'Pobierz');
  const naglowek = widok.querySelector('.naglowek-strony');
  if (naglowek) naglowek.appendChild(pasek);
  else widok.prepend(pasek);
}

// ---------- Import: plik przeciągnięty do okna albo wybrany przyciskiem ----------
const MAKS_IMPORT = 20 * 1024 * 1024;

async function wyslijPlik(plik, tryb) {
  const r = await fetch(`/api/import?tryb=${tryb}`, { method: 'POST', body: plik,
    headers: { 'X-Finanse': '1', 'Content-Type': 'application/octet-stream', 'X-Nazwa-Pliku': encodeURIComponent(plik.name) } });
  const w = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(w.blad || `Błąd ${r.status}`);
  return w;
}

async function importujPlik(plik) {
  if (plik.size > MAKS_IMPORT) {
    return kartaImportu({ rozpoznany: false, plik_zrodlowy: plik.name, ostrzezenie: 'Plik większy niż 20 MB. To nie wygląda na eksport z banku ani z biura.' });
  }
  komunikat(`Sprawdzam plik ${plik.name}…`);
  try {
    const w = await wyslijPlik(plik, 'podglad');
    komunikat('');
    kartaImportu(w, plik);
  } catch (e) {
    komunikat(`Nie udało się sprawdzić pliku: ${e.message}`, true);
  }
}

const LICZNIKI = [['pominiete', 'Pominięte'], ['dodane', 'Dodane'], ['zaktualizowane', 'Zaktualizowane'], ['bez_zmian', 'Bez zmian']];

function licznikiImportu(l) {
  return `<div class="import-liczniki">${LICZNIKI.map(([k, n]) => `<div class="${k === 'pominiete' && l[k] ? 'uwaga' : ''}"><b>${l[k] ?? 0}</b><span>${n}</span></div>`).join('')}</div>`;
}

function kartaImportu(w, plik) {
  const k = $('#karta');
  const zamknij = '<button class="zamknij" aria-label="Zamknij">×</button>';
  if (!w.rozpoznany) {
    k.innerHTML = `${zamknij}<h2>Tego pliku nie zaimportuję</h2>
      <div class="komunikat"><span>${esc(w.ostrzezenie)}</span></div>
      <dl><dt>Plik</dt><dd>${esc(w.plik_zrodlowy || plik?.name || '')}</dd></dl>
      <p class="notka">Nic nie zostało zapisane. Apka rozpoznaje plik po zawartości (nagłówki kolumn, arkusze), nie po nazwie.</p>
      <div class="akcje"><button data-a="anuluj">Zamknij</button></div>`;
  } else {
    const przyklady = (tytul, lista) => lista?.length ? `<h3>${tytul}</h3><ul class="przyklady">${lista.map(x => `<li>${esc(x)}</li>`).join('')}</ul>` : '';
    k.innerHTML = `${zamknij}<h2>Import pliku</h2>
      <dl><dt>Plik</dt><dd>${esc(w.plik_zrodlowy)}</dd><dt>Rozpoznany jako</dt><dd>${esc(w.opis_zrodla)}</dd>
        <dt>Wierszy w pliku</dt><dd>${w.wierszy}</dd>
        <dt>${w.duplikat ? 'Już jest w Dane jako' : 'Zapiszę w Dane jako'}</dt><dd>${esc(w.duplikat || w.cel)}</dd></dl>
      ${licznikiImportu(w.liczniki)}
      ${(w.uwagi || []).map(u => `<p class="notka">${esc(u)}</p>`).join('')}
      ${przyklady('Pominięte (nie trafią do apki)', w.przyklady?.pominiete)}${przyklady('Dodane, na przykład', w.przyklady?.dodane)}
      ${przyklady('Zaktualizowane, na przykład', w.przyklady?.zaktualizowane)}
      <p class="notka">Porównanie z tym, co już jest w folderze Dane. ${w.duplikat ? 'Pliku nie zapiszę drugi raz; import trafi tylko do historii.' : 'Plik trafi do folderu bez zmian, a apka przeliczy dane.'}</p>
      <div class="akcje"><button class="glowny" data-a="importuj">${w.duplikat ? 'Zapisz w historii' : 'Importuj'}</button><button data-a="anuluj">Anuluj</button></div>`;
  }
  k.hidden = false;
  $('.zamknij', k).onclick = () => { k.hidden = true; };
  k.querySelector('[data-a="anuluj"]').onclick = () => { k.hidden = true; };
  const b = k.querySelector('[data-a="importuj"]');
  if (b) b.onclick = async () => {
    b.disabled = true;
    b.textContent = 'Importuję…';
    try {
      const z = await wyslijPlik(plik, 'zapisz');
      if (!z.zapisano) { kartaImportu(z, plik); return; }
      k.hidden = true;
      await sprawdzStan();
      location.hash = `#/platnosci/import?id=${encodeURIComponent(z.id)}`;
      komunikat(z.cel ? `Zaimportowano: plik jest w Dane/${z.cel}.${z.bledy?.length ? ' Uwagi: ' + z.bledy.join('; ') : ''}`
        : 'Ten sam plik już był w Dane; import zapisany w historii, dane bez zmian.', !!z.bledy?.length);
    } catch (e) {
      b.disabled = false;
      b.textContent = 'Importuj';
      komunikat(`Nie udało się zaimportować: ${e.message}`, true);
    }
  };
}

// Przeciągnięcie pliku nad okno: nakładka; upuszczenie: podgląd importu. Przeglądarka nie otwiera pliku sama.
(() => {
  const nakladka = document.createElement('div');
  nakladka.id = 'upusc';
  nakladka.hidden = true;
  nakladka.setAttribute('aria-hidden', 'true');
  nakladka.innerHTML = `<div>${ik('plik')}<b>Upuść plik, żeby go zaimportować</b>
    <span>Historia operacji ING, eksport z Fakturowni albo Budget Studio, rejestr zakupów albo wyniki z biura. Najpierw zobaczysz podsumowanie, nic nie zapiszę bez „Importuj”.</span></div>`;
  document.body.appendChild(nakladka);
  let glebokosc = 0;
  const maPliki = e => [...(e.dataTransfer?.types || [])].includes('Files');
  window.addEventListener('dragenter', e => { if (!maPliki(e)) return; e.preventDefault(); glebokosc++; nakladka.hidden = false; });
  window.addEventListener('dragover', e => { if (!maPliki(e)) return; e.preventDefault(); e.dataTransfer.dropEffect = 'copy'; });
  window.addEventListener('dragleave', e => { if (!maPliki(e)) return; glebokosc = Math.max(0, glebokosc - 1); if (!glebokosc) nakladka.hidden = true; });
  window.addEventListener('drop', e => {
    if (!maPliki(e)) return;
    e.preventDefault();
    glebokosc = 0;
    nakladka.hidden = true;
    const pliki = [...e.dataTransfer.files];
    if (pliki.length > 1) komunikat('Przeciągnij jeden plik naraz. Sprawdzam pierwszy.', true);
    if (pliki[0]) importujPlik(pliki[0]);
  });
})();

// ---------- Ekrany ----------
const czasPl = iso => iso ? new Date(iso).toLocaleString('pl-PL', { dateStyle: 'short', timeStyle: 'short' }) : '';

function chipStanu(x) {
  const s = x.stan || '';
  const [klasa, tekst] = s === 'wczytany' ? ['plus', 'wczytany'] : s === 'błąd odczytu' ? ['minus', 'błąd odczytu']
    : s.startsWith('zastąpiony') ? ['neutral', 'zastąpiony nowszym'] : s.startsWith('kopia') ? ['neutral', 'kopia pliku']
      : s.startsWith('ten sam plik') ? ['neutral', 'ten sam plik'] : ['neutral', s];
  return `<span class="chip ${klasa}" title="${esc(s)}">${esc(tekst)}</span>`;
}

const ZRODLA_IMPORTU = ['ING', 'Fakturownia', 'Budget Studio', 'Rejestr zakupów', 'Wyniki biura'];

// Pola wyboru ekranu Eksport: [nazwa parametru, etykieta, opcje | 'data' | 'rok'].
function poleEksportu([id, etykieta, opcje], wartosc) {
  if (opcje === 'data') return `<label>${etykieta}<input type="date" data-pole="${id}" value="${esc(wartosc || '')}"></label>`;
  if (opcje === 'rok') return `<label>${etykieta}<input type="number" min="2020" max="2100" step="1" data-pole="${id}" value="${esc(wartosc || '')}"></label>`;
  return `<label>${etykieta}<select data-pole="${id}">${opcje.map(([v, n]) => `<option value="${esc(v)}"${String(wartosc ?? '') === String(v) ? ' selected' : ''}>${esc(n)}</option>`).join('')}</select></label>`;
}

Object.assign(WIDOKI, {
  // Ekran Eksport jak w BS: zakładki formatu (Excel, CSV), kafle zakresów z polami i przyciskiem pobrania.
  async eksport(p) {
    const format = p.format === 'csv' ? 'csv' : 'xlsx';
    const drzewo = await api('budzet/drzewo').catch(() => null);
    const arkusze = (drzewo?.foldery || []).flatMap(f => Object.values(f.kategorie).flat().map(a => [a.id, `${f.folder} / ${a.nazwa}`]));
    const rok = (STAN?.bank_do || '').slice(0, 4) || String(new Date().getFullYear());
    // listy planu: widoki listy płatności z pakietu 7, które są samym zakresem listy (wszystkie, po terminie, do zapłacenia...)
    const widokiPl = await api('widoki', { ekran: 'platnosci' }).catch(() => []);
    const listy = widokiPl.filter(v => Object.keys(v.parametry || {}).every(k => k === 'lista'))
      .map(v => [v.parametry?.lista || 'wszystkie', v.nazwa]);
    const rachunki = [['', 'Wszystkie'], ['główny', 'Główny'], ['online', 'Online'], ['VAT', 'VAT']];
    const zakresy = [
      { tytul: 'Płatności budżetu', ik: 'link', sciezka: 'budzet/lista', glowny: true,
        opis: 'Plany i połączone płatności rzeczywiste w układzie eksportu Budget Studio: te same kolumny, kwoty ze znakiem. Plik porównasz 1:1 z eksportem z BS.',
        pola: [['lista', 'Lista', listy], ['rodzaj', 'Rodzaj', [['', 'Wpływy i obciążenia'], ['1', 'Wpływy'], ['-1', 'Obciążenia']]]] },
      { tytul: 'Faktury sprzedażowe', ik: 'dokument', sciezka: 'faktury', opis: 'Faktury z Fakturowni ze stanem zapłaty z banku, klientem i pozycjami.',
        pola: [['od', 'Wystawione od', 'data'], ['do', 'do', 'data']] },
      { tytul: 'Należności z wiekowaniem', ik: 'kalendarzX', sciezka: 'naleznosci', opis: 'Nieopłacone faktury z dniami po terminie i przedziałem wiekowania, w Excelu także sumy przedziałów.',
        pola: [['po_terminie', 'Zakres', [['', 'Wszystkie nieopłacone'], ['1', 'Tylko po terminie']]]] },
      { tytul: 'Bank ING', ik: 'bank', sciezka: 'operacje', opis: 'Operacje z rachunków ING z ruchem wewnętrznym i połączonymi fakturami.',
        pola: [['rachunek', 'Rachunek', rachunki], ['od', 'Od', 'data'], ['do', 'Do', 'data']] },
      { tytul: 'Rejestr zakupów', ik: 'dokument', sciezka: 'zakupy', opis: 'Dokumenty kosztowe z biura z płatnością znalezioną w banku.',
        pola: [['od', 'Od', 'data'], ['do', 'Do', 'data']] },
      { tytul: 'Wydatki z banku', ik: 'dol', sciezka: 'wydatki', opis: 'Płatności wychodzące z rodzajem kosztu, klientem i dokumentem z rejestru.',
        pola: [['od', 'Od', 'data'], ['do', 'Do', 'data']] },
      { tytul: 'Wynik zarządczy', ik: 'wykres', sciezka: 'wynik', opis: 'Pozycje wyniku zarządczego miesiąc po miesiącu.', pola: [['rok', 'Rok', 'rok']], start: { rok } },
      { tytul: 'Rentowność klientów', ik: 'osoby', sciezka: 'rentownosc/klienci', opis: 'Obrót, koszty klienta, marża, koszt pracy i wynik klienta.',
        pola: [['rok', 'Rok', 'rok']], start: { rok } },
      { tytul: 'Arkusze: plan i wykonanie', ik: 'arkusz', sciezka: 'rentownosc/arkusze', opis: 'Plan i wykonanie przychodów i kosztów każdego arkusza budżetu.', pola: [] },
      { tytul: 'Podatek VAT', ik: 'przekreslony', sciezka: 'vat', opis: 'VAT należny, naliczony, do zapłaty i zapłacony w każdym miesiącu.', pola: [['rok', 'Rok', 'rok']], start: { rok } },
      { tytul: 'Cash flow', ik: 'fale', sciezka: 'cashflow/okresy', opis: 'Wpływy, obciążenia i saldo w okresach oraz lista pozycji. Bez dat: 13 tygodni od dnia stanu.',
        pola: [['granulacja', 'Granulacja', [['tydzien', 'Tydzień'], ['dzien', 'Dzień'], ['miesiac', 'Miesiąc']]], ['od', 'Od', 'data'], ['do', 'Do', 'data']],
        start: { granulacja: 'tydzien' } },
      { tytul: 'Arkusz budżetu', ik: 'arkusz', sciezka: 'budzet/arkusz', opis: 'Wiersze arkusza z ustawieniami razy miesiące, saldo okresu i saldo narastająco.',
        pola: [['id', 'Arkusz', arkusze.length ? arkusze : [['', 'Brak arkuszy']]]], start: { id: arkusze[0]?.[0] || '' } },
    ];
    const kafle = zakresy.map((z, i) => {
      const start = { ...(z.pola.some(x => x[0] === 'lista') ? { lista: 'wszystkie' } : {}), ...(z.start || {}) };
      return `<div class="eksport-kafel${z.glowny ? ' glowny' : ''}" data-zakres="${i}">
        <div class="tytul">${ik(z.ik)}${esc(z.tytul)}</div><div class="opis">${esc(z.opis)}</div>
        ${z.pola.length ? `<div class="filtry">${z.pola.map(f => poleEksportu(f, start[f[0]])).join('')}</div>` : ''}
        <div class="dol"><a class="przycisk glowny" download href="${esc(adresEksportu(z.sciezka, start, format))}">${ik('plik')}Pobierz ${format === 'csv' ? 'CSV' : 'Excel'}</a></div></div>`;
    }).join('');
    setTimeout(() => document.querySelectorAll('.eksport-kafel').forEach(el => {
      const z = zakresy[+el.dataset.zakres];
      const odswiez = () => {
        const par = Object.fromEntries([...el.querySelectorAll('[data-pole]')].map(x => [x.dataset.pole, x.value]));
        el.querySelector('a.przycisk').href = adresEksportu(z.sciezka, par, format);
      };
      el.querySelectorAll('[data-pole]').forEach(x => x.addEventListener('input', odswiez));
    }));
    return `<h1>Eksport ${pytajnik('eksport')}</h1>
      <div class="zakladki" role="tablist">
        <a role="tab" href="#/eksport" aria-selected="${format === 'xlsx'}">${ik('arkusz')}Excel</a>
        <a role="tab" href="#/eksport?format=csv" aria-selected="${format === 'csv'}">${ik('plik')}CSV</a></div>
      <div class="eksport-info">${ik('ptaszek')}<span>Plik powstaje z danych na tym komputerze i pobiera go przeglądarka; nic nie wychodzi do internetu.
        ${format === 'csv' ? 'CSV: średnik, przecinek dziesiętny, UTF-8 (Excel otworzy go wprost); płatności budżetu w formacie pliku z Budget Studio (tabulator).'
          : 'Excel: kwoty jako liczby w złotych, daty jako daty, osobny arkusz z podsumowaniem i sumami.'}
        Każdą listę z bieżącymi filtrami pobierzesz też przyciskami Excel i CSV nad listą.</span></div>
      <div class="eksport-siatka">${kafle}</div>`;
  },

  // Historia importów jak w BS: każdy plik w Dane to import; liczniki Dodane, Zaktualizowane, Bez zmian, Pominięte.
  async 'platnosci/importy'(p) {
    const d = await api('importy/historia');
    let lista = d.importy;
    if (p.zrodlo) lista = lista.filter(x => x.zrodlo === p.zrodlo);
    if (p.sposob) lista = lista.filter(x => x.sposob === p.sposob);
    if (p.status === 'pominiete') lista = lista.filter(x => x.pominiete);
    if (p.status === 'zaktualizowane') lista = lista.filter(x => x.zaktualizowane);
    const liczba = (k, n) => ({ id: k, naglowek: n, liczba: true, html: x => `<span class="${k === 'pominiete' && x[k] ? 'minus' : ''}">${x[k]}</span>`, sortKlucz: x => x[k] });
    const kol = [
      { naglowek: 'Stan', html: chipStanu, sortKlucz: x => x.stan },
      { naglowek: 'Sposób dodania', wartosc: x => x.sposob },
      { naglowek: 'Źródło', wartosc: x => x.zrodlo },
      { naglowek: 'Nazwa', html: x => `${esc(x.plik)}${x.plik_zrodlowy && x.plik_zrodlowy !== x.plik ? `<br><span class="szary">z pliku ${esc(x.plik_zrodlowy)}</span>` : ''}`, sortKlucz: x => x.plik },
      { naglowek: 'Data importu', wartosc: x => czasPl(x.czas), sortKlucz: x => x.czas },
      { naglowek: 'Wierszy', liczba: true, wartosc: x => x.wierszy, sortKlucz: x => x.wierszy },
      liczba('dodane', 'Dodane'), liczba('zaktualizowane', 'Zaktualizowane'), liczba('bez_zmian', 'Bez zmian'), liczba('pominiete', 'Pominięte'),
    ];
    setTimeout(() => {
      const wybor = $('#import-plik');
      if (wybor) wybor.onchange = () => { if (wybor.files[0]) importujPlik(wybor.files[0]); wybor.value = ''; };
    });
    const inne = (d.inne || []).map(x => `<li>${esc(x.rodzaj)}: ${x.wierszy} (${esc(x.uwagi || '')})</li>`).join('');
    return `<div class="naglowek-strony"><div><h1>Historia importów ${pytajnik('importy')}</h1><div class="okruszki">Płatności / Dane</div></div>
        <div class="akcje"><label class="przycisk glowny">${ik('plus')}Importuj plik<input type="file" id="import-plik" accept=".csv,.xlsx,.xls,text/csv" hidden></label>
          <button id="odswiez">Wczytaj pliki na nowo</button></div></div>
      <p class="notka">Każdy plik w folderze ${esc(d.katalog)} to jeden import. Nowy plik przeciągnij do okna apki (na dowolnym ekranie) albo wybierz przyciskiem:
        apka rozpozna źródło po zawartości, pokaże podsumowanie i dopiero po „Importuj” zapisze plik w folderze Dane. Pominięte sprawdzaj najpierw.</p>
      <div class="filtry">
        ${filtr('zrodlo', 'Źródło', [['', 'Wszystkie'], ...ZRODLA_IMPORTU.map(z => [z, z])], p.zrodlo)}
        ${filtr('sposob', 'Sposób dodania', [['', 'Wszystkie'], ['folder Dane', 'Folder Dane'], ['przeciągnięty do okna', 'Przeciągnięty do okna']], p.sposob)}
        ${filtr('status', 'Pokaż', [['', 'Wszystkie importy'], ['pominiete', 'Tylko z pominiętymi'], ['zaktualizowane', 'Tylko z aktualizacjami']], p.status)}
      </div>
      ${tabela({ kolumny: kol, dane: lista, sortLokalny: true, onWiersz: x => { location.hash = `#/platnosci/import?id=${encodeURIComponent(x.id)}`; } })}
      ${inne ? `<h2 class="sekcja">Inne źródła</h2><ul class="lista szary">${inne}</ul>` : ''}
      <p class="szary">Ostatnie wczytanie plików: ${esc(STAN?.meta?.odbudowa ? czasPl(STAN.meta.odbudowa) : '')}, ${esc(STAN?.meta?.mac || '')}</p>`;
  },

  // Podsumowanie jednego importu jak w BS: zakładki z licznikami, najpierw Pominięte (z powodem).
  async 'platnosci/import'(p) {
    const d = await api('importy/podsumowanie', p);
    const im = d.import;
    const adres = k => `#/platnosci/import?id=${encodeURIComponent(im.id)}&kategoria=${k}`;
    const kol = [{ naglowek: 'Wiersz w pliku', liczba: true, wartosc: x => x.wiersz ?? '' }, { naglowek: 'Pozycja', wartosc: x => x.opis }];
    if (d.kategoria === 'pominiete') kol.push({ naglowek: 'Powód', wartosc: x => x.powod });
    if (d.kategoria === 'zaktualizowane') kol.push({ naglowek: 'Co się zmieniło', wartosc: x => x.zmiany });
    const opisy = { pominiete: 'Te wiersze nie trafiły do apki. Popraw plik u źródła i zaimportuj go jeszcze raz albo zostaw, jeśli powód jest w porządku.',
      dodane: 'Pozycje, których wcześniej nie było.', zaktualizowane: 'Te same pozycje (ten sam numer) z nowymi danymi, np. faktura opłacona po poprzednim imporcie.',
      bez_zmian: 'Pozycje, które już były, z tymi samymi danymi.' };
    const pola = [['Źródło', im.opis_zrodla || im.zrodlo], ['Plik', im.katalog ? `Dane/${im.katalog}/${im.plik}` : im.plik],
      ['Nazwa oryginalna', im.plik_zrodlowy && im.plik_zrodlowy !== im.plik ? im.plik_zrodlowy : ''], ['Sposób dodania', im.sposob],
      ['Data importu', czasPl(im.czas)], ['Stan', im.stan], ['Wierszy w pliku', String(im.wierszy)], ['Uwagi', im.uwagi], ['Błąd', im.blad]];
    return `<div class="naglowek-strony"><div><h1>Podsumowanie importu ${pytajnik('importy')}</h1>
        <div class="okruszki"><a href="#/platnosci/importy">Historia importów</a> / ${esc(im.plik)}</div></div>
        <div class="akcje"><a class="przycisk" href="#/platnosci/importy">Wróć do historii</a></div></div>
      <dl class="import-naglowek">${pola.filter(([, v]) => v).map(([n, v]) => `<dt>${esc(n)}</dt><dd>${esc(v)}</dd>`).join('')}</dl>
      <div class="zakladki" role="tablist">${LICZNIKI.map(([k, n]) => `<a role="tab" href="${adres(k)}" aria-selected="${d.kategoria === k}">${n}
        <span class="licznik${k === 'pominiete' && im[k] ? '' : ' szary'}">${im[k]}</span></a>`).join('')}</div>
      <p class="notka">${esc(opisy[d.kategoria])}</p>
      ${tabela({ kolumny: kol, dane: d.wiersze, poczatek: (d.strona - 1) * d.ile + 1 })}
      ${stopka(d, p)}`;
  },
});

Object.assign(POMOC, {
  importy: { tytul: 'Historia importów', krotko: 'Każdy plik z banku, Fakturowni, biura i Budget Studio to import z licznikami jak w Budget Studio.',
    co: 'Dodane: pozycje, których wcześniej nie było. Zaktualizowane: te same pozycje (numer operacji, faktury, dokumentu) z innymi danymi. Bez zmian: już były. Pominięte: wiersze, których apka nie przyjmie, z powodem (np. drugi raz ta sama operacja w pliku, wiersz rejestru bez numeru, plik nieczytelny).',
    skad: 'Pliki z folderu Finanse/Raporty/Dane. Plik przeciągnięty do okna apka zapisuje tam bez zmian, pod nazwą źródło_rodzaj_data, z uprawnieniami tylko dla właściciela.',
    jak: 'Każdy plik porównany ze stanem sprzed niego: ING, rejestr i wyniki z biura ze wszystkimi wcześniejszymi plikami, Fakturownia i Budget Studio z poprzednim plikiem (liczy się tylko najnowszy). Ten sam plik drugi raz: wszystko Bez zmian i pliku nie zapisuję drugi raz.',
    zrob: 'Po każdym imporcie zajrzyj najpierw w Pominięte. Nieznany plik dostaje ostrzeżenie i nie jest zapisywany.' },
  eksport: { tytul: 'Eksport', krotko: 'Pobranie danych do Excela albo CSV: płatności budżetu jak w Budget Studio, listy, zestawienia.',
    co: 'Płatności budżetu mają układ eksportu Budget Studio (te same kolumny, kwoty ze znakiem), więc porównasz je 1:1 z plikiem z BS. Listy i zestawienia mają kolumny jak na ekranie i arkusz z podsumowaniem.',
    skad: 'Te same zapytania, z których korzystają ekrany apki, na danych z tego komputera.',
    jak: 'Przyciski nad listą biorą bieżące filtry i wszystkie strony listy. Suma kolumny Brutto w eksporcie płatności równa się stopce listy.',
    zrob: 'Excel do pracy i filtrowania, CSV do porównań i innych programów. Plik zapisuje przeglądarka w folderze pobranych.' },
});

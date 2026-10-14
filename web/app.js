'use strict';
// Finanse DigitalH: interfejs. Wszystkie liczby przychodzą z serwera w groszach; tu tylko formatowanie.

const MIESIACE = ['stycznia', 'lutego', 'marca', 'kwietnia', 'maja', 'czerwca', 'lipca', 'sierpnia',
  'września', 'października', 'listopada', 'grudnia'];

const IKONY = {
  pulpit: '<path d="M3 11l9-7 9 7v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/>',
  budzet: '<rect x="3" y="4" width="18" height="16" rx="1"/><path d="M3 9h18M3 14h18M9 4v16"/>',
  platnosci: '<circle cx="12" cy="12" r="9"/><path d="M15 9.5c-.5-1-1.6-1.5-3-1.5-1.7 0-3 .8-3 2s1.3 1.7 3 2 3 .8 3 2-1.3 2-3 2c-1.4 0-2.6-.6-3-1.6M12 6v2M12 16v2"/>',
  cashflow: '<path d="M3 8c3-3 6 3 9 0s6 3 9 0M3 13c3-3 6 3 9 0s6 3 9 0M3 18c3-3 6 3 9 0s6 3 9 0"/>',
  rentownosc: '<path d="M5 20V11M10 20V5M15 20v-7M20 20v-4M3 20h18"/>',
  eksport: '<path d="M12 4v11M7 10l5 5 5-5M4 19h16"/>',
};

const MENU = [
  { id: 'pulpit', nazwa: 'Pulpit' },
  { id: 'budzet', nazwa: 'Budżet' },
  { id: 'platnosci', nazwa: 'Płatności' },
  { id: 'cashflow', nazwa: 'Cash flow' },
  { id: 'rentownosc', nazwa: 'Rentowność' },
  { id: 'eksport', nazwa: 'Eksport' },
];

// Podstrony w wysuwanym panelu, jak w Budget Studio. etap = kiedy powstanie.
const PODSTRONY = {
  platnosci: [
    { grupa: 'Płatności oczekujące' },
    { nazwa: 'Do połączenia', hash: '#/platnosci/do-polaczenia', licznik: 'do_polaczenia' },
    { nazwa: 'Do weryfikacji', hash: '#/platnosci/do-weryfikacji', licznik: 'do_weryfikacji' },
    { grupa: 'Bank ING' },
    { nazwa: 'Wszystkie operacje', hash: '#/platnosci/bank' },
    { nazwa: 'Wpływy', hash: '#/platnosci/bank?kierunek=wplywy&wewnetrzne=bez' },
    { nazwa: 'Obciążenia', hash: '#/platnosci/bank?kierunek=obciazenia&wewnetrzne=bez' },
    { nazwa: 'Ruch wewnętrzny i VAT', hash: '#/platnosci/bank?wewnetrzne=tylko' },
    { grupa: 'Dokumenty' },
    { nazwa: 'Faktury sprzedażowe', hash: '#/platnosci/faktury' },
    { nazwa: 'Nadal nieopłacone', hash: '#/platnosci/naleznosci' },
    { nazwa: 'Po terminie płatności', hash: '#/platnosci/naleznosci?po_terminie=1' },
    { nazwa: 'Rejestr zakupów (biuro)', hash: '#/platnosci/zakupy' },
    { nazwa: 'Dokumenty bez płatności', hash: '#/platnosci/zakupy?stan=bez%20p%C5%82atno%C5%9Bci%20w%20banku' },
    { grupa: 'Dane' },
    { nazwa: 'Historia importów', hash: '#/platnosci/importy' },
    { nazwa: 'Wyniki z biura (RZiS)', hash: '#/platnosci/wyniki-biura' },
  ],
  budzet: [{ grupa: 'Foldery' }, { nazwa: 'Klienci', hash: '#/budzet' },
    { grupa: 'Wydatki z banku' }, { nazwa: 'Wszystkie wydatki', hash: '#/budzet/wydatki' },
    { nazwa: 'Nieprzypisane', hash: '#/budzet/wydatki?rodzaj=nieprzypisany' },
    { nazwa: 'Koszty klientów', hash: '#/budzet/wydatki?rodzaj=przenoszony' },
    { nazwa: 'Bez dokumentu w rejestrze', hash: '#/budzet/wydatki?dokument=bez%20dokumentu' },
    { grupa: 'Ustawienia' }, { nazwa: 'Reguły przypisań', hash: '#/budzet/reguly' }],
  cashflow: [{ grupa: 'Zapisane widoki' }, { nazwa: '2 tyg. w przód', etap: 5 }, { nazwa: '8 tyg. w przód', etap: 5 },
    { nazwa: '13 tyg. w przód', etap: 5 }, { nazwa: '6 mies. w przód', etap: 5 }],
  rentownosc: [{ grupa: 'Zapisane widoki' }, { nazwa: 'Wynik zarządczy', hash: '#/rentownosc' },
    { nazwa: 'Obroty wg klientów', hash: '#/rentownosc/klienci' }, { nazwa: 'Koszty wg kategorii', hash: '#/rentownosc/koszty' },
    { nazwa: 'Podatek VAT', hash: '#/rentownosc/vat' }],
  eksport: [{ grupa: 'Eksport' }, { nazwa: 'CSV i Excel', etap: 6 }],
};

const $ = (s, el = document) => el.querySelector(s);

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function zl(gr, waluta = true) {
  if (gr === null || gr === undefined) return '';
  const znak = gr < 0 ? '-' : '';
  const a = Math.abs(Math.trunc(gr));
  const calosc = String(Math.floor(a / 100)).replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
  return `${znak}${calosc},${String(a % 100).padStart(2, '0')}${waluta ? ' zł' : ''}`;
}

function dataPl(iso) {
  if (!iso) return '';
  const [r, m, d] = iso.split('-').map(Number);
  return `${d} ${MIESIACE[m - 1]} '${String(r).slice(2)}`;
}

async function api(sciezka, parametry = {}) {
  const q = new URLSearchParams(Object.entries(parametry).filter(([, v]) => v !== '' && v != null));
  const r = await fetch(`/api/${sciezka}${q.toString() ? '?' + q : ''}`);
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).blad || `Błąd ${r.status}`);
  return r.json();
}

async function odbuduj() {
  komunikat('Wczytuję pliki na nowo…');
  const r = await fetch('/api/odbuduj', { method: 'POST', headers: { 'X-Finanse': '1' } });
  if (!r.ok) return komunikat('Nie udało się odświeżyć danych.', true);
  await sprawdzStan();
  pokaz();
}

// Decyzja Mata: dopisanie do pliku zmian tego Maca i przeliczenie. Zwraca true, gdy się udało.
async function zmiana(typ, dane) {
  const r = await fetch('/api/zmiana', { method: 'POST', headers: { 'X-Finanse': '1', 'Content-Type': 'application/json' },
    body: JSON.stringify({ typ, dane }) });
  const w = await r.json().catch(() => ({}));
  if (!r.ok) { komunikat(w.blad || 'Nie udało się zapisać decyzji.', true); return false; }
  $('#karta').hidden = true;
  await sprawdzStan();
  await pokaz();
  komunikat('Zapisane. Decyzja jest w pliku zmian tego Maca, drugi Mac zobaczy ją po synchronizacji iCloud.');
  return true;
}

function komunikat(tekst, blad = false, przycisk = null) {
  const el = $('#komunikaty');
  if (!tekst) { el.innerHTML = ''; return; }
  el.innerHTML = `<div class="komunikat${blad ? ' blad' : ''}"><span>${esc(tekst)}</span></div>`;
  if (przycisk) {
    const b = document.createElement('button');
    b.textContent = przycisk.nazwa;
    b.onclick = przycisk.akcja;
    el.firstChild.appendChild(b);
  }
}

let STAN = null;
async function sprawdzStan() {
  STAN = await api('stan');
  $('#mac').textContent = `Ten komputer: ${STAN.mac}`;
  if (!STAN.aktualna) {
    komunikat('Są nowe pliki w folderze Dane albo zmiany z drugiego Maca.', false, { nazwa: 'Odśwież dane', akcja: odbuduj });
  } else if (STAN.bledy.length) {
    komunikat('Uwagi przy wczytywaniu: ' + STAN.bledy.join('; '), true);
  } else {
    komunikat('');
  }
}

// ---------- nawigacja ----------
function trasa() {
  const [sciezka, zapytanie] = (location.hash.slice(2) || 'pulpit').split('?');
  const [sekcja, podstrona] = sciezka.split('/');
  return { sekcja, podstrona, parametry: Object.fromEntries(new URLSearchParams(zapytanie || '')) };
}

function ustawParametry(nowe) {
  const t = trasa();
  const p = { ...t.parametry, ...nowe };
  Object.keys(p).forEach(k => (p[k] === '' || p[k] == null) && delete p[k]);
  const q = new URLSearchParams(p).toString();
  location.hash = `#/${t.sekcja}${t.podstrona ? '/' + t.podstrona : ''}${q ? '?' + q : ''}`;
}

function zbudujMenu() {
  const ul = $('#menu');
  ul.innerHTML = MENU.map(m => `<li><button data-id="${m.id}"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${IKONY[m.id]}</svg><span class="etykieta">${m.nazwa}</span></button></li>`).join('');
  ul.addEventListener('click', e => {
    const b = e.target.closest('button');
    if (!b) return;
    const id = b.dataset.id;
    if (id === 'pulpit') { zamknijWysuw(); location.hash = '#/pulpit'; return; }
    otworzWysuw(id);
  });
  document.addEventListener('click', e => {
    if (!e.target.closest('#wysuw') && !e.target.closest('#menu')) zamknijWysuw();
    if (!e.target.closest('#karta') && !e.target.closest('tbody')) $('#karta').hidden = true;
  });
  document.addEventListener('keydown', e => { if (e.key === 'Escape') { zamknijWysuw(); $('#karta').hidden = true; } });
}

function otworzWysuw(id) {
  const w = $('#wysuw');
  const nazwa = MENU.find(m => m.id === id).nazwa;
  w.innerHTML = `<h2>${nazwa}</h2>` + (PODSTRONY[id] || []).map(p => {
    if (p.grupa) return `<h3>${esc(p.grupa)}</h3>`;
    if (p.etap) return `<a class="nieaktywny">${esc(p.nazwa)} <span class="etap">etap ${p.etap}</span></a>`;
    const n = p.licznik && STAN?.naleznosci ? STAN.naleznosci[p.licznik] : 0;
    return `<a href="${p.hash}">${esc(p.nazwa)}${n ? ` <span class="liczba">${n}</span>` : ''}</a>`;
  }).join('');
  w.hidden = false;
  document.body.classList.add('wysuw-otwarty');
  w.querySelectorAll('a[href]').forEach(a => a.addEventListener('click', zamknijWysuw));
}

function zamknijWysuw() { $('#wysuw').hidden = true; document.body.classList.remove('wysuw-otwarty'); }

function zaznaczMenu(sekcja) {
  document.querySelectorAll('#menu button').forEach(b => b.setAttribute('aria-current', String(b.dataset.id === sekcja)));
}

// ---------- tabela w stylu listy płatności ----------
function tabela({ kolumny, dane, poczatek, onWiersz, stopkaSum, sortuj, kierunek }) {
  if (!dane.length) return '<div class="pusto">Brak pozycji dla tych filtrów.</div>';
  const th = kolumny.map(k => {
    const s = k.sort ? ` class="sort${k.liczba ? ' liczba-kol' : ''}" data-sort="${k.sort}"${sortuj === k.sort ? ` data-kierunek="${kierunek}"` : ''}` : (k.liczba ? ' class="liczba-kol"' : '');
    return `<th${s}>${k.naglowek}</th>`;
  }).join('');
  const tr = dane.map((w, i) => `<tr data-i="${i}" title="Źródło: ${esc(w.plik)}, wiersz ${w.wiersz}"><td class="lp">${poczatek + i}.</td>${kolumny.map(k => `<td class="${k.liczba ? 'liczba-kol ' : ''}${k.klasa ? k.klasa(w) : ''}">${k.html ? k.html(w) : esc(k.wartosc(w))}</td>`).join('')}</tr>`).join('');
  const tf = stopkaSum ? `<tfoot><tr><td></td>${kolumny.map(k => `<td class="${k.liczba ? 'liczba-kol' : ''}">${stopkaSum[k.id] ?? ''}</td>`).join('')}</tr></tfoot>` : '';
  setTimeout(() => {
    document.querySelectorAll('tbody tr').forEach(r => r.addEventListener('click', () => onWiersz(dane[r.dataset.i])));
    document.querySelectorAll('th.sort').forEach(h => h.addEventListener('click', () => {
      const nowy = sortuj === h.dataset.sort && kierunek === 'malejaco' ? 'rosnaco' : 'malejaco';
      ustawParametry({ sortuj: h.dataset.sort, kolejnosc: nowy, strona: 1 });
    }));
  });
  return `<div class="tabela-ramka"><table><thead><tr><th></th>${th}</tr></thead><tbody>${tr}</tbody>${tf}</table></div>`;
}

function stopka(wynik, parametry) {
  const od = wynik.razem ? (wynik.strona - 1) * wynik.ile + 1 : 0;
  const doN = Math.min(wynik.strona * wynik.ile, wynik.razem);
  const ostatnia = Math.max(1, Math.ceil(wynik.razem / wynik.ile));
  const html = `<div class="stopka">
    <label>Max widocznych <select id="ile">${[50, 100, 200, 500].map(n => `<option${n === wynik.ile ? ' selected' : ''}>${n}</option>`).join('')}</select></label>
    <button id="poprz" ${wynik.strona <= 1 ? 'disabled' : ''} aria-label="Poprzednia strona">↑</button>
    <span>Wyświetlono ${od}–${doN} z ${wynik.razem}</span>
    <button id="nast" ${wynik.strona >= ostatnia ? 'disabled' : ''} aria-label="Następna strona">↓</button>
    <input class="szukaj" id="szukaj" type="search" placeholder="Wyszukaj" value="${esc(parametry.q || '')}">
  </div>`;
  setTimeout(() => {
    $('#ile').onchange = e => ustawParametry({ ile: e.target.value, strona: 1 });
    $('#poprz').onclick = () => ustawParametry({ strona: wynik.strona - 1 });
    $('#nast').onclick = () => ustawParametry({ strona: wynik.strona + 1 });
    let t;
    $('#szukaj').oninput = e => { clearTimeout(t); t = setTimeout(() => ustawParametry({ q: e.target.value, strona: 1 }), 350); };
  });
  return html;
}

function filtr(id, etykieta, opcje, wartosc) {
  return `<label>${etykieta}<select data-filtr="${id}">${opcje.map(([v, n]) => `<option value="${v}"${(wartosc || '') === v ? ' selected' : ''}>${n}</option>`).join('')}</select></label>`;
}

function filtrData(id, etykieta, wartosc) {
  return `<label>${etykieta}<input type="date" data-filtr="${id}" value="${esc(wartosc || '')}"></label>`;
}

function podepnijFiltry() {
  document.querySelectorAll('[data-filtr]').forEach(el => el.addEventListener('change', () => ustawParametry({ [el.dataset.filtr]: el.value, strona: 1 })));
}

function pokazKarte(tytul, pola, zrodlo) {
  const k = $('#karta');
  k.innerHTML = `<button class="zamknij" aria-label="Zamknij">×</button><h2>${esc(tytul)}</h2>
    <dl>${pola.filter(([, v]) => v !== '' && v != null).map(([n, v]) => `<dt>${esc(n)}</dt><dd>${esc(v)}</dd>`).join('')}</dl>
    <div class="zrodlo">Źródło: ${esc(zrodlo)}</div>`;
  k.hidden = false;
  $('.zamknij', k).onclick = () => { k.hidden = true; };
}

const chipBank = x => {
  if (!x.stan_bank) return '';
  if (x.stan_bank === 'opłacona') return '<span class="chip plus">zapłacona</span>';
  if (x.stan_bank === 'opłacona poza bankiem') return '<span class="chip plus">poza bankiem</span>';
  if (x.stan_bank === 'częściowo') return '<span class="chip ostrzezenie">częściowo</span>';
  return x.dni_po_terminie > 0 ? `<span class="chip minus">${x.dni_po_terminie} dni po terminie</span>` : '<span class="chip neutral">czeka</span>';
};
const STAN_WPLATY = { dopasowana: 'połączona z fakturą', nieznana: 'do połączenia', sprzed_eksportu: 'faktura sprzed eksportu',
  bez_faktury: 'nie dotyczy faktury' };

const chipKwota = kwota => kwota > 0 ? '<span class="chip plus">↗ wpływy</span>' : '<span class="chip minus">↘ obciążenia</span>';

// ---------- widoki ----------
const WIDOKI = {
  async pulpit() {
    const s = STAN;
    const saldo = (r, opis) => s.salda[r] ? `<div class="kafel${r === 'główny' ? ' glowny' : ''}" title="Źródło: ${esc(s.salda[r].plik)}, wiersz ${s.salda[r].wiersz}">
      <div class="tytul">${opis}</div><div class="wartosc">${zl(s.salda[r].saldo_po)}</div>
      <div class="dop">saldo po ostatniej operacji z ${dataPl(s.salda[r].data_ksiegowania)}</div></div>` : '';
    return `<h1>Pulpit</h1><div class="okruszki">Stan na podstawie plików z folderu Dane</div>
      <div class="kafle">
        <div class="kafel glowny"><div class="tytul">Gotówka (główny + online)</div><div class="wartosc">${zl(s.gotowka)}</div>
          <div class="dop">bez rachunku VAT, który służy tylko do podatku</div></div>
        ${saldo('główny', 'Rachunek główny (5263)')}${saldo('online', 'Rachunek online (5271)')}${saldo('VAT', 'Rachunek VAT (5289)')}
      </div>
      <div class="kafle">
        <div class="kafel"><div class="tytul">Operacje w banku</div><div class="wartosc">${s.liczby.operacje}</div><div class="dop">od ${dataPl(s.bank_od)} do ${dataPl(s.bank_do)}</div></div>
        <div class="kafel"><div class="tytul">Faktury sprzedażowe</div><div class="wartosc">${s.liczby.faktury}</div><div class="dop">z najnowszego eksportu Fakturowni</div></div>
        <div class="kafel"><div class="tytul">Dokumenty kosztowe</div><div class="wartosc">${s.liczby.zakupy}</div><div class="dop">z rejestru zakupów biura</div></div>
      </div>
      ${kafleNaleznosci(s.naleznosci)}
      <p class="notka">Wykres gotówki na 6 miesięcy i płatności do zapłaty pojawią się w kolejnych etapach.</p>`;
  },

  async 'platnosci/bank'(p) {
    const sortuj = p.sortuj || 'data_ksiegowania', kierunek = p.kolejnosc || 'malejaco';
    const w = await api('operacje', p);
    const kol = [
      { naglowek: 'Rodzaj', html: x => chipKwota(x.kwota) },
      { naglowek: 'Rachunek', sort: 'rachunek', wartosc: x => x.rachunek, klasa: () => 'szary' },
      { naglowek: 'Dzień płatności', sort: 'data_ksiegowania', wartosc: x => dataPl(x.data_ksiegowania) },
      { naglowek: 'Kontrahent', sort: 'kontrahent', wartosc: x => x.kontrahent },
      { naglowek: 'Tytuł', wartosc: x => x.tytul || x.opis },
      { id: 'kwota', naglowek: 'Kwota PLN', sort: 'kwota', liczba: true, wartosc: x => zl(x.kwota, false), klasa: x => x.kwota > 0 ? 'plus' : 'minus' },
      { naglowek: 'Saldo po', liczba: true, wartosc: x => zl(x.saldo_po, false), klasa: () => 'szary' },
      { naglowek: 'Ruch', html: x => x.wewnetrzna ? '<span class="chip neutral">wewnętrzny</span>' : '' },
      { naglowek: 'Faktura', html: x => x.faktury ? esc(x.faktury) : x.stan_wplaty === 'nieznana' ? '<span class="chip ostrzezenie">do połączenia</span>' : '', klasa: () => 'szary' },
    ];
    const tytul = p.wewnetrzne === 'tylko' ? 'Ruch wewnętrzny i VAT' : p.kierunek === 'wplywy' ? 'Wpływy' : p.kierunek === 'obciazenia' ? 'Obciążenia' : 'Wszystkie operacje';
    return `<h1>Bank ING</h1><div class="okruszki">Płatności / ${tytul}</div>
      <div class="filtry">
        ${filtr('kierunek', 'Rodzaj', [['', 'Wszystko'], ['wplywy', 'Wpływy'], ['obciazenia', 'Obciążenia']], p.kierunek)}
        ${filtr('rachunek', 'Rachunek', [['', 'Wszystkie'], ['główny', 'Główny 5263'], ['online', 'Online 5271'], ['VAT', 'VAT 5289']], p.rachunek)}
        ${filtr('wewnetrzne', 'Ruch wewnętrzny', [['', 'Pokaż'], ['bez', 'Ukryj'], ['tylko', 'Tylko wewnętrzny']], p.wewnetrzne)}
        ${filtrData('od', 'Od', p.od)}${filtrData('do', 'Do', p.do)}
      </div>
      ${tabela({ kolumny: kol, dane: w.wiersze, poczatek: (w.strona - 1) * w.ile + 1, sortuj, kierunek,
        stopkaSum: { kwota: `<span class="plus">${zl(w.wplywy, false)}</span><br><span class="minus">${zl(w.obciazenia, false)}</span>` },
        onWiersz: x => x.stan_wplaty ? kartaWplaty(x.id) : pokazKarte(x.kontrahent || x.opis, [
          ['Kwota', zl(x.kwota)], ['Rachunek', `${x.rachunek} (${x.nrb.slice(-4)})`], ['Data księgowania', dataPl(x.data_ksiegowania)],
          ['Data transakcji', dataPl(x.data_transakcji)], ['Kwota oryginalna', x.kwota_oryg != null ? `${zl(x.kwota_oryg, false)} ${x.waluta_oryg}` : ''],
          ['Kontrahent', x.kontrahent], ['Rachunek kontrahenta', x.rachunek_kontrahenta], ['Opis', x.opis], ['Tytuł', x.tytul],
          ['Saldo po', zl(x.saldo_po)], ['Ruch wewnętrzny', x.wewnetrzna ? 'tak, nie liczy się do przychodów ani kosztów' : 'nie'],
          ['Numer referencyjny', x.nr_ref]], `${x.plik}, wiersz ${x.wiersz}`) })}
      ${stopka(w, p)}`;
  },

  async 'platnosci/faktury'(p) {
    const w = await api('faktury', p);
    const kol = [
      { naglowek: 'Fakturownia', html: x => x.status === 'Opłacona' ? '<span class="chip plus">opłacona</span>' : `<span class="chip neutral">${esc(x.status.toLowerCase())}</span>` },
      { naglowek: 'W banku', html: chipBank },
      { naglowek: 'Numer', wartosc: x => x.numer },
      { naglowek: 'Klient', wartosc: x => x.klient },
      { naglowek: 'Nabywca', wartosc: x => x.nabywca, klasa: () => 'szary' },
      { naglowek: 'Przedmiot', wartosc: x => x.pozycje },
      { id: 'netto', naglowek: 'Netto PLN', liczba: true, wartosc: x => zl(x.netto, false) },
      { id: 'brutto', naglowek: 'Brutto PLN', liczba: true, wartosc: x => zl(x.brutto, false) },
      { naglowek: 'Dzień wystawienia', wartosc: x => dataPl(x.data_wystawienia) },
      { naglowek: 'Data sprzedaży', wartosc: x => dataPl(x.data_sprzedazy), klasa: () => 'szary' },
      { naglowek: 'Termin', wartosc: x => dataPl(x.termin) },
    ];
    return `<h1>Faktury sprzedażowe</h1><div class="okruszki">Płatności / Faktury z Fakturowni</div>
      <div class="filtry">
        ${filtr('status', 'Status w Fakturowni', [['', 'Wszystkie'], ['Wystawiona', 'Wystawiona'], ['Opłacona', 'Opłacona']], p.status)}
        ${filtr('bank', 'Stan w banku', [['', 'Wszystkie'], ['opłacona', 'Zapłacone'], ['nieopłacona', 'Nieopłacone'], ['częściowo', 'Częściowo'], ['opłacona poza bankiem', 'Poza bankiem']], p.bank)}
        ${filtrData('od', 'Wystawione od', p.od)}${filtrData('do', 'do', p.do)}
      </div>
      <p class="notka">„Fakturownia” to status odhaczony ręcznie. „W banku” liczy aplikacja z wpłat na ING, na dzień ${dataPl(STAN.naleznosci?.dzien_stanu)}.</p>
      ${tabela({ kolumny: kol, dane: w.wiersze, poczatek: (w.strona - 1) * w.ile + 1,
        stopkaSum: { netto: zl(w.netto, false), brutto: zl(w.brutto, false) },
        onWiersz: x => kartaFaktury(x, [
          ['Klient', `${x.klient} (${x.klient_zrodlo})`], ['Nabywca', x.nabywca], ['NIP', x.nip], ['Status', x.status], ['Netto', zl(x.netto)], ['VAT', zl(x.vat)], ['Brutto', zl(x.brutto)],
          ['Opłacono (Fakturownia)', zl(x.oplacono)], ['W banku', x.stan_bank ? `${x.stan_bank}, zapłacono ${zl(x.zaplacono)}, zostało ${zl(x.pozostalo)}` : ''],
          ['Wpłaty', (x.wplaty || '').split('; ').filter(Boolean).map(s => { const [d, k] = s.split(' '); return `${dataPl(d)}: ${zl(+k)}`; }).join('\n')], ['Wystawiona', dataPl(x.data_wystawienia)], ['Data sprzedaży', dataPl(x.data_sprzedazy)],
          ['Termin płatności', dataPl(x.termin)], ['Numer KSeF', x.ksef], ['Korekta', x.korekta ? `tak, do ${x.oryginal}` : ''],
          ['Pozycje', (x.pozycje || '').replaceAll(' | ', '\n')], ['Uwagi', x.uwagi]], `${x.plik}, wiersz ${x.wiersz}`) })}
      ${stopka(w, p)}`;
  },

  async 'platnosci/zakupy'(p) {
    const w = await api('zakupy', p);
    const kol = [
      { naglowek: 'Rejestr', wartosc: x => x.rejestr, klasa: () => 'szary' },
      { naglowek: 'Nr ewid.', wartosc: x => x.nr_ewid, klasa: () => 'szary' },
      { naglowek: 'Kontrahent', wartosc: x => x.podmiot },
      { naglowek: 'Numer dokumentu', wartosc: x => x.nr_dok },
      { naglowek: 'Data', wartosc: x => dataPl(x.data) },
      { id: 'netto', naglowek: 'Netto PLN', liczba: true, wartosc: x => zl(x.netto, false) },
      { naglowek: 'VAT PLN', liczba: true, wartosc: x => x.rejestr === 'krajowe' ? zl(x.vat, false) : '' },
      { naglowek: 'Brutto PLN', liczba: true, wartosc: x => x.brutto != null ? zl(x.brutto, false) : '' },
      { naglowek: 'W banku', html: x => x.stan === 'opłacony' ? `<span class="chip plus">${dataPl(x.data_platnosci)}</span>` : x.stan ? '<span class="chip ostrzezenie">brak płatności</span>' : '' },
    ];
    return `<h1>Rejestr zakupów</h1><div class="okruszki">Płatności / Dokumenty kosztowe z biura</div>
      <div class="filtry">
        ${filtr('rejestr', 'Rejestr', [['', 'Wszystkie'], ['krajowe', 'Krajowe'], ['zagraniczne', 'Zagraniczne']], p.rejestr)}
        ${filtr('stan', 'Płatność w banku', [['', 'Wszystkie'], ['opłacony', 'Znaleziona'], ['bez płatności w banku', 'Brak płatności']], p.stan)}
        ${filtrData('od', 'Od', p.od)}${filtrData('do', 'Do', p.do)}
      </div>
      ${tabela({ kolumny: kol, dane: w.wiersze, poczatek: (w.strona - 1) * w.ile + 1, stopkaSum: { netto: zl(w.netto, false) },
        onWiersz: x => pokazKarte(x.podmiot, [['Numer dokumentu', x.nr_dok], ['Nr ewidencyjny', x.nr_ewid], ['Rejestr', x.rejestr],
          ['Data', dataPl(x.data)], ['Data zaewidencjonowania', dataPl(x.data_zaewid)], ['Netto', zl(x.netto)], ['VAT', zl(x.vat)],
          ['Brutto', x.brutto != null ? zl(x.brutto) : 'brak w rejestrze zagranicznym'],
          ['Płatność w banku', x.data_platnosci ? `${dataPl(x.data_platnosci)}, ${zl(-x.kwota_platnosci)}` : 'nie znaleziono (karta prywatna, kompensata albo jeszcze nieopłacony)']],
          `${x.plik}, wiersz ${x.wiersz}`) })}
      ${stopka(w, p)}`;
  },

  async 'platnosci/importy'() {
    const lista = await api('importy');
    const wiersze = lista.map(x => `<tr><td>${esc(x.rodzaj)}</td><td>${esc(x.plik)}</td><td class="liczba-kol">${x.wierszy}</td>
      <td class="liczba-kol">${x.nowych}</td><td class="liczba-kol szary">${x.pominietych}</td><td class="szary">${esc(x.uwagi || '')}</td></tr>`).join('');
    return `<h1>Historia importów</h1><div class="okruszki">Płatności / Dane</div>
      <p class="notka">Aplikacja czyta pliki z folderu Finanse/Raporty/Dane i niczego w nim nie zmienia. Baza powstaje od nowa przy każdym odświeżeniu, więc ten sam plik wczytany dwa razy nic nie dubluje. „Pominięte” to operacje, które były już w nowszym pliku.</p>
      <p><button id="odswiez">Wczytaj pliki na nowo</button> <span class="szary">Ostatnio: ${esc(STAN.meta.odbudowa ? new Date(STAN.meta.odbudowa).toLocaleString('pl-PL') : '')}, ${esc(STAN.meta.mac || '')}</span></p>
      <div class="tabela-ramka"><table><thead><tr><th>Źródło</th><th>Plik</th><th class="liczba-kol">Wierszy</th><th class="liczba-kol">Nowych</th><th class="liczba-kol">Pominiętych</th><th>Uwagi</th></tr></thead><tbody>${wiersze}</tbody></table></div>`;
  },

  async 'platnosci/wyniki-biura'() {
    const lista = await api('wyniki-biura');
    const wiersze = lista.map(x => `<tr title="Źródło: ${esc(x.plik)}, wiersz ${x.wiersz}"><td class="szary">${esc(x.okres)}</td><td>${esc(x.kod)}</td><td>${esc(x.opis)}</td>
      <td class="liczba-kol">${zl(x.wartosc, false)}</td><td class="liczba-kol szary">${x.wartosc_poprzednia != null ? zl(x.wartosc_poprzednia, false) : ''}</td></tr>`).join('');
    return `<h1>Wyniki z biura</h1><div class="okruszki">Płatności / Rachunek zysków i strat narastająco</div>
      <p class="notka">Punkt odniesienia do sprawdzania wyliczeń aplikacji, nie źródło liczenia.</p>
      <div class="tabela-ramka"><table><thead><tr><th>Okres</th><th>Kod</th><th>Pozycja</th><th class="liczba-kol">Bieżący okres</th><th class="liczba-kol">Poprzedni rok</th></tr></thead><tbody>${wiersze}</tbody></table></div>`;
  },
};

// ---------- Etap 2: należności i dopasowania ----------
const PRZEDZIALY = ['przed terminem', '1–30 dni', '31–60 dni', '61–90 dni', 'ponad 90 dni'];

function kafleNaleznosci(n) {
  if (!n) return '';
  const p = n.przedzialy;
  return `<div class="kafle">
      <div class="kafel"><div class="tytul">Należności razem</div><div class="wartosc">${zl(n.razem)}</div>
        <div class="dop">faktury nieopłacone w banku, stan na ${dataPl(n.dzien_stanu)}</div></div>
      <a class="kafel klik" href="#/platnosci/naleznosci?po_terminie=1"><div class="tytul">Po terminie</div><div class="wartosc minus">${zl(n.po_terminie)}</div>
        <div class="dop">${n.nabywcy_po_terminie.length} nabywców, najstarsza ${Math.max(0, ...n.nabywcy_po_terminie.map(x => x.najstarsza))} dni</div></a>
      <a class="kafel klik" href="#/platnosci/do-polaczenia"><div class="tytul">Wpłaty do połączenia</div><div class="wartosc">${n.do_polaczenia}</div>
        <div class="dop">wpływy, których aplikacja nie umie przypisać</div></a>
      <a class="kafel klik" href="#/platnosci/do-weryfikacji"><div class="tytul">Do weryfikacji</div><div class="wartosc">${n.do_weryfikacji}</div>
        <div class="dop">dopasowania do potwierdzenia i rozjazdy z Fakturownią</div></a>
    </div>
    <div class="wiekowanie">${PRZEDZIALY.map(x => `<a href="#/platnosci/naleznosci?przedzial=${encodeURIComponent(x)}" class="${x === 'przed terminem' ? '' : 'po'}">
      <span>${x}</span><b>${zl(p[x][1], false)}</b><small>${p[x][0]} faktur</small></a>`).join('')}</div>`;
}

async function kartaWplaty(id) {
  const d = await api('wplata', { id });
  const o = d.operacja;
  const k = $('#karta');
  const dop = d.dopasowania.map(x => `<li><b>${esc(x.numer)}</b> ${zl(x.kwota)} <span class="szary">${esc(x.metoda)}${x.pewnosc === 'prawdopodobne' ? ', do potwierdzenia' : ''}</span></li>`).join('');
  const otwarte = d.otwarte.map(f => `<label class="wybor"><input type="checkbox" value="${esc(f.numer)}"${f.rowna_kwota && f.podobny ? ' checked' : ''}>
      <span><b>${esc(f.numer)}</b> ${esc(f.nabywca)}<br><span class="szary">wystawiona ${dataPl(f.data_wystawienia)}, zostało ${zl(f.pozostalo)}${f.rowna_kwota ? ', ta sama kwota' : ''}</span></span></label>`).join('');
  k.innerHTML = `<button class="zamknij" aria-label="Zamknij">×</button><h2>${esc(o.kontrahent || o.opis)}</h2>
    <dl><dt>Kwota</dt><dd class="plus">${zl(o.kwota)}</dd><dt>Data</dt><dd>${dataPl(o.data_ksiegowania)}</dd><dt>Tytuł</dt><dd>${esc(o.tytul)}</dd>
      <dt>Stan</dt><dd>${esc(STAN_WPLATY[o.stan] || o.stan)}${o.uwaga ? `\n${esc(o.uwaga)}` : ''}${o.podpowiedz ? `\n${esc(o.podpowiedz)}` : ''}</dd>
      ${o.nadplata ? `<dt>Nadpłata</dt><dd class="minus">${zl(o.nadplata)}</dd>` : ''}</dl>
    ${dop ? `<h3>Połączona z</h3><ul class="lista">${dop}</ul>` : ''}
    <div class="akcje">
      ${d.dopasowania.some(x => x.pewnosc === 'prawdopodobne') ? '<button class="glowny" data-a="zatwierdz">Potwierdź dopasowanie</button><button data-a="odrzuc">Odrzuć</button>' : ''}
      ${o.wpis ? '<button data-a="cofnij">Cofnij moją decyzję</button>' : ''}
    </div>
    <h3>${dop ? 'Połącz inaczej' : 'Połącz z fakturą'}</h3>
    <div class="wybory">${otwarte || '<p class="szary">Brak otwartych faktur.</p>'}</div>
    <div class="akcje"><button class="glowny" data-a="polacz">Połącz z zaznaczonymi</button></div>
    <h3>Albo: wpłata nie dotyczy faktury</h3>
    <div class="akcje"><select id="powod">${['zwrot płatności kartą', 'zwrot nadpłaty od dostawcy', 'zwrot podatku', 'cashback, nagroda banku', 'zwrot kosztów (prywatne)', 'windykacja, komornik', 'inne'].map(x => `<option>${x}</option>`).join('')}</select>
      <button data-a="bez_faktury">Oznacz</button></div>
    <div class="zrodlo">Źródło: ${esc(o.plik)}, wiersz ${o.wiersz}</div>`;
  k.hidden = false;
  $('.zamknij', k).onclick = () => { k.hidden = true; };
  k.querySelectorAll('[data-a]').forEach(b => b.onclick = async () => {
    const a = b.dataset.a;
    const prawd = d.dopasowania.filter(x => x.pewnosc === 'prawdopodobne').map(x => x.numer);
    if (a === 'polacz') {
      const faktury = [...k.querySelectorAll('.wybory input:checked')].map(i => i.value);
      if (!faktury.length) return komunikat('Zaznacz co najmniej jedną fakturę.', true);
      return zmiana('polacz', { operacja: o.klucz, faktury });
    }
    if (a === 'bez_faktury') return zmiana('bez_faktury', { operacja: o.klucz, powod: $('#powod').value });
    if (a === 'cofnij') return zmiana('cofnij', { wpis: o.wpis });
    for (const n of prawd) if (!(await zmianaCicha(a, { operacja: o.klucz, faktura: n }))) return;
    await zmiana(a, { operacja: o.klucz, faktura: prawd[prawd.length - 1] });
  });
}

// Kilka wpisów z rzędu (np. potwierdzenie dopasowania do 3 faktur): wszystkie poza ostatnim bez przerysowania.
async function zmianaCicha(typ, dane) {
  const r = await fetch('/api/zmiana', { method: 'POST', headers: { 'X-Finanse': '1', 'Content-Type': 'application/json' }, body: JSON.stringify({ typ, dane }) });
  if (!r.ok) { komunikat((await r.json().catch(() => ({}))).blad || 'Nie udało się zapisać.', true); return false; }
  return true;
}

Object.assign(WIDOKI, {
  async 'platnosci/do-polaczenia'(p) {
    const stan = p.stan || 'nieznana';
    const w = await api('wplaty', { ...p, stan });
    const l = w.liczniki;
    const kol = [
      { naglowek: 'Dzień płatności', wartosc: x => dataPl(x.data_ksiegowania) },
      { naglowek: 'Płatnik', wartosc: x => x.kontrahent },
      { naglowek: 'Tytuł', wartosc: x => x.tytul || x.opis },
      { id: 'kwota', naglowek: 'Kwota PLN', liczba: true, wartosc: x => zl(x.kwota, false), klasa: () => 'plus' },
      { naglowek: stan === 'dopasowana' ? 'Faktury' : 'Podpowiedź', wartosc: x => stan === 'dopasowana' ? x.faktury : (x.uwaga || x.podpowiedz), klasa: () => 'szary' },
    ];
    return `<h1>Wpłaty do połączenia</h1><div class="okruszki">Płatności / Płatności oczekujące</div>
      <div class="zakladki" role="tablist">${[['nieznana', 'Do połączenia'], ['sprzed_eksportu', 'Za faktury sprzed eksportu'], ['bez_faktury', 'Nie dotyczą faktury'], ['dopasowana', 'Połączone']]
        .map(([v, n]) => `<button role="tab" aria-selected="${stan === v}" data-stan="${v}">${n} <span class="szary">${l[v] || 0}</span></button>`).join('')}</div>
      <p class="notka">Wpływy z banku bez ruchu wewnętrznego. Kliknij wpłatę, żeby połączyć ją z fakturą albo oznaczyć, że faktury nie dotyczy (zwrot, cashback). Decyzja zapisuje się w pliku zmian i przeżywa każde odświeżenie danych.</p>
      ${tabela({ kolumny: kol, dane: w.wiersze, poczatek: (w.strona - 1) * w.ile + 1, stopkaSum: { kwota: zl(w.suma, false) }, onWiersz: x => kartaWplaty(x.id) })}
      ${stopka(w, p)}`;
  },

  async 'platnosci/do-weryfikacji'() {
    const lista = await api('do-weryfikacji');
    if (!lista.length) return '<h1>Do weryfikacji</h1><div class="okruszki">Płatności / Płatności oczekujące</div><div class="pusto">Nic do sprawdzenia.</div>';
    const grupy = {};
    lista.forEach(x => (grupy[x.tytul] ||= []).push(x));
    const sekcje = Object.entries(grupy).map(([tytul, xs]) => `<h2 class="sekcja">${esc(tytul)} <span class="szary">${xs.length}</span></h2>
      <div class="tabela-ramka niska"><table><thead><tr><th>Data</th><th>Kontrahent</th><th>Faktury</th><th class="liczba-kol">Kwota PLN</th><th>Szczegóły</th><th></th></tr></thead><tbody>
      ${xs.map((x, i) => `<tr data-g="${esc(tytul)}" data-i="${i}"><td>${dataPl(x.data)}</td><td>${esc(x.kontrahent)}</td><td>${esc(x.faktury || '')}</td>
        <td class="liczba-kol">${zl(x.kwota, false)}</td><td class="szary">${esc(x.opis.replace(/\d+ gr/, m => zl(parseInt(m)) ))}</td>
        <td class="akcje-wiersz">${x.rodzaj === 'prawdopodobne' ? '<button data-a="zatwierdz">Potwierdź</button><button data-a="odrzuc">Odrzuć</button>' : x.rodzaj === 'fakturownia_oplacona' ? '<button data-a="poza_bankiem">Opłacona poza bankiem</button>' : ''}</td></tr>`).join('')}
      </tbody></table></div>`).join('');
    setTimeout(() => document.querySelectorAll('tr[data-g]').forEach(tr => {
      const x = grupy[tr.dataset.g][tr.dataset.i];
      tr.onclick = async e => {
        const a = e.target.dataset?.a;
        if (!a) return x.operacja_id ? kartaWplaty(x.operacja_id) : (location.hash = `#/platnosci/faktury?q=${encodeURIComponent(x.numer)}`);
        e.stopPropagation();
        if (a === 'poza_bankiem') {
          return zmiana('poza_bankiem', { faktura: x.numer, powod: 'opłacona poza bankiem (oznaczone na ekranie Do weryfikacji)' });
        }
        const numery = x.faktury.split(', ');
        for (const n of numery.slice(0, -1)) if (!(await zmianaCicha(a, { operacja: x.klucz, faktura: n }))) return;
        zmiana(a, { operacja: x.klucz, faktura: numery[numery.length - 1] });
      };
    }));
    return `<h1>Do weryfikacji</h1><div class="okruszki">Płatności / Płatności oczekujące</div>
      <p class="notka">Rzeczy, których aplikacja nie rozstrzyga sama. „Potwierdź” i „Odrzuć” zapisują decyzję; kliknięcie wiersza otwiera wpłatę albo fakturę.</p>${sekcje}`;
  },

  async 'platnosci/naleznosci'(p) {
    const [w, n] = [await api('naleznosci', p), STAN.naleznosci];
    const kol = [
      { naglowek: 'W banku', html: chipBank },
      { naglowek: 'Numer', wartosc: x => x.numer },
      { naglowek: 'Nabywca', wartosc: x => x.nabywca },
      { naglowek: 'Termin', wartosc: x => dataPl(x.termin) },
      { naglowek: 'Brutto PLN', liczba: true, wartosc: x => zl(x.naleznosc, false), klasa: () => 'szary' },
      { id: 'pozostalo', naglowek: 'Do zapłaty PLN', liczba: true, wartosc: x => zl(x.pozostalo, false) },
      { naglowek: 'Fakturownia', wartosc: x => x.status, klasa: x => x.status === 'Opłacona' ? 'minus' : 'szary' },
    ];
    const tytul = p.po_terminie ? 'Po terminie płatności' : p.przedzial ? `Nieopłacone: ${p.przedzial}` : 'Nadal nieopłacone';
    const nabywcy = p.po_terminie && n ? `<div class="tabela-ramka niska"><table><thead><tr><th>Nabywca</th><th class="liczba-kol">Faktur</th><th class="liczba-kol">Do zapłaty PLN</th><th class="liczba-kol">Najstarsza</th></tr></thead><tbody>
      ${n.nabywcy_po_terminie.map(x => `<tr data-q="${esc(x.nabywca)}"><td>${esc(x.nabywca)}</td><td class="liczba-kol">${x.faktur}</td><td class="liczba-kol minus">${zl(x.kwota, false)}</td><td class="liczba-kol">${x.najstarsza} dni</td></tr>`).join('')}
      </tbody></table></div><h2 class="sekcja">Faktury</h2>` : '';
    setTimeout(() => document.querySelectorAll('tr[data-q]').forEach(tr => tr.onclick = () => ustawParametry({ q: tr.dataset.q, strona: 1 })));
    return `<h1>${tytul}</h1><div class="okruszki">Płatności / Należności, stan na ${dataPl(w.dzien_stanu)} (ostatni dzień w eksporcie z ING)</div>
      ${kafleNaleznosci(n)}
      <div class="filtry">${filtr('przedzial', 'Wiekowanie', [['', 'Wszystkie'], ...PRZEDZIALY.map(x => [x, x])], p.przedzial)}
        ${filtr('po_terminie', 'Termin', [['', 'Wszystkie'], ['1', 'Tylko po terminie']], p.po_terminie)}</div>
      ${nabywcy}
      ${tabela({ kolumny: kol, dane: w.wiersze, poczatek: (w.strona - 1) * w.ile + 1, stopkaSum: { pozostalo: zl(w.pozostalo, false) },
        onWiersz: x => pokazKarte(x.numer, [['Nabywca', x.nabywca], ['NIP', x.nip], ['Wystawiona', dataPl(x.data_wystawienia)], ['Termin', dataPl(x.termin)],
          ['Brutto', zl(x.brutto)], ['Korekty', x.korekty ? zl(x.korekty) : ''], ['Zapłacono w banku', zl(x.zaplacono)], ['Do zapłaty', zl(x.pozostalo)],
          ['Po terminie', x.dni_po_terminie ? `${x.dni_po_terminie} dni` : 'nie'], ['Status w Fakturowni', x.status], ['Numer KSeF', x.ksef]],
          `${x.plik}, wiersz ${x.wiersz}`) })}
      ${stopka(w, p)}`;
  },
});

// ---------- Etap 3: klienci, wydatki, reguły ----------
const RODZAJE = { przenoszony: 'koszt klienta', staly: 'koszt stały', praca: 'koszty pracy', podatki: 'podatki', vat: 'VAT',
  dywidenda: 'podział zysku', zwrot: 'zwrot dla klienta', nieprzypisany: 'nieprzypisany' };
const chipRodzaj = r => `<span class="chip ${r === 'nieprzypisany' ? 'ostrzezenie' : r === 'przenoszony' ? 'akcent' : 'neutral'}">${esc(RODZAJE[r] || r)}</span>`;
const chipDok = d => d === 'dokument' ? '<span class="chip plus">jest</span>' : d === 'bez dokumentu' ? '<span class="chip ostrzezenie">brak</span>'
  : d === 'po okresie rejestru' ? '<span class="chip neutral">rejestr jeszcze nie obejmuje</span>' : '<span class="szary">nie wymaga</span>';
const pole = (id, etykieta, html) => `<label class="pole"><span>${etykieta}</span>${html}</label>`;
const listaKlientow = klienci => `<datalist id="lista-klientow">${klienci.map(k => `<option value="${esc(k)}">`).join('')}</datalist>`;

function kartaFaktury(x, pola) {
  pokazKarte(x.numer, pola, `${x.plik}, wiersz ${x.wiersz}`);
  const k = $('#karta');
  const blok = document.createElement('div');
  blok.innerHTML = `<h3>Klient tej faktury</h3><p class="szary">Nabywca ${esc(x.nabywca)}${x.nip ? ` (NIP ${esc(x.nip)})` : ''}. Gdy płaci za kilku klientów, zmień tylko tę fakturę.</p>
    <div class="akcje"><input id="nowy-klient" list="lista-klientow" value="${esc(x.klient)}"></div>
    <div class="akcje"><button class="glowny" id="zapisz-klienta">Wszystkie faktury nabywcy</button><button id="zapisz-fakture">Tylko ta faktura</button></div>`;
  k.insertBefore(blok, $('.zrodlo', k));
  api('wydatki', { ile: 1 }).then(w => blok.insertAdjacentHTML('beforeend', listaKlientow(w.klienci)));
  $('#zapisz-klienta').onclick = () => zmiana('klient_nip', { nabywca: x.nabywca_klucz, klient: $('#nowy-klient').value });
  $('#zapisz-fakture').onclick = () => zmiana('klient_faktura', { faktura: x.numer, klient: $('#nowy-klient').value });
}

function kartaWydatku(x, klienci) {
  const k = $('#karta');
  k.innerHTML = `<button class="zamknij" aria-label="Zamknij">×</button><h2>${esc(x.kontrahent || x.opis)}</h2>
    <dl><dt>Kwota</dt><dd class="minus">${zl(x.kwota)}</dd><dt>Data</dt><dd>${dataPl(x.data_ksiegowania)}</dd><dt>Tytuł</dt><dd>${esc(x.tytul || x.opis)}</dd>
      <dt>Rodzaj</dt><dd>${esc(RODZAJE[x.rodzaj])}${x.klient ? `, ${esc(x.klient)}` : ''}</dd><dt>Skąd</dt><dd>${esc(x.zrodlo || 'brak reguły')}</dd>
      <dt>Dokument</dt><dd>${esc(x.dokumenty || x.dokument)}${x.netto_dok != null ? `\nnetto z dokumentu ${zl(x.netto_dok)}` : ''}</dd></dl>
    <h3>Przypisz</h3>
    <div class="formularz">${pole('', 'Rodzaj', `<select id="rodzaj">${Object.entries(RODZAJE).map(([v, n]) => `<option value="${v}"${v === x.rodzaj ? ' selected' : ''}>${n}</option>`).join('')}</select>`)}
      ${pole('', 'Klient (dla kosztu klienta)', `<input id="klient" list="lista-klientow" value="${esc(x.klient || '')}">`)}</div>
    ${listaKlientow(klienci)}
    <div class="akcje"><button class="glowny" data-a="regula">Wszystkie płatności do tego kontrahenta</button><button data-a="jedna">Tylko ta płatność</button>
      ${x.wpis ? '<button data-a="cofnij">Cofnij moją regułę</button>' : ''}</div>
    <p class="szary">Kontrahent w regule: „${esc(x.kontrahent_klucz)}”. Reguła obejmie też przyszłe płatności.</p>
    <div class="zrodlo">Źródło: ${esc(x.plik)}, wiersz ${x.wiersz}</div>`;
  k.hidden = false;
  $('.zamknij', k).onclick = () => { k.hidden = true; };
  k.querySelectorAll('[data-a]').forEach(b => b.onclick = () => {
    const rodzaj = $('#rodzaj').value, klient = rodzaj === 'przenoszony' ? $('#klient').value.trim() : '';
    if (b.dataset.a === 'cofnij') return zmiana('cofnij', { wpis: x.wpis });
    if (b.dataset.a === 'regula') return zmiana('koszt_regula', { kontrahent: x.kontrahent_klucz, rodzaj, klient });
    return zmiana('koszt_operacja', { operacja: x.klucz, rodzaj, klient });
  });
}

const procent = x => x == null ? '' : `${String(x).replace('.', ',')}%`;

Object.assign(WIDOKI, {
  async budzet(p) {
    const d = await api('klienci', p);
    const kol = [
      { naglowek: 'Klient', wartosc: x => x.klient },
      { naglowek: 'Faktur', liczba: true, wartosc: x => x.faktur },
      { id: 'przychod', naglowek: 'Przychód netto', liczba: true, wartosc: x => zl(x.przychod, false) },
      { naglowek: 'Wpłacono', liczba: true, wartosc: x => zl(x.wplaty, false), klasa: () => 'szary' },
      { naglowek: 'Należność', liczba: true, wartosc: x => x.naleznosc ? zl(x.naleznosc, false) : '', klasa: x => x.po_terminie ? 'minus' : '' },
      { id: 'koszty', naglowek: 'Koszty klienta', liczba: true, wartosc: x => x.koszty ? zl(-x.koszty, false) : '', klasa: () => 'minus' },
      { id: 'marza', naglowek: 'Marża wstępna', liczba: true, wartosc: x => zl(x.marza, false) },
      { naglowek: '%', liczba: true, wartosc: x => procent(x.marza_proc), klasa: x => x.marza_proc != null && x.marza_proc < 30 ? 'minus' : '' },
    ];
    const s = k => d.klienci.reduce((a, x) => a + (x[k] || 0), 0);
    return `<h1>Klienci</h1><div class="okruszki">Budżet / Foldery klientów</div>
      <div class="filtry">${filtr('rok', 'Rok', [['', 'Wszystko'], ...d.lata.map(r => [r, r])], d.rok || '')}</div>
      <p class="notka">Przychód z faktur (netto, wg daty sprzedaży). Koszty klienta to wydatki z banku przypisane do klienta: netto z dokumentu z rejestru biura, a bez dokumentu kwota z banku. Marża wstępna nie zawiera kosztów pracy zespołu, to etap 4. Czerwony procent: poniżej progu 30%.${d.przenoszone_bez_klienta.ile ? ` Koszty klientów bez wskazanego klienta: ${d.przenoszone_bez_klienta.ile} płatności, ${zl(d.przenoszone_bez_klienta.kwota)}.` : ''}</p>
      ${tabela({ kolumny: kol, dane: d.klienci, poczatek: 1, stopkaSum: { przychod: zl(s('przychod'), false), koszty: zl(-s('koszty'), false), marza: zl(s('marza'), false) },
        onWiersz: x => { location.hash = `#/budzet/klient?nazwa=${encodeURIComponent(x.klient)}${d.rok ? '&rok=' + d.rok : ''}`; } })}`;
  },

  async 'budzet/klient'(p) {
    const d = await api('klient', p);
    const max = Math.max(1, ...d.miesiace.map(m => Math.max(m.przychod, m.koszty)));
    const wykres = d.miesiace.map(m => `<div class="slupek" title="${m.miesiac}: przychód ${zl(m.przychod)}, koszty ${zl(m.koszty)}">
      <div class="paski"><i class="p" data-h="${100 * m.przychod / max}"></i><i class="k" data-h="${100 * m.koszty / max}"></i></div><small>${m.miesiac.slice(5)}.${m.miesiac.slice(2, 4)}</small></div>`).join('');
    const tf = d.faktury.map(f => `<tr data-q="${esc(f.numer)}"><td>${esc(f.numer)}</td><td>${dataPl(f.data_sprzedazy || f.data_wystawienia)}</td><td class="szary">${esc(f.nabywca)}</td>
      <td class="liczba-kol">${zl(f.netto, false)}</td><td>${chipBank({ stan_bank: f.stan, dni_po_terminie: f.dni_po_terminie })}</td></tr>`).join('');
    const tk = d.koszty.map(x => `<tr data-op="${x.id}"><td>${dataPl(x.data_ksiegowania)}</td><td>${esc(x.kontrahent)}</td><td class="szary">${esc(x.tytul)}</td>
      <td class="liczba-kol minus">${zl(-(x.koszt || 0), false)}</td><td>${chipDok(x.dokument)}</td></tr>`).join('');
    setTimeout(() => {
      // wysokość przez CSSOM: CSP strony blokuje atrybuty style w HTML
      document.querySelectorAll('.paski i[data-h]').forEach(i => { i.style.height = `${i.dataset.h}%`; });
      document.querySelectorAll('tr[data-q]').forEach(tr => tr.onclick = () => { location.hash = `#/platnosci/faktury?q=${encodeURIComponent(tr.dataset.q)}`; });
      document.querySelectorAll('tr[data-op]').forEach(tr => tr.onclick = () => { location.hash = `#/budzet/wydatki?klient=${encodeURIComponent(d.klient)}&rodzaj=przenoszony`; });
    });
    return `<h1>${esc(d.klient)}</h1><div class="okruszki"><a href="#/budzet">Budżet</a> / Klient${d.rok ? ' / ' + d.rok : ''}</div>
      <div class="wykres-klienta">${wykres || '<span class="szary">Brak danych.</span>'}</div>
      <div class="legenda"><i class="p"></i> przychód netto <i class="k"></i> koszty klienta</div>
      <h2 class="sekcja">Faktury <span class="szary">${d.faktury.length}</span></h2>
      <div class="tabela-ramka niska"><table><thead><tr><th>Numer</th><th>Sprzedaż</th><th>Nabywca</th><th class="liczba-kol">Netto PLN</th><th>W banku</th></tr></thead><tbody>${tf}</tbody></table></div>
      <h2 class="sekcja">Koszty klienta <span class="szary">${d.koszty.length}</span></h2>
      ${tk ? `<div class="tabela-ramka niska"><table><thead><tr><th>Data</th><th>Kontrahent</th><th>Tytuł</th><th class="liczba-kol">Koszt PLN</th><th>Dokument</th></tr></thead><tbody>${tk}</tbody></table></div>` : '<p class="szary">Brak przypisanych kosztów.</p>'}`;
  },

  async 'budzet/wydatki'(p) {
    const w = await api('wydatki', p);
    const kol = [
      { naglowek: 'Dzień płatności', wartosc: x => dataPl(x.data_ksiegowania) },
      { naglowek: 'Kontrahent', wartosc: x => x.kontrahent || x.opis },
      { naglowek: 'Tytuł', wartosc: x => x.tytul, klasa: () => 'szary' },
      { id: 'kwota', naglowek: 'Kwota PLN', liczba: true, wartosc: x => zl(x.kwota, false), klasa: () => 'minus' },
      { naglowek: 'Rodzaj', html: x => chipRodzaj(x.rodzaj) },
      { naglowek: 'Klient', wartosc: x => x.klient },
      { naglowek: 'Skąd', wartosc: x => x.zrodlo, klasa: () => 'szary' },
      { naglowek: 'Dokument', html: x => chipDok(x.dokument) },
    ];
    const pods = w.podsumowanie.map(x => `<a class="${p.rodzaj === x.rodzaj ? 'wybrany' : ''}" href="#/budzet/wydatki?rodzaj=${x.rodzaj}"><span>${esc(RODZAJE[x.rodzaj])}</span><b>${zl(-x.kwota, false)}</b><small>${x.ile} płatności</small></a>`).join('');
    return `<h1>Wydatki</h1><div class="okruszki">Budżet / Wydatki z banku (bez ruchu wewnętrznego)</div>
      <div class="wiekowanie rodzaje">${pods}</div>
      <div class="filtry">
        ${filtr('rodzaj', 'Rodzaj', [['', 'Wszystkie'], ...Object.entries(RODZAJE)], p.rodzaj)}
        ${filtr('klient', 'Klient', [['', 'Wszyscy'], ['-', 'bez klienta'], ...w.klienci.map(k => [k, k])], p.klient)}
        ${filtr('zrodlo', 'Skąd przypisanie', [['', 'Wszystkie'], ['mat', 'Twoje reguły'], ['bs', 'Budget Studio'], ['brak', 'Brak']], p.zrodlo)}
        ${filtr('dokument', 'Dokument w rejestrze', [['', 'Wszystkie'], ['dokument', 'Jest'], ['bez dokumentu', 'Brak'], ['po okresie rejestru', 'Rejestr jeszcze nie obejmuje'], ['nie wymaga', 'Nie wymaga']], p.dokument)}
        ${filtrData('od', 'Od', p.od)}${filtrData('do', 'Do', p.do)}
      </div>
      ${tabela({ kolumny: kol, dane: w.wiersze, poczatek: (w.strona - 1) * w.ile + 1, stopkaSum: { kwota: zl(w.suma, false) }, onWiersz: x => kartaWydatku(x, w.klienci) })}
      ${stopka(w, p)}`;
  },

  async 'budzet/reguly'() {
    const lista = await api('reguly');
    const nazwy = { klient_nip: 'Nabywca należy do klienta', klient_faktura: 'Faktura należy do klienta', koszt_regula: 'Kontrahent: rodzaj kosztu', koszt_operacja: 'Jedna płatność' };
    const wiersze = lista.map((x, i) => `<tr><td>${esc(nazwy[x.typ])}</td><td>${esc(x.klucz)}</td><td>${esc(x.wartosc)}</td>
      <td class="akcje-wiersz"><button data-i="${i}">Cofnij</button></td></tr>`).join('');
    setTimeout(() => document.querySelectorAll('button[data-i]').forEach(b => b.onclick = () => zmiana('cofnij', { wpis: lista[b.dataset.i].wpis })));
    return `<h1>Reguły przypisań</h1><div class="okruszki">Budżet / Ustawienia</div>
      <p class="notka">Twoje decyzje o klientach i rodzajach kosztów. Wygrywają z podpowiedziami z Budget Studio. Zapisane w pliku zmian tego Maca, drugi Mac widzi je po synchronizacji iCloud.</p>
      ${lista.length ? `<div class="tabela-ramka niska"><table><thead><tr><th>Rodzaj reguły</th><th>Kogo dotyczy</th><th>Przypisanie</th><th></th></tr></thead><tbody>${wiersze}</tbody></table></div>` : '<div class="pusto">Brak reguł. Dodasz je z karty wydatku albo faktury.</div>'}`;
  },
});

// ---------- Etap 4: rentowność ----------
const MIES_KROTKO = ['sty', 'lut', 'mar', 'kwi', 'maj', 'cze', 'lip', 'sie', 'wrz', 'paź', 'lis', 'gru'];
const mies = m => `${MIES_KROTKO[+m.slice(5, 7) - 1]} ${m.slice(2, 4)}`;
const tys = gr => gr ? zl(gr, false).replace(/,\d\d$/, '') : '';

function tabelaMiesiecy(miesiace, wiersze, niepelne = []) {
  const th = miesiace.map(m => `<th class="liczba-kol${niepelne.includes(m) ? ' niepelny' : ''}" title="${niepelne.includes(m) ? 'miesiąc niepełny' : ''}">${mies(m)}</th>`).join('');
  const tr = wiersze.map(w => `<tr class="${w.typ || ''}"${w.link ? ` data-link="${esc(w.link)}"` : ''}><td>${esc(w.nazwa)}</td>${miesiace.map(m => {
    const v = w.miesiace[m] || 0;
    return `<td class="liczba-kol${v < 0 ? ' minus' : ''}${niepelne.includes(m) ? ' niepelny' : ''}">${tys(v)}</td>`;
  }).join('')}<td class="liczba-kol razem${w.razem < 0 ? ' minus' : ''}">${tys(w.razem)}</td>${w.dodatkowe || ''}</tr>`).join('');
  setTimeout(() => document.querySelectorAll('tr[data-link]').forEach(x => x.onclick = () => { location.hash = x.dataset.link; }));
  return { th, tr };
}

function filtrRoku(d) {
  return `<div class="filtry">${filtr('rok', 'Rok', d.lata ? d.lata.map(r => [r, r]) : [[d.rok, d.rok]], d.rok)}</div>`;
}

Object.assign(WIDOKI, {
  async rentownosc(p) {
    const d = await api('wynik', p);
    const { th, tr } = tabelaMiesiecy(d.miesiace, d.wiersze.map(w => ({ ...w,
      link: { przenoszony: '#/rentownosc/koszty?rodzaj=przenoszony', praca: '#/rentownosc/koszty?rodzaj=praca', staly: '#/rentownosc/koszty?rodzaj=staly',
        nieprzypisany: '#/budzet/wydatki?rodzaj=nieprzypisany', obrot: '#/rentownosc/klienci' }[w.klucz] })), d.niepelne);
    const c = d.cele, czesc = c.czesc_roku;
    const pasek = (tytul, wart, cel) => cel ? `<div class="kafel"><div class="tytul">${tytul}</div><div class="wartosc">${zl(wart)}</div>
      <div class="pasek-celu"><i data-w="${Math.min(100, 100 * wart / cel)}"></i><b data-w="${100 * czesc}"></b></div>
      <div class="dop">${Math.round(100 * wart / cel)}% celu rocznego ${zl(cel)}; po ${Math.round(100 * czesc)}% roku powinno być ${zl(Math.round(cel * czesc))}</div></div>` : '';
    const b = d.porownanie_z_biurem;
    const porown = b ? `<h2 class="sekcja">Kontrola z księgami biura (narastająco do ${mies(b.okres)})</h2>
      <div class="tabela-ramka niska"><table><thead><tr><th></th><th class="liczba-kol">Biuro (RZiS)</th><th class="liczba-kol">Aplikacja</th><th class="liczba-kol">Różnica</th></tr></thead><tbody>
      <tr><td>Przychody netto ze sprzedaży</td><td class="liczba-kol">${zl(b.biuro.A, false)}</td><td class="liczba-kol">${zl(b.aplikacja_obrot, false)}</td><td class="liczba-kol">${zl(b.aplikacja_obrot - b.biuro.A, false)}</td></tr>
      <tr><td>Zysk ze sprzedaży (biuro) kontra wynik zarządczy</td><td class="liczba-kol">${zl(b.biuro.C, false)}</td><td class="liczba-kol">${zl(b.aplikacja_wynik, false)}</td><td class="liczba-kol">${zl(b.aplikacja_wynik - b.biuro.C, false)}</td></tr>
      ${b.biuro.D ? `<tr class="poza"><td>Pozostałe przychody operacyjne w księgach (np. dotacja), poza wynikiem aplikacji</td><td class="liczba-kol">${zl(b.biuro.D, false)}</td><td></td><td></td></tr>` : ''}
      </tbody></table></div><p class="notka">Wynik aplikacji liczy koszty z banku i rejestru, księgi biura memoriałowo z rozliczeniami okresowymi, więc różnica kilku tysięcy jest normalna. Duża różnica to sygnał do sprawdzenia przypisań.</p>` : '';
    setTimeout(() => document.querySelectorAll('.pasek-celu [data-w]').forEach(x => { x.style[x.tagName === 'I' ? 'width' : 'left'] = `${x.dataset.w}%`; }));
    return `<h1>Wynik zarządczy</h1><div class="okruszki">Rentowność / ${d.rok}, stan na ${dataPl(d.dzien_stanu)}</div>
      ${filtrRoku(d)}
      <div class="kafle">${pasek('Obrót netto od początku roku', d.obrot, c.obrot)}${pasek('Wynik zarządczy od początku roku', d.wynik, c.zysk)}
        <div class="kafel"><div class="tytul">Marża wyniku</div><div class="wartosc">${procent(d.marza_proc)}</div><div class="dop">wynik zarządczy do obrotu netto</div></div></div>
      <div class="tabela-ramka niska"><table class="miesiace"><thead><tr><th></th>${th}<th class="liczba-kol">Razem</th></tr></thead><tbody>${tr}</tbody></table></div>
      <p class="notka">Kwoty w złotych netto. Przychód wg daty sprzedaży, koszty z dokumentem wg daty dokumentu, koszty pracy wg miesiąca, którego dotyczą. Koszt bez dokumentu w rejestrze liczony kwotą z banku (z VAT), więc lekko zawyżony. Szare kolumny to miesiące niepełne: faktury za bieżący miesiąc i ZUS, PIT-4 oraz VAT za poprzedni jeszcze nie przyszły. Kliknij wiersz, żeby zobaczyć szczegóły.</p>
      ${porown}`;
  },

  async 'rentownosc/klienci'(p) {
    const d = await api('obroty-klientow', p);
    const { th, tr } = tabelaMiesiecy(d.miesiace, d.klienci.map(k => ({ nazwa: k.klient, miesiace: k.miesiace, razem: k.obrot,
      link: `#/budzet/klient?nazwa=${encodeURIComponent(k.klient)}&rok=${d.rok}`,
      dodatkowe: `<td class="liczba-kol szary">${procent(k.udzial)}</td><td class="liczba-kol minus">${tys(-k.koszty)}</td><td class="liczba-kol">${tys(k.pna)}</td>
        <td class="liczba-kol${k.marza_proc != null && k.marza_proc < 30 ? ' minus' : ''}">${procent(k.marza_proc)}</td>` })));
    return `<h1>Obroty wg klientów</h1><div class="okruszki">Rentowność / ${d.rok}</div>${filtrRoku({ rok: d.rok, lata: [d.rok] })}
      <div class="tabela-ramka niska"><table class="miesiace"><thead><tr><th>Klient</th>${th}<th class="liczba-kol">Obrót</th><th class="liczba-kol">Udział</th>
        <th class="liczba-kol">Koszty klienta</th><th class="liczba-kol">Po kosztach</th><th class="liczba-kol">Marża</th></tr></thead><tbody>${tr}</tbody></table></div>
      <p class="notka">Obrót netto z faktur wg daty sprzedaży. Marża przed kosztami pracy zespołu; czerwona poniżej progu 30%. Podział czasu zespołu na klientów to dalszy krok, po MVP.</p>`;
  },

  async 'rentownosc/koszty'(p) {
    const d = await api('koszty-kategorii', p);
    const { th, tr } = tabelaMiesiecy(d.miesiace, d.pozycje.map(x => ({ nazwa: d.rodzaj ? x.nazwa : (RODZAJE[x.klucz] || x.klucz),
      miesiace: x.miesiace, razem: x.razem, link: d.rodzaj ? `#/budzet/wydatki?q=${encodeURIComponent(x.nazwa.split(' ')[0])}` : `#/rentownosc/koszty?rodzaj=${x.klucz}&rok=${d.rok}` })));
    return `<h1>Koszty wg kategorii</h1><div class="okruszki"><a href="#/rentownosc/koszty">Rentowność / Koszty</a>${d.rodzaj ? ' / ' + esc(RODZAJE[d.rodzaj]) : ''} / ${d.rok}</div>
      <div class="filtry">${filtr('rodzaj', 'Rodzaj', [['', 'Wszystkie rodzaje'], ...Object.entries(RODZAJE)], d.rodzaj || '')}</div>
      <div class="tabela-ramka niska"><table class="miesiace"><thead><tr><th>${d.rodzaj ? 'Kontrahent' : 'Rodzaj'}</th>${th}<th class="liczba-kol">Razem</th></tr></thead><tbody>${tr}</tbody></table></div>
      <p class="notka">Kwoty dodatnie to wydatki. Netto z dokumentu, gdy jest w rejestrze biura, inaczej kwota z banku.</p>`;
  },

  async 'rentownosc/vat'(p) {
    const d = await api('vat', p);
    const tr = d.miesiace.map(m => `<tr><td>${mies(m.miesiac)}</td><td class="liczba-kol">${zl(m.nalezny, false)}</td>
      <td class="liczba-kol">${m.rejestr ? zl(m.naliczony, false) : '<span class="szary">brak rejestru</span>'}</td>
      <td class="liczba-kol">${m.rejestr ? zl(m.do_zaplaty, false) : ''}</td><td class="liczba-kol">${zl(m.zaplacony, false)}</td>
      <td class="liczba-kol${m.rejestr && Math.abs(m.zaplacony - m.do_zaplaty) > 10000 ? ' minus' : ' szary'}">${m.rejestr ? zl(m.zaplacony - m.do_zaplaty, false) : ''}</td></tr>`).join('');
    return `<h1>Podatek VAT</h1><div class="okruszki">Rentowność / ${d.rok}</div>
      <div class="tabela-ramka niska"><table><thead><tr><th>Okres</th><th class="liczba-kol">Należny (faktury)</th><th class="liczba-kol">Naliczony (rejestr biura)</th>
        <th class="liczba-kol">Wychodzi do zapłaty</th><th class="liczba-kol">Zapłacono (bank)</th><th class="liczba-kol">Różnica</th></tr></thead><tbody>${tr}</tbody></table></div>
      <p class="notka">Szacunek kontrolny, nie deklaracja: należny z faktur wg daty sprzedaży, naliczony z rejestru krajowego biura (bez importu usług), zapłata przypisana do okresu z tytułu przelewu („26M07”). Czerwona różnica ponad 100 zł to temat do pytania biura. Rejestr biura kończy się ${dataPl(d.koniec_rejestru)}.</p>`;
  },
});

function wBudowie(sekcja) {
  const nazwa = MENU.find(m => m.id === sekcja)?.nazwa || sekcja;
  const etap = { cashflow: 5, eksport: 6 }[sekcja];
  return `<h1>${esc(nazwa)}</h1><div class="okruszki">W budowie</div><p class="notka">Ten ekran powstanie w etapie ${etap}. Układ będzie taki jak w Budget Studio.</p>`;
}

async function pokaz() {
  const t = trasa();
  const klucz = t.podstrona ? `${t.sekcja}/${t.podstrona}` : t.sekcja;
  zaznaczMenu(t.sekcja);
  $('#karta').hidden = true;
  const widok = $('#widok');
  try {
    widok.innerHTML = WIDOKI[klucz] ? await WIDOKI[klucz](t.parametry) : wBudowie(t.sekcja);
    podepnijFiltry();
    document.querySelectorAll('.zakladki [data-stan]').forEach(b => b.onclick = () => ustawParametry({ stan: b.dataset.stan, strona: 1, q: '' }));
    const o = $('#odswiez');
    if (o) o.onclick = odbuduj;
  } catch (e) {
    widok.innerHTML = `<div class="komunikat blad">${esc(e.message)}</div>`;
  }
}

window.addEventListener('hashchange', pokaz);
zbudujMenu();
sprawdzStan().then(pokaz).catch(e => komunikat(e.message, true));
setInterval(() => sprawdzStan().catch(() => {}), 60000);

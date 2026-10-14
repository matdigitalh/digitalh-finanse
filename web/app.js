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
    { nazwa: 'Do połączenia', etap: 2 },
    { nazwa: 'Do weryfikacji', etap: 2 },
    { grupa: 'Bank ING' },
    { nazwa: 'Wszystkie operacje', hash: '#/platnosci/bank' },
    { nazwa: 'Wpływy', hash: '#/platnosci/bank?kierunek=wplywy&wewnetrzne=bez' },
    { nazwa: 'Obciążenia', hash: '#/platnosci/bank?kierunek=obciazenia&wewnetrzne=bez' },
    { nazwa: 'Ruch wewnętrzny i VAT', hash: '#/platnosci/bank?wewnetrzne=tylko' },
    { grupa: 'Dokumenty' },
    { nazwa: 'Faktury sprzedażowe', hash: '#/platnosci/faktury' },
    { nazwa: 'Nadal nieopłacone', etap: 2 },
    { nazwa: 'Po terminie płatności', etap: 2 },
    { nazwa: 'Rejestr zakupów (biuro)', hash: '#/platnosci/zakupy' },
    { grupa: 'Dane' },
    { nazwa: 'Historia importów', hash: '#/platnosci/importy' },
    { nazwa: 'Wyniki z biura (RZiS)', hash: '#/platnosci/wyniki-biura' },
  ],
  budzet: [{ grupa: 'Arkusze budżetu' }, { nazwa: 'Foldery klientów i arkusze', etap: 3 }],
  cashflow: [{ grupa: 'Zapisane widoki' }, { nazwa: '2 tyg. w przód', etap: 5 }, { nazwa: '8 tyg. w przód', etap: 5 },
    { nazwa: '13 tyg. w przód', etap: 5 }, { nazwa: '6 mies. w przód', etap: 5 }],
  rentownosc: [{ grupa: 'Zapisane widoki' }, { nazwa: 'Wynik zarządczy', etap: 4 }, { nazwa: 'Obroty wg klientów', etap: 4 },
    { nazwa: 'Obroty wg kategorii', etap: 4 }, { nazwa: 'Podatek VAT', etap: 4 }],
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
    return `<a href="${p.hash}">${esc(p.nazwa)}</a>`;
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
      <p class="notka">Kafle z należnościami, płatnościami do zapłaty i wykres gotówki na 6 miesięcy pojawią się w kolejnych etapach, gdy aplikacja zacznie sama łączyć wpłaty z fakturami.</p>`;
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
        onWiersz: x => pokazKarte(x.kontrahent || x.opis, [
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
      { naglowek: 'Etap', html: x => x.status === 'Opłacona' ? '<span class="chip plus">opłacona</span>' : `<span class="chip neutral">${esc(x.status.toLowerCase())}</span>` },
      { naglowek: 'Numer', wartosc: x => x.numer },
      { naglowek: 'Nabywca', wartosc: x => x.nabywca },
      { naglowek: 'NIP', wartosc: x => x.nip, klasa: () => 'szary' },
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
        ${filtrData('od', 'Wystawione od', p.od)}${filtrData('do', 'do', p.do)}
      </div>
      <p class="notka">Status pochodzi z Fakturowni i bywa nieodhaczony. W etapie 2 aplikacja sama sprawdzi wpłaty w banku.</p>
      ${tabela({ kolumny: kol, dane: w.wiersze, poczatek: (w.strona - 1) * w.ile + 1,
        stopkaSum: { netto: zl(w.netto, false), brutto: zl(w.brutto, false) },
        onWiersz: x => pokazKarte(x.numer, [
          ['Nabywca', x.nabywca], ['NIP', x.nip], ['Status', x.status], ['Netto', zl(x.netto)], ['VAT', zl(x.vat)], ['Brutto', zl(x.brutto)],
          ['Opłacono (Fakturownia)', zl(x.oplacono)], ['Wystawiona', dataPl(x.data_wystawienia)], ['Data sprzedaży', dataPl(x.data_sprzedazy)],
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
    ];
    return `<h1>Rejestr zakupów</h1><div class="okruszki">Płatności / Dokumenty kosztowe z biura</div>
      <div class="filtry">
        ${filtr('rejestr', 'Rejestr', [['', 'Wszystkie'], ['krajowe', 'Krajowe'], ['zagraniczne', 'Zagraniczne']], p.rejestr)}
        ${filtrData('od', 'Od', p.od)}${filtrData('do', 'Do', p.do)}
      </div>
      ${tabela({ kolumny: kol, dane: w.wiersze, poczatek: (w.strona - 1) * w.ile + 1, stopkaSum: { netto: zl(w.netto, false) },
        onWiersz: x => pokazKarte(x.podmiot, [['Numer dokumentu', x.nr_dok], ['Nr ewidencyjny', x.nr_ewid], ['Rejestr', x.rejestr],
          ['Data', dataPl(x.data)], ['Data zaewidencjonowania', dataPl(x.data_zaewid)], ['Netto', zl(x.netto)], ['VAT', zl(x.vat)],
          ['Brutto', x.brutto != null ? zl(x.brutto) : 'brak w rejestrze zagranicznym']], `${x.plik}, wiersz ${x.wiersz}`) })}
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

function wBudowie(sekcja) {
  const nazwa = MENU.find(m => m.id === sekcja)?.nazwa || sekcja;
  const etap = { budzet: 3, cashflow: 5, rentownosc: 4, eksport: 6 }[sekcja];
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

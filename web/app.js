'use strict';
// Finanse DigitalH: interfejs. Wszystkie liczby przychodzą z serwera w groszach; tu tylko formatowanie.

const MIESIACE = ['stycznia', 'lutego', 'marca', 'kwietnia', 'maja', 'czerwca', 'lipca', 'sierpnia',
  'września', 'października', 'listopada', 'grudnia'];

const IKONY = {
  pulpit: '<path d="M3 11l9-7 9 7v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/>',
  budzet: '<rect x="3" y="5" width="18" height="14" rx="1"/><path d="M3 10h18M3 14.5h18M9 5v14"/>',
  platnosci: '<circle cx="12" cy="12" r="9"/><path d="M15 9.5c-.5-1-1.6-1.5-3-1.5-1.7 0-3 .8-3 2s1.3 1.7 3 2 3 .8 3 2-1.3 2-3 2c-1.4 0-2.6-.6-3-1.6M12 6v2M12 16v2"/>',
  cashflow: '<path d="M3 8c3-3 6 3 9 0s6 3 9 0M3 13c3-3 6 3 9 0s6 3 9 0M3 18c3-3 6 3 9 0s6 3 9 0"/>',
  rentownosc: '<path d="M6 20V11M11 20V5M16 20v-8M3 20h18"/>',
  eksport: '<path d="M12 4v11M7 10l5 5 5-5M4 19h16"/>',
  wydatki: '<rect x="3" y="6" width="18" height="13" rx="1.5"/><path d="M3 10h18M16 14.5h2M6 6V4.5h12V6"/>',
};

// Drobne ikony interfejsu (obrys, 24 × 24), wstawiane funkcją ik().
const IK = {
  gora: '<path d="M7 17 17 7M9 7h8v8"/>', dol: '<path d="M7 7l10 10M17 9v8H9"/>',
  plus: '<path d="M12 5v14M5 12h14"/>', lupa: '<circle cx="11" cy="11" r="6"/><path d="m20 20-4.5-4.5"/>',
  warstwy: '<path d="M12 3 2 8l10 5 10-5z"/><path d="m2 13 10 5 10-5"/>', przywroc: '<path d="M9 14 4 9l5-5"/><path d="M4 9h10a6 6 0 0 1 0 12h-2"/>',
  kropki: '<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
  filtr: '<path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0"/><circle cx="16" cy="6" r="2"/><circle cx="10" cy="12" r="2"/><circle cx="18" cy="18" r="2"/>',
  kalendarz: '<rect x="3.5" y="5" width="17" height="15" rx="1.5"/><path d="M3.5 10h17M8 3v4M16 3v4"/>',
  kalendarzX: '<rect x="3.5" y="5" width="17" height="15" rx="1.5"/><path d="M3.5 10h17M8 3v4M16 3v4M9.5 13l5 4M14.5 13l-5 4"/>',
  kalendarzK: '<rect x="3.5" y="5" width="17" height="15" rx="1.5"/><path d="M3.5 10h17M8 3v4M16 3v4M9 14.5h6"/>',
  przekreslony: '<path d="M4 4l16 16M9 5h9v9M5 9v10h10"/>', plusKolko: '<circle cx="12" cy="12" r="8.5"/><path d="M12 8.5v7M8.5 12h7"/>',
  przelew: '<path d="M4 8h13l-3-3M20 16H7l3 3"/>', ptaszek: '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
  link: '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
  rozlacz: '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1M4 4l16 16"/>',
  weryfikuj: '<path d="M4 7h11M4 12h7M4 17h9M15 15l2 2 4-4"/>', bank: '<path d="M3 9.5 12 4l9 5.5M5 10v8M9.5 10v8M14.5 10v8M19 10v8M3 20h18"/>',
  dokument: '<path d="M7 3h7l5 5v13H7z"/><path d="M14 3v5h5M10 13h6M10 17h6"/>', folder: '<path d="M3 7a1 1 0 0 1 1-1h5l2 2h9a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1z"/>',
  folderOko: '<path d="M3 7a1 1 0 0 1 1-1h5l2 2h9a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1z"/><circle cx="12" cy="13.5" r="1.6"/>',
  pinezka: '<path d="M9 4h6l-1 6 3 3H7l3-3zM12 13v7"/>', arkusz: '<rect x="3.5" y="4.5" width="17" height="15" rx="1"/><path d="M3.5 9.5h17M9 4.5v15"/>',
  zebatka: '<circle cx="12" cy="12" r="3"/><path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6 7 7M17 17l1.4 1.4M5.6 18.4 7 17M17 7l1.4-1.4"/>',
  fale: '<path d="M3 9c3-3 6 3 9 0s6 3 9 0M3 15c3-3 6 3 9 0s6 3 9 0"/>', wykres: '<path d="M6 20V11M11 20V5M16 20v-8M3 20h18"/>',
  plik: '<path d="M7 3h7l5 5v13H7z"/><path d="M14 3v5h5"/>', historia: '<path d="M4 12a8 8 0 1 0 2.3-5.7L4 8.5M4 4v4.5h4.5M12 8v4l3 2"/>',
  osoby: '<circle cx="9" cy="8" r="3"/><path d="M3.5 19a5.5 5.5 0 0 1 11 0M16 5a3 3 0 0 1 0 6M18 14a5 5 0 0 1 2.5 5"/>', zamknij: '<path d="m6 6 12 12M18 6 6 18"/>',
  oko: '<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="2.5"/>',
  strzalkaP: '<path d="M5 12h14M13 6l6 6-6 6"/>', siatka: '<rect x="4" y="4" width="7" height="7"/><rect x="13" y="4" width="7" height="7"/><rect x="4" y="13" width="7" height="7"/><rect x="13" y="13" width="7" height="7"/>',
  rowne: '<path d="M5 9h14M5 15h14"/>', ksiazka: '<path d="M4 5.5A1.5 1.5 0 0 1 5.5 4H11v15H5.5A1.5 1.5 0 0 0 4 20.5zM20 5.5A1.5 1.5 0 0 0 18.5 4H13v15h5.5a1.5 1.5 0 0 1 1.5 1.5z"/>',
};
const ik = (nazwa, klasa = '') => `<svg class="ik${klasa ? ' ' + klasa : ''}" viewBox="0 0 24 24" aria-hidden="true">${IK[nazwa] || ''}</svg>`;

const MENU = [
  { id: 'pulpit', nazwa: 'Pulpit', bezPanelu: true },
  { id: 'budzet', nazwa: 'Budżet' },
  { id: 'platnosci', nazwa: 'Płatności' },
  { id: 'cashflow', nazwa: 'Cash flow' },
  { id: 'rentownosc', nazwa: 'Rentowność' },
  { id: 'wydatki', nazwa: 'Wydatki', bezPanelu: true },   // analiza wydatków (web/wydatki.js)
  { id: 'eksport', nazwa: 'Eksport', bezPanelu: true },
];

// Podstrony w wysuwanym panelu, jak w Budget Studio (grupa, ikona, licznik). Budżet ma osobny panel z drzewem arkuszy.
const PODSTRONY = {
  platnosci: [
    { grupa: 'Płatności oczekujące' },
    { nazwa: 'Do połączenia', hash: '#/platnosci/do-polaczenia', licznik: 'do_polaczenia', ik: 'rozlacz' },
    { nazwa: 'Do weryfikacji', hash: '#/platnosci/do-weryfikacji', licznik: 'do_weryfikacji', ik: 'weryfikuj' },
    { grupa: 'Połączone z budżetem', ik: 'link' },
    { ekran: 'platnosci', hash: '#/platnosci/plan' },   // widoki listy (startowe i zapisane) z liczbą pozycji, listy.js
    { grupa: 'Bank ING' },
    { ekran: 'bank', hash: '#/platnosci/bank' },
    { grupa: 'Dokumenty' },
    { ekran: 'faktury', hash: '#/platnosci/faktury' },
    { ekran: 'naleznosci', hash: '#/platnosci/naleznosci' },
    { ekran: 'zakupy', hash: '#/platnosci/zakupy' },
    { grupa: 'Dane' },
    { nazwa: 'Historia importów', hash: '#/platnosci/importy', ik: 'historia' },
    { nazwa: 'Wyniki z biura (RZiS)', hash: '#/platnosci/wyniki-biura', ik: 'plik' },
  ],
  budzet: [
    { grupa: 'Budżet' },
    { nazwa: 'Wszystkie arkusze', hash: '#/budzet/arkusze', ik: 'arkusz' },
    { nazwa: 'Klienci (foldery)', hash: '#/budzet', ik: 'folder' },
    { nazwa: 'Umowy z klientami', hash: '#/budzet/umowy', ik: 'dokument' },
    { nazwa: 'Rozjazdy z Budget Studio', hash: '#/budzet/rozjazdy', ik: 'weryfikuj' },
    { nazwa: 'Historia zmian planów', hash: '#/budzet/historia', ik: 'historia' },
    { grupa: 'Wydatki z banku' },
    { ekran: 'wydatki', hash: '#/budzet/wydatki' },
    { nazwa: 'Nieprzypisane wg kontrahenta', hash: '#/budzet/nieprzypisane', ik: 'osoby' },
    { nazwa: 'Konta reklamowe', hash: '#/budzet/konta', ik: 'wykres' },
    { grupa: 'Ustawienia' },
    { nazwa: 'Biblioteka', hash: '#/budzet/biblioteka', ik: 'ksiazka' },   // pakiet 4: słowniki, foldery i kategorie
    { nazwa: 'Reguły przypisań', hash: '#/budzet/reguly', ik: 'zebatka' },
    { nazwa: 'Ustawienia budżetu', hash: '#/budzet/ustawienia', ik: 'zebatka' }],
  cashflow: [{ grupa: 'Zapisane widoki', ik: 'oko' }],   // pozycje z WIDOKI_CF (budzet.js)
  rentownosc: [{ grupa: 'Zapisane widoki', ik: 'oko' }, { nazwa: 'Wynik zarządczy', hash: '#/rentownosc', ik: 'wykres' },
    { nazwa: 'Obroty wg klientów', hash: '#/rentownosc/klienci', ik: 'osoby' }, { nazwa: 'Koszty wg kategorii', hash: '#/rentownosc/koszty', ik: 'siatka' },
    { nazwa: 'Podatek VAT', hash: '#/rentownosc/vat', ik: 'przekreslony' },
    { grupa: 'Klienci i arkusze' }, { nazwa: 'Rentowność klientów', hash: '#/rentownosc/rent-klienci', ik: 'folder' },
    { nazwa: 'Arkusze: plan i wykonanie', hash: '#/rentownosc/arkusze', ik: 'arkusz' }],
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

// Kwota skrócona jak na kaflach BS: 60k, -9k, 1,2 mln; zero jako 0,00.
function skrot(gr) {
  if (!gr) return '0,00';
  const z = gr / 100, a = Math.abs(z);
  if (a >= 1e6) return `${(z / 1e6).toFixed(1).replace('.', ',')} mln`;
  if (a >= 1000) return `${Math.round(z / 1000)}k`;
  return zl(gr, false);
}

function dataPl(iso) {
  if (!iso) return '';
  const [r, m, d] = iso.split('-').map(Number);
  return `${d} ${MIESIACE[m - 1]} '${String(r).slice(2)}`;
}

async function api(sciezka, parametry = {}) {
  const q = new URLSearchParams(Object.entries(parametry).filter(([, v]) => v !== '' && v != null));
  if (typeof zapamietajZapytanie === 'function') zapamietajZapytanie(sciezka, parametry);   // eksport listy z tymi filtrami (eksport.js)
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
  komunikat('Zapisuję i przeliczam dane…');   // odbudowa trwa chwilę; bez tego klik wygląda na niezadziałany
  const r = await fetch('/api/zmiana', { method: 'POST', headers: { 'X-Finanse': '1', 'Content-Type': 'application/json' },
    body: JSON.stringify({ typ, dane }) });
  const w = await r.json().catch(() => ({}));
  if (!r.ok) { komunikat(w.blad || 'Nie udało się zapisać decyzji.', true); return false; }
  $('#karta').hidden = true;
  await sprawdzStan();
  await pokaz();
  komunikat('Zapisane. Decyzja jest w pliku zmian tego Maca, drugi Mac zobaczy ją po synchronizacji iCloud.', false,
    typ === 'bud' && typeof cofnijOstatni === 'function' ? { nazwa: 'Cofnij', akcja: cofnijOstatni }
      : ['rezerwa', 'lista_plac', 'kategoria_regula', 'kategoria_operacja', 'cel_wydatku', 'koszt_regula', 'seria'].includes(typ) && w.wpis ? { nazwa: 'Cofnij', akcja: () => zmiana('cofnij', { wpis: w.wpis }) } : null);
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
  ul.innerHTML = MENU.map(m => `<li><button data-id="${m.id}" aria-expanded="false"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${IKONY[m.id]}</svg><span class="etykieta">${m.nazwa}</span></button></li>`).join('');
  ul.addEventListener('click', e => {
    const b = e.target.closest('button');
    if (!b) return;
    const id = b.dataset.id;
    if (MENU.find(m => m.id === id)?.bezPanelu) { zamknijWysuw(); location.hash = `#/${id}`; return; }
    if (!$('#wysuw').hidden && $('#wysuw').dataset.sekcja === id) return zamknijWysuw();
    otworzWysuw(id);
  });
  document.addEventListener('click', e => {
    if (!e.target.closest('#wysuw') && !e.target.closest('#menu')) zamknijWysuw();
    if (!e.target.closest('#karta') && !e.target.closest('tbody') && !e.target.closest('[data-karta]')) $('#karta').hidden = true;
  });
  document.addEventListener('keydown', e => { if (e.key === 'Escape') { zamknijWysuw(); $('#karta').hidden = true; $('#pomoc').hidden = true; } });
  $('#przycisk-pomocy').onclick = () => otworzPomoc('dane');
}

// Pozycja panelu: ikona, nazwa, licznik oczekujących (pomarańczowy) albo liczba pozycji widoku listy (szary).
function pozycjaWysuwu(p) {
  const n = p.licznik && STAN?.naleznosci ? STAN.naleznosci[p.licznik] : 0;
  const aktywna = location.hash === p.hash ? ' aktywna' : '';
  return `<a class="poz${aktywna}" href="${p.hash}">${p.ik ? ik(p.ik) : ''}<span>${esc(p.nazwa)}</span>${n ? ` <span class="licznik">${n}</span>` : p.ile ? ` <span class="licznik szary">${p.ile}</span>` : ''}</a>`;
}

// Pozycja {ekran, hash} rozwija się w widoki tej listy z MENU_LISTY (GET /api/listy/menu).
function listaWysuwu(pozycje) {
  let html = '', otwarta = false;
  for (const p of pozycje) {
    if (p.grupa) { html += `${otwarta ? '</div>' : ''}<h3><span>${esc(p.grupa)}</span>${p.ik ? ik(p.ik, 'szary') : ''}</h3><div class="grupa-wysuw">`; otwarta = true; }
    else if (p.ekran) html += (MENU_LISTY?.ekrany[p.ekran] || []).map(v => pozycjaWysuwu({ nazwa: v.nazwa, ik: v.ik, ile: v.ile, hash: `${p.hash}?widok=${encodeURIComponent(v.id)}` })).join('');
    else html += pozycjaWysuwu(p);
  }
  return html + (otwarta ? '</div>' : '');
}

let KAFLE = null;   // liczby płatności list planu na kaflach pulpitu, odświeżane przy pulpicie
let MENU_LISTY = null;   // widoki list z liczbą pozycji (menu Płatności i Budżetu), null = pobrać przy otwarciu menu
async function otworzWysuw(id) {
  const w = $('#wysuw');
  const nazwa = id === 'budzet' ? 'Arkusze budżetu' : MENU.find(m => m.id === id).nazwa;
  w.dataset.sekcja = id;
  document.querySelectorAll('#menu button').forEach(b => b.setAttribute('aria-expanded', String(b.dataset.id === id)));
  const naglowek = (przycisk = '') => `<div class="wysuw-naglowek"><h2>${esc(nazwa)}</h2>${przycisk}</div>`;
  w.hidden = false;
  document.body.classList.add('wysuw-otwarty');
  if (id === 'budzet') {
    w.innerHTML = `${naglowek()}<div class="pusto-wysuw">Wczytuję arkusze…</div>`;
    const d = await api('budzet/drzewo').catch(() => null);
    if (w.dataset.sekcja !== 'budzet') return;
    // Drzewo pokazuje przypięte arkusze (A-OPS-07); wyszukiwarka filtruje po nazwie arkusza, kategorii i folderu (A-BUD-12),
    // a pasujące nieprzypięte dopisuje pod spodem, żeby fraza znalazła każdy arkusz.
    const drzewo = (q = '') => {
      const f = q.trim().toLowerCase();
      const pasuje = t => !f || String(t).toLowerCase().includes(f);
      const galaz = przypiete => (d?.foldery || []).map(fo => {
        const kat = Object.entries(fo.kategorie).map(([k, ark]) => {
          const a = ark.filter(x => !x.przypiety !== przypiete && (pasuje(x.nazwa) || pasuje(k) || pasuje(fo.folder)));
          return a.length ? `<a class="kat-wysuw" href="#/budzet/biblioteka?zakladka=struktura&folder=${encodeURIComponent(fo.folder)}&kategoria=${encodeURIComponent(k)}">${esc(k)}</a>${a.map(x => `<a class="ark-wysuw${przypiete ? '' : ' nieprzypiety'}" href="#/budzet/arkusz?id=${encodeURIComponent(x.id)}">${esc(x.nazwa)}</a>`).join('')}` : '';
        }).join('');
        return kat ? `<a class="folder-wysuw" href="#/budzet/biblioteka?zakladka=struktura&folder=${encodeURIComponent(fo.folder)}">${ik('folder')}${esc(fo.folder)}</a>${kat}` : '';
      }).join('');
      const html = galaz(true), reszta = f ? galaz(false) : '';
      if (!html && !reszta) return `<div class="pusto-wysuw">${f ? 'Brak arkuszy dla tej frazy.' : 'Brak przypiętych arkuszy. Wszystkie znajdziesz niżej, w „Zobacz wszystkie arkusze”.'}</div>`;
      return html + (reszta ? `<div class="wysuw-nieprzypiete">Nieprzypięte</div>${reszta}` : '');
    };
    w.innerHTML = `${naglowek(d?.planowanie ? `<button class="przycisk glowny" id="wysuw-dodaj-arkusz">Dodaj ${ik('plus')}</button>` : '')}
      <input class="szukaj-wysuw" id="wysuw-szukaj" type="search" placeholder="Wyszukaj" aria-label="Wyszukaj arkusz">
      <div id="wysuw-drzewo">${drzewo()}</div>
      <div class="stopka-wysuw"><a href="#/budzet/arkusze">Zobacz wszystkie arkusze →</a></div>
      <div id="wysuw-podstrony">${listaWysuwu(PODSTRONY.budzet)}</div>`;
    $('#wysuw-szukaj').oninput = e => { $('#wysuw-drzewo').innerHTML = drzewo(e.target.value); };
    odswiezMenuList(() => { if (w.dataset.sekcja === 'budzet') { $('#wysuw-podstrony').innerHTML = listaWysuwu(PODSTRONY.budzet); podepnijWysuw(); } });
    const dod = $('#wysuw-dodaj-arkusz');
    if (dod) dod.onclick = e => { e.stopPropagation(); zamknijWysuw(); kartaArkusza(null, d); };
  } else if (id === 'cashflow') {
    w.innerHTML = naglowek() + listaWysuwu([...PODSTRONY.cashflow, ...WIDOKI_CF.map(v => ({ nazwa: v.nazwa, hash: `#/cashflow?widok=${v.id}`, ik: v.ik }))]);
  } else if (id === 'platnosci') {
    w.innerHTML = naglowek() + listaWysuwu(PODSTRONY.platnosci);
    odswiezMenuList(() => { if (w.dataset.sekcja === 'platnosci') { w.innerHTML = naglowek() + listaWysuwu(PODSTRONY.platnosci); podepnijWysuw(); } });
  } else {
    w.innerHTML = naglowek() + listaWysuwu(PODSTRONY[id] || []);
  }
  podepnijWysuw();
}

function podepnijWysuw() { $('#wysuw').querySelectorAll('a[href]').forEach(a => a.addEventListener('click', zamknijWysuw)); }

// Liczniki w menu liczy serwer przy każdym otwarciu menu (widoki z datami względnymi zmieniają się z dniem stanu).
function odswiezMenuList(poPobraniu) {
  api('listy/menu').then(m => { MENU_LISTY = m; poPobraniu(); }).catch(() => {});
}

function zamknijWysuw() {
  $('#wysuw').hidden = true;
  $('#wysuw').dataset.sekcja = '';
  document.body.classList.remove('wysuw-otwarty');
  document.querySelectorAll('#menu button').forEach(b => b.setAttribute('aria-expanded', 'false'));
}

function zaznaczMenu(sekcja) {
  document.querySelectorAll('#menu button').forEach(b => b.setAttribute('aria-current', String(b.dataset.id === sekcja)));
}

// ---------- Wspólna tabela w stylu BS ----------
// Fioletowe nagłówki z linią, numer wiersza, liczby do prawej, kolor wg znaku, piguły, strzałka sortowania.
// Kolumna: {id?, naglowek, wartosc(x) | html(x), liczba?, klasa?(x), sort? (po stronie serwera), sortKlucz?(x) (lokalnie)}.
// Opcje: wierszKlasa(x) (tło planu, po terminie, wpływ), kropka(x) (kropka statusu przed wierszem),
// sortLokalny: sortowanie danych tej strony bez serwera (dla list bez stronicowania), naSort(klucz, kierunek): własna obsługa
// sortowania serwera (domyślnie parametry adresu), zaznacz: {czy(x), ustaw(x, tak), poZmianie()}: pole wyboru w miejscu numeru
// wiersza (po najechaniu, jak w BS), „zaznacz wszystkie na stronie” w nagłówku, Shift + klik zaznacza zakres.
// Każda tabela dostaje własny identyfikator, a zdarzenia podpinamy tylko w niej (dwie tabele na ekranie się nie mieszają).
let licznikTabel = 0;
function tabela(o) {
  const { kolumny, dane, poczatek = 1, onWiersz, stopkaSum, sortuj, kierunek, wierszKlasa, kropka, sortLokalny, naSort, zaznacz } = o;
  if (!dane.length) return '<div class="pusto">Brak pozycji dla tych filtrów.</div>';
  const id = o.id || `tabela-${++licznikTabel}`;
  const sortowalna = k => k.sort || (sortLokalny && (k.sortKlucz || k.wartosc));
  const kluczSortu = k => k.sort || `l:${kolumny.indexOf(k)}`;
  const th = kolumny.map(k => {
    const kl = [sortowalna(k) ? 'sort' : '', k.liczba ? 'liczba-kol' : ''].filter(Boolean).join(' ');
    return `<th${kl ? ` class="${kl}"` : ''}${sortowalna(k) ? ` data-sort="${esc(kluczSortu(k))}"${sortuj === kluczSortu(k) ? ` data-kierunek="${kierunek}"` : ''}` : ''}>${k.naglowek}</th>`;
  }).join('');
  const lp = (w, i) => zaznacz ? `<td class="lp"><input type="checkbox" class="zazn" data-z="${i}"${zaznacz.czy(w) ? ' checked' : ''} aria-label="Zaznacz wiersz ${poczatek + i}"><span class="nr">${poczatek + i}.</span></td>`
    : `<td class="lp">${poczatek + i}.</td>`;
  const tr = dane.map((w, i) => `<tr data-i="${i}" class="${wierszKlasa ? wierszKlasa(w) : ''}${zaznacz?.czy(w) ? ' zaznaczony' : ''}"${w.plik ? ` title="Źródło: ${esc(w.plik)}, wiersz ${w.wiersz}"` : ''}>${lp(w, i)}${kropka ? `<td class="kr">${kropka(w)}</td>` : ''}${kolumny.map(k => `<td class="${k.liczba ? 'liczba-kol ' : ''}${k.klasa ? k.klasa(w) : ''}">${k.html ? k.html(w) : esc(k.wartosc(w))}</td>`).join('')}</tr>`).join('');
  const tf = stopkaSum ? `<tfoot><tr><td></td>${kropka ? '<td></td>' : ''}${kolumny.map(k => `<td class="${k.liczba ? 'liczba-kol' : ''}">${stopkaSum[k.id] ?? ''}</td>`).join('')}</tr></tfoot>` : '';
  setTimeout(() => {
    const t = document.getElementById(id);
    if (!t) return;
    if (onWiersz) t.querySelectorAll('tbody tr[data-i]').forEach(r => r.addEventListener('click', () => onWiersz(dane[r.dataset.i])));
    if (zaznacz) {
      const naglowek = t.querySelector('input.zazn-strona');
      let ostatni = null;
      const sync = () => {
        let ile = 0;
        t.querySelectorAll('tbody tr[data-i]').forEach(r => {
          const c = zaznacz.czy(dane[r.dataset.i]);
          ile += c;
          r.classList.toggle('zaznaczony', c);
          r.querySelector('input.zazn').checked = c;
        });
        naglowek.checked = ile === dane.length;
        naglowek.indeterminate = ile > 0 && ile < dane.length;
        zaznacz.poZmianie?.();
      };
      t.odswiezZaznaczenie = sync;
      const klik = (i, tak, shift) => {
        const zakres = shift && ostatni != null ? [Math.min(i, ostatni), Math.max(i, ostatni)] : [i, i];
        for (let j = zakres[0]; j <= zakres[1]; j++) zaznacz.ustaw(dane[j], tak);
        ostatni = i;
        sync();
      };
      // cała komórka numeru działa jak pole wyboru (łatwiej trafić), nie otwiera karty wiersza
      t.querySelectorAll('tbody td.lp').forEach(td => td.addEventListener('click', e => {
        e.stopPropagation();
        const c = td.querySelector('input.zazn');
        klik(+c.dataset.z, e.target === c ? c.checked : !zaznacz.czy(dane[c.dataset.z]), e.shiftKey);
      }));
      naglowek.addEventListener('click', e => { e.stopPropagation(); dane.forEach(x => zaznacz.ustaw(x, naglowek.checked)); ostatni = null; sync(); });
      sync();
    }
    t.querySelectorAll('th.sort').forEach(h => h.addEventListener('click', () => {
      const nowy = sortuj === h.dataset.sort && kierunek === 'malejaco' ? 'rosnaco' : 'malejaco';
      if (!h.dataset.sort.startsWith('l:')) return naSort ? naSort(h.dataset.sort, nowy) : ustawParametry({ sortuj: h.dataset.sort, kolejnosc: nowy, strona: 1 });
      const k = kolumny[+h.dataset.sort.slice(2)], f = k.sortKlucz || k.wartosc;
      const znak = nowy === 'rosnaco' ? 1 : -1;
      const posort = [...dane].sort((a, b) => { const x = f(a), y = f(b); return znak * (typeof x === 'number' && typeof y === 'number' ? x - y : String(x ?? '').localeCompare(String(y ?? ''), 'pl')); });
      t.outerHTML = tabela({ ...o, id, dane: posort, sortuj: h.dataset.sort, kierunek: nowy });
    }));
  });
  const thLp = zaznacz ? '<th class="lp"><input type="checkbox" class="zazn-strona" aria-label="Zaznacz wszystkie na stronie" title="Zaznacz wszystkie na stronie"></th>' : '<th class="lp"></th>';
  return `<div class="tabela-ramka${o.niska ? ' niska' : ''}${zaznacz ? ' z-zaznaczaniem' : ''}" id="${id}"><table><thead><tr>${thLp}${kropka ? '<th></th>' : ''}${th}</tr></thead><tbody>${tr}</tbody>${tf}</table></div>`;
}

function stopka(wynik, parametry) {
  const od = wynik.razem ? (wynik.strona - 1) * wynik.ile + 1 : 0;
  const doN = Math.min(wynik.strona * wynik.ile, wynik.razem);
  const ostatnia = Math.max(1, Math.ceil(wynik.razem / wynik.ile));
  const html = `<div class="stopka">
    <label>Max widocznych <select id="ile">${[50, 100, 200, 500].map(n => `<option${n === wynik.ile ? ' selected' : ''}>${n}</option>`).join('')}</select></label>
    <button id="poprz" ${wynik.strona <= 1 ? 'disabled' : ''} aria-label="Poprzednia strona">↑</button>
    <span>Wyświetlono ${od}-${doN} z ${wynik.razem}</span>
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
  bez_faktury: 'nie dotyczy faktury', zwrot_zakupu: 'zwrot zakupu' };

// Piguła Rodzaj jak w BS: zaokrąglona, ikona strzałki, zielona dla wpływów, czerwona dla obciążeń.
const chipZnak = znak => znak > 0 ? `<span class="chip plus">${ik('gora')}wpływy</span>` : `<span class="chip minus">${ik('dol')}obciążenia</span>`;
const chipKwota = kwota => chipZnak(kwota);

// Kafle pulpitu jak w BS: lista planu, tytuł, ikona, kolor kafla, kropka statusu, klucz pomocy.
const KAFLE_PULPITU = [
  ['nieoplacone', 'Nadal nieopłacone (do aktualizacji)', 'kalendarzX', 'czerwony', 'czerwona', 'kafle_bs'],
  ['niewystawione', 'Nadal niewystawione (do aktualizacji)', 'kalendarzK', 'niebieski', 'czerwona', 'kafle_bs'],
  ['po_terminie', 'Po terminie płatności (oficjalnym)', 'przekreslony', 'czerwony', 'czerwona', 'kafle_bs'],
  ['do_wystawienia', 'Do wystawienia (najbliższe 2 tyg.)', 'plusKolko', 'niebieski', '', 'kafle_bs'],
  ['do_zaplacenia', 'Do zapłacenia (najbliższe 2 tyg.)', 'przelew', 'niebieski', 'czerwona', 'kafle_bs'],
  ['zaplacone', 'Zapłacone (ostatnie 2 tyg.)', 'ptaszek', 'fiolet', 'zielona', 'kafle_bs'],
];
const plusDniIso = (iso, n) => { const d = new Date(iso + 'T12:00:00Z'); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); };

// ---------- widoki ----------
const WIDOKI = {
  async pulpit() {
    const s = STAN;
    const dzien = s.naleznosci?.dzien_stanu || s.bank_do;
    const [c, k] = await Promise.all([api('controlling'), api('budzet/kafle').catch(() => null)]);
    if (k) KAFLE = k.listy;
    Promise.all([api('saldo-historia'), api('wynik'),
      api('cashflow/okresy', { granulacja: 'tydzien', od: plusDniIso(dzien, -35), do: plusDniIso(dzien, 182) })]).then(([h, d, cf]) => {
      if (!$('#pulpit-gotowka')) return;
      Wykresy.bs($('#pulpit-cf'), { okresy: cf.okresy, wysokosc: 250, opis: 'Cash flow 6 miesięcy w przód, tygodniowo',
        naKlik: () => { location.hash = '#/cashflow?widok=6mies'; } });
      Wykresy.linia($('#pulpit-gotowka'), { punkty: h, nazwa: 'Gotówka', kolor: Wykresy.kolor('--s1'), wysokosc: 200, opis: 'Saldo gotówki',
        etykietaX: x => MIESIACE[+x.slice(5, 7) - 1].slice(0, 3), etykietaPelna: x => dataPl(x),
        dodatkowe: p => [{ nazwa: 'w tym rachunek główny', wartosc: Wykresy.pelna(p.glowny) }, { nazwa: 'w tym online', wartosc: Wykresy.pelna(p.online) }] });
      wykresWyniku('pulpit', d, { tylkoWynik: true });
    });
    setTimeout(() => {
      document.querySelectorAll('.pasek-celu [data-w]').forEach(x => { x.style[x.tagName === 'I' ? 'width' : 'left'] = `${Math.max(0, Math.min(100, x.dataset.w))}%`; });
      document.querySelectorAll('.pasek-proporcji[data-w]').forEach(x => { x.style.width = `calc(74px + ${x.dataset.w} * (100% - 74px))`; });
      const b = $('#ustaw-cele'); if (b) b.onclick = e => { e.stopPropagation(); kartaCelow(c.cele, c.rezerwa); };
      const pm = $('#pulpit-pomoc'); if (pm) pm.onclick = () => otworzPomoc('kafle_bs');
      if (typeof pulpitDodatki === 'function') pulpitDodatki();   // pakiet 11: alerty umów, rachunek VAT, lista płac (pulpit.js)
    });
    const zakladki = `<div class="zakladki" role="tablist"><button role="tab" aria-selected="true">${ik('siatka')}Pulpit</button>
      <button role="tab" aria-selected="false" id="ustaw-cele" data-karta>${ik('zebatka')}Cele</button>
      <button role="tab" aria-selected="false" id="pulpit-pomoc">${ik('ksiazka')}Jak czytać pulpit</button></div>`;
    if (c.brak_danych) return `<h1>Pulpit</h1>${zakladki}<div class="pusto">Brak danych z banku.</div>`;
    const r = c.rezerwa, o = c.obrot, m = c.marza, n = c.naleznosci, pz = c.porzadek;
    const mies1 = x => x == null ? 'brak' : `${String(x).replace('.', ',')} mies.`;
    const brakuje = r.nadwyzka < 0 ? `brakuje ${zl(-r.nadwyzka)}` : `ponad cel ${zl(r.nadwyzka)}`;
    const ndo = s.naleznosci?.do_weryfikacji || 0;
    const npo = s.naleznosci?.do_polaczenia ?? pz.do_polaczenia;
    const maks = Math.max(1, ...Object.values(KAFLE || {}).flatMap(x => [Math.abs(x.wplywy.kwota), Math.abs(x.obciazenia.kwota)]));
    const linia = (lista, rodzaj, x, kropka) => {
      const znak = rodzaj === 'wplywy' ? 1 : -1, pusta = !x.ile;
      const kl = pusta ? 'zero' : znak > 0 ? 'plus' : 'minus';
      return `<a class="linia-bs${pusta ? ' pusta' : ''}" href="#/platnosci/plan?lista=${lista}&rodzaj=${znak}" title="${esc(zl(x.kwota))}">
        <i class="tlo-linii"></i><i class="pasek-proporcji" data-w="${pusta ? 0 : (Math.abs(x.kwota) / maks).toFixed(3)}"></i>
        <b class="${kl}">${pusta ? '0,00' : skrot(x.kwota)}</b>${pusta ? '<span class="pusty"></span>' : kropka}
        <small class="${kl}">${pusta ? 'Brak płatności' : `${x.ile} ${x.ile === 1 ? 'płatność' : x.ile < 5 ? 'płatności' : 'płatności'}`}</small>
        <span class="strzalka ${znak > 0 ? 'plus' : 'minus'}" aria-hidden="true">${znak > 0 ? '↗' : '↘'}</span></a>`;
    };
    const kafel = ([lista, tytul, ikona, kolor, kropka, pomoc]) => {
      const x = KAFLE?.[lista];
      if (!x) return '';
      const kr = kropka === 'zielona' ? '<span class="kropka zielona"></span>' : kropka ? '<span class="kropka czerwona"></span>' : '<span class="pusty"></span>';
      return `<div class="kafel-bs ${kolor}"><div class="tytul">${ik(ikona)}${esc(tytul)} ${pytajnik(pomoc)}</div>
        <div class="pudlo">${linia(lista, 'wplywy', x.wplywy, kr)}${linia(lista, 'obciazenia', x.obciazenia, kr)}</div></div>`;
    };
    return `<h1>Pulpit</h1>${zakladki}
      <div class="baner">Płatności nieuwzględnione w należnościach, cash flow i rentowności:
        <a href="#/platnosci/do-polaczenia" class="${npo ? '' : 'zero'}">${ik('rozlacz')}Do połączenia <span class="licznik">${npo}</span></a>
        <a href="#/platnosci/do-weryfikacji" class="${ndo ? '' : 'zero'}">${ik('weryfikuj')}Do weryfikacji <span class="licznik">${ndo}</span></a>
        <a href="#/budzet/wydatki?rodzaj=nieprzypisany" class="${pz.nieprzypisane ? '' : 'zero'}">${ik('przekreslony')}Wydatki bez rodzaju <span class="licznik">${pz.nieprzypisane}</span></a>
        <span id="pulpit-porzadek"></span>
        <span class="szary">stan na ${dataPl(c.dzien_stanu)}, ostatni dzień w eksporcie z ING</span></div>
      <div id="pulpit-alerty"></div>
      <div class="kafle-bs">${KAFLE_PULPITU.map(kafel).join('')}</div>
      <div class="naglowek-sekcji">${ik('kalendarz')}6 mies. w przód ${pytajnik('cf_pulpit')}</div>
      <div class="wykres-pulpitu"><div id="pulpit-cf"></div></div>
      <div class="naglowek-sekcji">${ik('wykres')}Kontroling ${pytajnik('porzadek')}</div>
      <div class="kontrolka">
        <a class="kafel-st ${r.status}" href="#/rentownosc/koszty">
          <div class="tytul">Rezerwa gotówki ${pytajnik('rezerwa')}</div>
          <div class="wartosc">${r.pokrycie_miesiecy == null ? 'brak' : `na ${mies1(r.pokrycie_miesiecy)}`}</div>
          ${chipStatus(r.status, r.status === 'dobrze' ? `co najmniej ${r.miesiecy_cel} mies. kosztów krytycznych` : `cel ${r.miesiecy_cel} mies., ${brakuje}`)}
          <div class="dop">kosztów krytycznych (${r.wlaczone.length ? `${esc(r.wlaczone.join(', ').toLowerCase())}: ${zlOkragle(r.koszt_krytyczny)}/mies.` : 'nie wybrano żadnej pozycji, ustaw w Cele'}); gotówka ${zl(s.gotowka)}; przy wszystkich kosztach: ${mies1(r.pokrycie_wszystkich)}</div>
        </a>
        <a class="kafel-st ${o.status}" href="#/rentownosc/klienci">
          <div class="tytul">Obrót do celu rocznego ${pytajnik('obrot')}</div>
          <div class="wartosc">${zl(o.ytd)}</div>
          <div class="pasek-celu"><i data-w="${100 * o.ytd / o.cel}"></i><b data-w="${100 * o.czesc_roku}"></b></div>
          ${chipStatus(o.status, `prognoza na koniec roku ${zl(o.prognoza)}`)}
          <div class="dop">cel ${zl(o.cel)}; na dziś plan ${zl(o.plan_na_dzis)}; do celu trzeba średnio ${zl(o.potrzeba_miesiecznie)} miesięcznie (dotąd ${zl(o.srednio_miesiecznie)})</div>
        </a>
        <a class="kafel-st ${m.status}" href="#/rentownosc">
          <div class="tytul">Marża zysku ${pytajnik('marza')}</div>
          <div class="wartosc">${procent(m.proc)}</div>
          ${chipStatus(m.status, `cel ${procent(m.cel_proc)}`)}
          <div class="dop">wynik zarządczy z pełnych miesięcy ${zl(m.wynik_pelne)}; w tym tempie rok zamknie się wynikiem ok. ${zl(m.prognoza_wynik)} przy celu ${zl(m.cel_zysk)}</div>
        </a>
        <a class="kafel-st ${n.status}" href="#/platnosci/naleznosci?po_terminie=1">
          <div class="tytul">Należności po 30 dniach ${pytajnik('naleznosci')}</div>
          <div class="wartosc">${zl(n.po_30_dniach)}</div>
          ${chipStatus(n.status, `${procent(n.po_30_proc)} wszystkich należności`)}
          <div class="dop">należności razem ${zl(n.razem)}; zielono, gdy po 30 dniach jest najwyżej 15%</div>
        </a>
      </div>
      ${kafleNaleznosci(s.naleznosci, true)}
      <div class="wykresy-2">
        <div class="karta-wyk"><h3>Gotówka na rachunkach ${pytajnik('gotowka')}</h3><div class="pod">główny i online, koniec dnia; najedź, żeby zobaczyć dzień</div><div id="pulpit-gotowka"></div></div>
        <div class="karta-wyk"><h3>Wynik zarządczy miesięcznie ${pytajnik('wynik')}</h3><div class="pod">kliknij miesiąc, żeby zobaczyć jego wydatki</div><div id="pulpit-wynik"></div></div>
      </div>
      <p class="notka">Rachunki: główny ${zl(s.salda['główny']?.saldo_po || 0)}, online ${zl(s.salda.online?.saldo_po || 0)}, VAT ${zl(s.salda.VAT?.saldo_po || 0)} (VAT nie liczy się do gotówki).
        Dane: ${s.liczby.operacje} operacji w banku, ${s.liczby.faktury} faktur, ${s.liczby.zakupy} dokumentów kosztowych. <a href="#/platnosci/importy">Historia importów</a></p>`;
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

function kafleNaleznosci(n, tylkoWiekowanie = false) {
  if (!n) return '';
  const p = n.przedzialy;
  return `${tylkoWiekowanie ? `<h2 class="sekcja">Należności wg terminu ${pytajnik('naleznosci')}</h2>` : `<div class="kafle">
      <div class="kafel"><div class="tytul">Należności razem</div><div class="wartosc">${zl(n.razem)}</div>
        <div class="dop">faktury nieopłacone w banku, stan na ${dataPl(n.dzien_stanu)}</div></div>
      <a class="kafel klik" href="#/platnosci/naleznosci?po_terminie=1"><div class="tytul">Po terminie</div><div class="wartosc minus">${zl(n.po_terminie)}</div>
        <div class="dop">${n.nabywcy_po_terminie.length} nabywców, najstarsza ${Math.max(0, ...n.nabywcy_po_terminie.map(x => x.najstarsza))} dni</div></a>
      <a class="kafel klik" href="#/platnosci/do-polaczenia"><div class="tytul">Wpłaty do połączenia</div><div class="wartosc">${n.do_polaczenia}</div>
        <div class="dop">wpływy, których aplikacja nie umie przypisać</div></a>
      <a class="kafel klik" href="#/platnosci/do-weryfikacji"><div class="tytul">Do weryfikacji</div><div class="wartosc">${n.do_weryfikacji}</div>
        <div class="dop">dopasowania do potwierdzenia i rozjazdy z Fakturownią</div></a>
    </div>`}
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
    // kilka faktur jednej wpłaty: jedna seria w pliku zmian (wszystko albo nic, cofnięcie całości)
    await zmiana('seria', { wpisy: prawd.map(n => ({ typ: a, dane: { operacja: o.klucz, faktura: n } })) });
  });
}

// Kilka wpisów z rzędu (np. potwierdzenie dopasowania do 3 faktur): wszystkie poza ostatnim bez przerysowania.
async function zmianaCicha(typ, dane) {
  const r = await fetch('/api/zmiana', { method: 'POST', headers: { 'X-Finanse': '1', 'Content-Type': 'application/json' }, body: JSON.stringify({ typ, dane }) });
  if (!r.ok) { komunikat((await r.json().catch(() => ({}))).blad || 'Nie udało się zapisać.', true); return false; }
  return true;
}

// ---------- Etap 3: klienci, wydatki, reguły ----------
const RODZAJE = { przenoszony: 'koszt klienta', staly: 'koszt stały', praca: 'koszty pracy', podatki: 'podatki', vat: 'VAT',
  dywidenda: 'podział zysku', zwrot: 'zwrot dla klienta', zwrocony: 'zakup zwrócony', nieprzypisany: 'nieprzypisany' };
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
  const kor = document.createElement('div');
  kor.innerHTML = `<h3>Korekta wpisana ręcznie</h3><p class="szary">Gdy eksport z Fakturowni nie ma korekty. Pomniejsza należność tej faktury; korekta z eksportu o tym samym numerze ma pierwszeństwo.</p>
    <div class="formularz">${pole('', 'Numer korekty', '<input id="kor-numer" placeholder="FK2026/08/1">')}${pole('', 'Kwota brutto korekty (zł)', '<input id="kor-kwota" inputmode="decimal">')}</div>
    <div class="akcje"><button id="zapisz-korekte">Dodaj korektę</button></div>`;
  k.insertBefore(kor, $('.zrodlo', k));
  $('#zapisz-korekte').onclick = () => {
    const kw = Math.round(parseFloat($('#kor-kwota').value.replace(/\s/g, '').replace(',', '.')) * 100);
    if (!$('#kor-numer').value.trim() || !(kw > 0)) return komunikat('Podaj numer i kwotę korekty.', true);
    zmiana('korekta', { numer: $('#kor-numer').value.trim(), faktura: x.numer, kwota: String(kw) });
  };
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

// Lista klientów i karta klienta: web/klienci.js (pakiet 11).
Object.assign(WIDOKI, {
  async 'budzet/reguly'() {
    const lista = await api('reguly');
    const nazwy = { klient_nip: 'Nabywca należy do klienta', klient_faktura: 'Faktura należy do klienta', konto_reklamowe: 'Konto reklamowe należy do klienta', koszt_regula: 'Kontrahent: rodzaj kosztu', koszt_operacja: 'Jedna płatność' };
    const wiersze = lista.map((x, i) => `<tr><td>${esc(nazwy[x.typ])}</td><td>${esc(x.klucz)}</td><td>${esc(x.wartosc)}</td>
      <td class="akcje-wiersz"><button data-i="${i}">Cofnij</button></td></tr>`).join('');
    setTimeout(() => document.querySelectorAll('button[data-i]').forEach(b => b.onclick = () => zmiana('cofnij', { wpis: lista[b.dataset.i].wpis })));
    return `<h1>Reguły przypisań</h1><div class="okruszki">Budżet / Ustawienia</div>
      <p class="notka">Twoje decyzje o klientach i rodzajach kosztów. Wygrywają z podpowiedziami z Budget Studio. Zapisane w pliku zmian tego Maca, drugi Mac widzi je po synchronizacji iCloud.</p>
      ${lista.length ? `<div class="tabela-ramka niska"><table><thead><tr><th>Rodzaj reguły</th><th>Kogo dotyczy</th><th>Przypisanie</th><th></th></tr></thead><tbody>${wiersze}</tbody></table></div>` : '<div class="pusto">Brak reguł. Dodasz je z karty wydatku albo faktury.</div>'}`;
  },
});

// ---------- Wykresy na ekranach ----------
const KOLOR = { obrot: '--s1', przenoszony: '--s2', praca: '--s3', staly: '--s4', nieprzypisany: '--szary-seria' };
const ostatniDzien = m => { const [r, mm] = m.split('-').map(Number); return `${m}-${String(new Date(r, mm, 0).getDate()).padStart(2, '0')}`; };
const MIES_PELNE = ['styczeń', 'luty', 'marzec', 'kwiecień', 'maj', 'czerwiec', 'lipiec', 'sierpień', 'wrzesień', 'październik', 'listopad', 'grudzień'];
const miesPelny = m => `${MIES_PELNE[+m.slice(5, 7) - 1]} ${m.slice(0, 4)}`;

function wykresWyniku(id, d, { tylkoWynik = false } = {}) {
  const w = Object.fromEntries(d.wiersze.map(x => [x.klucz, x]));
  const wart = (k, minus = false) => d.miesiace.map(m => (minus ? -1 : 1) * (w[k].miesiace[m] || 0));
  const niepelne = d.miesiace.map((m, i) => d.niepelne.includes(m) ? i : -1).filter(i => i >= 0);
  const naKlik = i => { location.hash = `#/budzet/wydatki?od=${d.miesiace[i]}-01&do=${ostatniDzien(d.miesiace[i])}`; };
  const wspolne = { kategorie: d.miesiace.map(mies), etykietyPelne: d.miesiace.map(miesPelny), niepelne, naKlik };
  if (!tylkoWynik) Wykresy.slupki($(`#${id}-obrot`), { ...wspolne, wysokosc: 250, opis: 'Obrót i koszty miesięcznie',
    sumaStosu: { koszty: 'Koszty razem' },
    serie: [
      { klucz: 'obrot', nazwa: 'Obrót netto', kolor: Wykresy.kolor(KOLOR.obrot), wartosci: wart('obrot') },
      { klucz: 'przenoszony', nazwa: 'Koszty klientów', kolor: Wykresy.kolor(KOLOR.przenoszony), wartosci: wart('przenoszony', true), stos: 'koszty' },
      { klucz: 'praca', nazwa: 'Koszty pracy', kolor: Wykresy.kolor(KOLOR.praca), wartosci: wart('praca', true), stos: 'koszty' },
      { klucz: 'staly', nazwa: 'Koszty stałe', kolor: Wykresy.kolor(KOLOR.staly), wartosci: wart('staly', true), stos: 'koszty' },
      { klucz: 'nieprzypisany', nazwa: 'Nieprzypisane', kolor: Wykresy.kolor(KOLOR.nieprzypisany), wartosci: wart('nieprzypisany', true), stos: 'koszty' },
    ] });
  Wykresy.slupki($(`#${id}-wynik`), { ...wspolne, wysokosc: tylkoWynik ? 220 : 250, opis: 'Wynik zarządczy miesięcznie',
    serie: [{ klucz: 'wynik', nazwa: 'Wynik zarządczy', bezLegendy: true, kolor: Wykresy.kolor('--s1'), kolorUjemny: Wykresy.kolor('--minus'), wartosci: wart('wynik') }] });
}

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
    setTimeout(() => {
      document.querySelectorAll('.pasek-celu [data-w]').forEach(x => { x.style[x.tagName === 'I' ? 'width' : 'left'] = `${x.dataset.w}%`; });
      wykresWyniku('rent', d);
    });
    return `<h1>Wynik zarządczy</h1><div class="okruszki">Rentowność / ${d.rok}, stan na ${dataPl(d.dzien_stanu)}</div>
      ${filtrRoku(d)}
      <div class="kafle">${pasek('Obrót netto od początku roku', d.obrot, c.obrot)}${pasek('Wynik zarządczy od początku roku', d.wynik, c.zysk)}
        <div class="kafel"><div class="tytul">Marża wyniku ${pytajnik('marza')}</div><div class="wartosc">${procent(d.marza_proc)}</div><div class="dop">wynik zarządczy do obrotu netto</div></div></div>
      <div class="wykresy-2">
        <div class="karta-wyk"><h3>Obrót i koszty ${pytajnik('obrot_koszty')}</h3><div class="pod">lewy słupek obrót, prawy koszty; legenda ukrywa serie</div><div id="rent-obrot"></div></div>
        <div class="karta-wyk"><h3>Wynik zarządczy ${pytajnik('wynik')}</h3><div class="pod">czerwony to strata; kliknij miesiąc, żeby zobaczyć wydatki</div><div class="wyk-odstep"></div><div id="rent-wynik"></div></div>
      </div>
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
    setTimeout(() => Wykresy.ranking($('#klienci-wyk'), {
      serie: [{ klucz: 'obrot', nazwa: 'Obrót netto', kolor: Wykresy.kolor('--s1') }, { klucz: 'koszty', nazwa: 'Koszty klienta', kolor: Wykresy.kolor('--s2') }],
      wiersze: d.klienci.map(k => ({ nazwa: k.klient, wartosci: { obrot: k.obrot, koszty: k.koszty }, marza: k.marza_proc, udzial: k.udzial,
        naKlik: () => { location.hash = `#/budzet/klient?nazwa=${encodeURIComponent(k.klient)}&rok=${d.rok}`; } })),
      opisWiersza: w => `${tys(w.wartosci.obrot)} zł · marża ${procent(w.marza)}` }));
    return `<h1>Obroty wg klientów</h1><div class="okruszki">Rentowność / ${d.rok}</div>${filtrRoku({ rok: d.rok, lata: d.lata || [d.rok] })}
      <div class="karta-wyk"><h3>Klienci wg obrotu</h3><div class="pod">kliknij klienta, żeby otworzyć jego folder</div><div id="klienci-wyk"></div></div>
      <div class="tabela-ramka niska"><table class="miesiace"><thead><tr><th>Klient</th>${th}<th class="liczba-kol">Obrót</th><th class="liczba-kol">Udział</th>
        <th class="liczba-kol">Koszty klienta</th><th class="liczba-kol">Po kosztach</th><th class="liczba-kol">Marża</th></tr></thead><tbody>${tr}</tbody></table></div>
      <p class="notka">Obrót netto z faktur wg daty sprzedaży. Marża przed kosztami pracy zespołu; czerwona poniżej progu 30%. Podział czasu zespołu na klientów to dalszy krok, po MVP.</p>`;
  },

  async 'rentownosc/koszty'(p) {
    const d = await api('koszty-kategorii', p);
    const { th, tr } = tabelaMiesiecy(d.miesiace, d.pozycje.map(x => ({ nazwa: d.rodzaj ? x.nazwa : (RODZAJE[x.klucz] || x.klucz),
      miesiace: x.miesiace, razem: x.razem, link: d.rodzaj ? `#/budzet/wydatki?q=${encodeURIComponent(x.nazwa.split(' ')[0])}` : `#/rentownosc/koszty?rodzaj=${x.klucz}&rok=${d.rok}` })));
    setTimeout(() => {
      const top = d.pozycje.slice(0, 4), reszta = d.pozycje.slice(4);
      const serie = top.map((x, i) => ({ klucz: x.klucz, nazwa: d.rodzaj ? x.nazwa.split(/\s{2,}| \d/)[0].slice(0, 40) : (RODZAJE[x.klucz] || x.klucz),
        kolor: Wykresy.kolor(d.rodzaj ? `--s${i + 1}` : (KOLOR[x.klucz] || '--szary-seria')), wartosci: d.miesiace.map(m => x.miesiace[m] || 0), stos: 'k' }));
      if (reszta.length) serie.push({ klucz: 'reszta', nazwa: d.rodzaj ? `Pozostali (${reszta.length})` : 'Pozostałe rodzaje', kolor: Wykresy.kolor('--szary-seria'),
        wartosci: d.miesiace.map(m => reszta.reduce((a, x) => a + (x.miesiace[m] || 0), 0)), stos: 'k' });
      Wykresy.slupki($('#koszty-wyk'), { kategorie: d.miesiace.map(mies), etykietyPelne: d.miesiace.map(miesPelny), wysokosc: 260, serie,
        sumaStosu: { k: 'Razem' }, opis: 'Koszty wg kategorii',
        naKlik: i => { location.hash = `#/budzet/wydatki?od=${d.miesiace[i]}-01&do=${ostatniDzien(d.miesiace[i])}${d.rodzaj ? '&rodzaj=' + d.rodzaj : ''}`; } });
    });
    return `<h1>Koszty wg kategorii</h1><div class="okruszki"><a href="#/rentownosc/koszty">Rentowność / Koszty</a>${d.rodzaj ? ' / ' + esc(RODZAJE[d.rodzaj]) : ''} / ${d.rok}</div>
      <div class="filtry">${filtr('rodzaj', 'Rodzaj', [['', 'Wszystkie rodzaje'], ...Object.entries(RODZAJE)], d.rodzaj || '')}</div>
      <div class="karta-wyk"><h3>${d.rodzaj ? esc(RODZAJE[d.rodzaj]) + ': największych 4 kontrahentów' : 'Koszty miesięcznie wg rodzaju'}</h3><div class="pod">kliknij miesiąc, żeby zobaczyć wydatki; legenda ukrywa serie</div><div id="koszty-wyk"></div></div>
      <div class="tabela-ramka niska"><table class="miesiace"><thead><tr><th>${d.rodzaj ? 'Kontrahent' : 'Rodzaj'}</th>${th}<th class="liczba-kol">Razem</th></tr></thead><tbody>${tr}</tbody></table></div>
      <p class="notka">Kwoty dodatnie to wydatki. Netto z dokumentu, gdy jest w rejestrze biura, inaczej kwota z banku.</p>`;
  },

  async 'rentownosc/vat'(p) {
    const d = await api('vat', p);
    const tr = d.miesiace.map(m => m.tylko_prognoza ? `<tr class="szary"><td>${mies(m.miesiac)}</td><td colspan="5" class="szary">jeszcze bez faktur i przelewów</td>
      <td class="liczba-kol sep">${m.prognoza != null ? zl(m.prognoza, false) : ''}</td><td class="liczba-kol">${m.od_biura != null ? zl(m.od_biura, false) : ''}</td><td></td></tr>`
      : `<tr><td>${mies(m.miesiac)}</td><td class="liczba-kol">${zl(m.nalezny, false)}</td>
      <td class="liczba-kol">${m.rejestr ? zl(m.naliczony, false) : '<span class="szary">brak rejestru</span>'}</td>
      <td class="liczba-kol">${m.rejestr ? zl(m.do_zaplaty, false) : ''}</td><td class="liczba-kol">${zl(m.zaplacony, false)}</td>
      <td class="liczba-kol${m.rejestr && Math.abs(m.zaplacony - m.do_zaplaty) > 10000 ? ' minus' : ' szary'}">${m.rejestr ? zl(m.zaplacony - m.do_zaplaty, false) : ''}</td>
      <td class="liczba-kol sep">${m.prognoza != null ? zl(m.prognoza, false) : ''}</td><td class="liczba-kol">${m.od_biura != null ? zl(m.od_biura, false) : ''}</td>
      <td class="liczba-kol${m.roznica_biuro && Math.abs(m.roznica_biuro) > 10000 ? ' minus' : ' szary'}">${m.roznica_biuro != null ? zl(m.roznica_biuro, false) : ''}</td></tr>`).join('');
    return `<h1>Podatek VAT ${pytajnik('vat')}</h1><div class="okruszki">Rentowność / ${d.rok}</div>${filtrRoku(d)}
      <div class="tabela-ramka niska"><table><thead><tr><th>Okres</th><th class="liczba-kol">Należny (faktury)</th><th class="liczba-kol">Naliczony (rejestr biura)</th>
        <th class="liczba-kol">Wychodzi do zapłaty</th><th class="liczba-kol">Zapłacono (bank)</th><th class="liczba-kol">Różnica</th>
        <th class="liczba-kol sep">Prognoza z budżetu</th><th class="liczba-kol">Kwota od biura</th><th class="liczba-kol">Różnica prognozy</th></tr></thead><tbody>${tr}</tbody></table></div>
      <p class="notka">Szacunek kontrolny, nie deklaracja: należny z faktur wg daty sprzedaży, naliczony z rejestru krajowego biura (bez importu usług), zapłata przypisana do okresu z tytułu przelewu („26M07”). Czerwona różnica ponad 100 zł to temat do pytania biura. Rejestr biura kończy się ${dataPl(d.koniec_rejestru)}.
        Trzy ostatnie kolumny: prognoza VAT z budżetu (arkusz Opłaty urzędowe), kwota od biura i różnica między nimi (plus: prognoza wyższa niż biuro). Kwotę od biura wpiszesz w <a href="#/budzet/podatki">Podatki i ZUS</a>.</p>`;
  },
});

// ---------- Statusy, cele, pomoc ----------
const STATUS = { dobrze: ['✓', 'w normie'], uwaga: ['!', 'uwaga'], zle: ['✕', 'poniżej celu'], brak: ['?', 'brak danych'] };
const chipStatus = (st, tekst) => `<div class="chip-st ${st}"><b aria-hidden="true">${STATUS[st][0]}</b><span>${esc(STATUS[st][1])}</span><small>${esc(tekst)}</small></div>`;

// Kwota w pełnych złotych (kafle, tabela rezerwy): 47 700 zł.
const zlOkragle = gr => `${zl(Math.round(gr / 100) * 100, false).replace(/,00$/, '')} zł`;
// Pole „zł miesięcznie” na grosze: puste = null (średnia z banku), inaczej liczba ≥ 0; zły tekst = undefined.
function groszeZPola(tekst) {
  const t = tekst.replace(/\s/g, '').replace(',', '.');
  if (!t) return null;
  if (!/^\d+(\.\d{1,2})?$/.test(t)) return undefined;
  const [c, u = ''] = t.split('.');
  return Number(c) * 100 + Number(u.padEnd(2, '0'));
}

function tabelaRezerwy(r) {
  const tr = r.pozycje.map(p => `<tr data-poz="${p.klucz}"><td><label class="przelacznik"><input type="checkbox" data-wl ${p.wlaczona ? 'checked' : ''} aria-label="Wchodzi do rezerwy: ${esc(p.nazwa)}"><span class="suwak"></span>
      <span><b>${esc(p.nazwa)}</b><br><small class="szary">${esc(p.opis)}</small></span></label></td>
    <td class="liczba-kol">${zlOkragle(p.srednia)}</td>
    <td class="liczba-kol"><input data-kw inputmode="decimal" placeholder="średnia" aria-label="Kwota własna: ${esc(p.nazwa)}"
      value="${p.kwota_wlasna == null ? '' : zl(p.kwota_wlasna, false).replace(/,00$/, '')}"></td>
    <td class="liczba-kol" data-liczona>${p.wlaczona ? zlOkragle(p.liczona) : '<span class="szary">nie wchodzi</span>'}</td></tr>`).join('');
  return `<div class="tabela-ramka niska"><table class="tabela-rezerwy"><thead><tr><th>Pozycja</th><th class="liczba-kol">Średnia z banku</th>
    <th class="liczba-kol">Kwota własna (zł/mies.)</th><th class="liczba-kol">Liczona kwota</th></tr></thead><tbody>${tr}</tbody>
    <tfoot><tr><td>Koszt krytyczny miesięcznie</td><td></td><td></td><td class="liczba-kol" id="rez-suma">${zlOkragle(r.koszt_krytyczny)}</td></tr></tfoot></table></div>`;
}

function kartaCelow(cele, r) {
  const k = $('#karta');
  k.innerHTML = `<button class="zamknij" aria-label="Zamknij">×</button><h2>Cele</h2>
    <p class="szary">Na nich opierają się kolory na pulpicie. Zapis idzie do pliku zmian tego Maca, więc drugi Mac zobaczy te same cele.</p>
    <div class="formularz">
      ${pole('', 'Obrót netto w roku (zł)', `<input id="cel-obrot" inputmode="numeric" value="${Math.round(cele.cel_obrot_rok / 100)}">`)}
      ${pole('', 'Marża zysku na czysto (%)', `<input id="cel-marza" inputmode="decimal" value="${String(cele.cel_marza_proc).replace('.', ',')}">`)}
    </div>
    ${r ? `<h3>Rezerwa gotówki na koszty krytyczne ${pytajnik('rezerwa')}</h3>
    <p class="szary">Zaznacz koszty, których nie możesz nie zapłacić. Średnia z banku to ${r.okno.length} pełnych miesięcy (${esc(mies(r.okno[0]))} do ${esc(mies(r.okno[r.okno.length - 1]))}). Kwota własna zastępuje średnią; puste pole = średnia.</p>
    ${tabelaRezerwy(r)}
    <div class="formularz">
      ${pole('', 'Rezerwa gotówki (miesięcy kosztów krytycznych)', `<input id="cel-rezerwa" inputmode="decimal" value="${String(cele.rezerwa_miesiecy).replace('.', ',')}">`)}
      ${pole('', 'Kontrahenci księgowości (po przecinku)', `<input id="rez-ksiegowosc" list="rez-kontrahenci" value="${esc(r.ksiegowosc.join(', '))}">
        <datalist id="rez-kontrahenci">${r.kontrahenci_stali.map(x => `<option value="${esc(x)}">`).join('')}</datalist>`)}
    </div>
    <p id="rez-wynik">wymagana rezerwa <b>${zl(r.wymagana)}</b> (${String(r.miesiecy_cel).replace('.', ',')} mies. × ${zlOkragle(r.koszt_krytyczny)}); gotówka ${zl(r.gotowka)} wystarcza na <b>${r.pokrycie_miesiecy == null ? 'brak' : String(r.pokrycie_miesiecy).replace('.', ',') + ' mies.'}</b> kosztów krytycznych${r.nadwyzka < 0 ? `, brakuje ${zl(-r.nadwyzka)}` : `, ponad cel ${zl(r.nadwyzka)}`}.</p>`
    : `<div class="formularz">${pole('', 'Rezerwa gotówki (miesięcy kosztów)', `<input id="cel-rezerwa" inputmode="decimal" value="${String(cele.rezerwa_miesiecy).replace('.', ',')}">`)}</div>`}
    <div class="akcje"><button class="glowny" id="zapisz-cele">Zapisz</button></div>
    <p class="szary">${pytajnik('cele')} Jak cele przekładają się na kolory: rezerwa zielona od pełnej liczby miesięcy, żółta od 2/3; obrót zielony, gdy prognoza na koniec roku sięga celu, żółty od 90%; marża zielona od celu, żółta od połowy.</p>`;
  k.hidden = false;
  $('.zamknij', k).onclick = () => { k.hidden = true; };
  // Podgląd sumy na żywo (przed zapisem): włączone pozycje, kwota własna albo średnia.
  const przelicz = () => {
    let suma = 0;
    for (const p of r?.pozycje || []) {
      const w = $(`tr[data-poz="${p.klucz}"]`, k), wl = $('[data-wl]', w).checked, kw = groszeZPola($('[data-kw]', w).value);
      const liczona = kw == null ? p.srednia : kw;
      $('[data-liczona]', w).innerHTML = !wl ? '<span class="szary">nie wchodzi</span>' : kw === undefined ? '<span class="minus">zła kwota</span>' : zlOkragle(liczona);
      if (wl && kw !== undefined) suma += liczona;
    }
    if (r) $('#rez-suma').textContent = zlOkragle(suma);
  };
  k.querySelectorAll('.tabela-rezerwy input').forEach(x => { x.oninput = przelicz; });
  $('#zapisz-cele').onclick = async () => {
    const liczba = s => s.replace(/\s/g, '').replace(',', '.');
    const wpisy = [['cel_obrot_rok', String(Math.round(parseFloat(liczba($('#cel-obrot').value)) * 100))],
      ['cel_marza_proc', liczba($('#cel-marza').value)], ['rezerwa_miesiecy', liczba($('#cel-rezerwa').value)]]
      .filter(([kl, v]) => String(cele[kl]) !== v && String(Math.round(cele[kl] * 100) / 100) !== v)
      .map(([kl, v]) => ['cel', { klucz: kl, wartosc: v }]);
    if (r) {
      const pozycje = {};
      for (const p of r.pozycje) {
        const w = $(`tr[data-poz="${p.klucz}"]`, k), wl = $('[data-wl]', w).checked, kw = groszeZPola($('[data-kw]', w).value);
        if (kw === undefined) { komunikat(`${p.nazwa}: kwota własna to liczba złotych albo puste pole.`, true); return; }
        const zm = {};
        if (wl !== p.wlaczona) zm.wlaczona = wl;
        if (kw !== p.kwota_wlasna) zm.kwota = kw;
        if (Object.keys(zm).length) pozycje[p.klucz] = zm;
      }
      const ksieg = $('#rez-ksiegowosc').value.split(',').map(x => x.trim().toLowerCase()).filter(Boolean);
      const dane = Object.keys(pozycje).length ? { pozycje } : {};
      if (ksieg.join('|') !== r.ksiegowosc.join('|')) dane.ksiegowosc = ksieg;
      if (Object.keys(dane).length) wpisy.push(['rezerwa', dane]);
    }
    if (!wpisy.length) { k.hidden = true; return; }
    for (const [typ, d] of wpisy.slice(0, -1)) if (!(await zmianaCicha(typ, d))) return;
    zmiana(...wpisy[wpisy.length - 1]);
  };
}

const POMOC = {
  kafle_bs: { tytul: 'Kafle płatności', krotko: 'Sześć list jak w Budget Studio: górna linia wpływy, dolna obciążenia; kwota brutto, liczba płatności i strzałka do listy.',
    co: 'Nadal nieopłacone: przychody wystawione, a nie zapłacone. Nadal niewystawione: plany przychodów bez faktury, których miesiąc już trwa albo minął. Po terminie: plany i dokumenty po terminie płatności. Do wystawienia i Do zapłacenia: najbliższe 2 tygodnie. Zapłacone: ostatnie 2 tygodnie.',
    skad: 'Plany z budżetu połączone z bankiem i Fakturownią (te same warunki co listy w menu Płatności).',
    jak: 'Kwota skrócona (60k = ok. 60 tys. zł brutto); pełna kwota po najechaniu. Pasek w tle pokazuje wielkość kwoty na tle pozostałych kafli. Czerwona kropka: wymaga uwagi; zielony ptaszek: zapłacone.',
    zrob: 'Kliknij linię, żeby otworzyć listę płatności tego rodzaju.' },
  cf_pulpit: { tytul: 'Cash flow 6 miesięcy w przód', krotko: 'Tygodniowe wpływy i obciążenia z saldem narastającym, od 5 tygodni wstecz do pół roku w przód.',
    co: 'Zielone słupki w górę to wpływy, czerwone w dół obciążenia, kreskowany słupek to saldo tygodnia, linia to saldo gotówki narastająco. Pomarańczowa linia: tydzień dnia stanu.',
    skad: 'Przed dniem stanu przepływy z banku, po nim prognoza (należności z faktur i plany z budżetu, scenariusz ostrożny).',
    jak: 'Tydzień od wtorku do poniedziałku, jak w Budget Studio. Jaśniejsza część słupka to plany, pełna to dokumenty i bank.',
    zrob: 'Kliknij wykres, żeby otworzyć pełny ekran Cash flow.' },
  rezerwa: { tytul: 'Rezerwa gotówki', krotko: 'Na ile miesięcy kosztów krytycznych wystarczy gotówka, gdyby wpłaty od klientów stanęły.',
    co: 'Koszty krytyczne to te, których nie możesz nie zapłacić. Domyślnie wynagrodzenia (pensje, ZUS, PIT, PPK, Medicover) i księgowość. Sam wybierasz, co wchodzi: w Cele zaznaczasz pozycje (też narzędzia, podatki, koszty klientów, nieprzypisane).',
    skad: 'Gotówka: saldo rachunku głównego i online z ostatniej operacji w eksporcie ING. Koszty: średnia miesięczna z banku z 6 ostatnich pełnych miesięcy, bez VAT, podziału zysku, zwrotów i przelewów między własnymi rachunkami. Księgowość to koszty stałe kontrahentów z listy w Cele.',
    jak: 'Koszt krytyczny = suma zaznaczonych pozycji; przy każdej możesz wpisać własną kwotę miesięczną, która zastępuje średnią (puste pole = średnia). Wymagana rezerwa = koszt krytyczny razy liczba miesięcy z celu. Zielony od pełnej liczby miesięcy, żółty od 2/3. W opisie kafla dla porównania: na ile starczy przy wszystkich kosztach.',
    zrob: 'Czerwony: wstrzymać wydatki niepilne, przyspieszyć windykację (kafel należności), nie wypłacać zysku. Pozycje, kwoty i liczbę miesięcy ustawiasz przyciskiem Cele.' },
  obrot: { tytul: 'Obrót do celu rocznego', krotko: 'Obrót netto z faktur od początku roku, plan na dziś i prognoza na koniec roku.',
    co: 'Ile zafakturowaliśmy netto od 1 stycznia, ile powinno być przy równym tempie przez cały rok (pomarańczowa kreska na pasku) i dokąd dojdziemy w obecnym tempie.',
    skad: 'Faktury z eksportu Fakturowni wg daty sprzedaży, korekty ze znakiem minus.',
    jak: 'Prognoza = średni obrót z pełnych miesięcy razy 12. Bieżący i poprzedni miesiąc nie liczą się do średniej, bo faktury za nie jeszcze spływają. Zielony, gdy prognoza sięga celu, żółty od 90% celu.',
    zrob: 'Kliknij kafel, żeby zobaczyć, którzy klienci robią obrót. Kwota „trzeba średnio miesięcznie” mówi, ile musi wpadać do końca roku.' },
  marza: { tytul: 'Marża zysku', krotko: 'Wynik zarządczy jako procent obrotu, z pełnych miesięcy, kontra cel.',
    co: 'Ile z każdej złotówki obrotu zostaje po wszystkich kosztach w wyniku: klientów, pracy, stałych i nieprzypisanych.',
    skad: 'Ekran Rentowność, wynik zarządczy. Koszty z dokumentem liczone netto wg daty dokumentu, koszty pracy wg miesiąca, którego dotyczą.',
    jak: 'Tylko pełne miesiące. Zielona od celu, żółta od połowy celu. To wynik przed podatkiem dochodowym i bez dotacji.',
    zrob: 'Kliknij kafel: tabela pokaże, który miesiąc i który rodzaj kosztów ciągnie wynik w dół.' },
  naleznosci: { tytul: 'Należności po 30 dniach', krotko: 'Ile pieniędzy od klientów wisi ponad 30 dni po terminie.',
    co: 'Faktury nieopłacone w banku, ponad 30 dni po terminie płatności, i ich udział we wszystkich należnościach.',
    skad: 'Faktury z Fakturowni połączone z wpłatami z banku (ekrany Do połączenia i Do weryfikacji).',
    jak: 'Liczone na ostatni dzień eksportu z ING. Zielony do 15% należności, żółty do 30%.',
    zrob: 'Kliknij kafel: lista dłużników od największej kwoty. Zanim zadzwonisz, sprawdź Do weryfikacji, czy wpłata nie wisi niepołączona.' },
  porzadek: { tytul: 'Porządek w danych', krotko: 'Rzeczy, które aplikacja zostawiła do Twojej decyzji. Im mniej, tym dokładniejsze liczby.',
    co: 'Wpłaty bez faktury, dopasowania do potwierdzenia, wydatki bez rodzaju, plany nieaktualne (minął ich dzień, a dokumentu brak) i wiersze budżetu z podejrzanymi ustawieniami.',
    skad: 'Wynik automatycznego łączenia wpłat z fakturami i wydatków z rodzajami kosztów.',
    jak: 'Każda Twoja decyzja zapisuje się w pliku zmian i obowiązuje także dla przyszłych danych (reguły dla kontrahenta).',
    zrob: 'Raz w tygodniu przejrzyj linki w żółtym pasku. Reguła dla kontrahenta załatwia od razu wszystkie jego płatności.' },
  laczenie: { tytul: 'Łączenie z budżetem', krotko: 'Faktura albo przelew trafia do budżetu dopiero, gdy połączysz go z planem.',
    co: 'Dokument bez planu czeka na liście Do połączenia. Apka podpowiada najlepiej pasujący plan (arkusz, wiersz, miesiąc), a Ty klikasz Połącz. Nic nie łączy się samo.',
    skad: 'Faktury z Fakturowni, dokumenty z rejestru biura i przelewy z ING kontra plany w arkuszach.',
    jak: 'Podpowiedź bierze pod uwagę kontrahenta, kwotę i datę. Po połączeniu dokument zastępuje plan: komórka pokazuje kwotę z dokumentu, a różnicę widać od razu.',
    zrob: 'Raz w tygodniu opróżnij listę Do połączenia. Gdy podpowiedź nie pasuje, wybierz plan ręcznie albo przenieś pozycję do Do weryfikacji.' },
  vat: { tytul: 'Podatek VAT', krotko: 'Kontrola VAT miesiąc po miesiącu: z faktur, od biura i z banku.',
    co: 'Należny VAT z faktur sprzedaży, naliczony z rejestru biura, ile wychodzi do zapłaty i ile poszło przelewem. W trzech ostatnich kolumnach prognoza z budżetu, kwota od biura i różnica między nimi.',
    skad: 'Fakturownia, rejestr zakupów biura, wyciąg ING i prognoza VAT z budżetu (Podatki i ZUS).',
    jak: 'Różnica prognozy: plus znaczy, że budżet przewidział więcej niż wyszło u biura. Miesiące bez faktur pokazują tylko prognozę.',
    zrob: 'Czerwona różnica ponad 100 zł to temat do sprawdzenia: stawka VAT w wierszu, Księgowane, miesiąc księgowania.' },
  gotowka: { tytul: 'Gotówka na rachunkach', krotko: 'Saldo rachunku głównego i online na koniec każdego dnia.',
    co: 'Linia salda dzień po dniu. Pokazuje, jak gotówka faluje w miesiącu: wpływy od klientów kontra pensje, ZUS, VAT.',
    skad: 'Kolumna „saldo po transakcji” z eksportu ING; dni bez operacji przenoszą saldo z poprzedniego dnia.',
    jak: 'Bez rachunku VAT.', zrob: 'Najdź na dzień, żeby zobaczyć saldo z podziałem na rachunki. Dołki to zwykle 6.–10. (pensje) i 15.–25. (ZUS, VAT).' },
  wynik: { tytul: 'Wynik zarządczy miesięcznie', krotko: 'Obrót minus koszty w wyniku, miesiąc po miesiącu. Czerwony to strata.',
    co: 'Ile zarobiliśmy w danym miesiącu po kosztach klientów, pracy, stałych i nieprzypisanych.',
    skad: 'Faktury (przychód) i wydatki z banku powiązane z rejestrem biura (koszty).',
    jak: 'Przychód wg daty sprzedaży, koszt z fakturą wg daty i netto faktury, koszty pracy wg miesiąca, którego dotyczą. Ostatnie dwa miesiące niepełne (kursywa).',
    zrob: 'Kliknij miesiąc, żeby zobaczyć jego wydatki. Pełna tabela: Rentowność, Wynik zarządczy.' },
  obrot_koszty: { tytul: 'Obrót i koszty', krotko: 'Lewy słupek obrót netto, prawy koszty w rozbiciu na rodzaje.',
    co: 'Porównanie, ile wpadło i na co poszło w każdym miesiącu.', skad: 'Jak w wyniku zarządczym.',
    jak: 'Kliknięcie w legendę ukrywa rodzaj kosztów, skala przelicza się sama.', zrob: 'Kliknij miesiąc, żeby otworzyć wydatki z tego miesiąca.' },
  cele: { tytul: 'Cele', krotko: 'Twoje cele roczne, od których zależą kolory na pulpicie.',
    co: 'Obrót netto w roku, marża zysku na czysto i rezerwa gotówki w miesiącach kosztów.',
    skad: 'Domyślnie z pliku Finanse/Aplikacja/ustawienia.json, zmiany z przycisku Cele w pliku zmian.',
    jak: 'Cel zysku = obrót razy marża.', zrob: 'Zmień, gdy zmieni się plan roczny. Stare wartości zostają w historii pliku zmian.' },
  dane: { tytul: 'Skąd są dane', krotko: 'Pliki z folderu Finanse/Raporty/Dane, bez połączenia z internetem.',
    co: 'Aplikacja czyta eksporty: ING (operacje), Fakturownia (faktury sprzedażowe), biuro (rejestr zakupów, RZiS) i Budget Studio (kopia planów i porównanie w okresie równoległym).',
    skad: 'Nowy plik w folderze Dane wystarczy: aplikacja zauważy go i zaproponuje odświeżenie.',
    jak: 'Baza budowana jest od zera przy każdym odświeżeniu, więc nic się nie dubluje. Twoje decyzje żyją w Finanse/Aplikacja/zmiany.',
    zrob: 'Raz w tygodniu wrzuć świeży eksport z ING i Fakturowni. Historia importów pokazuje, co zostało wczytane.' },
};

function pytajnik(klucz) {
  const p = POMOC[klucz];
  return p ? `<button type="button" class="pomoc-btn" data-pomoc="${klucz}" aria-label="Pomoc: ${esc(p.tytul)}">?</button>` : '';
}

function otworzPomoc(klucz) {
  const panel = $('#pomoc');
  panel.innerHTML = `<button class="zamknij" aria-label="Zamknij pomoc">×</button><h2>Pomoc</h2>` +
    Object.entries(POMOC).map(([k, p]) => `<section id="pomoc-${k}" class="${k === klucz ? 'wybrana' : ''}"><h3>${esc(p.tytul)}</h3>
      <p class="krotko">${esc(p.krotko)}</p><dl><dt>Co to jest</dt><dd>${esc(p.co)}</dd><dt>Skąd dane</dt><dd>${esc(p.skad)}</dd>
      <dt>Jak liczone</dt><dd>${esc(p.jak)}</dd><dt>Co z tym zrobić</dt><dd>${esc(p.zrob)}</dd></dl></section>`).join('');
  panel.hidden = false;
  $('.zamknij', panel).onclick = () => { panel.hidden = true; };
  if (klucz) $(`#pomoc-${klucz}`, panel)?.scrollIntoView({ block: 'start' });
}

// Dymek po najechaniu na „?”, panel po kliknięciu (delegowane, działa na każdym ekranie).
(() => {
  let dymek;
  document.addEventListener('pointerover', e => {
    const b = e.target.closest?.('.pomoc-btn');
    if (!b) return;
    dymek ||= Object.assign(document.createElement('div'), { className: 'pomoc-dymek' });
    dymek.textContent = `${POMOC[b.dataset.pomoc].krotko} Kliknij, żeby otworzyć pomoc.`;
    document.body.appendChild(dymek);
    const r = b.getBoundingClientRect();
    dymek.style.left = `${Math.min(window.innerWidth - 300, r.left)}px`;
    dymek.style.top = `${r.bottom + 6}px`;
  });
  document.addEventListener('pointerout', e => { if (e.target.closest?.('.pomoc-btn') && dymek) dymek.remove(); });
  document.addEventListener('click', e => {
    const b = e.target.closest('.pomoc-btn');
    if (b) { e.preventDefault(); e.stopPropagation(); dymek?.remove(); otworzPomoc(b.dataset.pomoc); }
  }, true);
})();

// ---------- Poprawki z testu 14.10: reguły zbiorcze, konta reklamowe ----------
Object.assign(WIDOKI, {
  async 'budzet/nieprzypisane'() {
    const [grupy, w] = await Promise.all([api('nieprzypisane-grupy'), api('wydatki', { ile: 1 })]);
    const opcje = Object.entries(RODZAJE).filter(([k]) => k !== 'nieprzypisany').map(([v, n]) => `<option value="${v}">${n}</option>`).join('');
    const wiersze = grupy.map((g, i) => `<tr data-i="${i}"><td>${esc(g.przyklad)}<div class="szary">reguła dla: „${esc(g.klucz)}”${g.konto ? `, ${esc(g.konto)} (przypisz w Konta reklamowe)` : ''}</div></td>
      <td class="liczba-kol">${g.ile}</td><td class="liczba-kol minus">${zl(-g.kwota, false)}</td><td>${dataPl(g.ostatnia)}</td>
      <td><select data-rodzaj><option value="">wybierz rodzaj</option>${opcje}</select></td>
      <td><input data-klient list="lista-klientow" placeholder="klient (dla kosztu klienta)"></td>
      <td class="akcje-wiersz"><button data-zapisz>Zapisz regułę</button></td></tr>`).join('');
    setTimeout(() => document.querySelectorAll('tr[data-i]').forEach(tr => {
      const g = grupy[tr.dataset.i];
      $('[data-zapisz]', tr).onclick = () => {
        const rodzaj = $('[data-rodzaj]', tr).value;
        if (!rodzaj) return komunikat('Wybierz rodzaj kosztu.', true);
        zmiana('koszt_regula', { kontrahent: g.klucz, rodzaj, klient: rodzaj === 'przenoszony' ? $('[data-klient]', tr).value.trim() : '' });
      };
    }));
    const suma = grupy.reduce((a, g) => a + g.kwota, 0), ile = grupy.reduce((a, g) => a + g.ile, 0);
    return `<h1>Nieprzypisane wg kontrahenta</h1><div class="okruszki">Budżet / Wydatki z banku</div>
      <p class="notka">${ile} płatności, ${zl(suma)} w ${grupy.length} grupach. Jedna reguła ustawia rodzaj dla wszystkich płatności kontrahenta, także przyszłych. Rodzaj wybierasz Ty; reguły cofniesz w Reguły przypisań.</p>
      ${listaKlientow(w.klienci)}
      <div class="tabela-ramka niska"><table><thead><tr><th>Kontrahent</th><th class="liczba-kol">Płatności</th><th class="liczba-kol">Razem PLN</th><th>Ostatnia</th><th>Rodzaj</th><th>Klient</th><th></th></tr></thead><tbody>${wiersze}</tbody></table></div>`;
  },

  async 'budzet/konta'() {
    const [konta, w] = await Promise.all([api('konta-reklamowe'), api('wydatki', { ile: 1 })]);
    const wiersze = konta.map((k, i) => `<tr data-i="${i}"><td>${esc(k.konto)}</td><td class="liczba-kol">${k.platnosci}</td><td class="liczba-kol minus">${k.suma ? zl(-k.suma, false) : ''}</td>
      <td>${dataPl(k.ostatnia)}</td><td class="szary">${esc(k.podpowiedz || '')}</td>
      <td><input data-klient list="lista-klientow" value="${esc(k.klient ?? k.klient_podpowiedz ?? '')}" placeholder="klient"></td>
      <td class="akcje-wiersz">${k.klient != null ? `<span class="chip plus">przypisane</span>` : ''}<button data-zapisz>${k.klient != null ? 'Zmień' : 'Zatwierdź'}</button></td></tr>`).join('');
    setTimeout(() => document.querySelectorAll('tr[data-i]').forEach(tr => {
      $('[data-zapisz]', tr).onclick = () => zmiana('konto_reklamowe', { konto: konta[tr.dataset.i].konto, klient: $('[data-klient]', tr).value.trim() });
    }));
    return `<h1>Konta reklamowe</h1><div class="okruszki">Budżet / Google Ads i Meta</div>
      <p class="notka">Płatności kartą za reklamy przypisane do kont: Google Ads po numerze w nazwie płatności (ADS1234567890 to konto 123-456-7890), Meta przez fakturę z folderu Faktury (kwota i data). Podpowiedź pochodzi z wykazów faktur i nazw plików. Po zatwierdzeniu wszystkie płatności konta stają się kosztem tego klienta. Puste pole klienta i Zatwierdź: konto agencji, bez klienta.</p>
      ${listaKlientow(w.klienci)}
      <div class="tabela-ramka niska"><table><thead><tr><th>Konto</th><th class="liczba-kol">Płatności</th><th class="liczba-kol">Razem PLN</th><th>Ostatnia</th><th>Podpowiedź</th><th>Klient</th><th></th></tr></thead><tbody>${wiersze}</tbody></table></div>`;
  },
});

// Adres, którego apka nie zna (np. stary link): komunikat zamiast pustego ekranu.
function nieznanyEkran(sekcja) {
  const nazwa = MENU.find(m => m.id === sekcja)?.nazwa || sekcja;
  return `<h1>${esc(nazwa)}</h1><div class="okruszki">Nie ma takiego ekranu</div><p class="notka">Ten adres nie prowadzi do żadnego ekranu. Wybierz pozycję z menu po lewej.</p>`;
}

let ostatniKlucz = '';
async function pokaz() {
  const t = trasa();
  const klucz = t.podstrona ? `${t.sekcja}/${t.podstrona}` : t.sekcja;
  zaznaczMenu(t.sekcja);
  $('#karta').hidden = true;
  // panel „Wygląd i filtry” należy do ekranu cash flow; inny ekran go zamyka
  if (klucz !== ostatniKlucz && typeof cfPanel !== 'undefined') cfPanel = false;
  if (klucz !== ostatniKlucz && typeof panelListy !== 'undefined') panelListy = false;   // to samo dla list (listy.js)
  ostatniKlucz = klucz;
  zamknijWysuw();
  $('#panel-filtrow').hidden = true;
  document.body.classList.remove('filtry-otwarte');
  const widok = $('#widok');
  try {
    widok.innerHTML = WIDOKI[klucz] ? await WIDOKI[klucz](t.parametry) : nieznanyEkran(t.sekcja);
    if (typeof poWidoku === 'function') poWidoku(klucz);   // przyciski Excel i CSV nad listą (eksport.js)
    podepnijFiltry();
    const o = $('#odswiez');
    if (o) o.onclick = odbuduj;
  } catch (e) {
    widok.innerHTML = `<div class="komunikat blad">${esc(e.message)}</div>`;
  }
}

// ---------- Tryb jasny / ciemny ----------
// Wybór zapamiętany w tej przeglądarce; bez wyboru obowiązuje ustawienie systemu.
const IKONA_SLONCE = 'M12 4V2M12 22v-2M4 12H2M22 12h-2M5.6 5.6 4.2 4.2M19.8 19.8l-1.4-1.4M5.6 18.4l-1.4 1.4M19.8 4.2l-1.4 1.4M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8z';
const IKONA_KSIEZYC = 'M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z';
function trybCiemny() {
  const t = document.documentElement.dataset.theme;
  return t ? t === 'dark' : window.matchMedia('(prefers-color-scheme: dark)').matches;
}
function pokazPrzelacznik() {
  const ciemny = trybCiemny();
  $('#ikona-trybu-sciezka').setAttribute('d', ciemny ? IKONA_SLONCE : IKONA_KSIEZYC);
  $('#etykieta-trybu').textContent = ciemny ? 'Tryb jasny' : 'Tryb ciemny';
}
(() => {
  try { const z = localStorage.getItem('finanse-tryb'); if (z === 'dark' || z === 'light') document.documentElement.dataset.theme = z; } catch (e) { /* bez pamięci wyboru */ }
  pokazPrzelacznik();
  $('#przelacz-tryb').onclick = () => {
    const nowy = trybCiemny() ? 'light' : 'dark';
    document.documentElement.dataset.theme = nowy;
    try { localStorage.setItem('finanse-tryb', nowy); } catch (e) { /* bez pamięci wyboru */ }
    pokazPrzelacznik();
    pokaz();   // wykresy czytają kolory z tokenów, więc rysujemy je na nowo
  };
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => { pokazPrzelacznik(); pokaz(); });
})();

window.addEventListener('hashchange', pokaz);
zbudujMenu();
sprawdzStan().then(pokaz).catch(e => komunikat(e.message, true));
setInterval(() => sprawdzStan().catch(() => {}), 60000);

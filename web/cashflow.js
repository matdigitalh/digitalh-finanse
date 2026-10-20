'use strict';
// Cash flow jak w Budget Studio (pakiet 9). Tryb domyślny jak w BS: po dniu stanu tylko płatności budżetu (plany
// i rzeczywiste nieopłacone) na dniu realnej płatności, przed nim historia z banku. Panel „Wygląd i filtry” jak w BS
// (Wygląd: granulacja, saldo startowe, kolumny, sortowanie, serie wykresu, historia; Prognoza: pochodzenie, zaległości,
// klienci odchodzą; Cechy: rodzaj, podstawa, status aktualności, etap; Daty: wystawienia, płatności, realnej, miesiąc
// księgowania z filtrami ruchomymi z pakietu 7), zapisane widoki (zdarzenie „widok”, ekran „cashflow”, ten sam mechanizm
// co listy), tabela okresów z SUM/MAX/MIN, minimapa z ramką wycinka, wykres i lista płatności wycinka na silniku list
// z pakietu 7 (sortowanie na serwerze, zaznaczanie z sumą, akcje grupowe). Liczby liczy serwer (cashflow/okresy,
// lista/cashflow); tu tylko stan ekranu w adresie, wycinek i rysowanie. Plik ładowany po listy.js i panel.js.

// Widoki startowe (lustro cashflow.WIDOKI_STARTOWE do menu bocznego przed pierwszym otwarciem; potem lista z serwera).
const WIDOKI_CF = [
  { id: '13tyg', nazwa: '13 tyg. w przód', ik: 'kalendarz' }, { id: '2tyg', nazwa: '2 tygodnie w przód', ik: 'kalendarz' },
  { id: '6mies', nazwa: '6 mies. w przód', ik: 'kalendarz' }, { id: '12mies', nazwa: '12 miesięcy w przód', ik: 'kalendarz' },
  { id: 'rok', nazwa: 'Ten rok: historia i prognoza', ik: 'fale' }, { id: 'dni', nazwa: 'Dzień po dniu (30 dni)', ik: 'fale' },
];
const GRANULACJE_CF = { dzien: 'Dzień', tydzien: 'Tydzień', miesiac: 'Miesiąc' };
const ZAKRESY_CF = [['ruchomy:dzien:14:0', '2 tyg. w przód'], ['ruchomy:dzien:30:0', '30 dni w przód'], ['ruchomy:dzien:91:0', '13 tyg. w przód'],
  ['ruchomy:dzien:182:0', '6 mies. w przód'], ['ruchomy:miesiac:12:0', '12 mies. w przód'], ['biezacy:rok', 'Ten rok'], ['wszystko', 'Wszystko']];
const SERIE_CF = { wplywy: 'Wpływy', obciazenia: 'Obciążenia', saldo: 'Saldo okresu', narastajaco: 'Saldo narastające' };
const ETAPY_CF = ['Planowana', 'Niewymagana', 'Po terminie', 'Opłacona'];
const ETAPY_CF_DOMYSLNE = ETAPY_CF.slice(0, 3);   // jak w BS: bez opłaconych (są już w saldzie startowym)
const POCHODZENIE_CF_DOMYSLNE = ['plan', 'rzeczywista', 'umowa', 'bank'];
const POCHODZENIE_KROTKO = { plan: 'plan', rzeczywista: 'rzeczywista', umowa: 'z umowy', bank: 'bank', faktura: 'faktura spoza budżetu',
  szacunek: 'szacunek' };
const KROPKA_CF = { plan: 'niebieska', rzeczywista: 'zolta', umowa: 'fioletowa', bank: 'zielona', faktura: 'zolta', szacunek: 'szara' };
const MAKS_PUNKTOW = 120;
const SPOZA_BUDZETU = 'W zaznaczeniu są pozycje spoza budżetu (historia z banku, z umowy, szacunek, należność spoza budżetu): akcja działa tylko na płatnościach budżetu.';
let cfPanel = false;   // panel „Wygląd i filtry” zostaje otwarty po Zastosuj (jak w BS)
let CF_OKNO = { klucz: '', okno: null };   // wycinek zostaje po zapisie akcji i zmianie sortowania listy
let CF_LISTA = { klucz: '', q: '', strona: 1, ile: 100, sortuj: '', kolejnosc: '' };

Object.assign(POMOC, {
  cashflow: { tytul: 'Cash flow', krotko: 'Saldo gotówki w okresach (dzień, tydzień, miesiąc) liczone jak w Budget Studio: co wpłynie, co wypłynie i ile zostanie.',
    co: 'Tabela okresów: saldo narastająco, saldo okresu, wpływy, obciążenia; zielona ramka to najwyższe saldo, czerwona najniższe. Pod nią miniatura całego zakresu z ramką do wyboru wycinka, wykres i lista płatności wycinka.',
    skad: 'Przed dniem stanu: przepływy z banku ING (rachunek główny i online). Po nim, jak w Budget Studio, wyłącznie płatności budżetu z „W cash flow”: plany i rzeczywiste nieopłacone, na dniu realnej płatności, kwoty brutto, z VAT i CIT z arkusza Opłaty urzędowe. Klienci z umową, których plany się kończą, dostają pozycje „z umowy” (fioletowe, kreskowane). Szacunek kosztów i należności spoza budżetu to opcje w „Wygląd i filtry”, domyślnie wyłączone.',
    jak: 'Płatność nieopłacona z minionym dniem realnym (zaległość) zostaje na swoim dniu, jak w BS; scenariusz pełny liczy ją za 7 dni. Scenariusz „klienci odchodzą”: każdy klient z umową wypowiada dziś i od miesiąca po odejściu nie płaci. Saldo startowe: gotówka z banku na koniec dnia przed zakresem, chyba że wpiszesz własne. Rachunek VAT liczony osobno. Tydzień od wtorku do poniedziałku, jak w BS.',
    zrob: 'Patrz na MIN w lewym kafelku: to poziom bezpieczeństwa. Zaległości rozstrzygnij (przesuń dzień realny albo oznacz opłacone poza bankiem). Przeciągnij ramkę na miniaturze, żeby obejrzeć inny wycinek; zaznacz płatności na liście, żeby przesunąć je razem.' },
});

// ---------- Lista płatności wycinka: definicja dla silnika list (listy.js) ----------
const typBudzetu = x => x.typ === 'plan' || x.typ === 'rzeczywista';
const chipPochodzenia = x => `<span class="chip ${{ plan: 'niebieski', umowa: 'akcent', szacunek: 'neutral', faktura: 'ostrzezenie', bank: 'plus' }[x.typ] || 'neutral'}">${esc(POCHODZENIE_KROTKO[x.typ] || x.typ)}</span>`;
const uwagiCf = x => [x.zaleglosc ? 'zaległość: minął dzień realny, liczona za 7 dni' : '', x.po_koncu_umowy ? 'plan po końcu umowy' : '',
  x.typ === 'umowa' ? 'brak planu klienta, wartość z umowy' : '', x.typ === 'szacunek' ? 'szacunek, poza BS' : '',
  x.aktualnosc === 'Nieaktualna' && !x.zaleglosc ? 'nieaktualna' : ''].filter(Boolean).join('; ');
const DEF_CF = {
  hash: '#/cashflow', tytul: 'Cash flow', okruszek: 'Cash flow', csv: 'cash-flow', datyStare: 'realny',
  id: x => x.id,
  kolumny: [
    { k: 'rodzaj', n: 'Rodzaj', sort: 'rodzaj', html: x => chipZnak(x.kwota), csv: x => x.kwota > 0 ? 'wpływ' : 'obciążenie' },
    { k: 'pochodzenie', n: 'Pochodzenie', sort: 'pochodzenie', html: chipPochodzenia, csv: x => POCHODZENIE_KROTKO[x.typ] || x.typ },
    { k: 'etap', n: 'Etap<br>płatności', sort: 'etap', html: x => chipEtap(x.etap_cf), csv: x => x.etap_cf },
    kolTekst('aktualnosc', 'Status<br>aktualności', x => x.aktualnosc),
    kolTekst('podstawa', 'Podstawa<br>płatności', x => x.podstawa_platnosci, { klasa: x => x.skladowa === 'us' || x.skladowa === 'zus' ? 'szary' : '' }),
    kolTekst('kontrahent', 'Kontrahent', x => x.kontrahent),
    kolTekst('tytul', 'Tytuł', x => x.tytul || (x.typ === 'plan' ? 'Przedmiot transakcji' : '')),
    kolTekst('nr_dok', 'Numer<br>dokumentu', x => x.nr_dok || '-'),
    kolKwota('netto', 'Netto PLN<br>(wartość)', x => x.netto),
    kolKwota('brutto', 'Brutto PLN<br>(wartość)', x => x.kwota),
    kolKwota('vat', 'VAT PLN<br>(wartość)', x => x.vat),
    { k: 'stawka', n: 'Stawka<br>VAT', sort: 'stawka', liczba: true, wartosc: x => x.stawka != null ? `${x.stawka}%` : '-', csv: x => x.stawka ?? '' },
    kolData('wystawienie', 'Dzień<br>wystawienia', x => x.wystawienie),
    kolData('termin', 'Dzień<br>płatności', x => x.termin),
    kolData('data', 'Dzień realnej<br>płatności', x => x.data),
    { k: 'przesuniecie', n: 'Przesunięcie<br>płatności', sort: 'przesuniecie', liczba: true, wartosc: x => `${x.przesuniecie || 0} dni`, csv: x => x.przesuniecie || 0 },
    { k: 'ksiegowanie', n: 'Miesiąc<br>księgowania', sort: 'ksiegowanie', wartosc: x => x.ksiegowanie ? mies(x.ksiegowanie) : '', csv: x => x.ksiegowanie || '' },
    { k: 'miesiac', n: 'Miesiąc<br>budżetowy', sort: 'miesiac', wartosc: x => x.miesiac ? mies(x.miesiac) : '', csv: x => x.miesiac || '' },
    kolTekst('arkusz', 'Arkusz budżetu', x => x.arkusz || '-'),
    kolTekst('folder', 'Folder', x => x.folder),
    kolTekst('metoda', 'Metoda<br>płatności', x => x.metoda),
    kolTekst('waluta', 'Waluta', x => x.waluta || 'PLN'),
    { k: 'uwagi', n: 'Uwagi', html: x => esc(uwagiCf(x)), csv: uwagiCf, klasa: () => 'szary' },
  ],
  domyslne: ['rodzaj', 'pochodzenie', 'podstawa', 'kontrahent', 'tytul', 'nr_dok', 'netto', 'brutto', 'vat', 'stawka', 'wystawienie', 'data',
    'przesuniecie', 'arkusz', 'miesiac', 'metoda', 'uwagi'],
  kwoty: x => ({ rodzaj: x.kwota > 0 ? 1 : -1, netto: x.netto, vat: x.vat, brutto: x.kwota }),
  kropka: x => `<span class="kropka ${x.aktualnosc === 'Nieaktualna' || x.etap_cf === 'Po terminie' ? 'czerwona' : KROPKA_CF[x.typ] || 'szara'}" title="${esc(POCHODZENIE_KROTKO[x.typ] || '')}${x.etap_cf ? ', ' + esc(x.etap_cf.toLowerCase()) : ''}${x.aktualnosc === 'Nieaktualna' ? ', nieaktualna' : ''}"></span>`,
  wierszKlasa: x => `${['plan', 'umowa', 'szacunek'].includes(x.typ) ? 'wiersz-plan' : x.etap_cf === 'Po terminie' ? 'wiersz-po' : ''}${x.typ === 'umowa' ? ' wiersz-umowa' : ''}${x.typ === 'szacunek' ? ' wiersz-szacunek' : ''}${x.kwota > 0 ? ' wiersz-plus' : ''}`,
  onWiersz: x => {
    if (typBudzetu(x)) kartaPlatnosci([x.id], null);
    else if (x.typ === 'faktura') location.hash = `#/platnosci/faktury?q=${encodeURIComponent(x.nr_dok)}`;
    else if (x.typ === 'bank') location.hash = `#/platnosci/bank?q=${encodeURIComponent(x.kontrahent || x.tytul)}&d_data_ksiegowania=${encodeURIComponent(`zakres:${x.data}:${x.data}`)}`;
    else if (x.typ === 'umowa') location.hash = '#/budzet/umowy';
  },
  // akcje list płatności budżetu (pakiet 7): zmień dzień realny, opłacona poza bankiem, do weryfikacji; eksport CSV dokłada silnik
  akcje: EKRANY_LIST.platnosci.akcje.map(a => ({ ...a, powod: (r, d) => r.some(x => !typBudzetu(x)) ? SPOZA_BUDZETU : (a.powod ? a.powod(r, d) : null) })),
};

// ---------- Pomocnicze ----------
const plusMiesCf = (iso, n) => { const d = new Date(iso + 'T12:00:00Z'); d.setUTCMonth(d.getUTCMonth() + n); d.setUTCDate(d.getUTCDate() - 1); return d.toISOString().slice(0, 10); };
const zlSaldoCf = s => { const t = String(s ?? '').replace(/[\s ]/g, '').replace(',', '.'); const m = /^(-?)(\d+)(?:\.(\d{1,2}))?$/.exec(t);
  return m ? (m[1] ? -1 : 1) * ((+m[2]) * 100 + +((m[3] || '') + '00').slice(0, 2)) : NaN; };
const wieleCf = v => (v || '').split('|').filter(Boolean);
// Stan ekranu (adres) → parametry zapytania (serwer nie zna serii, kolumn i sortowania listy; saldo to saldo_start)
function zapytanieCf(ef, arkusz) {
  const q = Object.fromEntries(Object.entries(ef).filter(([k]) => !['serie', 'kol', 'sortuj', 'kolejnosc', 'saldo'].includes(k)));
  return { ...q, saldo_start: ef.saldo ?? '', arkusz: arkusz || '' };
}

function widokArkuszaCf(ark, stan) {
  const koniec = ark && `${ark.do}-28` > stan ? plusMiesCf(`${ark.do}-01`, 1) : plusMiesCf(stan, 6);
  return { id: 'arkusz', nazwa: 'Cash flow arkusza', domyslny: true, parametry: { granulacja: 'tydzien', d_realny: `zakres:${stan}:${koniec}` } };
}

function kartaSumCf(okresy, maks, mini, tytul = '') {
  if (!okresy.length) return '';
  const zakres = okresy.length === 1 ? okresy[0].etykieta : `${okresy[0].etykieta.split(' – ')[0]} - ${okresy[okresy.length - 1].etykieta.split(' – ').pop()}`;
  const kl = v => v < 0 ? 'minus' : 'plus';
  const sum = okresy[okresy.length - 1].narastajaco;
  return `<div class="cf-karta">${tytul ? `<div class="tytul-karty">${esc(tytul)}</div>` : ''}<div class="zakres">${esc(zakres)}</div><dl>
    <dt>SUM</dt><dd class="${kl(sum)}" title="saldo narastające na koniec wycinka">${zl(sum, false)}</dd>
    <dt>MAX</dt><dd class="${kl(maks.narastajaco)}" title="${esc(maks.etykieta)}">${zl(maks.narastajaco, false)}</dd>
    <dt>MIN</dt><dd class="${kl(mini.narastajaco)}" title="${esc(mini.etykieta)}">${zl(mini.narastajaco, false)}</dd></dl></div>`;
}

function tabelaOkresowCf(okresy) {
  if (!okresy.length) return '';
  const mx = okresy.reduce((a, x) => x.narastajaco > a.narastajaco ? x : a), mn = okresy.reduce((a, x) => x.narastajaco < a.narastajaco ? x : a);
  const kl = v => v < 0 ? 'minus' : v > 0 ? 'plus' : 'zero';
  const wiersz = (nazwa, znak, pole, klasa = '', ramki = false) => `<tr class="${klasa}"><td><span class="znak-w">${znak}</span>${nazwa}</td>${okresy.map(o => {
    const v = o[pole], r = ramki ? (o === mx ? ' max' : o === mn ? ' min' : '') : '';
    return `<td class="${klasa ? '' : kl(v)}">${r ? `<span class="ramka${r}" title="${r === ' max' ? 'najwyższe saldo' : 'najniższe saldo'}">${zl(v, false)}</span>` : zl(v, false)}</td>`;
  }).join('')}</tr>`;
  const naglowek = o => `${o.biezacy ? `<span class="biezacy" title="okres dnia stanu">${esc(o.etykieta)}</span>` : esc(o.etykieta)}${o.po_koncu_umowy
    ? `<span class="znacznik-umowy" title="${o.po_koncu_umowy} ${o.po_koncu_umowy === 1 ? 'plan' : 'plany'} po końcu umowy na czas określony">!</span>` : ''}`;
  return `<div class="cf-tabela"><table><thead><tr><th></th>${okresy.map(o => `<th>${naglowek(o)}</th>`).join('')}</tr></thead>
    <tbody>${wiersz('Saldo narastająco', '+', 'narastajaco', '', true)}${wiersz('Saldo okresu', '=', 'saldo')}
    <tr class="oddziel w-wplywy"><td><span class="znak-w">↗</span>Wpływy</td>${okresy.map(o => `<td>${zl(o.wplywy, false)}</td>`).join('')}</tr>
    ${wiersz('Obciążenia', '↘', 'obciazenia', 'w-obciazenia')}</tbody></table></div>`;
}

// Ostrzeżenia i dodatki nad tabelą: zaległości poza prognozą, plany po końcu umowy, opcje spoza BS, scenariusz odejść.
function uwagiCfHtml(d, ef) {
  const par = d.parametry || {}, poch = par.pochodzenie || [], u = [];
  if (d.poza_prognoza?.ile) u.push(`<button type="button" class="cf-uwaga" data-cf-akcja="pelny" title="Nieopłacone płatności budżetu, którym minął dzień realny. Jak w BS nie ma ich w prognozie od dziś.">
    <span class="kropka czerwona"></span>${d.poza_prognoza.ile} ${liczebnik(d.poza_prognoza.ile, ['zaległość', 'zaległości', 'zaległości'])} poza prognozą (${zl(d.poza_prognoza.kwota)}): pokaż za 7 dni</button>`);
  if (par.scenariusz === 'pelny') u.push('<span class="pigulka miekka">zaległości za 7 dni (scenariusz pełny)</span>');
  if (d.plany_po_koncu_umowy?.ile) u.push(`<a class="cf-uwaga" href="#/budzet/umowy" title="Plany zostają w cash flow jak w BS; sprawdź, czy umowa będzie przedłużona."><span class="znacznik-umowy">!</span>${d.plany_po_koncu_umowy.ile} ${liczebnik(d.plany_po_koncu_umowy.ile, ['plan', 'plany', 'planów'])} po końcu umowy: ${esc(d.plany_po_koncu_umowy.klienci.join(', '))}</a>`);
  if (poch.includes('szacunek')) u.push('<span class="pigulka ostrzezenie" title="Średnia 6 miesięcy kosztów pracy i stałych w miesiącach bez planu kosztów. Budget Studio tego nie liczy.">z szacunkiem kosztów (poza BS)</span>');
  if (poch.includes('faktura')) u.push('<span class="pigulka ostrzezenie" title="Faktury z Fakturowni niepołączone z budżetem, w terminie przesuniętym o średnie spóźnienie nabywcy.">z należnościami spoza budżetu (poza BS)</span>');
  if (!poch.includes('umowa')) u.push('<span class="pigulka miekka">bez pozycji z umów</span>');
  if (par.historia === 'budzet') u.push('<span class="pigulka miekka">historia z budżetu, jak w BS</span>');
  return u.length ? `<div class="cf-uwagi">${u.join('')}</div>` : '';
}

function kafelOdejscCf(d) {
  if (!d.odejscia?.length || !d.bez_odejsc) return '';
  const mn = d.okresy[d.min.okres];
  const kl = v => v < 0 ? 'minus' : 'plus';
  return `<div class="cf-scenariusz"><div class="naglowek-kafla">${ik('osoby')}Gotówka w najgorszym scenariuszu</div>
    <div class="kwota ${kl(d.min.saldo)}">${zl(d.min.saldo)}</div>
    <div class="szary">najniższe saldo, ${esc(mn.etykieta)}; bez odejść ${zl(d.bez_odejsc.min.saldo)} (${esc(d.bez_odejsc.min_etykieta)})</div>
    <div class="szary">na koniec zakresu ${zl(d.sum)} zamiast ${zl(d.bez_odejsc.sum)}</div>
    <ul>${d.odejscia.map(x => `<li><b>${esc(x.folder)}</b>: odchodzi ${dataPl(x.odejscie)}, bez wpływów od ${esc(mies(x.od_miesiaca))}${x.wplywy_wypadle ? `, w zakresie mniej o ${zl(x.wplywy_wypadle)}` : ''}</li>`).join('')}</ul></div>`;
}

// ---------- Ekran ----------
async function widokCashflow(p, { arkusz = null, ark = null } = {}) {
  const stan = STAN?.naleznosci?.dzien_stanu || STAN?.bank_do;
  let widoki;
  if (arkusz) widoki = [widokArkuszaCf(ark, stan)];
  else {
    widoki = await pobierzWidoki('cashflow');
    WIDOKI_CF.splice(0, WIDOKI_CF.length, ...widoki.map(v => ({ id: v.id, nazwa: v.nazwa, ik: v.ik || 'oko' })));   // menu boczne
  }
  const { widok, ef, zmieniony } = stanListy(widoki, p, DEF_CF);
  const zap = zapytanieCf(ef, arkusz);
  let d;
  try {
    d = await api('cashflow/okresy', zap);
  } catch (err) {   // zły filtr w adresie: komunikat i droga powrotu do filtrów widoku
    setTimeout(() => { const b = $('#cf-przywroc'); if (b) b.onclick = () => przejdzDoWidoku(DEF_CF, p, (widok || widoki[0]).id); });
    return `${arkusz ? '' : '<h1>Cash flow</h1>'}<div class="komunikat blad"><span>${esc(err.message)}</span><button id="cf-przywroc">Przywróć filtry widoku</button></div>`;
  }
  if (d.brak_danych) return '<h1>Cash flow</h1><div class="pusto">Brak danych z banku.</div>';
  const zmien = nowe => przejdz(DEF_CF, p, { ...ef, ...nowe }, widok?.id);
  const serie = ef.serie ? Object.fromEntries(Object.keys(SERIE_CF).map(k => [k, ef.serie.split(',').includes(k)])) : {};
  const bazowe = widok ? stanWidoku(widok) : {};
  const panelowe = Object.keys(ef).filter(k => !['granulacja', 'd_realny', 'rodzaj', 'saldo', 'kol', 'sortuj', 'kolejnosc'].includes(k) && String(ef[k]) !== String(bazowe[k] ?? ''));
  const n = d.okresy.length;
  const bi = Math.max(0, d.okresy.findIndex(o => o.biezacy));
  const kluczOkna = JSON.stringify(zap);
  let okno = CF_OKNO.klucz === kluczOkna && CF_OKNO.okno && CF_OKNO.okno[1] < n ? CF_OKNO.okno
    : n <= MAKS_PUNKTOW ? [0, n - 1] : [Math.max(0, Math.min(n - MAKS_PUNKTOW, bi - 4)), Math.max(0, Math.min(n - MAKS_PUNKTOW, bi - 4)) + MAKS_PUNKTOW - 1];
  CF_OKNO = { klucz: kluczOkna, okno };
  if (CF_LISTA.klucz !== kluczOkna) CF_LISTA = { klucz: kluczOkna, q: '', strona: 1, ile: CF_LISTA.ile || 100, sortuj: ef.sortuj || '', kolejnosc: ef.kolejnosc || '' };
  const caly = d.okresy, maxC = caly[d.max.okres], minC = caly[d.min.okres];
  const kol = kolumnyListy('cashflow', DEF_CF, ef);
  let WYK = null;

  const rysujWycinek = () => {
    const [a, b] = okno, wyc = caly.slice(a, b + 1);
    const mx = wyc.reduce((x, y) => y.narastajaco > x.narastajaco ? y : x), mn = wyc.reduce((x, y) => y.narastajaco < x.narastajaco ? y : x);
    $('#cf-karta-dol').innerHTML = kartaSumCf(wyc, mx, mn);
    $('#cf-tabela').innerHTML = tabelaOkresowCf(wyc);
    $('#cf-powieksz').disabled = n > MAKS_PUNKTOW || (a === 0 && b === n - 1);
    WYK.ustaw({ okresy: wyc });
    rysujListe();
  };

  // Lista wycinka: silnik list z pakietu 7 (tabela z zaznaczaniem, pasek podsumowania i akcji), dane z serwera
  const rysujListe = async () => {
    const [a, b] = okno;
    const zapL = { ...zap, w_od: caly[a].od, w_do: caly[b].do, sortuj: CF_LISTA.sortuj, kolejnosc: CF_LISTA.kolejnosc };
    let w;
    try {
      w = await api('lista/cashflow', { ...zapL, q: CF_LISTA.q, strona: CF_LISTA.strona, ile: CF_LISTA.ile });
    } catch (err) { $('#cf-lista').innerHTML = `<div class="komunikat blad"><span>${esc(err.message)}</span></div>`; return; }
    if (!$('#cf-lista')) return;
    const kluczZ = `cashflow|${JSON.stringify({ ...zapL, sortuj: '', kolejnosc: '' })}|${CF_LISTA.q}`;
    if (ZAZN.klucz !== kluczZ) ZAZN = { klucz: kluczZ, wiersze: new Map() };
    KONTEKST_LISTY = { e: 'cashflow', def: DEF_CF, d: w, ef: zapL, p: { q: CF_LISTA.q }, o: {}, widok, widoki, kol, panelowe };
    const kolumny = kol.map(k => DEF_CF.kolumny.find(c => c.k === k)).filter(Boolean);
    $('#cf-lista').innerHTML = tabela({ id: 'ls-tabela', kolumny: kolumny.map(c => ({ ...c, id: c.k, naglowek: c.n })), dane: w.wiersze,
      poczatek: (w.strona - 1) * w.ile + 1, sortuj: w.sortuj, kierunek: w.kolejnosc, niska: true,
      naSort: (k, kier) => { CF_LISTA.sortuj = k; CF_LISTA.kolejnosc = kier; CF_LISTA.strona = 1; rysujListe(); },
      kropka: DEF_CF.kropka, wierszKlasa: DEF_CF.wierszKlasa, onWiersz: x => DEF_CF.onWiersz(x),
      stopkaSum: w.razem ? { rodzaj: `suma ${w.razem} pozycji`, netto: zl(w.podsumowanie.razem.netto, false), brutto: zl(w.podsumowanie.razem.brutto, false),
        vat: zl(w.podsumowanie.razem.vat, false) } : null,
      zaznacz: { czy: x => ZAZN.wiersze.has(DEF_CF.id(x)), ustaw: (x, wl) => wl ? ZAZN.wiersze.set(DEF_CF.id(x), x) : ZAZN.wiersze.delete(DEF_CF.id(x)), poZmianie: rysujPasek } })
      .replace('Brak pozycji dla tych filtrów.', 'Brak płatności w tym wycinku.');
    const ost = Math.max(1, Math.ceil(w.razem / w.ile));
    $('#cf-info').textContent = `Wyświetlono ${w.razem ? (w.strona - 1) * w.ile + 1 : 0}-${Math.min(w.strona * w.ile, w.razem)} z ${w.razem}`;
    $('#cf-poprz').disabled = w.strona <= 1;
    $('#cf-nast').disabled = w.strona >= ost;
    rysujPasek();
  };

  setTimeout(() => {
    if (!$('#cf-wyk')) return;
    WYK = Wykresy.bs($('#cf-wyk'), { okresy: caly.slice(okno[0], okno[1] + 1), wysokosc: 220, serie, opis: 'Cash flow: wpływy, obciążenia i saldo' });
    const mapa = Wykresy.minimapa($('#cf-mapa'), { wartosci: caly.map(o => o.narastajaco), etykiety: caly.map(o => o.etykieta), okno, maks: MAKS_PUNKTOW,
      naZmiane: o2 => { okno = o2; CF_OKNO.okno = o2; CF_LISTA.strona = 1; rysujWycinek(); } });
    $('#cf-powieksz').onclick = () => { okno = [0, n - 1]; CF_OKNO.okno = okno; mapa.ustaw(okno); rysujWycinek(); };
    rysujWycinek();
    $('#cf-ile').onchange = e => { CF_LISTA.ile = +e.target.value; CF_LISTA.strona = 1; rysujListe(); };
    $('#cf-poprz').onclick = () => { CF_LISTA.strona--; rysujListe(); };
    $('#cf-nast').onclick = () => { CF_LISTA.strona++; rysujListe(); };
    let t;
    $('#cf-szukaj').oninput = e => { clearTimeout(t); t = setTimeout(() => { CF_LISTA.q = e.target.value; CF_LISTA.strona = 1; rysujListe(); }, 250); };
    // pasek filtrów: działa od razu, jak filtry podręczne w BS
    document.querySelectorAll('[data-cf]').forEach(el => el.onchange = () => {
      const k = el.dataset.cf;
      if (k === 'd_realny' && el.value === 'wlasny') { cfPanel = true; return otworzPanelCf(); }
      zmien({ [k]: el.value });
    });
    const saldo = $('#cf-saldo');
    saldo.onchange = () => {
      if (!saldo.value.trim()) return zmien({ saldo: '' });
      const g = zlSaldoCf(saldo.value);
      if (isNaN(g)) return komunikat('Saldo startowe wpisz liczbą, np. 70 000,00.', true);
      zmien({ saldo: String(g) });
    };
    $('#cf-saldo-wyczysc').onclick = () => zmien({ saldo: '' });
    document.querySelectorAll('[data-cf-akcja="pelny"]').forEach(b => b.onclick = () => zmien({ scenariusz: 'pelny' }));
    const przyw = $('#cf-przywroc');
    if (przyw) przyw.onclick = () => przejdzDoWidoku(DEF_CF, p, (widok || widoki[0]).id);
    $('#cf-filtry').onclick = e => { e.stopPropagation(); cfPanel = !cfPanel; cfPanel ? otworzPanelCf() : zamknijPanelCf(); };
    const menu = $('#cf-menu');
    if (menu) menu.onclick = e => {   // zapisane widoki: ten sam mechanizm co listy (menuWidokow z listy.js, zdarzenie „widok”)
      e.stopPropagation();
      const lista = KONTEKST_LISTY;
      KONTEKST_LISTY = { e: 'cashflow', def: DEF_CF, ef: { ...ef, ...(CF_LISTA.sortuj ? { sortuj: CF_LISTA.sortuj, kolejnosc: CF_LISTA.kolejnosc } : {}) },
        p, widok, widoki, kol: kolumnyListy('cashflow', DEF_CF, ef) };
      menuWidokow(menu);
      KONTEKST_LISTY = lista;
    };
    if (cfPanel) otworzPanelCf();
  });

  function otworzPanelCf() {   // wspólny panel „Wygląd i filtry” (panel.js), sekcje jak w BS (zrzut 03)
    const zm = k => String(ef[k] ?? '') !== String(bazowe[k] ?? '');
    const o = d.opcje || {};
    const pochodzenie = wieleCf(ef.pochodzenie).length ? wieleCf(ef.pochodzenie) : POCHODZENIE_CF_DOMYSLNE;
    const etapy = wieleCf(ef.etap).length ? wieleCf(ef.etap) : ETAPY_CF_DOMYSLNE;
    const klienci = o.klienci_umowy || [];
    const odejscia = ef.odejscia === 'wszyscy' ? klienci : wieleCf(ef.odejscia);
    const sekcje = [
      { grupa: 'Wygląd' },
      { klucz: 'granulacja', etykieta: 'Granulacja', typ: 'radio', opcje: GRANULACJE_CF, wartosc: ef.granulacja || 'tydzien', zmieniona: zm('granulacja') },
      { klucz: 'saldo', etykieta: 'Saldo startowe', typ: 'tekst', inputmode: 'decimal', placeholder: `z banku: ${zl(d.saldo_start, false)}`, puste: 'z banku',
        wartosc: ef.saldo != null && ef.saldo !== '' ? zlWpis(+ef.saldo) : '', opis: 'Puste: gotówka z banku na koniec dnia przed zakresem.', zmieniona: zm('saldo') },
      { klucz: 'kol', etykieta: 'Widoczne kolumny', typ: 'kolumny', opcje: DEF_CF.kolumny.map(x => [x.k, x.n]), wartosc: kol, domyslne: DEF_CF.domyslne, zmieniona: zm('kol') },
      { klucz: 'sortuj', etykieta: 'Sortowanie', typ: 'select', opcje: [['', 'Dzień realnej płatności (domyślne)'], ...DEF_CF.kolumny.filter(x => x.sort).map(x => [x.sort, x.n.replace(/<br>/g, ' ')])],
        wartosc: CF_LISTA.sortuj || '', zmieniona: zm('sortuj') },
      { klucz: 'kolejnosc', etykieta: 'Kierunek', typ: 'radio', opcje: { rosnaco: 'rosnąco', malejaco: 'malejąco' }, wartosc: CF_LISTA.kolejnosc || 'rosnaco', zmieniona: zm('kolejnosc') },
      { klucz: 'serie', etykieta: 'Serie wykresu', typ: 'multi', opcje: Object.entries(SERIE_CF), wartosc: Object.keys(SERIE_CF).filter(k => serie[k] !== false), zmieniona: zm('serie') },
      ...(arkusz ? [] : [{ klucz: 'historia', etykieta: 'Przed dniem stanu', typ: 'radio', opcje: { '': 'historia z banku (przelewy ING)', budzet: 'płatności budżetu wg etapu, jak w BS' },
        wartosc: ef.historia || '', zmieniona: zm('historia') }]),
      { grupa: 'Prognoza' },
      { klucz: 'pochodzenie', etykieta: 'Pochodzenie', typ: 'multi', puste: 'jak w BS', opcje: (o.pochodzenie || []).filter(([k]) => !arkusz || !['bank', 'faktura', 'szacunek'].includes(k)),
        wartosc: pochodzenie, zmieniona: zm('pochodzenie'), opis: 'Domyślnie jak w BS: plany, rzeczywiste nieopłacone, pozycje z umów i historia z banku. Szacunek kosztów i należności spoza budżetu są poza BS i na wykresie wyróżnione.' },
      { klucz: 'scenariusz', etykieta: 'Zaległości', typ: 'radio', opcje: { '': 'na swoim dniu realnym, jak w BS', pelny: 'za 7 dni (scenariusz pełny)' },
        wartosc: ef.scenariusz === 'pelny' ? 'pelny' : '', zmieniona: zm('scenariusz') },
      ...(arkusz ? [] : [{ klucz: 'odejscia', etykieta: 'Klienci odchodzą', typ: 'multi', opcje: klienci.map(k => [k, k]), wartosc: odejscia, zmieniona: zm('odejscia'),
        puste: 'wyłączony', wszystkie: 'wszyscy klienci z umową',
        opis: klienci.length ? 'Zaznaczeni klienci z umową wypowiadają dziś i od miesiąca po okresie wypowiedzenia nie płacą. Nic nie zaznaczone: scenariusz wyłączony.'
          : 'Brak umów powiązanych z budżetem: dodaj je w Budżet, Umowy z klientami.' }]),
      { grupa: 'Cechy' },
      { klucz: 'rodzaj', etykieta: 'Rodzaj', typ: 'radio', opcje: { '': 'Wszystko', 1: 'Wpływy', '-1': 'Obciążenia' }, wartosc: ef.rodzaj || '', zmieniona: zm('rodzaj') },
      { klucz: 'podstawa', etykieta: 'Podstawa płatności', typ: 'multi', opcje: (o.podstawa || []).map(v => [v, v]), wartosc: wieleCf(ef.podstawa), zmieniona: zm('podstawa') },
      { klucz: 'aktualnosc', etykieta: 'Status aktualności', typ: 'radio', opcje: { '': 'Wszystko', Aktualna: 'Aktualne', Nieaktualna: 'Nieaktualne' }, wartosc: ef.aktualnosc || '', zmieniona: zm('aktualnosc') },
      { klucz: 'etap', etykieta: 'Etap płatności', typ: 'multi', opcje: ETAPY_CF.map(e => [e, e]), wartosc: etapy, zmieniona: zm('etap') },
      { grupa: 'Daty' },
      { klucz: 'd_wystawienie', etykieta: 'Dzień wystawienia', typ: 'data', wartosc: ef.d_wystawienie || '', zmieniona: zm('d_wystawienie') },
      { klucz: 'd_termin', etykieta: 'Dzień płatności', typ: 'data', wartosc: ef.d_termin || '', zmieniona: zm('d_termin') },
      { klucz: 'd_realny', etykieta: 'Dzień realnej płatności', typ: 'data', wartosc: ef.d_realny || 'ruchomy:dzien:91:0', zmieniona: zm('d_realny') },
      { klucz: 'd_ksiegowanie', etykieta: 'Miesiąc księgowania', typ: 'data', miesieczny: true, wartosc: ef.d_ksiegowanie || '', zmieniona: zm('d_ksiegowanie') },
    ];
    panelFiltrow({
      widoki: arkusz ? null : { opcje: widoki.map(v => [v.id, v.nazwa]), wybrany: widok?.id || '', naZmiane: id => przejdzDoWidoku(DEF_CF, p, id) },
      sekcje,
      naZamknij: () => { cfPanel = false; zamknijPanelCf(); },
      naZastosuj: w => {
        const g = w.saldo ? zlSaldoCf(w.saldo) : '';
        if (w.saldo && isNaN(g)) return komunikat('Saldo startowe wpisz liczbą, np. 70 000,00.', true);
        const rowne = (a, b) => a.length === b.length && a.every(x => b.includes(x));
        const listaKol = w.kol.length ? w.kol : DEF_CF.domyslne;
        try { localStorage.setItem('finanse-kol-cashflow', JSON.stringify(listaKol)); } catch (e) { /* wygoda, nie stan */ }
        const nowe = {
          granulacja: w.granulacja, saldo: w.saldo ? String(g) : '', kol: bazowe.kol ? listaKol.join(',') : '',
          sortuj: w.sortuj, kolejnosc: w.sortuj ? w.kolejnosc : '',
          serie: w.serie.length === Object.keys(SERIE_CF).length ? '' : w.serie.join(','),
          historia: w.historia || '', pochodzenie: !w.pochodzenie.length || rowne(w.pochodzenie, POCHODZENIE_CF_DOMYSLNE) ? '' : w.pochodzenie.join('|'),
          scenariusz: w.scenariusz, odejscia: !w.odejscia?.length ? '' : w.odejscia.length === klienci.length ? 'wszyscy' : w.odejscia.join('|'),
          rodzaj: w.rodzaj, podstawa: w.podstawa.length === (o.podstawa || []).length ? '' : w.podstawa.join('|'), aktualnosc: w.aktualnosc,
          etap: rowne(w.etap, ETAPY_CF_DOMYSLNE) || !w.etap.length ? '' : w.etap.join('|'),
          d_wystawienie: w.d_wystawienie, d_termin: w.d_termin, d_realny: w.d_realny || 'wszystko', d_ksiegowanie: w.d_ksiegowanie,
        };
        if (arkusz) delete nowe.historia;
        CF_LISTA.sortuj = nowe.sortuj; CF_LISTA.kolejnosc = nowe.kolejnosc;
        const przed = location.hash;
        przejdz(DEF_CF, p, nowe, widok?.id);
        if (location.hash === przed) pokaz();   // same kolumny albo sortowanie bez zmiany adresu: rysujemy od nowa
      },
    });
    const b = $('#cf-filtry'); if (b) b.innerHTML = `${ik('zamknij')}Zamknij filtry <span class="kropka-fil"></span>`;
  }

  // pasek filtrów nad tabelą (jak w BS): dzień realnej płatności, granulacja, rodzaj, saldo startowe
  const spec = ef.d_realny || 'ruchomy:dzien:91:0';
  const zakresy = arkusz ? [] : [...ZAKRESY_CF];
  if (!zakresy.some(([v]) => v === spec)) zakresy.push([spec, opisDaty(spec)]);
  zakresy.push(['wlasny', 'Własny zakres…']);
  const pasekFiltrow = `<div class="filtry">
      <label>Dzień realnej płatności<select data-cf="d_realny">${zakresy.map(([v, t]) => `<option value="${esc(v)}"${v === spec ? ' selected' : ''}>${esc(t)}</option>`).join('')}</select></label>
      <label>Granulacja<select data-cf="granulacja">${Object.entries(GRANULACJE_CF).map(([v, t]) => `<option value="${v}"${v === (ef.granulacja || 'tydzien') ? ' selected' : ''}>${t}</option>`).join('')}</select></label>
      <label>Rodzaj<select data-cf="rodzaj"><option value="">Wszystko</option><option value="1"${ef.rodzaj === '1' ? ' selected' : ''}>Wpływy</option><option value="-1"${ef.rodzaj === '-1' ? ' selected' : ''}>Obciążenia</option></select></label>
      <label class="pole-saldo">Saldo startowe<input id="cf-saldo" inputmode="decimal" value="${ef.saldo != null && ef.saldo !== '' ? esc(zlWpis(+ef.saldo)) : ''}" placeholder="${esc(zl(d.saldo_start, false))}" title="${d.zrodlo_salda === 'ręcznie' ? 'wpisane ręcznie' : 'z banku: gotówka na koniec dnia przed zakresem'}">
        <button id="cf-saldo-wyczysc" type="button" aria-label="Wyczyść saldo startowe">${ik('zamknij')}</button></label>
      <button class="przycisk miekki" id="cf-filtry" type="button">${ik('filtr')}Wygląd i filtry ${panelowe.length ? '<span class="kropka-fil"></span>' : ''}</button>
      ${arkusz && zmieniony ? `<button class="pigulka przywroc" id="cf-przywroc">${ik('przywroc')}Przywróć</button>` : ''}
    </div>`;
  const naglowek = arkusz ? '' : `<h1>Cash flow ${pytajnik('cashflow')}</h1>
    <div class="pigulki"><span class="pigulka">${ik('warstwy')}${esc(widok ? widok.nazwa : 'Widok niezapisany')}${zmieniony && widok ? ' (zmieniony)' : ''}</span>
      ${zmieniony ? `<button class="pigulka przywroc" id="cf-przywroc">${ik('przywroc')}Przywróć</button>` : ''}
      <button class="przycisk-ikona" id="cf-menu" aria-label="Zapisane widoki: zapisz, zmień, usuń" data-karta>${ik('kropki')}</button>
      <span class="szary">dzień stanu ${dataPl(d.dzien_stanu)}, saldo z ING ${zl(d.saldo_ing)}, rachunek VAT osobno ${zl(d.saldo_vat)}</span></div>`;
  return `${naglowek}${pasekFiltrow}${uwagiCfHtml(d, ef)}${kafelOdejscCf(d)}
    <div class="cf-uklad">${kartaSumCf(caly, maxC, minC)}<div id="cf-tabela"></div></div>
    <div class="cf-mapa-uklad"><button class="przycisk" id="cf-powieksz">Powiększ zakres ↔</button><div id="cf-mapa"></div></div>
    <div class="cf-uklad"><div id="cf-karta-dol"></div><div id="cf-wyk"></div></div>
    <div class="legenda-stany cf-legenda"><span><i class="l-rzecz"></i>rzeczywiste i bank</span><span><i class="l-plan"></i>plany</span>
      <span><i class="l-umowa"></i>z umowy</span>${(d.parametry?.pochodzenie || []).includes('szacunek') ? '<span><i class="l-szacunek"></i>szacunek kosztów</span>' : ''}</div>
    <div class="cf-lista-naglowek"><h2 class="sekcja">Płatności w wycinku</h2>
      <span class="legenda-stany"><span><span class="kropka niebieska"></span>plan</span><span><span class="kropka zolta"></span>rzeczywista nieopłacona</span>
        <span><span class="kropka fioletowa"></span>z umowy</span><span><span class="kropka czerwona"></span>po terminie albo nieaktualna</span>
        <span><span class="kropka zielona"></span>bank</span></span></div>
    <div id="cf-lista"></div>
    <div class="pasek-zazn" id="pasek-zazn" hidden></div>
    <div class="stopka">
      <label>Max widocznych <select id="cf-ile">${[50, 100, 200, 500].map(x => `<option${x === CF_LISTA.ile ? ' selected' : ''}>${x}</option>`).join('')}</select></label>
      <button id="cf-poprz" aria-label="Poprzednia strona">↑</button><span id="cf-info"></span><button id="cf-nast" aria-label="Następna strona">↓</button>
      <input class="szukaj" id="cf-szukaj" type="search" placeholder="Wyszukaj" value="${esc(CF_LISTA.q)}" aria-label="Wyszukaj kontrahenta, tytuł, numer dokumentu">
    </div>`;
}

function zamknijPanelCf() {
  zamknijPanelFiltrow();
  const w = $('#cf-filtry'); if (w) w.innerHTML = `${ik('filtr')}Wygląd i filtry`;
}

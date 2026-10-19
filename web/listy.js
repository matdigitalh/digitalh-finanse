'use strict';
// Listy płatności jak w Budget Studio (pakiet 7): wszystkie listy menu Płatności (połączone z budżetem, Do połączenia,
// Do weryfikacji, bank, faktury, należności, rejestr zakupów) i wydatki z banku na jednym silniku. Sortowanie po każdej
// kolumnie po stronie serwera, wyszukiwarka, strony, filtry podręczne nad listą, panel „Wygląd i filtry” (panel.js),
// zapisane widoki (zdarzenie „widok” w pliku zmian), zaznaczanie wierszy z paskiem podsumowania i akcjami grupowymi
// (jedna seria zmian: wszystko albo nic), eksport zaznaczonych do CSV. Stan listy żyje w adresie, więc działa „wstecz”.

const META_LISTY = ['widok', 'zm', 'strona', 'ile', 'q', 'id', 'zakladka'];
const MAKS_SERIA = 1000;
let panelListy = false;          // panel „Wygląd i filtry” zostaje otwarty po Zastosuj (jak w BS)
let WIDOKI_LISTY = {};           // ekran → widoki z serwera (startowe + zapisane), odświeżane po zmianie widoku
let ZAZN = { klucz: '', wiersze: new Map() };   // zaznaczenie trwa przy zmianie strony i sortowania, znika przy zmianie filtrów

// ---------- Kolumny: wyświetlanie, CSV (kwoty z przecinkiem bez spacji, daty ISO) ----------
const kwotaCsv = gr => gr == null ? '' : `${gr < 0 ? '-' : ''}${Math.floor(Math.abs(gr) / 100)},${String(Math.abs(gr) % 100).padStart(2, '0')}`;
const kolKwota = (k, n, f, o = {}) => ({ k, n, sort: k, liczba: true, wartosc: x => f(x) == null ? '' : zl(f(x), false), csv: x => kwotaCsv(f(x)), ...o });
const kolData = (k, n, f, o = {}) => ({ k, n, sort: k, wartosc: x => dataPl(f(x)), csv: x => f(x) || '', ...o });
const kolTekst = (k, n, f, o = {}) => ({ k, n, sort: k, wartosc: x => f(x) ?? '', csv: x => f(x) ?? '', ...o });
const takNie = v => v ? 'tak' : 'nie';
const chipTyp = x => x.typ === 'plan' ? '<span class="chip niebieski">plan</span>' : '<span class="chip neutral">rzeczywista</span>';
const KROPKA_ETAPU_L = { 'Po terminie': 'czerwona', 'Opłacona': 'zielona', 'Planowana': 'niebieska', 'Wystawiona': 'zolta', 'Częściowo opłacona': 'zolta' };
// Daniny z arkusza systemowego Opłaty urzędowe (pakiet 8) liczy apka: kwota od biura i dzień realny tylko w Budżet, Podatki.
const danina = x => String(x.id || '').startsWith('sys:');
const DANINA_POWOD = 'W zaznaczeniu są daniny z arkusza systemowego Opłaty urzędowe: kwotę od biura i dzień realnej płatności wpiszesz w Budżet, Podatki.';
const przesuniecie = x => x.realny_ef && x.termin_efektywny ? Math.round((new Date(x.realny_ef) - new Date(x.termin_efektywny)) / 86400000) : null;
const POWODY_POZA = ['kompensata', 'karta w walucie', 'gotówka', 'inny rachunek', 'inne'];
const POWODY_BEZ_FAKTURY = ['zwrot płatności kartą', 'zwrot nadpłaty od dostawcy', 'zwrot podatku', 'cashback, nagroda banku', 'zwrot kosztów (prywatne)',
  'windykacja, komornik', 'inne'];

// ---------- Definicje list ----------
const EKRANY_LIST = {
  platnosci: {
    hash: '#/platnosci/plan', tytul: 'Płatności', okruszek: 'Połączone z budżetem', csv: 'platnosci', opcje: true,
    id: x => x.id,
    kolumny: [
      { k: 'rodzaj', n: 'Rodzaj', sort: 'rodzaj', html: x => chipZnak(x.rodzaj), csv: x => x.rodzaj > 0 ? 'wpływ' : 'obciążenie' },
      { k: 'typ', n: 'Typ', sort: 'typ', html: chipTyp, csv: x => x.typ === 'plan' ? 'plan' : 'rzeczywista' },
      { k: 'etap', n: 'Etap<br>płatności', sort: 'etap', html: x => chipEtap(x.etap), csv: x => x.etap },
      kolTekst('aktualnosc', 'Status<br>aktualności', x => x.aktualnosc),
      kolTekst('podstawa', 'Podstawa<br>płatności', x => x.podstawa_platnosci, { klasa: x => x.skladowa === 'us' || x.skladowa === 'zus' ? 'szary' : '' }),
      kolTekst('kontrahent', 'Kontrahent', x => x.w_kontrahent),
      kolTekst('tytul', 'Tytuł', x => x.tytul || (x.typ === 'plan' ? 'Przedmiot transakcji' : '')),
      kolTekst('nr_dok', 'Numer<br>dokumentu', x => x.nr_dok || '-'),
      kolKwota('netto', 'Netto PLN<br>(wartość)', x => x.netto * x.rodzaj),
      kolKwota('brutto', 'Brutto PLN<br>(wartość)', x => x.brutto * x.rodzaj),
      kolKwota('vat', 'VAT PLN<br>(wartość)', x => (x.vat || 0) * x.rodzaj),
      { k: 'stawka', n: 'Stawka<br>VAT', sort: 'stawka', liczba: true, wartosc: x => x.stawka != null ? `${x.stawka}%` : '-', csv: x => x.stawka ?? '' },
      kolData('wystawienie', 'Dzień<br>wystawienia', x => x.wystawienie),
      kolData('termin', 'Dzień<br>płatności', x => x.termin_efektywny),
      kolData('realny', 'Dzień realnej<br>płatności', x => x.realny_ef),
      { k: 'przesuniecie', n: 'Przesunięcie<br>płatności', sort: 'przesuniecie', liczba: true, wartosc: x => przesuniecie(x) == null ? '' : `${przesuniecie(x)} dni`, csv: x => przesuniecie(x) ?? '' },
      { k: 'ksiegowanie', n: 'Miesiąc<br>księgowania', sort: 'ksiegowanie', wartosc: x => x.ksiegowanie_mies ? mies(x.ksiegowanie_mies) : '', csv: x => x.ksiegowanie_mies || '' },
      { k: 'miesiac', n: 'Miesiąc<br>budżetowy', sort: 'miesiac', wartosc: x => mies(x.miesiac), csv: x => x.miesiac },
      kolTekst('arkusz', 'Arkusz budżetu', x => x.arkusz),
      kolTekst('folder', 'Folder', x => x.folder),
      kolTekst('kategoria', 'Kategoria', x => x.kategoria),
      kolTekst('sekcja', 'Sekcja', x => x.sekcja),
      kolTekst('przedmiot', 'Przedmiot<br>transakcji', x => x.przedmiot),
      kolTekst('metoda', 'Metoda<br>płatności', x => x.metoda_ef),
      { k: 'ksiegowane', n: 'Księgowane', sort: 'ksiegowane', wartosc: x => takNie(x.ksiegowane), csv: x => takNie(x.ksiegowane) },
      { k: 'w_cashflow', n: 'W cash<br>flow', sort: 'w_cashflow', wartosc: x => takNie(x.w_cashflow), csv: x => takNie(x.w_cashflow) },
      kolTekst('komentarz', 'Komentarz', x => x.komentarz),
      kolTekst('uwagi', 'Uwagi', x => x.uwaga_stanu || x.decyzja, { klasa: () => 'szary' }),
    ],
    domyslne: ['rodzaj', 'typ', 'etap', 'podstawa', 'kontrahent', 'tytul', 'nr_dok', 'netto', 'brutto', 'vat', 'stawka', 'wystawienie', 'termin',
      'realny', 'miesiac', 'arkusz', 'uwagi'],
    szybkie: [
      { k: 'rodzaj', n: 'Rodzaj', opcje: [['', 'Wszystko'], ['1', 'Wpływy'], ['-1', 'Obciążenia']] },
      { k: 'podstawa', n: 'Podstawa płatności', multi: true, opcje: d => d.opcje.podstawa.map(v => [v, v]) },
      { k: 'aktualnosc', n: 'Status aktualności', opcje: [['', 'Wszystko'], ['Aktualna', 'Aktualne'], ['Nieaktualna', 'Nieaktualne']] },
      { k: 'etap', n: 'Etap płatności', multi: true, opcje: d => d.opcje.etap.map(v => [v, v]) },
    ],
    cechy: (d, o) => [
      { klucz: 'lista', etykieta: 'Zakres listy', typ: 'select', opcje: Object.entries(d.listy) },
      { klucz: 'rodzaj', etykieta: 'Rodzaj', typ: 'radio', opcje: { '': 'Wszystko', 1: 'Wpływy', '-1': 'Obciążenia' } },
      { klucz: 'typ', etykieta: 'Typ płatności', typ: 'radio', opcje: { '': 'Wszystko', plan: 'Planowane', rzeczywista: 'Rzeczywiste' } },
      { klucz: 'podstawa', etykieta: 'Podstawa płatności', typ: 'multi', opcje: d.opcje.podstawa.map(v => [v, v]) },
      { klucz: 'aktualnosc', etykieta: 'Status aktualności', typ: 'radio', opcje: { '': 'Wszystko', Aktualna: 'Aktualne', Nieaktualna: 'Nieaktualne' } },
      { klucz: 'etap', etykieta: 'Etap płatności', typ: 'multi', opcje: d.opcje.etap.map(v => [v, v]) },
      { klucz: 'kontrahent', etykieta: 'Kontrahent', typ: 'multi', szukaj: true, opcje: d.opcje.kontrahent.map(v => [v, v]) },
      ...(o.arkusz ? [] : [
        { klucz: 'folder', etykieta: 'Folder', typ: 'multi', szukaj: true, opcje: d.opcje.folder.map(v => [v, v]) },
        { klucz: 'kategoria', etykieta: 'Kategoria', typ: 'multi', szukaj: true, opcje: d.opcje.kategoria.map(v => [v, v]) },
        { klucz: 'arkusz', etykieta: 'Arkusz budżetu', typ: 'multi', szukaj: true, opcje: d.opcje.arkusz }]),
      { klucz: 'sekcja', etykieta: 'Sekcja', typ: 'multi', opcje: d.opcje.sekcja.map(v => [v, v]) },
      { klucz: 'przedmiot', etykieta: 'Przedmiot transakcji', typ: 'multi', szukaj: true, opcje: d.opcje.przedmiot.map(v => [v, v]) },
      { klucz: 'metoda', etykieta: 'Metoda płatności', typ: 'multi', opcje: d.opcje.metoda.map(v => [v, v]) },
      { klucz: 'ksiegowane', etykieta: 'Księgowane', typ: 'radio', opcje: { '': 'Wszystko', 1: 'Tak', 0: 'Nie' } },
      { klucz: 'w_cashflow', etykieta: 'W cash flow', typ: 'radio', opcje: { '': 'Wszystko', 1: 'Tak', 0: 'Nie' } },
    ],
    daty: [['wystawienie', 'Dzień wystawienia'], ['termin', 'Dzień płatności'], ['realny', 'Dzień realnej płatności'],
      ['ksiegowanie', 'Miesiąc księgowania', true], ['miesiac', 'Miesiąc budżetowy', true]],
    kwoty: x => ({ rodzaj: x.rodzaj, netto: x.netto * x.rodzaj, vat: (x.vat || 0) * x.rodzaj, brutto: x.brutto * x.rodzaj }),
    kropka: x => `<span class="kropka ${x.aktualnosc === 'Nieaktualna' ? 'czerwona' : KROPKA_ETAPU_L[x.etap] || 'szara'}" title="${esc(x.etap || '')}${x.aktualnosc === 'Nieaktualna' ? ', nieaktualna' : ''}"></span>`,
    wierszKlasa: x => `${x.typ === 'plan' ? 'wiersz-plan' : x.etap === 'Po terminie' ? 'wiersz-po' : ''}${x.rodzaj === 1 ? ' wiersz-plus' : ''}`,
    onWiersz: x => kartaPlatnosci([x.id], null),
    stopkaSum: d => ({ rodzaj: `suma ${d.razem} pozycji`, netto: zl(d.podsumowanie.razem.netto, false), brutto: zl(d.podsumowanie.razem.brutto, false),
      vat: zl(d.podsumowanie.razem.vat, false) }),
    notka: d => `Etap wynika z banku i Fakturowni, nie z kliknięcia: „Opłacona” dopiero, gdy jest wpłata albo przelew; wyjątek poza bankiem oznaczysz z datą. Stan na ${dataPl(d.dzien_stanu)}.`,
    akcje: [
      { id: 'realny', nazwa: 'Zmień dzień realnej płatności', ik: 'kalendarz',
        powod: (r, d) => !d.planowanie ? 'Planowanie w apce jest wyłączone; włączysz je w Budżet, Ustawienia budżetu.'
          : r.some(danina) ? DANINA_POWOD
          : r.some(x => x.etap === 'Opłacona') ? 'W zaznaczeniu są płatności opłacone: ich dzień realny to data przelewu z banku.'
            : r.some(x => x.generowany && WOREK.includes(x.podstawa)) ? 'W zaznaczeniu są plany z worka: ich daty idą z tygodni, zmień je w arkuszu.'
              : r.some(x => x.generowany && (x.skladowa === 'us' || x.skladowa === 'zus')) ? 'PIT i ZUS umowy idą za wypłatą dla osoby; zaznacz składową dla osoby.' : null,
        wykonaj: (r, d) => formularzAkcji('Dzień realnej płatności', `${r.length} ${odmiana(r.length)}: nowy dzień, w którym pieniądze faktycznie przejdą. Cash flow przesunie je od razu, termin płatności zostaje.`,
          pole('', 'Dzień realnej płatności', `<input type="date" id="fa-data" value="${esc(d.dzien_stanu)}">`), () => {
            const data = $('#fa-data').value;
            if (!data) return komunikat('Wybierz dzień.', true);
            return zmiana('bud', { op: 'seria', operacje: r.map(x => ({ op: 'platnosc', obiekt: { id: x.id, realny: data } })) });
          }) },
      { id: 'oplacona', nazwa: 'Opłacona poza bankiem', ik: 'ptaszek',
        powod: (r, d) => !d.planowanie ? 'Planowanie w apce jest wyłączone; włączysz je w Budżet, Ustawienia budżetu.'
          : r.some(danina) ? DANINA_POWOD
          : r.some(x => x.etap === 'Opłacona') ? 'Część zaznaczonych jest już opłacona.' : null,
        wykonaj: r => formularzAkcji('Opłacona poza bankiem', `Tylko wyjątki, których nie ma w wyciągu ING (kompensata, karta w walucie). ${r.length} ${odmiana(r.length)} dostanie etap „Opłacona” z tą datą.`,
          pole('', 'Data zapłaty', '<input type="date" id="fa-data">'), () => {
            const data = $('#fa-data').value;
            if (!data) return komunikat('Podaj datę zapłaty.', true);
            return zmiana('bud', { op: 'seria', operacje: r.map(x => ({ op: 'decyzja_planu', platnosc: x.id, decyzja: 'zaplacone', data })) });
          }) },
      akcjaDoWeryfikacji('platnosc', x => x.id),
    ],
  },

  bank: {
    hash: '#/platnosci/bank', tytul: 'Bank ING', okruszek: 'Płatności', csv: 'bank-ing',
    id: x => String(x.id),
    kolumny: [
      { k: 'rodzaj', n: 'Rodzaj', sort: 'rodzaj', html: x => chipKwota(x.kwota), csv: x => x.kwota > 0 ? 'wpływ' : 'obciążenie' },
      kolTekst('rachunek', 'Rachunek', x => x.rachunek, { klasa: () => 'szary' }),
      kolData('data_ksiegowania', 'Dzień płatności', x => x.data_ksiegowania),
      kolData('data_transakcji', 'Data transakcji', x => x.data_transakcji),
      kolTekst('kontrahent', 'Kontrahent', x => x.kontrahent),
      kolTekst('tytul', 'Tytuł', x => x.tytul || x.opis),
      kolKwota('kwota', 'Kwota PLN', x => x.kwota, { klasa: x => x.kwota > 0 ? 'plus' : 'minus' }),
      kolKwota('saldo_po', 'Saldo po', x => x.saldo_po, { klasa: () => 'szary' }),
      { k: 'wewnetrzna', n: 'Ruch', sort: 'wewnetrzna', html: x => x.wewnetrzna ? '<span class="chip neutral">wewnętrzny</span>' : '', csv: x => x.wewnetrzna ? 'wewnętrzny' : '' },
      { k: 'faktury', n: 'Faktura', sort: 'faktury', html: x => x.faktury ? esc(x.faktury) : x.stan_wplaty === 'nieznana' ? '<span class="chip ostrzezenie">do połączenia</span>' : '', csv: x => x.faktury || '', klasa: () => 'szary' },
    ],
    domyslne: ['rodzaj', 'rachunek', 'data_ksiegowania', 'kontrahent', 'tytul', 'kwota', 'saldo_po', 'wewnetrzna', 'faktury'],
    szybkie: [
      { k: 'kierunek', n: 'Rodzaj', opcje: [['', 'Wszystko'], ['wplywy', 'Wpływy'], ['obciazenia', 'Obciążenia']] },
      { k: 'rachunek', n: 'Rachunek', opcje: [['', 'Wszystkie'], ['główny', 'Główny 5263'], ['online', 'Online 5271'], ['VAT', 'VAT 5289']] },
      { k: 'wewnetrzne', n: 'Ruch wewnętrzny', opcje: [['', 'Pokaż'], ['bez', 'Ukryj'], ['tylko', 'Tylko wewnętrzny']] },
    ],
    daty: [['ksiegowania', 'Dzień płatności (księgowania)'], ['transakcji', 'Data transakcji']],
    datyStare: 'ksiegowania',
    kwoty: x => ({ rodzaj: x.kwota > 0 ? 1 : -1, brutto: x.kwota }),
    wierszKlasa: x => x.kwota > 0 ? 'wiersz-plus' : '',
    stopkaSum: d => ({ kwota: `<span class="plus">${zl(d.podsumowanie.wplywy.brutto, false)}</span><br><span class="minus">${zl(d.podsumowanie.obciazenia.brutto, false)}</span>` }),
    onWiersz: x => x.stan_wplaty ? kartaWplaty(x.id) : pokazKarte(x.kontrahent || x.opis, [
      ['Kwota', zl(x.kwota)], ['Rachunek', `${x.rachunek} (${(x.nrb || '').slice(-4)})`], ['Data księgowania', dataPl(x.data_ksiegowania)],
      ['Data transakcji', dataPl(x.data_transakcji)], ['Kwota oryginalna', x.kwota_oryg != null ? `${zl(x.kwota_oryg, false)} ${x.waluta_oryg}` : ''],
      ['Kontrahent', x.kontrahent], ['Rachunek kontrahenta', x.rachunek_kontrahenta], ['Opis', x.opis], ['Tytuł', x.tytul],
      ['Saldo po', zl(x.saldo_po)], ['Ruch wewnętrzny', x.wewnetrzna ? 'tak, nie liczy się do przychodów ani kosztów' : 'nie'],
      ['Numer referencyjny', x.nr_ref]], `${x.plik}, wiersz ${x.wiersz}`),
    akcje: [akcjaDoWeryfikacji('operacja', x => x.klucz)],
  },

  faktury: {
    hash: '#/platnosci/faktury', tytul: 'Faktury sprzedażowe', okruszek: 'Płatności / Faktury z Fakturowni', csv: 'faktury',
    id: x => x.numer,
    kolumny: [
      { k: 'status', n: 'Fakturownia', sort: 'status', html: x => x.status === 'Opłacona' ? '<span class="chip plus">opłacona</span>' : `<span class="chip neutral">${esc((x.status || '').toLowerCase())}</span>`, csv: x => x.status },
      { k: 'stan_bank', n: 'W banku', sort: 'stan_bank', html: chipBank, csv: x => x.stan_bank },
      kolTekst('numer', 'Numer', x => x.numer),
      kolTekst('klient', 'Klient', x => x.klient),
      kolTekst('nabywca', 'Nabywca', x => x.nabywca, { klasa: () => 'szary' }),
      kolTekst('pozycje', 'Przedmiot', x => x.pozycje),
      kolKwota('netto', 'Netto PLN', x => x.netto),
      kolKwota('vat', 'VAT PLN', x => x.vat),
      kolKwota('brutto', 'Brutto PLN', x => x.brutto),
      kolKwota('pozostalo', 'Do zapłaty PLN', x => x.pozostalo, { klasa: () => 'szary' }),
      kolData('data_wystawienia', 'Dzień wystawienia', x => x.data_wystawienia),
      kolData('data_sprzedazy', 'Data sprzedaży', x => x.data_sprzedazy, { klasa: () => 'szary' }),
      kolData('termin', 'Termin', x => x.termin),
    ],
    domyslne: ['status', 'stan_bank', 'numer', 'klient', 'nabywca', 'pozycje', 'netto', 'brutto', 'data_wystawienia', 'data_sprzedazy', 'termin'],
    szybkie: [
      { k: 'status', n: 'Status w Fakturowni', opcje: [['', 'Wszystkie'], ['Wystawiona', 'Wystawiona'], ['Opłacona', 'Opłacona']] },
      { k: 'bank', n: 'Stan w banku', opcje: [['', 'Wszystkie'], ['opłacona', 'Zapłacone'], ['nieopłacona', 'Nieopłacone'], ['częściowo', 'Częściowo'], ['opłacona poza bankiem', 'Poza bankiem']] },
    ],
    daty: [['wystawienie', 'Dzień wystawienia'], ['sprzedaz', 'Data sprzedaży'], ['termin', 'Termin płatności']],
    datyStare: 'wystawienie',
    kwoty: x => ({ rodzaj: 1, netto: x.netto, vat: x.vat, brutto: x.brutto }),
    stopkaSum: d => ({ netto: zl(d.podsumowanie.razem.netto, false), vat: zl(d.podsumowanie.razem.vat, false), brutto: zl(d.podsumowanie.razem.brutto, false) }),
    notka: () => `„Fakturownia” to status odhaczony ręcznie. „W banku” liczy aplikacja z wpłat na ING, na dzień ${dataPl(STAN.naleznosci?.dzien_stanu)}.`,
    onWiersz: x => kartaFaktury(x, [
      ['Klient', `${x.klient} (${x.klient_zrodlo})`], ['Nabywca', x.nabywca], ['NIP', x.nip], ['Status', x.status], ['Netto', zl(x.netto)], ['VAT', zl(x.vat)], ['Brutto', zl(x.brutto)],
      ['Opłacono (Fakturownia)', zl(x.oplacono)], ['W banku', x.stan_bank ? `${x.stan_bank}, zapłacono ${zl(x.zaplacono)}, zostało ${zl(x.pozostalo)}` : ''],
      ['Wpłaty', (x.wplaty || '').split('; ').filter(Boolean).map(s => { const [dd, k] = s.split(' '); return `${dataPl(dd)}: ${zl(+k)}`; }).join('\n')], ['Wystawiona', dataPl(x.data_wystawienia)], ['Data sprzedaży', dataPl(x.data_sprzedazy)],
      ['Termin płatności', dataPl(x.termin)], ['Numer KSeF', x.ksef], ['Korekta', x.korekta ? `tak, do ${x.oryginal}` : ''],
      ['Pozycje', (x.pozycje || '').replaceAll(' | ', '\n')], ['Uwagi', x.uwagi]]),
    akcje: [
      akcjaPozaBankiem(x => x.numer, x => x.stan_bank === 'opłacona' || x.stan_bank === 'opłacona poza bankiem'),
      { id: 'klient', nazwa: 'Przypisz klienta', ik: 'osoby',
        wykonaj: r => api('wydatki', { ile: 1 }).then(w => formularzAkcji('Klient faktur', `${r.length} ${liczebnik(r.length, ['faktura dostanie', 'faktury dostaną', 'faktur dostanie'])} tego klienta (tylko te faktury, nie cały nabywca).`,
          pole('', 'Klient', '<input id="fa-klient" list="lista-klientow">') + listaKlientow(w.klienci), () => {
            const klient = $('#fa-klient').value.trim();
            if (!klient) return komunikat('Wpisz klienta.', true);
            return zmiana('seria', { wpisy: r.map(x => ({ typ: 'klient_faktura', dane: { faktura: x.numer, klient } })) });
          })) },
      akcjaDoWeryfikacji('faktura', x => x.numer),
    ],
  },

  naleznosci: {
    hash: '#/platnosci/naleznosci', tytul: 'Należności', okruszek: 'Płatności / Należności', csv: 'naleznosci',
    id: x => x.numer,
    kolumny: [
      { k: 'stan_bank', n: 'W banku', sort: 'stan_bank', html: chipBank, csv: x => x.stan_bank },
      kolTekst('numer', 'Numer', x => x.numer),
      kolTekst('nabywca', 'Nabywca', x => x.nabywca),
      kolData('data_wystawienia', 'Dzień wystawienia', x => x.data_wystawienia),
      kolData('termin', 'Termin', x => x.termin),
      { k: 'dni_po_terminie', n: 'Po terminie', sort: 'dni_po_terminie', liczba: true, wartosc: x => x.dni_po_terminie ? `${x.dni_po_terminie} dni` : '', csv: x => x.dni_po_terminie || 0 },
      kolKwota('naleznosc', 'Brutto PLN', x => x.naleznosc, { klasa: () => 'szary' }),
      kolKwota('pozostalo', 'Do zapłaty PLN', x => x.pozostalo),
      kolTekst('status', 'Fakturownia', x => x.status, { klasa: x => x.status === 'Opłacona' ? 'minus' : 'szary' }),
    ],
    domyslne: ['stan_bank', 'numer', 'nabywca', 'termin', 'naleznosc', 'pozostalo', 'status'],
    szybkie: [
      { k: 'przedzial', n: 'Wiekowanie', opcje: [['', 'Wszystkie'], ...PRZEDZIALY.map(x => [x, x])] },
      { k: 'po_terminie', n: 'Termin', opcje: [['', 'Wszystkie'], ['1', 'Tylko po terminie']] },
    ],
    daty: [['wystawienie', 'Dzień wystawienia'], ['termin', 'Termin płatności']],
    kwoty: x => ({ rodzaj: 1, brutto: x.pozostalo }),
    stopkaSum: d => ({ pozostalo: zl(d.podsumowanie.razem.brutto, false) }),
    przed: (d, ef) => {
      const n = STAN.naleznosci;
      setTimeout(() => document.querySelectorAll('tr[data-q]').forEach(tr => tr.onclick = () => ustawParametry({ q: tr.dataset.q, strona: 1 })));
      return `${kafleNaleznosci(n)}${ef.po_terminie && n ? `<div class="tabela-ramka niska"><table><thead><tr><th>Nabywca</th><th class="liczba-kol">Faktur</th><th class="liczba-kol">Do zapłaty PLN</th><th class="liczba-kol">Najstarsza</th></tr></thead><tbody>
        ${n.nabywcy_po_terminie.map(x => `<tr data-q="${esc(x.nabywca)}"><td>${esc(x.nabywca)}</td><td class="liczba-kol">${x.faktur}</td><td class="liczba-kol minus">${zl(x.kwota, false)}</td><td class="liczba-kol">${x.najstarsza} dni</td></tr>`).join('')}
        </tbody></table></div><h2 class="sekcja">Faktury</h2>` : ''}`;
    },
    info: d => `stan na ${dataPl(d.dzien_stanu)} (ostatni dzień w eksporcie z ING)`,
    onWiersz: x => pokazKarte(x.numer, [['Nabywca', x.nabywca], ['NIP', x.nip], ['Wystawiona', dataPl(x.data_wystawienia)], ['Termin', dataPl(x.termin)],
      ['Brutto', zl(x.brutto)], ['Korekty', x.korekty ? zl(x.korekty) : ''], ['Zapłacono w banku', zl(x.zaplacono)], ['Do zapłaty', zl(x.pozostalo)],
      ['Po terminie', x.dni_po_terminie ? `${x.dni_po_terminie} dni` : 'nie'], ['Status w Fakturowni', x.status], ['Numer KSeF', x.ksef]],
    `${x.plik}, wiersz ${x.wiersz}`),
    akcje: [akcjaPozaBankiem(x => x.numer, () => false), akcjaDoWeryfikacji('faktura', x => x.numer)],
  },

  zakupy: {
    hash: '#/platnosci/zakupy', tytul: 'Rejestr zakupów', okruszek: 'Płatności / Dokumenty kosztowe z biura', csv: 'rejestr-zakupow',
    id: x => x.nr_ewid,
    kolumny: [
      kolTekst('rejestr', 'Rejestr', x => x.rejestr, { klasa: () => 'szary' }),
      kolTekst('nr_ewid', 'Nr ewid.', x => x.nr_ewid, { klasa: () => 'szary' }),
      kolTekst('podmiot', 'Kontrahent', x => x.podmiot),
      kolTekst('nr_dok', 'Numer dokumentu', x => x.nr_dok),
      kolData('data', 'Data', x => x.data),
      kolData('data_zaewid', 'Data zaewid.', x => x.data_zaewid, { klasa: () => 'szary' }),
      kolKwota('netto', 'Netto PLN', x => x.netto),
      kolKwota('vat', 'VAT PLN', x => x.rejestr === 'krajowe' ? x.vat : null),
      kolKwota('brutto', 'Brutto PLN', x => x.brutto),
      { k: 'stan', n: 'W banku', sort: 'data_platnosci', html: x => x.stan === 'opłacony' ? `<span class="chip plus">${dataPl(x.data_platnosci)}</span>` : x.stan ? '<span class="chip ostrzezenie">brak płatności</span>' : '', csv: x => x.data_platnosci || x.stan || '' },
    ],
    domyslne: ['rejestr', 'nr_ewid', 'podmiot', 'nr_dok', 'data', 'netto', 'vat', 'brutto', 'stan'],
    szybkie: [
      { k: 'rejestr', n: 'Rejestr', opcje: [['', 'Wszystkie'], ['krajowe', 'Krajowe'], ['zagraniczne', 'Zagraniczne']] },
      { k: 'stan', n: 'Płatność w banku', opcje: [['', 'Wszystkie'], ['opłacony', 'Znaleziona'], ['bez płatności w banku', 'Brak płatności']] },
    ],
    daty: [['data', 'Data dokumentu'], ['zaewid', 'Data zaewidencjonowania']],
    datyStare: 'data',
    kwoty: x => ({ rodzaj: -1, netto: -(x.netto || 0), vat: x.vat == null ? null : -x.vat, brutto: x.brutto == null ? null : -x.brutto }),
    stopkaSum: d => ({ netto: zl(-d.podsumowanie.razem.netto, false), vat: zl(-d.podsumowanie.razem.vat, false), brutto: zl(-d.podsumowanie.razem.brutto, false) }),
    onWiersz: x => pokazKarte(x.podmiot, [['Numer dokumentu', x.nr_dok], ['Nr ewidencyjny', x.nr_ewid], ['Rejestr', x.rejestr],
      ['Data', dataPl(x.data)], ['Data zaewidencjonowania', dataPl(x.data_zaewid)], ['Netto', zl(x.netto)], ['VAT', zl(x.vat)],
      ['Brutto', x.brutto != null ? zl(x.brutto) : 'brak w rejestrze zagranicznym'],
      ['Płatność w banku', x.data_platnosci ? `${dataPl(x.data_platnosci)}, ${zl(-x.kwota_platnosci)}` : 'nie znaleziono (karta prywatna, kompensata albo jeszcze nieopłacony)']],
    `${x.plik}, wiersz ${x.wiersz}`),
    akcje: [akcjaDoWeryfikacji('zakup', x => x.nr_ewid)],
  },

  wplaty: {
    hash: '#/platnosci/do-polaczenia', tytul: 'Wpłaty do połączenia', okruszek: 'Płatności / Płatności oczekujące', csv: 'wplaty',
    id: x => String(x.id),
    kolumny: [
      kolData('data_ksiegowania', 'Dzień płatności', x => x.data_ksiegowania),
      kolTekst('kontrahent', 'Płatnik', x => x.kontrahent),
      kolTekst('tytul', 'Tytuł', x => x.tytul || x.opis),
      kolKwota('kwota', 'Kwota PLN', x => x.kwota, { klasa: () => 'plus' }),
      kolTekst('faktury', 'Faktury', x => x.faktury, { klasa: () => 'szary' }),
      kolTekst('uwaga', 'Podpowiedź', x => [x.uwaga, x.podpowiedz].filter(Boolean).join(' · '), { klasa: () => 'szary' }),
    ],
    domyslne: ['data_ksiegowania', 'kontrahent', 'tytul', 'kwota', 'uwaga'],
    szybkie: [],
    daty: [['ksiegowania', 'Dzień płatności']],
    kwoty: x => ({ rodzaj: 1, brutto: x.kwota }),
    stopkaSum: d => ({ kwota: zl(d.podsumowanie.razem.brutto, false) }),
    przed: (d, ef) => `<div class="zakladki" role="tablist">${[['nieznana', 'Do połączenia'], ['sprzed_eksportu', 'Za faktury sprzed eksportu'], ['bez_faktury', 'Nie dotyczą faktury'], ['zwrot_zakupu', 'Zwroty zakupów'], ['dopasowana', 'Połączone']]
      .map(([v, n]) => `<button role="tab" aria-selected="${(ef.stan || 'nieznana') === v}" data-ls-stan="${v}">${n} <span class="szary">${d.liczniki[v] || 0}</span></button>`).join('')}</div>`,
    notka: () => 'Wpływy z banku bez ruchu wewnętrznego. Kliknij wpłatę, żeby połączyć ją z fakturą albo oznaczyć, że faktury nie dotyczy (zwrot, cashback). Decyzja zapisuje się w pliku zmian i przeżywa każde odświeżenie danych.',
    onWiersz: x => kartaWplaty(x.id),
    akcje: [
      { id: 'bez_faktury', nazwa: 'Nie dotyczy faktury', ik: 'przekreslony',
        powod: r => r.some(x => x.stan === 'dopasowana') ? 'Część wpłat jest połączona z fakturą; cofnij połączenie na karcie wpłaty.' : null,
        wykonaj: r => formularzAkcji('Wpłaty nie dotyczą faktury', `${r.length} ${liczebnik(r.length, ['wpłata zniknie', 'wpłaty znikną', 'wpłat zniknie'])} z Do połączenia z tym powodem.`,
          pole('', 'Powód', `<select id="fa-powod">${POWODY_BEZ_FAKTURY.map(x => `<option>${x}</option>`).join('')}</select>`),
          () => zmiana('seria', { wpisy: r.map(x => ({ typ: 'bez_faktury', dane: { operacja: x.klucz, powod: $('#fa-powod').value } })) })) },
      akcjaDoWeryfikacji('operacja', x => x.klucz),
    ],
  },

  do_weryfikacji: {
    hash: '#/platnosci/do-weryfikacji', tytul: 'Do weryfikacji', okruszek: 'Płatności / Płatności oczekujące', csv: 'do-weryfikacji',
    id: x => x.id,
    kolumny: [
      { k: 'grupa', n: 'Co sprawdzić', sort: 'grupa', html: x => `<span class="chip ${x.rodzaj === 'oznaczone' ? 'akcent' : 'ostrzezenie'}">${esc(x.tytul)}</span>`, csv: x => x.tytul },
      kolData('data', 'Data', x => x.data),
      kolTekst('kontrahent', 'Kontrahent', x => x.kontrahent),
      kolTekst('faktury', 'Faktury', x => x.faktury),
      kolKwota('kwota', 'Kwota PLN', x => x.kwota),
      kolTekst('opis', 'Szczegóły', x => (x.opis || '').replace(/-?\d+ gr/g, m => zl(parseInt(m))), { klasa: () => 'szary' }),
      { k: 'akcje', n: '', html: x => x.rodzaj === 'prawdopodobne' ? '<button data-ls-a="zatwierdz">Potwierdź</button><button data-ls-a="odrzuc">Odrzuć</button>'
        : x.rodzaj === 'fakturownia_oplacona' ? '<button data-ls-a="poza_bankiem">Opłacona poza bankiem</button>'
          : x.rodzaj === 'korekta_w_tytule' ? `<button data-ls-a="korekta">Dodaj korektę ${esc(x.korekta || '')} na ${zl(x.kwota)}</button>`
            : x.rodzaj === 'oznaczone' ? '<button data-ls-a="sprawdzone">Sprawdzone</button>' : '', klasa: () => 'akcje-wiersz', csv: () => '' },
    ],
    domyslne: ['grupa', 'data', 'kontrahent', 'faktury', 'kwota', 'opis', 'akcje'],
    szybkie: [{ k: 'grupa', n: 'Co sprawdzić', opcje: d => [['', 'Wszystko'], ...Object.entries(d.grupy)] }],
    daty: [['data', 'Data']],
    kwoty: x => ({ rodzaj: (x.kwota || 0) >= 0 ? 1 : -1, brutto: x.kwota || 0 }),
    stopkaSum: d => ({ kwota: zl(d.podsumowanie.razem.brutto, false) }),
    notka: () => 'Rzeczy, których aplikacja nie rozstrzyga sama, i pozycje przeniesione tu z innych list. Przyciski w wierszu albo zaznaczenie kilku i akcja na dole; kliknięcie wiersza otwiera wpłatę albo fakturę.',
    onWiersz: x => x.operacja_id ? kartaWplaty(x.operacja_id) : x.platnosc ? kartaPlatnosci([x.platnosc], null)
      : x.numer ? (location.hash = `#/platnosci/faktury?q=${encodeURIComponent(x.numer)}`) : null,
    wWierszu: async (a, x) => {
      if (a === 'korekta') return zmiana('korekta', { numer: x.korekta || `korekta do ${x.numer}`, faktura: x.numer, kwota: String(x.kwota) });
      if (a === 'poza_bankiem') return akcjaPozaBankiem(y => y.numer, () => false).wykonaj([x]);
      if (a === 'sprawdzone') return zmiana('do_weryfikacji', { obiekt: x.obiekt, ref: x.ref, usun: true });
      return zmiana('seria', { wpisy: x.faktury.split(', ').map(n => ({ typ: a, dane: { operacja: x.klucz, faktura: n } })) });
    },
    akcje: [
      ...['zatwierdz', 'odrzuc'].map(a => ({ id: a, nazwa: a === 'zatwierdz' ? 'Potwierdź dopasowania' : 'Odrzuć dopasowania', ik: a === 'zatwierdz' ? 'ptaszek' : 'zamknij',
        powod: r => r.some(x => x.rodzaj !== 'prawdopodobne') ? 'Potwierdzisz albo odrzucisz tylko „Dopasowanie do potwierdzenia”.' : null,
        wykonaj: r => zmiana('seria', { wpisy: r.flatMap(x => x.faktury.split(', ').map(n => ({ typ: a, dane: { operacja: x.klucz, faktura: n } }))) }) })),
      { id: 'poza', nazwa: 'Opłacona poza bankiem', ik: 'przelew',
        powod: r => r.some(x => x.rodzaj !== 'fakturownia_oplacona') ? 'Dotyczy tylko „W Fakturowni opłacona, w banku brak wpłaty”.' : null,
        wykonaj: r => akcjaPozaBankiem(x => x.numer, () => false).wykonaj(r) },
      { id: 'sprawdzone', nazwa: 'Sprawdzone', ik: 'ptaszek',
        powod: r => r.some(x => x.rodzaj !== 'oznaczone') ? 'Dotyczy tylko pozycji przeniesionych do sprawdzenia.' : null,
        wykonaj: r => zmiana('seria', { wpisy: r.map(x => ({ typ: 'do_weryfikacji', dane: { obiekt: x.obiekt, ref: x.ref, usun: true } })) }) },
    ],
  },

  wydatki: {
    hash: '#/budzet/wydatki', tytul: 'Wydatki', okruszek: 'Budżet / Wydatki z banku (bez ruchu wewnętrznego)', csv: 'wydatki',
    id: x => String(x.id),
    kolumny: [
      kolData('data_ksiegowania', 'Dzień płatności', x => x.data_ksiegowania),
      kolTekst('kontrahent', 'Kontrahent', x => x.kontrahent || x.opis),
      kolTekst('tytul', 'Tytuł', x => x.tytul, { klasa: () => 'szary' }),
      kolKwota('kwota', 'Kwota PLN', x => x.kwota, { klasa: () => 'minus' }),
      kolKwota('netto_dok', 'Netto z dokumentu', x => x.netto_dok, { klasa: () => 'szary' }),
      { k: 'rodzaj', n: 'Rodzaj', sort: 'rodzaj', html: x => chipRodzaj(x.rodzaj), csv: x => RODZAJE[x.rodzaj] || x.rodzaj },
      kolTekst('klient', 'Klient', x => x.klient),
      kolTekst('zrodlo', 'Skąd', x => x.zrodlo, { klasa: () => 'szary' }),
      { k: 'dokument', n: 'Dokument', sort: 'dokument', html: x => chipDok(x.dokument), csv: x => x.dokumenty || x.dokument },
    ],
    domyslne: ['data_ksiegowania', 'kontrahent', 'tytul', 'kwota', 'rodzaj', 'klient', 'zrodlo', 'dokument'],
    szybkie: [
      { k: 'rodzaj', n: 'Rodzaj', opcje: [['', 'Wszystkie'], ...Object.entries(RODZAJE)] },
      { k: 'klient', n: 'Klient', opcje: d => [['', 'Wszyscy'], ['-', 'bez klienta'], ...d.klienci.map(k => [k, k])] },
      { k: 'zrodlo', n: 'Skąd przypisanie', opcje: [['', 'Wszystkie'], ['mat', 'Twoje reguły'], ['bs', 'Budget Studio'], ['brak', 'Brak']] },
      { k: 'dokument', n: 'Dokument w rejestrze', opcje: [['', 'Wszystkie'], ['dokument', 'Jest'], ['bez dokumentu', 'Brak'], ['po okresie rejestru', 'Rejestr jeszcze nie obejmuje'], ['nie wymaga', 'Nie wymaga']] },
    ],
    daty: [['ksiegowania', 'Dzień płatności']],
    datyStare: 'ksiegowania',
    kwoty: x => ({ rodzaj: -1, brutto: x.kwota }),
    stopkaSum: d => ({ kwota: zl(d.podsumowanie.razem.brutto, false) }),
    przed: (d, ef) => `<div class="wiekowanie rodzaje">${d.rodzaje.map(x => `<a class="${ef.rodzaj === x.rodzaj ? 'wybrany' : ''}" href="#/budzet/wydatki?rodzaj=${x.rodzaj}"><span>${esc(RODZAJE[x.rodzaj])}</span><b>${zl(-x.kwota, false)}</b><small>${x.ile} płatności</small></a>`).join('')}</div>`,
    onWiersz: (x, d) => kartaWydatku(x, d.klienci),
    akcje: [
      { id: 'rodzaj', nazwa: 'Przypisz rodzaj', ik: 'zebatka',
        wykonaj: (r, d) => formularzAkcji('Rodzaj kosztu', `${r.length} ${odmiana(r.length)}. „Tylko te płatności” zapisuje decyzję przy każdej; „Reguła dla kontrahentów” obejmie też ich przyszłe płatności.`,
          `${pole('', 'Rodzaj', `<select id="fa-rodzaj">${Object.entries(RODZAJE).map(([v, n]) => `<option value="${v}">${n}</option>`).join('')}</select>`)}
           ${pole('', 'Klient (dla kosztu klienta)', '<input id="fa-klient" list="lista-klientow">')}${listaKlientow(d.klienci)}
           ${pole('', 'Zakres', '<select id="fa-zakres"><option value="jedna">Tylko te płatności</option><option value="regula">Reguła dla kontrahentów</option></select>')}`, () => {
            const rodzaj = $('#fa-rodzaj').value, klient = rodzaj === 'przenoszony' ? $('#fa-klient').value.trim() : '';
            const wpisy = $('#fa-zakres').value === 'regula'
              ? [...new Set(r.map(x => x.kontrahent_klucz))].map(k => ({ typ: 'koszt_regula', dane: { kontrahent: k, rodzaj, klient } }))
              : r.map(x => ({ typ: 'koszt_operacja', dane: { operacja: x.klucz, rodzaj, klient } }));
            return zmiana('seria', { wpisy });
          }) },
      akcjaDoWeryfikacji('operacja', x => x.klucz),
    ],
  },
};
const EKRAN_Z_HASHA = { 'platnosci/plan': 'platnosci', 'platnosci/bank': 'bank', 'platnosci/faktury': 'faktury', 'platnosci/naleznosci': 'naleznosci',
  'platnosci/zakupy': 'zakupy', 'platnosci/do-polaczenia': 'wplaty', 'platnosci/do-weryfikacji': 'do_weryfikacji', 'budzet/wydatki': 'wydatki' };

// Liczebnik po polsku: 1 pozycja, 2–4 pozycje, 5 pozycji (12–14 też „pozycji”).
const liczebnik = (n, [jeden, kilka, wiele]) => n === 1 ? jeden : n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 10 || n % 100 >= 20) ? kilka : wiele;
const odmiana = n => liczebnik(n, ['płatność', 'płatności', 'płatności']);

function akcjaDoWeryfikacji(obiekt, ref) {
  return { id: 'do_weryfikacji', nazwa: 'Do weryfikacji', ik: 'weryfikuj',
    wykonaj: r => formularzAkcji('Przenieś do Do weryfikacji', `Na listę Do weryfikacji: ${r.length} ${liczebnik(r.length, ['pozycja', 'pozycje', 'pozycji'])}. Każda zostaje tam, dopóki nie oznaczysz jej jako sprawdzonej.`,
      pole('', 'Co sprawdzić (opcjonalnie)', '<input id="fa-powod" maxlength="200" placeholder="np. zapytać biuro o kwotę">'),
      () => zmiana('seria', { wpisy: r.map(x => ({ typ: 'do_weryfikacji', dane: { obiekt, ref: ref(x), powod: $('#fa-powod').value.trim() } })) })) };
}

function akcjaPozaBankiem(numer, oplacona) {
  return { id: 'poza_bankiem', nazwa: 'Opłacona poza bankiem', ik: 'ptaszek',
    powod: r => r.some(oplacona) ? 'Część zaznaczonych faktur jest już opłacona.' : null,
    wykonaj: r => formularzAkcji('Opłacona poza bankiem', `Tylko wyjątki, których nie ma w wyciągu ING (kompensata, karta w walucie, gotówka). ${r.length} ${liczebnik(r.length, ['faktura przestanie', 'faktury przestaną', 'faktur przestanie'])} wisieć w należnościach.`,
      `${pole('', 'Data zapłaty', '<input type="date" id="fa-data">')}${pole('', 'Jak zapłacona', `<select id="fa-powod">${POWODY_POZA.map(x => `<option>${x}</option>`).join('')}</select>`)}`, () => {
        const data = $('#fa-data').value;
        if (!data) return komunikat('Podaj datę zapłaty.', true);
        return zmiana('seria', { wpisy: r.map(x => ({ typ: 'poza_bankiem', dane: { faktura: numer(x), powod: `opłacona poza bankiem: ${$('#fa-powod').value}`, data } })) });
      }) };
}

// Formularz akcji grupowej w karcie po prawej; zapis = jedna seria (wszystko albo nic). Zaznaczenie znika po zapisie.
function formularzAkcji(tytul, opis, pola, zapisz) {
  const k = $('#karta');
  k.innerHTML = `<button class="zamknij" aria-label="Zamknij">×</button><h2>${esc(tytul)}</h2><p class="szary">${esc(opis)}</p>
    <div class="formularz">${pola}</div><div class="akcje"><button class="glowny" id="fa-zapisz">Zapisz</button><button id="fa-anuluj">Anuluj</button></div>`;
  k.hidden = false;
  k.querySelector('input:not([type="date"]), select')?.focus();
  $('.zamknij', k).onclick = $('#fa-anuluj').onclick = () => { k.hidden = true; };
  $('#fa-zapisz').onclick = () => wyslijZaznaczone(zapisz);
}

async function wyslijZaznaczone(fn) {
  const kopia = new Map(ZAZN.wiersze);
  ZAZN.wiersze.clear();
  const ok = await fn();
  if (ok === false || ok === undefined) { ZAZN.wiersze = kopia; odswiezZaznaczenie(); return; }
  MENU_LISTY = null;
}

// ---------- Stan listy: widok bazowy + zmiany w adresie ----------
const stanZAdresu = p => Object.fromEntries(Object.entries(p).filter(([k, v]) => !META_LISTY.includes(k) && v !== ''));
const stanWidoku = v => ({ ...v.parametry, ...(v.kolumny?.length ? { kol: v.kolumny.join(',') } : {}) });
const rowneStany = (a, b) => { const ka = Object.keys(a).filter(k => a[k] !== ''), kb = Object.keys(b).filter(k => b[k] !== '');
  return ka.length === kb.length && ka.every(k => String(a[k]) === String(b[k])); };

function stanListy(widoki, p, def) {
  const stan = stanZAdresu(p);
  if (def.datyStare && (stan.od || stan.do) && !stan[`d_${def.datyStare}`]) {   // stare linki ?od=&do= (wykresy, klient)
    stan[`d_${def.datyStare}`] = `zakres:${stan.od || ''}:${stan.do || ''}`;
    delete stan.od; delete stan.do;
  }
  let widok = widoki.find(v => v.id === p.widok);
  if (p.widok && p.zm !== '1') return { widok: widok || widoki[0], ef: stanWidoku(widok || widoki[0]), zmieniony: false };
  if (!widok && !Object.keys(stan).length) widok = widoki[0];
  if (!widok && stan.lista) widok = widoki.find(v => v.id === stan.lista);   // linki z pulpitu ?lista=…&rodzaj=…
  if (!widok) widok = widoki.find(v => rowneStany(stanWidoku(v), stan));
  return { widok, ef: Object.keys(stan).length || !widok ? stan : stanWidoku(widok), zmieniony: widok ? !rowneStany(stan, stanWidoku(widok)) && Object.keys(stan).length > 0 : true };
}

function bazaAdresu(def, p) {
  const t = trasa();
  return { hash: `#/${t.sekcja}${t.podstrona ? '/' + t.podstrona : ''}`, staly: Object.fromEntries(['id', 'zakladka'].filter(k => p[k]).map(k => [k, p[k]])) };
}

function przejdz(def, p, ef, widokId) {
  const b = bazaAdresu(def, p);
  const nowe = { ...b.staly, ...(p.ile ? { ile: p.ile } : {}), ...(p.q ? { q: p.q } : {}), ...(widokId ? { widok: widokId, zm: '1' } : {}), ...ef };
  Object.keys(nowe).forEach(k => (nowe[k] === '' || nowe[k] == null) && delete nowe[k]);
  location.hash = `${b.hash}?${new URLSearchParams(nowe)}`;
}

function przejdzDoWidoku(def, p, id) {
  const b = bazaAdresu(def, p);
  location.hash = `${b.hash}?${new URLSearchParams({ ...b.staly, widok: id })}`;
}

async function pobierzWidoki(ekran, swieze = false) {
  if (swieze || !WIDOKI_LISTY[ekran]) WIDOKI_LISTY[ekran] = await api('widoki', { ekran });
  return WIDOKI_LISTY[ekran];
}

function kolumnyListy(e, def, ef) {
  const znane = def.kolumny.map(k => k.k);
  let kol = ef.kol ? ef.kol.split(',') : null;
  if (!kol) try { kol = JSON.parse(localStorage.getItem(`finanse-kol-${e}`) || 'null'); } catch (x) { kol = null; }
  kol = (Array.isArray(kol) ? kol : def.domyslne).filter(k => znane.includes(k));
  return kol.length ? kol : def.domyslne;
}

// ---------- Ekran listy ----------
let KONTEKST_LISTY = null;   // bieżąca lista: definicja, dane, stan; dla paska zaznaczenia i akcji

async function ekranListy(e, p, o = {}) {
  const def = EKRANY_LIST[e];
  const widoki = await pobierzWidoki(e);
  const { widok, ef, zmieniony } = stanListy(widoki, p, def);
  let d;
  try {
    d = await api(`lista/${e.replace('_', '-')}`, { ...ef, kol: '', q: p.q, strona: p.strona, ile: p.ile, opcje: def.opcje ? 1 : '',
      ...(o.arkusz ? { arkusz: o.arkusz } : {}) });
  } catch (err) {   // zły filtr w adresie (np. zakres dat): komunikat i droga powrotu, zamiast pustego ekranu
    setTimeout(() => { const b = $('#ls-przywroc'); if (b) b.onclick = () => przejdzDoWidoku(def, p, (widok || widoki[0]).id); });
    return `${o.arkusz ? '' : `<h1>${esc(widok?.nazwa || def.tytul)}</h1>`}<div class="komunikat blad"><span>${esc(err.message)}</span>
      <button id="ls-przywroc">Przywróć filtry widoku</button></div>`;
  }
  const kol = kolumnyListy(e, def, ef).filter(k => !o.arkusz || !['arkusz', 'folder', 'kategoria'].includes(k));   // w arkuszu to samo w każdym wierszu
  const kluczZ = `${e}|${o.arkusz || ''}|${JSON.stringify(Object.fromEntries(Object.entries(ef).filter(([k]) => !['sortuj', 'kolejnosc', 'kol'].includes(k))))}|${p.q || ''}`;
  if (ZAZN.klucz !== kluczZ) ZAZN = { klucz: kluczZ, wiersze: new Map() };
  const kolumny = kol.map(k => def.kolumny.find(c => c.k === k));
  // kropka przy „Wygląd i filtry”: filtry ustawione tylko w panelu (bez filtrów podręcznych, sortowania, zakresu listy)
  const panelowe = Object.keys(ef).filter(k => !def.szybkie.some(s => s.k === k) && !['sortuj', 'kolejnosc', 'lista', 'stan', 'kol'].includes(k));
  KONTEKST_LISTY = { e, def, d, ef, p, o, widok, widoki, kol, panelowe };

  setTimeout(() => {
    if (!$('#ls-lista')) return;
    document.querySelectorAll('[data-ls-f]').forEach(el => el.onchange = () => przejdz(def, p, { ...ef, [el.dataset.lsF]: el.value }, widok?.id));
    document.querySelectorAll('[data-ls-ww]').forEach(b => b.onclick = ev => { ev.stopPropagation(); wyborWiele(b, def, d, ef, p, widok); });
    document.querySelectorAll('[data-ls-stan]').forEach(b => b.onclick = () => przejdz(def, p, { ...ef, stan: b.dataset.lsStan === 'nieznana' ? '' : b.dataset.lsStan }, widok?.id));
    const przyw = $('#ls-przywroc');
    if (przyw) przyw.onclick = () => przejdzDoWidoku(def, p, (widok || widoki[0]).id);
    $('#ls-filtry').onclick = ev => { ev.stopPropagation(); panelListy = !panelListy; panelListy ? otworzPanelListy() : zamknijPanelListy(); };
    const menu = $('#ls-menu');
    if (menu) menu.onclick = ev => { ev.stopPropagation(); menuWidokow(menu); };
    // przyciski w wierszach (np. Potwierdź na Do weryfikacji) przed kliknięciem wiersza
    if (def.wWierszu) $('#ls-lista').addEventListener('click', ev => {
      const b = ev.target.closest('[data-ls-a]');
      if (!b) return;
      ev.stopPropagation();
      const i = +b.closest('tr').dataset.i;
      def.wWierszu(b.dataset.lsA, d.wiersze[i]);
    }, true);
    rysujPasek();
    if (panelListy) otworzPanelListy();
  });

  const szybkie = def.szybkie.map(s => s.multi ? `<label>${esc(s.n)}<button type="button" class="wybor" data-ls-ww="${s.k}">${esc(opisWyboru(filtryWartosci(ef[s.k]), (typeof s.opcje === 'function' ? s.opcje(d) : s.opcje).length))}</button></label>`
    : filtrListy(s.k, s.n, typeof s.opcje === 'function' ? s.opcje(d) : s.opcje, ef[s.k]));
  const naglowek = o.arkusz ? '' : `<h1>${esc(widok?.nazwa || def.tytul)}</h1>
    <div class="pigulki"><span class="pigulka">${ik('warstwy')}${esc(def.okruszek)} / ${esc(widok ? widok.nazwa : 'Widok niezapisany')}${zmieniony && widok ? ' (zmieniony)' : ''}</span>
      ${zmieniony ? `<button class="pigulka przywroc" id="ls-przywroc">${ik('przywroc')}Przywróć</button>` : ''}
      <button class="przycisk-ikona" id="ls-menu" aria-label="Zapisane widoki: zapisz, zmień, usuń" data-karta>${ik('kropki')}</button>
      <span class="szary">${esc(def.info ? def.info(d) : `${d.razem} ${liczebnik(d.razem, ['pozycja', 'pozycje', 'pozycji'])}`)}</span></div>`;
  const tab = tabela({ id: 'ls-tabela', kolumny: kolumny.map(c => ({ ...c, id: c.k, naglowek: c.n })), dane: d.wiersze, poczatek: (d.strona - 1) * d.ile + 1,
    sortuj: ef.sortuj, kierunek: ef.kolejnosc || 'malejaco', naSort: (k, kier) => przejdz(def, p, { ...ef, sortuj: k, kolejnosc: kier }, widok?.id),
    kropka: def.kropka, wierszKlasa: def.wierszKlasa, onWiersz: x => def.onWiersz?.(x, d),
    stopkaSum: def.stopkaSum ? def.stopkaSum(d) : null,
    zaznacz: { czy: x => ZAZN.wiersze.has(def.id(x)), ustaw: (x, wl) => wl ? ZAZN.wiersze.set(def.id(x), x) : ZAZN.wiersze.delete(def.id(x)), poZmianie: rysujPasek } });
  return `${naglowek}
    ${def.przed ? def.przed(d, ef) : ''}
    <div class="filtry">${szybkie.join('')}
      <button class="przycisk miekki" id="ls-filtry" type="button">${ik('filtr')}Wygląd i filtry${panelowe.length ? ' <span class="kropka-fil"></span>' : ''}</button>
      ${o.arkusz && zmieniony ? `<button class="pigulka przywroc" id="ls-przywroc">${ik('przywroc')}Przywróć</button>` : ''}</div>
    ${def.notka ? `<p class="notka">${esc(def.notka(d))}</p>` : ''}
    <div id="ls-lista">${tab}</div>
    <div class="pasek-zazn" id="pasek-zazn" hidden></div>
    ${stopka(d, p)}`;
}

const filtryWartosci = v => (v || '').split('|').filter(Boolean);
const opisWyboru = (w, n) => !w.length || w.length === n ? 'Wszystko' : w.length === 1 ? w[0] : `${w.length} z ${n}`;

function filtrListy(id, etykieta, opcje, wartosc) {
  return `<label>${esc(etykieta)}<select data-ls-f="${id}">${opcje.map(([v, n]) => `<option value="${esc(v)}"${(wartosc || '') === v ? ' selected' : ''}>${esc(n)}</option>`).join('')}</select></label>`;
}

// Filtr podręczny wielokrotnego wyboru (podstawa, etap): lista pól do zaznaczenia pod przyciskiem, „Zastosuj”.
function wyborWiele(przycisk, def, d, ef, p, widok) {
  document.querySelectorAll('.wybor-lista').forEach(x => x.remove());
  const s = def.szybkie.find(x => x.k === przycisk.dataset.lsWw);
  const opcje = typeof s.opcje === 'function' ? s.opcje(d) : s.opcje, w = filtryWartosci(ef[s.k]);
  const m = document.createElement('div');
  m.className = 'wybor-lista';
  m.innerHTML = `${opcje.map(([v, t]) => `<label><input type="checkbox" value="${esc(v)}"${w.includes(v) ? ' checked' : ''}>${esc(t)}</label>`).join('')}
    <div class="akcje"><button class="glowny" type="button" data-w="ok">Zastosuj</button><button type="button" data-w="wyczysc">Wszystko</button></div>`;
  const r = przycisk.getBoundingClientRect();
  m.style.left = `${r.left + window.scrollX}px`;
  m.style.top = `${r.bottom + window.scrollY + 4}px`;
  document.body.appendChild(m);
  const zamknij = ev => { if (!m.contains(ev.target)) { m.remove(); document.removeEventListener('click', zamknij); } };
  setTimeout(() => document.addEventListener('click', zamknij));
  m.querySelector('[data-w="ok"]').onclick = () => {
    const v = [...m.querySelectorAll('input:checked')].map(x => x.value);
    m.remove();
    przejdz(def, p, { ...ef, [s.k]: v.length === opcje.length ? '' : v.join('|') }, widok?.id);
  };
  m.querySelector('[data-w="wyczysc"]').onclick = () => { m.remove(); przejdz(def, p, { ...ef, [s.k]: '' }, widok?.id); };
}

// ---------- Zaznaczenie: pasek podsumowania i akcje ----------
function podsumujZaznaczenie(wiersze, kwoty) {
  const pusty = () => ({ ile: 0, netto: 0, vat: 0, brutto: 0, jest: { netto: false, vat: false, brutto: false } });
  const w = { wplywy: pusty(), obciazenia: pusty() };
  for (const x of wiersze) {
    const k = kwoty(x), g = w[(k.rodzaj || 0) > 0 ? 'wplywy' : 'obciazenia'];
    g.ile++;
    for (const n of ['netto', 'vat', 'brutto']) if (k[n] != null) { g[n] += k[n]; g.jest[n] = true; }
  }
  return w;
}

function odswiezZaznaczenie() {
  const t = document.getElementById('ls-tabela');
  if (t?.odswiezZaznaczenie) t.odswiezZaznaczenie();
  else rysujPasek();
}

function rysujPasek() {
  const pasek = $('#pasek-zazn'), c = KONTEKST_LISTY;
  if (!pasek || !c) return;
  const wiersze = [...ZAZN.wiersze.values()];
  document.body.classList.toggle('jest-zaznaczenie', wiersze.length > 0);
  if (!wiersze.length) { pasek.hidden = true; pasek.innerHTML = ''; return; }
  const s = podsumujZaznaczenie(wiersze, c.def.kwoty);
  const grupa = (nazwa, g, kl) => !g.ile ? '' : `<span class="pz-grupa ${kl}"><b>${nazwa} ${g.ile}</b>${['netto', 'vat', 'brutto'].filter(n => g.jest[n])
    .map(n => `<span>${n === 'vat' ? 'VAT' : n} <i>${zl(g[n], false)}</i></span>`).join('')}</span>`;
  const jest = n => s.wplywy.jest[n] || s.obciazenia.jest[n];
  const razem = s.wplywy.ile && s.obciazenia.ile ? `<span class="pz-grupa"><b>Razem</b>${['netto', 'vat', 'brutto'].filter(jest).map(n => `<span>${n === 'vat' ? 'VAT' : n} <i>${zl(s.wplywy[n] + s.obciazenia[n], false)}</i></span>`).join('')}</span>` : '';
  const naStronie = c.d.wiersze.every(x => ZAZN.wiersze.has(c.def.id(x)));
  const wszystkie = naStronie && c.d.razem > c.d.wiersze.length && wiersze.length < c.d.razem
    ? `<button type="button" class="link" id="pz-wszystkie">Zaznacz wszystkie wyniki (${c.d.razem})</button>` : '';
  const akcje = [{ id: 'csv', nazwa: 'Eksport zaznaczonych (CSV)', ik: 'plik', wykonaj: r => eksportCsv(c, r) }, ...(c.def.akcje || [])];
  pasek.innerHTML = `<div class="pz-gora"><span class="pz-ile">${ik('ptaszek')}Zaznaczono ${wiersze.length}</span>${grupa('Wpływy', s.wplywy, 'plus')}${grupa('Obciążenia', s.obciazenia, 'minus')}${razem}${wszystkie}</div>
    <div class="pz-akcje">${akcje.map(a => { const pw = a.powod?.(wiersze, c.d);
      return `<button type="button" class="przycisk miekki" data-pz="${a.id}" data-karta${pw ? ` disabled title="${esc(pw)}"` : ''}>${ik(a.ik)}${esc(a.nazwa)}</button>`; }).join('')}
      ${akcje.some(a => a.powod?.(wiersze, c.d)) ? `<span class="pz-powod szary">${esc(akcje.map(a => a.powod?.(wiersze, c.d)).find(Boolean))}</span>` : ''}
      <button type="button" class="anuluj" id="pz-anuluj">Anuluj zaznaczenie</button></div>`;
  pasek.hidden = false;
  pasek.querySelectorAll('[data-pz]').forEach(b => b.onclick = ev => {
    ev.stopPropagation();
    const a = akcje.find(x => x.id === b.dataset.pz);
    if (a.id !== 'csv' && wiersze.length > MAKS_SERIA) return komunikat(`Jedna akcja obejmie najwyżej ${MAKS_SERIA} pozycji; zawęź filtry.`, true);
    a.wykonaj(wiersze, c.d);
  });
  $('#pz-anuluj').onclick = () => { ZAZN.wiersze.clear(); odswiezZaznaczenie(); };
  const wsz = $('#pz-wszystkie');
  if (wsz) wsz.onclick = async () => {
    wsz.disabled = true;
    const w = await api(`lista/${c.e.replace('_', '-')}`, { ...c.ef, kol: '', q: c.p.q, wszystkie: 1, ...(c.o.arkusz ? { arkusz: c.o.arkusz } : {}) });
    if (w.razem > w.wiersze.length) komunikat(`Zaznaczono pierwsze ${w.wiersze.length} z ${w.razem}; zawęź filtry, żeby objąć resztę.`, true);
    w.wiersze.forEach(x => ZAZN.wiersze.set(c.def.id(x), x));
    odswiezZaznaczenie();
  };
}

// CSV jak w Excelu po polsku: UTF-8 z BOM, średnik, przecinek dziesiętny, daty ISO; kolumny jak na liście.
function eksportCsv(c, wiersze) {
  const kolumny = c.kol.map(k => c.def.kolumny.find(x => x.k === k)).filter(x => x.n);
  const pole = v => { const s = String(v ?? ''); return /[;"\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
  const linie = [kolumny.map(x => pole(x.n.replace(/<br>/g, ' '))).join(';'),
    ...wiersze.map(w => kolumny.map(x => pole(x.csv ? x.csv(w) : x.wartosc ? x.wartosc(w) : '')).join(';'))];
  const blob = new Blob(['﻿' + linie.join('\r\n') + '\r\n'], { type: 'text/csv;charset=utf-8' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `${c.def.csv}-zaznaczone-${STAN?.naleznosci?.dzien_stanu || 'lista'}.csv`;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); });
  komunikat(`Zapisano plik CSV: ${wiersze.length} pozycji, kolumny jak na liście.`);
}

// ---------- Panel „Wygląd i filtry” ----------
function zamknijPanelListy() {
  zamknijPanelFiltrow();
  const b = $('#ls-filtry');
  if (b) b.innerHTML = `${ik('filtr')}Wygląd i filtry${KONTEKST_LISTY?.panelowe.length ? ' <span class="kropka-fil"></span>' : ''}`;
}

function otworzPanelListy() {
  const c = KONTEKST_LISTY;
  if (!c) return;
  const { def, d, ef, p, o, widok, widoki, kol } = c;
  const bazowe = widok ? stanWidoku(widok) : {};
  const zm = k => String(ef[k] ?? '') !== String(bazowe[k] ?? '');
  const sorty = def.kolumny.filter(x => x.sort);
  const cechy = (def.cechy ? def.cechy(d, o) : def.szybkie.map(s => {
    const opcje = typeof s.opcje === 'function' ? s.opcje(d) : s.opcje;
    return s.multi ? { klucz: s.k, etykieta: s.n, typ: 'multi', opcje } : { klucz: s.k, etykieta: s.n, typ: 'select', opcje };
  })).map(s => ({ ...s, wartosc: s.typ === 'multi' ? filtryWartosci(ef[s.klucz]) : (ef[s.klucz] ?? (s.typ === 'select' && s.klucz === 'lista' ? 'wszystkie' : '')), zmieniona: zm(s.klucz) }));
  const sekcje = [
    { grupa: 'Wygląd' },
    { klucz: 'kol', etykieta: 'Widoczne kolumny', typ: 'kolumny', opcje: def.kolumny.filter(x => x.n).map(x => [x.k, x.n]), wartosc: kol, domyslne: def.domyslne, zmieniona: zm('kol') },
    { klucz: 'sortuj', etykieta: 'Sortowanie', typ: 'select', opcje: [['', 'domyślne'], ...sorty.map(x => [x.sort, x.n.replace(/<br>/g, ' ')])], wartosc: ef.sortuj || '', zmieniona: zm('sortuj') },
    { klucz: 'kolejnosc', etykieta: 'Kierunek', typ: 'radio', opcje: { malejaco: 'malejąco', rosnaco: 'rosnąco' }, wartosc: ef.kolejnosc || 'malejaco', zmieniona: zm('kolejnosc') },
    { grupa: 'Cechy' }, ...cechy,
    { grupa: 'Daty' },
    ...def.daty.map(([t, n, m]) => ({ klucz: `d_${t}`, etykieta: n, typ: 'data', miesieczny: !!m, wartosc: ef[`d_${t}`] || '', zmieniona: zm(`d_${t}`) })),
  ];
  panelFiltrow({
    widoki: { opcje: widoki.map(v => [v.id, v.nazwa]), wybrany: widok?.id || '', naZmiane: id => przejdzDoWidoku(def, p, id) },
    sekcje,
    naZamknij: () => { panelListy = false; zamknijPanelListy(); },
    naZastosuj: w => {
      const nowe = { ...(ef.stan ? { stan: ef.stan } : {}) };
      for (const s of sekcje.filter(x => !x.grupa)) {
        let v = w[s.klucz];
        if (s.typ === 'multi') v = v.length === s.opcje.length ? '' : v.join('|');
        if (s.typ === 'kolumny') {   // kolumny pamięta przeglądarka per lista; widok z własnymi kolumnami widzi zmianę jako zmianę widoku
          const lista = v.length ? v : def.domyslne;
          try { localStorage.setItem(`finanse-kol-${c.e}`, JSON.stringify(lista)); } catch (x) { /* wygoda, nie stan */ }
          v = bazowe.kol ? lista.join(',') : '';
        }
        if (s.klucz === 'lista' && v === 'wszystkie') v = '';
        if (s.klucz === 'kolejnosc' && !w.sortuj) v = '';
        nowe[s.klucz] = v;
      }
      przejdz(def, p, nowe, widok?.id);
    },
  });
  const b = $('#ls-filtry');
  if (b) b.innerHTML = `${ik('zamknij')}Zamknij filtry <span class="kropka-fil"></span>`;
}

// ---------- Zapisane widoki: zapisz jako, zapisz zmiany, zmień nazwę, usuń, przywróć ----------
function menuWidokow(przycisk) {
  const c = KONTEKST_LISTY, { def, ef, p, widok, widoki } = c;
  document.querySelectorAll('.zarzadzaj-menu').forEach(x => x.remove());
  const m = document.createElement('div');
  m.className = 'zarzadzaj-menu menu-widokow';
  const zmieniony = widok && !rowneStany(ef, stanWidoku(widok));
  m.innerHTML = `<button data-m="nowy">${ik('plus')}Zapisz jako nowy widok…</button>
    ${widok ? `<button data-m="zapisz"${zmieniony ? '' : ' disabled'}>${ik('ptaszek')}Zapisz zmiany w „${esc(widok.nazwa)}”</button>
      <button data-m="nazwa">${ik('zebatka')}Zmień nazwę widoku…</button>
      <button data-m="usun"${widok.domyslny ? ' disabled title="Widoku domyślnego nie usuniesz"' : ''}>${ik('zamknij')}Usuń widok „${esc(widok.nazwa)}”</button>` : ''}
    ${zmieniony || !widok ? `<button data-m="przywroc">${ik('przywroc')}Przywróć filtry widoku</button>` : ''}
    <div class="opis">Widok zapisuje filtry, sortowanie i kolumny. Daty względne (np. „najbliższe 2 tyg.”) liczą się od nowa przy każdym otwarciu.</div>`;
  const r = przycisk.getBoundingClientRect();
  m.style.left = `${r.left + window.scrollX}px`;
  m.style.top = `${r.bottom + window.scrollY + 4}px`;
  document.body.appendChild(m);
  setTimeout(() => document.addEventListener('click', () => m.remove(), { once: true }));
  const parametry = () => Object.fromEntries(Object.entries(ef).filter(([k, v]) => k !== 'kol' && v !== ''));
  const kolumny = () => c.kol;
  const zapisz = async (dane, nowyId) => {
    if (!(await zmiana('widok', { ekran: c.e, ...dane }))) return;
    WIDOKI_LISTY[c.e] = null;
    MENU_LISTY = null;
    if (nowyId) przejdzDoWidoku(def, p, nowyId);
    else pokaz();
  };
  m.querySelectorAll('[data-m]').forEach(b => b.onclick = ev => {
    ev.stopPropagation();
    m.remove();
    const a = b.dataset.m;
    if (a === 'przywroc') return przejdzDoWidoku(def, p, (widok || widoki[0]).id);
    if (a === 'zapisz') return zapisz({ id: widok.id, nazwa: widok.nazwa, parametry: parametry(), kolumny: kolumny() }, widok.id);
    if (a === 'usun') return formularzAkcji('Usuń widok', `Widok „${widok.nazwa}” zniknie z menu i z listy widoków. Płatności się nie zmienią; cofniesz to w pliku zmian.`, '', async () => {
      if (!(await zmiana('widok', { ekran: c.e, id: widok.id, usun: true }))) return false;
      WIDOKI_LISTY[c.e] = null; MENU_LISTY = null;
      przejdzDoWidoku(def, p, widoki[0].id);
      return true;
    });
    const nowy = a === 'nowy';
    formularzAkcji(nowy ? 'Zapisz jako nowy widok' : 'Zmień nazwę widoku', nowy ? 'Bieżące filtry, sortowanie i kolumny pod nową nazwą. Widok pojawi się w menu z liczbą pozycji.' : 'Nazwa w menu i na liście widoków.',
      pole('', 'Nazwa widoku', `<input id="fa-nazwa" maxlength="60" value="${nowy ? '' : esc(widok.nazwa)}">`), async () => {
        const nazwa = $('#fa-nazwa').value.trim();
        if (!nazwa) { komunikat('Wpisz nazwę widoku.', true); return false; }
        if (nowy) { const id = `w-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`; await zapisz({ id, nazwa, parametry: parametry(), kolumny: kolumny() }, id); return true; }
        await zapisz({ id: widok.id, nazwa, parametry: widok.parametry, kolumny: widok.kolumny || [] }, null);
        return true;
      });
  });
}

// ---------- Ekrany ----------
Object.assign(WIDOKI, Object.fromEntries(Object.entries(EKRAN_Z_HASHA).map(([h, e]) => [h, p => ekranListy(e, p)])));

// Zakładka Płatności arkusza: ta sama lista, tylko płatności arkusza.
function listaPlatnosci(p, { arkusz }) { return ekranListy('platnosci', p, { arkusz }); }

'use strict';
// Ekran Wydatki: na co ile wydajemy (kategorie pod rodzajem kosztu), koszty stałe z celem i oceną, sprawy do decyzji.
// Dane: GET /api/wydatki/analiza?od&do, /api/wydatki/stale, /api/wydatki/do-decyzji?od&do, /api/wydatki/kontrahent?klucz&od&do
// (finanse/wydatki.py). Zapis: wpisy „kategoria_regula”, „kategoria_operacja”, „cel_wydatku”, „ustawienie” (obszary) w pliku zmian.
// Korzysta z app.js (api, zmiana, zmianaCicha, tabela, pytajnik, esc, zl, ...), wykresy.js i eksport.js (przyciskiEksportu).

EKSPORT_EKRANU.wydatki = ['wydatki/analiza'];   // przyciski Excel i CSV w nagłówku (eksport.js): kategorie, kontrahenci, koszty stałe

const WYD_PRACA = ['pensje', 'wspolpracownicy', 'zus', 'pit4', 'ppk', 'benefity'];
const WYD_KLIENCI = ['klienci_media', 'klienci_druk', 'klienci_podwykonawcy'];
// Grupy na wykresie miesięcznym: stały kolor dla grupy (kolor idzie za grupą, nie za miejscem w rankingu).
const WYD_GRUPY = [
  { klucz: 'praca', nazwa: 'Koszt pracy', kat: WYD_PRACA, kolor: '--s1' },
  { klucz: 'narzedzia', nazwa: 'Narzędzia i subskrypcje', kat: ['narzedzia'], kolor: '--s2' },
  { klucz: 'klienci', nazwa: 'Koszty klientów', kat: WYD_KLIENCI, kolor: '--s3' },
  { klucz: 'podatki', nazwa: 'Podatki (VAT, CIT)', kat: ['vat', 'cit'], kolor: '--s4' },
];
const WYD_OCENY = { zasadny: 'zasadny', do_sprawdzenia: 'do sprawdzenia', do_wypowiedzenia: 'do wypowiedzenia' };
const chipOceny = o => o ? `<span class="chip ${o === 'zasadny' ? 'plus' : o === 'do_wypowiedzenia' ? 'minus' : 'ostrzezenie'}">${esc(WYD_OCENY[o] || o)}</span>` : '<span class="szary">brak oceny</span>';
const wydBez = p => p.widok === 'bez';
const wydWidoczna = (k, bez) => !bez || !(WYD_KLIENCI.includes(k) || k === 'vat');
const ROZWINIETE_KAT = new Set();

Object.assign(POMOC, {
  wydatki: { tytul: 'Wydatki', krotko: 'Na co ile wydajemy: kategorie kosztów, koszty stałe z celem i oceną, sprawy do decyzji.',
    co: 'Każdy wydatek z banku ma rodzaj (od niego zależy wynik zarządczy, rezerwa i cash flow) i kategorię: drugi poziom do analizy, np. Pensje, ZUS, Narzędzia i subskrypcje, Podróże. Kategoria nie zmienia rodzaju ani wyniku.',
    skad: 'Wyciąg ING (wydatki bez przelewów między własnymi rachunkami). Kwoty z banku są brutto, z VAT. Gdy wydatek ma dokument w rejestrze biura, w szczegółach płatności widać też netto z dokumentu, ale sumy liczymy z banku.',
    jak: 'Kategoria: Twoja decyzja dla płatności, potem Twoja reguła dla kontrahenta, potem reguły wbudowane (nazwa kontrahenta, tytuł, rodzaj), na końcu Inne albo Nieprzypisane. Średnia miesięczna liczy tylko pełne miesiące; miesiąc dnia stanu jest niepełny.',
    zrob: 'Kliknij kategorię, żeby zobaczyć kontrahentów, a kontrahenta, żeby wpisać kategorię, cel (obszar, kto, uzasadnienie) i ocenę.' },
  wyd_praca: { tytul: 'Pensje i koszt pracy', krotko: 'Pensje na rękę, ZUS, PIT-4, PPK i benefity w wybranym okresie.',
    co: 'Wszystko, co kosztuje zespół: pensje (przelewy „wynagrodzenie” z listy płac: etat i powołanie zarządu), współpracownicy (przelewy do osób bez listy płac: faktury B2B, umowy o dzieło), składki ZUS, zaliczki PIT-4 od pensji, PPK i benefity (pakiet medyczny).',
    skad: 'Przelewy z banku z kategoriami Pensje, ZUS, PIT-4, PPK i Benefity.',
    jak: 'Suma w okresie i średnia z pełnych miesięcy. ZUS i PIT-4 są tu, a nie w podatkach, więc nic nie liczy się dwa razy. Przelew wypłaty jest w miesiącu przelewu, nie miesiącu listy płac.',
    zrob: 'Porównaj z listą płac i kosztem pracodawcy w Budżet, Lista płac.' },
  wyd_podatki: { tytul: 'Podatki', krotko: 'VAT oraz CIT i opłaty urzędowe zapłacone w okresie.',
    co: 'Przelewy do urzędu skarbowego za VAT i CIT, opłaty urzędowe. ZUS i PIT-4 od pensji są w koszcie pracy, nie tutaj.',
    skad: 'Przelewy z banku z kategoriami Podatki: VAT i Podatki: CIT i opłaty.',
    jak: 'VAT jest poza wynikiem zarządczym (to pieniądze urzędu). Kwota brutto przelewu.',
    zrob: 'Szczegóły okresów VAT i prognoza: Rentowność, Podatek VAT.' },
  wyd_narzedzia: { tytul: 'Narzędzia i subskrypcje miesięcznie', krotko: 'Średni miesięczny koszt narzędzi i subskrypcji z pełnych miesięcy okresu.',
    co: 'Oprogramowanie, abonamenty, domeny i hosting, telefony.',
    skad: 'Płatności z kategorią Narzędzia i subskrypcje (głównie karta na rachunku online).',
    jak: 'Płatności bieżące: suma z pełnych miesięcy wybranego okresu (miesiące wypisane pod kwotą; bieżący, niepełny miesiąc pomijamy) podzielona przez ich liczbę. Opłaty roczne zapłacone w okresie (np. Adobe) dodajemy jako 1/12 kwoty, tak jak w kosztach stałych. Płatności w walucie po kursie z wyciągu.',
    zrob: 'Lista kosztów stałych pokazuje, które narzędzia płacisz co miesiąc i czy cena się zmieniła.' },
  wyd_stale: { tytul: 'Koszty stałe', krotko: 'Kontrahenci, którym płacisz regularnie: miesięcznie i rocznie.',
    co: 'Kontrahent (osobno dla każdej kategorii, więc zwroty za wyjazdy nie mieszają się z pensją) z płatnością w co najmniej 3 z 4 ostatnich pełnych miesięcy, albo opłata roczna. Aktywny tylko, gdy zapłacono w ostatnim pełnym miesiącu albo w bieżącym; pozostali to wygasłe. Bez VAT, podziału zysku, zwrotów, kosztów klientów, podróży, reprezentacji i sprzętu.',
    skad: 'Wyciąg ING, wszystkie dostępne miesiące. Okno 4 miesięcy liczy się od dnia stanu, nie od wybranego okresu.',
    jak: 'Koszt miesięczny = suma płatności z ostatniego pełnego miesiąca (gdy wtedy nic, z bieżącego), roczny = 12 razy więcej. Opłata roczna (narzędzie z jedną płatnością od 300 zł w 12 miesiącach albo Twoje oznaczenie „roczna”) liczy się jako 1/12. Ostatnia płatność = data i suma jej miesiąca. Flagi: zmiana kwoty ponad 50% (miesiąc kontra poprzedni miesiąc z płatnością) i płatność ponad 3 dni od zwykłego dnia cyklu.',
    zrob: 'Wpisz przy każdym cel (obszar, kto, uzasadnienie) i ocenę. Flagi sprawdź: zmiana planu, nowa licencja albo opłata poza cyklem. Błędnie wykrytego oznacz w karcie jako niestały, brakującego jako stały, opłatę roczną jako roczną.' },
  wyd_wykres: { tytul: 'Wydatki miesięcznie', krotko: 'Wydatki z banku miesiąc po miesiącu, w grupach kategorii.',
    co: 'Słupek to suma wydatków miesiąca, podzielona na koszt pracy, narzędzia, koszty klientów, podatki i pozostałe kategorie.',
    skad: 'Wyciąg ING, kwoty brutto.', jak: 'Przełącznik „bez kosztów klientów i VAT” zostawia koszty samej agencji. Szary miesiąc jest niepełny.',
    zrob: 'Kliknij miesiąc, żeby zobaczyć listę jego wydatków.' },
  wyd_udzial: { tytul: 'Udział kategorii', krotko: 'Która kategoria zjada jaką część wydatków w okresie.',
    co: 'Kategorie od największej, z sumą i procentem wszystkich wydatków w widoku.', skad: 'Te same płatności co tabela niżej.',
    jak: 'Udział liczony od sumy widocznych kategorii (przy przełączniku bez kosztów klientów i VAT, od kosztów samej agencji).',
    zrob: 'Kliknij kategorię, żeby rozwinąć ją w tabeli.' },
  wyd_decyzje: { tytul: 'Do decyzji', krotko: 'Wydatki bez kategorii i kategorie, które nie pasują do rodzaju kosztu.',
    co: 'Nieprzypisane: kontrahenci, których żadna reguła nie rozpoznała. Niezgodne: kategoria nie pasuje do rodzaju (np. Narzędzia przy kosztach pracy) albo rodzaj jest nieprzypisany.',
    skad: 'Wydatki z wybranego okresu.',
    jak: 'Apka niczego tu nie poprawia sama: kategoria nie zmienia rodzaju, a rodzaj wpływa na wynik zarządczy.',
    zrob: 'Ustaw rodzaj jednym kliknięciem (reguła dla kontrahenta) albo zmień kategorię w karcie kontrahenta.' },
});

function wydZakladki(p, aktywna) {
  const z = [['analiza', 'Analiza', 'wykres'], ['stale', 'Koszty stałe', 'kalendarz'], ['decyzje', 'Do decyzji', 'weryfikuj']];
  setTimeout(() => document.querySelectorAll('.zakladki [data-wzakl]').forEach(b => b.onclick = () => ustawParametry({ zakladka: b.dataset.wzakl === 'analiza' ? '' : b.dataset.wzakl })));
  return `<div class="zakladki" role="tablist">${z.map(([k, n, i]) => `<button role="tab" data-wzakl="${k}" aria-selected="${aktywna === k}">${ik(i)}${n}</button>`).join('')}</div>`;
}

function wydOkres(d, p) {
  const rok = d.dzien_stanu.slice(0, 4);
  const szybkie = [['Ten rok', `${rok}-01-01`, d.dzien_stanu], ['Poprzedni rok', `${+rok - 1}-01-01`, `${+rok - 1}-12-31`]];
  setTimeout(() => {
    ['od', 'do'].forEach(k => { const el = $(`#wyd-${k}`); if (el) el.onchange = () => ustawParametry({ [k]: el.value }); });
    document.querySelectorAll('[data-okres]').forEach(b => b.onclick = () => { const [od, doo] = b.dataset.okres.split('|'); ustawParametry({ od, do: doo }); });
    const w = $('#wyd-widok');
    if (w) w.onchange = () => ustawParametry({ widok: w.value });
  });
  return `<div class="filtry">
    <label>Od<input type="date" id="wyd-od" value="${esc(d.od)}" max="${esc(d.dzien_stanu)}"></label>
    <label>Do<input type="date" id="wyd-do" value="${esc(d.do)}" max="${esc(d.dzien_stanu)}"></label>
    ${szybkie.map(([n, od, doo]) => `<button class="przycisk maly" data-okres="${od}|${doo}">${n}</button>`).join('')}
    <label>Pokaż<select id="wyd-widok"><option value="">wszystkie wydatki</option><option value="bez"${wydBez(p) ? ' selected' : ''}>bez kosztów klientów i VAT</option></select></label>
    <span class="szary">${d.niepelne.length ? `niepełny: ${d.niepelne.map(mies).join(', ')}` : 'same pełne miesiące'}</span></div>`;
}

const wydNaglowek = (podtytul) => `<div class="naglowek-strony"><div><h1>Wydatki ${pytajnik('wydatki')}</h1>
  <div class="okruszki">${podtytul}</div></div></div>`;

Object.assign(WIDOKI, {
  async wydatki(p) {
    const zakl = p.zakladka || 'analiza';
    if (zakl === 'stale') return wydStale(p);
    if (zakl === 'decyzje') return wydDecyzje(p);
    const d = await api('wydatki/analiza', { od: p.od, do: p.do });
    const bez = wydBez(p);
    const kat = d.kategorie.filter(x => wydWidoczna(x.klucz, bez));
    const razem = kat.reduce((a, x) => a + x.suma, 0);
    const k = d.kafle;
    const linie = arr => arr.filter(x => x.suma).map(x => `${esc(x.nazwa)}: ${zl(x.suma)}`).join('<br>');
    const kafle = `<div class="kafle">
      <div class="kafel glowny"><div class="tytul">Pensje i koszt pracy ${pytajnik('wyd_praca')}</div><div class="wartosc">${zl(k.koszt_pracy.suma)}</div>
        <div class="dop">${k.koszt_pracy.srednia != null ? `średnio ${zl(k.koszt_pracy.srednia)} miesięcznie<br>` : ''}${linie(k.koszt_pracy.rozbicie)}</div></div>
      <div class="kafel"><div class="tytul">Podatki ${pytajnik('wyd_podatki')}</div><div class="wartosc">${zl(k.podatki.suma)}</div>
        <div class="dop">${linie(k.podatki.rozbicie)}<br>ZUS ${zl(k.podatki.w_koszcie_pracy[0].suma)} i PIT-4 ${zl(k.podatki.w_koszcie_pracy[1].suma)} są w koszcie pracy, nie tutaj.</div></div>
      <div class="kafel"><div class="tytul">Narzędzia i subskrypcje ${pytajnik('wyd_narzedzia')}</div>
        <div class="wartosc">${k.narzedzia.srednia != null ? zl(k.narzedzia.srednia) : 'brak pełnego miesiąca'}</div>
        <div class="dop">${k.narzedzia.miesiecy ? `miesięcznie: ${zl(k.narzedzia.biezace_mies)} średnio z ${k.narzedzia.miesiecy} pełnych miesięcy (${mies(k.narzedzia.od_miesiaca)} do ${mies(k.narzedzia.do_miesiaca)})
          + ${zl(k.narzedzia.roczne_mies)} z ${k.narzedzia.roczne_ile} opłat rocznych (1/12)<br>` : ''}w okresie zapłacono ${zl(k.narzedzia.suma)}</div></div>
      <div class="kafel"><div class="tytul">Koszty stałe ${pytajnik('wyd_stale')}</div><div class="wartosc">${zl(k.stale.miesiecznie)}</div>
        <div class="dop">miesięcznie, ${k.stale.ile} kontrahentów; rocznie ${zl(k.stale.rocznie)}. <a href="#/wydatki?zakladka=stale">Lista</a></div></div>
    </div>`;
    setTimeout(() => wydWykresy(d, kat, razem, bez));
    const decyzje = d.do_decyzji ? `<p class="notka">${d.do_decyzji} spraw do decyzji (wydatki bez kategorii albo kategoria niepasująca do rodzaju). <a href="#/wydatki?zakladka=decyzje${p.od ? `&od=${p.od}` : ''}${p.do ? `&do=${p.do}` : ''}">Do decyzji</a></p>` : '';
    return `${wydNaglowek(`Analiza wydatków z banku, ${dataPl(d.od)} do ${dataPl(d.do)}, kwoty brutto`)}${wydZakladki(p, 'analiza')}${wydOkres(d, p)}${kafle}${decyzje}
      <div class="wykresy-2">
        <div class="karta-wyk"><h3>Wydatki miesięcznie ${pytajnik('wyd_wykres')}</h3><div class="pod">grupy kategorii; legenda ukrywa grupę; kliknij miesiąc, żeby zobaczyć wydatki</div><div id="wyd-mies"></div></div>
        <div class="karta-wyk"><h3>Udział kategorii ${pytajnik('wyd_udzial')}</h3><div class="pod">od największej; ${bez ? 'bez kosztów klientów i VAT' : 'wszystkie wydatki'}, razem ${zl(razem)}</div><div id="wyd-udzial"></div></div>
      </div>
      <h2 class="sekcja">Kategorie</h2>
      <div class="tabela-ramka niska"><table id="wyd-kat"><thead><tr><th>Kategoria</th><th class="liczba-kol">Suma</th><th class="liczba-kol">Średnio miesięcznie</th>
        <th class="liczba-kol">Udział</th><th class="liczba-kol">Płatności</th></tr></thead><tbody>${wydWierszeKat(kat, razem, d)}</tbody>
        <tfoot><tr><td>Razem</td><td class="liczba-kol">${zl(razem)}</td><td></td><td class="liczba-kol">100%</td><td class="liczba-kol">${kat.reduce((a, x) => a + x.ile, 0)}</td></tr></tfoot></table></div>
      <p class="notka">Kwoty z banku, brutto (z VAT). Średnia miesięczna z pełnych miesięcy okresu. Kliknij kategorię, żeby zobaczyć kontrahentów; kliknij kontrahenta, żeby zobaczyć płatności i wpisać cel. Znak ! oznacza kategorię niepasującą do rodzaju kosztu.</p>`;
  },
});

function wydWierszeKat(kat, razem, d) {
  const rows = [];
  for (const x of kat) {
    const otw = ROZWINIETE_KAT.has(x.klucz);
    rows.push(`<tr class="rozwijany" data-kat="${esc(x.klucz)}"><td><button type="button" class="rozwin" aria-expanded="${otw}" aria-label="${otw ? 'Zwiń' : 'Rozwiń'}">${otw ? '▾' : '▸'}</button> ${esc(x.nazwa)}</td>
      <td class="liczba-kol">${zl(x.suma)}</td><td class="liczba-kol">${x.srednia != null ? zl(x.srednia) : ''}</td>
      <td class="liczba-kol">${razem ? procent(Math.round(1000 * x.suma / razem) / 10) : ''}</td><td class="liczba-kol">${x.ile}</td></tr>`);
    if (otw) for (const c of x.kontrahenci) rows.push(`<tr class="poz-1 klik" data-kontr="${esc(c.klucz)}"><td class="wcieta">${esc(c.nazwa)}${c.ostrzezenie ? ' <span class="chip ostrzezenie" title="kategoria nie pasuje do rodzaju kosztu">!</span>' : ''}
      <span class="szary">ostatnia ${dataPl(c.ostatnia)}</span></td><td class="liczba-kol">${zl(c.suma)}</td><td></td>
      <td class="liczba-kol szary">${x.suma ? procent(Math.round(1000 * c.suma / x.suma) / 10) : ''}</td><td class="liczba-kol">${c.ile}</td></tr>`);
  }
  setTimeout(() => {
    const t = $('#wyd-kat');
    if (!t) return;
    t.querySelectorAll('tr[data-kat]').forEach(tr => tr.onclick = () => {
      const k = tr.dataset.kat;
      ROZWINIETE_KAT.has(k) ? ROZWINIETE_KAT.delete(k) : ROZWINIETE_KAT.add(k);
      t.querySelector('tbody').innerHTML = wydWierszeKat(kat, razem, d);
    });
    t.querySelectorAll('tr[data-kontr]').forEach(tr => tr.onclick = e => { e.stopPropagation(); wydKarta(tr.dataset.kontr, d); });
  });
  return rows.join('');
}

function wydWykresy(d, kat, razem, bez) {
  if (!$('#wyd-mies')) return;
  const po = Object.fromEntries(kat.map(x => [x.klucz, x]));
  const wart = klucze => d.miesiace.map(m => klucze.reduce((a, k) => a + (po[k]?.miesiace[m] || 0), 0));
  const uzyte = new Set();
  const serie = WYD_GRUPY.map(g => {
    const kl = g.kat.filter(k => po[k]);
    kl.forEach(k => uzyte.add(k));
    return { klucz: g.klucz, nazwa: g.klucz === 'podatki' && bez ? 'Podatki (CIT i opłaty)' : g.nazwa, kolor: Wykresy.kolor(g.kolor), wartosci: wart(kl), stos: 'w' };
  }).filter(s => s.wartosci.some(Boolean));
  const reszta = kat.map(x => x.klucz).filter(k => !uzyte.has(k));
  if (reszta.length) serie.push({ klucz: 'reszta', nazwa: `Pozostałe kategorie (${reszta.length})`, kolor: Wykresy.kolor('--szary-seria'), wartosci: wart(reszta), stos: 'w' });
  Wykresy.slupki($('#wyd-mies'), { kategorie: d.miesiace.map(mies), etykietyPelne: d.miesiace.map(miesPelny), wysokosc: 260, serie,
    niepelne: d.miesiace.map((m, i) => d.niepelne.includes(m) ? i : -1).filter(i => i >= 0), sumaStosu: { w: 'Razem' },
    opis: 'Wydatki miesięcznie wg grup kategorii',
    naKlik: i => { location.hash = `#/budzet/wydatki?od=${d.miesiace[i]}-01&do=${ostatniDzien(d.miesiace[i])}`; } });
  Wykresy.ranking($('#wyd-udzial'), { serie: [{ klucz: 'suma', nazwa: 'Suma w okresie', kolor: Wykresy.kolor('--s1') }],
    wiersze: [...kat].sort((a, b) => b.suma - a.suma).map(x => ({ nazwa: x.nazwa, wartosci: { suma: x.suma }, udzial: razem ? Math.round(1000 * x.suma / razem) / 10 : 0,
      naKlik: () => { ROZWINIETE_KAT.add(x.klucz); const t = $('#wyd-kat'); if (t) { t.querySelector('tbody').innerHTML = wydWierszeKat(kat, razem, d); t.querySelector(`tr[data-kat="${CSS.escape(x.klucz)}"]`)?.scrollIntoView({ block: 'center' }); } } })),
    opisWiersza: w => `${tys(w.wartosci.suma)} zł · ${procent(w.udzial)}` });
}

// ---------- karta kontrahenta: płatności, kategoria, cel ----------
async function wydKarta(klucz, okres = {}) {
  const t = trasa().parametry;
  const d = await api('wydatki/kontrahent', { klucz, od: okres.od || t.od, do: okres.do || t.do });
  const k = $('#karta');
  const c = d.cel || {};
  const opcjeKat = (wybrana, pusta) => (pusta ? `<option value="">${pusta}</option>` : '') + d.lista_kategorii.map(x => `<option value="${x.klucz}"${x.klucz === wybrana ? ' selected' : ''}>${esc(x.nazwa)}</option>`).join('');
  const st = d.staly;
  const stalyOpis = st ? `koszt stały: ${zl(st.miesiecznie)} miesięcznie, ${zl(st.rocznie)} rocznie (${esc(st.sposob)})${st.zmiana_ceny ? `; zmiana ceny ${procent(st.zmiana_ceny.proc)}: ${zl(st.zmiana_ceny.poprzednia)} na ${zl(st.zmiana_ceny.ostatnia)}` : ''}`
    : d.wygasly ? `koszt stały wygasł: ostatnia płatność ${dataPl(d.wygasly.ostatnia_data)}` : 'nie jest kosztem stałym';
  const wiersze = d.platnosci.map((x, i) => `<tr><td>${dataPl(x.data)}</td><td>${esc(x.rachunek)}</td>
    <td class="liczba-kol minus">${zl(-x.kwota)}${x.netto_dok != null ? `<br><small class="szary">netto z dokumentu ${zl(x.netto_dok)}</small>` : ''}${x.waluta_oryg && x.waluta_oryg !== 'PLN' ? `<br><small class="szary">${zl(-x.kwota_oryg, false)} ${esc(x.waluta_oryg)}</small>` : ''}</td>
    <td>${esc(x.tytul || x.opis)}</td>
    <td><small>Rodzaj: ${esc(x.rodzaj_nazwa)}${x.klient ? `, ${esc(x.klient)}` : ''} <span class="szary">(${esc(x.zrodlo || 'brak reguły')})</span><br>
      Kategoria: ${esc(x.kategoria_nazwa)}${x.zgodna ? '' : ' <span class="chip ostrzezenie" title="kategoria nie pasuje do rodzaju">!</span>'} <span class="szary">(${esc(x.kategoria_zrodlo)})</span></small>
      <div><select data-op="${i}" aria-label="Kategoria tej płatności">${opcjeKat('', 'zmień tylko tę płatność')}</select>
      ${x.kategoria_wpis && x.kategoria_zrodlo.startsWith('decyzja') ? `<button class="przycisk maly" data-cof="${esc(x.kategoria_wpis)}">Cofnij</button>` : ''}</div></td></tr>`).join('');
  k.innerHTML = `<div class="wyd-karta"><button class="zamknij" aria-label="Zamknij">×</button><h2>${esc(d.nazwa)}</h2>
    <p class="szary">${d.ile} płatności w okresie ${dataPl(d.od)} do ${dataPl(d.do)}, razem ${zl(d.suma)} brutto (wszystkich w banku: ${d.ile_wszystkich}); ${stalyOpis}.</p>
    <h3>Kategoria i cel</h3>
    <div class="formularz">
      ${pole('', 'Kategoria (wszystkie płatności kontrahenta)', `<select id="wk-kat">${opcjeKat(d.kategoria)}</select>`)}
      ${pole('', 'Obszar', `<select id="wk-obszar"><option value="">bez obszaru</option>${d.obszary.map(o => `<option${o === c.obszar ? ' selected' : ''}>${esc(o)}</option>`).join('')}</select>`)}
      ${pole('', 'Kto (osoba)', `<input id="wk-kto" list="wk-osoby" value="${esc(c.kto || '')}"><datalist id="wk-osoby">${d.osoby.map(o => `<option value="${esc(o)}">`).join('')}</datalist>`)}
      ${pole('', 'Ocena', `<select id="wk-ocena"><option value="">brak oceny</option>${Object.entries(d.oceny).map(([v, n]) => `<option value="${v}"${v === c.ocena ? ' selected' : ''}>${esc(n)}</option>`).join('')}</select>`)}
      ${pole('', 'Opłata roczna (koszt 1/12 miesięcznie)', `<select id="wk-roczna"><option value="auto"${c.roczna == null ? ' selected' : ''}>wykrywaj automatycznie</option><option value="tak"${c.roczna === 1 ? ' selected' : ''}>tak, roczna</option><option value="nie"${c.roczna === 0 ? ' selected' : ''}>nie, miesięczna</option></select>`)}
      ${pole('', 'Koszt stały', `<select id="wk-staly"><option value="auto"${c.staly == null ? ' selected' : ''}>wykrywaj automatycznie</option><option value="tak"${c.staly === 1 ? ' selected' : ''}>tak, stały</option><option value="nie"${c.staly === 0 ? ' selected' : ''}>nie, niestały</option></select>`)}
    </div>
    ${pole('', 'Uzasadnienie (po co to płacimy)', `<textarea id="wk-uz" rows="3" maxlength="500">${esc(c.uzasadnienie || '')}</textarea>`)}
    <p class="szary">${c.data_oceny ? `Ostatnia ocena ${dataPl(c.data_oceny)}. ` : ''}Kategoria nie zmienia rodzaju kosztu ani wyniku zarządczego.</p>
    <div class="akcje"><button class="glowny" id="wk-zapisz">Zapisz</button><button id="wk-obszar-nowy">Dodaj obszar</button>
      ${d.regula_wpis ? '<button id="wk-cof-kat">Cofnij moją kategorię</button>' : ''}${c.wpis ? '<button id="wk-cof-cel">Cofnij ostatnią zmianę celu</button>' : ''}</div>
    <h3>Płatności</h3>
    <div class="tabela-ramka niska"><table><thead><tr><th>Data</th><th>Rachunek</th><th class="liczba-kol">Kwota</th><th>Tytuł</th><th>Skąd przypisanie</th></tr></thead><tbody>${wiersze}</tbody></table></div>
    <div class="zrodlo">Źródło: wyciąg ING (${esc(d.platnosci[0]?.plik || '')}). Klucz kontrahenta: „${esc(d.klucz)}”.</div></div>`;
  k.hidden = false;
  $('.zamknij', k).onclick = () => { k.hidden = true; };
  k.querySelectorAll('select[data-op]').forEach(s => s.onchange = () => s.value && zmiana('kategoria_operacja', { operacja: d.platnosci[s.dataset.op].klucz, kategoria: s.value }));
  k.querySelectorAll('[data-cof]').forEach(b => b.onclick = () => zmiana('cofnij', { wpis: b.dataset.cof }));
  if ($('#wk-cof-kat')) $('#wk-cof-kat').onclick = () => zmiana('cofnij', { wpis: d.regula_wpis });
  if ($('#wk-cof-cel')) $('#wk-cof-cel').onclick = () => zmiana('cofnij', { wpis: c.wpis });
  $('#wk-obszar-nowy').onclick = async () => {
    const n = (window.prompt('Nazwa nowego obszaru (np. Szkolenia):') || '').trim();
    if (!n) return;
    const nowe = [...d.obszary.filter(o => !['Działalność spółki', 'New Business', 'Realizacja dla klientów', 'Zespół', 'Rozwój'].includes(o)), n];
    if (await zmiana('ustawienie', { klucz: 'obszary_wydatkow', wartosc: nowe })) wydKarta(klucz, okres);
  };
  $('#wk-zapisz').onclick = async () => {
    const wpisy = [];
    if ($('#wk-kat').value !== d.kategoria) wpisy.push(['kategoria_regula', { kontrahent: d.klucz, kategoria: $('#wk-kat').value }]);
    const cel = {};
    const stary = { obszar: c.obszar || '', kto: c.kto || '', uzasadnienie: c.uzasadnienie || '', ocena: c.ocena || '' };
    const nowy = { obszar: $('#wk-obszar').value, kto: $('#wk-kto').value.trim(), uzasadnienie: $('#wk-uz').value.trim(), ocena: $('#wk-ocena').value };
    for (const p of Object.keys(nowy)) if (nowy[p] !== stary[p]) cel[p] = nowy[p];
    const s = $('#wk-staly').value, sw = s === 'auto' ? null : s === 'tak';
    if (sw !== (c.staly == null ? null : !!c.staly)) cel.staly = sw;
    const r = $('#wk-roczna').value, rw = r === 'auto' ? null : r === 'tak';
    if (rw !== (c.roczna == null ? null : !!c.roczna)) cel.roczna = rw;
    if (Object.keys(cel).length) wpisy.push(['cel_wydatku', { kontrahent: d.klucz, ...cel }]);
    if (!wpisy.length) { k.hidden = true; return; }
    for (const [typ, dane] of wpisy.slice(0, -1)) if (!(await zmianaCicha(typ, dane))) return;
    zmiana(...wpisy[wpisy.length - 1]);
  };
}

// ---------- koszty stałe ----------
async function wydStale(p) {
  const d = await api('wydatki/stale');
  const poz = d.pozycje.filter(x => (!p.ocena || (p.ocena === 'brak' ? !x.ocena : x.ocena === p.ocena)) && (!p.obszar || (p.obszar === 'brak' ? !x.obszar : x.obszar === p.obszar)));
  const suma = poz.reduce((a, x) => a + x.miesiecznie, 0), sumaR = poz.reduce((a, x) => a + x.rocznie, 0);
  const tab = tabela({ id: 'wyd-stale', dane: poz, sortLokalny: true, onWiersz: x => wydKarta(x.kontrahent),
    kolumny: [
      { naglowek: 'Kontrahent', html: x => `${esc(x.nazwa)}<br><small class="szary">${esc(x.sposob)}</small>`, sortKlucz: x => x.nazwa.toLowerCase() },
      { naglowek: 'Kategoria', wartosc: x => x.kategoria_nazwa },
      { id: 'mies', naglowek: 'Miesięcznie', liczba: true, html: x => zl(x.miesiecznie), sortKlucz: x => x.miesiecznie },
      { id: 'rok', naglowek: 'Rocznie', liczba: true, html: x => zl(x.rocznie), sortKlucz: x => x.rocznie },
      { naglowek: 'Ostatnia płatność', html: x => `${dataPl(x.ostatnia_data)}<br><small class="szary">${zl(x.ostatnia_kwota)}${x.ostatnia_ile > 1 ? `, ${x.ostatnia_ile} płatności w miesiącu` : ''}</small>`, sortKlucz: x => x.ostatnia_data },
      { naglowek: 'Zmiana ceny', liczba: true, html: x => `${x.flagi.map(f => `<span class="chip ostrzezenie">${esc(f)}</span>`).join(' ')}${x.zmiana_ceny ? `<br><span class="${x.zmiana_ceny.proc > 0 ? 'minus' : 'plus'}">${x.zmiana_ceny.proc > 0 ? '+' : ''}${procent(x.zmiana_ceny.proc)}</span><br><small class="szary">${mies(x.zmiana_ceny.poprzedni_miesiac)} ${zl(x.zmiana_ceny.poprzednia, false)}, ${mies(x.zmiana_ceny.miesiac)} ${zl(x.zmiana_ceny.ostatnia, false)}</small>` : ''}`, sortKlucz: x => x.flagi.length * 1000 + (x.zmiana_ceny ? Math.abs(x.zmiana_ceny.proc) : 0) },
      { naglowek: 'Obszar', wartosc: x => x.obszar },
      { naglowek: 'Kto', wartosc: x => x.kto },
      { naglowek: 'Ocena', html: x => `${chipOceny(x.ocena)}${x.data_oceny ? `<br><small class="szary">${dataPl(x.data_oceny)}</small>` : ''}`, sortKlucz: x => x.ocena || 'zz' },
    ],
    stopkaSum: { mies: zl(suma), rok: zl(sumaR) } });
  const sumy = (tytul, lista, pustaNazwa) => `<div><h3>${tytul}</h3><div class="tabela-ramka niska"><table><thead><tr><th>${tytul.split(' ').pop()}</th><th class="liczba-kol">Pozycji</th>
    <th class="liczba-kol">Miesięcznie</th><th class="liczba-kol">Rocznie</th></tr></thead><tbody>${lista.map(x => `<tr><td>${esc(x.nazwa || pustaNazwa)}</td><td class="liczba-kol">${x.ile}</td>
    <td class="liczba-kol">${zl(x.miesiecznie)}</td><td class="liczba-kol">${zl(x.rocznie)}</td></tr>`).join('')}</tbody></table></div></div>`;
  const opcje = (lista, wart) => lista.map(([v, n]) => `<option value="${esc(v)}"${(wart || '') === v ? ' selected' : ''}>${esc(n)}</option>`).join('');
  setTimeout(() => {
    $('#wyd-f-ocena').onchange = e => ustawParametry({ ocena: e.target.value });
    $('#wyd-f-obszar').onchange = e => ustawParametry({ obszar: e.target.value });
  });
  return `${wydNaglowek(`Koszty stałe na ${dataPl(d.dzien_stanu)}, okno ${mies(d.okno[0])} do ${mies(d.okno[3])}`)}${wydZakladki(p, 'stale')}
    <div class="filtry">
      <label>Ocena<select id="wyd-f-ocena">${opcje([['', 'wszystkie'], ...Object.entries(WYD_OCENY), ['brak', 'bez oceny']], p.ocena)}</select></label>
      <label>Obszar<select id="wyd-f-obszar">${opcje([['', 'wszystkie'], ...d.obszary.map(o => [o, o]), ['brak', 'bez obszaru']], p.obszar)}</select></label>
      <span class="eksport-pasek">${przyciskiEksportu('wydatki/stale', { ocena: p.ocena && p.ocena !== 'brak' ? p.ocena : '', obszar: p.obszar && p.obszar !== 'brak' ? p.obszar : '' }, 'Pobierz listę')}</span>
    </div>
    <div class="kafle">
      <div class="kafel glowny"><div class="tytul">Koszty stałe miesięcznie ${pytajnik('wyd_stale')}</div><div class="wartosc">${zl(suma)}</div><div class="dop">${poz.length} kontrahentów${poz.length !== d.pozycje.length ? ` (z ${d.pozycje.length}, filtr)` : ''}</div></div>
      <div class="kafel"><div class="tytul">Rocznie</div><div class="wartosc">${zl(sumaR)}</div><div class="dop">12 razy koszt miesięczny, opłaty roczne w pełnej kwocie</div></div>
      <div class="kafel"><div class="tytul">Do oceny</div><div class="wartosc">${d.pozycje.filter(x => !x.ocena).length}</div><div class="dop">bez oceny; do wypowiedzenia: ${d.pozycje.filter(x => x.ocena === 'do_wypowiedzenia').length}</div></div>
    </div>
    ${tab}
    <p class="notka">Kwoty brutto z banku. Kliknij wiersz, żeby wpisać obszar, osobę, uzasadnienie i ocenę albo oznaczyć kontrahenta jako niestały. Sumy niżej liczą całą listę, bez filtrów.</p>
    <div class="wykresy-2">${sumy('Wg obszaru', d.wg_obszaru, 'bez obszaru')}${sumy('Wg osoby', d.wg_osoby, 'bez osoby')}</div>
    <h2 class="sekcja">Wygasłe: ${d.wygasle.length} ${pytajnik('wyd_stale')}</h2>
    ${tabela({ id: 'wyd-wygasle', dane: d.wygasle, sortLokalny: true, onWiersz: x => wydKarta(x.kontrahent),
      kolumny: [{ naglowek: 'Kontrahent', wartosc: x => x.nazwa }, { naglowek: 'Kategoria', wartosc: x => x.kategoria_nazwa },
        { naglowek: 'Ostatnia płatność', html: x => dataPl(x.ostatnia_data), sortKlucz: x => x.ostatnia_data },
        { naglowek: 'Kwota w tamtym miesiącu', liczba: true, html: x => zl(x.ostatnia_kwota), sortKlucz: x => x.ostatnia_kwota },
        { naglowek: 'Dlaczego', wartosc: x => x.powod }] })}
    <p class="notka">Wygasłe: płacone regularnie, ale bez płatności w ostatnim pełnym miesiącu (${mies(d.ostatni_pelny)}) ani w bieżącym. Nie liczą się do sum. Gdy to nadal koszt (np. przesunięty termin), oznacz w karcie „tak, stały”.</p>`;
}

// ---------- do decyzji ----------
async function wydDecyzje(p) {
  const d = await api('wydatki/do-decyzji', { od: p.od, do: p.do });
  const nie = tabela({ id: 'wyd-nie', dane: d.nieprzypisane, sortLokalny: true, onWiersz: x => wydKarta(x.klucz, d),
    kolumny: [{ naglowek: 'Kontrahent', wartosc: x => x.nazwa }, { naglowek: 'Płatności', liczba: true, wartosc: x => x.ile },
      { naglowek: 'Suma', liczba: true, html: x => zl(x.suma), sortKlucz: x => x.suma }, { naglowek: 'Ostatnia', html: x => dataPl(x.ostatnia), sortKlucz: x => x.ostatnia }] });
  const RODZ = { praca: 'koszty pracy', staly: 'koszt stały', podatki: 'podatki', vat: 'VAT', dywidenda: 'podział zysku', zwrot: 'zwrot dla klienta' };
  const niezg = tabela({ id: 'wyd-niezg', dane: d.niezgodne, sortLokalny: true,
    kolumny: [{ naglowek: 'Kontrahent', html: x => `${esc(x.nazwa)}${x.od_mata ? ' <span class="chip akcent">Twoja kategoria</span>' : ''}` , sortKlucz: x => x.nazwa.toLowerCase() },
      { naglowek: 'Kategoria', wartosc: x => x.kategoria_nazwa }, { naglowek: 'Rodzaj teraz', html: x => `<span class="chip ${x.typ === 'bez_rodzaju' ? 'ostrzezenie' : 'neutral'}">${esc(x.rodzaj_nazwa)}</span>` },
      { naglowek: 'Pasuje rodzaj', wartosc: x => x.zgodne_rodzaje.join(', ') },
      { naglowek: 'Płatności', liczba: true, wartosc: x => x.ile }, { naglowek: 'Suma', liczba: true, html: x => zl(x.suma), sortKlucz: x => x.suma },
      { naglowek: '', html: (x) => `${x.rodzaj_podpowiedz ? `<button class="przycisk maly" data-rodzaj="${esc(x.rodzaj_podpowiedz)}" data-klucze="${esc(JSON.stringify(x.klucze))}">Ustaw rodzaj: ${esc(RODZ[x.rodzaj_podpowiedz])}</button>` : ''}
        <button class="przycisk maly" data-karta-kontr="${esc(x.klucz)}">Zmień kategorię</button>` }] });
  setTimeout(() => {
    document.querySelectorAll('#wyd-niezg [data-rodzaj]').forEach(b => b.onclick = e => {
      e.stopPropagation();
      const klucze = JSON.parse(b.dataset.klucze), rodzaj = b.dataset.rodzaj;
      const wpisy = klucze.map(kk => ({ typ: 'koszt_regula', dane: { kontrahent: kk, rodzaj, klient: '' } }));
      zmiana(wpisy.length === 1 ? wpisy[0].typ : 'seria', wpisy.length === 1 ? wpisy[0].dane : { wpisy });
    });
    document.querySelectorAll('#wyd-niezg [data-karta-kontr]').forEach(b => b.onclick = e => { e.stopPropagation(); wydKarta(b.dataset.kartaKontr, d); });
  });
  const suma = l => zl(l.reduce((a, x) => a + x.suma, 0));
  return `${wydNaglowek(`Do decyzji, ${dataPl(d.od)} do ${dataPl(d.do)}`)}${wydZakladki(p, 'decyzje')}
    <p class="notka">${pytajnik('wyd_decyzje')} Apka nic tu nie zmienia sama. Kategoria nie zmienia rodzaju kosztu, a od rodzaju zależy wynik zarządczy, rezerwa i cash flow. „Ustaw rodzaj” zapisuje regułę rodzaju dla kontrahenta (jak w Reguły przypisań); koszt klienta przypiszesz z klientem na liście wydatków.</p>
    <h2 class="sekcja">Bez kategorii (Nieprzypisane): ${d.nieprzypisane.length} kontrahentów, ${suma(d.nieprzypisane)}</h2>${nie}
    <h2 class="sekcja">Kategoria nie pasuje do rodzaju: ${d.niezgodne.length} pozycji, ${suma(d.niezgodne)}</h2>${niezg}`;
}

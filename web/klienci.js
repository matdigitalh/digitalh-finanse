'use strict';
// Pakiet 11 (BL-02, część formalna): lista klientów z kolumnami umowy i karta klienta z umową edytowaną na miejscu.
// Lista łączy GET /api/klienci (obroty, należności, marża; z niej idzie eksport do Excela) z GET /api/klienci/umowy
// (stan umowy, typ, wypowiedzenie, termin, wartość, folder i plany w budżecie). Karta: GET /api/klienci/karta.
// Umowę zapisuje istniejący wpis „umowa” (rejestr umów); pola, które doda pakiet 9 (folder, arkusze), wracają w zapisie
// bez zmian (u.dane). Korzysta z app.js (api, zmiana, tabela, filtr, zl, dataPl, ...) i budzet.js (naGrosze, nowyId).
(() => {

const STAN_KLASA = { 'minął': 'minus', alert: 'ostrzezenie', ok: 'plus', 'brak umowy': 'neutral' };
const KOLEJ_STANU = { 'minął': 0, alert: 1, 'brak umowy': 2, ok: 3 };
const klucz = s => String(s || '').trim().replace(/\s+/g, ' ').toLowerCase();
const chipUmowy = s => `<span class="chip ${STAN_KLASA[s] || 'neutral'}">${esc(s)}</span>`;
const dniTekst = d => d == null ? '' : d < 0 ? `${-d} dni temu` : d === 0 ? 'dziś' : `za ${d} dni`;

Object.assign(POMOC, {
  klienci: { tytul: 'Klienci i umowy', krotko: 'Wszyscy klienci w jednym miejscu: umowa, obroty, należności i plany w budżecie.',
    co: 'Każdy wiersz to klient: stan umowy (ok, alert, minął, brak umowy), typ i okres wypowiedzenia, najbliższy termin, wartość miesięczna, plany wpływów na 12 miesięcy oraz przychód, należność i marża z faktur.',
    skad: 'Obroty i należności z Fakturowni i banku. Umowy z rejestru umów (wpisujesz je Ty). Plany z arkuszy w folderze klienta w budżecie.',
    jak: 'Alert: do terminu zostało mniej dni, niż ustawiłeś w umowie. Minął: termin już był. Brak umowy: klient nie ma umowy w rejestrze.',
    zrob: 'Filtr „Do decyzji” pokazuje umowy, przy których trzeba coś zrobić. Kliknij klienta, żeby otworzyć jego kartę i poprawić umowę.' },
  klient: { tytul: 'Karta klienta', krotko: 'Umowa, obroty, należności, rentowność i plany klienta na jednym ekranie.',
    co: 'U góry dane klienta i umowa. Umowę poprawiasz od razu na karcie i zapisujesz przyciskiem. Niżej obroty z faktur, rentowność i plany w budżecie na 12 miesięcy.',
    skad: 'NIP i nabywcy z faktur w Fakturowni. Folder i arkusze z budżetu (folder o nazwie klienta). Umowa z rejestru umów.',
    jak: 'Ostatni dzień na wypowiedzenie dotyczy umowy, która sama się przedłuża: po tym dniu przedłuży się na kolejny okres. Termin odejścia: kiedy najwcześniej skończy się współpraca, jeśli jedna ze stron wypowie umowę dziś. Plany po końcu umowy: budżet ma plany wpływów po dacie końca umowy na czas określony; zostają w cash flow, apka tylko ostrzega.',
    zrob: 'Uzupełnij umowę każdemu klientowi z planami w budżecie. Gdy pojawi się alert, zdecyduj: przedłużyć, renegocjować albo wypowiedzieć.' },
});

// ---------- Lista klientów ----------
async function listaKlientow(p) {
  const [d, u] = await Promise.all([api('klienci', p), api('klienci/umowy')]);
  const um = new Map(u.klienci.map(x => [klucz(x.klient), x]));
  const fin = new Map(d.klienci.map(x => [klucz(x.klient), x]));
  const zero = { faktur: 0, przychod: 0, wplaty: 0, naleznosc: 0, po_terminie: 0, koszty: 0, marza: 0, marza_proc: null };
  const brak = { stan: 'brak umowy', umowa: null, plany_12m: 0, arkusze: [], ostrzezenia: [] };
  const wszystkie = [...d.klienci.map(x => ({ ...x, u: um.get(klucz(x.klient)) || brak })),
    ...u.klienci.filter(x => !fin.has(klucz(x.klient))).map(x => ({ ...zero, klient: x.klient, u: x }))];
  const q = klucz(p.q);
  const dane = wszystkie.filter(x => (!p.stan || (p.stan === 'decyzja' ? ['alert', 'minął'].includes(x.u.stan) : x.u.stan === p.stan))
    && (!p.typ || (p.typ === 'brak' ? !x.u.umowa : !!x.u.umowa && (p.typ === 'okreslony') === !!x.u.umowa.okreslony))
    && (!q || klucz(x.klient).includes(q)));
  const termin = x => {
    const o = x.u.umowa;
    if (!o) return '';
    if (o.ostatni_dzien_wypowiedzenia) return `<b>${dataPl(o.ostatni_dzien_wypowiedzenia.ich)}</b><div class="szary">ostatni dzień na wypowiedzenie · ${dniTekst(o.dni)}</div>`;
    if (o.okreslony) return `<b>${dataPl(o.termin)}</b><div class="szary">umowa wygasa · ${dniTekst(o.dni)}</div>`;
    return `<span class="szary">w każdej chwili</span><div class="szary">odejście najwcześniej ${dataPl(o.termin_odejscia)}</div>`;
  };
  const kol = [
    { naglowek: 'Klient', html: x => `${esc(x.klient)}${x.u.folder ? '' : ' <span class="szary" title="W budżecie nie ma folderu o tej nazwie">(bez folderu)</span>'}`, sortKlucz: x => x.klient },
    { naglowek: 'Umowa', html: x => chipUmowy(x.u.stan) + (x.u.ostrzezenia || []).filter(o => o.rodzaj === 'plany_po_koncu')
      .map(o => ` <span class="chip ostrzezenie" title="${esc(o.tekst)}">plany po końcu</span>`).join(''), sortKlucz: x => KOLEJ_STANU[x.u.stan] },
    { naglowek: 'Typ', wartosc: x => x.u.umowa?.typ || '', sortKlucz: x => x.u.umowa?.typ || '~' },
    { naglowek: 'Wypowiedzenie', wartosc: x => x.u.umowa?.wypowiedzenie || '', sortKlucz: x => x.u.umowa?.wypowiedzenie || '~' },
    { naglowek: 'Termin', html: termin, sortKlucz: x => x.u.umowa?.ostatni_dzien_wypowiedzenia?.ich || (x.u.umowa?.okreslony ? x.u.umowa.termin : '') || '9999' },
    { id: 'wartosc', naglowek: 'Wartość / mies.', liczba: true, wartosc: x => x.u.umowa?.wartosc_mies ? zl(x.u.umowa.wartosc_mies, false) : '', sortKlucz: x => x.u.umowa?.wartosc_mies || 0 },
    { id: 'plany', naglowek: 'Plany wpływów 12 mies.', liczba: true, wartosc: x => x.u.plany_12m ? zl(x.u.plany_12m, false) : '', sortKlucz: x => x.u.plany_12m || 0 },
    { id: 'przychod', naglowek: 'Przychód netto', liczba: true, wartosc: x => zl(x.przychod, false), sortKlucz: x => x.przychod },
    { naglowek: 'Należność', liczba: true, wartosc: x => x.naleznosc ? zl(x.naleznosc, false) : '', klasa: x => x.po_terminie ? 'minus' : '', sortKlucz: x => x.naleznosc },
    { id: 'marza', naglowek: 'Marża wstępna', liczba: true, wartosc: x => zl(x.marza, false), sortKlucz: x => x.marza },
    { naglowek: '%', liczba: true, wartosc: x => procent(x.marza_proc), klasa: x => x.marza_proc != null && x.marza_proc < 30 ? 'minus' : '', sortKlucz: x => x.marza_proc ?? -1e9 },
  ];
  const s = f => dane.reduce((a, x) => a + (f(x) || 0), 0);
  const doDecyzji = wszystkie.filter(x => ['alert', 'minął'].includes(x.u.stan)).length;
  const bezUmowy = wszystkie.filter(x => x.u.stan === 'brak umowy' && x.u.plany_12m).length;
  setTimeout(() => {
    const i = $('#klienci-szukaj');
    let t;
    if (i) i.oninput = () => { clearTimeout(t); t = setTimeout(() => ustawParametry({ q: i.value }), 300); };
  });
  return `<div class="naglowek-strony"><div><h1>Klienci ${pytajnik('klienci')}</h1>
      <div class="okruszki">Budżet / Foldery klientów · ${wszystkie.length} klientów${doDecyzji ? ` · <a href="#/budzet?stan=decyzja" class="minus">${doDecyzji} umów do decyzji</a>` : ''}${bezUmowy ? ` · ${bezUmowy} z planami bez umowy` : ''}</div></div>
      <a class="przycisk" href="#/budzet/umowy">${ik('dokument')}Rejestr umów</a></div>
    <div class="filtry">${filtr('rok', 'Rok', [['', 'Wszystko'], ...d.lata.map(r => [r, r])], d.rok || '')}
      ${filtr('stan', 'Stan umowy', [['', 'Wszystkie'], ['decyzja', 'Do decyzji (alert, minął)'], ['ok', 'ok'], ['alert', 'alert'], ['minął', 'minął'], ['brak umowy', 'brak umowy']], p.stan || '')}
      ${filtr('typ', 'Umowa', [['', 'Wszystkie'], ['okreslony', 'na czas określony'], ['nieokreslony', 'na czas nieokreślony'], ['brak', 'bez umowy']], p.typ || '')}
      <label>Szukaj<input id="klienci-szukaj" type="search" value="${esc(p.q || '')}" placeholder="nazwa klienta"></label></div>
    <p class="notka">Przychód z faktur (netto, wg daty sprzedaży), koszty klienta z banku i rejestru biura. Kolumny umowy z rejestru umów, plany wpływów z arkuszy w folderze klienta (od bieżącego miesiąca, 12 miesięcy). Czerwony procent: marża poniżej 30%.${d.przenoszone_bez_klienta.ile ? ` Koszty klientów bez wskazanego klienta: ${d.przenoszone_bez_klienta.ile} płatności, ${zl(d.przenoszone_bez_klienta.kwota)}.` : ''}</p>
    ${tabela({ kolumny: kol, dane, poczatek: 1, sortLokalny: true,
      stopkaSum: { wartosc: zl(s(x => x.u.umowa?.wartosc_mies), false), plany: zl(s(x => x.u.plany_12m), false), przychod: zl(s(x => x.przychod), false), marza: zl(s(x => x.marza), false) },
      onWiersz: x => { location.hash = `#/budzet/klient?nazwa=${encodeURIComponent(x.klient)}${d.rok ? '&rok=' + d.rok : ''}`; } })}`;
}

// ---------- Karta klienta ----------
function polaUmowy(u) {
  const w = u || {};
  const zl2 = gr => gr ? (gr / 100).toFixed(2).replace('.', ',') : '';
  return `<div class="formularz umowa-form">
    ${pole('', 'Data podpisania (zawarcia)', `<input id="ku-zawarta" type="date" value="${esc(w.zawarta || '')}">`)}
    ${pole('', 'Czas trwania', `<select id="ku-rodzaj"><option value="nieokreslony">nieokreślony</option><option value="okreslony"${w.rodzaj === 'okreslony' ? ' selected' : ''}>określony</option></select>`)}
    ${pole('', 'Koniec umowy', `<input id="ku-do" type="date" value="${esc(w.do || '')}">`)}
    ${pole('', 'Przedłuża się automatycznie', `<select id="ku-przedl"><option value="">nie</option><option value="1"${w.przedluzenie ? ' selected' : ''}>tak</option></select>`)}
    ${pole('', 'Okres wypowiedzenia (miesiące)', `<input id="ku-okres" inputmode="numeric" value="${esc(w.wypowiedzenie_mies ?? 1)}">`)}
    ${pole('', 'Ze skutkiem na koniec miesiąca', `<select id="ku-km"><option value="1">tak</option><option value=""${w.koniec_miesiaca === false ? ' selected' : ''}>nie</option></select>`)}
    ${pole('', 'Wartość netto / mies. (zł)', `<input id="ku-wartosc" inputmode="decimal" value="${esc(zl2(w.wartosc_mies))}" placeholder="np. 6 000,00">`)}
    ${pole('', 'Alert: ile dni przed terminem', `<input id="ku-alert" inputmode="numeric" value="${esc(w.alert_dni ?? 30)}">`)}
    ${pole('', 'Uwagi', `<input id="ku-uwagi" maxlength="300" value="${esc(w.uwagi || '')}">`)}</div>`;
}

function stanUmowyHtml(o) {
  if (!o) return '<dl class="umowa-stan"><dt>Stan</dt><dd>' + chipUmowy('brak umowy') + '</dd></dl><p class="szary">Klient nie ma umowy w rejestrze. Uzupełnij pola i zapisz.</p>';
  const ost = o.ostatni_dzien_wypowiedzenia;
  const wyp = ost ? `z naszej strony: <b>${dataPl(ost.nasza)}</b><br>z ich strony: <b>${dataPl(ost.ich)}</b><div class="szary">${dniTekst(o.dni)}; po tym dniu umowa przedłuży się na kolejny okres</div>`
    : o.okreslony ? `<span class="szary">nie trzeba wypowiadać: umowa wygasa ${dataPl(o.dane.do)}</span>`
      : '<span class="szary">w każdej chwili (czas nieokreślony)</span>';
  return `<dl class="umowa-stan">
    <dt>Stan</dt><dd>${chipUmowy(o.stan)} <span class="szary">${esc(o.typ)}; wypowiedzenie ${esc(o.wypowiedzenie)}</span></dd>
    <dt>Ostatni dzień na wypowiedzenie</dt><dd>${wyp}</dd>
    <dt>Termin odejścia przy wypowiedzeniu dziś</dt><dd>${o.termin_odejscia ? dataPl(o.termin_odejscia) : '<span class="szary">nieznany (brak daty zawarcia)</span>'}</dd>
    ${o.plany_po_koncu ? `<dt>Plany po końcu umowy</dt><dd class="minus">${o.plany_po_koncu.ile} mies. od ${mies(o.plany_po_koncu.od)}, razem ${zl(o.plany_po_koncu.kwota)}</dd>` : ''}
  </dl>`;
}

function podepnijFormularzUmowy(d, o) {
  const pokazPola = () => {
    const okr = $('#ku-rodzaj').value === 'okreslony';
    $('#ku-do').closest('.pole').hidden = !okr;
    $('#ku-przedl').closest('.pole').hidden = !okr;
  };
  $('#ku-rodzaj').onchange = pokazPola;
  pokazPola();
  $('#ku-zapisz').onclick = () => {
    const rodzaj = $('#ku-rodzaj').value;
    const wart = $('#ku-wartosc').value.trim();
    const gr = wart ? naGrosze(wart) : 0;
    if (gr == null) return komunikat('Wartość miesięczną wpisz liczbą, np. 6 000,00.', true);
    if (rodzaj === 'okreslony' && !$('#ku-do').value) return komunikat('Umowa na czas określony potrzebuje daty końca.', true);
    // pola, których karta nie edytuje (np. folder i arkusze z pakietu 9), wracają bez zmian
    zmiana('umowa', { ...(o?.dane || {}), id: o?.id || nowyId('u'), klient: d.klient, zawarta: $('#ku-zawarta').value, rodzaj,
      do: rodzaj === 'okreslony' ? $('#ku-do').value : '', przedluzenie: rodzaj === 'okreslony' && !!$('#ku-przedl').value,
      wypowiedzenie_mies: $('#ku-okres').value.trim() || '0', koniec_miesiaca: !!$('#ku-km').value, wartosc_mies: String(gr),
      alert_dni: $('#ku-alert').value.trim() || '30', uwagi: $('#ku-uwagi').value });
  };
  const usun = $('#ku-usun');
  if (usun) usun.onclick = e => {
    e.stopPropagation();
    kartaFormularza('Usunąć umowę?', `<p>Umowa klienta ${esc(d.klient)} zniknie z rejestru umów i z alertów. Wpis zostaje w pliku zmian, więc da się go cofnąć.</p>`,
      'Tak, usuń', () => zmiana('umowa', { id: o.id, usun: true }));
  };
}

async function kartaKlienta(p) {
  const d = await api('klienci/karta', p);
  const o = (p.umowa && d.umowy.find(x => x.id === p.umowa)) || d.umowa;
  const f = d.obroty;
  const link = (extra = '') => `#/budzet/klient?nazwa=${encodeURIComponent(d.klient)}${d.rok ? '&rok=' + d.rok : ''}${extra}`;
  const ostrz = d.ostrzezenia.map(x => `<div class="komunikat${x.rodzaj === 'brak_umowy' ? '' : ' blad'}"><span>${esc(x.tekst)}</span></div>`).join('')
    + (o && ['alert', 'minął'].includes(o.stan) ? `<div class="komunikat blad"><span>Umowa wymaga decyzji: ${esc(o.co || '')}, ${dataPl(o.termin)} (${dniTekst(o.dni)}).</span></div>` : '');
  const inne = d.umowy.length > 1 ? `<p class="szary">Inne umowy klienta: ${d.umowy.filter(x => x.id !== o?.id).map(x => `<a href="${link('&umowa=' + encodeURIComponent(x.id))}">${esc(x.typ)}</a>`).join(', ')}</p>` : '';
  const arkusze = d.arkusze.length ? d.arkusze.map(a => `<a href="#/budzet/arkusz?id=${encodeURIComponent(a.id)}">${esc(a.nazwa)}</a> <span class="szary">${esc(a.kategoria)}</span>`).join('<br>')
    : '<span class="szary">brak arkuszy</span>';
  const r = d.rentownosc, b = d.budzet;
  const rent = `<div class="tabela-ramka niska"><table><thead><tr><th></th><th class="liczba-kol">Faktury i bank (wynik zarządczy)</th><th class="liczba-kol">Budżet, pozycje Księgowane</th></tr></thead><tbody>
    <tr><td>Przychód (wpływy netto)</td><td class="liczba-kol">${r ? zl(r.obrot) : ''}</td><td class="liczba-kol">${b ? zl(b.wplywy) : ''}</td></tr>
    <tr><td>Koszty klienta (obciążenia netto)</td><td class="liczba-kol minus">${r ? zl(-r.koszty) : ''}</td><td class="liczba-kol minus">${b ? zl(-b.obciazenia) : ''}</td></tr>
    <tr><td>Koszt pracy zespołu${r?.udzial_czasu != null ? ` (${procent(r.udzial_czasu)} czasu)` : ''}</td><td class="liczba-kol minus">${r?.koszt_pracy != null ? zl(-r.koszt_pracy) : '<a href="#/rentownosc/rent-klienci">wpisz udział czasu</a>'}</td><td class="liczba-kol szary">w obciążeniach, gdy jest w arkuszu</td></tr>
    <tr class="wynik"><td><b>Wynik</b></td><td class="liczba-kol"><b>${r ? zl(r.wynik_klienta ?? r.pna) : ''}</b></td><td class="liczba-kol"><b>${b ? zl(b.wynik) : ''}</b></td></tr>
    <tr><td>Marża</td><td class="liczba-kol">${r ? procent(r.marza_proc) : ''}</td><td class="liczba-kol">${b ? procent(b.marza) : ''}</td></tr>
    </tbody></table></div>`;
  const plany = d.plany.map(x => `<tr><td>${mies(x.miesiac)}</td><td class="liczba-kol">${x.plan_wplywy ? zl(x.plan_wplywy, false) : ''}</td>
    <td class="liczba-kol">${x.rzecz_wplywy ? zl(x.rzecz_wplywy, false) : ''}</td><td class="liczba-kol minus">${x.obciazenia ? zl(-x.obciazenia, false) : ''}</td>
    <td class="liczba-kol ${x.plan_wplywy + x.rzecz_wplywy - x.obciazenia < 0 ? 'minus' : ''}">${zl(x.plan_wplywy + x.rzecz_wplywy - x.obciazenia, false)}</td>
    ${o?.wartosc_mies ? `<td class="liczba-kol szary">${zl(o.wartosc_mies, false)}</td>` : ''}</tr>`).join('');
  const tf = d.faktury.slice(0, 50).map(x => `<tr data-q="${esc(x.numer)}"><td>${esc(x.numer)}</td><td>${dataPl(x.data_sprzedazy || x.data_wystawienia)}</td><td class="szary">${esc(x.nabywca)}</td>
    <td class="liczba-kol">${zl(x.netto, false)}</td><td>${chipBank({ stan_bank: x.stan, dni_po_terminie: x.dni_po_terminie })}</td></tr>`).join('');
  const tk = d.koszty.slice(0, 50).map(x => `<tr data-op="${x.id}"><td>${dataPl(x.data_ksiegowania)}</td><td>${esc(x.kontrahent)}</td><td class="szary">${esc(x.tytul)}</td>
    <td class="liczba-kol minus">${zl(-(x.koszt || 0), false)}</td><td>${chipDok(x.dokument)}</td></tr>`).join('');
  setTimeout(() => {
    podepnijFormularzUmowy(d, o);
    if (d.miesiace.length) Wykresy.slupki($('#klient-wyk'), { kategorie: d.miesiace.map(m => mies(m.miesiac)), etykietyPelne: d.miesiace.map(m => miesPelny(m.miesiac)),
      wysokosc: 220, opis: 'Przychód i koszty klienta', serie: [
        { klucz: 'p', nazwa: 'Przychód netto', kolor: Wykresy.kolor('--s1'), wartosci: d.miesiace.map(m => m.przychod) },
        { klucz: 'k', nazwa: 'Koszty klienta', kolor: Wykresy.kolor('--s2'), wartosci: d.miesiace.map(m => m.koszty) }] });
    document.querySelectorAll('tr[data-q]').forEach(tr => tr.onclick = () => { location.hash = `#/platnosci/faktury?q=${encodeURIComponent(tr.dataset.q)}`; });
    document.querySelectorAll('tr[data-op]').forEach(tr => tr.onclick = () => { location.hash = `#/budzet/wydatki?klient=${encodeURIComponent(d.klient)}&rodzaj=przenoszony`; });
  });
  return `<div class="naglowek-strony"><div><h1>${esc(d.klient)} ${pytajnik('klient')}</h1>
      <div class="okruszki"><a href="#/budzet">Klienci</a> / karta klienta${d.rok ? ' / ' + d.rok : ''} · stan na ${dataPl(d.dzien_stanu)}</div></div>
      <div>${chipUmowy(d.stan)}</div></div>
    <div class="filtry">${filtr('rok', 'Rok', [['', 'Wszystko'], ...d.lata.map(x => [x, x])], d.rok || '')}</div>
    ${ostrz}
    <div class="karta-klienta">
      <section class="karta-wyk"><h3>${ik('osoby')}Dane klienta</h3>
        <dl class="dane-klienta"><dt>NIP</dt><dd>${d.nip.length ? d.nip.map(esc).join(', ') : '<span class="szary">brak na fakturach</span>'}</dd>
          <dt>Nabywcy na fakturach</dt><dd>${d.nabywcy.length ? d.nabywcy.map(n => `${esc(n.nabywca)} <span class="szary">(${n.faktur} faktur)</span>`).join('<br>') : '<span class="szary">brak faktur</span>'}</dd>
          <dt>Folder budżetu</dt><dd>${d.folder ? esc(d.folder) : '<span class="szary">w budżecie nie ma folderu o nazwie klienta</span>'}</dd>
          <dt>Arkusze</dt><dd>${arkusze}</dd>
          <dt>Ostatni plan wpływu</dt><dd>${d.ostatni_plan ? mies(d.ostatni_plan) : '<span class="szary">brak planów</span>'}</dd></dl>
        <p class="szary">Folder i arkusze klienta dobiera apka po nazwie folderu. Ręczne powiązanie umowy z arkuszami dojdzie razem z cash flow.</p></section>
      <section class="karta-wyk"><h3>${ik('dokument')}Umowa</h3>
        ${stanUmowyHtml(o)}${inne}
        ${polaUmowy(o?.dane)}
        <div class="akcje"><button class="glowny" id="ku-zapisz">${o ? 'Zapisz umowę' : 'Dodaj umowę'}</button>${o ? '<button id="ku-usun">Usuń umowę</button>' : ''}</div></section>
    </div>
    <h2 class="sekcja">Obroty i należności${d.rok ? ` ${d.rok}` : ''}</h2>
    <div class="kafle">
      <div class="kafel"><div class="tytul">Przychód netto</div><div class="wartosc">${zl(f.przychod)}</div><div class="dop">${f.faktur} faktur</div></div>
      <div class="kafel"><div class="tytul">Wpłacono</div><div class="wartosc">${zl(f.wplaty)}</div><div class="dop">z banku, brutto</div></div>
      <a class="kafel klik" href="#/platnosci/naleznosci?q=${encodeURIComponent(d.nabywcy[0]?.nabywca || d.klient)}"><div class="tytul">Należność</div><div class="wartosc${f.po_terminie ? ' minus' : ''}">${zl(f.naleznosc)}</div>
        <div class="dop">${f.po_terminie ? `po terminie ${zl(f.po_terminie)}` : 'nic po terminie'}</div></a>
      <div class="kafel"><div class="tytul">Koszty klienta</div><div class="wartosc minus">${zl(-(f.koszty || 0))}</div><div class="dop">media, druk, podwykonawcy</div></div>
      <div class="kafel"><div class="tytul">Marża wstępna</div><div class="wartosc">${zl(f.marza)}</div><div class="dop">${procent(f.marza_proc)} przychodu, przed kosztami pracy</div></div>
    </div>
    <div class="karta-wyk"><h3>Przychód i koszty miesięcznie</h3><div class="pod">koszty klienta: netto z dokumentu, bez dokumentu kwota z banku</div>${d.miesiace.length ? '<div id="klient-wyk"></div>' : '<span class="szary">Brak danych.</span>'}</div>
    <h2 class="sekcja">Rentowność ${d.rok_rentownosci} ${d.folder ? `<a class="szary" href="#/rentownosc/przestawna?rok=${d.rok_rentownosci}&folder=${encodeURIComponent(d.folder)}&poziomy=kategoria,arkusz,kontrahent">rentowność budżetu klienta →</a>` : ''}</h2>
    ${rent}
    <h2 class="sekcja">Plany w budżecie, 12 miesięcy <span class="szary">${d.arkusze.length} arkuszy</span></h2>
    ${d.arkusze.length ? `<div class="tabela-ramka niska"><table><thead><tr><th>Miesiąc</th><th class="liczba-kol">Plan wpływów</th><th class="liczba-kol">Wpływy rzeczywiste</th>
      <th class="liczba-kol">Obciążenia</th><th class="liczba-kol">Saldo</th>${o?.wartosc_mies ? '<th class="liczba-kol">Wartość z umowy</th>' : ''}</tr></thead><tbody>${plany}</tbody></table></div>`
      : '<p class="szary">Klient nie ma arkuszy w budżecie.</p>'}
    <h2 class="sekcja">Faktury <span class="szary">${d.faktury.length}${d.faktury.length > 50 ? ', pokazane 50 najnowszych' : ''}</span></h2>
    ${tf ? `<div class="tabela-ramka niska"><table><thead><tr><th>Numer</th><th>Sprzedaż</th><th>Nabywca</th><th class="liczba-kol">Netto PLN</th><th>W banku</th></tr></thead><tbody>${tf}</tbody></table></div>` : '<p class="szary">Brak faktur.</p>'}
    <h2 class="sekcja">Koszty klienta <span class="szary">${d.koszty.length}</span></h2>
    ${tk ? `<div class="tabela-ramka niska"><table><thead><tr><th>Data</th><th>Kontrahent</th><th>Tytuł</th><th class="liczba-kol">Koszt PLN</th><th>Dokument</th></tr></thead><tbody>${tk}</tbody></table></div>` : '<p class="szary">Brak przypisanych kosztów.</p>'}`;
}

Object.assign(WIDOKI, { budzet: listaKlientow, 'budzet/klient': kartaKlienta });

})();

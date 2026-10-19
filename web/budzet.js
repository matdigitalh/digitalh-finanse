'use strict';
// Budżet jak w Budget Studio (folder → kategoria → arkusz), listy płatności planu, rozjazdy, historia, ustawienia,
// cash flow, rentowność klientów i arkuszy. Korzysta z funkcji z app.js (api, zmiana, tabela, zl, ...).

const ETAPY_KLASA = { 'Opłacona': 'plus', 'Planowana': 'neutral', 'Po terminie': 'minus', 'Wystawiona': 'akcent',
  'Częściowo opłacona': 'ostrzezenie', 'Opłacona wg BS': 'ostrzezenie', 'Nieaktualna': 'neutral' };
const chipEtap = e => `<span class="chip ${ETAPY_KLASA[e] || 'neutral'}">${esc(e || '')}</span>`;
const PODSTAWY = ['Faktura (jedna)', 'Faktura (w worku)', 'Bez faktury', 'Bez faktury (w worku)', 'Umowa o dzieło', 'Umowa zlecenie',
  'Umowa o pracę', 'Podatek VAT', 'Podatek dochodowy'];
const WOREK = ['Faktura (w worku)', 'Bez faktury (w worku)'];
const UMOWY = { 'Umowa o dzieło': ['osoba', 'us'], 'Umowa zlecenie': ['osoba', 'us', 'zus'], 'Umowa o pracę': ['osoba', 'us', 'zus'] };
const SKLADOWE = { osoba: 'dla osoby (na rękę)', us: 'PIT (urząd skarbowy)', zus: 'ZUS (wszystkie składki)' };
// Co oznacza kwota w komórce (A-KOL-10)
const KWOTA_KOMORKI = { 'Faktura (jedna)': 'netto; VAT i brutto policzy apka ze stawki wiersza', 'Faktura (w worku)': 'netto na cały miesiąc; apka podzieli ją na tygodnie',
  'Bez faktury': 'kwota tak, jak jest, bez VAT', 'Bez faktury (w worku)': 'kwota na cały miesiąc; apka podzieli ją na tygodnie',
  'Umowa o dzieło': 'brutto umowy (wynagrodzenie z zaliczką PIT)', 'Umowa zlecenie': 'pełny koszt zleceniodawcy', 'Umowa o pracę': 'pełny koszt pracodawcy' };
const zlWpis = gr => gr == null || gr === '' ? '' : (gr / 100).toFixed(2).replace('.', ',');
const plusDni = (iso, n) => { const d = new Date(iso + 'T12:00:00Z'); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); };
const roznicaDni = (a, b) => Math.round((new Date(b + 'T12:00:00Z') - new Date(a + 'T12:00:00Z')) / 86400000);
const nastMies = (m, o = 1) => { const x = +m.slice(0, 4) * 12 + +m.slice(5, 7) - 1 + o; return `${Math.floor(x / 12)}-${String(x % 12 + 1).padStart(2, '0')}`; };
// Reguła dnia wystawienia: „Ostatni”, „1.”, „10. +1 B” (B: księgowanie wg miesiąca budżetu), „20. -1”.
const regulaZ = t => { const m = /^(ostatni|pierwszy|(\d{1,2})\.?)(?:\s*([+-]\d{1,2}))?(\s*b)?$/i.exec(String(t || '').trim());
  if (!m) return { typ: 'ostatni', dzien: 10, przes: 0, b: false };
  const typ = /^ostatni/i.test(m[1]) ? 'ostatni' : (/^pierwszy/i.test(m[1]) || m[2] === '1') ? 'pierwszy' : 'dzien';
  return { typ, dzien: m[2] ? +m[2] : 10, przes: +(m[3] || 0), b: !!m[4] }; };
const regulaNa = r => (r.typ === 'ostatni' ? 'Ostatni' : r.typ === 'pierwszy' ? '1.' : `${r.dzien}.`) + (r.przes ? ` ${r.przes > 0 ? '+' : ''}${r.przes}` : '') + (r.przes && r.b ? ' B' : '');
const nowyId = p => `${p}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`;
// BS podaje stawkę jako ułamek (0.23) albo tekst („np”, „zw”); pokazujemy procent.
const stawka = s => { const v = parseFloat(String(s ?? '').replace(',', '.')); return isNaN(v) ? esc(s || '') : `${Math.round(v <= 1 ? v * 100 : v)} %`; };
// Kwota z pola („1 234,56”) na grosze bez liczb zmiennoprzecinkowych; zły zapis: NaN.
const naGrosze = s => { const t = String(s ?? '').replace(/[\s\u00a0]/g, '').replace(',', '.'); const m = /^(\d+)(?:\.(\d{1,2}))?$/.exec(t);
  return m ? (+m[1]) * 100 + +((m[2] || '') + '00').slice(0, 2) : NaN; };
const STAWKI = [23, 8, 5, 0];
// Stawka z zapisu BS (0,23 albo efektywna 0,2299) jako 23, 8, 5, 0; inna (kilka stawek na fakturze) albo brak: null.
const stawkaStd = s => { let v = parseFloat(String(s ?? '').replace(',', '.')); if (isNaN(v)) return null; if (v > 0 && v < 1) v *= 100; return STAWKI.find(x => Math.abs(v - x) <= (x ? 0.1 : 0)) ?? null; };
// Zmiany, które nie mają do czego się odnieść (np. płatności nie ma już w eksporcie BS), nie znikają po cichu.
const banerOsieroconych = n => n ? `<div class="komunikat blad"><span>${n} ${n === 1 ? 'zmiana nie ma' : 'zmian nie ma'} do czego się odnieść. Sprawdź listę w <a href="#/budzet/historia">Historii zmian</a>.</span></div>` : '';

Object.assign(POMOC, {
  budzet: { tytul: 'Budżet: arkusze', krotko: 'Foldery klientów, kategorie i arkusze jak w Budget Studio, z planem i wykonaniem.',
    co: 'Każdy arkusz ma wiersze (powtarzalne pozycje) i kolumny miesięcy. Komórka to płatność: plan albo rzeczywista.',
    skad: 'Do końca 2026: eksport Budget Studio (plik importu w Finanse/Aplikacja, odtwarzany przy każdym eksporcie). Od 2027: plany wpisane w apce (plik zmian).',
    jak: 'Kolor komórki: zielony opłacone (z banku), szary plan, czerwony plan po terminie, żółty „opłacone według BS”, ale bez śladu w banku lub Fakturowni.',
    zrob: 'Kliknij komórkę, żeby zobaczyć płatność, jej fakturę i przelew. Czerwone komórki czekają na decyzję: przesuń, zapłacone, anuluj.' },
  rozjazdy: { tytul: 'Rozjazdy z Budget Studio', krotko: 'Gdzie Budget Studio mówi co innego niż bank i Fakturownia.',
    co: 'Pozycje opłacone w BS bez śladu w danych, zapłacone w banku a w BS nadal planowane, różne kwoty, faktury i wydatki bez pozycji w BS.',
    skad: 'Import z eksportu BS kontra wpłaty, wydatki i faktury w apce.',
    jak: 'Koszty pracy, VAT i podatek dochodowy porównujemy sumą w miesiącu płatności, bo BS trzyma koszt pracodawcy w jednej kwocie.',
    zrob: 'Przejrzyj największe kwoty. Do końca 2026 poprawki robisz w BS; od 2027 plany są w apce.' },
  cashflow: { tytul: 'Cash flow', krotko: 'Saldo gotówki w okresach (dzień, tydzień, miesiąc): co wpłynie, co wypłynie i ile zostanie.',
    co: 'Tabela okresów: saldo narastająco, saldo okresu, wpływy, obciążenia; zielona ramka to najwyższe saldo, czerwona najniższe. Pod nią miniatura całego zakresu z ramką do wyboru wycinka, wykres i lista płatności wycinka.',
    skad: 'Przed dniem stanu: przepływy z banku ING (rachunek główny i online). Po nim prognoza: należności z Fakturowni w terminie przesuniętym o średnie spóźnienie nabywcy, plany przychodów i kosztów z budżetu, a gdy w miesiącu brak planu kosztów, szacunek kosztów pracy i stałych ze średniej 6 miesięcy.',
    jak: 'Scenariusz ostrożny pomija należności i plany już po terminie; pełny liczy je za 7 dni. Saldo startowe: gotówka z banku na koniec dnia przed zakresem, chyba że wpiszesz własne. Tydzień od wtorku do poniedziałku, jak w Budget Studio.',
    zrob: 'Patrz na MIN w lewym kafelku: to poziom bezpieczeństwa. Plany po terminie rozstrzygnij, żeby nie wisiały. Przeciągnij ramkę na miniaturze, żeby obejrzeć inny wycinek.' },
});

// ---------- Drzewo arkuszy ----------
Object.assign(WIDOKI, {
  async 'budzet/arkusze'() {
    const d = await api('budzet/drzewo');
    const imp = d.import;
    const foldery = d.foldery.map(f => `<section class="folder"><h2 class="sekcja">${esc(f.folder)} <span class="szary">${zl(f.saldo)}</span></h2>
      ${Object.entries(f.kategorie).map(([k, ark]) => `<div class="kategoria"><h3>${esc(k)}</h3>
        ${ark.map(a => `<a class="arkusz-link" href="#/budzet/arkusz?id=${a.id}"><span>${esc(a.nazwa)}</span>
          <small>${mies(a.od)} – ${mies(a.do)} · ${a.wierszy} wierszy${a.po_terminie ? ` · <b class="minus">${a.po_terminie} po terminie</b>` : ''}</small>
          <b class="${a.saldo < 0 ? 'minus' : ''}">${zl(a.saldo, false)}</b></a>`).join('')}</div>`).join('')}</section>`).join('');
    setTimeout(() => { const b = $('#dodaj-arkusz'); if (b) b.onclick = () => kartaArkusza(null, d); });
    return `<div class="naglowek-strony"><div><h1>Arkusze budżetu ${pytajnik('budzet')}</h1>
        <div class="okruszki">Budżet / ${d.planowanie ? 'planowanie w apce włączone' : 'tryb podglądu: plany z Budget Studio, tylko do odczytu'}</div></div>
        ${d.planowanie ? '<button class="przycisk" id="dodaj-arkusz">Dodaj arkusz</button>' : ''}</div>
      ${banerOsieroconych(d.osierocone)}
      ${imp ? `<p class="notka">Import z ${esc(imp.plik)} (${imp.wierszy} płatności, ostatnia zmiana w BS ${esc(imp.najnowsza_modyfikacja)}). Saldo arkusza jak w Budget Studio: netto wpływów minus obciążeń, razem z pozycjami nieaktualnymi.</p>` : '<p class="notka">Brak eksportu Budget Studio w folderze Dane.</p>'}
      <div class="drzewo">${foldery}</div>`;
  },

  // ---------- Widok arkusza jak w BS: zakładki Arkusz / Płatności / Cash flow / Zarządzaj ----------
  async 'budzet/arkusz'(p) {
    const d = await api('budzet/arkusz', { id: p.id });
    const a = d.arkusz;
    const zakl = ['arkusz', 'platnosci', 'cashflow'].includes(p.zakladka) ? p.zakladka : 'arkusz';
    const nazwyZakl = { arkusz: 'Arkusz', platnosci: 'Płatności', cashflow: 'Cash flow' };
    setTimeout(() => {
      document.querySelectorAll('[data-zakl]').forEach(b => b.onclick = () => {
        if (b.dataset.zakl === 'zarzadzaj') return menuZarzadzaj(b, d);
        location.hash = `#/budzet/arkusz?id=${encodeURIComponent(a.id)}${b.dataset.zakl === 'arkusz' ? '' : '&zakladka=' + b.dataset.zakl}`;
      });
    });
    const naglowek = `<h1>${ik('pinezka', 'ik-tytul')}${esc(a.nazwa)}<span title="Folder: ${esc(a.folder)}, kategoria: ${esc(a.kategoria)}">${ik('folderOko', 'ik-tytul szary')}</span></h1>
      <div class="pigulki"><span class="pigulka">${ik('warstwy')}${nazwyZakl[zakl]} / Widok główny</span>
        <span class="szary">${esc(a.folder)} / ${esc(a.kategoria)} · ${mies(a.od)} - ${mies(a.do)} · źródło: ${esc(a.zrodlo)}</span></div>
      <div class="zakladki" role="tablist">
        <button role="tab" data-zakl="arkusz" aria-selected="${zakl === 'arkusz'}">${ik('arkusz')}Arkusz</button>
        <button role="tab" data-zakl="platnosci" aria-selected="${zakl === 'platnosci'}">${ik('fale')}Płatności</button>
        <button role="tab" data-zakl="cashflow" aria-selected="${zakl === 'cashflow'}">${ik('fale')}Cash flow</button>
        <button role="tab" data-zakl="zarzadzaj" aria-selected="false" data-karta>${ik('zebatka')}Zarządzaj</button></div>
      ${banerOsieroconych(0)}`;
    if (zakl === 'cashflow') return naglowek + await widokCashflow(p, { arkusz: a.id, ark: a });
    if (zakl === 'platnosci') return naglowek + await listaPlanu({ ...p, lista: p.lista || 'wszystkie' }, { arkusz: a.id });
    return naglowek + arkuszTabela(d, p);
  },

  // ---------- Listy płatności planu (jak w BS) ----------
  async 'platnosci/plan'(p) {
    const d = await api('budzet/lista', p);
    return `<h1>${esc(d.nazwa)}</h1><div class="okruszki">Połączone z budżetem / ${esc(d.nazwa)}</div>${await listaPlanu(p, { dane: d })}`;
  },

  async 'budzet/rozjazdy'() {
    const lista = await api('budzet/rozjazdy');
    const grupy = {};
    lista.forEach(x => (grupy[x.rodzaj] ||= []).push(x));
    const sekcje = Object.entries(grupy).map(([g, xs]) => `<h2 class="sekcja">${esc(g)} <span class="szary">${xs.length} · ${zl(xs.reduce((a, x) => a + x.kwota, 0))}</span></h2>
      <div class="tabela-ramka niska"><table><thead><tr><th>Arkusz</th><th>Kontrahent</th><th>Miesiąc</th><th class="liczba-kol">Kwota PLN</th><th>Opis</th></tr></thead><tbody>
      ${xs.slice(0, 200).map(x => `<tr data-ref="${esc(x.ref)}" data-ark="${esc(x.arkusz_id || '')}"><td>${esc(x.arkusz || '')}</td><td>${esc(x.kontrahent || '')}</td>
        <td>${x.miesiac ? mies(x.miesiac) : ''}</td><td class="liczba-kol">${zl(x.kwota, false)}</td><td class="szary">${esc(x.opis.replace(/(-?\d+) gr/g, (_, v) => zl(+v)))}</td></tr>`).join('')}
      </tbody></table></div>`).join('');
    setTimeout(() => document.querySelectorAll('tr[data-ref]').forEach(tr => tr.onclick = () => {
      if (tr.dataset.ref.startsWith('bs:') || tr.dataset.ref.startsWith('plan:')) kartaPlatnosci([tr.dataset.ref], null);
      else if (tr.dataset.ref.startsWith('FV')) location.hash = `#/platnosci/faktury?q=${encodeURIComponent(tr.dataset.ref)}`;
    }));
    return `<h1>Rozjazdy z Budget Studio ${pytajnik('rozjazdy')}</h1><div class="okruszki">Budżet / BS kontra bank i Fakturownia</div>
      <p class="notka">Lista do decyzji. Kliknij wiersz, żeby zobaczyć płatność i jej powiązania.</p>${sekcje || '<div class="pusto">Brak rozjazdów.</div>'}`;
  },

  async 'budzet/historia'() {
    const h = await api('budzet/historia');
    const lista = h.zmiany, sieroty = h.osierocone;
    const wiersze = lista.map((h, i) => `<tr><td>${esc(new Date(h.czas).toLocaleString('pl-PL'))}</td><td>${esc(h.mac)}</td><td>${esc(h.op)}</td>
      <td class="szary">${esc(h.obiekt)}</td><td class="szary">${esc(opisZmiany(h))}</td><td class="akcje-wiersz"><button data-i="${i}">Cofnij</button></td></tr>`).join('');
    setTimeout(() => document.querySelectorAll('button[data-i]').forEach(b => b.onclick = () => zmiana('cofnij', { wpis: lista[b.dataset.i].wpis })));
    const sierotyHtml = sieroty.length ? `<h2 class="sekcja">Zmiany bez obiektu <span class="szary">${sieroty.length}</span></h2>
      <p class="notka">Te zmiany nie mają do czego się odnieść (np. płatności nie ma już w eksporcie BS) i nie są uwzględnione w budżecie. Cofnij je albo odtwórz brakujący obiekt.</p>
      <div class="tabela-ramka niska"><table><thead><tr><th>Kiedy</th><th>Komputer</th><th>Zmiana</th><th>Czego dotyczy</th><th>Powód</th><th></th></tr></thead><tbody>
      ${sieroty.map((x, i) => `<tr><td>${esc(new Date(x.czas).toLocaleString('pl-PL'))}</td><td>${esc(x.mac)}</td><td>${esc(x.op)}</td><td class="szary">${esc(x.obiekt)}</td>
        <td>${esc(x.powod)}</td><td class="akcje-wiersz"><button data-s="${i}">Cofnij</button></td></tr>`).join('')}</tbody></table></div>` : '';
    setTimeout(() => document.querySelectorAll('button[data-s]').forEach(b => b.onclick = () => zmiana('cofnij', { wpis: sieroty[b.dataset.s].wpis })));
    return `<h1>Historia zmian planów</h1><div class="okruszki">Budżet / kto, kiedy, było i jest</div>
      ${banerOsieroconych(sieroty.length)}${sierotyHtml}
      ${lista.length ? `<div class="tabela-ramka niska"><table><thead><tr><th>Kiedy</th><th>Komputer</th><th>Zmiana</th><th>Czego dotyczy</th><th>Było → jest</th><th></th></tr></thead><tbody>${wiersze}</tbody></table></div>`
        : '<div class="pusto">Brak zmian. Do końca 2026 plany są w Budget Studio.</div>'}`;
  },

  async 'budzet/ustawienia'() {
    const [d, k] = await Promise.all([api('budzet/drzewo'), api('rentownosc/klienci')]);
    setTimeout(() => {
      $('#przelacz-planowanie').onclick = () => zmiana('ustawienie', { klucz: 'planowanie', wartosc: d.planowanie ? 'nie' : 'tak' });
    });
    return `<h1>Ustawienia budżetu</h1><div class="okruszki">Budżet / Ustawienia</div>
      <div class="karta-wyk"><h3>Planowanie w apce</h3>
        <p class="notka">Teraz: <b>${d.planowanie ? 'włączone' : 'wyłączone (tryb podglądu)'}</b>. Do 31.12.2026 źródłem planów jest Budget Studio, a apka tylko je czyta i porównuje z bankiem.
        Po włączeniu możesz dodawać i zmieniać arkusze, wiersze i płatności; każda zmiana trafia do historii i da się ją cofnąć. Wyłączenie nie kasuje zmian.</p>
        <div class="akcje"><button class="${d.planowanie ? '' : 'glowny'}" id="przelacz-planowanie">${d.planowanie ? 'Wyłącz planowanie w apce' : 'Włącz planowanie w apce'}</button></div></div>
      <div class="karta-wyk"><h3>Udział czasu zespołu na klientów</h3>
        <p class="notka">Do rentowności klientów: jaki procent czasu zespołu idzie na klienta. Ustawisz go na ekranie Rentowność, Rentowność klientów.</p>
        <p><a href="#/rentownosc/rent-klienci">Przejdź do rentowności klientów</a> · uzupełnione: ${k.klienci.length - k.bez_estymaty} z ${k.klienci.length}</p></div>`;
  },

  // ---------- Cash flow (widok jak w BS, kod niżej: widokCashflow) ----------
  async cashflow(p) { return widokCashflow(p); },

  // ---------- Rentowność klientów i arkuszy ----------
  async 'rentownosc/rent-klienci'(p) {
    const d = await api('rentownosc/klienci', p);
    const wiersze = d.klienci.map((k, i) => `<tr><td>${esc(k.klient)}</td><td class="liczba-kol">${tys(k.obrot)}</td><td class="liczba-kol minus">${tys(-k.koszty)}</td>
      <td class="liczba-kol">${tys(k.pna)}</td><td class="liczba-kol">${procent(k.marza_proc)}</td>
      <td><input class="maly" data-est="${i}" inputmode="decimal" value="${k.udzial_czasu ?? ''}" placeholder="%"></td>
      <td class="liczba-kol minus">${k.koszt_pracy != null ? tys(-k.koszt_pracy) : ''}</td>
      <td class="liczba-kol ${k.wynik_klienta < 0 ? 'minus' : ''}"><b>${k.wynik_klienta != null ? tys(k.wynik_klienta) : ''}</b></td></tr>`).join('');
    setTimeout(() => document.querySelectorAll('[data-est]').forEach(inp => inp.onchange = () => {
      if (inp.value.trim() === '') return;
      zmiana('estymata', { klient: d.klienci[inp.dataset.est].klient, udzial: inp.value });
    }));
    return `<div class="naglowek-strony"><div><h1>Rentowność klientów</h1><div class="okruszki">Rentowność / ${d.rok}</div></div>
        <a class="przycisk" href="/api/eksport/rentownosc?rok=${d.rok}">Excel</a></div>
      <p class="notka">Koszt pracy klienta = udział czasu zespołu (wpisz %, zapis po wyjściu z pola) razy koszty pracy roku (${zl(d.koszty_pracy_rok)}). Suma wpisanych udziałów: ${procent(d.suma_udzialow)}. To szacunek do rozmowy o cenie, nie księgowość.</p>
      <div class="tabela-ramka niska"><table><thead><tr><th>Klient</th><th class="liczba-kol">Obrót</th><th class="liczba-kol">Koszty klienta</th><th class="liczba-kol">Po kosztach</th>
        <th class="liczba-kol">Marża</th><th>Czas %</th><th class="liczba-kol">Koszt pracy</th><th class="liczba-kol">Wynik klienta</th></tr></thead><tbody>${wiersze}</tbody></table></div>`;
  },

  async 'rentownosc/arkusze'() {
    const lista = await api('rentownosc/arkusze');
    const kol = [
      { naglowek: 'Folder', wartosc: x => x.folder }, { naglowek: 'Arkusz', wartosc: x => x.nazwa },
      { naglowek: 'Plan przychód', liczba: true, wartosc: x => tys(x.plan_przychod), sortKlucz: x => x.plan_przychod }, { naglowek: 'Wykonanie przychód', liczba: true, wartosc: x => tys(x.wyk_przychod), sortKlucz: x => x.wyk_przychod },
      { naglowek: 'Realizacja', liczba: true, wartosc: x => procent(x.realizacja_proc) },
      { naglowek: 'Plan koszt', liczba: true, wartosc: x => tys(-x.plan_koszt), klasa: () => 'minus' }, { naglowek: 'Wykonanie koszt', liczba: true, wartosc: x => tys(-x.wyk_koszt), klasa: () => 'minus' },
      { naglowek: 'Saldo planu', liczba: true, wartosc: x => tys(x.plan_saldo), sortKlucz: x => x.plan_saldo },
      { naglowek: 'Po terminie', liczba: true, wartosc: x => x.po_terminie || '', klasa: x => x.po_terminie ? 'minus' : '' },
    ];
    return `<h1>Arkusze: plan i wykonanie</h1><div class="okruszki">Rentowność / budżet</div>
      <p class="notka">Plan: wszystkie aktualne pozycje arkusza (netto). Wykonanie: pozycje opłacone według banku (przychód przez fakturę, koszt przez przelew).</p>
      ${tabela({ kolumny: kol, dane: lista, poczatek: 1, sortLokalny: true, onWiersz: x => { location.hash = `#/budzet/arkusz?id=${x.id}`; } })}`;
  },
});

function opisZmiany(h) {
  try {
    const b = JSON.parse(h.bylo || 'null'), j = JSON.parse(h.jest || 'null');
    if (!b) return 'dodano';
    if (!j) return 'usunięto';
    return Object.keys(j).filter(k => JSON.stringify(b[k]) !== JSON.stringify(j[k]) && k !== 'zrodlo')
      .map(k => `${k}: ${JSON.stringify(b[k])} → ${JSON.stringify(j[k])}`).join('; ') || 'bez zmian';
  } catch (e) { return ''; }
}

// ---------- Karty: komórka, płatność, wiersz, arkusz ----------
// Komórka (wiersz × miesiąc) ma kwotę; plany są z niej liczone wg podstawy i ustawień wiersza (pakiet 2).
function komorkaHtml(w, m, kwota) {
  return `<div class="formularz" data-komorka>
      ${pole('', `Kwota w komórce (${esc(KWOTA_KOMORKI[w.podstawa] || 'kwota')})`, `<input data-kwota inputmode="decimal" value="${esc(zlWpis(kwota))}">`)}</div>
    <div class="akcje"><button class="glowny" data-zapisz-komorke>Zapisz kwotę</button>${kwota != null ? '<button data-wyczysc-komorke>Wyczyść komórkę</button>' : ''}</div>
    <p class="szary">0 znaczy: płatność będzie, kwota jeszcze nieznana. Pusta komórka nie ma planów.</p>`;
}

function podepnijKomorke(k, w, m) {
  const b = k.querySelector('[data-zapisz-komorke]');
  if (!b) return;
  b.onclick = () => {
    const kwota = naGrosze(k.querySelector('[data-kwota]').value);
    if (!(kwota >= 0)) return komunikat('Wpisz kwotę liczbą, np. 1 234,56.', true);
    zmiana('bud', { op: 'komorka', wiersz: w.id, miesiac: m, kwota });
  };
  const c = k.querySelector('[data-wyczysc-komorke]');
  if (c) c.onclick = () => zmiana('bud', { op: 'komorka', wiersz: w.id, miesiac: m, kwota: null });
}

function kartaKomorki(w, m) {
  const k = $('#karta');
  k.innerHTML = `<button class="zamknij" aria-label="Zamknij">×</button><h2>${esc(miesPelny(m))}</h2>
    <div class="szary">${esc(w.kontrahent || w.komentarz || 'Wiersz')} · ${esc(w.podstawa)}</div>${komorkaHtml(w, m, null)}`;
  k.hidden = false;
  $('.zamknij', k).onclick = () => { k.hidden = true; };
  podepnijKomorke(k, w, m);
  $('[data-kwota]', k).focus();
}

// Pola planu, które wolno zmienić na pojedynczej płatności (reszta przychodzi z wiersza; serwer sprawdza to samo).
function polaPlanu(p) {
  if (p.typ !== 'plan') return ['netto', 'stawka', 'termin'];
  if (WOREK.includes(p.podstawa)) return ['kontrahent', 'komentarz'];
  if (p.skladowa === 'us' || p.skladowa === 'zus') return [];
  const pola = ['kontrahent', 'komentarz', 'wystawienie', 'dni', 'termin', 'realny', 'metoda', 'ksiegowane', 'w_cashflow'];
  if (!UMOWY[p.podstawa]) pola.unshift('netto');
  if (p.podstawa === 'Faktura (jedna)' || (!p.generowany && p.podstawa.startsWith('Faktura'))) pola.push('stawka');
  return pola;
}

function formularzPlatnosci(p) {
  const pola = polaPlanu(p);
  if (!pola.length) return '<p class="szary">PIT i ZUS umowy idą za składową dla osoby: zmień ją albo ustawienia wiersza.</p>';
  const dni = p.wystawienie && p.termin ? roznicaDni(p.wystawienie, p.termin) : '';
  const f = {
    netto: () => pole('', p.generowany ? 'Kwota (zmienia kwotę komórki)' : 'Netto (zł)', `<input data-f="netto" inputmode="decimal" value="${zlWpis(p.netto)}">`),
    stawka: () => pole('', 'Stawka VAT', `<select data-f="stawka">${STAWKI.map(x => `<option value="${x}"${p.stawka === x ? ' selected' : ''}>${x} %</option>`).join('')}</select>`),
    kontrahent: () => pole('', 'Kontrahent', `<input data-f="kontrahent" value="${esc(p.w_kontrahent || '')}">`),
    komentarz: () => pole('', 'Komentarz', `<input data-f="komentarz" maxlength="170" value="${esc(p.komentarz || '')}">`),
    wystawienie: () => pole('', 'Dzień wystawienia', `<input type="date" data-f="wystawienie" value="${esc(p.wystawienie || '')}">`),
    dni: () => pole('', 'Dni na płatność', `<input data-f="dni" inputmode="numeric" value="${dni}">`),
    termin: () => pole('', 'Dzień płatności', `<input type="date" data-f="termin" value="${esc((p.typ === 'plan' ? p.termin : p.termin_efektywny) || '')}">`),
    realny: () => pole('', 'Dzień realnej płatności', `<input type="date" data-f="realny" value="${esc(p.realny || '')}">`),
    metoda: () => pole('', 'Metoda płatności', `<input data-f="metoda" value="${esc(p.metoda || '')}">`),
    ksiegowane: () => pole('', 'Księgowane (VAT, CIT, rentowność)', `<select data-f="ksiegowane"><option value="1">tak</option><option value=""${p.ksiegowane ? '' : ' selected'}>nie</option></select>`),
    w_cashflow: () => pole('', 'W cash flow', `<select data-f="w_cashflow"><option value="1">tak</option><option value=""${p.w_cashflow ? '' : ' selected'}>nie</option></select>`),
  };
  return `<div class="formularz" data-edyt="${esc(p.id)}">${pola.map(x => f[x]()).join('')}</div>
    <div class="akcje"><button data-zapisz="${esc(p.id)}">Zapisz tę płatność</button></div>
    ${p.typ === 'plan' ? '<p class="szary">Zmiana tej samej cechy w wierszu nadpisze ręczną zmianę we wszystkich planach wiersza.</p>' : ''}`;
}

function zbierzPlatnosc(box) {
  const o = {};
  box.querySelectorAll('[data-f]').forEach(el => { o[el.dataset.f] = el.value; });
  return o;
}

async function kartaPlatnosci(ids, ark, kom) {
  const k = $('#karta');
  const dane = await Promise.all(ids.slice(0, 8).map(id => api('budzet/platnosc', { id })));
  const planowanie = dane[0]?.planowanie;
  const naglowekKomorki = kom && kom.w && planowanie && !dane.some(x => x.platnosc.typ !== 'plan' && !WOREK.includes(kom.w.podstawa))
    ? `<h2>${esc(miesPelny(kom.m))}</h2><div class="szary">${esc(kom.w.kontrahent || kom.w.komentarz || '')} · ${esc(kom.w.podstawa)}</div>
       ${komorkaHtml(kom.w, kom.m, dane[0]?.kwota_komorki ?? kom.w.komorki?.[kom.m]?.kwota ?? null)}<hr>` : '';
  k.innerHTML = `<button class="zamknij" aria-label="Zamknij">×</button>${naglowekKomorki}` + dane.map(({ platnosc: p, powiazania, historia }) => `
    <h2>${esc(p.w_kontrahent || p.tytul || 'Płatność')}</h2>
    <div class="szary">${esc(p.folder)} / ${esc(p.arkusz)} · ${mies(p.miesiac)} · ${p.typ === 'plan' ? 'plan' : 'rzeczywista'}</div>
    <dl><dt>Podstawa</dt><dd>${esc(p.podstawa_platnosci)}</dd><dt>Etap</dt><dd>${chipEtap(p.etap)}${p.uwaga_stanu ? `\n${esc(p.uwaga_stanu)}` : ''}</dd>
      <dt>Wg reguł BS</dt><dd>${esc(p.etap_wg_bs || '')}, ${esc((p.aktualnosc || '').toLowerCase())}</dd>
      <dt>Netto</dt><dd>${zl(p.netto * p.rodzaj)}</dd><dt>VAT</dt><dd>${zl(p.vat * p.rodzaj)}${p.stawka != null ? ` (${p.stawka} %)` : ''}</dd><dt>Brutto</dt><dd>${zl(p.brutto * p.rodzaj)}</dd>
      ${p.wystawienie ? `<dt>Wystawienie</dt><dd>${dataPl(p.wystawienie)}</dd>` : ''}<dt>Termin</dt><dd>${dataPl(p.termin_efektywny)}</dd>
      ${p.realny ? `<dt>Realna płatność</dt><dd>${dataPl(p.realny)}</dd>` : ''}${p.ksiegowanie ? `<dt>Księgowanie</dt><dd>${mies(p.ksiegowanie.slice(0, 7))}</dd>` : ''}
      ${p.data_zaplaty ? `<dt>Zapłacono</dt><dd>${dataPl(p.data_zaplaty)}</dd>` : ''}
      <dt>Metoda</dt><dd>${esc(p.metoda || '–')}</dd><dt>Księgowane, W cash flow</dt><dd>${p.ksiegowane ? 'tak' : 'nie'}, ${p.w_cashflow ? 'tak' : 'nie'}</dd>
      ${p.komentarz ? `<dt>Komentarz</dt><dd>${esc(p.komentarz)}</dd>` : ''}
      ${p.nr_dok ? `<dt>Nr dokumentu</dt><dd>${esc(p.nr_dok)}</dd>` : ''}${p.nr_wewn ? `<dt>Nr wewnętrzny</dt><dd>${esc(p.nr_wewn)}</dd>` : ''}
      ${p.tytul ? `<dt>Tytuł</dt><dd>${esc(p.tytul)}</dd>` : ''}${p.bs_id ? `<dt>Etap w BS</dt><dd>${esc(p.etap_bs || '–')}</dd>` : ''}
      ${p.decyzja ? `<dt>Decyzja</dt><dd>${esc(p.decyzja)}</dd>` : ''}
      ${Object.keys(p.nadpisane || {}).length ? `<dt>Zmienione ręcznie</dt><dd>${esc(Object.keys(p.nadpisane).join(', '))}</dd>` : ''}</dl>
    <h3>Powiązania</h3>${powiazania.length ? `<ul class="lista">${powiazania.map(x => `<li><b>${esc(x.typ)}</b> ${esc((x.opis || '').replace(/(-?\d+) gr/g, (_, v) => zl(+v)))} <span class="szary">${esc(x.metoda)}, ${esc(x.pewnosc)}</span></li>`).join('')}</ul>` : '<p class="szary">Brak: ani faktury, ani przelewu.</p>'}
    ${planowanie && p.etap === 'Po terminie' ? `<h3>Decyzja</h3><div class="akcje" data-pid="${esc(p.id)}"><input type="date" data-termin>
      <button data-d="przesun">Przesuń</button><button data-d="zaplacone">Zapłacone</button><button data-d="anuluj">Anuluj</button></div>` : ''}
    ${planowanie ? `<h3>Zmień</h3>${formularzPlatnosci(p)}` : ''}
    ${historia.length ? `<h3>Historia</h3><ul class="lista">${historia.map(h => `<li>${esc(new Date(h.czas).toLocaleString('pl-PL'))}: ${esc(h.op)} <span class="szary">${esc(opisZmiany(h))}</span></li>`).join('')}</ul>` : ''}
    <div class="zrodlo">Źródło: ${esc(p.zrodlo || '')}${p.bs_id ? `, ID w BS ${esc(p.bs_id)}, wiersz ${p.wiersz_pliku}` : ''}</div>`).join('<hr>');
  k.hidden = false;
  $('.zamknij', k).onclick = () => { k.hidden = true; };
  if (naglowekKomorki) podepnijKomorke(k, kom.w, kom.m);
  k.querySelectorAll('[data-d]').forEach(b => b.onclick = () => {
    const box = b.closest('[data-pid]');
    const termin = $('[data-termin]', box).value;
    if (b.dataset.d === 'przesun' && !termin) return komunikat('Wybierz nowy termin.', true);
    zmiana('bud', { op: 'decyzja_planu', platnosc: box.dataset.pid, decyzja: b.dataset.d, termin, data: termin });
  });
  k.querySelectorAll('[data-edyt]').forEach(box => {
    // dni na płatność ↔ dzień płatności: zmiana jednego przelicza drugie; zmiana dnia płatności ustawia dzień realny
    const el = n => box.querySelector(`[data-f="${n}"]`);
    if (el('dni') && el('termin') && el('wystawienie')) {
      el('dni').oninput = () => { const n = parseInt(el('dni').value, 10); if (n >= 0 && el('wystawienie').value) { el('termin').value = plusDni(el('wystawienie').value, n); if (el('realny')) el('realny').value = el('termin').value; } };
      el('termin').onchange = () => { if (el('wystawienie').value && el('termin').value) el('dni').value = roznicaDni(el('wystawienie').value, el('termin').value); if (el('realny')) el('realny').value = el('termin').value; };
      el('wystawienie').onchange = () => el('dni').oninput();
    }
    box.dataset.poczatek = JSON.stringify(zbierzPlatnosc(box));
  });
  k.querySelectorAll('[data-zapisz]').forEach(b => b.onclick = () => {
    const box = k.querySelector(`[data-edyt="${CSS.escape(b.dataset.zapisz)}"]`);
    const przed = JSON.parse(box.dataset.poczatek), po = zbierzPlatnosc(box);
    // tylko pola zmienione na karcie; VAT i brutto liczy serwer z netto i stawki
    const obiekt = { id: b.dataset.zapisz };
    for (const [k2, v] of Object.entries(po)) {
      if (v === przed[k2] || k2 === 'dni') continue;
      if (k2 === 'netto') { const g = naGrosze(v); if (!(g >= 0)) return komunikat('Podaj kwotę liczbą, np. 1 234,56.', true); obiekt.netto = g; }
      else if (k2 === 'stawka') obiekt.stawka = +v;
      else if (k2 === 'ksiegowane' || k2 === 'w_cashflow') obiekt[k2] = !!v;
      else obiekt[k2] = v;
    }
    if (Object.keys(obiekt).length === 1) return komunikat('Nic się nie zmieniło.', true);
    zmiana('bud', { op: 'platnosc', obiekt });
  });
}

// Wiersz = generator planów (pakiet 2): podstawa, VAT, reguła dnia wystawienia, dni na płatność, metoda, przełączniki,
// proporcje umów. Zapis wysyła tylko zmienione cechy: zmiana cechy nadpisuje ją we wszystkich planach wiersza.
function kartaWiersza(w, d) {
  const k = $('#karta');
  const r = regulaZ(w?.dzien_wystawienia || 'Ostatni');
  const prop = w?.proporcje || {};
  const zablokowane = !!w?.ma_rzeczywiste;
  const sel = (id, opcje, wartosc, wyl = false) => `<select id="${id}"${wyl ? ' disabled' : ''}>${opcje.map(([v, n]) => `<option value="${esc(v)}"${String(wartosc) === String(v) ? ' selected' : ''}>${esc(n)}</option>`).join('')}</select>`;
  const taknie = [['1', 'tak'], ['', 'nie']];
  k.innerHTML = `<button class="zamknij" aria-label="Zamknij">×</button><h2>${w ? 'Wiersz' : 'Nowy wiersz'}</h2>
    <div class="szary">${esc(d.arkusz.nazwa)}</div>
    ${zablokowane ? '<p class="notka">Wiersz ma płatność rzeczywistą: podstawy, rodzaju i proporcji umowy już nie zmienisz (obejście: zduplikuj wiersz). Reszta ustawień dotyczy tylko planów.</p>' : ''}
    <div class="formularz">
      ${pole('', 'Przedmiot transakcji', `<input id="w-przedmiot" value="${esc(w?.przedmiot || '')}">`)}
      ${pole('', 'Kontrahent', `<input id="w-kontrahent" value="${esc(w?.kontrahent || '')}">`)}
      ${pole('', 'Sekcja', `<input id="w-sekcja" value="${esc(w?.sekcja || '')}" placeholder="-">`)}
      ${pole('', 'Komentarz (do 170 znaków)', `<input id="w-komentarz" maxlength="170" value="${esc(w?.komentarz || '')}">`)}
      ${pole('', 'Rodzaj', sel('w-rodzaj', [['-1', 'obciążenia (koszt)'], ['1', 'wpływy (przychód)']], w?.rodzaj ?? -1, zablokowane))}
      ${pole('', 'Podstawa płatności', sel('w-podstawa', (PODSTAWY.includes(w?.podstawa) || !w ? PODSTAWY : [w.podstawa, ...PODSTAWY]).map(x => [x, x]), w?.podstawa || 'Faktura (jedna)', zablokowane))}
      ${pole('', 'Stawka VAT', sel('w-vat', STAWKI.map(x => [x, `${x} %`]), stawkaStd(w?.stawka_vat) ?? 23))}
      ${pole('', 'Dzień wystawienia', sel('w-dzien-typ', [['ostatni', 'ostatni dzień miesiąca'], ['pierwszy', 'pierwszy dzień miesiąca'], ['dzien', 'wybrany dzień']], r.typ))}
      ${pole('', 'Który dzień (1–31)', `<input id="w-dzien" inputmode="numeric" value="${r.dzien}">`)}
      ${pole('', 'Miesiąc wystawienia względem kolumny', sel('w-przes', [...Array(25)].map((_, i) => i - 12).map(n => [n, n === 0 ? 'ten sam miesiąc' : n > 0 ? `${n} mies. później (z dołu)` : `${-n} mies. wcześniej (z góry)`]), r.przes))}
      ${pole('', 'Miesiąc księgowania (przy przesunięciu i dniu 1–15)', sel('w-ksieg', [['', 'wg daty wystawienia'], ['B', 'wg miesiąca budżetu']], r.b ? 'B' : ''))}
      ${pole('', 'Dni na płatność (0–99)', `<input id="w-dni" inputmode="numeric" list="w-dni-lista" value="${w ? esc(String(w.dni_na_platnosc ?? '').replace(/\D.*$/, '') || '0') : '14'}"><datalist id="w-dni-lista">${[0, 7, 14, 21, 30, 60].map(x => `<option value="${x}">`).join('')}</datalist>`)}
      ${pole('', 'Metoda płatności', `<input id="w-metoda" value="${esc(w?.metoda || 'Konto firmowe')}">`)}
      ${pole('', 'Księgowane (VAT, CIT, rentowność)', sel('w-ksiegowane', taknie, w ? (w.ksiegowane ? '1' : '') : '1'))}
      ${pole('', 'W cash flow', sel('w-cf', taknie, w ? (w.w_cashflow ? '1' : '') : '1'))}
      ${pole('', 'Split payment', sel('w-split', taknie, w?.split ? '1' : ''))}
      <p class="szary">Wzorce: odsetki od kredytu K tak, CF tak; kapitał kredytu K nie, CF tak; wypłata zysku K nie, CF tak; amortyzacja i różnice kursowe K tak, CF nie;
        koszt opłacony prywatnie to dwa wiersze: koszt (K tak, CF nie) i zwrot pracownikowi bez faktury (K nie, CF tak). K = Księgowane, CF = W cash flow.</p>
      <div class="formularz" id="w-umowa">
        <p class="szary">Kwoty od księgowej z jednej umowy albo suma kilku list płac. Z nich apka liczy udziały i dzieli każdą komórkę.</p>
        ${['osoba', 'us', 'zus'].map(x => pole('', `Kwota ${SKLADOWE[x]} (zł)`, `<input id="w-prop-${x}" inputmode="decimal" value="${zlWpis(prop[x])}"${zablokowane ? ' disabled' : ''}>`)).join('')}
        ${pole('', 'Koszty uzyskania przychodu (dzieło)', sel('w-kup', [['', 'nie dotyczy'], ['20', '20 %'], ['50', '50 %']], w?.kup ?? ''))}
      </div>
    </div>
    <h3>Kwoty w miesiącach</h3>
    <div class="formularz">
      ${pole('', 'Kwota (zostaw puste, żeby nie zmieniać komórek)', '<input id="w-kwota" inputmode="decimal">')}
      ${pole('', 'Co ile', sel('w-co', [['1', 'co miesiąc'], ['3', 'co kwartał'], ['12', 'co rok'], ['0', 'tylko w pierwszym miesiącu']], '1'))}
      ${pole('', 'Od miesiąca', `<input id="w-od" type="month" value="${esc(d.arkusz.od)}">`)}
      ${pole('', 'Do miesiąca', `<input id="w-do" type="month" value="${esc(d.arkusz.do)}">`)}
    </div>
    <div class="akcje"><button class="glowny" id="w-zapisz">Zapisz wiersz</button></div>
    <p class="szary" id="w-opis-kwoty"></p>`;
  k.hidden = false;
  $('.zamknij', k).onclick = () => { k.hidden = true; };
  const odswiez = () => {
    const pod = $('#w-podstawa').value, umowa = !!UMOWY[pod], worek = WOREK.includes(pod);
    $('#w-vat').disabled = !pod.startsWith('Faktura');
    $('#w-umowa').hidden = !umowa;
    $('#w-prop-zus').closest('.pole').hidden = pod === 'Umowa o dzieło';
    $('#w-kup').closest('.pole').hidden = pod !== 'Umowa o dzieło';
    ['#w-dzien-typ', '#w-przes', '#w-ksieg'].forEach(x => { $(x).disabled = worek; });
    $('#w-dzien').disabled = worek || $('#w-dzien-typ').value !== 'dzien';
    $('#w-ksieg').disabled = worek || +$('#w-przes').value === 0 || ($('#w-dzien-typ').value === 'dzien' && +$('#w-dzien').value > 15) || $('#w-dzien-typ').value === 'ostatni';
    if (umowa) { $('#w-rodzaj').value = '-1'; $('#w-ksiegowane').value = '1'; }
    $('#w-rodzaj').disabled = zablokowane || umowa;
    $('#w-ksiegowane').disabled = umowa;
    $('#w-opis-kwoty').textContent = `Kwota w komórce: ${KWOTA_KOMORKI[pod] || 'kwota planu'}.${worek ? ' Dzień wystawienia: początek każdego tygodnia.' : ''}`;
  };
  ['#w-podstawa', '#w-dzien-typ', '#w-przes', '#w-dzien'].forEach(x => { $(x).onchange = odswiez; });
  odswiez();
  const zbierz = () => {
    const pod = $('#w-podstawa').value;
    const o = { przedmiot: $('#w-przedmiot').value.trim(), kontrahent: $('#w-kontrahent').value.trim(), sekcja: $('#w-sekcja').value.trim(),
      komentarz: $('#w-komentarz').value.trim(), rodzaj: +$('#w-rodzaj').value, podstawa: pod, metoda: $('#w-metoda').value.trim(),
      ksiegowane: !!$('#w-ksiegowane').value, w_cashflow: !!$('#w-cf').value, split: !!$('#w-split').value,
      dni_na_platnosc: parseInt($('#w-dni').value, 10) };
    if (pod.startsWith('Faktura')) o.stawka_vat = +$('#w-vat').value;
    if (!WOREK.includes(pod)) o.dzien_wystawienia = regulaNa({ typ: $('#w-dzien-typ').value, dzien: +$('#w-dzien').value, przes: +$('#w-przes').value, b: $('#w-ksieg').value === 'B' && !$('#w-ksieg').disabled });
    if (UMOWY[pod]) {
      o.proporcje = {};
      UMOWY[pod].forEach(x => { o.proporcje[x] = naGrosze($(`#w-prop-${x}`).value || '0'); });
      if (pod === 'Umowa o dzieło' && $('#w-kup').value) o.kup = +$('#w-kup').value;
    }
    return o;
  };
  const poczatek = JSON.stringify(zbierz());
  $('#w-zapisz').onclick = () => {
    const o = zbierz(), stare = JSON.parse(poczatek);
    if (!(o.dni_na_platnosc >= 0 && o.dni_na_platnosc <= 99)) return komunikat('Dni na płatność: liczba od 0 do 99.', true);
    if ($('#w-dzien-typ').value === 'dzien' && !(+$('#w-dzien').value >= 1 && +$('#w-dzien').value <= 31)) return komunikat('Dzień wystawienia: od 1 do 31.', true);
    if (o.proporcje && Object.values(o.proporcje).some(x => !(x >= 0))) return komunikat('Kwoty umowy wpisz liczbami, np. 2 700,96.', true);
    if (o.proporcje && !Object.values(o.proporcje).some(x => x > 0)) return komunikat('Podaj kwoty od księgowej (dla osoby, PIT i ZUS).', true);
    const id = w?.id || nowyId('w');
    // nowy wiersz: wszystkie pola; istniejący: tylko zmienione (zmiana cechy kasuje ręczne wyjątki w planach)
    const obiekt = w ? Object.fromEntries(Object.entries(o).filter(([x, v]) => JSON.stringify(v) !== JSON.stringify(stare[x]))) : { ...o, arkusz: d.arkusz.id };
    const ops = Object.keys(obiekt).length ? [{ op: 'wiersz', obiekt: { id, ...obiekt } }] : [];
    const kwotaTxt = $('#w-kwota').value.trim();
    if (kwotaTxt) {
      const kwota = naGrosze(kwotaTxt), co = +$('#w-co').value, od = $('#w-od').value, doM = $('#w-do').value;
      if (!(kwota >= 0)) return komunikat('Kwotę wpisz liczbą, np. 1 234,56.', true);
      if (!od || !doM || od > doM || od < d.arkusz.od || doM > d.arkusz.do) return komunikat(`Miesiące w zakresie arkusza: ${mies(d.arkusz.od)} do ${mies(d.arkusz.do)}.`, true);
      for (let m = od, i = 0; m <= doM; m = nastMies(m), i++) {
        if (co === 0 ? i === 0 : i % co === 0) ops.push({ op: 'komorka', wiersz: id, miesiac: m, kwota });
      }
    }
    if (!ops.length) return komunikat('Nic się nie zmieniło.', true);
    zmiana('bud', ops.length === 1 ? ops[0] : { op: 'seria', operacje: ops });
  };
}

function kartaArkusza(a, drzewo) {
  const k = $('#karta');
  const foldery = drzewo.foldery.map(f => f.folder);
  const kategorie = [...new Set(drzewo.foldery.flatMap(f => Object.keys(f.kategorie)))];
  k.innerHTML = `<button class="zamknij" aria-label="Zamknij">×</button><h2>${a ? 'Arkusz' : 'Nowy arkusz'}</h2>
    <div class="formularz">${pole('', 'Nazwa', '<input id="a-nazwa">')}
      ${pole('', 'Folder (klient albo obszar)', `<input id="a-folder" list="a-foldery">`)}<datalist id="a-foldery">${foldery.map(f => `<option value="${esc(f)}">`).join('')}</datalist>
      ${pole('', 'Kategoria (możesz wpisać nową)', `<input id="a-kategoria" list="a-kategorie">`)}<datalist id="a-kategorie">${kategorie.map(f => `<option value="${esc(f)}">`).join('')}</datalist>
      ${pole('', 'Od miesiąca', '<input id="a-od" type="month">')}${pole('', 'Do miesiąca', '<input id="a-do" type="month">')}</div>
    <div class="akcje"><button class="glowny" id="a-zapisz">Zapisz arkusz</button></div>`;
  k.hidden = false;
  $('.zamknij', k).onclick = () => { k.hidden = true; };
  $('#a-zapisz').onclick = () => {
    const o = { id: nowyId('a'), nazwa: $('#a-nazwa').value.trim(), folder: $('#a-folder').value.trim(), kategoria: $('#a-kategoria').value.trim(), od: $('#a-od').value, do: $('#a-do').value };
    if (!o.nazwa || !o.folder || !o.kategoria || !o.od || !o.do || o.od > o.do) return komunikat('Uzupełnij nazwę, folder, kategorię i zakres miesięcy.', true);
    zmiana('bud', { op: 'arkusz', obiekt: o });
  };
}

// Akcje na zaznaczonych wierszach: każda z podglądem (co się stanie) i potwierdzeniem w karcie. Cała akcja to jeden
// wpis „seria”: serwer sprawdza wszystkie operacje i zapisuje je razem albo wcale (jedno przeliczenie, cofnięcie w całości).
// Kopie płatności powstają na serwerze ze wzoru („wzor”): ta sama stawka i daty, VAT liczony z netto.
async function akcjaNaWierszach(akcja, d) {
  const ids = [...document.querySelectorAll('[data-zazn]:checked')].map(x => x.dataset.zazn);
  const wiersze = d.wiersze.filter(w => ids.includes(w.id));
  if (!wiersze.length) return komunikat('Zaznacz co najmniej jeden wiersz.', true);
  if ((akcja === 'scal' && wiersze.length < 2) || (akcja === 'podziel' && wiersze.length !== 1)) return komunikat(akcja === 'scal' ? 'Do scalenia zaznacz co najmniej dwa wiersze.' : 'Do podziału zaznacz jeden wiersz.', true);
  if (akcja === 'scal' && new Set(wiersze.map(w => w.rodzaj)).size > 1) return komunikat('Scalić można tylko wiersze tego samego rodzaju (same wpływy albo same obciążenia).', true);
  const k = $('#karta');
  const opis = { duplikuj: 'Powstanie kopia każdego wiersza z tymi samymi płatnościami planowanymi (ta sama stawka VAT i daty).', przenies: 'Wiersze przejdą do wybranego arkusza.',
    scal: 'Powstanie jeden wiersz ze wszystkimi płatnościami zaznaczonych wierszy; zaznaczone wiersze znikną.', podziel: 'Powstanie drugi wiersz z podanym procentem każdej płatności; pierwszy zostanie pomniejszony.',
    usun: 'Wiersze i ich płatności znikną z budżetu (cofniesz w historii).' }[akcja];
  k.innerHTML = `<button class="zamknij" aria-label="Zamknij">×</button><h2>${{ duplikuj: 'Duplikuj', przenies: 'Przenieś', scal: 'Scal', podziel: 'Podziel', usun: 'Usuń' }[akcja]}</h2>
    <p>${esc(opis)}</p><ul class="lista">${wiersze.map(w => `<li>${esc(w.kontrahent)} · ${esc(w.komentarz)} · ${esc(w.podstawa)}</li>`).join('')}</ul>
    ${akcja === 'przenies' ? pole('', 'Do arkusza', `<select id="ak-ark">${d.arkusze.filter(a => a.id !== d.arkusz.id).map(a => `<option value="${a.id}">${esc(a.folder)} / ${esc(a.nazwa)}</option>`).join('')}</select>`) : ''}
    ${akcja === 'podziel' ? pole('', 'Ile procent do nowego wiersza', '<input id="ak-proc" inputmode="decimal" value="50">') : ''}
    <div class="akcje"><button class="glowny" id="ak-ok">Wykonaj</button></div>`;
  k.hidden = false;
  $('.zamknij', k).onclick = () => { k.hidden = true; };
  $('#ak-ok').onclick = async () => {
    const ops = [];
    // aktualne płatności wiersza z kwotami netto (te same, które sumuje komórka)
    const platnosciWiersza = w => Object.values(w.komorki).flatMap(c => Object.entries(c.kwoty || {}).map(([id, netto]) => ({ id, netto })));
    const kopia = (wzor, wiersz, netto) => ({ op: 'platnosc', obiekt: { id: nowyId('p'), wzor, wiersz, netto } });
    // pola wiersza do zapisu (bez pól liczonych przez apkę)
    const opisWiersza = w => {
      const o = { arkusz: w.arkusz, rodzaj: w.rodzaj, podstawa: w.podstawa, kontrahent: w.kontrahent || '', komentarz: w.komentarz || '',
        przedmiot: w.przedmiot || '', sekcja: w.sekcja || '', dzien_wystawienia: w.dzien_wystawienia || '', metoda: w.metoda || '',
        ksiegowane: !!w.ksiegowane, w_cashflow: !!w.w_cashflow, cykl: w.cykl || 'brak', plan: w.plan || null, split: !!w.split };
      if (w.proporcje) o.proporcje = w.proporcje;
      if (w.kup) o.kup = w.kup;
      if (stawkaStd(w.stawka_vat) != null) o.stawka_vat = stawkaStd(w.stawka_vat);
      if (w.dni_na_platnosc !== '' && w.dni_na_platnosc != null) o.dni_na_platnosc = w.dni_na_platnosc;
      return o;
    };
    // komórki z kwotą wpisaną w apce kopiujemy jako kwoty (plany policzą się z ustawień kopii), resztę jako kopie płatności
    const zKomorek = w => Object.entries(w.komorki).filter(([, c]) => c.kwota != null);
    const spozaKomorek = w => Object.values(w.komorki).filter(c => c.kwota == null).flatMap(c => Object.entries(c.kwoty || {}).map(([id, netto]) => ({ id, netto })));
    if (akcja === 'duplikuj') for (const w of wiersze) {
      const id = nowyId('w');
      ops.push({ op: 'wiersz', obiekt: { ...opisWiersza(w), id } }, ...zKomorek(w).map(([m, c]) => ({ op: 'komorka', wiersz: id, miesiac: m, kwota: c.kwota })),
        ...spozaKomorek(w).map(x => kopia(x.id, id, x.netto)));
    }
    if (akcja === 'przenies') ops.push({ op: 'przenies', wiersze: ids, do_arkusza: $('#ak-ark').value });
    if (akcja === 'usun') wiersze.forEach(w => ops.push({ op: 'wiersz', obiekt: { id: w.id }, usun: true }));
    if (akcja === 'scal') {
      const id = nowyId('w');
      ops.push({ op: 'wiersz', obiekt: { ...opisWiersza(wiersze[0]), id, komentarz: `scalone: ${wiersze.map(w => w.komentarz || w.kontrahent).join(' + ')}`.slice(0, 170) } });
      wiersze.forEach(w => platnosciWiersza(w).forEach(x => ops.push(kopia(x.id, id, x.netto))));
      wiersze.forEach(w => ops.push({ op: 'wiersz', obiekt: { id: w.id }, usun: true }));
    }
    if (akcja === 'podziel') {
      const proc = parseFloat($('#ak-proc').value.replace(',', '.')) / 100;
      if (!(proc > 0 && proc < 1)) return komunikat('Procent między 0 a 100.', true);
      const w = wiersze[0], id = nowyId('w');
      ops.push({ op: 'wiersz', obiekt: { ...opisWiersza(w), id, komentarz: `${w.komentarz || ''} (część)`.slice(0, 170) } });
      platnosciWiersza(w).forEach(x => {
        const czesc = Math.round(x.netto * proc);
        ops.push(kopia(x.id, id, czesc), { op: 'platnosc', obiekt: { id: x.id, netto: x.netto - czesc } });
      });
    }
    if (!ops.length) return komunikat('Brak zmian do zapisania.', true);
    zmiana('bud', ops.length === 1 ? ops[0] : { op: 'seria', operacje: ops });
  };
}

// ---------- Rejestr umów z klientami ----------
Object.assign(POMOC, {
  umowy: { tytul: 'Rejestr umów', krotko: 'Umowy z klientami i terminy wypowiedzenia, z alertem przed czasem.',
    co: 'Każda umowa: klient, data zawarcia, czas określony albo nieokreślony, okres wypowiedzenia, wartość miesięczna.',
    skad: 'Wpisujesz Ty; zapis w pliku zmian (oba Maki widzą to samo).',
    jak: 'Określony z przedłużeniem: ostatni dzień na wypowiedzenie = koniec minus okres. Bez przedłużenia: data wygaśnięcia. Nieokreślony: najwcześniejszy koniec przy wypowiedzeniu dziś.',
    zrob: 'Czerwone i żółte wiersze wymagają decyzji: przedłużyć, renegocjować albo wypowiedzieć.' },
});
const STAN_UMOWY = { 'minął': 'minus', alert: 'ostrzezenie', ok: 'plus', 'bez terminu': 'neutral' };

Object.assign(WIDOKI, {
  async 'budzet/umowy'() {
    const d = await api('umowy');
    const wiersze = d.umowy.map((u, i) => `<tr data-i="${i}"><td><span class="chip ${STAN_UMOWY[u.stan]}">${esc(u.stan)}</span></td><td>${esc(u.klient)}</td>
      <td>${u.rodzaj === 'okreslony' ? `do ${dataPl(u.do)}${u.przedluzenie ? ', przedłuża się' : ''}` : 'nieokreślony'}</td>
      <td>${u.wypowiedzenie_mies} mies.${u.koniec_miesiaca ? ', na koniec miesiąca' : ''}</td>
      <td><b>${dataPl(u.data)}</b><div class="szary">${esc(u.co)}${u.dni >= 0 ? ` · za ${u.dni} dni` : ''}</div></td>
      <td class="liczba-kol">${zl(u.wartosc_mies, false)}</td><td class="szary">${esc(u.uwagi || '')}</td></tr>`).join('');
    setTimeout(() => {
      $('#dodaj-umowe').onclick = e => { e.stopPropagation(); kartaUmowy(null); };
      document.querySelectorAll('tr[data-i]').forEach(tr => tr.onclick = e => { e.stopPropagation(); kartaUmowy(d.umowy[tr.dataset.i]); });
    });
    return `<div class="naglowek-strony"><div><h1>Umowy z klientami ${pytajnik('umowy')}</h1>
        <div class="okruszki">Budżet / rejestr umów · ${d.umowy.length} umów, ${zl(d.wartosc_mies)} miesięcznie${d.alerty ? ` · <b class="minus">${d.alerty} do decyzji</b>` : ''}</div></div>
        <button class="przycisk" id="dodaj-umowe">Dodaj umowę</button></div>
      ${d.umowy.length ? `<div class="tabela-ramka niska"><table><thead><tr><th>Stan</th><th>Klient</th><th>Czas trwania</th><th>Wypowiedzenie</th><th>Termin</th>
        <th class="liczba-kol">Wartość / mies.</th><th>Uwagi</th></tr></thead><tbody>${wiersze}</tbody></table></div>`
        : '<div class="pusto">Brak umów. Dodaj pierwszą przyciskiem w prawym górnym rogu.</div>'}`;
  },
});

async function kartaUmowy(u) {
  const k = $('#karta');
  const w = await api('wydatki', { ile: 1 });
  k.innerHTML = `<button class="zamknij" aria-label="Zamknij">×</button><h2>${u ? 'Umowa' : 'Nowa umowa'}</h2>
    <div class="formularz">
      ${pole('', 'Klient', `<input id="u-klient" list="lista-klientow" value="${esc(u?.klient || '')}">`)}${listaKlientow(w.klienci)}
      ${pole('', 'Data zawarcia', `<input id="u-zawarta" type="date" value="${esc(u?.zawarta || '')}">`)}
      ${pole('', 'Czas trwania', `<select id="u-rodzaj"><option value="nieokreslony">nieokreślony</option><option value="okreslony"${u?.rodzaj === 'okreslony' ? ' selected' : ''}>określony</option></select>`)}
      ${pole('', 'Koniec (czas określony)', `<input id="u-do" type="date" value="${esc(u?.do || '')}">`)}
      ${pole('', 'Przedłuża się automatycznie', `<select id="u-przedl"><option value="">nie</option><option value="1"${u?.przedluzenie ? ' selected' : ''}>tak</option></select>`)}
      ${pole('', 'Okres wypowiedzenia (miesiące)', `<input id="u-okres" inputmode="numeric" value="${u?.wypowiedzenie_mies ?? 1}">`)}
      ${pole('', 'Ze skutkiem na koniec miesiąca', `<select id="u-km"><option value="1">tak</option><option value=""${u && !u.koniec_miesiaca ? ' selected' : ''}>nie</option></select>`)}
      ${pole('', 'Wartość miesięczna netto (zł)', `<input id="u-wartosc" inputmode="decimal" value="${u?.wartosc_mies ? (u.wartosc_mies / 100).toFixed(2).replace('.', ',') : ''}">`)}
      ${pole('', 'Alert ile dni wcześniej', `<input id="u-alert" inputmode="numeric" value="${u?.alert_dni ?? 30}">`)}
      ${pole('', 'Uwagi', `<input id="u-uwagi" value="${esc(u?.uwagi || '')}">`)}
    </div>
    <div class="akcje"><button class="glowny" id="u-zapisz">Zapisz</button>${u ? '<button id="u-usun">Usuń umowę</button>' : ''}</div>`;
  k.hidden = false;
  $('.zamknij', k).onclick = () => { k.hidden = true; };
  $('#u-zapisz').onclick = () => zmiana('umowa', { id: u?.id || nowyId('u'), klient: $('#u-klient').value.trim(), zawarta: $('#u-zawarta').value,
    rodzaj: $('#u-rodzaj').value, do: $('#u-do').value, przedluzenie: !!$('#u-przedl').value, wypowiedzenie_mies: $('#u-okres').value,
    koniec_miesiaca: !!$('#u-km').value, wartosc_mies: String(naGrosze($('#u-wartosc').value || '0') || 0), alert_dni: $('#u-alert').value, uwagi: $('#u-uwagi').value });
  if (u) $('#u-usun').onclick = () => zmiana('umowa', { id: u.id, usun: true });
}

// ---------- Cash flow jak w Budget Studio ----------
// Zapisane widoki (zakres liczony od dnia stanu przy każdym otwarciu), pasek filtrów, panel „Wygląd i filtry”,
// tabela okresów z SUM/MAX/MIN, minimapa z ramką wycinka, wykres i lista płatności wycinka. Wszystkie liczby z serwera
// (GET /api/cashflow/okresy); tu tylko wycinek, wyszukiwarka, sortowanie i strony listy.
const WIDOKI_CF = [
  { id: '2tyg', nazwa: '2 tyg. w przód', ik: 'kalendarz', granulacja: 'dzien', dni: 13 },
  { id: '13tyg', nazwa: '13 tyg. w przód', ik: 'kalendarz', granulacja: 'tydzien', dni: 90 },
  { id: '6mies', nazwa: '6 mies. w przód', ik: 'kalendarz', granulacja: 'tydzien', mies: 6 },
  { id: '12mies', nazwa: '12 mies. w przód', ik: 'kalendarz', granulacja: 'miesiac', mies: 12 },
  { id: 'rok', nazwa: 'Ten rok: historia i prognoza', ik: 'fale', granulacja: 'miesiac', rok: true },
  { id: 'dni', nazwa: 'Dzień po dniu (30 dni)', ik: 'fale', granulacja: 'dzien', dni: 29 },
];
const GRANULACJE = { dzien: 'Dzień', tydzien: 'Tydzień', miesiac: 'Miesiąc' };
const TYPY_CF = { plan: 'Plany z budżetu', faktura: 'Należności z faktur', bank: 'Przepływy z banku', szacunek: 'Szacunek kosztów' };
const SERIE_CF = { wplywy: 'Wpływy', obciazenia: 'Obciążenia', saldo: 'Saldo okresu', narastajaco: 'Saldo narastające' };
const KOLUMNY_CF = [
  ['rodzaj', 'Rodzaj'], ['podstawa', 'Podstawa<br>płatności'], ['kontrahent', 'Kontrahent'], ['tytul', 'Tytuł'], ['nr_dok', 'Numer<br>dokumentu'],
  ['netto', 'Netto PLN<br>(wartość)'], ['brutto', 'Brutto PLN<br>(wartość)'], ['vat', 'VAT PLN<br>(wartość)'], ['stawka', 'Stawka<br>VAT'],
  ['wystawienie', 'Dzień<br>wystawienia'], ['data', 'Dzień realnej<br>płatności'], ['przesuniecie', 'Przesunięcie<br>płatności'],
  ['arkusz', 'Arkusz budżetu'], ['miesiac', 'Miesiąc<br>budżetowy'], ['metoda', 'Metoda<br>płatności'], ['waluta', 'Waluta'], ['etap', 'Etap']];
const KOLUMNY_CF_DOMYSLNE = KOLUMNY_CF.map(k => k[0]).filter(k => k !== 'etap');
const KROPKA_TYPU = { plan: 'niebieska', faktura: 'zolta', bank: 'zielona', szacunek: 'szara' };
const MAKS_PUNKTOW = 120;
let cfPanel = false;   // panel „Wygląd i filtry” zostaje otwarty po Zastosuj (jak w BS)

const plusMies = (iso, n) => { const d = new Date(iso + 'T12:00:00Z'); d.setUTCMonth(d.getUTCMonth() + n); d.setUTCDate(d.getUTCDate() - 1); return d.toISOString().slice(0, 10); };
function zakresWidoku(v, stan) {
  if (v.rok) { const k = `${stan.slice(0, 4)}-12-31`, pol = plusMies(stan, 6); return { od: `${stan.slice(0, 4)}-01-01`, do: pol > k ? pol : k }; }
  return { od: stan, do: v.dni ? plusDni(stan, v.dni) : plusMies(stan, v.mies) };
}
const zlSaldo = s => { const t = String(s ?? '').replace(/[\s ]/g, '').replace(',', '.'); const m = /^(-?)(\d+)(?:\.(\d{1,2}))?$/.exec(t);
  return m ? (m[1] ? -1 : 1) * ((+m[2]) * 100 + +((m[3] || '') + '00').slice(0, 2)) : NaN; };
function kolumnyCf() {
  try { const z = JSON.parse(localStorage.getItem('finanse-cf-kolumny') || 'null'); if (Array.isArray(z) && z.length) return z; } catch (e) { /* wygoda, nie stan */ }
  return KOLUMNY_CF_DOMYSLNE;
}

function kartaSumCf(okresy, maks, mini) {
  if (!okresy.length) return '';
  const zakres = okresy.length === 1 ? okresy[0].etykieta : `${okresy[0].etykieta.split(' – ')[0]} - ${okresy[okresy.length - 1].etykieta.split(' – ').pop()}`;
  const kl = v => v < 0 ? 'minus' : 'plus';
  const sum = okresy[okresy.length - 1].narastajaco;
  return `<div class="cf-karta"><div class="zakres">${esc(zakres)}</div><dl>
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
  return `<div class="cf-tabela"><table><thead><tr><th></th>${okresy.map(o => `<th>${o.biezacy ? `<span class="biezacy" title="okres dnia stanu">${esc(o.etykieta)}</span>` : esc(o.etykieta)}</th>`).join('')}</tr></thead>
    <tbody>${wiersz('Saldo narastająco', '+', 'narastajaco', '', true)}${wiersz('Saldo okresu', '=', 'saldo')}
    <tr class="oddziel w-wplywy"><td><span class="znak-w">↗</span>Wpływy</td>${okresy.map(o => `<td>${zl(o.wplywy, false)}</td>`).join('')}</tr>
    ${wiersz('Obciążenia', '↘', 'obciazenia', 'w-obciazenia')}</tbody></table></div>`;
}

function komorkaCf(x, k) {
  const z = v => v == null ? '' : zl(v, false);
  return {
    rodzaj: chipZnak(x.kwota), podstawa: esc(x.podstawa || ''), kontrahent: esc(x.kontrahent || ''), tytul: esc(x.tytul || ''), nr_dok: esc(x.nr_dok || '-'),
    netto: z(x.netto), brutto: z(x.kwota), vat: z(x.vat), stawka: x.stawka != null ? `${x.stawka}%` : '-', wystawienie: dataPl(x.wystawienie),
    data: dataPl(x.data), przesuniecie: `${x.przesuniecie || 0} dni`, arkusz: esc(x.arkusz || '-'), miesiac: x.miesiac ? mies(x.miesiac) : '',
    metoda: esc(x.metoda || ''), waluta: esc(x.waluta || 'PLN'), etap: esc(x.etap || ''),
  }[k];
}
const SORT_CF = { rodzaj: x => x.kwota > 0 ? 1 : 0, netto: x => x.netto ?? 0, brutto: x => x.kwota, vat: x => x.vat ?? 0, stawka: x => x.stawka ?? -1,
  przesuniecie: x => x.przesuniecie || 0 };
const LICZBOWE_CF = ['netto', 'brutto', 'vat', 'stawka', 'przesuniecie'];

async function widokCashflow(p, { arkusz = null, ark = null } = {}) {
  const stan = STAN?.naleznosci?.dzien_stanu || STAN?.bank_do;
  const widok = WIDOKI_CF.find(v => v.id === p.widok) || WIDOKI_CF[1];
  const bazowy = arkusz ? { granulacja: 'tydzien', od: stan, do: ark && `${ark.do}-28` > stan ? plusMies(`${ark.do}-01`, 1) : plusMies(stan, 6) } : { granulacja: widok.granulacja, ...zakresWidoku(widok, stan) };
  const ef = { granulacja: p.granulacja || bazowy.granulacja, od: p.od || bazowy.od, do: p.do || bazowy.do, rodzaj: p.rodzaj || '',
    saldo_start: p.saldo ?? '', scenariusz: p.scenariusz || 'ostrozny' };
  const d = await api('cashflow/okresy', { ...ef, arkusz: arkusz || '' });
  if (d.brak_danych) return '<h1>Cash flow</h1><div class="pusto">Brak danych z banku.</div>';
  const typy = (p.typ || '').split(',').filter(Boolean);
  const serie = p.serie ? Object.fromEntries(Object.keys(SERIE_CF).map(k => [k, p.serie.split(',').includes(k)])) : {};
  const zmienione = ['granulacja', 'od', 'do', 'rodzaj', 'saldo', 'scenariusz', 'typ', 'serie'].filter(k => p[k] != null && p[k] !== '');
  const n = d.okresy.length;
  const bi = Math.max(0, d.okresy.findIndex(o => o.biezacy));
  let okno = n <= MAKS_PUNKTOW ? [0, n - 1] : [Math.max(0, Math.min(n - MAKS_PUNKTOW, bi - 4)), Math.max(0, Math.min(n - MAKS_PUNKTOW, bi - 4)) + MAKS_PUNKTOW - 1];
  const caly = d.okresy, maxC = caly[d.max.okres], minC = caly[d.min.okres];
  const poTerminie = d.pozycje.filter(z => z.etap === 'Po terminie').length;
  const pasujacyZakres = WIDOKI_CF.find(v => { const z = zakresWidoku(v, stan); return z.od === ef.od && z.do === ef.do; });
  let lista = { q: '', strona: 1, ile: 100, sort: 'data', kier: 'rosnaco' };

  const rysujWycinek = () => {
    const [a, b] = okno, wyc = caly.slice(a, b + 1);
    const mx = wyc.reduce((x, y) => y.narastajaco > x.narastajaco ? y : x), mn = wyc.reduce((x, y) => y.narastajaco < x.narastajaco ? y : x);
    $('#cf-karta-dol').innerHTML = kartaSumCf(wyc, mx, mn);
    $('#cf-tabela').innerHTML = tabelaOkresowCf(wyc);
    $('#cf-powieksz').disabled = n > MAKS_PUNKTOW || (a === 0 && b === n - 1);
    WYK.ustaw({ okresy: wyc });
    rysujListe();
  };
  let WYK = null;
  const rysujListe = () => {
    const [a, b] = okno, q = lista.q.trim().toLowerCase();
    let poz = d.pozycje.filter(z => z.okres >= a && z.okres <= b && (!typy.length || typy.includes(z.typ)));
    if (q) poz = poz.filter(z => `${z.kontrahent} ${z.tytul} ${z.nr_dok} ${z.arkusz} ${z.opis}`.toLowerCase().includes(q));
    const f = SORT_CF[lista.sort] || (x => x[lista.sort] ?? '');
    const znak = lista.kier === 'rosnaco' ? 1 : -1;
    poz.sort((x, y) => { const u = f(x), v = f(y); return znak * (typeof u === 'number' ? u - v : String(u).localeCompare(String(v), 'pl')); });
    const kol = kolumnyCf();
    const razem = poz.length, ost = Math.max(1, Math.ceil(razem / lista.ile));
    lista.strona = Math.min(lista.strona, ost);
    const od = (lista.strona - 1) * lista.ile, strona = poz.slice(od, od + lista.ile);
    const th = kol.map(k => `<th class="sort${LICZBOWE_CF.includes(k) ? ' liczba-kol' : ''}" data-k="${k}"${lista.sort === k ? ` data-kierunek="${lista.kier}"` : ''}>${KOLUMNY_CF.find(x => x[0] === k)[1]}</th>`).join('');
    const tr = strona.map((x, i) => `<tr data-i="${od + i}" class="${x.typ === 'plan' || x.typ === 'szacunek' ? 'wiersz-plan' : x.etap === 'Po terminie' ? 'wiersz-po' : ''}${x.kwota > 0 ? ' wiersz-plus' : ''}" title="${esc(x.opis)}">
      <td class="lp">${od + i + 1}.</td><td class="kr"><span class="kropka ${x.etap === 'Po terminie' ? 'czerwona' : KROPKA_TYPU[x.typ]}" title="${esc(TYPY_CF[x.typ])}${x.etap ? ', ' + esc(x.etap.toLowerCase()) : ''}"></span></td>
      ${kol.map(k => `<td class="${LICZBOWE_CF.includes(k) ? 'liczba-kol' : ''}">${komorkaCf(x, k)}</td>`).join('')}</tr>`).join('');
    $('#cf-lista').innerHTML = razem ? `<div class="tabela-ramka niska"><table><thead><tr><th class="lp"></th><th></th>${th}</tr></thead><tbody>${tr}</tbody></table></div>`
      : '<div class="pusto">Brak płatności w tym wycinku.</div>';
    $('#cf-info').textContent = `Wyświetlono ${razem ? od + 1 : 0}-${Math.min(od + lista.ile, razem)} z ${razem}`;
    $('#cf-poprz').disabled = lista.strona <= 1;
    $('#cf-nast').disabled = lista.strona >= ost;
    $('#cf-lista').querySelectorAll('th.sort').forEach(h => h.onclick = () => {
      lista.kier = lista.sort === h.dataset.k && lista.kier === 'rosnaco' ? 'malejaco' : 'rosnaco'; lista.sort = h.dataset.k; rysujListe(); });
    $('#cf-lista').querySelectorAll('tbody tr').forEach(r => r.onclick = e => {
      e.stopPropagation();
      const x = poz[r.dataset.i];
      if (x.typ === 'plan') kartaPlatnosci([x.zrodlo], null);
      else if (x.typ === 'faktura') location.hash = `#/platnosci/faktury?q=${encodeURIComponent(x.nr_dok)}`;
      else if (x.typ === 'bank') location.hash = `#/platnosci/bank?q=${encodeURIComponent(x.kontrahent || x.tytul)}&od=${x.data}&do=${x.data}`;
    });
  };

  setTimeout(() => {
    if (!$('#cf-wyk')) return;
    WYK = Wykresy.bs($('#cf-wyk'), { okresy: caly.slice(okno[0], okno[1] + 1), wysokosc: 220, serie, opis: 'Cash flow: wpływy, obciążenia i saldo' });
    const mapa = Wykresy.minimapa($('#cf-mapa'), { wartosci: caly.map(o => o.narastajaco), etykiety: caly.map(o => o.etykieta), okno, maks: MAKS_PUNKTOW,
      naZmiane: o2 => { okno = o2; lista.strona = 1; rysujWycinek(); } });
    $('#cf-powieksz').onclick = () => { okno = [0, n - 1]; mapa.ustaw(okno); rysujWycinek(); };
    rysujWycinek();
    $('#cf-ile').onchange = e => { lista.ile = +e.target.value; lista.strona = 1; rysujListe(); };
    $('#cf-poprz').onclick = () => { lista.strona--; rysujListe(); };
    $('#cf-nast').onclick = () => { lista.strona++; rysujListe(); };
    let t;
    $('#cf-szukaj').oninput = e => { clearTimeout(t); t = setTimeout(() => { lista.q = e.target.value; lista.strona = 1; rysujListe(); }, 200); };
    // pasek filtrów: działa od razu, jak filtry podręczne w BS
    document.querySelectorAll('[data-cf]').forEach(el => el.onchange = () => {
      const k = el.dataset.cf;
      if (k === 'zakres') {
        if (el.value === 'wlasny') { cfPanel = true; return otworzPanelCf(); }
        const v = WIDOKI_CF.find(x => x.id === el.value);
        if (v) return ustawParametry(zakresWidoku(v, stan));
      }
      ustawParametry({ [k]: el.value });
    });
    const saldo = $('#cf-saldo');
    saldo.onchange = () => {
      if (!saldo.value.trim()) return ustawParametry({ saldo: '' });
      const g = zlSaldo(saldo.value);
      if (isNaN(g)) return komunikat('Saldo startowe wpisz liczbą, np. 70 000,00.', true);
      ustawParametry({ saldo: String(g) });
    };
    $('#cf-saldo-wyczysc').onclick = () => ustawParametry({ saldo: '' });
    const przyw = $('#cf-przywroc');
    if (przyw) przyw.onclick = () => { location.hash = arkusz ? `#/budzet/arkusz?id=${encodeURIComponent(arkusz)}&zakladka=cashflow` : `#/cashflow?widok=${widok.id}`; };
    $('#cf-filtry').onclick = e => { e.stopPropagation(); cfPanel = !cfPanel; cfPanel ? otworzPanelCf() : zamknijPanelCf(); };
    const menu = $('#cf-menu');
    if (menu) menu.onclick = e => {
      e.stopPropagation();
      const m = document.createElement('div');
      m.className = 'zarzadzaj-menu';
      m.innerHTML = `<a href="/api/eksport/cashflow">${ik('plik')}Eksport do Excela (prognoza 13 tygodni)</a>
        <a href="#/cashflow?widok=${widok.id}">${ik('przywroc')}Usuń zastosowane filtry</a>`;
      const r = menu.getBoundingClientRect();
      m.style.left = `${r.left}px`; m.style.top = `${r.bottom + window.scrollY + 4}px`;
      document.body.appendChild(m);
      setTimeout(() => document.addEventListener('click', () => m.remove(), { once: true }));
    };
    if (cfPanel) otworzPanelCf();
  });

  function otworzPanelCf() {
    const panel = $('#panel-filtrow');
    const szkic = { granulacja: ef.granulacja, saldo: p.saldo ?? '', scenariusz: ef.scenariusz, rodzaj: ef.rodzaj, od: ef.od, do: ef.do,
      typ: typy.length ? typy : Object.keys(TYPY_CF), serie: Object.keys(SERIE_CF).filter(k => serie[k] !== false), kolumny: kolumnyCf() };
    const sekcja = (klucz, etykieta, wartosc, html, zm) => `<details${zm ? ' class="zmienione"' : ''}><summary>${etykieta}: <b>${esc(wartosc)}</b></summary><div class="zawartosc">${html}</div></details>`;
    const radio = (nazwa, opcje, wart) => Object.entries(opcje).map(([v, t]) => `<label><input type="radio" name="pf-${nazwa}" value="${v}"${String(wart) === v ? ' checked' : ''}>${esc(t)}</label>`).join('');
    const pola = (nazwa, opcje, wybrane) => Object.entries(opcje).map(([v, t]) => `<label><input type="checkbox" name="pf-${nazwa}" value="${v}"${wybrane.includes(v) ? ' checked' : ''}>${t.replace('<br>', ' ')}</label>`).join('');
    panel.innerHTML = `<div class="gora"><button class="zamknij" aria-label="Zamknij filtry">×</button><h2>Wygląd i filtry</h2>
        ${arkusz ? '' : `<label class="etyk">Zapisane widoki</label><select id="pf-widok">${WIDOKI_CF.map(v => `<option value="${v.id}"${v.id === widok.id ? ' selected' : ''}>${esc(v.nazwa)}</option>`).join('')}</select>`}</div>
      <div class="srodek">
        <div class="grupa">Wygląd</div>
        ${sekcja('granulacja', 'Granulacja', GRANULACJE[szkic.granulacja], radio('granulacja', GRANULACJE, szkic.granulacja), p.granulacja)}
        ${sekcja('saldo', 'Saldo startowe', szkic.saldo !== '' ? zl(+szkic.saldo) : 'z banku', `<input type="text" id="pf-saldo" inputmode="decimal" placeholder="z banku: ${esc(zl(d.saldo_start, false))}" value="${szkic.saldo !== '' ? esc(zlWpis(+szkic.saldo)) : ''}"><span class="szary">Puste: gotówka z banku na koniec dnia przed zakresem.</span>`, p.saldo)}
        ${sekcja('scenariusz', 'Scenariusz', szkic.scenariusz === 'pelny' ? 'pełny' : 'ostrożny', radio('scenariusz', { ostrozny: 'ostrożny: bez zaległości', pelny: 'pełny: zaległości za 7 dni' }, szkic.scenariusz), p.scenariusz)}
        ${sekcja('serie', 'Serie wykresu', szkic.serie.length === 4 ? 'Wszystkie' : `${szkic.serie.length} z 4`, pola('serie', SERIE_CF, szkic.serie), p.serie)}
        ${sekcja('kolumny', 'Widoczne kolumny', `${szkic.kolumny.length} z ${KOLUMNY_CF.length}`, pola('kolumny', Object.fromEntries(KOLUMNY_CF), szkic.kolumny), false)}
        <div class="grupa">Cechy</div>
        ${sekcja('rodzaj', 'Rodzaj', { '': 'Wszystko', 1: 'Wpływy', '-1': 'Obciążenia' }[szkic.rodzaj], radio('rodzaj', { '': 'Wszystko', 1: 'Wpływy', '-1': 'Obciążenia' }, szkic.rodzaj), p.rodzaj)}
        ${sekcja('typ', 'Pochodzenie', szkic.typ.length === 4 ? 'Wszystko' : `${szkic.typ.length} z 4`, pola('typ', TYPY_CF, szkic.typ), p.typ)}
        <div class="grupa">Daty</div>
        ${sekcja('daty', 'Dzień realnej płatności', `${dataPl(szkic.od)} - ${dataPl(szkic.do)}`, `<label>od <input type="date" id="pf-od" value="${esc(szkic.od)}"></label><label>do <input type="date" id="pf-do" value="${esc(szkic.do)}"></label>`, p.od || p.do)}
      </div>
      <div class="dol"><button class="przycisk" id="pf-zastosuj">Zastosuj</button><button class="anuluj" id="pf-anuluj">Anuluj</button></div>`;
    panel.hidden = false;
    document.body.classList.add('filtry-otwarte');
    const w = $('#cf-filtry'); if (w) w.innerHTML = `${ik('zamknij')}Zamknij filtry <span class="kropka-fil"></span>`;
    $('.zamknij', panel).onclick = () => { cfPanel = false; zamknijPanelCf(); };
    $('#pf-anuluj').onclick = () => { cfPanel = false; zamknijPanelCf(); };
    const pw = $('#pf-widok');
    if (pw) pw.onchange = () => { location.hash = `#/cashflow?widok=${pw.value}`; };
    $('#pf-zastosuj').onclick = () => {
      const wart = n2 => panel.querySelector(`input[name="pf-${n2}"]:checked`)?.value ?? '';
      const zazn = n2 => [...panel.querySelectorAll(`input[name="pf-${n2}"]:checked`)].map(x => x.value);
      const kol = zazn('kolumny');
      try { localStorage.setItem('finanse-cf-kolumny', JSON.stringify(kol.length ? kol : KOLUMNY_CF_DOMYSLNE)); } catch (e) { /* wygoda */ }
      const s = $('#pf-saldo').value.trim(), g = s ? zlSaldo(s) : '';
      if (s && isNaN(g)) return komunikat('Saldo startowe wpisz liczbą, np. 70 000,00.', true);
      const od = $('#pf-od').value, doo = $('#pf-do').value;
      if (!od || !doo || od > doo) return komunikat('Zakres dat: początek nie może być po końcu.', true);
      const t = zazn('typ'), se = zazn('serie');
      ustawParametry({ granulacja: wart('granulacja') === bazowy.granulacja ? '' : wart('granulacja'), saldo: s ? String(g) : '',
        scenariusz: wart('scenariusz') === 'ostrozny' ? '' : wart('scenariusz'), rodzaj: wart('rodzaj'),
        typ: t.length === 4 ? '' : t.join(','), serie: se.length === 4 ? '' : se.join(','),
        od: od === bazowy.od ? '' : od, do: doo === bazowy.do ? '' : doo });
      if (JSON.stringify(kol) !== JSON.stringify(kolumnyCf())) rysujListe();
    };
  }

  const opcjeZakresu = [...(arkusz ? [] : WIDOKI_CF.map(v => [v.id, v.nazwa])), ['wlasny', pasujacyZakres && !arkusz ? 'Własny zakres…' : `${dataPl(ef.od)} - ${dataPl(ef.do)}`]];
  const wybranyZakres = !arkusz && pasujacyZakres ? pasujacyZakres.id : 'wlasny';
  const pasekFiltrow = `<div class="filtry">
      <label>Dzień realnej płatności<select data-cf="zakres">${opcjeZakresu.map(([v, t]) => `<option value="${v}"${v === wybranyZakres ? ' selected' : ''}>${esc(t)}</option>`).join('')}</select></label>
      <label>Granulacja<select data-cf="granulacja">${Object.entries(GRANULACJE).map(([v, t]) => `<option value="${v}"${v === ef.granulacja ? ' selected' : ''}>${t}</option>`).join('')}</select></label>
      <label>Rodzaj<select data-cf="rodzaj"><option value="">Wszystko</option><option value="1"${ef.rodzaj === '1' ? ' selected' : ''}>Wpływy</option><option value="-1"${ef.rodzaj === '-1' ? ' selected' : ''}>Obciążenia</option></select></label>
      <label class="pole-saldo">Saldo startowe<input id="cf-saldo" inputmode="decimal" value="${p.saldo != null && p.saldo !== '' ? esc(zlWpis(+p.saldo)) : ''}" placeholder="${esc(zl(d.saldo_start, false))}" title="${d.zrodlo_salda === 'ręcznie' ? 'wpisane ręcznie' : 'z banku: gotówka na koniec dnia przed zakresem'}">
        <button id="cf-saldo-wyczysc" type="button" aria-label="Wyczyść saldo startowe">${ik('zamknij')}</button></label>
      <button class="przycisk miekki" id="cf-filtry" type="button">${ik('filtr')}Wygląd i filtry ${zmienione.length ? '<span class="kropka-fil"></span>' : ''}</button>
      ${d.scenariusz === 'pelny' ? '<span class="pigulka miekka">scenariusz pełny</span>' : ''}
    </div>`;
  const naglowek = arkusz ? '' : `<h1>Cash flow ${pytajnik('cashflow')}</h1>
    <div class="pigulki"><span class="pigulka">${ik('warstwy')}${esc(widok.nazwa)}</span>
      ${zmienione.length ? `<button class="pigulka przywroc" id="cf-przywroc">${ik('przywroc')}Przywróć</button>` : ''}
      <button class="przycisk-ikona" id="cf-menu" aria-label="Więcej">${ik('kropki')}</button>
      <span class="szary">dzień stanu ${dataPl(d.dzien_stanu)}, saldo z ING ${zl(d.saldo_ing)}</span></div>`;
  return `${naglowek}${pasekFiltrow}
    <div class="cf-uklad">${kartaSumCf(caly, maxC, minC)}<div id="cf-tabela"></div></div>
    <div class="cf-mapa-uklad"><button class="przycisk" id="cf-powieksz">Powiększ zakres ↔</button><div id="cf-mapa"></div></div>
    <div class="cf-uklad"><div id="cf-karta-dol"></div><div id="cf-wyk"></div></div>
    <div class="cf-lista-naglowek"><h2 class="sekcja">Płatności w wycinku</h2>
      <span class="legenda-stany"><span><span class="kropka niebieska"></span>plan</span><span><span class="kropka zolta"></span>faktura czeka</span>
        <span><span class="kropka czerwona"></span>po terminie</span><span><span class="kropka zielona"></span>bank</span><span><span class="kropka szara"></span>szacunek</span></span>
      ${poTerminie ? `<a class="cf-uwaga" href="#/platnosci/plan?lista=po_terminie"><span class="kropka czerwona"></span>${poTerminie} po terminie do decyzji</a>` : ''}</div>
    <div id="cf-lista"></div>
    <div class="stopka">
      <label>Max widocznych <select id="cf-ile">${[50, 100, 200, 500].map(x => `<option${x === 100 ? ' selected' : ''}>${x}</option>`).join('')}</select></label>
      <button id="cf-poprz" aria-label="Poprzednia strona">↑</button><span id="cf-info"></span><button id="cf-nast" aria-label="Następna strona">↓</button>
      <input class="szukaj" id="cf-szukaj" type="search" placeholder="Wyszukaj" aria-label="Wyszukaj kontrahenta, tytuł, numer dokumentu">
    </div>`;
}

function zamknijPanelCf() {
  $('#panel-filtrow').hidden = true;
  document.body.classList.remove('filtry-otwarte');
  const w = $('#cf-filtry'); if (w) w.innerHTML = `${ik('filtr')}Wygląd i filtry`;
}

// ---------- Lista płatności planu w stylu BS (menu Płatności i zakładka Płatności arkusza) ----------
const KROPKA_ETAPU = { 'Po terminie': 'czerwona', 'Opłacona': 'zielona', 'Planowana': 'niebieska', 'Wystawiona': 'zolta', 'Częściowo opłacona': 'zolta' };
async function listaPlanu(p, { arkusz = null, dane = null } = {}) {
  const d = dane || await api('budzet/lista', { ...p, arkusz: arkusz || '' });
  const z = v => v == null ? '' : zl(v, false);
  const kol = [
    { id: 'rodzaj', naglowek: 'Rodzaj', html: x => chipZnak(x.rodzaj) },
    { naglowek: 'Etap<br>płatności', html: x => chipEtap(x.etap) },
    { naglowek: 'Podstawa<br>płatności', wartosc: x => x.podstawa_platnosci, klasa: x => x.skladowa === 'us' || x.skladowa === 'zus' ? 'szary' : '' },
    { naglowek: 'Kontrahent', wartosc: x => x.w_kontrahent },
    { naglowek: 'Tytuł', wartosc: x => x.tytul || (x.typ === 'plan' ? 'Przedmiot transakcji' : '') },
    { naglowek: 'Numer<br>dokumentu', wartosc: x => x.nr_dok || '-' },
    { naglowek: 'Netto PLN<br>(wartość)', liczba: true, wartosc: x => z(x.netto * x.rodzaj) },
    { id: 'kwota', naglowek: 'Brutto PLN<br>(wartość)', liczba: true, wartosc: x => z(x.brutto * x.rodzaj) },
    { naglowek: 'VAT PLN<br>(wartość)', liczba: true, wartosc: x => z((x.vat || 0) * x.rodzaj) },
    { naglowek: 'Stawka<br>VAT', liczba: true, wartosc: x => x.stawka != null ? `${x.stawka}%` : '-' },
    { naglowek: 'Dzień<br>wystawienia', wartosc: x => dataPl(x.wystawienie) },
    { naglowek: 'Dzień<br>płatności', wartosc: x => dataPl(x.termin_efektywny) },
    { naglowek: 'Miesiąc<br>budżetowy', wartosc: x => mies(x.miesiac) },
    ...(arkusz ? [] : [{ naglowek: 'Arkusz budżetu', wartosc: x => x.arkusz }]),
    { naglowek: 'Uwagi', wartosc: x => x.uwaga_stanu || x.decyzja, klasa: () => 'szary' },
  ];
  return `<div class="filtry">${arkusz ? '' : filtr('lista', 'Lista', Object.entries(d.listy), d.lista)}
      ${filtr('rodzaj', 'Rodzaj', [['', 'Wszystko'], ['1', 'Wpływy'], ['-1', 'Obciążenia']], p.rodzaj)}</div>
    <p class="notka">Etap wynika z banku i Fakturowni, nie z kliknięcia: „Opłacona” dopiero, gdy jest wpłata albo przelew. ${d.razem} pozycji, saldo brutto ${zl(d.suma)}, stan na ${dataPl(d.dzien_stanu)}.</p>
    ${tabela({ kolumny: kol, dane: d.wiersze, poczatek: (d.strona - 1) * d.ile + 1, onWiersz: x => kartaPlatnosci([x.id], null),
      kropka: x => `<span class="kropka ${x.aktualnosc === 'Nieaktualna' ? 'czerwona' : KROPKA_ETAPU[x.etap] || 'szara'}" title="${esc(x.etap || '')}${x.aktualnosc === 'Nieaktualna' ? ', nieaktualna' : ''}"></span>`,
      wierszKlasa: x => `${x.typ === 'plan' ? 'wiersz-plan' : x.etap === 'Po terminie' ? 'wiersz-po' : ''}${x.rodzaj === 1 ? ' wiersz-plus' : ''}`,
      stopkaSum: { rodzaj: `suma ${d.razem} pozycji`, kwota: zl(d.suma, false) } })}
    ${stopka(d, p)}`;
}

// ---------- Arkusz budżetu: tabela jak w BS (wygląd; edycja jak dotąd: karta komórki, wiersza i płatności) ----------
const suwak = wl => `<span class="suwak${wl ? ' wl' : ''}" role="img" aria-label="${wl ? 'tak' : 'nie'}"></span>`;
const dniOpis = v => v === '' || v == null ? '' : /^\d+$/.test(String(v)) ? (+v === 0 ? 'Natychmiast' : `${v} dni`) : String(v);
const KOL_UST = [
  ['podstawa', 'Podstawa płatności', w => esc(w.podstawa), '', w => w.podstawa],
  ['vat', 'VAT', w => w.podstawa.startsWith('Faktura') ? stawka(w.stawka_vat) : '-', 'liczba-kol', w => stawkaStd(w.stawka_vat) ?? -1],
  ['dzien', 'Dzień wystaw.', w => esc(w.dzien_opis), '', w => w.dzien_opis],
  ['dni', 'Dni na płatność', w => esc(dniOpis(w.dni_na_platnosc)), 'liczba-kol', w => parseInt(w.dni_na_platnosc, 10) || 0],
  ['metoda', 'Metoda płatn.', w => esc(w.metoda || ''), '', w => w.metoda || ''],
  ['split', 'Split Pay.', w => suwak(w.split), 'przel', w => +w.split],
  ['ksiegowane', 'Księgowane', w => suwak(w.ksiegowane), 'przel', w => +w.ksiegowane],
  ['w_cashflow', 'W cash flow', w => suwak(w.w_cashflow), 'przel', w => +w.w_cashflow],
];
const KOL_OPIS = [
  ['przedmiot', 'Przedmiot transakcji', w => esc(w.przedmiot || 'Przedmiot transakcji'), 'sep', w => w.przedmiot || ''],
  ['kontrahent', 'Kontrahent', w => esc(w.kontrahent || ''), '', w => w.kontrahent || ''],
  ['sekcja', 'Sekcja', w => esc(w.sekcja || '-'), 'szary', w => w.sekcja || ''],
  ['komentarz', 'Komentarz', w => esc(w.komentarz || ''), '', w => w.komentarz || ''],
  ['rodzaj', 'Rodzaj', w => chipZnak(w.rodzaj), '', w => w.rodzaj],
];
const GRUPY_ARK = { '': 'Nie grupuj', rodzaj: 'Rodzaj', kontrahent: 'Kontrahent', przedmiot: 'Przedmiot transakcji', podstawa: 'Podstawa płatności',
  vat: 'Stawka VAT', dzien: 'Dzień wystawienia', dni: 'Dni na płatność', metoda: 'Metoda płatności', ksiegowane: 'Księgowane', w_cashflow: 'W cash flow' };
const etykietaGrupy = (k, w) => ({ rodzaj: w.rodzaj === 1 ? 'wpływy' : 'obciążenia', vat: w.podstawa.startsWith('Faktura') ? stawka(w.stawka_vat) : 'bez VAT',
  dzien: w.dzien_opis, dni: dniOpis(w.dni_na_platnosc) || '-', ksiegowane: w.ksiegowane ? 'Księgowane' : 'Nieksięgowane',
  w_cashflow: w.w_cashflow ? 'W cash flow' : 'Poza cash flow', sekcja: w.sekcja || 'bez sekcji' }[k] ?? (w[k] || '-'));
const miesNag = m => { const t = mies(m); return t.charAt(0).toUpperCase() + t.slice(1); };

function arkuszTabela(d, p) {
  const m = d.miesiace, ust = p.ustawienia === '1', sekcje = p.sekcje === '1', grupuj = GRUPY_ARK[p.grupuj] ? p.grupuj || '' : '';
  const stanM = (STAN?.naleznosci?.dzien_stanu || '').slice(0, 7);
  const kolumny = [...(ust ? KOL_UST : []), ...KOL_OPIS];
  const nOpis = 1 + (d.planowanie ? 1 : 0) + kolumny.length;
  let wiersze = [...d.wiersze];
  const ks = kolumny.find(k => k[0] === p.sortuj);
  if (ks) {
    const znak = p.kolejnosc === 'malejaco' ? -1 : 1;
    wiersze.sort((a, b) => { const x = ks[4](a), y = ks[4](b); return znak * (typeof x === 'number' ? x - y : String(x).localeCompare(String(y), 'pl')); });
  }
  const suma = w => Object.values(w.komorki).reduce((s, k) => s + k.netto, 0);
  const kom = (w, x) => {
    const k = w.komorki[x];
    if (!k) return `<td class="liczba-kol pusta${d.planowanie ? ' klik' : ''}" data-w="${esc(w.id)}" data-m="${x}">-</td>`;
    const kl = ['komorka', k.rzeczywiste ? '' : 'plany', k.stan === 'po-terminie' ? 'po-terminie' : '', k.stan === 'wg-bs' ? 'wg-bs' : '', k.netto < 0 ? 'minus' : k.netto > 0 ? 'plus' : ''].filter(Boolean).join(' ');
    const kropka = k.nieaktualne || k.stan === 'po-terminie' ? '<span class="kropka czerwona" title="wymaga uwagi"></span>' : k.stan === 'oplacona' ? '<span class="kropka zielona" title="opłacone"></span>' : '';
    const tytul = `${k.platnosci.length} ${k.platnosci.length === 1 ? 'płatność' : 'płatności'}${k.rzeczywiste ? `, w tym rzeczywiste: ${k.rzeczywiste}` : ', tylko plany'}`;
    return `<td class="liczba-kol ${kl}" data-p="${k.platnosci.join(',')}" data-w="${esc(w.id)}" data-m="${x}" title="${tytul}"><span class="kom">${kropka}${zl(k.netto, false)}</span></td>`;
  };
  let lp = 0;
  const wiersz = w => `<tr data-w="${esc(w.id)}"><td class="lp">${++lp}.</td>${d.planowanie ? `<td class="kr"><input type="checkbox" data-zazn="${esc(w.id)}" aria-label="Zaznacz wiersz"></td>` : ''}
    ${kolumny.map(k => `<td class="opis-kom ${k[3] || ''}${k[0] === 'podstawa' || k[0] === 'dzien' ? ' ust' : ''}">${k[2](w)}</td>`).join('')}
    ${m.map(x => kom(w, x)).join('')}<td class="liczba-kol sep ${suma(w) < 0 ? 'minus' : 'plus'}">${zl(suma(w), false)}</td></tr>`;
  const naglowekGrupy = (etyk, ws, wciecie = false) => {
    const s = x => ws.reduce((a, w) => a + (w.komorki[x]?.netto || 0), 0);
    const r = ws.reduce((a, w) => a + suma(w), 0);
    return `<tr class="grupa"><td colspan="${nOpis}">${wciecie ? '&nbsp;&nbsp;&nbsp;· ' : ''}${esc(etyk)} <span class="szary">(${ws.length})</span></td>
      ${m.map(x => `<td class="liczba-kol ${s(x) < 0 ? 'minus' : s(x) > 0 ? 'plus' : 'szary'}">${s(x) ? zl(s(x), false) : '-'}</td>`).join('')}<td class="liczba-kol sep">${zl(r, false)}</td></tr>`;
  };
  const grupy = (ws, klucz) => { const g = new Map(); ws.forEach(w => { const e = etykietaGrupy(klucz, w); (g.get(e) || g.set(e, []).get(e)).push(w); }); return [...g]; };
  let tbody = '';
  if (sekcje) {
    for (const [sek, ws] of grupy(wiersze, 'sekcja')) {
      tbody += naglowekGrupy(sek, ws);
      tbody += grupuj ? grupy(ws, grupuj).map(([e, xs]) => naglowekGrupy(e, xs, true) + xs.map(wiersz).join('')).join('') : ws.map(wiersz).join('');
    }
  } else if (grupuj) tbody = grupy(wiersze, grupuj).map(([e, ws]) => naglowekGrupy(e, ws) + ws.map(wiersz).join('')).join('');
  else tbody = wiersze.map(wiersz).join('');
  const sumaCala = d.podsumowanie.reduce((a, x) => a + x.saldo, 0);
  const wp = d.podsumowanie.reduce((a, x) => a + x.wplywy, 0), ob = d.podsumowanie.reduce((a, x) => a + x.obciazenia, 0);
  const pusteOpis = `<th colspan="${nOpis}"></th>`;
  const thead = `<tr class="ark-wykres">${pusteOpis}<th colspan="${m.length + 1}"><div id="ark-wyk"></div></th></tr>
    <tr class="ark-mies">${pusteOpis}${m.map(x => `<th class="${x === stanM ? 'biezacy' : ''}">${esc(miesNag(x))}</th>`).join('')}<th class="sep">Suma</th></tr>
    <tr class="ark-suma pierwszy"><th class="etyk" colspan="${nOpis}">=</th>${d.podsumowanie.map(s => `<th>${zl(s.saldo, false)}</th>`).join('')}<th class="sep">${zl(sumaCala, false)}</th></tr>
    <tr class="ark-suma"><th class="etyk" colspan="${nOpis}"><span class="plus">↗</span><br><span class="minus">↘</span></th>${d.podsumowanie.map(s => `<th><span class="plus">${zl(s.wplywy, false)}</span><br><span class="minus">${zl(s.obciazenia, false)}</span></th>`).join('')}
      <th class="sep"><span class="plus">${zl(wp, false)}</span><br><span class="minus">${zl(ob, false)}</span></th></tr>
    <tr class="ark-kol"><th class="lp"></th>${d.planowanie ? '<th></th>' : ''}${kolumny.map(k => `<th class="sort${k[3] === 'liczba-kol' ? ' liczba-kol' : ''}${k[3] === 'sep' ? ' sep' : ''}" data-sort="${k[0]}"${p.sortuj === k[0] ? ` data-kierunek="${p.kolejnosc === 'malejaco' ? 'malejaco' : 'rosnaco'}"` : ''}>${k[1]}</th>`).join('')}
      ${m.map(() => '<th></th>').join('')}<th class="sep"></th></tr>`;
  let wybrana = null;
  setTimeout(() => {
    const tab = $('#ark-tabela');
    if (!tab) return;
    const naglowkiMies = () => [...tab.querySelectorAll('tr.ark-mies th:not([colspan])')].slice(0, m.length);
    Wykresy.bs($('#ark-wyk'), { wysokosc: 118, opis: 'Arkusz miesięcznie: wpływy, obciążenia i saldo narastające',
      okresy: d.podsumowanie.map(s => ({ etykieta: mies(s.miesiac), wplywy: s.wplywy, obciazenia: s.obciazenia, saldo: s.saldo, narastajaco: s.narastajaco, biezacy: s.miesiac === stanM })),
      kolumny: () => { const r0 = $('#ark-wyk').getBoundingClientRect(); return naglowkiMies().map(th => { const r = th.getBoundingClientRect(); return { x: r.left - r0.left, w: r.width }; }); } });
    const wiersz = id => d.wiersze.find(w => w.id === id);
    const pokazWiersz = w => {
      tab.querySelectorAll('tr.zaznaczony').forEach(x => x.classList.remove('zaznaczony'));
      tab.querySelector(`tr[data-w="${CSS.escape(w.id)}"]`)?.classList.add('zaznaczony');
      $('#ark-zazn').innerHTML = `<span>${w.rodzaj === 1 ? '<b class="plus">↗</b>' : '<b class="minus">↘</b>'} ${esc(w.podstawa)}</span><span>${w.podstawa.startsWith('Faktura') ? stawka(w.stawka_vat) : 'bez VAT'}</span>
        <span>${esc(w.dzien_opis)}</span><span>${esc(dniOpis(w.dni_na_platnosc))}</span><span>${esc(w.metoda || '')}</span>
        <span>split ${suwak(w.split)}</span><span>K ${suwak(w.ksiegowane)}</span><span>CF ${suwak(w.w_cashflow)}</span>
        <span>${esc(w.przedmiot || 'Przedmiot transakcji')}</span><span>${esc(w.kontrahent || '')}</span><span>${esc(w.sekcja || '-')}</span>`;
    };
    const wybierz = td => {
      tab.querySelectorAll('.wybrana').forEach(x => x.classList.remove('wybrana'));
      td.classList.add('wybrana'); wybrana = td;
      pokazWiersz(wiersz(td.dataset.w));
      $('#ark-karta').disabled = !td.classList.contains('komorka');
    };
    tab.querySelectorAll('td.komorka').forEach(td => td.onclick = e => { e.stopPropagation(); wybierz(td);
      kartaPlatnosci(td.dataset.p.split(','), d, { w: wiersz(td.dataset.w), m: td.dataset.m }); });
    tab.querySelectorAll('td.pusta').forEach(td => td.onclick = e => { e.stopPropagation(); wybierz(td);
      if (d.planowanie) kartaKomorki(wiersz(td.dataset.w), td.dataset.m); });
    tab.querySelectorAll('tr[data-w] td.opis-kom').forEach(td => td.onclick = e => {
      e.stopPropagation(); const w = wiersz(td.parentElement.dataset.w); pokazWiersz(w); if (d.planowanie) kartaWiersza(w, d); });
    $('#ark-karta').onclick = e => { e.stopPropagation(); if (wybrana?.classList.contains('komorka')) wybrana.click(); };
    tab.querySelectorAll('th.sort').forEach(h => h.onclick = () => ustawParametry({ sortuj: h.dataset.sort,
      kolejnosc: p.sortuj === h.dataset.sort && p.kolejnosc !== 'malejaco' ? 'malejaco' : 'rosnaco' }));
    $('#ark-grupuj').onchange = e => ustawParametry({ grupuj: e.target.value });
    $('#ark-sekcje').onchange = e => ustawParametry({ sekcje: e.target.checked ? '1' : '' });
    $('#ark-ustawienia').onchange = e => ustawParametry({ ustawienia: e.target.checked ? '1' : '' });
    // wyszukiwarka arkusza: nie ukrywa wierszy, podświetla komórki z frazą (A-ARK-12)
    let trafienia = [], nr = -1;
    const szukaj = $('#ark-szukaj');
    szukaj.oninput = () => {
      const q = szukaj.value.trim().toLowerCase();
      tab.querySelectorAll('.podswietl').forEach(x => x.classList.remove('podswietl'));
      trafienia = q ? [...tab.querySelectorAll('tbody td')].filter(td => td.textContent.toLowerCase().includes(q)) : [];
      trafienia.forEach(td => td.classList.add('podswietl'));
      nr = -1;
    };
    const skocz = krok => { if (!trafienia.length) return; nr = (nr + krok + trafienia.length) % trafienia.length; trafienia[nr].scrollIntoView({ block: 'center', inline: 'center' }); };
    $('#ark-szukaj-gora').onclick = () => skocz(-1);
    $('#ark-szukaj-dol').onclick = () => skocz(1);
    document.addEventListener('keydown', function f(e) {
      if (!document.body.contains(szukaj)) return document.removeEventListener('keydown', f);
      if ((e.metaKey || e.ctrlKey) && e.key === 'f') { e.preventDefault(); szukaj.focus(); }
    });
    if (d.planowanie) {
      $('#dodaj-wiersz').onclick = e => { e.stopPropagation(); kartaWiersza(null, d); };
      document.querySelectorAll('[data-akcja]').forEach(b => b.onclick = e => { e.stopPropagation(); akcjaNaWierszach(b.dataset.akcja, d); });
    }
    if (d.wiersze[0]) pokazWiersz(d.wiersze[0]);
  });
  return `<div class="ark-pasek">
      <label class="pole-grupuj">Grupuj wiersze wg<select id="ark-grupuj">${Object.entries(GRUPY_ARK).map(([v, t]) => `<option value="${v}"${v === grupuj ? ' selected' : ''}>${t}</option>`).join('')}</select></label>
      <label class="przelacznik"><input type="checkbox" id="ark-sekcje"${sekcje ? ' checked' : ''}><span class="suwak"></span>Sekcje</label>
      <label class="przelacznik"><input type="checkbox" id="ark-ustawienia"${ust ? ' checked' : ''}><span class="suwak"></span>Ustawienia planowanych płatności</label>
      <span class="prawo"></span>
      ${d.planowanie ? `<button class="przycisk glowny" id="dodaj-wiersz">Dodaj wiersz ${ik('plus')}</button>` : ''}
      <button class="przycisk" id="ark-karta" disabled data-karta>Otwórz kartę płatności</button></div>
    ${d.planowanie ? `<div class="akcje"><span class="szary">Zaznaczone wiersze:</span><button data-akcja="duplikuj">Duplikuj</button><button data-akcja="przenies">Przenieś do arkusza</button>
        <button data-akcja="scal">Scal</button><button data-akcja="podziel">Podziel</button><button data-akcja="usun">Usuń</button></div>`
      : '<p class="notka">Tryb podglądu: plany z Budget Studio. Edycję włącza przełącznik w Ustawieniach budżetu.</p>'}
    <div class="legenda-stany"><span><i class="plany"></i>tylko plany</span><span><i class="rzecz"></i>rzeczywiste</span><span><i class="po"></i>po terminie</span>
      <span><i class="wg-bs"></i>opłacone tylko wg BS</span><span><span class="kropka czerwona"></span>wymaga uwagi</span><span><span class="kropka zielona"></span>opłacone</span></div>
    <div class="tabela-ramka arkusz" id="ark-tabela"><table class="ark"><thead>${thead}</thead><tbody>${tbody || `<tr><td colspan="${nOpis + m.length + 1}" class="pusto">Arkusz nie ma wierszy.</td></tr>`}</tbody></table></div>
    <div class="stopka"><span class="zaznaczony" id="ark-zazn"></span>
      <button id="ark-szukaj-gora" aria-label="Poprzednie trafienie">↑</button><button id="ark-szukaj-dol" aria-label="Następne trafienie">↓</button>
      <input class="szukaj" id="ark-szukaj" type="search" placeholder="Wyszukaj" aria-label="Wyszukaj w arkuszu"></div>`;
}

function menuZarzadzaj(przycisk, d) {
  document.querySelectorAll('.zarzadzaj-menu').forEach(x => x.remove());
  const m = document.createElement('div');
  m.className = 'zarzadzaj-menu';
  m.innerHTML = `<a href="/api/eksport/arkusz?id=${encodeURIComponent(d.arkusz.id)}">${ik('plik')}Eksport arkusza do Excela</a>
    ${d.planowanie ? `<button data-m="wiersz">${ik('plus')}Dodaj wiersz</button>` : ''}
    <a href="#/budzet/historia">${ik('historia')}Historia zmian planów</a>
    <div class="opis">Zmiana nazwy, zakresu miesięcy i folderu arkusza: jeszcze nie w apce.</div>`;
  const r = przycisk.getBoundingClientRect();
  m.style.left = `${r.left}px`; m.style.top = `${r.bottom + window.scrollY + 2}px`;
  document.body.appendChild(m);
  const b = m.querySelector('[data-m="wiersz"]');
  if (b) b.onclick = e => { e.stopPropagation(); m.remove(); kartaWiersza(null, d); };
  setTimeout(() => document.addEventListener('click', () => m.remove(), { once: true }));
}

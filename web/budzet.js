'use strict';
// Budżet jak w Budget Studio (folder → kategoria → arkusz), listy płatności planu, rozjazdy, historia, ustawienia,
// cash flow, rentowność klientów i arkuszy. Korzysta z funkcji z app.js (api, zmiana, tabela, zl, ...).

const ETAPY_KLASA = { 'Opłacona': 'plus', 'Planowana': 'neutral', 'Po terminie': 'minus', 'Wystawiona': 'akcent',
  'Częściowo opłacona': 'ostrzezenie', 'Opłacona wg BS': 'ostrzezenie', 'Nieaktualna': 'neutral' };
const chipEtap = e => `<span class="chip ${ETAPY_KLASA[e] || 'neutral'}">${esc(e || '')}</span>`;
const PODSTAWY = ['Faktura (jedna)', 'Faktura (w worku)', 'Bez faktury', 'Bez faktury (w worku)', 'Umowa o dzieło', 'Umowa zlecenie',
  'Umowa o pracę'];   // VAT i podatek dochodowy tylko w arkuszu systemowym Opłaty urzędowe (pakiet 8)
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
    skad: 'Eksport Budget Studio (plik importu w Finanse/Aplikacja, odtwarzany przy każdym eksporcie), a po włączeniu planowania w Ustawieniach budżetu także plany wpisane w apce (plik zmian).',
    jak: 'Kolor komórki: zielony opłacone (z banku), szary plan, czerwony plan po terminie, żółty „opłacone według BS”, ale bez śladu w banku lub Fakturowni.',
    zrob: 'Klik zaznacza komórkę, Enter albo wpisanie liczby edytuje kwotę, Cmd+Enter otwiera kartę płatności z fakturą i przelewem. Czerwona kropka: plan nieaktualny, do naprawy (przesuń, przenieś kwotę, usuń).' },
  rozjazdy: { tytul: 'Rozjazdy z Budget Studio', krotko: 'Gdzie Budget Studio mówi co innego niż bank i Fakturownia.',
    co: 'Pozycje opłacone w BS bez śladu w danych, zapłacone w banku a w BS nadal planowane, różne kwoty, faktury i wydatki bez pozycji w BS.',
    skad: 'Import z eksportu BS kontra wpłaty, wydatki i faktury w apce.',
    jak: 'Koszty pracy, VAT i podatek dochodowy porównujemy sumą w miesiącu płatności, bo BS trzyma koszt pracodawcy w jednej kwocie.',
    zrob: 'Przejrzyj największe kwoty. Dopóki Budget Studio jest źródłem planów, poprawki robisz w BS.' },
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
        <div class="okruszki">Budżet / ${d.planowanie ? 'planowanie w apce włączone' : 'planowanie wyłączone (Ustawienia budżetu): plany z Budget Studio, tylko do odczytu'}</div></div>
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
    // Zdarzenia podpinamy po narysowaniu treści zakładki: Płatności i Cash flow najpierw pytają serwer, a wcześniejszy
    // setTimeout trafiłby w przyciski poprzedniego ekranu (zakładki nie reagowały na klik).
    const podepnij = () => setTimeout(() => {
      document.querySelectorAll('[data-zakl]').forEach(b => b.onclick = e => {
        if (b.dataset.zakl === 'zarzadzaj') { e.stopPropagation(); return menuZarzadzaj(b, d); }
        location.hash = `#/budzet/arkusz?id=${encodeURIComponent(a.id)}${b.dataset.zakl === 'arkusz' ? '' : '&zakladka=' + b.dataset.zakl}`;
      });
      // A-ARK-01: klik w nazwę = zmiana nazwy, ikona folderu = zmiana folderu i kategorii
      const n = $('#ark-nazwa'), f = $('#ark-miejsce');
      if (n) n.onclick = e => { e.stopPropagation(); kartaNazwy(d); };
      if (f) f.onclick = e => { e.stopPropagation(); kartaMiejsca(d); };
    });
    const tytul = d.planowanie ? `<button class="tytul-ark" id="ark-nazwa" data-karta title="Zmień nazwę">${esc(a.nazwa)}</button>` : esc(a.nazwa);
    const miejsce = d.planowanie ? `<button class="ikona-ark" id="ark-miejsce" data-karta title="Folder: ${esc(a.folder)}, kategoria: ${esc(a.kategoria)}. Kliknij, żeby zmienić.">${ik('folderOko', 'ik-tytul szary')}</button>`
      : `<span title="Folder: ${esc(a.folder)}, kategoria: ${esc(a.kategoria)}">${ik('folderOko', 'ik-tytul szary')}</span>`;
    const naglowek = `<h1>${ik('pinezka', 'ik-tytul')}${tytul}${miejsce}</h1>
      <div class="pigulki"><span class="pigulka">${ik('warstwy')}${nazwyZakl[zakl]} / Widok główny</span>
        <span class="szary">${esc(a.folder)} / ${esc(a.kategoria)} · ${mies(a.od)} - ${mies(a.do)} · źródło: ${esc(a.zrodlo)}</span></div>
      <div class="zakladki" role="tablist">
        <button role="tab" data-zakl="arkusz" aria-selected="${zakl === 'arkusz'}">${ik('arkusz')}Arkusz</button>
        <button role="tab" data-zakl="platnosci" aria-selected="${zakl === 'platnosci'}">${ik('fale')}Płatności</button>
        <button role="tab" data-zakl="cashflow" aria-selected="${zakl === 'cashflow'}">${ik('fale')}Cash flow</button>
        <button role="tab" data-zakl="zarzadzaj" aria-selected="false" data-karta>${ik('zebatka')}Zarządzaj</button></div>
      ${banerOsieroconych(0)}${umowaArkuszaHtml(d.umowa)}${d.systemowy ? `<p class="notka">Arkusz systemowy: VAT i podatek dochodowy liczy apka z budżetu, więc tu nic się nie edytuje.
        Kwotę od biura i dzień realnej płatności wpiszesz w <a href="#/budzet/podatki">Budżet, Podatki i ZUS</a>.</p>` : ''}`;
    const tresc = zakl === 'cashflow' ? await widokCashflow(p, { arkusz: a.id, ark: a })
      : zakl === 'platnosci' ? await listaPlatnosci(p, { arkusz: a.id })   // lista z pakietu 7 (listy.js)
        : `<div id="ark-widok">${arkuszTabela(d, p)}</div>`;
    podepnij();
    return naglowek + tresc;
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
      else if (tr.dataset.ark) location.hash = `#/budzet/arkusz?id=${encodeURIComponent(tr.dataset.ark)}`;
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
        : '<div class="pusto">Brak zmian planów wpisanych w apce.</div>'}`;
  },

  async 'budzet/ustawienia'() {
    const [d, k] = await Promise.all([api('budzet/drzewo'), api('rentownosc/klienci')]);
    setTimeout(() => {
      $('#przelacz-planowanie').onclick = () => zmiana('ustawienie', { klucz: 'planowanie', wartosc: d.planowanie ? 'nie' : 'tak' });
    });
    return `<h1>Ustawienia budżetu</h1><div class="okruszki">Budżet / Ustawienia</div>
      <div class="karta-wyk"><h3>Planowanie w apce</h3>
        <p class="notka">Teraz: <b>${d.planowanie ? 'włączone' : 'wyłączone'}</b>. Dopóki planowanie jest wyłączone, edycja budżetu w apce jest zablokowana: plany pochodzą z Budget Studio, a apka tylko je czyta i porównuje z bankiem.
        Po włączeniu dodajesz i zmieniasz arkusze, wiersze i płatności jak w Budget Studio; każda zmiana trafia do historii i da się ją cofnąć (Cmd+Z na arkuszu). Wyłączenie nie kasuje zmian.</p>
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

const NAZWY_OP = { komorka: 'kwota w komórce', wiersz: 'wiersz', platnosc: 'płatność', arkusz: 'arkusz', przenies: 'przeniesienie wierszy',
  decyzja_planu: 'decyzja o planie', scal: 'scalenie wierszy', podziel: 'podział wiersza', duplikuj: 'duplikat wierszy',
  przesun_arkusz: 'przesunięcie startu arkusza', duplikuj_arkusz: 'duplikat arkusza' };
const nazwaOp = op => String(op || '').split(': ').map(x => NAZWY_OP[x] || x).join(': ');

function opisZmiany(h) {
  try {
    const b = JSON.parse(h.bylo || 'null'), j = JSON.parse(h.jest || 'null');
    const op = String(h.op || '').replace(/^seria: /, '');
    if (op === 'scal') return `scalono ${b?.wiersze?.length || ''} wierszy w jeden`;
    if (op === 'podziel') return 'wiersz rozdzielony na osobne wiersze, po jednej płatności';
    if (op === 'duplikuj') return 'kopia wiersza z kwotami';
    if (op === 'duplikuj_arkusz') return `kopia arkusza${j?.nazwa ? ` „${j.nazwa}”` : ''}`;
    if (op === 'przesun_arkusz') return `${b?.od ? `${mies(b.od)} - ${mies(b.do)}` : ''} → ${j?.od ? `${mies(j.od)} - ${mies(j.do)}` : ''}`;
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
  const zapisz = () => {
    const pole_ = k.querySelector('[data-kwota]').value.trim();
    const kwota = pole_ === '' ? null : kwotaZTekstu(pole_);
    if (Number.isNaN(kwota)) return komunikat('Wpisz kwotę liczbą, np. 1 234,56.', true);
    zapiszBud({ op: 'komorka', wiersz: w.id, miesiac: m, kwota });
  };
  b.onclick = zapisz;
  k.querySelector('[data-kwota]').onkeydown = e => { if (e.key === 'Enter') { e.preventDefault(); zapisz(); } };
  const c = k.querySelector('[data-wyczysc-komorke]');
  if (c) c.onclick = () => zapiszBud({ op: 'komorka', wiersz: w.id, miesiac: m, kwota: null });
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

// Pole formularza → cecha płatności do pomarańczowego podświetlenia (odstępstwo od ustawień wiersza).
const POLE_ODST = { kontrahent: 'kontrahent', komentarz: 'komentarz', wystawienie: 'wystawienie', termin: 'termin', realny: 'realny', metoda: 'metoda',
  ksiegowane: 'ksiegowane', w_cashflow: 'w_cashflow', stawka: 'stawka' };

function formularzPlatnosci(p) {
  const pola = polaPlanu(p);
  if (!pola.length) return '<p class="szary">PIT i ZUS umowy idą za składową dla osoby: zmień ją albo ustawienia wiersza.</p>';
  const dni = p.wystawienie && p.termin ? roznicaDni(p.wystawienie, p.termin) : '';
  const f = {
    netto: () => pole('', p.generowany ? 'Kwota (zmienia kwotę komórki)' : 'Netto (zł)', `<input data-f="netto" inputmode="decimal" value="${zlWpis(p.netto)}">`),
    stawka: () => pole('', 'Stawka VAT', `<select data-f="stawka">${STAWKI.map(x => `<option value="${x}"${p.stawka === x ? ' selected' : ''}>${x} %</option>`).join('')}</select>`),
    kontrahent: () => pole('', 'Kontrahent', `<input data-f="kontrahent" value="${esc(p.w_kontrahent || '')}">`),
    komentarz: () => pole('', 'Komentarz (do 170 znaków)', `<input data-f="komentarz" maxlength="170" value="${esc(p.komentarz || '')}">`),
    wystawienie: () => pole('', 'Dzień wystawienia (przesuwa dzień płatności o tyle samo)', `<input type="date" data-f="wystawienie" value="${esc(p.wystawienie || '')}">`),
    dni: () => pole('', 'Dni na płatność', `<input data-f="dni" inputmode="numeric" value="${dni}">`),
    termin: () => pole('', 'Dzień płatności', `<input type="date" data-f="termin" value="${esc((p.typ === 'plan' ? p.termin : p.termin_efektywny) || '')}">`),
    realny: () => pole('', 'Dzień realnej płatności', `<input type="date" data-f="realny" value="${esc(p.realny || '')}">`),
    metoda: () => pole('', 'Metoda płatności', `<input data-f="metoda" value="${esc(p.metoda || '')}">`),
    ksiegowane: () => pole('', 'Księgowane (VAT, CIT, rentowność)', `<select data-f="ksiegowane"><option value="1">tak</option><option value=""${p.ksiegowane ? '' : ' selected'}>nie</option></select>`),
    w_cashflow: () => pole('', 'W cash flow', `<select data-f="w_cashflow"><option value="1">tak</option><option value=""${p.w_cashflow ? '' : ' selected'}>nie</option></select>`),
  };
  const odst = new Set(p.odstepstwa || []);
  const html = pola.map(x => { const h = f[x](); return odst.has(POLE_ODST[x]) ? h.replace('<label class="pole">', '<label class="pole inna" title="Inne niż w ustawieniach wiersza">') : h; }).join('');
  // rzeczywista: pola dokumentu edytowalne dopiero po „Edytuj dane” (B-LIS-13)
  const rz = p.typ !== 'plan';
  return `${rz ? `<div class="akcje"><button data-edytuj-dane="${esc(p.id)}">Edytuj dane</button><span class="szary">Dane dokumentu zmieniaj tylko, gdy import się pomylił.</span></div>` : ''}
    <div${rz ? ' hidden' : ''} data-edycja-box="${esc(p.id)}"><div class="formularz" data-edyt="${esc(p.id)}">${html}</div>
    <div class="akcje"><button data-zapisz="${esc(p.id)}">Zapisz tę płatność</button>${p.typ === 'plan' && !(WOREK.includes(p.podstawa) && p.generowany) && !p.skladowa ? `<button data-usun-plan="${esc(p.id)}">Usuń plan</button>` : ''}</div>
    ${p.typ === 'plan' ? '<p class="szary">Zmiana tej samej cechy w wierszu nadpisze ręczną zmianę we wszystkich planach wiersza.</p>' : ''}</div>`;
}

function zbierzPlatnosc(box) {
  const o = {};
  box.querySelectorAll('[data-f]').forEach(el => { o[el.dataset.f] = el.value; });
  return o;
}

// Treść karty jednej płatności: dane, etap, powiązania, decyzja po terminie, edycja (plany) i historia. Cechy różne od
// ustawień wiersza (ręczne wyjątki, dane dokumentu) pomarańczowe (A-ARK-11).
function htmlPlatnosci({ platnosc: p, powiazania, historia }, { plan, wKomorce = false }) {
  const odst = new Set(p.odstepstwa || []);
  const dd = (pole_, html) => `<dd${odst.has(pole_) ? ' class="inna" title="Inne niż w ustawieniach wiersza"' : ''}>${html}</dd>`;
  return `<section class="karta-platnosc" data-platnosc="${esc(p.id)}"><h2>${esc(p.w_kontrahent || p.tytul || 'Płatność')}</h2>
    <div class="szary">${wKomorce ? '' : `${esc(p.folder)} / ${esc(p.arkusz)} · ${mies(p.miesiac)} · `}${p.typ === 'plan' ? 'plan' : 'rzeczywista'}${p.skladowa ? ` · ${esc(p.podstawa_platnosci)}` : ''}</div>
    <dl><dt>Podstawa</dt><dd>${esc(p.podstawa_platnosci)}</dd><dt>Etap</dt><dd>${chipEtap(p.etap)}${p.uwaga_stanu ? `\n${esc(p.uwaga_stanu)}` : ''}</dd>
      <dt>Wg reguł BS</dt><dd>${esc(p.etap_wg_bs || '')}, ${p.aktualnosc === 'Nieaktualna' ? '<span class="kropka czerwona"></span> nieaktualna' : esc((p.aktualnosc || '').toLowerCase())}</dd>
      <dt>Netto</dt><dd>${zl(p.netto * p.rodzaj)}</dd><dt>VAT</dt>${dd('stawka', `${zl(p.vat * p.rodzaj)}${p.stawka != null ? ` (${p.stawka} %)` : ''}`)}<dt>Brutto</dt><dd>${zl(p.brutto * p.rodzaj)}</dd>
      ${p.wystawienie ? `<dt>Wystawienie</dt>${dd('wystawienie', dataPl(p.wystawienie))}` : ''}<dt>Termin</dt>${dd('termin', dataPl(p.termin_efektywny))}
      ${p.realny ? `<dt>Realna płatność</dt>${dd('realny', dataPl(p.realny))}` : ''}${p.ksiegowanie ? `<dt>Księgowanie</dt>${dd('ksiegowanie', mies(p.ksiegowanie.slice(0, 7)))}` : ''}
      ${p.data_zaplaty ? `<dt>Zapłacono</dt><dd>${dataPl(p.data_zaplaty)}</dd>` : ''}
      <dt>Kontrahent</dt>${dd('kontrahent', esc(p.w_kontrahent || '-'))}<dt>Metoda</dt>${dd('metoda', esc(p.metoda || '-'))}
      <dt>Księgowane</dt>${dd('ksiegowane', p.ksiegowane ? 'tak' : 'nie')}<dt>W cash flow</dt>${dd('w_cashflow', p.w_cashflow ? 'tak' : 'nie')}
      ${p.komentarz || odst.has('komentarz') ? `<dt>Komentarz</dt>${dd('komentarz', esc(p.komentarz || '(pusty)'))}` : ''}
      ${p.nr_dok ? `<dt>Nr dokumentu</dt><dd>${esc(p.nr_dok)}</dd>` : ''}${p.nr_wewn ? `<dt>Nr wewnętrzny</dt><dd>${esc(p.nr_wewn)}</dd>` : ''}
      ${p.tytul ? `<dt>Tytuł</dt><dd>${esc(p.tytul)}</dd>` : ''}${p.bs_id ? `<dt>Etap w BS</dt><dd>${esc(p.etap_bs || '-')}</dd>` : ''}
      ${p.decyzja ? `<dt>Decyzja</dt><dd>${esc(p.decyzja)}</dd>` : ''}</dl>
    ${odst.size ? `<p class="szary"><span class="inna">Pomarańczowe</span>: inne niż w ustawieniach wiersza (${esc([...odst].map(x => ODSTEPSTWA_OPIS[x] || x).join(', '))}). Zmiana tej cechy w wierszu ${p.typ === 'plan' ? 'je nadpisze' : 'nie zmieni rzeczywistej'}.</p>` : ''}
    <h3>Powiązania</h3>${powiazania.length ? `<ul class="lista">${powiazania.map(x => `<li><b>${esc(x.typ)}</b> ${esc((x.opis || '').replace(/(-?\d+) gr/g, (_, v) => zl(+v)))} <span class="szary">${esc(x.metoda)}, ${esc(x.pewnosc)}</span></li>`).join('')}</ul>` : '<p class="szary">Brak: ani faktury, ani przelewu.</p>'}
    ${plan && p.etap === 'Po terminie' ? `<h3>Decyzja</h3><div class="akcje" data-pid="${esc(p.id)}"><input type="date" data-termin>
      <button data-d="przesun">Przesuń</button><button data-d="zaplacone">Zapłacone</button><button data-d="anuluj">Anuluj</button></div>` : ''}
    ${plan ? `<h3>${p.typ === 'plan' ? 'Zmień ten plan' : 'Dane dokumentu'}</h3>${formularzPlatnosci(p)}` : ''}
    ${historia.length ? `<h3>Historia</h3><ul class="lista">${historia.map(h => `<li>${esc(new Date(h.czas).toLocaleString('pl-PL'))}: ${esc(nazwaOp(h.op))} <span class="szary">${esc(opisZmiany(h))}</span></li>`).join('')}</ul>` : ''}
    <div class="zrodlo">Źródło: ${esc(p.zrodlo || '')}${p.bs_id ? `, ID w BS ${esc(p.bs_id)}, wiersz ${p.wiersz_pliku}` : ''}</div></section>`;
}
const ODSTEPSTWA_OPIS = { kontrahent: 'kontrahent', komentarz: 'komentarz', metoda: 'metoda', ksiegowane: 'Księgowane', w_cashflow: 'W cash flow',
  stawka: 'stawka VAT', wystawienie: 'dzień wystawienia', termin: 'dzień płatności', realny: 'dzień realnej płatności', ksiegowanie: 'miesiąc księgowania' };

// Zdarzenia w karcie płatności (pojedynczej albo komórki): decyzje, edycja zmienionych pól, usunięcie planu.
function podepnijPlatnosci(k, dane) {
  const zostaw = { zostawKarte: true };
  k.querySelectorAll('[data-d]').forEach(b => b.onclick = () => {
    const box = b.closest('[data-pid]');
    const termin = $('[data-termin]', box).value;
    if (b.dataset.d === 'przesun' && !termin) return komunikat('Wybierz nowy termin.', true);
    zapiszBud({ op: 'decyzja_planu', platnosc: box.dataset.pid, decyzja: b.dataset.d, termin, data: termin }, zostaw);
  });
  k.querySelectorAll('[data-edytuj-dane]').forEach(b => b.onclick = () => {
    k.querySelector(`[data-edycja-box="${CSS.escape(b.dataset.edytujDane)}"]`).hidden = false;
    b.closest('.akcje').hidden = true;
  });
  k.querySelectorAll('[data-usun-plan]').forEach(b => b.onclick = () => zapiszBud({ op: 'platnosc', obiekt: { id: b.dataset.usunPlan }, usun: true }, zostaw));
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
      if (k2 === 'netto') { const g = kwotaZTekstu(v); if (Number.isNaN(g)) return komunikat('Podaj kwotę liczbą, np. 1 234,56.', true); obiekt.netto = g; }
      else if (k2 === 'stawka') obiekt.stawka = +v;
      else if (k2 === 'ksiegowane' || k2 === 'w_cashflow') obiekt[k2] = !!v;
      else obiekt[k2] = v;
    }
    if (Object.keys(obiekt).length === 1) return komunikat('Nic się nie zmieniło.', true);
    zapiszBud({ op: 'platnosc', obiekt }, zostaw);
  });
}

// Karta płatności z list, cash flow i rozjazdów (wszystkie wskazane płatności, bez limitu); z komórki arkusza karta komórki.
async function kartaPlatnosci(ids, ark, kom) {
  if (kom && kom.w && typeof kartaKomorkiArk === 'function' && arkWidoczny()) return kartaKomorkiArk(kom.w.id, kom.m);
  const k = $('#karta');
  let dane;
  try { dane = await Promise.all(ids.map(id => api('budzet/platnosc', { id }))); } catch (e) { return komunikat(e.message, true); }
  const plan = dane[0]?.planowanie;
  k.innerHTML = `<button class="zamknij" aria-label="Zamknij">×</button>${dane.map(x => htmlPlatnosci(x, { plan })).join('<hr>')}`;
  k.hidden = false;
  $('.zamknij', k).onclick = () => { k.hidden = true; };
  podepnijPlatnosci(k, dane);
}

// Wiersz = generator planów (pakiet 2): podstawa, VAT, reguła dnia wystawienia, dni na płatność, metoda, przełączniki,
// proporcje umów. Zapis wysyła tylko zmienione cechy: zmiana cechy nadpisuje ją we wszystkich planach wiersza.
function kartaWiersza(w, d, wstepne = {}) {
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
  // z listy podstaw w arkuszu: umowa potrzebuje kwot od księgowej, więc karta otwiera się z wybraną podstawą
  if (wstepne.podstawa) { $('#w-podstawa').value = wstepne.podstawa; odswiez(); $('#w-prop-osoba').focus(); }
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
    zapiszBud(ops.length === 1 ? ops[0] : { op: 'seria', operacje: ops });
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

// ---------- Rejestr umów z klientami ----------
// Pakiet 9: umowa wskazuje folder klienta w budżecie i jego arkusze przychodowe (cash flow: pozycje „z umowy”, scenariusz
// „klienci odchodzą”, ostrzeżenie o planach po końcu umowy). Kartę klienta z umową robi pakiet 11.
Object.assign(POMOC, {
  umowy: { tytul: 'Rejestr umów', krotko: 'Umowy z klientami i terminy wypowiedzenia, z alertem przed czasem; powiązane z folderem klienta w budżecie.',
    co: 'Każda umowa: klient i jego folder w budżecie, arkusze przychodowe, data zawarcia, czas określony albo nieokreślony, okres wypowiedzenia (osobno nasz, gdy inny), wartość miesięczna netto.',
    skad: 'Wpisujesz Ty; zapis w pliku zmian (oba Maki widzą to samo). Stara umowa bez folderu jest dopasowana do folderu po nazwie klienta.',
    jak: 'Określony z przedłużeniem: ostatni dzień na wypowiedzenie = koniec minus okres. Bez przedłużenia: data wygaśnięcia. Nieokreślony: najwcześniejszy koniec przy wypowiedzeniu dziś. Cash flow: gdy plany wpływów klienta się kończą, dolicza wartość z umowy (czas nieokreślony albo z przedłużeniem); po końcu umowy na czas określony nie dolicza, a plany po końcu oznacza ostrzeżeniem.',
    zrob: 'Czerwone i żółte wiersze wymagają decyzji: przedłużyć, renegocjować albo wypowiedzieć. Klienci bez umowy są liczeni w cash flow tylko z planów.' },
});
const STAN_UMOWY = { 'minął': 'minus', alert: 'ostrzezenie', ok: 'plus', 'bez terminu': 'neutral' };

Object.assign(WIDOKI, {
  async 'budzet/umowy'() {
    const d = await api('umowy');
    const obie = (o, pole) => o[pole].klient === o[pole].my ? dataPl(o[pole].klient) : `klient ${dataPl(o[pole].klient)}, my ${dataPl(o[pole].my)}`;
    const wiersze = d.umowy.map((u, i) => `<tr data-i="${i}"><td><span class="chip ${STAN_UMOWY[u.stan]}">${esc(u.stan)}</span></td><td>${esc(u.klient)}</td>
      <td>${u.folder ? esc(u.folder) : '<span class="chip ostrzezenie">brak folderu</span>'}${u.folder_zrodlo && u.folder_zrodlo !== 'wpis' ? `<div class="szary">${esc(u.folder_zrodlo)}</div>` : ''}
        <div class="szary">${u.arkusze.length ? esc(u.arkusze.map(a => a.nazwa).join(', ')) : 'bez arkuszy przychodowych'}</div></td>
      <td>${u.rodzaj === 'okreslony' ? `do ${dataPl(u.do)}${u.przedluzenie ? ', przedłuża się' : ''}` : 'nieokreślony'}</td>
      <td>${u.wypowiedzenie_mies} mies.${u.wypowiedzenie_mies_my != null && u.wypowiedzenie_mies_my !== u.wypowiedzenie_mies ? ` (nasz ${u.wypowiedzenie_mies_my} mies.)` : ''}${u.koniec_miesiaca ? ', na koniec miesiąca' : ''}
        ${u.ostatni_dzien_wypowiedzenia.klient ? `<div class="szary">ostatni dzień: ${esc(obie(u, 'ostatni_dzien_wypowiedzenia'))}</div>` : ''}</td>
      <td><b>${dataPl(u.data)}</b><div class="szary">${esc(u.co)}${u.dni >= 0 ? ` · za ${u.dni} dni` : ''}</div></td>
      <td>${esc(obie(u, 'odejscie_przy_wypowiedzeniu_dzis'))}</td>
      <td class="liczba-kol">${zl(u.wartosc_mies, false)}</td>
      <td class="szary">${u.plany_po_koncu.ile ? `<span class="chip ostrzezenie" title="Plany zostają w cash flow jak w BS">${u.plany_po_koncu.ile} plan. po końcu umowy</span> ` : ''}${esc(u.uwagi || '')}</td></tr>`).join('');
    const bez = d.klienci.filter(x => x.brak_umowy);
    setTimeout(() => {
      $('#dodaj-umowe').onclick = e => { e.stopPropagation(); kartaUmowy(null, d); };
      document.querySelectorAll('tr[data-i]').forEach(tr => tr.onclick = e => { e.stopPropagation(); kartaUmowy(d.umowy[tr.dataset.i], d); });
      document.querySelectorAll('[data-nowa-umowa]').forEach(b => b.onclick = e => { e.stopPropagation(); kartaUmowy({ klient: b.dataset.nowaUmowa, folder: b.dataset.nowaUmowa, nowa: true }, d); });
    });
    return `<div class="naglowek-strony"><div><h1>Umowy z klientami ${pytajnik('umowy')}</h1>
        <div class="okruszki">Budżet / rejestr umów · ${d.umowy.length} ${liczebnik(d.umowy.length, ['umowa', 'umowy', 'umów'])}, ${zl(d.wartosc_mies)} miesięcznie${d.alerty ? ` · <b class="minus">${d.alerty} do decyzji</b>` : ''}${d.plany_po_koncu ? ` · <b class="minus">${d.plany_po_koncu} ${liczebnik(d.plany_po_koncu, ['plan', 'plany', 'planów'])} po końcu umowy</b>` : ''}</div></div>
        <button class="przycisk" id="dodaj-umowe">Dodaj umowę</button></div>
      ${d.umowy.length ? `<div class="tabela-ramka niska"><table><thead><tr><th>Stan</th><th>Klient</th><th>Folder i arkusze w budżecie</th><th>Czas trwania</th><th>Wypowiedzenie</th><th>Termin</th>
        <th>Odejście przy wypowiedzeniu dziś</th><th class="liczba-kol">Wartość / mies.</th><th>Uwagi</th></tr></thead><tbody>${wiersze}</tbody></table></div>`
        : '<div class="pusto">Brak umów. Dodaj pierwszą przyciskiem w prawym górnym rogu.</div>'}
      ${bez.length ? `<h2 class="sekcja">Klienci bez umowy (${bez.length})</h2>
        <p class="notka">Cash flow liczy ich tylko z planów w arkuszach: bez pozycji „z umowy” i poza scenariuszem „klienci odchodzą”.</p>
        <div class="pigulki">${bez.map(x => `<button class="pigulka miekka" type="button" data-nowa-umowa="${esc(x.folder)}" title="Dodaj umowę dla folderu ${esc(x.folder)}">${ik('plus')}${esc(x.folder)}</button>`).join('')}</div>` : ''}`;
  },
});

// Pakiet 9, decyzja 10: ostrzeżenie w arkuszu, gdy są plany wpływów po końcu umowy na czas określony (zostają w cash flow).
function umowaArkuszaHtml(u) {
  const po = u?.plany_po_koncu;
  if (!u?.umowa || !po?.ile) return '';
  return `<div class="komunikat ostrzezenie"><span><span class="znacznik-umowy">!</span>${po.ile} ${liczebnik(po.ile, ['plan', 'plany', 'planów'])} wpływu po końcu umowy
    (${dataPl(u.koniec_umowy)}), od ${esc(mies(po.od_miesiaca))}, netto ${zl(po.netto)}. Jak w BS zostają w cash flow; sprawdź, czy umowa będzie przedłużona.</span>
    <a href="#/budzet/umowy">Umowy z klientami</a></div>`;
}

// Formularz umowy: folder klienta i arkusze przychodowe (puste zaznaczenie = wszystkie arkusze folderu z wpływami).
async function kartaUmowy(u, d) {
  const k = $('#karta');
  d = d || await api('umowy');
  const foldery = d.foldery || [];
  const folder = u?.folder || '';
  const wlasne = Array.isArray(u?.arkusze) && u.arkusze.length && typeof u.arkusze[0] === 'object' && u.arkusze_zrodlo === 'wpis' ? u.arkusze.map(a => a.id) : [];
  const listaArkuszy = f => {
    const ark = (foldery.find(x => x.folder === f) || { arkusze: [] }).arkusze;
    if (!ark.length) return '<span class="szary">Wybierz folder klienta.</span>';
    return ark.map(a => `<label><input type="checkbox" value="${esc(a.id)}"${wlasne.length ? (wlasne.includes(a.id) ? ' checked' : '') : (a.wplywy ? ' checked' : '')}>${esc(a.nazwa)}${a.wplywy ? '' : ' <span class="szary">(bez wpływów)</span>'}</label>`).join('');
  };
  const istniejaca = u && !u.nowa;
  k.innerHTML = `<button class="zamknij" aria-label="Zamknij">×</button><h2>${istniejaca ? 'Umowa' : 'Nowa umowa'}</h2>
    <div class="formularz">
      ${pole('', 'Klient', `<input id="u-klient" value="${esc(u?.klient || '')}">`)}
      ${pole('', 'Folder klienta w budżecie', `<select id="u-folder"><option value="">(dopasuj po nazwie klienta)</option>${foldery.map(f => `<option${f.folder === folder ? ' selected' : ''}>${esc(f.folder)}</option>`).join('')}</select>`)}
      ${pole('', 'Arkusze przychodowe (zaznaczone liczą się w cash flow)', `<div class="umowa-arkusze" id="u-arkusze">${listaArkuszy(folder)}</div>`)}
      ${pole('', 'Data zawarcia', `<input id="u-zawarta" type="date" value="${esc(u?.zawarta || '')}">`)}
      ${pole('', 'Czas trwania', `<select id="u-rodzaj"><option value="nieokreslony">nieokreślony</option><option value="okreslony"${u?.rodzaj === 'okreslony' ? ' selected' : ''}>określony</option></select>`)}
      ${pole('', 'Koniec (czas określony)', `<input id="u-do" type="date" value="${esc(u?.do || '')}">`)}
      ${pole('', 'Przedłuża się automatycznie', `<select id="u-przedl"><option value="">nie</option><option value="1"${u?.przedluzenie ? ' selected' : ''}>tak</option></select>`)}
      ${pole('', 'Okres wypowiedzenia (miesiące)', `<input id="u-okres" inputmode="numeric" value="${u?.wypowiedzenie_mies ?? 1}">`)}
      ${pole('', 'Nasz okres wypowiedzenia, gdy inny (miesiące)', `<input id="u-okres-my" inputmode="numeric" placeholder="jak klienta" value="${u?.wypowiedzenie_mies_my ?? ''}">`)}
      ${pole('', 'Ze skutkiem na koniec miesiąca', `<select id="u-km"><option value="1">tak</option><option value=""${u && u.koniec_miesiaca === false ? ' selected' : ''}>nie</option></select>`)}
      ${pole('', 'Wartość miesięczna netto (zł)', `<input id="u-wartosc" inputmode="decimal" value="${u?.wartosc_mies ? (u.wartosc_mies / 100).toFixed(2).replace('.', ',') : ''}">`)}
      ${pole('', 'Alert ile dni wcześniej', `<input id="u-alert" inputmode="numeric" value="${u?.alert_dni ?? 30}">`)}
      ${pole('', 'Uwagi', `<input id="u-uwagi" value="${esc(u?.uwagi || '')}">`)}
    </div>
    <p class="szary">Bez zaznaczonych arkuszy liczą się wszystkie arkusze folderu z wierszami wpływów. Stawka VAT i dni na płatność pozycji „z umowy” są z wiersza wpływów klienta (domyślnie 23% i 7 dni).</p>
    <div class="akcje"><button class="glowny" id="u-zapisz">Zapisz</button>${istniejaca ? '<button id="u-usun">Usuń umowę</button>' : ''}</div>`;
  k.hidden = false;
  $('.zamknij', k).onclick = () => { k.hidden = true; };
  $('#u-folder').onchange = e => {
    if (!$('#u-klient').value.trim()) $('#u-klient').value = e.target.value;
    $('#u-arkusze').innerHTML = listaArkuszy(e.target.value);
  };
  $('#u-zapisz').onclick = () => {
    const f = $('#u-folder').value;
    const zazn = [...document.querySelectorAll('#u-arkusze input:checked')].map(x => x.value);
    const domyslne = ((foldery.find(x => x.folder === f) || { arkusze: [] }).arkusze).filter(a => a.wplywy).map(a => a.id);
    const arkusze = f && !(zazn.length === domyslne.length && zazn.every(x => domyslne.includes(x))) ? zazn : [];
    zmiana('umowa', { id: istniejaca ? u.id : nowyId('u'), klient: $('#u-klient').value.trim() || f, folder: f, arkusze, zawarta: $('#u-zawarta').value,
      rodzaj: $('#u-rodzaj').value, do: $('#u-do').value, przedluzenie: !!$('#u-przedl').value, wypowiedzenie_mies: $('#u-okres').value,
      wypowiedzenie_mies_my: $('#u-okres-my').value.trim(), koniec_miesiaca: !!$('#u-km').value,
      wartosc_mies: String(naGrosze($('#u-wartosc').value || '0') || 0), alert_dni: $('#u-alert').value, uwagi: $('#u-uwagi').value });
  };
  if (istniejaca) $('#u-usun').onclick = () => zmiana('umowa', { id: u.id, usun: true });
}

// ---------- Cash flow jak w Budget Studio ----------
// Ekran cash flow (widokCashflow, także zakładka arkusza) i jego pomoc: web/cashflow.js (pakiet 9).

'use strict';
// Budżet jak w Budget Studio (folder → kategoria → arkusz), listy płatności planu, rozjazdy, historia, ustawienia,
// cash flow, rentowność klientów i arkuszy, eksport. Korzysta z funkcji z app.js (api, zmiana, tabela, zl, ...).

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
  cashflow: { tytul: 'Prognoza gotówki', krotko: 'Saldo dziś plus to, co ma wpłynąć i wypłynąć w 13 tygodni.',
    co: 'Dwa scenariusze: ostrożny (bez należności już po terminie i bez planów po terminie) i pełny (z nimi, za 7 dni).',
    skad: 'Saldo z ING, należności z Fakturowni z terminem przesuniętym o średnie spóźnienie nabywcy, plany przychodów i kosztów z budżetu.',
    jak: 'Gdy w miesiącu brak planu kosztów, prognoza dolicza szacunek kosztów pracy i stałych ze średniej 6 miesięcy.',
    zrob: 'Patrz na najniższy punkt scenariusza ostrożnego. Plany po terminie rozstrzygnij, żeby nie wisiały.' },
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

  // ---------- Widok arkusza ----------
  async 'budzet/arkusz'(p) {
    const d = await api('budzet/arkusz', { id: p.id });
    const a = d.arkusz, m = d.miesiace;
    const kom = (w, x) => {
      const k = w.komorki[x];
      if (!k) return `<td class="liczba-kol pusta${d.planowanie ? ' klik' : ''}" data-w="${esc(w.id)}" data-m="${x}">–</td>`;
      return `<td class="liczba-kol komorka ${k.stan}" data-p="${k.platnosci.join(',')}" data-w="${esc(w.id)}" data-m="${x}" title="${k.platnosci.length} płatności">${zl(k.netto, false)}</td>`;
    };
    const wiersze = d.wiersze.map(w => `<tr data-w="${w.id}">${d.planowanie ? `<td><input type="checkbox" data-zazn="${w.id}" aria-label="Zaznacz wiersz"></td>` : ''}
      <td>${esc(w.podstawa)}</td><td class="liczba-kol">${w.podstawa.startsWith('Faktura') ? stawka(w.stawka_vat) : '-'}</td>
      <td title="${esc(w.dzien_wystawienia)}">${esc(w.dzien_opis)}</td><td>${esc(w.dni_na_platnosc)}</td><td>${esc(w.metoda)}</td>
      <td>${esc(w.kontrahent)}</td><td class="szary">${esc(w.sekcja || '–')}</td><td>${esc(w.komentarz)}</td>
      <td>${w.rodzaj === 1 ? '<span class="chip plus">↗ wpływy</span>' : '<span class="chip minus">↘ obciążenia</span>'}</td>
      ${m.map(x => kom(w, x)).join('')}</tr>`).join('');
    const sumy = (pole, nazwa, klasa) => `<tr class="${klasa}"><td colspan="${d.planowanie ? 10 : 9}">${nazwa}</td>${d.podsumowanie.map(s => `<td class="liczba-kol ${s[pole] < 0 ? 'minus' : s[pole] > 0 ? 'plus' : ''}">${zl(s[pole], false)}</td>`).join('')}</tr>`;
    setTimeout(() => {
      Wykresy.slupki($('#ark-wyk'), { kategorie: m.map(mies), etykietyPelne: m.map(miesPelny), wysokosc: 220, opis: 'Arkusz miesięcznie',
        sumaStosu: {}, serie: [
          { klucz: 'w', nazwa: 'Wpływy', kolor: Wykresy.kolor('--plus'), wartosci: d.podsumowanie.map(s => s.wplywy) },
          { klucz: 'o', nazwa: 'Obciążenia', kolor: Wykresy.kolor('--minus'), wartosci: d.podsumowanie.map(s => s.obciazenia) },
          { klucz: 'n', nazwa: 'Narastająco', typ: 'linia', kolor: Wykresy.kolor('--s1'), wartosci: d.podsumowanie.map(s => s.narastajaco) }] });
      const wiersz = id => d.wiersze.find(w => w.id === id);
      document.querySelectorAll('td.komorka').forEach(td => td.onclick = e => { e.stopPropagation();
        kartaPlatnosci(td.dataset.p.split(','), d, { w: wiersz(td.dataset.w), m: td.dataset.m }); });
      if (d.planowanie) {
        document.querySelectorAll('td.pusta.klik').forEach(td => td.onclick = e => { e.stopPropagation(); kartaKomorki(wiersz(td.dataset.w), td.dataset.m); });
        $('#dodaj-wiersz').onclick = e => { e.stopPropagation(); kartaWiersza(null, d); };
        document.querySelectorAll('tr[data-w] td:not(.komorka):not(.pusta):not(:first-child)').forEach(td => td.onclick = e => {
          e.stopPropagation(); kartaWiersza(d.wiersze.find(w => w.id === td.parentElement.dataset.w), d); });
        document.querySelectorAll('[data-akcja]').forEach(b => b.onclick = e => { e.stopPropagation(); akcjaNaWierszach(b.dataset.akcja, d); });
      }
    });
    return `<div class="naglowek-strony"><div><h1>${esc(a.nazwa)}</h1>
        <div class="okruszki"><a href="#/budzet/arkusze">Arkusze</a> / ${esc(a.folder)} / ${esc(a.kategoria)} · ${mies(a.od)} – ${mies(a.do)} · źródło: ${esc(a.zrodlo)}</div></div>
        <a class="przycisk" href="/api/eksport/arkusz?id=${encodeURIComponent(a.id)}">Excel</a></div>
      <div class="karta-wyk"><h3>Arkusz miesięcznie ${pytajnik('budzet')}</h3><div class="pod">wpływy i obciążenia netto, linia: saldo narastająco</div><div id="ark-wyk"></div></div>
      ${d.planowanie ? `<div class="akcje">
        <button class="glowny" id="dodaj-wiersz">Dodaj wiersz</button>
        <span class="szary">Zaznaczone:</span><button data-akcja="duplikuj">Duplikuj</button><button data-akcja="przenies">Przenieś do arkusza</button>
        <button data-akcja="scal">Scal</button><button data-akcja="podziel">Podziel</button><button data-akcja="usun">Usuń</button></div>
        <p class="notka">Kliknij pustą komórkę, żeby wpisać kwotę planu; kliknij wiersz (opis), żeby zmienić jego ustawienia. Plany liczą się z kwoty komórki i ustawień wiersza.</p>`
        : '<p class="notka">Tryb podglądu: plany z Budget Studio. Edycję włącza przełącznik w Budżet, Ustawienia (planowanie w apce od 2027).</p>'}
      <div class="legenda-stany"><span class="komorka oplacona">opłacone (bank)</span><span class="komorka planowana">plan</span>
        <span class="komorka po-terminie">po terminie</span><span class="komorka wg-bs">opłacone tylko wg BS</span></div>
      <div class="tabela-ramka arkusz"><table><thead><tr>${d.planowanie ? '<th></th>' : ''}<th>Podstawa płatności</th><th class="liczba-kol">VAT</th><th>Dzień wystaw.</th>
        <th>Dni na płatność</th><th>Metoda</th><th>Kontrahent</th><th>Sekcja</th><th>Komentarz</th><th>Rodzaj</th>
        ${m.map(x => `<th class="liczba-kol">${mies(x)}</th>`).join('')}</tr></thead>
        <tbody>${wiersze}</tbody><tfoot>${sumy('wplywy', 'Wpływy', '')}${sumy('obciazenia', 'Obciążenia', '')}${sumy('saldo', 'Saldo miesiąca', 'suma')}${sumy('narastajaco', 'Narastająco', 'suma')}</tfoot></table></div>`;
  },

  // ---------- Listy płatności planu (jak w BS) ----------
  async 'platnosci/plan'(p) {
    const d = await api('budzet/lista', p);
    const kol = [
      { id: 'rodzaj', naglowek: 'Rodzaj', html: x => x.rodzaj === 1 ? '<span class="chip plus">↗ wpływy</span>' : '<span class="chip minus">↘ obciążenia</span>' },
      { naglowek: 'Etap', html: x => chipEtap(x.etap) },
      { naglowek: 'Kontrahent', wartosc: x => x.w_kontrahent },
      { naglowek: 'Podstawa', wartosc: x => x.podstawa_platnosci, klasa: x => x.skladowa === 'us' || x.skladowa === 'zus' ? 'szary' : '' },
      { naglowek: 'Tytuł', wartosc: x => x.tytul, klasa: () => 'szary' },
      { naglowek: 'Arkusz', wartosc: x => x.arkusz },
      { naglowek: 'Miesiąc', wartosc: x => mies(x.miesiac) },
      { naglowek: 'Termin', wartosc: x => dataPl(x.termin_efektywny) },
      { id: 'kwota', naglowek: 'Brutto PLN', liczba: true, wartosc: x => zl(x.brutto * x.rodzaj, false), klasa: x => x.rodzaj === 1 ? 'plus' : 'minus' },
      { naglowek: 'Uwagi', wartosc: x => x.uwaga_stanu || x.decyzja, klasa: () => 'szary' },
    ];
    return `<h1>${esc(d.nazwa)}</h1><div class="okruszki">Płatności / Plan z budżetu, stan na ${dataPl(d.dzien_stanu)}</div>
      <div class="filtry">${filtr('lista', 'Lista', Object.entries(d.listy), d.lista)}
        ${filtr('rodzaj', 'Rodzaj', [['', 'Wszystko'], ['1', 'Wpływy'], ['-1', 'Obciążenia']], p.rodzaj)}</div>
      <p class="notka">Etap wynika z banku i Fakturowni, nie z kliknięcia: „Opłacona” dopiero, gdy jest wpłata albo przelew. ${d.razem} pozycji, saldo ${zl(d.suma)}.</p>
      ${tabela({ kolumny: kol, dane: d.wiersze, poczatek: (d.strona - 1) * d.ile + 1, onWiersz: x => kartaPlatnosci([x.id], null),
        stopkaSum: { rodzaj: `suma wszystkich ${d.razem} pozycji`, kwota: zl(d.suma, false) } })}
      ${stopka(d, p)}`;
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

  // ---------- Cash flow ----------
  async cashflow(p) {
    const d = await api('cashflow');
    if (d.brak_danych) return '<h1>Cash flow</h1><div class="pusto">Brak danych z banku.</div>';
    const dni = p.widok === 'dni';
    setTimeout(() => {
      if (dni) {
        Wykresy.linia($('#cf-wyk'), { punkty: d.dni.map(x => ({ x: x.data, y: x.ostrozny, pelny: x.pelny })), nazwa: 'Saldo, scenariusz ostrożny',
          kolor: Wykresy.kolor('--s1'), wysokosc: 260, opis: 'Saldo dzień po dniu', etykietaX: x => MIESIACE[+x.slice(5, 7) - 1].slice(0, 3),
          etykietaPelna: x => dataPl(x), dodatkowe: q => [{ nazwa: 'scenariusz pełny', wartosc: Wykresy.pelna(q.pelny), kolor: Wykresy.kolor('--s2') }] });
      } else {
        Wykresy.slupki($('#cf-wyk'), { kategorie: d.tygodnie.map(t => t.od.slice(8, 10) + '.' + t.od.slice(5, 7)),
          etykietyPelne: d.tygodnie.map(t => `${dataPl(t.od)} – ${dataPl(t.do)}`), wysokosc: 260, opis: 'Prognoza 13 tygodni',
          serie: [{ klucz: 'w', nazwa: 'Wpływy', kolor: Wykresy.kolor('--plus'), wartosci: d.tygodnie.map(t => t.wplywy) },
            { klucz: 'o', nazwa: 'Wydatki', kolor: Wykresy.kolor('--minus'), wartosci: d.tygodnie.map(t => t.wydatki) },
            { klucz: 'so', nazwa: 'Saldo ostrożne', typ: 'linia', kolor: Wykresy.kolor('--s1'), wartosci: d.tygodnie.map(t => t.saldo_ostrozny) },
            { klucz: 'sp', nazwa: 'Saldo pełne', typ: 'linia', przerywana: true, kolor: Wykresy.kolor('--s2'), wartosci: d.tygodnie.map(t => t.saldo_pelny) }] });
      }
      document.querySelectorAll('tr[data-t]').forEach(tr => tr.onclick = () => tr.nextElementSibling.classList.toggle('ukryty'));
      document.querySelectorAll('tr[data-pp]').forEach(tr => tr.onclick = e => { e.stopPropagation(); kartaPlatnosci([tr.dataset.pp], null); });
    });
    const tyg = d.tygodnie.map((t, i) => `<tr data-t="${i}" class="klikalny"><td>${dataPl(t.od)} – ${dataPl(t.do)}</td><td class="liczba-kol plus">${zl(t.wplywy, false)}</td>
      <td class="liczba-kol minus">${zl(t.wydatki, false)}</td><td class="liczba-kol szary">${t.tylko_pelny ? zl(t.tylko_pelny, false) : ''}</td>
      <td class="liczba-kol ${t.saldo_ostrozny < 0 ? 'minus' : ''}"><b>${zl(t.saldo_ostrozny, false)}</b></td><td class="liczba-kol szary">${zl(t.saldo_pelny, false)}</td></tr>
      <tr class="ukryty pozycje"><td colspan="6">${t.pozycje.map(x => `<div><span>${dataPl(x.data)}</span> <b class="${x.kwota < 0 ? 'minus' : 'plus'}">${zl(x.kwota)}</b> ${esc(x.opis)} <span class="szary">(${esc(x.rodzaj)}${x.scenariusz === 'pelny' ? ', tylko pełny' : ''})</span></div>`).join('') || '<span class="szary">brak pozycji</span>'}</td></tr>`).join('');
    return `<div class="naglowek-strony"><div><h1>Cash flow ${pytajnik('cashflow')}</h1><div class="okruszki">Prognoza od ${dataPl(d.dzien_stanu)} (ostatni dzień eksportu ING)</div></div>
        <a class="przycisk" href="/api/eksport/cashflow">Excel</a></div>
      <div class="kafle"><div class="kafel"><div class="tytul">Saldo startowe</div><div class="wartosc">${zl(d.saldo_start)}</div><div class="dop">rachunek główny i online</div></div>
        <div class="kafel"><div class="tytul">Najniższy punkt (ostrożny)</div><div class="wartosc ${d.minimum_ostrozny.saldo < 0 ? 'minus' : ''}">${zl(d.minimum_ostrozny.saldo)}</div><div class="dop">${dataPl(d.minimum_ostrozny.data)}</div></div>
        <div class="kafel"><div class="tytul">Za 13 tygodni</div><div class="wartosc">${zl(d.koniec.ostrozny)}</div><div class="dop">ostrożny; pełny ${zl(d.koniec.pelny)}</div></div>
        <div class="kafel"><div class="tytul">Plany po terminie</div><div class="wartosc ${d.po_terminie.length ? 'minus' : ''}">${d.po_terminie.length}</div><div class="dop">tylko w scenariuszu pełnym, do decyzji</div></div></div>
      <div class="filtry">${filtr('widok', 'Widok', [['', '13 tygodni'], ['dni', 'Dzień po dniu']], p.widok || '')}</div>
      <div class="karta-wyk"><h3>${dni ? 'Saldo dzień po dniu' : 'Wpływy, wydatki i saldo w tygodniach'}</h3><div class="pod">${dni ? 'linia: scenariusz ostrożny; w podpowiedzi także pełny' : 'linie: saldo na koniec tygodnia, ciągła ostrożny, przerywana pełny'}</div><div id="cf-wyk"></div></div>
      <div class="tabela-ramka niska"><table><thead><tr><th>Tydzień</th><th class="liczba-kol">Wpływy</th><th class="liczba-kol">Wydatki</th><th class="liczba-kol">Tylko pełny</th>
        <th class="liczba-kol">Saldo ostrożne</th><th class="liczba-kol">Saldo pełne</th></tr></thead><tbody>${tyg}</tbody></table></div>
      ${d.po_terminie.length ? `<h2 class="sekcja">Plany po terminie</h2><div class="tabela-ramka niska"><table><tbody>${d.po_terminie.map(x => `<tr data-pp="${esc(x.platnosc)}" class="klikalny"><td>${dataPl(x.termin)}</td><td>${esc(x.opis)}</td><td class="liczba-kol minus">${zl(x.kwota, false)}</td></tr>`).join('')}</tbody></table></div>` : ''}
      <p class="notka">Kliknij tydzień, żeby rozwinąć pozycje. Należności liczone w dniu terminu przesuniętym o średnie spóźnienie nabywcy.</p>`;
  },

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
      { naglowek: 'Plan przychód', liczba: true, wartosc: x => tys(x.plan_przychod) }, { naglowek: 'Wykonanie przychód', liczba: true, wartosc: x => tys(x.wyk_przychod) },
      { naglowek: 'Realizacja', liczba: true, wartosc: x => procent(x.realizacja_proc) },
      { naglowek: 'Plan koszt', liczba: true, wartosc: x => tys(-x.plan_koszt), klasa: () => 'minus' }, { naglowek: 'Wykonanie koszt', liczba: true, wartosc: x => tys(-x.wyk_koszt), klasa: () => 'minus' },
      { naglowek: 'Saldo planu', liczba: true, wartosc: x => tys(x.plan_saldo) },
      { naglowek: 'Po terminie', liczba: true, wartosc: x => x.po_terminie || '', klasa: x => x.po_terminie ? 'minus' : '' },
    ];
    return `<h1>Arkusze: plan i wykonanie</h1><div class="okruszki">Rentowność / budżet</div>
      <p class="notka">Plan: wszystkie aktualne pozycje arkusza (netto). Wykonanie: pozycje opłacone według banku (przychód przez fakturę, koszt przez przelew).</p>
      ${tabela({ kolumny: kol, dane: lista, poczatek: 1, onWiersz: x => { location.hash = `#/budzet/arkusz?id=${x.id}`; } })}`;
  },

  async eksport() {
    return `<h1>Eksport</h1><div class="okruszki">Excel, z danych na dziś</div>
      <div class="kafle"><a class="kafel klik" href="/api/eksport/cashflow"><div class="tytul">Cash flow</div><div class="wartosc">13 tygodni</div><div class="dop">tygodnie, pozycje, saldo dzienne</div></a>
        <a class="kafel klik" href="/api/eksport/rentownosc"><div class="tytul">Rentowność</div><div class="wartosc">klienci i arkusze</div><div class="dop">obrót, koszty, marża, plan i wykonanie</div></a>
        <a class="kafel klik" href="#/budzet/arkusze"><div class="tytul">Arkusz budżetu</div><div class="wartosc">wybierz arkusz</div><div class="dop">przycisk Excel w widoku arkusza</div></a></div>`;
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

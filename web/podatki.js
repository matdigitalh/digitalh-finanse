'use strict';
// Pakiet 8: ekran Podatki i ZUS (VAT, CIT, PIT-4, ZUS, rachunek VAT) i ustawienia podatkowe. Osobny plik: dopina się do
// menu, widoków i pomocy z app.js (PODSTRONY, WIDOKI, POMOC), nie zmienia ich wyglądu. Liczby w groszach z serwera.
// Całość w funkcji: żadna nazwa nie trafia do zakresu globalnego (app.js i budzet.js mają własne).
(() => {

(() => {
  const menu = [{ grupa: 'Podatki' }, { nazwa: 'Podatki i ZUS', hash: '#/budzet/podatki' },
    { nazwa: 'Ustawienia podatków', hash: '#/budzet/podatki-ustawienia' }];
  const b = PODSTRONY.budzet;
  const i = b.findIndex(p => p.grupa === 'Ustawienia');
  if (i >= 0) b.splice(i, 0, ...menu); else b.push(...menu);
})();

Object.assign(POMOC, {
  podatki: { tytul: 'Podatki i ZUS', krotko: 'VAT i zaliczki CIT liczone z budżetu, kwoty od biura, przelewy z banku i rachunek VAT.',
    co: 'Arkusz systemowy Opłaty urzędowe: plan VAT za każdy miesiąc i zaliczki CIT, jak w Budget Studio. Plany trafiają do cash flow. Obok kalendarz PIT-4 i ZUS z umów oraz prognoza salda rachunku VAT.',
    skad: 'Płatności budżetu z Księgowane = tak, wg miesiąca księgowania. VAT z faktur (należny minus naliczony), CIT od netto wpływów minus netto obciążeń. Kwoty od biura: wpis w apce albo opłacona danina z eksportu Budget Studio. Zapłacono: przelewy do urzędu skarbowego i ZUS z ING, okres z tytułu przelewu.',
    jak: 'Nadpłata VAT przechodzi na kolejne miesiące, a na końcu budżetu staje się zwrotem. Zaliczka CIT = podatek od podstawy narastająco minus zaliczki wcześniej w roku. Kwota od biura zamraża okres: dalej nic się w nim nie przelicza. Stawka i okres CIT, terminy i przenoszenie nadpłaty są w Ustawieniach podatków (do potwierdzenia z biurem).',
    zrob: 'Po deklaracji wpisz kwotę od biura (klik w okres). Gdy prognoza różni się od biura, najczęstsze przyczyny to: zła stawka VAT w wierszu, brak Księgowane, inny miesiąc księgowania niż u biura, przeterminowane plany kosztów, nadpłata sprzed startu budżetu, amortyzacja i różnice kursowe poza budżetem, prezes wpisany brutto jako Bez faktury (jego PIT nie jest składową umowy).' },
});

const zlPole = gr => gr == null ? '' : zl(gr, false);
const naGrosze = s => {
  const t = String(s || '').replace(/\s/g, '').replace(',', '.');
  if (!/^\d+(\.\d{1,2})?$/.test(t)) return null;
  const [c, g = ''] = t.split('.');
  return parseInt(c, 10) * 100 + parseInt((g + '00').slice(0, 2), 10);
};
const KIERUNEK = { zaplata: 'do zapłaty', przeniesienie: 'nadwyżka do przeniesienia', zwrot: 'zwrot' };
const NAZWA_DANINY = { vat: 'VAT', cit: 'Zaliczka CIT', vat_zwrot: 'Zwrot VAT', cit_roczny: 'CIT roczny' };

function chipPodatku(x) {
  const s = x.status || '';
  const klasa = s.startsWith('zapłacone') && s !== 'zapłacone, inna kwota' || s === 'zwrot otrzymany' ? 'plus'
    : s === 'po terminie' ? 'minus' : s === 'zapłacone, inna kwota' ? 'ostrzezenie' : s.startsWith('kwota od biura') || s.startsWith('od biura') ? 'akcent' : 'neutral';
  const brak = x.brak_kwoty_od_biura && s !== 'nic do zapłaty' ? ' <span class="chip ostrzezenie">wpisz kwotę od biura</span>' : '';
  return `<span class="chip ${klasa}">${esc(s)}</span>${brak}`;
}

function wierszOkresu(x, i, lista) {
  const biuro = x.od_biura ? `${zl(x.od_biura.kwota, false)}<div class="szary">${esc(KIERUNEK[x.od_biura.kierunek])}, ${esc(x.od_biura.zrodlo)}</div>` : '';
  const przen = x.przeniesienie ? `<div class="szary">w tym nadpłata z poprzedniego: ${zl(x.przeniesienie, false)}</div>` : '';
  return `<tr data-lista="${lista}" data-i="${i}" title="Kliknij, żeby wpisać kwotę od biura albo dzień realnej płatności">
    <td>${esc(x.nazwa)}</td><td class="liczba-kol">${zlPole(x.prognoza)}${przen}</td><td class="liczba-kol szary">${zlPole(x.prognoza_bs)}</td>
    <td class="liczba-kol">${biuro}</td><td class="liczba-kol">${x.plan ? zl(x.plan, false) : ''}</td>
    <td class="liczba-kol">${x.zaplacono ? zl(x.zaplacono, false) : ''}</td>
    <td class="liczba-kol ${x.roznica && Math.abs(x.roznica) > 100 ? 'minus' : ''}">${zlPole(x.roznica)}</td>
    <td>${dataPl(x.termin)}${x.realny && x.realny !== x.termin ? `<div class="szary">realnie ${dataPl(x.realny)}</div>` : ''}</td>
    <td>${chipPodatku(x)}</td></tr>`;
}

const NAGLOWEK_OKRESOW = '<tr><th>Okres</th><th class="liczba-kol">Prognoza z budżetu</th><th class="liczba-kol">Prognoza BS</th><th class="liczba-kol">Kwota od biura</th><th class="liczba-kol">W cash flow</th><th class="liczba-kol">Zapłacono (bank)</th><th class="liczba-kol">Różnica prognozy</th><th>Termin</th><th>Status</th></tr>';

function kartaDaniny(x, d) {
  const k = $('#karta');
  const vat = x.danina === 'vat';
  const roczny = x.danina === 'cit_roczny' || x.danina === 'vat_zwrot';
  const kierunki = { vat: ['zaplata', 'przeniesienie', 'zwrot'], cit: ['zaplata'], vat_zwrot: ['zwrot'], cit_roczny: ['zaplata', 'zwrot'] }[x.danina];
  const przelewy = (x.przelewy || []).map(o => `${dataPl(o.data)}: ${zl(o.kwota)} (${o.tytul})`).join('; ');
  const pola = [['Prognoza z budżetu', zlPole(x.prognoza)], ['Prognoza Budget Studio', zlPole(x.prognoza_bs)],
    ['Nadpłata z poprzedniego okresu', x.przeniesienie ? zl(x.przeniesienie) : ''], ['Podstawa narastająco', x.podstawa_narastajaco != null ? zl(x.podstawa_narastajaco) : ''],
    ['Kwota od biura', x.od_biura ? `${zl(x.od_biura.kwota)}, ${KIERUNEK[x.od_biura.kierunek]} (${x.od_biura.zrodlo})` : 'brak'],
    ['Zapłacono w banku', przelewy || 'brak przelewu'], ['Termin ustawowy', dataPl(x.termin_ustawowy)]];
  k.innerHTML = `<button class="zamknij" aria-label="Zamknij">×</button><h2>${esc(NAZWA_DANINY[x.danina])}: ${esc(x.nazwa)}</h2>
    <dl>${pola.filter(([, v]) => v).map(([n, v]) => `<dt>${esc(n)}</dt><dd>${esc(v)}</dd>`).join('')}</dl>
    <p class="szary">Kwota od biura zamraża okres: plan staje się płatnością rzeczywistą i dalej się nie przelicza${vat ? ', a nadwyżka do przeniesienia zmniejsza kolejny miesiąc' : ''}.</p>
    <div class="formularz">
      ${pole('', 'Kwota od biura (zł)', `<input id="dan-kwota" inputmode="decimal" value="${x.od_biura ? esc(zl(x.od_biura.kwota, false)) : ''}" placeholder="np. 6 312,00">`)}
      ${kierunki.length > 1 ? pole('', 'Kierunek', `<select id="dan-kier">${kierunki.map(v => `<option value="${v}"${(x.od_biura?.kierunek || kierunki[0]) === v ? ' selected' : ''}>${KIERUNEK[v]}</option>`).join('')}</select>`) : ''}
      ${pole('', 'Termin', `<input id="dan-termin" type="date" value="${esc(x.termin || '')}">`)}
      ${pole('', 'Dzień realnej płatności', `<input id="dan-realny" type="date" value="${esc(x.realny || '')}">`)}
      ${pole('', 'Komentarz', `<input id="dan-kom" maxlength="170" value="${esc(x.od_biura?.komentarz || '')}">`)}
    </div>
    <div class="akcje"><button class="glowny" id="dan-zapisz">Zapisz</button>
      ${!x.od_biura && (x.przelewy || []).length && !roczny ? `<button id="dan-bank">Przyjmij kwotę z banku (${esc(zl(x.zaplacono))})</button>` : ''}
      ${!x.od_biura && !(x.przelewy || []).length && x.termin && x.termin < d.dzien_stanu && !roczny ? '<button id="dan-zero">Biuro: 0 zł</button>' : ''}
      ${x.od_biura ? '<button id="dan-odmroz">Wróć do prognozy</button>' : ''}</div>
    <div class="zrodlo">Źródło: arkusz systemowy Opłaty urzędowe, wpisy „danina” w pliku zmian tego Maca.</div>`;
  k.hidden = false;
  $('.zamknij', k).onclick = () => { k.hidden = true; };
  const baza = { danina: x.danina, okres: x.okres };
  $('#dan-zapisz').onclick = () => {
    const dane = { ...baza };
    const tekst = $('#dan-kwota').value.trim();
    if (tekst) {
      const gr = naGrosze(tekst);
      if (gr == null) return komunikat('Kwota od biura: liczba w złotych, np. 6 312,00.', true);
      if (!x.od_biura || gr !== x.od_biura.kwota || ($('#dan-kier')?.value || kierunki[0]) !== x.od_biura.kierunek) {
        dane.kwota = gr;
        dane.kierunek = $('#dan-kier')?.value || kierunki[0];
      }
    }
    if ($('#dan-termin').value && $('#dan-termin').value !== x.termin) dane.termin = $('#dan-termin').value;
    if ($('#dan-realny').value && $('#dan-realny').value !== x.realny) dane.realny = $('#dan-realny').value;
    if ($('#dan-kom').value.trim() !== (x.od_biura?.komentarz || '')) dane.komentarz = $('#dan-kom').value.trim();
    if (Object.keys(dane).length === 2) { k.hidden = true; return; }
    zmiana('danina', dane);
  };
  const bank = $('#dan-bank');
  if (bank) bank.onclick = () => zmiana('danina', { ...baza, kwota: Math.abs(x.zaplacono), kierunek: x.zaplacono < 0 ? 'zwrot' : 'zaplata', komentarz: 'kwota z przelewu w banku' });
  const zero = $('#dan-zero');
  if (zero) zero.onclick = () => zmiana('danina', { ...baza, kwota: 0, kierunek: 'zaplata', komentarz: 'biuro: nic do zapłaty' });
  const odmroz = $('#dan-odmroz');
  if (odmroz) odmroz.onclick = () => zmiana('danina', { ...baza, usun: true });
}

Object.assign(WIDOKI, {
  async 'budzet/podatki'() {
    const d = await api('podatki');
    if (!d.horyzont) return '<h1>Podatki i ZUS</h1><div class="okruszki">Budżet / Opłaty urzędowe</div><div class="pusto">Brak arkuszy budżetu, więc nie ma z czego liczyć podatków.</div>';
    const u = d.ustawienia, rv = d.rachunek_vat || {}, nv = rv.vat_najblizszy;
    const rok = d.dzien_stanu.slice(0, 4);
    const citRok = d.cit.filter(x => x.rok === rok), roczny = d.cit_roczny.find(y => y.okres === rok);
    const doUzup = [...d.vat, ...d.cit].filter(x => x.brak_kwoty_od_biura && x.status !== 'nic do zapłaty').length;
    const listy = { vat: d.vat, cit: d.cit, rok: d.cit_roczny, zwrot: d.vat_zwrot ? [d.vat_zwrot] : [] };
    setTimeout(() => document.querySelectorAll('tr[data-lista]').forEach(tr => {
      tr.onclick = () => kartaDaniny(listy[tr.dataset.lista][tr.dataset.i], d);
    }));
    const rocznyHtml = d.cit_roczny.map((y, i) => `<tr data-lista="rok" data-i="${i}"><td>${esc(y.okres)}</td>
      <td class="liczba-kol">${zlPole(y.podatek_roku)}</td><td class="liczba-kol">${zl(y.zaliczki, false)}</td>
      <td class="liczba-kol">${y.prognoza == null ? '' : y.prognoza < 0 ? `zwrot ${zl(-y.prognoza, false)}` : y.prognoza > 0 ? `niedopłata ${zl(y.prognoza, false)}` : '0,00'}</td>
      <td class="liczba-kol szary">${zlPole(y.prognoza_bs)}</td><td class="liczba-kol">${y.od_biura ? zl(y.od_biura.kwota, false) : ''}</td>
      <td class="liczba-kol">${y.plan ? zl(y.plan, false) : ''}</td><td class="liczba-kol">${y.zaplacono ? zl(y.zaplacono, false) : ''}</td>
      <td>${dataPl(y.termin)}</td><td>${chipPodatku(y)}</td></tr>`).join('');
    const wyn = d.wynagrodzenia.map(x => `<tr><td>${esc(x.nazwa)}</td>
      <td class="liczba-kol">${x.pit4_plan ? zl(x.pit4_plan, false) : ''}</td><td class="liczba-kol">${x.pit4_zaplacono ? zl(x.pit4_zaplacono, false) : ''}</td><td>${dataPl(x.pit4_termin)}</td>
      <td class="liczba-kol">${x.zus_plan ? zl(x.zus_plan, false) : ''}</td><td class="liczba-kol">${x.zus_zaplacono ? zl(x.zus_zaplacono, false) : ''}</td><td>${dataPl(x.zus_termin)}</td></tr>`).join('');
    const zdarzenia = (rv.zdarzenia || []).map(z => `<tr><td>${dataPl(z.data)}</td><td>${esc(z.opis)}</td>
      <td class="liczba-kol ${z.kwota < 0 ? 'minus' : 'plus'}">${zl(z.kwota, false)}</td><td class="liczba-kol">${z.kwota < 0 ? zl(z.z_rachunku_vat, false) : ''}</td>
      <td class="liczba-kol ${z.z_glownego ? 'minus' : ''}">${z.z_glownego ? zl(z.z_glownego, false) : ''}</td><td class="liczba-kol">${zl(z.saldo, false)}</td></tr>`).join('');
    return `<h1>Podatki i ZUS ${pytajnik('podatki')}</h1><div class="okruszki">Budżet / Opłaty urzędowe (arkusz systemowy)</div>
      <p class="notka">Dzień stanu ${dataPl(d.dzien_stanu)}. VAT ${u.vat_okres === 'kwartal' ? 'kwartalnie' : 'miesięcznie'}, termin ${u.vat_dzien}.; CIT ${u.cit_okres === 'kwartal' ? 'kwartalnie' : 'miesięcznie'}, ${u.cit_stawka ? u.cit_stawka + '%' : 'bez prognozy'}, termin ${u.cit_dzien}.; PIT-4 do ${d.stale.pit4_dzien}., ZUS do ${d.stale.zus_dzien}.
        Budżet od ${esc(d.horyzont[0])} do ${esc(d.horyzont[1])}. <a href="#/budzet/podatki-ustawienia">Ustawienia podatków</a> (do potwierdzenia z biurem).
        ${d.zastapione_arkusze_bs.length ? `Arkusze z Budget Studio zastąpione arkuszem systemowym: ${esc(d.zastapione_arkusze_bs.join(', '))}.` : ''}</p>
      <div class="kafle">
        <div class="kafel"><div class="tytul">Najbliższy VAT</div><div class="wartosc">${nv ? zl(-nv.kwota) : 'brak'}</div>
          <div class="dop">${nv ? `${dataPl(nv.data)}; z rachunku VAT ${zl(-nv.z_rachunku_vat)}, z głównego ${zl(-nv.z_glownego)}` : 'w najbliższych 13 tygodniach'}</div></div>
        <div class="kafel"><div class="tytul">Rachunek VAT</div><div class="wartosc">${zl(rv.saldo_start || 0)}</div>
          <div class="dop">za 13 tygodni ${zl(rv.saldo_koniec || 0)}; MPP to ${String(rv.udzial_mpp ?? 0).replace('.', ',')}% VAT ze sprzedaży</div></div>
        <div class="kafel"><div class="tytul">CIT ${rok}</div><div class="wartosc">${zl(citRok.reduce((a, x) => a + x.plan, 0))}</div>
          <div class="dop">zaliczki w roku; po roku ${roczny ? (roczny.plan < 0 ? `zwrot ${zl(-roczny.plan)}` : roczny.niedoplata ? `niedopłata ${zl(roczny.niedoplata)} (bez planu)` : 'bez zwrotu') : ''}</div></div>
        <div class="kafel"><div class="tytul">Do uzupełnienia</div><div class="wartosc ${doUzup ? 'minus' : ''}">${doUzup}</div>
          <div class="dop">okresy po terminie bez kwoty od biura; zgodność prognozy z przelewami: ${d.kontrola.zgodnych} z ${d.kontrola.okresow}</div></div>
      </div>
      <h2 class="sekcja">VAT</h2>
      <div class="tabela-ramka niska"><table><thead>${NAGLOWEK_OKRESOW}</thead><tbody>${d.vat.map((x, i) => wierszOkresu(x, i, 'vat')).join('')}
        ${d.vat_zwrot ? wierszOkresu({ ...d.vat_zwrot, nazwa: `Zwrot: ${d.vat_zwrot.nazwa}` }, 0, 'zwrot') : ''}</tbody></table></div>
      <h2 class="sekcja">Zaliczki CIT</h2>
      <div class="tabela-ramka niska"><table><thead>${NAGLOWEK_OKRESOW}</thead><tbody>${d.cit.map((x, i) => wierszOkresu(x, i, 'cit')).join('')}</tbody></table></div>
      <div class="tabela-ramka niska"><table><thead><tr><th>Rok</th><th class="liczba-kol">Podatek roczny (prognoza)</th><th class="liczba-kol">Zaliczki</th><th class="liczba-kol">Po roku</th><th class="liczba-kol">Prognoza BS</th><th class="liczba-kol">Kwota od biura</th><th class="liczba-kol">W cash flow</th><th class="liczba-kol">Bank</th><th>Termin</th><th>Status</th></tr></thead><tbody>${rocznyHtml}</tbody></table></div>
      <h2 class="sekcja">PIT-4 i ZUS z umów</h2>
      <p class="notka">Składowe umów z budżetu wg miesiąca wypłaty, obok przelewy z ING. Prezes na powołaniu jest w budżecie jako Bez faktury, więc jego PIT jest tylko w przelewie.</p>
      <div class="tabela-ramka niska"><table><thead><tr><th>Miesiąc wypłaty</th><th class="liczba-kol">PIT-4 plan</th><th class="liczba-kol">PIT-4 zapłacono</th><th>Termin</th><th class="liczba-kol">ZUS plan</th><th class="liczba-kol">ZUS zapłacono</th><th>Termin</th></tr></thead><tbody>${wyn}</tbody></table></div>
      <h2 class="sekcja">Rachunek VAT: 13 tygodni</h2>
      <p class="notka">Start: saldo rachunku VAT z ING. Wpływy: VAT z wpłat podzieloną płatnością (należności i plany; wiersz z Split payment to cały VAT, inaczej udział MPP klienta z historii wpłat). Wypływy: ${u.rachunek_vat_na === 'wszystkie' ? 'VAT, CIT, PIT-4 i ZUS' : 'VAT'} najpierw z rachunku VAT, resztę dokłada rachunek główny. Gotówka w cash flow jest bez rachunku VAT.</p>
      ${zdarzenia ? `<div class="tabela-ramka niska"><table><thead><tr><th>Data</th><th>Co</th><th class="liczba-kol">Kwota</th><th class="liczba-kol">Z rachunku VAT</th><th class="liczba-kol">Z głównego</th><th class="liczba-kol">Saldo rachunku VAT</th></tr></thead><tbody>${zdarzenia}</tbody></table></div>` : '<div class="pusto">Brak ruchów na rachunku VAT w najbliższych 13 tygodniach.</div>'}`;
  },

  async 'budzet/podatki-ustawienia'() {
    const d = await api('podatki');
    const u = d.ustawienia;
    const wybor = (id, opcje, v) => `<select id="${id}">${opcje.map(([w, n]) => `<option value="${w}"${String(v) === String(w) ? ' selected' : ''}>${n}</option>`).join('')}</select>`;
    setTimeout(() => {
      $('#ust-zapisz').onclick = () => {
        const nowe = {
          vat_okres: $('#u-vat-okres').value, vat_dzien: parseInt($('#u-vat-dzien').value, 10), vat_przenoszenie: $('#u-przen').value,
          vat_saldo_startowe: naGrosze($('#u-saldo').value || '0'), zwrot_termin: $('#u-zwrot').value.trim(),
          cit_okres: $('#u-cit-okres').value, cit_stawka: $('#u-stawka').value ? parseInt($('#u-stawka').value, 10) : null,
          cit_dzien: parseInt($('#u-cit-dzien').value, 10), cit_zaokraglenie: $('#u-zaokr').value, rachunek_vat_na: $('#u-rach').value,
        };
        if (nowe.vat_saldo_startowe == null) return komunikat('Nadwyżka VAT na start: kwota w złotych, np. 1 250,00.', true);
        const zmienione = Object.fromEntries(Object.entries(nowe).filter(([k, v]) => v !== u[k]));
        if (!Object.keys(zmienione).length) return komunikat('Bez zmian.');
        zmiana('ustawienie', { klucz: 'podatki', wartosc: zmienione });
      };
    });
    const dzien = (id, v) => `<input id="${id}" inputmode="numeric" value="${esc(v)}">`;
    return `<h1>Ustawienia podatków ${pytajnik('podatki')}</h1><div class="okruszki">Budżet / Ustawienia / Podatki i daniny</div>
      <p class="notka">Wartości startowe są jak w Budget Studio DigitalH. Każde ustawienie oznaczone gwiazdką jest do potwierdzenia z biurem. Zmiana przelicza arkusz systemowy Opłaty urzędowe i cash flow; okresy z kwotą od biura zostają bez zmian.</p>
      <div class="karta-wyk"><h3>Firma</h3>
        <p class="notka">Forma prawna: ${esc(d.stale.forma)}. VAT: ${esc(d.stale.vat)}. Podatek dochodowy: CIT. PIT-4 do ${d.stale.pit4_dzien}. i ZUS do ${d.stale.zus_dzien}. dnia miesiąca po wypłacie (terminy ustawowe sp. z o.o., z umów w budżecie).</p></div>
      <div class="karta-wyk"><h3>VAT</h3><div class="formularz">
        ${pole('', 'Okres rozliczenia VAT', wybor('u-vat-okres', [['miesiac', 'miesiąc'], ['kwartal', 'kwartał']], u.vat_okres))}
        ${pole('', 'Termin VAT: dzień miesiąca po okresie *', dzien('u-vat-dzien', u.vat_dzien))}
        ${pole('', 'Nadpłata VAT *', wybor('u-przen', [['tak', 'przechodzi na kolejne okresy (jak w BS)'], ['nie', 'zwrot za każdy okres, 60 dni po terminie']], u.vat_przenoszenie))}
        ${pole('', 'Nadwyżka VAT na start budżetu (zł) *', `<input id="u-saldo" inputmode="decimal" value="${esc(zl(u.vat_saldo_startowe, false))}">`)}
        ${pole('', 'Termin zwrotu nadpłaty w roku następnym, MM-DD (VAT na końcu budżetu, CIT po roku) *', `<input id="u-zwrot" value="${esc(u.zwrot_termin)}">`)}
      </div></div>
      <div class="karta-wyk"><h3>Podatek dochodowy (CIT)</h3><div class="formularz">
        ${pole('', 'Okres zaliczek CIT *', wybor('u-cit-okres', [['kwartal', 'kwartał (jak w BS)'], ['miesiac', 'miesiąc']], u.cit_okres))}
        ${pole('', 'Stawka CIT do prognozy *', wybor('u-stawka', [['19', '19%'], ['9', '9% (mały podatnik)'], ['', 'bez prognozy CIT']], u.cit_stawka ?? ''))}
        ${pole('', 'Termin zaliczki: dzień miesiąca po okresie *', dzien('u-cit-dzien', u.cit_dzien))}
        ${pole('', 'Zaokrąglenie zaliczki *', wybor('u-zaokr', [['grosze', 'do grosza (jak w BS)'], ['zl', 'do pełnych złotych']], u.cit_zaokraglenie))}
      </div></div>
      <div class="karta-wyk"><h3>Rachunek VAT</h3><div class="formularz">
        ${pole('', 'Z rachunku VAT płacimy najpierw', wybor('u-rach', [['wszystkie', 'VAT, CIT, PIT-4 i ZUS (tak jest w wyciągach ING)'], ['vat', 'tylko VAT']], u.rachunek_vat_na))}
      </div></div>
      <div class="akcje"><button class="glowny" id="ust-zapisz">Zapisz ustawienia</button></div>`;
  },
});
})();

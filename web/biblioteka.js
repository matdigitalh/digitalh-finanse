'use strict';
// Biblioteka budżetu (pakiet 4, A-KON-01 do 12, A-BUD-05 do 11): kontrahenci, przedmioty transakcji, sekcje, metody
// płatności, foldery i kategorie, arkusze. Każda zmiana to wpis „bud” (op „slownik” albo „struktura”); reguły, blokady
// i przepinanie wystąpień liczy serwer (finanse/biblioteka.py), tu tylko podgląd i komunikat z wyprzedzeniem.
// Korzysta z app.js (api, zmiana, tabela, stopka, komunikat, pole, ik) i budzet.js (regulaZ, regulaNa, PODSTAWY).

const ZAKLADKI_BIB = [
  ['kontrahenci', 'Kontrahenci', 'osoby', 'kontrahent'], ['przedmioty', 'Przedmioty transakcji', 'dokument', 'przedmiot'],
  ['sekcje', 'Sekcje', 'warstwy', 'sekcja'], ['metody', 'Metody płatności', 'przelew', 'metoda'],
  ['struktura', 'Foldery i kategorie', 'folder', null], ['arkusze', 'Arkusze budżetu', 'arkusz', null]];
const DODAJ_BIB = { kontrahent: 'Dodaj kontrahenta', przedmiot: 'Dodaj przedmiot transakcji', sekcja: 'Dodaj sekcję', metoda: 'Dodaj metodę płatności' };
const NAZWA_BIB = { kontrahent: 'Kontrahent', przedmiot: 'Przedmiot transakcji', sekcja: 'Sekcja', metoda: 'Metoda płatności' };
const RACHUNEK_OPIS = { '': 'nie wskazano', 'główny': 'ING, rachunek główny', online: 'ING, rachunek online', VAT: 'ING, rachunek VAT', karta: 'karta firmowa' };
const odmWyst = n => `${n} ${n === 1 ? 'wystąpienie' : [2, 3, 4].includes(n % 10) && ![12, 13, 14].includes(n % 100) ? 'wystąpienia' : 'wystąpień'}`;
const odmArk = n => `${n} ${n === 1 ? 'arkusz' : [2, 3, 4].includes(n % 10) && ![12, 13, 14].includes(n % 100) ? 'arkusze' : 'arkuszy'}`;
const bibUrl = (zakl, p = {}) => `#/budzet/biblioteka?${new URLSearchParams({ zakladka: zakl, ...p })}`;
const dzienBib = t => { if (!t) return ''; const r = regulaZ(t);
  return (r.typ === 'ostatni' ? 'ostatni dzień' : r.typ === 'pierwszy' ? '1. dzień' : `${r.dzien}. dzień`)
    + (r.przes ? `, ${r.przes > 0 ? '+' : ''}${r.przes} mies.` : '') + (r.przes && r.b ? ', księg. wg budżetu' : ''); };
Object.assign(IK, { wyzej: '<path d="M12 19V5M6 11l6-6 6 6"/>', nizej: '<path d="M12 5v14M6 13l6 6 6-6"/>',
  olowek: '<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="m13.5 6.5 4 4"/>', kosz: '<path d="M5 7h14M10 7V4h4v3M7 7l1 13h8l1-13"/>' });
let BIB = null;   // dane ekranu (do kart i paska akcji)
let BIB_FOKUS = false;   // wyszukiwarka w stopce zachowuje fokus po przerysowaniu listy
const BIB_ZAZN = { kontrahent: new Set(), przedmiot: new Set(), sekcja: new Set(), metoda: new Set() };

Object.assign(POMOC, {
  biblioteka: { tytul: 'Biblioteka', krotko: 'Słowniki budżetu (kontrahenci, przedmioty, sekcje, metody płatności) oraz foldery i kategorie.',
    co: 'Jedno miejsce na nazwy używane w arkuszach. Kontrahent ma też ustawienia domyślne: podstawę, VAT, dzień wystawienia, dni na płatność, metodę i przełączniki, które wypełniają nowy wiersz, gdy zaczniesz go od wyboru tego kontrahenta.',
    skad: 'Na start z danych (kopia z Budget Studio albo import): każda nazwa z wierszy i płatności, foldery i kategorie z arkuszy. Nazwa wpisana w arkuszu trafia tu sama. Pełna nazwa i NIP mogą podpowiadać się z Fakturowni.',
    jak: 'Zmiana nazwy i połączenie przepinają wszystkie wiersze i płatności jedną zmianą (Cmd+Z albo Historia zmian cofa całość). Usunąć można tylko pozycję bez wystąpień; folder i kategorię tylko puste albo z przeniesieniem arkuszy.',
    zrob: 'Połącz duplikaty (np. „PayU” i „PayU PL”), ustaw ustawienia domyślne stałych kontrahentów i jednego kontrahenta domyślnego dla nowych wierszy.' },
});
if (typeof OPISY_OP === 'object') Object.assign(OPISY_OP, { slownik: 'zmiana w Bibliotece', struktura: 'foldery i kategorie' });
if (typeof NAZWY_OP === 'object') Object.assign(NAZWY_OP, { slownik: 'Biblioteka', struktura: 'foldery i kategorie' });

Object.assign(WIDOKI, {
  async 'budzet/biblioteka'(p) {
    const d = await api('budzet/biblioteka');
    BIB = d;
    const zakl = ZAKLADKI_BIB.find(z => z[0] === p.zakladka) || ZAKLADKI_BIB[0];
    const rodzaj = zakl[3];
    const zakladki = `<div class="zakladki" role="tablist">${ZAKLADKI_BIB.map(([id, nazwa, ikona]) =>
      `<a role="tab" href="${bibUrl(id)}" aria-selected="${id === zakl[0]}">${ik(ikona)}${nazwa}</a>`).join('')}</div>`;
    const przycisk = rodzaj && d.planowanie ? `<button class="przycisk glowny" id="bib-dodaj" data-karta>${DODAJ_BIB[rodzaj]} ${ik('plus')}</button>` : '';
    const tresc = rodzaj ? widokSlownika(d, rodzaj, p) : zakl[0] === 'struktura' ? widokStruktury(d, p) : widokArkuszyBib(d, p);
    setTimeout(() => { const b = $('#bib-dodaj'); if (b) b.onclick = e => { e.stopPropagation(); kartaSlownika(rodzaj, null); }; });
    return `<div class="naglowek-strony"><div><h1>Biblioteka ${pytajnik('biblioteka')}</h1><div class="okruszki">Budżet / Biblioteka / ${zakl[1]}</div></div>${przycisk}</div>
      ${d.planowanie ? '' : `<p class="notka">${esc(TEKST_PODGLADU)} Do tego czasu Biblioteka jest do odczytu.</p>`}${zakladki}${tresc}`;
  },
});

// ---------- Słowniki: lista z licznikiem, sortowaniem, wyszukiwarką, stronami i zaznaczaniem (A-KON-02, 09 do 11) ----------
function kolumnySlownika(r) {
  const nazwa = { id: 'nazwa', naglowek: r === 'kontrahent' ? 'Skrócona nazwa' : 'Nazwa', sort: 'nazwa', html: x => `${x.systemowy ? `<span class="szary">${esc(x.etykieta)}</span>` : esc(x.nazwa)}${x.systemowy ? ' <span class="chip neutral">systemowy</span>' : ''}${x.arkusz_systemowy ? ' <span class="chip neutral" title="Używa go arkusz systemowy Opłaty urzędowe (podatki)">podatki</span>' : ''}` };
  const dom = { id: 'domyslny', naglowek: 'Domyślny', sort: 'domyslny', html: x => x.domyslny ? `<span class="chip akcent" title="Wstawiany do każdego nowego wiersza">${ik('ptaszek')}domyślny</span>` : '' };
  const liczby = [{ id: 'wiersze', naglowek: 'Wiersze', liczba: true, sort: 'wiersze', wartosc: x => x.wiersze }, { id: 'platnosci', naglowek: 'Płatności', liczba: true, sort: 'platnosci', wartosc: x => x.platnosci },
    { id: 'uzyc', naglowek: r === 'kontrahent' ? 'Wystąpienia' : 'Liczba', liczba: true, sort: 'uzyc', html: x => x.uzyc ? `<b>${x.uzyc}</b>` : '<span class="chip plus">0</span>' }];
  if (r === 'kontrahent') {
    const u = (x, k, f) => { const v = x.ustawienia?.[k]; return v == null || v === '' ? '' : f ? f(v, x.ustawienia) : esc(v); };
    return [nazwa, { id: 'pelna', naglowek: 'Pełna nazwa', sort: 'pelna', html: x => x.pelna && x.pelna !== x.nazwa ? esc(x.pelna) : x.podpowiedz ? `<span class="szary" title="Podpowiedź z Fakturowni, zapisz w karcie">${esc(x.podpowiedz.pelna)}</span>` : esc(x.pelna || '') }, dom,
      { id: 'nip', naglowek: 'NIP', sort: 'nip', html: x => x.nip ? esc(x.nip) : x.podpowiedz ? `<span class="szary" title="Podpowiedź z Fakturowni (nabywca ${esc(x.podpowiedz.pelna)}). Zapisz w karcie kontrahenta.">${esc(x.podpowiedz.nip)} ?</span>` : '' },
      { id: 'podstawa', naglowek: 'Podstawa', html: x => u(x, 'podstawa') }, { id: 'vat', naglowek: 'VAT', html: x => u(x, 'stawka_vat', v => `${v} %`) },
      { id: 'dzien', naglowek: 'Dzień wystaw.', html: x => u(x, 'dzien_wystawienia', v => esc(dzienBib(v))) },
      { id: 'dni', naglowek: 'Dni', liczba: true, html: x => u(x, 'dni_na_platnosc', v => +v === 0 ? 'Natychmiast' : String(v)) },
      { id: 'metoda', naglowek: 'Metoda', html: x => u(x, 'metoda') }, { id: 'rodzaj', naglowek: 'Rodzaj', html: x => x.ustawienia ? chipZnak(x.ustawienia.rodzaj ?? -1) : '' },
      { id: 'split', naglowek: 'Split', html: x => x.ustawienia ? suwak(!!x.ustawienia.split) : '' }, { id: 'ksieg', naglowek: 'Księg.', html: x => x.ustawienia ? suwak(x.ustawienia.ksiegowane !== false) : '' },
      { id: 'wcf', naglowek: 'W CF', html: x => x.ustawienia ? suwak(x.ustawienia.w_cashflow !== false) : '' }, ...liczby];
  }
  if (r === 'przedmiot') return [nazwa, dom, ...liczby];
  if (r === 'metoda') return [nazwa, { id: 'rachunek', naglowek: 'Rachunek', sort: 'rachunek', html: x => x.rachunek ? esc(RACHUNEK_OPIS[x.rachunek] || x.rachunek) : '' },
    { id: 'bank', naglowek: 'Bank', sort: 'bank', html: x => esc(x.bank || '') }, ...liczby];
  return [nazwa, ...liczby];
}

function widokSlownika(d, r, p) {
  const q = (p.q || '').trim().toLowerCase();
  let lista = d[r].filter(x => !q || [x.etykieta, x.pelna, x.nip, x.podpowiedz?.nip, x.bank].some(v => String(v || '').toLowerCase().includes(q)));
  const sortuj = p.sortuj || '', kier = p.kolejnosc === 'malejaco' ? -1 : 1;
  if (sortuj) {
    const k = x => sortuj === 'nazwa' ? x.etykieta : sortuj === 'domyslny' ? (x.domyslny ? 0 : 1) : x[sortuj] ?? '';
    lista = [...lista].sort((a, b) => { const x = k(a), y = k(b); return kier * (typeof x === 'number' && typeof y === 'number' ? x - y : String(x).localeCompare(String(y), 'pl')); });
  }
  const ile = [50, 100, 200, 500].includes(+p.ile) ? +p.ile : 100, razem = lista.length;
  const strona = Math.min(Math.max(1, +p.strona || 1), Math.max(1, Math.ceil(razem / ile)));
  const dane = lista.slice((strona - 1) * ile, strona * ile);
  const zazn = BIB_ZAZN[r];
  [...zazn].forEach(n => { if (!d[r].some(x => x.nazwa === n)) zazn.delete(n); });
  setTimeout(() => pasekBib(r));
  const nieuzywane = d[r].filter(x => !x.uzyc && !x.systemowy).length;
  return `<p class="notka">${d[r].length} pozycji, nieużywanych ${nieuzywane}. Kliknij wiersz, żeby zmienić nazwę, ustawienia albo połączyć duplikaty.
      ${r === 'kontrahent' ? 'Szary NIP ze znakiem zapytania to podpowiedź z Fakturowni.' : ''} Usunąć można tylko pozycję z licznikiem 0.</p>
    ${tabela({ kolumny: kolumnySlownika(r), dane, poczatek: (strona - 1) * ile + 1, sortuj, kierunek: p.kolejnosc === 'malejaco' ? 'malejaco' : 'rosnaco',
    wierszKlasa: x => x.systemowy ? 'wiersz-plan' : '', onWiersz: x => kartaSlownika(r, x),
    zaznacz: d.planowanie ? { czy: x => zazn.has(x.nazwa), ustaw: (x, tak) => { if (tak) zazn.add(x.nazwa); else zazn.delete(x.nazwa); }, poZmianie: () => pasekBib(r) } : null })}
    <div class="ark-akcje" id="bib-akcje" hidden></div>${stopka({ strona, ile, razem }, p)}${fokusSzukaj()}`;
}

function fokusSzukaj() {
  setTimeout(() => {
    const s = $('#szukaj');
    if (!s) return;
    s.placeholder = 'Wyszukaj (nazwa, NIP)';
    s.addEventListener('input', () => { BIB_FOKUS = true; });
    s.addEventListener('blur', () => setTimeout(() => { if (document.contains(s)) BIB_FOKUS = false; }));
    if (BIB_FOKUS) { s.focus(); s.setSelectionRange(s.value.length, s.value.length); }
  });
  return '';
}

// Pasek akcji zaznaczonych (A-KON-07): Usuń tylko pozycje bez wystąpień; Połącz przy co najmniej dwóch.
function pasekBib(r) {
  const el = $('#bib-akcje');
  if (!el) return;
  const xs = BIB[r].filter(x => BIB_ZAZN[r].has(x.nazwa));
  el.hidden = !xs.length;
  if (!xs.length) return;
  const zly = xs.find(x => x.systemowy || x.domyslny || x.uzyc || x.arkusz_systemowy);
  const powod = !zly ? '' : zly.systemowy ? `„${zly.etykieta}” to wpis systemowy.` : zly.domyslny ? `„${zly.etykieta}” jest domyślny dla nowych wierszy.`
    : zly.uzyc ? `„${zly.etykieta}” ma ${odmWyst(zly.uzyc)}. Usunąć można tylko pozycje z licznikiem 0; tę połącz z innym wpisem.` : `„${zly.etykieta}” używa arkusz systemowy Opłaty urzędowe.`;
  el.innerHTML = `<span>Zaznaczono: <b>${xs.length}</b> · wystąpień razem: ${xs.reduce((s, x) => s + x.uzyc, 0)}</span>
    <div class="przyciski"><button id="bib-polacz" data-karta${xs.length < 2 ? ' disabled title="Zaznacz co najmniej dwie pozycje"' : ''}>${ik('link')}Połącz zaznaczone</button>
      <button id="bib-usun" data-karta${zly ? ` disabled title="${esc(powod)}"` : ''}>${ik('zamknij')}Usuń</button>
      <button id="bib-odznacz">Odznacz</button></div>`;
  $('#bib-usun').onclick = e => { e.stopPropagation(); kartaUsunieciaBib(r, xs); };
  $('#bib-polacz').onclick = e => { e.stopPropagation(); kartaPolaczenia(r, xs[0], xs.slice(1)); };
  $('#bib-odznacz').onclick = () => { BIB_ZAZN[r].clear(); pokaz(); };
}

function kartaUsunieciaBib(r, xs) {
  kartaFormularza(xs.length === 1 ? `Usuń: ${esc(xs[0].etykieta)}` : `Usuń ${xs.length} pozycji`,
    `<p>${xs.length === 1 ? 'Pozycja zniknie' : 'Pozycje znikną'} z Biblioteki (${esc(NAZWA_BIB[r].toLowerCase())}). Nie mają wystąpień, więc w arkuszach nic się nie zmieni.
      Cofniesz to w Historii zmian.</p><ul class="lista">${xs.slice(0, 30).map(x => `<li>${esc(x.etykieta)}</li>`).join('')}${xs.length > 30 ? `<li>i ${xs.length - 30} innych</li>` : ''}</ul>`,
    'Tak, usuń', async () => { if (await zmiana('bud', { op: 'slownik', akcja: 'usun', rodzaj: r, nazwy: xs.map(x => x.nazwa) })) BIB_ZAZN[r].clear(); });
}

// ---------- Karta pozycji: dodanie i edycja (A-KON-04, 09 do 11) ----------
function poleUstawien(u) {
  const reg = regulaZ(u?.dzien_wystawienia || 'Ostatni');
  const metody = BIB.metoda.filter(x => x.nazwa).map(x => x.nazwa);
  const opcje = (lista, v, pusta) => (pusta != null ? `<option value="">${esc(pusta)}</option>` : '') + lista.map(([w, e]) => `<option value="${esc(w)}"${String(w) === String(v ?? '') ? ' selected' : ''}>${esc(e)}</option>`).join('');
  const prz = (id, et, wl) => `<label class="przelacznik"><input type="checkbox" id="${id}"${wl ? ' checked' : ''}><span class="suwak"></span>${et}</label>`;
  return `<div class="bib-ust">
    ${pole('', 'Rodzaj', `<select id="u-rodzaj">${opcje([[-1, 'obciążenia (koszt)'], [1, 'wpływy (przychód)']], u?.rodzaj ?? -1)}</select>`)}
    ${pole('', 'Podstawa płatności', `<select id="u-podstawa">${opcje(BIB.podstawy.map(x => [x, x]), u?.podstawa || 'Faktura (jedna)')}</select>`)}
    ${pole('', 'Stawka VAT', `<select id="u-vat">${opcje(STAWKI.map(x => [x, `${x} %`]), u?.stawka_vat ?? 23)}</select>`)}
    ${pole('', 'Dni na płatność (0 = natychmiast)', `<input id="u-dni" type="number" min="0" max="99" value="${esc(u?.dni_na_platnosc ?? 14)}">`)}
    ${pole('', 'Dzień wystawienia', `<select id="u-typ">${opcje([['ostatni', 'ostatni dzień miesiąca'], ['pierwszy', 'pierwszy dzień miesiąca'], ['dzien', 'wybrany dzień']], reg.typ)}</select>`)}
    ${pole('', 'Który dzień (1 do 31)', `<input id="u-dzien" inputmode="numeric" value="${reg.dzien}">`)}
    ${pole('', 'Miesiąc wystawienia', `<select id="u-przes">${opcje([...Array(25)].map((_, i) => i - 12).map(n => [n, n === 0 ? 'ten sam miesiąc' : n > 0 ? `${n} mies. później` : `${-n} mies. wcześniej`]), reg.przes)}</select>`)}
    ${pole('', 'Miesiąc księgowania', `<select id="u-ksieg">${opcje([['', 'wg daty wystawienia'], ['B', 'wg miesiąca budżetu']], reg.b ? 'B' : '')}</select>`)}
    ${pole('', 'Metoda płatności', `<select id="u-metoda">${opcje(metody.map(x => [x, x]), u?.metoda || '', 'bez metody')}</select>`)}
    ${pole('', 'Przedmiot transakcji', `<select id="u-przedmiot">${opcje(BIB.przedmiot.filter(x => x.nazwa).map(x => [x.nazwa, x.nazwa]), u?.przedmiot || '', 'przedmiot domyślny')}</select>`)}
    ${pole('', 'Sekcja', `<select id="u-sekcja">${opcje(BIB.sekcja.filter(x => x.nazwa).map(x => [x.nazwa, x.nazwa]), u?.sekcja || '', '-')}</select>`)}
    <div class="bib-przel">${prz('u-split', 'Split payment', !!u?.split)}${prz('u-ksiegowane', 'Księgowane', u?.ksiegowane !== false)}${prz('u-wcf', 'W cash flow', u?.w_cashflow !== false)}</div></div>`;
}

function zbierzUstawienia(k) {
  const v = s => $(s, k).value;
  const typ = v('#u-typ'), przes = +v('#u-przes'), dz = +v('#u-dzien'), pod = v('#u-podstawa');
  if (typ === 'dzien' && !(dz >= 1 && dz <= 31)) throw new Error('Dzień wystawienia: od 1 do 31.');
  const dni = v('#u-dni').trim() === '' ? 0 : +v('#u-dni');
  if (!Number.isInteger(dni) || dni < 0 || dni > 99) throw new Error('Dni na płatność: liczba od 0 do 99.');
  const u = { rodzaj: +v('#u-rodzaj'), podstawa: pod, stawka_vat: jestFaktura({ podstawa: pod }) ? +v('#u-vat') : null, dni_na_platnosc: dni,
    metoda: v('#u-metoda'), przedmiot: v('#u-przedmiot'), sekcja: v('#u-sekcja'), split: $('#u-split', k).checked,
    ksiegowane: $('#u-ksiegowane', k).checked, w_cashflow: $('#u-wcf', k).checked };
  if (!WOREK.includes(pod)) u.dzien_wystawienia = regulaNa({ typ, dzien: dz, przes, b: v('#u-ksieg') === 'B' && !!przes && typ !== 'ostatni' && !(typ === 'dzien' && dz > 15) });
  return u;
}

// Te same ustawienia (brak pola = wartość domyślna), żeby zapis karty bez zmian nie tworzył wpisu.
function rowneUstawienia(a, b) {
  if (!b) return false;
  const dom = { split: false, ksiegowane: true, w_cashflow: true, stawka_vat: null };
  return [...new Set([...Object.keys(a), ...Object.keys(b)])].every(k => {
    const x = a[k] ?? dom[k] ?? '', y = b[k] ?? dom[k] ?? '';
    return k === 'dzien_wystawienia' && (!a[k] || !b[k]) ? true : String(x) === String(y);
  });
}

function podepnijUstawienia(k) {
  const odswiez = () => {
    const pod = $('#u-podstawa', k).value, typ = $('#u-typ', k).value, przes = +$('#u-przes', k).value, dz = +$('#u-dzien', k).value;
    $('#u-vat', k).disabled = !jestFaktura({ podstawa: pod });
    const worek = WOREK.includes(pod);
    ['#u-typ', '#u-przes'].forEach(s => { $(s, k).disabled = worek; });
    $('#u-dzien', k).disabled = worek || typ !== 'dzien';
    $('#u-ksieg', k).disabled = worek || !przes || typ === 'ostatni' || (typ === 'dzien' && dz > 15);
  };
  k.querySelector('.bib-ust').addEventListener('change', odswiez);
  k.querySelector('.bib-ust').addEventListener('input', odswiez);
  odswiez();
}

function kartaSlownika(r, x) {
  const nowy = !x, sys = !!x?.systemowy, edycja = BIB.planowanie;
  const wyl = edycja ? '' : ' disabled';
  const nazwaPola = sys ? `<input id="b-nazwa" value="${esc(x.etykieta)}" disabled title="Wpis systemowy: nazwy nie zmienisz">`
    : `<input id="b-nazwa" maxlength="${r === 'metoda' ? 60 : r === 'sekcja' ? 100 : 200}" value="${esc(x?.nazwa || '')}"${wyl}>`;
  const podp = x?.podpowiedz;
  let pola = pole('', r === 'kontrahent' ? 'Nazwa skrócona (w arkuszach i na listach)' : 'Nazwa', nazwaPola);
  if (r === 'kontrahent' && !sys) {
    pola += pole('', 'Nazwa pełna', `<input id="b-pelna" maxlength="300" value="${esc(x?.pelna || '')}"${wyl}>`)
      + pole('', 'NIP (opcjonalnie)', `<input id="b-nip" maxlength="20" value="${esc(x?.nip || '')}"${wyl}>`)
      + (podp && !x.nip ? `<p class="szary">Z Fakturowni: ${esc(podp.pelna)}, NIP ${esc(podp.nip)}. ${edycja ? '<button class="przycisk maly miekki" id="b-podp">Wpisz z Fakturowni</button>' : ''}</p>` : '');
  }
  if (r === 'metoda') {
    pola += pole('', 'Rachunek (do łączenia z bankiem)', `<select id="b-rachunek"${wyl}>${['', ...BIB.rachunki].map(v => `<option value="${esc(v)}"${(x?.rachunek || '') === v ? ' selected' : ''}>${esc(RACHUNEK_OPIS[v] || v)}</option>`).join('')}</select>`)
      + pole('', 'Bank', `<input id="b-bank" maxlength="60" value="${esc(x?.bank || '')}"${wyl}>`);
  }
  if (r === 'kontrahent' || r === 'przedmiot') {
    const zablok = x?.domyslny ? ' disabled title="Jeden wpis musi być domyślny: ustaw jako domyślny inny wpis, a ten przestanie nim być sam"' : wyl;
    pola += `<label class="przelacznik"><input type="checkbox" id="b-dom"${x?.domyslny ? ' checked' : ''}${zablok}><span class="suwak"></span>Domyślny dla nowych wierszy w arkuszach</label>`;
  }
  const liczba = x ? `<p class="szary">Wystąpienia: <b>${x.uzyc}</b> (wiersze ${x.wiersze}, płatności ${x.platnosci})${x.arkusz_systemowy ? '; używa go też arkusz systemowy Opłaty urzędowe' : ''}.</p>` : '';
  const powodUsun = !x ? '' : sys ? 'To wpis systemowy.' : x.domyslny ? 'Wpis jest domyślny dla nowych wierszy: najpierw ustaw jako domyślny inny.'
    : x.arkusz_systemowy ? 'Używa go arkusz systemowy Opłaty urzędowe (podatki).' : x.uzyc ? `Ma ${odmWyst(x.uzyc)}. Usunąć można tylko pozycję z licznikiem 0; połącz ją z innym wpisem.` : '';
  const ust = r === 'kontrahent' ? `<h3>Ustawienia domyślne</h3><p class="szary">Wypełniają nowy wiersz, gdy zaczniesz go od wyboru tego kontrahenta. Zmiana tutaj nie zmienia istniejących wierszy.</p>${poleUstawien(x?.ustawienia || (nowy ? BIB.kontrahent.find(y => y.domyslny)?.ustawienia : null))}` : '';
  const k = $('#karta');
  k.innerHTML = `<button class="zamknij" aria-label="Zamknij">×</button><h2>${nowy ? DODAJ_BIB[r] : esc(x.etykieta)}</h2>
    <div class="formularz">${pola}</div>${ust}${liczba}
    <div class="akcje">${edycja ? `<button class="glowny" id="b-zapisz">${nowy ? 'Dodaj' : 'Zapisz'}</button>` : ''}
      ${!nowy && edycja ? `<button id="b-polacz" data-karta>${ik('link')}Połącz z istniejącym</button><button id="b-usun" data-karta${powodUsun ? ` disabled title="${esc(powodUsun)}"` : ''}>${ik('zamknij')}Usuń</button>` : ''}
      <button id="b-anuluj">Anuluj</button></div>
    ${!nowy && powodUsun && edycja ? `<p class="szary">Usuwanie: ${esc(powodUsun)}</p>` : ''}`;
  k.hidden = false;
  $('.zamknij', k).onclick = $('#b-anuluj', k).onclick = () => { k.hidden = true; };
  if (r === 'kontrahent') {
    podepnijUstawienia(k);
    if (!edycja) k.querySelectorAll('.bib-ust select, .bib-ust input').forEach(el => { el.disabled = true; });
  }
  const pp = $('#b-podp', k);
  if (pp) pp.onclick = e => { e.stopPropagation(); $('#b-pelna', k).value = podp.pelna; $('#b-nip', k).value = podp.nip; };
  const pol = $('#b-polacz', k);
  if (pol) pol.onclick = e => { e.stopPropagation(); kartaPolaczenia(r, x, []); };
  const us = $('#b-usun', k);
  if (us) us.onclick = e => { e.stopPropagation(); kartaUsunieciaBib(r, [x]); };
  const zap = $('#b-zapisz', k);
  if (!zap) return;
  const zapisz = () => {
    const d = { op: 'slownik', akcja: nowy ? 'dodaj' : 'zmien', rodzaj: r, nazwa: nowy ? $('#b-nazwa', k).value.trim() : x.nazwa };
    const nazwa = $('#b-nazwa', k).value.trim();
    if (!sys && !nazwa) return komunikat('Nazwa nie może być pusta. Wpisz nazwę.', true);
    if (!nowy && !sys && nazwa !== x.nazwa) {
      const ist = BIB[r].find(y => y.nazwa !== x.nazwa && y.nazwa.toLowerCase() === nazwa.toLowerCase());
      if (ist) return komunikat(`„${ist.etykieta}” już jest w Bibliotece. Żeby zostawić jeden wpis, użyj „Połącz z istniejącym”.`, true);
      d.nowa = nazwa;
    }
    if (nowy && BIB[r].some(y => y.nazwa.toLowerCase() === nazwa.toLowerCase())) return komunikat(`„${nazwa}” już jest w Bibliotece. Wybierz go z listy.`, true);
    if (r === 'kontrahent' && !sys) { d.pelna = $('#b-pelna', k).value.trim(); d.nip = $('#b-nip', k).value.trim(); }
    if (r === 'metoda') { d.rachunek = $('#b-rachunek', k).value; d.bank = $('#b-bank', k).value.trim(); }
    const dom = $('#b-dom', k);
    if (dom && dom.checked && !x?.domyslny) d.domyslny = true;
    if (r === 'kontrahent') {
      try { d.ustawienia = zbierzUstawienia(k); } catch (e) { return komunikat(e.message, true); }
      if (!nowy && rowneUstawienia(d.ustawienia, x.ustawienia)) delete d.ustawienia;
    }
    if (!nowy) {
      if ('pelna' in d && d.pelna === (x.pelna || '')) delete d.pelna;
      if ('nip' in d && d.nip.replace(/[\s-]/g, '').toUpperCase().replace(/^PL(?=\d{10}$)/, '') === (x.nip || '')) delete d.nip;
      if (r === 'metoda' && d.rachunek === (x.rachunek || '') && d.bank === (x.bank || '')) { delete d.rachunek; delete d.bank; }
      if (Object.keys(d).length === 4) return komunikat('Nic się nie zmieniło.');
    }
    zmiana('bud', d);
  };
  zap.onclick = zapisz;
  k.querySelectorAll('.formularz input').forEach(i => i.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); zapisz(); } }));
  if (!sys && edycja) { const n = $('#b-nazwa', k); n.focus(); if (!nowy) n.select(); }
}

// ---------- Łączenie duplikatów (A-KON-06): wybór drugiego wpisu i danych, które zostają; jeden wpis w pliku zmian ----------
function kartaPolaczenia(r, x, inne) {
  let wybrane = inne.length ? [x, ...inne] : [x];
  let cel = wybrane.find(y => y.systemowy) || x;
  const k = $('#karta');
  const pola = r === 'kontrahent' ? [['pelna', 'Pełna nazwa'], ['nip', 'NIP'], ['ustawienia', 'Ustawienia domyślne']] : r === 'metoda' ? [['rachunek', 'Rachunek'], ['bank', 'Bank']] : [];
  const dane = {};
  const opisPola = (y, p) => p === 'ustawienia' ? (y.ustawienia ? [y.ustawienia.podstawa, y.ustawienia.stawka_vat != null ? `${y.ustawienia.stawka_vat} %` : '', y.ustawienia.metoda].filter(Boolean).join(', ') : 'brak')
    : p === 'rachunek' ? RACHUNEK_OPIS[y.rachunek || ''] : (y[p] || 'brak');
  const rysuj = (q = '') => {
    const f = q.trim().toLowerCase();
    const kandydaci = BIB[r].filter(y => !wybrane.includes(y) && (!f || y.etykieta.toLowerCase().includes(f) || String(y.nip || '').includes(f))).slice(0, 40);
    const razem = wybrane.reduce((s, y) => s + y.uzyc, 0);
    const maWartosc = y => p => !!y[p];
    pola.forEach(([p]) => { if (!(p in dane) || !wybrane.includes(dane[p])) dane[p] = maWartosc(cel)(p) ? cel : wybrane.find(y => maWartosc(y)(p)) || cel; });
    $('#p-tresc', k).innerHTML = `${wybrane.length < 2 ? `<p>Wybierz drugi wpis, z którym połączysz „${esc(x.etykieta)}”.</p>
        ${pole('', 'Szukaj', `<input id="p-szukaj" value="${esc(q)}" placeholder="fragment nazwy${r === 'kontrahent' ? ' albo NIP' : ''}">`)}
        <div class="wybor-lista bib-kandydaci">${kandydaci.map(y => `<button data-k="${esc(y.nazwa)}">${esc(y.etykieta)} <span class="szary">${odmWyst(y.uzyc)}</span></button>`).join('') || '<span class="szary">Brak pasujących wpisów.</span>'}</div>`
      : `<p>Wszystkie wystąpienia (${razem}) przejdą na jeden wpis, pozostałe znikną z Biblioteki. To jedna zmiana: Cmd+Z albo Historia zmian cofa całość.</p>
        <table class="bib-wybor"><thead><tr><th>Co zostaje</th>${wybrane.map(y => `<th>${esc(y.etykieta)}<br><span class="szary">${odmWyst(y.uzyc)}</span></th>`).join('')}</tr></thead><tbody>
        <tr><td>${r === 'kontrahent' ? 'Nazwa skrócona' : 'Nazwa'}</td>${wybrane.map((y, i) => `<td><label><input type="radio" name="p-cel" value="${i}"${y === cel ? ' checked' : ''}${wybrane.some(z => z.systemowy) && !y.systemowy ? ' disabled title="Wpis systemowy zostaje zawsze"' : ''}> ${esc(y.etykieta)}</label></td>`).join('')}</tr>
        ${pola.map(([p, n]) => `<tr><td>${n}</td>${wybrane.map((y, i) => `<td><label><input type="radio" name="p-${p}" value="${i}"${dane[p] === y ? ' checked' : ''}> ${esc(opisPola(y, p))}</label></td>`).join('')}</tr>`).join('')}
        </tbody></table>${inne.length ? '' : '<p><button class="przycisk maly" id="p-zmien">Wybierz inny wpis</button></p>'}`}`;
    $('#p-ok', k).disabled = wybrane.length < 2;
    k.querySelectorAll('[data-k]').forEach(b => b.onclick = e => { e.stopPropagation(); wybrane = [x, BIB[r].find(y => y.nazwa === b.dataset.k)]; cel = wybrane.find(y => y.systemowy) || x; rysuj(); });
    const s = $('#p-szukaj', k);
    if (s) { s.oninput = () => rysuj(s.value); s.focus(); s.setSelectionRange(s.value.length, s.value.length); }
    const z = $('#p-zmien', k);
    if (z) z.onclick = e => { e.stopPropagation(); wybrane = [x]; rysuj(); };
    k.querySelectorAll('input[name="p-cel"]').forEach(i => i.onchange = () => { cel = wybrane[+i.value]; });
    pola.forEach(([p]) => k.querySelectorAll(`input[name="p-${p}"]`).forEach(i => i.onchange = () => { dane[p] = wybrane[+i.value]; }));
  };
  k.innerHTML = `<button class="zamknij" aria-label="Zamknij">×</button><h2>Połącz z istniejącym</h2><div id="p-tresc"></div>
    <div class="akcje"><button class="glowny" id="p-ok">Połącz</button><button id="p-anuluj">Anuluj</button></div>`;
  k.hidden = false;
  $('.zamknij', k).onclick = $('#p-anuluj', k).onclick = () => { k.hidden = true; };
  $('#p-ok', k).onclick = async () => {
    const d = { op: 'slownik', akcja: 'polacz', rodzaj: r, cel: cel.nazwa, zrodla: wybrane.filter(y => y !== cel).map(y => y.nazwa) };
    pola.forEach(([p]) => { if (dane[p] !== cel) d[p] = p === 'ustawienia' ? dane[p].ustawienia : dane[p][p] || ''; });
    if (r === 'kontrahent' && 'nip' in d && !d.nip) delete d.nip;
    if (await zmiana('bud', d)) BIB_ZAZN[r].clear();
  };
  rysuj();
}

// ---------- Foldery i kategorie (A-BUD-05 do 11): trzy kolumny jak w BS, dodaj, zmień nazwę, usuń, kolejność ----------
function widokStruktury(d, p) {
  const zwykle = d.struktura.filter(f => !f.systemowy);
  const f = d.struktura.find(x => x.folder === p.folder) || zwykle[0] || d.struktura[0];
  const kat = f ? (f.kategorie.find(x => x.kategoria === p.kategoria) || f.kategorie[0]) : null;
  const ed = d.planowanie;
  const ikony = (typ, i, n, tytulUsun, blokada, sys) => sys || !ed ? '' : `<span class="bib-ikony">
      <button class="przycisk-ikona" data-a="gora" data-typ="${typ}" data-i="${i}"${i === 0 ? ' disabled' : ''} aria-label="Wyżej" title="Wyżej">${ik('wyzej')}</button>
      <button class="przycisk-ikona" data-a="dol" data-typ="${typ}" data-i="${i}"${i === n - 1 ? ' disabled' : ''} aria-label="Niżej" title="Niżej">${ik('nizej')}</button>
      <button class="przycisk-ikona" data-a="nazwa" data-typ="${typ}" data-i="${i}" aria-label="Zmień nazwę" title="Zmień nazwę">${ik('olowek')}</button>
      <button class="przycisk-ikona" data-a="usun" data-typ="${typ}" data-i="${i}" data-karta title="${esc(tytulUsun || 'Usuń')}"${blokada ? ' aria-disabled="true"' : ''} aria-label="Usuń">${ik('kosz')}</button></span>`;
  const foldery = d.struktura.map((x, i) => `<div class="bib-poz${x === f ? ' aktywna' : ''}${x.systemowy ? ' systemowy' : ''}" data-f="${i}">
      <a href="${bibUrl('struktura', { folder: x.folder })}">${esc(x.folder)}</a><span class="licz">${x.arkuszy}</span>
      ${ikony('folder', i, zwykle.length, x.arkuszy ? `Folder ma ${odmArk(x.arkuszy)}: przy usuwaniu wybierzesz, dokąd je przenieść.` : '', false, x.systemowy)}</div>`).join('');
  const kategorie = f ? f.kategorie.map((x, i) => `<div class="bib-poz${x === kat ? ' aktywna' : ''}" data-k="${i}">
      <a href="${bibUrl('struktura', { folder: f.folder, kategoria: x.kategoria })}">${esc(x.kategoria)}</a><span class="licz">${x.arkusze.length}</span>
      ${ikony('kategoria', i, f.kategorie.length, f.kategorie.length === 1 ? 'To ostatnia kategoria folderu: folder musi mieć co najmniej jedną. Usuń cały folder albo najpierw dodaj inną kategorię.'
    : x.arkusze.length ? `Kategoria ma ${odmArk(x.arkusze.length)}: przy usuwaniu wybierzesz, dokąd je przenieść.` : '', f.kategorie.length === 1, f.systemowy)}</div>`).join('') : '';
  const miejsca = zwykle.flatMap(x => x.kategorie.map(y => [x.folder, y.kategoria]));
  const arkusze = kat ? kat.arkusze.map(a => `<div class="bib-poz ark"><a href="#/budzet/arkusz?id=${encodeURIComponent(a.id)}">${esc(a.nazwa)}</a>
      <span class="szary">${mies(a.od)} - ${mies(a.do)}</span>
      ${ed && !f.systemowy ? `<select data-przenies="${esc(a.id)}" aria-label="Przenieś arkusz do"><option value="">Przenieś do…</option>${miejsca.filter(([x, y]) => x !== f.folder || y !== kat.kategoria)
    .map(([x, y]) => `<option value="${esc(JSON.stringify([x, y]))}">${esc(x)} / ${esc(y)}</option>`).join('')}</select>` : ''}</div>`).join('') : '';
  setTimeout(() => podepnijStrukture(d, f, kat));
  return `<div class="bib-struktura">
      <div class="bib-kol"><h3>Folder</h3><div class="bib-lista">${foldery || '<div class="pusto-lista">Brak folderów.</div>'}</div>
        ${ed ? `<div class="bib-dodaj" id="s-dodaj-folder"><button class="przycisk maly miekki" data-karta>Dodaj folder ${ik('plus')}</button></div>` : ''}</div>
      <div class="bib-kol"><h3>Kategoria${f ? ` <span class="szary">w folderze ${esc(f.folder)}</span>` : ''}</h3><div class="bib-lista">${kategorie}</div>
        ${ed && f && !f.systemowy ? `<div class="bib-dodaj" id="s-dodaj-kategorie"><button class="przycisk maly miekki" data-karta>Dodaj kategorię ${ik('plus')}</button></div>` : ''}</div>
      <div class="bib-kol"><h3>Arkusze${kat ? ` <span class="szary">${esc(kat.kategoria)}</span>` : ''}</h3><div class="bib-lista">${arkusze || '<div class="pusto-lista">Brak arkuszy. Pusty folder i kategoria nie pokazują się w drzewie budżetu, ale możesz je wybrać przy dodawaniu arkusza.</div>'}</div></div>
    </div>
    <p class="notka">Nazwa folderu jest unikalna w całej apce, kategorii w obrębie folderu. Folder lub kategorię z arkuszami usuniesz, przenosząc arkusze w inne miejsce;
      ostatniej kategorii folderu nie usuniesz. Zmiana nazwy od razu widać na arkuszach, płatnościach, w cash flow i rentowności. Folder ${esc(d.folder_systemowy)} należy do arkusza systemowego z podatkami.</p>`;
}

function podepnijStrukture(d, f, kat) {
  const box = $('.bib-struktura');
  if (!box) return;
  box.querySelectorAll('.bib-poz.aktywna').forEach(el => { const l = el.closest('.bib-lista'); if (l) l.scrollTop = el.offsetTop - l.offsetTop - l.clientHeight / 3; });
  const zwykle = d.struktura.filter(x => !x.systemowy);
  const wyslij = dane => zmiana('bud', { op: 'struktura', ...dane });
  box.querySelectorAll('[data-a]').forEach(b => b.onclick = e => {
    e.preventDefault(); e.stopPropagation();
    const typ = b.dataset.typ, i = +b.dataset.i, a = b.dataset.a;
    const lista = typ === 'folder' ? zwykle.map(x => x.folder) : f.kategorie.map(x => x.kategoria);
    const x = typ === 'folder' ? d.struktura[i] : f.kategorie[i];
    const nazwa = typ === 'folder' ? x.folder : x.kategoria;
    if (a === 'gora' || a === 'dol') {
      const j = a === 'gora' ? i - 1 : i + 1, nowa = [...lista];
      [nowa[i], nowa[j]] = [nowa[j], nowa[i]];
      return wyslij(typ === 'folder' ? { akcja: 'kolejnosc', foldery: nowa } : { akcja: 'kolejnosc', folder: f.folder, kategorie: nowa });
    }
    if (a === 'nazwa') return edytujNazweStruktury(b.closest('.bib-poz'), nazwa, n => {
      const ist = lista.find(y => y !== nazwa && y.toLowerCase() === n.toLowerCase());
      if (ist) return komunikat(`„${ist}” już jest${typ === 'folder' ? '' : ` w folderze „${f.folder}”`}. Wybierz inną nazwę.`, true);
      wyslij(typ === 'folder' ? { akcja: 'zmien_folder', folder: nazwa, nazwa: n } : { akcja: 'zmien_kategorie', folder: f.folder, kategoria: nazwa, nazwa: n })
        .then(z => { if (z) location.hash = bibUrl('struktura', typ === 'folder' ? { folder: n } : { folder: f.folder, kategoria: n }); });
    });
    if (b.getAttribute('aria-disabled') === 'true') return komunikat(b.title, true);
    kartaUsunieciaStruktury(d, typ, f, x);
  });
  box.querySelectorAll('[data-przenies]').forEach(s => s.onchange = () => {
    if (!s.value) return;
    const [folder, kategoria] = JSON.parse(s.value);
    zmiana('bud', { op: 'arkusz', obiekt: { id: s.dataset.przenies, folder, kategoria } });
  });
  const df = $('#s-dodaj-folder'), dk = $('#s-dodaj-kategorie');
  if (df) df.querySelector('button').onclick = e => { e.stopPropagation(); formularzDodaniaStruktury(df, 'folder', d, f); };
  if (dk) dk.querySelector('button').onclick = e => { e.stopPropagation(); formularzDodaniaStruktury(dk, 'kategoria', d, f); };
}

// Edycja nazwy w miejscu (A-BUD-10): pole, ✓ zapis, × anuluj; Enter i Esc.
function edytujNazweStruktury(poz, stara, ok) {
  const html = poz.innerHTML;
  poz.innerHTML = `<input class="bib-input" maxlength="80" value="${esc(stara)}" aria-label="Nowa nazwa"><span class="bib-ikony widoczne">
    <button class="przycisk-ikona" data-ok aria-label="Zapisz" title="Zapisz">${ik('ptaszek')}</button><button class="przycisk-ikona" data-x aria-label="Anuluj" title="Anuluj">${ik('zamknij')}</button></span>`;
  const inp = poz.querySelector('input');
  const anuluj = () => { poz.innerHTML = html; pokaz(); };
  const zapisz = () => { const n = inp.value.trim(); if (!n) return komunikat('Nazwa nie może być pusta.', true); if (n === stara) return anuluj(); ok(n); };
  poz.querySelector('[data-ok]').onclick = e => { e.stopPropagation(); zapisz(); };
  poz.querySelector('[data-x]').onclick = e => { e.stopPropagation(); anuluj(); };
  inp.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); zapisz(); } if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); anuluj(); } });
  inp.focus(); inp.select();
}

// Dodanie (A-BUD-09): folder zawsze z pierwszą kategorią; kategoria do folderu zaznaczonego po lewej.
function formularzDodaniaStruktury(box, typ, d, f) {
  box.innerHTML = `${typ === 'folder' ? '<input class="bib-input" id="s-nowy-folder" maxlength="80" placeholder="Nazwa folderu">' : ''}
    <input class="bib-input" id="s-nowa-kategoria" maxlength="80" placeholder="${typ === 'folder' ? 'Pierwsza kategoria (wymagana)' : 'Nazwa kategorii'}">
    <span class="bib-ikony widoczne"><button class="przycisk-ikona" data-ok aria-label="Dodaj" title="Dodaj">${ik('ptaszek')}</button>
    <button class="przycisk-ikona" data-x aria-label="Anuluj" title="Anuluj">${ik('zamknij')}</button></span>`;
  const nf = $('#s-nowy-folder'), nk = $('#s-nowa-kategoria');
  const ok = () => {
    const kat = nk.value.trim();
    if (typ === 'folder') {
      const fol = nf.value.trim();
      if (!fol || !kat) return komunikat('Folder musi mieć co najmniej jedną kategorię: wpisz nazwę folderu i pierwszej kategorii.', true);
      const ist = d.struktura.find(x => x.folder.toLowerCase() === fol.toLowerCase());
      if (ist) return komunikat(`Folder „${ist.folder}” już jest. Nazwa folderu musi być unikalna w całej apce.`, true);
      return zmiana('bud', { op: 'struktura', akcja: 'dodaj_folder', folder: fol, kategoria: kat }).then(z => { if (z) location.hash = bibUrl('struktura', { folder: fol }); });
    }
    if (!kat) return komunikat('Wpisz nazwę kategorii.', true);
    const ist = f.kategorie.find(x => x.kategoria.toLowerCase() === kat.toLowerCase());
    if (ist) return komunikat(`Kategoria „${ist.kategoria}” już jest w folderze „${f.folder}”.`, true);
    zmiana('bud', { op: 'struktura', akcja: 'dodaj_kategorie', folder: f.folder, kategoria: kat });
  };
  box.querySelector('[data-ok]').onclick = e => { e.stopPropagation(); ok(); };
  box.querySelector('[data-x]').onclick = e => { e.stopPropagation(); pokaz(); };
  box.querySelectorAll('input').forEach(i => i.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); ok(); } if (e.key === 'Escape') { e.preventDefault(); pokaz(); } }));
  (nf || nk).focus();
}

// Usunięcie (A-BUD-11): pusty od razu po potwierdzeniu; z arkuszami tylko z przeniesieniem w inne miejsce.
function kartaUsunieciaStruktury(d, typ, f, x) {
  const zwykle = d.struktura.filter(y => !y.systemowy);
  const ark = typ === 'folder' ? x.arkuszy : x.arkusze.length;
  const nazwa = typ === 'folder' ? x.folder : x.kategoria;
  let wybor = '';
  if (ark && typ === 'folder') {
    const cele = zwykle.filter(y => y !== x);
    if (!cele.length) return komunikat('To jedyny folder z arkuszami: dodaj najpierw inny folder, żeby przenieść do niego arkusze.', true);
    wybor = `<p>Folder ma ${odmArk(ark)}. Przenieś ${ark === 1 ? 'go' : 'je'} razem z kategoriami do innego folderu (kategoria o tej samej nazwie połączy się z istniejącą):</p>
      ${pole('', 'Folder docelowy', `<select id="s-cel">${cele.map(y => `<option>${esc(y.folder)}</option>`).join('')}</select>`)}`;
  } else if (ark) {
    const cele = zwykle.flatMap(y => y.kategorie.filter(z => !(y === f && z === x)).map(z => [y.folder, z.kategoria]));
    wybor = `<p>Kategoria ma ${odmArk(ark)}. Przenieś ${ark === 1 ? 'go' : 'je'} do innej kategorii:</p>
      ${pole('', 'Folder / kategoria docelowa', `<select id="s-cel">${cele.map(c => `<option value="${esc(JSON.stringify(c))}"${c[0] === f.folder ? ' selected' : ''}>${esc(c[0])} / ${esc(c[1])}</option>`).join('')}</select>`)}`;
  }
  const opis = typ === 'folder' ? `Folder „${esc(nazwa)}” zniknie razem z kategoriami (${x.kategorie.length}).` : `Kategoria „${esc(nazwa)}” zniknie z folderu „${esc(f.folder)}”.`;
  kartaFormularza(`Usuń ${typ === 'folder' ? 'folder' : 'kategorię'}`, `<div class="formularz">${wybor}</div><p>${opis} Cofniesz to w Historii zmian.</p>`,
    ark ? 'Przenieś i usuń' : 'Tak, usuń', () => {
      const d2 = typ === 'folder' ? { akcja: 'usun_folder', folder: nazwa } : { akcja: 'usun_kategorie', folder: f.folder, kategoria: nazwa };
      const cel = $('#s-cel');
      if (cel && typ === 'folder') d2.do_folderu = cel.value;
      if (cel && typ !== 'folder') { const [cf, ck] = JSON.parse(cel.value); Object.assign(d2, { do_folderu: cf, do_kategorii: ck }); }
      zmiana('bud', { op: 'struktura', ...d2 }).then(z => { if (z) location.hash = bibUrl('struktura', typ === 'folder' ? {} : { folder: f.folder }); });
    });
}

// ---------- Arkusze (A-KON-12): wszystkie arkusze, także te, których nie ma w drzewie ----------
function widokArkuszyBib(d, p) {
  const q = (p.q || '').trim().toLowerCase();
  const dane = d.arkusze.filter(a => !q || [a.nazwa, a.folder, a.kategoria].some(v => String(v).toLowerCase().includes(q)));
  const kol = [{ naglowek: 'Arkusz', html: a => `<a href="#/budzet/arkusz?id=${encodeURIComponent(a.id)}">${esc(a.nazwa)}</a>`, sortKlucz: a => a.nazwa },
    { naglowek: 'Folder', wartosc: a => a.folder }, { naglowek: 'Kategoria', wartosc: a => a.kategoria },
    { naglowek: 'Zakres', wartosc: a => `${mies(a.od)} - ${mies(a.do)}`, sortKlucz: a => a.od }, { naglowek: 'Wierszy', liczba: true, wartosc: a => a.wierszy },
    { naglowek: 'Źródło', wartosc: a => a.zrodlo === 'system' ? 'systemowy (podatki)' : a.zrodlo || '' }];
  setTimeout(() => {   // filtr w miejscu: wiersze bez frazy chowamy (bez przerysowania, fokus zostaje w polu)
    const s = $('#bib-szukaj-ark');
    if (s) s.oninput = () => { const f = s.value.trim().toLowerCase(); document.querySelectorAll('.bib-arkusze tbody tr').forEach(tr => { tr.hidden = !!f && !tr.textContent.toLowerCase().includes(f); }); };
  });
  return `<div class="ark-pasek"><input class="szukaj" id="bib-szukaj-ark" type="search" placeholder="Wyszukaj arkusz, folder, kategorię" value="${esc(p.q || '')}" aria-label="Wyszukaj arkusz"></div>
    <p class="notka">${d.arkusze.length} arkuszy w ${d.struktura.length} folderach. Kliknij nazwę, żeby otworzyć arkusz; miejsce arkusza zmienisz w zakładce Foldery i kategorie albo w arkuszu (Zarządzaj).</p>
    <div class="bib-arkusze">${tabela({ kolumny: kol, dane, sortLokalny: true, niska: true, onWiersz: a => { location.hash = `#/budzet/arkusz?id=${encodeURIComponent(a.id)}`; } })}</div>`;
}

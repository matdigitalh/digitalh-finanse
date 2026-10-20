'use strict';
// Pakiet 5: rzeczywiste vs planowane i łączenie jak w Budget Studio (decyzja Mata 2026-10-19, pkt 2 i 12).
// - „Do połączenia”: dokumenty rzeczywiste (Fakturownia, rejestr biura, przelew ING bez dokumentu, płatność dodana ręcznie)
//   niepołączone z budżetem, z PODPOWIEDZIĄ planu (arkusz, wiersz, miesiąc, pewność, uzasadnienie). „Połącz” podstawia
//   podpowiedź i łączy jednym kliknięciem; nic nie łączy się samo. Akcje grupowe: połącz wg podpowiedzi (jedna seria),
//   nowe wiersze w arkuszu (B-LACZ-07), odłącz, do weryfikacji, usuń płatność dodaną ręcznie.
// - Ekran łączenia (karta dokumentu, B-LACZ-01 do 03): podpowiedzi i wyszukiwarka komórek po lewej, wybrane komórki z kwotami
//   po prawej, „Do rozliczenia” musi wyjść 0,00, różnica od planu, co z resztą planu.
// - Dodaj płatność (formularz jak w BS, B-DOD-02), zamiana planu na rzeczywistą (B-LACZ-06), lista płac za miesiąc
//   (koszt pracy, decyzja 12) z ostrzeżeniami.
// Korzysta z globali app.js, budzet.js, arkusz.js i listy.js (ładowany po nich).

const ZRODLA_DOK = { faktura: 'Fakturownia', zakup: 'Rejestr biura', operacja: 'Bank ING', reczna: 'Dodana ręcznie' };
const PEWNOSC_KLASA = { wysoka: 'plus', 'średnia': 'akcent', niska: 'ostrzezenie' };
const chipPewnosc = p => `<span class="chip ${p ? PEWNOSC_KLASA[p] : 'neutral'}">${esc(p || 'brak')}</span>`;
const czescRef = ref => { const i = String(ref).indexOf(':'); return { obiekt: ref.slice(0, i), ref: ref.slice(i + 1) }; };
const miejsceKomorki = x => `${x.arkusz_nazwa} · ${x.kontrahent || x.komentarz || x.przedmiot || 'wiersz'} · ${miesPelny(x.miesiac)}`;
const jednostkaDok = d => d.rodzina === 'bank' || d.rodzina === 'Bez faktury' ? 'kwota (brutto, jak w banku)' : 'netto';
const dzisWpisu = () => [STAN?.naleznosci?.dzien_stanu || '', new Date().toISOString().slice(0, 10)].sort().pop();
const LACZ = { planowanie: false };

// Opisy nowych operacji w historii zmian i w „Cofnij”
Object.assign(OPISY_OP, { polacz: 'połączenie z budżetem', odlacz: 'odłączenie od budżetu', rzeczywista: 'płatność dodana ręcznie',
  zamien: 'zamiana planu na rzeczywistą', lista_plac: 'lista płac', zamknij_worek: 'zamknięcie worka' });
Object.assign(NAZWY_OP, { polacz: 'połączenie z budżetem', odlacz: 'odłączenie od budżetu', rzeczywista: 'płatność dodana ręcznie',
  zamien: 'zamiana planu na rzeczywistą', lista_plac: 'lista płac', zamknij_worek: 'zamknięcie worka' });

// Menu: „Do połączenia” to poczekalnia rzeczywistych jak w BS; wpłaty do faktur (etap 2) jako osobna pozycja w Banku ING.
(() => {
  const pl = PODSTRONY.platnosci;
  const i = pl.findIndex(p => p.hash === '#/platnosci/do-polaczenia');
  if (i >= 0) pl.splice(i, 1, { nazwa: 'Do połączenia', hash: '#/platnosci/laczenie', licznik: 'do_polaczenia_bud', ik: 'rozlacz' },
    { nazwa: 'Dodaj płatność', hash: '#/platnosci/dodaj', ik: 'plus' });
  const b = pl.findIndex(p => p.ekran === 'bank');
  if (b >= 0) pl.splice(b + 1, 0, { nazwa: 'Wpłaty do połączenia z fakturą', hash: '#/platnosci/do-polaczenia', licznik: 'do_polaczenia', ik: 'link' });
  const bu = PODSTRONY.budzet;
  const u = bu.findIndex(p => p.hash === '#/budzet/umowy');
  bu.splice(u >= 0 ? u + 1 : bu.length, 0, { nazwa: 'Lista płac', hash: '#/budzet/lista-plac', licznik: 'ostrzezenia', ik: 'osoby' });
})();

// Komunikat z kilkoma przyciskami (np. „Zostaw resztę planu” i „Cofnij” po połączeniu jednym kliknięciem).
function komunikatAkcje(tekst, przyciski = [], blad = false) {
  komunikat(tekst, blad);
  const el = $('#komunikaty').firstChild;
  for (const p of przyciski) {
    const b = document.createElement('button');
    b.textContent = p.nazwa;
    b.onclick = p.akcja;
    el.appendChild(b);
  }
}

const tekstRoznicy = (plan, kwota) => {
  const r = plan - kwota;
  return r === 0 ? 'kwota równa planowi' : `różnica ${zl(r)} (plan ${zl(plan)}, dokument ${zl(kwota)})`;
};

// Jedno kliknięcie: podpowiedź podstawiona i połączona. Gdy dokument jest mniejszy niż plan pojedynczy, komunikat pyta,
// czy zostawić resztę planu (jak w BS); domyślnie plan znika w całości.
async function polaczJednym(x) {
  const dane = { op: 'polacz', dokument: x.ref, czesci: [{ wiersz: x.pod_wiersz, miesiac: x.pod_miesiac, kwota: x.kwota }] };
  if (!(await zmiana('bud', dane))) return false;
  const worek = WOREK.includes(x.pod_podstawa);
  const reszta = !worek && x.pod_kwota > x.kwota;
  const przyciski = [];
  if (reszta) przyciski.push({ nazwa: 'Zostaw resztę planu', akcja: () => zmiana('bud', { op: 'seria', operacje: [{ op: 'odlacz', dokument: x.ref }, { ...dane, reszta: 'zostaw' }] }) });
  przyciski.push({ nazwa: 'Cofnij', akcja: cofnijOstatni });
  komunikatAkcje(`Połączono ${x.kontrahent_krotko || x.kontrahent} z ${x.pod_arkusz_nazwa}, ${miesPelny(x.pod_miesiac)}: ${tekstRoznicy(x.pod_kwota, x.kwota)}.`
    + (reszta ? ' Plan był większy: jego reszta zniknęła (jak w BS), chyba że ją zostawisz.' : ''), przyciski);
  return true;
}

function polaczWgPodpowiedzi(r) {
  const op = r.map(x => ({ op: 'polacz', dokument: x.ref, czesci: [{ wiersz: x.pod_wiersz, miesiac: x.pod_miesiac, kwota: x.kwota }] }));
  const roznice = r.filter(x => x.roznica);
  formularzAkcji('Połącz wg podpowiedzi', `${r.length} ${liczebnik(r.length, ['dokument trafi', 'dokumenty trafią', 'dokumentów trafi'])} do podpowiedzianych komórek jednym zapisem (jedna seria, cofasz całość). Rzeczywista zastępuje plan; plan pojedynczy znika w całości, worek zostaje otwarty.`,
    `${roznice.length ? `<p class="szary">Różnice od planu: ${roznice.length}</p><ul class="lista">${roznice.slice(0, 12).map(x => `<li>${esc(x.kontrahent_krotko)}: ${esc(tekstRoznicy(x.pod_kwota, x.kwota))}</li>`).join('')}${roznice.length > 12 ? `<li>i ${roznice.length - 12} więcej</li>` : ''}</ul>` : '<p class="szary">Wszystkie kwoty równe planom.</p>'}
     ${pole('', 'Reszta planu, gdy dokument jest mniejszy', '<select id="fa-reszta"><option value="">usuń (jak w BS: komórka = kwota dokumentu)</option><option value="zostaw">zostaw jako plan w tej komórce</option></select>')}`,
    () => zmiana('bud', { op: 'seria', operacje: op.map(o => ({ ...o, ...($('#fa-reszta').value ? { reszta: $('#fa-reszta').value } : {}) })) }));
}

// B-LACZ-07: każdy zaznaczony dokument jako NOWY wiersz w wybranym arkuszu (1 wiersz = 1 płatność), wiersz z danymi dokumentu
// (dzień wystawienia, stawka VAT, dni na płatność), plan 0 w miesiącu dokumentu i połączenie, wszystko jedną serią.
// Wołane też z rozjazdów „Faktura bez pozycji w BS” i „Wydatek z banku bez pozycji w BS” (budzet.js).
const dniMiedzy = (a, b) => Math.round((Date.parse(`${b}T12:00:00Z`) - Date.parse(`${a}T12:00:00Z`)) / 864e5);
async function nowymiWierszami(r) {
  let drzewo;
  try { drzewo = await api('budzet/drzewo'); } catch (e) { return komunikat(e.message, true); }
  const arkusze = drzewo.foldery.flatMap(f => Object.values(f.kategorie).flat()).filter(a => a.zrodlo !== 'system');
  formularzAkcji('Połącz z budżetem: nowe wiersze', `${r.length} ${liczebnik(r.length, ['dokument stanie', 'dokumenty staną', 'dokumentów stanie'])} się nowym wierszem w wybranym arkuszu (jak „Połącz z budżetem” w BS). Wiersz bierze z dokumentu kontrahenta, dzień wystawienia, stawkę VAT i dni na płatność.`,
    pole('', 'Arkusz', `<select id="fa-arkusz">${arkusze.map(a => `<option value="${esc(a.id)}">${esc(a.nazwa)} (${esc(a.folder)})</option>`).join('')}</select>`), () => {
      const aid = $('#fa-arkusz').value;
      const operacje = [];
      for (const x of r) {
        const wid = nowyId('w');
        const dzien = x.data ? `${+x.data.slice(8, 10)}.` : 'Ostatni';
        const stawka = x.netto ? [23, 8, 5, 0].find(s => Math.abs(x.vat * 100 / x.netto - s) <= 0.1) : null;
        const bezFaktury = x.rodzina === 'Bez faktury' || x.rodzina === 'bank';   // przelew bez dokumentu = bez faktury
        const dni = x.termin && x.data ? Math.max(0, dniMiedzy(x.data, x.termin)) : 14;
        operacje.push({ op: 'wiersz', obiekt: { id: wid, arkusz: aid, rodzaj: x.rodzaj, podstawa: bezFaktury ? 'Bez faktury' : 'Faktura (jedna)',
          kontrahent: (x.kontrahent_krotko || x.kontrahent || '').slice(0, 200), dzien_wystawienia: dzien, dni_na_platnosc: dni,
          ...(bezFaktury ? {} : { stawka_vat: stawka ?? 23 }) } },
        { op: 'komorka', wiersz: wid, miesiac: x.data.slice(0, 7), kwota: 0 },
        { op: 'polacz', dokument: x.ref, czesci: [{ wiersz: wid, miesiac: x.data.slice(0, 7), kwota: x.kwota }] });
      }
      return zmiana('bud', { op: 'seria', operacje });
    });
}

const powodPlanowania = d => d.planowanie ? null : 'Planowanie w apce jest wyłączone; łączenie z budżetem włączysz w Budżet, Ustawienia budżetu.';

EKRANY_LIST.do_polaczenia = {
  hash: '#/platnosci/laczenie', tytul: 'Do połączenia', okruszek: 'Płatności / Płatności oczekujące', csv: 'do-polaczenia',
  id: x => x.ref,
  kolumny: [
    { k: 'rodzaj', n: 'Rodzaj', sort: 'rodzaj', html: x => chipZnak(x.rodzaj), csv: x => x.rodzaj > 0 ? 'wpływ' : 'obciążenie' },
    kolTekst('zrodlo', 'Źródło', x => x.zrodlo_nazwa, { klasa: () => 'szary' }),
    kolData('data', 'Dzień<br>wystawienia', x => x.data),
    { k: 'kontrahent', n: 'Kontrahent', sort: 'kontrahent', html: x => `<span title="${esc(x.kontrahent)}">${esc(x.kontrahent_krotko)}</span>`, csv: x => x.kontrahent },
    kolTekst('nr_dok', 'Numer<br>dokumentu', x => x.nr_dok || '-'),
    kolTekst('tytul', 'Tytuł', x => x.tytul, { klasa: () => 'szary' }),
    kolKwota('netto', 'Netto PLN', x => x.netto * x.rodzaj),
    kolKwota('vat', 'VAT PLN', x => x.vat * x.rodzaj),
    kolKwota('brutto', 'Brutto PLN', x => x.brutto * x.rodzaj),
    { k: 'podpowiedz', n: 'Podpowiedź planu<br>(arkusz · wiersz · miesiąc)', sort: 'podpowiedz',
      html: x => x.pod_wiersz ? `<span class="pod-miejsce">${esc(x.pod_arkusz_nazwa)} · ${esc(x.pod_kontrahent || x.pod_komentarz || x.pod_przedmiot || 'wiersz')} · ${esc(miesPelny(x.pod_miesiac))}</span><span class="pod-dlaczego">${esc(x.uzasadnienie || '')}</span>`
        : '<span class="szary">brak: wybierz plan ręcznie</span>',
      csv: x => x.pod_wiersz ? `${x.pod_arkusz_nazwa} · ${x.pod_kontrahent || x.pod_komentarz || ''} · ${x.pod_miesiac}` : '' },
    { k: 'pewnosc', n: 'Pewność', sort: 'pewnosc', html: x => chipPewnosc(x.pewnosc), csv: x => x.pewnosc || 'brak' },
    { k: 'roznica', n: 'Plan<br>i różnica', sort: 'roznica', liczba: true,
      html: x => x.pod_kwota == null ? '' : `${zl(x.pod_kwota, false)}${x.roznica ? `<br><span class="pod-roznica">${zl(x.roznica, false)}</span>` : '<br><span class="szary">równa</span>'}`,
      csv: x => x.roznica == null ? '' : kwotaCsv(x.roznica) },
    { k: 'akcje', n: '', klasa: () => 'akcje-wiersz', csv: () => '',
      html: x => x.stan === 'polaczony' ? '<button data-ls-a="wybierz">Pokaż</button>'
        : `${LACZ.planowanie && x.pod_wiersz ? '<button class="glowny" data-ls-a="polacz">Połącz</button>' : ''}<button data-ls-a="wybierz">${x.pod_wiersz ? 'Inny plan' : 'Wybierz plan'}</button>` },
  ],
  domyslne: ['rodzaj', 'zrodlo', 'data', 'kontrahent', 'nr_dok', 'brutto', 'podpowiedz', 'pewnosc', 'roznica', 'akcje'],
  szybkie: [
    { k: 'rodzaj', n: 'Rodzaj', opcje: [['', 'Wszystko'], ['1', 'Wpływy'], ['-1', 'Obciążenia']] },
    { k: 'zrodlo', n: 'Źródło', multi: true, opcje: Object.entries(ZRODLA_DOK) },
    { k: 'pewnosc', n: 'Podpowiedź', multi: true, opcje: [['wysoka', 'pewność wysoka'], ['średnia', 'pewność średnia'], ['niska', 'pewność niska'], ['brak', 'bez podpowiedzi']] },
  ],
  daty: [['data', 'Dzień wystawienia']],
  kwoty: x => ({ rodzaj: x.rodzaj, netto: x.netto * x.rodzaj, vat: x.vat * x.rodzaj, brutto: x.brutto * x.rodzaj }),
  wierszKlasa: x => x.rodzaj === 1 ? 'wiersz-plus' : '',
  stopkaSum: d => ({ netto: zl(d.podsumowanie.razem.netto, false), vat: zl(d.podsumowanie.razem.vat, false), brutto: zl(d.podsumowanie.razem.brutto, false) }),
  info: d => { LACZ.planowanie = d.planowanie; return `${d.razem} ${liczebnik(d.razem, ['pozycja', 'pozycje', 'pozycji'])}`; },
  przed: (d, ef) => {
    setTimeout(() => {
      const b = $('#lacz-od');
      if (b) b.onclick = () => kartaStartuLaczenia(d.laczenie_od);
    });
    return `<div class="zakladki" role="tablist">${Object.entries(d.stany).map(([v, n]) => `<button role="tab" aria-selected="${(ef.stan || 'do_polaczenia') === v}" data-ls-stan="${v === 'do_polaczenia' ? 'nieznana' : v}">${esc(n)} <span class="szary">${d.liczniki[v] || 0}</span></button>`).join('')}
      <a class="prawo przycisk miekki" href="#/platnosci/dodaj">${ik('plus')}Dodaj płatność</a></div>
      <p class="szary lacz-od">Łączenie w apce od ${esc(dataPl(d.laczenie_od))}: wcześniejsze dokumenty są połączone w Budget Studio (kopia BS). <button class="link" id="lacz-od" data-karta>Zmień datę</button></p>
      ${d.planowanie ? '' : '<div class="komunikat"><span>Planowanie w apce jest wyłączone, więc łączenie też (Budżet, Ustawienia budżetu). Podpowiedzi widać już teraz.</span></div>'}`;
  },
  notka: () => 'Płatność rzeczywista nie liczy się do budżetu, cash flow, podatków ani rentowności, dopóki nie połączysz jej z planem (jak w BS). Apka podpowiada plan (kontrahent, kwota, miesiąc, wcześniejsze połączenia), ale nic nie łączy się samo: „Połącz” wstawia podpowiedź, „Inny plan” otwiera ekran łączenia z podziałem na kilka komórek.',
  onWiersz: x => { location.hash = `#/platnosci/polacz?ref=${encodeURIComponent(x.ref)}`; },
  wWierszu: (a, x) => a === 'polacz' ? polaczJednym(x) : (location.hash = `#/platnosci/polacz?ref=${encodeURIComponent(x.ref)}`),
  akcje: [
    { id: 'polacz_wg', nazwa: 'Połącz wg podpowiedzi', ik: 'link',
      powod: (r, d) => powodPlanowania(d) || (r.some(x => x.stan !== 'do_polaczenia') ? 'Połączysz tylko pozycje z zakładki Do połączenia.'
        : r.some(x => !x.pod_wiersz) ? 'Część zaznaczonych nie ma podpowiedzi: połącz je na ekranie łączenia („Wybierz plan”).' : null),
      wykonaj: r => polaczWgPodpowiedzi(r) },
    { id: 'nowe_wiersze', nazwa: 'Połącz z budżetem: nowe wiersze', ik: 'arkusz',
      powod: (r, d) => powodPlanowania(d) || (r.some(x => x.stan === 'polaczony') ? 'Pozycje połączone w apce najpierw odłącz.' : null),
      wykonaj: r => nowymiWierszami(r) },
    { id: 'odlacz', nazwa: 'Odłącz od budżetu', ik: 'rozlacz',
      powod: (r, d) => powodPlanowania(d) || (r.some(x => x.stan !== 'polaczony') ? 'Odłączysz tylko pozycje połączone w apce.' : null),
      wykonaj: r => formularzAkcji('Odłącz od budżetu', `${r.length} ${liczebnik(r.length, ['dokument wróci', 'dokumenty wrócą', 'dokumentów wróci'])} do Do połączenia, a w komórkach wrócą plany.`, '',
        () => zmiana('bud', { op: 'seria', operacje: r.map(x => ({ op: 'odlacz', dokument: x.ref })) })) },
    { id: 'usun', nazwa: 'Usuń (dodane ręcznie)', ik: 'zamknij',
      powod: (r, d) => powodPlanowania(d) || (r.some(x => x.typ !== 'reczna' || x.stan === 'polaczony') ? 'Usuniesz tylko płatności dodane ręcznie i niepołączone; dokumentów z importu nie usuwa się w apce.' : null),
      wykonaj: r => formularzAkcji('Usuń płatności', `${r.length} ${liczebnik(r.length, ['płatność dodana ręcznie zniknie', 'płatności dodane ręcznie znikną', 'płatności dodanych ręcznie zniknie'])}. Cofniesz to przyciskiem Cofnij.`, '',
        () => zmiana('bud', { op: 'seria', operacje: r.map(x => ({ op: 'rzeczywista', obiekt: { id: czescRef(x.ref).ref }, usun: true })) })) },
    { id: 'do_weryfikacji', nazwa: 'Do weryfikacji', ik: 'weryfikuj',
      wykonaj: r => formularzAkcji('Przenieś do Do weryfikacji', `Na listę Do weryfikacji: ${r.length} ${liczebnik(r.length, ['pozycja', 'pozycje', 'pozycji'])}. Wrócą do Do połączenia, gdy oznaczysz je jako sprawdzone.`,
        pole('', 'Co sprawdzić (opcjonalnie)', '<input id="fa-powod" maxlength="200" placeholder="np. zapytać biuro, do którego klienta">'),
        () => zmiana('seria', { wpisy: r.map(x => ({ typ: 'do_weryfikacji', dane: { ...czescRef(x.ref), powod: $('#fa-powod').value.trim() } })) })) },
  ],
};
WIDOKI['platnosci/laczenie'] = p => ekranListy('do_polaczenia', p);

function kartaStartuLaczenia(od) {
  formularzAkcji('Łączenie w apce od', 'Dokumenty od tego dnia czekają w Do połączenia na Twoje kliknięcie. Wcześniejsze są połączone w Budget Studio i przychodzą z kopii BS (decyzja: łączenie w apce od 1.11.2026).',
    pole('', 'Dzień startu łączenia', `<input type="date" id="fa-od" value="${esc(od)}">`), () => {
      const v = $('#fa-od').value;
      if (!v) return komunikat('Wybierz dzień.', true);
      return zmiana('ustawienie', { klucz: 'laczenie_od', wartosc: v });
    });
}

// Połączone z budżetem: masowe odłączenie (B-LACZ-05, B-LIS-09) płatności połączonych w apce.
EKRANY_LIST.platnosci.akcje.splice(2, 0, { id: 'odlacz', nazwa: 'Odłącz od budżetu', ik: 'rozlacz',
  powod: (r, d) => powodPlanowania(d) || (r.some(x => !x.dokument) ? 'Odłączysz tylko płatności połączone w apce (z dokumentu, zamiany planu albo listy płac).' : null),
  wykonaj: r => formularzAkcji('Odłącz od budżetu', 'Rzeczywiste wrócą do Do połączenia (lista płac i zamiana planu: wraca plan), w komórkach znów pojawią się plany.', '',
    () => zmiana('bud', { op: 'seria', operacje: [...new Set(r.map(x => x.dokument))].map(d => ({ op: 'odlacz', dokument: d })) })) });

// Do weryfikacji: ostrzeżenie listy płac otwiera listę płac, płatność dodana ręcznie otwiera ekran łączenia.
(() => {
  const dw = EKRANY_LIST.do_weryfikacji, stary = dw.onWiersz;
  dw.onWiersz = (x, d) => x.lista_plac ? (location.hash = `#/budzet/lista-plac?miesiac=${x.lista_plac}`)
    : x.obiekt === 'reczna' ? (location.hash = `#/platnosci/polacz?ref=${encodeURIComponent(`reczna:${x.ref}`)}`) : stary(x, d);
})();

// ---------- Ekran łączenia (karta dokumentu → Budżet) ----------
let EKR = null;   // stan ekranu łączenia: dokument, podpowiedzi, wybrane komórki z kwotami, reszta planu

WIDOKI['platnosci/polacz'] = async p => {
  const ref = p.ref || '';
  let d;
  try { d = await api('laczenie/dokument', { ref }); } catch (e) { return `<h1>Połącz z budżetem</h1><div class="komunikat blad"><span>${esc(e.message)}</span></div>`; }
  EKR = { ref, d, wybrane: [], reszta: '', q: '' };
  const x = d.dokument;
  setTimeout(podepnijEkranLaczenia);
  const naglowek = `<h1>Połącz z budżetem</h1><div class="pigulki"><a class="pigulka" href="#/platnosci/laczenie">${ik('strzalkaP')}Do połączenia</a>
    <span class="szary">${esc(ZRODLA_DOK[x.typ] || x.zrodlo)} · ${esc(x.kontrahent_krotko)}${x.nr_dok ? ` · ${esc(x.nr_dok)}` : ''}</span></div>`;
  const dok = `<section class="lacz-dok">
      <div><span class="szary">Kontrahent</span><b title="${esc(x.kontrahent)}">${esc(x.kontrahent_krotko)}</b></div>
      <div><span class="szary">Rodzaj</span>${chipZnak(x.rodzaj)}</div>
      <div><span class="szary">Podstawa</span><b>${esc(x.rodzina === 'bank' ? 'przelew bez dokumentu' : x.rodzina)}</b></div>
      <div><span class="szary">Dzień wystawienia</span><b>${esc(dataPl(x.wystawienie))}</b></div>
      <div><span class="szary">Dzień płatności</span><b>${esc(dataPl(x.termin) || '-')}</b></div>
      <div><span class="szary">Netto</span><b>${zl(x.netto)}</b></div>
      <div><span class="szary">VAT</span><b>${zl(x.vat)}</b></div>
      <div><span class="szary">Brutto</span><b>${zl(x.brutto)}</b></div>
      ${x.oplacono ? `<div><span class="szary">Zapłacono (bank)</span><b>${esc(dataPl(x.oplacono))}</b></div>` : ''}
      ${x.tytul ? `<div class="szeroki"><span class="szary">Tytuł, pozycje</span><span>${esc(x.tytul)}</span></div>` : ''}
    </section>`;
  const akcjeDok = `<div class="akcje">
      ${d.oznaczone == null && d.stan !== 'polaczony' ? '<button id="lacz-weryf" data-karta>Przenieś do Do weryfikacji</button>' : ''}
      ${x.typ === 'reczna' ? `<a class="przycisk" href="#/platnosci/dodaj?id=${encodeURIComponent(czescRef(ref).ref)}">Edytuj płatność</a>` : ''}
      ${x.typ === 'reczna' && d.stan !== 'polaczony' && d.planowanie ? '<button id="lacz-usun">Usuń płatność</button>' : ''}</div>
      ${d.oznaczone != null ? `<div class="komunikat"><span>Ta pozycja jest w Do weryfikacji${d.oznaczone ? `: ${esc(d.oznaczone)}` : ''}. Połączyć ją możesz, a z listy zdejmiesz ją jako sprawdzoną.</span></div>` : ''}`;
  if (d.stan === 'polaczony') {
    return `${naglowek}${dok}<h2 class="sekcja">${ik('link')}Połączona z budżetem</h2>
      <div class="tabela-ramka niska"><table><thead><tr><th>Arkusz</th><th>Wiersz</th><th>Miesiąc</th><th class="liczba-kol">Netto</th><th class="liczba-kol">Brutto</th><th>Etap</th></tr></thead><tbody>
      ${d.platnosci.map(p => `<tr><td><a href="#/budzet/arkusz?id=${encodeURIComponent(p.arkusz_id)}">${esc(p.arkusz)}</a></td><td>${esc(p.w_kontrahent || p.w_komentarz || '')}</td><td>${esc(miesPelny(p.miesiac))}</td>
        <td class="liczba-kol">${zl(p.netto, false)}</td><td class="liczba-kol">${zl(p.brutto, false)}</td><td>${chipEtap(p.etap)}</td></tr>`).join('')}</tbody></table></div>
      <div class="akcje">${d.planowanie ? '<button class="glowny" id="lacz-odlacz">Odłącz od budżetu</button>' : ''}<span class="szary">Odłączenie: dokument wraca do Do połączenia, w komórkach wraca plan.</span></div>${akcjeDok}`;
  }
  if (d.stan === 'w_budzecie') {
    return `${naglowek}${dok}<div class="komunikat"><span>Ten dokument jest już w budżecie jako płatność z Budget Studio (ten sam numer albo przelew). Nie łącz go drugi raz.</span></div>${akcjeDok}`;
  }
  return `${naglowek}${dok}${akcjeDok}
    ${d.planowanie ? '' : '<div class="komunikat"><span>Planowanie w apce jest wyłączone, więc łączenie też (Budżet, Ustawienia budżetu). Podpowiedzi możesz przejrzeć.</span></div>'}
    <div class="lacz-kolumny">
      <section class="lacz-lewa"><h2 class="sekcja">${ik('lupa')}Plany do wyboru</h2>
        <input type="search" id="lacz-szukaj" placeholder="Szukaj komórki: arkusz, folder, kontrahent, komentarz, miesiąc (2026-11)" aria-label="Szukaj komórki budżetu">
        <p class="szary">Kolejność jak w BS: ten sam kontrahent, zbliżona kwota, bliski miesiąc, wcześniejsze połączenia. Tylko komórki z planem tego samego rodzaju i zgodnej podstawy.</p>
        <div id="lacz-podp"></div></section>
      <section class="lacz-prawa"><h2 class="sekcja">${ik('link')}Połącz z tymi komórkami</h2>
        <div id="lacz-wybrane"></div></section>
    </div>`;
};

function htmlPodpowiedzi(lista) {
  if (!lista.length) return `<p class="szary">${EKR.q ? 'Brak komórek z planem dla tej frazy.' : 'Brak planu, który pasuje. Wyszukaj komórkę albo dodaj w arkuszu plan (choćby 0) i wróć tutaj.'}</p>`;
  return `<div class="lacz-lista">${lista.map((c, i) => {
    const wybrana = EKR.wybrane.some(w => w.wiersz === c.wiersz && w.miesiac === c.miesiac);
    return `<div class="lacz-poz${wybrana ? ' wybrana' : ''}">
      <div class="lacz-poz-gl"><b>${esc(c.arkusz_nazwa)}</b> <span class="szary">${esc(c.folder)}</span><br>${esc(c.kontrahent || c.komentarz || c.przedmiot || 'wiersz')} · ${esc(miesPelny(c.miesiac))}${c.worek ? ' · <span class="chip neutral">worek</span>' : ''}${c.rzeczywistych ? ` · <span class="szary">${c.rzeczywistych} rzecz.</span>` : ''}
        <div class="pod-dlaczego">${esc(c.uzasadnienie || 'bez dopasowania kontrahenta i kwoty')}</div></div>
      <div class="lacz-poz-kw"><span class="szary">plan</span> ${zl(c.plan, false)}<br>${c.roznica ? `<span class="pod-roznica">różnica ${zl(c.roznica, false)}</span>` : '<span class="szary">równa</span>'}<br>${chipPewnosc(c.pewnosc)}</div>
      <div><button data-dodaj="${i}"${wybrana || !EKR.d.planowanie ? ' disabled' : ''}>${wybrana ? 'Wybrana' : 'Dodaj'} ${ik('strzalkaP')}</button></div></div>`;
  }).join('')}</div>`;
}

function rysujWybrane() {
  const x = EKR.d.dokument, w = EKR.wybrane;
  const suma = w.reduce((a, c) => a + (Number.isNaN(c.kwota) ? 0 : c.kwota), 0);
  const zostalo = x.kwota - suma, bledna = w.some(c => Number.isNaN(c.kwota) || c.kwota <= 0);
  const plan = w.reduce((a, c) => a + c.plan, 0);
  const mniejsza = w.some(c => !c.worek && c.kwota < c.plan), worek = w.some(c => c.worek);
  const ok = w.length && !zostalo && !bledna && EKR.d.planowanie;
  $('#lacz-wybrane').innerHTML = `${w.length ? `<div class="lacz-lista">${w.map((c, i) => `<div class="lacz-poz">
      <div class="lacz-poz-gl"><b>${esc(c.arkusz_nazwa)}</b><br>${esc(c.kontrahent || c.komentarz || c.przedmiot || 'wiersz')} · ${esc(miesPelny(c.miesiac))}${c.worek ? ' · <span class="chip neutral">worek</span>' : ''}
        <div class="pod-dlaczego">plan ${zl(c.plan)}${Number.isNaN(c.kwota) ? '' : ` · różnica ${zl(c.plan - c.kwota)}`}</div></div>
      <label class="pole lacz-kwota"><span>Kwota (${esc(jednostkaDok(x))})</span><input data-kwota="${i}" inputmode="decimal" value="${Number.isNaN(c.kwota) ? '' : zlWpis(c.kwota)}"></label>
      <div><button class="przycisk-ikona" data-usun="${i}" aria-label="Usuń komórkę">${ik('zamknij')}</button></div></div>`).join('')}</div>`
    : '<p class="szary">Dodaj komórkę z listy po lewej. Jedną płatność możesz rozdzielić na kilka komórek, także w różnych arkuszach.</p>'}
    <div class="lacz-sumy">
      <div><span class="szary">Kwota dokumentu</span><b>${zl(x.kwota)}</b></div>
      <div class="${zostalo ? 'minus' : 'plus'}"><span class="szary">Do rozliczenia</span><b>${zl(zostalo)}</b></div>
      <div><span class="szary">Różnica od planu</span><b>${w.length ? zl(plan - suma) : '-'}</b></div>
    </div>
    ${w.length && (mniejsza || worek) ? `<fieldset class="lacz-reszta"><legend>Co z resztą planu?</legend>
      <label><input type="radio" name="reszta" value=""${EKR.reszta === '' ? ' checked' : ''}> Jak w BS: plan pojedynczy znika w całości, worek zostaje otwarty na kolejne płatności</label>
      ${mniejsza ? `<label><input type="radio" name="reszta" value="zostaw"${EKR.reszta === 'zostaw' ? ' checked' : ''}> Zostaw resztę planu (dokument jest mniejszy niż plan; reszta czeka na kolejny dokument)</label>` : ''}
      <label><input type="radio" name="reszta" value="usun"${EKR.reszta === 'usun' ? ' checked' : ''}> Usuń resztę planu${worek ? ' i zamknij worek' : ''}</label></fieldset>` : ''}
    <div class="akcje"><button class="glowny" id="lacz-ok"${ok ? '' : ' disabled'}>Połącz z budżetem</button>
      ${w.length ? `<span class="szary">${zostalo ? 'Rozdziel całą kwotę dokumentu: Do rozliczenia musi wynosić 0,00 zł.' : bledna ? 'Każda komórka musi mieć kwotę większą od zera.' : 'Rzeczywista zastąpi plan w wybranych komórkach.'}</span>` : ''}</div>`;
  $('#lacz-wybrane').querySelectorAll('[data-kwota]').forEach(el => {
    el.onchange = () => { EKR.wybrane[+el.dataset.kwota].kwota = kwotaZTekstu(el.value); rysujWybrane(); };
  });
  $('#lacz-wybrane').querySelectorAll('[data-usun]').forEach(b => b.onclick = () => { EKR.wybrane.splice(+b.dataset.usun, 1); rysujWybrane(); rysujPodpowiedzi(); });
  $('#lacz-wybrane').querySelectorAll('[name="reszta"]').forEach(r => r.onchange = () => { EKR.reszta = r.value; });
  const b = $('#lacz-ok');
  if (b) b.onclick = async () => {
    const dane = { op: 'polacz', dokument: EKR.ref, czesci: EKR.wybrane.map(c => ({ wiersz: c.wiersz, miesiac: c.miesiac, kwota: c.kwota })),
      ...(EKR.reszta ? { reszta: EKR.reszta } : {}) };
    const opis = `Połączono z ${EKR.wybrane.length} ${liczebnik(EKR.wybrane.length, ['komórką', 'komórkami', 'komórkami'])}: różnica od planu ${zl(plan - suma)}.`;
    const ref = EKR.ref;
    if (!(await wyslijPolaczenie(dane))) return;
    location.hash = '#/platnosci/laczenie';
    setTimeout(() => komunikatAkcje(opis, [{ nazwa: 'Pokaż połączenie', akcja: () => { location.hash = `#/platnosci/polacz?ref=${encodeURIComponent(ref)}`; } },
      { nazwa: 'Cofnij', akcja: cofnijOstatni }]), 400);
  };
}

async function wyslijPolaczenie(dane) {
  const r = await wyslijBud(dane);
  if (!r.ok) { komunikat(r.blad, true); return false; }
  await sprawdzStan();
  return true;
}

function rysujPodpowiedzi() {
  const el = $('#lacz-podp');
  if (!el) return;
  el.innerHTML = htmlPodpowiedzi(EKR.lista || EKR.d.podpowiedzi);
  el.querySelectorAll('[data-dodaj]').forEach(b => b.onclick = () => {
    const c = (EKR.lista || EKR.d.podpowiedzi)[+b.dataset.dodaj];
    const reszta = EKR.d.dokument.kwota - EKR.wybrane.reduce((a, w) => a + (Number.isNaN(w.kwota) ? 0 : w.kwota), 0);
    EKR.wybrane.push({ ...c, kwota: Math.max(0, reszta) });
    rysujWybrane();
    rysujPodpowiedzi();
  });
}

function podepnijEkranLaczenia() {
  const x = EKR?.d?.dokument;
  if (!x) return;
  const odl = $('#lacz-odlacz');
  if (odl) odl.onclick = () => zmiana('bud', { op: 'odlacz', dokument: EKR.ref });
  const wer = $('#lacz-weryf');
  if (wer) wer.onclick = () => formularzAkcji('Przenieś do Do weryfikacji', 'Pozycja zniknie z Do połączenia, dopóki nie oznaczysz jej jako sprawdzonej.',
    pole('', 'Co sprawdzić (opcjonalnie)', '<input id="fa-powod" maxlength="200">'),
    async () => { const ok = await zmiana('do_weryfikacji', { ...czescRef(EKR.ref), powod: $('#fa-powod').value.trim() }); if (ok) location.hash = '#/platnosci/laczenie'; return ok; });
  const usun = $('#lacz-usun');
  if (usun) usun.onclick = async () => { if (await zmiana('bud', { op: 'rzeczywista', obiekt: { id: czescRef(EKR.ref).ref }, usun: true })) location.hash = '#/platnosci/laczenie'; };
  if (!$('#lacz-podp')) return;
  rysujPodpowiedzi();
  rysujWybrane();
  let t = null;
  $('#lacz-szukaj').oninput = e => {
    clearTimeout(t);
    t = setTimeout(async () => {
      EKR.q = e.target.value.trim();
      if (!EKR.q) { EKR.lista = null; return rysujPodpowiedzi(); }
      try { EKR.lista = (await api('laczenie/dokument', { ref: EKR.ref, q: EKR.q })).podpowiedzi; } catch (err) { return komunikat(err.message, true); }
      rysujPodpowiedzi();
    }, 250);
  };
}

// ---------- Dodaj płatność rzeczywistą (formularz jak w BS: faktura albo bez faktury) ----------
WIDOKI['platnosci/dodaj'] = async p => {
  let o = {};
  if (p.id) {
    try { o = (await api('laczenie/dokument', { ref: `reczna:${p.id}` })).dokument.dane || {}; } catch (e) { return `<div class="komunikat blad"><span>${esc(e.message)}</span></div>`; }
  }
  const fakt = (o.podstawa || 'Faktura') === 'Faktura';
  const dzis = dzisWpisu();
  setTimeout(() => podepnijFormularzRecznej(o, p.id));
  const sel = (id, opcje, v) => `<select id="${id}">${opcje.map(([k, n]) => `<option value="${esc(k)}"${String(v) === String(k) ? ' selected' : ''}>${esc(n)}</option>`).join('')}</select>`;
  return `<h1>${p.id ? 'Edytuj płatność rzeczywistą' : 'Dodaj płatność rzeczywistą'}</h1>
    <div class="pigulki"><a class="pigulka" href="#/platnosci/laczenie">${ik('strzalkaP')}Do połączenia</a><span class="szary">Formularz jak w Budget Studio: tylko płatności rzeczywiste (dokument już jest). Przyszłe płatności planujesz w arkuszu budżetu.</span></div>
    <div class="formularz rz-form">
      ${pole('', 'Rodzaj', sel('rz-rodzaj', [[-1, 'Obciążenie (koszt)'], [1, 'Wpływ (przychód)']], o.rodzaj ?? -1))}
      ${pole('', 'Podstawa', sel('rz-podstawa', [['Faktura', 'Faktura'], ['Bez faktury', 'Bez faktury']], o.podstawa || 'Faktura'))}
      ${pole('', 'Kontrahent', `<input id="rz-kontrahent" maxlength="200" value="${esc(o.kontrahent || '')}">`)}
      <label class="pole" data-fakt>Numer faktury<input id="rz-nr" maxlength="60" value="${esc(o.nr_dok || '')}"></label>
      <label class="pole" data-fakt>Numer wewnętrzny (opcjonalnie)<input id="rz-nrw" maxlength="60" value="${esc(o.nr_wewn || '')}"></label>
      ${pole('', 'Data wystawienia (nie z przyszłości)', `<input type="date" id="rz-wyst" max="${dzis}" value="${esc(o.wystawienie || dzis)}">`)}
      <label class="pole" data-fakt>Data sprzedaży<input type="date" id="rz-sprz" value="${esc(o.sprzedaz || '')}"></label>
      ${pole('', 'Dzień płatności (termin z dokumentu)', `<input type="date" id="rz-termin" value="${esc(o.termin || '')}">`)}
      ${pole('', 'Dzień realnej płatności (domyślnie = dzień płatności)', `<input type="date" id="rz-realny" value="${esc(o.realny || '')}">`)}
      <label class="pole"><span id="rz-netto-et">${fakt ? 'Netto' : 'Wartość'} (zł)</span><input id="rz-netto" inputmode="decimal" value="${o.netto != null ? zlWpis(o.netto) : ''}"></label>
      <label class="pole" data-fakt>Stawka VAT${sel('rz-stawka', [[23, '23 %'], [8, '8 %'], [5, '5 %'], [0, '0 % (także import usług, WNT, ZW)']], o.stawka ?? 23)}</label>
      <label class="pole" data-fakt>VAT (zł, policzony ze stawki; popraw przy fakturze z kilkoma stawkami)<input id="rz-vat" inputmode="decimal" value="${o.vat != null ? zlWpis(o.vat) : ''}"></label>
      <div class="pole" data-fakt><span>Brutto</span><b id="rz-brutto">-</b></div>
      ${pole('', 'Metoda płatności', `<input id="rz-metoda" maxlength="60" value="${esc(o.metoda || '')}" placeholder="np. Przelew, Karta">`)}
      ${pole('', 'Miesiąc księgowania (domyślnie miesiąc sprzedaży)', `<input type="month" id="rz-ksieg" value="${esc(o.ksiegowanie || '')}">`)}
      ${pole('', 'Księgowane (VAT, CIT, rentowność)', sel('rz-ksiegowane', [['1', 'tak'], ['', 'nie']], o.ksiegowane === false ? '' : '1'))}
      ${pole('', 'W cash flow', sel('rz-cf', [['1', 'tak'], ['', 'nie']], o.w_cashflow === false ? '' : '1'))}
      ${pole('', 'Komentarz (do 170 znaków)', `<input id="rz-kom" maxlength="170" value="${esc(o.komentarz || '')}">`)}
      ${pole('', 'Zapłacona poza bankiem: data (tylko wyjątki: karta w walucie, kompensata; zwykle opłacenie przyjdzie z banku)', `<input type="date" id="rz-opl" max="${dzis}" value="${esc(o.oplacona || '')}">`)}
    </div>
    <div class="akcje"><button class="glowny" id="rz-zapisz">${p.id ? 'Zapisz zmiany' : 'Dodaj i połącz z budżetem'}</button>${p.id ? '' : '<button id="rz-zapisz-sam">Dodaj do Do połączenia</button>'}</div>
    <p class="notka">Walidacje jak w BS: data wystawienia nie z przyszłości i najwyżej 5 lat wstecz, dzień realnej płatności faktury najwcześniej 45 dni przed wystawieniem (bez faktury: od dnia wystawienia). Wynagrodzenia wpisujesz listą płac (Budżet, Lista płac).</p>`;
};

function podepnijFormularzRecznej(o, id) {
  const pod = $('#rz-podstawa');
  if (!pod) return;
  const vatRecznie = { v: o.vat != null };
  const przelicz = () => {
    const fakt = pod.value === 'Faktura';
    document.querySelectorAll('[data-fakt]').forEach(el => { el.hidden = !fakt; });
    $('#rz-netto-et').textContent = `${fakt ? 'Netto' : 'Wartość'} (zł)`;
    const n = kwotaZTekstu($('#rz-netto').value);
    if (fakt && !vatRecznie.v && !Number.isNaN(n)) $('#rz-vat').value = zlWpis(Math.round(n * +$('#rz-stawka').value / 100));
    const v = kwotaZTekstu($('#rz-vat').value);
    $('#rz-brutto').textContent = Number.isNaN(n) ? '-' : zl(n + (fakt && !Number.isNaN(v) ? v : 0));
  };
  pod.onchange = przelicz;
  $('#rz-netto').oninput = przelicz;
  $('#rz-stawka').onchange = () => { vatRecznie.v = false; przelicz(); };
  $('#rz-vat').oninput = () => { vatRecznie.v = true; przelicz(); };
  $('#rz-termin').onchange = () => { if (!$('#rz-realny').value) $('#rz-realny').value = $('#rz-termin').value; };
  przelicz();
  const zbierz = () => {
    const fakt = pod.value === 'Faktura';
    const netto = kwotaZTekstu($('#rz-netto').value), vat = kwotaZTekstu($('#rz-vat').value);
    if (Number.isNaN(netto)) { komunikat('Podaj kwotę liczbą, np. 1 234,56.', true); return null; }
    if (!$('#rz-kontrahent').value.trim()) { komunikat('Podaj kontrahenta.', true); return null; }
    const ob = { id: id || nowyId('r'), rodzaj: +$('#rz-rodzaj').value, podstawa: pod.value, kontrahent: $('#rz-kontrahent').value.trim(),
      wystawienie: $('#rz-wyst').value, netto, metoda: $('#rz-metoda').value.trim(), ksiegowane: !!$('#rz-ksiegowane').value,
      w_cashflow: !!$('#rz-cf').value, komentarz: $('#rz-kom').value.trim() };
    for (const [k, el] of [['termin', '#rz-termin'], ['realny', '#rz-realny'], ['oplacona', '#rz-opl']]) if ($(el).value) ob[k] = $(el).value;
    if ($('#rz-ksieg').value) ob.ksiegowanie = $('#rz-ksieg').value;
    if (fakt) {
      ob.nr_dok = $('#rz-nr').value.trim();
      ob.nr_wewn = $('#rz-nrw').value.trim();
      if ($('#rz-sprz').value) ob.sprzedaz = $('#rz-sprz').value;
      ob.stawka = +$('#rz-stawka').value;
      if (!Number.isNaN(vat)) ob.vat = vat;
    }
    return ob;
  };
  const zapisz = async polacz => {
    const ob = zbierz();
    if (!ob) return;
    if (!(await wyslijPolaczenie({ op: 'rzeczywista', obiekt: ob }))) return;
    location.hash = polacz || id ? `#/platnosci/polacz?ref=${encodeURIComponent(`reczna:${ob.id}`)}` : '#/platnosci/laczenie';
    setTimeout(() => komunikatAkcje(id ? 'Zapisane.' : polacz ? 'Płatność dodana: wybierz plan, z którym ją połączyć.' : 'Płatność dodana do Do połączenia.',
      [{ nazwa: 'Cofnij', akcja: cofnijOstatni }]), 400);
  };
  $('#rz-zapisz').onclick = () => zapisz(true);
  const sam = $('#rz-zapisz-sam');
  if (sam) sam.onclick = () => zapisz(false);
}

// ---------- Karta płatności: zamiana planu na rzeczywistą, odłączenie, lista płac (hooki w htmlPlatnosci) ----------
function akcjeRzeczywistych({ platnosc: p, wiersz: w }, plan) {
  if (!plan || String(p.id).startsWith('sys:')) return '';
  const wyn = UMOWY[p.podstawa] || /^Umowa (o pracę|zlecenie|o dzieło) - /.test(p.podstawa || '') || w?.lista_plac;
  const btn = [];
  if (p.typ === 'plan' && wyn && (!p.skladowa || p.skladowa === 'osoba')) {
    btn.push(`<a class="przycisk" href="#/budzet/lista-plac?miesiac=${esc(p.miesiac)}">${ik('osoby')}Lista płac za ${esc(miesPelny(p.miesiac))}</a>`);
  } else if (p.typ === 'plan' && !WOREK.includes(p.podstawa) && !wyn && !p.skladowa) {
    const przyszly = p.wystawienie && p.wystawienie > dzisWpisu();
    btn.push(`<button data-zamien="${esc(p.id)}" data-karta${przyszly ? ` disabled title="Dostępne od dnia wystawienia planu (${esc(dataPl(p.wystawienie))}); wcześniej przesuń dzień wystawienia na karcie."` : ''}>Zmień na rzeczywistą</button>`);
  }
  if (p.typ !== 'plan' && p.dokument) {
    btn.push(`<button data-odlacz="${esc(p.dokument)}">Odłącz od budżetu</button>`);
    if (!p.dokument.startsWith('zamiana:') && !p.dokument.startsWith('lista:')) btn.push(`<a class="przycisk" href="#/platnosci/polacz?ref=${encodeURIComponent(p.dokument)}">Dokument i połączenie</a>`);
  }
  return btn.length ? `<div class="akcje">${btn.join('')}</div>` : '';
}

function podepnijRzeczywiste(k, dane) {
  k.querySelectorAll('[data-odlacz]').forEach(b => b.onclick = () => zapiszBud({ op: 'odlacz', dokument: b.dataset.odlacz }, { zostawKarte: true }));
  k.querySelectorAll('[data-zamien]').forEach(b => b.onclick = ev => {
    ev.stopPropagation();
    const x = dane.find(d => d.platnosc.id === b.dataset.zamien);
    if (x) kartaZamiany(x.platnosc);
  });
}

// B-LACZ-06: plan → rzeczywista w tej samej komórce; popraw dane i podaj numer dokumentu.
function kartaZamiany(p) {
  const fakt = String(p.podstawa).startsWith('Faktura');
  formularzAkcji('Zmień na rzeczywistą', `Plan ${esc(p.w_kontrahent || '')} za ${miesPelny(p.miesiac)} stanie się płatnością rzeczywistą w tej samej komórce (1:1, bez podziału). Komentarz planu przechodzi na rzeczywistą.`,
    `${pole('', fakt ? 'Numer faktury' : 'Numer dokumentu (opcjonalnie)', '<input id="fz-nr" maxlength="60">')}
     ${pole('', fakt ? 'Netto (zł)' : 'Kwota (zł)', `<input id="fz-netto" inputmode="decimal" value="${zlWpis(p.netto)}">`)}
     ${pole('', 'Kontrahent', `<input id="fz-kontrahent" maxlength="200" value="${esc(p.w_kontrahent || '')}">`)}
     ${pole('', 'Dzień wystawienia', `<input type="date" id="fz-wyst" max="${dzisWpisu()}" value="${esc(p.wystawienie || '')}">`)}
     ${pole('', 'Dzień płatności', `<input type="date" id="fz-termin" value="${esc(p.termin || '')}">`)}`, () => {
      const netto = kwotaZTekstu($('#fz-netto').value);
      if (Number.isNaN(netto)) { komunikat('Podaj kwotę liczbą, np. 1 234,56.', true); return false; }
      const obiekt = { nr_dok: $('#fz-nr').value.trim() };
      if (netto !== p.netto) obiekt.netto = netto;
      if ($('#fz-kontrahent').value.trim() !== (p.w_kontrahent || '')) obiekt.kontrahent = $('#fz-kontrahent').value.trim();
      if ($('#fz-wyst').value && $('#fz-wyst').value !== p.wystawienie) obiekt.wystawienie = $('#fz-wyst').value;
      if ($('#fz-termin').value && $('#fz-termin').value !== p.termin) obiekt.termin = $('#fz-termin').value;
      return zapiszBud({ op: 'zamien', plan: p.id, obiekt });
    });
}

// ---------- Lista płac za miesiąc (decyzja Mata 12, pola z 2026-10-20): kwoty od biura to dane rzeczywiste ----------
// Zapis wpisem „lista_plac” (nie zdarzeniem budżetu): działa przy wyłączonym planowaniu, ma pierwszeństwo przed kwotami
// z kopii BS i przetrwa przyjęcie kopii. Puste pole = brak na liście (zostaje kwota z BS albo planu), 0 = zero.
const POLA_LISTY = [
  ['osoba', 'Wypłata na konto'], ['us', 'PIT'], ['zus', 'ZUS (wszystkie składki)'], ['ppk_pracownik', 'PPK pracownika'],
  ['ppk_pracodawca', 'PPK pracodawcy'], ['pakiet', 'Pakiet medyczny'], ['potracenia', 'Potrącenia z wypłaty']];
const SKL_LISTY = Object.fromEntries(POLA_LISTY.slice(0, 3));

WIDOKI['budzet/lista-plac'] = async p => {
  let d;
  try { d = await api('lista-plac', { miesiac: p.miesiac || '' }); } catch (e) { return `<h1>Lista płac</h1><div class="komunikat blad"><span>${esc(e.message)}</span></div>`; }
  const dodane = (p.dodaj || '').split(',').filter(Boolean);
  const kand = d.kandydaci.filter(k => dodane.includes(k.id)).map(k => ({ wiersz: k.id, kontrahent: k.kontrahent, komentarz: k.komentarz,
    podstawa: k.podstawa, arkusz: k.arkusz, arkusz_id: '', umowa: false, skladowe: ['osoba', 'us', 'zus'], plan: {}, rzeczywiste: {}, wpisane: {},
    bs: {}, z_listy: false, z_kopii: false, mozna: true, przelewy: [], dodany: true }));
  const osoby = [...d.osoby.filter(o => o.mozna || o.z_listy), ...kand];
  setTimeout(() => podepnijListePlac(d, osoby));
  const mies = [...new Set([d.miesiac, ...d.miesiace])].sort().reverse();
  const komorka = (o, k) => {
    if (o.umowa && ['osoba', 'us', 'zus'].includes(k) && !o.skladowe.includes(k)) return '<td class="liczba-kol szary">-</td>';
    const wart = o.wpisane[k];
    const pod = SKL_LISTY[k] ? (o.bs[k] ?? o.plan[k]) : null;
    return `<td class="liczba-kol"><input class="lp-kwota${SKL_LISTY[k] ? '' : ' waska'}" data-lp="${esc(o.wiersz)}" data-s="${k}" inputmode="decimal"
      value="${wart == null ? '' : zlWpis(wart)}" placeholder="${pod != null ? zlWpis(pod) : ''}"${o.mozna || o.z_listy ? '' : ' disabled'}>
      ${SKL_LISTY[k] && o.bs[k] != null ? `<span class="lp-bs" title="kwota z kopii Budget Studio (estymacja)">BS ${zl(o.bs[k], false)}</span>` : ''}</td>`;
  };
  const stan = o => o.z_listy ? '<span class="chip plus">z listy płac</span>' : o.z_kopii ? '<span class="chip ostrzezenie">do wpisania (kwoty z BS)</span>'
    : o.dodany ? '<span class="chip niebieski">nowy na liście</span>'
    : !Object.keys(o.plan).length ? '<span class="chip neutral">brak planu</span>' : o.termin_wyplaty && o.termin_wyplaty < d.dzien_stanu
      ? '<span class="chip ostrzezenie">wypłata minęła</span>' : '<span class="chip niebieski">estymacja</span>';
  const sumaBank = l => l.reduce((a, x) => a + x.kwota, 0);
  const ppk = d.ppk;
  const wierszePpk = d.kandydaci.concat(ppk.wiersz && !d.kandydaci.some(k => k.id === ppk.wiersz) ? [{ id: ppk.wiersz, kontrahent: ppk.wiersz, komentarz: '', arkusz: '' }] : []);
  const roznica = v => v == null ? '-' : `<span class="${v > 0 ? 'minus' : v < 0 ? 'plus' : ''}">${zl(v, false)}</span>`;
  return `<h1>Lista płac za ${esc(miesPelny(d.miesiac))}</h1>
    <div class="pigulki"><label class="pigulka miekka">Miesiąc <select id="lp-mies">${mies.map(m => `<option value="${m}"${m === d.miesiac ? ' selected' : ''}>${esc(miesPelny(m))}</option>`).join('')}</select></label>
      <span class="szary">Kwoty z listy płac od biura to dane rzeczywiste: zastępują estymację z arkusza i kwoty z kopii Budget Studio (w BS są liczone z podziału procentowego). Działa też przy wyłączonym planowaniu. Przelew z banku tylko podpowiada i oznacza opłacenie.</span></div>
    ${d.ostrzezenia.map(o => `<div class="komunikat"><span>${esc(o.opis)}</span></div>`).join('')}
    <div class="tabela-ramka niska"><table class="lp-tabela"><thead><tr><th>Osoba</th><th>Stan</th><th>Data wypłaty</th>
      ${POLA_LISTY.map(([, n]) => `<th class="liczba-kol">${esc(n)}</th>`).join('')}<th class="liczba-kol">Koszt pracodawcy</th><th class="liczba-kol">Różnica z BS</th><th class="liczba-kol">Przelew wypłaty</th></tr></thead><tbody>
      ${osoby.map(o => `<tr data-wiersz="${esc(o.wiersz)}"><td><b>${esc(o.kontrahent || o.komentarz)}</b><br><span class="szary">${esc(o.podstawa)}${o.arkusz_id ? ` · <a href="#/budzet/arkusz?id=${encodeURIComponent(o.arkusz_id)}">${esc(o.arkusz)}</a>` : ` · ${esc(o.arkusz || '')}`}</span>
          ${o.ostatnia ? `<br><span class="szary">ostatnia lista: ${zl(o.ostatnia.razem, false)} (${esc(miesPelny(o.ostatnia.miesiac))})</span>` : ''}</td>
        <td>${stan(o)}</td><td><input type="date" class="lp-data" data-lp="${esc(o.wiersz)}" value="${esc(o.data_wyplaty || '')}"${o.mozna || o.z_listy ? '' : ' disabled'}></td>
        ${POLA_LISTY.map(([k]) => komorka(o, k)).join('')}<td class="liczba-kol" data-razem="${esc(o.wiersz)}">-</td>
        <td class="liczba-kol">${roznica(o.roznica_bs)}${o.bs_razem != null ? `<span class="lp-bs">BS razem ${zl(o.bs_razem, false)}</span>` : ''}</td>
        <td class="liczba-kol">${o.przelewy.length ? o.przelewy.map(x => `${zl(x.kwota, false)}<br><span class="szary">${esc(dataPl(x.data))}</span>`).join('<br>') : '<span class="szary">brak</span>'}</td></tr>`).join('')
        || '<tr><td colspan="13" class="szary">Brak wierszy wynagrodzeń z planem albo z kwotami z BS w tym miesiącu (umowa o pracę, zlecenie, dzieło albo wiersz bez faktury dodany do listy).</td></tr>'}
      </tbody><tfoot><tr><td colspan="3">Przelewy z banku za miesiąc wypłaty: PIT-4 ${d.bank.us.length ? zl(sumaBank(d.bank.us)) : 'brak'}, ZUS ${d.bank.zus.length ? zl(sumaBank(d.bank.zus)) : 'brak'}</td>
        ${POLA_LISTY.map(([k]) => `<td class="liczba-kol" data-suma="${k}">-</td>`).join('')}<td class="liczba-kol" data-suma="razem">-</td><td></td><td></td></tr></tfoot></table></div>
    <p class="notka">Koszt pracodawcy = wypłata + ZUS + PIT + PPK pracownika i pracodawcy + pakiet medyczny + potrącenia (potrącenie, np. Luxmed, jest częścią wynagrodzenia brutto). Pakiet i potrącenia nie są osobną płatnością: opłaca je faktura za pakiet medyczny, która już jest w budżecie, więc nic nie liczy się dwa razy. Terminy: wypłata wg daty z listy, ZUS i PPK do 15., PIT do 20. dnia miesiąca po wypłacie.</p>
    <h2 class="sekcja">${ik('kalendarz')}PPK z tej listy</h2>
    <div class="lp-ppk"><label>Zbiorczy wiersz PPK w budżecie <select id="lp-ppk-w"><option value="">bez wiersza (PPK tylko w koszcie pracodawcy)</option>${wierszePpk.map(k => `<option value="${esc(k.id)}"${k.id === ppk.wiersz ? ' selected' : ''}>${esc(k.kontrahent || '')}${k.komentarz ? ` · ${esc(k.komentarz)}` : ''}${k.arkusz ? ` (${esc(k.arkusz)})` : ''}</option>`).join('')}</select></label>
      <label>Komórka BS do zastąpienia (miesiąc przelewu) <input type="month" id="lp-ppk-m" value="${esc(ppk.miesiac || '')}"></label>
      <label>Termin przelewu <input type="date" id="lp-ppk-t" value="${esc(ppk.termin || '')}"></label>
      <span class="szary">W tej komórce BS ma ${ppk.bs != null ? zl(ppk.bs) : ppk.plan != null ? `plan ${zl(ppk.plan)}` : 'nic'}${ppk.wpisane ? `, z listy ${zl(ppk.lista)}, różnica ${roznica(ppk.roznica)}` : ''}. PPK z listy stoi w budżecie w miesiącu listy (${esc(miesPelny(d.miesiac))}), jak ZUS i PIT: tam liczy się koszt, rentowność i wynik; termin przelewu (cash flow) bez zmian. BS trzyma PPK wg miesiąca przelewu, więc lista zastępuje tę komórkę BS, żeby nic się nie dublowało.</span></div>
    ${d.ppk_mapa.length ? `<details class="notka"><summary>Mapa PPK: miesiąc w budżecie i komórka BS</summary><p class="szary">Rozjazd z BS w PPK to układ miesięcy, nie kwota: w apce PPK stoi w miesiącu listy, w BS w miesiącu przelewu. Różnica kwot to tylko lista płac kontra estymacja BS.</p><div class="tabela-ramka niska"><table><thead><tr><th>W budżecie</th><th>Lista płac za</th><th>Komórka BS (przelew)</th><th>Termin</th><th class="liczba-kol">BS</th><th class="liczba-kol">Z listy</th><th class="liczba-kol">Różnica</th></tr></thead><tbody>
      ${d.ppk_mapa.map(x => `<tr><td>${esc(miesPelny(x.budzet || x.komorka))}</td><td>${x.lista ? esc(miesPelny(x.lista)) : '<span class="szary">bez listy, kwota z BS</span>'}</td><td>${x.lista ? `${esc(miesPelny(x.komorka))}${x.przesuniecie ? ` <span class="szary">(+${x.przesuniecie} mies.)</span>` : ''}` : '<span class="szary">ta sama</span>'}</td><td>${x.termin ? esc(dataPl(x.termin)) : ''}</td>
        <td class="liczba-kol">${x.bs != null ? zl(x.bs, false) : '-'}</td><td class="liczba-kol">${x.z_listy != null ? zl(x.z_listy, false) : '-'}</td><td class="liczba-kol">${roznica(x.roznica)}</td></tr>`).join('')}</tbody></table></div></details>` : ''}
    <h2 class="sekcja">${ik('weryfikuj')}Uwaga do listy</h2>
    <textarea id="lp-uwaga" class="lp-uwaga" maxlength="500" placeholder="np. różnica ZUS z biurem do wyjaśnienia">${esc(d.uwaga || '')}</textarea>
    <div class="akcje"><button class="glowny" id="lp-zapisz">Zapisz listę płac</button>${d.z_listy ? '<button id="lp-usun">Usuń listę za ten miesiąc (wraca BS albo estymacja)</button>' : ''}
      <span class="szary">Puste pole = brak na liście: zostaje kwota z BS albo planu. Wpisz 0, gdy na liście jest zero.</span></div>
    ${d.kandydaci.length ? `<h2 class="sekcja">${ik('plus')}Wiersz wynagrodzenia bez umowy</h2>
      <p class="notka">Np. powołanie zarządu zapisane w arkuszu jako „Bez faktury” jedną kwotą brutto. Lista płac rozbije ją na wypłatę na konto, zdrowotną (ZUS) i PIT; suma kosztu się nie zmienia.</p>
      <div class="akcje"><select id="lp-kand">${d.kandydaci.map(k => `<option value="${esc(k.id)}">${esc(k.kontrahent || k.komentarz || k.id)}${k.komentarz ? ` · ${esc(k.komentarz)}` : ''} (${esc(k.arkusz)})</option>`).join('')}</select><button id="lp-kand-ok">Dodaj do tej listy</button></div>` : ''}
    ${d.koszt.length ? `<h2 class="sekcja">${ik('osoby')}Koszt pracy z list płac</h2><div class="tabela-ramka niska"><table><thead><tr><th>Lista za</th><th class="liczba-kol">Koszt pracodawcy</th><th class="liczba-kol">W budżecie (wypłaty, ZUS, PIT, PPK)</th><th class="liczba-kol">Przez fakturę za pakiet</th><th class="liczba-kol">Zastąpione kwoty BS</th></tr></thead><tbody>
      ${d.koszt.map(x => `<tr><td><a href="#/budzet/lista-plac?miesiac=${x.miesiac}">${esc(miesPelny(x.miesiac))}</a></td><td class="liczba-kol">${zl(x.koszt_pracodawcy, false)}</td><td class="liczba-kol">${zl(x.platnosci, false)}</td><td class="liczba-kol">${zl(x.przez_fakture, false)}</td><td class="liczba-kol">${zl(x.bs_zastapione, false)}</td></tr>`).join('')}</tbody></table></div>` : ''}`;
};

function podepnijListePlac(d, osoby) {
  const s = $('#lp-mies');
  if (!s) return;
  s.onchange = () => { location.hash = `#/budzet/lista-plac?miesiac=${s.value}`; };
  const wartosc = el => el.value.trim() === '' ? null : kwotaZTekstu(el.value);
  const sumuj = () => {
    const sumy = Object.fromEntries(POLA_LISTY.map(([k]) => [k, 0]));
    document.querySelectorAll('tr[data-wiersz]').forEach(tr => {
      let r = 0;
      tr.querySelectorAll('.lp-kwota').forEach(el => { const v = wartosc(el); if (v != null && !Number.isNaN(v)) { r += v; sumy[el.dataset.s] += v; } });
      tr.querySelector('[data-razem]').textContent = r ? zl(r, false) : '-';
    });
    for (const k of Object.keys(sumy)) $(`[data-suma="${k}"]`).textContent = zl(sumy[k], false);
    $('[data-suma="razem"]').textContent = zl(Object.values(sumy).reduce((a, x) => a + x, 0), false);
  };
  document.querySelectorAll('.lp-kwota').forEach(el => { el.oninput = sumuj; });
  sumuj();
  $('#lp-zapisz').onclick = () => {
    const poz = {};
    for (const el of document.querySelectorAll('.lp-kwota:not(:disabled)')) {
      const v = wartosc(el);
      if (v != null && (Number.isNaN(v) || v < 0)) return komunikat('Kwoty wpisz liczbą od zera, np. 6 716,06.', true);
      const x = (poz[el.dataset.lp] ||= { wiersz: el.dataset.lp });
      if (v != null) x[el.dataset.s] = v;
    }
    for (const el of document.querySelectorAll('.lp-data:not(:disabled)')) if (el.value && poz[el.dataset.lp]) poz[el.dataset.lp].data_wyplaty = el.value;
    const pozycje = Object.values(poz).filter(x => POLA_LISTY.some(([k]) => x[k] != null));
    if (!pozycje.length) return komunikat('Wpisz kwoty z listy płac co najmniej jednej osoby.', true);
    const dane = { miesiac: d.miesiac, pozycje };
    const w = $('#lp-ppk-w').value;
    if (w) dane.ppk = { wiersz: w, ...($('#lp-ppk-m').value ? { miesiac: $('#lp-ppk-m').value } : {}), ...($('#lp-ppk-t').value ? { termin: $('#lp-ppk-t').value } : {}) };
    const u = $('#lp-uwaga').value.trim();
    if (u) dane.uwaga = u;
    zmiana('lista_plac', dane);
  };
  const u = $('#lp-usun');
  if (u) u.onclick = () => zmiana('lista_plac', { miesiac: d.miesiac, usun: true });
  const k = $('#lp-kand-ok');
  if (k) k.onclick = () => {
    const juz = osoby.filter(o => o.dodany).map(o => o.wiersz);
    location.hash = `#/budzet/lista-plac?miesiac=${d.miesiac}&dodaj=${encodeURIComponent([...juz, $('#lp-kand').value].join(','))}`;
  };
}

// ---------- Worek na karcie komórki: podpięte rzeczywiste, niezrealizowane plany tygodniowe, ręczne zamknięcie ----------
function htmlWorka(d) {
  const w = d.worek;
  if (!w) return '';
  const rz = d.platnosci.map(x => x.platnosc).filter(p => p.typ !== 'plan');
  const lista = rz.length ? `<ul class="lista">${rz.map(p => `<li>${esc(dataPl(p.wystawienie) || '')} ${esc(p.w_kontrahent || '')} <b>${zl(p.netto)}</b>${p.dokument && !p.dokument.startsWith('worek:') ? ` <a href="#/platnosci/polacz?ref=${encodeURIComponent(p.dokument)}">dokument</a>` : ''}</li>`).join('')}</ul>` : '';
  const stan = w.zamkniety ? '<span class="chip neutral">zamknięty</span>' : '<span class="chip niebieski">otwarty</span>';
  const akcja = !d.planowanie ? '' : w.zamkniety
    ? `<button data-worek="otworz">Otwórz worek</button><span class="szary">Wrócą plany tygodniowe na resztę kwoty komórki.</span>`
    : w.rzeczywistych ? `<button data-worek="zamknij">Zamknij worek</button><span class="szary">Niezrealizowane plany tygodniowe (${zl(w.plany)}) znikną, komórka = suma rzeczywistych.</span>` : '';
  return `<section class="lacz-worek"><h3>Worek ${stan}</h3>
    <p class="szary">Rzeczywiste: ${w.rzeczywistych} na ${zl(d.rzeczywiste)} · niezrealizowane plany tygodniowe: ${w.planow} na ${zl(w.plany)}.
      Worek przyjmuje kolejne płatności z Do połączenia, dopóki go nie zamkniesz.</p>${lista}
    ${akcja ? `<div class="akcje">${akcja}</div>` : ''}</section>`;
}

function podepnijWorek(k, d) {
  k.querySelectorAll('[data-worek]').forEach(b => b.onclick = () => zapiszBud(b.dataset.worek === 'zamknij'
    ? { op: 'zamknij_worek', wiersz: d.wiersz.id, miesiac: d.miesiac }
    : { op: 'odlacz', dokument: `worek:${d.wiersz.id}:${d.miesiac}` }, { zostawKarte: true }));
}

// ---------- Ostrzeżenia kosztu pracy (decyzja 12) i Do połączenia: pulpit i arkusz ----------
const htmlOstrzezen = (lista, ile) => {
  if (!lista.length && !ile) return '';
  const rodz = {};
  lista.forEach(o => (rodz[o.tytul] ||= []).push(o));
  return `<div class="komunikat lacz-ostrz"><span>${ile ? `<a href="#/platnosci/laczenie">Do połączenia: ${ile} ${liczebnik(ile, ['pozycja', 'pozycje', 'pozycji'])}</a>. ` : ''}${Object.entries(rodz).map(([t, xs]) =>
    `<a href="#/budzet/lista-plac?miesiac=${esc(xs[0].miesiac)}">${esc(t)}: ${xs.length}</a>`).join(' · ')}${lista.length ? ` <span class="szary">(${esc(lista[0].opis)})</span>` : ''}</span></div>`;
};

(() => {
  const stary = WIDOKI.pulpit;
  WIDOKI.pulpit = async function (p) {
    // najpierw dane, potem ekran: ekran podpina przyciski w setTimeout, który musi wypaść po wstawieniu HTML
    const o = await api('ostrzezenia').catch(() => null);
    const html = await stary.call(this, p);
    // ostrzeżenia listy płac pokazuje na pulpicie kafel „Lista płac do wpisania” (pakiet 11, pulpit.js); tu zostaje Do połączenia
    const pas = o ? htmlOstrzezen(typeof pulpitDodatki === 'function' ? [] : o.ostrzezenia, o.do_polaczenia) : '';
    return pas ? html.replace(/(<\/h1>)/, `$1${pas}`) : html;
  };
  const ark = WIDOKI['budzet/arkusz'];
  WIDOKI['budzet/arkusz'] = async function (p) {
    const o = await api('ostrzezenia').catch(() => null);   // przed ekranem, jak wyżej
    const html = await ark.call(this, p);
    setTimeout(() => {
      if (!o || !ARK?.d?.wiersze) return;
      const ids = new Set(ARK.d.wiersze.map(w => w.id));
      const moje = o.ostrzezenia.filter(x => ids.has(x.wiersz));
      const pas = htmlOstrzezen(moje, 0);
      const h = document.querySelector('#widok h1') || document.querySelector('h1');
      if (pas && h && !document.querySelector('.lacz-ostrz')) h.insertAdjacentHTML('afterend', pas);
    });
    return html;
  };
})();

// ---------- Cash flow: masowe „Odłącz od budżetu” dla płatności połączonych w apce w bieżącym wycinku ----------
let CF_POZ = [];
function podepnijCfLaczenie(poz) {
  CF_POZ = poz;
  const nag = document.querySelector('.cf-lista-naglowek');
  if (!nag || nag.querySelector('#cf-odlacz')) return;
  nag.insertAdjacentHTML('beforeend', `<button class="przycisk miekki" id="cf-odlacz" data-karta>${ik('rozlacz')}Odłącz od budżetu</button>`);
  $('#cf-odlacz').onclick = async () => {
    let mapa, poz;
    try {
      mapa = await api('laczenie/polaczone');
      poz = typeof CF_POZ === 'function' ? await CF_POZ() : CF_POZ;   // pakiet 9: cały wycinek z serwera
    } catch (e) { return komunikat(e.message, true); }
    const dok = {};
    for (const x of poz) {   // płatności budżetu: plan albo rzeczywista (podział z pakietu 9)
      const id = x.zrodlo || x.id;
      if ((x.typ === 'plan' || x.typ === 'rzeczywista') && mapa[id]) (dok[mapa[id]] ||= []).push(x);
    }
    const refs = Object.keys(dok);
    if (!refs.length) return komunikat('W tym wycinku nie ma płatności połączonych w apce (z Do połączenia, zamiany planu albo listy płac).');
    formularzAkcji('Odłącz od budżetu', `Płatności połączone w apce w tym wycinku: ${refs.length}. Zaznaczone wrócą do Do połączenia (lista płac i zamiana planu: wraca plan), w komórkach znów pojawią się plany. Jedna seria, cofasz całość.`,
      `<div class="lacz-cf-lista">${refs.map((r, i) => { const x = dok[r][0]; return `<label><input type="checkbox" data-cf-ref="${i}" checked> ${esc(dataPl(x.data))} · ${esc(x.kontrahent || x.tytul || '')} · ${esc(x.arkusz || '')} <b>${zl(dok[r].reduce((a, y) => a + y.kwota, 0))}</b></label>`; }).join('')}</div>`,
      () => {
        const wyb = [...document.querySelectorAll('[data-cf-ref]:checked')].map(el => refs[+el.dataset.cfRef]);
        if (!wyb.length) return komunikat('Zaznacz co najmniej jedną płatność.', true);
        return zmiana('bud', { op: 'seria', operacje: wyb.map(d => ({ op: 'odlacz', dokument: d })) });
      });
  };
}

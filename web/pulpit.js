'use strict';
// Pakiet 11, pulpit: baner alertów umów (APK-BRAK-03, BL-02), kafel rachunku VAT (ile dołożyć z rachunku głównego, PRZ-03),
// kafel „Lista płac do wpisania” (ostrzeżenia kosztu pracy z pakietu 5, GET /api/ostrzezenia; bez tego adresu kafla nie ma),
// kafel umów i licznik planów nieaktualnych w pasku „Porządek w danych” (B-INNE-03, rytuał tygodniowy).
// app.js woła pulpitDodatki() po narysowaniu pulpitu; dane pobierane w tle, pulpit nie czeka.
(() => {

async function odczyt(sciezka) {
  const r = await fetch(`/api/${sciezka}`);
  if (!r.ok) { const e = new Error(`Błąd ${r.status}`); e.status = r.status; throw e; }
  return r.json();
}

Object.assign(POMOC, {
  alerty_umow: { tytul: 'Alerty umów', krotko: 'Umowy, przy których trzeba coś zrobić: termin wypowiedzenia blisko albo minął, brak umowy, plany po końcu umowy.',
    co: 'Czerwone: termin minął. Żółte: do terminu zostało mniej dni, niż ustawiłeś w umowie (domyślnie 30). Do tego klienci z planami wpływów w budżecie bez umowy w rejestrze i umowy na czas określony, po których końcu budżet ma jeszcze plany wpływów.',
    skad: 'Rejestr umów (wpisujesz Ty na karcie klienta albo w Rejestrze umów) i plany w arkuszach klienta.',
    jak: 'Liczone od dnia stanu, czyli ostatniego dnia w eksporcie z ING.',
    zrob: 'Kliknij klienta, żeby otworzyć jego kartę: tam poprawisz umowę albo zdecydujesz o przedłużeniu.' },
  rachunek_vat: { tytul: 'Rachunek VAT', krotko: 'Ile wynosi najbliższy VAT do zapłaty i ile trzeba dołożyć z rachunku głównego.',
    co: 'VAT płacimy najpierw z rachunku VAT. Gdy na nim jest za mało, resztę dokłada rachunek główny. Kafel pokazuje kwotę, termin i brakującą część.',
    skad: 'Prognoza VAT z budżetu (Podatki i ZUS), saldo rachunku VAT z ING i wpływy z podzielonej płatności przewidziane do terminu.',
    jak: 'Saldo rachunku VAT w dniu przelewu = saldo dziś plus VAT z wpłat klientów płacących podzieloną płatnością minus wcześniejsze przelewy z tego rachunku.',
    zrob: 'Gdy kafel jest żółty, przed terminem zostaw na rachunku głównym kwotę „dołóż”. Szczegóły w Budżet, Podatki i ZUS.' },
  lista_plac: { tytul: 'Lista płac do wpisania', krotko: 'Miesiące, za które nie wpisałeś jeszcze kwot z listy płac od biura.',
    co: 'Plany wynagrodzeń są zawyżonym szacunkiem. Prawdziwe kwoty (wypłata, PIT, ZUS) wpisujesz ręcznie z listy płac. Kafel liczy miesiące, które minęły bez wpisu, szacunki niższe niż ostatnia prawdziwa kwota i różnice między wpisem a przelewem.',
    skad: 'Plany umów w budżecie, wpisy listy płac i przelewy z ING.',
    jak: 'Dopóki listy płac nie wpiszesz, plan zostaje w cash flow.',
    zrob: 'Kliknij kafel i wpisz listę płac za wskazany miesiąc.' },
  plany_nieaktualne: { tytul: 'Plany nieaktualne', krotko: 'Plany, którym minął dzień wystawienia albo płatności, a nie ma do nich dokumentu.',
    co: 'Każdy taki plan to pytanie: faktura nie przyszła, przyszła z inną datą albo plan jest już nieaktualny.',
    skad: 'Plany z budżetu porównane z dniem stanu (ostatni dzień w eksporcie z ING).',
    jak: 'Jak w Budget Studio: plan jest nieaktualny, gdy minął jego dzień wystawienia, płatności albo realnej płatności.',
    zrob: 'Raz w tygodniu przejdź listę: przesuń plan, przenieś kwotę na inny miesiąc albo usuń plan.' },
});

// Chip statusu jak chipStatus z app.js, ale z własną etykietą (tamte etykiety mówią o celach finansowych)
const ZNAK = { dobrze: '✓', uwaga: '!', zle: '✕', brak: '?' };
const chipSt = (st, etykieta, tekst) => `<div class="chip-st ${st}"><b aria-hidden="true">${ZNAK[st]}</b><span>${esc(etykieta)}</span><small>${esc(tekst)}</small></div>`;
const liczba = (n, formy) => `${n} ${n === 1 ? formy[0] : [2, 3, 4].includes(n % 10) && ![12, 13, 14].includes(n % 100) ? formy[1] : formy[2]}`;
const dni = d => d == null ? '' : d < 0 ? `${-d} dni temu` : d === 0 ? 'dziś' : `za ${d} dni`;
const linkKlienta = n => `#/budzet/klient?nazwa=${encodeURIComponent(n)}`;

function banerUmow(alerty) {
  const pilne = alerty.filter(a => a.rodzaj !== 'brak umowy');
  const brak = alerty.filter(a => a.rodzaj === 'brak umowy');
  if (!alerty.length) return '';
  const opis = a => {
    if (a.rodzaj === 'plany po końcu') return 'plany wpływów po końcu umowy';
    const ost = String(a.co || '').startsWith('ostatni dzień');
    if (a.rodzaj === 'minął') return `${ost ? 'minął ostatni dzień na wypowiedzenie' : 'umowa wygasła'} ${dataPl(a.data)}`;
    return `${ost ? 'ostatni dzień na wypowiedzenie' : 'umowa wygasa'} ${dataPl(a.data)} (${dni(a.dni)})`;
  };
  const pozycje = pilne.slice(0, 4).map(a => `<a class="${a.rodzaj === 'minął' ? 'minus' : ''}" href="${linkKlienta(a.klient)}"><b>${esc(a.klient)}</b>: ${esc(opis(a))}</a>`);
  if (pilne.length > 4) pozycje.push(`<a href="#/budzet?stan=decyzja">i ${pilne.length - 4} więcej</a>`);
  if (brak.length) pozycje.push(`<a href="#/budzet?stan=brak%20umowy" title="${esc(brak.map(a => a.klient).join(', '))}">${liczba(brak.length, ['klient', 'klientów', 'klientów'])} z planami wpływów bez umowy</a>`);
  return `<div class="baner baner-umow${pilne.some(a => a.rodzaj === 'minął') ? ' pilny' : ''}">${ik('dokument')}<b>Umowy</b> ${pytajnik('alerty_umow')} ${pozycje.join('<span class="szary">·</span>')}</div>`;
}

function kafelVat(pod) {
  const r = pod?.rachunek_vat;
  if (!r || r.brak_danych) return '';
  const v = r.vat_najblizszy;
  if (!v) {
    return `<a class="kafel-st dobrze" href="#/budzet/podatki"><div class="tytul">VAT do zapłaty ${pytajnik('rachunek_vat')}</div><div class="wartosc">0,00 zł</div>
      ${chipSt('dobrze', 'w normie', 'brak przelewu VAT w najbliższych 13 tygodniach')}<div class="dop">na rachunku VAT ${zl(r.saldo_start)}</div></a>`;
  }
  const dolozyc = -v.z_glownego;
  const st = dolozyc > 0 ? 'uwaga' : 'dobrze';
  return `<a class="kafel-st ${st}" href="#/budzet/podatki"><div class="tytul">VAT do zapłaty ${dataPl(v.data)} ${pytajnik('rachunek_vat')}</div>
    <div class="wartosc">${zl(-v.kwota)}</div>
    ${chipSt(st, dolozyc > 0 ? 'dołóż z głównego' : 'w normie', dolozyc > 0 ? `${zl(dolozyc)} przed terminem` : 'rachunek VAT wystarczy')}
    <div class="dop">na rachunku VAT w dniu przelewu ${zl(v.saldo_przed)}, z niego pójdzie ${zl(-v.z_rachunku_vat)}${dolozyc > 0 ? `, z głównego ${zl(dolozyc)}` : ''}</div></a>`;
}

// Kształt odpowiedzi GET /api/ostrzezenia (pakiet 5), opisany w README: {ostrzezenia: [{rodzaj, osoba, miesiac, opis, kwota, link}]};
// rodzaj: „lista_plac” (miesiąc minął, lista płac niewpisana), „estymacja” (szacunek niższy niż ostatnia kwota), „roznica_bank”.
async function listaPlac() {
  try {
    const d = await odczyt('ostrzezenia');
    const lista = Array.isArray(d) ? d : d.ostrzezenia;
    return Array.isArray(lista) ? lista : null;
  } catch (e) {
    return null;   // 404: pakiet 5 jeszcze nie scalony; inny błąd też nie psuje pulpitu
  }
}

function kafelListyPlac(lista) {
  if (!lista) return '';
  const niewpisane = lista.filter(x => x.rodzaj === 'lista_plac');
  const inne = lista.filter(x => x.rodzaj !== 'lista_plac');
  const miesiace = [...new Set(niewpisane.map(x => x.miesiac).filter(Boolean))].sort();
  const st = niewpisane.length ? 'zle' : inne.length ? 'uwaga' : 'dobrze';
  const link = (niewpisane[0] || inne[0])?.link || '#/platnosci/do-weryfikacji';
  const opis = niewpisane.length ? `${miesiace.length || niewpisane.length} ${miesiace.length === 1 ? 'miesiąc' : 'mies.'} bez listy płac`
    : inne.length ? `${inne.length} do sprawdzenia` : 'wszystkie listy płac wpisane';
  const szczeg = [...niewpisane, ...inne].slice(0, 3).map(x => `${x.miesiac ? miesPelny(x.miesiac) + ': ' : ''}${x.osoba || ''}${x.opis ? ` (${x.opis})` : ''}`).join('; ');
  return `<a class="kafel-st ${st}" href="${esc(link)}"><div class="tytul">Lista płac do wpisania ${pytajnik('lista_plac')}</div>
    <div class="wartosc">${niewpisane.length || inne.length || 0}</div>${chipSt(st, { zle: 'do wpisania', uwaga: 'do sprawdzenia', dobrze: 'w normie' }[st], opis)}<div class="dop">${esc(szczeg || 'kwoty z listy płac od biura wpisujesz ręcznie')}</div></a>`;
}

function kafelUmow(alerty, liczniki) {
  if (!liczniki) return '';
  const decyzja = (liczniki['alert'] || 0) + (liczniki['minął'] || 0);
  const brak = alerty.filter(a => a.rodzaj === 'brak umowy').length;
  const st = liczniki['minął'] ? 'zle' : decyzja || brak ? 'uwaga' : 'dobrze';
  return `<a class="kafel-st ${st}" href="#/budzet${decyzja ? '?stan=decyzja' : ''}"><div class="tytul">Umowy z klientami ${pytajnik('alerty_umow')}</div>
    <div class="wartosc">${decyzja} do decyzji</div>${chipSt(st, { zle: 'termin minął', uwaga: 'do decyzji', dobrze: 'w normie' }[st],
      brak ? `${liczba(brak, ['klient', 'klientów', 'klientów'])} z planami bez umowy` : 'każdy klient z planami ma umowę')}
    <div class="dop">umowy w rejestrze: ${(liczniki.ok || 0) + decyzja}, klienci: ${Object.values(liczniki).reduce((a, x) => a + x, 0)}</div></a>`;
}

window.pulpitDodatki = async () => {
  const box = $('#pulpit-alerty');
  if (!box) return;
  const [al, pod, plac] = await Promise.all([odczyt('pulpit/alerty').catch(() => null), odczyt('podatki').catch(() => null), listaPlac()]);
  if (!document.body.contains(box)) return;
  const porz = $('#pulpit-porzadek');
  if (porz && al) {
    const n = al.nieaktualne_plany.ile;
    porz.outerHTML = `<a href="#/platnosci/plan?typ=plan&aktualnosc=Nieaktualna" class="${n ? '' : 'zero'}" title="${esc(POMOC.plany_nieaktualne.krotko)}">${ik('kalendarzX')}Plany nieaktualne <span class="licznik">${n}</span></a>`
      + (al.ostrzezenia_wierszy.ile ? `<a href="#/budzet/ostrzezenia" title="${esc(POMOC.ostrzezenia_wiersza?.krotko || '')}">${ik('weryfikuj')}Ustawienia wierszy do sprawdzenia <span class="licznik">${al.ostrzezenia_wierszy.wierszy}</span></a>` : '');
  }
  const kafle = [kafelUmow(al?.umowy || [], al?.liczniki_umow), kafelVat(pod), kafelListyPlac(plac)].filter(Boolean).join('');
  box.innerHTML = (al ? banerUmow(al.umowy) : '') + (kafle ? `<div class="kontrolka kafle-dodatkowe">${kafle}</div>` : '');
};

})();

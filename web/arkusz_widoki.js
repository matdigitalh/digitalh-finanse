'use strict';
// Pakiet 11, arkusz budżetu: zapisane widoki arkusza (A-ARK-02, wpis „widok” z ekranem „arkusz”), wybór serii wykresu
// (A-ARK-07, parametr „serie”); przypinanie arkuszy (A-OPS-07) jest w budzet.js (pakiet 4, pole „przypiety” arkusza),
// ostrzeżenia o ustawieniach wierszy (A-CF-17, GET /api/budzet/ostrzezenia), ostrzeżenie „plany po końcu umowy” i brązowy
// tekst danin na listach (A-INN-07). Dopina się do budzet.js i arkusz.js przez funkcje na window (pigulkaWidokow,
// serieArkusza, poArkuszu, klasaDaniny); bez tego pliku arkusz działa jak wcześniej.
(() => {

const KLUCZE = ['grupuj', 'sortuj', 'kolejnosc', 'sekcje', 'sekcje_kier', 'ustawienia', 'serie'];
const SERIE = { wplywy: 'Wpływy', obciazenia: 'Obciążenia', saldo: 'Saldo okresu', narastajaco: 'Saldo narastające' };
const PODATKOWE = ['Podatek VAT', 'Podatek dochodowy'];

// Odczyt w tle, bez zapamiętywania zapytania do eksportu ekranu (eksport.js patrzy tylko na zapytania ekranu)
async function odczyt(sciezka, parametry = {}) {
  const q = new URLSearchParams(Object.entries(parametry).filter(([, v]) => v !== '' && v != null));
  const r = await fetch(`/api/${sciezka}${q.toString() ? '?' + q : ''}`);
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).blad || `Błąd ${r.status}`);
  return r.json();
}

Object.assign(POMOC, {
  ark_sekcje: { tytul: 'Sekcje w arkuszu', krotko: 'Grupuje wiersze arkusza po polu Sekcja i pokazuje sumę każdej grupy.',
    co: 'Sekcja to Twój podział wierszy w arkuszu, np. „Zespół” i „Narzędzia”. Po włączeniu przełącznika wiersze z tą samą sekcją stoją razem, a nad każdą grupą jest jej suma w miesiącach.',
    skad: 'Pole Sekcja każdego wiersza (kolumna Sekcja w arkuszu), z Budget Studio albo ustawione w apce.',
    jak: 'Wiersz bez sekcji ma w kolumnie „-”. Gdy żaden wiersz nie ma sekcji, po włączeniu widać jedną grupę „bez sekcji”, więc tabela wygląda prawie tak samo.',
    zrob: 'Żeby podzielić arkusz, ustaw sekcję w kolumnie Sekcja przy wierszach (kliknij komórkę i wybierz albo wpisz nazwę). Przełącznik tylko pokazuje podział, niczego nie zmienia.' },
  ark_ustawienia: { tytul: 'Ustawienia planowanych płatności', krotko: 'Pokazuje kolumny, z których apka tworzy plany płatności dla każdego wiersza.',
    co: 'Kolumny: podstawa płatności (faktura, bez faktury, worek), stawka VAT, dzień wystawienia, dni na płatność, metoda płatności, split payment, Księgowane (czy wchodzi do rentowności) i W cash flow (czy wchodzi do prognozy gotówki).',
    skad: 'Ustawienia wierszy z Budget Studio; po włączeniu planowania w apce zmieniasz je tutaj.',
    jak: 'Z kwoty w komórce i tych ustawień apka liczy datę i kwotę płatności: dzień wystawienia plus dni na płatność daje termin, stawka VAT daje kwotę brutto. Przełącznik tylko pokazuje albo chowa kolumny.',
    zrob: 'Gdy planowanie w apce jest wyłączone (do 1.11), kolumny są tylko do podglądu. Włączysz je w Budżet, Ustawienia budżetu.' },
  widoki_arkusza: { tytul: 'Widoki i przypięte arkusze', krotko: 'Zapisz ustawienia arkusza pod nazwą i zostaw w drzewie Budżetu tylko ważne arkusze.',
    co: 'Widok pamięta grupowanie, sortowanie, sekcje, kolumny ustawień i serie wykresu. Każdy arkusz ma własne widoki; Widok główny to arkusz bez zmian. Pinezka przy nazwie przypina albo odpina arkusz w drzewie w menu Budżet (bez decyzji arkusz jest przypięty).',
    skad: 'Twoje zapisy w pliku zmian tego Maca (widok, zmiana arkusza), więc drugi Mac widzi to samo.',
    jak: 'Gdy zmienisz coś w widoku, przy nazwie pojawia się „zmieniony”: zapisz zmiany albo przywróć widok.',
    zrob: 'Kliknij pigułkę z nazwą widoku pod tytułem arkusza. Pinezka: klik przypina, drugi klik odpina.' },
  ostrzezenia_wiersza: { tytul: 'Ustawienia wierszy do sprawdzenia', krotko: 'Apka szuka ustawień, które psują prognozę, i podpowiada poprawkę.',
    co: 'Cztery przypadki: worek przy stałej opłacie (jedna faktura w miesiącu), faktura kosztowa poza cash flow, stawka 23% u firmy z zagranicy, dzień wystawienia inny niż na fakturach.',
    skad: 'Ustawienia wiersza, jego faktury i przelewy w budżecie oraz rejestr zakupów biura (rejestr zagraniczny).',
    jak: 'To tylko podpowiedź: nic się samo nie zmienia i nic nie jest blokowane. Dzień wystawienia porównujemy z ostatnimi sześcioma fakturami wiersza.',
    zrob: 'Kliknij ostrzeżenie, żeby zaznaczyć wiersz, i popraw ustawienie w kolumnie z prawej strony (Ustawienia planowanych płatności).' },
});

// ---------- Ekran: wszystkie ustawienia wierszy do sprawdzenia (link z pulpitu) ----------
(() => {
  const b = PODSTRONY.budzet;
  const i = b.findIndex(p => p.hash === '#/budzet/historia');
  b.splice(i >= 0 ? i + 1 : b.length, 0, { nazwa: 'Ustawienia wierszy do sprawdzenia', hash: '#/budzet/ostrzezenia', ik: 'weryfikuj' });
})();

WIDOKI['budzet/ostrzezenia'] = async () => {
  const o = await api('budzet/ostrzezenia');
  const kol = [
    { naglowek: 'Arkusz', html: x => `${esc(x.arkusz_nazwa)}<div class="szary">${esc(x.folder)}</div>`, sortKlucz: x => `${x.folder} ${x.arkusz_nazwa}` },
    { naglowek: 'Wiersz', html: x => `${esc(x.przedmiot || '')}${x.przedmiot && x.kontrahent ? '<br>' : ''}<span class="szary">${esc(x.kontrahent)}</span>`, sortKlucz: x => x.kontrahent },
    { naglowek: 'Co jest nie tak', html: x => `<b>${esc(x.tytul)}</b><div>${esc(x.opis)}</div>`, sortKlucz: x => x.tytul },
    { naglowek: 'Co zrobić', html: x => `<span class="szary">${esc(x.rada)}</span>` },
  ];
  return `<div class="naglowek-strony"><div><h1>Ustawienia wierszy do sprawdzenia ${pytajnik('ostrzezenia_wiersza')}</h1>
      <div class="okruszki">Budżet / ${o.wierszy} ${o.wierszy === 1 ? 'wiersz' : 'wierszy'}, ${o.ile} ${o.ile === 1 ? 'ostrzeżenie' : 'ostrzeżeń'}</div></div></div>
    <p class="notka">Ustawienia, które zwykle psują prognozę cash flow albo VAT. To tylko podpowiedź: kliknij wiersz, żeby otworzyć arkusz, i popraw ustawienie w kolumnach Ustawienia planowanych płatności.</p>
    ${tabela({ kolumny: kol, dane: o.ostrzezenia, sortLokalny: true, onWiersz: x => { location.hash = `#/budzet/arkusz?id=${encodeURIComponent(x.arkusz)}&ustawienia=1`; } })}`;
};

// ---------- Kolor danin na listach (A-INN-07, B-MOD-12) ----------
window.klasaDaniny = x => (String(x.id || '').startsWith('sys:') || PODATKOWE.includes(x.podstawa) || ['us', 'zus'].includes(x.skladowa)
  ? ' wiersz-danina' : '');

// ---------- Widoki arkusza (A-ARK-02) ----------
const biezace = p => Object.fromEntries(KLUCZE.filter(k => p[k]).map(k => [k, String(p[k])]));
const roznySie = (p, v) => KLUCZE.some(k => (p[k] || '') !== ((v?.parametry || {})[k] || ''));
const adresWidoku = (aid, v) => `#/budzet/arkusz?${new URLSearchParams({ id: aid, ...(v ? { widok: v.id, ...v.parametry } : {}) })}`;

window.pigulkaWidokow = (a, p, nazwaZakl) => {
  setTimeout(() => podepnijWidoki(a, p));
  return `<button type="button" class="pigulka miekka pigulka-widokow" id="ark-widoki" data-karta title="Zapisane widoki arkusza">${ik('warstwy')}${esc(nazwaZakl)} / <span id="ark-widok-nazwa">${p.widok ? '' : 'Widok główny'}</span> <span aria-hidden="true">▾</span></button>`;
};

async function podepnijWidoki(a, p) {
  const b = $('#ark-widoki');
  if (!b) return;
  const widoki = (await odczyt('budzet/widoki-arkusza', { arkusz: a.id }).catch(() => ({ widoki: [] }))).widoki;
  if (!document.body.contains(b)) return;
  const v = widoki.find(x => x.id === p.widok) || null;
  const zmieniony = roznySie(p, v);
  $('#ark-widok-nazwa').innerHTML = `${esc(v ? v.nazwa : 'Widok główny')}${zmieniony ? ' <i class="szary">(zmieniony)</i>' : ''}`;
  b.onclick = e => { e.stopPropagation(); menuWidokow(b, a, p, widoki, v, zmieniony); };
}

function menuWidokow(przycisk, a, p, widoki, v, zmieniony) {
  document.querySelectorAll('.zarzadzaj-menu').forEach(x => x.remove());
  const m = document.createElement('div');
  m.className = 'zarzadzaj-menu menu-widokow';
  const poz = (x, nazwa) => `<a href="${esc(adresWidoku(a.id, x))}"${(x?.id || '') === (v?.id || '') ? ' class="aktywny"' : ''}>${ik(x ? 'oko' : 'arkusz')}${esc(nazwa)}</a>`;
  m.innerHTML = `<div class="opis">Widoki tego arkusza</div>${poz(null, 'Widok główny')}${widoki.map(x => poz(x, x.nazwa)).join('')}
    <div class="oddziel"></div>
    <button data-w="nowy">${ik('plus')}Zapisz jako nowy widok</button>
    ${v ? `<button data-w="zapisz"${zmieniony ? '' : ' disabled title="Widok nie ma zmian do zapisania"'}>${ik('ptaszek')}Zapisz zmiany w „${esc(v.nazwa)}”</button>
      <button data-w="nazwa">${ik('dokument')}Zmień nazwę widoku</button><button data-w="usun">${ik('zamknij')}Usuń widok</button>` : ''}
    ${zmieniony ? `<button data-w="przywroc">${ik('przywroc')}Przywróć ${v ? 'ustawienia widoku' : 'widok główny'}</button>` : ''}
    <div class="opis">Widok pamięta grupowanie, sortowanie, sekcje, kolumny ustawień i serie wykresu.</div>`;
  const r = przycisk.getBoundingClientRect();
  m.style.left = `${r.left + window.scrollX}px`;
  m.style.top = `${r.bottom + window.scrollY + 2}px`;
  document.body.appendChild(m);
  m.querySelectorAll('a').forEach(x => x.addEventListener('click', () => m.remove()));
  const zapisz = async (id, nazwa, par, cel) => {
    const ok = await zmiana('widok', { ekran: 'arkusz', id, nazwa, parametry: { arkusz: a.id, ...par }, kolumny: [] });
    if (ok && cel) location.hash = cel;
  };
  const akcje = {
    nowy: () => { kartaFormularza('Zapisz jako nowy widok', `<div class="formularz">${pole('', 'Nazwa widoku (do 60 znaków)', '<input id="w-nazwa" maxlength="60">')}</div>
      <p class="szary">Zapisze bieżące ustawienia arkusza: ${esc(opisUstawien(p))}.</p>`, 'Zapisz widok', () => {
      const nazwa = $('#w-nazwa').value.trim();
      if (!nazwa) return komunikat('Wpisz nazwę widoku.', true);
      const id = `a${Date.now().toString(36)}${Math.random().toString(36).slice(2, 5)}`;
      zapisz(id, nazwa, biezace(p), adresWidoku(a.id, { id, parametry: biezace(p) }));
    }); $('#w-nazwa').focus(); },
    zapisz: () => zapisz(v.id, v.nazwa, biezace(p), adresWidoku(a.id, { id: v.id, parametry: biezace(p) })),
    nazwa: () => {
      const k = kartaFormularza('Zmień nazwę widoku', `<div class="formularz">${pole('', 'Nazwa widoku (do 60 znaków)', `<input id="w-nazwa" maxlength="60" value="${esc(v.nazwa)}">`)}</div>`,
        'Zmień nazwę', () => {
          const nazwa = $('#w-nazwa').value.trim();
          if (!nazwa) return komunikat('Wpisz nazwę widoku.', true);
          zapisz(v.id, nazwa, v.parametry, null);
        });
      $('#w-nazwa', k).select();
    },
    usun: () => kartaFormularza('Usunąć widok?', `<p>Widok „${esc(v.nazwa)}” zniknie z menu tego arkusza. Arkusz i jego dane zostają bez zmian.</p>`, 'Tak, usuń',
      async () => { if (await zmiana('widok', { ekran: 'arkusz', id: v.id, usun: true })) location.hash = adresWidoku(a.id, null); }),
    przywroc: () => { location.hash = adresWidoku(a.id, v); },
  };
  m.querySelectorAll('button[data-w]').forEach(x => x.onclick = e => { e.stopPropagation(); m.remove(); akcje[x.dataset.w](); });
  setTimeout(() => document.addEventListener('click', () => m.remove(), { once: true }));
}

function opisUstawien(p) {
  const czesci = [];
  if (p.grupuj) czesci.push(`grupowanie wg ${(typeof GRUPY_ARK !== 'undefined' && GRUPY_ARK[p.grupuj]) || p.grupuj}`);
  if (p.sortuj) czesci.push(`sortowanie wg ${(typeof KOL !== 'undefined' && KOL[p.sortuj]?.naglowek) || p.sortuj}`);
  if (p.sekcje) czesci.push('sekcje');
  if (p.ustawienia) czesci.push('kolumny ustawień');
  if (p.serie) czesci.push(`serie wykresu: ${p.serie.split(',').map(s => SERIE[s] || s).join(', ')}`);
  return czesci.join(', ') || 'jak widok główny';
}

// ---------- Serie wykresu arkusza (A-ARK-07) ----------
window.serieArkusza = p => p.serie ? Object.fromEntries(Object.keys(SERIE).map(k => [k, p.serie.split(',').includes(k)])) : undefined;

function przyciskiSerii(p) {
  const wl = p.serie ? p.serie.split(',') : Object.keys(SERIE);
  const div = document.createElement('div');
  div.className = 'serie-ark';
  div.innerHTML = `<span class="szary">Wykres:</span>${Object.entries(SERIE).map(([k, n]) =>
    `<button type="button" class="seria-ark seria-${k}" data-seria="${k}" aria-pressed="${wl.includes(k)}">${esc(n)}</button>`).join('')}`;
  div.querySelectorAll('[data-seria]').forEach(b => b.onclick = () => {
    const nowe = Object.keys(SERIE).filter(k => k === b.dataset.seria ? !wl.includes(k) : wl.includes(k));
    if (!nowe.length) return komunikat('Wykres musi mieć co najmniej jedną serię.', true);
    ustawParametry({ serie: nowe.length === Object.keys(SERIE).length ? '' : nowe.join(',') });
  });
  return div;
}

// ---------- Po narysowaniu arkusza: serie, ostrzeżenia wierszy, umowa klienta ----------
const umowyCache = { czas: 0, dane: null };

window.poArkuszu = (d, p) => {
  const pasek = $('#ark-widok .ark-pasek');
  if (!pasek) return;
  pasek.querySelector('.serie-ark')?.remove();
  pasek.querySelector('.prawo')?.before(przyciskiSerii(p));
  if (d.systemowy) return;
  const aid = d.arkusz.id;
  odczyt('budzet/ostrzezenia', { arkusz: aid }).then(o => {
    if (!$('#ark-tabela') || ARK?.aid !== aid) return;
    $('#ark-widok .ostrzezenia-ark')?.remove();
    if (!o.ostrzezenia.length) return;
    o.ostrzezenia.forEach(x => {
      const td = $('#ark-tabela').querySelector(`tr[data-w="${CSS.escape(x.wiersz)}"] td.lp`);
      if (td && !td.querySelector('.ostrz-wiersza')) td.insertAdjacentHTML('afterbegin', `<span class="ostrz-wiersza" title="${esc(x.tytul)}: ${esc(x.opis)}">!</span>`);
    });
    const blok = document.createElement('details');
    blok.className = 'ostrzezenia-ark';
    blok.innerHTML = `<summary>${ik('weryfikuj')}Ustawienia do sprawdzenia: ${o.wierszy} ${o.wierszy === 1 ? 'wiersz' : o.wierszy < 5 ? 'wiersze' : 'wierszy'} ${pytajnik('ostrzezenia_wiersza')}</summary>
      <ul>${o.ostrzezenia.map((x, i) => `<li><button type="button" class="link" data-o="${i}">${esc(x.przedmiot || x.kontrahent || 'wiersz')}${x.kontrahent && x.przedmiot ? ` · ${esc(x.kontrahent)}` : ''}</button>
        <b>${esc(x.tytul)}.</b> ${esc(x.opis)} <span class="szary">${esc(x.rada)}</span></li>`).join('')}</ul>`;
    blok.querySelectorAll('[data-o]').forEach(b => b.onclick = () => {
      const x = o.ostrzezenia[b.dataset.o];
      if (ARK?.wiersze?.includes(x.wiersz)) zaznacz(x.wiersz, ARK.kol.includes('przedmiot') ? 'przedmiot' : ARK.kol[0]);
    });
    $('#ark-widok .legenda-stany')?.before(blok);
  }).catch(() => {});
  // plany po końcu umowy klienta, do którego należy arkusz (decyzja Mata 10: zostają w cash flow, apka ostrzega)
  const teraz = Date.now();
  const dane = teraz - umowyCache.czas < 60000 && umowyCache.dane ? Promise.resolve(umowyCache.dane)
    : odczyt('klienci/umowy').then(x => { umowyCache.czas = teraz; umowyCache.dane = x; return x; });
  dane.then(u => {
    if (!$('#ark-tabela') || ARK?.aid !== aid) return;
    const k = u.klienci.find(x => x.arkusze.some(a => a.id === aid));
    const o = k?.ostrzezenia.find(x => x.rodzaj === 'plany_po_koncu');
    $('#ark-widok .umowa-ark')?.remove();
    if (!o) return;
    const n = document.createElement('div');
    n.className = 'komunikat umowa-ark';
    n.innerHTML = `<span>${esc(o.tekst)} <a href="#/budzet/klient?nazwa=${encodeURIComponent(k.klient)}">Karta klienta</a></span>`;
    pasek.before(n);
  }).catch(() => {});
};

})();

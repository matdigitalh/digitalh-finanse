'use strict';
// Wspólny panel „Wygląd i filtry” jak w Budget Studio (pakiet 7): zapisane widoki na górze, grupy (Wygląd, Cechy, Daty),
// rozwijane sekcje z bieżącą wartością w nagłówku (zmienione wyróżnione kropką), jeden „Zastosuj” dla wszystkich filtrów.
// Używają go listy płatności (listy.js) i cash flow (budzet.js). Kolory wyłącznie z tokenów w styl.css.
//
// Sekcja: {grupa: 'Wygląd'} albo {klucz, etykieta, typ, wartosc, zmieniona, ...}:
//   radio   opcje: {wartość: tekst}
//   select  opcje: [[wartość, tekst]]
//   multi   opcje: [[wartość, tekst]], wartosc: tablica (pusta = wszystko); szukaj: true dodaje pole zawężające listę
//   tekst   placeholder, opis
//   zakres  wartosc: {od, do} (dwa pola dat)
//   data    filtr daty BS (tryby: wszystko, bieżący okres, od dziś do końca okresu, zakres statyczny, zakres ruchomy);
//           wartosc: zapis trybu jak w adresie („ruchomy:dzien:14:0”), miesieczny: true dla miesięcy księgowania i budżetowego
//   kolumny opcje: [[klucz, nazwa]] wszystkie, wartosc: widoczne w kolejności; strzałki zmieniają kolejność

const TRYBY_DATY = { wszystko: 'Wszystko', biezacy: 'Bieżący okres', dokonca: 'Od dziś do końca okresu', zakres: 'Zakres statyczny',
  ruchomy: 'Zakres ruchomy' };
const OKRESY_DATY = { tydzien: 'tydzień', miesiac: 'miesiąc', kwartal: 'kwartał', rok: 'rok' };
const JEDNOSTKI_DATY = { dzien: 'Dzień od dziś', dzien_tyg: 'Dzień tygodnia', miesiac: 'Miesiąc', kwartal: 'Kwartał', rok: 'Rok' };
const DNI_TYGODNIA = ['poniedziałek', 'wtorek', 'środa', 'czwartek', 'piątek', 'sobota', 'niedziela'];
// Szybki wybór (daty względne, liczone od dnia stanu przy każdym otwarciu); drugi zestaw dla miesięcy księgowania i budżetowego
const SZYBKIE_DATY = [['ruchomy:dzien:14:0', 'Najbliższe 2 tyg.'], ['ruchomy:dzien:14:-13', 'Ostatnie 2 tyg.'], ['biezacy:tydzien', 'Ten tydzień'],
  ['biezacy:miesiac', 'Ten miesiąc'], ['dokonca:miesiac', 'Od dziś do końca miesiąca'], ['ruchomy:miesiac:1:-1', 'Poprzedni miesiąc'],
  ['ruchomy:miesiac:1:1', 'Następny miesiąc'], ['biezacy:rok', 'Ten rok']];
const SZYBKIE_MIESIACE = [['biezacy:miesiac', 'Ten miesiąc'], ['ruchomy:miesiac:1:-1', 'Poprzedni miesiąc'], ['ruchomy:miesiac:1:1', 'Następny miesiąc'],
  ['biezacy:kwartal', 'Ten kwartał'], ['ruchomy:kwartal:1:-1', 'Poprzedni kwartał'], ['biezacy:rok', 'Ten rok']];

// Zapis filtra daty ↔ obiekt pól formularza
function rozbierzDate(spec) {
  const [tryb = 'wszystko', a = '', b = '', c = '', d = ''] = String(spec || 'wszystko').split(':');
  if (tryb === 'biezacy' || tryb === 'dokonca') return { tryb, okres: a || 'miesiac' };
  if (tryb === 'zakres') return { tryb, od: a, do: b };
  if (tryb === 'ruchomy') return { tryb, jedn: a || 'dzien', n: b || '14', k: c || '0', wd: d || '0' };
  return { tryb: 'wszystko' };
}

function zlozDate(o) {
  if (o.tryb === 'biezacy' || o.tryb === 'dokonca') return `${o.tryb}:${o.okres}`;
  if (o.tryb === 'zakres') return o.od || o.do ? `zakres:${o.od || ''}:${o.do || ''}` : '';
  if (o.tryb === 'ruchomy') return `ruchomy:${o.jedn}:${o.n}:${o.k || 0}${o.jedn === 'dzien_tyg' ? `:${o.wd || 0}` : ''}`;
  return '';
}

const okresyDaty = (tryb, miesieczny) => Object.entries(OKRESY_DATY).filter(([k]) =>
  miesieczny ? k !== 'tydzien' : !(tryb === 'biezacy' && k === 'kwartal'));
const jednostkiDaty = miesieczny => Object.entries(JEDNOSTKI_DATY).filter(([k]) => !miesieczny || !k.startsWith('dzien'));
const dataLubMiesiac = (t, miesieczny) => !t ? '' : t.length === 7 || miesieczny ? mies(t.slice(0, 7)) : dataPl(t);

function opisDaty(spec, miesieczny = false) {
  const szybki = (miesieczny ? SZYBKIE_MIESIACE : SZYBKIE_DATY).find(([v]) => v === spec);
  if (szybki) return szybki[1];
  const o = rozbierzDate(spec);
  if (o.tryb === 'biezacy') return `Bieżący ${OKRESY_DATY[o.okres]}`;
  if (o.tryb === 'dokonca') return `Od dziś do końca: ${OKRESY_DATY[o.okres]}`;
  if (o.tryb === 'zakres') return o.od && o.do ? `${dataLubMiesiac(o.od, miesieczny)} - ${dataLubMiesiac(o.do, miesieczny)}`
    : o.od ? `od ${dataLubMiesiac(o.od, miesieczny)}` : o.do ? `do ${dataLubMiesiac(o.do, miesieczny)}` : 'Wszystko';
  if (o.tryb === 'ruchomy') {
    const n = +o.n, k = +o.k;
    const jedn = { dzien: 'dni', dzien_tyg: `dni od: ${DNI_TYGODNIA[+o.wd]}`, miesiac: 'mies.', kwartal: 'kw.', rok: n === 1 ? 'rok' : 'lat' }[o.jedn];
    return `${n} ${jedn}${k ? `, start ${k > 0 ? '+' : ''}${k}` : ''}`;
  }
  return 'Wszystko';
}

function opisSekcji(s, w) {
  if (s.typ === 'radio') return s.opcje[w] ?? s.opcje[''] ?? '';
  if (s.typ === 'select') return (s.opcje.find(([v]) => String(v) === String(w)) || ['', ''])[1];
  if (s.typ === 'multi') return !w.length || w.length === s.opcje.length ? 'Wszystko'
    : w.length <= 2 ? w.map(v => (s.opcje.find(([x]) => x === v) || [v, v])[1]).join(', ') : `${w.length} z ${s.opcje.length}`;
  if (s.typ === 'tekst') return w || s.puste || '';
  if (s.typ === 'zakres') return `${dataPl(w.od)} - ${dataPl(w.do)}`;
  if (s.typ === 'data') return opisDaty(w, s.miesieczny);
  if (s.typ === 'kolumny') return `${w.length} z ${s.opcje.length}`;
  return '';
}

function htmlSekcji(s) {
  const n = `pf-${s.klucz}`;
  if (s.typ === 'radio') return Object.entries(s.opcje).map(([v, t]) =>
    `<label><input type="radio" name="${n}" value="${esc(v)}"${String(s.wartosc ?? '') === v ? ' checked' : ''}>${esc(t)}</label>`).join('');
  if (s.typ === 'select') return `<select name="${n}">${s.opcje.map(([v, t]) => `<option value="${esc(v)}"${String(s.wartosc) === String(v) ? ' selected' : ''}>${esc(t)}</option>`).join('')}</select>`;
  if (s.typ === 'multi') return `${s.szukaj ? `<input type="text" class="pf-szukaj" placeholder="Wyszukaj" aria-label="Zawęź listę: ${esc(s.etykieta)}">` : ''}
    <div class="pf-akcje"><button type="button" data-pf="wszystkie">Zaznacz wszystkie</button><button type="button" data-pf="wyczysc">Wyczyść</button></div>
    <div class="pf-lista">${s.opcje.map(([v, t]) => `<label data-t="${esc(String(t).toLowerCase())}"><input type="checkbox" name="${n}" value="${esc(v)}"${s.wartosc.includes(v) ? ' checked' : ''}>${esc(t)}</label>`).join('')}</div>`;
  if (s.typ === 'tekst') return `<input type="text" name="${n}" inputmode="${s.inputmode || 'text'}" placeholder="${esc(s.placeholder || '')}" value="${esc(s.wartosc || '')}">${s.opis ? `<span class="szary">${esc(s.opis)}</span>` : ''}`;
  if (s.typ === 'zakres') return `<label>od <input type="date" name="${n}-od" value="${esc(s.wartosc.od || '')}"></label><label>do <input type="date" name="${n}-do" value="${esc(s.wartosc.do || '')}"></label>`;
  if (s.typ === 'kolumny') {
    const kol = [...s.wartosc.map(k => s.opcje.find(([x]) => x === k)).filter(Boolean), ...s.opcje.filter(([k]) => !s.wartosc.includes(k))];
    return `<div class="pf-akcje"><button type="button" data-pf="wszystkie">Pokaż wszystkie</button>${s.domyslne ? '<button type="button" data-pf="domyslne">Domyślne</button>' : ''}</div>
      <div class="pf-kolumny">${kol.map(([k, t]) => `<div class="pf-kol" data-k="${esc(k)}"><label><input type="checkbox" name="${n}" value="${esc(k)}"${s.wartosc.includes(k) ? ' checked' : ''}>${String(t).replace(/<br>/g, ' ')}</label>
        <button type="button" data-pf="gora" aria-label="Wyżej">↑</button><button type="button" data-pf="dol" aria-label="Niżej">↓</button></div>`).join('')}</div>`;
  }
  if (s.typ === 'data') return htmlDaty(s);
  return s.html || '';
}

function htmlDaty(s) {
  const o = rozbierzDate(s.wartosc), m = !!s.miesieczny, typ = m ? 'month' : 'date';
  const opcje = (lista, wart) => lista.map(([v, t]) => `<option value="${v}"${String(wart) === v ? ' selected' : ''}>${esc(t)}</option>`).join('');
  const szybkie = m ? SZYBKIE_MIESIACE : SZYBKIE_DATY;
  return `<div class="pf-data" data-miesieczny="${m ? 1 : 0}">
    <select data-szybki aria-label="Szybki wybór zakresu"><option value="">Szybki wybór…</option>${opcje(szybkie, s.wartosc)}</select>
    <select data-d="tryb" aria-label="Tryb filtra daty">${opcje(Object.entries(TRYBY_DATY), o.tryb)}</select>
    <div data-tryb="biezacy dokonca"><select data-d="okres" aria-label="Okres">${opcje(okresyDaty(o.tryb === 'dokonca' ? 'dokonca' : 'biezacy', m), o.okres || 'miesiac')}</select></div>
    <div data-tryb="zakres"><label>od <input type="${typ}" data-d="od" value="${esc((o.od || '').slice(0, m ? 7 : 10))}"></label>
      <label>do <input type="${typ}" data-d="do" value="${esc((o.do || '').slice(0, m ? 7 : 10))}"></label></div>
    <div data-tryb="ruchomy">
      <label>Jednostka <select data-d="jedn">${opcje(jednostkiDaty(m), o.jedn || (m ? 'miesiac' : 'dzien'))}</select></label>
      <label data-tylko="dzien_tyg">Od dnia <select data-d="wd">${opcje(DNI_TYGODNIA.map((d, i) => [String(i), d]), o.wd || '0')}</select></label>
      <label>Długość <input type="number" min="1" step="1" data-d="n" value="${esc(o.n || '14')}"></label>
      <label>Przesunięcie startu <input type="number" step="1" data-d="k" value="${esc(o.k || '0')}"></label>
    </div>
    <div class="pf-podglad szary" aria-live="polite"></div></div>`;
}

function stanDaty(box) {
  const v = k => box.querySelector(`[data-d="${k}"]`)?.value ?? '';
  return { tryb: v('tryb'), okres: v('okres'), od: v('od'), do: v('do'), jedn: v('jedn'), n: v('n'), k: v('k'), wd: v('wd') };
}

// Pokazuje pola trybu i podgląd „dziś, jutro, za miesiąc” liczony przez serwer (ta sama funkcja co filtr).
function podepnijDate(box, naZmiane) {
  const m = box.dataset.miesieczny === '1';
  let t;
  const odswiez = () => {
    const o = stanDaty(box);
    box.querySelectorAll('[data-tryb]').forEach(el => { el.hidden = !el.dataset.tryb.split(' ').includes(o.tryb); });
    box.querySelectorAll('[data-tylko]').forEach(el => { el.hidden = o.jedn !== el.dataset.tylko; });
    const okres = box.querySelector('[data-d="okres"]');
    const dozwolone = okresyDaty(o.tryb, m).map(([k]) => k);
    [...okres.options].forEach(op => { op.hidden = !dozwolone.includes(op.value); });
    if (!dozwolone.includes(okres.value)) okres.value = dozwolone.includes('miesiac') ? 'miesiac' : dozwolone[0];
    const spec = zlozDate(stanDaty(box));
    naZmiane(spec);
    const pod = box.querySelector('.pf-podglad');
    clearTimeout(t);
    if (!spec || o.tryb === 'zakres') { pod.textContent = ''; return; }
    t = setTimeout(() => api('zakres', { spec, miesieczny: m ? 1 : '' }).then(r => {
      const z = x => !x ? 'wszystko' : dataLubMiesiac(x[0], m) === dataLubMiesiac(x[1], m) ? dataLubMiesiac(x[0], m)
        : `${dataLubMiesiac(x[0], m)} - ${dataLubMiesiac(x[1], m)}`;
      pod.textContent = `Dziś obejmie: ${z(r.dzis)}. Jutro: ${z(r.jutro)}. Za miesiąc: ${z(r.za_miesiac)}.`;
    }).catch(e => { pod.textContent = e.message; }), 150);
  };
  const szybki = box.querySelector('[data-szybki]');
  box.addEventListener('input', odswiez);
  box.addEventListener('change', e => {
    if (e.target === szybki && szybki.value) {   // szybki wybór ustawia pola trybu, dalej można je zmieniać
      const o = rozbierzDate(szybki.value);
      Object.entries(o).forEach(([k, v]) => { const el = box.querySelector(`[data-d="${k}"]`); if (el) el.value = v; });
    } else if (e.target !== szybki) szybki.value = '';
    odswiez();
  });
  odswiez();
}

function zamknijPanelFiltrow() {
  $('#panel-filtrow').hidden = true;
  document.body.classList.remove('filtry-otwarte');
}

// Rysuje panel; naZastosuj dostaje {klucz: wartość} wszystkich sekcji, naZamknij wołany przy × i Anuluj.
function panelFiltrow({ tytul = 'Wygląd i filtry', widoki = null, sekcje, naZastosuj, naZamknij }) {
  const panel = $('#panel-filtrow');
  const sek = sekcje.filter(s => !s.grupa);
  const szczegol = s => `<details data-s="${esc(s.klucz)}"${s.zmieniona ? ' class="zmienione"' : ''}${s.otwarta ? ' open' : ''}>
    <summary><span>${esc(s.etykieta)}: <b>${esc(opisSekcji(s, s.wartosc))}</b></span></summary><div class="zawartosc">${htmlSekcji(s)}</div></details>`;
  panel.innerHTML = `<div class="gora"><button class="zamknij" aria-label="Zamknij filtry">×</button><h2>${esc(tytul)}</h2>
      ${widoki ? `<label class="etyk" for="pf-widok">Zapisane widoki</label><select id="pf-widok">${widoki.opcje.map(([v, t]) => `<option value="${esc(v)}"${v === widoki.wybrany ? ' selected' : ''}>${esc(t)}</option>`).join('')}${widoki.wybrany ? '' : '<option value="" selected>Widok niezapisany</option>'}</select>` : ''}</div>
    <div class="srodek">${sekcje.map(s => s.grupa ? `<div class="grupa">${esc(s.grupa)}</div>` : szczegol(s)).join('')}</div>
    <div class="dol"><button class="przycisk" id="pf-zastosuj">Zastosuj</button><button class="anuluj" id="pf-anuluj">Anuluj</button></div>`;
  panel.hidden = false;
  document.body.classList.add('filtry-otwarte');
  const wartosci = {};
  const zbierz = s => {
    const box = panel.querySelector(`details[data-s="${CSS.escape(s.klucz)}"]`);
    const n = `pf-${s.klucz}`;
    if (s.typ === 'radio') return box.querySelector(`input[name="${n}"]:checked`)?.value ?? '';
    if (s.typ === 'select' || s.typ === 'tekst') return box.querySelector(`[name="${n}"]`).value.trim();
    if (s.typ === 'multi' || s.typ === 'kolumny') return [...box.querySelectorAll(`input[name="${n}"]:checked`)].map(x => x.value);
    if (s.typ === 'zakres') return { od: box.querySelector(`[name="${n}-od"]`).value, do: box.querySelector(`[name="${n}-do"]`).value };
    if (s.typ === 'data') return wartosci[s.klucz] ?? s.wartosc;
    return s.zbierz ? s.zbierz(box) : s.wartosc;
  };
  for (const s of sek) {
    const box = panel.querySelector(`details[data-s="${CSS.escape(s.klucz)}"]`);
    const opis = () => { box.querySelector('summary b').textContent = opisSekcji(s, zbierz(s)); };
    if (s.typ === 'data') podepnijDate(box.querySelector('.pf-data'), spec => { wartosci[s.klucz] = spec; opis(); });
    else box.addEventListener('change', opis);
    const szukaj = box.querySelector('.pf-szukaj');
    if (szukaj) szukaj.oninput = () => { const f = szukaj.value.trim().toLowerCase(); box.querySelectorAll('.pf-lista label').forEach(l => { l.hidden = f && !l.dataset.t.includes(f); }); };
    box.querySelectorAll('[data-pf]').forEach(b => b.onclick = () => {
      const a = b.dataset.pf;
      if (a === 'wszystkie' || a === 'wyczysc') box.querySelectorAll(`input[name="pf-${s.klucz}"]`).forEach(c => { if (!c.closest('label').hidden) c.checked = a === 'wszystkie'; });
      if (a === 'domyslne') box.querySelectorAll(`input[name="pf-${s.klucz}"]`).forEach(c => { c.checked = s.domyslne.includes(c.value); });
      if (a === 'gora' || a === 'dol') {
        const w = b.closest('.pf-kol'), sasiad = a === 'gora' ? w.previousElementSibling : w.nextElementSibling;
        if (sasiad) a === 'gora' ? sasiad.before(w) : sasiad.after(w);
      }
      opis();
    });
  }
  const zamknij = () => { zamknijPanelFiltrow(); naZamknij?.(); };
  $('.zamknij', panel).onclick = zamknij;
  $('#pf-anuluj').onclick = zamknij;
  const pw = $('#pf-widok');
  if (pw && widoki.naZmiane) pw.onchange = () => pw.value && widoki.naZmiane(pw.value);
  $('#pf-zastosuj').onclick = () => naZastosuj(Object.fromEntries(sek.map(s => [s.klucz, zbierz(s)])));
}

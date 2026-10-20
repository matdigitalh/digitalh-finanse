'use strict';
// Arkusz budżetu jak w Budget Studio (pakiet 3): zaznaczanie komórek klikiem i strzałkami, wpisywanie kwot w miejscu,
// listy wyboru i przełączniki w kolumnach ustawień, kopiuj/wklej (także blok z Excela jako jedna seria), wiersz „Dodaj +”,
// akcje na zaznaczonych wierszach, karta komórki z pomarańczowymi odstępstwami, cofanie (Cmd+Z) i menu Zarządzaj.
// Każda zmiana to wpis „bud” w pliku zmian; reguły i blokady liczy serwer (budzet.py), tu tylko podgląd, wygoda
// i wcześniejszy komunikat. Korzysta z app.js (api, komunikat, zl, ...) i budzet.js (kartaWiersza, kartaPlatnosci, ...).

Object.assign(IK, { klodka: '<rect x="5" y="11" width="14" height="9" rx="1.5"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>' });
const suwak = wl => `<span class="suwak${wl ? ' wl' : ''}" role="img" aria-label="${wl ? 'tak' : 'nie'}"></span>`;
const dniOpis = v => v === '' || v == null ? '' : /^\d+$/.test(String(v)) ? (+v === 0 ? 'Natychmiast' : `${v} dni`) : String(v);
const miesNag = m => { const t = mies(m); return t.charAt(0).toUpperCase() + t.slice(1); };
const jestFaktura = w => (w.podstawa || '').startsWith('Faktura');
const DNI_OPCJE = [0, 7, 14, 21, 30, 60];
const TEKST_PODGLADU = 'Edycja jest wyłączona, dopóki planowanie w apce jest wyłączone. Włączysz je w Budżet, Ustawienia budżetu.';
// Arkusz systemowy Opłaty urzędowe (pakiet 8) jest zawsze tylko do odczytu, niezależnie od planowania.
const TEKST_SYSTEMOWY = 'To arkusz systemowy: VAT i podatek dochodowy liczy apka. Kwotę od biura i dzień realny wpiszesz w Budżet, Podatki i ZUS.';
const tekstPodgladu = (d = ARK?.d) => d?.systemowy ? TEKST_SYSTEMOWY : TEKST_PODGLADU;
const NOWY = { rodzaj: -1, podstawa: 'Faktura (jedna)', stawka_vat: 23, dzien_wystawienia: 'Ostatni', dni_na_platnosc: 14, metoda: 'Konto firmowe',
  ksiegowane: true, w_cashflow: true, split: false, przedmiot: '', kontrahent: '', sekcja: '', komentarz: '' };

// Kolumny opisu i ustawień wiersza: wygląd, sortowanie, tekst do schowka i rodzaj edycji (A-ARK-14).
const KOL = {
  podstawa: { naglowek: 'Podstawa płatności', typ: 'lista', pole: 'podstawa', html: w => esc(w.podstawa), sort: w => w.podstawa, tekst: w => w.podstawa },
  vat: { naglowek: 'VAT', typ: 'lista', pole: 'stawka_vat', klasa: 'liczba-kol', html: w => jestFaktura(w) ? stawka(w.stawka_vat) : '-',
    sort: w => stawkaStd(w.stawka_vat) ?? -1, tekst: w => jestFaktura(w) ? String(stawkaStd(w.stawka_vat) ?? '') : '' },
  dzien: { naglowek: 'Dzień wystaw.', typ: 'dzien', pole: 'dzien_wystawienia', html: w => esc(w.dzien_opis), sort: w => w.dzien_opis,
    tekst: w => WOREK.includes(w.podstawa) ? '' : (w.dzien_wystawienia || '') },
  dni: { naglowek: 'Dni na płatność', typ: 'lista', pole: 'dni_na_platnosc', klasa: 'liczba-kol', html: w => esc(dniOpis(w.dni)), sort: w => w.dni ?? 0,
    tekst: w => String(w.dni ?? '') },
  metoda: { naglowek: 'Metoda płatn.', typ: 'slownik', pole: 'metoda', slownik: 'metoda', html: w => esc(w.metoda || ''), sort: w => w.metoda || '', tekst: w => w.metoda || '' },
  split: { naglowek: 'Split Pay.', typ: 'przel', pole: 'split', klasa: 'przel', html: w => suwak(w.split), sort: w => +w.split, tekst: w => w.split ? 'tak' : 'nie' },
  ksiegowane: { naglowek: 'Księgowane', typ: 'przel', pole: 'ksiegowane', klasa: 'przel', html: w => suwak(w.ksiegowane), sort: w => +w.ksiegowane,
    tekst: w => w.ksiegowane ? 'tak' : 'nie' },
  w_cashflow: { naglowek: 'W cash flow', typ: 'przel', pole: 'w_cashflow', klasa: 'przel', html: w => suwak(w.w_cashflow), sort: w => +w.w_cashflow,
    tekst: w => w.w_cashflow ? 'tak' : 'nie' },
  przedmiot: { naglowek: 'Przedmiot transakcji', typ: 'slownik', pole: 'przedmiot', slownik: 'przedmiot', klasa: 'sep',
    html: w => esc(w.przedmiot || 'Przedmiot transakcji'), sort: w => w.przedmiot || '', tekst: w => w.przedmiot || '' },
  kontrahent: { naglowek: 'Kontrahent', typ: 'slownik', pole: 'kontrahent', slownik: 'kontrahent', html: w => esc(w.kontrahent || ''), sort: w => w.kontrahent || '',
    tekst: w => w.kontrahent || '' },
  sekcja: { naglowek: 'Sekcja', typ: 'slownik', pole: 'sekcja', slownik: 'sekcja', klasa: 'szary', html: w => esc(w.sekcja || '-'), sort: w => w.sekcja || '',
    tekst: w => w.sekcja || '-' },
  komentarz: { naglowek: 'Komentarz', typ: 'tekst', pole: 'komentarz', maks: 170, html: w => esc(w.komentarz || ''), sort: w => w.komentarz || '', tekst: w => w.komentarz || '' },
  rodzaj: { naglowek: 'Rodzaj', typ: 'rodzaj', pole: 'rodzaj', html: w => chipZnak(w.rodzaj), sort: w => w.rodzaj, tekst: w => w.rodzaj === 1 ? 'wpływy' : 'obciążenia' },
};
const KOL_UST = ['podstawa', 'vat', 'dzien', 'dni', 'metoda', 'split', 'ksiegowane', 'w_cashflow'];
// Pakiet 4: na dole listy słownika link do Biblioteki (jak „Edycja kontrahentów” w BS)
const EDYCJA_SLOWNIKA = { kontrahent: ['Edycja kontrahentów', 'kontrahenci'], przedmiot: ['Edycja przedmiotów transakcji', 'przedmioty'],
  sekcja: ['Edycja sekcji', 'sekcje'], metoda: ['Edycja metod płatności', 'metody'] };
const KOL_OPIS = ['przedmiot', 'kontrahent', 'sekcja', 'komentarz', 'rodzaj'];
const GRUPY_ARK = { '': 'Nie grupuj', rodzaj: 'Rodzaj', kontrahent: 'Kontrahent', przedmiot: 'Przedmiot transakcji', podstawa: 'Podstawa płatności',
  vat: 'Stawka VAT', dzien: 'Dzień wystawienia', dni: 'Dni na płatność', metoda: 'Metoda płatności', ksiegowane: 'Księgowane', w_cashflow: 'W cash flow' };
const etykietaGrupy = (k, w) => ({ rodzaj: w.rodzaj === 1 ? 'wpływy' : 'obciążenia', vat: jestFaktura(w) ? stawka(w.stawka_vat) : 'bez VAT',
  dzien: w.dzien_opis, dni: dniOpis(w.dni) || '-', ksiegowane: w.ksiegowane ? 'Księgowane' : 'Nieksięgowane',
  w_cashflow: w.w_cashflow ? 'W cash flow' : 'Poza cash flow', sekcja: w.sekcja || 'bez sekcji' }[k] ?? (w[k] || '-'));

// Stan arkusza na ekranie: dane z serwera, zaznaczenie (komórka i kotwica zakresu), kolejność wierszy i kolumn,
// zaznaczone wiersze (w kolejności klikania, „pierwszy zaznaczony” przy scalaniu), otwarty edytor.
let ARK = null;
const arkWidoczny = () => !!ARK && document.body.contains($('#ark-tabela'));
const wierszArk = id => ARK.d.wiersze.find(w => w.id === id) || null;
const sumaWiersza = w => Object.values(w.komorki).reduce((s, k) => s + k.netto, 0);
const tdW = (w, k) => $('#ark-tabela')?.querySelector(`tr[data-w="${CSS.escape(w)}"] td[data-k="${CSS.escape(k)}"]`);
const fokusWPolu = () => { const a = document.activeElement; return !!a && a !== document.body && a.matches('input, select, textarea, button, [contenteditable]'); };

// ---------- Kwoty i wartości z tekstu (wpisywanie, wklejanie z Excela) ----------
// „1 234,56”, „1234.56”, „1.234,56 zł”, „-500” (znak wynika z rodzaju wiersza); grosze bez liczb zmiennoprzecinkowych,
// trzecie miejsce po przecinku zaokrąglane połówkami w górę. Zły zapis: NaN.
function kwotaZTekstu(s) {
  let t = String(s ?? '').replace(/[\s  ]/g, '').replace(/zł|pln/gi, '');
  if (/^[+-]/.test(t)) t = t.slice(1);
  if (!t) return NaN;
  const p = t.lastIndexOf(','), k = t.lastIndexOf('.');
  let calk = t, ulam = '';
  if (p >= 0 && k >= 0) { const d = Math.max(p, k); calk = t.slice(0, d).replace(/[.,]/g, ''); ulam = t.slice(d + 1); }
  else if (/^\d{1,3}([.,]\d{3})+$/.test(t) && (t.match(/[.,]/g).length > 1 || k >= 0)) calk = t.replace(/[.,]/g, '');
  else if (p >= 0 || k >= 0) { const d = Math.max(p, k); if (t.indexOf(t[d]) !== d) return NaN; calk = t.slice(0, d); ulam = t.slice(d + 1); }
  if (!/^\d{1,9}$/.test(calk) || !/^\d*$/.test(ulam)) return NaN;
  let gr = (+calk) * 100 + +((ulam + '00').slice(0, 2));
  if (ulam.length > 2 && +ulam[2] >= 5) gr += 1;
  return gr;
}

// Reguła dnia wystawienia z tekstu: zapis wiersza („10. +1 B”), opis z apki („10. dzień, miesiąc później, księgowanie wg
// budżetu”) albo skrót BS („15-ty”). Zwraca zapis kanoniczny albo null (auto); zły zapis: wyjątek z podpowiedzią.
function regulaZTekstu(t) {
  const s = String(t ?? '').trim().toLowerCase();
  if (!s || s === '(auto)' || s.startsWith('automat') || s.startsWith('tydzień')) return null;
  let m = /^(ostatni|pierwszy|(\d{1,2})(?:\.|-[a-ząęółśżźćń]+)?)(?:\s*dzień)?(?:,\s*(?:(miesiąc)|(\d{1,2}) mies\.)\s*(później|wcześniej))?(?:,\s*księgowanie wg (budżetu|wystawienia))?$/.exec(s);
  if (m) {
    const n = m[3] ? 1 : m[4] ? +m[4] : 0, przes = m[5] === 'wcześniej' ? -n : n;
    const typ = m[1] === 'ostatni' ? 'ostatni' : (m[1] === 'pierwszy' || m[2] === '1') ? 'pierwszy' : 'dzien';
    return regulaNa({ typ, dzien: m[2] ? +m[2] : 1, przes, b: m[6] === 'budżetu' });
  }
  m = /^(ostatni|pierwszy|(\d{1,2})\.?)\s*([+-]\d{1,2})?\s*(b)?$/.exec(s);
  if (!m || (m[2] && !(+m[2] >= 1 && +m[2] <= 31)) || Math.abs(+(m[3] || 0)) > 12) throw new Error('dzień wystawienia: „Ostatni”, „Pierwszy” albo dzień 1–31, opcjonalnie przesunięcie o miesiące (np. „10. +1”)');
  const typ = m[1] === 'ostatni' ? 'ostatni' : (m[1] === 'pierwszy' || m[2] === '1') ? 'pierwszy' : 'dzien';
  return regulaNa({ typ, dzien: m[2] ? +m[2] : 1, przes: +(m[3] || 0), b: !!m[4] });
}

const tak = s => /^(tak|t|1|true|on|prawda|x|✓)$/i.test(s) ? true : /^(nie|n|0|false|off|fałsz|-)?$/i.test(s) ? false : null;
const ALIASY_PODSTAW = { 'faktura': 'Faktura (jedna)', 'faktura (worek)': 'Faktura (w worku)', 'faktura w worku': 'Faktura (w worku)',
  'bez faktury (worek)': 'Bez faktury (w worku)', 'bez faktury w worku': 'Bez faktury (w worku)' };

// Wartość pola wiersza z tekstu dla kolumny k: [pole, wartość] albo [null] (pomiń); zły zapis: wyjątek z podpowiedzią.
function wartoscZTekstu(k, t) {
  const s = String(t ?? '').trim(), kol = KOL[k];
  if (k === 'podstawa') {
    const z = s.toLowerCase().replace(/\s+/g, ' ');
    const v = PODSTAWY.find(x => x.toLowerCase() === z) || ALIASY_PODSTAW[z];
    if (!s) return [null];
    if (!v) throw new Error(`„${s}” to nie podstawa płatności. Użyj nazwy z listy, np. Faktura (jedna)`);
    return ['podstawa', v];
  }
  if (k === 'vat') {
    if (!s || s === '-') return [null];
    const v = stawkaStd(s.replace('%', ''));
    if (v == null) throw new Error(`„${s}” to nie stawka VAT. Wpisz 23, 8, 5 albo 0`);
    return ['stawka_vat', v];
  }
  if (k === 'dzien') { const r = regulaZTekstu(s); return r ? ['dzien_wystawienia', r] : [null]; }
  if (k === 'dni') {
    if (!s) return [null];
    const n = /^natychmiast$/i.test(s) ? 0 : (/^\d{1,3}/.exec(s) || [])[0];
    if (n == null || +n > 99) throw new Error(`„${s}” to nie liczba dni. Wpisz od 0 do 99 (Natychmiast = 0)`);
    return ['dni_na_platnosc', +n];
  }
  if (kol.typ === 'przel') {
    const v = tak(s);
    if (v == null) throw new Error(`„${s}” to nie przełącznik. Wpisz tak albo nie`);
    return [kol.pole, v];
  }
  if (k === 'rodzaj') {
    if (/^(wpływ|wpływy|przychód|przychody|\+|1)$/i.test(s)) return ['rodzaj', 1];
    if (/^(obciążenie|obciążenia|koszt|koszty|-|-1)$/i.test(s)) return ['rodzaj', -1];
    throw new Error(`„${s}” to nie rodzaj. Wpisz wpływy albo obciążenia`);
  }
  if (k === 'komentarz' && s.length > 170) throw new Error(`komentarz ma ${s.length} znaków, a może mieć najwyżej 170. Skróć go`);
  if (k === 'przedmiot' && s === 'Przedmiot transakcji') return ['przedmiot', ''];
  if (k === 'sekcja' && s === '-') return ['sekcja', ''];
  if (s.length > 200) throw new Error(`tekst ma ${s.length} znaków, a może mieć najwyżej 200`);
  return [kol.pole, s];
}

const rowneW = (pole, a, b) => pole === 'stawka_vat' ? stawkaStd(a) === stawkaStd(b)
  : pole === 'dni_na_platnosc' ? +String(a ?? 0).replace(/\D.*$/, '') === +String(b ?? 0).replace(/\D.*$/, '')
  : typeof b === 'boolean' ? !!a === b : (a ?? '') === (b ?? '');

// ---------- Tabela ----------
function arkuszTabela(d, p) {
  if (!ARK || ARK.aid !== d.arkusz.id) ARK = { aid: d.arkusz.id, sel: null, kotwica: null, zazn: [], podglad: new Map() };
  ARK.d = d; ARK.p = p; ARK.podglad.clear();
  ARK.zazn = ARK.zazn.filter(id => d.wiersze.some(w => w.id === id));
  const m = d.miesiace, ust = p.ustawienia === '1', sekcje = p.sekcje === '1', grupuj = GRUPY_ARK[p.grupuj] ? p.grupuj || '' : '';
  const stanM = (STAN?.naleznosci?.dzien_stanu || '').slice(0, 7);
  const kolumny = [...(ust ? KOL_UST : []), ...KOL_OPIS];
  ARK.kol = [...kolumny, ...m.map(x => `m:${x}`)];
  const nOpis = 1 + kolumny.length;
  let wiersze = [...d.wiersze];
  const ks = KOL[p.sortuj] && kolumny.includes(p.sortuj) ? KOL[p.sortuj] : null;
  if (ks) {
    const znak = p.kolejnosc === 'malejaco' ? -1 : 1;
    wiersze.sort((a, b) => { const x = ks.sort(a), y = ks.sort(b); return znak * (typeof x === 'number' ? x - y : String(x).localeCompare(String(y), 'pl')); });
  }
  const kom = (w, x) => {
    const k = w.komorki[x], dk = `data-k="m:${x}"`;
    if (!k) return `<td class="liczba-kol pusta" ${dk}>-</td>`;
    const kl = ['liczba-kol komorka', k.plany && !k.rzeczywiste ? 'plany' : '', k.plany && k.rzeczywiste ? 'mieszana' : '',
      k.rzeczywiste && k.stan === 'po-terminie' ? 'po-terminie' : '', k.stan === 'wg-bs' ? 'wg-bs' : '',
      k.netto < 0 ? 'minus' : k.netto > 0 ? 'plus' : ''].filter(Boolean).join(' ');
    const ikony = (k.nieaktualne ? '<span class="kropka czerwona" title="płatność nieaktualna: wymaga uwagi"></span>' : '')
      + (k.oplacone ? '<span class="kropka zielona" title="jest płatność opłacona"></span>' : '');
    const n = k.platnosci.length;
    const tytul = `${n} ${n === 1 ? 'płatność' : 'płatności'}${k.rzeczywiste ? `, w tym rzeczywiste: ${k.rzeczywiste}` : ', tylko plany'}${k.nieaktualne ? `, nieaktualne: ${k.nieaktualne}` : ''}`;
    return `<td class="${kl}" ${dk} title="${tytul}"><span class="kom">${ikony}${zl(k.netto, false)}</span></td>`;
  };
  let lp = 0;
  const kolejnosc = [];
  const wiersz = w => {
    kolejnosc.push(w.id);
    const z = ARK.zazn.includes(w.id);
    return `<tr data-w="${esc(w.id)}"${z ? ' class="zazn"' : ''}><td class="lp"><span class="nr">${++lp}.</span>${d.planowanie ? `<input type="checkbox" data-zazn="${esc(w.id)}" aria-label="Zaznacz wiersz ${lp}"${z ? ' checked' : ''}>` : ''}</td>
      ${kolumny.map(k => `<td data-k="${k}" class="opis-kom ${KOL[k].klasa || ''}${KOL_UST.includes(k) ? ' ust' : ''}">${KOL[k].html(w)}</td>`).join('')}
      ${m.map(x => kom(w, x)).join('')}<td class="liczba-kol sep ${sumaWiersza(w) < 0 ? 'minus' : 'plus'}">${zl(sumaWiersza(w), false)}</td></tr>`;
  };
  const naglowekGrupy = (etyk, ws, wciecie = false) => {
    const s = x => ws.reduce((a, w) => a + (w.komorki[x]?.netto || 0), 0);
    const r = ws.reduce((a, w) => a + sumaWiersza(w), 0);
    return `<tr class="grupa"><td colspan="${nOpis}">${wciecie ? '&nbsp;&nbsp;&nbsp;· ' : ''}${esc(etyk)} <span class="szary">(${ws.length})</span></td>
      ${m.map(x => `<td class="liczba-kol ${s(x) < 0 ? 'minus' : s(x) > 0 ? 'plus' : 'szary'}">${s(x) ? zl(s(x), false) : '-'}</td>`).join('')}<td class="liczba-kol sep">${zl(r, false)}</td></tr>`;
  };
  const grupy = (ws, klucz) => { const g = new Map(); ws.forEach(w => { const e = etykietaGrupy(klucz, w); (g.get(e) || g.set(e, []).get(e)).push(w); }); return [...g]; };
  let tbody = '';
  if (sekcje) {
    // kolejność sekcji = sortowanie kolumny Sekcja sprzed włączenia przełącznika (A-ARK-05); późniejsze sortowanie jej nie zmienia
    const sek = grupy(wiersze, 'sekcja');
    if (p.sekcje_kier) sek.sort(([a], [b]) => (p.sekcje_kier === 'malejaco' ? -1 : 1) * a.localeCompare(b, 'pl'));
    for (const [sek_, ws] of sek) {
      tbody += naglowekGrupy(sek_, ws);
      tbody += grupuj ? grupy(ws, grupuj).map(([e, xs]) => naglowekGrupy(e, xs, true) + xs.map(wiersz).join('')).join('') : ws.map(wiersz).join('');
    }
  } else if (grupuj) tbody = grupy(wiersze, grupuj).map(([e, ws]) => naglowekGrupy(e, ws) + ws.map(wiersz).join('')).join('');
  else tbody = wiersze.map(wiersz).join('');
  if (d.planowanie) { tbody += wierszNowy(kolumny, m); kolejnosc.push('__nowy'); }
  ARK.wiersze = kolejnosc;
  const sumaCala = d.podsumowanie.reduce((a, x) => a + x.saldo, 0);
  const wp = d.podsumowanie.reduce((a, x) => a + x.wplywy, 0), ob = d.podsumowanie.reduce((a, x) => a + x.obciazenia, 0);
  const pusteOpis = `<th colspan="${nOpis}"></th>`;
  const thead = `<tr class="ark-wykres">${pusteOpis}<th colspan="${m.length + 1}"><div id="ark-wyk"></div></th></tr>
    <tr class="ark-mies">${pusteOpis}${m.map(x => `<th class="${x === stanM ? 'biezacy' : ''}">${esc(miesNag(x))}</th>`).join('')}<th class="sep">Suma</th></tr>
    <tr class="ark-suma pierwszy"><th class="etyk" colspan="${nOpis}">=</th>${d.podsumowanie.map(s => `<th>${zl(s.saldo, false)}</th>`).join('')}<th class="sep">${zl(sumaCala, false)}</th></tr>
    <tr class="ark-suma"><th class="etyk" colspan="${nOpis}"><span class="plus">↗</span><br><span class="minus">↘</span></th>${d.podsumowanie.map(s => `<th><span class="plus">${zl(s.wplywy, false)}</span><br><span class="minus">${zl(s.obciazenia, false)}</span></th>`).join('')}
      <th class="sep"><span class="plus">${zl(wp, false)}</span><br><span class="minus">${zl(ob, false)}</span></th></tr>
    <tr class="ark-kol"><th class="lp">${d.planowanie && d.wiersze.length ? '<input type="checkbox" id="ark-wszystkie" aria-label="Zaznacz wszystkie wiersze">' : ''}</th>${kolumny.map(k => `<th class="sort${KOL[k].klasa === 'liczba-kol' ? ' liczba-kol' : ''}${KOL[k].klasa === 'sep' ? ' sep' : ''}" data-sort="${k}"${p.sortuj === k ? ` data-kierunek="${p.kolejnosc === 'malejaco' ? 'malejaco' : 'rosnaco'}"` : ''}>${KOL[k].naglowek}</th>`).join('')}
      ${m.map(() => '<th></th>').join('')}<th class="sep"></th></tr>`;
  setTimeout(podepnijArkusz);
  return `<div class="ark-pasek">
      <label class="pole-grupuj">Grupuj wiersze wg<select id="ark-grupuj">${Object.entries(GRUPY_ARK).map(([v, t]) => `<option value="${v}"${v === grupuj ? ' selected' : ''}>${t}</option>`).join('')}</select></label>
      <label class="przelacznik"><input type="checkbox" id="ark-sekcje"${sekcje ? ' checked' : ''}><span class="suwak"></span>Sekcje</label>
      <label class="przelacznik"><input type="checkbox" id="ark-ustawienia"${ust ? ' checked' : ''}><span class="suwak"></span>Ustawienia planowanych płatności</label>
      <span class="prawo"></span>
      ${d.planowanie ? `<button class="przycisk" id="dodaj-wiersz" title="Pełny formularz wiersza (także umowy z kwotami od księgowej)">Dodaj wiersz ${ik('plus')}</button>` : ''}
      <button class="przycisk" id="ark-karta" disabled data-karta title="Cmd+Enter albo Cmd+dwuklik na komórce">Otwórz kartę płatności</button></div>
    ${d.planowanie ? '<p class="notka ark-podpowiedz">Klik zaznacza komórkę, strzałki i Tab przesuwają zaznaczenie. Wpisz kwotę albo naciśnij Enter, żeby edytować; Cmd+Enter otwiera kartę płatności, Cmd+C i Cmd+V kopiują i wklejają (także blok z Excela), Cmd+Z cofa ostatnią zmianę.</p>'
      : d.systemowy ? '' : `<p class="notka">${TEKST_PODGLADU} Do tego czasu plany pochodzą z Budget Studio, tylko do odczytu.</p>`}
    <div class="legenda-stany"><span><i class="plany"></i>tylko plany</span><span><i class="rzecz"></i>rzeczywiste</span><span><i class="mieszana"></i>plany i rzeczywiste</span><span><i class="po"></i>rzeczywiste po terminie</span>
      <span><i class="wg-bs"></i>opłacone tylko wg BS</span><span><span class="kropka czerwona"></span>nieaktualna, wymaga uwagi</span><span><span class="kropka zielona"></span>jest opłacona</span></div>
    <div class="tabela-ramka arkusz" id="ark-tabela"><table class="ark"><thead>${thead}</thead><tbody>${tbody || `<tr><td colspan="${nOpis + m.length + 1}" class="pusto">Arkusz nie ma wierszy.</td></tr>`}</tbody></table></div>
    <div class="ark-akcje" id="ark-akcje" hidden></div>
    <div class="stopka"><span class="zaznaczony" id="ark-zazn"></span>
      <button id="ark-szukaj-gora" aria-label="Poprzednie trafienie">↑</button><button id="ark-szukaj-dol" aria-label="Następne trafienie">↓</button>
      <input class="szukaj" id="ark-szukaj" type="search" placeholder="Wyszukaj" aria-label="Wyszukaj w arkuszu"></div>`;
}

// Wiersz „Dodaj +” na dole (A-ARK-10): wpisanie wartości w dowolnej kolumnie tworzy wiersz z ustawieniami domyślnymi.
function wierszNowy(kolumny, m) {
  return `<tr class="nowy" data-w="__nowy"><td class="lp">${ik('plus')}</td>
    ${kolumny.map((k, i) => `<td data-k="${k}" class="opis-kom ${KOL[k].klasa || ''}">${i === 0 ? '<span class="szary">Dodaj +</span>' : ''}</td>`).join('')}
    ${m.map(x => `<td class="liczba-kol pusta" data-k="m:${x}"></td>`).join('')}<td class="sep"></td></tr>`;
}

function podepnijArkusz() {
  const tab = $('#ark-tabela');
  if (!tab || !ARK) return;
  const { d, p } = ARK;
  const m = d.miesiace, stanM = (STAN?.naleznosci?.dzien_stanu || '').slice(0, 7);
  const naglowkiMies = () => [...tab.querySelectorAll('tr.ark-mies th:not([colspan])')].slice(0, m.length);
  Wykresy.bs($('#ark-wyk'), { wysokosc: 118, opis: 'Arkusz miesięcznie: wpływy, obciążenia i saldo narastające',
    okresy: d.podsumowanie.map(s => ({ etykieta: mies(s.miesiac), wplywy: s.wplywy, obciazenia: s.obciazenia, saldo: s.saldo, narastajaco: s.narastajaco, biezacy: s.miesiac === stanM })),
    kolumny: () => { const r0 = $('#ark-wyk').getBoundingClientRect(); return naglowkiMies().map(th => { const r = th.getBoundingClientRect(); return { x: r.left - r0.left, w: r.width }; }); } });
  if (ARK.scroll) { [tab.scrollTop, tab.scrollLeft] = ARK.scroll; ARK.scroll = null; }

  tab.addEventListener('mousedown', e => { if (e.shiftKey && e.target.closest('td[data-k]')) e.preventDefault(); });   // bez zaznaczania tekstu
  tab.addEventListener('click', e => {
    const td = e.target.closest('td[data-k]');
    if (!td || !td.closest('tr[data-w]')) return;
    e.stopPropagation();
    const wid = td.parentElement.dataset.w, k = td.dataset.k;
    zaznacz(wid, k, { rozszerz: e.shiftKey });
    if (e.shiftKey || !d.planowanie) return;
    const w = wid === '__nowy' ? null : wierszArk(wid);
    if (KOL[k]?.typ === 'przel' && e.target.closest('.suwak')) przelacz(w, k);
    if (k === 'rodzaj' && w && e.target.closest('.chip')) zmienRodzaj(w);
  });
  tab.addEventListener('dblclick', e => {
    const td = e.target.closest('td[data-k]');
    if (!td || !td.closest('tr[data-w]')) return;
    zaznacz(td.parentElement.dataset.w, td.dataset.k);
    if (e.metaKey || e.ctrlKey || !d.planowanie) return otworzKarte();
    if (KOL[td.dataset.k]?.typ === 'przel' || td.dataset.k === 'rodzaj') return;   // przełącznik zmienia pojedynczy klik
    edytuj(null);
  });
  tab.addEventListener('change', e => {
    if (e.target.matches('[data-zazn]')) zaznaczWiersz(e.target.dataset.zazn, e.target.checked);
    if (e.target.id === 'ark-wszystkie') { d.wiersze.forEach(w => zaznaczWiersz(w.id, e.target.checked, false)); pasekAkcji(); }
  });
  tab.querySelectorAll('th.sort').forEach(h => h.onclick = () => ustawParametry({ sortuj: h.dataset.sort,
    kolejnosc: p.sortuj === h.dataset.sort && p.kolejnosc !== 'malejaco' ? 'malejaco' : 'rosnaco' }));
  $('#ark-grupuj').onchange = e => ustawParametry({ grupuj: e.target.value });
  $('#ark-sekcje').onchange = e => ustawParametry({ sekcje: e.target.checked ? '1' : '',
    sekcje_kier: e.target.checked && p.sortuj === 'sekcja' ? (p.kolejnosc === 'malejaco' ? 'malejaco' : 'rosnaco') : '' });
  $('#ark-ustawienia').onchange = e => ustawParametry({ ustawienia: e.target.checked ? '1' : '' });
  $('#ark-karta').onclick = e => { e.stopPropagation(); otworzKarte(); };
  const dodaj = $('#dodaj-wiersz');
  if (dodaj) dodaj.onclick = e => { e.stopPropagation(); kartaWiersza(null, d); };
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
  szukaj.onkeydown = e => { if (e.key === 'Enter') { e.preventDefault(); skocz(e.shiftKey ? -1 : 1); } if (e.key === 'Escape') szukaj.blur(); };
  const skocz = krok => {
    if (!trafienia.length) return;
    nr = (nr + krok + trafienia.length) % trafienia.length;
    const td = trafienia[nr];
    td.scrollIntoView({ block: 'center', inline: 'center' });
    if (td.dataset.k && td.parentElement.dataset.w) zaznacz(td.parentElement.dataset.w, td.dataset.k, { przewin: false });
  };
  $('#ark-szukaj-gora').onclick = () => skocz(-1);
  $('#ark-szukaj-dol').onclick = () => skocz(1);
  if (ARK.sel && (!ARK.wiersze.includes(ARK.sel.w) || !ARK.kol.includes(ARK.sel.k))) ARK.sel = ARK.kotwica = null;
  if (ARK.sel) rysujZaznaczenie(false);
  else if (d.wiersze[0]) pokazWiersz(d.wiersze[0]);
  pasekAkcji();
}

// ---------- Zaznaczenie, zakres i panel podglądu ----------
function zaznacz(w, k, { rozszerz = false, przewin = true } = {}) {
  if (!rozszerz || !ARK.kotwica) ARK.kotwica = { w, k };
  ARK.sel = { w, k };
  $('#ark-tabela')?.querySelectorAll('.skopiowane').forEach(x => x.classList.remove('skopiowane'));
  rysujZaznaczenie(przewin);
}

function zakresArk() {
  const r = [ARK.wiersze.indexOf(ARK.kotwica.w), ARK.wiersze.indexOf(ARK.sel.w)], c = [ARK.kol.indexOf(ARK.kotwica.k), ARK.kol.indexOf(ARK.sel.k)];
  return { r0: Math.min(...r), r1: Math.max(...r), c0: Math.min(...c), c1: Math.max(...c) };
}

function komorkiZakresu(z = zakresArk()) {
  const wynik = [];
  for (let r = z.r0; r <= z.r1; r++) for (let c = z.c0; c <= z.c1; c++) wynik.push({ w: ARK.wiersze[r], k: ARK.kol[c], r, c });
  return wynik;
}

function rysujZaznaczenie(przewin) {
  const tab = $('#ark-tabela');
  if (!tab || !ARK.sel) return;
  tab.querySelectorAll('.wybrana, .w-zakresie').forEach(x => x.classList.remove('wybrana', 'w-zakresie'));
  tab.querySelectorAll('tr.zaznaczony').forEach(x => x.classList.remove('zaznaczony'));
  const z = zakresArk();
  if (z.r1 > z.r0 || z.c1 > z.c0) komorkiZakresu(z).forEach(x => tdW(x.w, x.k)?.classList.add('w-zakresie'));
  const td = tdW(ARK.sel.w, ARK.sel.k);
  if (!td) return;
  td.classList.add('wybrana');
  td.parentElement.classList.add('zaznaczony');
  if (przewin) td.scrollIntoView({ block: 'nearest', inline: 'nearest' });
  const w = wierszArk(ARK.sel.w), c = w && ARK.sel.k.startsWith('m:') ? w.komorki[ARK.sel.k.slice(2)] : null;
  $('#ark-karta').disabled = !c;
  podgladStopki(w, ARK.sel.k);
}

function pokazWiersz(w) {
  const el = $('#ark-zazn');
  if (!el) return;
  el.innerHTML = w ? `<span>${w.rodzaj === 1 ? '<b class="plus">↗</b>' : '<b class="minus">↘</b>'} ${esc(w.podstawa)}</span><span>${jestFaktura(w) ? stawka(w.stawka_vat) : 'bez VAT'}</span>
    <span>${esc(w.dzien_opis)}</span><span>${esc(dniOpis(w.dni))}</span><span>${esc(w.metoda || '')}</span>
    <span>split ${suwak(w.split)}</span><span>K ${suwak(w.ksiegowane)}</span><span>CF ${suwak(w.w_cashflow)}</span>
    <span>${esc(w.przedmiot || 'Przedmiot transakcji')}</span><span>${esc(w.kontrahent || '')}</span><span>${esc(w.sekcja || '-')}</span>`
    : '<span class="szary">Nowy wiersz: wpisz wartość w dowolnej kolumnie</span>';
}

// Panel podglądu (A-ARK-11): komórka opisu = ustawienia wiersza; komórka miesiąca = szybki podgląd płatności, a cechy
// różne od ustawień wiersza na pomarańczowo (ręczne wyjątki).
async function podgladStopki(w, k) {
  if (!w || !k.startsWith('m:') || !w.komorki[k.slice(2)]) return pokazWiersz(w);
  const m = k.slice(2), klucz = `${w.id}|${m}`;
  let dane = ARK.podglad.get(klucz);
  if (!dane) {
    try { dane = await api('budzet/komorka', { wiersz: w.id, miesiac: m }); } catch (e) { return pokazWiersz(w); }
    ARK.podglad.set(klucz, dane);
  }
  if (!ARK.sel || ARK.sel.w !== w.id || ARK.sel.k !== k) return;
  const ps = dane.platnosci.map(x => x.platnosc);
  const el = $('#ark-zazn');
  const z = (p, pole, html) => `<span${(p.odstepstwa || []).includes(pole) ? ' class="inna" title="Inne niż w ustawieniach wiersza"' : ''}>${html}</span>`;
  if (ps.length === 1) {
    const p = ps[0];
    el.innerHTML = `<span>${p.typ === 'plan' ? 'plan' : 'rzeczywista'} ${chipEtap(p.etap)}</span>${z(p, 'stawka', p.stawka != null ? `VAT ${p.stawka} %` : 'bez VAT')}
      ${z(p, 'wystawienie', `wyst. ${dataPl(p.wystawienie)}`)}${z(p, 'termin', `termin ${dataPl(p.termin)}`)}${p.realny && p.realny !== p.termin ? z(p, 'realny', `realny ${dataPl(p.realny)}`) : ''}
      ${z(p, 'kontrahent', esc(p.w_kontrahent || ''))}${z(p, 'metoda', esc(p.metoda || ''))}${z(p, 'ksiegowane', `K ${suwak(p.ksiegowane)}`)}${z(p, 'w_cashflow', `CF ${suwak(p.w_cashflow)}`)}
      ${p.komentarz ? z(p, 'komentarz', esc(p.komentarz)) : ''}`;
  } else {
    const inne = ps.filter(p => (p.odstepstwa || []).length).length;
    const terminy = ps.map(p => p.termin).filter(Boolean).sort();
    el.innerHTML = `<span>${ps.length} płatności: ${ps.filter(p => p.typ === 'plan').length} plan., ${ps.filter(p => p.typ !== 'plan').length} rzecz.</span>
      <span>netto ${zl(ps.reduce((a, p) => a + p.netto, 0), false)}</span>${terminy.length ? `<span>terminy ${dataPl(terminy[0])} do ${dataPl(terminy[terminy.length - 1])}</span>` : ''}
      ${inne ? `<span class="inna" title="Cechy inne niż w ustawieniach wiersza">zmienione ręcznie: ${inne}</span>` : ''}<span class="szary">Cmd+Enter: karta</span>`;
  }
}

// ---------- Klawiatura, schowek, cofanie (zdarzenia na dokumencie, działają tylko na ekranie arkusza) ----------
document.addEventListener('keydown', e => {
  if (!arkWidoczny() || ARK.edycja) return;
  if (fokusWPolu() || (!$('#karta').hidden && $('#karta').contains(document.activeElement))) return;
  const mod = e.metaKey || e.ctrlKey, kl = e.key;
  if (mod && kl.toLowerCase() === 'f') { e.preventDefault(); $('#ark-szukaj').focus(); return; }
  if (mod && kl.toLowerCase() === 'z' && !e.shiftKey) { e.preventDefault(); cofnijOstatni(); return; }
  if (mod && kl.toLowerCase() === 'a' && ARK.sel) { e.preventDefault(); ARK.kotwica = { w: ARK.wiersze[0], k: ARK.kol[0] }; ARK.sel = { w: ARK.wiersze[ARK.wiersze.length - 1], k: ARK.kol[ARK.kol.length - 1] }; rysujZaznaczenie(false); return; }
  const strzalki = { ArrowUp: [-1, 0], ArrowDown: [1, 0], ArrowLeft: [0, -1], ArrowRight: [0, 1] };
  if (!ARK.sel) {
    if (strzalki[kl] && ARK.wiersze.length) { e.preventDefault(); zaznacz(ARK.wiersze[0], ARK.kol.find(k => k.startsWith('m:')) || ARK.kol[0]); }
    return;
  }
  if (strzalki[kl]) { e.preventDefault(); ruch(...strzalki[kl], e.shiftKey, mod); return; }
  if (kl === 'Tab') { e.preventDefault(); ruch(0, e.shiftKey ? -1 : 1); return; }
  if (kl === 'Enter') { e.preventDefault(); if (mod) otworzKarte(); else if (!ARK.d.planowanie) otworzKarte(); else edytuj(null); return; }
  if (kl === 'F2') { e.preventDefault(); edytuj(null); return; }
  if (kl === 'Escape') { ARK.kotwica = { ...ARK.sel }; zaznacz(ARK.sel.w, ARK.sel.k, { przewin: false }); return; }
  if (kl === 'Delete' || kl === 'Backspace') { e.preventDefault(); wyczysc(); return; }
  if (kl.length === 1 && !mod) { e.preventDefault(); edytuj(kl); }
});

document.addEventListener('copy', e => {
  if (!arkWidoczny() || ARK.edycja || fokusWPolu() || !ARK.sel || window.getSelection()?.toString()) return;
  const z = zakresArk(), wiersze = [];
  for (let r = z.r0; r <= z.r1; r++) {
    const wid = ARK.wiersze[r], w = wid === '__nowy' ? null : wierszArk(wid);
    const kom = [];
    for (let c = z.c0; c <= z.c1; c++) kom.push(tekstKomorki(w, ARK.kol[c]));
    wiersze.push(kom.join('\t'));
  }
  e.clipboardData.setData('text/plain', wiersze.join('\n'));
  e.preventDefault();
  komorkiZakresu(z).forEach(x => tdW(x.w, x.k)?.classList.add('skopiowane'));
  komunikat(`Skopiowano ${(z.r1 - z.r0 + 1) * (z.c1 - z.c0 + 1)} ${(z.r1 - z.r0 + 1) * (z.c1 - z.c0 + 1) === 1 ? 'komórkę' : 'komórek'}. Wklejasz Cmd+V w arkuszu albo w Excelu.`);
});

document.addEventListener('paste', e => {
  if (!arkWidoczny() || ARK.edycja || fokusWPolu() || !ARK.sel) return;
  const t = e.clipboardData.getData('text/plain');
  if (!t) return;
  e.preventDefault();
  try { wklej(blokZTekstu(t)); } catch (err) { komunikat(`Nic nie wklejono. ${err.message}.`, true); }
});

function tekstKomorki(w, k) {
  if (!w) return '';
  if (k.startsWith('m:')) { const c = w.komorki[k.slice(2)]; return c ? zlWpis(c.kwota ?? Math.abs(c.netto)) : ''; }
  return KOL[k].tekst(w);
}

// Tekst ze schowka (Excel: tabulatory i nowe linie, pola w cudzysłowach) na tablicę wierszy.
function blokZTekstu(t) {
  const wiersze = [[]];
  let pole = '', cudzy = false;
  for (let i = 0; i < t.length; i++) {
    const z = t[i];
    if (cudzy) { if (z === '"' && t[i + 1] === '"') { pole += '"'; i++; } else if (z === '"') cudzy = false; else pole += z; continue; }
    if (z === '"' && pole === '') cudzy = true;
    else if (z === '\t') { wiersze[wiersze.length - 1].push(pole); pole = ''; }
    else if (z === '\n' || z === '\r') { if (z === '\r' && t[i + 1] === '\n') i++; wiersze[wiersze.length - 1].push(pole); pole = ''; wiersze.push([]); }
    else pole += z;
  }
  wiersze[wiersze.length - 1].push(pole);
  if (wiersze.length > 1 && wiersze[wiersze.length - 1].join('') === '') wiersze.pop();
  return wiersze;
}

function ruch(dr, dc, rozszerz = false, krawedz = false) {
  const r = ARK.wiersze.indexOf(ARK.sel.w), c = ARK.kol.indexOf(ARK.sel.k);
  const nr = krawedz && dr ? (dr < 0 ? 0 : ARK.wiersze.length - 1) : Math.max(0, Math.min(ARK.wiersze.length - 1, r + dr));
  const nc = krawedz && dc ? (dc < 0 ? 0 : ARK.kol.length - 1) : Math.max(0, Math.min(ARK.kol.length - 1, c + dc));
  zaznacz(ARK.wiersze[nr], ARK.kol[nc], { rozszerz });
}

// ---------- Zapis: kolejka, odświeżenie samego arkusza, cofanie ----------
let kolejkaArk = Promise.resolve(), oczekujace = 0, bladWSerii = false;

async function wyslijBud(dane, typ = 'bud') {
  try {
    const r = await fetch('/api/zmiana', { method: 'POST', headers: { 'X-Finanse': '1', 'Content-Type': 'application/json' }, body: JSON.stringify({ typ, dane }) });
    const w = await r.json().catch(() => ({}));
    return r.ok ? { ok: true, wpis: w.wpis } : { ok: false, blad: w.blad || 'Nie udało się zapisać zmiany.' };
  } catch (e) {
    return { ok: false, blad: 'Brak połączenia z apką: zmiana nie została zapisana.' };
  }
}

// Zmiany z arkusza idą po kolei (szybkie wpisywanie kwot nie wyprzedza zapisu); arkusz odświeża się raz, gdy kolejka
// opustoszeje, i tylko on (bez przeładowania strony), z zachowaniem zaznaczenia i przewinięcia.
function zapiszArk(dane, { po } = {}) {
  oczekujace++;
  const zadanie = kolejkaArk.then(async () => {
    const r = await wyslijBud(dane);
    if (!r.ok) { bladWSerii = true; komunikat(r.blad, true); }
    else if (!bladWSerii) komunikat('Zapisane.', false, { nazwa: 'Cofnij', akcja: cofnijOstatni });
    return r.ok;
  });
  kolejkaArk = zadanie.then(async ok => {
    oczekujace--;
    if (!oczekujace) { await odswiezArkusz(); bladWSerii = false; }
    if (ok && po) po();
    return ok;
  });
  return zadanie;
}

// Zapis z kart (płatność, komórka, wiersz): na ekranie arkusza bez przeładowania strony, gdzie indziej jak dotąd.
function zapiszBud(dane, { zostawKarte = false } = {}) {
  if (arkWidoczny()) { if (!zostawKarte) { $('#karta').hidden = true; ARK.karta = null; } return zapiszArk(dane); }
  return zmiana('bud', dane);
}

async function odswiezArkusz() {
  if (!arkWidoczny()) return;
  if (ARK.edycja) { ARK.odswiez = true; return; }
  let d;
  try { d = await api('budzet/arkusz', { id: ARK.aid }); } catch (e) { location.hash = '#/budzet/arkusze'; return; }
  if (!arkWidoczny()) return;
  if (ARK.edycja) { ARK.odswiez = true; return; }
  const t = $('#ark-tabela');
  ARK.scroll = t ? [t.scrollTop, t.scrollLeft] : null;
  $('#ark-widok').innerHTML = arkuszTabela(d, ARK.p);
  if (ARK.karta && !$('#karta').hidden) kartaKomorkiArk(ARK.karta.w, ARK.karta.m);
}

const OPISY_OP = { komorka: 'kwota w komórce', wiersz: 'zmiana wiersza', platnosc: 'zmiana płatności', arkusz: 'zmiana arkusza', przenies: 'przeniesienie wierszy',
  decyzja_planu: 'decyzja o planie', scal: 'scalenie wierszy', podziel: 'podział wiersza', duplikuj: 'duplikat wierszy', przesun_arkusz: 'przesunięcie arkusza',
  duplikuj_arkusz: 'duplikat arkusza' };
const odmZmian = n => `${n} ${n === 1 ? 'zmiana' : [2, 3, 4].includes(n % 10) && ![12, 13, 14].includes(n % 100) ? 'zmiany' : 'zmian'}`;
const opisOp = o => { const ops = (o.ops?.length ? o.ops : [String(o.op || '').replace(/^seria: /, '')]).map(x => OPISY_OP[x] || x);
  return `${ops.join(', ')}${o.ile > 1 ? ` (${odmZmian(o.ile)} w jednej serii)` : ''}`; };

// Cmd+Z i przycisk „Cofnij”: unieważnia ostatnią obowiązującą zmianę budżetu (wpis „cofnij” w pliku zmian).
async function cofnijOstatni() {
  await kolejkaArk;
  let o;
  try { o = (await api('budzet/ostatni')).ostatni; } catch (e) { return komunikat(e.message, true); }
  if (!o) return komunikat('Nie ma zmiany budżetu do cofnięcia.', true);
  const r = await wyslijBud({ wpis: o.wpis }, 'cofnij');
  if (!r.ok) return komunikat(r.blad, true);
  komunikat(`Cofnięto: ${opisOp(o)}. Kolejne Cmd+Z cofa wcześniejszą zmianę.`);
  if (arkWidoczny()) await odswiezArkusz(); else { await sprawdzStan(); await pokaz(); }
}

// ---------- Edycja w miejscu ----------
// Lista albo panel pod komórką; gdy pod komórką brak miejsca (stopka, koniec ekranu), nad nią.
function umiescPrzy(el, td, minSzer = 0) {
  const r = td.getBoundingClientRect(), h = el.offsetHeight, w = Math.max(el.offsetWidth, minSzer);
  const dol = r.bottom + 2 + h <= window.innerHeight - 52;
  el.style.left = `${Math.max(4, Math.min(r.left, window.innerWidth - w - 8)) + window.scrollX}px`;
  el.style.top = `${(dol ? r.bottom + 2 : Math.max(4, r.top - h - 2)) + window.scrollY}px`;
}

function edytuj(znak) {
  const { w: wid, k } = ARK.sel;
  if (!ARK.d.planowanie) return komunikat(tekstPodgladu(), true);
  const td = tdW(wid, k), w = wid === '__nowy' ? null : wierszArk(wid);
  if (!td) return;
  const typ = k.startsWith('m:') ? 'kwota' : KOL[k].typ;
  if (znak === ' ' && typ !== 'przel' && typ !== 'rodzaj') return;
  if (typ === 'kwota') return edytujKwote(td, w, k.slice(2), znak);
  if (typ === 'przel') return znak == null || znak === ' ' ? przelacz(w, k) : null;
  if (typ === 'rodzaj') return znak == null || znak === ' ' ? zmienRodzaj(w) : null;
  if (typ === 'dzien') return edytujDzien(td, w);
  return edytujPole(td, w, k, znak);
}

function blokadaKomorki(w, m) {
  const c = w?.komorki[m];
  if (c && c.rzeczywiste && !WOREK.includes(w.podstawa)) return 'W tej komórce jest już płatność rzeczywista, więc kwoty nie zmienisz. Wpisz plan w innym miesiącu albo zduplikuj wiersz.';
  return null;
}
const wartoscKomorki = c => c ? (c.kwota ?? Math.abs(c.netto)) : null;
const ZNAKI_KWOTY = /^[0-9\-+,. ]$/;

function edytujKwote(td, w, m, znak) {
  const blok = blokadaKomorki(w, m);
  if (blok) return komunikat(blok, true);
  if (znak != null && !ZNAKI_KWOTY.test(znak)) return komunikat('W komórce kwotowej wpisujesz tylko liczby, np. 1 234,56.', true);
  const c = w?.komorki[m], stara = wartoscKomorki(c), stareHtml = td.innerHTML;
  const tryb = znak == null ? 'edycja' : 'wpis';   // „wpis”: strzałki zatwierdzają i przechodzą dalej, jak w Excelu
  td.classList.add('edycja');
  td.innerHTML = `<span class="ark-stare">${stareHtml}</span><input class="ark-input" inputmode="decimal" aria-label="Kwota w komórce">`;
  const inp = td.querySelector('input');
  inp.value = znak ?? (stara == null ? '' : zlWpis(stara));
  inp.focus();
  if (znak == null) inp.select(); else inp.setSelectionRange(inp.value.length, inp.value.length);
  let koniec = false;
  const zamknij = () => { koniec = true; ARK.edycja = null; td.classList.remove('edycja'); if (ARK.odswiez) { ARK.odswiez = false; setTimeout(odswiezArkusz); } };
  const anuluj = () => { if (koniec) return; zamknij(); td.innerHTML = stareHtml; };
  const zatwierdz = krok => {
    if (koniec) return;
    const t = inp.value.trim(), kwota = t === '' ? null : kwotaZTekstu(t);
    if (Number.isNaN(kwota)) { komunikat('To nie jest kwota. Wpisz liczbę, np. 1 234,56 (najwyżej dwa miejsca po przecinku).', true); setTimeout(() => inp.focus()); return; }
    zamknij();
    if (kwota === stara || (kwota == null && !c)) td.innerHTML = stareHtml;
    else {
      const znakW = w ? w.rodzaj : wzorNowego({}).rodzaj;
      td.innerHTML = `<span class="kom">${kwota == null ? '-' : zl(kwota * znakW, false)}</span>`;
      td.classList.add('zapisuje');
      if (w) zapiszArk({ op: 'komorka', wiersz: w.id, miesiac: m, kwota });
      else if (kwota != null) nowyWiersz({}, [{ op: 'komorka', miesiac: m, kwota }]);
    }
    if (krok) ruch(...krok);
  };
  ARK.edycja = { anuluj };
  inp.addEventListener('keydown', e => {
    e.stopPropagation();   // klawisze należą do edytora (po zamknięciu nie mogą przesunąć zaznaczenia drugi raz)
    const strz = { ArrowUp: [-1, 0], ArrowDown: [1, 0], ArrowLeft: [0, -1], ArrowRight: [0, 1] }[e.key];
    if (e.key === 'Enter') { e.preventDefault(); e.stopPropagation(); zatwierdz(e.shiftKey ? [-1, 0] : [1, 0]); }
    else if (e.key === 'Tab') { e.preventDefault(); zatwierdz([0, e.shiftKey ? -1 : 1]); }
    else if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); anuluj(); }
    else if (strz && (tryb === 'wpis' || !strz[1])) { e.preventDefault(); zatwierdz(strz); }
    else if (e.key.length === 1 && !e.metaKey && !e.ctrlKey && !ZNAKI_KWOTY.test(e.key)) { e.preventDefault(); komunikat('W komórce kwotowej wpisujesz tylko liczby, np. 1 234,56.', true); }
  });
  inp.addEventListener('blur', () => zatwierdz(null));
}

// Nowy wiersz z wiersza „Dodaj +” (A-ARK-10): do serwera idą tylko pola pierwszej akcji z flagą „domyslne”, a resztę
// uzupełnia serwer z Biblioteki: ustawienia wybranego kontrahenta, gdy to on był pierwszą akcją, inaczej kontrahent
// domyślny i jego ustawienia (A-KOL-04, A-KOL-05; pakiet 4). Tu tylko podgląd z tych samych danych.
function wzorNowego(pola) {
  const dom = ARK.d.slowniki?.domyslne || { kontrahent: '', przedmiot: '' }, wz = ARK.d.wzorce || {};
  const kontrahent = 'kontrahent' in pola ? pola.kontrahent : dom.kontrahent;
  const u = { ...NOWY, ...(wz[dom.kontrahent] || {}), ...(wz[kontrahent] || {}) };
  const w = { ...u, przedmiot: u.przedmiot || dom.przedmiot || '', sekcja: u.sekcja || '', komentarz: '', kontrahent, ...pola };
  if (!jestFaktura(w)) delete w.stawka_vat;
  if (WOREK.includes(w.podstawa)) delete w.dzien_wystawienia;
  return w;
}

function nowyWiersz(pola, komorki = []) {
  const id = nowyId('w');
  const obiekt = { id, arkusz: ARK.aid, ...wzorNowego(pola) };
  const ops = [{ op: 'wiersz', obiekt: { id, arkusz: ARK.aid, ...pola }, domyslne: true },
    ...komorki.map(k => ({ op: 'komorka', wiersz: id, miesiac: k.miesiac, kwota: k.kwota }))];
  // wiersz od razu na ekranie (z ustawieniami domyślnymi), żeby kolejne Tab i wpisy trafiały do niego, zanim serwer odpowie
  const stub = { ...obiekt, komorki: {}, ma_rzeczywiste: false, dni: obiekt.dni_na_platnosc ?? 0, dzien_opis: obiekt.dzien_wystawienia || 'tydzień (worek)', proporcje: null };
  komorki.forEach(k => { stub.komorki[k.miesiac] = { netto: k.kwota * stub.rodzaj, kwota: k.kwota, platnosci: [], kwoty: {}, plany: 1, rzeczywiste: 0, nieaktualne: 0, oplacone: 0, stan: 'planowana' }; });
  ARK.d.wiersze.push(stub);
  const tr = $('#ark-tabela tr[data-w="__nowy"]');
  if (tr) {
    const kolumny = ARK.kol.filter(k => !k.startsWith('m:'));
    tr.insertAdjacentHTML('afterend', wierszNowy(kolumny, ARK.d.miesiace));
    tr.dataset.w = id;
    tr.classList.remove('nowy');
    tr.querySelector('td.lp').innerHTML = `<span class="nr">${ARK.d.wiersze.length}.</span>`;
    kolumny.forEach(k => { const td = tr.querySelector(`td[data-k="${k}"]`); if (td) { td.innerHTML = KOL[k].html(stub); td.classList.add('zapisuje'); } });
    ARK.wiersze.splice(ARK.wiersze.indexOf('__nowy'), 0, id);
    if (ARK.sel?.w === '__nowy') ARK.sel.w = id;
    if (ARK.kotwica?.w === '__nowy') ARK.kotwica.w = id;
  }
  zapiszArk(ops.length === 1 ? ops[0] : { op: 'seria', operacje: ops });
  return id;
}

function zapiszPole(w, pole, wartosc) {
  if (!w) return nowyWiersz({ [pole]: wartosc });
  if (rowneW(pole, w[pole], wartosc)) return;
  w[pole] = wartosc;
  if (pole === 'dni_na_platnosc') w.dni = wartosc;
  if (pole === 'dzien_wystawienia') w.dzien_opis = wartosc;
  const k = Object.keys(KOL).find(x => KOL[x].pole === pole);
  const td = k && tdW(w.id, k);
  if (td) { td.innerHTML = KOL[k].html(w); td.classList.add('zapisuje'); }
  zapiszArk({ op: 'wiersz', obiekt: { id: w.id, [pole]: wartosc } });
}

function przelacz(w, k) {
  if (!ARK.d.planowanie) return komunikat(tekstPodgladu(), true);
  if (k === 'ksiegowane' && w && UMOWY[w.podstawa]) return komunikat('Umowa jest zawsze księgowana (koszt i podatki liczy księgowa), więc tego przełącznika nie zmienisz.', true);
  zapiszPole(w, KOL[k].pole, !(w ? w[KOL[k].pole] : wzorNowego({})[KOL[k].pole]));
}

function zmienRodzaj(w) {
  if (!ARK.d.planowanie) return komunikat(tekstPodgladu(), true);
  if (w?.ma_rzeczywiste) return komunikat('Wiersz ma już płatność rzeczywistą, więc rodzaju (wpływ albo obciążenie) nie zmienisz. Zduplikuj wiersz i zmień rodzaj w kopii.', true);
  if (w && UMOWY[w.podstawa]) return komunikat('Umowa to zawsze obciążenie (koszt), więc rodzaju nie zmienisz.', true);
  zapiszPole(w, 'rodzaj', -(w ? w.rodzaj : wzorNowego({}).rodzaj));
}

// Delete i Backspace: jedna komórka = edycja od pustej wartości (Enter czyści); zakres komórek miesięcy = wyczyszczenie
// wszystkich jedną serią (cofniesz ją Cmd+Z).
function wyczysc() {
  if (!ARK.d.planowanie) return komunikat(tekstPodgladu(), true);
  const kom = komorkiZakresu();
  if (kom.length === 1) {
    const x = kom[0];
    if (x.k.startsWith('m:') || ['tekst', 'slownik'].includes(KOL[x.k]?.typ)) edytuj('');
    return;
  }
  const ops = [];
  for (const x of kom) {
    if (!x.k.startsWith('m:') || x.w === '__nowy') continue;
    const w = wierszArk(x.w), m = x.k.slice(2);
    if (!w.komorki[m]) continue;
    const blok = blokadaKomorki(w, m);
    if (blok) return komunikat(`Nic nie wyczyszczono. Wiersz ${ARK.wiersze.indexOf(x.w) + 1}, ${miesNag(m)}: ${blok}`, true);
    ops.push({ op: 'komorka', wiersz: w.id, miesiac: m, kwota: null });
  }
  if (!ops.length) return komunikat('W zaznaczeniu nie ma kwot do wyczyszczenia.', true);
  zapiszArk(ops.length === 1 ? ops[0] : { op: 'seria', operacje: ops });
}

// Lista wyboru pod komórką (kontrahent, sekcja, przedmiot, metoda, podstawa, VAT, dni) z filtrowaniem po wpisanym
// fragmencie, strzałkami i Enterem; „Dodaj …”, gdy wpisanej wartości nie ma na liście (A-ARK-14).
function edytujPole(td, w, k, znak) {
  const kol = KOL[k];
  if (k === 'podstawa' && w?.ma_rzeczywiste) return komunikat('Wiersz ma już płatność rzeczywistą, więc podstawy nie zmienisz. Zduplikuj wiersz i ustaw nową podstawę w kopii.', true);
  if (k === 'vat' && w && !jestFaktura(w)) return komunikat('Stawka VAT dotyczy tylko faktur; przy tej podstawie VAT nie występuje. Zmień podstawę na fakturę, jeśli trzeba.', true);
  const obecna = w ? (k === 'dni' ? w.dni : w[kol.pole]) : null;
  const opcje = k === 'podstawa' ? PODSTAWY.map(x => [x, x]) : k === 'vat' ? STAWKI.map(x => [x, `${x} %`]) : k === 'dni' ? DNI_OPCJE.map(x => [x, dniOpis(x)])
    : kol.slownik ? (ARK.d.slowniki?.[kol.slownik] || []).map(x => [x, x]) : null;
  const wlasna = k === 'dni' ? t => /^\d{1,2}$/.test(t) ? [+t, `${dniOpis(+t)} (nietypowe)`] : null
    : (kol.typ === 'slownik' || kol.typ === 'tekst') ? t => [t, t ? `Dodaj „${t}”` : 'Wyczyść'] : () => null;
  const tekstowe = kol.typ === 'slownik' || kol.typ === 'tekst';
  const stareHtml = td.innerHTML;
  td.classList.add('edycja');
  td.innerHTML = `<span class="ark-stare">${stareHtml}</span><input class="ark-input tekst" maxlength="${kol.maks || 200}" aria-label="${esc(kol.naglowek)}">`;
  const inp = td.querySelector('input');
  inp.value = znak ?? (tekstowe ? (obecna || '') : '');
  inp.focus();
  if (znak == null) inp.select();
  let aktywny = -1, pozycje = [];
  const lista = document.createElement('div');
  lista.className = 'ark-lista';
  lista.setAttribute('role', 'listbox');
  document.body.appendChild(lista);
  lista.style.minWidth = `${Math.max(td.getBoundingClientRect().width, 220)}px`;
  const rysuj = () => {
    const q = inp.value.trim().toLowerCase();
    if (kol.typ === 'tekst') { pozycje = []; lista.innerHTML = `<div class="pusto-lista">${inp.value.trim().length} / ${kol.maks} znaków. Enter zapisuje, Esc anuluje.</div>`; umiescPrzy(lista, td); return; }
    pozycje = (opcje || []).filter(([, e]) => !q || e.toLowerCase().includes(q)).slice(0, 80);
    const t = inp.value.trim();
    const dokladna = (opcje || []).some(([v, e]) => e.toLowerCase() === t.toLowerCase() || String(v) === t);
    const wl = !dokladna && (t || tekstowe) ? wlasna(t) : null;
    if (wl && (t || obecna)) pozycje.push([wl[0], wl[1], true]);
    if (aktywny >= pozycje.length || aktywny < 0) aktywny = pozycje.findIndex(([v]) => String(v) === String(obecna ?? '') || (k === 'vat' && v === stawkaStd(obecna)));
    if (q && aktywny < 0 && pozycje.length) aktywny = 0;
    lista.innerHTML = (pozycje.length ? pozycje.map(([v, e, nowa], i) => `<div class="poz${i === aktywny ? ' aktywna' : ''}${nowa ? ' dodaj' : ''}${String(v) === String(obecna ?? '') ? ' obecna' : ''}" data-i="${i}" role="option">${esc(e)}</div>`).join('')
      : '<div class="pusto-lista">Brak pasujących pozycji.</div>')
      + (EDYCJA_SLOWNIKA[kol.slownik] ? `<a class="ark-edycja" href="#/budzet/biblioteka?zakladka=${EDYCJA_SLOWNIKA[kol.slownik][1]}">${EDYCJA_SLOWNIKA[kol.slownik][0]} …</a>` : '');
    lista.querySelector('.aktywna')?.scrollIntoView({ block: 'nearest' });
    umiescPrzy(lista, td);
  };
  rysuj();
  let koniec = false;
  const zamknij = () => { koniec = true; ARK.edycja = null; lista.remove(); td.classList.remove('edycja'); if (ARK.odswiez) { ARK.odswiez = false; setTimeout(odswiezArkusz); } };
  const anuluj = () => { if (koniec) return; zamknij(); td.innerHTML = stareHtml; };
  const wybierz = (v, krok) => {
    if (koniec) return;
    if (k === 'komentarz' && String(v).length > 170) { komunikat(`Komentarz ma ${String(v).length} znaków, a może mieć najwyżej 170. Skróć go.`, true); return; }
    zamknij();
    td.innerHTML = stareHtml;
    const wart = k === 'sekcja' && v === '-' ? '' : v;
    if (k === 'podstawa' && UMOWY[wart] && !(w && w.podstawa === wart)) {
      kartaWiersza(w, ARK.d, { podstawa: wart });
      komunikat('Umowa potrzebuje kwot od księgowej (dla osoby, PIT, ZUS): uzupełnij je w karcie wiersza i zapisz.');
    } else if (!(w && rowneW(kol.pole, obecna, wart))) zapiszPole(w, kol.pole, wart);
    if (krok) ruch(...krok);
  };
  const zatwierdz = krok => {
    const t = inp.value.trim();
    if (aktywny >= 0 && pozycje[aktywny] && (!tekstowe || t)) return wybierz(pozycje[aktywny][0], krok);
    if (tekstowe) return t || obecna ? wybierz(t, krok) : (anuluj(), krok && ruch(...krok));
    const wl = wlasna(t);
    if (wl) return wybierz(wl[0], krok);
    komunikat(k === 'dni' ? 'Dni na płatność: liczba od 0 do 99. Dłuższy termin ustaw na karcie płatności (dzień płatności).'
      : 'Wybierz pozycję z listy (strzałki i Enter).', true);
  };
  ARK.edycja = { anuluj };
  inp.addEventListener('input', () => { aktywny = -1; rysuj(); });
  inp.addEventListener('keydown', e => {
    e.stopPropagation();
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      if (pozycje.length) { aktywny = (aktywny + (e.key === 'ArrowDown' ? 1 : -1) + pozycje.length) % pozycje.length; rysuj(); }
    } else if (e.key === 'Enter') { e.preventDefault(); e.stopPropagation(); zatwierdz(e.shiftKey ? [-1, 0] : [1, 0]); }
    else if (e.key === 'Tab') { e.preventDefault(); zatwierdz([0, e.shiftKey ? -1 : 1]); }
    else if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); anuluj(); }
  });
  lista.addEventListener('mousedown', e => {
    e.preventDefault();   // bez utraty fokusu w polu
    const ed = e.target.closest('.ark-edycja');
    if (ed) { anuluj(); location.hash = ed.getAttribute('href'); return; }   // Biblioteka (pakiet 4)
    const p = e.target.closest('.poz');
    if (p) wybierz(pozycje[+p.dataset.i][0], null);
  });
  inp.addEventListener('blur', () => setTimeout(() => {
    if (koniec) return;
    const t = inp.value.trim();
    if (kol.typ === 'tekst' && t !== (obecna || '')) wybierz(t, null); else anuluj();   // słownik: bez zgadywania nowej pozycji
  }));
}

// Dzień wystawienia (A-KOL-12): ostatni, pierwszy albo wybrany dzień, przesunięcie o miesiące, miesiąc księgowania.
function edytujDzien(td, w) {
  if (w && WOREK.includes(w.podstawa)) return komunikat('W worku dzień wystawienia ustala apka: początek każdego tygodnia miesiąca.', true);
  const r = regulaZ(w?.dzien_wystawienia || wzorNowego({}).dzien_wystawienia || NOWY.dzien_wystawienia);
  const panel = document.createElement('div');
  panel.className = 'ark-lista ark-dzien';
  panel.innerHTML = `<div class="formularz">
      ${pole('', 'Dzień wystawienia', `<select data-typ><option value="ostatni">ostatni dzień miesiąca</option><option value="pierwszy">pierwszy dzień miesiąca</option><option value="dzien">wybrany dzień</option></select>`)}
      ${pole('', 'Który dzień (1–31)', `<input data-dzien inputmode="numeric" value="${r.dzien}">`)}
      ${pole('', 'Miesiąc wystawienia względem kolumny', `<select data-przes>${[...Array(25)].map((_, i) => i - 12).map(n => `<option value="${n}">${n === 0 ? 'ten sam miesiąc' : n > 0 ? `${n} mies. później (z dołu)` : `${-n} mies. wcześniej (z góry)`}</option>`).join('')}</select>`)}
      ${pole('', 'Miesiąc księgowania', '<select data-ksieg><option value="">wg daty wystawienia</option><option value="B">wg miesiąca budżetu</option></select>')}</div>
    <p class="szary" data-przyklad></p>
    <div class="akcje"><button class="glowny" data-ok>Zastosuj</button><button data-anuluj>Anuluj</button></div>`;
  document.body.appendChild(panel);
  const el = s => panel.querySelector(s);
  el('[data-typ]').value = r.typ; el('[data-przes]').value = String(r.przes); el('[data-ksieg]').value = r.b ? 'B' : '';
  const m0 = ARK.d.miesiace[0];
  const odswiez = () => {
    const typ = el('[data-typ]').value, przes = +el('[data-przes]').value, dz = +el('[data-dzien]').value;
    el('[data-dzien]').disabled = typ !== 'dzien';
    el('[data-ksieg]').disabled = !przes || typ === 'ostatni' || (typ === 'dzien' && dz > 15);
    const reg = { typ, dzien: dz, przes, b: el('[data-ksieg]').value === 'B' && !el('[data-ksieg]').disabled };
    const cel = nastMies(m0, przes), ost = new Date(+cel.slice(0, 4), +cel.slice(5, 7), 0).getDate();
    const dzien = typ === 'ostatni' ? ost : typ === 'pierwszy' ? 1 : Math.min(dz || 1, ost);
    el('[data-przyklad]').textContent = `Np. kolumna ${miesPelny(m0)}: wystawienie ${dataPl(`${cel}-${String(dzien).padStart(2, '0')}`)}, księgowanie ${miesPelny(reg.b ? m0 : cel)}.`;
    return reg;
  };
  panel.addEventListener('change', odswiez);
  panel.addEventListener('input', odswiez);
  odswiez();
  umiescPrzy(panel, td);
  let koniec = false;
  const zamknij = () => { koniec = true; ARK.edycja = null; panel.remove(); document.removeEventListener('mousedown', poza, true); if (ARK.odswiez) { ARK.odswiez = false; setTimeout(odswiezArkusz); } };
  const anuluj = () => { if (!koniec) zamknij(); };
  const ok = () => {
    const reg = odswiez();
    if (reg.typ === 'dzien' && !(reg.dzien >= 1 && reg.dzien <= 31)) return komunikat('Dzień wystawienia: od 1 do 31.', true);
    zamknij();
    zapiszPole(w, 'dzien_wystawienia', regulaNa(reg));
  };
  const poza = e => { if (!panel.contains(e.target)) anuluj(); };
  document.addEventListener('mousedown', poza, true);
  el('[data-ok]').onclick = ok;
  el('[data-anuluj]').onclick = anuluj;
  panel.addEventListener('keydown', e => {
    e.stopPropagation();
    if (e.key === 'Enter') { e.preventDefault(); e.stopPropagation(); ok(); }
    if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); anuluj(); }
  });
  ARK.edycja = { anuluj };
  el('[data-typ]').focus();
}

// ---------- Wklejanie bloku (Excel, inna część arkusza): jedna seria, wszystko albo nic ----------
function wklej(blok) {
  if (!ARK.d.planowanie) throw new Error(tekstPodgladu().replace(/\.$/, ''));
  const z = zakresArk();
  let dane = blok;
  if (blok.length === 1 && blok[0].length === 1 && (z.r1 > z.r0 || z.c1 > z.c0)) {   // jedna wartość na zaznaczony zakres
    dane = [...Array(z.r1 - z.r0 + 1)].map(() => [...Array(z.c1 - z.c0 + 1)].map(() => blok[0][0]));
  }
  const ops = [], poKolumnach = [];
  let pominiete = 0, nowych = 0, komorek = 0, pol = 0;
  dane.forEach((wartosci, i) => {
    const ri = z.r0 + i, wid = ARK.wiersze[ri], w = wid && wid !== '__nowy' ? wierszArk(wid) : null;
    const pola = {}, kom = [];
    wartosci.forEach((tekst, j) => {
      const k = ARK.kol[z.c0 + j];
      if (!k) { pominiete++; return; }
      const gdzie = `Wiersz ${ri + 1}, kolumna ${k.startsWith('m:') ? miesNag(k.slice(2)) : KOL[k].naglowek}`;
      const t = String(tekst).trim();
      if (k.startsWith('m:')) {
        const m = k.slice(2), c = w?.komorki[m];
        const kwota = t === '' ? null : kwotaZTekstu(t);
        if (Number.isNaN(kwota)) throw new Error(`${gdzie}: „${t}” to nie kwota. Wklej liczby, np. 1 234,56`);
        if (kwota === wartoscKomorki(c) || (kwota == null && !c)) return;
        const blokada = blokadaKomorki(w, m);
        if (blokada) throw new Error(`${gdzie}: ${blokada.charAt(0).toLowerCase()}${blokada.slice(1).replace(/\.$/, '')}`);
        kom.push({ miesiac: m, kwota });
      } else {
        let wynik;
        try { wynik = wartoscZTekstu(k, t); } catch (e) { throw new Error(`${gdzie}: ${e.message}`); }
        const [pole_, wart] = wynik;
        if (pole_ && !(w && rowneW(pole_, w[pole_], wart))) pola[pole_] = wart;
      }
    });
    if (w && w.ma_rzeczywiste && (('podstawa' in pola && pola.podstawa !== w.podstawa) || ('rodzaj' in pola && pola.rodzaj !== w.rodzaj))) {
      throw new Error(`Wiersz ${ri + 1}: ma płatność rzeczywistą, więc podstawy ani rodzaju nie zmienisz. Zduplikuj wiersz i zmień je w kopii`);
    }
    komorek += kom.length;
    pol += Object.keys(pola).length;
    if (!w) {
      if (!Object.keys(pola).length && !kom.length) return;
      const id = nowyId('w');
      ops.push({ op: 'wiersz', obiekt: { id, arkusz: ARK.aid, ...pola }, domyslne: true });   // resztę pól uzupełni serwer z Biblioteki
      kom.forEach(x => ops.push({ op: 'komorka', wiersz: id, ...x }));
      nowych++;
    } else {
      if (Object.keys(pola).length) ops.push({ op: 'wiersz', obiekt: { id: w.id, ...pola } });
      kom.forEach(x => { ops.push({ op: 'komorka', wiersz: w.id, ...x }); poKolumnach.push({ w, ...x }); });
    }
  });
  if (!ops.length) return komunikat('Wklejone wartości są takie same jak w arkuszu, więc nie ma czego zapisać.');
  if (ops.length > 1000) throw new Error(`Jedno wklejenie to najwyżej 1000 zmian, a tu jest ${ops.length}. Wklej mniejszy blok`);
  poKolumnach.forEach(x => { const td = tdW(x.w.id, `m:${x.miesiac}`); if (td) { td.innerHTML = `<span class="kom">${x.kwota == null ? '-' : zl(x.kwota * x.w.rodzaj, false)}</span>`; td.classList.add('zapisuje'); } });
  zapiszArk(ops.length === 1 ? ops[0] : { op: 'seria', operacje: ops }, {
    po: () => komunikat(`Wklejono: ${[komorek ? `kwoty: ${komorek}` : '', pol ? `ustawienia i opisy: ${pol}` : ''].filter(Boolean).join(', ')}${nowych ? `, nowe wiersze: ${nowych}` : ''}${pominiete ? `, pominięto ${pominiete} wartości poza arkuszem` : ''}. Całość to jedna zmiana (Cmd+Z cofa ją w całości).`, false, { nazwa: 'Cofnij', akcja: cofnijOstatni }) });
}

// ---------- Karta komórki (A-ARK-13): wszystkie płatności, kwota komórki, naprawa nieaktualnego planu ----------
function otworzKarte() {
  if (!ARK.sel) return;
  const w = wierszArk(ARK.sel.w);
  if (!w) return;
  if (!ARK.sel.k.startsWith('m:')) return ARK.d.planowanie ? kartaWiersza(w, ARK.d) : komunikat(tekstPodgladu(), true);
  const m = ARK.sel.k.slice(2);
  if (!w.komorki[m]) return ARK.d.planowanie ? edytuj(null) : komunikat('Ta komórka jest pusta.', true);
  kartaKomorkiArk(w.id, m);
}

async function kartaKomorkiArk(wid, m) {
  let d;
  try { d = await api('budzet/komorka', { wiersz: wid, miesiac: m }); } catch (e) { return komunikat(e.message, true); }
  ARK.karta = { w: wid, m };
  const w = d.wiersz, k = $('#karta'), plan = d.planowanie;
  const worek = WOREK.includes(w.podstawa);
  const zablokowana = d.ma_rzeczywiste && !worek;
  const plany = d.platnosci.map(x => x.platnosc).filter(p => p.typ === 'plan');
  const wartosc = d.kwota ?? d.platnosci.reduce((a, x) => a + (x.platnosc.aktualna ? x.platnosc.netto : 0), 0);
  const inne = ARK.d.miesiace.filter(x => x !== m);
  const nieaktualne = plany.filter(p => p.aktualnosc === 'Nieaktualna' && p.aktualna);
  k.innerHTML = `<button class="zamknij" aria-label="Zamknij">×</button><h2>${esc(miesPelny(m))}</h2>
    <div class="szary">${esc(w.kontrahent || w.komentarz || 'Wiersz')} · ${esc(w.podstawa)} · ${esc(d.arkusz.nazwa)}</div>
    ${plan && !zablokowana ? komorkaHtml(w, m, d.kwota ?? (d.platnosci.length ? wartosc : null)) : ''}
    ${zablokowana ? '<p class="notka">W tej komórce jest płatność rzeczywista, więc kwoty komórki nie zmienisz (plan zastąpiła rzeczywista).</p>' : ''}
    ${plan && worek && d.ma_rzeczywiste ? `<p class="notka">Worek ma rzeczywiste na ${zl(d.rzeczywiste)}: kwoty nie zmniejszysz poniżej tej sumy.</p>` : ''}
    ${nieaktualne.length ? `<div class="komunikat"><span>Nieaktualne plany: ${nieaktualne.length}. Minął ich dzień wystawienia albo płatności. Napraw: przesuń dzień wystawienia na karcie planu niżej, przenieś kwotę na inny miesiąc albo usuń plan.</span></div>` : ''}
    ${plan && plany.length && !d.ma_rzeczywiste ? `<div class="akcje"><label class="szary">Przenieś kwotę na miesiąc</label><select data-przenies>${inne.map(x => `<option value="${x}">${esc(miesPelny(x))}</option>`).join('')}</select><button data-przenies-ok>Przenieś</button></div>` : ''}
    <p class="szary">${d.platnosci.length} ${d.platnosci.length === 1 ? 'płatność' : 'płatności'}${d.platnosci.some(x => (x.platnosc.odstepstwa || []).length) ? ' · <span class="inna">pomarańczowe</span>: inne niż w ustawieniach wiersza' : ''}</p>
    ${d.platnosci.map(x => htmlPlatnosci(x, { plan, wKomorce: true })).join('<hr>')}
    ${plan ? '<div class="akcje"><button data-ustawienia-wiersza>Ustawienia wiersza</button></div>' : ''}`;
  k.hidden = false;
  $('.zamknij', k).onclick = () => { k.hidden = true; ARK.karta = null; };
  if (plan && !zablokowana) podepnijKomorke(k, w, m);
  const b = k.querySelector('[data-przenies-ok]');
  if (b) b.onclick = () => przeniesKwote(w, m, k.querySelector('[data-przenies]').value, d);
  const u = k.querySelector('[data-ustawienia-wiersza]');
  if (u) u.onclick = () => kartaWiersza(wierszArk(wid) || w, ARK.d);
  podepnijPlatnosci(k, d.platnosci);
}

// B-MOD-11: kwota planu na inny miesiąc. Komórka z kwotą: przenosi kwotę (plany policzą się z reguł dla nowego miesiąca);
// plany z BS: każdy plan przechodzi z datami przesuniętymi o tyle samo miesięcy.
function przeniesKwote(w, m, m2, d) {
  const cel = (wierszArk(w.id)?.komorki || {})[m2];
  const blok = blokadaKomorki(wierszArk(w.id), m2);
  if (blok) return komunikat(`Nic nie przeniesiono. ${miesPelny(m2)}: ${blok}`, true);
  let ops;
  if (d.kwota != null) ops = [{ op: 'komorka', wiersz: w.id, miesiac: m, kwota: null },
    { op: 'komorka', wiersz: w.id, miesiac: m2, kwota: (wartoscKomorki(cel) || 0) + d.kwota }];
  else ops = d.platnosci.map(x => x.platnosc).filter(p => p.typ === 'plan').map(p => ({ op: 'platnosc', obiekt: { id: p.id, miesiac: m2 } }));
  ARK.karta = null;
  $('#karta').hidden = true;
  zapiszArk(ops.length === 1 ? ops[0] : { op: 'seria', operacje: ops });
}

// ---------- Akcje na zaznaczonych wierszach (A-OPS-08 do 13): pasek na dole, każda akcja jedną serią ----------
function zaznaczWiersz(id, wl, rysuj = true) {
  const i = ARK.zazn.indexOf(id);
  if (wl && i < 0) ARK.zazn.push(id);
  if (!wl && i >= 0) ARK.zazn.splice(i, 1);
  const tr = $('#ark-tabela')?.querySelector(`tr[data-w="${CSS.escape(id)}"]`);
  if (tr) { tr.classList.toggle('zazn', wl); const c = tr.querySelector('[data-zazn]'); if (c) c.checked = wl; }
  if (rysuj) pasekAkcji();
}

const liczbaPlatnosci = w => Object.values(w.komorki).reduce((a, c) => a + c.plany + c.rzeczywiste, 0);
const rodzinaPodstawy = p => ({ 'Faktura (w worku)': 'Faktura (jedna)', 'Bez faktury (w worku)': 'Bez faktury' })[p] || p;

function powodyAkcji(ws) {
  const rz = ws.filter(w => w.ma_rzeczywiste);
  return {
    usun: rz.length ? `Nie usuniesz wierszy z płatnościami rzeczywistymi (${rz.length}). Odznacz je albo wyczyść tylko plany.` : '',
    duplikuj: '',
    przenies: '',
    nowy: '',
    scal: ws.length < 2 ? 'Do scalenia zaznacz co najmniej dwa wiersze.'
      : new Set(ws.map(w => w.rodzaj)).size > 1 ? 'Scalić można tylko wiersze tego samego rodzaju (same wpływy albo same obciążenia).'
      : new Set(ws.map(w => rodzinaPodstawy(w.podstawa))).size > 1 ? 'Scalić można tylko wiersze o tej samej podstawie (faktura z fakturą w worku wolno).' : '',
    podziel: ws.length !== 1 ? 'Do podziału zaznacz jeden wiersz.' : UMOWY[ws[0].podstawa] ? 'Wiersza umowy nie podzielisz: wypłata, PIT i ZUS zostają razem.'
      : liczbaPlatnosci(ws[0]) < 2 ? 'Podzielić można tylko wiersz z co najmniej dwiema płatnościami.' : '',
    procent: ws.length !== 1 ? 'Do podziału procentem zaznacz jeden wiersz.' : ws[0].ma_rzeczywiste ? 'Wiersz ma płatności rzeczywiste: ich kwot nie dzielimy.'
      : WOREK.includes(ws[0].podstawa) || UMOWY[ws[0].podstawa] ? 'Procentem dzielisz tylko faktury jednej i bez faktury; worek i umowę zmieniasz kwotami w komórkach.' : '',
  };
}

function pasekAkcji() {
  const bar = $('#ark-akcje');
  if (!bar || !ARK) return;
  const ws = ARK.zazn.map(wierszArk).filter(Boolean);
  const wsz = $('#ark-wszystkie');
  if (wsz) { wsz.checked = ws.length > 0 && ws.length === ARK.d.wiersze.length; wsz.indeterminate = ws.length > 0 && ws.length < ARK.d.wiersze.length; }
  if (!ws.length) { bar.hidden = true; bar.innerHTML = ''; return; }
  const wp = ws.filter(w => w.rodzaj === 1).reduce((a, w) => a + sumaWiersza(w), 0), ob = ws.filter(w => w.rodzaj === -1).reduce((a, w) => a + sumaWiersza(w), 0);
  const pw = powodyAkcji(ws);
  const przycisk = (a, nazwa) => `<button data-a="${a}"${pw[a] ? ` disabled title="${esc(pw[a])}"` : ''}>${nazwa}</button>`;
  bar.innerHTML = `<span class="ile">Zaznaczone: <b>${ws.length}</b> ${ws.length === 1 ? 'wiersz' : ws.length < 5 ? 'wiersze' : 'wierszy'}</span>
    <span class="plus" title="suma wierszy wpływów">↗ ${zl(wp, false)}</span><span class="minus" title="suma wierszy obciążeń">↘ ${zl(ob, false)}</span>
    <span class="przyciski">${przycisk('usun', 'Usuń')}${przycisk('duplikuj', 'Duplikuj')}${przycisk('przenies', 'Przenieś do arkusza')}${przycisk('nowy', 'Przenieś do nowego arkusza')}
    ${przycisk('scal', 'Scal')}${przycisk('podziel', 'Podziel')}${przycisk('procent', 'Podziel procentem')}<button data-a="odznacz">Odznacz</button></span>`;
  bar.hidden = false;
  bar.querySelectorAll('button[data-a]').forEach(b => b.onclick = e => { e.stopPropagation(); akcjaWierszy(b.dataset.a, ws); });
}

function akcjaWierszy(a, ws) {
  const ids = ws.map(w => w.id), d = ARK.d;
  if (a === 'odznacz') { [...ARK.zazn].forEach(id => zaznaczWiersz(id, false, false)); return pasekAkcji(); }
  const wyczyscZazn = () => { ARK.zazn = []; };
  if (a === 'duplikuj') { wyczyscZazn(); return zapiszArk({ op: 'duplikuj', wiersze: ids, nowe: ids.map(() => nowyId('w')) }); }
  if (a === 'podziel') { wyczyscZazn(); return zapiszArk({ op: 'podziel', wiersz: ids[0] }); }
  const k = $('#karta');
  const lista = `<ul class="lista">${ws.map((w, i) => `<li>${i === 0 && a === 'scal' ? '<b>' : ''}${esc(w.kontrahent || '(bez kontrahenta)')} · ${esc(w.komentarz || w.przedmiot || '')} · ${esc(w.podstawa)} · ${zl(sumaWiersza(w), false)}${i === 0 && a === 'scal' ? '</b>' : ''}</li>`).join('')}</ul>`;
  const otworz = (tytul, tresc, ok) => {
    k.innerHTML = `<button class="zamknij" aria-label="Zamknij">×</button><h2>${tytul}</h2>${tresc}<div class="akcje"><button class="glowny" id="ak-ok">${tytul}</button><button id="ak-anuluj">Anuluj</button></div>`;
    k.hidden = false;
    $('.zamknij', k).onclick = $('#ak-anuluj').onclick = () => { k.hidden = true; };
    $('#ak-ok').onclick = ok;
    $('#ak-ok').focus();
  };
  if (a === 'usun') {
    const plany = ws.reduce((s, w) => s + liczbaPlatnosci(w), 0);
    return otworz('Usuń', `<p>Znikną wiersze (${ws.length}) i ich plany (${plany}). Cofniesz to Cmd+Z albo w Historii zmian.</p>${lista}`,
      () => { k.hidden = true; wyczyscZazn(); zapiszArk({ op: 'seria', operacje: ids.map(id => ({ op: 'wiersz', obiekt: { id }, usun: true })) }); });
  }
  if (a === 'scal') {
    return otworz('Scal', `<p>Powstanie jeden wiersz z opisem i ustawieniami pierwszego zaznaczonego (pogrubiony) i ze wszystkimi płatnościami pozostałych, bez sumowania kwot.
      Gdy w którymś miesiącu będzie kilka płatności, wiersz dostanie podstawę „w worku”.</p>${lista}`,
      () => { k.hidden = true; wyczyscZazn(); zapiszArk({ op: 'scal', wiersze: ids }); });
  }
  if (a === 'przenies') {
    const grupy = {};
    d.arkusze.filter(x => x.id !== d.arkusz.id).forEach(x => (grupy[x.folder] ||= []).push(x));
    return otworz('Przenieś', `<p>Wiersze (${ws.length}) przejdą razem z płatnościami do wybranego arkusza; płatności przejmą jego folder i kategorię.</p>${lista}
      ${pole('', 'Do arkusza', `<select id="ak-ark">${Object.entries(grupy).map(([f, xs]) => `<optgroup label="${esc(f)}">${xs.map(x => `<option value="${esc(x.id)}">${esc(x.nazwa)} (${mies(x.od)} - ${mies(x.do)})</option>`).join('')}</optgroup>`).join('')}</select>`)}`,
      () => { k.hidden = true; wyczyscZazn(); zapiszArk({ op: 'przenies', wiersze: ids, do_arkusza: $('#ak-ark').value }); });
  }
  if (a === 'nowy') {
    const a0 = d.arkusz;
    otworz('Przenieś do nowego arkusza', `<p>Powstanie nowy arkusz, a wiersze (${ws.length}) przejdą do niego razem z płatnościami.</p>${lista}
      <div class="formularz">${pole('', 'Nazwa (do 80 znaków)', `<input id="ak-nazwa" maxlength="80" value="${esc(`${a0.nazwa} - część`.slice(0, 80))}">`)}
      ${pole('', 'Folder', `<input id="ak-folder" list="ak-foldery" value="${esc(a0.folder)}">`)}<datalist id="ak-foldery">${[...new Set(d.arkusze.map(x => x.folder))].map(f => `<option value="${esc(f)}">`).join('')}</datalist>
      ${pole('', 'Kategoria', `<input id="ak-kategoria" list="ak-kategorie" value="${esc(a0.kategoria)}">`)}<datalist id="ak-kategorie">${[...new Set(d.arkusze.map(x => x.kategoria))].map(f => `<option value="${esc(f)}">`).join('')}</datalist>
      ${pole('', 'Od miesiąca', `<input id="ak-od" type="month" value="${esc(a0.od)}">`)}${pole('', 'Do miesiąca', `<input id="ak-do" type="month" value="${esc(a0.do)}">`)}</div>`,
      async () => {
        const o = { id: nowyId('a'), nazwa: $('#ak-nazwa').value.trim(), folder: $('#ak-folder').value.trim(), kategoria: $('#ak-kategoria').value.trim(), od: $('#ak-od').value, do: $('#ak-do').value };
        if (!o.nazwa || !o.folder || !o.kategoria || !o.od || !o.do) return komunikat('Uzupełnij nazwę, folder, kategorię i zakres miesięcy.', true);
        const r = await wyslijBud({ op: 'seria', operacje: [{ op: 'arkusz', obiekt: o }, { op: 'przenies', wiersze: ids, do_arkusza: o.id }] });
        if (!r.ok) return komunikat(r.blad, true);
        k.hidden = true; wyczyscZazn();
        komunikat(`Wiersze są w nowym arkuszu „${o.nazwa}”.`, false, { nazwa: 'Przejdź do niego', akcja: () => { location.hash = `#/budzet/arkusz?id=${encodeURIComponent(o.id)}`; } });
        await odswiezArkusz();
      });
    return;
  }
  if (a === 'procent') {
    const w = ws[0];
    return otworz('Podziel procentem', `<p>Powstanie drugi wiersz z podanym procentem kwoty każdej komórki; w pierwszym zostanie reszta. To nie jest „Podziel” z BS: tamto rozdziela płatności na osobne wiersze.</p>${lista}
      ${pole('', 'Ile procent do nowego wiersza', '<input id="ak-proc" inputmode="decimal" value="50">')}`, () => {
      const pm = /^(\d{1,2})(?:[.,](\d{1,2}))?$/.exec($('#ak-proc').value.trim());
      const bp = pm ? +pm[1] * 100 + +((pm[2] || '') + '00').slice(0, 2) : 0;   // setne części procenta
      if (!(bp > 0 && bp < 10000)) return komunikat('Procent między 0 a 100, najwyżej dwa miejsca po przecinku.', true);
      const id = nowyId('w'), ops = [{ op: 'duplikuj', wiersze: [w.id], nowe: [id] }];
      for (const [m, c] of Object.entries(w.komorki)) {
        const kw = wartoscKomorki(c), czesc = Math.floor((kw * bp + 5000) / 10000);
        ops.push({ op: 'komorka', wiersz: id, miesiac: m, kwota: czesc }, { op: 'komorka', wiersz: w.id, miesiac: m, kwota: kw - czesc });
      }
      k.hidden = true; wyczyscZazn();
      zapiszArk({ op: 'seria', operacje: ops });
    });
  }
}

// ---------- Zarządzaj (A-OPS-01 do 07): dodaj, nazwa, zakres miesięcy, folder i kategoria, duplikat, przypięcie, usunięcie ----------
function menuZarzadzaj(przycisk, d) {
  document.querySelectorAll('.zarzadzaj-menu').forEach(x => x.remove());
  const m = document.createElement('div');
  m.className = 'zarzadzaj-menu';
  const wyl = d.planowanie ? '' : ` disabled title="${esc(tekstPodgladu(d))}"`;
  const maRz = d.wiersze.some(w => w.ma_rzeczywiste);
  m.innerHTML = `<button data-m="nazwa"${wyl}>${ik('dokument')}Zmień nazwę</button>
    <button data-m="zakres"${wyl}>${ik('kalendarz')}Zmodyfikuj czas trwania</button>
    <button data-m="miejsce"${wyl}>${ik('folder')}Zmień folder / kategorię</button>
    <button data-m="duplikuj"${wyl}>${ik('warstwy')}Duplikuj</button>
    <button data-m="pin"${d.systemowy ? ' disabled title="Arkusz systemowy jest zawsze przypięty."' : wyl}>${ik('pinezka')}${d.arkusz.przypiety ? 'Odepnij z drzewa' : 'Przypnij do drzewa'}</button>
    <button data-m="usun"${d.planowanie && maRz ? ' disabled title="Arkusz ma płatności rzeczywiste, więc go nie usuniesz. Przenieś wiersze z rzeczywistymi do innego arkusza."' : wyl}>${ik('zamknij')}Usuń arkusz</button>
    <div class="oddziel"></div>
    <a href="/api/eksport/arkusz?id=${encodeURIComponent(d.arkusz.id)}">${ik('plik')}Eksport arkusza do Excela</a>
    ${d.planowanie ? `<button data-m="wiersz">${ik('plus')}Dodaj wiersz (pełny formularz)</button><button data-m="nowy">${ik('plus')}Dodaj nowy arkusz</button>` : ''}
    <a href="#/budzet/historia">${ik('historia')}Historia zmian planów</a>`;
  const r = przycisk.getBoundingClientRect();
  m.style.left = `${r.left + window.scrollX}px`; m.style.top = `${r.bottom + window.scrollY + 2}px`;
  document.body.appendChild(m);
  const akcje = { nazwa: kartaNazwy, zakres: kartaZakresu, miejsce: kartaMiejsca, duplikuj: kartaDuplikatu, usun: kartaUsunieciaArkusza, wiersz: x => kartaWiersza(null, x),
    pin: x => przypnijArkusz(x.arkusz.id, !x.arkusz.przypiety), nowy: () => kartaArkusza(null, { foldery: [] }) };
  m.querySelectorAll('button[data-m]').forEach(b => b.onclick = e => { e.stopPropagation(); m.remove(); akcje[b.dataset.m](d); });
  setTimeout(() => document.addEventListener('click', () => m.remove(), { once: true }));
}

function kartaFormularza(tytul, tresc, przycisk, ok) {
  const k = $('#karta');
  k.innerHTML = `<button class="zamknij" aria-label="Zamknij">×</button><h2>${tytul}</h2>${tresc}<div class="akcje"><button class="glowny" id="z-ok">${przycisk}</button><button id="z-anuluj">Anuluj</button></div>`;
  k.hidden = false;
  $('.zamknij', k).onclick = $('#z-anuluj').onclick = () => { k.hidden = true; };
  $('#z-ok').onclick = ok;
  k.querySelectorAll('input').forEach(i => i.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); ok(); } }));
  return k;
}

async function zmianaArkusza(dane, cel = null) {
  const r = await wyslijBud(dane);
  if (!r.ok) return komunikat(r.blad, true), false;
  $('#karta').hidden = true;
  await sprawdzStan();
  if (cel) location.hash = cel; else await pokaz();
  komunikat('Zapisane.', false, { nazwa: 'Cofnij', akcja: cofnijOstatni });
  return true;
}

function kartaNazwy(d) {
  const k = kartaFormularza('Zmień nazwę', `<div class="formularz">${pole('', 'Nazwa arkusza (do 80 znaków, nie musi być unikalna)', `<input id="z-nazwa" maxlength="80" value="${esc(d.arkusz.nazwa)}">`)}</div>
    <p class="szary" id="z-licznik"></p><p class="szary">Nowa nazwa od razu widać na płatnościach, w cash flow i rentowności.</p>`, 'Zmień nazwę', () => {
    const nazwa = $('#z-nazwa').value.trim();
    if (!nazwa) return komunikat('Nazwa arkusza nie może być pusta.', true);
    if (nazwa.length > 80) return komunikat('Nazwa arkusza może mieć najwyżej 80 znaków. Skróć ją.', true);
    if (nazwa === d.arkusz.nazwa) return komunikat('Nazwa jest taka sama.', true);
    zmianaArkusza({ op: 'arkusz', obiekt: { id: d.arkusz.id, nazwa } });
  });
  const inp = $('#z-nazwa', k), licz = () => { $('#z-licznik').textContent = `${inp.value.length} / 80 znaków`; };
  inp.oninput = licz; licz(); inp.focus(); inp.select();
}

function kartaMiejsca(d) {
  const foldery = {};
  (d.slowniki?.struktura || []).forEach(x => { foldery[x.folder] = new Set(x.kategorie); });   // pakiet 4: kolejność i puste z Biblioteki
  d.arkusze.filter(x => !String(x.id).startsWith('sys:')).forEach(x => (foldery[x.folder] ||= new Set()).add(x.kategoria));
  let folder = d.arkusz.folder, kategoria = d.arkusz.kategoria;
  const k = kartaFormularza('Zmień folder / kategorię', '<div class="dwie-kolumny" id="z-miejsce"></div>', 'Przenieś arkusz', () => {
    const f = ($('#z-nowy-folder').value.trim() || folder), kat = ($('#z-nowa-kategoria').value.trim() || kategoria);
    const istF = Object.keys(foldery).find(x => x.toLowerCase() === f.toLowerCase());
    if ($('#z-nowy-folder').value.trim() && istF) return komunikat(`Folder „${istF}” już jest. Wybierz go z listy zamiast dodawać drugi raz.`, true);
    const istK = [...(foldery[istF || f] || [])].find(x => x.toLowerCase() === kat.toLowerCase());
    if ($('#z-nowa-kategoria').value.trim() && istK) return komunikat(`Kategoria „${istK}” już jest w tym folderze. Wybierz ją z listy.`, true);
    if (!f || !kat) return komunikat('Wybierz folder i kategorię albo wpisz nowe.', true);
    if (f.length > 80 || kat.length > 80) return komunikat('Nazwa folderu i kategorii: najwyżej 80 znaków.', true);
    if (f === d.arkusz.folder && kat === d.arkusz.kategoria) return komunikat('Arkusz już jest w tym miejscu.', true);
    zmianaArkusza({ op: 'arkusz', obiekt: { id: d.arkusz.id, folder: f, kategoria: kat } });
  });
  const rysuj = () => {
    $('#z-miejsce', k).innerHTML = `<div><h3>Folder</h3><div class="wybor-lista">${Object.keys(foldery).map(f => `<button data-f="${esc(f)}" class="${f === folder ? 'aktywna' : ''}">${esc(f)}</button>`).join('')}</div>
        ${pole('', 'albo nowy folder', '<input id="z-nowy-folder" maxlength="80">')}</div>
      <div><h3>Kategoria</h3><div class="wybor-lista">${[...(foldery[folder] || [])].map(x => `<button data-k="${esc(x)}" class="${x === kategoria ? 'aktywna' : ''}">${esc(x)}</button>`).join('') || '<span class="szary">nowy folder: wpisz kategorię</span>'}</div>
        ${pole('', 'albo nowa kategoria', '<input id="z-nowa-kategoria" maxlength="80">')}</div>`;
    k.querySelectorAll('[data-f]').forEach(b => b.onclick = e => { e.stopPropagation(); folder = b.dataset.f; if (!foldery[folder].has(kategoria)) kategoria = [...foldery[folder]][0]; rysuj(); });
    k.querySelectorAll('[data-k]').forEach(b => b.onclick = e => { e.stopPropagation(); kategoria = b.dataset.k; rysuj(); });
    k.querySelectorAll('#z-miejsce .aktywna').forEach(b => b.scrollIntoView({ block: 'nearest' }));
  };
  rysuj();
}

// Kalendarz zakresu (A-OPS-04): klik miesiąc startu, potem miesiąc końca; kłódka = są rzeczywiste (miesiąc musi zostać),
// znak planu = są plany (można wyciąć, plany znikną). Druga zakładka: przesunięcie startu (A-OPS-05).
function kartaZakresu(d) {
  const a = d.arkusz, flagi = {};
  d.wiersze.forEach(w => Object.entries(w.komorki).forEach(([m, c]) => { const f = flagi[m] ||= { rz: 0, pl: 0 }; f.rz += c.rzeczywiste; f.pl += c.plany || (!c.rzeczywiste ? 1 : 0); }));
  Object.entries(d.poza_zakresem || {}).forEach(([m, x]) => { const f = flagi[m] ||= { rz: 0, pl: 0 }; f.rz += x.rzeczywiste; f.pl += x.plany; });
  const maRz = Object.values(flagi).some(f => f.rz);
  let od = a.od, doo = a.do, krok = 0, zakladka = 'zakres';
  const lata = Object.keys(flagi).map(m => +m.slice(0, 4)).concat([+a.od.slice(0, 4), +a.do.slice(0, 4)]);
  const r0 = Math.min(...lata) - 1, r1 = Math.max(...lata) + 2;
  const ileMies = (x, y) => (+y.slice(0, 4) - +x.slice(0, 4)) * 12 + +y.slice(5, 7) - +x.slice(5, 7) + 1;
  const k = kartaFormularza('Zmodyfikuj czas trwania', `<div class="zakladki" role="tablist"><button role="tab" data-z="zakres">Nowy zakres</button><button role="tab" data-z="przesun">Przesuń miesiąc startu</button></div><div id="z-zakres"></div>`, 'Zmień zakres dat', () => zastosuj());
  const rysuj = () => {
    k.querySelectorAll('[data-z]').forEach(b => b.setAttribute('aria-selected', String(b.dataset.z === zakladka)));
    const box = $('#z-zakres', k);
    if (zakladka === 'przesun') {
      $('#z-ok').textContent = 'Przesuń arkusz';
      $('#z-ok').disabled = maRz;
      box.innerHTML = maRz ? '<p class="notka">Arkusz ma płatności rzeczywiste, więc jego startu nie przesuniesz. Zmień zakres w zakładce „Nowy zakres” albo zduplikuj arkusz z przesunięciem startu.</p>'
        : `<p class="notka">Cały arkusz przesunie się bez zmiany długości; kwoty przejdą o tyle samo miesięcy, a plany policzą się na nowo z ustawień wierszy (ręczne zmiany pojedynczych planów przepadną).</p>
          <div class="formularz">${pole('', 'Nowy miesiąc startu', `<input id="z-start" type="month" value="${esc(a.od)}">`)}</div><p class="szary" id="z-podglad"></p>`;
      const s = $('#z-start', k);
      if (s) { const p = () => { const o = ileMies(a.od, s.value || a.od) - 1; $('#z-podglad').textContent = o ? `Przesunięcie o ${o > 0 ? '+' : ''}${o} mies.: ${mies(a.od)} - ${mies(a.do)} → ${mies(nastMies(a.od, o))} - ${mies(nastMies(a.do, o))}.` : 'Wybierz inny miesiąc niż obecny start.'; }; s.oninput = p; p(); }
      return;
    }
    $('#z-ok').textContent = 'Zmień zakres dat';
    const wyciete = Object.entries(flagi).filter(([m, f]) => m >= a.od && m <= a.do && (m < od || m > doo));
    const rzPoza = Object.entries(flagi).filter(([m, f]) => f.rz && (m < od || m > doo)).map(([m]) => m).sort();
    const plPoza = wyciete.filter(([, f]) => f.pl && !f.rz);
    const n = ileMies(od, doo);
    $('#z-ok').disabled = !!rzPoza.length || n > 240 || (od === a.od && doo === a.do);
    box.innerHTML = `<p class="szary">${krok ? '<b>Teraz kliknij miesiąc końca.</b>' : 'Kliknij miesiąc startu, a potem miesiąc końca.'}</p>
      <div class="kalendarz-ark">${[...Array(r1 - r0 + 1)].map((_, i) => r0 + i).map(r => `<div class="rok">${r}</div>${[...Array(12)].map((_, j) => {
        const m = `${r}-${String(j + 1).padStart(2, '0')}`, f = flagi[m];
        const kl = [m >= od && m <= doo ? 'w-zakresie' : '', m >= a.od && m <= a.do ? 'obecny' : '', f?.rz ? 'rz' : '', m === od || m === doo ? 'kraniec' : ''].filter(Boolean).join(' ');
        return `<button data-m="${m}" class="${kl}" title="${esc(miesPelny(m))}${f?.rz ? ': płatności rzeczywiste, miesiąc musi zostać' : f?.pl ? ': są plany' : ''}">${MIES_KROTKO[j]}${f?.rz ? ik('klodka', 'mini') : f?.pl ? '<span class="dolar">$</span>' : ''}</button>`;
      }).join('')}`).join('')}</div>
      <p><b>${esc(miesPelny(od))} do ${esc(miesPelny(doo))}</b> · ${n} mies.${n > 240 ? ' <span class="minus">(najwyżej 240, czyli 20 lat)</span>' : ''}</p>
      ${rzPoza.length ? `<p class="minus">Miesiące z płatnościami rzeczywistymi muszą zostać w zakresie: ${esc(rzPoza.map(miesPelny).join(', '))}.</p>` : ''}
      ${plPoza.length ? `<p class="ostrzezenie-tekst">Plany z wyciętych miesięcy zostaną usunięte: ${esc(plPoza.map(([m, f]) => `${miesPelny(m)} (wiersze z planami: ${f.pl})`).join(', '))}.</p>` : ''}
      <p class="szary">${ik('klodka', 'mini')} są płatności rzeczywiste · <span class="dolar">$</span> są plany · ramka: obecny zakres</p>`;
    box.querySelectorAll('[data-m]').forEach(b => b.onclick = e => {
      e.stopPropagation();   // przycisk znika przy przerysowaniu, a karta zamyka się na klik „poza nią”
      const m = b.dataset.m;
      if (!krok) { od = doo = m; krok = 1; } else { if (m < od) od = m; else doo = m; krok = 0; }
      rysuj();
    });
  };
  const zastosuj = () => {
    if (zakladka === 'przesun') {
      const s = $('#z-start').value, o = ileMies(a.od, s) - 1;
      if (!s || !o) return komunikat('Wybierz inny miesiąc startu niż obecny.', true);
      return zmianaArkusza({ op: 'przesun_arkusz', arkusz: a.id, o });
    }
    zmianaArkusza({ op: 'arkusz', obiekt: { id: a.id, od, do: doo } });
  };
  k.querySelectorAll('[data-z]').forEach(b => b.onclick = e => { e.stopPropagation(); zakladka = b.dataset.z; rysuj(); });
  rysuj();
}

function kartaDuplikatu(d) {
  const a = d.arkusz, dl = (+a.do.slice(0, 4) - +a.od.slice(0, 4)) * 12 + +a.do.slice(5, 7) - +a.od.slice(5, 7);
  const k = kartaFormularza('Duplikuj arkusz', `<div class="formularz">
      ${pole('', 'Nazwa kopii (do 80 znaków)', `<input id="z-nazwa" maxlength="80" value="${esc(`${a.nazwa} - kopia`.slice(0, 80))}">`)}
      ${pole('', 'Folder', `<input id="z-folder" list="z-foldery" value="${esc(a.folder)}">`)}<datalist id="z-foldery">${[...new Set(d.arkusze.map(x => x.folder))].map(f => `<option value="${esc(f)}">`).join('')}</datalist>
      ${pole('', 'Kategoria', `<input id="z-kategoria" list="z-kategorie" value="${esc(a.kategoria)}">`)}<datalist id="z-kategorie">${[...new Set(d.arkusze.map(x => x.kategoria))].map(f => `<option value="${esc(f)}">`).join('')}</datalist>
      <fieldset class="radio"><legend>Zakres miesięcy</legend>
        <label><input type="radio" name="z-tryb" value="bez" checked>Bez zmian (${mies(a.od)} - ${mies(a.do)})</label>
        <label><input type="radio" name="z-tryb" value="wybierz">Wybierz zakres: wartości tylko w miesiącach wspólnych</label>
        <label><input type="radio" name="z-tryb" value="przesun">Przesuń miesiąc startu: ta sama długość, wartości przesunięte</label></fieldset>
      ${pole('', 'Od miesiąca', `<input id="z-od" type="month" value="${esc(nastMies(a.od, 12))}">`)}${pole('', 'Do miesiąca', `<input id="z-do" type="month" value="${esc(nastMies(a.do, 12))}">`)}
      <label class="przelacznik"><input type="checkbox" id="z-wartosci"><span class="suwak"></span>Duplikuj wartości (kwoty komórek)</label></div>
    <p class="szary" id="z-opis"></p>`, 'Duplikuj arkusz', () => {
    const tryb = k.querySelector('input[name="z-tryb"]:checked').value;
    const nazwa = $('#z-nazwa').value.trim(), folder = $('#z-folder').value.trim(), kategoria = $('#z-kategoria').value.trim();
    if (!nazwa || !folder || !kategoria) return komunikat('Uzupełnij nazwę, folder i kategorię kopii.', true);
    let od = a.od, doo = a.do, przes = 0;
    if (tryb === 'wybierz') { od = $('#z-od').value; doo = $('#z-do').value; }
    if (tryb === 'przesun') { od = $('#z-od').value; przes = (+od.slice(0, 4) - +a.od.slice(0, 4)) * 12 + +od.slice(5, 7) - +a.od.slice(5, 7); doo = nastMies(a.do, przes); }
    if (!od || !doo || od > doo) return komunikat('Zakres kopii: początek nie może być po końcu.', true);
    const id = nowyId('a');
    zmianaArkusza({ op: 'duplikuj_arkusz', arkusz: a.id, obiekt: { id, nazwa, folder, kategoria, od, do: doo }, przesuniecie: przes, wartosci: $('#z-wartosci').checked },
      `#/budzet/arkusz?id=${encodeURIComponent(id)}`);
  });
  const opis = () => {
    const tryb = k.querySelector('input[name="z-tryb"]:checked').value;
    $('#z-od').closest('.pole').hidden = tryb === 'bez';
    $('#z-do').closest('.pole').hidden = tryb !== 'wybierz';
    if (tryb === 'przesun') $('#z-od').closest('.pole').querySelector('span').textContent = 'Nowy miesiąc startu';
    else $('#z-od').closest('.pole').querySelector('span').textContent = 'Od miesiąca';
    const od = $('#z-od').value;
    $('#z-opis').textContent = `${$('#z-wartosci').checked ? 'Kopia dostanie wiersze, sekcje, ustawienia i kwoty komórek; wszystkie płatności oryginału (plany i rzeczywiste) staną się w kopii nowymi planami z ustawień wiersza.'
      : 'Kopia dostanie tylko strukturę: wiersze, sekcje i ustawienia, bez kwot (szablon).'}${tryb === 'przesun' && od ? ` Zakres kopii: ${mies(od)} - ${mies(nastMies(od, dl))}.` : ''}`;
  };
  const pola = k.querySelector('.formularz');   // nie #karta: ten element służy też innym kartom
  pola.addEventListener('change', opis);
  pola.addEventListener('input', opis);
  opis();
  $('#z-nazwa').focus();
}

function kartaUsunieciaArkusza(d) {
  const plany = d.wiersze.reduce((s, w) => s + liczbaPlatnosci(w), 0);
  kartaFormularza('Usuń arkusz', `<p>Arkusz „${esc(d.arkusz.nazwa)}” zniknie razem z wierszami (${d.wiersze.length}) i planami (${plany}).
    Cofniesz to w Historii zmian (Cmd+Z na innym arkuszu też cofa ostatnią zmianę).</p>`, 'Usuń arkusz',
  () => zmianaArkusza({ op: 'arkusz', obiekt: { id: d.arkusz.id }, usun: true }, '#/budzet/arkusze'));
}

'use strict';
// Wykresy Finanse DigitalH: słupki (grupy i stosy, wartości ujemne), linia z obszarem i celownikiem.
// Bez bibliotek i CDN. Jedna oś Y. Kolory z tokenów CSS (--s1..--s4, --szary-seria, --minus), osobne dla trybu ciemnego.
// Podpowiedź po najechaniu, legenda włącza i wyłącza serie, kliknięcie w kolumnę wywołuje naKlik(indeks).
// Teksty zawsze przez textContent (nazwy kontrahentów to dane z plików).

const Wykresy = (() => {
  const NS = 'http://www.w3.org/2000/svg';
  const ruchOk = () => !window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function el(nazwa, atrybuty = {}, rodzic) {
    const e = document.createElementNS(NS, nazwa);
    for (const [k, v] of Object.entries(atrybuty)) e.setAttribute(k, v);
    if (rodzic) rodzic.appendChild(e);
    return e;
  }

  function kolor(token) {
    return getComputedStyle(document.documentElement).getPropertyValue(token).trim() || '#888';
  }

  // Czytelne podziałki: 0 / 20 tys. / 40 tys.
  function podzialki(min, max, ile = 5) {
    if (min === max) max = min + 1;
    const surowy = (max - min) / ile;
    const rzad = 10 ** Math.floor(Math.log10(surowy));
    const krok = [1, 2, 2.5, 5, 10].map(x => x * rzad).find(x => x >= surowy);
    const od = Math.floor(min / krok) * krok, doo = Math.ceil(max / krok) * krok;
    const wynik = [];
    for (let v = od; v <= doo + krok / 2; v += krok) wynik.push(Math.round(v));
    return wynik;
  }

  function krotko(gr) {
    const zl = gr / 100, a = Math.abs(zl);
    if (a >= 1e6) return `${(zl / 1e6).toFixed(1).replace('.', ',')} mln`;
    if (a >= 1000) return `${Math.round(zl / 1000)} tys.`;
    return `${Math.round(zl)}`;
  }

  function pelna(gr) {
    const znak = gr < 0 ? '-' : '', a = Math.abs(Math.round(gr));
    return `${znak}${String(Math.floor(a / 100)).replace(/\B(?=(\d{3})+(?!\d))/g, ' ')},${String(a % 100).padStart(2, '0')} zł`;
  }

  // Słupek z zaokrąglonym końcem danych (4px) i prostą podstawą.
  function sciezkaSlupka(x, y0, y1, w) {
    const gora = Math.min(y0, y1), dol = Math.max(y0, y1), h = dol - gora;
    const r = Math.min(4, h, w / 2);
    if (h <= 0.5) return `M${x},${y0}h${w}`;
    if (y1 < y0) return `M${x},${dol}V${gora + r}q0,-${r} ${r},-${r}h${w - 2 * r}q${r},0 ${r},${r}V${dol}Z`;
    return `M${x},${gora}V${dol - r}q0,${r} ${r},${r}h${w - 2 * r}q${r},0 ${r},-${r}V${gora}Z`;
  }

  function podpowiedz(ramka) {
    let t = ramka.querySelector('.wyk-podpowiedz');
    if (!t) { t = document.createElement('div'); t.className = 'wyk-podpowiedz'; t.hidden = true; ramka.appendChild(t); }
    return {
      pokaz(tytul, wiersze, x, y) {
        t.replaceChildren();
        const h = document.createElement('div'); h.className = 'wyk-pp-tytul'; h.textContent = tytul; t.appendChild(h);
        for (const w of wiersze) {
          const r = document.createElement('div'); r.className = 'wyk-pp-wiersz' + (w.suma ? ' suma' : '');
          const k = document.createElement('i'); if (w.kolor) k.style.background = w.kolor; else k.className = 'pusty';
          const v = document.createElement('b'); v.textContent = w.wartosc;
          const n = document.createElement('span'); n.textContent = w.nazwa;
          r.append(k, v, n); t.appendChild(r);
        }
        t.hidden = false;
        const szer = ramka.clientWidth, tw = t.offsetWidth;
        t.style.left = `${Math.max(4, Math.min(szer - tw - 4, x + 14))}px`;
        t.style.top = `${Math.max(4, y - t.offsetHeight - 8)}px`;
      },
      ukryj() { t.hidden = true; },
    };
  }

  function legenda(ramka, serie, ukryte, naZmiane) {
    let l = ramka.querySelector('.wyk-legenda');
    if (!l) { l = document.createElement('div'); l.className = 'wyk-legenda'; ramka.prepend(l); }
    l.replaceChildren();
    for (const s of serie) {
      if (s.bezLegendy) continue;
      const b = document.createElement('button');
      b.type = 'button';
      b.setAttribute('aria-pressed', String(!ukryte.has(s.klucz)));
      b.title = 'Kliknij, żeby ukryć albo pokazać';
      const k = document.createElement('i'); k.className = s.typ === 'linia' ? 'linia' : ''; k.style.background = s.kolor;
      const n = document.createElement('span'); n.textContent = s.nazwa;
      b.append(k, n);
      b.onclick = () => { ukryte.has(s.klucz) ? ukryte.delete(s.klucz) : ukryte.add(s.klucz); naZmiane(); };
      l.appendChild(b);
    }
  }

  // ---------- Słupki ----------
  // opcje: { kategorie: [etykieta], etykietyPelne?: [..], serie: [{klucz, nazwa, kolor, wartosci, stos?, kolorUjemny?}],
  //          wysokosc, naKlik(i), sumaStosu?: {stos: nazwa}, niepelne?: [i] }
  function slupki(ramka, opcje) {
    ramka.classList.add('wyk');
    const ukryte = new Set(opcje.ukryte || []);
    const svg = ramka.querySelector('svg') || el('svg', { role: 'img', 'aria-label': opcje.opis || 'wykres' }, ramka);
    const pp = podpowiedz(ramka);
    const elementy = new Map();

    function rysuj() {
      legenda(ramka, opcje.serie, ukryte, rysuj);
      const W = ramka.clientWidth || 600, H = opcje.wysokosc || 240;
      const m = { l: 54, r: 8, t: 10, b: 26 };
      svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
      svg.setAttribute('width', W); svg.setAttribute('height', H);
      const wszystkieWidoczne = opcje.serie.filter(s => !ukryte.has(s.klucz));
      const linie = wszystkieWidoczne.filter(s => s.typ === 'linia');
      const widoczne = wszystkieWidoczne.filter(s => s.typ !== 'linia');
      const stosy = [...new Set(widoczne.map(s => s.stos || s.klucz))];
      const n = opcje.kategorie.length;
      // zakres: sumy dodatnie i ujemne w stosach
      let min = 0, max = 0;
      for (let i = 0; i < n; i++) for (const st of stosy) {
        let plus = 0, minus = 0;
        for (const s of widoczne.filter(s => (s.stos || s.klucz) === st)) { const v = s.wartosci[i] || 0; v >= 0 ? plus += v : minus += v; }
        max = Math.max(max, plus); min = Math.min(min, minus);
      }
      for (const s of linie) for (const v of s.wartosci) { max = Math.max(max, v || 0); min = Math.min(min, v || 0); }
      const ticks = podzialki(min, max, 4);
      const yMin = ticks[0], yMax = ticks[ticks.length - 1];
      const y = v => m.t + (H - m.t - m.b) * (1 - (v - yMin) / (yMax - yMin || 1));
      const pasmo = (W - m.l - m.r) / Math.max(n, 1);
      const szer = Math.min(24, (pasmo * 0.72 - 2 * (stosy.length - 1)) / Math.max(stosy.length, 1));
      const grupa = stosy.length * szer + (stosy.length - 1) * 2;

      // siatka i oś
      let siatka = svg.querySelector('g.siatka'); if (!siatka) siatka = el('g', { class: 'siatka' }, svg);
      siatka.replaceChildren();
      for (const t of ticks) {
        el('line', { x1: m.l, x2: W - m.r, y1: y(t), y2: y(t), class: t === 0 ? 'zero' : '' }, siatka);
        const tx = el('text', { x: m.l - 8, y: y(t) + 4, 'text-anchor': 'end' }, siatka); tx.textContent = krotko(t);
      }
      opcje.kategorie.forEach((k, i) => {
        const tx = el('text', { x: m.l + pasmo * i + pasmo / 2, y: H - 8, 'text-anchor': 'middle',
          class: opcje.niepelne?.includes(i) ? 'niepelny' : '' }, siatka);
        tx.textContent = k;
      });
      let warstwa = svg.querySelector('g.slupki'); if (!warstwa) warstwa = el('g', { class: 'slupki' }, svg);
      // słupki: każdy segment ma stały element (animacja między stanami)
      const uzyte = new Set();
      for (let i = 0; i < n; i++) {
        stosy.forEach((st, si) => {
          const x = m.l + pasmo * i + (pasmo - grupa) / 2 + si * (szer + 2);
          let plus = 0, minus = 0;
          const wStosie = widoczne.filter(s => (s.stos || s.klucz) === st);
          wStosie.forEach((s, idx) => {
            const v = s.wartosci[i] || 0, id = `${s.klucz}|${i}`;
            uzyte.add(id);
            let e = elementy.get(id);
            if (!e) { e = el('path', { class: 'slupek' }, warstwa); elementy.set(id, e); e._stan = { a: y(0), b: y(0) }; }
            e.setAttribute('fill', v < 0 && s.kolorUjemny ? s.kolorUjemny : s.kolor);
            const od = v >= 0 ? plus : minus, doo = od + v;
            v >= 0 ? plus = doo : minus = doo;
            // 2px przerwy w kolorze tła między segmentami stosu
            const gap = idx > 0 && wStosie.length > 1 ? 1 : 0;
            const a = y(od) - (v >= 0 ? gap : -gap), b = y(doo);
            const ostatni = idx === wStosie.length - 1 || wStosie.slice(idx + 1).every(z => !(z.wartosci[i]) || Math.sign(z.wartosci[i]) !== Math.sign(v));
            animujSlupek(e, x, a, b, szer, ostatni);
          });
        });
      }
      for (const [id, e] of elementy) if (!uzyte.has(id)) { e.remove(); elementy.delete(id); }

      // linie (np. saldo narastająco) na tej samej osi, 2px, kropka na końcu
      let wLinie = svg.querySelector('g.linie'); if (!wLinie) wLinie = el('g', { class: 'linie' }, svg);
      wLinie.replaceChildren();
      for (const s of linie) {
        const pts = s.wartosci.map((v, i) => `${(m.l + pasmo * i + pasmo / 2).toFixed(1)},${y(v || 0).toFixed(1)}`);
        el('polyline', { points: pts.join(' '), fill: 'none', stroke: s.kolor, 'stroke-width': 2, 'stroke-linejoin': 'round',
          'stroke-linecap': 'round', 'stroke-dasharray': s.przerywana ? '5 4' : '' }, wLinie);
        const [lx, ly] = pts[pts.length - 1].split(',');
        el('circle', { cx: lx, cy: ly, r: 4, fill: s.kolor, stroke: 'var(--tlo)', 'stroke-width': 2 }, wLinie);
      }

      // strefy najechania i kliknięcia: całe pasmo kategorii
      let strefy = svg.querySelector('g.strefy'); if (!strefy) strefy = el('g', { class: 'strefy' }, svg);
      strefy.replaceChildren();
      for (let i = 0; i < n; i++) {
        const r = el('rect', { x: m.l + pasmo * i, y: m.t, width: pasmo, height: H - m.t - m.b, fill: 'transparent', tabindex: 0,
          class: opcje.naKlik ? 'klik' : '' }, strefy);
        const pokaz = ev => {
          strefy.querySelectorAll('rect').forEach(z => z.classList.toggle('aktywna', z === r));
          const wiersze = wszystkieWidoczne.map(s => ({ nazwa: s.nazwa, wartosc: pelna(s.wartosci[i] || 0), kolor: s.kolor }));
          for (const [st, nazwa] of Object.entries(opcje.sumaStosu || {})) {
            const wSt = widoczne.filter(s => s.stos === st);
            if (wSt.length > 1) wiersze.push({ nazwa, wartosc: pelna(wSt.reduce((a, s) => a + (s.wartosci[i] || 0), 0)), suma: true });
          }
          const box = ramka.getBoundingClientRect();
          const px = ev?.clientX ? ev.clientX - box.left : m.l + pasmo * (i + 0.5);
          const py = ev?.clientY ? ev.clientY - box.top : m.t + 20;
          pp.pokaz((opcje.etykietyPelne || opcje.kategorie)[i] + (opcje.niepelne?.includes(i) ? ' (niepełny)' : ''), wiersze, px, py);
        };
        r.addEventListener('pointermove', pokaz);
        r.addEventListener('focus', () => pokaz());
        r.addEventListener('pointerleave', () => { pp.ukryj(); r.classList.remove('aktywna'); });
        r.addEventListener('blur', () => pp.ukryj());
        if (opcje.naKlik) {
          r.addEventListener('click', () => opcje.naKlik(i));
          r.addEventListener('keydown', e => { if (e.key === 'Enter') opcje.naKlik(i); });
        }
      }
    }

    function animujSlupek(e, x, a, b, w, zaokraglij) {
      const start = e._stan || { a, b }, cel = { a, b };
      const t0 = performance.now(), czas = ruchOk() ? 380 : 0;
      e._stan = cel;
      const rysujKlatke = (aa, bb) => e.setAttribute('d', zaokraglij ? sciezkaSlupka(x, aa, bb, w)
        : `M${x},${Math.min(aa, bb)}h${w}V${Math.max(aa, bb)}h${-w}Z`);
      if (!czas) return rysujKlatke(a, b);
      const krok = t => {
        const p = Math.min(1, (t - t0) / czas), q = 1 - (1 - p) ** 3;
        rysujKlatke(start.a + (a - start.a) * q, start.b + (b - start.b) * q);
        if (p < 1) requestAnimationFrame(krok);
      };
      requestAnimationFrame(krok);
    }

    rysuj();
    new ResizeObserver(() => rysuj()).observe(ramka);
    return { rysuj };
  }

  // ---------- Linia z obszarem i celownikiem ----------
  // opcje: { punkty: [{x: 'RRRR-MM-DD', y: grosze}], nazwa, kolor, wysokosc, etykietaX(x) }
  function linia(ramka, opcje) {
    ramka.classList.add('wyk');
    const svg = ramka.querySelector('svg') || el('svg', { role: 'img', 'aria-label': opcje.opis || 'wykres' }, ramka);
    const pp = podpowiedz(ramka);
    const pkt = opcje.punkty;
    function rysuj() {
      svg.replaceChildren();
      const W = ramka.clientWidth || 600, H = opcje.wysokosc || 220;
      const m = { l: 54, r: 12, t: 12, b: 26 };
      svg.setAttribute('viewBox', `0 0 ${W} ${H}`); svg.setAttribute('width', W); svg.setAttribute('height', H);
      if (!pkt.length) return;
      const ys = pkt.map(p => p.y);
      const ticks = podzialki(Math.min(0, ...ys), Math.max(...ys), 4);
      const yMin = ticks[0], yMax = ticks[ticks.length - 1];
      const x = i => m.l + (W - m.l - m.r) * (pkt.length === 1 ? 0.5 : i / (pkt.length - 1));
      const y = v => m.t + (H - m.t - m.b) * (1 - (v - yMin) / (yMax - yMin || 1));
      const siatka = el('g', { class: 'siatka' }, svg);
      for (const t of ticks) {
        el('line', { x1: m.l, x2: W - m.r, y1: y(t), y2: y(t), class: t === 0 ? 'zero' : '' }, siatka);
        el('text', { x: m.l - 8, y: y(t) + 4, 'text-anchor': 'end' }, siatka).textContent = krotko(t);
      }
      // podpisy osi X: pierwszy dzień każdego miesiąca
      let ostatni = '';
      pkt.forEach((p, i) => {
        const mm = p.x.slice(0, 7);
        if (mm !== ostatni) { ostatni = mm; el('text', { x: x(i), y: H - 8, 'text-anchor': 'start' }, siatka).textContent = opcje.etykietaX(p.x); }
      });
      const d = pkt.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p.y).toFixed(1)}`).join('');
      const obszar = el('path', { d: `${d}L${x(pkt.length - 1)},${y(Math.max(0, yMin))}L${x(0)},${y(Math.max(0, yMin))}Z`, fill: opcje.kolor, 'fill-opacity': 0.1 }, svg);
      const l = el('path', { d, fill: 'none', stroke: opcje.kolor, 'stroke-width': 2, 'stroke-linejoin': 'round', 'stroke-linecap': 'round' }, svg);
      // Tylko przy pierwszym rysowaniu i tylko przezroczystość: animacja „rysowania” kreską przerywana
      // przerysowaniem (zmiana rozmiaru) zostawiała linię urwaną w połowie (zgłoszenie z 14.10, pkt 13).
      if (ruchOk() && !ramka.dataset.pokazany) {
        for (const e of [l, obszar]) {
          e.style.opacity = '0';
          requestAnimationFrame(() => { e.style.transition = 'opacity .5s ease-out'; e.style.opacity = '1'; });
        }
      }
      ramka.dataset.pokazany = '1';
      const ost = pkt.length - 1;
      el('circle', { cx: x(ost), cy: y(pkt[ost].y), r: 4, fill: opcje.kolor, stroke: 'var(--tlo)', 'stroke-width': 2 }, svg);
      const celownik = el('line', { y1: m.t, y2: H - m.b, class: 'celownik', visibility: 'hidden' }, svg);
      const kropka = el('circle', { r: 4, fill: opcje.kolor, stroke: 'var(--tlo)', 'stroke-width': 2, visibility: 'hidden' }, svg);
      const strefa = el('rect', { x: m.l, y: m.t, width: W - m.l - m.r, height: H - m.t - m.b, fill: 'transparent' }, svg);
      strefa.addEventListener('pointermove', ev => {
        const box = svg.getBoundingClientRect();
        const px = (ev.clientX - box.left) * (W / box.width);
        const i = Math.max(0, Math.min(ost, Math.round((px - m.l) / ((W - m.l - m.r) / Math.max(ost, 1)))));
        for (const e of [celownik]) { e.setAttribute('x1', x(i)); e.setAttribute('x2', x(i)); e.setAttribute('visibility', 'visible'); }
        kropka.setAttribute('cx', x(i)); kropka.setAttribute('cy', y(pkt[i].y)); kropka.setAttribute('visibility', 'visible');
        pp.pokaz(opcje.etykietaPelna(pkt[i].x), [{ nazwa: opcje.nazwa, wartosc: pelna(pkt[i].y), kolor: opcje.kolor },
          ...(opcje.dodatkowe ? opcje.dodatkowe(pkt[i]) : [])], ev.clientX - ramka.getBoundingClientRect().left, y(pkt[i].y));
      });
      strefa.addEventListener('pointerleave', () => { pp.ukryj(); celownik.setAttribute('visibility', 'hidden'); kropka.setAttribute('visibility', 'hidden'); });
    }
    rysuj();
    new ResizeObserver(() => rysuj()).observe(ramka);
  }

  // ---------- Paski poziome (ranking) ----------
  // opcje: { wiersze: [{nazwa, wartosci: {klucz: grosze}, naKlik}], serie: [{klucz, nazwa, kolor}], opisWiersza(w) }
  function ranking(ramka, opcje) {
    ramka.classList.add('wyk', 'ranking');
    const ukryte = new Set();
    const pp = podpowiedz(ramka);
    function rysuj() {
      legenda(ramka, opcje.serie, ukryte, rysuj);
      let lista = ramka.querySelector('.wyk-lista');
      if (!lista) { lista = document.createElement('div'); lista.className = 'wyk-lista'; ramka.appendChild(lista); }
      lista.replaceChildren();
      const widoczne = opcje.serie.filter(s => !ukryte.has(s.klucz));
      const max = Math.max(1, ...opcje.wiersze.flatMap(w => widoczne.map(s => Math.abs(w.wartosci[s.klucz] || 0))));
      for (const w of opcje.wiersze) {
        const r = document.createElement('button'); r.type = 'button'; r.className = 'wyk-wiersz';
        const n = document.createElement('span'); n.className = 'nazwa'; n.textContent = w.nazwa;
        const paski = document.createElement('span'); paski.className = 'paski';
        for (const s of widoczne) {
          const p = document.createElement('i'); p.style.background = s.kolor; p.style.width = '0%';
          paski.appendChild(p);
          const cel = `${100 * Math.abs(w.wartosci[s.klucz] || 0) / max}%`;
          ruchOk() ? requestAnimationFrame(() => requestAnimationFrame(() => { p.style.width = cel; })) : (p.style.width = cel);
        }
        const v = document.createElement('span'); v.className = 'wartosc'; v.textContent = opcje.opisWiersza(w);
        r.append(n, paski, v);
        r.addEventListener('pointermove', ev => {
          const box = ramka.getBoundingClientRect();
          pp.pokaz(w.nazwa, widoczne.map(s => ({ nazwa: s.nazwa, wartosc: pelna(w.wartosci[s.klucz] || 0), kolor: s.kolor })),
            ev.clientX - box.left, ev.clientY - box.top);
        });
        r.addEventListener('pointerleave', () => pp.ukryj());
        if (w.naKlik) r.addEventListener('click', w.naKlik);
        lista.appendChild(r);
      }
    }
    rysuj();
  }


  // ---------- Wykres cash flow jak w BS ----------
  // Słupki wpływów (zielone, w górę) i obciążeń (karmazynowe, w dół): pełna część to dokumenty i bank, jaśniejsza to plany.
  // Kreskowany słupek obok: saldo okresu. Linia: saldo narastające z wypełnieniem (zielone nad zerem, różowe pod zerem).
  // Pionowa pomarańczowa linia: okres bieżący (dzień stanu). Etykiety okresów u góry, oś kwot po lewej.
  // opcje: { okresy, wysokosc, serie?: {wplywy, obciazenia, saldo, narastajaco}, kolumny?: () => [{x, w}] (pozycje kolumn
  //   tabeli arkusza względem ramki), osY?: bool, etykiety?: bool, naKlik?(i), opis }
  let licznikBs = 0;
  function liczbaOs(gr) {
    const z = Math.round(gr / 100), a = Math.abs(z);
    return `${z < 0 ? '-' : ''}${String(a).replace(/\B(?=(\d{3})+(?!\d))/g, ' ')}`;
  }
  // Gładka linia przez punkty (monotoniczna, bez przestrzeleń poza wartości).
  function gladka(pkt) {
    if (pkt.length < 3) return pkt.map((p, i) => `${i ? 'L' : 'M'}${p[0]},${p[1]}`).join('');
    const n = pkt.length, dx = [], dy = [], m = [];
    for (let i = 0; i < n - 1; i++) { dx.push(pkt[i + 1][0] - pkt[i][0]); dy.push((pkt[i + 1][1] - pkt[i][1]) / (dx[i] || 1)); }
    m.push(dy[0]);
    for (let i = 1; i < n - 1; i++) m.push(dy[i - 1] * dy[i] <= 0 ? 0 : (dy[i - 1] + dy[i]) / 2);
    m.push(dy[n - 2]);
    let d = `M${pkt[0][0]},${pkt[0][1]}`;
    for (let i = 0; i < n - 1; i++) {
      const h = dx[i] / 3;
      d += `C${pkt[i][0] + h},${pkt[i][1] + m[i] * h} ${pkt[i + 1][0] - h},${pkt[i + 1][1] - m[i + 1] * h} ${pkt[i + 1][0]},${pkt[i + 1][1]}`;
    }
    return d;
  }

  function bs(ramka, opcje) {
    ramka.classList.add('wyk');
    const nr = ++licznikBs;
    const svg = ramka.querySelector('svg') || el('svg', { role: 'img', 'aria-label': opcje.opis || 'wykres cash flow' }, ramka);
    const pp = podpowiedz(ramka);
    function rysuj() {
      const o = opcje.okresy || [], n = o.length;
      const serie = { wplywy: true, obciazenia: true, saldo: true, narastajaco: true, ...(opcje.serie || {}) };
      const W = ramka.clientWidth || 600, H = opcje.wysokosc || 240;
      const osY = opcje.osY !== false, etyk = opcje.etykiety !== false;
      const m = { l: osY ? 52 : 4, r: 10, t: etyk ? 26 : 10, b: 10 };
      svg.replaceChildren();
      svg.setAttribute('viewBox', `0 0 ${W} ${H}`); svg.setAttribute('width', W); svg.setAttribute('height', H);
      if (!n) return;
      const kol = opcje.kolumny ? opcje.kolumny() : null;
      const krok = (W - m.l - m.r) / n;
      const cx = i => kol ? kol[i].x + kol[i].w / 2 : m.l + krok * (i + .5);
      const szer = i => kol ? kol[i].w : krok;
      let min = 0, max = 0;
      for (const x of o) {
        if (serie.wplywy) max = Math.max(max, x.wplywy);
        if (serie.obciazenia) min = Math.min(min, x.obciazenia);
        if (serie.saldo) { max = Math.max(max, x.saldo); min = Math.min(min, x.saldo); }
        if (serie.narastajaco) { max = Math.max(max, x.narastajaco); min = Math.min(min, x.narastajaco); }
      }
      const tiki = podzialki(min, max, 4);
      const lo = tiki[0], hi = tiki[tiki.length - 1];
      const y = v => m.t + (hi - v) / (hi - lo || 1) * (H - m.t - m.b);
      const k = c => kolor(c);
      const defs = el('defs', {}, svg);
      const kres = (id, c) => { const pt = el('pattern', { id, width: 4, height: 4, patternUnits: 'userSpaceOnUse', patternTransform: 'rotate(45)' }, defs);
        el('rect', { width: 4, height: 4, fill: c, 'fill-opacity': .18 }, pt); el('line', { x1: 0, y1: 0, x2: 0, y2: 4, stroke: c, 'stroke-width': 2.2 }, pt); };
      kres(`bs-k-plus-${nr}`, k('--wyk-plus')); kres(`bs-k-minus-${nr}`, k('--wyk-minus'));
      kres(`bs-k-umowa-${nr}`, k('--wyk-umowa')); kres(`bs-k-szacunek-${nr}`, k('--szary-seria'));   // pakiet 9: z umowy, szacunek
      const grad = (id, c, gora) => { const g = el('linearGradient', { id, x1: 0, y1: 0, x2: 0, y2: 1 }, defs);
        el('stop', { offset: '0%', 'stop-color': c, 'stop-opacity': gora ? .22 : .02 }, g); el('stop', { offset: '100%', 'stop-color': c, 'stop-opacity': gora ? .02 : .22 }, g); };
      grad(`bs-g-plus-${nr}`, k('--wyk-plus'), true); grad(`bs-g-minus-${nr}`, k('--wyk-minus'), false);
      const gs = (id, c1, c2) => { const g = el('linearGradient', { id, x1: 0, y1: 0, x2: 0, y2: 1 }, defs);
        el('stop', { offset: '0%', 'stop-color': c1 }, g); el('stop', { offset: '100%', 'stop-color': c2 }, g); };
      gs(`bs-s-plus-${nr}`, k('--wyk-plus'), k('--wyk-plus-2')); gs(`bs-s-minus-${nr}`, k('--wyk-minus-2'), k('--wyk-minus'));
      const y0 = y(0);
      const cg = el('clipPath', { id: `bs-c-gora-${nr}` }, defs); el('rect', { x: 0, y: 0, width: W, height: Math.max(0, y0) }, cg);
      const cd = el('clipPath', { id: `bs-c-dol-${nr}` }, defs); el('rect', { x: 0, y: y0, width: W, height: Math.max(0, H - y0) }, cd);
      // siatka i oś
      const siatka = el('g', { class: 'siatka' }, svg);
      const lewy = kol ? kol[0].x - 4 : osY ? m.l : 0, prawy = kol ? kol[n - 1].x + kol[n - 1].w : W - m.r;
      for (const t of tiki) {
        el('line', { x1: lewy, x2: prawy, y1: y(t), y2: y(t), class: t === 0 ? 'zero' : 'przerywana' }, siatka);
        if (osY) { const tx = el('text', { x: lewy - 4, y: y(t) + 3, 'text-anchor': 'end' }, siatka); tx.textContent = `${liczbaOs(t)} -`; }
      }
      if (etyk) {
        const co = Math.max(1, Math.ceil(n / Math.max(1, Math.floor((W - m.l) / 64))));
        o.forEach((x, i) => { if (i % co) return; const tx = el('text', { x: cx(i), y: 10, 'text-anchor': 'middle', class: 'os' }, svg); tx.textContent = x.etykieta; });
      }
      // słupki
      const g = el('g', {}, svg);
      const bw = Math.max(2, Math.min(18, szer(0) * (kol ? .26 : .3)));
      const slupek = (x, v1, v2, fill, op = 1) => { if (Math.abs(y(v1) - y(v2)) < .5) return;
        el('rect', { x, y: Math.min(y(v1), y(v2)), width: bw, height: Math.abs(y(v1) - y(v2)), fill, 'fill-opacity': op }, g); };
      o.forEach((x, i) => {
        const c = cx(i);
        if (serie.saldo && x.saldo) slupek(c - bw - 1, 0, x.saldo, `url(#bs-k-${x.saldo > 0 ? 'plus' : 'minus'}-${nr})`);
        const xs = serie.saldo ? c + 1 : c - bw / 2;
        // od osi: rzeczywiste (pełne), plany (jaśniejsze), z umowy i szacunek (kreskowane, własny kolor; pakiet 9)
        if (serie.wplywy && x.wplywy) {
          const um = x.wplywy_umowa || 0, rz = x.wplywy - (x.wplywy_plan || 0) - um;
          slupek(xs, 0, rz, `url(#bs-s-plus-${nr})`); slupek(xs, rz, rz + (x.wplywy_plan || 0), k('--wyk-plus'), .45);
          slupek(xs, x.wplywy - um, x.wplywy, `url(#bs-k-umowa-${nr})`);
        }
        if (serie.obciazenia && x.obciazenia) {
          const sz = x.obciazenia_szacunek || 0, rz = x.obciazenia - (x.obciazenia_plan || 0) - sz;
          slupek(xs, 0, rz, `url(#bs-s-minus-${nr})`); slupek(xs, rz, rz + (x.obciazenia_plan || 0), k('--wyk-minus'), .45);
          slupek(xs, x.obciazenia - sz, x.obciazenia, `url(#bs-k-szacunek-${nr})`);
        }
      });
      // linia salda narastającego z polem
      if (serie.narastajaco) {
        const pkt = o.map((x, i) => [cx(i), y(x.narastajaco)]);
        const d = gladka(pkt);
        const pole = `${d}L${pkt[n - 1][0]},${y0}L${pkt[0][0]},${y0}Z`;
        el('path', { d: pole, fill: `url(#bs-g-plus-${nr})`, 'clip-path': `url(#bs-c-gora-${nr})` }, svg);
        el('path', { d: pole, fill: `url(#bs-g-minus-${nr})`, 'clip-path': `url(#bs-c-dol-${nr})` }, svg);
        el('path', { d, fill: 'none', stroke: k('--wyk-linia'), 'stroke-width': 1.3 }, svg);
        if (n <= 60) pkt.forEach(p => el('circle', { cx: p[0], cy: p[1], r: 2, fill: k('--wyk-linia') }, svg));
      }
      // dziś
      const bi = o.findIndex(x => x.biezacy);
      if (bi >= 0) {
        el('line', { x1: cx(bi), x2: cx(bi), y1: etyk ? 14 : m.t, y2: H - 2, stroke: k('--dzis'), 'stroke-width': 2 }, svg);
        if (serie.narastajaco) el('circle', { cx: cx(bi), cy: y(o[bi].narastajaco), r: 3.5, fill: k('--dzis'), stroke: k('--tlo'), 'stroke-width': 1 }, svg);
      }
      // strefy podpowiedzi
      const strefy = el('g', { class: 'strefy' }, svg);
      o.forEach((x, i) => {
        const r = el('rect', { x: cx(i) - szer(i) / 2, y: m.t, width: szer(i), height: H - m.t - m.b, fill: 'transparent', class: opcje.naKlik ? 'klik' : '' }, strefy);
        r.addEventListener('pointerenter', () => {
          r.classList.add('aktywna');
          pp.pokaz(x.etykieta, [
            { nazwa: 'Saldo narastająco', wartosc: pelna(x.narastajaco) },
            { nazwa: 'Saldo okresu', wartosc: pelna(x.saldo) },
            { nazwa: 'Wpływy', wartosc: pelna(x.wplywy), kolor: k('--wyk-plus'), suma: true },
            { nazwa: 'Obciążenia', wartosc: pelna(x.obciazenia), kolor: k('--wyk-minus') },
            ...(x.wplywy_plan || x.obciazenia_plan ? [{ nazwa: 'w tym plany', wartosc: pelna((x.wplywy_plan || 0) + (x.obciazenia_plan || 0)) }] : []),
            ...(x.wplywy_umowa ? [{ nazwa: 'w tym z umowy', wartosc: pelna(x.wplywy_umowa), kolor: k('--wyk-umowa') }] : []),
            ...(x.obciazenia_szacunek ? [{ nazwa: 'w tym szacunek', wartosc: pelna(x.obciazenia_szacunek), kolor: k('--szary-seria') }] : [])], cx(i), m.t + 30);
        });
        r.addEventListener('pointerleave', () => { r.classList.remove('aktywna'); pp.ukryj(); });
        if (opcje.naKlik) r.addEventListener('click', () => opcje.naKlik(i));
      });
    }
    rysuj();
    if (!ramka.dataset.obserwowany) { ramka.dataset.obserwowany = '1'; new ResizeObserver(() => requestAnimationFrame(() => { if (ramka.isConnected) rysuj(); })).observe(ramka); }
    return { rysuj, ustaw(nowe) { Object.assign(opcje, nowe); rysuj(); } };
  }

  // ---------- Minimapa zakresu z suwakiem (BS: wykres panoramiczny) ----------
  // Miniatura salda narastającego dla całego zakresu, pomarańczowa ramka wybiera wycinek (przeciąganie środka przesuwa,
  // krawędzi zmienia szerokość, najwyżej `maks` okresów). Daty wycinka nad początkiem i pod końcem ramki.
  // opcje: { wartosci, etykiety, okno: [od, do] (indeksy włącznie), maks, naZmiane([od, do]) }
  function minimapa(ramka, opcje) {
    ramka.classList.add('minimapa');
    ramka.innerHTML = '<div class="daty-gora"><span></span></div><div class="tor"><svg aria-hidden="true"></svg><div class="okno" role="slider" tabindex="0" aria-label="Wycinek zakresu"><span class="uchwyt l"></span><span class="uchwyt p"></span></div></div><div class="daty"><span></span></div>';
    const svg = ramka.querySelector('svg'), okno = ramka.querySelector('.okno');
    const gora = ramka.querySelector('.daty-gora span'), dol = ramka.querySelector('.daty span');
    const n = opcje.wartosci.length, maks = opcje.maks || 120;
    let [a, b] = opcje.okno;
    function pokazOkno() {
      const W = ramka.clientWidth || 600;
      okno.style.left = `${a / n * 100}%`; okno.style.width = `${(b - a + 1) / n * 100}%`;
      gora.textContent = opcje.etykiety[a] || ''; dol.textContent = opcje.etykiety[b] || '';
      gora.style.marginLeft = `${Math.min(W - 80, a / n * W)}px`;
      dol.style.marginLeft = `${Math.max(0, Math.min(W - 80, (b + 1) / n * W - 60))}px`;
      okno.setAttribute('aria-valuetext', `${opcje.etykiety[a]} do ${opcje.etykiety[b]}`);
    }
    function rysuj() {
      const W = ramka.clientWidth || 600, H = 32;
      svg.replaceChildren(); svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
      const v = opcje.wartosci, lo = Math.min(0, ...v), hi = Math.max(0, ...v);
      const y = x => 3 + (hi - x) / (hi - lo || 1) * (H - 6);
      const pkt = v.map((x, i) => [(i + .5) / n * W, y(x)]);
      const d = gladka(pkt);
      el('path', { d: `${d}L${pkt[n - 1][0]},${y(0)}L${pkt[0][0]},${y(0)}Z`, fill: kolor('--wyk-plus'), 'fill-opacity': .14 }, svg);
      el('path', { d, fill: 'none', stroke: kolor('--wyk-linia'), 'stroke-width': 1 }, svg);
      pokazOkno();
    }
    let start = null;
    const ruch = e => {
      if (!start) return;
      const W = ramka.clientWidth || 600, d = Math.round((e.clientX - start.x) / (W / n));
      if (start.tryb === 'srodek') { const dl = start.b - start.a; a = Math.max(0, Math.min(n - 1 - dl, start.a + d)); b = a + dl; }
      else if (start.tryb === 'l') a = Math.max(0, Math.max(start.b - maks + 1, Math.min(start.b, start.a + d)));
      else b = Math.min(n - 1, Math.min(start.a + maks - 1, Math.max(start.a, start.b + d)));
      pokazOkno();
    };
    const koniec = () => { if (!start) return; const zmiana = start.a !== a || start.b !== b; start = null; if (zmiana) opcje.naZmiane([a, b]); };
    okno.addEventListener('pointerdown', e => {
      e.preventDefault();
      okno.setPointerCapture(e.pointerId);
      start = { x: e.clientX, a, b, tryb: e.target.classList.contains('l') ? 'l' : e.target.classList.contains('p') ? 'p' : 'srodek' };
    });
    okno.addEventListener('pointermove', ruch);
    okno.addEventListener('pointerup', koniec);
    okno.addEventListener('pointercancel', koniec);
    okno.addEventListener('keydown', e => {
      const dl = b - a;
      if (e.key === 'ArrowLeft' && a > 0) { a--; b = a + dl; } else if (e.key === 'ArrowRight' && b < n - 1) { a++; b = a + dl; } else return;
      e.preventDefault(); pokazOkno(); opcje.naZmiane([a, b]);
    });
    rysuj();
    new ResizeObserver(() => requestAnimationFrame(() => { if (ramka.isConnected) rysuj(); })).observe(ramka);
    return { ustaw(o2) { [a, b] = o2; pokazOkno(); } };
  }

  return { slupki, linia, ranking, bs, minimapa, kolor, pelna };
})();

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
      const widoczne = opcje.serie.filter(s => !ukryte.has(s.klucz));
      const stosy = [...new Set(widoczne.map(s => s.stos || s.klucz))];
      const n = opcje.kategorie.length;
      // zakres: sumy dodatnie i ujemne w stosach
      let min = 0, max = 0;
      for (let i = 0; i < n; i++) for (const st of stosy) {
        let plus = 0, minus = 0;
        for (const s of widoczne.filter(s => (s.stos || s.klucz) === st)) { const v = s.wartosci[i] || 0; v >= 0 ? plus += v : minus += v; }
        max = Math.max(max, plus); min = Math.min(min, minus);
      }
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

      // strefy najechania i kliknięcia: całe pasmo kategorii
      let strefy = svg.querySelector('g.strefy'); if (!strefy) strefy = el('g', { class: 'strefy' }, svg);
      strefy.replaceChildren();
      for (let i = 0; i < n; i++) {
        const r = el('rect', { x: m.l + pasmo * i, y: m.t, width: pasmo, height: H - m.t - m.b, fill: 'transparent', tabindex: 0,
          class: opcje.naKlik ? 'klik' : '' }, strefy);
        const pokaz = ev => {
          strefy.querySelectorAll('rect').forEach(z => z.classList.toggle('aktywna', z === r));
          const wiersze = widoczne.map(s => ({ nazwa: s.nazwa, wartosc: pelna(s.wartosci[i] || 0), kolor: s.kolor }));
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
      if (ruchOk()) {
        const len = l.getTotalLength();
        l.style.strokeDasharray = `${len}`; l.style.strokeDashoffset = `${len}`;
        obszar.style.opacity = '0';
        requestAnimationFrame(() => {
          l.style.transition = 'stroke-dashoffset .7s ease-out'; l.style.strokeDashoffset = '0';
          obszar.style.transition = 'opacity .7s ease-out'; obszar.style.opacity = '1';
        });
      }
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

  return { slupki, linia, ranking, kolor, pelna };
})();

'use strict';
// Ładowany bez defer, przed stylami strony: ustawia zapamiętany tryb jasny lub ciemny, zanim strona się narysuje.
try {
  const z = localStorage.getItem('finanse-tryb');
  if (z === 'dark' || z === 'light') document.documentElement.dataset.theme = z;
} catch (e) { /* bez pamięci wyboru obowiązuje tryb systemu */ }

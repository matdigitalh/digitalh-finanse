"""Pakiet 11: odczyty nowych ekranów w jednym miejscu (serwer woła ODCZYTY[ścieżka](con, parametry)).

- klienci/umowy: kolumny umowy do listy klientów (karta_klienta.lista),
- klienci/karta?nazwa=&rok=: karta klienta z umową (karta_klienta.karta),
- pulpit/alerty: alerty umów, licznik planów nieaktualnych (rytuał tygodniowy), liczba ostrzeżeń ustawień wierszy,
- rentownosc/przestawna?rok=&poziomy=&os=: rentowność budżetu jak w BS (przestawna.policz),
- budzet/ostrzezenia?arkusz=: ostrzeżenia o ustawieniach wierszy (ostrzezenia_wierszy.policz),
- budzet/przypiete: arkusze przypięte (pole „przypiety” arkusza z pakietu 4), budzet/widoki-arkusza?arkusz=: zapisane widoki
  arkusza (widoki.py).
Wszystko tylko do odczytu; zapis idzie zwykłymi wpisami w pliku zmian („umowa”, „widok”, przypięcie: „bud” op „arkusz”)."""
from . import karta_klienta, ostrzezenia_wierszy, przestawna, widoki


def _rok(q):
    r = q.get('rok', '')
    return r if len(r) == 4 and r.isdigit() else None


def nieaktualne_plany(con) -> dict:
    """Plany, którym minął dzień wystawienia, płatności albo realnej płatności, a nie mają rzeczywistej (A-INN-02, B-INNE-03).
    Te same warunki co lista Płatności z filtrami typ = plan i status aktualności = nieaktualna, więc licznik na pulpicie
    i lista po kliknięciu pokazują to samo."""
    r = con.execute("SELECT COUNT(*), COALESCE(SUM(p.brutto), 0) FROM bud_platnosc p JOIN bud_stan s ON s.platnosc = p.id"
                    " WHERE p.typ = 'plan' AND s.aktualnosc = 'Nieaktualna'").fetchone()
    return {'ile': r[0], 'kwota': r[1]}


def alerty_pulpitu(con, q=None) -> dict:
    o = ostrzezenia_wierszy.policz(con)
    k = karta_klienta.lista(con)
    return {'umowy': karta_klienta.alerty(con, k['klienci']), 'liczniki_umow': k['liczniki'], 'nieaktualne_plany': nieaktualne_plany(con),
            'ostrzezenia_wierszy': {'ile': o['ile'], 'wierszy': o['wierszy']}}


ODCZYTY = {
    'klienci/umowy': lambda con, q: karta_klienta.lista(con),
    'klienci/karta': lambda con, q: karta_klienta.karta(con, q.get('nazwa', ''), _rok(q)),
    'pulpit/alerty': alerty_pulpitu,
    'rentownosc/przestawna': lambda con, q: przestawna.policz(con, _rok(q), q.get('poziomy'), q.get('os') or 'budzet',
                                                               q.get('folder') or None),
    'budzet/ostrzezenia': lambda con, q: ostrzezenia_wierszy.policz(con, q.get('arkusz') or None),
    'budzet/przypiete': lambda con, q: {'arkusze': widoki.przypiete(con)},
    'budzet/widoki-arkusza': lambda con, q: {'widoki': widoki.arkusza(con, q.get('arkusz', ''))},
}


def sprawdz_odwolania(con, typ: str, dane: dict):
    """Widok arkusza musi wskazywać istniejący arkusz (nic zmyślonego nie trafia do pliku zmian)."""
    aid = None
    if typ == 'widok' and dane.get('ekran') == 'arkusz' and not dane.get('usun'):
        aid = (dane.get('parametry') or {}).get('arkusz')
        if not aid:
            raise ValueError('widok arkusza: brak arkusza')
    if aid is not None and not con.execute('SELECT 1 FROM bud_arkusz WHERE id = ?', (aid,)).fetchone():
        raise ValueError('nie ma takiego arkusza')

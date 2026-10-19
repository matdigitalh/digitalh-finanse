"""Strażnik zasady 1 briefu: w repo nie ma danych finansowych. Plus zasada 8: bez długich myślników w UI."""
import subprocess
import unittest
from pathlib import Path

APKA = Path(__file__).resolve().parent.parent
ZAKAZANE = ('.sqlite', '.sqlite3', '.db', '.csv', '.xlsx', '.xls', '.pdf', '.jsonl')


def pliki_w_gicie():
    wynik = subprocess.run(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '.'],
                           cwd=APKA, capture_output=True, text=True, check=True)
    return [l for l in wynik.stdout.splitlines() if l]


def pliki_interfejsu():
    """Kod interfejsu (HTML, JS, CSS) także w podkatalogach; font i jego licencja (OFL) to nie kod."""
    return [p for p in (APKA / 'web').rglob('*') if p.suffix in ('.html', '.js', '.css')]


class TestRepo(unittest.TestCase):
    def test_brak_plikow_z_danymi(self):
        zle = [p for p in pliki_w_gicie() if p.lower().endswith(ZAKAZANE)]
        self.assertEqual(zle, [], 'pliki z danymi trafiłyby do repo')

    def test_bez_dlugich_myslnikow_w_interfejsie(self):
        for p in pliki_interfejsu():
            self.assertNotIn('—', p.read_text(encoding='utf-8'), p.name)

    def test_brak_zewnetrznych_adresow_w_interfejsie(self):
        for p in pliki_interfejsu():
            tresc = p.read_text(encoding='utf-8')
            # przestrzeń nazw SVG to identyfikator, nie adres do pobrania
            self.assertNotRegex(tresc, r'https?://(?!127\.0\.0\.1|www\.w3\.org/2000/svg\b)', p.name)

    def test_font_lokalnie_z_licencja(self):
        self.assertTrue((APKA / 'web' / 'fonty' / 'RobotoFlex.woff2').is_file())
        self.assertIn('SIL OPEN FONT LICENSE', (APKA / 'web' / 'fonty' / 'OFL.txt').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()

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


class TestRepo(unittest.TestCase):
    def test_brak_plikow_z_danymi(self):
        zle = [p for p in pliki_w_gicie() if p.lower().endswith(ZAKAZANE)]
        self.assertEqual(zle, [], 'pliki z danymi trafiłyby do repo')

    def test_bez_dlugich_myslnikow_w_interfejsie(self):
        for p in (APKA / 'web').iterdir():
            self.assertNotIn('—', p.read_text(encoding='utf-8'), p.name)

    def test_brak_zewnetrznych_adresow_w_interfejsie(self):
        for p in (APKA / 'web').iterdir():
            tresc = p.read_text(encoding='utf-8')
            self.assertNotRegex(tresc, r'https?://(?!127\.0\.0\.1)', p.name)


if __name__ == '__main__':
    unittest.main()

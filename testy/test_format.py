import unittest

from finanse.format import data_iso, grosze, norm, zl


class TestFormat(unittest.TestCase):
    def test_grosze_ing(self):
        self.assertEqual(grosze('-2460,00'), -246000)
        self.assertEqual(grosze('101 302,80'), 10130280)
        self.assertEqual(grosze('1.234,56'), 123456)
        self.assertEqual(grosze(''), 0)

    def test_grosze_kropka(self):
        self.assertEqual(grosze('8246.01', przecinek_dziesietny=False), 824601)
        self.assertEqual(grosze('0.1', przecinek_dziesietny=False), 10)

    def test_grosze_liczby_z_excela_bez_bledu_zmiennoprzecinkowego(self):
        self.assertEqual(grosze(0.1 + 0.2), 30)
        self.assertEqual(grosze(1338.75), 133875)

    def test_zle_dane(self):
        with self.assertRaises(ValueError):
            grosze('abc')

    def test_zl(self):
        self.assertEqual(zl(1234567), '12 345,67 zł')
        self.assertEqual(zl(123456), '1 234,56 zł')
        self.assertEqual(zl(-5), '-0,05 zł')
        self.assertEqual(zl(10000000, waluta=False), '100 000,00')

    def test_data(self):
        self.assertEqual(data_iso('2026-10-13'), '2026-10-13')
        self.assertEqual(data_iso('13.10.2026'), '2026-10-13')
        self.assertIsNone(data_iso(''))
        with self.assertRaises(ValueError):
            data_iso('2026-13-45')

    def test_norm(self):
        self.assertEqual(norm('DIGITALH SPÓŁKA Z O.O.'), 'digitalh spolka z o o')
        self.assertEqual(norm('Łódź'), 'lodz')


if __name__ == '__main__':
    unittest.main()

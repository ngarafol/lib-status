"""Testovi parsera — pokreću se običnim Pythonom, bez Home Assistant instalacije.

    python -m unittest discover -s tests -t .

`custom_components/knjiznica_metelgrad/__init__.py` uvozi Home Assistant, pa se zato
čisti `parser.py` (bez HA i bez mreže) učitava izravno iz putanje.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from datetime import date
from pathlib import Path
from types import ModuleType


def _load_parser() -> ModuleType:
    path = (
        Path(__file__).resolve().parent.parent
        / "custom_components"
        / "knjiznica_metelgrad"
        / "parser.py"
    )
    spec = importlib.util.spec_from_file_location("metelgrad_parser", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


parser = _load_parser()

BASE_URL = "https://library.foi.hr"

# SINTETIČKI HTML — nije snimka stvarne stranice. Opisuje oblik koji parser očekuje:
# tablica posudbi, datum posudbe pa rok vraćanja, i poveznica `page=prod` za produženje.
SYNTHETIC_PAGE = """
<html lang="hr"><body>
  <h2>Moje posudbe</h2>
  <table class="table table-striped table-hover">
    <thead>
      <tr>
        <th>Naslov</th><th>Autor</th><th>Signatura</th>
        <th>Datum posudbe</th><th>Rok vraćanja</th><th>Produženje</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td><a href="/lib/knjiga.php?B=11&amp;K=0000123">Mali princ</a></td>
        <td>Saint-Exupéry, Antoine de</td>
        <td>D-123</td>
        <td>20.09.2026.</td>
        <td>18.10.2026.</td>
        <td><a href="/lib/korisnik.php?page=prod&amp;B=11&amp;H=&amp;N=0000123">Produži</a></td>
      </tr>
      <tr>
        <td><a href="/lib/knjiga.php?B=11&amp;K=0000456">Dnevnik Pauline P.</a></td>
        <td>Kušec, Sanja</td>
        <td>D-456</td>
        <td>1.10.2026.</td>
        <td>29. 10. 2026.</td>
        <td><a href="/lib/korisnik.php?page=prod&amp;B=11&amp;H=&amp;N=0000456">Produži</a></td>
      </tr>
      <tr>
        <td>Zagonetni dvorac</td>
        <td>Bilić, Tea</td>
        <td>D-789</td>
        <td></td>
        <td></td>
        <td></td>
      </tr>
      <tr>
        <td>Bajke za laku noć</td>
        <td>Nepoznati autor</td>
        <td>D-999</td>
        <td></td>
        <td></td>
        <td><a href="/lib/korisnik.php?page=prod&amp;B=11&amp;H=&amp;N=0000999">Produži</a></td>
      </tr>
    </tbody>
  </table>
</body></html>
"""

# Odgovor koji stranica daje neprijavljenom korisniku (provjereno na živoj stranici).
LOGGED_OUT_HTML = "Pregled je dozvoljen samo za prijavljene korisnike!"


class ParseDateTest(unittest.TestCase):
    def test_croatian_dates(self) -> None:
        self.assertEqual(parser.parse_date("18.10.2026."), date(2026, 10, 18))
        self.assertEqual(parser.parse_date("5. 3. 2027."), date(2027, 3, 5))
        self.assertEqual(
            parser.parse_date("posudba: 1.10.2026., rok 29.10.2026."), date(2026, 10, 1)
        )

    def test_invalid_dates(self) -> None:
        self.assertIsNone(parser.parse_date(""))
        self.assertIsNone(parser.parse_date("nema datuma"))
        self.assertIsNone(parser.parse_date("32.13.2026."))


class LoggedOutTest(unittest.TestCase):
    def test_marker_is_recognised(self) -> None:
        self.assertTrue(parser.is_logged_out(LOGGED_OUT_HTML))

    def test_real_page_is_not_logged_out(self) -> None:
        self.assertFalse(parser.is_logged_out(SYNTHETIC_PAGE))


class ParseLoansTest(unittest.TestCase):
    def setUp(self) -> None:
        self.loans = parser.parse_loans(SYNTHETIC_PAGE, BASE_URL)

    def test_only_real_loans_are_kept(self) -> None:
        # Redak bez datuma i bez produženja ("Zagonetni dvorac") se preskače,
        # a redak zaglavlja ne završi kao posudba.
        self.assertEqual(
            [loan.title for loan in self.loans],
            ["Mali princ", "Dnevnik Pauline P.", "Bajke za laku noć"],
        )

    def test_fields(self) -> None:
        loan = self.loans[0]
        self.assertEqual(loan.author, "Saint-Exupéry, Antoine de")
        self.assertEqual(loan.due_on, date(2026, 10, 18))
        self.assertEqual(
            loan.renew_url,
            "https://library.foi.hr/lib/korisnik.php?page=prod&B=11&H=&N=0000123",
        )
        self.assertTrue(loan.renewable)

    def test_due_column_not_borrow_column(self) -> None:
        # 29.10. je rok vraćanja, 01.10. je datum posudbe.
        self.assertEqual(self.loans[1].due_on, date(2026, 10, 29))

    def test_loan_without_date_is_kept_if_renewable(self) -> None:
        loan = self.loans[2]
        self.assertIsNone(loan.due_on)
        self.assertTrue(loan.renewable)

    def test_empty_page(self) -> None:
        self.assertEqual(parser.parse_loans("<html><body>Nema posudbi</body></html>", BASE_URL), [])


class LoanTest(unittest.TestCase):
    def test_days_until(self) -> None:
        loan = parser.Loan("Mali princ", None, date(2026, 10, 18), "https://x")
        self.assertEqual(loan.days_until(date(2026, 10, 13)), 5)
        self.assertEqual(loan.days_until(date(2026, 10, 20)), -2)

    def test_days_until_without_due_date(self) -> None:
        loan = parser.Loan("Bez roka", None, None, None)
        self.assertIsNone(loan.days_until(date(2026, 10, 13)))

    def test_as_dict_is_serialisable(self) -> None:
        loan = parser.Loan("Mali princ", "Saint-Exupéry", date(2026, 10, 18), None)
        self.assertEqual(
            loan.as_dict(date(2026, 10, 13)),
            {
                "title": "Mali princ",
                "author": "Saint-Exupéry",
                "due_on": "2026-10-18",
                "days_left": 5,
                "renewable": False,
            },
        )


if __name__ == "__main__":
    unittest.main()

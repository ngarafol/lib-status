"""Testovi parsera.

.venv-ha/bin/pytest tests/test_parser.py
"""

from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path

from custom_components.knjiznica_metelgrad import parser

# Snimke stvarnih stranica (izvan gita). Ako ih nema, ti se testovi preskaču.
RECON = Path(__file__).resolve().parent.parent / "recon"

# SINTETIČKI HTML — nije snimka stvarne stranice, ali prati njen stvarni oblik:
# posudba je div.col-sm-12 s elementom "Rok vraćanja", naslov je a.knaslink, a
# autor span.anaso. Naslovi i datumi su izmišljeni.
CITAM_HTML = """
<html><body>
<div class="row">
  <div class="col-sm-12">
    <div class="row">
      <div class="col-sm-2"><div id="gradie">
        <a href="https://library.foi.hr/lib/knjiga.php?B=11&amp;sqlx=D10001"><img src="1.png"></a>
      </div></div>
      <div class="col-sm-10">
        <div class="row">
          <div class="col-sm-3"><span class="txx12">10.10.2026</span></div>
          <div class="col-sm-9"><div class="txx12">Rok vraćanja: 01.11.2026</div></div>
        </div>
        <div class="col-sm-12">
          <div><span class="anaso">Autor, Ante</span></div>
          <div><a class="knaslink"
             href="https://library.foi.hr/lib/knjiga.php?B=11&amp;sqlx=D10001&amp;sqlid=11&amp;sqlnivo=&amp;H=">Mali
             princ</a></div>
          <div><span class="txx11">Zagreb : Nakladnik, 2017. -</span></div>
        </div>
      </div>
    </div>
  </div>
  <div class="col-sm-12">
    <div class="row">
      <div class="col-sm-2"><div id="gradie">
        <a href="https://library.foi.hr/lib/knjiga.php?B=11&amp;sqlx=D10002"><img src="2.png"></a>
      </div></div>
      <div class="col-sm-10">
        <div class="row">
          <div class="col-sm-3"><span class="txx12">1.10.2026.</span></div>
          <div class="col-sm-9"><div class="txx12">Rok vraćanja: 29. 10. 2026.</div></div>
        </div>
        <div class="col-sm-12">
          <div><span class="anaso">Autorica, Ana</span></div>
          <div><a class="knaslink"
             href="https://library.foi.hr/lib/knjiga.php?B=11&amp;sqlx=D10002&amp;sqlid=11&amp;sqlnivo=&amp;H=">Dnevnik</a></div>
        </div>
      </div>
    </div>
  </div>
  <div class="col-sm-12">
    <div class="row"><div class="col-sm-10"><div class="txx12">Bez roka vraćanja</div></div></div>
  </div>
</div>
</body></html>
"""

PROD_HTML = """
<html><body>
<form method="post" name="formo" id="formo"
      action="https://library.foi.hr/lib/korisnik.php?page=prod">
  <input type="hidden" name="H" value="">
  <input type="hidden" name="B" value="11">
  <input type="hidden" name="zahtjev" value="1">
  <div class="row">
    <div class="col-sm-12">
      <div class="row">
        <div class="col-sm-4 txx10"><strong></strong></div>
        <div class="col-sm-8 txx10">Rok vraćanja: 01.11.2026.</div>
      </div>
      <div class="col-8"><span class="txx10">Autor, Ante</span><br></div>
      <div class="col-4 txx10">Produlji posudbu
        <label class="checkbox"><input type="checkbox" name="prod[]" value="MK27317"><span
          class="success"></span></label>
      </div>
      <div class="col-sm-12"><a class="knaslink"
        href="https://library.foi.hr/lib/knjiga.php?B=11&amp;item=D10001&amp;nivo=%20&amp;H="><b>Mali
        princ</b></a></div>
      <div class="col-sm-12"><span class="txx10">Zagreb : Nakladnik, 2017.</span></div>
    </div>
    <div class="col-sm-12">
      <div class="row">
        <div class="col-sm-4 txx10"><strong></strong></div>
        <div class="col-sm-8 txx10">Rok vraćanja: 29.10.2026.</div>
      </div>
      <div class="col-8"><span class="txx10">Autorica, Ana</span><br></div>
      <div class="col-4 txx10">Produlji posudbu
        <label class="checkbox"><input type="checkbox" name="prod[]" value="MK22508"><span
          class="success"></span></label>
      </div>
      <div class="col-sm-12"><a class="knaslink"
        href="https://library.foi.hr/lib/knjiga.php?B=11&amp;item=D10002&amp;nivo=%20&amp;H="><b>Dnevnik</b></a></div>
    </div>
  </div>
  <input type="submit" name="btnLogin" value=" Pošalji zahtjev za produljenje ">
</form>
</body></html>
"""

# Odgovor koji stranica daje neprijavljenom korisniku (provjereno na živoj stranici).
LOGGED_OUT_HTML = "Pregled je dozvoljen samo za prijavljene korisnike!"


class ParseDateTest(unittest.TestCase):
    def test_croatian_dates(self) -> None:
        self.assertEqual(parser.parse_date("18.10.2026."), date(2026, 10, 18))
        self.assertEqual(parser.parse_date("5. 3. 2027."), date(2027, 3, 5))
        self.assertEqual(parser.parse_date("Rok vraćanja: 01.11.2026."), date(2026, 11, 1))

    def test_invalid_dates(self) -> None:
        self.assertIsNone(parser.parse_date(""))
        self.assertIsNone(parser.parse_date("nema datuma"))
        self.assertIsNone(parser.parse_date("32.13.2026."))


class LoggedOutTest(unittest.TestCase):
    def test_marker_is_recognised(self) -> None:
        self.assertTrue(parser.is_logged_out(LOGGED_OUT_HTML))


class ParseLoansTest(unittest.TestCase):
    def setUp(self) -> None:
        self.loans = parser.parse_loans(CITAM_HTML)

    def test_only_loan_blocks_are_returned(self) -> None:
        # Unutarnji div.col-sm-12 (autor/naslov) nije zasebna posudba, a blok bez
        # "Rok vraćanja" se preskače.
        self.assertEqual([loan.title for loan in self.loans], ["Mali princ", "Dnevnik"])

    def test_fields(self) -> None:
        loan = self.loans[0]
        self.assertEqual(loan.title, "Mali princ")
        self.assertEqual(loan.author, "Autor, Ante")
        self.assertEqual(loan.due_on, date(2026, 11, 1))
        self.assertEqual(loan.record_key, "D10001")
        self.assertIsNone(loan.renew_id)
        self.assertFalse(loan.renewable)

    def test_due_date_is_not_borrow_date(self) -> None:
        # 10.10.2026. je datum posudbe, 01.11.2026. rok vraćanja.
        self.assertEqual(self.loans[0].due_on, date(2026, 11, 1))
        self.assertEqual(self.loans[1].due_on, date(2026, 10, 29))

    def test_empty_page(self) -> None:
        self.assertEqual(parser.parse_loans("<html><body>Nema posudbi</body></html>"), [])


class ParseRenewPageTest(unittest.TestCase):
    def setUp(self) -> None:
        self.page = parser.parse_renew_page(PROD_HTML)
        assert self.page is not None

    def test_form(self) -> None:
        self.assertEqual(self.page.action, "https://library.foi.hr/lib/korisnik.php?page=prod")
        self.assertEqual(self.page.checkbox_name, "prod[]")
        self.assertEqual(self.page.hidden, {"H": "", "B": "11", "zahtjev": "1"})
        self.assertEqual(self.page.submit, (("btnLogin", " Pošalji zahtjev za produljenje "),))

    def test_options(self) -> None:
        self.assertEqual(
            [(option.renew_id, option.title, option.record_key) for option in self.page.options],
            [("MK27317", "Mali princ", "D10001"), ("MK22508", "Dnevnik", "D10002")],
        )
        self.assertEqual(self.page.options[0].due_on, date(2026, 11, 1))

    def test_form_data_for_post(self) -> None:
        self.assertEqual(
            self.page.form_data(["MK27317"]),
            {
                "H": "",
                "B": "11",
                "zahtjev": "1",
                "prod[]": ["MK27317"],
                "btnLogin": " Pošalji zahtjev za produljenje ",
            },
        )

    def test_page_without_form(self) -> None:
        self.assertIsNone(parser.parse_renew_page("<html><body>Ništa</body></html>"))


class MatchRenewOptionsTest(unittest.TestCase):
    """Uparivanje posudbi s ponuđenim primjercima (bez HTML-a)."""

    def _option(self, renew_id: str, title: str, due_on: date, record_key: str | None):
        return parser.RenewOption(renew_id, title, due_on, record_key)

    def _page(self, *options) -> parser.RenewPage:
        return parser.RenewPage(
            action="https://library.foi.hr/lib/korisnik.php?page=prod",
            checkbox_name="prod[]",
            hidden={"B": "11"},
            submit=(),
            options=options,
        )

    def _loan(self, title: str, due_on: date, record_key: str | None, renew_id=None):
        return parser.Loan(title, None, due_on, record_key, renew_id)

    def test_same_record_key_different_dates(self) -> None:
        # Isti naslov posuđen dvaput: razlikuje se po roku vraćanja.
        first = self._option("MK1", "Mali princ", date(2026, 11, 1), "D1")
        second = self._option("MK2", "Mali princ", date(2026, 12, 1), "D1")
        page = self._page(first, second)

        loan = self._loan("Mali princ", date(2026, 12, 1), "D1")
        self.assertEqual(parser.find_option(loan, page).renew_id, "MK2")

    def test_match_by_title_when_no_record_key(self) -> None:
        page = self._page(self._option("MK9", "Dnevnik", date(2026, 11, 1), None))
        loan = self._loan("  dnevnik ", date(2026, 11, 1), None)
        self.assertEqual(parser.find_option(loan, page).renew_id, "MK9")

    def test_no_match(self) -> None:
        page = self._page(self._option("MK9", "Dnevnik", date(2026, 11, 1), "D9"))
        self.assertIsNone(parser.find_option(self._loan("Nema me", date(2026, 11, 1), "D7"), page))

    def test_with_renew_ids(self) -> None:
        page = self._page(
            self._option("MK1", "Mali princ", date(2026, 11, 1), "D1"),
            self._option("MK2", "Dnevnik", date(2026, 10, 29), "D2"),
        )
        loans = [
            self._loan("Mali princ", date(2026, 11, 1), "D1"),
            self._loan("Nema me", date(2026, 11, 1), "D7"),
        ]
        linked = parser.with_renew_ids(loans, page)
        self.assertEqual([loan.renew_id for loan in linked], ["MK1", None])
        self.assertTrue(linked[0].renewable)
        self.assertFalse(linked[1].renewable)

    def test_with_renew_ids_without_page(self) -> None:
        loans = [self._loan("Mali princ", date(2026, 11, 1), "D1", renew_id="MK1")]
        self.assertEqual([loan.renew_id for loan in parser.with_renew_ids(loans, None)], [None])


class LoanTest(unittest.TestCase):
    def test_days_until(self) -> None:
        loan = parser.Loan("Mali princ", None, date(2026, 10, 18), "D1")
        self.assertEqual(loan.days_until(date(2026, 10, 13)), 5)
        self.assertEqual(loan.days_until(date(2026, 10, 20)), -2)


@unittest.skipUnless((RECON / "citam.html").exists(), "nema snimke u recon/")
class RealSnapshotTest(unittest.TestCase):
    """Provjera parsera na stvarnoj snimci (snimka ostaje izvan gita)."""

    def test_real_loan_page_parses(self) -> None:
        html = (RECON / "citam.html").read_text(encoding="utf-8", errors="replace")
        loans = parser.parse_loans(html)
        self.assertGreater(len(loans), 0)
        self.assertTrue(all(loan.title for loan in loans))
        self.assertTrue(all(loan.due_on for loan in loans))
        self.assertTrue(all(loan.record_key for loan in loans))
        self.assertEqual(len({loan.title for loan in loans}), len(loans))

    @unittest.skipUnless((RECON / "prod.html").exists(), "nema snimke u recon/")
    def test_real_renew_page_parses(self) -> None:
        html = (RECON / "prod.html").read_text(encoding="utf-8", errors="replace")
        page = parser.parse_renew_page(html)
        self.assertIsNotNone(page)
        assert page is not None
        citam = parser.parse_loans(
            (RECON / "citam.html").read_text(encoding="utf-8", errors="replace")
        )
        self.assertEqual(len(page.options), len(citam))
        linked = parser.with_renew_ids(citam, page)
        self.assertTrue(all(loan.renewable for loan in linked))


if __name__ == "__main__":
    unittest.main()

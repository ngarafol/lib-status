"""Testovi HTTP klijenta — bez mreže (lažna sesija bilježi zahtjeve).

Provjeravaju ugovor prema knjižnici: POST prijave mora nositi `Referer`, jer bez
njega server vraća 403, što se u Home Assistantu prikazivalo kao "ne mogu se
spojiti" umjesto greške prijave.

    .venv-ha/bin/pytest tests/test_api.py
"""

from __future__ import annotations

import unittest
from datetime import date
from typing import Any

from custom_components.knjiznica_metelgrad.api import MetelgradClient
from custom_components.knjiznica_metelgrad.const import LOGIN_PATH, USER_PAGES_URL
from custom_components.knjiznica_metelgrad.parser import Loan

CITAM_HTML = """
<html><body>
  <div class="col-sm-12">
    <div class="row">
      <div class="col-sm-3"><span class="txx12">10.10.2026</span></div>
      <div class="col-sm-9"><div class="txx12">Rok vraćanja: 01.11.2026</div></div>
    </div>
    <div class="col-sm-12">
      <span class="anaso">Saint-Exupéry, Antoine de</span>
      <a class="knaslink"
         href="https://library.foi.hr/lib/knjiga.php?B=11&amp;sqlx=D10001">Mali princ</a>
    </div>
  </div>
</body></html>
"""

PROD_HTML = """
<html><body>
<form method="post" action="korisnik.php?page=prod">
  <input type="hidden" name="H" value="">
  <input type="hidden" name="B" value="11">
  <input type="hidden" name="zahtjev" value="1">
  <div class="col-sm-12">
    <div class="col-sm-8 txx10">Rok vraćanja: 01.11.2026.</div>
    <label class="checkbox"><input type="checkbox" name="prod[]" value="MK27317"></label>
    <a class="knaslink"
       href="https://library.foi.hr/lib/knjiga.php?B=11&amp;item=D10001">Mali princ</a>
    <input type="submit" name="btnLogin" value=" Pošalji zahtjev za produljenje ">
  </div>
</form>
</body></html>
"""


class _FakeResponse:
    def __init__(self, body: str) -> None:
        self._body = body

    async def __aenter__(self) -> _FakeResponse:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    def raise_for_status(self) -> None:
        pass

    async def text(self) -> str:
        return self._body


class _FakeSession:
    """Bilježi (metoda, url, kwargs) i vraća zadana tijela redom."""

    def __init__(self, *bodies: str) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self._bodies = list(bodies)

    def _body(self) -> str:
        return self._bodies.pop(0) if len(self._bodies) > 1 else self._bodies[0]

    def post(self, url: str, **kwargs: Any) -> _FakeResponse:
        self.calls.append(("POST", url, kwargs))
        return _FakeResponse(self._body())

    def get(self, url: str, **kwargs: Any) -> _FakeResponse:
        self.calls.append(("GET", url, kwargs))
        return _FakeResponse(self._body())


class ClientTest(unittest.IsolatedAsyncioTestCase):
    def _client(self, *bodies: str) -> tuple[MetelgradClient, _FakeSession]:
        session = _FakeSession(*bodies)
        return MetelgradClient(session, "ana@example.com", "tajna", "11"), session

    async def test_login_sends_referer_and_form_fields(self) -> None:
        client, session = self._client("")

        await client.async_login()

        method, url, kwargs = session.calls[0]
        self.assertEqual(method, "POST")
        self.assertTrue(url.endswith(LOGIN_PATH))
        self.assertEqual(kwargs["headers"]["Referer"], USER_PAGES_URL)
        self.assertEqual(
            kwargs["data"],
            {
                "username": "ana@example.com",
                "password": "tajna",
                "B": "11",
                "bookid": "",
                "refURL": USER_PAGES_URL,
                "navo": "1",
            },
        )

    async def test_fetch_sends_referer_on_both_pages(self) -> None:
        client, session = self._client(CITAM_HTML, PROD_HTML)

        loans = await client.async_fetch_loans()

        self.assertEqual([call[0] for call in session.calls], ["GET", "GET"])
        referers = [call[2]["headers"]["Referer"] for call in session.calls]
        self.assertEqual(referers, [USER_PAGES_URL, USER_PAGES_URL])
        self.assertEqual([loan.title for loan in loans], ["Mali princ"])
        self.assertEqual(loans[0].renew_id, "MK27317")

    async def test_renew_posts_to_form_action_with_referer(self) -> None:
        client, session = self._client(PROD_HTML)
        loan = Loan("Mali princ", "Saint-Exupéry", date(2026, 11, 1), "D10001")

        await client.async_renew(loan)

        self.assertEqual([call[0] for call in session.calls], ["GET", "POST"])
        _, url, kwargs = session.calls[1]
        self.assertEqual(url, "https://library.foi.hr/lib/korisnik.php?page=prod")
        self.assertIn("page=prod&B=11", kwargs["headers"]["Referer"])
        self.assertEqual(kwargs["data"]["prod[]"], ["MK27317"])
        self.assertEqual(kwargs["data"]["zahtjev"], "1")
        self.assertEqual(kwargs["data"]["B"], "11")


if __name__ == "__main__":
    unittest.main()
